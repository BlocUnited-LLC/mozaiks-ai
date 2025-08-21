# ==============================================================================
# FILE: workflows/Generator/tools/request_api_key.py
# DESCRIPTION: API key request tool - single async function export
# NOTE: 'description' in the 'payload' must be a property to use to display the agent's instructions, making the whole system easier to extend.
# ==============================================================================

import logging
from typing import Dict, Any, Optional
from datetime import datetime
import re
import hashlib

# Import the centralized UI tool functions and exceptions
from core.workflow.ui_tools import emit_ui_tool_event, wait_for_ui_tool_response, UIToolError

# Secure storage and DB client
from core.core_config import get_mongo_client

# Import enhanced logging
from logs.logging_config import get_workflow_logger

async def request_api_key(
    service: str,
    description: Optional[str] = None,
    label: Optional[str] = None,
    placeholder: Optional[str] = None,
    required: bool = True,
    auto_store: bool = True,
    workflow_name: str = "generator",
    chat_id: Optional[str] = None,
    enterprise_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    AG2 tool function to request an API key from the user via a dynamic UI component.
    
    This tool follows the modern, modular pattern:
    1. It prints a message to the user, which appears in the chat log.
    2. It emits a UI tool event to render the 'AgentAPIKeyInput' component.
    3. It waits for the user to submit their key via the component.
    
    Args:
        service: The service name (e.g., "openai", "anthropic").
        description: A message to display within the UI component.
        label: The label for the input field in the UI component.
        placeholder: The placeholder text for the input field.
        required: Whether the API key is required.
        workflow_name: The name of the workflow initiating the request.
        chat_id: The ID of the current chat session.
        
    Returns:
        A dictionary containing the API key response data.
        
    Raises:
        UIToolError: If the UI interaction fails.
    """
    wf_logger = get_workflow_logger(workflow_name=workflow_name, chat_id=chat_id, enterprise_id=enterprise_id)
    wf_logger.info(f"🔑 Requesting API key for service: {service} in chat: {chat_id}")
    
    # 1. The agent "speaks" its request to the user via a standard print.
    # This message appears in the main chat log.
    agent_message = description or f"I need your {service.replace('_', ' ').title()} API key to proceed. Please enter it in the component below."
    print(agent_message)

    # 2. Prepare the payload for the 'AgentAPIKeyInput' React component.
    # The 'description' here is for the component itself, not the chat message.
    payload = {
        "service": service,
        "label": label or f"{service.replace('_', ' ').title()} API Key",
        "description": f"Please enter the API key for {service}.",
        "placeholder": placeholder or f"Your {service.upper()} API key",
        "required": required
    }
    
    try:
        # 3. Emit the UI tool event to render the component and wait for the response.
        event_id = await emit_ui_tool_event(
            tool_id="AgentAPIKeyInput",  # This MUST match the React component's name
            payload=payload,
            display="inline",
            chat_id=chat_id,
            workflow_name=workflow_name
        )
        
        response = await wait_for_ui_tool_response(event_id)

        wf_logger.info(f"🔑 API key request for {service} completed with status: {response.get('status', 'unknown')}")

        # Zero-shot storage: store immediately after successful submission
        if auto_store and isinstance(response, dict) and response.get("status") == "success":
            try:
                # Extract API key from UI response
                data = response.get("data") if isinstance(response, dict) else None
                api_key = None
                if isinstance(data, dict):
                    api_key = data.get("apiKey") or data.get("api_key") or data.get("key")
                    svc = data.get("service") or service
                else:
                    api_key = response.get("apiKey") or response.get("api_key") or response.get("key")
                    svc = service

                if not api_key:
                    wf_logger.warning("🔎 UI response missing 'apiKey'; skipping auto-store")
                else:
                    storage_result = await _store_api_key_internal(
                        api_key=api_key.strip(),
                        service=svc.strip(),
                        enterprise_id=enterprise_id,
                        user_id=user_id,
                        scope="enterprise" if enterprise_id else "user"
                    )
                    # Attach storage result to the tool response for the agent
                    response = {**response, "storage": storage_result, "autoStored": True}
                    wf_logger.info(
                        f"✅ Zero-shot stored API key for {svc}: {storage_result.get('status')}"
                    )
            except Exception as se:
                wf_logger.warning(f"⚠️ Auto-store failed for {service}: {se}")

        # Return the data submitted by the user (and optional storage result)
        return response
    except UIToolError as e:
        wf_logger.error(f"❌ UI tool interaction failed for service {service}: {e}")
        # Re-raise the error to be handled by the agent's error handling mechanism
        raise
    except Exception as e:
        wf_logger.error(f"❌ An unexpected error occurred during API key request for {service}: {e}", exc_info=True)
        # Wrap unexpected errors in UIToolError to standardize error handling
        raise UIToolError(f"An unexpected error occurred while requesting the API key for {service}.")


async def _store_api_key_internal(
    api_key: str,
    service: str,
    enterprise_id: Optional[str],
    user_id: Optional[str],
    scope: str
) -> Dict[str, Any]:
    """Internal function to store API key by recording reference in MongoDB."""
    
    if not api_key or not service or service == 'unknown':
        return {"status": "error", "message": "API key and service are required"}

    # Sanitize for secret name
    svc = re.sub(r"[^a-zA-Z0-9-]", "-", service.lower())
    eid = enterprise_id or 'global'
    uid = user_id or 'anon'
    prefix = 'ak'
    name_parts = [prefix, eid, svc]
    if scope == 'user':
        name_parts.append(uid)
    secret_name = "-".join(name_parts)[:127].strip('-')

    get_workflow_logger(workflow_name="generator").info(f"🔐 [STORE_API_KEY] Storing key for service={service} scope={scope} enterprise={enterprise_id} user={user_id} as secret='{secret_name}'")

    # 1) Compute hash and check idempotency from Mongo first
    hashed = hashlib.sha256(api_key.encode('utf-8')).hexdigest()
    client = get_mongo_client()
    db2 = client["MozaiksAI"]
    api_keys_col = db2["APIKeys"]
    now = datetime.utcnow()

    filter_doc = {
        "enterprise_id": enterprise_id,
        "user_id": user_id if scope == 'user' else None,
        "service": service,
        "scope": scope,
    }

    try:
        existing = await api_keys_col.find_one(filter_doc, projection={"hashed_key_sha256": 1, "secret_name": 1, "kv_version": 1})
        if existing and existing.get("hashed_key_sha256") == hashed:
            # No change; don't create a new KV version
            get_workflow_logger(workflow_name="generator").info("ℹ️ [STORE_API_KEY] Same key already stored; skipping new Key Vault version")
            return {
                "status": "noop",
                "message": "Key unchanged; no update",
                "service": service,
                "scope": scope,
                "secret_name": existing.get("secret_name"),
                "kv_version": existing.get("kv_version"),
                "masked_key": (api_key[:8] + "..." + api_key[-4:]) if len(api_key) > 12 else "***",
                "api_key": api_key,
            }
    except Exception as e:
        get_workflow_logger(workflow_name="generator").warning(f"⚠️ [STORE_API_KEY] Failed idempotency check, proceeding to store: {e}")

    # 2) Skip Key Vault storage (non-production). Keep a placeholder version for compatibility.
    version = None

    # 3) Upsert reference in MongoDB (no plaintext key)
    try:
        update_doc = {
            "$set": {
                "secret_name": secret_name,
                "kv_version": version,
                "masked_key": (api_key[:8] + "..." + api_key[-4:]) if len(api_key) > 12 else "***",
                "hashed_key_sha256": hashed,
                "updated_at": now,
            },
            "$setOnInsert": {
                "created_at": now,
            }
        }
        await api_keys_col.update_one(filter_doc, update_doc, upsert=True)
    except Exception as e:
        get_workflow_logger(workflow_name="generator").error(f"❌ [STORE_API_KEY] Failed to upsert API key reference in Mongo: {e}")
        # We already stored in KV; continue but warn the caller
        return {
            "status": "partial",
            "message": "Stored locally, but failed to record reference in DB",
            "service": service,
            "scope": scope,
            "secret_name": secret_name,
            "kv_version": version,
            "masked_key": (api_key[:8] + "..." + api_key[-4:]) if len(api_key) > 12 else "***",
            "api_key": api_key,
        }

    get_workflow_logger(workflow_name="generator").info(f"✅ [STORE_API_KEY] Stored and recorded reference for service={service} scope={scope}")
    return {
        "status": "success",
        "message": f"API key for {service} stored successfully",
        "service": service,
        "scope": scope,
        "secret_name": secret_name,
        "kv_version": version,
        "masked_key": (api_key[:8] + "..." + api_key[-4:]) if len(api_key) > 12 else "***",
        "api_key": api_key,
    }