# ==============================================================================
# FILE: core\transport\transport.py
# DESCRIPTION: Unified transport system with AG2 compatibility
# ==============================================================================
import json
import logging
from typing import Dict, Any, Optional
from fastapi import WebSocket
from fastapi.responses import StreamingResponse

from ..events.simple_protocols import SimpleCommunicationChannel
from ..workflow.init_registry import get_workflow_transport
from .ag2_sse_adapter import AG2SSEAdapter
from .ag2_websocket_adapter import AG2WebSocketManager, AG2WebSocketConnection
from ..events.simple_events import SimpleEventEncoder
from logs.logging_config import get_business_logger, log_business_event, get_transport_logger, log_operation

# Logger setup
business_logger = get_business_logger("transport")
transport_logger = get_transport_logger("transport_manager")
logger = logging.getLogger(__name__)


class TransportManager:
    """
    Unified transport manager for SSE and WebSocket connections with simplified events.
    
    Provides a single interface for all transport operations following AG2-compatible patterns.
    Uses simplified event system.
    """
    
    def __init__(self, default_llm_config: Dict[str, Any]):
        self.default_llm_config = default_llm_config
        self.ag2_sse_adapter = AG2SSEAdapter(default_llm_config)
        self.websocket_manager = AG2WebSocketManager()
        
    async def get_communication_channel(self, 
                                       chat_id: str, 
                                       enterprise_id: str, 
                                       user_id: str, 
                                       workflow_type: str) -> SimpleCommunicationChannel:
        """Get unified communication channel for any transport type."""
        with log_operation(transport_logger, "communication_channel_creation", 
                         workflow_type=workflow_type, chat_id=chat_id):
            
            transport = get_workflow_transport(workflow_type)
            
            transport_logger.info("Creating communication channel", extra={
                "chat_id": chat_id,
                "enterprise_id": enterprise_id,
                "user_id": user_id,
                "workflow_type": workflow_type,
                "transport_type": transport
            })
            
            log_business_event(
                event_type="COMMUNICATION_CHANNEL_REQUEST",
                description=f"Creating {transport} communication channel",
                context={
                    "chat_id": chat_id,
                    "workflow_type": workflow_type,
                    "transport": transport
                }
            )
            
            if transport == "websocket":
                # Use WebSocket manager for real-time bidirectional communication
                channel = self.websocket_manager.get_connection(
                    chat_id, enterprise_id, user_id
                )
                if channel is None:
                    transport_logger.error("Failed to create WebSocket connection", extra={
                        "chat_id": chat_id, "enterprise_id": enterprise_id, "user_id": user_id
                    })
                    raise RuntimeError(f"Failed to create WebSocket connection for chat {chat_id}")
            else:  # Default to SSE
                # Use SSE adapter for streaming communication
                channel = await self.ag2_sse_adapter._create_connection(
                    chat_id, enterprise_id, user_id, workflow_type
                )
            
            transport_logger.info("Communication channel created successfully", extra={
                "chat_id": chat_id,
                "transport_type": transport,
                "channel_type": type(channel).__name__
            })
            
            return channel

    async def create_sse_stream(self, chat_id: str, enterprise_id: str, 
                               user_id: str, workflow_type: str) -> StreamingResponse:
        """Create SSE streaming response."""
        transport = get_workflow_transport(workflow_type)
        
        if transport != "sse":
            logger.warning(f"Workflow {workflow_type} is configured for {transport} but SSE endpoint was called")
        
        # Delegate to AG2 SSE Adapter for stream creation
        stream = await self.ag2_sse_adapter.stream_events(
            chat_id=chat_id,
            enterprise_id=enterprise_id,
            user_id=user_id,
            workflow_type=workflow_type
        )
        return StreamingResponse(stream, media_type="text/event-stream")
    
    async def handle_websocket_connection(self, websocket: WebSocket, chat_id: str,
                                        enterprise_id: str, user_id: str, workflow_type: str):
        """Handle WebSocket connection using AG2 WebSocket integration."""
        transport = get_workflow_transport(workflow_type)
        
        if transport != "websocket":
            await websocket.close(
                code=1000, 
                reason=f"Workflow {workflow_type} uses {transport} transport"
            )
            return
        
        await websocket.accept()
        
        log_business_event(
            event_type="WEBSOCKET_CONNECTION_ACCEPTED",
            description=f"WebSocket connection accepted for workflow {workflow_type}",
            context={"chat_id": chat_id, "workflow_type": workflow_type}
        )
        
        try:
            # Create AG2 WebSocket connection
            # TODO: The AG2WebSocketManager interface needs to be updated to properly handle 
            # FastAPI WebSocket -> AG2 IOWebsockets integration
            connection_id = f"{enterprise_id}_{chat_id}_{user_id}"
            connection = AG2WebSocketConnection(chat_id, enterprise_id, user_id, workflow_type)
            self.websocket_manager.active_connections[connection_id] = connection
            
            logger.info(f"AG2 WebSocket connection established for chat {chat_id}")
            
            # Auto-start workflow if appropriate (after connection is established)
            await connection.auto_start_workflow_if_appropriate()
            
            # Basic WebSocket message loop with AG2 integration hooks
            # This delegates message handling to the AG2WebSocketConnection
            try:
                while True:
                    data = await websocket.receive_text()
                    message_data = json.loads(data)
                    
                    # Route message to AG2 connection
                    if message_data.get("type") == "user_input":
                        await connection.handle_human_input(message_data.get("message", ""))
                    else:
                        # Handle other message types as needed
                        logger.info(f"Received WebSocket message type: {message_data.get('type')}")
                        
            except Exception as e:
                if "1000" not in str(e):  # Normal close
                    logger.error(f"WebSocket message handling error: {e}")
                    
        except Exception as e:
            logger.error(f"WebSocket connection error: {e}")
            log_business_event(
                event_type="WEBSOCKET_CONNECTION_ERROR",
                description="WebSocket connection error",
                context={"chat_id": chat_id, "error": str(e)},
                level="ERROR"
            )
            await websocket.close()
        finally:
            # Clean up connection
            connection_id = f"{enterprise_id}_{chat_id}_{user_id}"
            if connection_id in self.websocket_manager.active_connections:
                del self.websocket_manager.active_connections[connection_id]
                logger.info(f"Cleaned up WebSocket connection for chat {chat_id}")
    
    async def handle_user_input(self, chat_id: str, enterprise_id: str, user_id: str,
                               workflow_type: str, message: str) -> Dict[str, Any]:
        """Handle user input for any transport type with unified workflow integration."""
        transport = get_workflow_transport(workflow_type)
        
        log_business_event(
            event_type="USER_INPUT_RECEIVED",
            description=f"User input received for {transport} workflow",
            context={
                "chat_id": chat_id,
                "workflow_type": workflow_type,
                "transport": transport,
                "message_length": len(message)
            }
        )
        
        # Get the unified communication channel
        communication_channel = await self.get_communication_channel(
            chat_id=chat_id,
            enterprise_id=enterprise_id,
            user_id=user_id,
            workflow_type=workflow_type
        )
        
        # Get workflow handler from registry
        from ..workflow.init_registry import get_workflow_handler
        workflow_handler = get_workflow_handler(workflow_type)
        
        if not workflow_handler:
            logger.error(f"No workflow handler found for type: {workflow_type}")
            return {"status": "error", "message": f"Unknown workflow type: {workflow_type}"}
        
        try:
            # Call workflow handler with unified communication channel
            # This is the key integration point - we inject the communication_channel
            await self._call_workflow_with_communication_channel(
                workflow_handler=workflow_handler,
                chat_id=chat_id,
                enterprise_id=enterprise_id,
                user_id=user_id,
                initial_message=message,
                communication_channel=communication_channel
            )
            
            return {"status": "processed", "transport": transport}
            
        except Exception as e:
            logger.error(f"Workflow execution failed: {e}")
            return {"status": "error", "message": str(e)}
    
    async def _call_workflow_with_communication_channel(
        self,
        workflow_handler,
        chat_id: str,
        enterprise_id: str,
        user_id: str,
        initial_message: str,
        communication_channel
    ):
        """
        Wrapper that calls workflow handlers with unified communication channel.
        
        This is the key integration point that makes workflows transport-agnostic.
        The workflow handler receives the communication_channel and doesn't need
        to know whether it's SSE or WebSocket.
        """
        import inspect
        
        # Get the workflow handler signature
        sig = inspect.signature(workflow_handler)
        
        # Prepare arguments for the workflow handler
        workflow_kwargs = {
            "enterprise_id": enterprise_id,
            "chat_id": chat_id,
            "user_id": user_id,
            "initial_message": initial_message,
        }
        
        # Check if the workflow handler accepts communication_channel parameter
        if "communication_channel" in sig.parameters:
            workflow_kwargs["communication_channel"] = communication_channel
        
        # Call the workflow handler
        await workflow_handler(**workflow_kwargs)
    
    def get_connection_info(self) -> Dict[str, Any]:
        """Get information about active connections."""
        return {
            "sse_connections": len(self.ag2_sse_adapter.active_connections),
            "websocket_connections": len(self.websocket_manager.active_connections),
            "total_connections": len(self.ag2_sse_adapter.active_connections) + len(self.websocket_manager.active_connections)
        }
    
    async def cleanup(self):
        """Clean up all connections."""
        log_business_event(
            event_type="TRANSPORT_CLEANUP",
            description="Transport cleanup initiated"
        )
        
        await self.ag2_sse_adapter.cleanup()
        logger.info("Transport cleanup completed")

class WebSocketConnectionQueue(SimpleCommunicationChannel):
    """Queues messages until WebSocket connection becomes available."""
    
    def __init__(self, chat_id: str, enterprise_id: str, user_id: str, workflow_type: str, websocket_manager):
        self.chat_id = chat_id
        self.enterprise_id = enterprise_id
        self.user_id = user_id
        self.workflow_type = workflow_type
        self.websocket_manager = websocket_manager
        self.message_queue = []
        self.max_queue_size = 100
    
    async def _try_send_queued_messages(self):
        """Try to send queued messages if connection becomes available"""
        connection = self.websocket_manager.get_connection(self.chat_id, self.enterprise_id, self.user_id)
        if connection and self.message_queue:
            logger.info(f"Connection available, sending {len(self.message_queue)} queued messages")
            for event_type, data, agent_name in self.message_queue:
                try:
                    await connection.send_event(event_type, data, agent_name)
                except Exception as e:
                    logger.error(f"Failed to send queued message: {e}")
            self.message_queue.clear()
    
    async def send_event(self, event_type: str, data: Any, agent_name: Optional[str] = None) -> None:
        # Try to get active connection first
        connection = self.websocket_manager.get_connection(self.chat_id, self.enterprise_id, self.user_id)
        if connection:
            await connection.send_event(event_type, data, agent_name)
        else:
            # Queue the message
            if len(self.message_queue) < self.max_queue_size:
                self.message_queue.append((event_type, data, agent_name))
                logger.debug(f"Queued event {event_type} for chat {self.chat_id}")
            else:
                logger.warning(f"Message queue full for chat {self.chat_id}, dropping event {event_type}")
    
    async def send_text_message_start(self, message_id: str, role: str) -> None:
        await self.send_event("text_message_start", {"message_id": message_id, "role": role})
    
    async def send_text_message_content(self, message_id: str, delta: str) -> None:
        await self.send_event("text_message_content", {"message_id": message_id, "delta": delta})
    
    async def send_text_message_end(self, message_id: str) -> None:
        await self.send_event("text_message_end", {"message_id": message_id})
    
    async def send_ui_tool(self, tool_id: str, payload: Any) -> None:
        await self.send_event("ui_tool", {"tool_id": tool_id, "payload": payload})
    
    async def send_ui_component_route(self, agent_id: str, content: str, routing_decision: Dict[str, Any]) -> None:
        await self.send_event("ui_component_route", {"agent_id": agent_id, "content": content, "routing_decision": routing_decision})
    
    async def send_custom_event(self, name: str, value: Any) -> None:
        await self.send_event("custom_event", {"name": name, "value": value})

# Global instance
transport_manager: Optional[TransportManager] = None
