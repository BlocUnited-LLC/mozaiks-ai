# ==============================================================================
# FILE: core\transport\ag2_sse_adapter.py
# DESCRIPTION: AG2 SSE Adapter with Simple Events support
# ==============================================================================
import asyncio
import json
import logging
import time
from typing import Dict, Any, Optional

import logging
from core.events.simple_protocols import SimpleCommunicationChannel
from core.workflow.init_registry import get_workflow_handler
from core.workflow.workflow_config import workflow_config
from logs.logging_config import (
    get_chat_logger, 
    get_business_logger, 
    get_performance_logger,
    log_business_event
)

# Logger setup
chat_logger = get_chat_logger("ag2_sse_adapter")
business_logger = get_business_logger("ag2_sse_adapter")
performance_logger = get_performance_logger("ag2_sse_adapter")

def should_auto_start_workflow(workflow_type: str) -> bool:
    """
    Determine if a workflow should auto-start based on workflow configuration.
    Uses workflow.json to determine if human interaction is required.
    """
    # Use the dynamic workflow configuration
    return workflow_config.should_auto_start(workflow_type)

class SSEConnection(SimpleCommunicationChannel):
    """
    Manages a single SSE connection and the workflow for a given chat.
    This class implements the CommunicationChannel protocol.
    """
    
    def __init__(self, chat_id: str, enterprise_id: str, user_id: str, workflow_type: str, default_llm_config: Dict[str, Any]):
        self.chat_id = chat_id
        self.enterprise_id = enterprise_id
        self.user_id = user_id
        self.workflow_type = workflow_type
        self.default_llm_config = default_llm_config
        self.event_queue = asyncio.Queue()
        self.active = True
        self.workflow_started = False  # Track if workflow has been started
        self.is_paused = False
        self.conversation_state: Dict[str, Any] = {}

    async def event_generator(self):
        """Yields events from the queue to be sent to the client."""
        try:
            while self.active:
                try:
                    event = await asyncio.wait_for(self.event_queue.get(), timeout=300) # 5 min timeout
                    yield f"data: {event}\n\n"
                    self.event_queue.task_done()
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'type': 'heartbeat', 'data': 'still alive'})}\n\n"
        except asyncio.CancelledError:
            log_business_event(
                event_type="sse_connection_closed", 
                description=f"Connection cancelled for chat {self.chat_id}"
            )
        finally:
            self.active = False

    async def handle_user_message(self, message_content: Optional[str]):
        """
        Processes a user message, initiates the workflow, and puts events in the queue.
        
        This method represents the start of a user feedback loop:
        1. User provides input (message_content)
        2. Workflow processes the input through agents
        3. Results are streamed back to user
        4. Loop is completed and tracked at the core level.
        """
        try:
            # Mark workflow as started to prevent duplicate starts
            self.workflow_started = True
            
            # Get the correct workflow handler from the registry
            workflow_handler = get_workflow_handler(self.workflow_type)
            
            if not workflow_handler:
                await self.send_event(
                    event_type='error', 
                    data={'message': f"Invalid workflow type: {self.workflow_type}"}
                )
                return

            # Track user interaction (if user provided input)
            if message_content is not None:
                log_business_event(
                    event_type="user_input_received",
                    description=f"User input received for chat {self.chat_id}",
                    context={
                        "chat_id": self.chat_id,
                        "message_length": len(message_content) if message_content else 0
                    }
                )
            else:
                # This is an auto-started workflow
                log_business_event(
                    event_type="workflow_auto_initiated",
                    description=f"Workflow auto-initiated without user input for chat {self.chat_id}",
                    context={
                        "chat_id": self.chat_id,
                        "workflow_type": self.workflow_type,
                        "auto_start": True
                    }
                )

            # Run the workflow - token management is now handled at the core level
            await workflow_handler(
                enterprise_id=self.enterprise_id,
                chat_id=self.chat_id,
                user_id=self.user_id,
                initial_message=message_content,
                communication_channel=self
            )

        except Exception as e:
            logging.exception("Error during message handling")
            await self.send_event(
                event_type='error', 
                data={'message': f"An unexpected error occurred: {e}"}
            )

    async def send_event(self, event_type: str, data: Any, agent_name: Optional[str] = None):
        """Enhanced event sending with streaming support."""
        event_data = {
            "type": event_type, 
            "data": data,
            "timestamp": int(time.time() * 1000)
        }
        if agent_name:
            event_data["agent_name"] = agent_name
            
        event = json.dumps(event_data)
        await self.event_queue.put(event)
        
        # Log streaming events for debugging
        if event_type.startswith("text_stream"):
            chat_logger.debug(f"📡 [SSE] Streaming event: {event_type}")
        elif event_type in ["TEXT_MESSAGE_START", "TEXT_MESSAGE_CONTENT", "TEXT_MESSAGE_END"]:
            chat_logger.debug(f"📡 [SSE] Message event: {event_type}")
    
    # Implementation of CommunicationChannel protocol methods
    async def send_text_message_start(self, message_id: str, role: str) -> None:
        """Emits a TextMessageStart event (initialize a new streaming message)."""
        await self.send_event(
            event_type="TEXT_MESSAGE_START",
            data={"messageId": message_id, "role": role}
        )

    async def send_text_message_content(self, message_id: str, delta: str) -> None:
        """Emits a TextMessageContent event (stream a chunk of text)."""
        await self.send_event(
            event_type="TEXT_MESSAGE_CONTENT",
            data={"messageId": message_id, "delta": delta}
        )

    async def send_text_message_end(self, message_id: str) -> None:
        """Emits a TextMessageEnd event (finalize the streaming message)."""
        await self.send_event(
            event_type="TEXT_MESSAGE_END",
            data={"messageId": message_id}
        )

    async def send_streaming_text(self, text_chunk: str, agent_name: str, message_id: Optional[str] = None):
        """Send a streaming text chunk to the client."""
        await self.send_event(
            event_type="text_stream",
            data={
                "chunk": text_chunk,
                "message_id": message_id or f"{agent_name}_{int(asyncio.get_event_loop().time())}"
            },
            agent_name=agent_name
        )

    async def send_message_complete(self, full_message: str, agent_name: str, message_id: Optional[str] = None):
        """Send a complete message event."""
        await self.send_event(
            event_type="message_complete",
            data={
                "content": full_message,
                "message_id": message_id or f"{agent_name}_{int(asyncio.get_event_loop().time())}"
            },
            agent_name=agent_name
        )
    # Keep send_messages_snapshot as it's used in websocket adapter for conversation resuming
    async def send_messages_snapshot(self, messages: Any) -> None:
        """Emits a MessagesSnapshot event."""
        await self.send_event(event_type="MESSAGES_SNAPSHOT", data=messages)

    async def send_ui_tool(self, tool_id: str, payload: Any) -> None:
        """Emits a UI tool request event for front-end custom components."""
        await self.send_event(
            event_type="ui_tool",
            data={"toolId": tool_id, "payload": payload}
        )

    async def send_custom_event(self, name: str, value: Any) -> None:
        """Send simple custom event."""
        event_data = {
            "type": name,
            "data": value,
            "timestamp": int(time.time() * 1000)
        }
        await self.send_event(name, event_data)
    
    async def send_ui_component_route(self, agent_id: str, content: str, routing_decision: dict) -> None:
        """Send simplified UI routing decision."""
        if routing_decision.get("target") == "artifact":
            await self.send_custom_event("route_to_artifact", {
                "title": routing_decision.get("title", "Generated Content"),
                "content": content,
                "category": routing_decision.get("category", "general"),
                "artifact_id": f"artifact_{int(time.time())}",
                "agent_id": agent_id
            })
        else:
            await self.send_custom_event("route_to_chat", {
                "content": content,
                "component_type": routing_decision.get("component_type", "default"),
                "agent_id": agent_id
            })

    async def pause_conversation(self) -> Dict[str, Any]:
        """Pause the current conversation and save state."""
        from datetime import datetime
        from core.data.db_manager import mongodb_manager
        
        self.is_paused = True
        
        # Capture current conversation state with enhanced metadata
        self.conversation_state = {
            "chat_id": self.chat_id,
            "enterprise_id": self.enterprise_id,
            "workflow_type": self.workflow_type,
            "paused_at": datetime.utcnow().isoformat(),
            "workflow_started": self.workflow_started
        }
        
        # Save to database using the enhanced pause method
        await mongodb_manager.pause_chat(
            self.chat_id, 
            self.enterprise_id, 
            self.conversation_state,
            reason="user_requested"
        )
        
        await self.send_event("CONVERSATION_PAUSED", {
            "chatId": self.chat_id,
            "pausedAt": self.conversation_state["paused_at"]
        })
        
        log_business_event(
            event_type="conversation_paused",
            description=f"SSE conversation paused for chat {self.chat_id}",
            context={"chat_id": self.chat_id, "transport": "sse"}
        )
        
        return self.conversation_state
    
    async def resume_conversation(self, new_message: Optional[str] = None) -> bool:
        """Resume a paused conversation."""
        from datetime import datetime
        from core.data.db_manager import mongodb_manager
        
        try:
            # Load conversation state from database
            loaded_state = await mongodb_manager.resume_chat(self.chat_id, self.enterprise_id)
            
            if loaded_state and isinstance(loaded_state, dict):
                self.conversation_state = loaded_state
                self.workflow_started = loaded_state.get("workflow_started", False)
                self.is_paused = False
                
                # Send resume event to client
                await self.send_event("CONVERSATION_RESUMED", {
                    "chatId": self.chat_id,
                    "resumedAt": datetime.utcnow().isoformat(),
                    "previousPauseTime": loaded_state.get("paused_at")
                })
                
                log_business_event(
                    event_type="conversation_resumed",
                    description=f"SSE conversation resumed for chat {self.chat_id}",
                    context={"chat_id": self.chat_id, "transport": "sse"}
                )
                
                # Handle new message if provided during resume
                if new_message:
                    await self.handle_user_message(new_message)
                
                return True
            else:
                chat_logger.warning(f"No conversation state found for chat {self.chat_id}")
                return False
                
        except Exception as e:
            chat_logger.error(f"Error resuming SSE conversation: {e}")
            await self.send_event("CONVERSATION_RESUME_ERROR", {
                "chatId": self.chat_id,
                "error": str(e)
            })
            return False

    async def auto_start_workflow_if_appropriate(self):
        """
        Auto-start the workflow if it doesn't require user input to begin.
        This should be called after connection is established.
        """
        if self.workflow_started:
            return  # Already started
            
        if should_auto_start_workflow(self.workflow_type):
            business_logger.info(
                f"🚀 [SSE] Auto-starting workflow '{self.workflow_type}' for chat {self.chat_id} "
                f"(workflow does not require user input to begin)"
            )
            
            log_business_event(
                event_type="workflow_auto_started",
                description=f"Workflow auto-started on SSE connection",
                context={
                    "chat_id": self.chat_id,
                    "workflow_type": self.workflow_type,
                    "enterprise_id": self.enterprise_id,
                    "user_id": self.user_id
                }
            )
            
            # Start the workflow without requiring user input
            await self.handle_user_message(message_content=None)
        else:
            business_logger.info(
                f"⏳ [SSE] Workflow '{self.workflow_type}' for chat {self.chat_id} "
                f"waiting for user input to begin"
            )
            
            await self.send_event(
                event_type='status', 
                data={'message': 'Connected. Waiting for your message to start the conversation.'}
            )

class AG2SSEAdapter:
    """
    Manages all active SSE connections and orchestrates chat workflows.
    """
    
    def __init__(self, default_llm_config: Dict[str, Any]):
        self.active_connections: Dict[str, SSEConnection] = {}
        self.default_llm_config = default_llm_config
        business_logger.info("AG2SSEAdapter initialized.")

    async def _create_connection(self, chat_id: str, enterprise_id: str, user_id: str, workflow_type: str) -> SSEConnection:
        """Creates, stores, and initializes a new SSE connection."""
        connection_id = f"{enterprise_id}_{chat_id}_{user_id}"
        
        connection = SSEConnection(
            chat_id=chat_id,
            enterprise_id=enterprise_id,
            user_id=user_id,
            workflow_type=workflow_type,
            default_llm_config=self.default_llm_config
        )
        
        # Store and log new connection
        self.active_connections[connection_id] = connection
        log_business_event(event_type="sse_connection_created", description=f"New SSE connection for {connection_id}")
        
        return connection

    async def stream_events(self, chat_id: str, enterprise_id: str, user_id: str, workflow_type: str):
        """
        Creates a new SSE connection or reuses an existing one, returning the event generator.
        """
        connection_id = f"{enterprise_id}_{chat_id}_{user_id}"
        
        connection = self.active_connections.get(connection_id)
        if connection and connection.active:
            log_business_event(event_type="sse_connection_reused", description=f"Reusing active SSE connection for {connection_id}")
            return connection.event_generator()

        # Create a new connection if one doesn't exist or is inactive
        connection = await self._create_connection(chat_id, enterprise_id, user_id, workflow_type)
        
        # Auto-start workflow if appropriate (after connection is established)
        asyncio.create_task(connection.auto_start_workflow_if_appropriate())
            
        # Return the event generator to stream events to the client
        return connection.event_generator()

    async def handle_user_input(self, chat_id: str, enterprise_id: str, user_id: str, workflow_type: str, message: str):
        """
        Handles user input. If the connection is lost, it creates a new one to ensure
        the user's message is not lost.
        """
        connection_id = f"{enterprise_id}_{chat_id}_{user_id}"
        connection = self.active_connections.get(connection_id)

        if not connection or not connection.active:
            log_business_event(
                event_type="sse_connection_reestablished", 
                description=f"No active connection for {connection_id}. Re-establishing...", 
                level="WARNING"
            )
            # Create a new connection to handle the user's message seamlessly
            connection = await self._create_connection(chat_id, enterprise_id, user_id, workflow_type)

        await connection.handle_user_message(message)

    async def pause_conversation(self, chat_id: str, enterprise_id: str, user_id: str) -> Dict[str, Any]:
        """Pause a conversation in the SSE adapter."""
        connection_id = f"{enterprise_id}_{chat_id}_{user_id}"
        connection = self.active_connections.get(connection_id)
        
        if connection and connection.active:
            return await connection.pause_conversation()
        else:
            business_logger.warning(f"No active SSE connection found for {connection_id} to pause")
            return {}
    
    async def resume_conversation(self, chat_id: str, enterprise_id: str, user_id: str, 
                                new_message: Optional[str] = None) -> bool:
        """Resume a conversation in the SSE adapter."""
        connection_id = f"{enterprise_id}_{chat_id}_{user_id}"
        connection = self.active_connections.get(connection_id)
        
        if not connection or not connection.active:
            # Create a new connection if one doesn't exist
            workflow_type = "default"  # You might need to get this from the database
            connection = await self._create_connection(chat_id, enterprise_id, user_id, workflow_type)
        
        return await connection.resume_conversation(new_message)

    async def cleanup(self):
        """Cleans up all active connections."""
        for connection in self.active_connections.values():
            connection.active = False
            # This will cause the generator to break its loop and close
        self.active_connections.clear()
        business_logger.info("AG2SSEAdapter cleaned up all connections.")
