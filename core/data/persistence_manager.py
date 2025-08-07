"""
Enhanced PersistenceManager with VE-style chat session management
Supports multiple workflows per enterprise with comprehensive session tracking
Based on AD_DevDeploy.py patterns for production-scale chat management
"""
import logging
import time
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Union, Tuple, Callable
from dataclasses import dataclass, field
from bson import ObjectId
from bson.errors import InvalidId

from logs.logging_config import get_business_logger
from core.core_config import get_mongo_client

# OpenTelemetry instrumentation for database operations
from opentelemetry import trace

logger = get_business_logger("persistence")
tracer = trace.get_tracer(__name__)

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
    """

    def __init__(self):
        self.client = get_mongo_client()
        self.db1 = self.client['MozaiksDB']
        self.db2 = self.client['MozaiksAI']
        
        # Core collections (optimized 3-collection design)
        self.enterprises_collection = self.db1['Enterprises']
        self.chat_sessions_collection = self.db2['ChatSessions']  # VE-style comprehensive sessions
    
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
        with tracer.start_as_current_span("persistence.create_chat_session") as span:
            span.set_attributes({
                "chat_id": chat_id,
                "enterprise_id": str(enterprise_id),
                "user_id": user_id,
                "workflow_name": workflow_name
            })
            
            try:
                eid = await self._validate_enterprise_exists(enterprise_id)
                
                # VE-style comprehensive session document
                session_doc = {
                    "chat_id": chat_id,
                    "enterprise_id": eid,
                    "user_id": user_id,
                    "workflow_name": workflow_name,
                    
                    # VE-style session state tracking
                    "is_complete": False,
                    "connection_state": "active",
                    "can_resume": True,
                    "transport_type": "websocket",
                    "flow_state": "initial",  # VE workflow progression tracking
                    
                    # VE-style workflow-specific status and state tracking
                    "workflow_status": {
                        workflow_name: 0  # Per-workflow status tracking (0 = in progress, 1 = completed)
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
                    
                    # Enhanced real-time tracking (replaces separate UnifiedTracking collection)
                    "real_time_tracking": {
                        "session_id": f"track_{chat_id}_{int(datetime.utcnow().timestamp() * 1000)}",
                        "start_time": datetime.utcnow(),
                        "end_time": None,
                        "current_status": "running",  # running|completed|failed
                        
                        # Comprehensive token tracking
                        "tokens": {
                            "total_tokens": 0,
                            "prompt_tokens": 0,
                            "completion_tokens": 0,
                            "total_cost": 0.0,
                            "model_breakdown": {},
                            "agent_breakdown": {},
                            "cumulative_tokens": 0,
                            "cumulative_cost": 0.0,
                            "last_updated": datetime.utcnow()
                        },
                        
                        # Performance metrics
                        "performance": {
                            "agent_count": 0,
                            "operation_count": 0,
                            "avg_response_time_ms": 0.0,
                            "duration_ms": 0,
                            "response_times": [],
                            "last_operation": datetime.utcnow()
                        },
                        
                        # OpenLit observability integration
                        "observability": {
                            "trace_id": None,
                            "span_ids": [],
                            "metrics_exported": False,
                            "last_export": None,
                            "export_count": 0
                        }
                    },
                    
                    # Legacy token_usage (for backward compatibility - will be deprecated)
                    "token_usage": {
                        "total_tokens": 0,
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "total_cost": 0.0,
                        "model_breakdown": {},
                        "agent_breakdown": {},
                        "session_id": None,
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
                span.set_attribute("success", True)
                return True
                
            except Exception as e:
                logger.error(f"❌ Failed to create chat session: {e}")
                span.set_attribute("success", False)
                span.set_attribute("error", str(e))
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

    # ==================================================================================
    # OPTIMIZED REAL-TIME TRACKING (Replaces UnifiedTracking collection)
    # ==================================================================================

    async def update_real_time_tracking(self, chat_id: str, enterprise_id: Union[str, ObjectId],
                                       tracking_data: Dict[str, Any]) -> bool:
        """Update real-time tracking data directly in ChatSessions (eliminates UnifiedTracking collection)"""
        try:
            eid = await self._validate_enterprise_exists(enterprise_id)
            
            update_fields = {}
            current_time = datetime.utcnow()
            
            # Update token data if provided
            if "tokens" in tracking_data:
                for key, value in tracking_data["tokens"].items():
                    update_fields[f"real_time_tracking.tokens.{key}"] = value
                update_fields["real_time_tracking.tokens.last_updated"] = current_time
            
            # Update performance data if provided
            if "performance" in tracking_data:
                for key, value in tracking_data["performance"].items():
                    if key == "response_times" and isinstance(value, list):
                        # Append to response times array
                        update_fields["$push"] = {"real_time_tracking.performance.response_times": {"$each": value}}
                    else:
                        update_fields[f"real_time_tracking.performance.{key}"] = value
                update_fields["real_time_tracking.performance.last_operation"] = current_time
            
            # Update status if provided
            if "status" in tracking_data:
                update_fields["real_time_tracking.current_status"] = tracking_data["status"]
                if tracking_data["status"] in ["completed", "failed"]:
                    update_fields["real_time_tracking.end_time"] = current_time
            
            # Update observability data if provided
            if "observability" in tracking_data:
                for key, value in tracking_data["observability"].items():
                    update_fields[f"real_time_tracking.observability.{key}"] = value
            
            update_fields["last_updated"] = current_time
            
            # Separate push operations if needed
            push_ops = update_fields.pop("$push", None)
            
            # Perform the update
            if update_fields:
                await self.chat_sessions_collection.update_one(
                    {"chat_id": chat_id, "enterprise_id": eid},
                    {"$set": update_fields}
                )
            
            if push_ops:
                await self.chat_sessions_collection.update_one(
                    {"chat_id": chat_id, "enterprise_id": eid},
                    {"$push": push_ops}
                )
            
            logger.debug(f"📊 Updated real-time tracking for {chat_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to update real-time tracking: {e}")
            return False

    async def get_real_time_tracking(self, chat_id: str, enterprise_id: Union[str, ObjectId]) -> Optional[Dict[str, Any]]:
        """Get real-time tracking data from ChatSessions"""
        try:
            eid = await self._validate_enterprise_exists(enterprise_id)
            
            session = await self.chat_sessions_collection.find_one(
                {"chat_id": chat_id, "enterprise_id": eid},
                {"real_time_tracking": 1}
            )
            
            if session and "real_time_tracking" in session:
                return session["real_time_tracking"]
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Failed to get real-time tracking: {e}")
            return None

    async def finalize_real_time_tracking(self, chat_id: str, enterprise_id: Union[str, ObjectId],
                                         success: bool = True) -> str:
        """Finalize real-time tracking session and return tracking session ID"""
        try:
            eid = await self._validate_enterprise_exists(enterprise_id)
            
            session = await self.chat_sessions_collection.find_one(
                {"chat_id": chat_id, "enterprise_id": eid},
                {"real_time_tracking.session_id": 1}
            )
            
            if not session:
                raise ValueError(f"Session not found: {chat_id}")
            
            tracking_session_id = session.get("real_time_tracking", {}).get("session_id")
            
            final_status = "completed" if success else "failed"
            current_time = datetime.utcnow()
            
            await self.chat_sessions_collection.update_one(
                {"chat_id": chat_id, "enterprise_id": eid},
                {
                    "$set": {
                        "real_time_tracking.current_status": final_status,
                        "real_time_tracking.end_time": current_time,
                        "is_complete": success,
                        "last_updated": current_time
                    }
                }
            )
            
            logger.info(f"✅ Finalized real-time tracking: {tracking_session_id} ({final_status})")
            return tracking_session_id
            
        except Exception as e:
            logger.error(f"❌ Failed to finalize real-time tracking: {e}")
            raise

    async def add_message(self, chat_id: str, enterprise_id: Union[str, ObjectId],
                        sender: str, content: str, tokens_used: int = 0, cost: float = 0.0) -> bool:
        """Add message to consolidated session document"""
        try:
            # Validate enterprise exists, but allow fallback if invalid or missing
            try:
                eid = await self._validate_enterprise_exists(enterprise_id)
            except InvalidEnterpriseIdError:
                logger.warning(f"⚠️ Invalid enterprise_id '{enterprise_id}', skipping validation and using raw value")
                # Use raw enterprise_id when validation fails
                eid = enterprise_id
            
            message = {
                "sender": sender,
                "content": content,
                "timestamp": datetime.utcnow(),
                "tokens_used": tokens_used,
                "cost": cost,
                "message_id": str(ObjectId())
            }
            
            # Create a proper session document if it doesn't exist
            # Note: Don't include fields that are also in $set (to avoid conflicts)
            current_time = datetime.utcnow()
            session_defaults = {
                "chat_id": chat_id,
                "enterprise_id": eid,
                "user_id": "unknown",  # Default user_id for upsert cases
                "workflow_name": "default",
                "is_complete": False,
                "connection_state": "active",
                "can_resume": True,
                "workflow_status": {"default": 0},  # Default workflow status
                "workflow_state": {},
                "agent_history": [],
                "agents": [],
                "current_speaker": None,
                "last_speaker": None,
                "round_count": 0,
                "token_usage": {
                    "total_tokens": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_cost": 0.0,
                    "agent_breakdown": {},
                    "cumulative_tokens": 0,
                    "cumulative_cost": 0.0
                },
                "performance": {
                    "session_duration_ms": 0,
                    "avg_response_time_ms": 0,
                    "agent_metrics": {},
                    "response_times": []
                },
                "connection_info": {
                    "websocket_id": None,
                    "client_ip": None,
                    "user_agent": None,
                    "last_ping": current_time
                },
                "resume_attempts": 0,
                "max_resume_attempts": 5,
                "created_at": current_time
                # Don't include last_updated and last_activity here since they're in $set
            }
            
            await self.chat_sessions_collection.update_one(
                {"chat_id": chat_id, "enterprise_id": eid},
                {
                    "$push": {"messages": message},
                    "$set": {"last_updated": current_time, "last_activity": current_time},
                    "$setOnInsert": session_defaults
                },
                upsert=True  # This will create the document if it doesn't exist
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
            
            # Calculate duration safely
            created_at = session.get("created_at")
            duration_seconds = 0
            if created_at:
                duration_seconds = (datetime.utcnow() - created_at).total_seconds()
                
            return {
                "session_info": {
                    "chat_id": session.get("chat_id", chat_id),
                    "user_id": session.get("user_id", "unknown"),
                    "workflow_name": session.get("workflow_name", "default"),
                    "status": session.get("status", 0),
                    "is_complete": session.get("is_complete", False),
                    "created_at": created_at,
                    "duration_seconds": duration_seconds
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
                # Import token configurations
                from core.core_config import get_free_trial_config, get_token_config
                trial_config = get_free_trial_config()
                token_config = get_token_config()
                
                # Create default user token data using environment configuration
                default_tokens = {
                    "available_tokens": token_config["available_tokens_default"],
                    "available_trial_tokens": trial_config["default_tokens"],
                    "free_trial": trial_config["enabled"],
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
        """Update chat status (VE pattern: 0=in progress, 1=complete)"""
        try:
            eid = await self._validate_enterprise_exists(enterprise_id)
            
            update_doc = {
                "status": status,
                f"workflow_status.{workflow_name}": status,
                "last_updated": datetime.utcnow(),
                "last_activity": datetime.utcnow()
            }
            
            # Mark as complete if status >= 1 (VE pattern)
            if status >= 1:
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
        with tracer.start_as_current_span("persistence.update_conversation") as span:
            span.set_attributes({
                "chat_id": chat_id,
                "enterprise_id": str(enterprise_id),
                "sender": sender,
                "workflow_name": workflow_name,
                "has_agent_output": agent_output is not None
            })
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
                span.set_attribute("success", True)
                return True
                
            except Exception as e:
                logger.error(f"❌ Failed to update conversation: {e}")
                span.set_attribute("success", False)
                span.set_attribute("error", str(e))
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
                 "is_complete": 1, "can_resume": 1, "resume_attempts": 1, 
                 "max_resume_attempts": 1, "connection_state": 1}
            )
            
            if not session:
                return False, "Session not found"
            
            # Check completion status using workflow-specific status
            workflow_status = session.get("workflow_status", {}).get(workflow_name, 0)
            
            if workflow_status >= 1:
                return False, f"Workflow completed with status {workflow_status}"
            
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
            
            logger.info(f"🔄 Session {chat_id} can be resumed (workflow_status: {workflow_status})")
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
            workflow_status = session.get("workflow_status", {}).get(workflow_name, 0)
            
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
                "status": workflow_status,
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
            logger.info(f"   - Status: {workflow_status}, State: {state.get('current_step', 'unknown')}")
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
                "status": {"$lt": 1}
            }
            
            if workflow_name:
                query["workflow_name"] = workflow_name
            
            sessions = await self.chat_sessions_collection.find(
                query,
                {
                    "chat_id": 1, "user_id": 1, "workflow_name": 1, "workflow_status": 1,
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
                    "active_sessions": {"$sum": {"$cond": [{"$lt": ["$status", 1]}, 1, 0]}},
                    "completed_sessions": {"$sum": {"$cond": [{"$gte": ["$status", 1]}, 1, 0]}},
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
                                               final_status: int = 1, workflow_name: str = "default",
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
                {f"workflow_status.{workflow_name}": 1}
            )
            
            if session:
                # Return workflow-specific status
                return session.get("workflow_status", {}).get(workflow_name, 0)
            
            return 0
            
        except Exception as e:
            logger.error(f"❌ Failed to get workflow status: {e}")
            return 0

    # ==================================================================================
    # RESUME & LIFECYCLE MANAGEMENT (VE Style)
    # ==================================================================================

    async def finalize_conversation(self, chat_id: str, enterprise_id: Union[str, ObjectId],
                                  final_status: int = 1, workflow_name: str = "default") -> bool:
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
                 "is_complete": 1, "can_resume": 1}
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
                    {f"workflow_status.{workflow_name}": 1}
                )
                
                if session:
                    workflow_status = session.get("workflow_status", {}).get(workflow_name)
                    main_status = session.get("status", 0)
                    status = workflow_status if workflow_status is not None else main_status
                    
                    if status >= 1:  # VE uses 1 for completion
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

# ===================================================================
# CENTRALIZED WORKFLOW CHAT MANAGER
# ===================================================================

class WorkflowChatManager:
    """
    Centralized chat persistence manager.
    This class provides single-source-of-truth for chat history and real-time token tracking.
    
    Moved from orchestration_patterns.py to centralize all persistence logic.
    """
    
    def __init__(self, workflow_name: str, enterprise_id: str, chat_id: str, 
                 user_id: Optional[str] = None, persistence_manager: Optional[PersistenceManager] = None):
        self.workflow_name = workflow_name
        self.enterprise_id = enterprise_id
        self.chat_id = chat_id
        self.user_id = user_id or "unknown"
        
        # Use provided persistence manager or create new one
        self.persistence_manager = persistence_manager or PersistenceManager()
        
        # Centralized message store - single source of truth
        self.agent_history: List[Dict[str, Any]] = []
        
        # Token tracking integration
        self.session_id = str(int(time.time() * 1000))  # Unique session ID
        self.cumulative_tokens = 0
        self.cumulative_cost = 0.0
        
        # Workflow state
        self.message_count = 0
        self.last_speaker = None
        
        logger.info(f"🏗️ WorkflowChatManager initialized: {workflow_name} | {chat_id} | session: {self.session_id}")
        
    async def ensure_session_exists(self) -> bool:
        """
        Ensure comprehensive session document exists in database.
        This creates the full session structure if it doesn't exist.
        """
        try:
            # Check if session already exists
            eid = await self.persistence_manager._validate_enterprise_exists(self.enterprise_id)
            existing_session = await self.persistence_manager.chat_sessions_collection.find_one({
                "chat_id": self.chat_id,
                "enterprise_id": eid
            })
            
            if existing_session:
                logger.debug(f"✅ Session already exists: {self.chat_id}")
                return True
            
            # Create comprehensive session document
            success = await self.persistence_manager.create_chat_session(
                chat_id=self.chat_id,
                enterprise_id=self.enterprise_id,
                user_id=self.user_id,
                workflow_name=self.workflow_name
            )
            
            if success:
                logger.info(f"✅ Created comprehensive session document: {self.chat_id}")
                return True
            else:
                logger.error(f"❌ Failed to create session document: {self.chat_id}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error ensuring session exists: {e}")
            return False

    
    async def add_message_to_history(self, sender: str, content: str, role: str = "assistant") -> Optional[Dict[str, Any]]:
        """
        Add message to centralized history and immediately persist to database.
        This is the SINGLE entry point for all message storage.
        """
        try:
            # Create standardized message object
            message = {
                "timestamp": datetime.utcnow(),
                "sender": sender,
                "content": content,
                "role": role,
                "name": sender,
                "tokens_used": 0,  # Will be updated when tokens are calculated
                "cost": 0.0,      # Will be updated when tokens are calculated
                "session_id": self.session_id,
                "message_id": f"{self.session_id}_{self.message_count}",
                "workflow_name": self.workflow_name
            }
            
            # Check for duplicates (prevent double storage)
            if not any(
                msg["content"] == content and msg["sender"] == sender 
                for msg in self.agent_history
            ):
                # Add to centralized in-memory store
                self.agent_history.append(message)
                self.message_count += 1
                self.last_speaker = sender
                
                # REAL-TIME persistence - immediately persist to database
                await self._persist_message_to_database_realtime(message)
                
                logger.info(f"� REAL-TIME PERSIST: Added and persisted message from {sender} ({len(content)} chars)")
                return message
            else:
                logger.debug(f"🚫 DUPLICATE SKIP: Message from {sender} already in history")
                return None
                
        except Exception as e:
            logger.error(f"❌ CENTRALIZED STORE ERROR: Failed to add message from {sender}: {e}")
            raise
    
    async def _persist_message_to_database(self, message: Dict[str, Any]) -> None:
        """
        Internal method to immediately persist message to database.
        """
        try:
            await self.persistence_manager.add_message(
                chat_id=self.chat_id,
                enterprise_id=self.enterprise_id,
                sender=message["sender"],
                content=message["content"],
                tokens_used=message["tokens_used"],
                cost=message["cost"]
            )
            logger.debug(f"💾 DB PERSIST: Message from {message['sender']} stored in database")
            
        except Exception as db_error:
            logger.error(f"❌ DB PERSIST FAILED: Database storage failed for {message['sender']}: {db_error}")
            # Don't raise - we still have it in memory, this is just persistence layer

    async def _persist_message_to_database_realtime(self, message: Dict[str, Any]) -> None:
        """
        REAL-TIME: Immediately persist message to database without blocking.
        This is called from event processing for instant persistence.
        """
        try:
            # Debug: Log the enterprise_id we're working with
            logger.info(f"🚀 REAL-TIME DB START: Attempting to persist message from {message['sender']} | Chat: {self.chat_id} | Enterprise: {self.enterprise_id}")
            
            await self.persistence_manager.add_message(
                chat_id=self.chat_id,
                enterprise_id=self.enterprise_id,
                sender=message["sender"],
                content=message["content"],
                tokens_used=message["tokens_used"],
                cost=message["cost"]
            )
            # Mark as persisted to avoid duplicate storage
            message["database_persisted"] = True
            message["persisted_at"] = datetime.utcnow()
            
            logger.info(f"🚀 REAL-TIME DB SUCCESS: Message from {message['sender']} immediately persisted to database")
            
        except Exception as db_error:
            logger.error(f"❌ REAL-TIME DB FAILED: {db_error}")
            logger.error(f"❌ REAL-TIME DB ERROR DETAILS: Chat: {self.chat_id}, Enterprise: {self.enterprise_id}, Sender: {message.get('sender')}")
            import traceback
            logger.error(f"❌ REAL-TIME DB TRACEBACK: {traceback.format_exc()}")
            # Mark as needing persistence retry
            message["needs_persistence"] = True
            message["persistence_error"] = str(db_error)
    
    async def flush_messages_to_database(self) -> None:
        """
        Flush all cached messages to database.
        Called when AG2 conversation completes to ensure all messages are persisted.
        """
        try:
            if not self.agent_history:
                logger.warning(f"⚠️ FLUSH SKIP: No messages to flush to database")
                return
            
            persisted_count = 0
            for message in self.agent_history:
                try:
                    # Check if message already has database persistence marker
                    if not message.get("database_persisted", False):
                        await self.persistence_manager.add_message(
                            chat_id=self.chat_id,
                            enterprise_id=self.enterprise_id,
                            sender=message["sender"],
                            content=message["content"],
                            tokens_used=message["tokens_used"],
                            cost=message["cost"]
                        )
                        # Mark as persisted to avoid duplicates
                        message["database_persisted"] = True
                        persisted_count += 1
                        
                except Exception as persist_error:
                    logger.error(f"❌ FLUSH ERROR: Failed to persist message from {message['sender']}: {persist_error}")
            
            logger.info(f"✅ FLUSH SUCCESS: Persisted {persisted_count}/{len(self.agent_history)} messages to database")
            
        except Exception as e:
            logger.error(f"❌ FLUSH FAILED: {e}")
            raise

    async def update_message_tokens(self, tracker_summary: Dict[str, Any]) -> None:
        """
        Update messages in centralized history with real token usage data.
        """
        try:
            total_tokens = tracker_summary.get("total_tokens", 0)
            total_cost = tracker_summary.get("total_cost", 0.0)
            
            if total_tokens == 0 or not self.agent_history:
                logger.warning(f"⚠️ TOKEN UPDATE SKIP: No tokens ({total_tokens}) or no messages ({len(self.agent_history)})")
                return
            
            # Filter agent messages for token distribution (generic agent pattern)
            agent_messages = [
                msg for msg in self.agent_history 
                if msg["sender"].endswith("Agent") or msg["sender"] == "Assistant"
            ]
            
            if not agent_messages:
                logger.warning(f"⚠️ TOKEN UPDATE SKIP: No agent messages found for token distribution")
                return
            
            # Calculate total content length for proportional distribution
            total_content_length = sum(len(msg["content"]) for msg in agent_messages)
            
            if total_content_length == 0:
                logger.warning(f"⚠️ TOKEN UPDATE SKIP: Total content length is 0")
                return
            
            # Distribute tokens proportionally based on content length
            for message in agent_messages:
                content_length = len(message["content"])
                proportion = content_length / total_content_length
                
                message["tokens_used"] = int(total_tokens * proportion)
                message["cost"] = total_cost * proportion
                message["token_update_timestamp"] = datetime.utcnow()
                message["token_tracking_session"] = self.session_id
            
            # Update cumulative tracking
            self.cumulative_tokens += total_tokens
            self.cumulative_cost += total_cost
            
            # Update database with token information
            await self._update_database_with_tokens()
            
            logger.info(f"✅ TOKEN UPDATE SUCCESS: Updated {len(agent_messages)} messages with {total_tokens} tokens, ${total_cost:.6f}")
            
        except Exception as e:
            logger.error(f"❌ TOKEN UPDATE FAILED: {e}")
            raise
    
    async def _update_database_with_tokens(self) -> None:
        """
        Update database messages with token information from centralized history.
        """
        try:
            # Get current chat session
            chat_session = await self.persistence_manager.chat_sessions_collection.find_one({
                "chat_id": self.chat_id,
                "enterprise_id": await self.persistence_manager._validate_enterprise_exists(self.enterprise_id)
            })
            
            if not chat_session:
                logger.error(f"❌ TOKEN DB UPDATE: Chat session not found for {self.chat_id}")
                return
            
            # Create mapping of session messages by message content and sender for matching
            db_messages = chat_session.get("messages", [])
            updated_messages = []
            
            for db_msg in db_messages:
                # Find matching message in our centralized history
                matching_msg = None
                for hist_msg in self.agent_history:
                    if (hist_msg["content"] == db_msg.get("content", "") and 
                        hist_msg["sender"] == db_msg.get("sender", "")):
                        matching_msg = hist_msg
                        break
                
                if matching_msg and matching_msg["tokens_used"] > 0:
                    # Update database message with token data from centralized history
                    db_msg["tokens_used"] = matching_msg["tokens_used"]
                    db_msg["cost"] = matching_msg["cost"]
                    db_msg["token_update_timestamp"] = matching_msg["token_update_timestamp"]
                    db_msg["session_id"] = self.session_id
                
                updated_messages.append(db_msg)
            
            # Update entire messages array in database
            await self.persistence_manager.chat_sessions_collection.update_one(
                {"chat_id": self.chat_id, "enterprise_id": await self.persistence_manager._validate_enterprise_exists(self.enterprise_id)},
                {
                    "$set": {
                        "messages": updated_messages,
                        "centralized_token_update": True,
                        "total_session_tokens": self.cumulative_tokens,
                        "total_session_cost": self.cumulative_cost,
                        "last_token_update": datetime.utcnow()
                    }
                }
            )
            
            logger.info(f"✅ DB TOKEN UPDATE: Updated database with centralized token data")
            
        except Exception as e:
            logger.error(f"❌ DB TOKEN UPDATE FAILED: {e}")
            raise
    
    def get_message_history(self) -> List[Dict[str, Any]]:
        """Get complete message history from centralized store."""
        return self.agent_history.copy()
    
    def get_session_summary(self) -> Dict[str, Any]:
        """Get session summary including token usage."""
        return {
            "session_id": self.session_id,
            "workflow_name": self.workflow_name,
            "message_count": len(self.agent_history),
            "total_tokens": self.cumulative_tokens,
            "total_cost": self.cumulative_cost,
            "last_speaker": self.last_speaker,
            "chat_id": self.chat_id,
            "enterprise_id": self.enterprise_id
        }


def create_event_driven_message_processor(chat_manager: WorkflowChatManager) -> Dict[str, Any]:
    """
    Create event-driven message processor that uses the centralized chat manager.
    
    Used by event streaming in orchestration_patterns.py for real-time persistence.
    """
    
    async def process_event_message(event_data: Dict[str, Any]) -> None:
        """
        Process AG2 event messages for centralized storage via direct event processing.
        """
        try:
            # Extract message details from event
            sender_name = event_data.get("sender", "Unknown")
            content = event_data.get("content", "")
            ag2_event_type = event_data.get("type", "message")
            
            # Skip empty messages or unknown senders
            if not content or sender_name == "Unknown":
                logger.debug(f"🚫 EVENT SKIP: Empty content or unknown sender: {sender_name}")
                return
            
            logger.debug(f"🎯 EVENT PROCESSOR: Processing {ag2_event_type} from {sender_name}")
            
            try:
                # Log the message for real-time monitoring to AGENT CHAT LOG
                from logs.logging_config import get_chat_logger
                agent_chat_logger = get_chat_logger("agent_messages")
                agent_chat_logger.info(f"AGENT_MESSAGE | Chat: {chat_manager.chat_id} | Agent: {sender_name} | {content}")
                
                # Also log to business logic for debugging
                logger.info(f"📝 AGENT_MESSAGE | {sender_name} | {content[:150]}...")
                
                # Use centralized chat manager for immediate storage
                message_result = await chat_manager.add_message_to_history(
                    sender=sender_name,
                    content=content,
                    role="assistant"
                )
                
                if message_result:
                    logger.info(f"✅ EVENT SUCCESS: Message from {sender_name} processed and stored")
                else:
                    logger.debug(f"🚫 EVENT DUPLICATE: Message from {sender_name} already existed")
                
            except Exception as storage_error:
                logger.error(f"❌ EVENT STORAGE ERROR: Failed to store message from {sender_name}: {storage_error}")
                raise
            
        except Exception as event_error:
            logger.error(f"❌ EVENT PROCESSOR FAILED: {event_error}")
            raise
    
    async def process_event_stream(events) -> None:
        """
        Process a stream of AG2 events for message persistence.
        This is the main entry point for event-driven persistence.
        """
        try:
            async for event in events:
                event_type = getattr(event, 'type', type(event).__name__.replace('Event', '').lower())
                
                if event_type == "text" or event_type == "message":
                    # TextEvent contains actual agent messages - this is what we want to persist
                    agent_name = getattr(event, 'sender', 'Unknown')
                    content = getattr(event, 'content', str(event))
                    
                    logger.debug(f"🎯 EVENT STREAM: Processing TextEvent from '{agent_name}' (content: {len(content)} chars)")
                    
                    await process_event_message({
                        "sender": agent_name,
                        "content": content,
                        "type": "message"
                    })
                    
                elif event_type == "group_chat_run_chat":
                    # GroupChatRunChatEvent indicates turn changes - log but don't persist as message
                    speaker = getattr(event, 'speaker', 'Unknown')
                    logger.debug(f"🔄 EVENT STREAM: Group chat turn for '{speaker}'")
                    
                elif event_type == "input_request":
                    logger.debug(f"🔄 EVENT: Input request received")
                    
                elif event_type == "termination":
                    logger.info(f"🏁 EVENT: Workflow termination received")
                    break
                    
                else:
                    logger.debug(f"🔍 EVENT STREAM: Unhandled event type '{event_type}': {type(event).__name__}")
        except Exception as stream_error:
            logger.error(f"❌ EVENT STREAM ERROR: {stream_error}")
            raise
    
    return {
        "process_event_message": process_event_message,
        "process_event_stream": process_event_stream
    }

# ==================================================================================
# AG2 GROUPCHAT PERSISTENCE EXTENSIONS 
# ==================================================================================
class AG2PersistenceExtensions:
    """
    AG2-specific persistence methods that extend the main PersistenceManager.
    These handle AG2 groupchat resume functionality.
    """
    
    def __init__(self, persistence_manager: PersistenceManager):
        self.pm = persistence_manager
        self.logger = logger
    
    async def save_ag2_groupchat_state(
        self,
        chat_id: str,
        enterprise_id: Union[str, ObjectId],
        groupchat_messages: List[Dict[str, Any]],
        workflow_name: str = "default"
    ) -> bool:
        """Save AG2 groupchat state for resume functionality"""
        try:
            eid = await self.pm._validate_enterprise_exists(enterprise_id)
            
            # Convert messages to AG2 format
            ag2_messages = []
            if groupchat_messages:
                for msg in groupchat_messages:
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
            
            # Update existing chat session with AG2 state
            await self.pm.chat_sessions_collection.update_one(
                {"chat_id": chat_id, "enterprise_id": eid, "workflow_name": workflow_name},
                {
                    "$set": {
                        "ag2_state": {
                            "messages": ag2_messages,
                            "message_count": len(ag2_messages),
                            "can_resume": True,
                            "last_saved": datetime.utcnow()
                        },
                        "last_updated": datetime.utcnow()
                    }
                },
                upsert=True
            )
            
            self.logger.info(f"💾 Saved AG2 groupchat state: {len(ag2_messages)} messages for {chat_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to save AG2 groupchat state: {e}")
            return False

    async def load_ag2_groupchat_state(self, chat_id: str, enterprise_id: Union[str, ObjectId], 
                                      workflow_name: str = "default") -> Optional[Dict[str, Any]]:
        """Load AG2 groupchat state for resume"""
        try:
            eid = await self.pm._validate_enterprise_exists(enterprise_id)
            
            session = await self.pm.chat_sessions_collection.find_one(
                {"chat_id": chat_id, "enterprise_id": eid, "workflow_name": workflow_name}
            )
            
            if session and session.get("ag2_state", {}).get("can_resume", False):
                return session["ag2_state"]
            
            return None
            
        except Exception as e:
            self.logger.error(f"❌ Failed to load AG2 groupchat state: {e}")
            return None

    async def resume_ag2_groupchat(
        self,
        chat_id: str,
        enterprise_id: Union[str, ObjectId],
        workflow_name: str = "default"
    ) -> Tuple[bool, Optional[List[Dict[str, Any]]], Optional[str]]:
        """Resume AG2 groupchat and return messages"""
        try:
            state = await self.load_ag2_groupchat_state(chat_id, enterprise_id, workflow_name)
            if not state:
                return False, None, "No resumable state found"
            
            messages = state.get("messages", [])
            if not messages:
                return False, None, "No messages in state"
            
            self.logger.info(f"✅ AG2 groupchat can be resumed: {len(messages)} messages")
            return True, messages, None
            
        except Exception as e:
            self.logger.error(f"❌ AG2 resume failed: {e}")
            return False, None, f"Resume failed: {str(e)}"

    async def get_ag2_resume_info(
        self,
        chat_id: str,
        enterprise_id: Union[str, ObjectId],
        workflow_name: str = "default"
    ) -> Dict[str, Any]:
        """Get information about whether an AG2 chat can be resumed"""
        try:
            state = await self.load_ag2_groupchat_state(chat_id, enterprise_id, workflow_name)
            
            if not state:
                return {
                    "can_resume": False,
                    "reason": "no_existing_session",
                    "is_new_chat": True,
                    "message_count": 0
                }
            
            message_count = state.get("message_count", 0)
            
            return {
                "can_resume": message_count > 0,
                "message_count": message_count,
                "is_new_chat": message_count == 0,
                "reason": "messages_found" if message_count > 0 else "no_messages",
                "last_saved": state.get("last_saved")
            }
            
        except Exception as e:
            self.logger.error(f"❌ Failed to get AG2 resume info: {e}")
            return {
                "can_resume": False,
                "reason": "error",
                "error": str(e),
                "is_new_chat": True,
                "message_count": 0
            }

    async def process_runtime_event(self, event_data) -> bool:
        """Process AG2 runtime events for real-time persistence and monitoring
        
        Args:
            event_data: Either a Dict[str, Any] (from unified event dispatcher) 
                       or a raw AG2 event object (from direct AG2 event consumers)
        """
        try:
            # Handle both dictionary format (from unified dispatcher) and raw AG2 events
            # Check if it's a real dictionary by looking for 'event_type' key (our unified dispatcher format)
            if hasattr(event_data, 'get') and 'event_type' in event_data:
                # Dictionary format from unified event dispatcher
                event_type = event_data.get("event_type", "unknown")
                agent_name = event_data.get("agent_name", "unknown")
                raw_content = event_data.get("content", "")
                metadata = event_data.get("metadata", {})
                event_id = event_data.get("event_id")
                timestamp = event_data.get("timestamp", datetime.utcnow().isoformat())
                
                # Handle case where content is still an AG2 event object
                if hasattr(raw_content, 'content'):
                    # Content is an AG2 event object, extract its content
                    content = str(getattr(raw_content, 'content', ''))
                elif hasattr(raw_content, 'termination_reason'):
                    content = str(getattr(raw_content, 'termination_reason', ''))
                elif hasattr(raw_content, 'prompt'):
                    content = str(getattr(raw_content, 'prompt', ''))
                else:
                    content = str(raw_content) if raw_content else ""
                
            else:
                # Raw AG2 event object - based on actual AG2 source structure
                # All AG2 events have .type attribute and direct attributes for data
                event_type = getattr(event_data, 'type', type(event_data).__name__.lower().replace('event', ''))
                
                # Extract agent name based on AG2 event structure
                if hasattr(event_data, 'sender'):
                    agent_name = getattr(event_data, 'sender', 'unknown')
                elif hasattr(event_data, 'speaker'):
                    agent_name = getattr(event_data, 'speaker', 'unknown')
                else:
                    agent_name = 'unknown'
                
                # Extract content based on AG2 event structure  
                if hasattr(event_data, 'content'):
                    content = getattr(event_data, 'content', '')
                    # Handle complex content (lists, dicts, etc.)
                    if not isinstance(content, str):
                        content = str(content)
                elif hasattr(event_data, 'termination_reason'):
                    content = getattr(event_data, 'termination_reason', '')
                elif hasattr(event_data, 'prompt'):
                    content = getattr(event_data, 'prompt', '')
                else:
                    content = ''
                
                # Try to extract agent name from debug content if present
                if content and content.startswith("uuid=UUID(") and "speaker=" in content:
                    import re
                    speaker_match = re.search(r"speaker='([^']+)'", content)
                    if speaker_match:
                        agent_name = speaker_match.group(1)
                
                # Build metadata from AG2 event attributes
                metadata = {
                    "event_class": type(event_data).__name__
                }
                
                # Add recipient if available
                if hasattr(event_data, 'recipient'):
                    metadata['recipient'] = getattr(event_data, 'recipient')
                    
                # Get event ID from uuid
                if hasattr(event_data, 'uuid'):
                    event_id = str(getattr(event_data, 'uuid'))
                else:
                    event_id = None
                    
                timestamp = datetime.utcnow().isoformat()
            
            # Extract chat_id from metadata if available
            chat_id = metadata.get("chat_id") if isinstance(metadata, dict) else None
            enterprise_id = metadata.get("enterprise_id", "default") if isinstance(metadata, dict) else "default"
            
            # Log the runtime event for monitoring
            self.logger.debug(f"🔄 Processing AG2 runtime event: {event_type} from {agent_name}")
            
            # FOR MESSAGE EVENTS - LEGACY PERSISTENCE DISABLED 
            # This legacy persistence was creating duplicate messages with incorrect "Generator" sender
            # Real-time streaming persistence (in orchestration_patterns.py) handles message persistence correctly
            if event_type in ["text", "message", "group_chat_run_chat"] and content and agent_name != "unknown":
                # Filter out debug messages and simple continuations
                if (content.startswith("uuid=UUID(") or 
                    content.lower().strip() in ["continue", "next", ""] or
                    len(content.strip()) < 10):
                    # Skip persisting debug/continuation messages
                    self.logger.debug(f"🔍 Skipping debug/continuation message: {content[:50]}...")
                else:
                    # LEGACY PERSISTENCE DISABLED - Real-time streaming handles message persistence
                    # This was causing duplicate messages with sender "Generator" instead of actual agent names
                    self.logger.debug(f"🔄 LEGACY PERSISTENCE DISABLED | Skipping duplicate persistence for {agent_name}: {len(content)} chars")
                    # try:
                    #     if chat_id:  # Only persist if we have chat context
                    #         await self.pm.add_message(
                    #             chat_id=chat_id,
                    #             enterprise_id=enterprise_id,
                    #             sender=agent_name,
                    #             content=content,
                    #             tokens_used=0,  # Tokens will be updated separately
                    #             cost=0.0       # Cost will be updated separately
                    #         )
                    #         self.logger.info(f"💬 Persisted AG2 message from {agent_name}: {len(content)} chars")
                    # except Exception as persist_error:
                    #     self.logger.error(f"❌ Failed to persist AG2 message from {agent_name}: {persist_error}")
            
            # If we have chat context, update real-time tracking
            if chat_id:
                await self.pm.update_real_time_tracking(
                    chat_id=chat_id,
                    enterprise_id=enterprise_id,
                    tracking_data={
                        "runtime_events": {
                            "last_event": {
                                "type": event_type,
                                "agent": agent_name,
                                "timestamp": timestamp,
                                "event_id": event_id
                            }
                        }
                    }
                )
            
            # Store runtime event for analytics if needed
            runtime_event_doc = {
                "event_type": event_type,
                "agent_name": agent_name,
                "content": content[:1000],  # Truncate for storage
                "metadata": metadata,
                "timestamp": datetime.utcnow(),
                "event_id": event_id,
                "chat_id": chat_id,
                "enterprise_id": enterprise_id
            }
            
            # Optional: Store in runtime_events collection for detailed analysis
            # await self.pm.db.runtime_events.insert_one(runtime_event_doc)
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to process runtime event: {e}")
            return False
