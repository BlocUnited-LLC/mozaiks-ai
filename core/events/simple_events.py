# ==============================================================================
# FILE: core/ui/simple_events.py
# DESCRIPTION: Simplified event system
# ==============================================================================

from typing import Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum
import json
import time
import logging

from logs.logging_config import get_event_logger

event_logger = get_event_logger("simple_events")


class SimpleEventType(str, Enum):
    """Simple event types for our actual needs"""
    CHAT_MESSAGE = "chat_message"
    ROUTE_TO_ARTIFACT = "route_to_artifact" 
    ROUTE_TO_CHAT = "route_to_chat"
    UI_TOOL_ACTION = "ui_tool_action"
    STATUS = "status"
    ERROR = "error"


@dataclass
class SimpleEvent:
    """Base event class"""
    type: SimpleEventType
    data: Dict[str, Any]
    timestamp: Optional[int] = None
    agent_name: Optional[str] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = int(time.time() * 1000)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        result = {
            "type": self.type,
            "data": self.data,
            "timestamp": self.timestamp
        }
        if self.agent_name:
            result["agent_name"] = self.agent_name
        return result
    
    def to_json(self) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict())


class SimpleEventEncoder:
    """Simple event encoder"""
    
    def encode_sse(self, event: SimpleEvent) -> str:
        """Encode event for SSE transport"""
        return f"data: {event.to_json()}\n\n"
    
    def encode_websocket(self, event: SimpleEvent) -> str:
        """Encode event for WebSocket transport"""
        return event.to_json()


# Event creation helpers
def create_chat_message(content: str, sender: str, role: str = "assistant") -> SimpleEvent:
    """Create a simple chat message event"""
    event_logger.debug("Creating chat message event", extra={
        "sender": sender,
        "role": role,
        "content_length": len(content) if content else 0
    })
    
    return SimpleEvent(
        type=SimpleEventType.CHAT_MESSAGE,
        data={
            "content": content,
            "sender": sender,
            "role": role
        },
        agent_name=sender
    )


def create_artifact_component_route(title: str, content: str, component_name: str, category: str = "general", component_data: Optional[Dict[str, Any]] = None, agent_id: str = "agent") -> SimpleEvent:
    """Create artifact component routing event for full-featured right panel components"""
    return SimpleEvent(
        type=SimpleEventType.ROUTE_TO_ARTIFACT,
        data={
            "title": title,
            "content": content,
            "category": category,
            "component_name": component_name,
            "component_data": component_data or {},
            "artifact_id": f"artifact_{int(time.time())}"
        },
        agent_name=agent_id
    )


def create_inline_component_route(content: str, component_name: str, component_data: Optional[Dict[str, Any]] = None, agent_id: str = "agent") -> SimpleEvent:
    """Create inline component routing event for lightweight UI elements in chat flow"""
    return SimpleEvent(
        type=SimpleEventType.ROUTE_TO_CHAT,
        data={
            "content": content,
            "component_name": component_name,
            "component_data": component_data or {}
        },
        agent_name=agent_id
    )


def create_ui_tool_action(tool_id: str, action_type: str, payload: Dict[str, Any]) -> SimpleEvent:
    """Create UI tool action event"""
    return SimpleEvent(
        type=SimpleEventType.UI_TOOL_ACTION,
        data={
            "tool_id": tool_id,
            "action_type": action_type,
            "payload": payload
        }
    )


def create_status_event(message: str) -> SimpleEvent:
    """Create status event"""
    return SimpleEvent(
        type=SimpleEventType.STATUS,
        data={"message": message}
    )


def create_error_event(error_message: str, error_code: Optional[str] = None) -> SimpleEvent:
    """Create error event"""
    data = {"message": error_message}
    if error_code:
        data["code"] = error_code
    
    return SimpleEvent(
        type=SimpleEventType.ERROR,
        data=data
    )
