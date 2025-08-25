# chat_session_data.py
# Single-file module:
#   - Persistence (chat_sessions): raw session history, lifecycle, session wall-clock only (no performance fields)
#   - Performance (workflow_summaries schema + on-read builder): aggregates/averages for dashboards
# MongoDB, no wallet/billing writes here.

from __future__ import annotations
from typing import TypedDict, Required, NotRequired, Literal, List, Dict, Any, Optional
from datetime import datetime, timezone
from collections import defaultdict

# =========================
# ----- PERSISTENCE -------
# =========================

Role = Literal["user", "assistant"]
EventType = Literal["message.created"]  # extend only if you add more events
Status = Literal["created", "in_progress", "completed", "failed"]

class MessageDoc(TypedDict, total=False):
    """
    Raw message event stored in a chat session.
    NOTE: No performance fields (no latency_ms / duration_ms) by design.
    """
    role: Required[Role]
    content: Required[str]
    timestamp: Required[datetime]        # UTC-aware
    event_type: Required[EventType]      # "message.created"
    event_id: Required[str]              # unique per message event

    # Optional metadata (non-performance)
    is_user_proxy: NotRequired[bool]
    agent_name: NotRequired[str]         # required when role == "assistant"

class ChatSessionDoc(TypedDict, total=False):
    """
    Persistence-only session document.
    Contains lifecycle, identifiers, session wall-clock, and raw message stream.
    """
    _id: Required[str]                   # session id
    enterprise_id: Required[str]
    workflow_name: Required[str]
    user_id: Required[str]

    status: Required[Status]
    created_at: Required[datetime]       # UTC-aware
    last_updated_at: Required[datetime]  # UTC-aware
    completed_at: NotRequired[datetime]  # UTC-aware
    termination_reason: NotRequired[str]
    trace_id: NotRequired[str]

    # Session wall-clock (seconds) — kept as persistence metadata
    duration_sec: Required[float]

    # Event stream
    messages: Required[List[MessageDoc]]

# --------- Helpers & Guardrails ---------

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)

def _ensure_aware(ts: datetime) -> datetime:
    return ts if ts.tzinfo is not None else ts.replace(tzinfo=timezone.utc)

def validate_message_invariants(msg: MessageDoc) -> None:
    # event type
    if msg["event_type"] != "message.created":
        raise ValueError("event_type must be 'message.created' for MessageDoc.")
    # timestamp must be timezone-aware
    if msg["timestamp"].tzinfo is None:
        raise ValueError("timestamp must be timezone-aware (UTC).")
    # role vs agent_name
    role = msg["role"]
    has_agent = "agent_name" in msg and msg["agent_name"] is not None
    if role == "assistant" and not has_agent:
        raise ValueError("agent_name is required when role='assistant'.")
    if role == "user" and has_agent:
        raise ValueError("agent_name must be omitted when role='user'.")

def validate_session_invariants(doc: ChatSessionDoc) -> None:
    if doc["last_updated_at"] < doc["created_at"]:
        raise ValueError("last_updated_at cannot be earlier than created_at.")
    if "completed_at" in doc and doc["completed_at"] < doc["created_at"]:
        raise ValueError("completed_at cannot be earlier than created_at.")

def normalize_message(message: Dict[str, Any]) -> MessageDoc:
    """
    Accepts a loose message dict and returns a strict MessageDoc, applying defaults:
      - event_type defaults to 'message.created'
      - timestamp defaults to now (UTC)
      - role defaults: 'assistant' if agent_name present, else 'user'
      - event_id required; if missing, derive from time
      - content must be a string (persistence-friendly)
    """
    content = message.get("content")
    if not isinstance(content, str):
        raise ValueError("Message 'content' must be a string for persistence.")

    ts = message.get("timestamp")
    if not isinstance(ts, datetime):
        ts = _utcnow()
    else:
        ts = _ensure_aware(ts)

    event_type: EventType = message.get("event_type") or "message.created"
    agent_name = message.get("agent_name")
    role: Role = message.get("role") or ("assistant" if agent_name else "user")
    event_id = message.get("event_id") or f"evt-{int(ts.timestamp() * 1000)}"

    doc: MessageDoc = {
        "role": role,
        "content": content,
        "timestamp": ts,
        "event_type": event_type,
        "event_id": event_id,
    }
    if agent_name is not None:
        doc["agent_name"] = str(agent_name)
    if "is_user_proxy" in message:
        doc["is_user_proxy"] = bool(message["is_user_proxy"])

    # validate the normalized shape
    validate_message_invariants(doc)
    return doc

# -------- DAO (persistence) --------

def _chat_sessions(db):
    return db["chat_sessions"]

def create_session(*, db, session: ChatSessionDoc) -> None:
    """
    Insert a new session.
    - Ensure messages list and duration_sec exist (default [] and 0.0)
    - Set created_at / last_updated_at if missing
    - Validate invariants
    """
    doc = dict(session)
    doc.setdefault("messages", [])
    doc.setdefault("duration_sec", 0.0)

    created_at = doc.get("created_at", _utcnow())
    if isinstance(created_at, datetime):
        doc["created_at"] = _ensure_aware(created_at)
    else:
        doc["created_at"] = _utcnow()
    
    last_updated_at = doc.get("last_updated_at", doc["created_at"])
    if isinstance(last_updated_at, datetime):
        doc["last_updated_at"] = _ensure_aware(last_updated_at)
    else:
        doc["last_updated_at"] = doc["created_at"]
    if "completed_at" in doc and isinstance(doc["completed_at"], datetime):
        doc["completed_at"] = _ensure_aware(doc["completed_at"])

    validate_session_invariants(doc)  # type: ignore[arg-type]
    messages = doc.get("messages", [])
    if isinstance(messages, list):
        for m in messages:
            validate_message_invariants(m)

    _chat_sessions(db).insert_one(doc)

def get_session(*, db, session_id: str) -> Optional[ChatSessionDoc]:
    return _chat_sessions(db).find_one({"_id": session_id})

def append_message(
    *,
    db,
    session_id: str,
    message: MessageDoc,
    update_duration_sec: float | None = None
) -> None:
    """
    Append a message and update timestamps. Optionally max() in duration_sec.
    """
    # Normalize if needed (in case caller passed a loose dict)
    msg = message
    if not isinstance(msg.get("timestamp"), datetime):  # type: ignore[union-attr]
        msg = normalize_message(message)  # type: ignore[arg-type]
    validate_message_invariants(msg)

    update: Dict[str, Any] = {
        "$push": {"messages": msg},
        "$set": {"last_updated_at": _utcnow()},
    }
    if isinstance(update_duration_sec, (int, float)):
        update["$max"] = {"duration_sec": float(update_duration_sec)}

    _chat_sessions(db).update_one({"_id": session_id}, update)

def complete_session(
    *,
    db,
    session_id: str,
    termination_reason: str | None = None,
    completed_at: datetime | None = None
) -> None:
    """
    Mark a session completed; do not write any billing fields.
    """
    now = _utcnow()
    comp = _ensure_aware(completed_at) if isinstance(completed_at, datetime) else now
    _chat_sessions(db).update_one(
        {"_id": session_id},
        {
            "$set": {
                "status": "completed",
                "termination_reason": termination_reason or "completed",
                "completed_at": comp,
                "last_updated_at": now,
            }
        },
    )

# =================================================
# ------- PERFORMANCE (SCHEMAS + ON-READ ROLLUP) --
# =================================================

class AggregateAveragesDoc(TypedDict):
    avg_duration_sec: float          # wall-clock per session/agent
    avg_latency_ms: float            # kept 0.0 here (no latency persisted in chat_sessions)
    avg_prompt_tokens: int           # if you compute tokens elsewhere; keep 0 if unknown
    avg_completion_tokens: int
    avg_total_tokens: int
    avg_cost_total_usd: float

class ChatSessionStatsDoc(TypedDict):
    duration_sec: float
    avg_latency_ms: float            # 0.0 here unless enriched from metering/telemetry
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_total_usd: float

class AgentAggregateDoc(TypedDict):
    avg: AggregateAveragesDoc
    sessions: Dict[str, ChatSessionStatsDoc]  # keyed by chat session id

class OverallBlockDoc(TypedDict):
    avg: AggregateAveragesDoc
    sessions: Dict[str, ChatSessionStatsDoc]

class WorkflowSummaryDoc(TypedDict):
    _id: str
    enterprise_id: str
    workflow_name: str
    overall: OverallBlockDoc
    agents: Dict[str, AgentAggregateDoc]

def _zeros_agg() -> AggregateAveragesDoc:
    return {
        "avg_duration_sec": 0.0,
        "avg_latency_ms": 0.0,
        "avg_prompt_tokens": 0,
        "avg_completion_tokens": 0,
        "avg_total_tokens": 0,
        "avg_cost_total_usd": 0.0,
    }

def _zeros_stats() -> ChatSessionStatsDoc:
    return {
        "duration_sec": 0.0,
        "avg_latency_ms": 0.0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "cost_total_usd": 0.0,
    }

def compute_workflow_summary_on_read(
    *,
    db,
    enterprise_id: str,
    workflow_name: str
) -> WorkflowSummaryDoc:
    """
    Build a WorkflowSummaryDoc from chat_sessions on demand.
    - Since latency isn't persisted in chat_sessions, avg_latency_ms is 0.0 here.
    - Token/cost fields are left as 0 unless you enrich from another store.
    - No writes to chat_sessions; this is read-only aggregation.
    """
    cursor = _chat_sessions(db).find(
        {"enterprise_id": enterprise_id, "workflow_name": workflow_name},
        projection={"_id": 1, "messages": 1, "duration_sec": 1}
    )

    overall_sessions: Dict[str, ChatSessionStatsDoc] = {}
    # Agent -> (session_id -> stats)
    agent_sessions: Dict[str, Dict[str, ChatSessionStatsDoc]] = defaultdict(dict)

    # For averages
    overall_durations: List[float] = []
    agent_duration_sum: Dict[str, float] = defaultdict(float)
    agent_session_counts: Dict[str, int] = defaultdict(int)

    for doc in cursor:
        sid = doc["_id"]
        duration_sec = float(doc.get("duration_sec", 0.0))
        msgs: List[MessageDoc] = doc.get("messages", [])

        # Session-level stats
        overall_sessions[sid] = {
            **_zeros_stats(),
            "duration_sec": duration_sec,
            "avg_latency_ms": 0.0,  # no latency persisted here
        }
        overall_durations.append(duration_sec)

        # Per-agent participation (duration carried from session; latency 0.0)
        seen_agents = set(
            m["agent_name"] for m in msgs if "agent_name" in m and m["agent_name"] is not None
        )
        for agent in seen_agents:
            agent_sessions[agent][sid] = {
                **_zeros_stats(),
                "duration_sec": duration_sec,
                "avg_latency_ms": 0.0,
            }
            agent_duration_sum[agent] += duration_sec
            agent_session_counts[agent] += 1

    # Build overall averages
    overall_avg = _zeros_agg()
    if overall_sessions:
        n = len(overall_sessions)
        overall_avg["avg_duration_sec"] = sum(overall_durations) / n if n else 0.0
        overall_avg["avg_latency_ms"] = 0.0  # not tracked in persistence

    # Build agent averages
    agents_block: Dict[str, AgentAggregateDoc] = {}
    for agent, sess_map in agent_sessions.items():
        n = agent_session_counts.get(agent, 0)
        avg_block = _zeros_agg()
        if n:
            avg_block["avg_duration_sec"] = agent_duration_sum[agent] / n
            avg_block["avg_latency_ms"] = 0.0
        agents_block[agent] = {"avg": avg_block, "sessions": sess_map}

    summary: WorkflowSummaryDoc = {
        "_id": f"wf_{enterprise_id}_{workflow_name}_summary",
        "enterprise_id": enterprise_id,
        "workflow_name": workflow_name,
        "overall": {"avg": overall_avg, "sessions": overall_sessions},
        "agents": agents_block,
    }
    return summary

# ================
# Index helpers
# ================

def ensure_indexes(db) -> None:
    """
    Create recommended indexes. Call once at startup.
    """
    cs = _chat_sessions(db)
    cs.create_index([("workflow_name", 1), ("created_at", -1)])
    cs.create_index([("enterprise_id", 1), ("user_id", 1), ("created_at", -1)])
    cs.create_index([("status", 1), ("created_at", -1)])
    cs.create_index([("trace_id", 1)])
    # If you implement message buckets, create those indexes in that module:
    # message_buckets.create_index([("chat_id", 1), ("bucket_index", 1)], unique=True)
    # message_buckets.create_index([("chat_id", 1), ("open", 1)])
