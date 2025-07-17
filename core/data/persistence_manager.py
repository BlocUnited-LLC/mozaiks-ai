# ==============================================================================
# FILE: core/data/persistence_manager.py
# DESCRIPTION: Centralized persistence and AG2 groupchat resume management
# ==============================================================================

import logging
from typing import Dict, List, Optional, Any, Union, Tuple
from datetime import datetime
from bson.objectid import ObjectId
from bson.errors import InvalidId

# AG2 imports for proper resume functionality
from autogen import Agent, GroupChatManager
from autogen.agentchat.groupchat import GroupChat

from core.core_config import get_mongo_client

logger = logging.getLogger(__name__)

class InvalidEnterpriseIdError(ValueError):
    """Raised when an invalid enterprise ID is provided"""
    pass

class PersistenceManager:
    """
    Centralized persistence manager for AG2 groupchat resume functionality.
    
    This manager implements AG2's official resume patterns from:
    https://docs.ag2.ai/latest/docs/user-guide/advanced-concepts/groupchat/resuming-group-chat/
    
    Key Features:
    - Proper AG2 message format persistence
    - Transport-agnostic resume logic
    - Connection state management
    - Token tracking integration
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
    # AG2 GROUPCHAT PERSISTENCE METHODS
    # ==================================================================================

    async def save_ag2_groupchat_state(
        self,
        chat_id: str,
        enterprise_id: Union[str, ObjectId],
        groupchat: GroupChat,
        manager: GroupChatManager,
        connection_info: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Save complete AG2 groupchat state for proper resume.
        
        This follows AG2's official persistence pattern:
        - Messages in AG2 format
        - Agent states and configurations
        - GroupChat settings
        - Manager state
        """
        try:
            eid = await self._validate_enterprise_exists(enterprise_id)
            
            # Extract AG2 messages in proper format
            ag2_messages = []
            if hasattr(groupchat, 'messages') and groupchat.messages:
                ag2_messages = [self._convert_to_ag2_message_format(msg) for msg in groupchat.messages]
            
            # Extract agent information
            agents_info = []
            if hasattr(groupchat, 'agents'):
                for agent in groupchat.agents:
                    agent_info = {
                        "name": agent.name,
                        "description": getattr(agent, 'description', ''),
                        "system_message": getattr(agent, 'system_message', ''),
                        "human_input_mode": getattr(agent, 'human_input_mode', 'NEVER'),
                        "max_consecutive_auto_reply": getattr(agent, 'max_consecutive_auto_reply', None),
                        "chat_messages": getattr(agent, 'chat_messages', {}),
                        "agent_type": agent.__class__.__name__
                    }
                    agents_info.append(agent_info)
            
            # Extract groupchat configuration
            groupchat_config = {
                "admin_name": getattr(groupchat, 'admin_name', None),
                "max_round": getattr(groupchat, 'max_round', None),
                "speaker_selection_method": getattr(groupchat, 'speaker_selection_method', 'auto'),
                "allow_repeat_speaker": getattr(groupchat, 'allow_repeat_speaker', True),
                "send_introductions": getattr(groupchat, 'send_introductions', False),
                "role_for_select_speaker_messages": getattr(groupchat, 'role_for_select_speaker_messages', 'system')
            }
            
            # Extract manager state
            manager_state = {
                "system_message": getattr(manager, 'system_message', ''),
                "max_consecutive_auto_reply": getattr(manager, 'max_consecutive_auto_reply', None),
                "human_input_mode": getattr(manager, 'human_input_mode', 'NEVER'),
                "llm_config": getattr(manager, 'llm_config', {})
            }
            
            # Create AG2-compatible persistence document
            persistence_doc = {
                "chat_id": chat_id,
                "enterprise_id": eid,
                "ag2_groupchat_state": {
                    "messages": ag2_messages,
                    "agents": agents_info,
                    "groupchat_config": groupchat_config,
                    "manager_state": manager_state,
                    "last_speaker": getattr(groupchat, '_last_speaker_name', None),
                    "message_count": len(ag2_messages),
                    "round_count": len(ag2_messages) // 2  # Approximate rounds
                },
                "connection_info": connection_info or {},
                "last_updated": datetime.utcnow(),
                "persistence_format": "ag2_official",
                "can_resume": True
            }
            
            # Update or create workflow document
            await self.workflows_collection.update_one(
                {"chat_id": chat_id, "enterprise_id": eid},
                {"$set": persistence_doc},
                upsert=True
            )
            
            logger.info(f"💾 Saved AG2 groupchat state: {len(ag2_messages)} messages, {len(agents_info)} agents")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to save AG2 groupchat state: {e}")
            return False

    async def load_ag2_groupchat_state(
        self,
        chat_id: str,
        enterprise_id: Union[str, ObjectId]
    ) -> Optional[Dict[str, Any]]:
        """
        Load AG2 groupchat state for resume.
        
        Returns state in AG2-compatible format for proper resume.
        """
        try:
            eid = await self._validate_enterprise_exists(enterprise_id)
            
            workflow = await self.workflows_collection.find_one(
                {"chat_id": chat_id, "enterprise_id": eid}
            )
            
            if not workflow:
                logger.info(f"No existing state found for chat {chat_id}")
                return None
            
            # Return AG2 state if available
            ag2_state = workflow.get("ag2_groupchat_state")
            if ag2_state and ag2_state.get("can_resume", False):
                logger.info(f"📥 Loaded AG2 groupchat state: {ag2_state.get('message_count', 0)} messages")
                return ag2_state
            
            # Fallback to legacy format conversion
            return self._convert_legacy_state_to_ag2(workflow)
            
        except Exception as e:
            logger.error(f"❌ Failed to load AG2 groupchat state: {e}")
            return None

    def _convert_to_ag2_message_format(self, message: Any) -> Dict[str, Any]:
        """
        Convert message to AG2's expected format.
        
        AG2 expects messages in format:
        {
            "content": "message content",
            "role": "user" | "assistant" | "system",
            "name": "agent_name"
        }
        """
        if isinstance(message, dict):
            # Already in proper format
            if "content" in message and "role" in message:
                return message
            
            # Convert from our format
            return {
                "content": message.get("content", str(message)),
                "role": message.get("role", "assistant"),
                "name": message.get("sender", message.get("name", "unknown"))
            }
        elif isinstance(message, str):
            # Plain string message
            return {
                "content": message,
                "role": "assistant",
                "name": "unknown"
            }
        else:
            # Unknown format - convert to string
            return {
                "content": str(message),
                "role": "assistant", 
                "name": "unknown"
            }

    def _convert_legacy_state_to_ag2(self, workflow: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Convert legacy state format to AG2 format for backward compatibility"""
        try:
            # Try to extract from various legacy formats
            messages = []
            
            # Check different possible message locations
            if "chat_history" in workflow:
                messages = workflow["chat_history"]
            elif "session_state" in workflow and "messages" in workflow["session_state"]:
                messages = workflow["session_state"]["messages"]
            elif "conversation_state" in workflow and "messages" in workflow["conversation_state"]:
                messages = workflow["conversation_state"]["messages"]
            
            if not messages:
                return None
            
            # Convert to AG2 format
            ag2_messages = [self._convert_to_ag2_message_format(msg) for msg in messages]
            
            return {
                "messages": ag2_messages,
                "agents": [],  # Legacy doesn't have agent info
                "groupchat_config": {},
                "manager_state": {},
                "last_speaker": None,
                "message_count": len(ag2_messages),
                "round_count": len(ag2_messages) // 2,
                "legacy_conversion": True
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to convert legacy state: {e}")
            return None

    # ==================================================================================
    # AG2 RESUME METHODS
    # ==================================================================================

    async def resume_ag2_groupchat(
        self,
        chat_id: str,
        enterprise_id: Union[str, ObjectId],
        groupchat: GroupChat,
        manager: GroupChatManager,
        new_message: Optional[str] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Resume AG2 groupchat using official AG2 resume patterns.
        
        This implements the official AG2 resume functionality:
        https://docs.ag2.ai/latest/docs/user-guide/advanced-concepts/groupchat/resuming-group-chat/
        
        Returns:
            (success: bool, error_message: Optional[str])
        """
        try:
            # Load persisted state
            state = await self.load_ag2_groupchat_state(chat_id, enterprise_id)
            if not state:
                return False, f"No resumable state found for chat {chat_id}"
            
            messages = state.get("messages", [])
            if not messages:
                return False, "No messages found in persisted state"
            
            # Restore messages to groupchat using AG2's official method
            groupchat.messages = messages.copy()
            
            # Restore agent chat_messages if available
            agents_info = state.get("agents", [])
            agent_lookup = {agent.name: agent for agent in groupchat.agents}
            
            for agent_info in agents_info:
                agent_name = agent_info.get("name")
                if agent_name in agent_lookup:
                    agent = agent_lookup[agent_name]
                    # Store chat messages in a safe way - AG2 agents may not have direct message storage
                    if "chat_messages" in agent_info:
                        # Store in custom attribute for safe access
                        setattr(agent, 'restored_chat_messages', agent_info["chat_messages"])
            
            # Apply groupchat configuration if available
            config = state.get("groupchat_config", {})
            for key, value in config.items():
                if hasattr(groupchat, key) and value is not None:
                    setattr(groupchat, key, value)
            
            # Set last speaker if available (AG2 compatible)
            last_speaker = state.get("last_speaker")
            if last_speaker:
                # Use safe attribute setting for AG2 compatibility
                setattr(groupchat, 'restored_last_speaker', last_speaker)
                # Try to set AG2's actual last speaker attribute if it exists
                if hasattr(groupchat, '_last_speaker_name'):
                    setattr(groupchat, '_last_speaker_name', last_speaker)
            
            logger.info(f"✅ AG2 groupchat resumed: {len(messages)} messages restored")
            
            # Determine resume message
            resume_message = new_message or "Continue the conversation"
            if messages and not new_message:
                last_message = messages[-1]
                if isinstance(last_message, dict) and "content" in last_message:
                    resume_message = f"Based on the previous message: {last_message['content'][:100]}... please continue."
            
            return True, None
            
        except Exception as e:
            error_msg = f"Failed to resume AG2 groupchat: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return False, error_msg

    # ==================================================================================
    # CONNECTION STATE MANAGEMENT
    # ==================================================================================

    async def mark_connection_state(
        self,
        chat_id: str,
        enterprise_id: Union[str, ObjectId],
        state: str,  # "active", "paused", "disconnected", "reconnected"
        transport_type: str,  # "websocket", "sse", "simple"
        connection_info: Optional[Dict[str, Any]] = None
    ) -> bool:
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

    async def get_connection_state(
        self,
        chat_id: str,
        enterprise_id: Union[str, ObjectId]
    ) -> Optional[Dict[str, Any]]:
        """Get current connection state"""
        try:
            eid = await self._validate_enterprise_exists(enterprise_id)
            
            workflow = await self.workflows_collection.find_one(
                {"chat_id": chat_id, "enterprise_id": eid},
                {
                    "connection_state": 1,
                    "transport_type": 1,
                    "connection_info": 1,
                    "paused_at": 1,
                    "disconnected_at": 1,
                    "reconnected_at": 1,
                    "last_updated": 1
                }
            )
            
            return workflow
            
        except Exception as e:
            logger.error(f"❌ Failed to get connection state: {e}")
            return None

    # ==================================================================================
    # LEGACY COMPATIBILITY METHODS
    # ==================================================================================

    async def create_workflow_for_chat(
        self,
        chat_id: str,
        enterprise_id: Union[str, ObjectId],
        concept_id: ObjectId,
        workflow_type: str,
        user_id: Optional[str] = None
    ) -> Optional[ObjectId]:
        """Create new workflow with enhanced persistence structure"""
        try:
            # Try to validate enterprise exists, create a fallback ObjectId if it doesn't
            try:
                eid = await self._validate_enterprise_exists(enterprise_id)
            except InvalidEnterpriseIdError:
                # Create ObjectId from the enterprise_id for new enterprises
                eid = self._ensure_object_id(enterprise_id, "enterprise_id")
                logger.info(f"Creating workflow for new/unknown enterprise {enterprise_id}")
            
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
                "connection_state": "active",
                "transport_type": "unknown",
                "ag2_groupchat_state": {
                    "messages": [],
                    "agents": [],
                    "groupchat_config": {},
                    "manager_state": {},
                    "can_resume": True
                },
                "token_usage": {},
                "total_token_usage": {
                    "total_tokens": 0,
                    "total_cost": 0.0,
                    "last_updated": datetime.utcnow().isoformat()
                }
            }

            result = await self.workflows_collection.insert_one(workflow_doc)
            logger.info(f"Created workflow {result.inserted_id} with AG2 persistence support")
            return result.inserted_id

        except Exception as e:
            logger.error(f"Error creating workflow: {e}")
            return None

    async def find_latest_concept_for_enterprise(self, enterprise_id: Union[str, ObjectId]) -> Optional[Dict[str, Any]]:
        """Find the latest concept for an enterprise (compatibility method)"""
        try:
            # Try to validate enterprise exists, but don't fail if it doesn't
            try:
                enterprise_oid = await self._validate_enterprise_exists(enterprise_id)
            except InvalidEnterpriseIdError:
                # Enterprise doesn't exist yet - this is okay for new enterprises
                logger.info(f"Enterprise {enterprise_id} not found in database - this is normal for new enterprises")
                return None
            
            # Check concepts collection in db2 (autogen_ai_agents) - this is where concepts actually are
            concepts_collection = self.db2['Concepts']  # Use self.db2 instead of db1
            
            concept = await concepts_collection.find_one(
                {"enterprise_id": enterprise_oid},
                sort=[("ConceptCode", -1)]
            )
            if not concept:
                concept = await concepts_collection.find_one(
                    {"enterprise_id": enterprise_oid},
                    sort=[("created_at", -1)]
                )
            if concept:
                logger.info(f"Found concept for enterprise {enterprise_id}")
            else:
                logger.warning(f"No concepts for enterprise {enterprise_id}")
            return concept
        except Exception as e:
            logger.error(f"Error finding concept: {e}")
            return None

    # Legacy method aliases for backward compatibility
    async def load_chat_state(self, chat_id: str, enterprise_id: Union[str, ObjectId]) -> Optional[Dict[str, Any]]:
        """Legacy alias - use load_ag2_groupchat_state instead"""
        return await self.load_ag2_groupchat_state(chat_id, enterprise_id)

    async def save_chat_state(self, *args, **kwargs) -> bool:
        """Legacy alias - use save_ag2_groupchat_state instead"""
        logger.warning("save_chat_state is deprecated - use save_ag2_groupchat_state")
        return True

    # ==================================================================================
    # TOKEN MANAGEMENT METHODS (for token_manager.py compatibility)
    # ==================================================================================

    async def update_budget_fields(self, chat_id: str, enterprise_id: Union[str, ObjectId], budget_data: Dict[str, Any]) -> bool:
        """Update budget fields for a workflow"""
        try:
            # Handle missing enterprises gracefully
            try:
                eid = await self._validate_enterprise_exists(enterprise_id)
            except InvalidEnterpriseIdError:
                eid = self._ensure_object_id(enterprise_id, "enterprise_id")
                logger.info(f"Updating budget for new/unknown enterprise {enterprise_id}")
            
            result = await self.workflows_collection.update_one(
                {"chat_id": chat_id, "enterprise_id": eid},
                {"$set": budget_data},
                upsert=True
            )
            
            logger.info(f"Updated budget fields for chat {chat_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating budget fields: {e}")
            return False

    async def decrement_free_loops(self, chat_id: str, enterprise_id: Union[str, ObjectId]) -> int:
        """Decrement free loops counter and return remaining count"""
        try:
            # Handle missing enterprises gracefully
            try:
                eid = await self._validate_enterprise_exists(enterprise_id)
            except InvalidEnterpriseIdError:
                eid = self._ensure_object_id(enterprise_id, "enterprise_id")
                logger.info(f"Decrementing loops for new/unknown enterprise {enterprise_id}")
            
            result = await self.workflows_collection.find_one_and_update(
                {"chat_id": chat_id, "enterprise_id": eid},
                {"$inc": {"free_loops_remaining": -1}},
                return_document=True,
                upsert=True
            )
            
            remaining = result.get("free_loops_remaining", 0) if result else 0
            logger.info(f"Decremented free loops for chat {chat_id}, remaining: {remaining}")
            return max(0, remaining)
            
        except Exception as e:
            logger.error(f"Error decrementing free loops: {e}")
            return 0

    async def save_token_usage(self, chat_id: str, enterprise_id: Union[str, ObjectId], 
                             session_id: Optional[str] = None, total_tokens: int = 0, 
                             prompt_tokens: int = 0, completion_tokens: int = 0,
                             total_cost: float = 0.0, turn_number: int = 0, **kwargs) -> bool:
        """Save token usage data"""
        try:
            # Handle missing enterprises gracefully
            try:
                eid = await self._validate_enterprise_exists(enterprise_id)
            except InvalidEnterpriseIdError:
                eid = self._ensure_object_id(enterprise_id, "enterprise_id")
                logger.info(f"Saving token usage for new/unknown enterprise {enterprise_id}")
            
            usage_record = {
                "chat_id": chat_id,
                "enterprise_id": eid,
                "session_id": session_id or chat_id,
                "total_tokens": total_tokens,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_cost": total_cost,
                "turn_number": turn_number,
                "timestamp": datetime.utcnow(),
                **kwargs
            }
            
            await self.usage_tracking_collection.insert_one(usage_record)
            logger.info(f"Saved token usage for chat {chat_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving token usage: {e}")
            return False

    async def update_token_usage(self, chat_id: str, enterprise_id: Union[str, ObjectId], 
                               session_usage: Optional[Dict[str, Any]] = None,
                               business_usage: Optional[Dict[str, Any]] = None,
                               observability_data: Optional[Dict[str, Any]] = None, **kwargs) -> bool:
        """Update token usage in workflow"""
        try:
            # Handle missing enterprises gracefully
            try:
                eid = await self._validate_enterprise_exists(enterprise_id)
            except InvalidEnterpriseIdError:
                eid = self._ensure_object_id(enterprise_id, "enterprise_id")
                logger.info(f"Updating token usage for new/unknown enterprise {enterprise_id}")
            
            token_data = {
                "session_usage": session_usage or {},
                "business_usage": business_usage or {},
                "observability_data": observability_data or {},
                "last_updated": datetime.utcnow(),
                **kwargs
            }
            
            result = await self.workflows_collection.update_one(
                {"chat_id": chat_id, "enterprise_id": eid},
                {"$set": {"token_usage": token_data}},
                upsert=True
            )
            
            logger.info(f"Updated token usage for chat {chat_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating token usage: {e}")
            return False

    async def close(self):
        """Close database connection"""
        if self.client:
            self.client.close()
            logger.info("MongoDB connection closed")

# Global instance
persistence_manager = PersistenceManager()

# Backward compatibility alias
mongodb_manager = persistence_manager
