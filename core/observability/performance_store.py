"""Lightweight persistence of span summaries into a Mongo 'Performance' collection.

Enabled via env MOZAIKS_PERSIST_PERF=1 (default off to avoid write overhead).

Each stored document (one per completed timed_span) captures a coarse summary:
  {
    _id: uuid4,
    ts: <UTC datetime>,
    key: <logical operation key>,
    duration_sec: <float>,
    attrs: { flattened attributes (pruned) },
    workflow: <optional>,
    enterprise_id: <optional>,
    chat_id: <optional>,
    agent: <optional>
  }

Writes are fire-and-forget (best-effort). Failures are swallowed so hot paths
aren't disrupted. Minimal indexes: ts (TTL optional later), key, workflow.
"""
from __future__ import annotations
import os, asyncio, uuid, datetime as _dt
from typing import Dict, Any, Optional
from logs.logging_config import get_workflow_logger
from core.core_config import get_mongo_client

logger = get_workflow_logger("perf_store")

_ENABLED = os.getenv("MOZAIKS_PERSIST_PERF", "0").lower() in ("1", "true", "yes", "on")
_LOGGED_ENABLED = False  # ensure we announce once
_PERF_DEBUG = os.getenv("MOZAIKS_PERF_DEBUG", "0").lower() in ("1", "true", "yes", "on")
_SKIP_COUNTS = {
    "disabled": 0,
    "no_loop": 0,
    "init_fail": 0,
    "filtered": 0,  # spans filtered out due to being too granular
}

# Immediate visibility at import so startup logs show flag state.
try:  # pragma: no cover
    if _ENABLED:
        logger.info("Performance persistence flag detected (MOZAIKS_PERSIST_PERF=1) – will write span summaries on first span completion")
    else:
        logger.debug("Performance persistence disabled (set MOZAIKS_PERSIST_PERF=1 to enable)")
except Exception:  # pragma: no cover
    pass
_client = None
_coll = None
_init_lock = asyncio.Lock()
_indexes_created = False


async def _ensure():
    global _client, _coll, _indexes_created
    if _coll is not None:
        return _coll
    async with _init_lock:
        if _coll is not None:
            return _coll
        try:
            _client = get_mongo_client()
            _coll = _client["MozaiksAI"]["Performance"]
            if not _indexes_created:
                try:  # best effort - check existing indexes first
                    existing_indexes = await _coll.list_indexes().to_list(length=None)
                    index_names = [idx["name"] for idx in existing_indexes]
                    
                    # Only create indexes that don't already exist
                    if "idx_ts" not in index_names:
                        await _coll.create_index([("ts", 1)], name="idx_ts")
                    if "idx_key_ts" not in index_names:
                        await _coll.create_index([("key", 1), ("ts", -1)], name="idx_key_ts")
                    if "idx_workflow_ts" not in index_names:
                        await _coll.create_index([("workflow", 1), ("ts", -1)], name="idx_workflow_ts")
                    if "idx_ent_ts" not in index_names:
                        await _coll.create_index([("enterprise_id", 1), ("ts", -1)], name="idx_ent_ts")
                    if "idx_type_chat" not in index_names:
                        await _coll.create_index([("type", 1), ("chat_id", 1)], name="idx_type_chat")
                    _indexes_created = True
                except Exception as e:  # pragma: no cover
                    logger.debug(f"perf index ensure skipped: {e}")
        except Exception as e:  # pragma: no cover
            _SKIP_COUNTS["init_fail"] += 1
            if _PERF_DEBUG:
                logger.debug(f"perf store init failed: {e}")
        return _coll


def refresh_enabled_flag() -> bool:
    """Re-evaluate env flag at runtime. Returns current enabled state.

    Useful if MOZAIKS_PERSIST_PERF is exported *after* initial import.
    """
    global _ENABLED
    old = _ENABLED
    _ENABLED = os.getenv("MOZAIKS_PERSIST_PERF", "0").lower() in ("1", "true", "yes", "on")
    if _ENABLED and not old:
        logger.info("Performance persistence dynamically ENABLED (refresh_enabled_flag)")
    elif not _ENABLED and old:
        logger.info("Performance persistence dynamically DISABLED (refresh_enabled_flag)")
    return _ENABLED


def _should_persist_span(key: str, attributes: Dict[str, Any]) -> bool:
    """Decide whether to persist a span summary.

    Relaxed logic: ALWAYS persist agent_turn spans (even with zero tokens) so we
    can build an agent list + duration stats for chats where initial turns have
    no token usage (e.g., system/context loading). Other span types remain
    filtered to keep collection lean.
    """
    if key == "agent_turn":  # keep only this span type, but no longer require tokens/cost
        return True
    return False


def persist_span_summary(key: str, duration_sec: float, attributes: Optional[Dict[str, Any]] = None) -> None:
    """Schedule persistence of a span summary document (non-blocking).

    Only persists agent-level spans with meaningful metrics (tokens/costs/latency).
    Filters out database operations and internal spans like persistence_manager filters non-TextEvent.
    """
    if not _ENABLED:
        _SKIP_COUNTS["disabled"] += 1
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        _SKIP_COUNTS["no_loop"] += 1
        return  # no loop available

    attrs = attributes or {}
    
    # Filter: Only persist meaningful spans (similar to TextEvent filtering)
    if not _should_persist_span(key, attrs):
        _SKIP_COUNTS["filtered"] += 1
        return
        
    # Prune / coerce values; keep only simple JSON scalars
    clean_attrs: Dict[str, Any] = {}
    for k, v in attrs.items():
        if isinstance(v, (str, int, float, bool)) and len(str(v)) < 400:
            clean_attrs[k] = v
    doc = {
        "_id": str(uuid.uuid4()),
        "ts": _dt.datetime.utcnow(),
        "key": key,
        "duration_sec": float(duration_sec),
        "attrs": clean_attrs,
        "workflow": clean_attrs.get("workflow"),
        "enterprise_id": clean_attrs.get("enterprise_id"),
        "chat_id": clean_attrs.get("chat_id"),
        "agent": clean_attrs.get("agent") or clean_attrs.get("agent_name"),
    }

    async def _write():  # pragma: no cover (best-effort path)
        try:
            coll = await _ensure()
            if coll is None:
                return
            global _LOGGED_ENABLED
            if _ENABLED and not _LOGGED_ENABLED:
                _LOGGED_ENABLED = True
                logger.info("Performance persistence ENABLED - writing agent turn aggregates to Mongo")
            
            # Only create/update chat-level aggregate documents (no individual span docs)
            # This creates ONE performance document per chat session with all agent metrics
            if key == "agent_turn" and doc.get("chat_id"):
                chat_id = str(doc["chat_id"])  # type: ignore[index]
                enterprise_id = doc.get("enterprise_id")
                workflow = doc.get("workflow")
                agent = doc.get("agent") or "unknown"
                inc_tokens_prompt = int(clean_attrs.get("prompt_tokens", 0))
                inc_tokens_completion = int(clean_attrs.get("completion_tokens", 0))
                inc_tokens_total = int(clean_attrs.get("total_tokens", inc_tokens_prompt + inc_tokens_completion))
                inc_cost = float(clean_attrs.get("cost_usd", 0.0))
                dur = float(doc.get("duration_sec", 0.0))
                
                # Use chat_id as the document _id for one performance doc per chat session
                perf_doc_id = f"perf_{chat_id}"
                
                # Build $inc ops for this agent turn
                inc_ops = {
                    "agent_turns": 1,
                    "total_prompt_tokens": inc_tokens_prompt,
                    "total_completion_tokens": inc_tokens_completion,
                    "total_tokens": inc_tokens_total,
                    "total_cost_usd": inc_cost,
                    "total_duration_sec": dur,
                    f"agents.{agent}.turns": 1,
                    f"agents.{agent}.prompt_tokens": inc_tokens_prompt,
                    f"agents.{agent}.completion_tokens": inc_tokens_completion,
                    f"agents.{agent}.total_tokens": inc_tokens_total,
                    f"agents.{agent}.cost_usd": inc_cost,
                    f"agents.{agent}.duration_sec": dur,
                }
                
                result = await coll.update_one(
                    {"_id": perf_doc_id},
                    {
                        "$setOnInsert": {
                            "_id": perf_doc_id,
                            "type": "chat_performance",
                            "chat_id": chat_id,
                            "enterprise_id": enterprise_id,
                            "workflow": workflow,
                            "created_ts": doc["ts"],
                            "agents": {},
                            "agent_turns": 0,
                            "total_prompt_tokens": 0,
                            "total_completion_tokens": 0,
                            "total_tokens": 0,
                            "total_cost_usd": 0.0,
                            "total_duration_sec": 0.0,
                            "max_agent_duration_sec": 0.0,
                        },
                        "$inc": inc_ops,
                        "$max": {"max_agent_duration_sec": dur},
                        "$set": {"last_updated_ts": doc["ts"]},
                    },
                    upsert=True,
                )
                
                if result.upserted_id:
                    logger.info(f"perf doc created chat_id={chat_id} first_agent_turn={agent}")
                else:
                    logger.debug(f"perf doc updated chat_id={chat_id} agent={agent} +tokens={inc_tokens_total} dur={dur:.4f}s")
            else:
                logger.debug(f"Skipped non-agent_turn span: {key}")
                
        except Exception as e:
            # swallow to avoid interfering with hot path
            logger.debug(f"perf span write failed: {e}")

    try:
        loop.create_task(_write())
    except Exception:
        if _PERF_DEBUG:
            logger.debug("Failed to schedule perf span write task")
        pass


def performance_persistence_enabled() -> bool:
    return _ENABLED


async def fetch_recent_performance(limit: int = 5) -> list:
    """Utility to inspect most recent raw span documents (debug only)."""
    coll = await _ensure()
    if not coll:
        return []
    cur = coll.find({"type": {"$ne": "chat_aggregate"}}).sort("ts", -1).limit(limit)
    return [doc async for doc in cur]


def perf_diagnostics() -> Dict[str, Any]:
    """Return counters explaining why writes might not be occurring."""
    return {
        "enabled": _ENABLED,
        "skip_counts": dict(_SKIP_COUNTS),
        "indexes_created": _indexes_created,
        "debug_mode": _PERF_DEBUG,
    }

__all__ = [
    "persist_span_summary",
    "performance_persistence_enabled",
    "refresh_enabled_flag",
    "fetch_recent_performance",
    "perf_diagnostics",
    "ensure_chat_perf_doc",
]


async def ensure_chat_perf_doc(chat_id: str, enterprise_id: str, workflow: str) -> None:
    """Create the base performance document for a chat session if persistence is enabled.

    Safe to call multiple times; it uses insert-one semantics and ignores duplicate errors.
    This lets the chat session, rollup summary, and performance aggregation all be born together.
    """
    if not _ENABLED:
        return
    try:
        coll = await _ensure()
        if coll is None:
            return
        perf_doc_id = f"perf_{chat_id}"
        # Check existence first to avoid duplicate key exception noise
        existing = await coll.find_one({"_id": perf_doc_id}, {"_id": 1})
        if existing:
            return
        now = _dt.datetime.utcnow()
        base_doc = {
            "_id": perf_doc_id,
            "type": "chat_performance",
            "chat_id": chat_id,
            "enterprise_id": enterprise_id,
            "workflow": workflow,
            "created_ts": now,
            "last_updated_ts": now,
            "agents": {},
            "agent_turns": 0,
            "total_prompt_tokens": 0,
            "total_completion_tokens": 0,
            "total_tokens": 0,
            "total_cost_usd": 0.0,
            "total_duration_sec": 0.0,
            "max_agent_duration_sec": 0.0,
        }
        try:
            await coll.insert_one(base_doc)
            logger.debug(f"perf base doc created chat_id={chat_id}")
        except Exception as ie:  # pragma: no cover
            # Ignore duplicate or transient failures; later agent_turn upsert will recover.
            if _PERF_DEBUG:
                logger.debug(f"perf base doc insert skipped chat_id={chat_id}: {ie}")
    except Exception as e:  # pragma: no cover
        if _PERF_DEBUG:
            logger.debug(f"ensure_chat_perf_doc failed chat_id={chat_id}: {e}")
