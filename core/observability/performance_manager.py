"""Performance & Observability Manager with incremental token tracking (clean version)."""
from __future__ import annotations

import os, asyncio
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from datetime import datetime

import openlit
from opentelemetry import trace
from opentelemetry.metrics import get_meter
from opentelemetry.trace import Status, StatusCode

from logs.logging_config import (
    get_workflow_logger,
)
from core.core_config import get_free_trial_config
from core.data.persistence_manager import AG2PersistenceManager
from core.data.chat_sessions_data import ChatSessionsRepository

logger = get_workflow_logger("performance_manager")
perf_logger = get_workflow_logger("performance")
token_logger = get_workflow_logger("token_tracking")
tracer = trace.get_tracer(__name__)
meter = get_meter(__name__)

@dataclass
class PerformanceConfig:
    endpoint: str = "http://localhost:4317"
    service_name: str = "mozaiks-ai"
    service_version: str = "1.0.0"
    environment: str = "production"
    flush_interval_sec: int = 0
    enabled: bool = True
    auto_disable_on_failure: bool = True
    connection_test_timeout_sec: float = 0.6

@dataclass
class ChatPerfState:
    chat_id: str
    enterprise_id: str
    workflow_name: str
    user_id: str
    started_at: datetime = field(default_factory=datetime.utcnow)
    ended_at: Optional[datetime] = None
    trace_id: Optional[str] = None
    agent_turns: int = 0
    tool_calls: int = 0
    errors: int = 0
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_cost: float = 0.0
    last_model: Optional[str] = None
    total_turn_duration_sec: float = 0.0
    last_turn_duration_sec: Optional[float] = None
    max_turn_duration_sec: Optional[float] = None
    latency_by_agent: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        avg = (self.total_turn_duration_sec / self.agent_turns) if self.agent_turns else 0.0
        trimmed_agents = {
            a: {
                "count": int(agg.get("count", 0)),
                "avg_sec": (float(agg.get("total_sec", 0.0)) / max(1, int(agg.get("count", 0))))
            }
            for a, agg in (self.latency_by_agent or {}).items()
        }
        return {
            "chat_id": self.chat_id,
            "enterprise_id": self.enterprise_id,
            "workflow_name": self.workflow_name,
            "user_id": self.user_id,
            "trace_id": self.trace_id,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "runtime_sec": ((self.ended_at or datetime.utcnow()) - self.started_at).total_seconds(),
            "counts": {"agent_turns": self.agent_turns, "tool_calls": self.tool_calls, "errors": self.errors},
            "tokens": {
                "total_tokens": self.total_tokens,
                "prompt_tokens": self.prompt_tokens,
                "completion_tokens": self.completion_tokens,
                "total_cost": self.total_cost,
                "last_model": self.last_model,
            },
            "latency": {
                "last_turn_duration_sec": self.last_turn_duration_sec,
                "avg_turn_duration_sec": avg,
                "max_turn_duration_sec": self.max_turn_duration_sec,
                "turn_count": self.agent_turns,
                "latency_by_agent": trimmed_agents,
            },
        }

class PerformanceManager:
    def __init__(self, config: Optional[PerformanceConfig] = None):
        self.config = config or PerformanceConfig()
        self.initialized = False
        self._states: Dict[str, ChatPerfState] = {}
        self._lock = asyncio.Lock()
        self._flush_task: Optional[asyncio.Task] = None
        self._persistence = AG2PersistenceManager()
        self._repo = ChatSessionsRepository(self._persistence.persistence)
        self._last_debited = {}
        self._token_counter = None
        self._agent_turn_duration = None
        self._workflow_duration = None
        self._tool_call_counter = None
        self._error_counter = None
        logger.info("PerformanceManager configured")

    async def initialize(self):
        if self.initialized:
            return
        try:
            # Allow overriding the OTEL endpoint via env for containerized runs
            env_ep = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
            if env_ep:
                self.config.endpoint = env_ep
            env_enabled = os.getenv("OPENLIT_ENABLED", "true").lower() not in ("0", "false", "no")
            if not env_enabled or not self.config.enabled:
                self.initialized = True
                logger.info("OpenLIT/OTel disabled")
                return
            # Optional basic connectivity test to avoid noisy stack traces if no collector
            if self.config.auto_disable_on_failure:
                try:
                    import socket, urllib.parse
                    parsed = urllib.parse.urlparse(self.config.endpoint)
                    host = parsed.hostname or "localhost"
                    port = parsed.port or (4317 if parsed.scheme.startswith("http") else 4317)
                    with socket.create_connection((host, port), timeout=self.config.connection_test_timeout_sec):
                        pass
                except Exception as _conn_err:
                    logger.warning(
                        f"OTel endpoint {self.config.endpoint} unreachable ({_conn_err}) – disabling instrumentation to prevent log noise"
                    )
                    self.config.enabled = False
                    self.initialized = True
                    os.environ["OTEL_TRACES_EXPORTER"] = "none"
                    return

            os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = self.config.endpoint
            # If endpoint is HTTP (4318) ensure signals default to http/protobuf to avoid gRPC mismatch
            if ":4318" in self.config.endpoint or self.config.endpoint.startswith("http://") or self.config.endpoint.startswith("https://"):
                os.environ.setdefault("OTEL_EXPORTER_OTLP_PROTOCOL", "http/protobuf")
                os.environ.setdefault("OTEL_EXPORTER_OTLP_TRACES_PROTOCOL", "http/protobuf")
                os.environ.setdefault("OTEL_EXPORTER_OTLP_METRICS_PROTOCOL", "http/protobuf")
                os.environ.setdefault("OTEL_EXPORTER_OTLP_LOGS_PROTOCOL", "http/protobuf")
            os.environ["OTEL_SERVICE_NAME"] = self.config.service_name
            os.environ["OTEL_RESOURCE_ATTRIBUTES"] = f"deployment.environment={self.config.environment},service.version={self.config.service_version}"
            openlit.init()
            self._token_counter = meter.create_counter("mozaiks_tokens_total", description="Total tokens", unit="tokens")
            self._agent_turn_duration = meter.create_histogram("mozaiks_agent_turn_duration", description="Agent turn duration", unit="s")
            self._workflow_duration = meter.create_histogram("mozaiks_workflow_duration", description="Workflow duration", unit="s")
            self._tool_call_counter = meter.create_counter("mozaiks_tool_calls_total", description="Tool calls", unit="calls")
            self._error_counter = meter.create_counter("mozaiks_errors_total", description="Errors", unit="errors")
            self.initialized = True
            logger.info("OpenLIT initialized")
            if self.config.flush_interval_sec > 0:
                self._flush_task = asyncio.create_task(self._periodic_flush())
        except Exception as e:
            logger.error(f"Perf init failed: {e}", exc_info=True)

    async def _periodic_flush(self):
        while True:
            await asyncio.sleep(self.config.flush_interval_sec)
            try:
                async with self._lock:
                    ids = list(self._states.keys())
                for cid in ids:
                    await self.flush(cid)
            except Exception as e:
                logger.debug(f"flush cycle error: {e}")

    async def record_workflow_start(self, chat_id: str, enterprise_id: str, workflow_name: str, user_id: str):
        async with self._lock:
            if chat_id not in self._states:
                self._states[chat_id] = ChatPerfState(chat_id, enterprise_id, workflow_name, user_id)
        # Ensure a ChatSessions doc exists for this chat
        try:
            await self._persistence.create_chat_session(chat_id, enterprise_id, workflow_name, user_id)
        except Exception:
            pass
        perf_logger.info("workflow_start", chat_id=chat_id, workflow=workflow_name, enterprise_id=enterprise_id)

    async def attach_trace_id(self, chat_id: str, trace_id: str):
        async with self._lock:
            st = self._states.get(chat_id)
            if st:
                st.trace_id = trace_id
        try:
            await self._repo.update_fields(chat_id=chat_id, fields={"trace_id": trace_id, "real_time_tracking.trace_id": trace_id})
        except Exception:
            pass

    async def record_agent_turn(self, chat_id: str, agent_name: str, duration_sec: float, model: Optional[str], prompt_tokens: int = 0, completion_tokens: int = 0, cost: float = 0.0):
        with tracer.start_as_current_span("agent_turn") as span:
            span.set_attributes({"chat_id": chat_id, "agent_name": agent_name, "model": model or "unknown", "duration_sec": duration_sec})
            if (prompt_tokens + completion_tokens) > 0 and self._token_counter:
                total = prompt_tokens + completion_tokens
                self._token_counter.add(total, {"token_type": "total", "agent_name": agent_name, "chat_id": chat_id})
                self._token_counter.add(prompt_tokens, {"token_type": "prompt", "agent_name": agent_name, "chat_id": chat_id})
                self._token_counter.add(completion_tokens, {"token_type": "completion", "agent_name": agent_name, "chat_id": chat_id})
            if self._agent_turn_duration:
                self._agent_turn_duration.record(duration_sec, {"agent_name": agent_name, "chat_id": chat_id})
            async with self._lock:
                st = self._states.get(chat_id)
                if not st:
                    span.set_status(Status(StatusCode.ERROR, "missing_state"))
                    return
                st.agent_turns += 1
                st.last_turn_duration_sec = duration_sec
                st.total_turn_duration_sec += max(0.0, duration_sec)
                if st.max_turn_duration_sec is None or duration_sec > st.max_turn_duration_sec:
                    st.max_turn_duration_sec = duration_sec
                if prompt_tokens or completion_tokens:
                    st.prompt_tokens += prompt_tokens
                    st.completion_tokens += completion_tokens
                    st.total_tokens += (prompt_tokens + completion_tokens)
                    st.total_cost += cost
                    st.last_model = model or st.last_model
                akey = (agent_name or "agent").replace(".", "_")[:64]
                agg = st.latency_by_agent.get(akey, {"count": 0, "total_sec": 0.0})
                agg["count"] += 1
                agg["total_sec"] += max(0.0, duration_sec)
                st.latency_by_agent[akey] = agg
                trimmed_agents = {a: {"count": int(v.get("count", 0)), "avg_sec": (float(v.get("total_sec", 0.0)) / max(1, int(v.get("count", 0))))} for a, v in st.latency_by_agent.items()}
                latency_doc = {
                    "last_turn_duration_sec": st.last_turn_duration_sec,
                    "avg_turn_duration_sec": (st.total_turn_duration_sec / st.agent_turns) if st.agent_turns else 0.0,
                    "max_turn_duration_sec": st.max_turn_duration_sec,
                    "turn_count": st.agent_turns,
                    "latency_by_agent": trimmed_agents,
                }
            span.set_status(Status(StatusCode.OK))
        perf_logger.info(
            "agent_turn",
            metric_name="agent_turn",
            value=float(duration_sec),
            unit="s",
            chat_id=chat_id,
            agent=agent_name,
        )
        try:
            await self._repo.update_fields(chat_id=chat_id, fields={"real_time_tracking.latency": latency_doc, "real_time_tracking.tokens.last_model": model})
        except Exception:
            pass

    async def record_final_token_usage(self, chat_id: str, usage_summary: Dict[str, Any]) -> None:
        with tracer.start_as_current_span("record_final_token_usage") as span:
            try:
                total_tokens = prompt_tokens = completion_tokens = 0
                total_cost = usage_summary.get("total_cost", 0.0)
                usage_details = usage_summary.get("usage", []) if isinstance(usage_summary, dict) else []
                if not isinstance(usage_details, list):
                    usage_details = []
                for ud in usage_details:
                    if isinstance(ud, dict):
                        total_tokens += ud.get("total_tokens", 0)
                        prompt_tokens += ud.get("prompt_tokens", 0)
                        completion_tokens += ud.get("completion_tokens", 0)
                async with self._lock:
                    st = self._states.get(chat_id)
                    if st:
                        st.total_tokens = total_tokens
                        st.prompt_tokens = prompt_tokens
                        st.completion_tokens = completion_tokens
                        st.total_cost = total_cost
                        last_model = st.last_model
                        has_incremental = (st.total_tokens > 0)
                    else:
                        last_model = None
                        has_incremental = False
                await self._repo.update_fields(chat_id=chat_id, fields={
                    "real_time_tracking.tokens.total_tokens": total_tokens,
                    "real_time_tracking.tokens.prompt_tokens": prompt_tokens,
                    "real_time_tracking.tokens.completion_tokens": completion_tokens,
                    "real_time_tracking.tokens.total_cost": total_cost,
                    "real_time_tracking.tokens.last_model": last_model,
                    # Mark incremental_debits true if any tokens recorded during the run
                    "real_time_tracking.tokens.incremental_debits": bool(has_incremental),
                    "real_time_tracking.last_usage_recorded_at": datetime.utcnow(),
                })
                span.set_status(Status(StatusCode.OK))
            except Exception as e:
                span.record_exception(e)
                span.set_status(Status(StatusCode.ERROR, str(e)))
                logger.error(f"final token usage failed: {e}", exc_info=True)

    async def record_tool_call(self, chat_id: str, tool_name: str, duration_sec: float, success: bool, error_type: Optional[str] = None):
        with tracer.start_as_current_span("tool_call") as span:
            span.set_attributes({"chat_id": chat_id, "tool_name": tool_name, "duration_sec": duration_sec, "success": success, "error_type": error_type or "none"})
            if self._tool_call_counter:
                self._tool_call_counter.add(1, {"tool_name": tool_name, "success": str(success), "chat_id": chat_id})
            if not success and self._error_counter:
                self._error_counter.add(1, {"error_type": error_type or "tool_call_failed", "tool_name": tool_name, "chat_id": chat_id})
            async with self._lock:
                st = self._states.get(chat_id)
                if not st:
                    span.set_status(Status(StatusCode.ERROR, "missing_state"))
                    return
                st.tool_calls += 1
                if not success:
                    st.errors += 1
            span.set_status(Status(StatusCode.OK if success else StatusCode.ERROR))
        perf_logger.info("tool_call", chat_id=chat_id, tool=tool_name, duration_sec=duration_sec, success=success, error_type=error_type)

    async def record_token_usage(self, chat_id: str, prompt_tokens: int, completion_tokens: int, model: Optional[str] = None, cost: float = 0.0):
        async with self._lock:
            st = self._states.get(chat_id)
            if not st:
                return
            st.prompt_tokens += prompt_tokens
            st.completion_tokens += completion_tokens
            delta = prompt_tokens + completion_tokens
            st.total_tokens += delta
            st.total_cost += cost
            if model:
                st.last_model = model
            prev_total = self._last_debited.get(chat_id, 0)
            to_debit = st.total_tokens - prev_total
        perf_logger.debug("token_update", chat_id=chat_id, delta=delta, to_debit=to_debit)
        # Token tracking: delta before debit
        try:
            token_logger.info(
                "token_tracking: delta_update",
                chat_id=chat_id,
                enterprise_id=st.enterprise_id if st else None,
                workflow_name=st.workflow_name if st else None,
                delta_total_tokens=max(0, delta),
                delta_prompt_tokens=max(0, prompt_tokens),
                delta_completion_tokens=max(0, completion_tokens),
                delta_cost=max(0.0, float(cost)),
                model=model,
                to_debit=max(0, to_debit),
            )
        except Exception:
            pass
        if to_debit > 0:
            try:
                async with self._lock:
                    st2 = self._states.get(chat_id)
                    enterprise_id = st2.enterprise_id if st2 else None
                    user_id = st2.user_id if st2 else None
                # Simple trial gating: if FREE_TRIAL_ENABLED, skip debiting wallet
                cfg = get_free_trial_config()
                trial_enabled = bool(cfg.get("enabled", False))
                if enterprise_id and user_id and not trial_enabled:
                    new_bal = await self._persistence.debit_tokens(
                        user_id, enterprise_id, to_debit, reason="perf_token_update", strict=False, meta={"chat_id": chat_id}
                    )
                    if new_bal is not None:
                        async with self._lock:
                            self._last_debited[chat_id] = self._states[chat_id].total_tokens
                        coll2 = await self._repo._coll()
                        await coll2.update_one({"chat_id": chat_id}, {"$set": {"real_time_tracking.tokens.remaining_balance": new_bal}})
                        # Token tracking: post-debit balance log only
                        try:
                            token_logger.info(
                                "token_tracking: post_debit",
                                chat_id=chat_id,
                                enterprise_id=enterprise_id,
                                user_id=user_id,
                                debited_tokens=max(0, to_debit),
                                remaining_balance=int(new_bal),
                            )
                        except Exception:
                            pass
            except Exception as e:
                logger.debug(f"wallet debit failed: {e}")

        # Persist latest cumulative totals and last delta for immediate visibility
        cum_total = cum_prompt = cum_completion = 0
        cum_cost = 0.0
        last_model = None
        try:
            async with self._lock:
                st_snap = self._states.get(chat_id)
                if not st_snap:
                    return
                cum_total = int(st_snap.total_tokens)
                cum_prompt = int(st_snap.prompt_tokens)
                cum_completion = int(st_snap.completion_tokens)
                cum_cost = float(st_snap.total_cost)
                last_model = st_snap.last_model
            coll3 = await self._repo._coll()
            await coll3.update_one(
                {"chat_id": chat_id},
                {"$set": {
                    "real_time_tracking.tokens.total_tokens": cum_total,
                    "real_time_tracking.tokens.prompt_tokens": cum_prompt,
                    "real_time_tracking.tokens.completion_tokens": cum_completion,
                    "real_time_tracking.tokens.total_cost": cum_cost,
                    "real_time_tracking.tokens.last_model": last_model,
                    "real_time_tracking.tokens.last_delta.total_tokens": max(0, delta),
                    "real_time_tracking.tokens.last_delta.prompt_tokens": max(0, prompt_tokens),
                    "real_time_tracking.tokens.last_delta.completion_tokens": max(0, completion_tokens),
                    "real_time_tracking.tokens.last_delta.total_cost": max(0.0, float(cost)),
                    "real_time_tracking.tokens.incremental_debits": True,
                    "real_time_tracking.last_usage_recorded_at": datetime.utcnow(),
                }}
            )
        except Exception as e:
            logger.debug(f"persist token delta failed: {e}")
        # Token tracking: cumulative snapshot persisted
        try:
            token_logger.info(
                "token_tracking: persisted_snapshot",
                chat_id=chat_id,
                cum_total_tokens=int(cum_total),
                cum_prompt_tokens=int(cum_prompt),
                cum_completion_tokens=int(cum_completion),
                cum_total_cost=float(cum_cost),
                last_model=last_model,
            )
        except Exception:
            pass

        # Emit a lightweight websocket token_update event (delta-based)
        try:
            from core.transport.simple_transport import SimpleTransport
            transport = SimpleTransport._get_instance()
            if transport:
                event_payload = {
                    "type": "token_update",
                    "data": {
                        "chat_id": chat_id,
                        "cumulative": {
                            "total_tokens": cum_total,
                            "prompt_tokens": cum_prompt,
                            "completion_tokens": cum_completion,
                            "total_cost": cum_cost,
                            "last_model": last_model,
                        },
                        "delta": {
                            "total_tokens": max(0, delta),
                            "prompt_tokens": max(0, prompt_tokens),
                            "completion_tokens": max(0, completion_tokens),
                            "total_cost": max(0.0, float(cost)),
                        },
                    },
                    "timestamp": datetime.utcnow().isoformat(),
                }
                await transport._broadcast_to_websockets(event_payload, chat_id)
        except Exception:
            # Never break the flow due to UI broadcast
            pass

    async def record_workflow_end(self, chat_id: str, status: str, termination_reason: Optional[str] = None):
        with tracer.start_as_current_span("workflow_end") as span:
            async with self._lock:
                st = self._states.get(chat_id)
                if not st:
                    span.set_status(Status(StatusCode.ERROR, "missing_state"))
                    return
                st.ended_at = datetime.utcnow()
                duration = (st.ended_at - st.started_at).total_seconds()
                span.set_attributes({
                    "chat_id": chat_id,
                    "status": status,
                    "termination_reason": termination_reason or "unknown",
                    "workflow_name": st.workflow_name,
                    "enterprise_id": st.enterprise_id,
                    "duration_sec": duration,
                    "total_tokens": st.total_tokens,
                    "agent_turns": st.agent_turns,
                    "tool_calls": st.tool_calls,
                    "errors": st.errors,
                })
                if self._workflow_duration:
                    self._workflow_duration.record(duration, {"workflow_name": st.workflow_name, "status": status, "enterprise_id": st.enterprise_id})
            span.set_status(Status(StatusCode.OK if status == "completed" else StatusCode.ERROR))
        perf_logger.info("workflow_end", chat_id=chat_id, status=status, termination_reason=termination_reason)
        await self.flush(chat_id)

    async def flush(self, chat_id: str):
        async with self._lock:
            st = self._states.get(chat_id)
            if not st:
                return
            snapshot = st.to_dict()
        perf_logger.info("perf_flush", chat_id=chat_id, **snapshot["tokens"], **snapshot["counts"])
        try:
            coll = await self._repo._coll()
            await coll.update_one(
                {"chat_id": chat_id},
                {"$set": {
                    "real_time_tracking.tokens": snapshot["tokens"],
                    "real_time_tracking.counts": snapshot["counts"],
                    "real_time_tracking.latency": snapshot.get("latency"),
                    "real_time_tracking.overall": {"runtime_sec": snapshot.get("runtime_sec")},
                    "real_time_tracking.last_flush_at": datetime.utcnow(),
                    "real_time_tracking.trace_id": snapshot.get("trace_id"),
                }}
            )
        except Exception:
            pass

_perf_instance: Optional[PerformanceManager] = None

async def get_performance_manager() -> PerformanceManager:
    global _perf_instance
    if _perf_instance is None:
        _perf_instance = PerformanceManager()
        await _perf_instance.initialize()
    return _perf_instance
