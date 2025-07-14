# ==============================================================================
# FILE: db_manager.py  
# DESCRIPTION: Enhanced MongoDB manager with token tracking and persistence
# ==============================================================================
import logging
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
from bson.objectid import ObjectId
from bson.errors import InvalidId

# TODO: Integrate Tokens API
# from core.core_config import TOKENS_API_URL
# import httpx

from core.core_config import get_mongo_client

logger = logging.getLogger(__name__)

class InvalidEnterpriseIdError(ValueError):
    """Raised when an invalid enterprise ID is provided"""
    pass

class MongoDBWorkflowManager:
    """Production MongoDB workflow manager with comprehensive persistence"""

    def __init__(self):
        self.client = get_mongo_client()
        self.db1 = self.client['MozaiksDB']
        self.db2 = self.client['autogen_ai_agents']
        self.enterprises_collection = self.db1['Enterprises']
        self.concepts_collection = self.db2['Concepts']
        self.workflows_collection = self.db2['Workflows']
        self.usage_tracking_collection = self.db2['UsageTracking']

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

    async def find_latest_concept_for_enterprise(self, enterprise_id: Union[str, ObjectId]) -> Optional[Dict[str, Any]]:
        """Find the latest concept for an enterprise"""
        try:
            enterprise_oid = await self._validate_enterprise_exists(enterprise_id)
            concept = await self.concepts_collection.find_one(
                {"enterprise_id": enterprise_oid},
                sort=[("ConceptCode", -1)]
            )
            if not concept:
                concept = await self.concepts_collection.find_one(
                    {"enterprise_id": enterprise_oid},
                    sort=[("created_at", -1)]
                )
            if concept:
                logger.info(f"Found concept for enterprise {enterprise_id}")
            else:
                logger.warning(f"No concepts for enterprise {enterprise_id}")
            return concept
        except InvalidEnterpriseIdError:
            raise
        except Exception as e:
            logger.error(f"Error finding concept: {e}")
            return None

    async def create_workflow_for_chat(
        self,
        chat_id: str,
        enterprise_id: Union[str, ObjectId],
        concept_id: ObjectId,
        workflow_type: str,
        user_id: Optional[str] = None
    ) -> Optional[ObjectId]:
        """Create new workflow with token tracking"""
        try:
            eid = await self._validate_enterprise_exists(enterprise_id)
            count = await self.workflows_collection.count_documents({"enterprise_id": eid})

            # Primary schema structure (inspired by VE_Concept_Verification.py)
            workflow_doc = {
                "_id": ObjectId(),
                "enterprise_id": eid,
                "concept_id": self._ensure_object_id(concept_id, "concept_id"),
                "user_id": user_id,
                "chat_id": chat_id,
                "workflow_type": workflow_type,
                "status": "active",
                "created_at": datetime.utcnow(),
                "last_updated": datetime.utcnow(),
                "chat_history": [],  # Simple message array (like VE AgentHistory)
                "chat_state": {      # Simple state tracking (like VE VerificationChatState)
                    "session_id": "",
                    "iteration_count": 0,
                    "agent_count": 0,
                    "last_speaker": None,
                    "last_updated": datetime.utcnow()
                },
                "token_usage": {},   # Session-based token tracking (like VE SessionTotals)
                "total_token_usage": {
                    "total_tokens": 0,
                    "total_cost": 0.0,
                    "last_updated": datetime.utcnow().isoformat()
                }
            }

            result = await self.workflows_collection.insert_one(workflow_doc)
            logger.info(f"Created workflow {result.inserted_id}")
            return result.inserted_id

        except InvalidEnterpriseIdError:
            raise
        except Exception as e:
            logger.error(f"Error creating workflow: {e}")
            return None

    async def append_message_to_chat(
        self, 
        chat_id: str, 
        enterprise_id: Union[str, ObjectId], 
        message: Dict[str, Any]
    ) -> bool:
        """Append message to chat history"""
        try:
            eid = self._ensure_object_id(enterprise_id, "enterprise_id")
            
            result = await self.workflows_collection.update_one(
                {"chat_id": chat_id, "enterprise_id": eid},
                {
                    "$push": {"session_state.messages": message},
                    "$set": {"last_updated": datetime.utcnow()}
                }
            )
            
            return result.matched_count > 0
                
        except Exception as e:
            logger.error(f"Error appending message: {e}")
            return False

    async def update_token_usage(
        self,
        chat_id: str,
        enterprise_id: Union[str, ObjectId],
        session_usage: Dict[str, Any],
        business_usage: Dict[str, Any],
        observability_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Update token usage with comprehensive tracking including business and technical data"""
        try:
            eid = self._ensure_object_id(enterprise_id, "enterprise_id")
            
            # Comprehensive usage data
            comprehensive_usage = {
                "business_usage": business_usage,  # Billing and budget data
                "session_usage": session_usage,   # Current turn data
                "observability_data": observability_data or {},  # Technical AG2 data
                "last_updated": datetime.utcnow()
            }
            
            # Update workflow with comprehensive usage
            await self.workflows_collection.update_one(
                {"chat_id": chat_id, "enterprise_id": eid},
                {
                    "$set": {
                        "token_usage": comprehensive_usage,
                        "last_updated": datetime.utcnow()
                    }
                }
            )
            
            # Track usage with enhanced data
            usage_record = {
                "chat_id": chat_id,
                "enterprise_id": eid,
                "timestamp": datetime.utcnow(),
                "session_usage": session_usage,
                "business_usage": business_usage,
                "observability_data": observability_data,
                "record_type": "token_usage_update"
            }
            
            await self.usage_tracking_collection.insert_one(usage_record)
            
            logger.info(f"💰 Enhanced usage updated for chat {chat_id}: {session_usage.get('total_tokens', 0)} tokens")
            return True
            
        except Exception as e:
            logger.error(f"Error updating token usage: {e}")
            return False

    async def update_token_balance(
        self,
        chat_id: str,
        enterprise_id: Union[str, ObjectId],
        token_balance: int
    ) -> bool:
        """Update token balance for a chat"""
        try:
            eid = self._ensure_object_id(enterprise_id, "enterprise_id")

            await self.workflows_collection.update_one(
                {"chat_id": chat_id, "enterprise_id": eid},
                {"$set": {"token_balance": token_balance, "last_updated": datetime.utcnow()}}
            )
            logger.info(f"Token balance updated for chat {chat_id}: {token_balance}")
            return True
        except Exception as e:
            logger.error(f"Error updating token balance: {e}")
            return False

    async def update_budget_fields(
        self,
        chat_id: str,
        enterprise_id: Union[str, ObjectId],
        budget_data: Dict[str, Any]
    ) -> bool:
        """Update budget-related fields for a chat workflow"""
        try:
            eid = self._ensure_object_id(enterprise_id, "enterprise_id")
            
            update_fields = {
                "budget_type": budget_data.get("budget_type"),
                "token_balance": budget_data.get("token_balance", 0),
                "last_updated": datetime.utcnow()
            }
            
            # Add free trial fields if applicable
            if budget_data.get("free_loops_remaining") is not None:
                update_fields["free_loops_remaining"] = budget_data["free_loops_remaining"]
            
            # Add turn limit if specified
            if budget_data.get("turn_limit") is not None:
                update_fields["turn_limit"] = budget_data["turn_limit"]
            
            result = await self.workflows_collection.update_one(
                {"chat_id": chat_id, "enterprise_id": eid},
                {"$set": update_fields}
            )
            
            if result.matched_count > 0:
                logger.info(f"Budget fields updated for chat {chat_id}: {budget_data.get('budget_type')}")
                return True
            else:
                logger.warning(f"No workflow found to update budget for chat_id: {chat_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error updating budget fields: {e}")
            return False

    async def decrement_free_loops(self, chat_id: str, enterprise_id: Union[str, ObjectId]) -> Optional[int]:
        """Atomically decrement free_loops_remaining and return new value"""
        try:
            eid = self._ensure_object_id(enterprise_id, "enterprise_id")
            filter_doc = {"chat_id": chat_id, "enterprise_id": eid, "free_loops_remaining": {"$exists": True}}
            update_doc = {"$inc": {"free_loops_remaining": -1}, "$set": {"last_updated": datetime.utcnow()}}
            
            result = await self.workflows_collection.find_one_and_update(
                filter_doc, update_doc, return_document=True
            )
            
            if result:
                remaining = result.get("free_loops_remaining", 0)
                logger.info(f"Decremented free_loops_remaining → {remaining}")
                return remaining
            return None
            
        except Exception as e:
            logger.error(f"Error decrementing free loops: {e}")
            return None

    async def load_chat_state(self, chat_id: str, enterprise_id: Union[str, ObjectId]) -> Optional[Dict[str, Any]]:
        """Load chat state from database"""
        try:
            eid = self._ensure_object_id(enterprise_id, "enterprise_id")
            workflow = await self.workflows_collection.find_one({"chat_id": chat_id, "enterprise_id": eid})
            return workflow
        except Exception as e:
            logger.error(f"Error loading state: {e}")
            return None

    async def finalize_chat(self, chat_id: str, enterprise_id: Union[str, ObjectId]) -> bool:
        """Mark chat as completed"""
        try:
            eid = self._ensure_object_id(enterprise_id, "enterprise_id")
            result = await self.workflows_collection.update_one(
                {"chat_id": chat_id, "enterprise_id": eid},
                {"$set": {"status": "completed", "completed_at": datetime.utcnow()}}
            )
            return result.matched_count > 0
        except Exception as e:
            logger.error(f"Error finalizing chat: {e}")
            return False

    async def mark_chat_disconnected(self, chat_id: str, enterprise_id: Union[str, ObjectId]) -> bool:
        """Mark chat as disconnected"""
        try:
            eid = self._ensure_object_id(enterprise_id, "enterprise_id")
            await self.workflows_collection.update_one(
                {"chat_id": chat_id, "enterprise_id": eid},
                {
                    "$set": {
                        "status": "disconnected",
                        "disconnected_at": datetime.utcnow(),
                        "last_updated": datetime.utcnow()
                    }
                }
            )
            return True
        except Exception as e:
            logger.error(f"Error marking chat disconnected: {e}")
            return False

    async def mark_chat_reconnected(self, chat_id: str, enterprise_id: Union[str, ObjectId]) -> bool:
        """Mark chat as reconnected after disconnection"""
        try:
            eid = self._ensure_object_id(enterprise_id, "enterprise_id")
            result = await self.workflows_collection.update_one(
                {"chat_id": chat_id, "enterprise_id": eid},
                {
                    "$set": {
                        "status": "active",
                        "reconnected_at": datetime.utcnow(),
                        "last_updated": datetime.utcnow()
                    },
                    "$unset": {"disconnected_at": ""}
                }
            )
            return result.matched_count > 0
        except Exception as e:
            logger.error(f"Error marking chat reconnected: {e}")
            return False

    async def pause_chat(self, chat_id: str, enterprise_id: Union[str, ObjectId], 
                        conversation_state: Dict[str, Any], reason: str = "user_requested") -> bool:
        """Mark chat as paused and save conversation state with detailed metadata"""
        try:
            eid = self._ensure_object_id(enterprise_id, "enterprise_id")
            
            # Prepare pause state with metadata
            pause_state = {
                "status": "paused",
                "paused_at": datetime.utcnow(),
                "pause_reason": reason,
                "last_updated": datetime.utcnow(),
                "conversation_state": conversation_state,
                "pause_metadata": {
                    "message_count": len(conversation_state.get("messages", [])),
                    "last_speaker": conversation_state.get("last_speaker"),
                    "workflow_stage": conversation_state.get("workflow_stage"),
                    "can_resume": True
                }
            }
            
            result = await self.workflows_collection.update_one(
                {"chat_id": chat_id, "enterprise_id": eid},
                {"$set": pause_state}
            )
            
            if result.matched_count > 0:
                logger.info(f"Chat {chat_id} paused successfully with {len(conversation_state.get('messages', []))} messages")
                return True
            else:
                logger.warning(f"No chat found to pause for chat_id: {chat_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error pausing chat: {e}")
            return False

    async def resume_chat(self, chat_id: str, enterprise_id: Union[str, ObjectId]) -> bool:
        """Mark chat as resumed and update timestamps"""
        try:
            eid = self._ensure_object_id(enterprise_id, "enterprise_id")
            
            resume_state = {
                "status": "active",
                "resumed_at": datetime.utcnow(),
                "last_updated": datetime.utcnow(),
                "$unset": {"paused_at": "", "pause_reason": ""}
            }
            
            result = await self.workflows_collection.update_one(
                {"chat_id": chat_id, "enterprise_id": eid},
                {"$set": resume_state["$set"], "$unset": resume_state["$unset"]}
            )
            
            if result.matched_count > 0:
                logger.info(f"Chat {chat_id} resumed successfully")
                return True
            else:
                logger.warning(f"No paused chat found to resume for chat_id: {chat_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error resuming chat: {e}")
            return False

    async def get_chat_pause_status(self, chat_id: str, enterprise_id: Union[str, ObjectId]) -> Optional[Dict[str, Any]]:
        """Get detailed pause status and conversation state for a chat"""
        try:
            eid = self._ensure_object_id(enterprise_id, "enterprise_id")
            workflow = await self.workflows_collection.find_one(
                {"chat_id": chat_id, "enterprise_id": eid},
                {
                    "status": 1, 
                    "paused_at": 1, 
                    "resumed_at": 1,
                    "pause_reason": 1,
                    "pause_metadata": 1,
                    "conversation_state": 1,
                    "last_updated": 1
                }
            )
            
            if workflow:
                return {
                    "is_paused": workflow.get("status") == "paused",
                    "status": workflow.get("status"),
                    "paused_at": workflow.get("paused_at"),
                    "resumed_at": workflow.get("resumed_at"),
                    "pause_reason": workflow.get("pause_reason"),
                    "pause_metadata": workflow.get("pause_metadata", {}),
                    "conversation_state": workflow.get("conversation_state", {}),
                    "last_updated": workflow.get("last_updated")
                }
            return None
            
        except Exception as e:
            logger.error(f"Error getting pause status: {e}")
            return None

    async def save_conversation_snapshot(self, chat_id: str, enterprise_id: Union[str, ObjectId], 
                                       messages: List[Dict[str, Any]], metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Save a conversation snapshot for state restoration"""
        try:
            eid = self._ensure_object_id(enterprise_id, "enterprise_id")
            
            snapshot = {
                "messages": messages,
                "snapshot_taken_at": datetime.utcnow(),
                "message_count": len(messages),
                "metadata": metadata or {}
            }
            
            result = await self.workflows_collection.update_one(
                {"chat_id": chat_id, "enterprise_id": eid},
                {
                    "$set": {
                        "conversation_snapshot": snapshot,
                        "last_updated": datetime.utcnow()
                    }
                }
            )
            
            return result.matched_count > 0
            
        except Exception as e:
            logger.error(f"Error saving conversation snapshot: {e}")
            return False

    async def get_conversation_snapshot(self, chat_id: str, enterprise_id: Union[str, ObjectId]) -> Optional[Dict[str, Any]]:
        """Get the latest conversation snapshot for state restoration"""
        try:
            eid = self._ensure_object_id(enterprise_id, "enterprise_id")
            workflow = await self.workflows_collection.find_one(
                {"chat_id": chat_id, "enterprise_id": eid},
                {"conversation_snapshot": 1}
            )
            
            if workflow and "conversation_snapshot" in workflow:
                return workflow["conversation_snapshot"]
            return None
            
        except Exception as e:
            logger.error(f"Error getting conversation snapshot: {e}")
            return None

    async def save_comprehensive_chat_state(
        self,
        chat_id: str,
        enterprise_id: Union[str, ObjectId],
        message_data: Dict[str, Any],
        business_usage: Optional[Dict[str, Any]] = None,
        observability_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Save comprehensive chat state (deprecated - use save_chat_state instead)"""
        try:
            eid = self._ensure_object_id(enterprise_id, "enterprise_id")
            
            # Create comprehensive state record for historical tracking
            state_record = {
                "chat_id": chat_id,
                "enterprise_id": eid,
                "timestamp": datetime.utcnow(),
                "message_data": message_data,
                "business_usage": business_usage or {},
                "observability_data": observability_data or {},
                "record_type": "comprehensive_chat_state"
            }
            
            # Save to usage tracking for detailed state history
            await self.usage_tracking_collection.insert_one(state_record)
            
            # Update the main workflow record with latest state (no more session_state)
            update_data = {
                "last_message": message_data,
                "last_updated": datetime.utcnow()
            }
            
            if business_usage:
                update_data["business_usage"] = business_usage
            if observability_data:
                update_data["observability_summary"] = observability_data
            
            # Update main workflow record
            await self.workflows_collection.update_one(
                {"chat_id": chat_id, "enterprise_id": eid},
                {"$set": update_data},
                upsert=True
            )
            
            logger.debug(f"💾 Saved comprehensive chat state for {chat_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save comprehensive chat state: {e}")
            return False

    async def save_chat_state(
        self,
        chat_id: str,
        enterprise_id: Union[str, ObjectId],
        sender: str,
        content: str,
        session_id: str,
        agent_count: int = 0,
        iteration_count: int = 0
    ) -> bool:
        """
        Save chat state using our primary schema
        This creates a simple, queryable structure.
        """
        try:
            eid = self._ensure_object_id(enterprise_id, "enterprise_id")
            
            # Create message format (like VE AgentHistory)
            message = {
                "timestamp": datetime.utcnow().isoformat(),
                "sender": sender,
                "content": content,
                "role": "user" if sender in ("user", "user_proxy") else "assistant",
                "name": sender,
            }
            
            # Prepare state update (following VE VerificationChatState pattern)
            state_update = {
                "session_id": session_id,
                "iteration_count": iteration_count,
                "agent_count": agent_count,
                "last_speaker": sender,
                "last_updated": datetime.utcnow()
            }
            
            # Update workflow with primary structure
            await self.workflows_collection.update_one(
                {"chat_id": chat_id, "enterprise_id": eid},
                {
                    "$push": {"chat_history": message},  # Simple message array like VE AgentHistory
                    "$set": {"chat_state": state_update}  # Simple state like VE VerificationChatState
                }
            )
            
            logger.debug(f"💾 Saved chat state for {chat_id} - {sender}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save chat state: {e}")
            return False

    async def save_token_usage(
        self,
        chat_id: str,
        enterprise_id: Union[str, ObjectId],
        session_id: str,
        total_tokens: int,
        prompt_tokens: int,
        completion_tokens: int,
        total_cost: float,
        turn_number: int
    ) -> bool:
        """
        Save token usage using our primary schema (inspired by VE_Concept_Verification.py SessionTotals)
        """
        try:
            eid = self._ensure_object_id(enterprise_id, "enterprise_id")
            
            # Create session usage data (like VE SessionTotals)
            session_usage = {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "total_cost": total_cost,
                "turn_number": turn_number,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            # Update with primary token structure
            await self.workflows_collection.update_one(
                {"chat_id": chat_id, "enterprise_id": eid},
                {
                    "$set": {
                        f"token_usage.session_{session_id}": session_usage,
                        "total_token_usage": {
                            "total_tokens": total_tokens,
                            "total_cost": total_cost,
                            "last_updated": datetime.utcnow().isoformat()
                        }
                    }
                }
            )
            
            logger.debug(f"💰 Saved token usage for {chat_id}: {total_tokens} tokens")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save token usage: {e}")
            return False

    async def close(self):
        """Close database connection"""
        if self.client:
            self.client.close()
            logger.info("MongoDB connection closed")

# Global instance
mongodb_manager = MongoDBWorkflowManager()