# ==============================================================================
# FILE: core/data/persistence_manager.py
# DESCRIPTION: Modular persistence manager based on VE concept creation patterns
# ==============================================================================
import logging
from typing import Dict, List, Optional, Any, Union, Tuple
from datetime import datetime
from bson.objectid import ObjectId
from bson.errors import InvalidId

from core.core_config import get_mongo_client

logger = logging.getLogger(__name__)

class InvalidEnterpriseIdError(ValueError):
    """Raised when an invalid enterprise ID is provided"""
    pass

class PersistenceManager:
    """
    Modular persistence manager based on VE concept creation patterns.
    
    Clean, workflow-agnostic persistence with simple schema:
    - Workflow status tracking
    - Conversation message storage  
    - Token usage management
    - Resume and lifecycle handling
    """

    def __init__(self):
        self.client = get_mongo_client()
        self.db1 = self.client['MozaiksDB']
        self.db2 = self.client['autogen_ai_agents']
        self.enterprises_collection = self.db1['Enterprises']
        self.concepts_collection = self.db2['Concepts']
        self.workflows_collection = self.db2['Workflows']
        self.usage_tracking_collection = self.db2['UsageTracking']
        # Token management collections
        self.user_tokens_collection = self.db2['UserTokens']
        self.token_usage_collection = self.db2['TokenUsage']
        # Performance analytics collections
        self.performance_metrics_collection = self.db2['PerformanceMetrics']
        self.workflow_averages_collection = self.db2['WorkflowAverages']
        self.workflow_performance_collection = self.db2['WorkflowPerformance']
    

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
    # WORKFLOW STATUS & CHAT MANAGEMENT (VE Style)
    # ==================================================================================

    async def update_workflow_status(self, chat_id: str, enterprise_id: Union[str, ObjectId], 
                                   status: int, workflow_name: str = "default") -> bool:
        """Update workflow status (replaces update_CreationChatStatus)"""
        try:
            eid = await self._validate_enterprise_exists(enterprise_id)
            
            await self.workflows_collection.update_one(
                {"chat_id": chat_id, "enterprise_id": eid},
                {
                    "$set": {
                        f"{workflow_name}_status": status,
                        "last_updated": datetime.utcnow()
                    }
                },
                upsert=True
            )
            
            logger.info(f"📊 Updated {workflow_name} status to {status} for chat {chat_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to update workflow status: {e}")
            return False

    async def update_conversation(self, chat_id: str, enterprise_id: Union[str, ObjectId],
                                sender: str, content: str, workflow_name: str = "default") -> bool:
        """Update conversation with new message (replaces update_ConceptCreationConvo)"""
        try:
            eid = await self._validate_enterprise_exists(enterprise_id)
            
            message = {
                "sender": sender,
                "content": content,
                "timestamp": datetime.utcnow(),
                "message_id": str(ObjectId())
            }
            
            # Extract any structured data from agent messages
            extracted_data = await self._extract_agent_data(sender, content)
            if extracted_data:
                message.update(extracted_data)
            
            await self.workflows_collection.update_one(
                {"chat_id": chat_id, "enterprise_id": eid},
                {
                    "$push": {f"{workflow_name}_conversation": message},
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
        """Save current chat state (simplified from complex AG2 state)"""
        try:
            eid = await self._validate_enterprise_exists(enterprise_id)
            
            # Simple state structure
            chat_state = {
                "agents": state_data.get("agents", []),
                "current_speaker": state_data.get("current_speaker"),
                "round_count": state_data.get("round_count", 0),
                "iteration_count": state_data.get("iteration_count", 0),
                "session_id": state_data.get("session_id"),
                "can_resume": True,
                "saved_at": datetime.utcnow()
            }
            
            await self.workflows_collection.update_one(
                {"chat_id": chat_id, "enterprise_id": eid},
                {
                    "$set": {
                        f"{workflow_name}_state": chat_state,
                        "last_updated": datetime.utcnow()
                    }
                },
                upsert=True
            )
            
            logger.info(f"💾 Saved chat state for {workflow_name} workflow")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to save chat state: {e}")
            return False

    async def get_workflow_status(self, chat_id: str, enterprise_id: Union[str, ObjectId],
                                workflow_name: str = "default") -> Optional[int]:
        """Get workflow status (replaces get_creation_chat_status)"""
        try:
            eid = await self._validate_enterprise_exists(enterprise_id)
            
            workflow = await self.workflows_collection.find_one(
                {"chat_id": chat_id, "enterprise_id": eid},
                {f"{workflow_name}_status": 1}
            )
            
            if workflow:
                return workflow.get(f"{workflow_name}_status", 0)
            
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
            
            await self.workflows_collection.update_one(
                {"chat_id": chat_id, "enterprise_id": eid},
                {
                    "$set": {
                        f"{workflow_name}_status": final_status,
                        "finalized_at": datetime.utcnow(),
                        "is_complete": True,
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
            
            await self.workflows_collection.update_one(
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
            
            workflow = await self.workflows_collection.find_one(
                {"chat_id": chat_id, "enterprise_id": eid},
                {f"{workflow_name}_conversation": 1}
            )
            
            if not workflow:
                return []
            
            conversation = workflow.get(f"{workflow_name}_conversation", [])
            
            if not include_last and conversation:
                conversation = conversation[:-1]
            
            # Format for frontend consumption
            formatted_history = []
            for msg in conversation:
                formatted_history.append({
                    "sender": msg.get("sender", "unknown"),
                    "content": msg.get("content", ""),
                    "timestamp": msg.get("timestamp"),
                    "message_id": msg.get("message_id")
                })
            
            logger.info(f"📜 Retrieved {len(formatted_history)} messages from history")
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
            
            workflow = await self.workflows_collection.find_one(
                {"chat_id": chat_id, "enterprise_id": eid},
                {f"{workflow_name}_state": 1, f"{workflow_name}_status": 1, "is_complete": 1}
            )
            
            if not workflow:
                return False
            
            # VE pattern: Check status for resume logic (0 = can resume, 1+ = completed)
            status = workflow.get(f"{workflow_name}_status", 0)
            state = workflow.get(f"{workflow_name}_state", {})
            is_complete = workflow.get("is_complete", False)
            
            # Can resume if status is 0 (in progress) and not marked complete
            # This mimics VE's CreationChatStatus logic
            can_resume = (status == 0 and not is_complete and state.get("can_resume", False))
            
            logger.info(f"🔄 Resume check - Status: {status}, Complete: {is_complete}, Can Resume: {can_resume}")
            return can_resume
            
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
                workflow = await self.workflows_collection.find_one(
                    {"chat_id": chat_id, "enterprise_id": eid},
                    {f"{workflow_name}_status": 1}
                )
                
                if workflow:
                    status = workflow.get(f"{workflow_name}_status", 0)
                    if status >= 100:  # VE uses 100+ for completion
                        logger.info(f"✅ {workflow_name.title()} workflow already completed with status {status}")
                        return False, {"already_complete": True, "status": status}
                
                return False, None
            
            eid = await self._validate_enterprise_exists(enterprise_id)
            
            workflow = await self.workflows_collection.find_one(
                {"chat_id": chat_id, "enterprise_id": eid}
            )
            
            if not workflow:
                return False, None
            
            # Get workflow-specific conversation history and state (using workflow_name)
            conversation = workflow.get(f"{workflow_name}_conversation", [])
            state = workflow.get(f"{workflow_name}_state", {})
            status = workflow.get(f"{workflow_name}_status", 0)
            
            resume_data = {
                "conversation": conversation,
                "state": state,
                "status": status,
                "workflow_name": workflow_name,  # Include workflow_name in resume data
                "can_resume": True
            }
            
            # Mark as reconnected
            await self.workflows_collection.update_one(
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
    # CONNECTION STATE & TOKEN METHODS (For groupchat_manager compatibility)
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
            
            await self.workflows_collection.update_one(
                {"chat_id": chat_id, "enterprise_id": eid},
                {"$set": update_doc}
            )
            
            logger.info(f"🔗 Connection state updated: {chat_id} → {state} ({transport_type})")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to update connection state: {e}")
            return False


    # ==================================================================================
    # MINIMAL CONVENIENCE METHODS (For shared_app integration only)
    # ==================================================================================

    async def load_chat_state(self, chat_id: str, enterprise_id: Union[str, ObjectId]) -> Optional[Dict[str, Any]]:
        """Load chat state for shared_app compatibility"""
        success, data = await self.resume_chat(chat_id, enterprise_id)
        return data if success else None

    async def create_workflow_for_chat(self, chat_id: str, enterprise_id: Union[str, ObjectId],
                                     concept_id: ObjectId, workflow_name: str,
                                     user_id: Optional[str] = None) -> Optional[ObjectId]:
        """Create new workflow with enhanced persistence structure"""
        try:
            try:
                eid = await self._validate_enterprise_exists(enterprise_id)
            except InvalidEnterpriseIdError:
                logger.warning(f"Enterprise {enterprise_id} not found, creating new ObjectId for tracking")
                eid = self._ensure_object_id(enterprise_id, "enterprise_id")

            workflow_doc = {
                "chat_id": chat_id,
                "enterprise_id": eid,
                "concept_id": concept_id,
                "workflow_name": workflow_name,
                "user_id": user_id,
                "created_at": datetime.utcnow(),
                "last_updated": datetime.utcnow(),
                f"{workflow_name}_state": {
                    "initialized": False,
                    "agents": [],
                    "current_speaker": None,
                    "round_count": 0,
                    "iteration_count": 0,
                    "can_resume": True
                },
                f"{workflow_name}_conversation": [],
                f"{workflow_name}_status": 0,
                "connection_state": "active",
                "is_complete": False
            }

            result = await self.workflows_collection.insert_one(workflow_doc)
            logger.info(f"📝 Created new workflow document with ID: {result.inserted_id}")
            return result.inserted_id

        except Exception as e:
            logger.error(f"❌ Failed to create workflow: {e}")
            return None

    # ==================================================================================
    # CONCEPT MANAGEMENT (NOTE: This is only for Mozaiks)
    # ==================================================================================

    async def find_latest_concept_for_enterprise(self, enterprise_id: Union[str, ObjectId]) -> Optional[Dict[str, Any]]:
        """Find the latest concept for an enterprise"""
        try:
            eid = await self._validate_enterprise_exists(enterprise_id)
            return await self.concepts_collection.find_one(
                {"enterprise_id": str(eid)},
                sort=[("ConceptCode", -1)]
            )
        except Exception as e:
            logger.error(f"❌ Failed to find latest concept: {e}")
            return None

    # ==================================================================================
    # TOKEN MANAGEMENT & ANALYTICS
    # ==================================================================================

    async def get_user_token_data(self, user_id: str, enterprise_id: Union[str, ObjectId]) -> Optional[Dict[str, Any]]:
        """Get user token data for TokenManager integration"""
        try:
            eid = await self._validate_enterprise_exists(enterprise_id)
            
            user_tokens = await self.user_tokens_collection.find_one({
                "user_id": user_id,
                "enterprise_id": eid
            })
            
            if not user_tokens:
                # Create default user token record
                default_data = {
                    "user_id": user_id,
                    "enterprise_id": eid,
                    "free_trial": True,
                    "available_tokens": 0,
                    "available_trial_tokens": 1000,  # Default trial tokens
                    "created_at": datetime.utcnow(),
                    "last_updated": datetime.utcnow(),
                    "trial_started_at": datetime.utcnow()
                }
                
                await self.user_tokens_collection.insert_one(default_data)
                logger.info(f"🆕 Created new user token record for {user_id}")
                return default_data
            
            return user_tokens
            
        except Exception as e:
            logger.error(f"❌ Failed to get user token data: {e}")
            return None

    async def update_user_tokens(self, user_id: str, enterprise_id: Union[str, ObjectId],
                               available_tokens: int, available_trial_tokens: int,
                               free_trial: Optional[bool] = None) -> bool:
        """Update user token balances"""
        try:
            eid = await self._validate_enterprise_exists(enterprise_id)
            
            update_doc = {
                "available_tokens": available_tokens,
                "available_trial_tokens": available_trial_tokens,
                "last_updated": datetime.utcnow()
            }
            
            if free_trial is not None:
                update_doc["free_trial"] = free_trial
            
            result = await self.user_tokens_collection.update_one(
                {"user_id": user_id, "enterprise_id": eid},
                {"$set": update_doc},
                upsert=True
            )
            
            logger.info(f"💰 Updated tokens for {user_id}: {available_tokens} regular, {available_trial_tokens} trial")
            return result.acknowledged
            
        except Exception as e:
            logger.error(f"❌ Failed to update user tokens: {e}")
            return False

    async def log_token_usage(self, user_id: str, enterprise_id: Union[str, ObjectId],
                            chat_id: str, workflow_name: str, session_id: str,
                            tokens_used: int, trial_tokens_used: int = 0,
                            token_type: str = "gpt-4", cost_usd: float = 0.0,
                            agent_breakdown: Optional[Dict[str, int]] = None) -> bool:
        """Log token usage for analytics and tracking"""
        try:
            eid = await self._validate_enterprise_exists(enterprise_id)
            
            usage_record = {
                "user_id": user_id,
                "enterprise_id": eid,
                "chat_id": chat_id,
                "workflow_name": workflow_name,
                "session_id": session_id,
                "tokens_used": tokens_used,
                "trial_tokens_used": trial_tokens_used,
                "token_type": token_type,
                "cost_usd": cost_usd,
                "timestamp": datetime.utcnow(),
                "agent_breakdown": agent_breakdown or {}
            }
            
            await self.token_usage_collection.insert_one(usage_record)
            logger.info(f"📊 Logged token usage: {tokens_used} tokens for {workflow_name}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to log token usage: {e}")
            return False

    # ==================================================================================
    # PERFORMANCE ANALYTICS & TRACKING
    # ==================================================================================

    async def log_performance_metrics(self, workflow_name: str, enterprise_id: Union[str, ObjectId],
                                    user_id: str, chat_id: str, session_id: str,
                                    agent_metrics: Dict[str, Any],
                                    session_metrics: Dict[str, Any]) -> bool:
        """Log detailed performance metrics for workflow analysis"""
        try:
            eid = await self._validate_enterprise_exists(enterprise_id)
            
            performance_doc = {
                "workflow_name": workflow_name,
                "enterprise_id": eid,
                "user_id": user_id,
                "chat_id": chat_id,
                "session_id": session_id,
                "timestamp": datetime.utcnow(),
                
                # Agent-level metrics
                "agent_metrics": agent_metrics,  # Contains per-agent response times, message counts, etc.
                
                # Session-level metrics
                "session_duration_seconds": session_metrics.get("session_duration_seconds", 0),
                "total_messages": session_metrics.get("total_messages", 0),
                "avg_agent_response_time_ms": session_metrics.get("avg_agent_response_time_ms", 0),
                "avg_token_calc_time_ms": session_metrics.get("avg_token_calc_time_ms", 0),
                "total_tokens": session_metrics.get("total_tokens", 0),
                "total_cost": session_metrics.get("total_cost", 0.0),
                
                # Performance indicators
                "agents_used": list(agent_metrics.keys()) if agent_metrics else [],
                "agent_count": len(agent_metrics) if agent_metrics else 0
            }
            
            await self.performance_metrics_collection.insert_one(performance_doc)
            
            # Update workflow averages asynchronously
            await self._update_workflow_averages(workflow_name, enterprise_id, performance_doc)
            
            logger.info(f"📊 Logged performance metrics for workflow: {workflow_name} | Session: {session_id[:8]}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to log performance metrics: {e}")
            return False

    async def _update_workflow_averages(self, workflow_name: str, enterprise_id: Union[str, ObjectId],
                                      performance_doc: Dict[str, Any]) -> None:
        """Update running averages for workflow performance"""
        try:
            eid = await self._validate_enterprise_exists(enterprise_id)
            
            # Check if averages document exists
            averages_doc = await self.workflow_averages_collection.find_one({
                "workflow_name": workflow_name,
                "enterprise_id": eid
            })
            
            if not averages_doc:
                # Create new averages document
                new_doc = {
                    "workflow_name": workflow_name,
                    "enterprise_id": eid,
                    "created_at": datetime.utcnow(),
                    "last_updated": datetime.utcnow(),
                    "session_count": 1,
                    "total_users": [performance_doc["user_id"]],  # Use list instead of set
                    
                    # Running averages
                    "avg_session_duration_seconds": performance_doc.get("session_duration_seconds", 0),
                    "avg_messages_per_session": performance_doc.get("total_messages", 0),
                    "avg_agent_response_time_ms": performance_doc.get("avg_agent_response_time_ms", 0),
                    "avg_token_calc_time_ms": performance_doc.get("avg_token_calc_time_ms", 0),
                    "avg_tokens_per_session": performance_doc.get("total_tokens", 0),
                    "avg_cost_per_session": performance_doc.get("total_cost", 0.0),
                    "avg_agents_per_session": performance_doc.get("agent_count", 0),
                    
                    # Agent-specific averages
                    "agent_averages": {}
                }
                
                # Add agent-specific metrics
                for agent_name, agent_data in (performance_doc.get("agent_metrics", {})).items():
                    new_doc["agent_averages"][agent_name] = {
                        "appearances": 1,
                        "avg_response_time_ms": agent_data.get("avg_response_time_ms", 0),
                        "avg_messages_per_session": agent_data.get("message_count", 0),
                        "avg_tokens_per_session": agent_data.get("total_tokens", 0)
                    }
                
                await self.workflow_averages_collection.insert_one(new_doc)
                
            else:
                # Update existing averages using incremental averaging
                session_count = averages_doc["session_count"] + 1
                
                update_doc = {
                    "$set": {
                        "last_updated": datetime.utcnow(),
                        "session_count": session_count,
                        
                        # Update running averages
                        "avg_session_duration_seconds": self._update_running_average(
                            averages_doc.get("avg_session_duration_seconds", 0),
                            performance_doc.get("session_duration_seconds", 0),
                            session_count
                        ),
                        "avg_messages_per_session": self._update_running_average(
                            averages_doc.get("avg_messages_per_session", 0),
                            performance_doc.get("total_messages", 0),
                            session_count
                        ),
                        "avg_agent_response_time_ms": self._update_running_average(
                            averages_doc.get("avg_agent_response_time_ms", 0),
                            performance_doc.get("avg_agent_response_time_ms", 0),
                            session_count
                        ),
                        "avg_token_calc_time_ms": self._update_running_average(
                            averages_doc.get("avg_token_calc_time_ms", 0),
                            performance_doc.get("avg_token_calc_time_ms", 0),
                            session_count
                        ),
                        "avg_tokens_per_session": self._update_running_average(
                            averages_doc.get("avg_tokens_per_session", 0),
                            performance_doc.get("total_tokens", 0),
                            session_count
                        ),
                        "avg_cost_per_session": self._update_running_average(
                            averages_doc.get("avg_cost_per_session", 0),
                            performance_doc.get("total_cost", 0.0),
                            session_count
                        ),
                        "avg_agents_per_session": self._update_running_average(
                            averages_doc.get("avg_agents_per_session", 0),
                            performance_doc.get("agent_count", 0),
                            session_count
                        )
                    },
                    "$addToSet": {
                        "total_users": performance_doc["user_id"]
                    }
                }
                
                # Update agent-specific averages
                agent_averages = averages_doc.get("agent_averages", {})
                for agent_name, agent_data in (performance_doc.get("agent_metrics", {})).items():
                    if agent_name in agent_averages:
                        # Update existing agent averages
                        agent_appearances = agent_averages[agent_name]["appearances"] + 1
                        agent_averages[agent_name] = {
                            "appearances": agent_appearances,
                            "avg_response_time_ms": self._update_running_average(
                                agent_averages[agent_name].get("avg_response_time_ms", 0),
                                agent_data.get("avg_response_time_ms", 0),
                                agent_appearances
                            ),
                            "avg_messages_per_session": self._update_running_average(
                                agent_averages[agent_name].get("avg_messages_per_session", 0),
                                agent_data.get("message_count", 0),
                                agent_appearances
                            ),
                            "avg_tokens_per_session": self._update_running_average(
                                agent_averages[agent_name].get("avg_tokens_per_session", 0),
                                agent_data.get("total_tokens", 0),
                                agent_appearances
                            )
                        }
                    else:
                        # New agent
                        agent_averages[agent_name] = {
                            "appearances": 1,
                            "avg_response_time_ms": agent_data.get("avg_response_time_ms", 0),
                            "avg_messages_per_session": agent_data.get("message_count", 0),
                            "avg_tokens_per_session": agent_data.get("total_tokens", 0)
                        }
                
                update_doc["$set"]["agent_averages"] = agent_averages
                
                await self.workflow_averages_collection.update_one(
                    {"workflow_name": workflow_name, "enterprise_id": eid},
                    update_doc
                )
                
        except Exception as e:
            logger.error(f"❌ Failed to update workflow averages: {e}")

    def _update_running_average(self, current_avg: float, new_value: float, count: int) -> float:
        """Update running average with new value"""
        if count <= 1:
            return new_value
        return ((current_avg * (count - 1)) + new_value) / count

    async def get_workflow_performance_averages(self, workflow_name: str,
                                              enterprise_id: Optional[Union[str, ObjectId]] = None) -> Dict[str, Any]:
        """Get comprehensive performance averages for a workflow"""
        try:
            query: Dict[str, Any] = {"workflow_name": workflow_name}
            if enterprise_id:
                eid = await self._validate_enterprise_exists(enterprise_id)
                query["enterprise_id"] = eid
                
            averages_doc = await self.workflow_averages_collection.find_one(query)
            
            if not averages_doc:
                return {
                    "workflow_name": workflow_name,
                    "enterprise_id": str(enterprise_id) if enterprise_id else None,
                    "session_count": 0,
                    "message": "No performance data available"
                }
            
            # Format response
            result = {
                "workflow_name": workflow_name,
                "enterprise_id": str(averages_doc["enterprise_id"]),
                "session_count": averages_doc["session_count"],
                "unique_users": len(averages_doc.get("total_users", [])),
                "created_at": averages_doc["created_at"].isoformat(),
                "last_updated": averages_doc["last_updated"].isoformat(),
                
                # Overall averages
                "performance_averages": {
                    "avg_session_duration_seconds": round(averages_doc.get("avg_session_duration_seconds", 0), 2),
                    "avg_messages_per_session": round(averages_doc.get("avg_messages_per_session", 0), 1),
                    "avg_agent_response_time_ms": round(averages_doc.get("avg_agent_response_time_ms", 0), 2),
                    "avg_token_calc_time_ms": round(averages_doc.get("avg_token_calc_time_ms", 0), 2),
                    "avg_tokens_per_session": round(averages_doc.get("avg_tokens_per_session", 0), 0),
                    "avg_cost_per_session": round(averages_doc.get("avg_cost_per_session", 0.0), 4),
                    "avg_agents_per_session": round(averages_doc.get("avg_agents_per_session", 0), 1)
                },
                
                # Agent-specific averages
                "agent_averages": averages_doc.get("agent_averages", {})
            }
            
            logger.info(f"📊 Retrieved performance averages for workflow: {workflow_name}")
            return result
            
        except Exception as e:
            logger.error(f"❌ Failed to get workflow performance averages: {e}")
            return {}

    async def get_enterprise_performance_summary(self, enterprise_id: Union[str, ObjectId],
                                               days_back: int = 30) -> List[Dict[str, Any]]:
        """Get performance summary across all workflows for an enterprise"""
        try:
            eid = await self._validate_enterprise_exists(enterprise_id)
            
            # Get all workflow averages for the enterprise
            workflow_averages = await self.workflow_averages_collection.find({
                "enterprise_id": eid
            }).to_list(None)
            
            # Get recent performance data for trend analysis
            from datetime import timedelta
            start_date = datetime.utcnow() - timedelta(days=days_back)
            
            recent_performance = await self.performance_metrics_collection.aggregate([
                {"$match": {
                    "enterprise_id": eid,
                    "timestamp": {"$gte": start_date}
                }},
                {"$group": {
                    "_id": "$workflow_name",
                    "recent_sessions": {"$sum": 1},
                    "recent_avg_response_time": {"$avg": "$avg_agent_response_time_ms"},
                    "recent_avg_tokens": {"$avg": "$total_tokens"},
                    "recent_avg_cost": {"$avg": "$total_cost"}
                }}
            ]).to_list(None)
            
            # Combine data
            summary = []
            for avg_doc in workflow_averages:
                workflow_summary = {
                    "workflow_name": avg_doc["workflow_name"],
                    "total_sessions": avg_doc["session_count"],
                    "unique_users": len(avg_doc.get("total_users", [])),
                    "last_updated": avg_doc["last_updated"].isoformat(),
                    
                    # Overall averages
                    "overall_averages": {
                        "avg_session_duration_seconds": round(avg_doc.get("avg_session_duration_seconds", 0), 2),
                        "avg_agent_response_time_ms": round(avg_doc.get("avg_agent_response_time_ms", 0), 2),
                        "avg_tokens_per_session": round(avg_doc.get("avg_tokens_per_session", 0), 0),
                        "avg_cost_per_session": round(avg_doc.get("avg_cost_per_session", 0.0), 4)
                    },
                    
                    # Recent trends
                    "recent_trends": {}
                }
                
                # Add recent trend data if available
                for recent in recent_performance:
                    if recent["_id"] == avg_doc["workflow_name"]:
                        workflow_summary["recent_trends"] = {
                            "recent_sessions": recent["recent_sessions"],
                            "recent_avg_response_time": round(recent.get("recent_avg_response_time", 0), 2),
                            "recent_avg_tokens": round(recent.get("recent_avg_tokens", 0), 0),
                            "recent_avg_cost": round(recent.get("recent_avg_cost", 0.0), 4)
                        }
                        break
                
                summary.append(workflow_summary)
            
            # Sort by session count (most active first)
            summary.sort(key=lambda x: x["total_sessions"], reverse=True)
            
            logger.info(f"📈 Retrieved enterprise performance summary for {len(summary)} workflows")
            return summary
            
        except Exception as e:
            logger.error(f"❌ Failed to get enterprise performance summary: {e}")
            return []

    # ==================================================================================
    # ANALYTICS QUERIES
    # ==================================================================================

    async def get_workflow_analytics(self, workflow_name: str, 
                                   enterprise_id: Optional[Union[str, ObjectId]] = None,
                                   days_back: int = 30) -> Dict[str, Any]:
        """Get analytics for a specific workflow"""
        try:
            match_filter: Dict[str, Any] = {"workflow_name": workflow_name}
            
            if enterprise_id:
                eid = await self._validate_enterprise_exists(enterprise_id)
                match_filter["enterprise_id"] = eid
            
            # Add time filter
            from datetime import timedelta
            start_date = datetime.utcnow() - timedelta(days=days_back)
            match_filter["timestamp"] = {"$gte": start_date}
            
            pipeline = [
                {"$match": match_filter},
                {"$group": {
                    "_id": "$workflow_name",
                    "total_tokens": {"$sum": "$tokens_used"},
                    "total_trial_tokens": {"$sum": "$trial_tokens_used"},
                    "session_count": {"$sum": 1},
                    "avg_tokens_per_session": {"$avg": "$tokens_used"},
                    "total_cost": {"$sum": "$cost_usd"},
                    "unique_users": {"$addToSet": "$user_id"}
                }},
                {"$addFields": {
                    "unique_user_count": {"$size": "$unique_users"}
                }}
            ]
            
            result = await self.token_usage_collection.aggregate(pipeline).to_list(1)
            
            if result:
                analytics = result[0]
                analytics["unique_users"] = len(analytics.get("unique_users", []))
                return analytics
            
            return {
                "workflow_name": workflow_name,
                "total_tokens": 0,
                "session_count": 0,
                "avg_tokens_per_session": 0,
                "unique_user_count": 0
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to get workflow analytics: {e}")
            return {}

    async def get_enterprise_usage_summary(self, enterprise_id: Union[str, ObjectId],
                                         days_back: int = 30) -> List[Dict[str, Any]]:
        """Get usage summary by workflow for an enterprise"""
        try:
            eid = await self._validate_enterprise_exists(enterprise_id)
            
            from datetime import timedelta
            start_date = datetime.utcnow() - timedelta(days=days_back)
            
            pipeline = [
                {"$match": {
                    "enterprise_id": eid,
                    "timestamp": {"$gte": start_date}
                }},
                {"$group": {
                    "_id": "$workflow_name",
                    "total_tokens": {"$sum": "$tokens_used"},
                    "total_cost": {"$sum": "$cost_usd"},
                    "session_count": {"$sum": 1},
                    "unique_users": {"$addToSet": "$user_id"}
                }},
                {"$addFields": {
                    "unique_user_count": {"$size": "$unique_users"}
                }},
                {"$sort": {"total_tokens": -1}}
            ]
            
            results = await self.token_usage_collection.aggregate(pipeline).to_list(None)
            
            # Clean up results
            for result in results:
                result["workflow_name"] = result["_id"]
                del result["_id"]
                del result["unique_users"]  # Remove the array, keep count
            
            logger.info(f"📈 Retrieved usage summary for enterprise {enterprise_id}")
            return results
            
        except Exception as e:
            logger.error(f"❌ Failed to get enterprise usage summary: {e}")
            return []

    async def get_user_usage_history(self, user_id: str, enterprise_id: Union[str, ObjectId],
                                   limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent usage history for a user"""
        try:
            eid = await self._validate_enterprise_exists(enterprise_id)
            
            history = await self.token_usage_collection.find(
                {"user_id": user_id, "enterprise_id": eid},
                {"_id": 0}  # Exclude MongoDB ObjectId
            ).sort("timestamp", -1).limit(limit).to_list(limit)
            
            logger.info(f"📜 Retrieved {len(history)} usage records for user {user_id}")
            return history
            
        except Exception as e:
            logger.error(f"❌ Failed to get user usage history: {e}")
            return []

    # ========================================================================
    # WORKFLOW PERFORMANCE ANALYTICS METHODS
    # ========================================================================

    async def log_workflow_performance(self, performance_data: Dict[str, Any]) -> bool:
        """Log workflow performance data for averaging and analytics."""
        try:
            # Add timestamp if not present
            if "timestamp" not in performance_data:
                performance_data["timestamp"] = datetime.utcnow()
            
            # Validate enterprise exists
            enterprise_id = performance_data.get("enterprise_id")
            if enterprise_id:
                await self._validate_enterprise_exists(enterprise_id)
            
            # Store in workflow performance collection
            result = await self.workflow_performance_collection.insert_one(performance_data)
            
            logger.info(f"📊 Logged workflow performance for {performance_data.get('workflow_name', 'unknown')}")
            return bool(result.inserted_id)
            
        except Exception as e:
            logger.error(f"❌ Failed to log workflow performance: {e}")
            return False

    async def get_workflow_averages(self, workflow_name: str, enterprise_id: Union[str, ObjectId],
                                  days_back: int = 30) -> Dict[str, Any]:
        """Get workflow performance averages across all users and sessions."""
        try:
            eid = await self._validate_enterprise_exists(enterprise_id)
            
            from datetime import timedelta
            start_date = datetime.utcnow() - timedelta(days=days_back)
            
            if not hasattr(self, 'workflow_performance_collection'):
                self.workflow_performance_collection = self.db2["WorkflowPerformance"]
            
            # Aggregation pipeline to calculate chat-level totals then averages
            pipeline = [
                {
                    "$match": {
                        "workflow_name": workflow_name,
                        "enterprise_id": eid,
                        "timestamp": {"$gte": start_date}
                    }
                },
                {
                    # First group by chat_id to get totals per conversation
                    "$group": {
                        "_id": "$chat_id",
                        "user_id": {"$first": "$user_id"},
                        "chat_total_duration": {"$sum": "$session_duration_seconds"},
                        "chat_avg_response_time": {"$avg": "$avg_agent_response_time_ms"},
                        "chat_total_tokens": {"$sum": "$total_tokens"},
                        "chat_total_cost": {"$sum": "$total_cost"},
                        "chat_total_messages": {"$sum": "$total_messages"},
                        "chat_max_agents": {"$max": "$agent_count"},
                        "session_count": {"$sum": 1}
                    }
                },
                {
                    # Then calculate averages across all chats
                    "$group": {
                        "_id": None,
                        "avg_chat_duration": {"$avg": "$chat_total_duration"},
                        "avg_response_time": {"$avg": "$chat_avg_response_time"},
                        "avg_tokens_per_chat": {"$avg": "$chat_total_tokens"},
                        "avg_cost_per_chat": {"$avg": "$chat_total_cost"},
                        "avg_messages_per_chat": {"$avg": "$chat_total_messages"},
                        "avg_agents_per_chat": {"$avg": "$chat_max_agents"},
                        "total_chats": {"$sum": 1},
                        "total_sessions": {"$sum": "$session_count"},
                        "unique_users": {"$addToSet": "$user_id"},
                        "total_tokens_all_chats": {"$sum": "$chat_total_tokens"},
                        "total_cost_all_chats": {"$sum": "$chat_total_cost"}
                    }
                },
                {
                    "$project": {
                        "_id": 0,
                        "workflow_name": {"$literal": workflow_name},
                        "enterprise_id": {"$literal": str(eid)},
                        "days_analyzed": {"$literal": days_back},
                        "avg_chat_duration_seconds": {"$round": ["$avg_chat_duration", 2]},
                        "avg_response_time_ms": {"$round": ["$avg_response_time", 2]},
                        "avg_tokens_per_chat": {"$round": ["$avg_tokens_per_chat", 0]},
                        "avg_cost_per_chat": {"$round": ["$avg_cost_per_chat", 4]},
                        "avg_messages_per_chat": {"$round": ["$avg_messages_per_chat", 1]},
                        "avg_agents_per_chat": {"$round": ["$avg_agents_per_chat", 1]},
                        "total_chats": "$total_chats",
                        "total_sessions": "$total_sessions",
                        "unique_user_count": {"$size": "$unique_users"},
                        "total_tokens_all_chats": "$total_tokens_all_chats",
                        "total_cost_all_chats": {"$round": ["$total_cost_all_chats", 4]},
                        "analysis_period": {
                            "$concat": [
                                "Last ", 
                                {"$toString": days_back}, 
                                " days"
                            ]
                        }
                    }
                }
            ]
            
            result = await self.performance_metrics_collection.aggregate(pipeline).to_list(1)
            
            if result:
                averages = result[0]
                logger.info(f"📊 Retrieved workflow averages for {workflow_name}: {averages['total_sessions']} sessions")
                return averages
            else:
                # Return empty averages if no data
                return {
                    "workflow_name": workflow_name,
                    "enterprise_id": str(eid),
                    "days_analyzed": days_back,
                    "avg_chat_duration_seconds": 0,
                    "avg_response_time_ms": 0,
                    "avg_tokens_per_chat": 0,
                    "avg_cost_per_chat": 0,
                    "avg_messages_per_chat": 0,
                    "avg_agents_per_chat": 0,
                    "total_chats": 0,
                    "total_sessions": 0,
                    "unique_user_count": 0,
                    "total_tokens_all_chats": 0,
                    "total_cost_all_chats": 0,
                    "analysis_period": f"Last {days_back} days"
                }
                
        except Exception as e:
            logger.error(f"❌ Failed to get workflow averages: {e}")
            return {}

    async def get_agent_performance_averages(self, workflow_name: str, enterprise_id: Union[str, ObjectId],
                                           days_back: int = 30) -> Dict[str, Dict[str, Any]]:
        """Get agent-specific performance averages for a workflow."""
        try:
            eid = await self._validate_enterprise_exists(enterprise_id)
            
            from datetime import timedelta
            start_date = datetime.utcnow() - timedelta(days=days_back)
            
            if not hasattr(self, 'workflow_performance_collection'):
                self.workflow_performance_collection = self.db2["WorkflowPerformance"]
            
            # Aggregation pipeline for agent-specific averages
            pipeline = [
                {
                    "$match": {
                        "workflow_name": workflow_name,
                        "enterprise_id": eid,
                        "timestamp": {"$gte": start_date}
                    }
                },
                {
                    "$unwind": {
                        "path": "$agent_performance",
                        "preserveNullAndEmptyArrays": False
                    }
                },
                {
                    "$group": {
                        "_id": "$agent_performance.k",  # Agent name
                        "avg_response_time": {
                            "$avg": "$agent_performance.v.avg_response_time_ms"
                        },
                        "avg_message_count": {
                            "$avg": "$agent_performance.v.message_count"
                        },
                        "avg_content_length": {
                            "$avg": "$agent_performance.v.avg_content_length"
                        },
                        "session_count": {"$sum": 1},
                        "total_messages": {
                            "$sum": "$agent_performance.v.message_count"
                        }
                    }
                },
                {
                    "$project": {
                        "_id": 0,
                        "agent_name": "$_id",
                        "avg_response_time_ms": {"$round": ["$avg_response_time", 2]},
                        "avg_messages_per_session": {"$round": ["$avg_message_count", 1]},
                        "avg_content_length": {"$round": ["$avg_content_length", 0]},
                        "sessions_participated": "$session_count",
                        "total_messages": "$total_messages"
                    }
                }
            ]
            
            results = await self.workflow_performance_collection.aggregate(pipeline).to_list(100)
            
            # Convert to dictionary format
            agent_averages = {}
            for result in results:
                agent_name = result["agent_name"]
                agent_averages[agent_name] = {
                    "avg_response_time_ms": result["avg_response_time_ms"],
                    "avg_messages_per_session": result["avg_messages_per_session"],
                    "avg_content_length": result["avg_content_length"],
                    "sessions_participated": result["sessions_participated"],
                    "total_messages": result["total_messages"]
                }
            
            logger.info(f"📊 Retrieved agent averages for {workflow_name}: {len(agent_averages)} agents")
            return agent_averages
            
        except Exception as e:
            logger.error(f"❌ Failed to get agent performance averages: {e}")
            return {}