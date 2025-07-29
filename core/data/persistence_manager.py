"""
Enhanced PersistenceManager with VE-style chat session management
Supports multiple workflows per enterprise with comprehensive session tracking
Based on AD_DevDeploy.py patterns for production-scale chat management
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Union, Tuple
from dataclasses import dataclass, field
from bson import ObjectId
from bson.errors import InvalidId

from logs.logging_config import get_business_logger
from core.core_config import get_mongo_client

logger = get_business_logger("persistence")

class InvalidEnterpriseIdError(Exception):
    """Raised when enterprise ID is invalid"""
    pass

class PersistenceManager:
    """
    VE-Style Persistence Manager with comprehensive chat session management
    
    Design Philosophy (from AD_DevDeploy.py):
    - Each enterprise can have multiple workflows (5-10+ different workflow types)
    - Each workflow can have thousands/millions of concurrent user sessions
    - Sessions need proper state tracking, resume capability, and cleanup
    - Connection state management for WebSocket reliability
    - Comprehensive chat history with agent output tracking
    
    Collection Design:
    - ChatSessions: Individual user sessions with workflow-specific data
    - Enterprises: Company data with embedded user management and workflow stats
    - Concepts: Workflow definitions and configuration (optional)
    """

    def __init__(self):
        self.client = get_mongo_client()
        self.db1 = self.client['MozaiksDB']
        self.db2 = self.client['autogen_ai_agents']
        
        # Core collections (optimized 3-collection design)
        self.enterprises_collection = self.db1['Enterprises']
        self.chat_sessions_collection = self.db2['ChatSessions']  # VE-style comprehensive sessions
        self.concepts_collection = self.db2['Concepts']  # Workflow definitions
    
    def _ensure_object_id(self, id_value: Union[str, ObjectId], field_name: str = "ID") -> ObjectId:
        """Convert string to ObjectId or validate existing ObjectId"""
        if isinstance(id_value, ObjectId):
            return id_value
        if isinstance(id_value, str) and len(id_value) == 24:
            try:
                return ObjectId(id_value)
            except InvalidId:
                pass
        raise InvalidEnterpriseIdError(f"Invalid {field_name}: {id_value}")

    async def _validate_enterprise_exists(self, enterprise_id: Union[str, ObjectId]) -> ObjectId:
        """Validate enterprise exists in database"""
        enterprise_oid = self._ensure_object_id(enterprise_id, "enterprise_id")
        if not await self.enterprises_collection.find_one({"_id": enterprise_oid}):
            raise InvalidEnterpriseIdError(f"Enterprise {enterprise_id} does not exist.")
        return enterprise_oid

    # ==================================================================================
    # CONSOLIDATED CHAT SESSION MANAGEMENT
    # ==================================================================================

    async def create_chat_session(self, chat_id: str, enterprise_id: Union[str, ObjectId],
                                user_id: str, workflow_name: str = "default") -> bool:
        """Create new VE-style chat session with comprehensive tracking"""
        try:
            eid = await self._validate_enterprise_exists(enterprise_id)
            
            # VE-style comprehensive session document
            session_doc = {
                "chat_id": chat_id,
                "enterprise_id": eid,
                "user_id": user_id,
                "workflow_name": workflow_name,
                
                # VE-style session state tracking
                "status": 0,  # 0 = in progress, 100+ = completed
                "is_complete": False,
                "connection_state": "active",
                "can_resume": True,
                "transport_type": "websocket",
                "flow_state": "initial",  # VE workflow progression tracking
                
                # VE-style workflow-specific status and state tracking
                "workflow_status": {
                    workflow_name: 0  # Per-workflow status tracking
                },
                "workflow_state": {
                    workflow_name: {
                        "can_resume": True,
                        "last_speaker": None,
                        "agent_iteration_counts": {},
                        "current_step": "initialization"
                    }
                },
                "current_workflow": workflow_name,
                
                # VE-style conversation tracking with agent output history
                "messages": [],  # All conversation messages
                "agent_history": [],  # Detailed agent outputs (VE pattern)
                "agents": [],  # Active agents in session
                "current_speaker": None,
                "last_speaker": None,
                "round_count": 0,
                
                # Token usage (embedded for performance)
                "token_usage": {
                    "total_tokens": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_cost": 0.0,
                    "model_breakdown": {},
                    "agent_breakdown": {},
                    "session_id": None,  # VE-style session tracking
                    "cumulative_tokens": 0,
                    "cumulative_cost": 0.0
                },
                
                # VE-style performance metrics
                "performance": {
                    "session_duration_ms": 0,
                    "avg_response_time_ms": 0,
                    "agent_metrics": {},
                    "response_times": [],
                    "file_structure_updates": 0,
                    "stepper_updates": []
                },
                
                # VE-style connection management
                "connection_info": {
                    "websocket_id": None,
                    "client_ip": None,
                    "user_agent": None,
                    "last_ping": datetime.utcnow()
                },
                
                # VE-style resume and lifecycle tracking
                "resume_attempts": 0,
                "max_resume_attempts": 5,
                "disconnection_reason": None,
                "finalized_at": None,
                
                # Timestamps
                "created_at": datetime.utcnow(),
                "last_updated": datetime.utcnow(),
                "connected_at": datetime.utcnow(),
                "last_activity": datetime.utcnow()
            }
            
            await self.chat_sessions_collection.insert_one(session_doc)
            logger.info(f"🆕 Created VE-style chat session: {chat_id} (workflow: {workflow_name})")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to create chat session: {e}")
            return False

    async def update_session_tokens(self, chat_id: str, enterprise_id: Union[str, ObjectId],
                                  agent_breakdown: Dict[str, Any]) -> bool:
        """Update token usage in consolidated session document"""
        try:
            eid = await self._validate_enterprise_exists(enterprise_id)
            
            # Calculate totals from agent breakdown
            total_tokens = sum(agent.get("total_tokens", 0) for agent in agent_breakdown.values())
            total_cost = sum(agent.get("total_cost", 0) for agent in agent_breakdown.values())
            prompt_tokens = sum(agent.get("prompt_tokens", 0) for agent in agent_breakdown.values())
            completion_tokens = sum(agent.get("completion_tokens", 0) for agent in agent_breakdown.values())
            
            await self.chat_sessions_collection.update_one(
                {"chat_id": chat_id, "enterprise_id": eid},
                {
                    "$set": {
                        "token_usage.total_tokens": total_tokens,
                        "token_usage.prompt_tokens": prompt_tokens,
                        "token_usage.completion_tokens": completion_tokens,
                        "token_usage.total_cost": total_cost,
                        "token_usage.agent_breakdown": agent_breakdown,
                        "last_updated": datetime.utcnow()
                    }
                }
            )
            
            logger.info(f"💰 Updated session tokens: {total_tokens} tokens, ${total_cost:.6f}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to update session tokens: {e}")
            return False

    async def add_message(self, chat_id: str, enterprise_id: Union[str, ObjectId],
                        sender: str, content: str, tokens_used: int = 0, cost: float = 0.0) -> bool:
        """Add message to consolidated session document"""
        try:
            eid = await self._validate_enterprise_exists(enterprise_id)
            
            message = {
                "sender": sender,
                "content": content,
                "timestamp": datetime.utcnow(),
                "tokens_used": tokens_used,
                "cost": cost,
                "message_id": str(ObjectId())
            }
            
            await self.chat_sessions_collection.update_one(
                {"chat_id": chat_id, "enterprise_id": eid},
                {
                    "$push": {"messages": message},
                    "$set": {"last_updated": datetime.utcnow()}
                }
            )
            
            logger.info(f"💬 Added message from {sender}: {tokens_used} tokens")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to add message: {e}")
            return False

    async def get_session_summary(self, chat_id: str, enterprise_id: Union[str, ObjectId]) -> Dict[str, Any]:
        """Get complete session data from single document"""
        try:
            eid = await self._validate_enterprise_exists(enterprise_id)
            
            session = await self.chat_sessions_collection.find_one({
                "chat_id": chat_id,
                "enterprise_id": eid
            })
            
            if not session:
                return {}
            
            return {
                "session_info": {
                    "chat_id": session["chat_id"],
                    "user_id": session["user_id"],
                    "workflow_name": session["workflow_name"],
                    "status": session["status"],
                    "is_complete": session["is_complete"],
                    "created_at": session["created_at"],
                    "duration_seconds": (datetime.utcnow() - session["created_at"]).total_seconds()
                },
                "usage_summary": session.get("token_usage", {}),
                "performance_metrics": session.get("performance", {}),
                "message_count": len(session.get("messages", [])),
                "agents": session.get("agents", [])
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to get session summary: {e}")
            return {}

    # ==================================================================================
    # ENTERPRISE TOKEN MANAGEMENT (Embedded in Enterprises collection)
    # ==================================================================================

    async def get_user_tokens(self, user_id: str, enterprise_id: Union[str, ObjectId]) -> Dict[str, Any]:
        """Get user token data embedded in enterprise document"""
        try:
            eid = await self._validate_enterprise_exists(enterprise_id)
            
            enterprise = await self.enterprises_collection.find_one(
                {"_id": eid},
                {f"users.{user_id}": 1}
            )
            
            if not enterprise or "users" not in enterprise or user_id not in enterprise["users"]:
                # Create default user token data
                default_tokens = {
                    "available_tokens": 0,
                    "available_trial_tokens": 1000,
                    "free_trial": True,
                    "trial_started_at": datetime.utcnow(),
                    "usage_history": []
                }
                
                await self.enterprises_collection.update_one(
                    {"_id": eid},
                    {"$set": {f"users.{user_id}": default_tokens}},
                    upsert=True
                )
                
                return default_tokens
            
            return enterprise["users"][user_id]
            
        except Exception as e:
            logger.error(f"❌ Failed to get user tokens: {e}")
            return {}

    async def update_user_tokens(self, user_id: str, enterprise_id: Union[str, ObjectId],
                               tokens_used: int, cost: float) -> bool:
        """Update user token balance embedded in enterprise document"""
        try:
            eid = await self._validate_enterprise_exists(enterprise_id)
            
            # Get current tokens
            current_tokens = await self.get_user_tokens(user_id, enterprise_id)
            
            # Calculate new balances
            new_trial_tokens = max(0, current_tokens["available_trial_tokens"] - tokens_used)
            tokens_from_paid = max(0, tokens_used - current_tokens["available_trial_tokens"])
            new_paid_tokens = max(0, current_tokens["available_tokens"] - tokens_from_paid)
            
            # Add to usage history
            usage_entry = {
                "date": datetime.utcnow().date().isoformat(),
                "tokens_used": tokens_used,
                "cost": cost,
                "timestamp": datetime.utcnow()
            }
            
            await self.enterprises_collection.update_one(
                {"_id": eid},
                {
                    "$set": {
                        f"users.{user_id}.available_tokens": new_paid_tokens,
                        f"users.{user_id}.available_trial_tokens": new_trial_tokens,
                        f"users.{user_id}.last_updated": datetime.utcnow()
                    },
                    "$push": {f"users.{user_id}.usage_history": usage_entry}
                }
            )
            
            logger.info(f"💰 Updated user tokens: -{tokens_used} tokens, ${cost:.6f}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to update user tokens: {e}")
            return False

    # ==================================================================================
    # VE-STYLE CHAT SESSION MANAGEMENT
    # ==================================================================================

    async def update_chat_status(self, chat_id: str, enterprise_id: Union[str, ObjectId], 
                                status: int, workflow_name: str = "default") -> bool:
        """Update chat status (VE pattern: 0=in progress, 100+=complete)"""
        try:
            eid = await self._validate_enterprise_exists(enterprise_id)
            
            update_doc = {
                "status": status,
                f"workflow_status.{workflow_name}": status,
                "last_updated": datetime.utcnow(),
                "last_activity": datetime.utcnow()
            }
            
            # Mark as complete if status >= 100 (VE pattern)
            if status >= 100:
                update_doc.update({
                    "is_complete": True,
                    "can_resume": False,
                    "finalized_at": datetime.utcnow()
                })
            
            await self.chat_sessions_collection.update_one(
                {"chat_id": chat_id, "enterprise_id": eid},
                {"$set": update_doc}
            )
            
            logger.info(f"📊 Updated chat status: {chat_id} → {status} ({workflow_name})")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to update chat status: {e}")
            return False

    async def update_conversation_with_agent_history(self, chat_id: str, enterprise_id: Union[str, ObjectId],
                                                   sender: str, content: str, workflow_name: str = "default",
                                                   agent_output: Optional[Dict[str, Any]] = None) -> bool:
        """Update conversation with VE-style agent history tracking"""
        try:
            eid = await self._validate_enterprise_exists(enterprise_id)
            
            message = {
                "sender": sender,
                "content": content,
                "timestamp": datetime.utcnow(),
                "message_id": str(ObjectId()),
                "workflow_name": workflow_name
            }
            
            # Extract structured data from agent messages (VE pattern)
            extracted_data = await self._extract_agent_data(sender, content)
            if extracted_data:
                message.update(extracted_data)
            
            update_doc = {
                "$push": {"messages": message},
                "$set": {
                    "last_updated": datetime.utcnow(),
                    "last_activity": datetime.utcnow(),
                    "last_speaker": sender
                }
            }
            
            # Add to agent history if this is an agent output (VE pattern)
            if agent_output or sender != "user_proxy":
                agent_history_entry = {
                    "agent_name": sender,
                    "content": content,
                    "timestamp": datetime.utcnow(),
                    "workflow_name": workflow_name,
                    "message_id": message["message_id"]
                }
                
                if agent_output:
                    agent_history_entry["parsed_output"] = agent_output
                
                update_doc["$push"]["agent_history"] = agent_history_entry
            
            await self.chat_sessions_collection.update_one(
                {"chat_id": chat_id, "enterprise_id": eid},
                update_doc,
                upsert=True
            )
            
            logger.info(f"💬 Added message from {sender} with agent history tracking")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to update conversation: {e}")
            return False

    async def get_chat_status(self, chat_id: str, enterprise_id: Union[str, ObjectId],
                            workflow_name: str = "default") -> Optional[int]:
        """Get chat status (VE pattern compatibility)"""
        return await self.get_workflow_status(chat_id, enterprise_id, workflow_name)

    async def save_chat_state_with_agents(self, chat_id: str, enterprise_id: Union[str, ObjectId],
                                        state_data: Dict[str, Any], workflow_name: str = "default",
                                        agents: Optional[List[str]] = None, 
                                        current_speaker: Optional[str] = None) -> bool:
        """Save comprehensive chat state with VE-style agent tracking"""
        try:
            eid = await self._validate_enterprise_exists(enterprise_id)
            
            # VE-style comprehensive state tracking
            workflow_state = {
                **state_data,
                "can_resume": True,
                "last_speaker": current_speaker,
                "agent_iteration_counts": state_data.get("agent_iteration_counts", {}),
                "current_step": state_data.get("current_step", "unknown"),
                "flow_state": state_data.get("flow_state", "main"),
                "last_updated": datetime.utcnow()
            }
            
            update_doc = {
                f"workflow_state.{workflow_name}": workflow_state,
                "current_workflow": workflow_name,
                "can_resume": True,
                "last_updated": datetime.utcnow(),
                "last_activity": datetime.utcnow()
            }
            
            if current_speaker:
                update_doc["current_speaker"] = current_speaker
                update_doc["last_speaker"] = current_speaker
            
            if agents:
                update_doc["agents"] = agents
            
            await self.chat_sessions_collection.update_one(
                {"chat_id": chat_id, "enterprise_id": eid},
                {"$set": update_doc},
                upsert=True
            )
            
            logger.info(f"💾 Saved VE-style chat state for {workflow_name}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to save chat state: {e}")
            return False

    async def can_resume_chat_with_validation(self, chat_id: str, enterprise_id: Union[str, ObjectId],
                                            workflow_name: str = "default") -> Tuple[bool, Optional[str]]:
        """VE-style resume validation with detailed reason"""
        try:
            eid = await self._validate_enterprise_exists(enterprise_id)
            
            session = await self.chat_sessions_collection.find_one(
                {"chat_id": chat_id, "enterprise_id": eid},
                {f"workflow_state.{workflow_name}": 1, f"workflow_status.{workflow_name}": 1, 
                 "is_complete": 1, "can_resume": 1, "status": 1, "resume_attempts": 1, 
                 "max_resume_attempts": 1, "connection_state": 1}
            )
            
            if not session:
                return False, "Session not found"
            
            # Check completion status
            workflow_status = session.get("workflow_status", {}).get(workflow_name)
            main_status = session.get("status", 0)
            status = workflow_status if workflow_status is not None else main_status
            
            if status >= 100:
                return False, f"Workflow completed with status {status}"
            
            # Check if session is marked complete
            if session.get("is_complete", False):
                return False, "Session marked as complete"
            
            # Check resume attempts (VE pattern)
            resume_attempts = session.get("resume_attempts", 0)
            max_attempts = session.get("max_resume_attempts", 5)
            if resume_attempts >= max_attempts:
                return False, f"Maximum resume attempts exceeded ({resume_attempts}/{max_attempts})"
            
            # Check can_resume flag
            if not session.get("can_resume", False):
                return False, "Session marked as non-resumable"
            
            # Check connection state
            connection_state = session.get("connection_state", "unknown")
            if connection_state == "terminated":
                return False, "Session terminated"
            
            # Check workflow-specific state
            workflow_state = session.get("workflow_state", {}).get(workflow_name, {})
            if not workflow_state.get("can_resume", False):
                return False, f"Workflow {workflow_name} marked as non-resumable"
            
            logger.info(f"🔄 Session {chat_id} can be resumed (status: {status})")
            return True, "Session can be resumed"
            
        except Exception as e:
            logger.error(f"❌ Failed to validate resume capability: {e}")
            return False, f"Error validating resume: {e}"

    async def resume_chat_with_comprehensive_data(self, chat_id: str, enterprise_id: Union[str, ObjectId],
                                                workflow_name: str = "default") -> Tuple[bool, Optional[Dict[str, Any]]]:
        """VE-style comprehensive resume with all session data"""
        try:
            can_resume, reason = await self.can_resume_chat_with_validation(chat_id, enterprise_id, workflow_name)
            
            if not can_resume:
                logger.info(f"❌ Cannot resume {workflow_name} chat {chat_id}: {reason}")
                return False, {"can_resume": False, "reason": reason}
            
            eid = await self._validate_enterprise_exists(enterprise_id)
            
            session = await self.chat_sessions_collection.find_one(
                {"chat_id": chat_id, "enterprise_id": eid}
            )
            
            if not session:
                return False, {"can_resume": False, "reason": "Session not found"}
            
            # Increment resume attempts
            await self.chat_sessions_collection.update_one(
                {"chat_id": chat_id, "enterprise_id": eid},
                {
                    "$inc": {"resume_attempts": 1},
                    "$set": {
                        "connection_state": "reconnected",
                        "reconnected_at": datetime.utcnow(),
                        "last_updated": datetime.utcnow(),
                        "last_activity": datetime.utcnow()
                    }
                }
            )
            
            # Build comprehensive resume data (VE pattern)
            messages = session.get("messages", [])
            conversation = [msg for msg in messages if msg.get("workflow_name", "default") == workflow_name]
            
            agent_history = session.get("agent_history", [])
            workflow_agent_history = [entry for entry in agent_history if entry.get("workflow_name", "default") == workflow_name]
            
            state = session.get("workflow_state", {}).get(workflow_name, {})
            workflow_status = session.get("workflow_status", {}).get(workflow_name)
            main_status = session.get("status", 0)
            status = workflow_status if workflow_status is not None else main_status
            
            resume_data = {
                "can_resume": True,
                "session_info": {
                    "chat_id": chat_id,
                    "user_id": session.get("user_id"),
                    "workflow_name": workflow_name,
                    "created_at": session.get("created_at"),
                    "last_updated": session.get("last_updated"),
                    "last_activity": session.get("last_activity"),
                    "connection_state": session.get("connection_state"),
                    "flow_state": session.get("flow_state", "initial")
                },
                "conversation": conversation,
                "agent_history": workflow_agent_history,
                "state": state,
                "status": status,
                "workflow_name": workflow_name,
                "agents": session.get("agents", []),
                "current_speaker": session.get("current_speaker"),
                "last_speaker": session.get("last_speaker"),
                "round_count": session.get("round_count", 0),
                "token_usage": session.get("token_usage", {}),
                "performance": session.get("performance", {}),
                "resume_attempts": session.get("resume_attempts", 0) + 1,
                "max_resume_attempts": session.get("max_resume_attempts", 5)
            }
            
            logger.info(f"🔄 Successfully resumed {workflow_name} chat {chat_id}")
            logger.info(f"   - {len(conversation)} messages, {len(workflow_agent_history)} agent outputs")
            logger.info(f"   - Status: {status}, State: {state.get('current_step', 'unknown')}")
            logger.info(f"   - Resume attempt: {resume_data['resume_attempts']}/{resume_data['max_resume_attempts']}")
            
            return True, resume_data
            
        except Exception as e:
            logger.error(f"❌ Failed to resume {workflow_name} chat: {e}")
            return False, {"can_resume": False, "reason": f"Resume error: {e}"}

    # ==================================================================================
    # VE-STYLE CONNECTION STATE MANAGEMENT 
    # ==================================================================================

    async def update_connection_state_with_info(self, chat_id: str, enterprise_id: Union[str, ObjectId],
                                              state: str, connection_info: Optional[Dict[str, Any]] = None,
                                              transport_type: str = "websocket") -> bool:
        """VE-style comprehensive connection state management"""
        try:
            eid = await self._validate_enterprise_exists(enterprise_id)
            
            update_doc = {
                "connection_state": state,
                "transport_type": transport_type,
                "last_updated": datetime.utcnow(),
                "last_activity": datetime.utcnow(),
                f"{state}_at": datetime.utcnow()
            }
            
            if connection_info:
                update_doc["connection_info"] = {
                    **connection_info,
                    "last_ping": datetime.utcnow()
                }
            
            # VE-style state-specific handling
            if state == "disconnected":
                update_doc.update({
                    "disconnection_reason": connection_info.get("reason", "unknown") if connection_info else "unknown",
                    "can_resume": True  # VE pattern: disconnection doesn't prevent resume
                })
            elif state == "connected":
                update_doc.update({
                    "connected_at": datetime.utcnow(),
                    "can_resume": True
                })
            elif state == "reconnected":
                update_doc.update({
                    "$inc": {"resume_attempts": 1}
                })
            
            await self.chat_sessions_collection.update_one(
                {"chat_id": chat_id, "enterprise_id": eid},
                {"$set": update_doc} if "$inc" not in update_doc else {
                    "$set": {k: v for k, v in update_doc.items() if k != "$inc"},
                    "$inc": update_doc["$inc"]
                },
                upsert=True
            )
            
            logger.info(f"🔗 Updated connection state: {chat_id} → {state} ({transport_type})")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to update connection state: {e}")
            return False

    async def handle_websocket_disconnection(self, chat_id: str, enterprise_id: Union[str, ObjectId],
                                           reason: str = "unknown") -> bool:
        """VE-style WebSocket disconnection handling with resume preservation"""
        return await self.update_connection_state_with_info(
            chat_id=chat_id,
            enterprise_id=enterprise_id,
            state="disconnected",
            connection_info={"reason": reason, "disconnected_at": datetime.utcnow()},
            transport_type="websocket"
        )

    # ==================================================================================
    # VE-STYLE ENTERPRISE WORKFLOW MANAGEMENT
    # ==================================================================================

    async def get_enterprise_active_sessions(self, enterprise_id: Union[str, ObjectId],
                                           workflow_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all active sessions for an enterprise (VE pattern: enterprise dashboard)"""
        try:
            eid = await self._validate_enterprise_exists(enterprise_id)
            
            query = {
                "enterprise_id": eid,
                "is_complete": {"$ne": True},
                "status": {"$lt": 100}
            }
            
            if workflow_name:
                query["workflow_name"] = workflow_name
            
            sessions = await self.chat_sessions_collection.find(
                query,
                {
                    "chat_id": 1, "user_id": 1, "workflow_name": 1, "status": 1,
                    "connection_state": 1, "created_at": 1, "last_activity": 1,
                    "current_speaker": 1, "round_count": 1, "can_resume": 1
                }
            ).to_list(length=None)
            
            logger.info(f"📊 Found {len(sessions)} active sessions for enterprise {enterprise_id}")
            return sessions
            
        except Exception as e:
            logger.error(f"❌ Failed to get enterprise sessions: {e}")
            return []

    async def get_workflow_session_stats(self, enterprise_id: Union[str, ObjectId],
                                       workflow_name: str) -> Dict[str, Any]:
        """Get comprehensive workflow statistics (VE pattern: workflow analytics)"""
        try:
            eid = await self._validate_enterprise_exists(enterprise_id)
            
            # Aggregate session statistics
            pipeline = [
                {"$match": {"enterprise_id": eid, "workflow_name": workflow_name}},
                {"$group": {
                    "_id": "$workflow_name",
                    "total_sessions": {"$sum": 1},
                    "active_sessions": {"$sum": {"$cond": [{"$lt": ["$status", 100]}, 1, 0]}},
                    "completed_sessions": {"$sum": {"$cond": [{"$gte": ["$status", 100]}, 1, 0]}},
                    "avg_tokens": {"$avg": "$token_usage.total_tokens"},
                    "total_tokens": {"$sum": "$token_usage.total_tokens"},
                    "avg_cost": {"$avg": "$token_usage.total_cost"},
                    "total_cost": {"$sum": "$token_usage.total_cost"},
                    "avg_duration": {"$avg": "$performance.session_duration_ms"},
                    "last_session": {"$max": "$created_at"}
                }}
            ]
            
            result = await self.chat_sessions_collection.aggregate(pipeline).to_list(length=1)
            
            if result:
                stats = result[0]
                stats["workflow_name"] = workflow_name
                stats["enterprise_id"] = str(eid)
                logger.info(f"📈 Workflow {workflow_name} stats: {stats['total_sessions']} sessions, ${stats['total_cost']:.6f} total cost")
                return stats
            else:
                return {
                    "workflow_name": workflow_name,
                    "enterprise_id": str(eid),
                    "total_sessions": 0,
                    "active_sessions": 0,
                    "completed_sessions": 0
                }
                
        except Exception as e:
            logger.error(f"❌ Failed to get workflow stats: {e}")
            return {}

    async def cleanup_stale_sessions(self, enterprise_id: Union[str, ObjectId],
                                   hours_inactive: int = 24) -> int:
        """Clean up stale sessions (VE pattern: session lifecycle management)"""
        try:
            eid = await self._validate_enterprise_exists(enterprise_id)
            
            cutoff_time = datetime.utcnow() - timedelta(hours=hours_inactive)
            
            # Find stale sessions
            stale_query = {
                "enterprise_id": eid,
                "last_activity": {"$lt": cutoff_time},
                "connection_state": {"$in": ["disconnected", "unknown"]},
                "is_complete": {"$ne": True}
            }
            
            stale_sessions = await self.chat_sessions_collection.find(stale_query).to_list(length=None)
            
            if stale_sessions:
                # Mark as terminated instead of deleting (VE pattern: preserve data)
                update_result = await self.chat_sessions_collection.update_many(
                    stale_query,
                    {
                        "$set": {
                            "connection_state": "terminated",
                            "can_resume": False,
                            "terminated_at": datetime.utcnow(),
                            "termination_reason": f"Inactive for {hours_inactive} hours"
                        }
                    }
                )
                
                logger.info(f"🧹 Cleaned up {update_result.modified_count} stale sessions")
                return update_result.modified_count
            else:
                logger.info("🧹 No stale sessions found")
                return 0
                
        except Exception as e:
            logger.error(f"❌ Failed to cleanup stale sessions: {e}")
            return 0

    async def finalize_conversation_with_cleanup(self, chat_id: str, enterprise_id: Union[str, ObjectId],
                                               final_status: int = 100, workflow_name: str = "default",
                                               cleanup_data: Optional[Dict[str, Any]] = None) -> bool:
        """VE-style conversation finalization with comprehensive cleanup"""
        try:
            eid = await self._validate_enterprise_exists(enterprise_id)
            
            finalization_data = {
                f"workflow_status.{workflow_name}": final_status,
                "status": final_status,
                "finalized_at": datetime.utcnow(),
                "is_complete": True,
                "can_resume": False,
                "connection_state": "completed",
                "last_updated": datetime.utcnow()
            }
            
            if cleanup_data:
                finalization_data["finalization_data"] = cleanup_data
            
            await self.chat_sessions_collection.update_one(
                {"chat_id": chat_id, "enterprise_id": eid},
                {"$set": finalization_data}
            )
            
            # Update enterprise workflow statistics
            session = await self.chat_sessions_collection.find_one(
                {"chat_id": chat_id, "enterprise_id": eid},
                {"token_usage": 1, "performance": 1}
            )
            
            if session:
                session_data = {
                    "total_tokens": session.get("token_usage", {}).get("total_tokens", 0),
                    "total_cost": session.get("token_usage", {}).get("total_cost", 0),
                    "duration_ms": session.get("performance", {}).get("session_duration_ms", 0),
                    "final_status": final_status
                }
                
                await self.update_workflow_stats(
                    enterprise_id=enterprise_id,
                    workflow_name=workflow_name,
                    session_data=session_data
                )
            
            logger.info(f"✅ Finalized {workflow_name} conversation: {chat_id} (status: {final_status})")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to finalize conversation: {e}")
            return False

    # ==================================================================================
    # BACKWARD COMPATIBILITY (VE Style)
    # ==================================================================================

    async def update_workflow_status(self, chat_id: str, enterprise_id: Union[str, ObjectId], 
                                   status: int, workflow_name: str = "default") -> bool:
        """Update workflow status (wrapper for get_workflow_status logic)"""
        try:
            eid = await self._validate_enterprise_exists(enterprise_id)
            
            await self.chat_sessions_collection.update_one(
                {"chat_id": chat_id, "enterprise_id": eid},
                {
                    "$set": {
                        f"workflow_status.{workflow_name}": status,
                        "status": status,
                        "last_updated": datetime.utcnow()
                    }
                },
                upsert=True
            )
            
            logger.info(f"📊 Updated {workflow_name} status to {status}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to update workflow status: {e}")
            return False

    async def update_conversation(self, chat_id: str, enterprise_id: Union[str, ObjectId],
                                sender: str, content: str, workflow_name: str = "default") -> bool:
        """Update conversation with new message (enhanced version of add_message)"""
        try:
            eid = await self._validate_enterprise_exists(enterprise_id)
            
            message = {
                "sender": sender,
                "content": content,
                "timestamp": datetime.utcnow(),
                "message_id": str(ObjectId()),
                "workflow_name": workflow_name
            }
            
            # Extract any structured data from agent messages
            extracted_data = await self._extract_agent_data(sender, content)
            if extracted_data:
                message.update(extracted_data)
            
            await self.chat_sessions_collection.update_one(
                {"chat_id": chat_id, "enterprise_id": eid},
                {
                    "$push": {"messages": message},
                    "$set": {"last_updated": datetime.utcnow()}
                },
                upsert=True
            )
            
            logger.info(f"💬 Added message from {sender} to {workflow_name} conversation")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to update conversation: {e}")
            return False

    async def save_chat_state(self, chat_id: str, enterprise_id: Union[str, ObjectId],
                            state_data: Dict[str, Any], workflow_name: str = "default") -> bool:
        """Save current chat state in consolidated session document"""
        try:
            eid = await self._validate_enterprise_exists(enterprise_id)
            
            await self.chat_sessions_collection.update_one(
                {"chat_id": chat_id, "enterprise_id": eid},
                {
                    "$set": {
                        f"workflow_state.{workflow_name}": state_data,
                        "current_workflow": workflow_name,
                        "can_resume": True,
                        "last_updated": datetime.utcnow()
                    }
                },
                upsert=True
            )
            
            logger.info(f"💾 Saved {workflow_name} chat state for {chat_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to save chat state: {e}")
            return False

    async def get_workflow_status(self, chat_id: str, enterprise_id: Union[str, ObjectId],
                                workflow_name: str = "default") -> Optional[int]:
        """Get workflow status from consolidated session document"""
        try:
            eid = await self._validate_enterprise_exists(enterprise_id)
            
            session = await self.chat_sessions_collection.find_one(
                {"chat_id": chat_id, "enterprise_id": eid},
                {f"workflow_status.{workflow_name}": 1, "status": 1}
            )
            
            if session:
                # Try workflow-specific status first, then fall back to main status
                return session.get("workflow_status", {}).get(workflow_name) or session.get("status", 0)
            
            return 0
            
        except Exception as e:
            logger.error(f"❌ Failed to get workflow status: {e}")
            return 0

    # ==================================================================================
    # RESUME & LIFECYCLE MANAGEMENT (VE Style)
    # ==================================================================================

    async def finalize_conversation(self, chat_id: str, enterprise_id: Union[str, ObjectId],
                                  final_status: int = 100, workflow_name: str = "default") -> bool:
        """Finalize conversation and mark as complete"""
        try:
            eid = await self._validate_enterprise_exists(enterprise_id)
            
            await self.chat_sessions_collection.update_one(
                {"chat_id": chat_id, "enterprise_id": eid},
                {
                    "$set": {
                        f"workflow_status.{workflow_name}": final_status,
                        "status": final_status,
                        "finalized_at": datetime.utcnow(),
                        "is_complete": True,
                        "can_resume": False,
                        "last_updated": datetime.utcnow()
                    }
                }
            )
            
            logger.info(f"✅ Finalized {workflow_name} conversation with status {final_status}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to finalize conversation: {e}")
            return False

    async def handle_disconnection(self, chat_id: str, enterprise_id: Union[str, ObjectId],
                                 connection_info: Optional[Dict[str, Any]] = None) -> bool:
        """Handle client disconnection"""
        try:
            eid = await self._validate_enterprise_exists(enterprise_id)
            
            await self.chat_sessions_collection.update_one(
                {"chat_id": chat_id, "enterprise_id": eid},
                {
                    "$set": {
                        "connection_state": "disconnected",
                        "disconnected_at": datetime.utcnow(),
                        "connection_info": connection_info or {},
                        "last_updated": datetime.utcnow()
                    }
                }
            )
            
            logger.info(f"🔌 Marked chat {chat_id} as disconnected")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to handle disconnection: {e}")
            return False

    async def send_chat_history(self, chat_id: str, enterprise_id: Union[str, ObjectId],
                              workflow_name: str = "default", include_last: bool = True) -> List[Dict[str, Any]]:
        """Get chat history for sending to client"""
        try:
            eid = await self._validate_enterprise_exists(enterprise_id)
            
            session = await self.chat_sessions_collection.find_one(
                {"chat_id": chat_id, "enterprise_id": eid},
                {"messages": 1}
            )
            
            if not session:
                return []
            
            messages = session.get("messages", [])
            
            # Filter by workflow_name if specified
            if workflow_name != "default":
                messages = [msg for msg in messages if msg.get("workflow_name", "default") == workflow_name]
            
            if not include_last and messages:
                messages = messages[:-1]
            
            # Format for frontend consumption
            formatted_history = []
            for msg in messages:
                formatted_history.append({
                    "sender": msg.get("sender", "unknown"),
                    "content": msg.get("content", ""),
                    "timestamp": msg.get("timestamp"),
                    "message_id": msg.get("message_id"),
                    "workflow_name": msg.get("workflow_name", "default")
                })
            
            logger.info(f"📜 Retrieved {len(formatted_history)} messages from {workflow_name} history")
            return formatted_history
            
        except Exception as e:
            logger.error(f"❌ Failed to get chat history: {e}")
            return []

    # ==================================================================================
    # SIMPLE RESUME LOGIC (VE Style)
    # ==================================================================================

    async def can_resume_chat(self, chat_id: str, enterprise_id: Union[str, ObjectId],
                            workflow_name: str = "default") -> bool:
        """Check if chat can be resumed (VE-style using status pattern)"""
        try:
            eid = await self._validate_enterprise_exists(enterprise_id)
            
            session = await self.chat_sessions_collection.find_one(
                {"chat_id": chat_id, "enterprise_id": eid},
                {f"workflow_state.{workflow_name}": 1, f"workflow_status.{workflow_name}": 1, 
                 "is_complete": 1, "can_resume": 1, "status": 1}
            )
            
            if not session:
                return False
            
            # VE pattern: Check status for resume logic (0 = can resume, 1+ = completed)
            workflow_status = session.get("workflow_status", {}).get(workflow_name)
            main_status = session.get("status", 0)
            status = workflow_status if workflow_status is not None else main_status
            
            state = session.get("workflow_state", {}).get(workflow_name, {})
            is_complete = session.get("is_complete", False)
            can_resume = session.get("can_resume", False)
            
            # Can resume if status is 0 (in progress) and not marked complete
            # This mimics VE's CreationChatStatus logic
            resumable = (status == 0 and not is_complete and can_resume)
            
            logger.info(f"🔄 Resume check - Status: {status}, Complete: {is_complete}, Can Resume: {resumable}")
            return resumable
            
        except Exception as e:
            logger.error(f"❌ Failed to check resume status: {e}")
            return False

    async def resume_chat(self, chat_id: str, enterprise_id: Union[str, ObjectId],
                        workflow_name: str = "default") -> Tuple[bool, Optional[Dict[str, Any]]]:
        """Resume chat with VE-style state restoration using workflow_name"""
        try:
            if not await self.can_resume_chat(chat_id, enterprise_id, workflow_name):
                logger.info(f"❌ Cannot resume {workflow_name} chat {chat_id} - checking completion status")
                
                # Check if workflow is already complete (VE pattern)
                eid = await self._validate_enterprise_exists(enterprise_id)
                session = await self.chat_sessions_collection.find_one(
                    {"chat_id": chat_id, "enterprise_id": eid},
                    {f"workflow_status.{workflow_name}": 1, "status": 1}
                )
                
                if session:
                    workflow_status = session.get("workflow_status", {}).get(workflow_name)
                    main_status = session.get("status", 0)
                    status = workflow_status if workflow_status is not None else main_status
                    
                    if status >= 100:  # VE uses 100+ for completion
                        logger.info(f"✅ {workflow_name.title()} workflow already completed with status {status}")
                        return False, {"already_complete": True, "status": status}
                
                return False, None
            
            eid = await self._validate_enterprise_exists(enterprise_id)
            
            session = await self.chat_sessions_collection.find_one(
                {"chat_id": chat_id, "enterprise_id": eid}
            )
            
            if not session:
                return False, None
            
            # Get workflow-specific conversation history and state (using workflow_name)
            messages = session.get("messages", [])
            # Filter messages for this workflow
            conversation = [msg for msg in messages if msg.get("workflow_name", "default") == workflow_name]
            
            state = session.get("workflow_state", {}).get(workflow_name, {})
            workflow_status = session.get("workflow_status", {}).get(workflow_name)
            main_status = session.get("status", 0)
            status = workflow_status if workflow_status is not None else main_status
            
            resume_data = {
                "conversation": conversation,
                "state": state,
                "status": status,
                "workflow_name": workflow_name,
                "can_resume": True,
                "session_info": {
                    "chat_id": chat_id,
                    "user_id": session.get("user_id"),
                    "created_at": session.get("created_at"),
                    "last_updated": session.get("last_updated")
                }
            }
            
            # Mark as reconnected
            await self.chat_sessions_collection.update_one(
                {"chat_id": chat_id, "enterprise_id": eid},
                {
                    "$set": {
                        "connection_state": "reconnected",
                        "reconnected_at": datetime.utcnow(),
                        "last_updated": datetime.utcnow()
                    }
                }
            )
            
            logger.info(f"🔄 Resumed {workflow_name} chat {chat_id} with {len(conversation)} messages, status {status}")
            return True, resume_data
            
        except Exception as e:
            logger.error(f"❌ Failed to resume {workflow_name} chat: {e}")
            return False, None

    # ==================================================================================
    # CONNECTION STATE MANAGEMENT (For AG2 iostream compatibility)
    # ==================================================================================

    async def mark_connection_state(self, chat_id: str, enterprise_id: Union[str, ObjectId],
                                  state: str, transport_type: str = "websocket",
                                  connection_info: Optional[Dict[str, Any]] = None) -> bool:
        """Mark connection state for proper resume handling"""
        try:
            eid = await self._validate_enterprise_exists(enterprise_id)
            
            update_doc = {
                "connection_state": state,
                "transport_type": transport_type,
                "last_updated": datetime.utcnow(),
                f"{state}_at": datetime.utcnow()
            }
            
            if connection_info:
                update_doc["connection_info"] = connection_info
            
            await self.chat_sessions_collection.update_one(
                {"chat_id": chat_id, "enterprise_id": eid},
                {"$set": update_doc},
                upsert=True
            )
            
            logger.info(f"🔗 Connection state updated: {chat_id} → {state} ({transport_type})")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to update connection state: {e}")
            return False

    # ==================================================================================
    # HELPER METHODS
    # ==================================================================================

    async def _extract_agent_data(self, sender: str, content: str) -> Dict[str, Any]:
        """Extract structured data from agent messages"""
        try:
            # Try to parse JSON content
            if content.strip().startswith('{') and content.strip().endswith('}'):
                import json
                clean_content = content.replace('```json', '').replace('```', '').strip()
                data = json.loads(clean_content)
                
                # Store agent-specific data
                return {
                    f"{sender}_data": data,
                    "has_structured_data": True
                }
                
        except Exception:
            pass
        
        return {}

    # ==================================================================================
    # ANALYTICS (Embedded in Enterprise document)
    # ==================================================================================

    async def update_workflow_stats(self, enterprise_id: Union[str, ObjectId], 
                                  workflow_name: str, session_data: Dict[str, Any]) -> bool:
        """Update workflow statistics embedded in enterprise document"""
        try:
            eid = await self._validate_enterprise_exists(enterprise_id)
            
            # Get current stats
            enterprise = await self.enterprises_collection.find_one(
                {"_id": eid},
                {f"workflow_stats.{workflow_name}": 1}
            )
            
            current_stats = {}
            if enterprise and "workflow_stats" in enterprise and workflow_name in enterprise["workflow_stats"]:
                current_stats = enterprise["workflow_stats"][workflow_name]
            
            # Calculate new averages
            session_count = current_stats.get("total_sessions", 0) + 1
            
            def update_avg(current_avg, new_value, count):
                if count <= 1:
                    return new_value
                return ((current_avg * (count - 1)) + new_value) / count
            
            new_stats = {
                "total_sessions": session_count,
                "avg_tokens_per_session": update_avg(
                    current_stats.get("avg_tokens_per_session", 0),
                    session_data.get("total_tokens", 0),
                    session_count
                ),
                "avg_cost_per_session": update_avg(
                    current_stats.get("avg_cost_per_session", 0),
                    session_data.get("total_cost", 0),
                    session_count
                ),
                "avg_duration_ms": update_avg(
                    current_stats.get("avg_duration_ms", 0),
                    session_data.get("duration_ms", 0),
                    session_count
                ),
                "last_updated": datetime.utcnow()
            }
            
            await self.enterprises_collection.update_one(
                {"_id": eid},
                {"$set": {f"workflow_stats.{workflow_name}": new_stats}}
            )
            
            logger.info(f"📊 Updated workflow stats for {workflow_name}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to update workflow stats: {e}")
            return False

    # ==================================================================================
    # BACKWARD COMPATIBILITY METHODS (for groupchat_manager.py)
    # ==================================================================================

    async def get_workflow_averages(self, workflow_name: str, enterprise_id: Union[str, ObjectId]) -> Dict[str, Any]:
        """Get workflow averages from enterprise analytics"""
        try:
            eid = await self._validate_enterprise_exists(enterprise_id)
            
            enterprise = await self.enterprises_collection.find_one(
                {"_id": eid},
                {f"workflow_stats.{workflow_name}": 1}
            )
            
            if enterprise and "workflow_stats" in enterprise and workflow_name in enterprise["workflow_stats"]:
                stats = enterprise["workflow_stats"][workflow_name]
                return {
                    "avg_tokens": stats.get("avg_tokens_per_session", 0),
                    "avg_cost": stats.get("avg_cost_per_session", 0),
                    "avg_duration_ms": stats.get("avg_duration_ms", 0),
                    "total_sessions": stats.get("total_sessions", 0)
                }
            
            return {"avg_tokens": 0, "avg_cost": 0, "avg_duration_ms": 0, "total_sessions": 0}
            
        except Exception as e:
            logger.error(f"❌ Failed to get workflow averages: {e}")
            return {"avg_tokens": 0, "avg_cost": 0, "avg_duration_ms": 0, "total_sessions": 0}

    async def load_chat_state(self, chat_id: str, enterprise_id: Union[str, ObjectId], 
                            workflow_name: str = "default") -> Optional[Dict[str, Any]]:
        """Load chat state from session document (compatible with old interface)"""
        try:
            eid = await self._validate_enterprise_exists(enterprise_id)
            
            session = await self.chat_sessions_collection.find_one(
                {"chat_id": chat_id, "enterprise_id": eid},
                {f"workflow_state.{workflow_name}": 1}
            )
            
            if session and "workflow_state" in session and workflow_name in session["workflow_state"]:
                return session["workflow_state"][workflow_name]
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Failed to load chat state: {e}")
            return None

    async def find_latest_concept_for_enterprise(self, enterprise_id: Union[str, ObjectId]) -> Optional[Dict[str, Any]]:
        """Find latest concept for enterprise (placeholder implementation)"""
        try:
            eid = await self._validate_enterprise_exists(enterprise_id)
            
            # For VE-style, we can return basic enterprise info as "concept"
            enterprise = await self.enterprises_collection.find_one({"_id": eid})
            
            if enterprise:
                return {
                    "enterprise_id": str(enterprise["_id"]),
                    "name": enterprise.get("name", "Unknown"),
                    "workflows": list(enterprise.get("workflow_stats", {}).keys()),
                    "concept_type": "enterprise_default"
                }
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Failed to find concept for enterprise: {e}")
            return None
