from __future__ import annotations
"""Lean Performance Manager aligned with new chat_sessions schema.

Removes heavy real_time_tracking persistence; only maintains minimal in-memory
metrics and updates session duration / a few flattened usage fields.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, Optional, List

from opentelemetry import trace
from core.observability.otel_helpers import timed_span, ensure_telemetry_initialized, get_duration_hist
from logs.logging_config import get_workflow_logger
from core.data.persistence_manager import AG2PersistenceManager
from autogen import gather_usage_summary

logger = get_workflow_logger("performance_manager")

logger = get_workflow_logger("performance_manager")
perf_logger = get_workflow_logger("performance")
tracer = trace.get_tracer(__name__)

class InsufficientTokensError(Exception):
    pass

@dataclass
class PerformanceConfig:
    flush_interval_sec: int = 0
    enabled: bool = True

@dataclass
class ChatPerfState:
    chat_id: str
    enterprise_id: str
    workflow_name: str
    user_id: str
    started_at: datetime = field(default_factory=datetime.utcnow)
    ended_at: Optional[datetime] = None
    agent_turns: int = 0
    tool_calls: int = 0
    errors: int = 0
    last_turn_duration_sec: Optional[float] = None

class PerformanceManager:
    def __init__(self, config: Optional[PerformanceConfig] = None):
        self.config = config or PerformanceConfig()
        self._states: Dict[str, ChatPerfState] = {}
        self._lock = asyncio.Lock()
        self._flush_task: Optional[asyncio.Task] = None
        self._persistence = AG2PersistenceManager()
        self._chat_coll = None
        self._agent_turn_duration = None
        self._workflow_duration = None
        self.initialized = False
        self._billed_totals: Dict[str, int] = {}

    async def _get_coll(self):
        if self._chat_coll is None:
            await self._persistence.persistence._ensure_client()
            client = self._persistence.persistence.client
            if client is None:
                raise RuntimeError("Mongo client unavailable")
            self._chat_coll = client["MozaiksAI"]["chat_sessions"]
        return self._chat_coll

    async def initialize(self):
        if self.initialized:
            return
        ensure_telemetry_initialized(
            endpoint="http://localhost:4317",
            service_name="mozaiks-ai",
            environment="dev",
            service_version="1.0.0",
            auto_disable_on_failure=True,
            connection_test_timeout_sec=0.3,
            enabled=self.config.enabled,
        )
        self._agent_turn_duration = get_duration_hist("agent_turn", "Agent turn duration")
        self._workflow_duration = get_duration_hist("workflow_duration", "Workflow duration")
        if self.config.flush_interval_sec > 0:
            self._flush_task = asyncio.create_task(self._periodic_flush())
        self.initialized = True

    async def _periodic_flush(self):
        while True:
            await asyncio.sleep(self.config.flush_interval_sec)
            async with self._lock:
                ids = list(self._states.keys())
            for cid in ids:
                await self.flush(cid)

    async def record_workflow_start(self, chat_id: str, enterprise_id: str, workflow_name: str, user_id: str):
        async with self._lock:
            if chat_id not in self._states:
                self._states[chat_id] = ChatPerfState(chat_id, enterprise_id, workflow_name, user_id)
        # Ensure lean session doc exists
        coll = await self._get_coll()
        now = datetime.utcnow()
        await coll.update_one(
            {"_id": chat_id, "enterprise_id": enterprise_id},
            {"$setOnInsert": {
                "_id": chat_id,
                "enterprise_id": enterprise_id,
                "workflow_name": workflow_name,
                "user_id": user_id,
                "status": "in_progress",
                "created_at": now,
                "last_updated_at": now,
                "duration_sec": 0.0,
                "messages": []
            }},
            upsert=True,
        )
        perf_logger.info("workflow_start", chat_id=chat_id, workflow=workflow_name)

    async def attach_trace_id(self, chat_id: str, trace_id: str):
        coll = await self._get_coll()
        await coll.update_one({"_id": chat_id}, {"$set": {"trace_id": trace_id}})

    async def record_agent_turn(self, chat_id: str, agent_name: str, duration_sec: float, model: Optional[str], prompt_tokens: int = 0, completion_tokens: int = 0, cost: float = 0.0):
        with timed_span("agent_turn", attributes={"chat_id": chat_id}):
            async with self._lock:
                st = self._states.get(chat_id)
                if not st:
                    return
                st.agent_turns += 1
                st.last_turn_duration_sec = duration_sec
            if self._agent_turn_duration:
                self._agent_turn_duration.record(duration_sec, {"chat_id": chat_id})
            coll = await self._get_coll()
            await coll.update_one({"_id": chat_id}, {"$set": {"last_updated_at": datetime.utcnow()}})

    async def record_tool_call(self, chat_id: str, tool_name: str, duration_sec: float, success: bool, error_type: Optional[str] = None):
        async with self._lock:
            st = self._states.get(chat_id)
            if st:
                st.tool_calls += 1
                if not success:
                    st.errors += 1

    async def record_workflow_end(self, chat_id: str, status: str, termination_reason: Optional[str] = None):
        async with self._lock:
            st = self._states.get(chat_id)
            if not st:
                return
            st.ended_at = datetime.utcnow()
        if self._workflow_duration:
            duration = (st.ended_at - st.started_at).total_seconds()  # type: ignore[name-defined]
            self._workflow_duration.record(duration, {"workflow_name": st.workflow_name, "status": status})
        await self.flush(chat_id)

    async def flush(self, chat_id: str):
        async with self._lock:
            st = self._states.get(chat_id)
            if not st:
                return
            runtime_sec = ((st.ended_at or datetime.utcnow()) - st.started_at).total_seconds()
        coll = await self._get_coll()
        await coll.update_one({"_id": chat_id}, {"$set": {"duration_sec": runtime_sec, "last_updated_at": datetime.utcnow()}})

    # Simplified billing (delta tokens) kept for compatibility with existing calls
    def _fold_usage(self, summary: dict) -> int:
        if not isinstance(summary, dict):
            return 0
        total = 0
        for model, data in summary.items():
            if model == "total_cost" or not isinstance(data, dict):
                continue
            tt = data.get("total_tokens")
            if isinstance(tt, int):
                total += tt
            else:
                total += int(data.get("prompt_tokens", 0)) + int(data.get("completion_tokens", 0))
        return total

    async def bill_usage_from_print_summary(self, chat_id: str, enterprise_id: str, user_id: str, agents: List[Any]) -> int:
        try:
            summary = gather_usage_summary(agents)
        except Exception:
            return 0
        current = summary.get("usage_including_cached_inference") or {}
        cumulative = self._fold_usage(current)
        last = self._billed_totals.get(chat_id, 0)
        delta = max(0, cumulative - last)
        self._billed_totals[chat_id] = cumulative
        return delta

    async def record_final_usage_from_agents(self, chat_id: str, enterprise_id: str, user_id: str, agents: List[Any]) -> None:
        try:
            summary = gather_usage_summary(agents)
        except Exception:
            return
        current = summary.get("usage_including_cached_inference") or {}
        cumulative = self._fold_usage(current)
        self._billed_totals[chat_id] = cumulative
        coll = await self._get_coll()
        await coll.update_one({"_id": chat_id}, {"$set": {"usage_total_tokens_final": cumulative, "last_updated_at": datetime.utcnow()}})

_perf_instance: Optional[PerformanceManager] = None

async def get_performance_manager() -> PerformanceManager:
    global _perf_instance
    if _perf_instance is None:
        _perf_instance = PerformanceManager()
        await _perf_instance.initialize()
    return _perf_instance
