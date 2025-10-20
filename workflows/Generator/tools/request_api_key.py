# ==============================================================================
# FILE: workflows/Generator/tools/request_api_key.py
# DESCRIPTION: UI tool function to request an external service API key from the user.
#              Never logs, returns, or echoes any portion (even masked) of the API key.
# RUNTIME PARAMS (injected via **runtime): chat_id, enterprise_id, workflow_name, context_variables.
# ==============================================================================
import uuid
from typing import Any, Dict, Optional, Annotated
from datetime import datetime, timezone

from logs.logging_config import get_workflow_logger
from core.workflow.outputs.ui_tools import use_ui_tool, UIToolError


def _extract_agent_name(container: Any) -> Optional[str]:
    """Best-effort agent attribution lookup from context variables."""
    if not container or not hasattr(container, "get"):
        return None

    candidate_keys = (
        "agent_name",
        "agentName",
        "turn_agent_name",
        "turn_agent",
        "auto_tool_agent_name",
        "auto_tool_agent",
        "last_agent_name",
        "speaker",
        "sender",
    )
    for key in candidate_keys:
        try:
            value = container.get(key)
        except Exception:  # pragma: no cover - defensive guard
            continue
        if isinstance(value, str):
            normalized = value.strip()
            if normalized:
                return normalized
    return None


async def request_api_key(
    service: Annotated[str, "Lowercase service identifier (e.g. 'openai', 'anthropic', 'huggingface')"],
    agent_message: Annotated[Optional[str], "Mandatory short sentence displayed in the chat along with the artifact for context."] = None,
    description: Optional[str] = None,
    required: Annotated[bool, "Whether key is required to proceed."] = True,
    mask_input: Annotated[bool, "Whether to mask characters in UI input field."] = True,
    service_display_name: Annotated[
        Optional[str],
        "Human-friendly service label shown to the user (e.g. 'OpenAI', 'Anthropic Claude'). Defaults to a title-cased version of the identifier.",
    ] = None,
    # AG2-native context injection
    context_variables: Annotated[Optional[Any], "Context variables provided by AG2"] = None,
) -> Dict[str, Any]:
    """Emit a UI interaction prompting the user to input an API key.

    Behavior:
      1. Builds a UI payload for the React component `AgentAPIKeyInput`.
      2. Emits the UI tool event via `emit_ui_tool_event`.
      3. Waits for the correlated frontend response.
      4. Optionally saves sanitized metadata to database.
      5. Returns a sanitized result (never includes the secret itself).

    SECURITY:
      - Does NOT log the provided key.
      - Does NOT return raw or masked fragments of the key.
      - Only metadata (length, status) is returned.
      - If saved to database, only metadata is stored (never the actual key).

    DATABASE INTEGRATION:
      - Automatically saves API key metadata to database (hardcoded settings)
      - Never stores actual API key - only service, length, timestamps, context
      - Database/collection names are configured in the tool code directly
      - Automatically adds enterprise_id, timestamps, and chat context
    """
    # Extract parameters from AG2 ContextVariables
    chat_id: Optional[str] = None
    workflow_name: Optional[str] = None
    agent_name: Optional[str] = None
    
    if context_variables and hasattr(context_variables, 'get'):
        chat_id = context_variables.get('chat_id')
        workflow_name = context_variables.get('workflow_name')
        agent_name = _extract_agent_name(context_variables)

    if not workflow_name:
        return {"status": "error", "message": "workflow_name is required for request_api_key"}

    wf_logger = get_workflow_logger(workflow_name=workflow_name, chat_id=chat_id)
    if not isinstance(service, str) or not service.strip():
        return {"status": "error", "message": "service is required"}
    service_norm = service.strip().lower().replace(" ", "_")
    display_name = service_display_name.strip() if isinstance(service_display_name, str) else None
    if not display_name:
        # Preserve original casing when available; fall back to prettified identifier.
        display_name = service.strip() if isinstance(service, str) else service_norm
        if display_name == service_norm:
            display_name = service_norm.replace("_", " ").title()
    # Optional: tool-scoped logger
    try:
        from logs.tools_logs import get_tool_logger as _get_tool_logger, log_tool_event as _log_tool_event  # type: ignore
        tlog = _get_tool_logger(tool_name="RequestAPIKey", chat_id=chat_id, workflow_name=workflow_name)
        _log_tool_event(tlog, action="start", status="ok", service=service_norm, service_display=display_name)
    except Exception:
        tlog = None  # type: ignore

    agent_message_id = f"msg_{uuid.uuid4().hex[:10]}"

    payload: Dict[str, Any] = {
        "service": service_norm,
        "service_display_name": display_name,
        "label": f"{display_name} API Key",
        "agent_message": agent_message or f"Please provide your {display_name} API key to continue.",
        "description": description or f"Enter your {display_name} API key to continue",
        "placeholder": f"Enter your {display_name} API key...",
        "required": required,
        "maskInput": mask_input,
        "agent_message_id": agent_message_id,
    }
    if agent_name:
        payload["agent_name"] = agent_name
        payload["agentName"] = agent_name
        payload["agent"] = agent_name

    # Optimized path: use unified helper to emit + wait
    try:
        # Emit UI tool and wait for response (display mode auto-resolved from tools.json)
        if 'tlog' in locals() and tlog:
            try:
                from logs.tools_logs import log_tool_event as _log_tool_event  # type: ignore
                _log_tool_event(tlog, action="emit_ui", status="start")
            except Exception:
                pass
        response = await use_ui_tool(
            "AgentAPIKeyInput",
            payload,
            chat_id=chat_id,
            workflow_name=str(workflow_name),
            # display parameter omitted - auto-resolved from tools.json
        )
        if 'tlog' in locals() and tlog:
            try:
                from logs.tools_logs import log_tool_event as _log_tool_event  # type: ignore
                _log_tool_event(
                    tlog,
                    action="emit_ui",
                    status="done",
                    result_status=(response or {}).get("status", "unknown"),
                    service_display=display_name,
                )
            except Exception:
                pass
    except UIToolError as e:
        return {"status": "error", "message": f"UI interaction failed: {e}"}
    except Exception as e:  # pragma: no cover
        wf_logger.error(f"❌ API key UI interaction failed: {e}")
        return {"status": "error", "message": "UI interaction failure"}

    # Normalize response structure
    status = (response or {}).get("status") or (response or {}).get("data", {}).get("status") or "unknown"

    # Detect cancellation / error early
    if status in {"cancelled", "canceled"}:
        return {
            "status": "cancelled",
            "service": service_norm,
            "service_display_name": display_name,
            "agent_message_id": agent_message_id,
            "ui_event_id": (response or {}).get("event_id"),
        }
    if status == "error":
        return {
            "status": "error",
            "service": service_norm,
            "message": (response or {}).get("error") or "User submission error",
            "service_display_name": display_name,
            "agent_message_id": agent_message_id,
            "ui_event_id": (response or {}).get("event_id"),
        }

    # Extract (without retaining) the key to compute metadata if present
    api_key = None
    try:
        data_block = response.get("data") if isinstance(response, dict) else None
        if isinstance(data_block, dict):
            api_key = data_block.get("apiKey") or data_block.get("api_key")
    except Exception:
        api_key = None

    key_length = len(api_key) if isinstance(api_key, str) else None
    
    # Prepare return data
    result = {
        "status": "success",
        "service": service_norm,
        "service_display_name": display_name,
        "agent_message_id": agent_message_id,
        "ui_event_id": (response or {}).get("event_id"),
        "has_key": bool(api_key),
        "key_length": key_length,
    }

    # Save metadata to database (NEVER the actual key)
    if api_key:  # Only save if we got a key
        try:
            # Database configuration - hardcoded in tool
            from core.core_config import get_mongo_client
            from bson import ObjectId
            
            database_enabled = True
            db_name = "autogen_ai_agents"  # Hardcoded database name
            coll_name = "APIKeys"          # Hardcoded collection name
            
            if database_enabled:
                # Connect to MongoDB
                client = get_mongo_client()
                db = client[db_name]
                collection = db[coll_name]
                
                # Prepare secure metadata document (no sensitive data)
                metadata = {
                    "api_key_service": service_norm,
                    "api_key_service_display": display_name,
                    "key_length": key_length,
                    "is_valid": key_length is not None and key_length > 10,  # Basic validation
                    "requested_by_user": True,
                    "requested_at": datetime.now(timezone.utc).isoformat(),
                    "validation_method": "length_check",
                    "source": "ui_interaction",
                    "agent_message_id": agent_message_id,
                    "ui_event_id": (response or {}).get("event_id"),
                    "chat_id": context_variables.get("chat_id") if context_variables else None,
                    "workflow_name": workflow_name,
                    "created_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc)
                }
                
                # Add enterprise_id context
                enterprise_id = context_variables.get("enterprise_id") if context_variables else None
                if enterprise_id:
                    try:
                        metadata["enterprise_id"] = ObjectId(enterprise_id)
                    except:
                        metadata["enterprise_id"] = enterprise_id
                
                # Insert document
                insert_result = await collection.insert_one(metadata)
                inserted_id = str(insert_result.inserted_id)
                
                wf_logger.info(f"✅ API key metadata saved to {db_name}.{coll_name}: {inserted_id}")
                result["metadata_saved"] = True
                result["metadata_id"] = inserted_id
                result["database_info"] = {
                    "database": db_name,
                    "collection": coll_name
                }
            else:
                result["metadata_saved"] = False
                
        except Exception as e:
            wf_logger.warning(f"⚠️ Database save failed (non-critical): {e}")
            result["metadata_saved"] = False
            result["metadata_error"] = str(e)
    else:
        result["metadata_saved"] = False

    return result

