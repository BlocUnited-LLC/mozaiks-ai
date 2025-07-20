# ==============================================================================
# FILE: core/transport/simple_transport.py
# DESCRIPTION: Complete transport system with AG2 resume functionality
# ==============================================================================
import json
import logging
import re
from typing import Dict, Any, Optional, Union, Tuple, List
from fastapi import WebSocket
from fastapi.responses import StreamingResponse
from datetime import datetime
import asyncio
import time

# AG2 imports for resume functionality
from autogen import Agent, GroupChatManager
from autogen.agentchat.groupchat import GroupChat

# Logging setup
logger = logging.getLogger(__name__)

# Import chat logger for agent message tracking
from logs.logging_config import get_chat_logger, setup_logging

# Ensure logging is set up and create our chat loggers
try:
    setup_logging()
except:
    pass  # Logging may already be set up

chat_logger = get_chat_logger("agent_messages")  # Specific logger for agent messages

# ==================================================================================
# COMMUNICATION CHANNEL WRAPPER
# ==================================================================================

class SimpleCommunicationChannelWrapper:
    """Wrapper class for AG2 communication channel integration"""
    
    def __init__(self, transport_instance, chat_id: str):
        self.transport = transport_instance
        self.chat_id = chat_id
        
    async def send_message(self, message: str, agent_name: Optional[str] = None):
        """Send a message through the transport layer"""
        await self.transport.stream_message_to_user(self.chat_id, message, agent_name)
        
    async def send_event(self, event_type: str, data: dict, agent_name: Optional[str] = None):
        """Send an event through the transport layer SSE system"""
        # Create event data structure
        event_data = {
            "type": event_type,
            "data": data,
            "timestamp": datetime.utcnow().isoformat()
        }
        # Use the internal broadcast method
        await self.transport._broadcast_to_sse(event_data, self.chat_id)
        
    async def get_user_input(self, prompt: Optional[str] = None) -> str:
        """Get user input through the transport layer"""
        # This would integrate with the user input collection system
        import time
        input_request_id = f"{self.chat_id}_{int(time.time())}"
        
        # Send user input request via SSE
        event_data = {
            "type": "user_input_request",
            "data": {"request_id": input_request_id, "prompt": prompt or "Please provide input:"},
            "timestamp": datetime.utcnow().isoformat()
        }
        await self.transport._broadcast_to_sse(event_data, self.chat_id)
        
        # Wait for user response
        return await SimpleTransport.wait_for_user_input(input_request_id)

# ==================================================================================
# MESSAGE FILTERING
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
# PERSISTENCE FUNCTIONALITY
# ==================================================================================

class PersistenceManager:
    """Simplified persistence for AG2 groupchat resume"""
    
    def __init__(self):
        from core.core_config import get_mongo_client
        self.client = get_mongo_client()
        self.db = self.client['autogen_ai_agents']
        self.workflows_collection = self.db['Workflows']
    
    async def save_ag2_state(
        self,
        chat_id: str,
        enterprise_id: str,
        groupchat: GroupChat,
        manager: GroupChatManager
    ) -> bool:
        """Save AG2 groupchat state for resume"""
        try:
            # Note: manager parameter available for future use if needed
            # Convert messages to AG2 format
            ag2_messages = []
            if hasattr(groupchat, 'messages') and groupchat.messages:
                for msg in groupchat.messages:
                    if isinstance(msg, dict):
                        ag2_messages.append({
                            "content": msg.get("content", str(msg)),
                            "role": msg.get("role", "assistant"),
                            "name": msg.get("name", msg.get("sender", "unknown"))
                        })
                    else:
                        ag2_messages.append({
                            "content": str(msg),
                            "role": "assistant",
                            "name": "unknown"
                        })
            
            # Create persistence document
            doc = {
                "chat_id": chat_id,
                "enterprise_id": enterprise_id,
                "ag2_state": {
                    "messages": ag2_messages,
                    "message_count": len(ag2_messages),
                    "can_resume": True
                },
                "last_updated": datetime.utcnow(),
                "status": "active"
            }
            
            await self.workflows_collection.update_one(
                {"chat_id": chat_id, "enterprise_id": enterprise_id},
                {"$set": doc},
                upsert=True
            )
            
            logger.info(f"💾 Saved AG2 state: {len(ag2_messages)} messages")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to save AG2 state: {e}")
            return False
    
    async def load_ag2_state(self, chat_id: str, enterprise_id: str) -> Optional[Dict[str, Any]]:
        """Load AG2 groupchat state for resume"""
        try:
            workflow = await self.workflows_collection.find_one(
                {"chat_id": chat_id, "enterprise_id": enterprise_id}
            )
            
            if workflow and workflow.get("ag2_state", {}).get("can_resume", False):
                return workflow["ag2_state"]
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Failed to load AG2 state: {e}")
            return None
    
    async def resume_ag2_groupchat(
        self,
        chat_id: str,
        enterprise_id: str,
        groupchat: GroupChat,
        manager: GroupChatManager
    ) -> Tuple[bool, Optional[str]]:
        """Resume AG2 groupchat using official patterns"""
        try:
            state = await self.load_ag2_state(chat_id, enterprise_id)
            if not state:
                return False, "No resumable state found"
            
            messages = state.get("messages", [])
            if not messages:
                return False, "No messages in state"
            
            # Restore messages using AG2's official method
            groupchat.messages = messages.copy()
            
            logger.info(f"✅ AG2 groupchat resumed: {len(messages)} messages")
            return True, None
            
        except Exception as e:
            return False, f"Resume failed: {str(e)}"

# ==================================================================================
# MAIN TRANSPORT CLASS
# ==================================================================================

class SimpleTransport:
    """
    Complete transport system with AG2 resume functionality.
    
    Features:
    - Message filtering (removes AutoGen noise)
    - AG2 groupchat persistence and resume
    - Transport-agnostic communication
    - Connection state tracking
    """
    
    def __init__(self, default_llm_config: Optional[Dict[str, Any]] = None):
        # LLM config is optional - transport doesn't need it for routing
        self.default_llm_config = default_llm_config or {}
        self.active_connections = {}
        self.connections: Dict[str, Dict[str, Any]] = {}
        self.message_filter = MessageFilter()
        self.persistence = PersistenceManager()
        
        # Store SSE event queues for broadcasting
        self.sse_queues: Dict[str, asyncio.Queue] = {}
        
        # User input collection mechanism
        self.pending_input_requests: Dict[str, asyncio.Future] = {}
        
        # Set this instance as the singleton for user input collection
        self._set_as_instance()
        
    def format_agent_name_for_ui(self, agent_name: str) -> str:
        """Format agent names for better UI display"""
        if not agent_name:
            return "Assistant"
        
        # Convert CamelCase to Title Case
        import re
        formatted = re.sub(r'([A-Z])', r' \1', agent_name).strip()
        formatted = formatted.replace("Agent", "").strip()
        return formatted or "Assistant"
        
    # ==================================================================================
    # USER INPUT COLLECTION (Production-Ready)
    # ==================================================================================
    
    @classmethod
    async def wait_for_user_input(cls, input_request_id: str, timeout: int = 300) -> str:
        """
        Wait for user input response for a specific input request.
        
        This is called by AG2StreamingIOStream when agents request user input.
        The frontend will call submit_user_input() to provide the response.
        """
        # Access the singleton instance
        instance = cls._get_instance()
        if not instance:
            raise RuntimeError("SimpleTransport instance not available")
            
        if input_request_id not in instance.pending_input_requests:
            # Create a future to wait for the input
            instance.pending_input_requests[input_request_id] = asyncio.Future()
        
        try:
            # Wait for the user input with timeout
            user_input = await asyncio.wait_for(
                instance.pending_input_requests[input_request_id],
                timeout=timeout
            )
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
        """Get the singleton instance of SimpleTransport"""
        # This is a simple approach - in production you might use a proper singleton pattern
        # For now, we'll store the instance as a class variable
        return getattr(cls, '_instance', None)
    
    def _set_as_instance(self):
        """Set this instance as the singleton"""
        SimpleTransport._instance = self
        
    def should_show_to_user(self, message: str, agent_name: Optional[str]) -> bool:
        """Check if a message should be shown to the user interface"""
        # For now, show all messages - can be enhanced with filtering logic
        return True
        
    def format_agent_name(self, agent_name: Optional[str]) -> str:
        """Format agent name for display"""
        if agent_name is None:
            return "System"
        return self.format_agent_name_for_ui(agent_name)
    
    # ==================================================================================
    # CONTEXT MANAGEMENT
    # ==================================================================================
    
    def set_enterprise_context(self, enterprise_id: str) -> None:
        """Set the current enterprise context for this transport instance"""
        self.current_enterprise_id = enterprise_id
        logger.debug(f"🏢 Enterprise context set to: {enterprise_id}")
    
    def get_enterprise_context(self) -> str:
        """Get the current enterprise context, defaulting to 'default' for backwards compatibility"""
        return getattr(self, 'current_enterprise_id', 'default')
    
    # ==================================================================================
    # CORE MESSAGE SENDING
    # ==================================================================================
    
    async def send_to_ui(
        self,
        message: Union[str, Dict[str, Any], Any],
        agent_name: Optional[str] = None,
        message_type: str = "chat_message",
        chat_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Send messages to UI via SSE broadcast.
        """
        
        # For simple strings, apply traditional filtering
        if isinstance(message, str):
            if not self.should_show_to_user(message, agent_name):
                logger.debug(f"🚫 Filtered message from {agent_name}: {message[:50]}...")
                return
        
        # Format agent name
        formatted_agent = self.format_agent_name(agent_name)
        
        # Log agent message to agent_chat.log for tracking
        if isinstance(message, str) and formatted_agent and formatted_agent != "Assistant":
            chat_logger.info(f"AGENT_MESSAGE | Chat: {chat_id or 'unknown'} | Agent: {formatted_agent} | Message: {str(message)[:200]}{'...' if len(str(message)) > 200 else ''}")
        elif isinstance(message, str):
            chat_logger.info(f"SYSTEM_MESSAGE | Chat: {chat_id or 'unknown'} | Type: {message_type} | Message: {str(message)[:200]}{'...' if len(str(message)) > 200 else ''}")
        
        # Create event data
        event_data = {
            "type": "chat_message",
            "data": {
                "message": str(message),
                "agent_name": formatted_agent,
                "chat_id": chat_id,
                "metadata": metadata or {},
                "message_type": message_type
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Broadcast to all SSE connections or specific chat
        await self._broadcast_to_sse(event_data, chat_id)
        
        logger.info(f"📤 {formatted_agent}: {str(message)[:100]}...")
        
    async def _broadcast_to_sse(self, event_data: Dict[str, Any], target_chat_id: Optional[str] = None) -> None:
        """Broadcast event to SSE connections and WebSocket connections"""
        try:
            if target_chat_id:
                # Send to specific chat's SSE queue
                if target_chat_id in self.sse_queues:
                    await self.sse_queues[target_chat_id].put(event_data)
                    logger.debug(f"📡 Broadcasted to SSE queue for chat {target_chat_id}")
                
                # Also send to WebSocket if connected
                if target_chat_id in self.connections:
                    connection_data = self.connections[target_chat_id]
                    if "websocket" in connection_data and connection_data.get("active", False):
                        try:
                            websocket = connection_data["websocket"]
                            await websocket.send_text(f"data: {json.dumps(event_data)}")
                            logger.debug(f"📡 Broadcasted to WebSocket for chat {target_chat_id}")
                        except Exception as ws_error:
                            logger.warning(f"⚠️ Failed to send to WebSocket {target_chat_id}: {ws_error}")
                            # Mark WebSocket as inactive if send fails
                            connection_data["active"] = False
                            if "websocket" in connection_data:
                                del connection_data["websocket"]
                
            else:
                # Broadcast to all SSE connections
                for chat_id, queue in self.sse_queues.items():
                    await queue.put(event_data)
                
                # Broadcast to all WebSocket connections
                for chat_id, connection_data in self.connections.items():
                    if "websocket" in connection_data and connection_data.get("active", False):
                        try:
                            websocket = connection_data["websocket"]
                            await websocket.send_text(f"data: {json.dumps(event_data)}")
                        except Exception as ws_error:
                            logger.warning(f"⚠️ Failed to send to WebSocket {chat_id}: {ws_error}")
                            # Mark WebSocket as inactive if send fails
                            connection_data["active"] = False
                            if "websocket" in connection_data:
                                del connection_data["websocket"]
                
                logger.debug(f"📡 Broadcasted to {len(self.sse_queues)} SSE connections and WebSocket connections")
                
        except Exception as e:
            logger.error(f"❌ Failed to broadcast event: {e}")
        
    async def send_error(
        self,
        error_message: str,
        error_code: str = "GENERAL_ERROR",
        chat_id: Optional[str] = None
    ) -> None:
        """Send error message to UI via SSE"""
        event_data = {
            "type": "error",
            "data": {
                "message": error_message,
                "error_code": error_code,
                "chat_id": chat_id
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
        await self._broadcast_to_sse(event_data, chat_id)
        logger.error(f"❌ Error: {error_message}")
        
    async def send_status(
        self,
        status_message: str,
        status_type: str = "info",
        chat_id: Optional[str] = None
    ) -> None:
        """Send status update to UI via SSE"""
        event_data = {
            "type": "status",
            "data": {
                "message": status_message,
                "status_type": status_type,
                "chat_id": chat_id
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
        await self._broadcast_to_sse(event_data, chat_id)
        logger.info(f"ℹ️ Status: {status_message}")
    
    # ==================================================================================
    # AG2 GROUPCHAT RESUME FUNCTIONALITY
    # ==================================================================================
    
    async def save_groupchat_session(
        self,
        chat_id: str,
        enterprise_id: str,
        groupchat: GroupChat,
        manager: GroupChatManager,
    ) -> bool:
        """Save AG2 groupchat session for resume capability"""
        return await self.persistence.save_ag2_state(
            chat_id=chat_id,
            enterprise_id=enterprise_id,
            groupchat=groupchat,
            manager=manager
        )
    
    async def resume_groupchat_session(
        self,
        chat_id: str,
        enterprise_id: str,
        groupchat: GroupChat,
        manager: GroupChatManager
    ) -> Tuple[bool, Optional[str]]:
        """Resume AG2 groupchat session with proper state restoration"""
        success, error = await self.persistence.resume_ag2_groupchat(
            chat_id=chat_id,
            enterprise_id=enterprise_id,
            groupchat=groupchat,
            manager=manager
        )
        
        if success:
            # Send restoration events to frontend
            await self.send_status(
                f"Resumed session with {len(groupchat.messages)} messages",
                "resume_success",
                chat_id
            )
            
            # Send message history for UI restoration
            await self.send_event(
                "messages_restored",
                {
                    "messages": groupchat.messages,
                    "count": len(groupchat.messages)
                }
            )
        
        return success, error
    
    async def get_resume_info(
        self,
        chat_id: str,
        enterprise_id: str
    ) -> Dict[str, Any]:
        """Get information about whether a chat can be resumed"""
        try:
            state = await self.persistence.load_ag2_state(chat_id, enterprise_id)
            
            if not state:
                return {
                    "can_resume": False,
                    "reason": "no_existing_session",
                    "is_new_chat": True
                }
            
            message_count = state.get("message_count", 0)
            
            return {
                "can_resume": message_count > 0,
                "message_count": message_count,
                "is_new_chat": message_count == 0,
                "reason": "messages_found" if message_count > 0 else "no_messages"
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to get resume info: {e}")
            return {
                "can_resume": False,
                "reason": f"error: {str(e)}",
                "is_new_chat": True
            }
    
    # ==================================================================================
    # SESSION MANAGEMENT
    # ==================================================================================
    
    async def create_session(
        self,
        chat_id: str,
        enterprise_id: str,
        check_resume: bool = True
    ) -> Dict[str, Any]:
        """Create or resume a session"""
        try:
            # Check if we can resume existing session
            if check_resume:
                resume_info = await self.get_resume_info(chat_id, enterprise_id)
                
                if resume_info.get("can_resume", False):
                    logger.info(f"📥 Resumable session found for {chat_id}: {resume_info['message_count']} messages")
                    
                    session_info = {
                        "chat_id": chat_id,
                        "enterprise_id": enterprise_id,
                        "session_type": "resumed",
                        "resume_info": resume_info,
                        "created_at": datetime.utcnow().isoformat()
                    }
                else:
                    logger.info(f"🆕 Starting new session for {chat_id}: {resume_info.get('reason', 'no existing state')}")
                    
                    session_info = {
                        "chat_id": chat_id,
                        "enterprise_id": enterprise_id,
                        "session_type": "new",
                        "resume_info": resume_info,
                        "created_at": datetime.utcnow().isoformat()
                    }
            else:
                session_info = {
                    "chat_id": chat_id,
                    "enterprise_id": enterprise_id,
                    "session_type": "new_forced",
                    "created_at": datetime.utcnow().isoformat()
                }
            
            # Store session locally
            self.connections[chat_id] = {
                "enterprise_id": enterprise_id,
                "session_info": session_info,
                "created_at": datetime.utcnow(),
                "active": True
            }
            
            await self.send_status(
                "Session initialized",
                "session_created",
                chat_id
            )
            
            logger.info(f"✅ Session created: {chat_id} ({session_info['session_type']})")
            return session_info
            
        except Exception as e:
            logger.error(f"❌ Failed to create session: {e}")
            raise
    
    # ==================================================================================
    # CONNECTION MANAGEMENT METHODS
    # ==================================================================================
    
    def disconnect(self) -> None:
        """Disconnect and cleanup all active connections"""
        try:
            # Close all active connections
            for connection_id, connection_data in self.connections.items():
                if connection_data.get("active", False):
                    connection_data["active"] = False
                    
                    # Close WebSocket if present
                    if "websocket" in connection_data:
                        try:
                            websocket = connection_data["websocket"]
                            # Note: WebSocket.close() is synchronous in FastAPI
                            # The actual cleanup happens in the WebSocket handler's finally block
                            logger.debug(f"🔌 Marked WebSocket for cleanup: {connection_id}")
                        except Exception as e:
                            logger.warning(f"⚠️ Error during WebSocket cleanup for {connection_id}: {e}")
                        finally:
                            del connection_data["websocket"]
                    
                    logger.info(f"🔌 Disconnected connection: {connection_id}")
            
            # Clear all SSE queues
            self.sse_queues.clear()
            logger.debug("🧹 Cleared all SSE event queues")
            
            # Clear active connections
            self.active_connections.clear()
            self.connections.clear()
            
            logger.info("✅ All transport connections disconnected")
            
        except Exception as e:
            logger.error(f"❌ Error during disconnect: {e}")
    
    def get_connection_info(self) -> Dict[str, int]:
        """Get information about active connections"""
        try:
            sse_count = 0
            websocket_count = 0
            
            # Count active connections by type
            for connection_data in self.connections.values():
                if connection_data.get("active", False):
                    if "websocket" in connection_data:
                        websocket_count += 1
                    else:
                        # SSE connections don't store websocket object
                        sse_count += 1
            
            # Also count SSE queues as active SSE connections
            sse_queue_count = len(self.sse_queues)
            if sse_queue_count > sse_count:
                sse_count = sse_queue_count
            
            total_count = sse_count + websocket_count
            
            return {
                "sse_connections": sse_count,
                "websocket_connections": websocket_count,
                "total_connections": total_count
            }
        except Exception as e:
            logger.error(f"❌ Error getting connection info: {e}")
            return {"sse_connections": 0, "websocket_connections": 0, "total_connections": 0}
    
    async def create_sse_stream(
        self,
        chat_id: str,
        user_id: str,
        workflow_type: str,
        enterprise_id: Optional[str] = None
    ) -> StreamingResponse:
        """Create Server-Sent Events stream for real-time communication"""
        try:
            logger.info(f"🔌 Creating SSE stream for chat_id: {chat_id}, workflow: {workflow_type}")
            
            # Set enterprise context if provided
            if enterprise_id:
                self.set_enterprise_context(enterprise_id)
            
            # Create session if it doesn't exist
            if chat_id not in self.connections:
                # Use provided enterprise_id or get from context
                effective_enterprise_id = enterprise_id or self.get_enterprise_context()
                await self.create_session(chat_id, effective_enterprise_id, check_resume=True)
                
                # Auto-start workflow if it's configured for auto-start
                # Let the workflow handle its own initialization (no fake user message)
                logger.info(f"🚀 Auto-starting workflow '{workflow_type}' for new session {chat_id}")
                welcome_result = await self.handle_user_input_from_api(
                    chat_id=chat_id,
                    user_id=user_id,
                    workflow_type=workflow_type,
                    message=None  # Let workflow handle initialization with null initial_message
                )
                logger.info(f"✅ Auto-start completed for {chat_id}: {welcome_result.get('status', 'unknown')}")
            
            async def event_generator():
                """Generate SSE events following the documented event types"""
                try:
                    # Create event queue for this connection
                    event_queue = asyncio.Queue()
                    self.sse_queues[chat_id] = event_queue
                    
                    # Send initial connection event
                    connection_event = {
                        "type": "status",
                        "data": {
                            "status": "connected",
                            "chat_id": chat_id,
                            "workflow_type": workflow_type
                        },
                        "timestamp": datetime.utcnow().isoformat()
                    }
                    yield f"data: {json.dumps(connection_event)}\n\n"
                    
                    # Listen for events from the queue and send heartbeats
                    last_heartbeat = time.time()
                    while chat_id in self.connections and self.connections[chat_id].get("active", False):
                        try:
                            # Check for new events (non-blocking)
                            event = await asyncio.wait_for(event_queue.get(), timeout=1.0)
                            yield f"data: {json.dumps(event)}\n\n"
                            last_heartbeat = time.time()
                        except asyncio.TimeoutError:
                            # Send heartbeat every 30 seconds
                            if time.time() - last_heartbeat > 30:
                                heartbeat_event = {
                                    "type": "status",
                                    "data": {
                                        "status": "heartbeat",
                                        "timestamp": datetime.utcnow().isoformat()
                                    },
                                    "timestamp": datetime.utcnow().isoformat()
                                }
                                yield f"data: {json.dumps(heartbeat_event)}\n\n"
                                last_heartbeat = time.time()
                        
                except asyncio.CancelledError:
                    logger.info(f"🔌 SSE stream cancelled for {chat_id}")
                except Exception as e:
                    logger.error(f"❌ SSE stream error for {chat_id}: {e}")
                    # Send error event before closing
                    error_event = {
                        "type": "error",
                        "data": {
                            "error": str(e),
                            "error_code": "SSE_STREAM_ERROR"
                        },
                        "timestamp": datetime.utcnow().isoformat()
                    }
                    yield f"data: {json.dumps(error_event)}\n\n"
                finally:
                    # Cleanup connection and queue
                    if chat_id in self.connections:
                        self.connections[chat_id]["active"] = False
                    if chat_id in self.sse_queues:
                        del self.sse_queues[chat_id]
                    logger.info(f"🔌 SSE stream ended for {chat_id}")
            
            return StreamingResponse(
                event_generator(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Headers": "Cache-Control"
                }
            )
            
        except Exception as e:
            logger.error(f"❌ Failed to create SSE stream: {e}")
            raise
    
    async def handle_websocket(
        self,
        websocket: WebSocket,
        chat_id: str,
        user_id: str,
        workflow_type: str,
        enterprise_id: Optional[str] = None
    ) -> None:
        """Handle WebSocket connection for real-time communication"""
        try:
            # Accept the WebSocket connection
            await websocket.accept()
            logger.info(f"🔌 WebSocket connected for chat_id: {chat_id}, workflow: {workflow_type}")
            
            # Set enterprise context if provided
            if enterprise_id:
                self.set_enterprise_context(enterprise_id)
            
            # Create session if it doesn't exist
            if chat_id not in self.connections:
                effective_enterprise_id = self.get_enterprise_context()
                await self.create_session(chat_id, effective_enterprise_id, check_resume=True)
            
            # Mark connection as active and store WebSocket
            self.connections[chat_id]["websocket"] = websocket
            self.connections[chat_id]["active"] = True
            
            # Create an event queue for this WebSocket connection to support unified broadcasting
            if chat_id not in self.sse_queues:
                self.sse_queues[chat_id] = asyncio.Queue()
            
            # Send initial connection event
            await websocket.send_text(json.dumps({
                "type": "status",
                "data": {
                    "status": "connected",
                    "chat_id": chat_id,
                    "workflow_type": workflow_type,
                    "connection_type": "websocket"
                },
                "timestamp": datetime.utcnow().isoformat()
            }))
            
            try:
                while True:
                    # Receive message from WebSocket
                    data = await websocket.receive_text()
                    message_data = json.loads(data)
                    
                    if message_data.get("type") == "user_message":
                        user_input = message_data.get("message", "")
                        if user_input.strip():
                            # Send user message to UI following your event system
                            await self.send_event("chat_message", {
                                "message": user_input,
                                "agent_name": "User",
                                "chat_id": chat_id
                            })
                            
                            # Process message through workflow system
                            from core.workflow.init_registry import get_workflow_handler
                            
                            # Determine workflow type from message or use default
                            workflow_type = message_data.get("workflow_type", "chat")
                            
                            # Process through workflow handler
                            workflow_handler = get_workflow_handler(workflow_type)
                            if workflow_handler:
                                try:
                                    result = await self.handle_user_input_from_api(
                                        chat_id=chat_id,
                                        user_id=user_id,
                                        workflow_type=workflow_type,
                                        message=user_input
                                    )
                                    
                                    await websocket.send_text(json.dumps({
                                        "type": "workflow_result",
                                        "result": result,
                                        "timestamp": datetime.utcnow().isoformat()
                                    }))
                                except Exception as e:
                                    logger.error(f"❌ Workflow processing failed: {e}")
                                    await websocket.send_text(json.dumps({
                                        "type": "error",
                                        "error": str(e),
                                        "timestamp": datetime.utcnow().isoformat()
                                    }))
                            else:
                                # Fallback: send acknowledgment
                                await websocket.send_text(json.dumps({
                                    "type": "message_received",
                                    "status": "processed",
                                    "timestamp": datetime.utcnow().isoformat()
                                }))
                    
                    elif message_data.get("type") == "component_action":
                        # Handle component action for AG2 ContextVariables
                        component_id = message_data.get("component_id")  # Changed from agent_name.component_name
                        action_type = message_data.get("action_type")    # Changed from component_name
                        action_data = message_data.get("action_data", {})
                        
                        logger.info(f"📋 Received component action: {component_id} -> {action_type}")
                        
                        try:
                            # Get the active workflow's context update tool
                            from workflows.Generator.ContextVariables import update_context_from_ui
                            
                            # Get current context variables from active session
                            context_variables = None
                            if chat_id in self.connections and "context" in self.connections[chat_id]:
                                context_variables = self.connections[chat_id]["context"]
                            
                            # Call AG2 tool directly
                            if context_variables:
                                result = update_context_from_ui(
                                    component_id=component_id,
                                    action_type=action_type,
                                    action_data=action_data,
                                    context_variables=context_variables
                                )
                                
                                logger.info(f"✅ Context updated via AG2 tool: {result}")
                                
                                # Send acknowledgment back to frontend
                                await websocket.send_text(json.dumps({
                                    "type": "component_action_response",
                                    "status": "success",
                                    "result": result,
                                    "timestamp": datetime.utcnow().isoformat()
                                }))
                            else:
                                logger.warning(f"⚠️ No context variables found for chat {chat_id}")
                                await websocket.send_text(json.dumps({
                                    "type": "component_action_response", 
                                    "status": "warning",
                                    "message": "No context variables available",
                                    "timestamp": datetime.utcnow().isoformat()
                                }))
                                
                        except Exception as action_error:
                            logger.error(f"❌ Component action failed: {action_error}")
                            await websocket.send_text(json.dumps({
                                "type": "component_action_response",
                                "status": "error", 
                                "error": str(action_error),
                                "timestamp": datetime.utcnow().isoformat()
                            }))
                    
                    elif message_data.get("type") == "ping":
                        # Respond to ping with pong
                        await websocket.send_text(json.dumps({
                            "type": "pong",
                            "timestamp": datetime.utcnow().isoformat()
                        }))
                    
            except Exception as e:
                logger.error(f"❌ WebSocket error for {chat_id}: {e}")
            
        except Exception as e:
            logger.error(f"❌ Failed to handle WebSocket: {e}")
        finally:
            # Cleanup connection and queues
            if chat_id in self.connections:
                self.connections[chat_id]["active"] = False
                if "websocket" in self.connections[chat_id]:
                    del self.connections[chat_id]["websocket"]
            
            # Clean up SSE queue if no other connections are using it
            if chat_id in self.sse_queues:
                # Only remove the queue if there's no active SSE connection
                connection_data = self.connections.get(chat_id, {})
                if not connection_data.get("active", False):
                    del self.sse_queues[chat_id]
                    logger.debug(f"🧹 Cleaned up SSE queue for {chat_id}")
            
            logger.info(f"🔌 WebSocket disconnected for {chat_id}")

    # ==================================================================================
    # WORKFLOW INTEGRATION METHODS
    # ==================================================================================
    
    async def handle_user_input_from_api(
        self, 
        chat_id: str, 
        user_id: Optional[str], 
        workflow_type: str, 
        message: Optional[str]
    ) -> Dict[str, Any]:
        """
        Handle user input from the POST API endpoint
        Integrates with workflow registry and follows the documented event system
        
        Args:
            message: User message or None for auto-start without user input
        """
        try:
            # Only send user message event if there's an actual message
            if message is not None:
                await self.send_event("chat_message", {
                    "message": message,
                    "agent_name": "User", 
                    "chat_id": chat_id
                })
            else:
                # For auto-start without user input, just log
                logger.info(f"🚀 Starting workflow '{workflow_type}' for {chat_id} without initial user message")
            
            # Create session if it doesn't exist, with resume capability
            if chat_id not in self.connections:
                # Extract enterprise_id from context or use default for backwards compatibility
                enterprise_id = getattr(self, 'current_enterprise_id', 'default')
                
                session_info = await self.create_session(
                    chat_id=chat_id, 
                    enterprise_id=enterprise_id,
                    check_resume=True
                )
                logger.info(f"🆕 Created session for API input: {session_info['session_type']}")
            
            # Create communication channel wrapper following the documented pattern
            communication_channel = SimpleCommunicationChannelWrapper(self, chat_id)
            
            # Integrate with actual workflow system
            if message:
                logger.info(f"🚀 Starting workflow '{workflow_type}' for message: {message[:50]}...")
            else:
                logger.info(f"🚀 Starting workflow '{workflow_type}' with auto-start (no initial message)")
            
            # Send status update
            await self.send_event("status", {
                "status": "processing",
                "workflow_type": workflow_type,
                "chat_id": chat_id
            })
            
            # Get the actual workflow handler and execute it
            from core.workflow.init_registry import get_workflow_handler
            
            workflow_handler = get_workflow_handler(workflow_type)
            if not workflow_handler:
                error_msg = f"Workflow '{workflow_type}' not found in registry"
                logger.error(f"❌ {error_msg}")
                await self.send_event("error", {
                    "error": error_msg,
                    "error_code": "WORKFLOW_NOT_FOUND",
                    "chat_id": chat_id
                })
                return {
                    "status": "error",
                    "message": error_msg,
                    "workflow_type": workflow_type
                }
            
            # Execute the workflow with proper parameters
            try:
                # Extract enterprise_id from context or use default for backwards compatibility
                enterprise_id = getattr(self, 'current_enterprise_id', 'default')
                
                # Log workflow start to agent_chat.log
                chat_logger.info(f"WORKFLOW_START | Chat: {chat_id} | Workflow: {workflow_type} | User: {user_id or 'unknown'} | HasMessage: {message is not None}")
                
                result = await workflow_handler(
                    enterprise_id=enterprise_id,
                    chat_id=chat_id,
                    user_id=user_id or "unknown",
                    initial_message=message,
                    communication_channel=communication_channel
                )
                
                logger.info(f"✅ Workflow '{workflow_type}' completed successfully")
                
                # Log workflow completion to agent_chat.log
                chat_logger.info(f"WORKFLOW_COMPLETE | Chat: {chat_id} | Workflow: {workflow_type} | Result: {str(result)[:100] if result else 'None'}")
                
                # Send completion status
                await self.send_event("status", {
                    "status": "completed",
                    "workflow_type": workflow_type,
                    "chat_id": chat_id
                })
                
                return {
                    "status": "processed",
                    "workflow_type": workflow_type,
                    "message_id": f"{chat_id}_{int(time.time())}",
                    "result": result if result else "completed"
                }
                
            except Exception as workflow_error:
                error_msg = f"Workflow execution failed: {str(workflow_error)}"
                logger.error(f"❌ {error_msg}", exc_info=True)
                
                # Log workflow error to agent_chat.log
                chat_logger.error(f"WORKFLOW_ERROR | Chat: {chat_id} | Workflow: {workflow_type} | Error: {str(workflow_error)[:200]}")
                
                await self.send_event("error", {
                    "error": error_msg,
                    "error_code": "WORKFLOW_EXECUTION_ERROR",
                    "chat_id": chat_id
                })
                
                return {
                    "status": "error",
                    "message": error_msg,
                    "workflow_type": workflow_type
                }
            
        except Exception as e:
            error_msg = f"Failed to process API message: {str(e)}"
            logger.error(f"❌ API workflow execution failed: {e}", exc_info=True)
            
            # Send error event following the documented event system
            await self.send_event("error", {
                "error": error_msg,
                "error_code": "API_PROCESSING_ERROR",
                "chat_id": chat_id
            })
            
            return {
                "status": "error", 
                "message": error_msg,
                "workflow_type": workflow_type
            }

    # ==================================================================================
    # PROTOCOL COMPATIBILITY METHODS
    # ==================================================================================
    
    async def send_event(self, event_type: str, data: Any, agent_name: Optional[str] = None) -> None:
        """Send event (for protocol compatibility)"""
        if event_type == "chat_message":
            message = data.get("message", str(data)) if isinstance(data, dict) else str(data)
            chat_id = data.get("chat_id") if isinstance(data, dict) else None
            
            # Log chat messages to agent_chat.log
            formatted_agent = self.format_agent_name(agent_name)
            if message and formatted_agent:
                chat_logger.info(f"EVENT_MESSAGE | Chat: {chat_id or 'unknown'} | Agent: {formatted_agent} | Message: {str(message)[:200]}{'...' if len(str(message)) > 200 else ''}")
            
            await self.send_to_ui(message, agent_name, "chat_message", chat_id)
        elif event_type == "error":
            error_msg = data.get("error", str(data)) if isinstance(data, dict) else str(data)
            await self.send_error(error_msg)
        elif event_type == "status":
            status_msg = data.get("status", str(data)) if isinstance(data, dict) else str(data)
            await self.send_status(status_msg)
        elif event_type == "route_to_chat":
            # Support for inline UI components
            await self.send_ui_event("route_to_chat", data)
        elif event_type == "route_to_artifact":
            # Support for artifact UI components  
            await self.send_ui_event("route_to_artifact", data)
        elif event_type == "ui_tool_action":
            # Support for UI tool interactions
            await self.send_ui_event("ui_tool_action", data)
        else:
            logger.info(f"📤 Event: {event_type} - {data}")
    
    async def send_custom_event(self, event_name: str, data: Any, chat_id: Optional[str] = None) -> None:
        """Send custom event"""
        logger.info(f"📤 Custom Event: {event_name} - {data}")

    async def send_ui_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """
        Send UI events for dynamic component routing - PRODUCTION READY.
        Supports route_to_chat, route_to_artifact, ui_tool_action
        """
        logger.info(f"🎯 UI Event: {event_type} - Component: {data.get('component_name', 'unknown')}")
        
        # Production implementation: Create proper event and send to UI
        event_data = {
            "type": event_type,
            "data": data,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Broadcast to SSE connections
        chat_id = data.get('chat_id')
        await self._broadcast_to_sse(event_data, chat_id)
        
        # Send to UI immediately - this is production behavior
        if event_type == "route_to_chat":
            logger.info(f"📱 Routing to inline component: {data.get('component_name')}")
        elif event_type == "route_to_artifact":
            logger.info(f"🗂️ Creating artifact component: {data.get('component_name')} - {data.get('title', 'No title')}")
        elif event_type == "ui_tool_action":
            logger.info(f"🔧 UI Tool Action: {data.get('tool_id')} - {data.get('action_type')}")
        
        # This is where the actual transport would send the event to frontend
        # The event_data is properly formatted for frontend consumption


