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
from typing import TYPE_CHECKING, Any, Union, Optional, cast
import autogen
import re
from autogen.events import BaseEvent
from autogen.events.agent_events import InputRequestEvent, TextEvent
from autogen.events.client_events import UsageSummaryEvent
from autogen.io.run_response import AsyncRunResponseProtocol

from core.data.persistence_manager import AG2PersistenceManager
from logs.logging_config import get_business_logger
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

        # Logging and persistence
        self.logger = get_business_logger("ui_event_processor")
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
        
    async def process(self, response: "AsyncRunResponseProtocol") -> None:
        """
        Process AG2 events - follows AG2's AsyncEventProcessorProtocol pattern.
        This is the main entry point called by AG2's run response system.
        """
        # Ensure performance manager knows about this workflow/chat
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
                    # Only assign back if changed to avoid side effects
                    if resolved is not getattr(event, "content"):
                        try:
                            setattr(event, "content", resolved)
                        except Exception:
                            # Some Pydantic models may be frozen; ignore if not assignable
                            pass
            except Exception as _resolve_err:
                # Never break processing due to resolver hiccups; log at debug level
                self.logger.debug(f"content resolver skipped: {_resolve_err}")
            # 0. Latency start heuristic: first TextEvent marks agent output start
            if isinstance(event, TextEvent) and not self._turn_active:
                self._turn_active = True
                self._turn_started_at = time.perf_counter()
                self._turn_agent_name = self._infer_agent_name(event)

            # 1. Persist the event in real-time (includes token updates + wallet debit)
            await self.persistence_manager.save_event(
                event=event,
                chat_id=self.chat_id,
                enterprise_id=self.enterprise_id,
                workflow_name=self.workflow_name,
                user_id=self.user_id
            )

            # 1.5 Usage + Latency: UsageSummaryEvent carries model + token counts.
            # Use it to compute token deltas in real time and record latency.
            if isinstance(event, UsageSummaryEvent):
                try:
                    if self._perf_mgr is None:
                        self._perf_mgr = await get_performance_manager()

                    content = getattr(event, "content", None)
                    model = None
                    prompt_tokens = completion_tokens = total_tokens = 0
                    total_cost = 0.0
                    if isinstance(content, dict):
                        model = content.get("model") or content.get("model_name")
                        # AG2 UsageSummaryEvent content often includes token counts
                        prompt_tokens = int(content.get("prompt_tokens", 0) or 0)
                        completion_tokens = int(content.get("completion_tokens", 0) or 0)
                        total_tokens = int(content.get("total_tokens", prompt_tokens + completion_tokens) or 0)
                        # cost may be absent; treat missing as 0.0
                        try:
                            total_cost = float(content.get("total_cost", 0.0) or 0.0)
                        except Exception:
                            total_cost = 0.0

                    # Compute deltas vs. our last cumulative snapshot
                    delta_prompt = max(0, prompt_tokens - self._cum_prompt_tokens)
                    delta_completion = max(0, completion_tokens - self._cum_completion_tokens)
                    delta_total = max(0, total_tokens - self._cum_total_tokens)

                    # Update our cumulative snapshots
                    self._cum_prompt_tokens = max(self._cum_prompt_tokens, prompt_tokens)
                    self._cum_completion_tokens = max(self._cum_completion_tokens, completion_tokens)
                    self._cum_total_tokens = max(self._cum_total_tokens, total_tokens)

                    # Record token deltas immediately for wallet + UI token_update
                    if delta_total > 0:
                        await self._perf_mgr.record_token_usage(
                            chat_id=self.chat_id,
                            prompt_tokens=delta_prompt,
                            completion_tokens=delta_completion,
                            model=model,
                            cost=0.0  # Per-turn granular cost often not provided; wallet debits by tokens
                        )

                    # Latency end only when a turn was active
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
                            prompt_tokens=0,
                            completion_tokens=0,
                            cost=0.0,
                        )
                finally:
                    # Reset latency state only; keep cumulative token snapshot across turns
                    if self._turn_active:
                        self._turn_active = False
                        self._turn_started_at = None
                        self._turn_agent_name = None

            # 2. Handle specific events for UI interaction or filtering
            if isinstance(event, InputRequestEvent):
                await self._handle_input_request(event)
                return  # Stop processing here, as it's handled

            # Filter out internal or noisy events that shouldn't go to the UI
            if event_type_name in ['GroupChatRunChatEvent', 'PrintEvent']:
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
                        success=True
                    )
            except Exception as hook_err:
                # Never let hooks break event flow
                self.logger.debug(f"perf hook skipped: {hook_err}")

            # 3. Forward all other relevant events to the UI
            from core.transport.simple_transport import SimpleTransport
            transport = SimpleTransport._get_instance()
            if transport:
                # For plain TextEvent, also emit a chat_message for the UI message list
                if isinstance(event, TextEvent):
                    try:
                        agent_name = self._turn_agent_name or self._infer_agent_name(event) or "Assistant"
                        # Sanitize content for UI (AG2 sometimes stringifies with uuid/sender)
                        clean_content = self._extract_clean_content(getattr(event, "content", ""))
                        if not clean_content:
                            return
                        await transport.send_to_ui(
                            message=clean_content,
                            agent_name=agent_name,
                            chat_id=self.chat_id,
                            message_type="chat_message",
                            bypass_filter=False,  # Let visual_agents filtering apply
                        )
                    except Exception as chat_err:
                        self.logger.debug(f"text forward skipped: {chat_err}")
                # Always forward the raw AG2 event for advanced clients
                await transport.send_event_to_ui(event, self.chat_id)

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
            # If anything fails, fall back to original value
            return value
        return value

    def _infer_agent_name(self, event: BaseEvent) -> Optional[str]:
        """Best-effort extraction of agent name from diverse AG2 events."""
        try:
            # Direct attributes first
            for attr in ("agent_name", "name", "sender", "agent"):
                val = getattr(event, attr, None)
                if isinstance(val, str) and val.strip():
                    return val.strip()
            # Nested content object/dict
            content = getattr(event, "content", None)
            if isinstance(content, dict):
                for key in ("agent_name", "name", "sender", "agent"):
                    val = content.get(key)
                    if isinstance(val, str) and val.strip():
                        return val.strip()
            else:
                for attr in ("agent_name", "name", "sender", "agent"):
                    val = getattr(content, attr, None) if content is not None else None
                    if isinstance(val, str) and val.strip():
                        return val.strip()
        except Exception:
            pass
        return None

    def _infer_tool_name(self, event: BaseEvent) -> Optional[str]:
        """Best-effort extraction of tool name from tool-call related events."""
        et = type(event).__name__
        # Quick prefilter: only attempt for likely tool events
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
            else:
                for attr in ("tool_name", "function_name", "name"):
                    val = getattr(content, attr, None) if content is not None else None
                    if isinstance(val, str) and val.strip():
                        return val.strip()
        except Exception:
            pass
        return None

    def _extract_clean_content(self, raw: Any) -> str:
        """Extract only the human-visible message text from diverse AG2 payload shapes.

        Handles:
        - dicts with 'content'
        - objects with .content
        - stringified events like "uuid=UUID('...'), sender='X', content='...')"
        - gracefully returns '' for None or 'None' values
        """
        try:
            if raw is None:
                return ""
            # Dict-like
            if isinstance(raw, dict):
                val = raw.get("content")
                return "" if val in (None, "None") else str(val)
            # Object with attribute
            if hasattr(raw, "content"):
                val = getattr(raw, "content")
                return "" if val in (None, "None") else str(val)
            # Already a plain string without AG2 metadata
            if isinstance(raw, str):
                text = raw.strip()
                if text in ("", "None"):
                    return ""
                # If it looks like a repr with content=... pattern, extract
                if "content=" in text:
                    # Try common quoted forms first
                    m = re.search(r"content='([^']*)'", text, flags=re.DOTALL)
                    if not m:
                        m = re.search(r'content="([^"]*)"', text, flags=re.DOTALL)
                    if m:
                        return m.group(1)
                    # Fallback: unquoted until comma or )
                    m = re.search(r"content=([^,\)]+)", text, flags=re.DOTALL)
                    if m:
                        extracted = m.group(1).strip()
                        # Strip surrounding quotes if present
                        if (extracted.startswith("'") and extracted.endswith("'")) or (extracted.startswith('"') and extracted.endswith('"')):
                            extracted = extracted[1:-1]
                        return "" if extracted in ("", "None") else extracted
                # Otherwise assume it's already the message
                return text
        except Exception:
            pass
        # Last resort
        try:
            return str(raw)
        except Exception:
            return ""

    async def _handle_input_request(self, event: InputRequestEvent) -> None:
        """
        Handles generic AG2 InputRequestEvents by logging a warning and auto-skipping.
        
        This behavior enforces the architectural decision that all user interactions
        should be handled by specific, defined UI tools (e.g., request_api_key) 
        rather than generic `agent.input()` calls. Our custom `ag2_iostream.py`
        is the designated handler for legitimate, non-tool-based input, so if an
        input request reaches this processor, it's considered an anti-pattern.
        """
        try:
            prompt = getattr(event.content, "prompt", None) or "Input required:"  # type: ignore[attr-defined]
            from core.transport.simple_transport import SimpleTransport
            transport = SimpleTransport._get_instance()
            if transport is None:
                self.logger.warning("SimpleTransport not available; responding with empty string")
                await event.content.respond("")  # type: ignore[attr-defined]
                return

            # Echo the prompt as an agent chat message so users see the agent's intent
            try:
                agent_name = self._turn_agent_name or self._infer_agent_name(cast(BaseEvent, event)) or "Assistant"
                await transport.send_to_ui(
                    message=str(prompt),
                    agent_name=agent_name,
                    chat_id=self.chat_id,
                    message_type="chat_message",
                    bypass_filter=False,  # Let visual_agents filtering apply
                )
            except Exception:
                pass

            # Route through UI and await real user input
            input_request_id = str(uuid.uuid4())
            await transport.send_user_input_request(
                input_request_id=input_request_id,
                chat_id=self.chat_id,
                payload={"prompt": prompt}
            )
            user_input = await transport.wait_for_user_input(input_request_id)
            await event.content.respond(user_input)  # type: ignore[attr-defined]
            self.logger.info(f"✅ [{self.chat_id}] Provided user input to InputRequestEvent")

        except Exception as e:
            self.logger.error(f"❌ [{self.chat_id}] Failed to handle InputRequestEvent: {e}")
            self.logger.error(f"   Traceback: {traceback.format_exc()}")
            # Ensure fallback response to prevent AG2 from hanging under any circumstance.
            try:
                if not getattr(event.content, "is_responded", True):  # type: ignore[attr-defined]
                    await event.content.respond("")  # type: ignore[attr-defined]
            except Exception:
                pass

# End of UIEventProcessor - clean AG2-compliant implementation
