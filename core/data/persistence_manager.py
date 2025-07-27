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
    # TOKEN USAGE & COST TRACKING (VE Style)
    # ==================================================================================

    async def calculate_and_update_usage(self, chat_id: str, enterprise_id: Union[str, ObjectId],
                                       session_id: str, agent_summary: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate token usage from agent summary"""
        try:
            session_data = {
                'PromptTokens': 0,
                'CompletionTokens': 0,
                'TotalTokens': 0,
                'TotalCost': 0.0
            }
            
            # Calculate from agent usage summary
            for model_name, model_data in agent_summary.get("usage_including_cached_inference", {}).items():
                if model_name != 'total_cost':
                    session_data['PromptTokens'] += model_data.get('prompt_tokens', 0)
                    session_data['CompletionTokens'] += model_data.get('completion_tokens', 0)
                    session_data['TotalTokens'] += model_data.get('total_tokens', 0)
                    session_data['TotalCost'] += model_data.get('cost', 0.0)
            
            # Update database with usage
            await self.update_database_usage(
                chat_id, enterprise_id, session_id,
                session_data['PromptTokens'],
                session_data['CompletionTokens'], 
                session_data['TotalTokens'],
                session_data['TotalCost']
            )
            
            return session_data
            
        except Exception as e:
            logger.error(f"❌ Failed to calculate usage: {e}")
            return {'PromptTokens': 0, 'CompletionTokens': 0, 'TotalTokens': 0, 'TotalCost': 0.0}

    async def update_database_usage(self, chat_id: str, enterprise_id: Union[str, ObjectId],
                                  session_id: str, prompt_tokens: int, completion_tokens: int,
                                  total_tokens: int, total_cost: float) -> bool:
        """Update token usage in database and modify enterprise balance"""
        try:
            eid = await self._validate_enterprise_exists(enterprise_id)
            
            # Insert usage tracking record
            usage_record = {
                "chat_id": chat_id,
                "enterprise_id": eid,
                "session_id": session_id,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "total_cost": total_cost,
                "timestamp": datetime.utcnow()
            }
            
            await self.usage_tracking_collection.insert_one(usage_record)
            
            # Update enterprise token balance
            await self.enterprises_collection.update_one(
                {"_id": eid},
                {"$inc": {"tokenBalance": -total_cost}}
            )
            
            logger.info(f"💰 Updated usage: {total_tokens} tokens, ${total_cost:.4f} cost")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to update database usage: {e}")
            return False

    async def display_token_usage(self, chat_id: str, enterprise_id: Union[str, ObjectId],
                                workflow_name: str = "default") -> Dict[str, Any]:
        """Display token usage statistics"""
        try:
            eid = await self._validate_enterprise_exists(enterprise_id)
            
            # Get usage for this chat
            usage_cursor = self.usage_tracking_collection.find(
                {"chat_id": chat_id, "enterprise_id": eid}
            ).sort("timestamp", -1)
            
            total_usage = {
                "total_tokens": 0,
                "total_cost": 0.0,
                "session_count": 0,
                "sessions": []
            }
            
            async for record in usage_cursor:
                total_usage["total_tokens"] += record.get("total_tokens", 0)
                total_usage["total_cost"] += record.get("total_cost", 0.0)
                total_usage["session_count"] += 1
                total_usage["sessions"].append({
                    "session_id": record.get("session_id"),
                    "tokens": record.get("total_tokens", 0),
                    "cost": record.get("total_cost", 0.0),
                    "timestamp": record.get("timestamp")
                })
            
            logger.info(f"📊 Usage Summary - Tokens: {total_usage['total_tokens']}, Cost: ${total_usage['total_cost']:.4f}")
            return total_usage
            
        except Exception as e:
            logger.error(f"❌ Failed to display token usage: {e}")
            return {"total_tokens": 0, "total_cost": 0.0, "session_count": 0, "sessions": []}

    async def save_session_usage(self, chat_id: str, enterprise_id: Union[str, ObjectId],
                               workflow_name: str, session_data: Dict[str, Any], 
                               agents: List[str]) -> bool:
        """
        NEW SCHEMA: Save session usage with per-agent tracking and workflow aggregates
        
        Implements the centralized schema:
        - Sessions with per-agent token/cost breakdown  
        - WorkflowTokenUsage aggregates across all sessions
        - Clean workflow-agnostic storage pattern
        """
        try:
            eid = await self._validate_enterprise_exists(enterprise_id)
            
            # Extract session data
            session_id = session_data["session_id"]
            session_totals = {
                "PromptTokens": session_data["PromptTokens"],
                "CompletionTokens": session_data["CompletionTokens"], 
                "TotalCost": session_data["TotalCost"]
            }
            
            # Add per-agent data to session
            for agent_name in agents:
                if agent_name in session_data.get("agents", {}):
                    agent_data = session_data["agents"][agent_name]
                    session_totals.update(agent_data)
            
            # Update workflow chat state with new session
            chat_state_field = f"{workflow_name}ChatState"
            session_path = f"{chat_state_field}.Sessions.{session_id}"
            
            # Step 1: Add/update this session
            await self.workflows_collection.update_one(
                {"chat_id": chat_id, "enterprise_id": eid},
                {
                    "$set": {
                        f"{session_path}": session_totals,
                        "last_updated": datetime.utcnow()
                    }
                },
                upsert=True
            )
            
            # Step 2: Calculate and update workflow aggregates
            # Get all sessions for this workflow to calculate totals
            workflow_doc = await self.workflows_collection.find_one(
                {"chat_id": chat_id, "enterprise_id": eid},
                {f"{chat_state_field}.Sessions": 1}
            )
            
            if workflow_doc and chat_state_field in workflow_doc:
                sessions = workflow_doc[chat_state_field].get("Sessions", {})
                
                # Calculate workflow-wide aggregates
                workflow_totals = {
                    "TotalPromptTokens": 0,
                    "TotalCompletionTokens": 0,
                    "TotalCost": 0.0
                }
                
                # Per-agent workflow totals
                agent_totals = {}
                for agent_name in agents:
                    agent_totals[f"{agent_name}_TotalPromptTokens"] = 0
                    agent_totals[f"{agent_name}_TotalCompletionTokens"] = 0
                    agent_totals[f"{agent_name}_TotalPromptCost"] = 0.0
                    agent_totals[f"{agent_name}_TotalCompletionCost"] = 0.0
                    agent_totals[f"{agent_name}_TotalCost"] = 0.0
                
                # Sum across all sessions
                for session_data_item in sessions.values():
                    workflow_totals["TotalPromptTokens"] += session_data_item.get("PromptTokens", 0)
                    workflow_totals["TotalCompletionTokens"] += session_data_item.get("CompletionTokens", 0)
                    workflow_totals["TotalCost"] += session_data_item.get("TotalCost", 0.0)
                    
                    # Sum per-agent totals
                    for agent_name in agents:
                        agent_totals[f"{agent_name}_TotalPromptTokens"] += session_data_item.get(f"{agent_name}_PromptTokens", 0)
                        agent_totals[f"{agent_name}_TotalCompletionTokens"] += session_data_item.get(f"{agent_name}_CompletionTokens", 0)
                        agent_totals[f"{agent_name}_TotalPromptCost"] += session_data_item.get(f"{agent_name}_PromptCost", 0.0)
                        agent_totals[f"{agent_name}_TotalCompletionCost"] += session_data_item.get(f"{agent_name}_CompletionCost", 0.0)
                        agent_totals[f"{agent_name}_TotalCost"] += session_data_item.get(f"{agent_name}_TotalCost", 0.0)
                
                # Combine workflow totals with agent totals
                workflow_usage = {**workflow_totals, **agent_totals}
                
                # Step 3: Update WorkflowTokenUsage aggregates
                await self.workflows_collection.update_one(
                    {"chat_id": chat_id, "enterprise_id": eid},
                    {
                        "$set": {
                            f"{chat_state_field}.WorkflowTokenUsage": workflow_usage,
                            "last_updated": datetime.utcnow()
                        }
                    }
                )
                
                logger.info(f"💰 NEW SCHEMA: Saved session {session_id} + updated workflow aggregates")
                logger.debug(f"Session: {session_totals['PromptTokens']}+{session_totals['CompletionTokens']} tokens, ${session_totals['TotalCost']:.4f}")
                logger.debug(f"Workflow Total: {workflow_usage['TotalPromptTokens']}+{workflow_usage['TotalCompletionTokens']} tokens, ${workflow_usage['TotalCost']:.4f}")
                
                return True
            else:
                logger.warning(f"Could not find workflow document for aggregate calculation")
                return False
                
        except Exception as e:
            logger.error(f"❌ Failed to save session usage (new schema): {e}")
            return False

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

    async def update_token_usage(self, chat_id: str, enterprise_id: Union[str, ObjectId],
                               session_id: str, usage_data: Dict[str, Any]) -> bool:
        """Update token usage (compatibility method)"""
        try:
            return await self.update_database_usage(
                chat_id, enterprise_id, session_id,
                usage_data.get('prompt_tokens', 0),
                usage_data.get('completion_tokens', 0),
                usage_data.get('total_tokens', 0),
                usage_data.get('total_cost', 0.0)
            )
        except Exception as e:
            logger.error(f"❌ Failed to update token usage: {e}")
            return False

    # ==================================================================================
    # MINIMAL CONVENIENCE METHODS (For shared_app integration only)
    # ==================================================================================

    async def load_chat_state(self, chat_id: str, enterprise_id: Union[str, ObjectId]) -> Optional[Dict[str, Any]]:
        """Load chat state for shared_app compatibility"""
        success, data = await self.resume_chat(chat_id, enterprise_id)
        return data if success else None

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
