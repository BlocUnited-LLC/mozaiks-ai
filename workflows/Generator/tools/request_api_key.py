# ==============================================================================
# FILE: workflows/Generator/tools/request_api_key.py
# DESCRIPTION: API key request tool - single async function export
# NOTE: 'description' in the 'payload' must be a property to use to display the agent's instructions, making the whole system easier to extend.
# ==============================================================================

import asyncio
import uuid
import logging
from typing import Dict, Any, Optional
from datetime import datetime

# Import enhanced logging
from logs.logging_config import get_business_logger

business_logger = get_business_logger("generator_request_api_key")

class UIToolError(Exception):
    """Custom exception for UI tool errors"""
    pass

async def emit_ui_tool_event(
    tool_id: str,
    payload: Dict[str, Any],
    event_id: Optional[str] = None,
    workflow_name: str = "generator"
) -> str:
    """
    Core function to emit UI tool events to the frontend.
    
    This follows the ag2_dynamicUI.md specification for workflow-agnostic event emission.
    """
    # Generate event ID if not provided
    if not event_id:
        event_id = f"{tool_id}_{str(uuid.uuid4())[:8]}"
    
    # Import transport to send events
    try:
        from core.transport.simple_transport import SimpleTransport
        transport = SimpleTransport()
    except ImportError:
        raise UIToolError("SimpleTransport not available for event emission")
    
    # Construct UI tool event
    ui_tool_event = {
        "type": "ui_tool_event",
        "toolId": tool_id,
        "eventId": event_id,
        "workflowname": workflow_name,
        "payload": payload,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    business_logger.info(f"🎯 [REQUEST_API_KEY] Emitting UI tool event: {tool_id} (event: {event_id})")
    business_logger.debug(f"🔍 [REQUEST_API_KEY] Event payload: {payload}")
    
    try:
        # Send the UI tool event through the transport system
        await transport.send_ui_tool_event(
            ui_tool_id=tool_id,
            payload=ui_tool_event,
            display="inline"
        )
        
        business_logger.info(f"✅ [REQUEST_API_KEY] Successfully emitted UI tool event: {event_id}")
        return event_id
        
    except Exception as e:
        business_logger.error(f"❌ [REQUEST_API_KEY] Failed to emit UI tool event: {e}")
        raise UIToolError(f"Failed to emit UI tool event: {e}")

async def wait_for_ui_tool_response(event_id: str) -> Dict[str, Any]:
    """
    Wait indefinitely for a response from a UI tool event.
    No timeout - users can take their time to respond.
    """
    business_logger.info(f"⏳ [REQUEST_API_KEY] Waiting for UI tool response: {event_id}")
    
    try:
        # Import here to avoid circular imports
        from core.transport.simple_transport import SimpleTransport
        
        # Wait indefinitely for the UI tool response - no timeout
        response = await SimpleTransport.wait_for_ui_tool_response(event_id)
        
        business_logger.info(f"✅ [REQUEST_API_KEY] Received UI tool response: {event_id}")
        business_logger.debug(f"🔍 [REQUEST_API_KEY] Response data: {response}")
        
        return response
        
    except asyncio.TimeoutError:
        business_logger.warning(f"⏰ [REQUEST_API_KEY] UI tool response timeout: {event_id}")
        raise UIToolError(f"UI tool response timeout for event: {event_id}")
    except Exception as e:
        business_logger.error(f"❌ [REQUEST_API_KEY] Error waiting for UI tool response: {e}")
        raise UIToolError(f"Error waiting for UI tool response: {e}")

async def request_api_key(
    service: str,
    description: Optional[str] = None,
    label: Optional[str] = None,
    placeholder: Optional[str] = None,
    required: bool = True,
    workflow_name: str = "generator"
) -> Dict[str, Any]:
    """
    AG2 tool function to request an API key from the user via UI.
    
    This tool emits a UI event that displays the AgentAPIKeyInput component
    in the frontend and waits for the user's response.
    
    Args:
        service: The service name (e.g., "openai", "anthropic", "azure_openai")
        description: Custom description for the API key request
        label: Custom label for the input field
        placeholder: Custom placeholder text
        required: Whether the API key is required
        workflow_name: The workflow type requesting the key
        
    Returns:
        Dict containing the API key response data
        
    Raises:
        UIToolError: If the request fails or times out
    """
    business_logger.info(f"🔑 [REQUEST_API_KEY] Requesting API key for service: {service}")
    
    # DEV NOTE: The 'description' key is the standardized way to pass the agent's
    # contextual message to the corresponding UI component. All dynamic UI tools
    # should follow this convention.
    # Prepare payload for AgentAPIKeyInput component
    payload = {
        "service": service,
        "label": label or f"{service.replace('_', ' ').title()} API Key",
        "description": description or f"Enter your {service} API key to continue",
        "placeholder": placeholder or f"Enter your {service.upper()} API key...",
        "required": required
    }
    
    # Emit the UI tool event
    event_id = await emit_ui_tool_event(
        tool_id="agent_api_key_input",
        payload=payload,
        workflow_name=workflow_name
    )
    
    # Wait for user response
    response = await wait_for_ui_tool_response(event_id)
    
    business_logger.info(f"🔑 [REQUEST_API_KEY] API key request completed for {service}: {response.get('status', 'unknown')}")
    
    return response