"""
Enhanced PersistenceManager with VE-style chat session management
Supports multiple workflows per enterprise with comprehensive session tracking
Based on AD_DevDeploy.py patterns for production-scale chat management
Added production wallet/token accounting with atomic debits/credits.
"""
import logging
import time
import asyncio
import traceback
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Union, Tuple, Callable
from dataclasses import dataclass, field
from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ReturnDocument
from uuid import uuid4

from logs.logging_config import get_business_logger
from core.core_config import get_mongo_client
from core.workflow.helpers import get_formatted_agent_name

# AG2 Event Imports for real-time processing
from autogen.events.base_event import BaseEvent
from autogen.events.agent_events import TextEvent
from autogen.events.client_events import UsageSummaryEvent

# OpenTelemetry instrumentation for database operations
from opentelemetry import trace

logger = get_business_logger("persistence")
tracer = trace.get_tracer(__name__)

class InvalidEnterpriseIdError(Exception):
    """Raised when enterprise ID is invalid"""
    pass

class PersistenceManager:
    """
    Provides access to MongoDB collections.
    This class is now simplified to be a thin wrapper around the database client,
    as the primary logic is handled by the AG2PersistenceManager.
    """
    def __init__(self):
        self.client = get_mongo_client()
        # VE-style databases/collections
        self.db1 = self.client["MozaiksDB"]
        self.db2 = self.client["MozaiksAI"]
        # Core collections
        self.enterprises_collection = self.db1["Enterprises"]
        self.chat_sessions_collection = self.db2["ChatSessions"]
        self.wallets_collection = self.db1["Wallets"]
        logger.info(
            "🔗 PersistenceManager initialized (VE-style): db1=MozaiksDB(Enterprises,Wallets), db2=MozaiksAI(ChatSessions)"
        )

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

    async def get_user_tokens(self, user_id: str, enterprise_id: Union[str, ObjectId]) -> Dict[str, Any]:
        """
        Retrieves user token data from the Enterprises collection.
        This remains a key function for checking user permissions before starting workflows.
        """
        with tracer.start_as_current_span("get_user_tokens"):
            eid = self._ensure_object_id(enterprise_id, "enterprise_id")
            
            enterprise = await self.enterprises_collection.find_one(
                {"_id": eid, "users.user_id": user_id},
                projection={"users.$": 1}
            )
            
            if enterprise and "users" in enterprise and enterprise["users"]:
                return enterprise["users"][0].get("tokens", {})
            return {}

    async def get_wallet_balance(self, user_id: str, enterprise_id: Union[str, ObjectId]) -> int:
        """Return current wallet balance (tokens) for a user/enterprise. Prefer VE uppercase schema."""
        eid = str(enterprise_id)
        # Prefer VE (uppercase) schema
        legacy = await self.wallets_collection.find_one({"EnterpriseId": eid, "UserId": user_id}, projection={"Balance": 1})
        if legacy and "Balance" in legacy:
            try:
                return int(legacy.get("Balance", 0))
            except Exception:
                return 0
        # Fallback to lowercase schema
        doc = await self.wallets_collection.find_one({"enterprise_id": eid, "user_id": user_id}, projection={"balance": 1})
        if doc and "balance" in doc:
            return int(doc.get("balance", 0))
        return 0

    async def ensure_wallet(self, user_id: str, enterprise_id: Union[str, ObjectId], initial_balance: int = 0) -> Dict[str, Any]:
        eid = str(enterprise_id)
        now = datetime.utcnow()
        # Upsert VE uppercase document
        await self.wallets_collection.update_one(
            {"EnterpriseId": eid, "UserId": user_id},
            {"$setOnInsert": {"Balance": int(initial_balance), "Transactions": [], "CreatedAt": now}, "$set": {"UpdatedAt": now}},
            upsert=True,
        )
        bal = await self.get_wallet_balance(user_id, eid)
        return {"enterprise_id": eid, "user_id": user_id, "balance": bal}

    async def record_transaction(self, *, user_id: str, enterprise_id: Union[str, ObjectId], amount: int, tx_type: str, reason: str, meta: Optional[Dict[str, Any]] = None) -> None:
        eid = str(enterprise_id)
        tx = {"ts": datetime.utcnow(), "type": tx_type, "amount": int(amount), "reason": reason, "meta": meta or {}}
        # Prefer uppercase doc
        upd = await self.wallets_collection.update_one(
            {"EnterpriseId": eid, "UserId": user_id},
            {"$push": {"Transactions": tx}, "$set": {"UpdatedAt": datetime.utcnow()}}
        )
        if getattr(upd, "matched_count", 0) == 0:
            # Fallback to lowercase schema
            await self.wallets_collection.update_one(
                {"enterprise_id": eid, "user_id": user_id},
                {"$push": {"transactions": tx}, "$set": {"updated_at": datetime.utcnow()}},
            )

    async def debit_tokens(self, user_id: str, enterprise_id: Union[str, ObjectId], amount: int, *, reason: str, strict: bool = True, meta: Optional[Dict[str, Any]] = None) -> Optional[int]:
        """Atomically debit tokens. Returns new balance or None if insufficient and strict=False. Uses VE uppercase schema primarily."""
        eid = str(enterprise_id)
        if amount <= 0:
            return await self.get_wallet_balance(user_id, eid)
        # Try uppercase first
        res = await self.wallets_collection.find_one_and_update(
            {"EnterpriseId": eid, "UserId": user_id, "Balance": {"$gte": int(amount)}},
            {"$inc": {"Balance": -int(amount)}, "$set": {"UpdatedAt": datetime.utcnow()}, "$push": {"Transactions": {"ts": datetime.utcnow(), "type": "debit", "amount": int(amount), "reason": reason, "meta": meta or {}}}},
            return_document=ReturnDocument.AFTER,
        )
        if res is None:
            # Fallback to lowercase
            res = await self.wallets_collection.find_one_and_update(
                {"enterprise_id": eid, "user_id": user_id, "balance": {"$gte": int(amount)}},
                {"$inc": {"balance": -int(amount)}, "$set": {"updated_at": datetime.utcnow()}, "$push": {"transactions": {"ts": datetime.utcnow(), "type": "debit", "amount": int(amount), "reason": reason, "meta": meta or {}}}},
                return_document=ReturnDocument.AFTER,
            )
        if res is None:
            if strict:
                raise ValueError("INSUFFICIENT_TOKENS")
            return None
        # Return whichever field exists
        return int(res.get("Balance", res.get("balance", 0)))

    async def credit_tokens(self, user_id: str, enterprise_id: Union[str, ObjectId], amount: int, *, reason: str, meta: Optional[Dict[str, Any]] = None) -> int:
        eid = str(enterprise_id)
        # Prefer uppercase
        res = await self.wallets_collection.find_one_and_update(
            {"EnterpriseId": eid, "UserId": user_id},
            {"$inc": {"Balance": int(amount)}, "$set": {"UpdatedAt": datetime.utcnow()}, "$push": {"Transactions": {"ts": datetime.utcnow(), "type": "credit", "amount": int(amount), "reason": reason, "meta": meta or {}}}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        if res is None:
            res = await self.wallets_collection.find_one_and_update(
                {"enterprise_id": eid, "user_id": user_id},
                {"$inc": {"balance": int(amount)}, "$set": {"updated_at": datetime.utcnow()}, "$push": {"transactions": {"ts": datetime.utcnow(), "type": "credit", "amount": int(amount), "reason": reason, "meta": meta or {}}}},
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
        return int(res.get("Balance", res.get("balance", 0)))

# ==================================================================================
# AG2 REAL-TIME PERSISTENCE MANAGER
# ==================================================================================

class AG2PersistenceManager:
    """
    Handles real-time persistence of AG2 events, including messages and performance metrics.
    This replaces previous batch-oriented performance tracking and chat history management.
    """
    def __init__(self):
        self.persistence = PersistenceManager()
        self.chat_sessions_collection = self.persistence.chat_sessions_collection
        logger.info("🚀 AG2 Real-Time Persistence Manager initialized.")

    # Wallet delegation -------------------------------------------------
    async def get_wallet_balance(self, user_id: str, enterprise_id: str) -> int:
        return await self.persistence.get_wallet_balance(user_id, enterprise_id)

    async def ensure_wallet(self, user_id: str, enterprise_id: str, initial_balance: int = 0) -> Dict[str, Any]:
        return await self.persistence.ensure_wallet(user_id, enterprise_id, initial_balance)

    async def debit_tokens(self, user_id: str, enterprise_id: str, amount: int, *, reason: str, strict: bool = True, meta: Optional[Dict[str, Any]] = None) -> Optional[int]:
        return await self.persistence.debit_tokens(user_id, enterprise_id, amount, reason=reason, strict=strict, meta=meta)

    async def credit_tokens(self, user_id: str, enterprise_id: str, amount: int, *, reason: str, meta: Optional[Dict[str, Any]] = None) -> int:
        return await self.persistence.credit_tokens(user_id, enterprise_id, amount, reason=reason, meta=meta)

    async def record_transaction(self, **kwargs) -> None:
        return await self.persistence.record_transaction(**kwargs)

    async def create_chat_session(self, chat_id: str, enterprise_id: str, workflow_name: str, user_id: str) -> None:
        """Creates a new chat session document in the database upon conversation start."""
        try:
            # Ensure enterprise exists (VE contract)
            await self.persistence._validate_enterprise_exists(enterprise_id)

            # Balance is managed in Wallets; no starting/remaining balance in ChatSessions
            now = datetime.utcnow()
            session_doc = {
                "chat_id": chat_id,
                "enterprise_id": enterprise_id,
                "user_id": user_id,
                "workflow_name": workflow_name,
                "status": "in_progress",
                "created_at": now,
                # last_updated_at intentionally NOT included here to avoid conflict with $set below
                "messages": [],
                "real_time_tracking": {
                    "tokens": {
                        "total_tokens": 0,
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "total_cost": 0.0,
                    }
                }
            }
            # Idempotent creation: upsert with $setOnInsert
            res = await self.chat_sessions_collection.update_one(
                {"chat_id": chat_id, "enterprise_id": enterprise_id},
                {"$setOnInsert": session_doc, "$set": {"last_updated_at": now}},
                upsert=True,
            )
            if getattr(res, "upserted_id", None):
                logger.info(
                    f"✅ Created new chat session document for chat_id: {chat_id} (id={res.upserted_id}, db=MozaiksAI, coll=ChatSessions, found=True)"
                )
            else:
                logger.info(
                    f"ℹ️ Chat session already exists for chat_id: {chat_id} (db=MozaiksAI, coll=ChatSessions) — using existing"
                )
        except InvalidEnterpriseIdError as e:
            logger.error(f"❌ Failed to create chat session for chat_id {chat_id}: {e}")
        except Exception as e:
            logger.error(f"❌ Failed to create chat session for chat_id {chat_id}: {e}\n{traceback.format_exc()}")

    async def mark_chat_completed(self, chat_id: str, enterprise_id: str, termination_reason: str) -> bool:
        """
        Marks a chat session as completed in the database.
        """
        try:
            now = datetime.utcnow()
            update_result = await self.chat_sessions_collection.update_one(
                {"chat_id": chat_id, "enterprise_id": enterprise_id},
                {
                    "$set": {
                        "status": "completed",
                        "termination_reason": termination_reason,
                        "completed_at": now,
                        "last_updated_at": now,
                    }
                }
            )
            if update_result.modified_count > 0:
                logger.info(f"✅ Marked chat {chat_id} as completed. Reason: {termination_reason}")
                return True
            logger.warning(f"⚠️ Chat {chat_id} not found or already marked completed.")
            return False
        except Exception as e:
            logger.error(f"❌ Failed to mark chat {chat_id} as completed: {e}")
            return False

    async def save_event(self, event: BaseEvent, chat_id: str, enterprise_id: str, workflow_name: str, user_id: str) -> None:
        """Saves a single AG2 event and updates tokens + wallet (atomic debit)."""
        with tracer.start_as_current_span("save_event") as span:
            span.set_attributes({
                "chat_id": chat_id,
                "enterprise_id": enterprise_id,
                "workflow_name": workflow_name,
                "user_id": user_id,
                "event_type": type(event).__name__
            })
            
            try:
                # 1. Persist text messages
                if isinstance(event, TextEvent):
                    # Be tolerant of differing event schema across AG2 versions
                    event_id = (
                        getattr(event, 'id', None)
                        or getattr(event, 'event_id', None)
                        or getattr(event, 'event_uuid', None)
                        or str(uuid4())
                    )
                    
                    # Centralized agent name extraction with better UUID content parsing
                    sender_obj = getattr(event, 'sender', None)
                    raw_agent_name = None
                    
                    # Try direct sender name first
                    if hasattr(sender_obj, 'name'):
                        raw_agent_name = sender_obj.name  # type: ignore
                    else:
                        # Try to extract from stringified UUID content (AG2 format)
                        content_str = str(getattr(event, 'content', ''))
                        if 'sender=' in content_str:
                            import re
                            sender_match = re.search(r"sender='([^']+)'", content_str)
                            if not sender_match:
                                sender_match = re.search(r'sender="([^"]+)"', content_str)
                            if sender_match:
                                raw_agent_name = sender_match.group(1)
                    
                    # Final fallback
                    if not raw_agent_name:
                        raw_agent_name = "assistant"

                    agent_name = get_formatted_agent_name(raw_agent_name)
                    
                    # Determine role conservatively to avoid mislabeling agents like 'UserFeedbackAgent'
                    norm_sender = raw_agent_name.lower().strip()
                    if norm_sender in ("user", "userproxy", "userproxyagent"):
                        role = "user"
                    else:
                        role = "assistant"

                    # Sanitize content
                    clean_content = str(getattr(event, 'content', ''))

                    # Get timestamp safely
                    timestamp = getattr(event, 'timestamp', None)
                    event_timestamp = datetime.fromtimestamp(timestamp) if timestamp else datetime.utcnow()

                    message_doc = {
                        "sender": raw_agent_name,
                        "agent_name": agent_name,
                        "content": clean_content,
                        "role": role,
                        "timestamp": event_timestamp,
                        "event_type": type(event).__name__,
                        "event_id": event_id,
                        # Helpful metadata for downstream consumers
                        "is_user_proxy": norm_sender in ("user", "userproxy", "userproxyagent"),
                    }
                    
                    span.set_attributes({
                        "agent_name": agent_name,
                        "content_length": len(clean_content),
                        "role": role
                    })
                    
                    await self.chat_sessions_collection.update_one(
                        {"chat_id": chat_id, "enterprise_id": enterprise_id},
                        {
                            "$push": {"messages": message_doc},
                            "$set": {"last_updated_at": datetime.utcnow()}
                        }
                    )
                    logger.debug(f"📝 Saved TextEvent from '{agent_name}' to chat {chat_id}")
                    span.add_event("message_saved", {"agent_name": agent_name, "content_length": len(clean_content)})

            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                logger.error(f"❌ Failed to save event for chat {chat_id}: {e}\n{traceback.format_exc()}")

    async def save_usage_summary(self, summary: Dict[str, Any], chat_id: str, enterprise_id: str, user_id: str, workflow_name: str) -> None:
        """Saves the aggregated usage summary after a workflow completes."""
        with tracer.start_as_current_span("save_usage_summary") as span:
            span.set_attributes({
                "chat_id": chat_id,
                "enterprise_id": enterprise_id,
                "user_id": user_id,
                "workflow_name": workflow_name
            })
            
            try:
                # Fetch existing real-time tracking doc FIRST so we can detect if incremental debits already happened.
                existing_doc = await self.chat_sessions_collection.find_one(
                    {"chat_id": chat_id, "enterprise_id": enterprise_id},
                    {"real_time_tracking.tokens": 1}
                )
                incremental_debits = False
                if existing_doc:
                    try:
                        incremental_debits = bool(existing_doc.get("real_time_tracking", {})
                                                       .get("tokens", {})
                                                       .get("incremental_debits", False))
                    except Exception:
                        incremental_debits = False

                total_tokens = 0
                prompt_tokens = 0
                completion_tokens = 0
                total_cost = summary.get("total_cost", 0.0)

                usage_details = summary.get("usage", [])
                if not isinstance(usage_details, list):
                    logger.warning(f"⚠️ `usage` field in summary is not a list for chat {chat_id}. Got: {type(usage_details)}")
                    usage_details = []

                for agent_usage in usage_details:
                    if isinstance(agent_usage, dict):
                        total_tokens += agent_usage.get("total_tokens", 0)
                        prompt_tokens += agent_usage.get("prompt_tokens", 0)
                        completion_tokens += agent_usage.get("completion_tokens", 0)

                span.set_attributes({
                    "total_tokens": total_tokens,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_cost": total_cost
                })
                # Persist authoritative totals (overwrite, not increment) even if zero so UI sees explicit zeros
                await self.chat_sessions_collection.update_one(
                    {"chat_id": chat_id, "enterprise_id": enterprise_id},
                    {"$set": {
                        "real_time_tracking.tokens.total_tokens": total_tokens,
                        "real_time_tracking.tokens.prompt_tokens": prompt_tokens,
                        "real_time_tracking.tokens.completion_tokens": completion_tokens,
                        "real_time_tracking.tokens.total_cost": total_cost,
                        # Preserve incremental_debits flag if it was already true.
                        "real_time_tracking.tokens.incremental_debits": incremental_debits,
                        "last_updated_at": datetime.utcnow(),
                        "usage_summary.finalized_at": datetime.utcnow(),
                        "usage_summary.raw": summary
                    }}
                )

                if total_tokens > 0:
                    if incremental_debits:
                        # Incremental debits already charged each delta; do NOT double debit.
                        logger.info(
                            f"💱 Skipping final wallet debit for chat {chat_id} because incremental debits already occurred (total_tokens={total_tokens})."
                        )
                        span.add_event("skipped_final_debit", {"total_tokens": total_tokens})
                    else:
                        # Atomic wallet debit (only once, at finalization)
                        new_bal = await self.debit_tokens(
                            user_id,
                            enterprise_id,
                            total_tokens,
                            reason="workflow_completion",
                            strict=False,
                            meta={"chat_id": chat_id, "workflow": workflow_name, "cost": total_cost}
                        )
                        logger.info(f"✅ Saved final usage summary for chat {chat_id}: {total_tokens} tokens, cost=${total_cost:.4f}. New wallet balance: {new_bal}")
                        span.add_event("usage_summary_saved", {"total_tokens": total_tokens, "new_wallet_balance": new_bal or 0})
                else:
                    logger.info(f"ℹ️ No token usage to save for chat {chat_id}. (All agents reported zero)")
                    span.add_event("no_usage_to_save", {"reported_agents": len(usage_details)})

            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                logger.error(f"❌ Failed to save usage summary for chat {chat_id}: {e}\n{traceback.format_exc()}")

    async def resume_chat(self, chat_id: str, enterprise_id: str) -> Optional[List[Dict[str, Any]]]:
        """
        Retrieves message history for a chat session to allow for resumption,
        but only if the chat is still in progress.
        """
        try:
            session = await self.chat_sessions_collection.find_one(
                {"chat_id": chat_id, "enterprise_id": enterprise_id, "status": "in_progress"}
            )
            
            # Only allow resumption if the session exists and is marked as "in_progress"
            if session and session.get("status") == "in_progress":
                logger.info(f"🔄 Resuming chat {chat_id} with {len(session.get('messages', []))} messages.")
                return session.get("messages")
            
            if session:
                logger.warning(f"⚠️ Attempted to resume a completed or invalid status chat: {chat_id} (Status: {session.get('status')})")
            
            # Return None if session does not exist, is completed, or has an invalid status
            return None
            
        except Exception as e:
            logger.error(f"❌ Failed to resume chat {chat_id}: {e}")
            return None
