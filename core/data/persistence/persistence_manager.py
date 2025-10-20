# ==============================================================================
# FILE: persistence_manager.py
# DESCRIPTION: 
# ==============================================================================

# === MOZAIKS-CORE-HEADER ===

"""Persistence layer for MozaiksAI workflows.

Clean implementation aligned with AG2 event system:
  * PersistenceManager: wallet + enterprise validation
  * AG2PersistenceManager: chat sessions + real-time usage tracking
"""

from __future__ import annotations

import json
import asyncio
from datetime import datetime, UTC
from typing import Dict, List, Any, Optional, Union, cast
import hashlib
from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ReturnDocument
from uuid import uuid4
from logs.logging_config import get_workflow_logger
from core.core_config import get_mongo_client, get_free_trial_config
from ..models import WorkflowStatus
from autogen.events.base_event import BaseEvent
from autogen.events.agent_events import TextEvent
from core.workflow.outputs.structured import agent_has_structured_output, get_structured_output_model_fields

logger = get_workflow_logger("persistence")


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
                # Primary chat session collection (canonical)
                coll = self.db2["ChatSessions"]
                # Check if index already exists before creating
                existing_indexes = await coll.list_indexes().to_list(length=None)
                index_names = [idx["name"] for idx in existing_indexes]
                
                # Create enterprise/workflow/created index if not exists
                ent_wf_created_exists = any(
                    name in ["idx_ent_wf_created", "cs_ent_wf_created"] 
                    for name in index_names
                )
                if not ent_wf_created_exists:
                    await coll.create_index([("enterprise_id", 1), ("workflow_name", 1), ("created_at", -1)], name="cs_ent_wf_created")
                    logger.debug("Created enterprise/workflow/created index")
                
                # Create status index if not exists  
                if "idx_status" not in index_names and "cs_status_created" not in index_names:
                    await coll.create_index("status", name="idx_status")
                    logger.debug("Created status index")
                    
                # Note: per-event normalized rows and their indexes in WorkflowStats
                # were removed to reduce collection noise; WorkflowStats now holds
                # live rollup documents (mon_ prefix) only, so no per-event index is needed.
            except Exception as e:  # pragma: no cover
                logger.warning(f"Index ensure issue: {e}")

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
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid balance value for user {user_id}, enterprise {enterprise_id}: {e}")
            return 0

    async def ensure_wallet(self, user_id: str, enterprise_id: Union[str, ObjectId], initial_balance: int = 0) -> Dict[str, Any]:
        await self._ensure_client()
        eid = str(enterprise_id)
        now = datetime.now(UTC)
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
        logger = get_workflow_logger()
        logger.debug(f"Debiting {amount} tokens for user {user_id}, enterprise {eid}, reason: {reason}", extra={"meta": meta})
        if amount <= 0:
            return await self.get_wallet_balance(user_id, eid)
        assert self.wallets_collection is not None
        res = await self.wallets_collection.find_one_and_update(
            {"EnterpriseId": eid, "UserId": user_id, "Balance": {"$gte": int(amount)}},
            {"$inc": {"Balance": -int(amount)}, "$set": {"UpdatedAt": datetime.now(UTC)}},
            return_document=ReturnDocument.AFTER,
        )
        if res is None:
            if strict:
                raise ValueError("INSUFFICIENT_TOKENS")
            return None
        return int(res.get("Balance", 0))

class AG2PersistenceManager:
    """Lean persistence using two collections: ChatSessions and WorkflowStats.

    ChatSessions: one document per chat workflow with embedded messages (transcript).
    WorkflowStats: holds unified live rollup documents (mon_{enterprise}_{workflow}).

    Per-event normalized rows were intentionally disabled to reduce collection noise.
    Replay/resume relies on ChatSessions.messages; metrics aggregate in real-time
    in the mon_ rollup documents.
    """

    def __init__(self):
        self.persistence = PersistenceManager()
        logger.info("AG2PersistenceManager (lean) ready")

    async def _coll(self):
        await self.persistence._ensure_client()
        assert self.persistence.client is not None, "Mongo client not initialized"
        return self.persistence.client["MozaiksAI"]["ChatSessions"]

    async def _workflow_stats_coll(self):
        await self.persistence._ensure_client()
        assert self.persistence.client is not None, "Mongo client not initialized"
        return self.persistence.client["MozaiksAI"]["WorkflowStats"]

    async def get_or_assign_cache_seed(self, chat_id: str, enterprise_id: Optional[str] = None) -> int:
        """Return a stable per-chat cache seed, assigning one if missing.

        Seed is deterministic by default (derived from chat_id and enterprise_id if provided),
        and persisted to the ChatSessions document under "cache_seed" for visibility and reuse.
        """
        coll = await self._coll()
        doc = await coll.find_one({"_id": chat_id}, {"cache_seed": 1})
        if doc and isinstance(doc.get("cache_seed"), (int, float)):
            try:
                reused_seed = int(doc["cache_seed"])
                logger.debug(
                    "[CACHE_SEED] Reusing existing per-chat seed",
                    extra={
                        "chat_id": chat_id,
                        "enterprise_id": enterprise_id,
                        "seed": reused_seed,
                        "source": "persisted",
                    },
                )
                return reused_seed  # normalize to int
            except Exception:
                logger.debug(
                    f"[CACHE_SEED] Persisted seed could not be coerced to int (value={doc.get('cache_seed')!r}); will recompute",
                    extra={"chat_id": chat_id, "enterprise_id": enterprise_id},
                )
        # Derive a deterministic 32-bit seed from chat_id (+ enterprise_id if provided)
        basis = chat_id if enterprise_id is None else f"{enterprise_id}:{chat_id}"
        seed_bytes = hashlib.sha256(basis.encode("utf-8")).digest()[:4]
        seed = int.from_bytes(seed_bytes, "big", signed=False)
        try:
            await coll.update_one({"_id": chat_id}, {"$set": {"cache_seed": seed}})
            logger.debug(
                "[CACHE_SEED] Assigned new deterministic per-chat seed",
                extra={
                    "chat_id": chat_id,
                    "enterprise_id": enterprise_id,
                    "seed": seed,
                    "basis": basis,
                    "basis_hash_prefix": hashlib.sha256(basis.encode('utf-8')).hexdigest()[:10],
                },
            )
        except Exception as e:
            logger.debug(f"Failed to persist cache_seed for chat {chat_id}: {e}")
            logger.debug(
                "[CACHE_SEED] Proceeding with in-memory seed only (persistence failure)",
                extra={"chat_id": chat_id, "enterprise_id": enterprise_id, "seed": seed},
            )
        return seed

    # Wallet delegation -------------------------------------------------
    async def get_wallet_balance(self, user_id: str, enterprise_id: str) -> int:
        return await self.persistence.get_wallet_balance(user_id, enterprise_id)

    async def ensure_wallet(self, user_id: str, enterprise_id: str, initial_balance: int = 0) -> Dict[str, Any]:
        return await self.persistence.ensure_wallet(user_id, enterprise_id, initial_balance)

    async def debit_tokens(self, user_id: str, enterprise_id: str, amount: int, *, reason: str, strict: bool = True, meta: Optional[Dict[str, Any]] = None) -> Optional[int]:
        return await self.persistence.debit_tokens(user_id, enterprise_id, amount, reason=reason, strict=strict, meta=meta)

    # Chat sessions -----------------------------------------------------
    async def create_chat_session(self, chat_id: str, enterprise_id: str, workflow_name: str, user_id: str) -> None:
        try:
            try:
                await self.persistence._validate_enterprise_exists(enterprise_id)
            except Exception as e:
                logger.error(f"Enterprise validation failed for {enterprise_id}: {e}")
            coll = await self._coll()
            if await coll.find_one({"_id": chat_id}):
                return
            now = datetime.now(UTC)
            await coll.insert_one({
                "_id": chat_id,
                "chat_id": chat_id,
                "enterprise_id": enterprise_id,
                "workflow_name": workflow_name,
                "user_id": user_id,
                "status": int(WorkflowStatus.IN_PROGRESS),
                "created_at": now,
                "last_updated_at": now,
                # per-session atomic sequence counter for message diffs
                "last_sequence": 0,
                # persisted UI context for multi-user resume of active artifact/tool panel
                # null until first artifact/tool emission is persisted via update_last_artifact()
                "last_artifact": None,
                "messages": [],
            })
            # Initialize / upsert unified real-time rollup doc (mon_{enterprise_id}_{workflow_name})
            # We maintain a single rollup document that is updated live instead of
            # a per-chat metrics_{chat_id} document plus a completion rollup.
            stats_coll = await self._workflow_stats_coll()
            summary_id = f"mon_{enterprise_id}_{workflow_name}"
            # Use $setOnInsert so we don't clobber existing real-time aggregates if concurrent chats start.
            await stats_coll.update_one(
                {"_id": summary_id},
                {"$setOnInsert": {
                    "_id": summary_id,
                    "enterprise_id": enterprise_id,
                    "workflow_name": workflow_name,
                    "last_updated_at": now,
                    # overall_avg block mirrors models.WorkflowSummaryDoc schema
                    "overall_avg": {
                        "avg_duration_sec": 0.0,
                        "avg_prompt_tokens": 0,
                        "avg_completion_tokens": 0,
                        "avg_total_tokens": 0,
                        "avg_cost_total_usd": 0.0,
                    },
                    "chat_sessions": {},
                    "agents": {}
                }},
                upsert=True
            )
            # Seed empty per-chat metrics container if not present
            await stats_coll.update_one(
                {"_id": summary_id, f"chat_sessions.{chat_id}": {"$exists": False}},
                {"$set": {f"chat_sessions.{chat_id}": {
                    "duration_sec": 0.0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "cost_total_usd": 0.0
                }, "last_updated_at": now}}
            )
        except Exception as e:  # pragma: no cover
            logger.error(f"Failed to create chat session {chat_id}: {e}")

    async def mark_chat_completed(self, chat_id: str, enterprise_id: str) -> bool:
        try:
            coll = await self._coll()
            now = datetime.now(UTC)
            # Fetch created_at & usage to compute duration for rollup averages
            base_doc = await coll.find_one({"_id": chat_id, "enterprise_id": enterprise_id}, {"created_at": 1})
            created_at = base_doc.get("created_at") if base_doc else None
            dur = float((now - created_at).total_seconds()) if created_at else 0.0
            res = await coll.update_one({"_id": chat_id, "enterprise_id": enterprise_id}, {"$set": {
                "status": int(WorkflowStatus.COMPLETED),
                "completed_at": now,
                "last_updated_at": now,
                "duration_sec": dur,
            }})
            # Fire & forget rollup refresh (no await block on success path)
            if res.modified_count > 0:
                try:  # pragma: no cover
                    from ..models import refresh_workflow_rollup_by_id  # local import to avoid circular at module import
                    # Need workflow_name for rollup; fetch minimally
                    doc = await coll.find_one({"_id": chat_id}, {"workflow_name": 1})
                    if doc and (wf := doc.get("workflow_name")):
                        summary_id = f"mon_{enterprise_id}_{wf}"
                        asyncio.create_task(refresh_workflow_rollup_by_id(summary_id))
                except Exception as e:
                    logger.debug(f"Rollup refresh failed for {chat_id}: {e}")
            return res.modified_count > 0
        except Exception as e:  # pragma: no cover
            logger.error(f"Failed to mark chat {chat_id} as completed: {e}")
            return False

    async def update_last_artifact(self, *, chat_id: str, enterprise_id: str, artifact: Dict[str, Any]) -> None:
        """Persist latest artifact/tool panel context for multi-user resume.

        Expected artifact dict keys (best-effort, flexible):
            ui_tool_id: str
            event_id: str | None
            display: str (e.g., 'artifact')
            workflow_name: str
            payload: arbitrary JSON-safe structure
        
            Semantics / lifecycle:
                - Only the most recent artifact-mode UI tool event is stored (overwrite strategy).
                - Cleared implicitly when a new chat session is created; we do NOT keep historical artifacts here.
                - Frontend uses /api/chats/meta and websocket chat_meta (last_artifact field) to restore the panel
                  when a second user joins or a browser refresh occurs without local cache.
                - Large payloads: currently stored verbatim. If future payloads exceed practical limits, introduce
                  truncation or a separate GridFS storage; shape kept minimal to ease migration.
        """
        try:
            coll = await self._coll()
            now = datetime.now(UTC)
            doc = {
                "ui_tool_id": artifact.get("ui_tool_id"),
                "event_id": artifact.get("event_id"),
                "display": artifact.get("display"),
                "workflow_name": artifact.get("workflow_name"),
                # Keep payload shallow (avoid huge memory copies); truncate strings if massive in future enhancement
                "payload": artifact.get("payload"),
                "updated_at": now,
            }
            await coll.update_one(
                {"_id": chat_id, "enterprise_id": enterprise_id},
                {"$set": {"last_artifact": doc, "last_updated_at": now}},
            )
            logger.debug(
                "[LAST_ARTIFACT] Updated",
                extra={"chat_id": chat_id, "enterprise_id": enterprise_id, "ui_tool_id": doc.get("ui_tool_id")},
            )
        except Exception as e:  # pragma: no cover
            logger.debug(f"[LAST_ARTIFACT] Update failed chat_id={chat_id}: {e}")

    async def persist_initial_messages(self, *, chat_id: str, enterprise_id: str, messages: List[Dict[str, Any]]) -> None:
        """Persist initial seed / user messages that AG2 does NOT emit as TextEvents.

        Rationale:
            a_run_group_chat() consumes the provided initial message list as starting
            context but does not re-emit those messages as TextEvent instances. Our
            persistence layer previously only stored AG2 TextEvents, leaving brand-new
            ChatSessions with an empty messages[] array until the first agent reply.

        Behavior:
            - Each provided message gets an auto-assigned sequence (incrementing last_sequence).
            - event_id is generated with 'init_' prefix for traceability.
            - Skips if list empty or chat session missing.
            - Safe to call multiple times: we perform a basic duplicate guard by checking
              if an identical (role, content) pair already exists as the latest message to
              avoid accidental double insertion on rare retries.
        """
        if not messages:
            return
        try:
            coll = await self._coll()
            base_doc = await coll.find_one({"_id": chat_id, "enterprise_id": enterprise_id}, {"messages": {"$slice": -5}})
            recent: List[Dict[str, Any]] = []
            if base_doc and isinstance(base_doc.get("messages"), list):
                recent = [m for m in base_doc["messages"] if isinstance(m, dict)]
            for m in messages:
                role = m.get("role") or "user"
                content = m.get("content")
                if content is None:
                    continue
                # Duplicate guard: if last message matches role+content, skip
                if recent and isinstance(recent[-1], dict):
                    last = recent[-1]
                    if last.get("role") == role and last.get("content") == content:
                        continue
                # Increment sequence counter atomically & fetch new value
                bump = await coll.find_one_and_update(
                    {"_id": chat_id, "enterprise_id": enterprise_id},
                    {"$inc": {"last_sequence": 1}, "$set": {"last_updated_at": datetime.now(UTC)}},
                    return_document=ReturnDocument.AFTER,
                )
                seq = int(bump.get("last_sequence", 1)) if bump else 1
                msg_doc = {
                    "role": role,
                    "content": str(content),
                    "timestamp": datetime.now(UTC),
                    "event_type": "message.created",
                    "event_id": f"init_{uuid4()}",
                    "sequence": seq,
                    "agent_name": m.get("name") or ("user" if role == "user" else "assistant"),
                }
                await coll.update_one(
                    {"_id": chat_id, "enterprise_id": enterprise_id},
                    {"$push": {"messages": msg_doc}, "$set": {"last_updated_at": datetime.now(UTC)}},
                )
                recent.append(msg_doc)
                logger.debug(
                    "[INIT_MSG_PERSIST] Inserted initial message",
                    extra={"chat_id": chat_id, "enterprise_id": enterprise_id, "seq": seq, "role": role},
                )
        except Exception as e:  # pragma: no cover
            logger.debug(f"[INIT_MSG_PERSIST] Failed chat_id={chat_id}: {e}")

    async def resume_chat(self, chat_id: str, enterprise_id: str) -> Optional[List[Dict[str, Any]]]:
        """Return full message list for an in-progress chat.

        Strict mode: only active (IN_PROGRESS) sessions are resumable; completed
        sessions require explicit inspection via administrative paths (not a
        transparent fallback inside runtime code).
        """
        try:
            coll = await self._coll()
            doc = await coll.find_one({"_id": chat_id, "enterprise_id": enterprise_id}, {"messages": 1, "status": 1})
            if not doc or int(doc.get("status", -1)) != int(WorkflowStatus.IN_PROGRESS):
                return None
            return doc.get("messages", [])
        except Exception as e:  # pragma: no cover
            logger.warning(f"Failed to resume chat {chat_id}: {e}")
            return None

    async def fetch_event_diff(self, *, chat_id: str, enterprise_id: str, last_sequence: int) -> List[Dict[str, Any]]:
        """Return message diff (messages with sequence > last_sequence).

        Assumes every persisted message carries an authoritative 'sequence'
        integer; absence of that field is considered a data integrity issue and
        results in those messages being ignored for diff purposes.
        """
        try:
            coll = await self._coll()
            doc = await coll.find_one({"_id": chat_id, "enterprise_id": enterprise_id}, {"messages": 1})
            if not doc:
                return []
            msgs = doc.get("messages", [])
            return [m for m in msgs if isinstance(m, dict) and m.get("sequence", 0) > int(last_sequence)]
        except Exception as e:  # pragma: no cover
            logger.warning(f"Failed to fetch event diff for {chat_id}: {e}")
            return []

    # Events ------------------------------------------------------------
    async def save_event(self, event: BaseEvent, chat_id: str, enterprise_id: str) -> None:
        try:
            # Only persist TextEvent messages; ignore all other AG2 event types
            if not isinstance(event, TextEvent):
                return
            # After the isinstance guard, we can safely treat event as TextEvent for type checkers
            text_event = cast(TextEvent, event)
            coll = await self._coll()
            # Atomically bump per-session sequence counter and read new value
            try:
                bump = await coll.find_one_and_update(
                    {"_id": chat_id, "enterprise_id": enterprise_id},
                    {"$inc": {"last_sequence": 1}, "$set": {"last_updated_at": datetime.now(UTC)}},
                    return_document=ReturnDocument.AFTER,
                )
                seq = int(bump.get("last_sequence", 1)) if bump else 1
                wf_name = bump.get("workflow_name") if bump else None
            except Exception as e:
                logger.warning(f"Failed to update sequence counter for {chat_id}: {e}")
                seq = 1
                wf_name = None
            event_id = getattr(text_event, "id", None) or getattr(text_event, "event_id", None) or getattr(text_event, "event_uuid", None) or str(uuid4())
            sender_obj = getattr(text_event, "sender", None)
            raw_name = getattr(sender_obj, "name", None) if sender_obj else None
            raw_content = getattr(text_event, "content", "")

            # Helper: attempt extraction from dict-like content
            def _extract_name_from_content(rc: Any) -> Optional[str]:
                try:
                    if isinstance(rc, dict):
                        for k in ("sender", "agent", "agent_name", "name"):
                            v = rc.get(k)
                            if isinstance(v, str) and v.strip():
                                return v.strip()
                    return None
                except Exception:  # pragma: no cover
                    return None

            if not raw_name:
                # If the raw content is a pydantic / dataclass / object with dict method, attempt that
                if hasattr(raw_content, "model_dump"):
                    try:
                        raw_name = _extract_name_from_content(raw_content.model_dump())  # type: ignore
                    except Exception:
                        pass
                if not raw_name and hasattr(raw_content, "dict"):
                    try:
                        raw_name = _extract_name_from_content(raw_content.dict())  # type: ignore
                    except Exception:
                        pass
                if not raw_name:
                    raw_name = _extract_name_from_content(raw_content)
            # Fallback: parse from string representation if still missing
            if not raw_name:
                try:
                    txt_for_parse = None
                    if isinstance(raw_content, str):
                        txt_for_parse = raw_content
                    else:
                        # Convert to str only if small to avoid huge dumps
                        dumped = str(raw_content)
                        if len(dumped) < 5000:
                            txt_for_parse = dumped
                    if txt_for_parse:
                        import re
                        # Try both sender='Name' and "sender": "Name" JSON style
                        m = re.search(r"sender(?:=|\"\s*:)['\"](?P<sender>[^'\"\\]+)['\"]", txt_for_parse)
                        if m:
                            raw_name = m.group("sender").strip()
                except Exception as e:
                    logger.debug(f"Failed to parse sender from string content: {e}")
            if not raw_name:
                raw_name = "assistant"  # final fallback
            name_lower = raw_name.lower()
            role = "user" if name_lower in ("user", "userproxy", "userproxyagent") else "assistant"
            # Preserve structured content when possible
            if isinstance(raw_content, (dict, list)):
                try:
                    content_str = json.dumps(raw_content)[:10000]
                except (TypeError, ValueError) as e:
                    logger.debug(f"Failed to serialize content as JSON: {e}")
                    content_str = str(raw_content)
            else:
                content_str = str(raw_content)
            # --------------------------------------------------
            # Post-process: extract inner message content to avoid storing the
            # verbose debug string: "uuid=UUID('...') content='...' sender='Agent' ..."
            # We keep only the 'content' portion; if that portion looks like JSON
            # we attempt to parse & re-dump for clean storage.
            # --------------------------------------------------
            try:
                # Fast check to avoid regex cost when pattern absent
                if "content=" in content_str and " sender=" in content_str:
                    import re
                    import json as _json
                    # Non-greedy capture between content=quote and the next quote before sender=
                    m = re.search(r"content=(?:'|\")(?P<inner>.*?)(?:'|\")\s+sender=", content_str, re.DOTALL)
                    if m:
                        inner = m.group("inner").strip()
                        cleaned: Any = inner
                        if inner.startswith("{") or inner.startswith("["):
                            try:
                                parsed = _json.loads(inner)
                                # Re-dump to normalized string with no escaping issues
                                cleaned = _json.dumps(parsed, ensure_ascii=False)
                            except Exception:
                                # leave as raw string if JSON parse fails
                                pass
                        content_str = cleaned if isinstance(cleaned, str) else _json.dumps(cleaned, ensure_ascii=False)
            except Exception as _ce:  # pragma: no cover
                logger.debug(f"Content clean failed: {_ce}")
            ts = getattr(event, "timestamp", None)
            evt_ts = datetime.fromtimestamp(ts) if isinstance(ts, (int, float)) else datetime.now(UTC)
            msg = {
                "role": role,
                "content": content_str,
                "timestamp": evt_ts,
                "event_type": "message.created",
                "event_id": event_id,
                "sequence": seq,
            }
            if role == "assistant":
                msg["agent_name"] = raw_name
            else:
                msg["agent_name"] = "user"
            # Structured output attachment (if agent registered for structured outputs in workflow)
            try:
                if role == "assistant" and wf_name and raw_name and agent_has_structured_output(wf_name, raw_name):
                    # Attempt to parse JSON from cleaned content
                    parsed = self._extract_json_from_text(content_str)
                    if parsed:
                        msg["structured_output"] = parsed
                        schema_fields = get_structured_output_model_fields(wf_name, raw_name) or {}
                        if schema_fields:
                            msg["structured_schema"] = schema_fields
            except Exception as so_err:  # pragma: no cover
                logger.debug(f"Structured output parse skipped agent={raw_name}: {so_err}")
            await coll.update_one(
                {"_id": chat_id, "enterprise_id": enterprise_id},
                {"$push": {"messages": msg}, "$set": {"last_updated_at": datetime.now(UTC)}},
            )
        except Exception as e:  # pragma: no cover
            logger.error(f"Failed to save event for {chat_id}: {e}")

    async def save_usage_summary_event(self, *, envelope: Dict[str, Any], chat_id: str, enterprise_id: str, workflow_name: str, user_id: str) -> None:
        """Process AG2 UsageSummaryEvent for metrics updates.
        
        Called directly from orchestration when UsageSummaryEvent is encountered.
        """
        try:
            if not envelope or envelope.get("event_type") != "UsageSummaryEvent":
                logger.warning(f"Invalid UsageSummaryEvent envelope for {chat_id}")
                return
                
            meta = envelope.get("meta", {})
            # Extract an event timestamp (seconds since epoch) if provided, else now()
            raw_ts = meta.get("timestamp") or meta.get("ts") or envelope.get("timestamp")
            evt_dt: Optional[datetime] = None
            try:
                if isinstance(raw_ts, (int, float)):
                    evt_dt = datetime.utcfromtimestamp(float(raw_ts))
            except Exception:
                evt_dt = None
            await self.update_session_metrics(
                chat_id=chat_id,
                enterprise_id=enterprise_id,
                user_id=user_id,
                workflow_name=workflow_name,
                prompt_tokens=int(meta.get("prompt_tokens", 0)),
                completion_tokens=int(meta.get("completion_tokens", 0)),
                cost_usd=float(meta.get("cost_usd", 0.0)),
                agent_name=meta.get("agent") or envelope.get("name"),
                event_ts=evt_dt,
            )
        except Exception as e:  # pragma: no cover
            logger.error(f"Failed to process UsageSummaryEvent for {chat_id}: {e}")

    # Usage summary ----------------------------------------------------
    async def update_session_metrics(
        self,
        chat_id: str,
        enterprise_id: str,
        user_id: str,
        workflow_name: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: float,
        agent_name: Optional[str] = None,
        event_ts: Optional[datetime] = None,
        duration_sec: float = 0.0,
    ) -> None:
        """Update live unified rollup document with per-chat + per-agent metrics and handle billing.

        Replaces per-chat metrics document updates. We directly mutate the
        rollup doc (mon_{enterprise_id}_{workflow_name}) so UI / analytics can read
        a single authoritative structure during execution.
        """
        try:
            stats_coll = await self._workflow_stats_coll()
            summary_id = f"mon_{enterprise_id}_{workflow_name}"
            total_tokens = prompt_tokens + completion_tokens
            now = datetime.now(UTC)
            if event_ts is None:
                event_ts = now
            # Ensure base summary & chat session containers exist
            await stats_coll.update_one(
                {"_id": summary_id},
                {"$setOnInsert": {
                    "_id": summary_id,
                    "enterprise_id": enterprise_id,
                    "workflow_name": workflow_name,
                    "last_updated_at": now,
                    "overall_avg": {
                        "avg_duration_sec": 0.0,
                        "avg_prompt_tokens": 0,
                        "avg_completion_tokens": 0,
                        "avg_total_tokens": 0,
                        "avg_cost_total_usd": 0.0,
                    },
                    "chat_sessions": {},
                    "agents": {}
                }}, upsert=True
            )
            # Seed chat session metrics if absent
            await stats_coll.update_one(
                {"_id": summary_id, f"chat_sessions.{chat_id}": {"$exists": False}},
                {"$set": {f"chat_sessions.{chat_id}": {
                    "duration_sec": 0.0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "cost_total_usd": 0.0,
                    # Track per-chat last event time to accumulate duration between usage deltas
                    "last_event_ts": event_ts
                }}, "$setOnInsert": {"last_updated_at": now}}
            )
            # Increment per-chat metrics
            inc_ops = {
                f"chat_sessions.{chat_id}.prompt_tokens": prompt_tokens,
                f"chat_sessions.{chat_id}.completion_tokens": completion_tokens,
                f"chat_sessions.{chat_id}.total_tokens": total_tokens,
                f"chat_sessions.{chat_id}.cost_total_usd": cost_usd,
            }
            # Compute chat-level duration delta, prefer provided duration_sec
            chat_duration_delta = max(0.0, duration_sec)
            if chat_duration_delta <= 0:
                try:
                    prev_ts_doc = await stats_coll.find_one({"_id": summary_id}, {f"chat_sessions.{chat_id}.last_event_ts": 1})
                    prev_session = None
                    if prev_ts_doc:
                        prev_cs_map = prev_ts_doc.get("chat_sessions") or {}
                        prev_session = prev_cs_map.get(chat_id) or {}
                    prev_ts_val = prev_session.get("last_event_ts") if prev_session else None  # type: ignore
                    if isinstance(prev_ts_val, datetime):
                        chat_duration_delta = max(0.0, (event_ts - prev_ts_val).total_seconds())  # type: ignore
                except Exception:
                    chat_duration_delta = 0.0
            if chat_duration_delta > 0:
                inc_ops[f"chat_sessions.{chat_id}.duration_sec"] = chat_duration_delta
            await stats_coll.update_one({"_id": summary_id}, {"$inc": inc_ops, "$set": {"last_updated_at": now, f"chat_sessions.{chat_id}.last_event_ts": event_ts}})

            # Also reflect usage counters directly inside ChatSessions doc so rollup recompute stays consistent
            chat_coll = await self._coll()
            await chat_coll.update_one(
                {"_id": chat_id, "enterprise_id": enterprise_id},
                {"$inc": {
                    "usage_prompt_tokens_final": prompt_tokens,
                    "usage_completion_tokens_final": completion_tokens,
                    "usage_total_tokens_final": total_tokens,
                    "usage_total_cost_final": cost_usd,
                }, "$set": {"last_updated_at": now}}
            )

            # Per-agent session metrics (with duration accumulation based on event timestamp)
            if agent_name:
                # Seed agent container & agent.session container if absent
                await stats_coll.update_one(
                    {"_id": summary_id, f"agents.{agent_name}": {"$exists": False}},
                    {"$set": {f"agents.{agent_name}": {
                        "avg": {
                            "avg_duration_sec": 0.0,
                            "avg_prompt_tokens": 0,
                            "avg_completion_tokens": 0,
                            "avg_total_tokens": 0,
                            "avg_cost_total_usd": 0.0,
                        },
                        "sessions": {}
                    }}}
                )
                await stats_coll.update_one(
                    {"_id": summary_id, f"agents.{agent_name}.sessions.{chat_id}": {"$exists": False}},
                    {"$set": {f"agents.{agent_name}.sessions.{chat_id}": {
                        "duration_sec": 0.0,
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "total_tokens": 0,
                        "cost_total_usd": 0.0
                    }}}
                )
                agent_inc = {
                    f"agents.{agent_name}.sessions.{chat_id}.prompt_tokens": prompt_tokens,
                    f"agents.{agent_name}.sessions.{chat_id}.completion_tokens": completion_tokens,
                    f"agents.{agent_name}.sessions.{chat_id}.total_tokens": total_tokens,
                    f"agents.{agent_name}.sessions.{chat_id}.cost_total_usd": cost_usd,
                }
                # Compute duration delta using last_event_ts (stored per agent session)
                duration_delta = max(0.0, duration_sec)
                if duration_delta <= 0:
                    try:
                        prev_ts_doc = await stats_coll.find_one({"_id": summary_id}, {f"agents.{agent_name}.sessions.{chat_id}.last_event_ts": 1})
                        prev_session = None
                        if prev_ts_doc:
                            prev_agents = prev_ts_doc.get("agents") or {}
                            prev_agent = prev_agents.get(agent_name) or {}
                            prev_sessions = prev_agent.get("sessions") or {}
                            prev_session = prev_sessions.get(chat_id) or {}
                        prev_ts_val = prev_session.get("last_event_ts") if prev_session else None  # type: ignore
                        if isinstance(prev_ts_val, datetime):
                            duration_delta = max(0.0, (event_ts - prev_ts_val).total_seconds())  # type: ignore
                        else:
                            duration_delta = 0.0
                    except Exception:
                        duration_delta = 0.0
                if duration_delta > 0:
                    agent_inc[f"agents.{agent_name}.sessions.{chat_id}.duration_sec"] = duration_delta
                # Apply increments and set last_event_ts
                await stats_coll.update_one({"_id": summary_id}, {"$inc": agent_inc, "$set": {f"agents.{agent_name}.sessions.{chat_id}.last_event_ts": event_ts}})

            # Recompute averages (simple read & aggregate) -- small doc so acceptable.
            doc = await stats_coll.find_one({"_id": summary_id}, {"chat_sessions": 1, "agents": 1})
            if doc and isinstance(doc.get("chat_sessions"), dict):
                cs = doc["chat_sessions"]
                n = len(cs) if cs else 0
                if n:
                    total_prompt = sum(int(v.get("prompt_tokens", 0)) for v in cs.values())
                    total_completion = sum(int(v.get("completion_tokens", 0)) for v in cs.values())
                    total_total = sum(int(v.get("total_tokens", 0)) for v in cs.values())
                    total_cost = sum(float(v.get("cost_total_usd", 0.0)) for v in cs.values())
                    total_duration = sum(float(v.get("duration_sec", 0.0)) for v in cs.values())
                    await stats_coll.update_one(
                        {"_id": summary_id},
                        {"$set": {
                            "overall_avg.avg_prompt_tokens": int(total_prompt / n),
                            "overall_avg.avg_completion_tokens": int(total_completion / n),
                            "overall_avg.avg_total_tokens": int(total_total / n),
                            "overall_avg.avg_cost_total_usd": (total_cost / n),
                            "overall_avg.avg_duration_sec": (total_duration / n),
                        }}
                    )
            if agent_name:
                doc = await stats_coll.find_one({"_id": summary_id}, {f"agents.{agent_name}": 1})
                ag = doc.get("agents", {}).get(agent_name) if doc else None
                if ag and isinstance(ag.get("sessions"), dict):
                    sess_map = ag["sessions"]
                    an = len(sess_map)
                    if an:
                        ap = sum(int(v.get("prompt_tokens", 0)) for v in sess_map.values())
                        ac = sum(int(v.get("completion_tokens", 0)) for v in sess_map.values())
                        at = sum(int(v.get("total_tokens", 0)) for v in sess_map.values())
                        acost = sum(float(v.get("cost_total_usd", 0.0)) for v in sess_map.values())
                        adur = sum(float(v.get("duration_sec", 0.0)) for v in sess_map.values())
                        await stats_coll.update_one({"_id": summary_id}, {"$set": {
                            f"agents.{agent_name}.avg.avg_prompt_tokens": int(ap / an),
                            f"agents.{agent_name}.avg.avg_completion_tokens": int(ac / an),
                            f"agents.{agent_name}.avg.avg_total_tokens": int(at / an),
                            f"agents.{agent_name}.avg.avg_cost_total_usd": (acost / an),
                            f"agents.{agent_name}.avg.avg_duration_sec": (adur / an),
                        }})
                
                # Real-time billing - debit tokens immediately if not free trial
                if total_tokens > 0:
                    cfg = get_free_trial_config()
                    if not bool(cfg.get("enabled", False)):
                        result = await self.debit_tokens(
                            user_id, enterprise_id, total_tokens, 
                            reason="realtime_usage", strict=False, 
                            meta={"chat_id": chat_id, "workflow": workflow_name, "cost": cost_usd, "agent": agent_name}
                        )
                        # If debit failed due to insufficient tokens, emit pause event
                        if result is None:
                            # SessionPausedEvent temporarily disabled - commenting out to prevent import errors
                            # from core.events import get_event_dispatcher, SessionPausedEvent
                            # dispatcher = get_event_dispatcher()
                            # await dispatcher.dispatch(SessionPausedEvent(
                            #     chat_id=chat_id,
                            #     reason="insufficient_tokens",
                            #     required_tokens=total_tokens,
                            #     user_id=user_id,
                            #     enterprise_id=enterprise_id
                            # ))
                            logger.warning(f"Token debit failed for chat {chat_id} - insufficient tokens ({total_tokens} required)")
                
        except Exception as e:  # pragma: no cover
            logger.error(f"Failed to update session metrics for {chat_id}: {e}")



    # used for generate_and_download
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
            logger.error(f"Failed to gather agent JSONs for {chat_id}: {e}")
            return result

