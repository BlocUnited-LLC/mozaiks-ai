# ==============================================================================
# FILE: core/ag2_websocket_adapter.py
# DESCRIPTION: AG2 WebSocket integration with IOStream and pause/resume support
# ==============================================================================
import json
import asyncio
import logging
import time
import uuid
from typing import Dict, Any, Optional, List
from datetime import datetime
from autogen.io import IOWebsockets
from autogen import GroupChatManager, GroupChat, ConversableAgent
from autogen.events.agent_events import GroupChatResumeEvent

from core.events.simple_protocols import SimpleCommunicationChannel
from core.workflow.init_registry import get_workflow_handler
from core.data.db_manager import mongodb_manager
from core.workflow.workflow_config import workflow_config
from logs.logging_config import (
    get_chat_logger, 
    get_business_logger, 
    get_performance_logger,
    log_business_event
)

# Logger setup
chat_logger = get_chat_logger("ag2_websocket_adapter")
business_logger = get_business_logger("ag2_websocket_adapter")
performance_logger = get_performance_logger("ag2_websocket_adapter")

def should_auto_start_workflow(workflow_type: str) -> bool:
    """
    Determine if a workflow should auto-start based on workflow configuration.
    Uses workflow.json to determine if human interaction is required.
    """
    # Use the dynamic workflow configuration
    return workflow_config.should_auto_start(workflow_type)

class AG2WebSocketConnection(SimpleCommunicationChannel):
    """AG2-native WebSocket connection using IOWebsockets with pause/resume support."""
    
    def __init__(self, chat_id: str, enterprise_id: str, user_id: str, workflow_type: str):
        self.chat_id = chat_id
        self.enterprise_id = enterprise_id
        self.user_id = user_id
        self.workflow_type = workflow_type
        self.iostream: Optional[IOWebsockets] = None
        self.group_chat_manager: Optional[GroupChatManager] = None
        self.group_chat: Optional[GroupChat] = None
        self.agents: List[ConversableAgent] = []
        self.workflow_started = False  # Track if workflow has been started
        self.is_paused = False
        self.conversation_state: Dict[str, Any] = {}
        self.workflow_started = False  # Track if workflow has been started
        
    async def auto_start_workflow_if_appropriate(self):
        """
        Auto-start the workflow if it doesn't require user input to begin.
        This should be called after connection is established.
        """
        if self.workflow_started:
            return  # Already started
            
        if should_auto_start_workflow(self.workflow_type):
            business_logger.info(
                f"🚀 [WS] Auto-starting workflow '{self.workflow_type}' for chat {self.chat_id} "
                f"(workflow does not require user input to begin)"
            )
            
            log_business_event(
                event_type="workflow_auto_started",
                description=f"Workflow auto-started on WebSocket connection",
                context={
                    "chat_id": self.chat_id,
                    "workflow_type": self.workflow_type,
                    "enterprise_id": self.enterprise_id,
                    "user_id": self.user_id,
                    "transport": "websocket"
                }
            )
            
            # Start the workflow without requiring user input
            await self.handle_user_message(message_content=None)
        else:
            business_logger.info(
                f"⏳ [WS] Workflow '{self.workflow_type}' for chat {self.chat_id} "
                f"waiting for user input to begin"
            )
            
            await self.send_event(
                event_type='status', 
                data={'message': 'Connected. Waiting for your message to start the conversation.'}
            )
    
    def _get_last_speaker(self) -> Optional[str]:
        """Get the name of the last speaker in the conversation."""
        if self.group_chat and self.group_chat.messages:
            last_message = self.group_chat.messages[-1]
            if isinstance(last_message, dict) and "name" in last_message:
                return last_message["name"]
            elif hasattr(last_message, "name"):
                return getattr(last_message, "name", None)
        return None
    
    def _get_current_workflow_stage(self) -> str:
        """Get the current workflow stage based on conversation state."""
        # This could be enhanced based on workflow-specific logic
        message_count = len(self.group_chat.messages) if self.group_chat else 0
        if message_count == 0:
            return "initialization"
        elif message_count < 5:
            return "early_stage"
        elif message_count < 15:
            return "mid_stage"
        else:
            return "advanced_stage"
        
    async def initialize(self, iostream: IOWebsockets, agents: List[ConversableAgent], 
                        group_chat: GroupChat, manager: GroupChatManager):
        """Initialize the connection with AG2 components."""
        self.iostream = iostream
        self.agents = agents
        self.group_chat = group_chat
        self.group_chat_manager = manager
        
        # Set up AG2 event streaming through our protocol
        self._setup_ag2_event_streaming()
        
        log_business_event(
            event_type="ag2_websocket_connection_initialized",
            description=f"AG2 WebSocket connection initialized for chat {self.chat_id}",
            context={"chat_id": self.chat_id, "agent_count": len(agents)}
        )
    
    def _setup_ag2_event_streaming(self):
        """Set up AG2 event streaming to emit Simple Events."""
        # Hook into AG2's event system to stream events via our protocol
        for agent in self.agents:
            if hasattr(agent, 'register_hook'):
                agent.register_hook("process_message_before_send", self._on_agent_message_hook)
                agent.register_hook("process_all_messages_before_reply", self._on_agent_processing_hook)
    
    def _on_agent_message_hook(self, sender, message):
        """Hook called when an agent sends a message."""
        message_id = str(uuid.uuid4())
        sender_name = getattr(sender, 'name', 'unknown')
        content = message.get("content", "") if isinstance(message, dict) else str(message)
        
        # Stream the message via Simple Events protocol
        asyncio.create_task(self._stream_agent_message(message_id, sender_name, content))
        return message
    
    def _on_agent_processing_hook(self, recipient, messages, sender, config):
        """Hook called when an agent starts processing."""
        recipient_name = getattr(recipient, 'name', 'unknown')
        asyncio.create_task(self.send_event("AGENT_PROCESSING_START", {"agentName": recipient_name}))
        return messages
    
    async def _stream_agent_message(self, message_id: str, sender_name: str, content: str):
        """Stream an agent message using Simple Events text streaming protocol."""
        await self.send_text_message_start(message_id, "assistant")
        
        # Stream content in chunks for better UX
        chunk_size = 50
        for i in range(0, len(content), chunk_size):
            chunk = content[i:i + chunk_size]
            await self.send_text_message_content(message_id, chunk)
            await asyncio.sleep(0.1)  # Small delay for streaming effect
            
        await self.send_text_message_end(message_id)
    
    async def pause_conversation(self) -> Dict[str, Any]:
        """Pause the current conversation and save state."""
        self.is_paused = True
        
        # Capture current conversation state with enhanced metadata
        self.conversation_state = {
            "messages": self.group_chat.messages.copy() if self.group_chat else [],
            "chat_id": self.chat_id,
            "enterprise_id": self.enterprise_id,
            "workflow_type": self.workflow_type,
            "paused_at": datetime.utcnow().isoformat(),
            "agent_names": [agent.name for agent in self.agents],
            "last_speaker": self._get_last_speaker(),
            "workflow_stage": self._get_current_workflow_stage()
        }
        
        # Save to database using the enhanced pause method
        await mongodb_manager.pause_chat(
            self.chat_id, 
            self.enterprise_id, 
            self.conversation_state,
            reason="user_requested"
        )
        
        # Also save a conversation snapshot for quick restoration
        await mongodb_manager.save_conversation_snapshot(
            self.chat_id,
            self.enterprise_id,
            self.conversation_state["messages"],
            {
                "last_speaker": self.conversation_state.get("last_speaker"),
                "workflow_stage": self.conversation_state.get("workflow_stage"),
                "pause_reason": "user_requested"
            }
        )
        
        await self.send_event("CONVERSATION_PAUSED", {
            "chatId": self.chat_id,
            "pausedAt": self.conversation_state["paused_at"],
            "messageCount": len(self.conversation_state["messages"])
        })
        
        log_business_event(
            event_type="conversation_paused",
            description=f"Conversation paused for chat {self.chat_id}",
            context={"chat_id": self.chat_id, "message_count": len(self.conversation_state["messages"])}
        )
        
        return self.conversation_state
    
    async def resume_conversation(self, new_message: Optional[str] = None) -> bool:
        """Resume a paused conversation."""
        try:
            if not self.conversation_state and not await self._load_conversation_state():
                chat_logger .error(f"No conversation state found for chat {self.chat_id}")
                return False
            
            self.is_paused = False
            
            # Use AG2's resume functionality
            if self.group_chat_manager and self.conversation_state.get("messages"):
                # Prepare for resuming using AG2's built-in resume
                last_agent, last_message = self.group_chat_manager.resume(
                    messages=self.conversation_state["messages"]
                )
                
                # Emit resume event
                resume_event = GroupChatResumeEvent(
                    last_speaker_name=last_agent.name if last_agent else "unknown",
                    events=[]
                )
                await self.send_event("GROUP_CHAT_RESUMED", {
                    "lastSpeaker": last_agent.name if last_agent else None,
                    "resumedAt": datetime.utcnow().isoformat()
                })
                
                # Send messages snapshot for frontend to rebuild state
                await self.send_messages_snapshot(self.conversation_state["messages"])
                
                # Continue with new message or last message
                message_to_use = new_message or "Continue the conversation"
                if isinstance(last_message, dict) and "content" in last_message:
                    message_to_use = new_message or last_message["content"]
                
                # Resume the chat
                await last_agent.a_initiate_chat(
                    recipient=self.group_chat_manager,
                    message=message_to_use,
                    clear_history=False
                )
                
                log_business_event(
                    event_type="conversation_resumed",
                    description=f"Conversation resumed for chat {self.chat_id}",
                    context={"chat_id": self.chat_id, "last_speaker": last_agent.name if last_agent else None}
                )
                
                return True
            
        except Exception as e:
            chat_logger .exception(f"Error resuming conversation for chat {self.chat_id}: {e}")
            await self.send_event("RESUME_ERROR", {"error": str(e)})
            return False
        
        return False  # Default return if no conditions are met
    
    async def _load_conversation_state(self) -> bool:
        """Load conversation state from database."""
        try:
            chat_state = await mongodb_manager.load_chat_state(self.chat_id, self.enterprise_id)
            if chat_state and "conversation_state" in chat_state:
                self.conversation_state = chat_state["conversation_state"]
                return True
            return False
        except Exception as e:
            chat_logger .error(f"Failed to load conversation state: {e}")
            return False
    
    async def handle_human_input(self, message: str) -> None:
        """Handle human input during conversation."""
        # Mark workflow as started to prevent duplicate starts
        self.workflow_started = True
        
        # For now, just track the input - specific iostream handling depends on AG2 version
        if message:  # Only log non-empty messages (avoid logging auto-start empty messages)
            chat_logger .info(f"Received human input for chat {self.chat_id}: {message[:100]}...")
        
        # Note: Token management is handled at the workflow/core level
        
        await self.send_event("HUMAN_INPUT_RECEIVED", {
            "message": message,
            "timestamp": datetime.utcnow().isoformat(),
            "auto_start": not bool(message)  # Flag if this was an auto-start
        })
    
    async def handle_user_message(self, message_content: Optional[str]):
        """
        Processes a user message using workflow handler, similar to SSE adapter.
        
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
                        "message_length": len(message_content) if message_content else 0,
                        "transport": "websocket"
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
                        "auto_start": True,
                        "transport": "websocket"
                    }
                )

            # Run the workflow - token management is handled at the core level
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

    # CommunicationChannel implementation
    async def send_event(self, event_type: str, data: Any, agent_name: Optional[str] = None) -> None:
        """Enhanced event sending with streaming support."""
        event_data = {
            "type": event_type,
            "data": data,
            "timestamp": int(time.time() * 1000)
        }
        if agent_name:
            event_data["agent_name"] = agent_name
        
        # Send via IOWebsockets if available
        if self.iostream:
            try:
                json_data = json.dumps(event_data)
                self.iostream.websocket.send(json_data)
                
                # Log streaming events
                if event_type.startswith("text_stream"):
                    chat_logger.debug(f"📡 [WS] Streaming event: {event_type}")
                elif event_type in ["TEXT_MESSAGE_START", "TEXT_MESSAGE_CONTENT", "TEXT_MESSAGE_END"]:
                    chat_logger.debug(f"📡 [WS] Message event: {event_type}")
                else:
                    business_logger.debug(f"📡 [WS] Event sent: {event_type} for chat {self.chat_id}")
                    
            except Exception as e:
                chat_logger.error(f"❌ [WS] Error sending streaming event: {e}")
        else:
            business_logger.debug(f"No iostream available, event {event_type} logged only")

    async def send_text_message_start(self, message_id: str, role: str) -> None:
        await self.send_event("TEXT_MESSAGE_START", {"messageId": message_id, "role": role})

    async def send_text_message_content(self, message_id: str, delta: str) -> None:
        await self.send_event("TEXT_MESSAGE_CONTENT", {"messageId": message_id, "delta": delta})

    async def send_text_message_end(self, message_id: str) -> None:
        await self.send_event("TEXT_MESSAGE_END", {"messageId": message_id})

    # Keep send_messages_snapshot as it's used for conversation resuming
    async def send_messages_snapshot(self, messages: Any) -> None:
        await self.send_event("MESSAGES_SNAPSHOT", messages)

    async def send_ui_tool(self, tool_id: str, payload: Any) -> None:
        """Emits a UI tool request event for front-end custom components."""
        await self.send_event(
            event_type="ui_tool",
            data={"toolId": tool_id, "payload": payload}
        )
    
    async def send_ui_component_route(self, agent_id: str, content: str, routing_decision: Dict[str, Any]) -> None:
        """Send UI component routing decision following AG2-compatible patterns."""
        await self.send_event(
            event_type="ui_component_route",
            data={
                "agentId": agent_id,
                "content": content,
                "routingDecision": routing_decision
            },
            agent_name=agent_id
        )
    
    async def send_custom_event(self, name: str, value: Any) -> None:
        """Send custom event following AG2-compatible patterns."""
        await self.send_event(
            event_type="custom_event",
            data={"name": name, "value": value}
        )


class AG2WebSocketManager:
    """Manager for AG2 WebSocket connections with native IOWebsockets support."""
    
    def __init__(self):
        self.active_connections: Dict[str, AG2WebSocketConnection] = {}
    
    async def create_connection(self, iostream: IOWebsockets, chat_id: str, enterprise_id: str, 
                             user_id: str, workflow_type: str) -> AG2WebSocketConnection:
        """Create a new AG2 WebSocket connection."""
        connection_id = f"{enterprise_id}_{chat_id}_{user_id}"
        
        connection = AG2WebSocketConnection(chat_id, enterprise_id, user_id, workflow_type)
        self.active_connections[connection_id] = connection
        
        return connection
    
    def get_connection(self, chat_id: str, enterprise_id: str, user_id: str) -> Optional[AG2WebSocketConnection]:
        """Get an existing connection."""
        connection_id = f"{enterprise_id}_{chat_id}_{user_id}"
        return self.active_connections.get(connection_id)
    
    async def pause_conversation(self, chat_id: str, enterprise_id: str, user_id: str) -> Dict[str, Any]:
        """Pause a conversation."""
        connection = self.get_connection(chat_id, enterprise_id, user_id)
        if connection:
            return await connection.pause_conversation()
        return {}
    
    async def resume_conversation(self, chat_id: str, enterprise_id: str, user_id: str, 
                                new_message: Optional[str] = None) -> bool:
        """Resume a conversation."""
        connection = self.get_connection(chat_id, enterprise_id, user_id)
        if connection:
            return await connection.resume_conversation(new_message)
        return False


# Global manager instance
ag2_websocket_manager = AG2WebSocketManager()