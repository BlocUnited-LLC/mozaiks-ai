"""
Enhanced Persistence Layer (organized)

This module provides:
1) Token Wallet persistence (VE uppercase schema) — single source of truth for balances and transactions
2) Chat/Workflow persistence — chat sessions, messages, usage summaries, resumption

Note: No functional changes in this pass; organization and doc-only improvements.
"""
import json
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

from logs.logging_config import get_workflow_logger
from core.core_config import get_mongo_client

# AG2 Event Imports for real-time processing
from autogen.events.base_event import BaseEvent
from autogen.events.agent_events import TextEvent

# OpenTelemetry instrumentation for database operations
from opentelemetry import trace

logger = get_workflow_logger("persistence")
tracer = trace.get_tracer(__name__)

class InvalidEnterpriseIdError(Exception):
    """Raised when enterprise ID is invalid"""
    pass

class PersistenceManager:
    """
    Provides access to MongoDB collections.
    Thin wrapper around the database client. Real-time chat persistence
    and accounting is performed by AG2PersistenceManager.

    Sections overview:
    - Enterprise/User helpers: ID validation and reading user token profile
    - TOKEN WALLET (VE uppercase): balance, debit/credit, transactions

    Concurrency & atomicity:
    - All wallet updates use MongoDB atomic updates (find_one_and_update / update_one)
    - Debit enforces Balance >= amount; credit upserts as needed
    """
    def __init__(self):
        # Lazy initialization to avoid Key Vault/Mongo access during server import/startup
        self.client = None
        self.db1 = None
        self.db2 = None
        # Collections are initialized lazily; annotate as Any to satisfy type checkers
        self.enterprises_collection: Any = None
        self.chat_sessions_collection: Any = None
        self.wallets_collection: Any = None
        # Async init lock to prevent concurrent initialization races
        self._init_lock = asyncio.Lock()
        logger.info("🔗 PersistenceManager created (lazy DB init; no connection yet)")
    async def _ensure_client(self):
        """Ensure the Mongo client and collections are initialized.

        Uses an asyncio.Lock to avoid races and retries with exponential backoff
        to mitigate transient network/keyvault issues.
        """
        if self.client is not None:
            return

        async with self._init_lock:
            # check again inside the lock
            if self.client is not None:
                return

            attempts = 3
            for attempt in range(1, attempts + 1):
                try:
                    self.client = get_mongo_client()
                    self.db1 = self.client["MozaiksDB"]
                    self.db2 = self.client["MozaiksAI"]
                    self.enterprises_collection = self.db1["Enterprises"]
                    self.chat_sessions_collection = self.db2["ChatSessions"]
                    self.wallets_collection = self.db1["Wallets"]
                    logger.info(
                        "🔗 PersistenceManager connected: db1=MozaiksDB(Enterprises,Wallets), db2=MozaiksAI(ChatSessions)"
                    )
                    # Ensure helpful indexes (idempotent)
                    try:
                        await self.chat_sessions_collection.create_index([
                            ("enterprise_id", 1), ("chat_id", 1)
                        ], unique=True, name="uniq_enterprise_chat")
                        await self.chat_sessions_collection.create_index("status", name="idx_status")
                        await self.chat_sessions_collection.create_index("created_at", name="idx_created_at")
                    except Exception as _idx_err:
                        logger.debug(f"Index ensure skipped/failed: {_idx_err}")
                    break
                except Exception as e:
                    logger.warning(f"Failed to initialize Mongo client (attempt {attempt}/{attempts}): {e}")
                    if attempt < attempts:
                        backoff = 0.5 * (2 ** (attempt - 1))
                        await asyncio.sleep(backoff)
                    else:
                        # bubble up the final exception
                        raise

    # ------------------------------------------------------------------
    # 🧾 Enterprise / User Config helpers
    # Contract:
    # - Inputs: enterprise_id (str|ObjectId), user_id (str)
    # - Outputs: ObjectId conversion, token profile dict
    # - Errors: raises InvalidEnterpriseIdError on bad ObjectId; returns {} if user not found
    # ------------------------------------------------------------------
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
        await self._ensure_client()
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
            await self._ensure_client()
            eid = self._ensure_object_id(enterprise_id, "enterprise_id")
            
            enterprise = await self.enterprises_collection.find_one(
                {"_id": eid, "users.user_id": user_id},
                projection={"users.$": 1}
            )
            
            if enterprise and "users" in enterprise and enterprise["users"]:
                return enterprise["users"][0].get("tokens", {})
            return {}

    # ------------------------------------------------------------------
    # 💳 TOKEN WALLET (uppercase schema only)
    # Single source of truth for balance and transactions
    # Contract:
    # - get_wallet_balance(user, enterprise): -> int (0 if missing)
    # - ensure_wallet(user, enterprise, initial_balance): upsert, returns {balance}
    # - debit_tokens(..., amount>0): atomic Balance >= amount; returns new balance or None when strict=False
    # - credit_tokens(...): atomic increment; returns new balance
    # Error modes:
    # - debit_tokens raises ValueError("INSUFFICIENT_TOKENS") when strict=True and insufficient funds
    # - All methods are async and may propagate database exceptions
    # ------------------------------------------------------------------
    async def get_wallet_balance(self, user_id: str, enterprise_id: Union[str, ObjectId]) -> int:
        """Return current wallet balance (tokens) using the VE uppercase schema only."""
        await self._ensure_client()
        eid = str(enterprise_id)
        doc = await self.wallets_collection.find_one({"EnterpriseId": eid, "UserId": user_id}, projection={"Balance": 1})
        if not doc:
            return 0
        try:
            return int(doc.get("Balance", 0))
        except Exception:
            return 0

    async def ensure_wallet(self, user_id: str, enterprise_id: Union[str, ObjectId], initial_balance: int = 0) -> Dict[str, Any]:
        await self._ensure_client()
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
        await self._ensure_client()
        eid = str(enterprise_id)
        tx = {"ts": datetime.utcnow(), "type": tx_type, "amount": int(amount), "reason": reason, "meta": meta or {}}
        await self.wallets_collection.update_one(
            {"EnterpriseId": eid, "UserId": user_id},
            {"$push": {"Transactions": tx}, "$set": {"UpdatedAt": datetime.utcnow()}},
            upsert=True,
        )

    async def debit_tokens(self, user_id: str, enterprise_id: Union[str, ObjectId], amount: int, *, reason: str, strict: bool = True, meta: Optional[Dict[str, Any]] = None) -> Optional[int]:
        """
        Atomically debit tokens (VE uppercase schema only).

        Inputs: user_id, enterprise_id, amount (>0), reason, strict, meta
        Returns: new balance (int) on success; None if insufficient and strict=False
        Errors: ValueError("INSUFFICIENT_TOKENS") if strict=True and insufficient
        """
        await self._ensure_client()
        eid = str(enterprise_id)
        if amount <= 0:
            return await self.get_wallet_balance(user_id, eid)
        # Uppercase schema only
        res = await self.wallets_collection.find_one_and_update(
            {"EnterpriseId": eid, "UserId": user_id, "Balance": {"$gte": int(amount)}},
            {"$inc": {"Balance": -int(amount)}, "$set": {"UpdatedAt": datetime.utcnow()}, "$push": {"Transactions": {"ts": datetime.utcnow(), "type": "debit", "amount": int(amount), "reason": reason, "meta": meta or {}}}},
            return_document=ReturnDocument.AFTER,
        )
        if res is None:
            if strict:
                raise ValueError("INSUFFICIENT_TOKENS")
            return None
        return int(res.get("Balance", 0))

    async def credit_tokens(self, user_id: str, enterprise_id: Union[str, ObjectId], amount: int, *, reason: str, meta: Optional[Dict[str, Any]] = None) -> int:
        """
        Atomically credit tokens (VE uppercase schema only).

        Inputs: user_id, enterprise_id, amount, reason, meta
        Returns: new balance (int)
        """
        await self._ensure_client()
        eid = str(enterprise_id)
        # Uppercase schema only
        res = await self.wallets_collection.find_one_and_update(
            {"EnterpriseId": eid, "UserId": user_id},
            {"$inc": {"Balance": int(amount)}, "$set": {"UpdatedAt": datetime.utcnow()}, "$push": {"Transactions": {"ts": datetime.utcnow(), "type": "credit", "amount": int(amount), "reason": reason, "meta": meta or {}}}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return int(res.get("Balance", 0))

# ==================================================================================
# AG2 REAL-TIME PERSISTENCE MANAGER
# ==================================================================================

class AG2PersistenceManager:
    """
        Real-time persistence of AG2 events (messages + usage), chat session lifecycle,
        and wallet debits/credits (delegated to PersistenceManager).

        Sections:
        - 💳 Token wallet delegation: thin wrappers, same contracts as PersistenceManager
        - 💬 Chat session persistence: create, complete, resume
            • Inputs: chat_id, enterprise_id, workflow_name, user_id
            • Outputs: upsert/update results (boolean for complete), message list for resume or None
            • Errors: logs and returns False/None on failures; raises only for programmer errors
        - 🧩 Event persistence: TextEvent messages, usage summary
            • save_event: persists TextEvent to ChatSessions.messages
            • save_usage_summary: writes authoritative totals and performs final debit (if not already incremental)
        - 🧰 Agent JSON helpers: extract structured outputs per agent from message history
    """
    def __init__(self):
        self.persistence = PersistenceManager()
        # Lazy import to avoid circulars at module import
        from .chat_sessions_data import ChatSessionsRepository
        self._repo = ChatSessionsRepository(self.persistence)
        logger.info("🚀 AG2 Real-Time Persistence Manager initialized.")

    # Removed unused chat_coll method

    # ------------------------------------------------------------------
    # 💳 TOKEN WALLET DELEGATION (thin wrappers to PersistenceManager)
    # Contract: mirrors PersistenceManager wallet API; no additional logic here
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # 💬 CHAT SESSION PERSISTENCE (create / complete / resume)
    # Contract:
    # - create_chat_session: idempotent upsert creating session skeleton
    # - mark_chat_completed: returns True if updated, False otherwise
    # - resume_chat: returns messages list if in_progress else None
    # ------------------------------------------------------------------
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
                    "tokens": {"total_tokens": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_cost": 0.0},
                    "counts": {"agent_turns": 0, "tool_calls": 0, "errors": 0},
                    "latency": {"turn_count": 0, "avg_turn_duration_sec": 0.0},
                    "overall": {"runtime_sec": 0.0},
                    "last_usage_recorded_at": now,
                    "last_flush_at": now
                }
            }
            
            coll = await self._repo._coll()
            res = await coll.update_one(
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
            logger.error(f"❌ Failed to create chat session for chat_id {chat_id}: {e}")

    async def mark_chat_completed(self, chat_id: str, enterprise_id: str, termination_reason: str) -> bool:
        """
        Marks a chat session as completed in the database.
        Returns True if updated, False otherwise.
        """
        try:
            return await self._repo.mark_completed(chat_id=chat_id, enterprise_id=enterprise_id, termination_reason=termination_reason)
        except Exception as e:
            logger.error(f"Failed to mark chat completed: {e}")
            return False

    async def resume_chat(self, chat_id: str, enterprise_id: str) -> Optional[List[Dict[str, Any]]]:
        """
        Retrieves message history for a chat session to allow for resumption,
        but only if the chat is still in progress.
        """
        try:
            coll = await self._repo._coll()
            session = await coll.find_one({"chat_id": chat_id, "enterprise_id": enterprise_id, "status": "in_progress"})
            if session and session.get("status") == "in_progress":
                logger.info(f"🔄 Resuming chat {chat_id} with {len(session.get('messages', []))} messages.")
                return session.get("messages", [])
            if session:
                logger.warning(f"⚠️ Attempted to resume a completed or invalid status chat: {chat_id} (Status: {session.get('status')})")
            return None
        except Exception as e:
            logger.error(f"❌ Failed to resume chat {chat_id}: {e}")
            return None

    # ------------------------------------------------------------------
    # 🧩 EVENT PERSISTENCE (messages + usage)
    # Contract:
    # - save_event(TextEvent): appends a message doc; logs errors
    # - save_usage_summary: overwrites totals, handles final debit unless incremental already occurred
    # Error modes: records exceptions to tracer, logs; does not raise for operational failures
    # ------------------------------------------------------------------
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
                    # Import helper here to avoid circular imports at module import time
                    from core.workflow.helpers import get_formatted_agent_name
                    agent_name = get_formatted_agent_name(raw_agent_name)
                    # Determine role conservatively to avoid mislabeling agents like 'UserFeedbackAgent'
                    norm_sender = raw_agent_name.lower().strip()
                    if norm_sender in ("user", "userproxy", "userproxyagent"):
                        role = "user"
                    else:
                        role = "assistant"
                    # Sanitize content and support structured outputs
                    raw_content = getattr(event, 'content', '')
                    clean_content = str(raw_content)
                    content_text = clean_content
                    content_json = None
                    content_format = "text"
                    content_parts: List[Dict[str, Any]] = []
                    try:
                        # If the event already provides structured content (dict/list), store as JSON part
                        if isinstance(raw_content, (dict, list)):
                            if isinstance(raw_content, dict):
                                content_json = raw_content
                            content_text = ""
                            content_format = "json"
                            content_parts.append({"type": "json", "value": raw_content})
                        else:
                            s = clean_content.strip()
                            js = self._extract_json_from_text(s)
                            if js is not None:
                                content_json = js if isinstance(js, dict) else None
                                start = s.find('{')
                                end = s.rfind('}')
                                if start != -1 and end != -1 and end > start:
                                    trimmed = (s[:start] + s[end+1:]).strip()
                                    content_text = trimmed
                                    before = s[:start].strip()
                                    after = s[end+1:].strip()
                                    if before:
                                        content_parts.append({"type": "text", "value": before})
                                    content_parts.append({"type": "json", "value": js})
                                    if after:
                                        content_parts.append({"type": "text", "value": after})
                                else:
                                    # Entire string is JSON
                                    content_parts.append({"type": "json", "value": js})
                                    content_text = ""
                                content_format = "json" if not content_text else "mixed"
                            else:
                                # Plain text only
                                content_parts.append({"type": "text", "value": s})
                                content_format = "text"
                    except Exception:
                        # best-effort parsing; keep plain content
                        if not content_parts:
                            content_parts = [{"type": "text", "value": clean_content.strip()}]
                    # Get timestamp safely
                    timestamp = getattr(event, 'timestamp', None)
                    event_timestamp = datetime.fromtimestamp(timestamp) if timestamp else datetime.utcnow()
                    message_doc = {
                        "sender": raw_agent_name,
                        "agent_name": agent_name,
                        # Back-compat raw content
                        "content": clean_content,
                        # Structured fields
                        "content_text": content_text,
                        "content_json": content_json or {},
                        "format": content_format,
                        "content_parts": content_parts,
                        "role": role,
                        "timestamp": event_timestamp,
                        "event_type": type(event).__name__,
                        "event_id": event_id,
                        "is_user_proxy": norm_sender in ("user", "userproxy", "userproxyagent"),
                    }
                    span.set_attributes({
                        "agent_name": agent_name,
                        "content_length": len(clean_content),
                        "role": role
                    })
                    await self._repo.push_message(chat_id=chat_id, enterprise_id=enterprise_id, message=message_doc)
                    logger.debug(f"📝 Saved TextEvent from '{agent_name}' to chat {chat_id}")
                    # Also mirror a concise line into the chat logger for easier tailing
                    try:
                        from logs.logging_config import get_chat_logger
                        chat_log = get_chat_logger("agent_chat")
                        preview_source = content_text if content_text else clean_content
                        chat_log.info(
                            "message_from_agent",
                            extra={
                                "chat_id": chat_id,
                                "enterprise_id": enterprise_id,
                                "agent_name": agent_name,
                                "role": role,
                                "format": content_format,
                                "content_preview": (preview_source[:300] + ("…" if len(preview_source) > 300 else "")),
                            },
                        )
                    except Exception:
                        pass
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
                coll = await self._repo._coll()
                existing_doc = await coll.find_one(
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
                raw_total_cost = summary.get("total_cost", 0.0)
                try:
                    total_cost = float(raw_total_cost)
                except Exception:
                    total_cost = 0.0

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
                await coll.update_one(
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
                            # Removed stray coll assignment
                        span.add_event("usage_summary_saved", {"total_tokens": total_tokens, "new_wallet_balance": new_bal or 0})
                else:
                    logger.info(f"ℹ️ No token usage to save for chat {chat_id}. (All agents reported zero)")
                    span.add_event("no_usage_to_save", {"reported_agents": len(usage_details)})

            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                logger.error(f"❌ Failed to save usage summary for chat {chat_id}: {e}\n{traceback.format_exc()}")

    # ------------------------------------------------------------------
    # Agent JSON output extraction (workflow-agnostic)
    # ------------------------------------------------------------------
    @staticmethod
    def _extract_json_from_text(text: Any) -> Optional[Dict[str, Any]]:
        """Extract the first JSON object from a text blob if present."""
        try:
            if text is None:
                return None
            if not isinstance(text, str):
                text = str(text)
            s = text.strip()
            # Try direct parse
            try:
                obj = json.loads(s)
                if isinstance(obj, dict):
                    return obj
            except Exception:
                pass
            # Fallback: find first {...}
            try:
                start = s.find('{')
                end = s.rfind('}')
                if start != -1 and end != -1 and end > start:
                    snippet = s[start:end+1]
                    obj = json.loads(snippet)
                    if isinstance(obj, dict):
                        return obj
            except Exception:
                return None
            return None
        except Exception:
            return None

    async def gather_latest_agent_jsons(
        self,
        *,
        chat_id: str,
        enterprise_id: str,
        agent_names: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Collect the most recent JSON per agent from the chat history.

        - If agent_names provided: returns {agent_name: last_json} for those names (present only if JSON found).
        - If agent_names not provided: auto-discovers agents and returns the last JSON per agent.
        """
        result: Dict[str, Any] = {}
        try:
            msgs = await self.resume_chat(chat_id, enterprise_id) or []
            # Normalize names to search across keys we persist
            # Messages saved via save_event contain both 'agent_name' (normalized) and 'sender' (raw)
            if agent_names:
                wanted = {n.lower().strip() for n in agent_names}
                for m in reversed(msgs):
                    if not isinstance(m, dict):
                        continue
                    name = str(m.get("agent_name") or m.get("sender") or "").strip()
                    if not name:
                        continue
                    low = name.lower()
                    if low in wanted and name not in result:
                        js = self._extract_json_from_text(m.get("content"))
                        if js is not None:
                            result[name] = js
                return result

            # Auto-discover: pick the last JSON per unique agent
            seen: set[str] = set()
            for m in reversed(msgs):
                if not isinstance(m, dict):
                    continue
                name = str(m.get("agent_name") or m.get("sender") or "").strip()
                if not name or name in seen:
                    continue
                js = self._extract_json_from_text(m.get("content"))
                if js is not None:
                    result[name] = js
                    seen.add(name)
            return result
        except Exception as e:
            logger.warning(f"gather_latest_agent_jsons failed for chat {chat_id}: {e}")
            return result

