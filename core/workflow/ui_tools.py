# ==============================================================================
# FILE: core/workflow/ui_tools.py
# DESCRIPTION: Centralized helper functions for agent-driven UI tool events.
#              This module provides a standardized, reusable pattern for any
#              agent tool that needs to interact with a custom UI component.
# ==============================================================================

import asyncio
import uuid
import logging
from typing import Dict, Any, Optional

# Import SimpleTransport for direct communication and UnifiedEventDispatcher for logging
from core.transport.simple_transport import SimpleTransport
from core.events.unified_event_dispatcher import emit_ui_tool_event as dispatch_ui_tool_event
from logs.logging_config import get_business_logger

business_logger = get_business_logger("ui_tools")

class UIToolError(Exception):
    """Custom exception for UI tool errors."""
    pass

async def emit_ui_tool_event(
    tool_id: str,
    payload: Dict[str, Any],
    display: str = "inline",
    chat_id: Optional[str] = None,
    workflow_name: str = "unknown"
) -> str:
    """
    Core function to emit a UI tool event to the frontend.

    This function is the standardized way for any agent tool to request
    that a UI component be rendered.

    Args:
        tool_id: The unique identifier for the UI component (e.g., "agent_api_key_input").
        payload: The data required by the UI component (props).
        display: How the component should be displayed ("inline" or "artifact").
        chat_id: The ID of the chat session to send the event to.
        workflow_name: The name of the workflow emitting the event.

    Returns:
        The unique event ID for this interaction.
    """
    event_id = f"{tool_id}_{str(uuid.uuid4())[:8]}"
    
    try:
        transport = await SimpleTransport.get_instance()
    except Exception as e:
        business_logger.error(f"❌ [UI_TOOLS] Failed to get SimpleTransport instance: {e}")
        raise UIToolError(f"SimpleTransport not available: {e}")

    business_logger.info(f"🎯 [UI_TOOLS] Emitting UI tool event: {tool_id} (Event: {event_id}, Display: {display})")
    
    try:
        # 1. Send the event to the UI for immediate rendering
        await transport.send_ui_tool_event(
            event_id=event_id,
            chat_id=chat_id,
            tool_name=workflow_name,
            component_name=tool_id,
            display_type=display,
            payload=payload
        )
        
        # 2. Dispatch the event for logging and monitoring
        await dispatch_ui_tool_event(
            ui_tool_id=tool_id,
            payload=payload,
            workflow_name=workflow_name,
            display=display,
            chat_id=chat_id
        )
        
        business_logger.info(f"✅ [UI_TOOLS] Successfully emitted and logged UI tool event: {event_id}")
        return event_id
        
    except Exception as e:
        business_logger.error(f"❌ [UI_TOOLS] Failed to emit UI tool event '{event_id}': {e}", exc_info=True)
        raise UIToolError(f"Failed to emit UI tool event: {e}")

async def wait_for_ui_tool_response(event_id: str) -> Dict[str, Any]:
    """
    Waits indefinitely for a response from a UI tool interaction.

    Args:
        event_id: The unique event ID that was sent to the UI.

    Returns:
        The response data submitted by the user from the UI component.
    """
    business_logger.info(f"⏳ [UI_TOOLS] Waiting for UI tool response for event: {event_id}")
    
    try:
        transport = await SimpleTransport.get_instance()
        
        # The transport layer manages the futures for waiting.
        response = await transport.wait_for_ui_tool_response(event_id)
        
        business_logger.info(f"✅ [UI_TOOLS] Received UI tool response for event: {event_id}")
        business_logger.debug(f"🔍 [UI_TOOLS] Response data: {response}")
        
        return response
    except Exception as e:
        business_logger.error(f"❌ [UI_TOOLS] Error waiting for UI tool response for event '{event_id}': {e}", exc_info=True)
        raise UIToolError(f"Error waiting for UI tool response: {e}")
