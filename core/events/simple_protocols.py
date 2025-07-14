# ==============================================================================
# FILE: core/transport/simple_protocols.py
# DESCRIPTION: Simplified protocol definitions
# ==============================================================================
from typing import Protocol, Any, Optional

class SimpleCommunicationChannel(Protocol):
    """
    Simplified communication channel protocol.
    
    Simple event sending.
    """
    
    async def send_event(self, event_type: str, data: Any, agent_name: Optional[str] = None) -> None:
        """Send a simple event through the communication channel."""
        ...
    
    # Simplified UI routing
    async def send_custom_event(self, name: str, value: Any) -> None:
        """Send custom event."""
        ...
    
    async def send_ui_component_route(self, agent_id: str, content: str, routing_decision: dict) -> None:
        """Send UI routing decision (simplified)."""
        ...
    
    # Optional: UI tool support
    async def send_ui_tool(self, tool_id: str, payload: Any) -> None:
        """Send UI tool request."""
        ...
