# ==============================================================================
# FILE: core/transport/ui_event_processor.py
# DESCRIPTION: AG2-compliant event processor following AsyncEventProcessorProtocol
# ==============================================================================

import logging
import asyncio
import inspect
import traceback
import uuid
import time
import re
from typing import Any, Optional, cast

from autogen.events import BaseEvent
from autogen.events.agent_events import InputRequestEvent, TextEvent
from autogen.events.client_events import UsageSummaryEvent
from autogen.io.run_response import AsyncRunResponseProtocol

from core.data.persistence_manager import AG2PersistenceManager
from logs.logging_config import get_workflow_logger
from core.observability.performance_manager import get_performance_manager


class UIEventProcessor:
    """
    AG2-compliant event processor that follows AsyncEventProcessorProtocol pattern.
    Routes events to the UI and handles persistence, following AG2 best practices.
    """

    def __init__(self, chat_id: str, enterprise_id: str, user_id: str, workflow_name: str):
        # Core identifiers
        self.chat_id = chat_id
        self.enterprise_id = enterprise_id
        self.user_id = user_id
        self.workflow_name = workflow_name
        # Logging and persistence (include workflow/chat context so breadcrumbs go to workflows.log)
        self.logger = get_workflow_logger(
            self.workflow_name,
            chat_id=self.chat_id,
            enterprise_id=self.enterprise_id,
            component="ui_event_processor",
        )
        self.persistence_manager = AG2PersistenceManager()

        # Lazy-initialized performance manager (async accessor)
        self._perf_mgr = None

        # Latency tracking for agent outputs
        self._turn_active = False
        self._turn_started_at = None  # perf_counter()
        self._turn_agent_name = None

        # Cumulative token snapshot to compute deltas from UsageSummaryEvent
        self._cum_prompt_tokens = 0
        self._cum_completion_tokens = 0
        self._cum_total_tokens = 0
        self._cum_total_cost = 0.0
        # Some providers emit only total or only actual. We track which we last used.
        self._last_usage_mode = None  # 'total' | 'actual'

    async def process(self, response: "AsyncRunResponseProtocol") -> None:
        """
        Optional helper to iterate the response events.
        """
        if self._perf_mgr is None:
            self._perf_mgr = await get_performance_manager()
        await self._perf_mgr.record_workflow_start(
            chat_id=self.chat_id,
            enterprise_id=self.enterprise_id,
            workflow_name=self.workflow_name,
            user_id=self.user_id,
        )
        async for event in response.events:
            await self.process_event(event)

    async def process_event(self, event: BaseEvent) -> None:
        """
        Process individual AG2 events, persisting and forwarding them to the UI.
        """
        event_type_name = type(event).__name__
        self.logger.debug(f"🔄 Processing event: {event_type_name} for chat {self.chat_id}")

        try:
            # -1. Pre-sanitize: resolve coroutine/awaitable content to concrete values
            try:
                if hasattr(event, "content"):
                    resolved = await self._resolve_maybe_awaitable(getattr(event, "content"))
                    if resolved is not getattr(event, "content"):
                        try:
                            setattr(event, "content", resolved)
                        except Exception:
                            pass
            except Exception as _resolve_err:
                self.logger.debug(f"content resolver skipped: {_resolve_err}")

            # 0. Agent turn timing: start on TextEvent; switch closes previous turn
            if isinstance(event, TextEvent):
                agent = self._infer_agent_name(event) or "unknown"
                now = time.perf_counter()
                if not self._turn_active:
                    self._turn_active = True
                    self._turn_started_at = now
                    self._turn_agent_name = agent
                    # Breadcrumb: mark that a turn started (no message content)
                    try:
                        self.logger.info("turn_summary started", agent_name=agent, status="started")
                    except Exception:
                        pass
                elif self._turn_agent_name and agent != self._turn_agent_name:
                    # Close previous turn
                    try:
                        duration = max(0.0, now - (self._turn_started_at or now))
                        if self._perf_mgr is None:
                            self._perf_mgr = await get_performance_manager()
                        await self._perf_mgr.record_agent_turn(
                            chat_id=self.chat_id,
                            agent_name=self._turn_agent_name,
                            duration_sec=duration,
                            model=None,
                        )
                        # Breadcrumb: mark completed turn without exposing content
                        try:
                            self.logger.info("turn_summary", agent_name=self._turn_agent_name, duration_seconds=duration, status="completed")
                        except Exception:
                            pass
                    except Exception as e:
                        self.logger.debug(f"record_agent_turn failed: {e}")
                    # Start new turn window
                    self._turn_started_at = now
                    self._turn_agent_name = agent

            # 1. Persist the event in real-time (save_event handles TextEvent; no-op for others)
            try:
                await self.persistence_manager.save_event(
                    event=event,
                    chat_id=self.chat_id,
                    enterprise_id=self.enterprise_id,
                    workflow_name=self.workflow_name,
                    user_id=self.user_id,
                )
            except Exception as pe:
                self.logger.debug(f"save_event failed: {pe}")

            # 1.5 Usage + Latency: UsageSummaryEvent carries model + token counts.
            if isinstance(event, UsageSummaryEvent):
                try:
                    if self._perf_mgr is None:
                        self._perf_mgr = await get_performance_manager()

                    model, p, c, t, total_cost = self._parse_usage_summary_event(event)

                    # Compute deltas against cumulative counters
                    delta_p = max(0, p - self._cum_prompt_tokens)
                    delta_c = max(0, c - self._cum_completion_tokens)
                    delta_t = max(0, t - self._cum_total_tokens)
                    prev_total_cost = float(self._cum_total_cost or 0.0)
                    delta_cost = max(0.0, float(total_cost or 0.0) - prev_total_cost)

                    # Update cumulative snapshots
                    self._cum_prompt_tokens = max(self._cum_prompt_tokens, p)
                    self._cum_completion_tokens = max(self._cum_completion_tokens, c)
                    self._cum_total_tokens = max(self._cum_total_tokens, t)
                    self._cum_total_cost = max(prev_total_cost, float(total_cost or 0.0))

                    # Record token deltas immediately for wallet + UI token_update
                    if delta_t > 0 or delta_cost > 0.0:
                        await self._perf_mgr.record_token_usage(
                            chat_id=self.chat_id,
                            prompt_tokens=delta_p,
                            completion_tokens=delta_c,
                            model=model,
                            cost=delta_cost,
                        )

                    # If provider marked this as total aggregate, persist final snapshot
                    mode = getattr(event, "mode", None) or getattr(event, "usage_type", None)
                    if isinstance(mode, str) and mode.lower() == "total":
                        summary_dict = {
                            "total_tokens": t,
                            "prompt_tokens": p,
                            "completion_tokens": c,
                            "total_cost": float(total_cost or 0.0),
                            "model": model,
                        }
                        await self._perf_mgr.record_final_token_usage(self.chat_id, summary_dict)
                        await self.persistence_manager.save_usage_summary(
                            summary=summary_dict,
                            chat_id=self.chat_id,
                            enterprise_id=self.enterprise_id,
                            user_id=self.user_id,
                            workflow_name=self.workflow_name,
                        )

                    # Close the active turn on usage summary (end of output)
                    if self._turn_active:
                        duration_sec = 0.0
                        if self._turn_started_at is not None:
                            duration_sec = max(0.0, time.perf_counter() - self._turn_started_at)
                        agent_name = self._turn_agent_name or self._infer_agent_name(event) or "agent"
                        await self._perf_mgr.record_agent_turn(
                            chat_id=self.chat_id,
                            agent_name=agent_name,
                            duration_sec=duration_sec,
                            model=model,
                        )
                        # Breadcrumb: end-of-output turn summary (no content)
                        try:
                            self.logger.info("turn_summary", agent_name=agent_name, duration_seconds=duration_sec, status="completed")
                        except Exception:
                            pass
                        self._turn_active = False
                        self._turn_started_at = None
                        self._turn_agent_name = None
                except Exception as e:
                    self.logger.debug(f"usage processing failed: {e}")

            # 2. Handle specific events for UI interaction or filtering
            if isinstance(event, InputRequestEvent):
                await self._handle_input_request(event)
                return  # Stop processing here, as it's handled

            # Filter out internal or noisy events that shouldn't go to the UI
            if event_type_name in ["GroupChatRunChatEvent", "PrintEvent"]:
                self.logger.debug(f"🔇 Skipping internal/noisy event for UI: {event_type_name}")
                return

            # 2.5 Performance hooks (best-effort for tool detection)
            try:
                if self._perf_mgr is None:
                    self._perf_mgr = await get_performance_manager()
                tool_name = self._infer_tool_name(event)
                if tool_name:
                    await self._perf_mgr.record_tool_call(
                        chat_id=self.chat_id,
                        tool_name=tool_name,
                        duration_sec=0.0,
                        success=True,
                    )
            except Exception as hook_err:
                self.logger.debug(f"perf hook skipped: {hook_err}")

            # 3. Forward events to the UI
            from core.transport.simple_transport import SimpleTransport
            transport = SimpleTransport._get_instance()
            if transport:
                if isinstance(event, TextEvent):
                    try:
                        agent_name = self._turn_agent_name or self._infer_agent_name(event) or "Assistant"
                        clean_content = self._extract_clean_content(getattr(event, "content", ""))
                        if clean_content:
                            await transport.send_to_ui(
                                message=clean_content,
                                agent_name=agent_name,
                                chat_id=self.chat_id,
                                message_type="chat_message",
                                bypass_filter=False,
                            )
                    except Exception as chat_err:
                        self.logger.debug(f"text forward skipped: {chat_err}")
                try:
                    await transport.send_event_to_ui(event, self.chat_id)
                except Exception:
                    pass

        except Exception as e:
            self.logger.error(f"❌ Failed during event processing for {event_type_name}: {e}\n{traceback.format_exc()}")

    async def _resolve_maybe_awaitable(self, value: Any) -> Any:
        """Resolve awaitables/coroutines inside common containers.

        - If value is awaitable, await and return result.
        - If value is list/tuple, resolve each element.
        - If value is dict, resolve each value.
        - Otherwise, return as-is.
        """
        try:
            if inspect.isawaitable(value):
                return await value
            if isinstance(value, list):
                return [await self._resolve_maybe_awaitable(v) for v in value]
            if isinstance(value, tuple):
                return tuple([await self._resolve_maybe_awaitable(v) for v in value])
            if isinstance(value, dict):
                out = {}
                for k, v in value.items():
                    out[k] = await self._resolve_maybe_awaitable(v)
                return out
        except Exception:
            return value
        return value

    def _infer_agent_name(self, event: BaseEvent) -> Optional[str]:
        """Best-effort extraction of agent name from diverse AG2 events."""
        try:
            for attr in ("agent_name", "name", "sender", "agent"):
                val = getattr(event, attr, None)
                if isinstance(val, str) and val.strip():
                    return val.strip()
            content = getattr(event, "content", None)
            if isinstance(content, dict):
                for key in ("agent_name", "name", "sender", "agent"):
                    val = content.get(key)
                    if isinstance(val, str) and val.strip():
                        return val.strip()
            elif content is not None:
                for attr in ("agent_name", "name", "sender", "agent"):
                    val = getattr(content, attr, None)
                    if isinstance(val, str) and val.strip():
                        return val.strip()
        except Exception:
            pass
        return None

    def _infer_tool_name(self, event: BaseEvent) -> Optional[str]:
        """Best-effort extraction of tool name from tool-call related events."""
        et = type(event).__name__
        if not ("Tool" in et or "Function" in et or "Call" in et):
            return None
        try:
            for attr in ("tool_name", "function_name", "name"):
                val = getattr(event, attr, None)
                if isinstance(val, str) and val.strip():
                    return val.strip()
            content = getattr(event, "content", None)
            if isinstance(content, dict):
                for key in ("tool_name", "function_name", "name"):
                    val = content.get(key)
                    if isinstance(val, str) and val.strip():
                        return val.strip()
            elif content is not None:
                for attr in ("tool_name", "function_name", "name"):
                    val = getattr(content, attr, None)
                    if isinstance(val, str) and val.strip():
                        return val.strip()
        except Exception:
            pass
        return None

    def _extract_clean_content(self, raw: Any) -> str:
        """Extract only the human-visible message text from diverse AG2 payload shapes."""
        try:
            if raw is None:
                return ""
            if isinstance(raw, dict):
                val = raw.get("content")
                return "" if val in (None, "None") else str(val)
            if hasattr(raw, "content"):
                val = getattr(raw, "content")
                return "" if val in (None, "None") else str(val)
            if isinstance(raw, str):
                text = raw.strip()
                if text in ("", "None"):
                    return ""
                if "content=" in text:
                    m = re.search(r"content='([^']*)'", text, flags=re.DOTALL)
                    if not m:
                        m = re.search(r'content="([^"]*)"', text, flags=re.DOTALL)
                    if m:
                        return m.group(1)
                    m = re.search(r"content=([^,\)]+)", text, flags=re.DOTALL)
                    if m:
                        extracted = m.group(1).strip()
                        if (extracted.startswith("'") and extracted.endswith("'")) or (
                            extracted.startswith('"') and extracted.endswith('"')
                        ):
                            extracted = extracted[1:-1]
                        return "" if extracted in ("", "None") else extracted
                return text
        except Exception:
            pass
        try:
            return str(raw)
        except Exception:
            return ""

    def _parse_usage_summary_event(self, event: UsageSummaryEvent) -> tuple[Optional[str], int, int, int, float]:
        """Extract model, prompt/completion/total tokens and total_cost from UsageSummaryEvent."""
        model: Optional[str] = None
        prompt_tokens = completion_tokens = total_tokens = 0
        total_cost = 0.0

        try:
            mode_val = getattr(event, "mode", None) or getattr(event, "usage_type", None) or "both"
            total_obj = getattr(event, "total", None)
            actual_obj = getattr(event, "actual", None)
            use_total = str(mode_val).lower() in ("both", "total") and total_obj is not None
            use_actual = str(mode_val).lower() in ("both", "actual") and actual_obj is not None

            usages_list = None
            if use_total and getattr(total_obj, "usages", None) is not None:
                usages_list = getattr(total_obj, "usages", None)
                try:
                    total_cost = float(getattr(total_obj, "total_cost", 0.0) or 0.0)
                except Exception:
                    total_cost = 0.0
                self._last_usage_mode = "total"
            elif use_actual and getattr(actual_obj, "usages", None) is not None:
                usages_list = getattr(actual_obj, "usages", None)
                try:
                    total_cost = float(getattr(actual_obj, "total_cost", 0.0) or 0.0)
                except Exception:
                    total_cost = 0.0
                self._last_usage_mode = "actual"

            if usages_list is not None:
                for item in usages_list or []:
                    try:
                        m = getattr(item, "model", None) if not isinstance(item, dict) else item.get("model")
                        pt = getattr(item, "prompt_tokens", 0) if not isinstance(item, dict) else item.get("prompt_tokens", 0)
                        ct = getattr(item, "completion_tokens", 0) if not isinstance(item, dict) else item.get("completion_tokens", 0)
                        tt = getattr(item, "total_tokens", None) if not isinstance(item, dict) else item.get("total_tokens", None)
                        if tt is None:
                            tt = (int(pt or 0) + int(ct or 0))
                        total_tokens += int(tt or 0)
                        prompt_tokens += int(pt or 0)
                        completion_tokens += int(ct or 0)
                        if model is None and isinstance(m, str) and m:
                            model = m
                    except Exception:
                        continue
                return model, int(prompt_tokens), int(completion_tokens), int(total_tokens), float(total_cost)
        except Exception:
            pass

        # Fallback: dict-like
        try:
            content = getattr(event, "content", None)
            if isinstance(content, dict):
                model = content.get("model") or content.get("model_name")
                prompt_tokens = int(content.get("prompt_tokens", 0) or 0)
                completion_tokens = int(content.get("completion_tokens", 0) or 0)
                total_tokens = int(content.get("total_tokens", prompt_tokens + completion_tokens) or 0)
                try:
                    total_cost = float(content.get("total_cost", 0.0) or 0.0)
                except Exception:
                    total_cost = 0.0
        except Exception:
            pass
        return model, int(prompt_tokens), int(completion_tokens), int(total_tokens), float(total_cost)

    async def _handle_input_request(self, event: InputRequestEvent) -> None:
        """Generic AG2 InputRequestEvents are discouraged; log and auto-respond."""
        try:
            prompt = getattr(event.content, "prompt", None) or "Input required:"  # type: ignore[attr-defined]
            from core.transport.simple_transport import SimpleTransport
            transport = SimpleTransport._get_instance()
            if transport is None:
                self.logger.warning("SimpleTransport not available; responding with empty string")
                await event.content.respond("")  # type: ignore[attr-defined]
                return
            # Optionally show the prompt in the UI
            try:
                agent_name = self._turn_agent_name or self._infer_agent_name(cast(BaseEvent, event)) or "Assistant"
                await transport.send_to_ui(
                    message=str(prompt),
                    agent_name=agent_name,
                    chat_id=self.chat_id,
                    message_type="chat_message",
                    bypass_filter=False,
                )
            except Exception:
                pass
            # Wait for a user response via transport, or auto-empty if not provided
            input_request_id = str(uuid.uuid4())
            await transport.send_user_input_request(
                input_request_id=input_request_id,
                chat_id=self.chat_id,
                payload={"prompt": prompt},
            )
            user_input = await transport.wait_for_user_input(input_request_id)
            await event.content.respond(user_input)  # type: ignore[attr-defined]
        except Exception as e:
            self.logger.error(f"❌ Failed to handle InputRequestEvent: {e}")
            try:
                await event.content.respond("")  # type: ignore[attr-defined]
            except Exception:
                pass
