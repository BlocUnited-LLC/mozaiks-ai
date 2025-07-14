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
    create_ui_tool_action,
    SimpleEventEncoder
)
from logs.logging_config import get_event_logger, get_component_logger

logger = logging.getLogger(__name__)
ui_event_logger = get_event_logger("ui_routing")
ui_component_logger = get_component_logger("ui_tools")

# Global reference to communication channel (set by groupchat_manager)
_communication_channel: Optional['CommunicationChannel'] = None
_event_encoder = SimpleEventEncoder()

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


async def smart_route_content(content: str, component_name: Optional[str] = None, reasoning: Optional[str] = None) -> str:
    """
    Automatically route content to appropriate component based on workflow configuration.
    
    Args:
        content: Content to route
        component_name: Optional specific component name (if known)
        reasoning: Optional reasoning for the routing decision
    
    Returns:
        Status message
    """
    if not _communication_channel:
        logger.warning("No communication channel available for UI routing")
        return "UI routing not available"
    
    try:
        # If no component specified, use simple heuristics for routing type only
        if not component_name:
            # Simple heuristics for routing TYPE (inline vs artifact) only
            route_to_artifact = (
                len(content) > 500 or  # Long content
                "```" in content or    # Code blocks
                "<" in content and ">" in content or  # HTML/XML
                "{" in content and "}" in content  # JSON/objects
            )
            
            if route_to_artifact:
                # Route to artifact component - let workflow determine which one
                return await route_to_artifact_component(
                    title="Generated Content",
                    content=content,
                    component_name="default_artifact",  # Workflow will resolve this
                    category="code" if "```" in content else "general"
                )
            else:
                # Route to inline component - let workflow determine which one
                return await route_to_inline_component(
                    content=content,
                    component_name="default_inline"  # Workflow will resolve this
                )
        else:
            # Component name specified - determine routing type from component name
            # This would be set by the workflow/agent calling this function
            if "artifact" in component_name.lower() or "editor" in component_name.lower() or "viewer" in component_name.lower():
                return await route_to_artifact_component(
                    title="Generated Content",
                    content=content,
                    component_name=component_name,
                    category="general"
                )
            else:
                return await route_to_inline_component(
                    content=content,
                    component_name=component_name
                )
            
    except Exception as e:
        logger.error(f"Failed to smart route content: {e}")
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
