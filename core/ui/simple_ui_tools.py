# ==============================================================================
# FILE: core/infrastructure/simple_ui_tools.py
# DESCRIPTION: Simplified UI routing tools
# ==============================================================================

import logging
from typing import Dict, Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..events.simple_protocols import SimpleCommunicationChannel as CommunicationChannel

from ..events.simple_events import (
    create_inline_component_route, 
    create_artifact_component_route, 
    create_ui_tool_action
)
from logs.logging_config import get_event_logger, get_component_logger

logger = logging.getLogger(__name__)
ui_event_logger = get_event_logger("ui_routing")
ui_component_logger = get_component_logger("ui_tools")

# Global reference to communication channel (set by groupchat_manager)
_communication_channel: Optional['CommunicationChannel'] = None

def set_communication_channel(channel: 'CommunicationChannel'):
    """Set the global communication channel for UI routing tools."""
    global _communication_channel
    _communication_channel = channel


async def route_to_inline_component(content: str, component_name: str, component_data: Optional[dict] = None) -> str:
    """
    Route content to inline UI component (lightweight elements in chat flow).
    
    Args:
        content: Content to display
        component_name: Specific component name from workflow (e.g., 'AgentAPIKeyInput')
        component_data: Data for the component
    
    Returns:
        Status message
    """
    if not _communication_channel:
        logger.warning("No communication channel available for UI routing")
        return "UI routing not available"
    
    try:
        event = create_inline_component_route(content, component_name, component_data)
        
        await _communication_channel.send_event(
            event_type="route_to_chat",
            data=event.data
        )
        
        logger.info(f"Routed content to inline component: {component_name}")
        return f"Content routed to inline component '{component_name}' successfully"
        
    except Exception as e:
        logger.error(f"Failed to route to inline component: {e}")
        return f"Error: {str(e)}"


async def route_to_artifact_component(title: str, content: str, component_name: str, category: str = "general", component_data: Optional[dict] = None) -> str:
    """
    Route content to artifact component (full-featured right panel components).
    
    Args:
        title: Title for the artifact
        content: Artifact content
        component_name: Specific component name (e.g., 'FileDownloadCenter')
        category: Artifact category
        component_data: Data for the component
    
    Returns:
        Status message
    """
    if not _communication_channel:
        logger.warning("No communication channel available for UI routing")
        return "UI routing not available"
    
    try:
        event = create_artifact_component_route(title, content, component_name, category, component_data)
        
        await _communication_channel.send_event(
            event_type="route_to_artifact",
            data=event.data
        )
        
        logger.info(f"Created artifact component '{component_name}' with {len(content)} chars")
        return f"Artifact component '{component_name}' created successfully"
        
    except Exception as e:
        logger.error(f"Failed to create artifact component: {e}")
        return f"Error: {str(e)}"


async def send_ui_tool_action(tool_id: str, action_type: str, payload: Dict[str, Any]) -> str:
    """
    Simple tool: Send UI tool action.
    
    Args:
        tool_id: Tool identifier
        action_type: Type of action
        payload: Action payload
    
    Returns:
        Status message
    """
    if not _communication_channel:
        logger.warning("No communication channel available for UI tool action")
        return "UI tool action not available"
    
    try:
        event = create_ui_tool_action(tool_id, action_type, payload)
        
        # Send via simple event
        await _communication_channel.send_event(
            event_type="ui_tool_action",
            data=event.data
        )
        
        logger.info(f"Sent UI tool action: {tool_id} - {action_type}")
        return f"UI tool action sent successfully"
        
    except Exception as e:
        logger.error(f"Failed to send UI tool action: {e}")
        return f"Error: {str(e)}"


async def handle_component_action(
    workflow_type: str,
    agent_name: str,
    component_name: str,
    action_data: Dict[str, Any],
    context_variables: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Handle component action and optionally adjust context variables
    
    This is the main entry point for component actions from the transport layer.
    It handles both backend processing and context adjustment.
    
    Args:
        workflow_type: The workflow type (e.g., 'Generator')
        agent_name: Name of the agent that owns the component
        component_name: Name of the component that sent the action
        action_data: The action data from the frontend component
        context_variables: The AG2 ContextVariables (optional)
        
    Returns:
        Result of the action handling
    """
    ui_component_logger.info(f"🎯 Handling component action: {workflow_type}.{agent_name}.{component_name}")
    
    try:
        result = {"status": "success", "component_handled": False, "context_adjusted": False}
        
        # Step 1: Handle backend processing if enabled
        # (This would integrate with existing backend handlers like api_manager.py, file_manager.py)
        
        # Step 2: Handle context adjustment if enabled
        if context_variables:
            from .context_adjustment import adjust_context_from_component_action
            
            context_result = await adjust_context_from_component_action(
                workflow_type, agent_name, component_name, action_data, context_variables
            )
            
            result["context_adjustment"] = context_result
            result["context_adjusted"] = context_result.get("status") == "success"
        
        # Step 3: Update component interaction tracking
        result.update({
            "workflow_type": workflow_type,
            "agent_name": agent_name,
            "component_name": component_name,
            "action_type": action_data.get('type', 'unknown')
        })
        
        ui_component_logger.info(f"✅ Component action handled: {component_name}")
        return result
        
    except Exception as e:
        ui_component_logger.error(f"❌ Component action failed for {component_name}: {e}")
        return {
            "status": "error",
            "message": str(e),
            "component_name": component_name,
            "agent_name": agent_name
        }
