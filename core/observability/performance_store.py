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
                
                # DEBUG: Log token values to identify where they're getting lost
                if _PERF_DEBUG:
                    logger.debug(f"OTEL agent_turn span: chat_id={chat_id} agent={agent} "
                               f"prompt_tokens={inc_tokens_prompt} completion_tokens={inc_tokens_completion} "
                               f"total_tokens={inc_tokens_total} cost_usd={inc_cost} duration={dur}")
                    logger.debug(f"Raw clean_attrs: {clean_attrs}")
                
                # Use chat_id as the document _id for one performance doc per chat session
                perf_doc_id = f"perf_{chat_id}"
                
                # ALSO create/update workflow-level aggregated document (like WorkflowStats pattern)
                workflow_perf_id = f"perf_mon_{enterprise_id}_{workflow}"
                
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
                
                # 1. Update per-chat performance document
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
                
                # 2. Update workflow-level aggregated document (following WorkflowStats pattern)
                workflow_inc_ops = {
                    "total_sessions": 0,  # Will be incremented separately when session completes
                    "total_agent_turns": 1,
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
                
                # Seed agent container if it doesn't exist (like WorkflowStats does)
                await coll.update_one(
                    {"_id": workflow_perf_id, f"agents.{agent}": {"$exists": False}},
                    {"$set": {f"agents.{agent}": {
                        "turns": 0,
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "total_tokens": 0,
                        "cost_usd": 0.0,
                        "duration_sec": 0.0,
                        "avg_duration_sec": 0.0,
                        "avg_prompt_tokens": 0.0,
                        "avg_completion_tokens": 0.0,
                        "avg_total_tokens": 0.0,
                        "avg_cost_usd": 0.0,
                        "sessions": {}
                    }}}
                )
                
                # Update workflow-level aggregates
                workflow_result = await coll.update_one(
                    {"_id": workflow_perf_id},
                    {
                        "$setOnInsert": {
                            "_id": workflow_perf_id,
                            "type": "workflow_performance_summary",
                            "enterprise_id": enterprise_id,
                            "workflow": workflow,
                            "created_ts": doc["ts"],
                            "agents": {},
                            "total_sessions": 0,
                            "total_agent_turns": 0,
                            "total_prompt_tokens": 0,
                            "total_completion_tokens": 0,
                            "total_tokens": 0,
                            "total_cost_usd": 0.0,
                            "total_duration_sec": 0.0,
                            "max_agent_duration_sec": 0.0,
                        },
                        "$inc": workflow_inc_ops,
                        "$max": {"max_agent_duration_sec": dur},
                        "$set": {"last_updated_ts": doc["ts"]},
                    },
                    upsert=True,
                )
                
                # Update per-agent session container within workflow document (like WorkflowStats)
                session_key = f"agents.{agent}.sessions.{chat_id}"
                await coll.update_one(
                    {"_id": workflow_perf_id},
                    {
                        "$inc": {
                            f"{session_key}.turns": 1,
                            f"{session_key}.prompt_tokens": inc_tokens_prompt,
                            f"{session_key}.completion_tokens": inc_tokens_completion,
                            f"{session_key}.total_tokens": inc_tokens_total,
                            f"{session_key}.cost_usd": inc_cost,
                            f"{session_key}.duration_sec": dur,
                        },
                        "$setOnInsert": {
                            f"{session_key}.chat_id": chat_id,
                            f"{session_key}.created_ts": doc["ts"],
                        },
                        "$set": {
                            f"{session_key}.last_updated_ts": doc["ts"],
                        }
                    },
                    upsert=True,
                )
                
                if result.upserted_id:
                    logger.info(f"perf doc created chat_id={chat_id} first_agent_turn={agent}")
                if workflow_result.upserted_id:
                    logger.info(f"workflow perf summary created enterprise_id={enterprise_id} workflow={workflow}")
                else:
                    logger.debug(f"perf docs updated chat_id={chat_id} workflow={workflow} agent={agent} +tokens={inc_tokens_total} dur={dur:.4f}s")
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
    "finalize_chat_performance",
    "compute_performance_averages",
    "debug_span_creation",
]


def debug_span_creation(chat_id: str, agent_name: str, duration_sec: float, prompt_tokens: int = 0, completion_tokens: int = 0, cost_usd: float = 0.0) -> None:
    """Debug function to manually test span creation with token data.
    
    This helps diagnose why OTEL spans aren't capturing token information properly.
    Call this with known token values to see if the performance_store receives them.
    """
    if not _ENABLED:
        logger.info("DEBUG: Performance persistence is DISABLED - enable with MOZAIKS_PERSIST_PERF=1")
        return
        
    logger.info(f"DEBUG: Creating test span with chat_id={chat_id} agent={agent_name} "
              f"prompt_tokens={prompt_tokens} completion_tokens={completion_tokens} cost_usd={cost_usd}")
    
    # Create test span attributes
    test_attributes = {
        "chat_id": chat_id,
        "enterprise_id": "debug_enterprise",
        "workflow": "debug_workflow", 
        "agent": agent_name,
        "agent_name": agent_name,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "cost_usd": cost_usd,
    }
    
    # Call persist_span_summary directly to test the flow
    persist_span_summary("agent_turn", duration_sec, test_attributes)
    logger.info("DEBUG: Test span creation scheduled")


async def finalize_chat_performance(chat_id: str, enterprise_id: str, workflow: str) -> None:
    """Mark a chat session as complete and increment workflow-level session count.
    
    Call this when a chat session ends to update the workflow summary document's total_sessions count.
    This aligns with the WorkflowStats pattern where sessions are counted upon completion.
    """
    if not _ENABLED:
        return
    try:
        coll = await _ensure()
        if coll is None:
            return
            
        workflow_perf_id = f"perf_mon_{enterprise_id}_{workflow}"
        
        # Increment total_sessions count for this workflow
        await coll.update_one(
            {"_id": workflow_perf_id},
            {
                "$inc": {"total_sessions": 1},
                "$set": {"last_updated_ts": _dt.datetime.utcnow()},
            }
        )
        
        logger.debug(f"finalized chat performance chat_id={chat_id} workflow={workflow}")
        
    except Exception as e:  # pragma: no cover
        if _PERF_DEBUG:
            logger.debug(f"finalize_chat_performance failed chat_id={chat_id}: {e}")


async def compute_performance_averages(enterprise_id: str, workflow: str) -> None:
    """Compute and update average metrics for all agents in a workflow performance summary.
    
    This replicates the WorkflowStats rollup logic to calculate per-agent averages
    based on all sessions for each agent. Call this periodically or after session completion.
    """
    if not _ENABLED:
        return
    try:
        coll = await _ensure()
        if coll is None:
            return
            
        workflow_perf_id = f"perf_mon_{enterprise_id}_{workflow}"
        
        # Fetch the current workflow performance document
        workflow_doc = await coll.find_one({"_id": workflow_perf_id})
        if not workflow_doc or "agents" not in workflow_doc:
            return
            
        # Compute averages for each agent
        update_ops = {}
        for agent_name, agent_data in workflow_doc["agents"].items():
            total_turns = agent_data.get("turns", 0)
            if total_turns > 0:
                # Calculate averages based on total metrics
                avg_duration = agent_data.get("duration_sec", 0.0) / total_turns
                avg_prompt_tokens = agent_data.get("prompt_tokens", 0) / total_turns
                avg_completion_tokens = agent_data.get("completion_tokens", 0) / total_turns
                avg_total_tokens = agent_data.get("total_tokens", 0) / total_turns
                avg_cost_usd = agent_data.get("cost_usd", 0.0) / total_turns
                
                # Set the computed averages
                update_ops[f"agents.{agent_name}.avg_duration_sec"] = avg_duration
                update_ops[f"agents.{agent_name}.avg_prompt_tokens"] = avg_prompt_tokens
                update_ops[f"agents.{agent_name}.avg_completion_tokens"] = avg_completion_tokens
                update_ops[f"agents.{agent_name}.avg_total_tokens"] = avg_total_tokens
                update_ops[f"agents.{agent_name}.avg_cost_usd"] = avg_cost_usd
        
        if update_ops:
            await coll.update_one(
                {"_id": workflow_perf_id},
                {"$set": update_ops}
            )
            logger.debug(f"computed performance averages for workflow={workflow} agents={list(workflow_doc['agents'].keys())}")
            
    except Exception as e:  # pragma: no cover
        if _PERF_DEBUG:
            logger.debug(f"compute_performance_averages failed enterprise_id={enterprise_id} workflow={workflow}: {e}")


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
