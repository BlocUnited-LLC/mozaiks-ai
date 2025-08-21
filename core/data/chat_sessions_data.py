from __future__ import annotations
from typing import TypedDict, Optional, Dict, List, Any
from datetime import datetime

# --- SCHEMA DEFINITIONS ---
class MessageDoc(TypedDict, total=False):
    sender: str
    agent_name: str
    content: str
    content_text: str
    content_json: Dict
    format: str  # "text" | "json" | "mixed"
    content_parts: List[Dict]
    role: str
    timestamp: datetime
    event_type: str
    event_id: str
    is_user_proxy: bool

class TokensLastDelta(TypedDict, total=False):
    total_tokens: int
    prompt_tokens: int
    completion_tokens: int
    total_cost: float

class Tokens(TypedDict, total=False):
    total_tokens: int
    prompt_tokens: int
    completion_tokens: int
    total_cost: float
    last_model: Optional[str]
    last_delta: TokensLastDelta
    remaining_balance: int
    incremental_debits: bool

class Counts(TypedDict, total=False):
    agent_turns: int
    tool_calls: int
    errors: int

class LatencyByAgentEntry(TypedDict, total=False):
    count: int
    avg_sec: float

class Latency(TypedDict, total=False):
    last_turn_duration_sec: Optional[float]
    avg_turn_duration_sec: float
    max_turn_duration_sec: Optional[float]
    turn_count: int
    latency_by_agent: Dict[str, LatencyByAgentEntry]

class Overall(TypedDict, total=False):
    runtime_sec: float

class RealTimeTracking(TypedDict, total=False):
    trace_id: Optional[str]
    tokens: Tokens
    counts: Counts
    latency: Latency
    overall: Overall
    last_usage_recorded_at: datetime
    last_flush_at: datetime

class UsageSummary(TypedDict, total=False):
    raw: Dict
    finalized_at: datetime

class ChatSession(TypedDict, total=False):
    chat_id: str
    enterprise_id: str
    user_id: str
    workflow_name: str
    status: str
    created_at: datetime
    last_updated_at: datetime
    completed_at: datetime
    termination_reason: str
    trace_id: str
    usage_summary: UsageSummary
    messages: List[MessageDoc]
    real_time_tracking: RealTimeTracking

# --- REPOSITORY ---
from core.data.persistence_manager import PersistenceManager

class ChatSessionsRepository:
    """Centralized writer for MozaiksAI.ChatSessions.

    All updates flow through update_fields(); filters by chat_id and optionally enterprise_id.
    """

    def __init__(self, persistence: Optional[PersistenceManager] = None):
        self._persistence = persistence or PersistenceManager()

    async def _coll(self):
        await self._persistence._ensure_client()
        return self._persistence.chat_sessions_collection

    async def update_fields(self, *, chat_id: str, fields: Dict[str, Any], enterprise_id: Optional[str] = None) -> None:
        filt: Dict[str, Any] = {"chat_id": chat_id}
        if enterprise_id:
            filt["enterprise_id"] = enterprise_id
        payload = {"$set": {**fields, "last_updated_at": datetime.utcnow()}}
        coll = await self._coll()
        await coll.update_one(filt, payload)

    async def push_message(self, *, chat_id: str, message: Dict[str, Any], enterprise_id: Optional[str] = None) -> None:
        filt: Dict[str, Any] = {"chat_id": chat_id}
        if enterprise_id:
            filt["enterprise_id"] = enterprise_id
        coll = await self._coll()
        await coll.update_one(filt, {"$push": {"messages": message}, "$set": {"last_updated_at": datetime.utcnow()}})

    async def mark_completed(self, *, chat_id: str, enterprise_id: str, termination_reason: str) -> bool:
        now = datetime.utcnow()
        coll = await self._coll()
        result = await coll.update_one(
            {"chat_id": chat_id, "enterprise_id": enterprise_id},
            {"$set": {"status": "completed", "termination_reason": termination_reason, "completed_at": now, "last_updated_at": now}}
        )
        return bool(getattr(result, "modified_count", 0))
