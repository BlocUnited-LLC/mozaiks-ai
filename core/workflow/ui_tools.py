# ==============================================================================
# FILE: core/workflow/ui_tools.py
# DESCRIPTION: Centralized helper utilities for agent-driven UI interactions.
#   - UI tool emission + response handling
#   - Unified event -> UI payload translation (single source of truth)
#   - InputTimeoutEvent (moved here to eliminate custom_events.py)
# ==============================================================================

from __future__ import annotations
import asyncio
import uuid
import logging
from typing import Dict, Any, Optional
from typing import Any
import datetime as _dt

logger = logging.getLogger(__name__)

# Import SimpleTransport for direct communication and UnifiedEventDispatcher for logging
from core.transport.simple_transport import SimpleTransport
from core.events.unified_event_dispatcher import emit_ui_tool_event as dispatch_ui_tool_event
from logs.logging_config import get_workflow_logger, get_chat_logger

# -----------------------------------------------------------------------------
# InputTimeoutEvent (moved from core.events.custom_events for consolidation)
# -----------------------------------------------------------------------------
try:  # Prefer pydantic BaseModel if available
    from pydantic import BaseModel as _PydanticBaseModel
    BaseModel = _PydanticBaseModel  # type: ignore
except Exception:  # pragma: no cover
    class BaseModel:  # minimal fallback
        def model_dump(self, *a, **k):  # mimic pydantic v2 API
            return {k: v for k, v in self.__dict__.items() if not k.startswith('_')}

class InputTimeoutEvent(BaseModel):
    """Synthetic event emitted when a human InputRequestEvent times out.

    Fields:
      input_request_id: correlates to original InputRequestEvent id
      timeout_seconds: configured timeout interval
      chat_id: conversation id for routing
      occurred_at: UTC ISO timestamp
      reason: textual reason (default 'input_timeout')
    """
    input_request_id: str
    timeout_seconds: float
    chat_id: str
    occurred_at: str = _dt.datetime.utcnow().isoformat()
    reason: str = "input_timeout"

    # Compatibility for both pydantic v1 & v2 style .dict()
    def dict(self, *a, **kw):  # pragma: no cover - convenience
        if hasattr(super(), "model_dump"):
            try:
                return super().model_dump(*a, **kw)  # type: ignore
            except Exception:
                return self.__dict__
        return self.__dict__

# -----------------------------------------------------------------------------
# Normalization (moved from event_normalizer.py)
# -----------------------------------------------------------------------------
import uuid as _uuid
try:
    from autogen.events.agent_events import TextEvent as _N_TextEvent, InputRequestEvent as _N_InputRequestEvent, ErrorEvent as _N_ErrorEvent, RunCompletionEvent as _N_RunCompletionEvent
    from autogen.events.client_events import UsageSummaryEvent as _N_UsageSummaryEvent
except Exception:  # pragma: no cover
    _N_TextEvent = _N_InputRequestEvent = _N_ErrorEvent = _N_RunCompletionEvent = _N_UsageSummaryEvent = object  # type: ignore

def _utc_now_iso() -> str:
    return _dt.datetime.utcnow().replace(tzinfo=_dt.timezone.utc).isoformat().replace("+00:00", "Z")

def normalize_event(ev: Any, *, sequence: int, chat_id: str) -> Dict[str, Any]:
    """Return a normalized persistence envelope for an AG2 event.

    Fields:
      id: uuid4 string
      chat_id
      sequence: monotonic within run post-resume
      ts_utc: capture time
      event_type: class name
      role: user|assistant|system|null (best-effort mapping)
      name: sender / agent name if present
      content: textual content or None
      meta: dict with supplemental fields
    """
    event_type = ev.__class__.__name__
    sender = getattr(ev, "sender", None) or getattr(ev, "agent_name", None)
    content = getattr(ev, "content", None)
    role = None

    if isinstance(ev, _N_TextEvent):
        if sender and isinstance(sender, str) and sender.lower().startswith("user"):
            role = "user"
        else:
            role = "assistant"
    elif isinstance(ev, (_N_InputRequestEvent, _N_ErrorEvent, _N_RunCompletionEvent, _N_UsageSummaryEvent, InputTimeoutEvent)):
        role = "system"

    meta: Dict[str, Any] = {}
    if isinstance(ev, _N_UsageSummaryEvent):
        for attr in ("total_tokens", "prompt_tokens", "completion_tokens", "cost", "model"):
            if hasattr(ev, attr):
                meta[attr] = getattr(ev, attr)
    if isinstance(ev, InputTimeoutEvent):
        meta.update({
            "input_request_id": getattr(ev, "input_request_id", None),
            "timeout_seconds": getattr(ev, "timeout_seconds", None),
            "reason": getattr(ev, "reason", None),
        })

    return {
        "id": str(_uuid.uuid4()),
        "chat_id": chat_id,
        "sequence": sequence,
        "ts_utc": _utc_now_iso(),
        "event_type": event_type,
        "role": role,
        "name": sender,
        "content": content,
        "meta": meta,
    }

# -----------------------------------------------------------------------------
# Unified event -> UI payload translation (single canonical mapping)
# -----------------------------------------------------------------------------
try:  # Optional imports (AG2 event types)
    from autogen.events.agent_events import (
        TextEvent as _ET_TextEvent,
        InputRequestEvent as _ET_InputRequestEvent,
        SelectSpeakerEvent as _ET_SelectSpeakerEvent,
        RunCompletionEvent as _ET_RunCompletionEvent,
        ErrorEvent as _ET_ErrorEvent,
        GroupChatResumeEvent as _ET_GroupChatResumeEvent,
        FunctionCallEvent as _ET_FunctionCallEvent,
        ToolCallEvent as _ET_ToolCallEvent,
        FunctionResponseEvent as _ET_FunctionResponseEvent,
        ToolResponseEvent as _ET_ToolResponseEvent,
    )
    from autogen.events.client_events import UsageSummaryEvent as _ET_UsageSummaryEvent
except Exception:  # pragma: no cover
    _ET_TextEvent = _ET_InputRequestEvent = _ET_SelectSpeakerEvent = _ET_RunCompletionEvent = _ET_ErrorEvent = _ET_UsageSummaryEvent = _ET_GroupChatResumeEvent = _ET_FunctionCallEvent = _ET_ToolCallEvent = _ET_FunctionResponseEvent = _ET_ToolResponseEvent = object  # type: ignore

def event_to_ui_payload(ev: Any) -> Dict[str, Any]:
    """Translate heterogeneous internal event objects into a stable, minimal UI payload.

    Returned dict always contains:
      kind: simplified categorical label (text, input_request, input_timeout, usage_summary,
            select_speaker, resume_boundary, error, run_complete, tool_call, tool_response, unknown)
      event_type: original class name (diagnostic / logging)

    Optional fields include: agent|next, content, prompt, request_id/input_request_id,
    timeout_seconds, reason, tool_name, component_type, awaiting_response, and token/cost metrics when present.

    Extension points:
      - Add tool_start/tool_progress/tool_complete kinds when tool events formalized.
      - Inject latency_ms once performance metrics are attached.
    """
    et = ev.__class__.__name__
    base: Dict[str, Any] = {"event_type": et}
    if isinstance(ev, _ET_TextEvent):
        sender = getattr(getattr(ev, "sender", None), "name", None) or getattr(ev, "sender", None) or getattr(ev, "agent_name", None)
        base.update({
            "kind": "text",
            "agent": sender,
            "content": getattr(ev, "content", None),
        })
        return base
    if isinstance(ev, _ET_InputRequestEvent):
        base.update({
            "kind": "input_request",
            "request_id": getattr(ev, "id", None) or getattr(ev, "input_request_id", None),
            "prompt": getattr(ev, "content", None) or getattr(ev, "prompt", None),
        })
        return base
    if isinstance(ev, InputTimeoutEvent):
        base.update({
            "kind": "input_timeout",
            "input_request_id": getattr(ev, "input_request_id", None),
            "timeout_seconds": getattr(ev, "timeout_seconds", None),
            "reason": getattr(ev, "reason", None),
        })
        return base
    if isinstance(ev, _ET_GroupChatResumeEvent):
        base.update({"kind": "resume_boundary"})
        return base
    if isinstance(ev, _ET_SelectSpeakerEvent):
        base.update({
            "kind": "select_speaker",
            "next": getattr(ev, "sender", None) or getattr(ev, "agent", None),
        })
        return base
    if isinstance(ev, (_ET_FunctionCallEvent, _ET_ToolCallEvent)):
        # Handle AG2 tool/function call events - convert to interactive UI events
        tool_name = (getattr(ev, "tool_name", None) or 
                    getattr(ev, "function_name", None) or 
                    getattr(getattr(ev, "content", {}), "name", None) if hasattr(getattr(ev, "content", {}), "get") 
                    else str(getattr(ev, "content", {}).get("name", "unknown_tool")) if isinstance(getattr(ev, "content", {}), dict) 
                    else "unknown_tool")
        
        # Determine if this tool should trigger UI interaction
        # Look for UI-specific tool names or patterns
        is_ui_tool = any(pattern in str(tool_name).lower() for pattern in [
            "input", "confirm", "select", "upload", "download", "edit", "api_key", "form"
        ])
        
        # Extract tool arguments/parameters
        content = getattr(ev, "content", {})
        if hasattr(content, "arguments"):
            tool_args = getattr(content, "arguments", {})
        elif isinstance(content, dict):
            tool_args = content.get("arguments", {}) or content
        else:
            tool_args = {}
            
        # Determine component type - default to inline, upgrade to artifact for large interactions
        component_type = "inline"
        if any(pattern in str(tool_name).lower() for pattern in ["editor", "viewer", "document", "artifact"]):
            component_type = "artifact"
            
        base.update({
            "kind": "tool_call",
            "tool_name": str(tool_name),
            "is_ui_tool": is_ui_tool,
            "component_type": component_type,
            "awaiting_response": True,
            "payload": {
                "tool_args": tool_args,
                "interaction_type": "input",  # default interaction type
                "agent_name": getattr(ev, "sender", None) or getattr(ev, "agent_name", None),
            }
        })
        return base
    if isinstance(ev, (_ET_FunctionResponseEvent, _ET_ToolResponseEvent)):
        # Handle tool/function response events
        tool_name = (getattr(ev, "tool_name", None) or 
                    getattr(ev, "function_name", None) or 
                    "unknown_tool")
        
        base.update({
            "kind": "tool_response",
            "tool_name": str(tool_name),
            "content": getattr(ev, "content", None),
            "success": not bool(getattr(ev, "error", None)),
        })
        return base
    if isinstance(ev, _ET_UsageSummaryEvent):
        for f in ("total_tokens", "prompt_tokens", "completion_tokens", "cost", "model"):
            if hasattr(ev, f):
                base[f] = getattr(ev, f)
        base.update({"kind": "usage_summary"})
        return base
    if isinstance(ev, _ET_ErrorEvent):
        base.update({
            "kind": "error",
            "message": getattr(ev, "message", None) or getattr(ev, "content", None) or str(ev),
        })
        return base
    if isinstance(ev, _ET_RunCompletionEvent):
        base.update({
            "kind": "run_complete",
            "reason": getattr(ev, "reason", None) or getattr(ev, "termination_reason", None),
        })
        return base
    base.update({"kind": "unknown"})
    return base

class UIToolError(Exception):
    """Custom exception for UI tool errors."""
    pass

async def emit_ui_tool_event(
    tool_id: str,
    payload: Dict[str, Any],
    display: str = "inline",
    chat_id: Optional[str] = None,
    workflow_name: str = "unknown"
) -> str:
    """
    Core function to emit a UI tool event to the frontend.

    This function is the standardized way for any agent tool to request
    that a UI component be rendered.

    Args:
        tool_id: The unique identifier for the UI component (e.g., "agent_api_key_input").
        payload: The data required by the UI component (props).
        display: How the component should be displayed ("inline" or "artifact").
        chat_id: The ID of the chat session to send the event to.
        workflow_name: The name of the workflow emitting the event.

    Returns:
        The unique event ID for this interaction.
    """
    event_id = f"{tool_id}_{str(uuid.uuid4())[:8]}"
    wf_logger = get_workflow_logger(workflow_name=workflow_name, chat_id=chat_id)
    chat_logger = get_chat_logger("ui_tools")
    
    try:
        transport = await SimpleTransport.get_instance()
    except Exception as e:
        wf_logger.error(f"❌ [UI_TOOLS] Failed to get SimpleTransport instance: {e}")
        raise UIToolError(f"SimpleTransport not available: {e}")

    chat_logger.info(f"🎯 UI tool event: {tool_id} (event={event_id}, display={display})")
    
    try:
        # 1. Send the event to the UI for immediate rendering
        await transport.send_ui_tool_event(
            event_id=event_id,
            chat_id=chat_id,
            tool_name=workflow_name,
            component_name=tool_id,
            display_type=display,
            payload=payload
        )
        
        # 2. Dispatch the event for logging and monitoring
        await dispatch_ui_tool_event(
            ui_tool_id=tool_id,
            payload=payload,
            workflow_name=workflow_name,
            display=display,
            chat_id=chat_id
        )
        
        wf_logger.info(f"✅ [UI_TOOLS] Emitted + logged UI tool event: {event_id}")
        return event_id
        
    except Exception as e:
        wf_logger.error(f"❌ [UI_TOOLS] Failed to emit UI tool event '{event_id}': {e}", exc_info=True)
        raise UIToolError(f"Failed to emit UI tool event: {e}")

async def wait_for_ui_tool_response(event_id: str) -> Dict[str, Any]:
    """
    Waits indefinitely for a response from a UI tool interaction.

    Args:
        event_id: The unique event ID that was sent to the UI.

    Returns:
        The response data submitted by the user from the UI component.
    """
    wf_logger = get_workflow_logger(workflow_name="unknown")
    chat_logger = get_chat_logger("ui_tools")
    wf_logger.info(f"⏳ [UI_TOOLS] Waiting for UI tool response for event: {event_id}")
    
    try:
        transport = await SimpleTransport.get_instance()
        
        # The transport layer manages the futures for waiting.
        response = await transport.wait_for_ui_tool_response(event_id)
        chat_logger.info(f"📨 UI tool response received (event={event_id})")
        wf_logger.info(f"✅ [UI_TOOLS] Received UI tool response for event: {event_id}")
        wf_logger.debug(f"🔍 [UI_TOOLS] Response data: {response}")
        
        return response
    except Exception as e:
        wf_logger.error(f"❌ [UI_TOOLS] Error waiting for UI tool response for event '{event_id}': {e}", exc_info=True)
        raise UIToolError(f"Error waiting for UI tool response: {e}")


async def handle_tool_call_for_ui_interaction(tool_call_event: Any, chat_id: str) -> Optional[Dict[str, Any]]:
    """
    Handle AG2 tool call events that require UI interaction.
    
    This function:
    1. Detects if a tool call should trigger UI interaction
    2. Emits a UI tool event if needed
    3. Waits for user response
    4. Returns the response for the agent to continue
    
    Args:
        tool_call_event: AG2 FunctionCallEvent or ToolCallEvent
        chat_id: Current chat session ID
        
    Returns:
        User response data if UI interaction occurred, None otherwise
    """
    wf_logger = get_workflow_logger(workflow_name="tool_interaction", chat_id=chat_id)
    
    # Extract tool information
    tool_name = (getattr(tool_call_event, "tool_name", None) or 
                getattr(tool_call_event, "function_name", None) or 
                getattr(getattr(tool_call_event, "content", {}), "name", None) if hasattr(getattr(tool_call_event, "content", {}), "get") 
                else str(getattr(tool_call_event, "content", {}).get("name", "unknown_tool")) if isinstance(getattr(tool_call_event, "content", {}), dict) 
                else "unknown_tool")
    
    # Check if this tool requires UI interaction
    is_ui_tool = any(pattern in str(tool_name).lower() for pattern in [
        "input", "confirm", "select", "upload", "download", "edit", "api_key", "form", "artifact"
    ])
    
    if not is_ui_tool:
        wf_logger.debug(f"🔧 Tool '{tool_name}' does not require UI interaction, skipping")
        return None
    
    wf_logger.info(f"🎯 Tool '{tool_name}' requires UI interaction, emitting UI event")
    
    # Extract tool arguments
    content = getattr(tool_call_event, "content", {})
    if hasattr(content, "arguments"):
        tool_args = getattr(content, "arguments", {})
    elif isinstance(content, dict):
        tool_args = content.get("arguments", {}) or content
    else:
        tool_args = {}
    
    # Determine component type and display mode
    component_type = "inline"
    if any(pattern in str(tool_name).lower() for pattern in ["editor", "viewer", "document", "artifact"]):
        component_type = "artifact"
    
    # Prepare UI tool payload
    ui_payload = {
        "tool_name": str(tool_name),
        "tool_args": tool_args,
        "component_type": component_type,
        "interaction_type": "input",
        "agent_name": getattr(tool_call_event, "sender", None) or getattr(tool_call_event, "agent_name", None),
    }
    
    try:
        # Emit UI tool event
        event_id = await emit_ui_tool_event(
            tool_id=str(tool_name),
            payload=ui_payload,
            display=component_type,
            chat_id=chat_id,
            workflow_name="tool_interaction"
        )
        
        # Wait for user response
        wf_logger.info(f"⏳ Waiting for user interaction on tool '{tool_name}'")
        response = await wait_for_ui_tool_response(event_id)
        
        wf_logger.info(f"✅ Received user response for tool '{tool_name}'")
        return response
        
    except Exception as e:
        wf_logger.error(f"❌ Error handling UI interaction for tool '{tool_name}': {e}", exc_info=True)
        return {"error": f"UI interaction failed: {e}"}

__all__ = [
    "emit_ui_tool_event",
    "wait_for_ui_tool_response",
    "handle_tool_call_for_ui_interaction",
    "event_to_ui_payload",
    "InputTimeoutEvent",
    "UIToolError",
]
