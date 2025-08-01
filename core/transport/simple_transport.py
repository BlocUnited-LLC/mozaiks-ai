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

# Import workflow configuration for agent visibility filtering
from core.workflow.workflow_config import workflow_config

# Import core configuration for token management
from core.core_config import get_free_trial_config

# Logging setup
logger = logging.getLogger(__name__)

# Import chat logger for agent message tracking
from logs.logging_config import get_chat_logger

# Get our chat logger (logging setup happens in main app)
chat_logger = get_chat_logger("agent_messages")  # Specific logger for agent messages

# ==================================================================================
# COMMUNICATION CHANNEL WRAPPER
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
        
        # User input collection mechanism
        self.pending_input_requests: Dict[str, asyncio.Future] = {}
        
        # AG2 streaming setup - if streaming is enabled in config
        self.ag2_streaming_manager = None
        if self.default_llm_config.get("stream"):
            self._setup_ag2_streaming()
        
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
        """Get the singleton instance of SimpleTransport"""
        # This is a simple approach - in production you might use a proper singleton pattern
        # For now, we'll store the instance as a class variable
        return getattr(cls, '_instance', None)
    
    def _set_as_instance(self):
        """Set this instance as the singleton"""
        SimpleTransport._instance = self
        
    def _setup_ag2_streaming(self):
        """Set up AG2 streaming infrastructure for all active chat sessions"""
        logger.info("Setting up AG2 streaming infrastructure...")
        
        try:
            from core.transport.ag2_iostream import AG2StreamingManager
            
            # Set up streaming for all active connections
            for chat_id, connection in self.connections.items():
                enterprise_id = connection.get('enterprise_id', 'default')
                user_id = connection.get('user_id', 'unknown')
                workflow_name = connection.get('workflow_name', 'default')
                
                logger.info(f"Setting up AG2 streaming for chat {chat_id}")
                
                # Create streaming manager for this chat session
                streaming_manager = AG2StreamingManager(
                    chat_id=chat_id,
                    enterprise_id=enterprise_id,
                    user_id=user_id,
                    workflow_name=workflow_name
                )
                
                # Set up streaming with the transport instance
                streaming_manager.setup_streaming(transport=self)
                
                # Store the streaming manager for this connection
                connection['ag2_streaming_manager'] = streaming_manager
            
            logger.info("AG2 streaming infrastructure initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to set up AG2 streaming: {e}")
            
    async def _setup_ag2_streaming_for_connection(self, chat_id: str, enterprise_id: str):
        """Set up AG2 streaming infrastructure for a single connection"""
        try:
            from core.transport.ag2_iostream import AG2StreamingManager
            
            connection = self.connections.get(chat_id)
            if not connection:
                logger.warning(f"No connection found for chat_id {chat_id}")
                return
                
            user_id = connection.get('user_id', 'unknown')
            workflow_name = connection.get('workflow_name', 'default')
            
            logger.info(f"Setting up AG2 streaming for new connection {chat_id}")
            
            # Create streaming manager for this chat session
            streaming_manager = AG2StreamingManager(
                chat_id=chat_id,
                enterprise_id=enterprise_id,
                user_id=user_id,
                workflow_name=workflow_name
            )
            
            # Set up streaming with the transport instance
            streaming_manager.setup_streaming(transport=self)
            
            # Store the streaming manager for this connection
            connection['ag2_streaming_manager'] = streaming_manager
            
            logger.info(f"AG2 streaming set up successfully for {chat_id}")
            
        except Exception as e:
            logger.error(f"Failed to set up AG2 streaming for {chat_id}: {e}")
            
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
            visible_agents = workflow_config.get_visible_agents(workflow_name)
            is_visible = agent_name in visible_agents
            
            if not is_visible:
                logger.debug(f"🚫 Agent '{agent_name}' not in visual_agents for workflow '{workflow_name}' - filtering from UI")
                return False
            else:
                logger.debug(f"✅ Agent '{agent_name}' is in visual_agents for workflow '{workflow_name}' - showing in UI")
        
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
        """Get the current enterprise context"""
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
        Send messages to UI via WebSocket broadcast.
        """
        
        # Extract clean content from AG2 UUID-formatted messages
        clean_message = self._extract_clean_content(message)
        
        # For simple strings, apply traditional filtering
        if isinstance(clean_message, str):
            if not self.should_show_to_user(agent_name, chat_id):
                logger.debug(f"🚫 Filtered message from {agent_name}: {clean_message[:50]}...")
                return
        
        # Format agent name
        formatted_agent = self.format_agent_name(agent_name)
        
        # Log agent message to agent_chat.log for tracking
        if isinstance(clean_message, str) and formatted_agent and formatted_agent != "Assistant":
            chat_logger.info(f"AGENT_MESSAGE | Chat: {chat_id or 'unknown'} | Agent: {formatted_agent} | Message: {str(clean_message)[:200]}{'...' if len(str(clean_message)) > 200 else ''}")
        elif isinstance(clean_message, str):
            chat_logger.info(f"SYSTEM_MESSAGE | Chat: {chat_id or 'unknown'} | Type: {message_type} | Message: {str(clean_message)[:200]}{'...' if len(str(clean_message)) > 200 else ''}")
        
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
        
    def _extract_clean_content(self, message: Union[str, Dict[str, Any], Any]) -> str:
        """Extract clean content from AG2 UUID-formatted messages or other formats."""
        
        # Handle string messages (most common case)
        if isinstance(message, str):
            # Check if it's a UUID-formatted AG2 message
            if 'uuid=UUID(' in message and 'content=' in message:
                # Extract content using regex
                import re
                # Try both single and double quotes
                content_match = re.search(r"content='([^']*)'|content=\"([^\"]*)\"", message)
                if content_match:
                    extracted_content = content_match.group(1) or content_match.group(2)
                    # Unescape common escape sequences
                    extracted_content = extracted_content.replace('\\n', '\n').replace('\\t', '\t').replace('\\\\', '\\')
                    return extracted_content
                else:
                    # Fallback: return the original message if parsing fails
                    return message
            else:
                # Regular string message
                return message
        
        # Handle dict messages
        elif isinstance(message, dict):
            # Try common content keys
            for key in ['content', 'message', 'text', 'body']:
                if key in message:
                    return str(message[key])
            # Fallback to string representation
            return str(message)
        
        # Handle other object types
        else:
            # Check if object has content attribute
            if hasattr(message, 'content'):
                return str(message.content)
            # Fallback to string representation
            return str(message)
        
    async def _broadcast_to_websockets(self, event_data: Dict[str, Any], target_chat_id: Optional[str] = None) -> None:
        """Broadcast event to WebSocket connections only"""
        try:
            if target_chat_id:
                # Send to specific chat's WebSocket
                if target_chat_id in self.connections:
                    connection_data = self.connections[target_chat_id]
                    if "websocket" in connection_data and connection_data.get("active", False):
                        try:
                            websocket = connection_data["websocket"]
                            # Send raw JSON for WebSocket clients to parse directly
                            await websocket.send_text(json.dumps(event_data))
                            logger.debug(f"📡 Broadcasted to WebSocket for chat {target_chat_id}")
                        except Exception as ws_error:
                            logger.warning(f"⚠️ Failed to send to WebSocket {target_chat_id}: {ws_error}")
                            # Mark WebSocket as inactive if send fails
                            connection_data["active"] = False
                            connection_data.pop("websocket", None)
                
            else:
                # Broadcast to all WebSocket connections
                websocket_count = 0
                for chat_id, connection_data in self.connections.items():
                    if "websocket" in connection_data and connection_data.get("active", False):
                        try:
                            websocket = connection_data["websocket"]
                            # Send raw JSON for WebSocket clients to parse directly
                            await websocket.send_text(json.dumps(event_data))
                            websocket_count += 1
                        except Exception as ws_error:
                            logger.warning(f"⚠️ Failed to send to WebSocket {chat_id}: {ws_error}")
                            # Mark WebSocket as inactive if send fails
                            connection_data["active"] = False
                            if "websocket" in connection_data:
                                del connection_data["websocket"]
                
                logger.debug(f"📡 Broadcasted to {websocket_count} WebSocket connections")
                
        except Exception as e:
            logger.error(f"❌ Failed to broadcast event: {e}")
        
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
            
            # Send message history for UI restoration using tool event
            await self.send_tool_event(
                "messages_restored",
                {
                    "messages": groupchat.messages,
                    "count": len(groupchat.messages)
                },
                "inline",
                chat_id
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
            
            # Set up AG2 streaming for this new connection if streaming is enabled
            if self.default_llm_config.get("stream"):
                await self._setup_ag2_streaming_for_connection(chat_id, enterprise_id)
            
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
                            # Close the WebSocket connection (sync in FastAPI)
                            websocket.close()
                            logger.debug(f"🔌 Closed WebSocket connection: {connection_id}")
                        except Exception as e:
                            logger.warning(f"⚠️ Error during WebSocket cleanup for {connection_id}: {e}")
                        finally:
                            del connection_data["websocket"]
                    
                    logger.info(f"🔌 Disconnected connection: {connection_id}")
            
            # Clear active connections
            self.active_connections.clear()
            self.connections.clear()
            
            logger.info("✅ All transport connections disconnected")
            
        except Exception as e:
            logger.error(f"❌ Error during disconnect: {e}")
    
    def get_connection_info(self) -> Dict[str, int]:
        """Get information about active connections"""
        try:
            websocket_count = 0
            websocket_count = 0
            
            # Count active connections by type
            for connection_data in self.connections.values():
                if connection_data.get("active", False):
                    if "websocket" in connection_data:
                        websocket_count += 1
            
            total_count = websocket_count
            
            return {
                "websocket_connections": websocket_count,
                "total_connections": total_count
            }
        except Exception as e:
            logger.error(f"❌ Error getting connection info: {e}")
            return {"websocket_connections": 0, "total_connections": 0}
    
    async def check_user_tokens(self, user_id: str, enterprise_id: str, chat_id: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Check if user has tokens available for AI usage.
        Returns (has_tokens, token_info)
        """
        try:
            from core.data.persistence_manager import PersistenceManager
            
            persistence = PersistenceManager()
            token_data = await persistence.get_user_tokens(user_id, enterprise_id)
            
            if not token_data:
                return False, None
            
            trial_config = get_free_trial_config()
            
            trial_tokens = token_data.get("available_trial_tokens", 0)
            available_tokens = token_data.get("available_tokens", 0)
            total_tokens = trial_tokens + available_tokens
            
            # Check if user is running low on trial tokens
            is_trial_user = token_data.get("free_trial", False)
            near_trial_limit = is_trial_user and trial_tokens <= trial_config["warning_threshold"]
            
            token_info = {
                "total_available": total_tokens,
                "trial_tokens": trial_tokens,
                "available_tokens": available_tokens,
                "is_trial_user": is_trial_user,
                "near_trial_limit": near_trial_limit,
                "warning_threshold": trial_config["warning_threshold"]
            }
            
            return total_tokens > 0, token_info
            
        except Exception as e:
            logger.error(f"❌ Error checking user tokens: {e}")
            return False, None
    
    async def send_token_exhausted_message(self, chat_id: str, token_info: Optional[Dict[str, Any]] = None) -> None:
        """Send token exhausted message to user via WebSocket"""
        trial_config = get_free_trial_config()
        
        # Determine message based on user type
        if token_info and token_info.get("is_trial_user", False):
            message = (
                "🚀 **Your free trial tokens have been used up!**\n\n"
                "To continue using MozaiksAI, please upgrade to a paid plan. "
                "You'll get more tokens and access to all features."
            )
        else:
            message = (
                "💰 **You've run out of tokens!**\n\n"
                "Please purchase more tokens to continue your conversation."
            )
        
        await self.send_chat_message(
            message,
            "System",
            chat_id
        )
        
        # Send structured token exhausted event
        await self.send_to_ui({
            "type": "token_exhausted",
            "data": {
                "message": message,
                "token_info": token_info,
                "upgrade_available": trial_config.get("auto_upgrade_prompt", True),
                "chat_paused": True
            }
        }, chat_id)
    
    async def send_low_tokens_warning(self, chat_id: str, token_info: Dict[str, Any]) -> None:
        """Send low tokens warning to user"""
        remaining = token_info.get("total_available", 0)
        
        if token_info.get("is_trial_user", False):
            message = (
                f"⚠️ **Trial tokens running low!**\n\n"
                f"You have {remaining} tokens remaining in your free trial. "
                f"Consider upgrading to continue unlimited conversations."
            )
        else:
            message = (
                f"⚠️ **Low token balance!**\n\n"
                f"You have {remaining} tokens remaining. "
                f"Consider purchasing more tokens to avoid interruption."
            )
        
        await self.send_chat_message(
            message,
            "System",
            chat_id
        )
    
    async def handle_websocket(
        self,
        websocket: WebSocket,
        chat_id: str,
        user_id: str,
        workflow_name: str,
        enterprise_id: Optional[str] = None
    ) -> None:
        """Handle WebSocket connection for real-time communication"""
        try:
            # Accept the WebSocket connection
            await websocket.accept()
            logger.info(f"🔌 WebSocket connected for chat_id: {chat_id}, workflow: {workflow_name}")
            
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
            
            # Send initial connection event
            await websocket.send_text(json.dumps({
                "type": "status",
                "data": {
                    "status": "connected",
                    "chat_id": chat_id,
                    "workflow_name": workflow_name,
                    "connection_type": "websocket"
                },
                "timestamp": datetime.utcnow().isoformat()
            }))
            # Auto-start workflow execution if configured (no initial user message)
            try:
                await self.handle_user_input_from_api(
                    chat_id=chat_id,
                    user_id=user_id,
                    workflow_name=workflow_name,
                    message=None
                )
            except Exception as e:
                logger.error(f"❌ Auto-start workflow failed for {chat_id}: {e}")
            
            try:
                while True:
                    # Receive message from WebSocket
                    data = await websocket.receive_text()
                    message_data = json.loads(data)
                    
                    if message_data.get("type") == "user_message":
                        user_input = message_data.get("message", "")
                        if user_input.strip():
                            # Send user message to UI following your event system
                            await self.send_chat_message(
                                user_input,
                                "User", 
                                chat_id
                            )
                            
                            # Process message through workflow system
                            from core.workflow.init_registry import get_or_discover_workflow_handler
                            
                            # Determine workflow type from message or use default
                            workflow_name = message_data.get("workflow_name", "chat")
                            
                            # Process through workflow handler
                            workflow_handler = get_or_discover_workflow_handler(workflow_name)
                            if workflow_handler:
                                try:
                                    result = await self.handle_user_input_from_api(
                                        chat_id=chat_id,
                                        user_id=user_id,
                                        workflow_name=workflow_name,
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
                    
                    elif message_data.get("type") == "user_input_response":
                        # Handle user input response for AG2 IOStream
                        input_request_id = message_data.get("input_request_id")
                        user_input = message_data.get("user_input", "")
                        
                        if input_request_id:
                            success = await self.submit_user_input(input_request_id, user_input)
                            if success:
                                logger.info(f"✅ User input submitted for request {input_request_id}")
                                await websocket.send_text(json.dumps({
                                    "type": "user_input_response_ack",
                                    "status": "success",
                                    "input_request_id": input_request_id,
                                    "timestamp": datetime.utcnow().isoformat()
                                }))
                            else:
                                logger.warning(f"⚠️ Failed to submit user input for request {input_request_id}")
                                await websocket.send_text(json.dumps({
                                    "type": "user_input_response_ack",
                                    "status": "error",
                                    "input_request_id": input_request_id,
                                    "message": "Input request not found or already completed",
                                    "timestamp": datetime.utcnow().isoformat()
                                }))
                        else:
                            logger.warning("⚠️ User input response missing input_request_id")
                    
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
            # Proper disconnection handling for AG2 resume functionality
            try:
                # Import and use the real persistence manager for disconnection handling
                from core.data.persistence_manager import PersistenceManager
                real_persistence = PersistenceManager()
                
                if enterprise_id:
                    await real_persistence.handle_websocket_disconnection(
                        chat_id=chat_id,
                        enterprise_id=enterprise_id,
                        reason="websocket_disconnected"
                    )
                    logger.info(f"💾 Saved disconnection state for resume: {chat_id}")
            except Exception as save_error:
                logger.error(f"❌ Failed to save disconnection state: {save_error}")
            
            # Cleanup connection
            if chat_id in self.connections:
                self.connections[chat_id]["active"] = False
                if "websocket" in self.connections[chat_id]:
                    del self.connections[chat_id]["websocket"]
            
            logger.info(f"🔌 WebSocket disconnected for {chat_id}")

    # ==================================================================================
    # WORKFLOW INTEGRATION METHODS
    # ==================================================================================
    
    async def handle_user_input_from_api(
        self, 
        chat_id: str, 
        user_id: Optional[str], 
        workflow_name: str, 
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
                await self.send_chat_message(
                    message,
                    "User", 
                    chat_id
                )
            else:
                # For auto-start without user input, just log
                logger.info(f"🚀 Starting workflow '{workflow_name}' for {chat_id} without initial user message")
            
            # Create session if it doesn't exist, with resume capability
            if chat_id not in self.connections:
                # Extract enterprise_id from context or use default
                enterprise_id = getattr(self, 'current_enterprise_id', 'default')
                
                session_info = await self.create_session(
                    chat_id=chat_id, 
                    enterprise_id=enterprise_id,
                    check_resume=True
                )
                logger.info(f"🆕 Created session for API input: {session_info['session_type']}")
            
            # Integrate with actual workflow system
            if message:
                logger.info(f"🚀 Starting workflow '{workflow_name}' for message: {message[:50]}...")
            else:
                logger.info(f"🚀 Starting workflow '{workflow_name}' with auto-start (no initial message)")
            
            # Send status update
            await self.send_status(
                "processing",
                "info",
                chat_id
            )
            
            # Get the actual workflow handler and execute it
            from core.workflow.init_registry import get_or_discover_workflow_handler
            
            workflow_handler = get_or_discover_workflow_handler(workflow_name)
            if not workflow_handler:
                error_msg = f"Workflow '{workflow_name}' not found in registry"
                logger.error(f"❌ {error_msg}")
                await self.send_error(
                    error_msg,
                    "WORKFLOW_NOT_FOUND",
                    chat_id
                )
                return {
                    "status": "error",
                    "message": error_msg,
                    "workflow_name": workflow_name
                }
            
            # Execute the workflow with proper parameters
            try:
                # Extract enterprise_id from context or use default
                enterprise_id = getattr(self, 'current_enterprise_id', 'default')
                
                # 🎯 CHECK USER TOKENS BEFORE WORKFLOW EXECUTION
                has_tokens, token_info = await self.check_user_tokens(
                    user_id=user_id or "unknown",
                    enterprise_id=enterprise_id,
                    chat_id=chat_id
                )
                
                if not has_tokens:
                    logger.warning(f"⚠️ User {user_id} has no tokens available for chat {chat_id}")
                    await self.send_token_exhausted_message(chat_id, token_info)
                    
                    return {
                        "status": "token_exhausted",
                        "message": "No tokens available for AI processing",
                        "workflow_name": workflow_name,
                        "token_info": token_info
                    }
                
                # Send low tokens warning if needed
                if token_info and token_info.get("near_trial_limit", False):
                    await self.send_low_tokens_warning(chat_id, token_info)
                
                # Log workflow start to agent_chat.log
                chat_logger.info(f"WORKFLOW_START | Chat: {chat_id} | Workflow: {workflow_name} | User: {user_id or 'unknown'} | HasMessage: {message is not None}")
                
                result = await workflow_handler(
                    enterprise_id=enterprise_id,
                    chat_id=chat_id,
                    user_id=user_id or "unknown",
                    initial_message=message
                )
                
                logger.info(f"✅ Workflow '{workflow_name}' completed successfully")
                
                # Log workflow completion to agent_chat.log
                chat_logger.info(f"WORKFLOW_COMPLETE | Chat: {chat_id} | Workflow: {workflow_name} | Result: {str(result)[:100] if result else 'None'}")
                
                # Send completion status
                await self.send_status(
                    "completed",
                    "info",
                    chat_id
                )
                
                return {
                    "status": "processed",
                    "workflow_name": workflow_name,
                    "message_id": f"{chat_id}_{int(time.time())}",
                    "result": result if result else "completed"
                }
                
            except Exception as workflow_error:
                error_msg = f"Workflow execution failed: {str(workflow_error)}"
                logger.error(f"❌ {error_msg}", exc_info=True)
                
                # Log workflow error to agent_chat.log
                chat_logger.error(f"WORKFLOW_ERROR | Chat: {chat_id} | Workflow: {workflow_name} | Error: {str(workflow_error)[:200]}")
                
                await self.send_error(
                    error_msg,
                    "WORKFLOW_EXECUTION_ERROR",
                    chat_id
                )
                
                return {
                    "status": "error",
                    "message": error_msg,
                    "workflow_name": workflow_name
                }
            
        except Exception as e:
            error_msg = f"Failed to process API message: {str(e)}"
            logger.error(f"❌ API workflow execution failed: {e}", exc_info=True)
            
            # Send error event following the documented event system
            await self.send_error(
                error_msg,
                "API_PROCESSING_ERROR",
                chat_id
            )
            
            return {
                "status": "error", 
                "message": error_msg,
                "workflow_name": workflow_name
            }

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
            connection_data = self.connections[chat_id]
            if "websocket" in connection_data and connection_data.get("active", False):
                try:
                    websocket = connection_data["websocket"]
                    
                    # For AG2 simple text approach, we can send structured data as JSON
                    # The frontend will parse it and handle display accordingly
                    message_data = {
                        "type": "simple_text",
                        "content": content,
                        "agent_name": agent_name or "Agent",
                        "timestamp": asyncio.get_event_loop().time(),
                        "chat_id": chat_id
                    }
                    
                    # Send as JSON for proper parsing
                    await websocket.send_text(json.dumps(message_data))
                    logger.debug(f"📤 Simple text sent to {chat_id} from {agent_name}: {content[:100]}...")
                except Exception as ws_error:
                    logger.warning(f"⚠️ Failed to send simple text to {chat_id}: {ws_error}")
    
    async def send_tool_event(
        self, 
        tool_id: str, 
        payload: Dict[str, Any], 
        display: str = "inline",
        chat_id: Optional[str] = None
    ) -> None:
        """
        Send tool UI event with clear routing.
        
        Args:
            tool_id: Unique identifier for the tool/component
            payload: Tool-specific data
            display: "inline" (in chat) or "artifact" (side panel)
            chat_id: Target chat ID
        """
        event_data = {
            "type": "ui_tool",
            "data": {
                "toolId": tool_id,
                "payload": payload,
                "display": display,
                "chat_id": chat_id
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
        await self._broadcast_to_websockets(event_data, chat_id)
        
        display_location = "inline chat" if display == "inline" else "artifact panel"
        logger.info(f"� Tool Event: {tool_id} → {display_location}")
    
    async def send_backend_notification(
        self, 
        action: str, 
        status: str, 
        data: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Send backend-only notification (not for chat UI).
        Used for system events, saves, etc.
        """
        logger.info(f"� Backend Action: {action} → {status}")
        if data:
            logger.debug(f"   Data: {data}")
    
    # ==================================================================================
    # UI TOOL RESPONSE COLLECTION (For Dynamic UI System)
    # ==================================================================================
    
    @classmethod
    async def wait_for_ui_tool_response(cls, event_id: str) -> Dict[str, Any]:
        """
        Wait indefinitely for UI tool response for a specific event.
        
        This is called by UI tool functions when they emit events and need responses.
        The frontend will call submit_ui_tool_response() to provide the response.
        No timeout - like ChatGPT, users can take their time to interact with UI components.
        """
        # Access the singleton instance
        instance = cls._get_instance()
        if not instance:
            raise RuntimeError("SimpleTransport instance not available")
            
        if not hasattr(instance, 'pending_ui_tool_responses'):
            instance.pending_ui_tool_responses = {}
            
        if event_id not in instance.pending_ui_tool_responses:
            # Create a future to wait for the response
            instance.pending_ui_tool_responses[event_id] = asyncio.Future()
        
        try:
            # Wait indefinitely for the UI tool response - no timeout
            response = await instance.pending_ui_tool_responses[event_id]
            return response
        finally:
            # Clean up the pending response
            if event_id in instance.pending_ui_tool_responses:
                del instance.pending_ui_tool_responses[event_id]
    
    async def submit_ui_tool_response(self, event_id: str, response_data: Dict[str, Any]) -> bool:
        """
        Submit UI tool response for a pending event.
        
        This method is called by the API endpoint when the frontend submits UI tool responses.
        """
        if not hasattr(self, 'pending_ui_tool_responses'):
            self.pending_ui_tool_responses = {}
            
        if event_id in self.pending_ui_tool_responses:
            future = self.pending_ui_tool_responses[event_id]
            if not future.done():
                future.set_result(response_data)
                logger.info(f"✅ [UI_TOOL] Submitted UI tool response for event {event_id}")
                return True
            else:
                logger.warning(f"⚠️ [UI_TOOL] Event {event_id} already completed")
                return False
        else:
            logger.warning(f"⚠️ [UI_TOOL] No pending UI tool response found for {event_id}")
            return False


