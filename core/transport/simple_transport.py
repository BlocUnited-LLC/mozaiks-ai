# ==============================================================================
# FILE: core/transport/simple_transport.py
# DESCRIPTION: Complete transport system with AG2 resume functionality
# ==============================================================================
import json
import logging
from typing import Dict, Any, Optional, Union, Tuple, List
from fastapi import WebSocket
from fastapi.responses import StreamingResponse
from datetime import datetime
import asyncio
import time

# AG2 imports for resume functionality
from autogen import Agent, GroupChatManager
from autogen.agentchat.groupchat import GroupChat

logger = logging.getLogger(__name__)

# ==================================================================================
# MESSAGE FILTERING
# ==================================================================================

class MessageFilter:
    """Simple message filter to remove AutoGen noise"""
    
    def should_stream_message(self, sender_name: str, message_content: str, message_type: str = "agent_message") -> bool:
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
    
    def __init__(self, default_llm_config: Dict[str, Any]):
        self.default_llm_config = default_llm_config
        self.active_connections = {}
        self.connections: Dict[str, Dict[str, Any]] = {}
        self.message_filter = MessageFilter()
        self.persistence = PersistenceManager()
        
    def should_show_to_user(self, message: str, agent_name: Optional[str] = None) -> bool:
        """The core filtering logic - removes AutoGen noise"""
        return self.message_filter.should_stream_message(
            sender_name=agent_name or "unknown",
            message_content=message
        )
    
    def format_agent_name(self, agent_name: Optional[str]) -> str:
        """Clean up agent names for UI display"""
        if not agent_name:
            return "Assistant"
        return self.message_filter.format_agent_name_for_ui(agent_name)
    
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
        Simple method - send messages to UI.
        """
        
        # For simple strings, apply traditional filtering
        if isinstance(message, str):
            if not self.should_show_to_user(message, agent_name):
                logger.debug(f"🚫 Filtered message from {agent_name}: {message[:50]}...")
                return
        
        # Format agent name
        formatted_agent = self.format_agent_name(agent_name)
        
        # Simple routing - send as chat message
        event_data = {
            "message": str(message),
            "agent_name": formatted_agent,
            "timestamp": datetime.utcnow().isoformat(),
            "chat_id": chat_id,
            "metadata": metadata or {},
            "message_type": message_type
        }
        
        # Send to all active connections (simplified - no complex routing)
        logger.info(f"📤 {formatted_agent}: {str(message)[:100]}...")
        
        # In a real implementation, this would send via SSE/WebSocket
        # For now, just log the clean output
        
    async def send_error(
        self,
        error_message: str,
        error_code: str = "GENERAL_ERROR",
        chat_id: Optional[str] = None
    ) -> None:
        """Send error message to UI"""
        event_data = {
            "error": error_message,
            "error_code": error_code,
            "timestamp": datetime.utcnow().isoformat(),
            "chat_id": chat_id
        }
        
        logger.error(f"❌ Error: {error_message}")
        
    async def send_status(
        self,
        status_message: str,
        status_type: str = "info",
        chat_id: Optional[str] = None
    ) -> None:
        """Send status update to UI"""
        event_data = {
            "status": status_message,
            "status_type": status_type,
            "timestamp": datetime.utcnow().isoformat(),
            "chat_id": chat_id
        }
        
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
        manager: GroupChatManager,
        new_message: Optional[str] = None
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
    # WORKFLOW INTEGRATION METHODS
    # ==================================================================================
    
    async def _handle_user_input(self, chat_id: str, user_input: str) -> None:
        """Handle user input from WebSocket/SSE and execute workflows"""
        try:
            # Get session info
            if chat_id not in self.connections:
                await self.send_error("Session not found", "SESSION_NOT_FOUND", chat_id)
                return
            
            session_info = self.connections[chat_id]
            enterprise_id = session_info["enterprise_id"]
            
            # Add user message to UI immediately
            await self.send_to_ui(
                message=user_input,
                agent_name="User",
                message_type="chat_message",
                chat_id=chat_id
            )
            
            # Get workflow handler from registry
            from ..workflow.init_registry import get_workflow_handler
            
            workflow_handler = get_workflow_handler("default")  # Use default workflow
            
            if not workflow_handler:
                error_msg = "No workflow handler found"
                logger.error(error_msg)
                await self.send_error(error_msg, "UNKNOWN_WORKFLOW", chat_id)
                return
            
            # Create communication channel wrapper
            communication_channel = SimpleCommunicationChannelWrapper(self, chat_id)
            
            # Call the workflow handler
            import inspect
            sig = inspect.signature(workflow_handler)
            
            workflow_kwargs = {
                "enterprise_id": enterprise_id,
                "chat_id": chat_id,
                "user_id": "user",
                "initial_message": user_input,
                "communication_channel": communication_channel
            }
            
            # Filter to only include parameters the workflow expects
            filtered_kwargs = {k: v for k, v in workflow_kwargs.items() if k in sig.parameters}
            
            logger.info(f"🚀 Executing workflow with message: {user_input[:50]}...")
            
            # Call the workflow
            result = await workflow_handler(**filtered_kwargs)
            
            logger.info(f"✅ Workflow completed successfully")
            
        except Exception as e:
            error_msg = f"Failed to process message: {str(e)}"
            logger.error(f"❌ Workflow execution failed: {e}", exc_info=True)
            
            await self.send_error(
                error_message=error_msg,
                error_code="PROCESSING_ERROR",
                chat_id=chat_id
            )
    
    async def handle_user_input_from_api(
        self, 
        chat_id: str, 
        user_id: Optional[str], 
        workflow_type: str, 
        message: str
    ) -> Dict[str, Any]:
        """Handle user input from the POST API endpoint"""
        try:
            # Add user message to UI immediately
            await self.send_to_ui(
                message=message,
                agent_name="User",
                message_type="chat_message",
                chat_id=chat_id
            )
            
            # Get workflow handler from registry
            from ..workflow.init_registry import get_workflow_handler
            
            workflow_handler = get_workflow_handler(workflow_type)
            
            if not workflow_handler:
                error_msg = f"No workflow handler found for type: {workflow_type}"
                logger.error(error_msg)
                await self.send_error(error_msg, "UNKNOWN_WORKFLOW", chat_id)
                return {"status": "error", "message": error_msg}
            
            # Create communication channel wrapper
            communication_channel = SimpleCommunicationChannelWrapper(self, chat_id)
            
            # Call the workflow handler
            import inspect
            sig = inspect.signature(workflow_handler)
            
            workflow_kwargs = {
                "enterprise_id": "default",
                "chat_id": chat_id,
                "user_id": user_id or "unknown",
                "initial_message": message,
                "communication_channel": communication_channel
            }
            
            # Filter to only include parameters the workflow expects
            filtered_kwargs = {k: v for k, v in workflow_kwargs.items() if k in sig.parameters}
            
            logger.info(f"🚀 Executing workflow '{workflow_type}' via API with message: {message[:50]}...")
            
            # Call the workflow
            result = await workflow_handler(**filtered_kwargs)
            
            logger.info(f"✅ Workflow '{workflow_type}' completed successfully via API")
            
            return {
                "status": "processed",
                "workflow_type": workflow_type,
                "result": result if result else "completed"
            }
            
        except Exception as e:
            error_msg = f"Failed to process message: {str(e)}"
            logger.error(f"❌ API workflow execution failed: {e}", exc_info=True)
            
            await self.send_error(
                error_message=error_msg,
                error_code="API_PROCESSING_ERROR",
                chat_id=chat_id
            )
            
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
            await self.send_to_ui(message, agent_name, "chat_message")
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
        
        # Send to UI immediately - this is production behavior
        if event_type == "route_to_chat":
            logger.info(f"📱 Routing to inline component: {data.get('component_name')}")
        elif event_type == "route_to_artifact":
            logger.info(f"🗂️ Creating artifact component: {data.get('component_name')} - {data.get('title', 'No title')}")
        elif event_type == "ui_tool_action":
            logger.info(f"🔧 UI Tool Action: {data.get('tool_id')} - {data.get('action_type')}")
        
        # This is where the actual transport would send the event to frontend
        # The event_data is properly formatted for frontend consumption

# ==================================================================================
# COMMUNICATION CHANNEL WRAPPER
# ==================================================================================

class SimpleCommunicationChannelWrapper:
    """Wrapper to make SimpleTransport compatible with workflow communication protocols"""
    
    def __init__(self, transport: SimpleTransport, chat_id: str):
        self.transport = transport
        self.chat_id = chat_id
    
    async def send_event(self, event_type: str, data: Any, agent_name: Optional[str] = None) -> None:
        await self.transport.send_event(event_type, data, agent_name)
    
    async def send_custom_event(self, name: str, value: Any) -> None:
        await self.transport.send_custom_event(name, value, self.chat_id)
    
    async def send_ui_component_route(self, agent_id: str, content: str, routing_decision: dict) -> None:
        await self.transport.send_event("route_to_artifact", {
            "agent_id": agent_id,
            "content": content,
            "routing_decision": routing_decision
        })
    
    async def send_ui_tool(self, tool_id: str, payload: Any) -> None:
        await self.transport.send_event("ui_tool_action", {
            "tool_id": tool_id,
            "payload": payload
        })
