# ==============================================================================
# FILE: core/workflow/orchestration_patterns.py
# DESCRIPTION: COMPLETE AG2 execution engine - Single-responsibility pattern for all workflow orchestration
# ==============================================================================

"""
MozaiksAI Orchestration Engine (organized)

Purpose
- Single entry point to run a workflow using AG2 patterns with streaming, tools, persistence, and perforamnce.

Sections (skim map)
- Logging setup (chat/workflow/perf)
- run_workflow_orchestration: main orchestration contract and steps
- create_orchestration_pattern: AG2 pattern factory
- logging helpers: agent message details and full conversation logging
"""

from typing import Dict, List, Optional, Any, Callable, Tuple
import os
import uuid
from datetime import datetime, UTC
import logging
import time
from time import perf_counter
import asyncio
import inspect
import re
import json
from collections import Counter

from pydantic import ValidationError

from autogen import ConversableAgent, UserProxyAgent
from autogen.agentchat.group.patterns import (
    DefaultPattern as AG2DefaultPattern,
    AutoPattern as AG2AutoPattern,
    RoundRobinPattern as AG2RoundRobinPattern,
    RandomPattern as AG2RandomPattern,
)
from autogen.events.agent_events import (
    TextEvent,
    InputRequestEvent,
    SelectSpeakerEvent,
    RunCompletionEvent,
)
from core.workflow.structured_outputs import agent_has_structured_output, get_structured_output_model_fields, get_structured_outputs_for_workflow
from core.data.persistence_manager import AG2PersistenceManager as _PM
from core.events.event_serialization import (
    build_ui_event_payload as unified_build_ui_event_payload,
    EventBuildContext as UnifiedEventBuildContext,
    build_structured_output_ready_event,
    serialize_event_content,
)

from ..data.persistence_manager import AG2PersistenceManager
from .termination_handler import create_termination_handler
from .derived_context import DerivedContextManager
from logs.logging_config import get_workflow_logger
from core.observability.ag2_runtime_logger import ag2_logging_session
from core.observability.performance_manager import get_performance_manager
from core.events.unified_event_dispatcher import get_event_dispatcher

from .tool_validation import SENTINEL_STATUS
from .ui_tools import InputTimeoutEvent
logger = logging.getLogger(__name__)

# Consolidated logging with optimized workflow logger
chat_logger = get_workflow_logger("orchestration")
workflow_logger = get_workflow_logger("orchestration")
performance_logger = get_workflow_logger("performance.orchestration")


__all__ = [
    'run_workflow_orchestration',
    'create_ag2_pattern',
    'InputTimeoutEvent'
]

# -------------------------------------------------------------------
# Helper: safe snapshot for verbose context logging (avoids secrets)
# -------------------------------------------------------------------
def _safe_context_snapshot(ctx) -> Dict[str, Any]:  # pragma: no cover (diagnostic)
    out: Dict[str, Any] = {}
    try:
        data = None
        if ctx is None:
            return {}
        if hasattr(ctx, 'data') and isinstance(getattr(ctx, 'data'), dict):
            data = getattr(ctx, 'data')
        elif hasattr(ctx, 'to_dict') and callable(getattr(ctx, 'to_dict')):
            data = ctx.to_dict()
        elif isinstance(ctx, dict):
            data = ctx
        if not isinstance(data, dict):
            return {"_repr": str(ctx)[:200]}
        for k, v in data.items():
            lk = k.lower()
            if any(s in lk for s in ("secret", "api", "key", "token", "password")):
                out[k] = "<redacted>"
                continue
            try:
                sv = v if isinstance(v, (int, float, bool)) else str(v)
            except Exception:
                sv = "<unserializable>"
            if isinstance(sv, str) and len(sv) > 300:
                sv = sv[:300] + "�?�"
            out[k] = sv
    except Exception as _snap_err:
        out["_error"] = f"snapshot_failed:{_snap_err}"  # pragma: no cover
    return out

# ===================================================================
# AG2 INTERNAL LOGGING CONFIGURATION
# ===================================================================
# Set AG2 internal logging to INFO level for production
logging.getLogger("autogen.agentchat").setLevel(logging.INFO)
logging.getLogger("autogen.io").setLevel(logging.INFO)
logging.getLogger("autogen.agentchat.group").setLevel(logging.INFO)

# ===================================================================
# HEALTH ENDPOINT SUPPORT
# ===================================================================
def get_run_registry_summary() -> Dict[str, Any]:
    """Simple health endpoint response - no actual registry tracking"""
    return {
        'active_count': 0,
        'total_runs': 0,
        'runs': [],
        'note': 'Registry tracking disabled for simplicity'
    }

# ===================================================================
# HELPERS: message normalization
# ===================================================================

def _normalize_to_strict_ag2(
    raw_msgs: Optional[List[Any]],
    *,
    default_user_name: str = "user",
) -> List[Dict[str, Any]]:
    """
    Ensure every message is in strict AG2 shape:
      {"role": "user"|"assistant", "name": "<exact agent name>", "content": <str|dict|list>}
    Assumes persisted messages already follow this; mainly fixes locally-seeded items.
    """
    if not raw_msgs:
        return []
    out: List[Dict[str, Any]] = []
    for m in raw_msgs:
        if not isinstance(m, dict):
            # ignore non-dicts
            continue

        role = m.get("role")
        name = m.get("name")
        content = m.get("content")

        # Accept strict messages as-is
        if role in ("user", "assistant") and isinstance(name, str) and name and content is not None:
            out.append({"role": role, "name": name, "content": content})
            continue

        # Try minimal fix-up for messages missing name/role (only for new seeds we add)
        # - If role == "user" and name missing -> set name to "user"
        # - If role missing but name == "user" -> set role to "user"
        # - Otherwise, if assistant-like seed comes through without name, we skip (cannot guess agent)
        if role == "user" and not name:
            name = default_user_name
        if not role and name == default_user_name:
            role = "user"

        if role in ("user", "assistant") and name and content is not None:
            out.append({"role": role, "name": name, "content": content})
        # else drop silently; strictness prevents bad resume
    return out

# -------------------------------------------------------------------
# Helper: robust agent name extraction for events/messages
# -------------------------------------------------------------------
def _normalize_text_content(raw: Any) -> str:
    """Convert AG2 text payloads (which may be dicts/BaseModels) into displayable strings."""
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    if hasattr(raw, 'model_dump') and callable(getattr(raw, 'model_dump')):
        try:
            return _normalize_text_content(raw.model_dump())
        except Exception:
            pass
    if isinstance(raw, dict):
        for key in ('content', 'text', 'message'):
            value = raw.get(key)
            if isinstance(value, str) and value.strip():
                return value
    if isinstance(raw, (list, tuple)):
        try:
            return ' '.join(str(x) for x in raw)
        except Exception:
            pass
    return str(raw)


def _serialize_event_content(raw: Any) -> Any:
    """Best-effort conversion of AG2 event content into JSON-serializable structures."""
    if raw is None or isinstance(raw, (str, int, float, bool)):
        return raw
    try:
        if hasattr(raw, 'model_dump') and callable(getattr(raw, 'model_dump')):
            return _serialize_event_content(raw.model_dump())
    except Exception:
        pass
    try:
        if hasattr(raw, 'dict') and callable(getattr(raw, 'dict')):
            return _serialize_event_content(raw.dict())
    except Exception:
        pass
    if isinstance(raw, dict):
        return {k: _serialize_event_content(v) for k, v in raw.items()}
    if isinstance(raw, (list, tuple, set)):
        return [_serialize_event_content(v) for v in list(raw)]
    if hasattr(raw, '__dict__'):
        try:
            return _serialize_event_content(vars(raw))
        except Exception:
            pass
    return str(raw)

def _extract_agent_name(obj: Any) -> Optional[str]:
    """Best-effort extraction of an agent/sender name from AG2 event/message objects.

    Traverses nested structures (dicts, lists, dataclasses) and falls back to string pattern
    matching so that tool and agent messages surface their logical speaker in the UI.
    """

    def _scan(candidate: Any) -> Optional[str]:
        if candidate is None:
            return None
        if isinstance(candidate, str):
            value = candidate.strip()
            if not value:
                return None
            match = re.search(r"sender(?:=|\"\s*:)['\"]([^'\"\\]+)['\"]", value)
            if match:
                return match.group(1).strip()
            if ' ' not in value and len(value) <= 64:
                return value
            return None
        if isinstance(candidate, dict):
            for key in ("sender", "agent", "agent_name", "name"):
                value = candidate.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            for key in ("sender", "agent", "agent_name", "name", "content"):
                value = candidate.get(key)
                result = _scan(value)
                if result:
                    return result
            return None
        if isinstance(candidate, (list, tuple, set)):
            for item in candidate:
                result = _scan(item)
                if result:
                    return result
            return None
        for key in ("sender", "agent", "agent_name", "name"):
            attr = getattr(candidate, key, None)
            if isinstance(attr, str) and attr.strip():
                return attr.strip()
            result = _scan(attr)
            if result:
                return result
        content = getattr(candidate, "content", None)
        if content is not None:
            return _scan(content)
        return None

    try:
        return _scan(obj)
    except Exception:  # pragma: no cover
        return None
 
# ===================================================================
# NEW HELPER (extracted to reduce complexity in _stream_events)
# ===================================================================
def _build_ui_event_payload(
    *,
    ev: Any,
    workflow_name: str,
    turn_agent: Optional[str],
    wf_logger: logging.Logger,
    tool_call_initiators: Dict[str, str],
    tool_names_by_id: Dict[str, str],
    workflow_name_upper: str,
) -> Optional[Dict[str, Any]]:
    """Build the UI event payload for a single AG2 event.

    This function contains logic extracted from the original monolithic if/elif block
    inside `_stream_events`. Behavior is intentionally identical; only structure changed.
    """
    try:
        from autogen.events.agent_events import (
            TextEvent as _T,
            InputRequestEvent as _IR,
            RunCompletionEvent as _RC,
            ErrorEvent as _EE,
            FunctionCallEvent as _FCe,
            ToolCallEvent as _TCe,
            FunctionResponseEvent as _FRe,
            ToolResponseEvent as _TRe,
            SelectSpeakerEvent as _SS,
            GroupChatResumeEvent as _GR,
            GroupChatRunChatEvent as _GRCE,
        )
        from autogen.events.client_events import UsageSummaryEvent as _US
        try:
            from autogen.events.print_event import PrintEvent as _PE
        except Exception:  # pragma: no cover
            _PE = object  # type: ignore
    except Exception:
        return {"event_type": ev.__class__.__name__, "kind": "unknown"}

    et_name = ev.__class__.__name__
    payload: Dict[str, Any] = {"event_type": et_name}

    if isinstance(ev, _T):
        sender = _extract_agent_name(ev)
        raw_content_obj = getattr(ev, "content", None)
        clean_content = _normalize_text_content(raw_content_obj)
        serialized_raw = _serialize_event_content(raw_content_obj) if raw_content_obj is not None else None
        payload.update({"kind": "text", "agent": sender, "content": clean_content})
        if serialized_raw is not None and not isinstance(serialized_raw, str):
            payload["raw_content"] = serialized_raw
        if not payload.get("agent"):
            fallback_agent = _extract_agent_name(serialized_raw) if serialized_raw is not None else None
            if not fallback_agent:
                fallback_agent = _extract_agent_name(getattr(ev, "sender", None))
            if not fallback_agent:
                fallback_agent = str(turn_agent) if turn_agent else None
            payload["agent"] = fallback_agent or "Assistant"
        try:
            if sender and workflow_name and agent_has_structured_output(workflow_name, sender):
                structured = _PM._extract_json_from_text(clean_content) if hasattr(_PM, '_extract_json_from_text') else None
                if structured:
                    payload["structured_output"] = structured
                    schema_fields = get_structured_output_model_fields(workflow_name, sender)
                    if schema_fields:
                        payload["structured_schema"] = schema_fields
                    try:
                        import json as _json
                        if isinstance(structured, dict):
                            so_keys = list(structured.keys())
                        elif isinstance(structured, list):
                            so_keys = [f"list[{len(structured)}]"]
                        else:
                            so_keys = [type(structured).__name__]
                        so_json = _json.dumps(structured, ensure_ascii=False)
                        max_len = 2000
                        if len(so_json) > max_len:
                            so_json = so_json[:max_len] + "...<truncated>"
                        wf_logger.info(f" [STRUCTURED_OUTPUT] agent={sender} keys={so_keys} json={so_json}")
                    except Exception as _so_log_err:  # pragma: no cover
                        wf_logger.debug(f"[STRUCTURED_OUTPUT] log skipped: {_so_log_err}")
        except Exception as so_err:  # pragma: no cover
            wf_logger.debug(f"Structured output attach failed sender={sender}: {so_err}")
        return payload

    if isinstance(ev, _PE):
        payload.update({
            "kind": "print",
            "agent": _extract_agent_name(ev),
            "content": _normalize_text_content(getattr(ev, "content", None)),
        })
        return payload

    if isinstance(ev, _IR):
        agent_name = _extract_agent_name(ev)
        request_obj = getattr(ev, "content", None)
        prompt_text = getattr(ev, "_mozaiks_prompt", None) or getattr(ev, "prompt", None)
        component_hint = None
        raw_payload = None
        if request_obj is not None:
            try:
                if prompt_text is None:
                    if hasattr(request_obj, "prompt"):
                        prompt_text = getattr(request_obj, "prompt")
                    elif isinstance(request_obj, dict):
                        prompt_text = request_obj.get("prompt") or request_obj.get("message")
                if hasattr(request_obj, "ui_tool_id"):
                    component_hint = getattr(request_obj, "ui_tool_id")
                elif isinstance(request_obj, dict):
                    component_hint = request_obj.get("ui_tool_id") or request_obj.get("component") or request_obj.get("component_type")
                if hasattr(request_obj, "model_dump"):
                    raw_payload = request_obj.model_dump()  # type: ignore[attr-defined]
                elif isinstance(request_obj, dict):
                    raw_payload = request_obj
            except Exception as prompt_err:
                wf_logger.debug(f"InputRequest prompt extraction failed: {prompt_err}")
        request_id = getattr(ev, "_mozaiks_request_id", None)
        if not request_id:
            request_id = getattr(ev, "uuid", None) or getattr(ev, "id", None)
        if request_id:
            request_id = str(request_id)
        payload.update({
            "kind": "input_request",
            "agent": agent_name,
            "request_id": request_id,
            "prompt": (prompt_text or ""),
        })
        payload["password"] = bool(getattr(ev, "password", False))
        if component_hint:
            payload["component_type"] = component_hint
        if raw_payload is not None:
            payload["raw_payload"] = raw_payload
        return payload

    if isinstance(ev, InputTimeoutEvent):
        agent_name = _extract_agent_name(ev)
        payload.update({
            "kind": "input_timeout",
            "agent": agent_name,
            "input_request_id": getattr(ev, "input_request_id", None),
            "timeout_seconds": getattr(ev, "timeout_seconds", None),
        })
        return payload

    if isinstance(ev, _SS):
        agent_name = _extract_agent_name(ev)
        next_agent_obj = getattr(ev, "agent", None)
        next_agent = None
        if next_agent_obj:
            next_agent = getattr(next_agent_obj, "name", None) or str(next_agent_obj)
        payload.update({
            "kind": "select_speaker",
            "agent": agent_name,
            "next": next_agent,
        })
        return payload

    if isinstance(ev, _GR):
        payload.update({"kind": "resume_boundary"})
        return payload

    # GroupChatRunChatEvent -------------------------------------------
    if isinstance(ev, _GRCE):
        payload.update({"kind": "unknown"})
        return payload

    if isinstance(ev, (_FCe, _TCe)):
        content_obj = None
        tool_name = None
        tool_calls = getattr(ev, "tool_calls", None)
        if isinstance(tool_calls, list) and tool_calls:
            first_call = tool_calls[0]
            fn = getattr(first_call, "function", None)
            name_attr = getattr(fn, "name", None)
            if isinstance(name_attr, str):
                tool_name = name_attr
        if not tool_name:
            function_call = getattr(ev, "function_call", None)
            fn_name = getattr(function_call, "name", None)
            if isinstance(fn_name, str):
                tool_name = fn_name
        if not tool_name:
            content_obj = getattr(ev, "content", None)
            tool_name = (
                getattr(ev, "tool_name", None)
                or getattr(content_obj, "name", None)
                or getattr(content_obj, "tool_name", None)
            )
            if not tool_name and content_obj:
                tool_calls = getattr(content_obj, "tool_calls", None)
                if isinstance(tool_calls, list) and tool_calls:
                    first_tool = tool_calls[0]
                    function_obj = getattr(first_tool, "function", None)
                    if function_obj:
                        tool_name = getattr(function_obj, "name", None)
                        if tool_name:
                            wf_logger.debug(f" [TOOL_EXTRACT] Found tool name: {tool_name}")
        if not tool_name:
            tool_name = "unknown_tool"
        tool_call_id = (
            getattr(ev, "id", None)
            or getattr(ev, "uuid", None)
            or f"tool_{tool_name}"
        )
        extracted_args: Dict[str, Any] = {}
        try:
            if isinstance(tool_calls, list) and tool_calls:
                first_tool = tool_calls[0]
                f_fn = getattr(first_tool, "function", None)
                if f_fn is not None:
                    poss_args = getattr(f_fn, "arguments", None)
                    if isinstance(poss_args, dict):
                        extracted_args = poss_args
            if not extracted_args:
                function_call = getattr(ev, "function_call", None)
                if function_call is not None:
                    poss_args = getattr(function_call, "arguments", None)
                    if isinstance(poss_args, dict):
                        extracted_args = poss_args
            if not extracted_args and content_obj is None:
                content_obj = getattr(ev, "content", None)
            if not extracted_args and content_obj is not None:
                poss_args = getattr(content_obj, "arguments", None)
                if isinstance(poss_args, dict):
                    extracted_args = poss_args
        except Exception as arg_ex:
            wf_logger.debug(f"[TOOL_ARGS] extraction failed for {tool_name}: {arg_ex}")
        agent_for_tool = _extract_agent_name(ev) or turn_agent or getattr(ev, "sender", None)
        if tool_call_id:
            tool_names_by_id[str(tool_call_id)] = str(tool_name)
        init_agent = agent_for_tool or payload.get("agent")
        if init_agent and tool_call_id:
            tool_call_initiators[str(tool_call_id)] = init_agent
        if extracted_args:
            payload.update({
                "kind": "tool_call",
                "agent": agent_for_tool,
                "tool_name": str(tool_name),
                "tool_call_id": str(tool_call_id),
                "corr": str(tool_call_id),
                "component_type": "inline",
                "awaiting_response": True,
                "payload": {
                    "tool_args": extracted_args,
                    "interaction_type": "input",
                    "agent_name": agent_for_tool,
                },
            })
            logger.info(f" [TOOL_CALL] agent={agent_for_tool} tool={tool_name} id={tool_call_id} args_keys={list(extracted_args.keys())}")
        else:
            logger.debug(f" [TOOL_CALL_SUPPRESSED] tool={tool_name} id={tool_call_id} (no args)")
        return payload

    if isinstance(ev, (_FRe, _TRe)):
        tool_name = getattr(ev, "tool_name", None)
        content_obj = getattr(ev, "content", None)
        if not tool_name and content_obj:
            tool_name = (
                getattr(content_obj, "tool_name", None)
                or getattr(content_obj, "name", None)
            )
        if not tool_name and content_obj:
            tool_calls = getattr(content_obj, "tool_calls", None)
            if isinstance(tool_calls, list) and tool_calls:
                first_tool = tool_calls[0]
                function_obj = getattr(first_tool, "function", None)
                if function_obj:
                    tool_name = getattr(function_obj, "name", None)
                    if tool_name:
                        wf_logger.debug(f" [TOOL_EXTRACT_RESPONSE] Found tool name: {tool_name}")
        if not tool_name:
            tool_name = "unknown_tool"
        agent_name = _extract_agent_name(ev)
        tool_response_id = (
            getattr(ev, "id", None)
            or getattr(ev, "uuid", None)
            or getattr(ev, "tool_call_id", None)
        )
        if not agent_name and tool_response_id:
            fallback_agent = tool_call_initiators.get(str(tool_response_id))
            if fallback_agent:
                agent_name = fallback_agent
                logger.debug(f" [TOOL_RESPONSE_AGENT_FALLBACK] Using initiator agent={agent_name} for tool_response id={tool_response_id}")
        if (not tool_name or tool_name == "unknown_tool") and tool_response_id:
            tool_name = tool_names_by_id.get(str(tool_response_id), tool_name)
        payload.update({
            "kind": "tool_response",
            "tool_name": str(tool_name),
            "agent": agent_name,
            "tool_call_id": str(tool_response_id) if tool_response_id else None,
            "corr": str(tool_response_id) if tool_response_id else None,
            "content": getattr(ev, "content", None),
        })
        wf_logger.debug(f" [TOOL_RESPONSE] agent={agent_name} tool={tool_name} id={tool_response_id}")
        return payload

    if isinstance(ev, _US):
        for f in ("total_tokens", "prompt_tokens", "completion_tokens", "cost", "model"):
            if hasattr(ev, f):
                payload[f] = getattr(ev, f)
        payload.update({"kind": "usage_summary"})
        return payload

    if isinstance(ev, _EE):
        agent_name = _extract_agent_name(ev)
        payload.update({
            "kind": "error",
            "agent": agent_name,
            "message": getattr(ev, "message", None) or getattr(ev, "content", None) or str(ev),
        })
        return payload

    if isinstance(ev, _RC):
        rc_agent = _extract_agent_name(ev) or getattr(ev, "agent", None) or "workflow"
        payload.update({
            "kind": "run_complete",
            "agent": rc_agent,
        })
        return payload

    payload.update({"kind": "unknown"})
    return payload
    
# ===================================================================
# SINGLE ENTRY POINT
# ===================================================================

def _normalize_human_in_the_loop(value) -> bool:
    """Normalize human_in_the_loop config values to a strict boolean.

    Accepts booleans directly, and common string/int representations:
    - True-y: "true", "yes", "1", "on", "always"
    - False-y: "false", "no", "0", "of", "never"
    Any other value defaults to False.
    """
    if isinstance(value, bool):
        return value
    # Handle integers passed through env parsing, etc.
    try:
        if isinstance(value, (int, float)):
            return bool(int(value))
    except Exception:
        pass
    if isinstance(value, str):
        v = value.strip().lower()
        if v in {"true", "yes", "1", "on", "always"}:
            return True
        if v in {"false", "no", "0", "of", "never"}:
            return False
    return False

"""Internal helper: load workflow config block."""
def _load_workflow_config(workflow_name: str):
    from .workflow_manager import workflow_manager
    config = workflow_manager.get_config(workflow_name)
    return {
        "config": config,
        "max_turns": config.get("max_turns", 50),
        "orchestration_pattern": config.get("orchestration_pattern", "AutoPattern"),
        "startup_mode": config.get("startup_mode", "AgentDriven"),
        "human_in_loop": _normalize_human_in_the_loop(config.get("human_in_the_loop", False)),
        "initial_agent_name": config.get("initial_agent", None),
    }


async def _resume_or_initialize_chat(
    persistence_manager: AG2PersistenceManager,
    termination_handler,
    config: Dict[str, Any],
    chat_id: str,
    enterprise_id: str,
    workflow_name: str,
    user_id: Optional[str],
    initial_message: Optional[str],
    wf_logger,
):
    resumed_messages = await persistence_manager.resume_chat(chat_id, enterprise_id)
    resume_raw_count = len(resumed_messages or [])

    # Determine if the resumed messages actually constitute a prior conversation.
    # We ignore purely system/context/metadata scaffolding so brand-new chats created
    # earlier (e.g. by a pre-flight ping) are not misclassified as a resume.
    meaningful_roles = {"user", "assistant", "agent", "tool"}
    meaningful_messages: List[Dict[str, Any]] = []
    for m in resumed_messages or []:
        role = m.get("role") if isinstance(m, dict) else None
        if role in meaningful_roles:
            meaningful_messages.append(m)

    resume_valid = resume_raw_count > 0 and len(meaningful_messages) > 0

    if resume_valid:
        wf_logger.info(
            f" [RESUME_DETECT] Resuming chat {chat_id}: total_messages={resume_raw_count} meaningful={len(meaningful_messages)}"
        )
        initial_messages: List[Dict[str, Any]] = list(resumed_messages or [])  # shallow copy to append safely
        if initial_message:
            initial_messages.append({"role": "user", "name": "user", "content": initial_message, "_mozaiks_seed_kind": "initial_message"})
    else:
        if resume_raw_count > 0:
            wf_logger.info(
                f" [RESUME_DETECT] Discarding resume for chat {chat_id}: only {resume_raw_count} scaffolding messages (meaningful=0). Treating as NEW."
            )
        else:
            wf_logger.info(f" [RESUME_DETECT] No prior messages for chat {chat_id}. Starting NEW chat.")
        resumed_messages = []  # normalize to empty for downstream checks
        initial_messages = []
        if initial_message:
            initial_messages.append({"role": "user", "name": "user", "content": initial_message, "_mozaiks_seed_kind": "initial_message"})
        current_user_id = user_id or "system_user"
        if not user_id:
            logger.warning(f"Starting chat {chat_id} without a specific user_id. Defaulting to 'system_user'.")
        try:
            await persistence_manager.create_chat_session(
                chat_id=chat_id,
                enterprise_id=enterprise_id,
                workflow_name=workflow_name,
                user_id=current_user_id,
            )
        except Exception as cs_err:
            wf_logger.error(f" Failed to create chat session doc for {chat_id}: {cs_err}")
        try:
            await termination_handler.on_conversation_start(user_id=current_user_id)
            logger.info(" Termination handler started for new conversation")
        except Exception as start_err:
            logger.error(f" Termination handler start failed: {start_err}")
        # Optionally persist the seed / initial messages. Disabled by default to avoid
        # duplicates when AG2 itself emits the initial user message as a TextEvent.
        # Enable by setting ENABLE_MANUAL_INITIAL_PERSIST=1
        import os
        if os.getenv("ENABLE_MANUAL_INITIAL_PERSIST") == "1":
            try:
                if initial_messages:
                    await persistence_manager.persist_initial_messages(
                        chat_id=chat_id,
                        enterprise_id=enterprise_id,
                        messages=initial_messages,
                    )
            except Exception as init_persist_err:  # pragma: no cover
                wf_logger.debug(f" Failed to persist initial messages for {chat_id}: {init_persist_err}")
    if not initial_messages:
        seed = config.get("initial_message") or config.get("initial_message_to_user")
        if seed:
            seed_kind = "initial_message" if config.get("initial_message") else "initial_message_to_user"
            initial_messages = [{"role": "user", "name": "user", "content": seed, "_mozaiks_seed_kind": seed_kind}]
            import os as _os
            if _os.getenv("ENABLE_MANUAL_INITIAL_PERSIST") == "1":
                # Persist config-seeded initial message too (optional)
                try:
                    await persistence_manager.persist_initial_messages(
                        chat_id=chat_id,
                        enterprise_id=enterprise_id,
                        messages=initial_messages,
                    )
                except Exception as seed_persist_err:  # pragma: no cover
                    wf_logger.debug(f" Failed to persist config seed message for {chat_id}: {seed_persist_err}")
    return resumed_messages, initial_messages


async def _load_llm_config(workflow_name: str, wf_logger, workflow_name_upper: str, *, cache_seed: Optional[int] = None):
    from .structured_outputs import get_llm_for_workflow
    try:
        extra = {"cache_seed": cache_seed} if cache_seed is not None else None
        _, llm_config = await get_llm_for_workflow(workflow_name, "base", extra_config=extra)
        wf_logger.info(f" [{workflow_name_upper}] Using workflow-specific LLM config")
    except (ValueError, FileNotFoundError):
        from .llm_config import get_llm_config
        extra = {"cache_seed": cache_seed} if cache_seed is not None else None
        _, llm_config = await get_llm_config(extra_config=extra)
        wf_logger.info(f" [{workflow_name_upper}] Using default LLM config")
    return llm_config


async def _build_context_blocking(
    context_factory: Optional[Callable],
    workflow_name: str,
    enterprise_id: str,
    chat_id: str,
    user_id: Optional[str],
    wf_logger,
    workflow_name_upper: str,
):
    """Build context and wait for it to be fully populated before first turn.

    - If a context_factory is provided, supports both sync and async factories.
    """
    try:
        if context_factory:
            result = context_factory()
            if inspect.isawaitable(result):
                return await result
            return result
        from .context_variables import _load_context_async
        # Use the internal async loader directly to ensure blocking population
        return await _load_context_async(workflow_name, enterprise_id)
    except Exception as e:
        wf_logger.error(f" [{workflow_name_upper}] Context load failed: {e}")
        return None


async def _create_agents(agents_factory: Optional[Callable], workflow_name: str, context_variables=None, *, cache_seed: Optional[int] = None):
    """Create agents for the workflow following AG2 patterns.

    Clean API: agents_factory(workflow_name, context_variables, cache_seed)
    """
    if agents_factory:
        return await agents_factory(workflow_name, context_variables, cache_seed)
    from .agents import create_agents
    return await create_agents(workflow_name, context_variables=context_variables, cache_seed=cache_seed)


def _ensure_user_proxy(
    agents: Dict[str, ConversableAgent],
    config: Dict[str, Any],
    startup_mode: str,
    llm_config: Dict[str, Any],
    human_in_loop: bool,
) -> Tuple[Dict[str, ConversableAgent], Optional[UserProxyAgent], bool]:
    user_proxy_agent: Optional[UserProxyAgent] = None
    user_proxy_exists = any(
        hasattr(a, "name") and a.name.lower() in ("user", "userproxy", "userproxyagent")
        for a in agents.values()
    )
    if not user_proxy_exists:
        human_in_loop_flag = _normalize_human_in_the_loop(config.get("human_in_the_loop", False))
        if startup_mode == "BackendOnly":
            human_input_mode = "NEVER"
        elif startup_mode == "UserDriven":
            human_input_mode = "ALWAYS"
        else:
            human_input_mode = "TERMINATE"
        user_proxy_agent = UserProxyAgent(
            name="user",
            human_input_mode=human_input_mode,
            max_consecutive_auto_reply=0,
            code_execution_config={"use_docker": False},
            system_message="You are a helpful user proxy.",
            llm_config=llm_config,
        )
        agents["user"] = user_proxy_agent
        human_in_loop = human_in_loop_flag
    else:
        for a in agents.values():
            if hasattr(a, "name") and a.name.lower() in ("user", "userproxy", "userproxyagent"):
                user_proxy_agent = a  # type: ignore[assignment]
                break
    return agents, user_proxy_agent, human_in_loop


def _resolve_initiating_agent(agents: Dict[str, ConversableAgent], initial_agent_name: Optional[str], workflow_name: str):
    initiating_agent = None
    if initial_agent_name:
        initiating_agent = agents.get(initial_agent_name)
        if not initiating_agent:
            for a in agents.values():
                if getattr(a, "name", None) == initial_agent_name:
                    initiating_agent = a
                    break
    if not initiating_agent:
        initiating_agent = next(iter(agents.values())) if agents else None
        if not initiating_agent:
            raise ValueError(f"No agents available for workflow {workflow_name}")
    return initiating_agent


def _filter_agents_for_pattern(
    agents: Dict[str, ConversableAgent],
    human_in_loop: bool,
    user_proxy_agent: Optional[UserProxyAgent]
) -> List[ConversableAgent]:
    """Filter agents list for AG2 pattern, excluding user proxy if handled separately."""
    agents_list = []
    for name, agent in agents.items():
        # Skip user proxy if it's handled separately in human-in-the-loop mode
        if name == "user" and human_in_loop and user_proxy_agent is not None:
            continue
        agents_list.append(agent)
    return agents_list


def _convert_to_ag2_context(context_variables: Any, wf_logger) -> Any:
    """Convert context variables to AG2 ContextVariables instance."""
    from autogen.agentchat.group import ContextVariables as AG2ContextVariables

    if context_variables is None:
        return AG2ContextVariables()
    elif isinstance(context_variables, AG2ContextVariables):
        return context_variables
    else:
        # Convert from our context system to AG2 ContextVariables
        try:
            if hasattr(context_variables, 'to_dict'):
                return AG2ContextVariables(data=context_variables.to_dict())
            elif isinstance(context_variables, dict):
                return AG2ContextVariables(data=context_variables)
            else:
                return AG2ContextVariables(data={"value": context_variables})
        except Exception as _cv_err:
            wf_logger.warning(f" [CONTEXT] Context conversion failed: {_cv_err}")
            return AG2ContextVariables()


async def _create_ag2_pattern(
    orchestration_pattern: str,
    workflow_name: str,
    agents: Dict[str, ConversableAgent],
    initiating_agent: ConversableAgent,
    user_proxy_agent: Optional[UserProxyAgent],
    human_in_loop: bool,
    context_variables: Any,
    llm_config: Dict[str, Any],
    handoffs_factory: Optional[Callable],
    wf_logger,
    chat_id: str,
    enterprise_id: str,
    user_id: Optional[str],
):
    """Create AG2 Pattern with proper context variables integration."""
    # Convert agents dict to list for AG2 pattern (exclude user proxy if handled separately)
    agents_list = _filter_agents_for_pattern(agents, human_in_loop, user_proxy_agent)
    
    # Ensure we have proper AG2 ContextVariables instance
    ag2_context = _convert_to_ag2_context(context_variables, wf_logger)
    
    # Ensure core WebSocket path parameters are always available
    # These may already be set by _build_context_blocking, but we ensure they're present
    if not ag2_context.get("workflow_name"):
        ag2_context.set("workflow_name", workflow_name)
    if not ag2_context.get("enterprise_id"):
        ag2_context.set("enterprise_id", enterprise_id)
    if not ag2_context.get("chat_id"):
        ag2_context.set("chat_id", chat_id)
    # Optionally attach user_id if provided
    if user_id and not ag2_context.get("user_id"):
        ag2_context.set("user_id", user_id)

    # Log final context state with emphasis on routing keys
    context_keys = list(ag2_context.data.keys())
    wf_logger.info(
        f"[CONTEXT] AG2 ContextVariables ready | total_keys={len(context_keys)} | "
        f"workflow_name={ag2_context.get('workflow_name')} | "
        f"enterprise_id={ag2_context.get('enterprise_id')} | "
        f"chat_id={ag2_context.get('chat_id')} | "
        f"user_id={ag2_context.get('user_id')}"
    )

    # Create AG2 Pattern following proper constructor signature
    pattern = create_ag2_pattern(
        pattern_name=orchestration_pattern,
        initial_agent=initiating_agent,
        agents=agents_list,
        user_agent=user_proxy_agent,
        context_variables=ag2_context,
        group_manager_args={"llm_config": llm_config},
    )
    try:
        snapshot = _safe_context_snapshot(ag2_context)
        wf_logger.info(
            f" [CONTEXT_INIT] AG2 context constructed | keys={list(snapshot.keys())}"
        )
        wf_logger.debug(
            f" [CONTEXT_INIT_DEBUG] snapshot={snapshot}"
        )
    except Exception as _snap_log_err:  # pragma: no cover
        wf_logger.debug(f" [CONTEXT_INIT] snapshot logging failed: {_snap_log_err}")
    try:
        # Light sanity: if pattern exposes group_manager/context_variables, log keys
        gm = getattr(pattern, "group_manager", None)
        if gm and hasattr(gm, "context_variables"):
            cv = getattr(gm, "context_variables")
            keys = list(getattr(cv, "data", {}).keys()) if hasattr(cv, "data") else []
            wf_logger.info(f" [PATTERN] ContextVariables attached to group manager | keys={keys}")
            try:
                wf_logger.debug(f" [PATTERN_DEBUG] group_manager.context snapshot={_safe_context_snapshot(cv)}")
            except Exception:
                pass
        else:
            wf_logger.debug("[PATTERN] Group manager or context_variables attribute not available for logging")
    except Exception as _pat_log_err:
        wf_logger.debug(f"[PATTERN] Context logging skipped: {_pat_log_err}")
    if orchestration_pattern == "DefaultPattern":
        try:
            if handoffs_factory:
                await handoffs_factory(agents)
            else:
                from .handoffs import wire_handoffs_with_debugging
                wire_handoffs_with_debugging(workflow_name, agents)
        except Exception as he:
            wf_logger.warning(f"Handoffs wiring failed: {he}")
    return pattern, ag2_context


async def _stream_events(
    pattern,
    resumed_messages,
    initial_messages,
    max_turns: int,
    agents: Dict[str, ConversableAgent],
    chat_id: str,
    enterprise_id: str,
    workflow_name: str,
    wf_logger,
    workflow_name_upper: str,
    transport,
    termination_handler,
    user_id: Optional[str],
    persistence_manager: AG2PersistenceManager,
    perf_mgr,
    derived_context_manager: Optional[DerivedContextManager] = None,
):
    """Stream AG2 events, forwarding them to transport/UI and persisting as needed.

    NOTE: This function was previously extremely complex with a very large if/elif
    ladder for event-type specific payload construction. To reduce cyclomatic complexity
    (and satisfy static analysis warnings around line ~582), the payload construction
    logic has been extracted into the helper `_build_ui_event_payload`. All original
    behavior, field names, and logging semantics are preserved. Only structural
    refactoring (no functional changes) has been performed.
    """
    # Import AG2 group chat execution and events
    from autogen.agentchat import a_run_group_chat
    from autogen.events.client_events import UsageSummaryEvent

    # pattern.context_variables provided by AG2 pattern if needed

    try:
        structured_registry = get_structured_outputs_for_workflow(workflow_name)
    except Exception as so_err:
        structured_registry = {}
        wf_logger.debug(f"[{workflow_name_upper}] Structured outputs unavailable: {so_err}")

    auto_tool_agents = {name for name, agent in agents.items() if getattr(agent, '_mozaiks_auto_tool_mode', False)}
    if auto_tool_agents:
        wf_logger.info(f" [{workflow_name_upper}] Auto-tool agents detected: {sorted(auto_tool_agents)}")
    else:
        wf_logger.debug(f" [{workflow_name_upper}] No auto-tool agents registered for this run.")
    dispatcher = get_event_dispatcher()
    if auto_tool_agents:
        wf_logger.info(f" [{workflow_name_upper}] Auto-tool agents detected: {sorted(auto_tool_agents)}")
    
    # Load lifecycle tools for this workflow
    from core.workflow.lifecycle_tools import get_lifecycle_manager
    lifecycle_manager = get_lifecycle_manager(workflow_name)

    resumed_mode = bool(resumed_messages)
    # Log which context keys are present at stream start for diagnostics
    try:
        gm_ctx_keys = []
        gm = getattr(pattern, "group_manager", None)
        if gm and hasattr(gm, "context_variables"):
            cv = getattr(gm, "context_variables")
            if hasattr(cv, "data") and isinstance(getattr(cv, "data"), dict):
                gm_ctx_keys = list(cv.data.keys())
            elif hasattr(cv, "to_dict"):
                gm_ctx_keys = list(cv.to_dict().keys())
        wf_logger.info(f" [EVENTS_INIT] ContextVariables available at start | keys={gm_ctx_keys}")
    except Exception as _ctx_log_err:
        wf_logger.debug(f"[EVENTS_INIT] ContextVariables keys logging skipped: {_ctx_log_err}")
    if resumed_mode:
        wf_logger.info(f" [AG2_RESUME] Using AG2 a_resume path for chat {chat_id} (history={len(initial_messages)} messages)")
        wf_logger.info(f" [AG2_RESUME] Pattern type: {type(pattern).__name__} | Messages count: {len(initial_messages)}")
        
        # Log initial messages for debugging
        for i, msg in enumerate(initial_messages):
            wf_logger.debug(f" [AG2_RESUME] Message[{i}]: {msg.get('role', 'unknown')} from {msg.get('name', 'unknown')}")
        
        # Some AG2 patterns now require max_rounds parameter; inspect signature to decide.
        import inspect as _inspect
        _pgc = getattr(pattern, "prepare_group_chat", None)
        if callable(_pgc):
            _sig = _inspect.signature(_pgc)
            if "max_rounds" in _sig.parameters:
                wf_logger.debug(" [AG2_RESUME] prepare_group_chat supports max_rounds -> passing it explicitly")
                prep_res = _pgc(messages=initial_messages, max_rounds=max_turns)  # type: ignore[attr-defined]
            else:
                prep_res = _pgc(messages=initial_messages)  # type: ignore[attr-defined]
        else:
            raise RuntimeError("Pattern missing prepare_group_chat callable during resume path")
        if asyncio.iscoroutine(prep_res):  # type: ignore
            prep_res = await prep_res  # type: ignore
        if isinstance(prep_res, (list, tuple)) and len(prep_res) == 2:
            group_manager = prep_res[1]
        else:
            group_manager = getattr(pattern, "group_manager", None)
            
        wf_logger.info(f" [AG2_RESUME] Group manager resolved: {type(group_manager).__name__ if group_manager else 'None'}")
        
        if not group_manager or not hasattr(group_manager, "a_resume"):
            wf_logger.error(" [AG2_RESUME] Pattern missing required a_resume capability!")
            raise RuntimeError("Pattern missing required a_resume capability; backward compatibility removed")
            
        wf_logger.info(f" [AG2_RESUME] Calling group_manager.a_resume() with {len(initial_messages)} messages, max_rounds={max_turns}")
        
        try:
            # Remove hard timeout to avoid cancelling when user feedback is slow
            response = await group_manager.a_resume(messages=initial_messages, max_rounds=max_turns)  # type: ignore[attr-defined]
            wf_logger.info(" [AG2_RESUME] a_resume() initialized successfully!")
        except Exception as resume_err:
            wf_logger.error(f" [AG2_RESUME] a_resume() failed: {resume_err}")
            raise
    else:
        wf_logger.info(f" [AG2_RUN] Using AG2 a_run_group_chat for NEW chat {chat_id}")
        wf_logger.info(f" [AG2_RUN] Pattern type: {type(pattern).__name__} | Messages count: {len(initial_messages)} | Max rounds: {max_turns}")
        
        # Log initial messages for debugging
        for i, msg in enumerate(initial_messages):
            wf_logger.debug(f" [AG2_RUN] Message[{i}]: {msg.get('role', 'unknown')} from {msg.get('name', 'unknown')} - {str(msg.get('content', ''))[:100]}")
            
        #  AG2 handles context variables setup internally via prepare_group_chat
        
        wf_logger.info(" [AG2_RUN] Calling a_run_group_chat() NOW...")
        
        try:
            # Remove hard timeout to avoid cancelling when user feedback is slow
            response = await a_run_group_chat(pattern=pattern, messages=initial_messages, max_rounds=max_turns)
            wf_logger.info(" [AG2_RUN] a_run_group_chat() initialized successfully!")
        except Exception as run_err:
            wf_logger.error(f" [AG2_RUN] a_run_group_chat() failed: {run_err}")
            raise

    turn_agent: Optional[str] = None
    turn_started: Optional[float] = None
    sequence_counter = 0
    first_event_logged = False
    chat_logger.info(f"[EVENT_STREAM] Starting event processing loop for chat {chat_id}")

    pending_input_requests: dict[str, Any] = {}
    # Track which agent initiated each tool call so we can echo it on the response if missing
    tool_call_initiators: dict[str, str] = {}
    # Track tool names by id so responses can be labeled even if AG2 omits tool_name
    tool_names_by_id: dict[str, str] = {}
    # Track schema validation retries per call/agent so we avoid infinite loops
    schema_retry_tracker: dict[str, int] = {}
    MAX_SCHEMA_RETRIES = 2

    def _build_auto_tool_context_payload(turn_sequence: int) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "chat_id": chat_id,
            "enterprise_id": enterprise_id,
            "workflow_name": workflow_name,
            "turn_sequence": turn_sequence,
        }
        try:
            ctx_source = None
            gm_candidate = getattr(pattern, "group_manager", None)
            if gm_candidate and hasattr(gm_candidate, "context_variables"):
                ctx_source = getattr(gm_candidate, "context_variables")
            elif hasattr(pattern, "context_variables"):
                ctx_source = getattr(pattern, "context_variables")

            raw_ctx: Optional[Dict[str, Any]] = None
            if ctx_source is not None:
                if hasattr(ctx_source, "data") and isinstance(getattr(ctx_source, "data"), dict):
                    raw_ctx = dict(getattr(ctx_source, "data"))  # type: ignore[arg-type]
                elif hasattr(ctx_source, "to_dict") and callable(getattr(ctx_source, "to_dict")):
                    raw_ctx = dict(ctx_source.to_dict())  # type: ignore[arg-type]
                elif isinstance(ctx_source, dict):
                    raw_ctx = dict(ctx_source)

            if raw_ctx:
                sanitized: Dict[str, Any] = {}
                for key, value in raw_ctx.items():
                    try:
                        sanitized[key] = serialize_event_content(value)
                    except Exception:
                        sanitized[key] = str(value)
                payload["context_variables"] = sanitized
        except Exception as ctx_err:
            wf_logger.debug(
                f" [{workflow_name_upper}] Auto-tool context snapshot failed: {ctx_err}"
            )
        return payload

    def _resolve_agent_object(agent_name: Optional[str]):
        if not agent_name:
            return None
        if agent_name in agents:
            return agents[agent_name]
        for candidate in agents.values():
            if getattr(candidate, "name", None) == agent_name:
                return candidate
        return None
    # ------------------------------------------------------------------
    # Verbose context diff support (optional via CONTEXT_VERBOSE_DEBUG=1)
    # ------------------------------------------------------------------
    verbose_ctx = os.getenv("CONTEXT_VERBOSE_DEBUG", "0").strip() in {"1", "true", "True"}
    prev_ctx_snapshot: Dict[str, Any] = {}
    if verbose_ctx:
        try:
            gm0 = getattr(pattern, "group_manager", None)
            base_ctx = None
            if gm0 and hasattr(gm0, "context_variables"):
                base_ctx = getattr(gm0, "context_variables")
            elif hasattr(pattern, "context_variables"):
                base_ctx = getattr(pattern, "context_variables")
            prev_ctx_snapshot = _safe_context_snapshot(base_ctx) if base_ctx else {}
            wf_logger.info(f" [CONTEXT_VERBOSE] Baseline snapshot captured | keys={len(prev_ctx_snapshot)}")
        except Exception as _init_snap_err:
            wf_logger.debug(f" [CONTEXT_VERBOSE] baseline snapshot failed: {_init_snap_err}")


    seed_user_messages = Counter()
    try:
        for seed in initial_messages or []:
            if (
                isinstance(seed, dict)
                and seed.get('role') == 'user'
                and seed.get('_mozaiks_seed_kind') == 'initial_message'
            ):
                content = seed.get('content')
                if isinstance(content, str) and content.strip():
                    seed_user_messages[content.strip()] += 1
    except Exception:
        seed_user_messages = Counter()

    try:
        if transport:
            transport.register_orchestration_input_registry(chat_id, pending_input_requests)  # type: ignore[attr-defined]
    except Exception as e:
        logger.debug(f"Failed to register orchestration input registry for {chat_id}: {e}")

    from .ui_tools import handle_tool_call_for_ui_interaction
    from autogen.events.agent_events import FunctionCallEvent as _FC, ToolCallEvent as _TC
    try:
        executed_agents: set[str] = set()
        async for ev in response.events:  # type: ignore[attr-defined]
            if not first_event_logged:
                wf_logger.info(
                    f" [{workflow_name_upper}] First event received: {ev.__class__.__name__} chat_id={chat_id}"
                )
                first_event_logged = True
            sequence_counter += 1
            
            # Comprehensive event tracing for debugging
            event_class = ev.__class__.__name__
            if event_class == 'TextEvent':
                try:
                    from core.events.event_serialization import extract_agent_name
                    agent_name = extract_agent_name(ev)
                    content = getattr(ev, 'content', '')
                    content_preview = str(content)[:100] if content else 'None'
                    wf_logger.info(f" [EVENT_TRACE] {event_class} from {agent_name}: content_len={len(str(content)) if content else 0} preview='{content_preview}...'")
                    if agent_name == 'ContextAgent':
                        wf_logger.info(f" [CONTEXT_AGENT_TRACE] ContextAgent event detected! auto_tool_agents={auto_tool_agents}")
                except Exception as trace_err:
                    wf_logger.debug(f" [EVENT_TRACE] Error tracing {event_class}: {trace_err}")
            else:
                wf_logger.debug(f" [EVENT_TRACE] {event_class} event received")
            # Context diffing relies on prev_ctx_snapshot captured before the loop; no per-event copy needed here.
            # TextEvent persistence + forwarding (wrapped in tight try so other event types continue on failure)
            if isinstance(ev, TextEvent):
                try:
                    await persistence_manager.save_event(ev, chat_id, enterprise_id)  # type: ignore[arg-type]
                    if derived_context_manager:
                        derived_context_manager.handle_event(ev)

                    # Forward TextEvent to UI via WebSocket (inner try isolates transport issues)
                    try:
                        from core.transport.simple_transport import SimpleTransport
                        transport = await SimpleTransport.get_instance()
                        if transport:
                            sender_name = _extract_agent_name(ev)
                            if not sender_name:
                                sender_attr = getattr(ev, 'sender', None)
                                if isinstance(sender_attr, str) and sender_attr.strip():
                                    sender_name = sender_attr.strip()
                                elif hasattr(sender_attr, 'name') and isinstance(getattr(sender_attr, 'name'), str):
                                    sender_name = getattr(sender_attr, 'name').strip()
                            sender_name = sender_name or 'Agent'
                            message_content = _normalize_text_content(getattr(ev, 'content', None))
                            content_key = message_content.strip()
                            sender_lower = sender_name.lower() if isinstance(sender_name, str) else ''
                            if content_key and seed_user_messages.get(content_key) and sender_lower in {'user', 'chat_manager', 'manager', 'agentmanager'}:
                                seed_user_messages[content_key] -= 1
                                if seed_user_messages[content_key] <= 0:
                                    seed_user_messages.pop(content_key, None)
                                wf_logger.debug(f" [{workflow_name_upper}] Suppressed seeded initial message for chat {chat_id}")
                                continue

                            wf_logger.info(
                                f" [{workflow_name_upper}] TextEvent details: sender='{sender_name}' content='{message_content[:100]}...' "
                                f"content_len={len(message_content)} has_sender={hasattr(ev, 'sender')} has_content={hasattr(ev, 'content')}"
                            )
                            
                            wf_logger.info(f" [{workflow_name_upper}] 🚨 CHECKPOINT A: About to check auto-tool intercept")
                            
                            # AUTO-TOOL INTERCEPT: Process ContextAgent structured outputs before UI forwarding
                            import uuid
                            actual_message_to_send = message_content
                            
                            wf_logger.info(f" [{workflow_name_upper}] 🚨 CHECKPOINT B: Variables initialized, checking auto_tool_agents")
                            try:
                                wf_logger.info(f" [{workflow_name_upper}] Auto-tool debug: sender_name='{sender_name}' type={type(sender_name)}")
                                wf_logger.info(f" [{workflow_name_upper}] Auto-tool debug: auto_tool_agents={auto_tool_agents}")
                                wf_logger.info(f" [{workflow_name_upper}] Auto-tool debug: sender in agents? {sender_name in auto_tool_agents}")
                            except Exception as debug_err:
                                wf_logger.error(f" [{workflow_name_upper}] Debug logging error: {debug_err}")
                            if sender_name in auto_tool_agents:
                                wf_logger.info(f" [{workflow_name_upper}] Auto-tool intercept for {sender_name} (content_len={len(message_content)})")
                                
                                # Try to extract structured output from message content
                                structured_blob = None
                                try:
                                    from core.data.persistence_manager import AG2PersistenceManager as _PM
                                    if hasattr(_PM, '_extract_json_from_text'):
                                        structured_blob = _PM._extract_json_from_text(message_content)
                                        wf_logger.info(f" [{workflow_name_upper}] JSON extraction result for {sender_name}: {structured_blob is not None}")
                                    
                                    if not structured_blob and isinstance(message_content, str):
                                        # Fallback: direct JSON parsing
                                        import json
                                        try:
                                            stripped_content = message_content.strip()
                                            if stripped_content.startswith('{') and stripped_content.endswith('}'):
                                                structured_blob = json.loads(stripped_content)
                                                wf_logger.info(f" [{workflow_name_upper}] Direct JSON parsing succeeded for {sender_name}")
                                        except json.JSONDecodeError:
                                            pass
                                    
                                    if structured_blob and isinstance(structured_blob, dict):
                                        # We have valid structured output - process it
                                        wf_logger.info(f" [{workflow_name_upper}] Structured output detected for {sender_name}, keys: {list(structured_blob.keys())}")
                                        
                                        # Extract friendly message from structured output
                                        agent_message = structured_blob.get("agent_message")
                                        if isinstance(agent_message, str) and agent_message.strip():
                                            actual_message_to_send = agent_message.strip()
                                            wf_logger.info(f" [{workflow_name_upper}] Using agent_message as display text: '{actual_message_to_send[:100]}...'")
                                        else:
                                            actual_message_to_send = f"{sender_name} prepared structured output."
                                            wf_logger.info(f" [{workflow_name_upper}] Using fallback display message for {sender_name}")
                                        
                                        # Emit structured_output_ready event
                                        try:
                                            turn_uuid = uuid.uuid5(uuid.NAMESPACE_URL, f"{chat_id}:{sequence_counter}")
                                            turn_key = f"turn-{turn_uuid.hex}"
                                            context_payload = _build_auto_tool_context_payload(sequence_counter)
                                            # Add agent_name to context so auto-tool handler can inject it into context_variables
                                            context_payload["agent_name"] = sender_name
                                            
                                            # Get the correct model name from structured outputs registry
                                            model_name = structured_registry.get(sender_name)
                                            if model_name and hasattr(model_name, '__name__'):
                                                model_name = model_name.__name__
                                            else:
                                                model_name = "UnknownModel"
                                            
                                            from core.events.event_serialization import build_structured_output_ready_event
                                            structured_event = build_structured_output_ready_event(
                                                agent=sender_name,
                                                model_name=model_name,
                                                structured_data=structured_blob,
                                                auto_tool_mode=True,
                                                context=context_payload,
                                            )
                                            structured_event["turn_idempotency_key"] = turn_key
                                            
                                            # Attach pattern context reference for auto-tool write-back
                                            try:
                                                gm_candidate = getattr(pattern, "group_manager", None)
                                                if gm_candidate and hasattr(gm_candidate, "context_variables"):
                                                    structured_event["_pattern_context_ref"] = getattr(gm_candidate, "context_variables")
                                                elif hasattr(pattern, "context_variables"):
                                                    structured_event["_pattern_context_ref"] = getattr(pattern, "context_variables")
                                            except Exception:
                                                pass
                                            
                                            if dispatcher:
                                                wf_logger.info(f" [{workflow_name_upper}] Dispatching structured_output_ready for {sender_name} (turn_key={turn_key})")
                                                import asyncio
                                                asyncio.create_task(dispatcher.emit("chat.structured_output_ready", structured_event))
                                        except Exception as struct_err:
                                            wf_logger.warning(f" [{workflow_name_upper}] Failed to emit structured_output_ready for {sender_name}: {struct_err}")
                                    else:
                                        wf_logger.debug(f" [{workflow_name_upper}] No valid structured output found for {sender_name}")
                                        
                                except Exception as auto_tool_err:
                                    wf_logger.warning(f" [{workflow_name_upper}] Auto-tool processing failed for {sender_name}: {auto_tool_err}")
                            
                            try:
                                await transport.send_chat_message(
                                    message=actual_message_to_send,
                                    agent_name=sender_name,
                                    chat_id=chat_id,
                                    metadata={"source": "ag2_textevent", "sequence": sequence_counter}
                                )
                                try:
                                    setattr(ev, "_mozaiks_forwarded", True)
                                except Exception:
                                    pass
                            except TypeError as te:
                                # Known intermittent issue: some AG2 TextEvent objects (older versions / mixed reload state)
                                # bubble a "'TextEvent' object is not subscriptable" error if a downstream layer
                                # accidentally treats them like dicts. Provide a resilient fallback path.
                                if "TextEvent" in str(te) and "not subscriptable" in str(te):
                                    wf_logger.warning(
                                        f" [{workflow_name_upper}] Fallback serialization for TextEvent (subscriptable TypeError) sender={sender_name} len={len(message_content)}"
                                    )
                                    # Build a normalized 'kind' payload so dispatcher fast-path handles it
                                    fallback_payload = {
                                        "kind": "text",
                                        "agent": sender_name,
                                        "content": message_content,
                                        "_fallback": True,
                                        "sequence": sequence_counter,
                                        "source": "textevent_fallback",
                                    }
                                    try:
                                        await transport.send_event_to_ui(fallback_payload, chat_id)
                                        wf_logger.info(f" [{workflow_name_upper}] Fallback TextEvent forwarded successfully sender={sender_name}")
                                    except Exception as fallback_err:
                                        wf_logger.error(
                                            f" [{workflow_name_upper}] Fallback TextEvent forwarding failed sender={sender_name}: {fallback_err}"
                                        )
                                else:
                                    # Re-raise unexpected TypeError
                                    raise
                            wf_logger.info(
                                f" [{workflow_name_upper}] TextEvent forwarded to UI: sender='{sender_name}' message_len={len(message_content)}"
                            )
                            
                            # LIFECYCLE TRIGGER: after_agent
                            # Execute after_agent lifecycle tools when an agent completes its turn
                            try:
                                gm_ctx = getattr(pattern, "group_manager", None)
                                active_ctx = getattr(gm_ctx, "context_variables", None) if gm_ctx else None
                                if not active_ctx and hasattr(pattern, "context_variables"):
                                    active_ctx = getattr(pattern, "context_variables")
                                
                                await lifecycle_manager.execute_trigger(
                                    trigger=LifecycleTrigger.AFTER_AGENT,
                                    workflow_name=workflow_name,
                                    agent_name=sender_name,
                                    agent_output=message_content,
                                    chat_id=chat_id,
                                    enterprise_id=enterprise_id,
                                    context_variables=active_ctx,
                                    sequence_number=sequence_counter,
                                )
                            except Exception as lc_err:
                                wf_logger.debug(f" [{workflow_name_upper}] after_agent lifecycle tools failed: {lc_err}")
                            
                    except Exception as transport_err:
                        import traceback as _tb
                        logger.warning(
                            f"Failed to forward TextEvent to UI for {chat_id}: {transport_err}\n"
                            f"Type={type(transport_err).__name__} Traceback:\n{_tb.format_exc()}"
                        )
                except Exception as e:
                    logger.warning(f"Failed to persist/handle TextEvent for {chat_id}: {e}")

            # AG2 FunctionCallEvent/ToolCallEvent are handled by the executor
            # Tools emit UI artifacts via use_ui_tool() calls

            if isinstance(ev, SelectSpeakerEvent):
                # Update realtime logger context when speaker changes
                try:
                    next_agent = getattr(ev, "agent", None)
                    if next_agent:
                        next_agent_name = getattr(next_agent, "name", None) or str(next_agent)
                        from core.observability.realtime_token_logger import get_realtime_token_logger
                        realtime_logger = get_realtime_token_logger()
                        realtime_logger.set_active_agent(next_agent_name)
                        wf_logger.debug(f"[REALTIME_TOKENS] Context updated for agent: {next_agent_name}")
                except Exception as ctx_err:
                    wf_logger.debug(f"Failed to update realtime token context: {ctx_err}")

                # LIFECYCLE TRIGGER: after_agent (for previous agent)
                # Execute after_agent lifecycle tools when previous agent's turn completes
                if turn_agent and turn_started is not None:
                    duration = max(0.0, time.perf_counter() - turn_started)
                    # Record agent turn performance
                    try:
                        await perf_mgr.record_agent_turn(
                            chat_id=chat_id,
                            agent_name=turn_agent,
                            duration_sec=duration,
                            model=None,
                        )
                    except Exception as perf_err:
                        logger.warning(f"Failed to record turn for {turn_agent}: {perf_err}")
                    
                    # Execute after_agent lifecycle tools
                    try:
                        gm_ctx = getattr(pattern, "group_manager", None)
                        active_ctx = getattr(gm_ctx, "context_variables", None) if gm_ctx else None
                        if not active_ctx and hasattr(pattern, "context_variables"):
                            active_ctx = getattr(pattern, "context_variables")
                        
                        await lifecycle_manager.trigger_after_agent(
                            agent_name=str(turn_agent),
                            context_variables=active_ctx,
                        )
                    except Exception as lc_err:
                        wf_logger.debug(f" [{workflow_name_upper}] after_agent lifecycle tools failed for {turn_agent}: {lc_err}")

                turn_agent = getattr(ev, "sender", None) or getattr(ev, "agent", None)
                if turn_agent:
                    executed_agents.add(str(turn_agent))
                    
                    # LIFECYCLE TRIGGER: before_agent (for new agent)
                    # Execute before_agent lifecycle tools when an agent's turn begins
                    try:
                        gm_ctx = getattr(pattern, "group_manager", None)
                        active_ctx = getattr(gm_ctx, "context_variables", None) if gm_ctx else None
                        if not active_ctx and hasattr(pattern, "context_variables"):
                            active_ctx = getattr(pattern, "context_variables")
                        
                        await lifecycle_manager.trigger_before_agent(
                            agent_name=str(turn_agent),
                            context_variables=active_ctx,
                        )
                    except Exception as lc_err:
                        wf_logger.debug(f" [{workflow_name_upper}] before_agent lifecycle tools failed for {turn_agent}: {lc_err}")
                    
                turn_started = time.perf_counter()
                wf_logger.debug(
                    f"[{workflow_name_upper}] New turn started with agent={turn_agent} seq={sequence_counter} chat_id={chat_id}"
                )

                candidates = getattr(ev, 'agents', None)
                selected_name = None
                if turn_agent is not None:
                    selected_name = getattr(turn_agent, 'name', None) or str(turn_agent)
                context_snapshot = {}
                try:
                    ctx_ref = locals().get('ag2_context', globals().get('ag2_context'))
                    if ctx_ref:
                        if hasattr(ctx_ref, 'to_dict') and callable(getattr(ctx_ref, 'to_dict')):
                            context_snapshot = dict(ctx_ref.to_dict())  # type: ignore[arg-type]
                        elif hasattr(ctx_ref, 'data') and isinstance(getattr(ctx_ref, 'data'), dict):
                            context_snapshot = dict(getattr(ctx_ref, 'data'))
                    if not context_snapshot:
                        base_ctx = locals().get('context', globals().get('context'))
                        if base_ctx:
                            if hasattr(base_ctx, 'to_dict') and callable(getattr(base_ctx, 'to_dict')):
                                context_snapshot = dict(base_ctx.to_dict())  # type: ignore[arg-type]
                            elif hasattr(base_ctx, 'data') and isinstance(getattr(base_ctx, 'data'), dict):
                                context_snapshot = dict(getattr(base_ctx, 'data'))
                except Exception as ctx_err:  # pragma: no cover
                    wf_logger.debug(f"[HANDOFF_TRACE] context snapshot unavailable: {ctx_err}")
                interview_state = context_snapshot.get('interview_complete') if isinstance(context_snapshot, dict) else None
                wf_logger.debug(
                    f"[HANDOFF_TRACE] SelectSpeakerEvent candidates={candidates} selected={selected_name} interview_complete={interview_state}"
                )

            if isinstance(ev, InputRequestEvent):
                request_obj = getattr(ev, "content", None)
                request_uuid = getattr(ev, "uuid", None) or getattr(ev, "id", None)
                if request_uuid is None and request_obj is not None:
                    request_uuid = getattr(request_obj, "uuid", None) or getattr(request_obj, "id", None)
                if request_uuid is None:
                    request_uuid = uuid.uuid4()
                request_id = str(request_uuid)
                setattr(ev, "_mozaiks_request_id", request_id)

                respond_cb = getattr(ev, "respond", None)
                if not callable(respond_cb) and request_obj is not None:
                    respond_cb = getattr(request_obj, "respond", None)
                if callable(respond_cb):
                    pending_input_requests[request_id] = respond_cb
                    try:
                        if transport:
                            registered_id = transport.register_input_request(chat_id, request_id, respond_cb)  # type: ignore[attr-defined]
                            if registered_id and registered_id != request_id:
                                pending_input_requests.pop(request_id, None)
                                pending_input_requests[registered_id] = respond_cb
                                setattr(ev, "_mozaiks_request_id", registered_id)
                                request_id = registered_id
                    except Exception as e:
                        logger.debug(f"Failed to register input request {request_id}: {e}")
                else:
                    logger.debug(f"No respond callback available for input request {request_id}")

                prompt_hint = getattr(ev, "prompt", None)
                if prompt_hint is None and request_obj is not None:
                    prompt_hint = getattr(request_obj, "prompt", None) or getattr(request_obj, "message", None)
                if prompt_hint is not None:
                    setattr(ev, "_mozaiks_prompt", prompt_hint)
            # Debug: Check if this is a ContextAgent TextEvent and transport conditions
            transport_available = transport is not None
            already_forwarded = getattr(ev, '_mozaiks_forwarded', False)
            wf_logger.debug(f" [TRANSPORT_CHECK] Event {ev.__class__.__name__}: transport_available={transport_available}, already_forwarded={already_forwarded}")
            
            if hasattr(ev, '__class__'):
                event_class = ev.__class__.__name__
                if event_class == 'TextEvent':
                    try:
                        from core.events.event_serialization import extract_agent_name
                        agent_name = extract_agent_name(ev)
                        if agent_name == 'ContextAgent':
                            wf_logger.info(f" [DEBUG_CONTEXT_AGENT] ContextAgent TextEvent: transport={transport_available}, forwarded={already_forwarded}, will_process={transport_available and not already_forwarded}")
                    except Exception as debug_err:
                        wf_logger.debug(f" [DEBUG_CONTEXT_AGENT] Debug error: {debug_err}")
            
            if transport and not getattr(ev, '_mozaiks_forwarded', False):
                wf_logger.debug(f" [TRANSPORT_PROCESSING] Processing {ev.__class__.__name__} through transport pipeline")
                try:
                    # Unified serialization context object
                    build_ctx = UnifiedEventBuildContext(
                        workflow_name=workflow_name,
                        turn_agent=turn_agent,
                        tool_call_initiators=tool_call_initiators,
                        tool_names_by_id=tool_names_by_id,
                        workflow_name_upper=workflow_name_upper,
                        wf_logger=wf_logger,
                    )
                    wf_logger.debug(f" [TRANSPORT_PROCESSING] Built context for {ev.__class__.__name__}")
                    payload = unified_build_ui_event_payload(ev=ev, ctx=build_ctx)
                    wf_logger.debug(f" [TRANSPORT_PROCESSING] Got payload for {ev.__class__.__name__}: {payload is not None}")
                    if payload:
                        if payload.get("kind") in {"text", "print"}:
                            if payload.get("kind") == "text":
                                wf_logger.debug(
                                    " [%s] Text payload from %s: %s", workflow_name_upper, payload.get("agent"), payload.get("content")
                                )
                            agent_for_event = payload.get("agent") or payload.get("sender") or turn_agent
                            wf_logger.debug(f" [{workflow_name_upper}] Checking auto-tool: agent={agent_for_event}, auto_tool_agents={auto_tool_agents}")
                            if agent_for_event in auto_tool_agents:
                                wf_logger.debug(f" [{workflow_name_upper}] Auto-tool intercept for agent {agent_for_event}; payload keys={list(payload.keys())}")
                                structured_blob = payload.get("structured_output")
                                wf_logger.debug(f" [{workflow_name_upper}] Initial structured_blob present: {bool(structured_blob)}")
                                if not structured_blob and isinstance(payload.get("content"), str):
                                    wf_logger.debug(
                                        f" [{workflow_name_upper}] No structured_output field for {agent_for_event}; attempting fallback parse."
                                    )
                                    try:
                                        structured_blob = _PM._extract_json_from_text(payload["content"]) if hasattr(_PM, '_extract_json_from_text') else None
                                        wf_logger.debug(f" [{workflow_name_upper}] Fallback parse result present={bool(structured_blob)}")
                                    except Exception as parse_err:
                                        wf_logger.debug(f" [{workflow_name_upper}] Structured output parse fallback failed for {agent_for_event}: {parse_err}")
                                        structured_blob = None
                                    # Additional parse attempts if persistence helper fails
                                    if not structured_blob:
                                        candidate_text = payload.get("content")
                                        if isinstance(candidate_text, str):
                                            stripped_candidate = candidate_text.strip()
                                            try:
                                                structured_blob = json.loads(stripped_candidate)
                                                wf_logger.debug(
                                                    f" [{workflow_name_upper}] Direct json.loads succeeded for {agent_for_event}"
                                                )
                                            except Exception as direct_err:
                                                # Try slicing the first JSON object substring
                                                start_idx = stripped_candidate.find('{')
                                                end_idx = stripped_candidate.rfind('}')
                                                if start_idx != -1 and end_idx > start_idx:
                                                    try:
                                                        structured_blob = json.loads(stripped_candidate[start_idx:end_idx + 1])
                                                        wf_logger.debug(
                                                            f" [{workflow_name_upper}] Substring json.loads succeeded for {agent_for_event}"
                                                        )
                                                    except Exception as substring_err:
                                                        wf_logger.debug(
                                                            f" [{workflow_name_upper}] Substring parse failed for {agent_for_event}: {substring_err}"
                                                        )
                                                else:
                                                    wf_logger.debug(
                                                        f" [{workflow_name_upper}] No JSON braces found in payload content for {agent_for_event}. Direct parse error: {direct_err}"
                                                    )
                                if structured_blob:

                                    wf_logger.debug(f" [{workflow_name_upper}] structured_blob truthy for {agent_for_event}: {bool(structured_blob)}")
                                    normalized_structured = structured_blob
                                    if isinstance(structured_blob, str):
                                        try:
                                            normalized_structured = json.loads(structured_blob)
                                        except json.JSONDecodeError:
                                            wf_logger.debug(
                                                f" [{workflow_name_upper}] Structured output JSON decode failed for {agent_for_event}"
                                            )
                                            normalized_structured = None
                                    if isinstance(normalized_structured, dict):
                                        model_cls = structured_registry.get(agent_for_event)
                                        if model_cls is not None:
                                            try:
                                                validated = model_cls.model_validate(normalized_structured)
                                                normalized_structured = validated.model_dump()  # type: ignore[attr-defined]
                                            except ValidationError as err:
                                                wf_logger.warning(
                                                    f" [{workflow_name_upper}] Structured output validation failed for {agent_for_event}: {err}"
                                                )
                                                normalized_structured = None
                                    else:
                                        normalized_structured = None
                                    if normalized_structured:
                                        wf_logger.info(f" [{workflow_name_upper}] Structured output ready for {agent_for_event}; emitting auto-tool event.")
                                        agent_message = normalized_structured.get("agent_message")
                                        if isinstance(agent_message, str) and agent_message.strip():
                                            display_message = agent_message.strip()
                                        else:
                                            display_message = f"{agent_for_event} prepared structured output."
                                        payload["content"] = display_message
                                        payload["is_structured_capable"] = True
                                        payload.pop("structured_output", None)
                                        payload.pop("structured_schema", None)
                                        turn_uuid = uuid.uuid5(uuid.NAMESPACE_URL, f"{chat_id}:{sequence_counter}")
                                        turn_key = f"turn-{turn_uuid.hex}"
                                        context_payload = _build_auto_tool_context_payload(sequence_counter)
                                        # Add agent_name to context so auto-tool handler can inject it into context_variables
                                        context_payload["agent_name"] = agent_for_event
                                        model_name = getattr(agents.get(agent_for_event), "_mozaiks_structured_model_name", None)
                                        if not model_name:
                                            model_cls = structured_registry.get(agent_for_event)
                                            if model_cls is not None:
                                                model_name = getattr(model_cls, "__name__", None)
                                        if not model_name:
                                            wf_logger.warning(
                                                f" [{workflow_name_upper}] Unable to determine structured model name for {agent_for_event}; skipping auto-tool dispatch"
                                            )
                                        else:
                                            structured_event = build_structured_output_ready_event(
                                                agent=agent_for_event,
                                                model_name=model_name,
                                                structured_data=normalized_structured,
                                                auto_tool_mode=True,
                                                context=context_payload,
                                            )
                                            structured_event["turn_idempotency_key"] = turn_key
                                            if dispatcher:
                                                wf_logger.info(
                                                    f" [{workflow_name_upper}] Dispatching chat.structured_output_ready for {agent_for_event} (turn_key={turn_key})"
                                                )
                                                asyncio.create_task(dispatcher.emit("chat.structured_output_ready", structured_event))
                                    else:
                                        wf_logger.debug(
                                            f" [{workflow_name_upper}] Normalized structured payload empty for {agent_for_event}; nothing to emit."
                                        )
                                else:
                                    wf_logger.debug(
                                        f" [{workflow_name_upper}] No structured content detected for {agent_for_event}; leaving message unchanged."
                                    )
                        if payload.get("kind") == "tool_response" and payload.get("status") == SENTINEL_STATUS:
                            agent_name = payload.get("agent")
                            tool_name = payload.get("name") or payload.get("tool_name") or "unknown_tool"
                            call_id = payload.get("call_id")
                            retry_key_parts = [str(part) for part in (call_id, agent_name, tool_name) if part]
                            retry_key = "|".join(retry_key_parts) if retry_key_parts else f"agent:{agent_name}|tool:{tool_name}"
                            attempts = schema_retry_tracker.get(retry_key, 0)
                            error_info = payload.get("error") or {}
                            expected_model = error_info.get("expected_model")
                            validation_errors = error_info.get("errors")

                            if attempts >= MAX_SCHEMA_RETRIES:
                                if attempts == MAX_SCHEMA_RETRIES:
                                    wf_logger.warning(
                                        f" [{workflow_name_upper}] Schema validation failed {attempts} time(s) for agent={agent_name} tool={tool_name} call_id={call_id}. No further auto-retries."
                                    )
                                    schema_retry_tracker[retry_key] = MAX_SCHEMA_RETRIES + 1
                                    if transport:
                                        error_payload = {
                                            "kind": "error",
                                            "agent": agent_name,
                                            "code": "SCHEMA_VALIDATION_FAILED",
                                            "message": (
                                                f"Schema validation failed repeatedly for tool '{tool_name}'. "
                                                "Manual follow-up is required."
                                            ),
                                        }
                                        try:
                                            await transport.send_event_to_ui(error_payload, chat_id)
                                        except Exception as err:
                                            logger.debug(
                                                f"Failed to send schema failure error event for {chat_id}: {err}"
                                            )
                            else:
                                schema_retry_tracker[retry_key] = attempts + 1
                                gm = getattr(pattern, "group_manager", None)
                                target_agent = _resolve_agent_object(agent_name)
                                if gm and target_agent:
                                    message_lines = []
                                    if attempts > 0:
                                        message_lines.append(
                                            f"Retry attempt {attempts + 1} of {MAX_SCHEMA_RETRIES}."
                                        )
                                    if expected_model:
                                        message_lines.append(
                                            f"The previous call to `{tool_name}` failed schema validation for model `{expected_model}`."
                                        )
                                    else:
                                        message_lines.append(
                                            f"The previous call to `{tool_name}` failed schema validation."
                                        )
                                    message_lines.append(
                                        "Review the validation errors and call the tool again with arguments that satisfy the schema."
                                    )
                                    if validation_errors:
                                        try:
                                            message_lines.append(
                                                "Validation errors: "
                                                + json.dumps(validation_errors, ensure_ascii=False)
                                            )
                                        except Exception:
                                            message_lines.append(
                                                f"Validation errors: {validation_errors}"
                                            )
                                    feedback_text = "\n".join(message_lines)
                                    try:
                                        await gm.a_send(
                                            message=feedback_text,
                                            recipient=target_agent,
                                            request_reply=True,
                                            silent=True,
                                        )
                                        wf_logger.info(
                                            f" [{workflow_name_upper}] Requested schema retry for agent={agent_name} tool={tool_name} attempt={attempts + 1}"
                                        )
                                    except Exception as retry_err:
                                        wf_logger.warning(
                                            f" [{workflow_name_upper}] Failed to enqueue schema retry for agent={agent_name} tool={tool_name}: {retry_err}"
                                        )
                                else:
                                    wf_logger.debug(
                                        f" [{workflow_name_upper}] Schema retry skipped; agent or group manager missing for agent={agent_name}"
                                    )
                        if payload.get("kind") == "text" and "source" not in payload:
                            payload["source"] = "ag2_textevent"
                        if payload.get("kind") == "run_complete" and not payload.get("agent"):
                            payload["agent"] = turn_agent or "workflow"
                        await transport.send_event_to_ui(payload, chat_id)
                except Exception as e:
                    logger.debug(f"Failed to send event to UI for {chat_id}: {e}")

            if isinstance(ev, (_FC, _TC)):
                try:
                    ui_response = await handle_tool_call_for_ui_interaction(ev, chat_id)
                    if ui_response and transport:
                        try:
                            await transport.send_event_to_ui(
                                {
                                    "kind": "tool_ui_response",
                                    "tool_name": getattr(ev, "tool_name", None),
                                    "response": ui_response,
                                    "chat_id": chat_id,
                                },
                                chat_id,
                            )
                        except Exception as e:
                            logger.debug(f"Failed to send tool UI response for {chat_id}: {e}")
                except Exception as tool_err:
                    wf_logger.debug(f"Tool UI interaction error: {tool_err}")

            if isinstance(ev, UsageSummaryEvent):
                try:
                    content_obj = getattr(ev, "content", None)
                    agg_prompt = getattr(content_obj, "prompt_tokens", 0) if content_obj else 0
                    agg_completion = getattr(content_obj, "completion_tokens", 0) if content_obj else 0
                    agg_cost = getattr(content_obj, "cost", 0.0) if content_obj else 0.0
                    wf_logger.info(
                        f"[USAGE_SUMMARY] prompt={agg_prompt} completion={agg_completion} cost=${agg_cost:.4f}"
                    )
                except Exception as summary_err:
                    logger.debug(f"UsageSummaryEvent logging failed: {summary_err}")

            if isinstance(ev, RunCompletionEvent):
                try:
                    from .handoffs import handoff_manager  # noqa: F401 (for side-effects / attr access)
                    remaining_after_work = []
                    for a_name, a_obj in agents.items():
                        tgt = None
                        try:
                            h = getattr(a_obj, "handoffs", None)
                            if h and hasattr(h, "after_work"):
                                tgt = getattr(h, "after_work", None)
                        except Exception:
                            pass
                        if tgt and a_name not in executed_agents:
                            remaining_after_work.append(
                                f"{a_name}->{getattr(getattr(tgt,'target',None),'name',getattr(tgt,'target',None))}"
                            )
                    if remaining_after_work:
                        wf_logger.warning(
                            f" [{workflow_name_upper}] RunCompletionEvent early. Executed: {sorted(executed_agents)} | Pending after_work chain: {remaining_after_work}"
                        )
                except Exception as diag_err:
                    wf_logger.debug(
                        f"Early termination diagnostics failed: {diag_err}"
                    )
                wf_logger.info(
                    f" [{workflow_name_upper}] Run complete chat_id={chat_id} events={sequence_counter} executed_agents={sorted(executed_agents)}"
                )
                break

            # After processing event, compute diff if verbose enabled
            # Also trigger on_context_change lifecycle tools for ANY changed variables
            try:
                gm_live = getattr(pattern, 'group_manager', None)
                active_ctx = None
                if gm_live and hasattr(gm_live, 'context_variables'):
                    active_ctx = getattr(gm_live, 'context_variables')
                elif hasattr(pattern, 'context_variables'):
                    active_ctx = getattr(pattern, 'context_variables')
                current_snapshot = _safe_context_snapshot(active_ctx) if active_ctx else {}
                # Diff
                added = [k for k in current_snapshot.keys() if k not in prev_ctx_snapshot]
                removed = [k for k in prev_ctx_snapshot.keys() if k not in current_snapshot]
                changed = []
                for k in current_snapshot.keys():
                    if k in prev_ctx_snapshot and current_snapshot[k] != prev_ctx_snapshot[k]:
                        changed.append(k)
                
                # LIFECYCLE TRIGGER: on_context_change
                # Trigger lifecycle tools for each changed variable
                if changed and active_ctx:
                    for context_key in changed:
                        try:
                            old_value = prev_ctx_snapshot.get(context_key)
                            new_value = current_snapshot.get(context_key)
                            
                            await lifecycle_manager.execute_trigger(
                                trigger=LifecycleTrigger.ON_CONTEXT_CHANGE,
                                workflow_name=workflow_name,
                                chat_id=chat_id,
                                enterprise_id=enterprise_id,
                                context_key=context_key,
                                old_value=old_value,
                                new_value=new_value,
                                context_variables=active_ctx,
                            )
                        except Exception as lc_err:
                            wf_logger.debug(
                                f" [{workflow_name_upper}] on_context_change lifecycle tool failed for {context_key}: {lc_err}"
                            )
                
                if verbose_ctx and (added or removed or changed):
                    wf_logger.info(
                        f" [CONTEXT_DIFF] seq={sequence_counter} added={added} removed={removed} changed={changed}"
                    )
                    # Only dump detailed values at DEBUG to avoid log noise
                    wf_logger.debug(
                        f" [CONTEXT_DIFF_DEBUG] seq={sequence_counter} snapshot={current_snapshot}"
                    )
                prev_ctx_snapshot = current_snapshot
            except Exception as _diff_err:
                wf_logger.debug(f" [CONTEXT_VERBOSE] diff computation failed: {_diff_err}")
    except Exception as loop_err:
        wf_logger.error(f"Event loop failure: {loop_err}")
    finally:
        # LIFECYCLE TRIGGER: after_chat
        # Execute after_chat lifecycle tools after event loop completes (success or error)
        try:
            gm_ctx = getattr(pattern, "group_manager", None)
            active_ctx = getattr(gm_ctx, "context_variables", None) if gm_ctx else None
            if not active_ctx and hasattr(pattern, "context_variables"):
                active_ctx = getattr(pattern, "context_variables")
            
            final_status = "error" if "loop_err" in locals() else "success"
            
            await lifecycle_manager.execute_trigger(
                trigger=LifecycleTrigger.AFTER_CHAT,
                workflow_name=workflow_name,
                chat_id=chat_id,
                enterprise_id=enterprise_id,
                user_id=user_id,
                context_variables=active_ctx,
                final_status=final_status,
            )
        except Exception as lc_err:
            wf_logger.warning(f" [{workflow_name_upper}] after_chat lifecycle tools failed: {lc_err}")
        
        # AG2-native: No manual context cleanup needed - AG2 handles lifecycle automatically
        pass

    return {
        "response": response,
        "turn_agent": turn_agent,
        "turn_started": turn_started,
        "sequence_counter": sequence_counter,
            }


async def run_workflow_orchestration(
    workflow_name: str,
    enterprise_id: str,
    chat_id: str,
    user_id: Optional[str] = None,
    initial_message: Optional[str] = None,
    agents_factory: Optional[Callable] = None,
    context_factory: Optional[Callable] = None,
    handoffs_factory: Optional[Callable] = None,
    **kwargs
) -> Any:
    start_time = perf_counter()
    workflow_name_upper = workflow_name.upper()
    orchestration_pattern = "unknown"
    agents: Dict[str, Any] = {}

    # Create workflow logger for this session  
    wf_lifecycle_logger = get_workflow_logger(workflow_name, chat_id=chat_id)
    
    wf_logger = get_workflow_logger(workflow_name, chat_id=chat_id, enterprise_id=enterprise_id)
    
    # Log orchestration start with session summary instead of verbose details
    logger.info(f" [ORCHESTRATION] Starting {workflow_name} workflow")
    


    # Persistence / transport / termination handler 
    persistence_manager = AG2PersistenceManager()

    from core.transport.simple_transport import SimpleTransport
    transport = await SimpleTransport.get_instance()
    if not transport:
        raise RuntimeError(f"SimpleTransport instance not available for {workflow_name} workflow")

    termination_handler = create_termination_handler(
        chat_id=chat_id,
        enterprise_id=enterprise_id,
        workflow_name=workflow_name,
        transport=transport
    )

    result_payload: Optional[Dict[str, Any]] = None
    # Pre-initialize to ensure safe access in final logs even if an early exception occurs
    stream_state: Dict[str, Any] = {}

    # -----------------------------------------------------------------
    # Reconnect handshake (optional) - if client supplies last_seen_sequence
    # kwargs key: last_seen_sequence (int). If provided we replay diff of
    # normalized events (sequence > last_seen_sequence) to the UI transport
    # BEFORE starting the AG2 pattern run. This is a best-effort replay; any
    # failures are logged and ignored (live stream then proceeds).
    # -----------------------------------------------------------------

    # Generate trace_id for this workflow session
    import uuid
    trace_id_hex = uuid.uuid4().hex
    logger.debug(f"Generated trace_id for workflow {workflow_name}: {trace_id_hex}")

    perf_mgr = await get_performance_manager()
    await perf_mgr.initialize()
    await perf_mgr.record_workflow_start(chat_id, enterprise_id, workflow_name, user_id or "unknown")
    await perf_mgr.attach_trace_id(chat_id, trace_id_hex)

    # Start AG2 runtime logging for this workflow session and keep it active
    # across the orchestration run so AG2 events (like LLM/tool calls) are captured.
    with ag2_logging_session(chat_id, workflow_name, enterprise_id):
        # Set up realtime token logger for immediate token tracking
        try:
            from core.observability.realtime_token_logger import get_realtime_token_logger
            realtime_logger = get_realtime_token_logger()
            realtime_logger.set_user(user_id or "unknown")
            realtime_logger.set_active_agent(workflow_name)
            wf_logger.info(f" [REALTIME_TOKENS] Realtime token logging prepared for chat {chat_id}")
        except Exception as rt_err:
            wf_logger.warning(f" [REALTIME_TOKENS] Failed to prepare realtime token logging: {rt_err}")

        try:
            # -----------------------------------------------------------------
            # 1) Load configuration
            # -----------------------------------------------------------------
            cfg = _load_workflow_config(workflow_name)
            config = cfg["config"]
            max_turns = cfg["max_turns"]
            orchestration_pattern = cfg["orchestration_pattern"]
            startup_mode = cfg["startup_mode"]
            human_in_loop = cfg["human_in_loop"]
            initial_agent_name = cfg["initial_agent_name"]

            # Brief, structured visibility into effective normalized config
            try:
                wf_logger.info(
                    f" [{workflow_name_upper}] CONFIG: startup_mode={startup_mode} human_in_loop={human_in_loop} pattern={orchestration_pattern} initial_agent={initial_agent_name}"
                )
            except Exception as _cfg_log_err:  # pragma: no cover
                logger.debug(f"config log failed: {_cfg_log_err}")

            # -----------------------------------------------------------------
            # 2) Resume or start chat
            # -----------------------------------------------------------------
            resumed_messages, initial_messages = await _resume_or_initialize_chat(
                persistence_manager=persistence_manager,
                termination_handler=termination_handler,
                config=config,
                chat_id=chat_id,
                enterprise_id=enterprise_id,
                workflow_name=workflow_name,
                user_id=user_id,
                initial_message=initial_message,
                wf_logger=wf_logger,
            )

            # Track resume mode early so downstream logging can reference it safely
            resumed_mode = bool(resumed_messages)

            # -----------------------------------------------------------------
            # 3) LLM config (per-chat cache seed)
            # -----------------------------------------------------------------
            try:
                cache_seed = await persistence_manager.get_or_assign_cache_seed(chat_id, enterprise_id)
            except Exception as seed_err:
                cache_seed = None
                wf_logger.debug(f" [{workflow_name_upper}] cache_seed assignment failed for chat {chat_id}: {seed_err}")
            llm_config = await _load_llm_config(workflow_name, wf_logger, workflow_name_upper, cache_seed=cache_seed)

            # -----------------------------------------------------------------
            # 3.5) Structured outputs preload (blocking)
            # -----------------------------------------------------------------
            try:
                from .structured_outputs import load_workflow_structured_outputs as _preload_so
                _preload_so(workflow_name)
                wf_logger.info(f" [{workflow_name_upper}] Structured outputs preloaded")
            except Exception as so_err:
                # Do not fail the run, but surface misconfiguration early
                wf_logger.warning(f" [{workflow_name_upper}] Structured outputs preload failed: {so_err}")

            # Log start
            chat_logger.info(f"[{workflow_name_upper}] WORKFLOW_STARTED chat_id={chat_id} pattern={orchestration_pattern}")
            wf_logger.info(
                "WORKFLOW_STARTED",
                event_type=f"{workflow_name_upper}_WORKFLOW_STARTED",
                description=f"{workflow_name} workflow orchestration initialized",
                enterprise_id=enterprise_id,
                chat_id=chat_id,
                user_id=user_id,
                pattern=orchestration_pattern,
                startup_mode=startup_mode,
                initial_message_count=len(initial_messages),
                trace_id=trace_id_hex,
            )

            # -----------------------------------------------------------------
            # 4) Context build
            # -----------------------------------------------------------------
            context = None
            context_start = perf_counter()
            context = await _build_context_blocking(
                context_factory=context_factory,
                workflow_name=workflow_name,
                enterprise_id=enterprise_id,
                chat_id=chat_id,
                user_id=user_id,
                wf_logger=wf_logger,
                workflow_name_upper=workflow_name_upper,
            )
            context_time = (perf_counter() - context_start) * 1000
            performance_logger.info(
                "context_load_duration_ms",
                extra={
                    "metric_name": "context_load_duration_ms",
                    "value": float(context_time),
                    "unit": "ms",
                    "workflow_name": workflow_name,
                    "enterprise_id": enterprise_id,
                },
            )

            # -----------------------------------------------------------------
            # 6) Agents creation following AG2 patterns
            # -----------------------------------------------------------------
            agents = await _create_agents(agents_factory, workflow_name, context_variables=context, cache_seed=cache_seed)
            agents = agents or {}
            if not agents:
                raise RuntimeError(f"No agents defined for workflow '{workflow_name}'")

            derived_context_manager = DerivedContextManager(workflow_name, agents, context)
            if derived_context_manager.has_variables():
                derived_context_manager.seed_defaults()

                def _derived_listener(payload: Dict[str, Any]):  # type: ignore
                    try:
                        var_name = payload.get('variable')
                        value = payload.get('value')
                        if not var_name:
                            return
                        if transport:
                            evt = {
                                'kind': 'context_update',
                                'variable': var_name,
                                'value': value,
                            }
                            asyncio.create_task(transport.send_event_to_ui(evt, chat_id))
                    except Exception as _dl_err:  # pragma: no cover
                        wf_logger.debug(f"Derived listener emit failed: {_dl_err}")

                try:
                    derived_context_manager.add_listener(_derived_listener)
                except Exception as _lerr:  # pragma: no cover
                    wf_logger.debug(f"Failed registering derived listener: {_lerr}")
            else:
                derived_context_manager = None

            # Get tool binding data for summary
            from .agent_tools import load_agent_tool_functions
            agent_tools = load_agent_tool_functions(workflow_name)

            try:
                # Produce a concise debug summary of loaded tools per agent
                _tool_summary = {a: [getattr(f, '__name__', '<noname>') for f in funcs] for a, funcs in agent_tools.items()}
                workflow_logger.debug(f"[ORCH][TRACE] Loaded agent tool mapping for {workflow_name}: {_tool_summary}")
            except Exception as _e:  # pragma: no cover
                workflow_logger.debug(f"[ORCH][TRACE] Failed building tool summary: {_e}")
            # Basic sanity: at least one tool across all agents if workflow expects tools
            total_tool_count = sum(len(funcs) for funcs in agent_tools.values())
            wf_logger.info(f" [{workflow_name_upper}] Tools bound across agents: {total_tool_count}")

            # Log consolidated agent setup summary using existing logger
            try:
                wf_logger.info(
                    f" [WORKFLOW_SETUP] {workflow_name}: agents={list(agents.keys())} tools={len(agent_tools)}"
                )
            except Exception as log_err:
                logger.debug(f"Agent setup summary logging failed: {log_err}")

            # -----------------------------------------------------------------
            # 6.5) Hooks readiness snapshot (blocking check via current agents)
            # -----------------------------------------------------------------
            try:
                from .agents import list_hooks_for_workflow as _list_hooks
                hooks_snapshot = _list_hooks(agents)
                total_hooks = sum(len(funcs) for agent_hooks in hooks_snapshot.values() for funcs in agent_hooks.values())
                wf_logger.info(f" [{workflow_name_upper}] Hooks registered across agents: {total_hooks}")
                workflow_logger.debug(f"[ORCH][TRACE] Hooks snapshot: {hooks_snapshot}")
            except Exception as hook_snap_err:  # pragma: no cover
                wf_logger.debug(f"Hooks snapshot failed: {hook_snap_err}")

            # Defer start log until after agents + initiating agent known
            try:
                context_var_count = (len(context) if context is not None and hasattr(context, '__len__') else 0)
            except Exception:
                context_var_count = 0

            wf_logger.debug(
                f" [{workflow_name_upper}] Chat START chat_id={chat_id} agents={len(agents)} max_turns={max_turns} "
                f"startup_mode={startup_mode} human_in_loop={human_in_loop} context_vars={context_var_count} resumed={resumed_mode}"
            )

            # -----------------------------------------------------------------
            # Store agents on transport
            try:
                if transport and hasattr(transport, 'connections') and chat_id in transport.connections:
                    transport.connections[chat_id]['agents'] = agents
                    # Expose context for component actions & UI updates
                    if context is not None:
                        transport.connections[chat_id]['context'] = context
            except Exception as _agents_store_err:
                wf_logger.debug(f"agent store failed: {_agents_store_err}")

            # Ensure user proxy presence (always named "user")
            agents, user_proxy_agent, human_in_loop = _ensure_user_proxy(
                agents=agents,
                config=config,
                startup_mode=startup_mode,
                llm_config=llm_config,
                human_in_loop=human_in_loop,
            )

            # -----------------------------------------------------------------
            # 7) Initiating agent (explicit or first available)
            # -----------------------------------------------------------------
            initiating_agent = _resolve_initiating_agent(
                agents=agents,
                initial_agent_name=initial_agent_name,
                workflow_name=workflow_name,
            )

            wf_logger.info(
                f" [{workflow_name_upper}] Initial agent resolved: {getattr(initiating_agent,'name',None)}"
            )

            # -----------------------------------------------------------------
            # 8) STRICT resume prep: normalize + enforce HIL (no tail stripping)
            # -----------------------------------------------------------------
            initial_messages = _normalize_to_strict_ag2(initial_messages, default_user_name="user")

            # Enforce human-in-the-loop if any user turns are present in history
            if any(m.get("role") == "user" for m in initial_messages):
                human_in_loop = True

            # -----------------------------------------------------------------
            # 9) Pattern creation (AG2 native)
            # -----------------------------------------------------------------
            pattern, ag2_context = await _create_ag2_pattern(
                orchestration_pattern=orchestration_pattern,
                workflow_name=workflow_name,
                agents=agents,
                initiating_agent=initiating_agent,
                user_proxy_agent=user_proxy_agent,
                human_in_loop=human_in_loop,
                context_variables=context,
                llm_config=llm_config,
                handoffs_factory=handoffs_factory,
                wf_logger=wf_logger,
                chat_id=chat_id,
                enterprise_id=enterprise_id,
                user_id=user_id,
            )

            try:
                wf_logger.info(" [CONTEXT_BRIDGE] Pattern created; preparing to register providers")
                gm = getattr(pattern, 'group_manager', None)
                if gm and hasattr(gm, 'context_variables'):
                    wf_logger.debug(
                        f" [CONTEXT_BRIDGE_DEBUG] group_manager.context id={id(gm.context_variables)} keys={list(getattr(gm.context_variables,'data',{}).keys())}"
                    )
            except Exception as _bridge_err:
                wf_logger.debug(f" [CONTEXT_BRIDGE] logging failed: {_bridge_err}")

            if derived_context_manager:
                # Register the AG2 pattern's context variables as the primary provider
                # This ensures derived variables update the actual context used by AG2
                if hasattr(pattern, "group_manager"):
                    group_manager = getattr(pattern, "group_manager", None)
                    if group_manager and hasattr(group_manager, "context_variables"):
                        pattern_context_vars = getattr(group_manager, "context_variables")
                        derived_context_manager.register_additional_provider(pattern_context_vars)
                        try:
                            wf_logger.info(
                                f" [DERIVED_CONTEXT] Registered group_manager context_variables provider | id={id(pattern_context_vars)} keys={list(getattr(pattern_context_vars,'data',{}).keys())}"
                            )
                        except Exception:
                            wf_logger.info(" [DERIVED_CONTEXT] Registered group_manager context_variables as provider (keys unavailable)")

                # Also register pattern-level context variables if available
                pattern_context = getattr(pattern, "context_variables", None)
                if pattern_context:
                    derived_context_manager.register_additional_provider(pattern_context)
                    try:
                        wf_logger.info(
                            f" [DERIVED_CONTEXT] Registered pattern.context_variables provider | id={id(pattern_context)} keys={list(getattr(pattern_context,'data',{}).keys())}"
                        )
                    except Exception:
                        wf_logger.info(" [DERIVED_CONTEXT] Registered pattern context_variables as provider")

                # Register the ag2_context we created as the primary provider
                # This ensures derived variables can update the same context AG2 uses
                if ag2_context:
                    derived_context_manager.register_additional_provider(ag2_context)
                    try:
                        wf_logger.info(
                            f" [DERIVED_CONTEXT] Registered ag2_context provider | id={id(ag2_context)} keys={list(getattr(ag2_context,'data',{}).keys())}"
                        )
                    except Exception:
                        wf_logger.info(" [DERIVED_CONTEXT] Registered ag2_context as primary provider")

                # Seed defaults into all newly registered providers
                derived_context_manager.seed_defaults()

                # Log final provider count for debugging
                provider_count = len(derived_context_manager.providers) if hasattr(derived_context_manager, 'providers') else 0
                try:
                    # Enumerate providers briefly
                    details = []
                    for idx, prov in enumerate(getattr(derived_context_manager, 'providers', [])):
                        keys = []
                        if hasattr(prov, 'data') and isinstance(getattr(prov,'data'), dict):
                            keys = list(getattr(prov,'data').keys())
                        elif hasattr(prov, 'to_dict'):
                            try:
                                keys = list(prov.to_dict().keys())  # type: ignore
                            except Exception:
                                keys = []
                        details.append({"idx": idx, "id": id(prov), "key_count": len(keys)})
                    wf_logger.info(f" [DERIVED_CONTEXT] Final provider count: {provider_count} | providers={details}")
                except Exception:
                    wf_logger.info(f" [DERIVED_CONTEXT] Final provider count: {provider_count}")
            # Hooks are  registered once inside define_agents() via workflow_manager.register_hooks.
            # This avoids duplicate log noise and ensures _hooks_loaded_workflows gating is respected.
            
            # -----------------------------------------------------------------
            # 10.5) Lifecycle Tools: before_chat trigger
            # -----------------------------------------------------------------
            try:
                from core.workflow.lifecycle_tools import get_lifecycle_manager
                lifecycle_manager = get_lifecycle_manager(workflow_name)
                await lifecycle_manager.trigger_before_chat(context_variables=ag2_context)
                wf_logger.info(f" [{workflow_name_upper}] Lifecycle before_chat triggers completed")
            except Exception as lc_err:
                wf_logger.debug(f" [{workflow_name_upper}] Lifecycle before_chat failed: {lc_err}")
            
            # -----------------------------------------------------------------
            # 11) Execute AG2 group chat with proper event streaming
            # -----------------------------------------------------------------
            wf_lifecycle_logger.info(
                f" [{workflow_name_upper}] Starting AG2 workflow execution",
                agent_count=len(agents),
                tool_count=sum(len(getattr(agent, 'tool_names', [])) for agent in agents.values()),
                pattern_name=orchestration_pattern,
                message_count=len(initial_messages),
                max_turns=max_turns,
                is_resume=bool(resumed_messages)
            )
                
            stream_state = await _stream_events(
                pattern=pattern,
                resumed_messages=resumed_messages,
                initial_messages=initial_messages,
                max_turns=max_turns,
                agents=agents,
                chat_id=chat_id,
                enterprise_id=enterprise_id,
                workflow_name=workflow_name,
                wf_logger=wf_logger,
                workflow_name_upper=workflow_name_upper,
                transport=transport,
                termination_handler=termination_handler,
                user_id=user_id,
                persistence_manager=persistence_manager,
                perf_mgr=perf_mgr,
                derived_context_manager=derived_context_manager,
            )
            response = stream_state["response"]
            turn_agent = stream_state["turn_agent"]
            turn_started = stream_state["turn_started"]

            if turn_agent and turn_started is not None:
                duration = max(0.0, time.perf_counter() - turn_started)
                # Record final agent turn performance
                try:
                    await perf_mgr.record_agent_turn(
                        chat_id=chat_id,
                        agent_name=turn_agent,
                        duration_sec=duration,
                        model=None,
                    )
                except Exception as e:
                    logger.warning(f"Failed to record final turn for {turn_agent}: {e}")

            # Final usage reconciliation using AG2's native gather_usage_summary
            try:
                from autogen import gather_usage_summary

                # Get authoritative usage data from AG2
                agent_list = list(agents.values())
                if agent_list:
                    final_summary = gather_usage_summary(agent_list)

                    # Extract AG2 final totals
                    def _safe_float_local(value: Any) -> float:
                        """Convert mixed autogen values to float safely."""
                        try:
                            if isinstance(value, dict):
                                if "total_cost" in value:
                                    return float(value.get("total_cost", 0.0))
                                values = list(value.values())
                                if values:
                                    return float(values[0])
                                return 0.0
                            return float(value)
                        except (TypeError, ValueError):
                            return 0.0

                    ag2_total_cost = _safe_float_local(final_summary.get("total_cost", 0.0))
                    ag2_usage_including_cached = final_summary.get("usage_including_cached", {})
                    ag2_usage_excluding_cached = final_summary.get("usage_excluding_cached", {})

                    # Log comprehensive AG2 final summary
                    wf_logger.info(
                        "[AG2_FINAL_SUMMARY] Authoritative usage data | "
                        f"total_cost=${ag2_total_cost:.4f} | "
                        f"with_cache={ag2_usage_including_cached} | "
                        f"without_cache={ag2_usage_excluding_cached}"
                    )

                    # Compare AG2 totals vs PerformanceManager snapshot for reconciliation
                    snapshot = await perf_mgr.snapshot_chat(chat_id)
                    tracked_prompt = int(snapshot.get("prompt_tokens", 0)) if snapshot else 0
                    tracked_completion = int(snapshot.get("completion_tokens", 0)) if snapshot else 0
                    tracked_cost = float(snapshot.get("cost", 0.0)) if snapshot else 0.0

                    final_cost_delta = max(0.0, ag2_total_cost - tracked_cost)
                    final_prompt_delta = max(0, int(ag2_usage_excluding_cached.get("prompt_tokens", 0) or 0) - tracked_prompt)
                    final_completion_delta = max(0, int(ag2_usage_excluding_cached.get("completion_tokens", 0) or 0) - tracked_completion)

                    if final_cost_delta > 0.01 or final_prompt_delta or final_completion_delta:
                        wf_logger.warning(
                            "[FINAL_RECONCILIATION] Delta detected | "
                            f"ag2_total=${ag2_total_cost:.4f} tracked_total=${tracked_cost:.4f} | "
                            f"delta=${final_cost_delta:.4f} prompt_delta={final_prompt_delta} completion_delta={final_completion_delta}"
                        )
                        await persistence_manager.update_session_metrics(
                            chat_id=chat_id,
                            enterprise_id=enterprise_id,
                            user_id=user_id or "unknown",
                            workflow_name=workflow_name,
                            prompt_tokens=final_prompt_delta,
                            completion_tokens=final_completion_delta,
                            cost_usd=final_cost_delta,
                            agent_name="ag2_final_reconciliation",
                            event_ts=datetime.now(UTC)
                        )
                    else:
                        wf_logger.info(
                            "o. [FINAL_RECONCILIATION] Usage tracking accurate | "
                            f"ag2=${ag2_total_cost:.4f} tracked=${tracked_cost:.4f} | "
                            f"delta=${final_cost_delta:.4f}"
                        )

                    # Log per-agent usage summaries for visibility
                    for agent_name, agent in agents.items():
                        try:
                            if hasattr(agent, 'print_usage_summary'):
                                wf_logger.debug(f" [AGENT_USAGE] {agent_name} summary logged to stdout")
                                # Note: print_usage_summary() outputs to stdout, captured by AG2 runtime logging
                        except Exception as agent_summary_err:
                            wf_logger.debug(f"Failed to log usage summary for {agent_name}: {agent_summary_err}")

            except ImportError:
                wf_logger.warning(" [FINAL_RECONCILIATION] autogen.gather_usage_summary not available")
            except Exception as reconcile_err:
                wf_logger.error(f" [FINAL_RECONCILIATION] Failed: {reconcile_err}")

            max_turns_reached = getattr(response, 'max_turns_reached', False)

            # Ensure termination handler is called to update status
            try:
                termination_result = await termination_handler.on_conversation_end(
                    max_turns_reached=max_turns_reached
                )
                try:
                    status_val = getattr(termination_result, 'status', 'completed')
                    logger.info(f" Termination completed: {status_val}")
                except Exception:
                    logger.info(" Termination completed (offline mode)")
            except Exception as term_err:
                logger.error(f" Termination handler failed: {term_err}")

            # Safely extract messages for logging
            try:
                messages_obj = getattr(response, 'messages', None)
                if asyncio.iscoroutine(messages_obj):
                    messages_obj = await messages_obj
                if messages_obj is not None:
                    await log_conversation_to_agent_chat_file(messages_obj, chat_id, enterprise_id, workflow_name)
            except Exception as log_err:
                logger.error(f" Failed to log conversation to agent chat file for {chat_id}: {log_err}")

            # Log execution completion
            duration_sec = perf_counter() - start_time
            wf_logger.info(f" [EXECUTION_COMPLETE] Duration: {duration_sec:.2f}s")

            # -----------------------------------------------------------------
            # 12) Lifecycle Tools: after_chat trigger
            # -----------------------------------------------------------------
            try:
                from core.workflow.lifecycle_tools import get_lifecycle_manager
                lifecycle_manager = get_lifecycle_manager(workflow_name)
                await lifecycle_manager.trigger_after_chat(context_variables=ag2_context)
                wf_logger.info(f" [{workflow_name_upper}] Lifecycle after_chat triggers completed")
            except Exception as lc_err:
                wf_logger.debug(f" [{workflow_name_upper}] Lifecycle after_chat failed: {lc_err}")

            result_payload = {
                "workflow_name": workflow_name,
                "chat_id": chat_id,
                "enterprise_id": enterprise_id,
                "user_id": user_id,
                "messages": getattr(response, 'messages', None),
                "max_turns_reached": max_turns_reached,
                "response": response
            }
                
        except Exception as e:
            logger.error(f" [{workflow_name_upper}] Orchestration failed: {e}", exc_info=True)
            try:
                await termination_handler.on_conversation_end()
                logger.info(" Termination handler called for error case")
            except Exception as term_err:
                logger.error(f" Termination handler error cleanup failed: {term_err}")
            raise
        finally:
            from core.data.models import WorkflowStatus
            status = WorkflowStatus.COMPLETED
            try:
                await perf_mgr.record_workflow_end(chat_id, int(status))
                await perf_mgr.flush(chat_id)
            except Exception as e:
                logger.debug(f"perf finalize failed: {e}")
            duration_sec = perf_counter() - start_time
        # AG2 runtime logging cleanup is now handled automatically by the context manager

    # Final logging & cleanup
    try:
        duration = perf_counter() - start_time
        
        # Log workflow completion with summary
        wf_lifecycle_logger.info(
            f" [{workflow_name_upper}] Workflow completed",
            duration_sec=duration,
            event_count=(stream_state.get('sequence_counter', 0) if isinstance(stream_state, dict) else 0),
            agent_count=len(agents),
            pattern_used=orchestration_pattern,
            chat_id=chat_id,
            enterprise_id=enterprise_id,
            result_status="success" if result_payload else "empty"
        )
        
        # Single consolidated completion log instead of multiple lines
        chat_logger.info(f"[{workflow_name_upper}] WORKFLOW_COMPLETED chat_id={chat_id} duration={duration:.2f}s agents={len(agents)}")
        
    finally:
        # Keeping block to preserve structure for future extension (e.g., tracing export hooks).
        pass

    return result_payload


# ==============================================================================
# AG2 PATTERN FACTORY - Direct AG2 Pattern Usage
# ==============================================================================

def create_ag2_pattern(
    pattern_name: str,
    initial_agent: ConversableAgent,
    agents: List[ConversableAgent],
    user_agent: Optional[UserProxyAgent] = None,
    context_variables: Optional[Any] = None,
    group_manager_args: Optional[Dict[str, Any]] = None,
    **pattern_kwargs
) -> Any:
    """
    Create AG2 Pattern following proper constructor signature.
    
    AG2 Pattern constructor signature:
    - initial_agent: ConversableAgent
    - agents: List[ConversableAgent] 
    - user_agent: Optional[ConversableAgent]
    - context_variables: Optional[ContextVariables]
    - group_manager_args: Optional[Dict[str, Any]]
    """
    pattern_map = {
        "AutoPattern": AG2AutoPattern,
        "DefaultPattern": AG2DefaultPattern,
        "RoundRobinPattern": AG2RoundRobinPattern,
        "RandomPattern": AG2RandomPattern
    }

    if pattern_name not in pattern_map:
        # Fail fast so misconfiguration is visible instead of silently defaulting
        raise ValueError(f"Unknown orchestration pattern: {pattern_name}")

    pattern_class = pattern_map[pattern_name]

    logger.info(f" Creating {pattern_name} using AG2's native implementation")
    logger.info(f" Pattern setup - initial_agent: {initial_agent.name}")
    logger.info(f" Pattern setup - agents count: {len(agents)}")
    logger.info(f" Pattern setup - user_agent included: {user_agent is not None}")
    if context_variables is not None:
        try:
            # Best-effort context diagnostics
            cv_type = type(context_variables).__name__
            cv_keys = []
            if hasattr(context_variables, 'to_dict'):
                cv_keys = list(context_variables.to_dict().keys())
            elif hasattr(context_variables, 'data') and isinstance(getattr(context_variables, 'data', None), dict):
                cv_keys = list(context_variables.data.keys())
            elif isinstance(context_variables, dict):
                cv_keys = list(context_variables.keys())
            logger.info(f" Pattern setup - context_variables: True | type={cv_type} | keys={cv_keys}")
        except Exception as _log_err:
            logger.info(f" Pattern setup - context_variables: True (keys unavailable: {_log_err})")
    else:
        logger.info(" Pattern setup - context_variables: False")

    # Build AG2 Pattern constructor arguments following proper signature
    pattern_args = {
        "initial_agent": initial_agent,
        "agents": agents,
        "context_variables": context_variables,  # AG2 ContextVariables instance
    }

    # Add user_agent if provided (AG2 handles human-in-the-loop logic)
    if user_agent is not None:
        pattern_args["user_agent"] = user_agent
        logger.info(" User agent included in AG2 pattern")

    # Add group_manager_args for GroupChatManager configuration
    if group_manager_args is not None:
        pattern_args["group_manager_args"] = group_manager_args

    # Add any additional pattern-specific kwargs
    pattern_args.update(pattern_kwargs)

    try:
        pattern = pattern_class(**pattern_args)
        logger.info(f" {pattern_name} AG2 pattern created successfully")
        # Verify context presence on the created pattern/manager
        try:
            gm = getattr(pattern, 'group_manager', None)
            cv = getattr(gm, 'context_variables', None) if gm else None
            if cv is not None:
                try:
                    keys = list(cv.data.keys()) if hasattr(cv, 'data') else list(cv.to_dict().keys()) if hasattr(cv, 'to_dict') else []
                except Exception:
                    keys = []
                logger.info(f" Pattern created with ContextVariables attached to group_manager | keys={keys}")
            else:
                logger.debug("Pattern created; group_manager.context_variables not exposed at pattern level (will be set up in prepare_group_chat)")
        except Exception as _post_err:
            logger.debug(f"ContextVariables post-create check skipped: {_post_err}")
        return pattern
    except Exception as e:
        logger.warning(f" Failed to create {pattern_name} with all args, trying minimal: {e}")
        minimal_args = {
            "initial_agent": initial_agent,
            "agents": agents,
        }
        if user_agent is not None:
            minimal_args["user_agent"] = user_agent

        # Include context_variables in minimal args if available
        if context_variables is not None:
            minimal_args["context_variables"] = context_variables
            
        minimal_pattern = pattern_class(**minimal_args)
        logger.info(f" {pattern_name} AG2 pattern created with minimal args")
        
        return minimal_pattern

# ==============================================================================
# LOGGING HELPERS
# ==============================================================================

def log_agent_message_details(message, sender_name, recipient_name):
    """Logs agent message details for tracking."""
    message_content = getattr(message, 'content', None) or str(message)

    if message_content and sender_name != 'unknown':
        summary = message_content[:150] + '...' if len(message_content) > 150 else message_content
        chat_logger.info(f" [AGENT] {sender_name}  {recipient_name}: {summary}")
        chat_logger.debug(f" [FULL] {sender_name} complete message:\n{'-'*50}\n{message_content}\n{'-'*50}")
        chat_logger.debug(f" [META] Length: {len(message_content)} chars | Type: {type(message).__name__}")
    return message


async def log_conversation_to_agent_chat_file(conversation_history, chat_id: str, enterprise_id: str, workflow_name: str):
    """
    Log the complete AG2 conversation to the agent chat log file.
    """
    try:
        agent_chat_logger = get_workflow_logger("agent_messages")

        if not conversation_history:
            agent_chat_logger.info(f" [{workflow_name}] No conversation history to log for chat {chat_id}")
            return

        msg_count = len(conversation_history) if hasattr(conversation_history, '__len__') else 0
        agent_chat_logger.info(f" [{workflow_name}] Logging {msg_count} messages to agent chat file for chat {chat_id}")

        for i, message in enumerate(conversation_history):
            try:
                sender_name = "Unknown"
                content = ""

                if isinstance(message, dict):
                    if 'name' in message and message['name']:
                        sender_name = message['name']
                    elif 'sender' in message and message['sender']:
                        sender_name = message['sender']
                    elif 'from' in message and message['from']:
                        sender_name = message['from']

                    if 'content' in message and message['content'] is not None:
                        content = message['content']
                    elif 'message' in message and message['message'] is not None:
                        content = message['message']
                    elif 'text' in message and message['text'] is not None:
                        content = message['text']
                elif isinstance(message, str):
                    content = message
                elif hasattr(message, 'name') and hasattr(message, 'content'):
                    sender_name = getattr(message, 'name', 'Unknown')
                    content = getattr(message, 'content', '')
                elif hasattr(message, 'sender') and hasattr(message, 'message'):
                    sender_name = getattr(message, 'sender', 'Unknown')
                    content = getattr(message, 'message', '')
                else:
                    content = str(message)

                clean_content = content if isinstance(content, str) else str(content)
                clean_content = clean_content.strip() if clean_content else ""

                if clean_content:
                    agent_chat_logger.info(
                        f"AGENT_MESSAGE | Chat: {chat_id} | Enterprise: {enterprise_id} | Agent: {sender_name} | Message #{i+1}: {clean_content}"
                    )
                    # Skip user proxy messages to prevent echo back to UI
                    message_role = message.get('role') if isinstance(message, dict) else None
                    if not (sender_name.lower() in ("user", "userproxy", "userproxyagent") or message_role == 'user'):
                        try:
                            from core.transport.simple_transport import SimpleTransport
                            transport = await SimpleTransport.get_instance()
                            if transport:
                                await transport.send_chat_message(
                                    message=clean_content,
                                    agent_name=sender_name,
                                    chat_id=chat_id,
                                    metadata={"source": "ag2_conversation", "message_index": i+1}
                                )
                        except Exception as ui_error:
                            logger.debug(f"UI forwarding failed for message {i+1}: {ui_error}")
                else:
                    agent_chat_logger.debug(f"EMPTY_MESSAGE | Chat: {chat_id} | Agent: {sender_name} | Message #{i+1}: (empty)")

            except Exception as msg_error:
                agent_chat_logger.error(f" Failed to log message {i+1} in chat {chat_id}: {msg_error}")

        agent_chat_logger.info(f" [{workflow_name}] Successfully logged {msg_count} messages for chat {chat_id}")

    except Exception as e:
        logger.error(f" Failed to log conversation to agent chat file for {chat_id}: {e}")
        # Do not raise



