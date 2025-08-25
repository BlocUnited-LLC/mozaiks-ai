# ==============================================================================
# FILE: core/transport/ag2_iostream.py
# DESCRIPTION: Clean AG2 IOStream implementation aligned with orchestration + resume
# ==============================================================================

import asyncio
import uuid
import re
from typing import Optional, Any, Coroutine
from datetime import datetime

# AG2 imports
from autogen.events.base_event import BaseEvent
from autogen.io.base import InputStream, OutputStream
from autogen.io import IOStream

from logs.logging_config import get_chat_logger, get_workflow_logger
from contextlib import contextmanager
from typing import Iterator

# Conversation transcript logger
chat_logger = get_chat_logger("agent_output")


# =========================
# Utilities
# =========================

def _infer_agent_from_text_blob(blob: str) -> Optional[str]:
    """Best-effort: find sender='AgentName' or sender="AgentName" inside a streamed line."""
    if not isinstance(blob, str):
        return None
    m = re.search(r"sender='([^']+)'", blob)
    if not m:
        m = re.search(r'sender="([^"]+)"', blob)
    if m:
        name = m.group(1).strip()
        if name and name.lower() not in ("system",):
            return name
    return None


# ==============================================================================
# IOStream implementation
# ==============================================================================

class AG2StreamingIOStream(InputStream, OutputStream):
    """
    IO-only class:
      - Forwards AG2 llm_config["stream"]=True tokens to WebSocket
      - Handles blocking input() by bridging to async transport
      - No pattern / manager creation here (orchestration owns that)
    """

    def __init__(
        self,
        chat_id: str,
        enterprise_id: str,
        *,
        user_id: str = "unknown",
        workflow_name: str = "default",
        loop: Optional[asyncio.AbstractEventLoop] = None,
        input_timeout_seconds: Optional[float] = 120.0,
    ) -> None:
        if not isinstance(chat_id, str) or not chat_id.strip():
            raise ValueError("chat_id must be a non-empty string")
        if not isinstance(enterprise_id, str) or not enterprise_id.strip():
            raise ValueError("enterprise_id must be a non-empty string")

        self.chat_id = chat_id.strip()
        self.enterprise_id = enterprise_id.strip()
        self.user_id = user_id
        self.workflow_name = workflow_name

        # Pin to the orchestrator loop (so streaming works from worker threads)
        self._loop: Optional[asyncio.AbstractEventLoop] = loop

        self.wf_logger = get_workflow_logger(
            workflow_name=self.workflow_name,
            chat_id=self.chat_id,
            enterprise_id=self.enterprise_id,
            component="ag2_iostream",
        )
        # State
        self.current_agent_name = None  # type: Optional[str]
        self.input_timeout_seconds = input_timeout_seconds

    # ---- core print hook (sync, non-blocking) ----
    def print(self, *objects: Any, sep: str = " ", end: str = "\n", flush: bool = False) -> None:
        """
        Called by AG2 when streaming. Must be synchronous and fast.
        We schedule the actual WebSocket send on the orchestrator loop.
        """
        # Make strings; convert coroutines defensively to a marker string
        parts = []
        for obj in objects:
            if asyncio.iscoroutine(obj):
                parts.append("<coroutine>")
            else:
                parts.append(str(obj))
        content = sep.join(parts) + end
        if not content.strip():
            return None

        # Opportunistic agent-name inference if not set
        agent_name = self.current_agent_name or _infer_agent_from_text_blob(content) or "Assistant"

        # Log a short preview
        clean_preview = content.strip()
        if len(clean_preview) > 500:
            preview = f"{clean_preview[:250]}...{clean_preview[-100:]}"
        else:
            preview = clean_preview
        chat_logger.info(f"🤖 [{agent_name}] {preview}")

        # Schedule async send on the pinned loop
        self._schedule_coro(self._send_to_websocket(content, agent_name, message_type="stream"))
        return None  # AG2 contract

    def send(self, message: BaseEvent) -> None:
        """Forward as a generic event."""
        self._schedule_coro(self._send_generic_event_to_websocket(message))

    # ---- blocking input() bridge ----
    def input(self, prompt: str = "", *, password: bool = False) -> str:
        """
        AG2 calls this synchronously; we bridge to async transport on the pinned loop.
        """
        if password:
            self.wf_logger.warning("Password-style input requested; treating as plain text.")

        if not self._loop:
            # Try to capture any running loop for a best-effort fallback
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                self.wf_logger.error("No asyncio loop available to service input().")
                return "Error: Transport unavailable."

        input_request_id = str(uuid.uuid4())
        fut = asyncio.run_coroutine_threadsafe(
            self._get_user_input(input_request_id, prompt),
            self._loop,
        )
        try:
            return fut.result()
        except Exception as e:
            self.wf_logger.error(f"input() failed for {input_request_id}: {e}")
            return "Error: Could not get user input."

    # ---- helpers: scheduling to the orchestrator loop ----
    def _schedule_coro(self, coro: Coroutine[Any, Any, Any]) -> None:
        """Run a coroutine on the pinned orchestrator loop safely from any thread."""
        loop = self._loop
        if loop and loop.is_running():
            # If already in the same loop thread, use create_task
            try:
                running = asyncio.get_running_loop()
                if running is loop:
                    asyncio.create_task(coro)
                    return
            except RuntimeError:
                pass
            # Different thread → thread-safe submit
            asyncio.run_coroutine_threadsafe(coro, loop)
        else:
            # Last-chance: try the current running loop (won't work from worker thread)
            try:
                running = asyncio.get_running_loop()
                running.create_task(coro)
            except RuntimeError:
                # Drop with a debug note—no loop to deliver on
                self.wf_logger.debug("No running loop to deliver streaming token; skipping chunk.")

    # ---- async senders ----
    async def _send_to_websocket(self, content: str, agent_name: str, *, message_type: str = "chat_message"):
        """Send content to WebSocket via SimpleTransport."""
        try:
            from .simple_transport import SimpleTransport
            transport = await SimpleTransport.get_instance()
            if not transport:
                self.wf_logger.warning("SimpleTransport not available for streaming.")
                return
            await transport.send_to_ui(
                message=content.strip(),
                agent_name=agent_name,
                chat_id=self.chat_id,
                message_type=message_type,  # "stream" marks token-chunks on UI
                bypass_filter=True,         # let UI decide how to merge stream/final
            )
        except Exception as e:
            self.wf_logger.error(f"WebSocket stream send failed: {e}")

    async def _send_generic_event_to_websocket(self, event: BaseEvent):
        try:
            from .simple_transport import SimpleTransport
            transport = await SimpleTransport.get_instance()
            if transport:
                await transport.send_event_to_ui(event=event, chat_id=self.chat_id)
        except Exception as e:
            self.wf_logger.error(f"Generic event send failed: {e}")

    async def _get_user_input(self, input_request_id: str, prompt: str) -> str:
        try:
            from .simple_transport import SimpleTransport
            transport = await SimpleTransport.get_instance()
            if not transport:
                return "Error: Transport not available."

            await transport.send_user_input_request(
                input_request_id=input_request_id,
                chat_id=self.chat_id,
                payload={"prompt": prompt},
            )
            # Apply optional timeout
            try:
                if self.input_timeout_seconds and self.input_timeout_seconds > 0:
                    user_input = await asyncio.wait_for(
                        transport.wait_for_user_input(input_request_id),
                        timeout=self.input_timeout_seconds,
                    )
                else:
                    user_input = await transport.wait_for_user_input(input_request_id)
                return user_input
            except asyncio.TimeoutError:
                self.wf_logger.warning(
                    f"User input timed out after {self.input_timeout_seconds}s (request_id={input_request_id})."
                )
                # Communicate timeout to UI
                try:
                    await transport.send_event_to_ui(
                        event={
                            "event_type": "InputTimeoutEvent",
                            "input_request_id": input_request_id,
                            "timeout_seconds": self.input_timeout_seconds,
                        },
                        chat_id=self.chat_id,
                    )
                except Exception:
                    pass
                return "<INPUT_TIMEOUT>"
        except Exception as e:
            self.wf_logger.error(f"User input flow failed: {e}")
            return "Error: Failed to receive user input."

    # ---- convenience ----
    def set_agent_context(self, agent_name: str):
        """Set the current agent for better streaming metadata."""
        if not isinstance(agent_name, str) or not agent_name.strip():
            return
        self.current_agent_name = agent_name.strip()
        self.wf_logger.debug(f"AGENT_CONTEXT | Chat: {self.chat_id} | Agent: {self.current_agent_name}")


# ------------------------------------------------------------------------------
# Context manager (moved from iostream_context.py) to install this stream globally
# ------------------------------------------------------------------------------
@contextmanager
def install_streaming_iostream(
    chat_id: str,
    enterprise_id: str,
    *,
    user_id: str = "unknown",
    workflow_name: str = "default",
    input_timeout_seconds: Optional[float] = 120.0,
) -> Iterator[AG2StreamingIOStream]:
    original: Optional[IOStream] = None
    custom: Optional[AG2StreamingIOStream] = None
    try:
        try:
            original = IOStream.get_default()  # type: ignore[attr-defined]
        except Exception:
            original = None
        custom = AG2StreamingIOStream(
            chat_id=chat_id,
            enterprise_id=enterprise_id,
            user_id=user_id,
            workflow_name=workflow_name,
            input_timeout_seconds=input_timeout_seconds,
        )
        IOStream.set_global_default(custom)  # type: ignore[attr-defined]
        yield custom
    finally:
        try:
            if original is not None:
                IOStream.set_global_default(original)  # type: ignore[attr-defined]
        except Exception:
            pass


# ==============================================================================
# Streaming manager (no groupchat creation)
# ==============================================================================

