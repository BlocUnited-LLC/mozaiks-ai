"""Persistence layer (clean version).

Contains:
  * PersistenceManager (wallet + enterprise validation)
  * AG2PersistenceManager (lean chat_sessions handling, usage totals)
"""

from __future__ import annotations
import json
import logging
import asyncio
import traceback
from datetime import datetime
from typing import Dict, List, Any, Optional, Union
from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ReturnDocument
from uuid import uuid4
from logs.logging_config import get_workflow_logger
from core.core_config import get_mongo_client, get_free_trial_config
from autogen.events.base_event import BaseEvent
from autogen.events.agent_events import TextEvent
from opentelemetry import trace

logger = get_workflow_logger("persistence")
tracer = trace.get_tracer(__name__)


class InvalidEnterpriseIdError(Exception):
    pass


class PersistenceManager:
    """Handles enterprise validation and wallet token accounting."""

    def __init__(self):
        self.client: Optional[Any] = None
        self.db1 = None
        self.db2 = None
        self.enterprises_collection = None
        self.wallets_collection = None
        self._init_lock = asyncio.Lock()
        logger.info("PersistenceManager created (lazy init)")

    async def _ensure_client(self) -> None:
        if self.client is not None:
            return
        async with self._init_lock:
            if self.client is not None:
                return
            self.client = get_mongo_client()
            self.db1 = self.client["MozaiksDB"]
            self.db2 = self.client["MozaiksAI"]
            self.enterprises_collection = self.db1["Enterprises"]
            self.wallets_collection = self.db1["Wallets"]
            try:
                coll = self.db2["chat_sessions"]
                await coll.create_index([("enterprise_id", 1), ("workflow_name", 1), ("created_at", -1)], name="idx_ent_wf_created")
                await coll.create_index("status", name="idx_status")
                # Normalized event collection (idempotent write target)
                ncoll = self.db2["chat_events"]
                await ncoll.create_index([("chat_id", 1), ("sequence", 1)], name="ux_chat_seq", unique=True)
                await ncoll.create_index([("chat_id", 1), ("sequence", -1)], name="idx_chat_seq_desc")
            except Exception as e:  # pragma: no cover
                logger.debug(f"index ensure skipped: {e}")

    # Enterprise helpers -------------------------------------------------
    def _ensure_object_id(self, v: Union[str, ObjectId], field: str) -> ObjectId:
        if isinstance(v, ObjectId):
            return v
        if isinstance(v, str) and len(v) == 24:
            try:
                return ObjectId(v)
            except InvalidId:
                pass
        raise InvalidEnterpriseIdError(f"Invalid {field}: {v}")

    async def _validate_enterprise_exists(self, enterprise_id: Union[str, ObjectId]) -> ObjectId:
        await self._ensure_client()
        oid = self._ensure_object_id(enterprise_id, "enterprise_id")
        assert self.enterprises_collection is not None
        if not await self.enterprises_collection.find_one({"_id": oid}):
            raise InvalidEnterpriseIdError(f"Enterprise {enterprise_id} does not exist")
        return oid

    # Wallet -------------------------------------------------------------
    async def get_wallet_balance(self, user_id: str, enterprise_id: Union[str, ObjectId]) -> int:
        await self._ensure_client()
        assert self.wallets_collection is not None
        doc = await self.wallets_collection.find_one({"EnterpriseId": str(enterprise_id), "UserId": user_id}, {"Balance": 1})
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
        assert self.wallets_collection is not None
        await self.wallets_collection.update_one(
            {"EnterpriseId": eid, "UserId": user_id},
            {"$setOnInsert": {"Balance": int(initial_balance), "CreatedAt": now}, "$set": {"UpdatedAt": now}},
            upsert=True,
        )
        return {"enterprise_id": eid, "user_id": user_id, "balance": await self.get_wallet_balance(user_id, eid)}

    async def debit_tokens(self, user_id: str, enterprise_id: Union[str, ObjectId], amount: int, *, reason: str, strict: bool = True, meta: Optional[Dict[str, Any]] = None) -> Optional[int]:
        await self._ensure_client()
        eid = str(enterprise_id)
        if amount <= 0:
            return await self.get_wallet_balance(user_id, eid)
        assert self.wallets_collection is not None
        res = await self.wallets_collection.find_one_and_update(
            {"EnterpriseId": eid, "UserId": user_id, "Balance": {"$gte": int(amount)}},
            {"$inc": {"Balance": -int(amount)}, "$set": {"UpdatedAt": datetime.utcnow()}},
            return_document=ReturnDocument.AFTER,
        )
        if res is None:
            if strict:
                raise ValueError("INSUFFICIENT_TOKENS")
            return None
        return int(res.get("Balance", 0))

    async def credit_tokens(self, user_id: str, enterprise_id: Union[str, ObjectId], amount: int, *, reason: str, meta: Optional[Dict[str, Any]] = None) -> int:
        await self._ensure_client()
        eid = str(enterprise_id)
        assert self.wallets_collection is not None
        res = await self.wallets_collection.find_one_and_update(
            {"EnterpriseId": eid, "UserId": user_id},
            {"$inc": {"Balance": int(amount)}, "$set": {"UpdatedAt": datetime.utcnow()}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return int(res.get("Balance", 0))


class AG2PersistenceManager:
    """Lean chat session + usage persistence using lowercase 'chat_sessions'."""

    def __init__(self):
        self.persistence = PersistenceManager()
        logger.info("AG2PersistenceManager (lean) ready")

    async def _coll(self):
        await self.persistence._ensure_client()
        assert self.persistence.client is not None, "Mongo client not initialized"
        return self.persistence.client["MozaiksAI"]["chat_sessions"]

    async def _events_coll(self):
        await self.persistence._ensure_client()
        assert self.persistence.client is not None, "Mongo client not initialized"
        return self.persistence.client["MozaiksAI"]["chat_events"]

    # Wallet delegation -------------------------------------------------
    async def get_wallet_balance(self, user_id: str, enterprise_id: str) -> int:
        return await self.persistence.get_wallet_balance(user_id, enterprise_id)

    async def ensure_wallet(self, user_id: str, enterprise_id: str, initial_balance: int = 0) -> Dict[str, Any]:
        return await self.persistence.ensure_wallet(user_id, enterprise_id, initial_balance)

    async def debit_tokens(self, user_id: str, enterprise_id: str, amount: int, *, reason: str, strict: bool = True, meta: Optional[Dict[str, Any]] = None) -> Optional[int]:
        return await self.persistence.debit_tokens(user_id, enterprise_id, amount, reason=reason, strict=strict, meta=meta)

    async def credit_tokens(self, user_id: str, enterprise_id: str, amount: int, *, reason: str, meta: Optional[Dict[str, Any]] = None) -> int:
        return await self.persistence.credit_tokens(user_id, enterprise_id, amount, reason=reason, meta=meta)

    # Chat sessions -----------------------------------------------------
    async def create_chat_session(self, chat_id: str, enterprise_id: str, workflow_name: str, user_id: str) -> None:
        try:
            try:
                await self.persistence._validate_enterprise_exists(enterprise_id)
            except Exception:
                pass
            coll = await self._coll()
            if await coll.find_one({"_id": chat_id}):
                return
            now = datetime.utcnow()
            await coll.insert_one({
                "_id": chat_id,
                "chat_id": chat_id,  # backward compatibility
                "enterprise_id": enterprise_id,
                "workflow_name": workflow_name,
                "user_id": user_id,
                "status": "in_progress",
                "created_at": now,
                "last_updated_at": now,
                "duration_sec": 0.0,
                "messages": [],
            })
        except Exception as e:  # pragma: no cover
            logger.error(f"create_chat_session failed: {e}")

    async def mark_chat_completed(self, chat_id: str, enterprise_id: str, termination_reason: str) -> bool:
        try:
            coll = await self._coll()
            res = await coll.update_one({"_id": chat_id, "enterprise_id": enterprise_id}, {"$set": {
                "status": "completed",
                "termination_reason": termination_reason,
                "completed_at": datetime.utcnow(),
                "last_updated_at": datetime.utcnow(),
            }})
            return res.modified_count > 0
        except Exception as e:  # pragma: no cover
            logger.error(f"mark_chat_completed failed: {e}")
            return False

    async def resume_chat(self, chat_id: str, enterprise_id: str) -> Optional[List[Dict[str, Any]]]:
        try:
            coll = await self._coll()
            doc = await coll.find_one({"_id": chat_id, "enterprise_id": enterprise_id}, {"messages": 1, "status": 1})
            if not doc or doc.get("status") != "in_progress":
                return None
            return doc.get("messages", [])
        except Exception as e:  # pragma: no cover
            logger.error(f"resume_chat failed: {e}")
            return None

    async def fetch_event_diff(self, *, chat_id: str, enterprise_id: str, last_sequence: int) -> List[Dict[str, Any]]:
        """Return normalized event envelopes with sequence > last_sequence ordered ascending.

        Used for reconnect handshake to replay only missing events.
        Returns empty list if collection missing or errors occur.
        """
        try:
            coll = await self._events_coll()
            cursor = coll.find({
                "chat_id": chat_id,
                "enterprise_id": enterprise_id,
                "sequence": {"$gt": int(last_sequence)}
            }, {"_id": 0}).sort("sequence", 1)
            return [doc async for doc in cursor]
        except Exception as e:  # pragma: no cover
            logger.debug(f"fetch_event_diff failed for {chat_id}: {e}")
            return []

    # Events ------------------------------------------------------------
    async def save_event(self, event: BaseEvent, chat_id: str, enterprise_id: str, workflow_name: str, user_id: str) -> None:
        with tracer.start_as_current_span("save_event") as span:
            span.set_attributes({"chat_id": chat_id, "enterprise_id": enterprise_id})
            try:
                if not isinstance(event, TextEvent):
                    return
                coll = await self._coll()
                event_id = getattr(event, "id", None) or getattr(event, "event_id", None) or getattr(event, "event_uuid", None) or str(uuid4())
                sender_obj = getattr(event, "sender", None)
                raw_name = getattr(sender_obj, "name", None) if sender_obj else None
                if not raw_name:
                    raw_name = "assistant"
                name_lower = raw_name.lower()
                role = "user" if name_lower in ("user", "userproxy", "userproxyagent") else "assistant"
                raw_content = getattr(event, "content", "")
                if isinstance(raw_content, (dict, list)):
                    try:
                        content_str = json.dumps(raw_content)[:10000]
                    except Exception:
                        content_str = str(raw_content)
                else:
                    content_str = str(raw_content)
                ts = getattr(event, "timestamp", None)
                evt_ts = datetime.fromtimestamp(ts) if isinstance(ts, (int, float)) else datetime.utcnow()
                msg = {
                    "role": role,
                    "content": content_str,
                    "timestamp": evt_ts,
                    "event_type": "message.created",
                    "event_id": event_id,
                }
                if role == "assistant":
                    msg["agent_name"] = raw_name
                await coll.update_one({"_id": chat_id, "enterprise_id": enterprise_id}, {"$push": {"messages": msg}, "$set": {"last_updated_at": datetime.utcnow()}})
                span.add_event("message_saved")
            except Exception as e:  # pragma: no cover
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                logger.error(f"save_event failed: {e}\n{traceback.format_exc()}")

    async def save_normalized_event(self, *, envelope: Dict[str, Any], chat_id: str, enterprise_id: str, workflow_name: str, user_id: str) -> None:
        """Persist a normalized event envelope idempotently.

        Expects envelope to already contain:
          id, chat_id, sequence, event_type, ts_utc, role, name, content, meta
        Adds enterprise/workflow/user context for querying & auditing.
        Enforces uniqueness on (chat_id, sequence) via unique index.
        Silently ignores duplicate key errors to support replay/idempotent re-saves.
        """
        with tracer.start_as_current_span("save_normalized_event") as span:
            span.set_attributes({"chat_id": chat_id, "enterprise_id": enterprise_id})
            try:
                if not envelope:
                    return
                seq = envelope.get("sequence")
                if seq is None:
                    return
                coll = await self._events_coll()
                doc = dict(envelope)
                doc.setdefault("chat_id", chat_id)
                doc.setdefault("enterprise_id", enterprise_id)
                doc.setdefault("workflow_name", workflow_name)
                doc.setdefault("user_id", user_id)
                # Provide a sortable datetime field if only ISO string present
                ts_iso = doc.get("ts_utc")
                if ts_iso and not isinstance(ts_iso, datetime):
                    try:
                        doc["ts_dt"] = datetime.fromisoformat(ts_iso.replace("Z", "+00:00"))
                    except Exception:
                        doc["ts_dt"] = datetime.utcnow()
                await coll.insert_one(doc)
                span.add_event("normalized_event_saved")
            except Exception as e:  # pragma: no cover
                # Ignore duplicate key errors (idempotency) while logging others at debug
                msg = str(e)
                if "E11000" in msg:
                    span.add_event("duplicate_ignored")
                else:
                    span.record_exception(e)
                    span.set_status(trace.Status(trace.StatusCode.ERROR, msg))
                    logger.debug(f"save_normalized_event non-dup error: {e}")

    # Usage summary ----------------------------------------------------
    async def save_usage_summary(self, summary: Dict[str, Any], chat_id: str, enterprise_id: str, user_id: str, workflow_name: str) -> None:
        with tracer.start_as_current_span("save_usage_summary") as span:
            span.set_attributes({"chat_id": chat_id, "enterprise_id": enterprise_id})
            try:
                coll = await self._coll()
                usage = summary.get("usage", [])
                if not isinstance(usage, list):
                    usage = []
                total_tokens = sum(d.get("total_tokens", 0) for d in usage if isinstance(d, dict))
                prompt_tokens = sum(d.get("prompt_tokens", 0) for d in usage if isinstance(d, dict))
                completion_tokens = sum(d.get("completion_tokens", 0) for d in usage if isinstance(d, dict))
                try:
                    total_cost = float(summary.get("total_cost", 0.0))
                except Exception:
                    total_cost = 0.0
                await coll.update_one({"_id": chat_id, "enterprise_id": enterprise_id}, {"$set": {
                    "usage_total_tokens_final": total_tokens,
                    "usage_prompt_tokens_final": prompt_tokens,
                    "usage_completion_tokens_final": completion_tokens,
                    "usage_total_cost_final": total_cost,
                    "usage_summary_raw": summary,
                    "last_updated_at": datetime.utcnow(),
                }})
                if total_tokens > 0:
                    cfg = get_free_trial_config()
                    if not bool(cfg.get("enabled", False)):
                        await self.debit_tokens(user_id, enterprise_id, total_tokens, reason="workflow_completion", strict=False, meta={"chat_id": chat_id, "workflow": workflow_name, "cost": total_cost})
                span.add_event("usage_summary_saved")
            except Exception as e:  # pragma: no cover
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                logger.error(f"save_usage_summary failed: {e}\n{traceback.format_exc()}")

    # JSON extraction convenience (kept for backward compatibility) ----
    @staticmethod
    def _extract_json_from_text(text: Any) -> Optional[Dict[str, Any]]:
        try:
            if text is None:
                return None
            if isinstance(text, dict):
                return text
            if isinstance(text, list):
                return None
            s = text if isinstance(text, str) else str(text)
            s_strip = s.strip()
            try:
                obj = json.loads(s_strip)
                if isinstance(obj, dict):
                    return obj
            except Exception:
                pass
            start = s_strip.find("{")
            end = s_strip.rfind("}")
            if start != -1 and end != -1 and end > start:
                snippet = s_strip[start:end+1]
                try:
                    obj = json.loads(snippet)
                    if isinstance(obj, dict):
                        return obj
                except Exception:
                    return None
            return None
        except Exception:
            return None

    async def gather_latest_agent_jsons(self, *, chat_id: str, enterprise_id: str, agent_names: Optional[List[str]] = None) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        try:
            msgs = await self.resume_chat(chat_id, enterprise_id) or []
            def agent_name_from(m: Dict[str, Any]) -> str:
                if m.get("role") == "assistant":
                    return str(m.get("agent_name") or "").strip()
                return "user"
            if agent_names:
                wanted = {n.strip() for n in agent_names}
                for m in reversed(msgs):
                    if not isinstance(m, dict):
                        continue
                    nm = agent_name_from(m)
                    if not nm or nm not in wanted or nm in result:
                        continue
                    js = self._extract_json_from_text(m.get("content"))
                    if js is not None:
                        result[nm] = js
                return result
            seen: set[str] = set()
            for m in reversed(msgs):
                if not isinstance(m, dict):
                    continue
                nm = agent_name_from(m)
                if not nm or nm in seen:
                    continue
                js = self._extract_json_from_text(m.get("content"))
                if js is not None:
                    result[nm] = js
                    seen.add(nm)
            return result
        except Exception as e:  # pragma: no cover
            logger.warning(f"gather_latest_agent_jsons failed for {chat_id}: {e}")
            return result
