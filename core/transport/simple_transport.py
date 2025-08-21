# ==============================================================================
# FILE: core/transport/simple_transport.py
# DESCRIPTION: Lean transport system for real-time UI communication
# ==============================================================================
import logging
import asyncio
import re
import json
import traceback
from typing import Dict, Any, Optional, Union, Tuple, List
from fastapi import WebSocket
from fastapi.responses import StreamingResponse
from datetime import datetime

# AG2 imports for event type checking
from autogen.events import BaseEvent

# Import workflow configuration for agent visibility filtering
from core.workflow.workflow_config import workflow_config
from core.workflow.helpers import get_formatted_agent_name

# Logging setup
logger = logging.getLogger(__name__)

# Import chat logger for agent message tracking
from logs.logging_config import get_chat_logger

# Get our chat logger (logging setup happens in main app)
chat_logger = get_chat_logger("agent_messages")

# ==================================================================================
# COMMUNICATION CHANNEL WRAPPER & MESSAGE FILTERING
# ==================================================================================

class MessageFilter:
    """Simple message filter to remove AutoGen noise"""
    
    def should_stream_message(self, sender_name: str, message_content: str) -> bool:
        """Core filtering logic - this is the real MVP"""
        
        # Filter out internal AutoGen agents
        internal_agents = {"chat_manager", "manager", "coordinator", "groupchat_manager"}
        if sender_name.lower() in internal_agents:
            return False
        
        # Filter out empty or very short messages
        if not message_content or len(message_content.strip()) < 5:
            return False
        
        # Filter out coordination messages
        coordination_keywords = [
            "next speaker:", "terminating.", "function_call", "recipient:",
            "sender:", "groupchat_manager", "Let me route this"
        ]
        content_lower = message_content.lower()
        if any(keyword in content_lower for keyword in coordination_keywords):
            return False
        
        # Filter out JSON-like structures and UUIDs
        if message_content.strip().startswith(("{", "[")) or len(message_content.replace("-", "")) == 32:
            return False
        
        return True

# ==================================================================================
# MAIN TRANSPORT CLASS
# ==================================================================================

class SimpleTransport:
    """
    Lean transport system focused solely on real-time UI communication.
    
    Features:
    - Message filtering (removes AutoGen noise)
    - WebSocket connection management
    - Event forwarding to the UI
    - Thread-safe singleton pattern
    """
    
    _instance = None
    _lock = asyncio.Lock()
    
    @classmethod
    async def get_instance(cls, *args, **kwargs):
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    # Call __new__ and __init__ inside the lock
                    instance = super().__new__(cls)
                    instance.__init__(*args, **kwargs)
                    cls._instance = instance
        return cls._instance

    def __init__(self):
        # Prevent re-initialization of singleton
        if hasattr(self, '_initialized'):
            return
            
        self.connections: Dict[str, Dict[str, Any]] = {}
        self.message_filter = MessageFilter()
        
        # User input collection mechanism
        self.pending_input_requests: Dict[str, asyncio.Future] = {}
        self.pending_ui_tool_responses: Dict[str, asyncio.Future] = {}
        
        # Mark as initialized
        self._initialized = True
        
        logger.info("🚀 SimpleTransport singleton initialized")
        
    # ==================================================================================
    # USER INPUT COLLECTION (Production-Ready)
    # ==================================================================================
    
    async def send_user_input_request(
        self,
        input_request_id: str,
        chat_id: str,
        payload: Dict[str, Any]
    ) -> None:
        """
        Send a dedicated user input request to the frontend.
        This is decoupled from the ui_tool_event system.
        """
        event_data = {
            "type": "user_input_request",
            "data": {
                "input_request_id": input_request_id,
                "chat_id": chat_id,
                "payload": payload,
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        await self._broadcast_to_websockets(event_data, chat_id)
        logger.info(f"📤 Sent user input request {input_request_id} to chat {chat_id}")

    @classmethod
    async def wait_for_user_input(cls, input_request_id: str) -> str:
        """
        Wait indefinitely for user input response for a specific input request.
        
        This is called by AG2StreamingIOStream when agents request user input.
        The frontend will call submit_user_input() to provide the response.
        
        No timeout - like ChatGPT, we wait indefinitely. Users can resume conversations
        using the AG2 resume functionality if they leave and come back.
        """
        # Access the singleton instance
        instance = cls._get_instance()
        if not instance:
            raise RuntimeError("SimpleTransport instance not available")
            
        if input_request_id not in instance.pending_input_requests:
            # Create a future to wait for the input
            instance.pending_input_requests[input_request_id] = asyncio.Future()
        
        try:
            # Wait indefinitely for user input - no timeout
            user_input = await instance.pending_input_requests[input_request_id]
            return user_input
        finally:
            # Clean up the pending request
            if input_request_id in instance.pending_input_requests:
                del instance.pending_input_requests[input_request_id]
    
    async def submit_user_input(self, input_request_id: str, user_input: str) -> bool:
        """
        Submit user input response for a pending input request.
        
        This method is called by the API endpoint when the frontend submits user input.
        """
        if input_request_id in self.pending_input_requests:
            future = self.pending_input_requests[input_request_id]
            if not future.done():
                future.set_result(user_input)
                logger.info(f"✅ [INPUT] Submitted user input for request {input_request_id}")
                return True
            else:
                logger.warning(f"⚠️ [INPUT] Request {input_request_id} already completed")
                return False
        else:
            logger.warning(f"⚠️ [INPUT] No pending request found for {input_request_id}")
            return False
    
    @classmethod
    def _get_instance(cls):
        if cls._instance is None:
            raise RuntimeError("SimpleTransport has not been initialized. Call get_instance() first.")
        return cls._instance
    
    @classmethod
    async def reset_instance(cls):
        async with cls._lock:
            cls._instance = None
            
    def should_show_to_user(self, agent_name: Optional[str], chat_id: Optional[str] = None) -> bool:
        """Check if a message should be shown to the user interface"""
        if not agent_name:
            return True  # Show system messages
        
        # Get the workflow type for this chat session
        workflow_name = None
        if chat_id and chat_id in self.connections:
            workflow_name = self.connections[chat_id].get("workflow_name")
        
        # If we have workflow type, use visual_agents filtering
        if workflow_name:
            try:
                config = workflow_config.get_config(workflow_name)
                visual_agents = config.get("visual_agents")
                
                # If visual_agents is defined, only show messages from those agents
                if isinstance(visual_agents, list):
                    # Normalize both the agent name and visual_agents list for comparison
                    # This matches the frontend normalization logic in ChatPage.js
                    def normalize_agent(name):
                        if not name:
                            return ''
                        return str(name).lower().replace('agent', '').replace(' ', '').strip()
                    
                    normalized_agent = normalize_agent(agent_name)
                    normalized_visual_agents = [normalize_agent(va) for va in visual_agents]
                    
                    is_allowed = normalized_agent in normalized_visual_agents
                    logger.debug(f"🔍 Backend visual_agents check: '{agent_name}' -> '{normalized_agent}' in {normalized_visual_agents} = {is_allowed}")
                    return is_allowed
            except FileNotFoundError:
                # If no specific config, default to showing the message
                pass
        
        return True
        
    def format_agent_name(self, agent_name: Optional[str]) -> str:
        """Format agent name for display using the centralized helper."""
        return get_formatted_agent_name(agent_name)
    
    # ==================================================================================
    # CORE MESSAGE SENDING
    # ==================================================================================
    
    async def send_to_ui(
        self,
        message: Union[str, Dict[str, Any], Any],
        agent_name: Optional[str] = None,
        message_type: str = "chat_message",
        chat_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        bypass_filter: bool = False,
    ) -> None:
        """
        Send messages to UI via WebSocket broadcast.
        """
        
        # Extract clean content from AG2 UUID-formatted messages
        clean_message = self._extract_clean_content(message)
        
        # Filter out unwanted system messages before any processing
        if not bypass_filter:
            if isinstance(clean_message, str):
                if not self.message_filter.should_stream_message(agent_name or "system", clean_message):
                    return
        
        # If agent_name is generic (Unknown Agent, Assistant, system), try to extract from message content
        if agent_name in [None, "Unknown Agent", "Assistant", "system"] and isinstance(message, str):
            extracted_name = self._extract_agent_name_from_uuid_content(message)
            if extracted_name:
                agent_name = extracted_name
        
        # Additional extraction for stringified content that didn't match UUID pattern
        if agent_name in [None, "Unknown Agent", "Assistant", "system"] and isinstance(clean_message, str):
            # Try to extract from various AG2 format patterns
            import re
            # Pattern: sender='AgentName'
            sender_match = re.search(r"sender='([^']+)'", clean_message)
            if not sender_match:
                sender_match = re.search(r'sender="([^"]+)"', clean_message)
            if sender_match:
                extracted = sender_match.group(1)
                if extracted and extracted not in ["user", "system"]:
                    agent_name = extracted
        
        # For simple strings, apply traditional visibility filtering
        if not bypass_filter:
            if isinstance(clean_message, str):
                if not self.should_show_to_user(agent_name, chat_id):
                    return
        
        # Format agent name
        formatted_agent = self.format_agent_name(agent_name)
        
        # Log agent message to agent_chat.log for tracking
        if isinstance(clean_message, str) and formatted_agent and formatted_agent != "Assistant":
            chat_logger.info(f"AGENT_MESSAGE | Chat: {chat_id} | Agent: {formatted_agent} | Message: {clean_message}")
        elif isinstance(clean_message, str):
            chat_logger.info(f"SYSTEM_MESSAGE | Chat: {chat_id} | Message: {clean_message}")
        
        # Create event data
        event_data = {
            "type": "chat_message",
            "data": {
                "message": str(clean_message),
                "agent_name": formatted_agent,
                "chat_id": chat_id,
                "metadata": metadata or {},
                "message_type": message_type
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Broadcast to WebSocket connections only
        await self._broadcast_to_websockets(event_data, chat_id)
        
        logger.info(f"📤 {formatted_agent}: {str(clean_message)[:100]}...")

    # Token usage is tracked from UsageSummaryEvent, not by ad-hoc captures here
        
    # ==================================================================================
    # AG2 EVENT SENDING
    # ==================================================================================
    
    async def send_event_to_ui(self, event: Any, chat_id: Optional[str] = None) -> None:
        """
        Serializes and sends a raw AG2 event to the UI.
        This is the primary method for forwarding AG2 native events.
        """
        try:
            # Filter events based on agent visibility before sending
            agent_name = None
            if hasattr(event, 'sender') and hasattr(event.sender, 'name'): # type: ignore
                agent_name = event.sender.name # type: ignore
            
            if not self.should_show_to_user(agent_name, chat_id):
                logger.debug(f"🚫 Filtered out AG2 event from agent '{agent_name}' for chat {chat_id}")
                return

            # Basic serialization for UI consumption
            # In a real-world scenario, you might use Pydantic's .dict() or a custom serializer
            if isinstance(event, BaseEvent):
                try:
                    payload = event.dict()
                except Exception:
                    # Try pydantic v2
                    try:
                        payload = event.model_dump()  # type: ignore[attr-defined]
                    except Exception:
                        payload = {
                            "event_type": type(event).__name__,
                            "content": self._stringify_unknown(getattr(event, "content", None)),
                        }
            else:
                # Fallback for non-pydantic objects
                payload = {"event_type": type(event).__name__, "content": self._stringify_unknown(event)}

            event_data = {
                "type": "ag2_event",
                "data": payload,
                "timestamp": datetime.utcnow().isoformat()
            }
            await self._broadcast_to_websockets(event_data, chat_id)
            logger.debug(f"📤 Forwarded AG2 event {type(event).__name__} to chat {chat_id}")

        except Exception as e:
            logger.error(f"❌ Failed to serialize or send AG2 event: {e}\n{traceback.format_exc()}")

    def _extract_clean_content(self, message: Union[str, Dict[str, Any], Any]) -> str:
        """Extract clean content from AG2 UUID-formatted messages or other formats."""
        
        # Handle string messages (most common case)
        if isinstance(message, str):
            # Check for AG2's UUID format and extract only the 'content' part
            match = re.search(r"content='(.*?)'", message, re.DOTALL)
            if match:
                return match.group(1)
            return message  # Return original string if not in UUID format
        elif isinstance(message, dict):
            # Handle dictionary messages
            return message.get('content', str(message))
        else:
            # Handle any other type by converting to string
            return str(message)
        
    def _extract_agent_name_from_uuid_content(self, content: str) -> Optional[str]:
        """Extract actual agent name from AG2 UUID-formatted message content."""
        import re
        
        # AG2 format: "uuid=UUID('...') content='...' sender='AgentName' recipient='...'"
        # Look for sender='AgentName' pattern
        sender_match = re.search(r"sender='([^']+)'", content)
        if sender_match:
            return sender_match.group(1)
        
        # Fallback patterns if above doesn't work
        sender_match_quotes = re.search(r'sender="([^"]+)"', content)
        if sender_match_quotes:
            return sender_match_quotes.group(1)
        
        return None  # no agent found
        
    async def _broadcast_to_websockets(self, event_data: Dict[str, Any], target_chat_id: Optional[str] = None) -> None:
        """Broadcast event data to relevant WebSocket connections."""
        active_connections = list(self.connections.items())
        
        # If a chat_id is specified, only send to that connection
        if target_chat_id:
            connection_info = self.connections.get(target_chat_id)
            if connection_info and connection_info.get("websocket"):
                try:
                    await connection_info["websocket"].send_json(event_data)
                except Exception as e:
                    logger.warning(f"⚠️ Failed to send to WebSocket for chat {target_chat_id}: {e}")
            return

        # Otherwise, broadcast to all connections
        for chat_id, info in active_connections:
            websocket = info.get("websocket")
            if websocket:
                try:
                    await websocket.send_json(event_data)
                except Exception as e:
                    logger.warning(f"⚠️ Failed to send to WebSocket for chat {chat_id}: {e}", exc_info=False)

    def _stringify_unknown(self, obj: Any) -> str:
        """Safely convert any object to a string for logging/transport."""
        try:
            if obj is None:
                return ""
            if isinstance(obj, (str, int, float, bool)):
                return str(obj)
            # Try JSON first with default=str to preserve structure
            return json.dumps(obj, default=str)
        except Exception:
            try:
                return str(obj)
            except Exception:
                return "<unserializable>"
        
    async def send_error(
        self,
        error_message: str,
        error_code: str = "GENERAL_ERROR",
        chat_id: Optional[str] = None
    ) -> None:
        """Send error message to UI via WebSocket"""
        event_data = {
            "type": "error",
            "data": {
                "message": error_message,
                "error_code": error_code,
                "chat_id": chat_id
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
        await self._broadcast_to_websockets(event_data, chat_id)
        logger.error(f"❌ Error: {error_message}")
        
    async def send_status(
        self,
        status_message: str,
        status_type: str = "info",
        chat_id: Optional[str] = None
    ) -> None:
        """Send status update to UI via WebSocket"""
        event_data = {
            "type": "status",
            "data": {
                "message": status_message,
                "status_type": status_type,
                "chat_id": chat_id
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
        await self._broadcast_to_websockets(event_data, chat_id)
        logger.info(f"ℹ️ Status: {status_message}")
    
    # ==================================================================================
    # CONNECTION MANAGEMENT METHODS
    # ==================================================================================
    
    async def handle_websocket(
        self,
        websocket: WebSocket,
        chat_id: str,
        user_id: str,
        workflow_name: str,
        enterprise_id: Optional[str] = None
    ) -> None:
        """Handle WebSocket connection for real-time communication"""
        await websocket.accept()
        self.connections[chat_id] = {
            "websocket": websocket,
            "user_id": user_id,
            "workflow_name": workflow_name,
            "enterprise_id": enterprise_id,
            "active": True,
        }
        logger.info(f"🔌 WebSocket connected for chat_id: {chat_id}")
        try:
            while True:
                # Keep the connection alive, processing is handled by the API
                await asyncio.sleep(1)
        except Exception as e:
            logger.warning(f"WebSocket error for chat {chat_id}: {e}")
        finally:
            if chat_id in self.connections:
                del self.connections[chat_id]
                logger.info(f"🔌 WebSocket disconnected for chat_id: {chat_id}")

    # ==================================================================================
    # WORKFLOW INTEGRATION METHODS
    # ==================================================================================
    
    async def handle_user_input_from_api(
        self, 
        chat_id: str, 
        user_id: Optional[str], 
        workflow_name: str, 
        message: Optional[str],
        enterprise_id: str
    ) -> Dict[str, Any]:
        """
        Handle user input from the POST API endpoint
        Integrates with workflow registry and follows the documented event system
        
        Args:
            message: User message or None for auto-start without user input
        """
        try:
            from core.workflow.orchestration_patterns import run_workflow_orchestration
            
            # This is now the single entry point for any workflow
            result = await run_workflow_orchestration(
                workflow_name=workflow_name,
                enterprise_id=enterprise_id,
                chat_id=chat_id,
                user_id=user_id,
                initial_message=message
            )
            
            # The result from AG2 is now a rich object, but for the API response,
            # we can return a simple success message. The UI will get all details
            # via WebSocket events in real-time.
            return {"status": "success", "chat_id": chat_id, "message": "Workflow started successfully."}
            
        except Exception as e:
            logger.error(f"❌ Workflow execution failed for chat {chat_id}: {e}\n{traceback.format_exc()}")
            await self.send_error(
                error_message=f"An internal error occurred: {e}",
                error_code="WORKFLOW_EXECUTION_FAILED",
                chat_id=chat_id
            )
            return {"status": "error", "chat_id": chat_id, "message": str(e)}

    # ==================================================================================
    # SIMPLIFIED EVENT API - WEBSOCKET ONLY
    # ==================================================================================
    
    async def send_chat_message(
        self, 
        message: str, 
        agent_name: Optional[str] = None, 
        chat_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Send chat message to user interface"""
        await self.send_to_ui(message, agent_name, "chat_message", chat_id, metadata)
    
    async def send_simple_text_message(self, content: str, chat_id: Optional[str] = None, agent_name: Optional[str] = None) -> None:
        """
        Send simple text message using AG2's official approach with agent context.
        Based on: https://docs.ag2.ai/latest/docs/_blogs/2025-01-10-WebSockets/
        """
        if chat_id and chat_id in self.connections:
            # This method is now simplified as the main send_to_ui handles formatting
            await self.send_chat_message(content, agent_name or "Assistant", chat_id)
    
    # ==================================================================================
    # UI TOOL EVENT HANDLING (Companion to user input)
    # ==================================================================================
    
    async def send_ui_tool_event(
        self,
        event_id: str,
        chat_id: Optional[str],
        tool_name: str,
        component_name: str,
        display_type: str,
        payload: Dict[str, Any]
    ) -> None:
        """
        Send a dedicated event to the frontend to render a specific UI component.
        """
        event_data = {
            "type": "ui_tool_event",
            "data": {
                "event_id": event_id,
                "chat_id": chat_id,
                "tool_name": tool_name,
                "component_name": component_name,
                "display_type": display_type,
                "payload": payload,
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        await self._broadcast_to_websockets(event_data, chat_id)
        logger.info(f"📤 Sent UI tool event {event_id} ({component_name}) to chat {chat_id}")

    @classmethod
    async def wait_for_ui_tool_response(cls, event_id: str) -> Dict[str, Any]:
        """
        Wait indefinitely for a response from a UI tool component.
        
        This is called by agent tools after they emit a UI tool event.
        The frontend will call submit_ui_tool_response() to provide the data.
        """
        instance = cls._get_instance()
        if not instance:
            raise RuntimeError("SimpleTransport instance not available")
            
        if event_id not in instance.pending_ui_tool_responses:
            instance.pending_ui_tool_responses[event_id] = asyncio.Future()
        
        try:
            response_data = await instance.pending_ui_tool_responses[event_id]
            return response_data
        finally:
            if event_id in instance.pending_ui_tool_responses:
                del instance.pending_ui_tool_responses[event_id]

    async def submit_ui_tool_response(self, event_id: str, response_data: Dict[str, Any]) -> bool:
        """
        Submit response data for a pending UI tool event.
        
        This method is called by an API endpoint when the frontend submits data
        from an interactive UI component.
        """
        if event_id in self.pending_ui_tool_responses:
            future = self.pending_ui_tool_responses[event_id]
            if not future.done():
                future.set_result(response_data)
                logger.info(f"✅ [UI_TOOL] Submitted response for event {event_id}")
                return True
            else:
                logger.warning(f"⚠️ [UI_TOOL] Event {event_id} already completed")
                return False
        else:
            logger.warning(f"⚠️ [UI_TOOL] No pending event found for {event_id}")
            return False


