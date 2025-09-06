# ==============================================================================
# FILE: core/workflow/orchestration_patterns.py
# DESCRIPTION: COMPLETE AG2 execution engine - Single-responsibility pattern for all workflow orchestration
# ==============================================================================

"""
MozaiksAI Orchestration Engine (organized)

Purpose
- Single entry point to run a workflow using AG2 patterns with streaming, tools, persistence, and telemetry.

Sections (skim map)
- Logging setup (chat/workflow/perf)
- run_workflow_orchestration: main orchestration contract and steps
- create_orchestration_pattern: AG2 pattern factory
- logging helpers: agent message details and full conversation logging
"""

from typing import Dict, List, Optional, Any, Callable, Tuple
from datetime import datetime
import logging
import time
from time import perf_counter
import asyncio
import os
import inspect
from opentelemetry import trace
from core.observability.otel_helpers import timed_span

from autogen import ConversableAgent, UserProxyAgent, runtime_logging
from autogen.agentchat.group.patterns import (
    DefaultPattern as AG2DefaultPattern,
    AutoPattern as AG2AutoPattern,
    RoundRobinPattern as AG2RoundRobinPattern,
    RandomPattern as AG2RandomPattern,
)
from autogen.events.agent_events import (
    FunctionCallEvent, 
    ToolCallEvent,
)
from core.workflow.structured_outputs import agent_has_structured_output, get_structured_output_model_fields
from core.data.persistence_manager import AG2PersistenceManager as _PM

from ..data.persistence_manager import AG2PersistenceManager
from .termination_handler import create_termination_handler
from logs.logging_config import (
    get_chat_logger,
    get_workflow_logger,
    WorkflowLogger,
)
from core.observability.performance_manager import get_performance_manager

# Import consolidated logging system

logger = logging.getLogger(__name__)

# Consolidated logging with optimized workflow logger
chat_logger = get_chat_logger("orchestration")
workflow_logger = get_workflow_logger("orchestration")
performance_logger = get_workflow_logger("performance.orchestration")

from .ui_tools import InputTimeoutEvent

__all__ = [
    'run_workflow_orchestration',
    'create_orchestration_pattern',
    'InputTimeoutEvent'
]

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
def _extract_agent_name(obj: Any) -> Optional[str]:
    """Best-effort extraction of an agent/sender name from AG2 event/message objects.

    Checks direct attributes, nested sender object, content dict, and string patterns.
    """
    try:
        # Direct attributes
        for k in ("sender", "agent", "agent_name", "name"):
            v = getattr(obj, k, None)
            if isinstance(v, str) and v.strip():
                return v.strip()
            # sender may be an object with 'name'
            if v and hasattr(v, "name"):
                nv = getattr(v, "name", None)
                if isinstance(nv, str) and nv.strip():
                    return nv.strip()
        content = getattr(obj, "content", None)
        if isinstance(content, dict):
            for k in ("sender", "agent", "agent_name", "name"):
                v = content.get(k)
                if isinstance(v, str) and v.strip():
                    return v.strip()
        # Parse from string representation if available
        if isinstance(content, str):
            import re
            m = re.search(r"sender(?:=|\"\s*:)['\"]([^'\"\\]+)['\"]", content)
            if m:
                return m.group(1).strip()
        return None
    except Exception:  # pragma: no cover
        return None

# ===================================================================
# SINGLE ENTRY POINT
# ===================================================================

"""Internal helper: load workflow config block."""
def _load_workflow_config(workflow_name: str):
    from .workflow_manager import workflow_manager
    config = workflow_manager.get_config(workflow_name)
    return {
        "config": config,
        "max_turns": config.get("max_turns", 50),
        "orchestration_pattern": config.get("orchestration_pattern", "AutoPattern"),
        "startup_mode": config.get("startup_mode", "AgentDriven"),
        "human_in_loop": config.get("human_in_the_loop", False),
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
    if resumed_messages and len(resumed_messages) > 0:
        logger.info(f"🔄 Resuming chat {chat_id} with {len(resumed_messages)} messages.")
        initial_messages: List[Dict[str, Any]] = resumed_messages
        if initial_message:
            initial_messages.append({"role": "user", "name": "user", "content": initial_message})
    else:
        logger.info(f"🚀 Starting new chat session for {chat_id}")
        initial_messages = []
        if initial_message:
            initial_messages.append({"role": "user", "name": "user", "content": initial_message})
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
            wf_logger.error(f"❌ Failed to create chat session doc for {chat_id}: {cs_err}")
        try:
            await termination_handler.on_conversation_start(user_id=current_user_id)
            logger.info("✅ Termination handler started for new conversation")
        except Exception as start_err:
            logger.error(f"❌ Termination handler start failed: {start_err}")
    if not initial_messages:
        seed = config.get("initial_message") or config.get("initial_message_to_user")
        if seed:
            initial_messages = [{"role": "user", "name": "user", "content": seed}]
    return resumed_messages, initial_messages


async def _load_llm_config(workflow_name: str, wf_logger, workflow_name_upper: str):
    from .structured_outputs import get_llm_for_workflow
    try:
        _, llm_config = await get_llm_for_workflow(workflow_name, "base")
        wf_logger.info(f"✅ [{workflow_name_upper}] Using workflow-specific LLM config")
    except (ValueError, FileNotFoundError):
        from .llm_config import get_llm_config
        _, llm_config = await get_llm_config()
        wf_logger.info(f"✅ [{workflow_name_upper}] Using default LLM config")
    return llm_config


async def _build_context_blocking(
    context_factory: Optional[Callable],
    workflow_name: str,
    enterprise_id: str,
    wf_logger,
    workflow_name_upper: str,
):
    """Build context and wait for it to be fully populated before first turn.

    - If a context_factory is provided, supports both sync and async factories.
    - Otherwise, uses context_variables.get_context_async to load context blocking.
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
        wf_logger.error(f"❌ [{workflow_name_upper}] Context load failed: {e}")
        return None


async def _define_agents(agents_factory: Optional[Callable], workflow_name: str):
    if agents_factory:
        return await agents_factory()
    from .agents import define_agents
    return await define_agents(workflow_name)


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
        human_in_loop_flag = config.get("human_in_the_loop", False)
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


async def _create_pattern_and_handoffs(
    orchestration_pattern: str,
    workflow_name: str,
    agents: Dict[str, ConversableAgent],
    initiating_agent: ConversableAgent,
    user_proxy_agent: Optional[UserProxyAgent],
    human_in_loop: bool,
    context: Any,
    llm_config: Dict[str, Any],
    handoffs_factory: Optional[Callable],
    wf_logger,
):
    agents_list = [
        a for n, a in agents.items() if not (n == "user" and human_in_loop and user_proxy_agent is not None)
    ]
    # Ensure context is an AG2 ContextVariables instance if possible
    ag2_context = context
    try:
        from autogen.agentchat.group import ContextVariables as _AG2Context
        if context is None:
            ag2_context = _AG2Context()
        elif not isinstance(context, _AG2Context):
            # Attempt to coerce from dict-like
            if hasattr(context, 'to_dict'):
                ag2_context = _AG2Context(data=context.to_dict())
            elif isinstance(context, dict):
                ag2_context = _AG2Context(data=context)
            else:
                # Fallback: wrap as single value for visibility
                ag2_context = _AG2Context(data={"value": context})
        wf_logger.info(
            f"🧠 [CONTEXT] Prepared AG2 ContextVariables for pattern | keys={list(getattr(ag2_context,'data',{}).keys())}"
        )
    except Exception as _cv_err:
        wf_logger.warning(f"⚠️ [CONTEXT] Could not coerce context to AG2 ContextVariables: {_cv_err}")
        ag2_context = context

    pattern = create_orchestration_pattern(
        pattern_name=orchestration_pattern,
        initial_agent=initiating_agent,
        agents=agents_list,
        user_agent=user_proxy_agent,
        context_variables=ag2_context,
        human_in_the_loop=human_in_loop,
        group_manager_args={"llm_config": llm_config},
    )
    try:
        # Light sanity: if pattern exposes group_manager/context_variables, log keys
        gm = getattr(pattern, "group_manager", None)
        if gm and hasattr(gm, "context_variables"):
            cv = getattr(gm, "context_variables")
            keys = list(getattr(cv, "data", {}).keys()) if hasattr(cv, "data") else []
            wf_logger.info(f"🔗 [PATTERN] ContextVariables attached to group manager | keys={keys}")
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
    return pattern


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
):
    from autogen.agentchat import a_run_group_chat
    from autogen.events.agent_events import (
        TextEvent,
        InputRequestEvent,
        GroupChatResumeEvent,
        SelectSpeakerEvent,
        RunCompletionEvent,
        ErrorEvent,
    )
    from autogen.events.client_events import UsageSummaryEvent
    try:
        from autogen.events.print_event import PrintEvent
    except Exception:  # pragma: no cover
        PrintEvent = object  # type: ignore

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
        wf_logger.info(f"🧭 [EVENTS_INIT] ContextVariables available at start | keys={gm_ctx_keys}")
    except Exception as _ctx_log_err:
        wf_logger.debug(f"[EVENTS_INIT] ContextVariables keys logging skipped: {_ctx_log_err}")
    if resumed_mode:
        wf_logger.info(f"🔄 [AG2_RESUME] Using AG2 a_resume path for chat {chat_id} (history={len(initial_messages)} messages)")
        wf_logger.info(f"🔄 [AG2_RESUME] Pattern type: {type(pattern).__name__} | Messages count: {len(initial_messages)}")
        
        # Log initial messages for debugging
        for i, msg in enumerate(initial_messages):
            wf_logger.debug(f"🔄 [AG2_RESUME] Message[{i}]: {msg.get('role', 'unknown')} from {msg.get('name', 'unknown')}")
        
        prep_res = pattern.prepare_group_chat(messages=initial_messages)  # type: ignore[attr-defined]
        if asyncio.iscoroutine(prep_res):  # type: ignore
            prep_res = await prep_res  # type: ignore
        if isinstance(prep_res, (list, tuple)) and len(prep_res) == 2:
            group_manager = prep_res[1]
        else:
            group_manager = getattr(pattern, "group_manager", None)
            
        wf_logger.info(f"🔄 [AG2_RESUME] Group manager resolved: {type(group_manager).__name__ if group_manager else 'None'}")
        
        if not group_manager or not hasattr(group_manager, "a_resume"):
            wf_logger.error(f"❌ [AG2_RESUME] Pattern missing required a_resume capability!")
            raise RuntimeError("Pattern missing required a_resume capability; backward compatibility removed")
            
        wf_logger.info(f"🚀 [AG2_RESUME] Calling group_manager.a_resume() with {len(initial_messages)} messages, max_rounds={max_turns}")
        
        try:
            response = await asyncio.wait_for(
                group_manager.a_resume(messages=initial_messages, max_rounds=max_turns), timeout=300.0
            )  # type: ignore[attr-defined]
            wf_logger.info(f"✅ [AG2_RESUME] a_resume() completed successfully!")
        except Exception as resume_err:
            wf_logger.error(f"❌ [AG2_RESUME] a_resume() failed: {resume_err}")
            raise
    else:
        wf_logger.info(f"🚀 [AG2_RUN] Using AG2 a_run_group_chat for NEW chat {chat_id}")
        wf_logger.info(f"🚀 [AG2_RUN] Pattern type: {type(pattern).__name__} | Messages count: {len(initial_messages)} | Max rounds: {max_turns}")
        
        # Log initial messages for debugging
        for i, msg in enumerate(initial_messages):
            wf_logger.debug(f"🚀 [AG2_RUN] Message[{i}]: {msg.get('role', 'unknown')} from {msg.get('name', 'unknown')} - {str(msg.get('content', ''))[:100]}")
            
        wf_logger.info(f"🔥 [AG2_RUN] Calling a_run_group_chat() NOW...")
        
        try:
            response = await asyncio.wait_for(
                a_run_group_chat(pattern=pattern, messages=initial_messages, max_rounds=max_turns), timeout=300.0
            )
            wf_logger.info(f"✅ [AG2_RUN] a_run_group_chat() completed successfully!")
        except Exception as run_err:
            wf_logger.error(f"❌ [AG2_RUN] a_run_group_chat() failed: {run_err}")
            raise

    turn_agent: Optional[str] = None
    turn_started: Optional[float] = None
    sequence_counter = 0
    first_event_logged = False
    last_agent_usage: Dict[str, Dict[str, Any]] = {}
    
    chat_logger.info(f"📡 [EVENT_STREAM] Starting event processing loop for chat {chat_id}")
    
    for agent_name, agent in agents.items():
        try:
            if hasattr(agent, "get_actual_usage"):
                usage = agent.get_actual_usage()
                if usage:
                    last_agent_usage[agent_name] = {
                        "prompt_tokens": usage.get("prompt_tokens", 0),
                        "completion_tokens": usage.get("completion_tokens", 0),
                        "total_cost": usage.get("total_cost", 0.0),
                    }
                else:
                    last_agent_usage[agent_name] = {
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "total_cost": 0.0,
                    }
        except Exception:
            last_agent_usage[agent_name] = {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_cost": 0.0,
            }

    pending_input_requests: dict[str, Any] = {}
    # Track which agent initiated each tool call so we can echo it on the response if missing
    tool_call_initiators: dict[str, str] = {}
    # Track tool names by id so responses can be labeled even if AG2 omits tool_name
    tool_names_by_id: dict[str, str] = {}
    try:
        if transport:
            transport.register_orchestration_input_registry(chat_id, pending_input_requests)  # type: ignore[attr-defined]
    except Exception as e:
        logger.debug(f"Failed to register orchestration input registry for {chat_id}: {e}")

    from .ui_tools import handle_tool_call_for_ui_interaction, InputTimeoutEvent as _ITO
    from autogen.events.agent_events import FunctionCallEvent as _FC, ToolCallEvent as _TC
    try:
        executed_agents: set[str] = set()
        async for ev in response.events:  # type: ignore[attr-defined]
            if not first_event_logged:
                wf_logger.info(
                    f"🛰️ [{workflow_name_upper}] First event received: {ev.__class__.__name__} chat_id={chat_id}"
                )
                first_event_logged = True
            sequence_counter += 1
            try:
                if isinstance(ev, TextEvent):
                    await persistence_manager.save_event(ev, chat_id, enterprise_id)  # type: ignore[arg-type]
            except Exception as e:
                logger.warning(f"Failed to save TextEvent for {chat_id}: {e}")

            # Note: FunctionCallEvent/ToolCallEvent are handled by AG2's executor.
            # Tool functions themselves should call use_ui_tool() to emit UI artifacts
            # and await user responses. Orchestration remains workflow-agnostic here.

            if isinstance(ev, SelectSpeakerEvent):
                if turn_agent and turn_started is not None:
                    duration = max(0.0, time.perf_counter() - turn_started)
                    prompt_delta = completion_delta = 0
                    cost_delta = 0.0
                    if turn_agent in agents:
                        agent = agents[turn_agent]
                        try:
                            if hasattr(agent, "get_actual_usage"):
                                current_usage = agent.get_actual_usage()
                                if current_usage:
                                    # Ensure agent is in last_agent_usage (first-time agent handling)
                                    if turn_agent not in last_agent_usage:
                                        last_agent_usage[turn_agent] = {
                                            "prompt_tokens": 0,
                                            "completion_tokens": 0,
                                            "total_cost": 0.0,
                                        }
                                        logger.debug(f"Initialized last_agent_usage for new agent: {turn_agent}")
                                    
                                    last_usage = last_agent_usage[turn_agent]
                                    prompt_delta = (
                                        current_usage.get("prompt_tokens", 0) - last_usage["prompt_tokens"]
                                    )
                                    completion_delta = (
                                        current_usage.get("completion_tokens", 0)
                                        - last_usage["completion_tokens"]
                                    )
                                    cost_delta = (
                                        current_usage.get("total_cost", 0.0) - last_usage["total_cost"]
                                    )
                                    
                                    # DEBUG: Log token detection
                                    if prompt_delta > 0 or completion_delta > 0 or cost_delta > 0:
                                        logger.debug(f"Token usage detected: agent={turn_agent} "
                                                   f"prompt_delta={prompt_delta} completion_delta={completion_delta} "
                                                   f"cost_delta={cost_delta}")
                                    
                                    last_agent_usage[turn_agent] = {
                                        "prompt_tokens": current_usage.get("prompt_tokens", 0),
                                        "completion_tokens": current_usage.get("completion_tokens", 0),
                                        "total_cost": current_usage.get("total_cost", 0.0),
                                    }
                                else:
                                    logger.debug(f"Agent {turn_agent} get_actual_usage() returned None/empty")
                            else:
                                logger.debug(f"Agent {turn_agent} does not have get_actual_usage() method")
                        except Exception as e:
                            logger.debug(f"Failed to get usage for agent {turn_agent}: {e}")
                    safe_prompt = max(0, prompt_delta)
                    safe_completion = max(0, completion_delta)
                    safe_cost = max(0.0, cost_delta)
                    if safe_prompt or safe_completion or safe_cost:
                        try:
                            await persistence_manager.update_session_metrics(
                                chat_id=chat_id,
                                enterprise_id=enterprise_id,
                                user_id=user_id or "unknown",
                                workflow_name=workflow_name,
                                prompt_tokens=safe_prompt,
                                completion_tokens=safe_completion,
                                cost_usd=safe_cost,
                                agent_name=turn_agent,
                                event_ts=datetime.utcnow(),
                            )
                        except Exception as m_err:
                            logger.exception(f"Metrics update failed for turn {turn_agent}: {m_err}")
                    try:
                        await perf_mgr.record_agent_turn(
                            chat_id=chat_id,
                            agent_name=turn_agent,
                            duration_sec=duration,
                            model=None,
                            prompt_tokens=safe_prompt,
                            completion_tokens=safe_completion,
                            cost=safe_cost,
                        )
                    except Exception as e:
                        logger.warning(f"Failed to record turn for {turn_agent}: {e}")
                turn_agent = getattr(ev, "sender", None) or getattr(ev, "agent", None)
                if turn_agent:
                    executed_agents.add(str(turn_agent))
                turn_started = time.perf_counter()
                wf_logger.debug(
                    f"🔄 [{workflow_name_upper}] New turn started with agent={turn_agent} seq={sequence_counter} chat_id={chat_id}"
                )

            if isinstance(ev, InputRequestEvent):
                request_id = getattr(ev, "id", None) or getattr(ev, "uuid", None)
                request_id = str(request_id)
                respond_cb = getattr(getattr(ev, "content", None), "respond", None)
                if respond_cb:
                    pending_input_requests[request_id] = respond_cb
                    try:
                        if transport:
                            transport.register_input_request(chat_id, request_id, respond_cb)  # type: ignore[attr-defined]
                    except Exception as e:
                        logger.debug(f"Failed to register input request {request_id}: {e}")

            if transport:
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
                    )
                    from autogen.events.client_events import UsageSummaryEvent as _US
                    from autogen.events.print_event import PrintEvent as _PE
                    et_name = ev.__class__.__name__
                    payload: Dict[str, Any] = {"event_type": et_name}
                    if isinstance(ev, _T):
                        sender = _extract_agent_name(ev)
                        raw_content = getattr(ev, "content", None)
                        payload.update({"kind": "text", "agent": sender, "content": raw_content})
                        try:
                            if sender and workflow_name and agent_has_structured_output(workflow_name, sender):
                                structured = _PM._extract_json_from_text(raw_content) if hasattr(_PM, '_extract_json_from_text') else None
                                if structured:
                                    payload["structured_output"] = structured
                                    schema_fields = get_structured_output_model_fields(workflow_name, sender)
                                    if schema_fields:
                                        payload["structured_schema"] = schema_fields
                        except Exception as so_err:  # pragma: no cover
                            wf_logger.debug(f"Structured output attach failed sender={sender}: {so_err}")
                    elif isinstance(ev, _PE):
                        payload.update(
                            {
                                "kind": "print",
                                "agent": _extract_agent_name(ev),
                                "content": getattr(ev, "content", None),
                            }
                        )
                    elif isinstance(ev, _IR):
                        # Extract agent name
                        agent_name = _extract_agent_name(ev)
                        payload.update(
                            {
                                "kind": "input_request",
                                "agent": agent_name,
                                "request_id": getattr(ev, "id", None) or getattr(ev, "input_request_id", None),
                                "prompt": getattr(ev, "content", None),
                            }
                        )
                    elif isinstance(ev, _ITO):
                        # Extract agent name  
                        agent_name = _extract_agent_name(ev)
                        payload.update(
                            {
                                "kind": "input_timeout",
                                "agent": agent_name,
                                "input_request_id": getattr(ev, "input_request_id", None),
                                "timeout_seconds": getattr(ev, "timeout_seconds", None),
                            }
                        )
                    elif isinstance(ev, _SS):
                        # Extract both current agent and next agent
                        agent_name = _extract_agent_name(ev)
                        next_agent_obj = getattr(ev, "agent", None)
                        next_agent = None
                        if next_agent_obj:
                            next_agent = getattr(next_agent_obj, "name", None) or str(next_agent_obj)
                        payload.update(
                            {
                                "kind": "select_speaker",
                                "agent": agent_name,
                                "next": next_agent,
                            }
                        )
                    elif isinstance(ev, _GR):
                        payload.update({"kind": "resume_boundary"})
                    elif isinstance(ev, (_FCe, _TCe)):
                        # Initialize to ensure availability for later debug logging even if early branches set tool_name
                        content_obj = None  # predefine to avoid potential UnboundLocalError in logging
                        tool_name = None
                        # ToolCallEvent path
                        tool_calls = getattr(ev, "tool_calls", None)
                        if isinstance(tool_calls, list) and tool_calls:
                            first_call = tool_calls[0]
                            fn = getattr(first_call, "function", None)
                            name_attr = getattr(fn, "name", None)
                            if isinstance(name_attr, str):
                                tool_name = name_attr
                        # FunctionCallEvent path
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
                            # NEW: Check tool_calls array for function name
                            if not tool_name and content_obj:
                                tool_calls = getattr(content_obj, "tool_calls", None)
                                if isinstance(tool_calls, list) and tool_calls:
                                    first_tool = tool_calls[0]
                                    function_obj = getattr(first_tool, "function", None)
                                    if function_obj:
                                        tool_name = getattr(function_obj, "name", None)
                                        if tool_name:
                                            wf_logger.debug(f"✅ [TOOL_EXTRACT] Found tool name: {tool_name}")
                        if not tool_name:
                            tool_name = "unknown_tool"
                        tool_call_id = (
                            getattr(ev, "id", None)
                            or getattr(ev, "uuid", None)
                            or f"tool_{tool_name}"
                        )
                        # Attempt to extract tool arguments from multiple possible AG2 event shapes
                        extracted_args = {}
                        try:
                            # From tool_calls array (function.arguments)
                            if isinstance(tool_calls, list) and tool_calls:
                                first_tool = tool_calls[0]
                                f_fn = getattr(first_tool, "function", None)
                                if f_fn is not None:
                                    poss_args = getattr(f_fn, "arguments", None)
                                    if isinstance(poss_args, dict):
                                        extracted_args = poss_args
                            # From function_call attribute
                            if not extracted_args:
                                function_call = getattr(ev, "function_call", None)
                                if function_call is not None:
                                    poss_args = getattr(function_call, "arguments", None)
                                    if isinstance(poss_args, dict):
                                        extracted_args = poss_args
                            # From content object
                            if not extracted_args and content_obj is None:
                                content_obj = getattr(ev, "content", None)
                            if not extracted_args and content_obj is not None:
                                poss_args = getattr(content_obj, "arguments", None)
                                if isinstance(poss_args, dict):
                                    extracted_args = poss_args
                        except Exception as arg_ex:
                            wf_logger.debug(f"[TOOL_ARGS] extraction failed for {tool_name}: {arg_ex}")

                        agent_for_tool = _extract_agent_name(ev) or turn_agent or getattr(ev, "sender", None)
                        # Cache tool name and initiator for later correlation
                        if tool_call_id:
                            tool_names_by_id[str(tool_call_id)] = str(tool_name)
                        init_agent = agent_for_tool or payload.get("agent")
                        if init_agent and tool_call_id:
                            tool_call_initiators[str(tool_call_id)] = init_agent
                        # Only emit a chat.tool_call to the UI when arguments exist; otherwise the tool likely manages its own UI
                        if extracted_args:
                            payload.update(
                                {
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
                                }
                            )
                            wf_logger.debug(f"🛠️ [TOOL_CALL] agent={agent_for_tool} tool={tool_name} id={tool_call_id} args_keys={list(extracted_args.keys())}")
                        else:
                            # No args: skip emitting tool_call to UI to avoid confusion/noise
                            wf_logger.debug(f"� [TOOL_CALL_SUPPRESSED] tool={tool_name} id={tool_call_id} (no args)")
                    elif isinstance(ev, (_FRe, _TRe)):
                        # Extract tool name using same logic as tool call events
                        tool_name = getattr(ev, "tool_name", None)
                        content_obj = getattr(ev, "content", None)
                        if not tool_name and content_obj:
                            tool_name = (
                                getattr(content_obj, "tool_name", None)
                                or getattr(content_obj, "name", None)
                            )
                        # NEW: Check tool_calls array for function name (same as tool call events)
                        if not tool_name and content_obj:
                            tool_calls = getattr(content_obj, "tool_calls", None)
                            if isinstance(tool_calls, list) and tool_calls:
                                first_tool = tool_calls[0]
                                function_obj = getattr(first_tool, "function", None)
                                if function_obj:
                                    tool_name = getattr(function_obj, "name", None)
                                    if tool_name:
                                        wf_logger.debug(f"✅ [TOOL_EXTRACT_RESPONSE] Found tool name: {tool_name}")
                        if not tool_name:
                            tool_name = "unknown_tool"
                        
                        # Extract agent name using same logic as text events
                        agent_name = _extract_agent_name(ev)
                        
                        tool_response_id = (
                            getattr(ev, "id", None)
                            or getattr(ev, "uuid", None)
                            or getattr(ev, "tool_call_id", None)
                        )
                        # Fallback: if no agent_name extracted, reuse initiator agent
                        if not agent_name and tool_response_id:
                            fallback_agent = tool_call_initiators.get(str(tool_response_id))
                            if fallback_agent:
                                agent_name = fallback_agent
                                wf_logger.debug(
                                    f"♻️ [TOOL_RESPONSE_AGENT_FALLBACK] Using initiator agent={agent_name} for tool_response id={tool_response_id}"
                                )
                        # Try to backfill tool_name using prior mapping if still unknown
                        if (not tool_name or tool_name == "unknown_tool") and tool_response_id:
                            tool_name = tool_names_by_id.get(str(tool_response_id), tool_name)
                        payload.update(
                            {
                                "kind": "tool_response",
                                "tool_name": str(tool_name),
                                "agent": agent_name,
                                "tool_call_id": str(tool_response_id) if tool_response_id else None,
                                "corr": str(tool_response_id) if tool_response_id else None,
                                "content": getattr(ev, "content", None),
                            }
                        )
                        wf_logger.debug(
                            f"✅ [TOOL_RESPONSE] agent={agent_name} tool={tool_name} id={tool_response_id}"
                        )
                    elif isinstance(ev, _US):
                        for f in (
                            "total_tokens",
                            "prompt_tokens",
                            "completion_tokens",
                            "cost",
                            "model",
                        ):
                            if hasattr(ev, f):
                                payload[f] = getattr(ev, f)
                        payload.update({"kind": "usage_summary"})
                    elif isinstance(ev, _EE):
                        # Extract agent name
                        agent_name = _extract_agent_name(ev)
                        payload.update(
                            {
                                "kind": "error",
                                "agent": agent_name,
                                "message": getattr(ev, "message", None)
                                or getattr(ev, "content", None)
                                or str(ev),
                            }
                        )
                    elif isinstance(ev, _RC):
                        rc_agent = _extract_agent_name(ev) or getattr(ev, "agent", None) or "workflow"
                        payload.update(
                            {
                                "kind": "run_complete",
                                "agent": rc_agent,
                            }
                        )
                    else:
                        payload.update({"kind": "unknown"})
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
                    agg_prompt = (
                        getattr(content_obj, "prompt_tokens", 0) if content_obj else 0
                    )
                    agg_completion = (
                        getattr(content_obj, "completion_tokens", 0) if content_obj else 0
                    )
                    agg_cost = getattr(content_obj, "cost", 0.0) if content_obj else 0.0
                    tracked_prompt = sum(u["prompt_tokens"] for u in last_agent_usage.values())
                    tracked_completion = sum(
                        u["completion_tokens"] for u in last_agent_usage.values()
                    )
                    tracked_cost = sum(u["total_cost"] for u in last_agent_usage.values())
                    delta_prompt = max(0, int(agg_prompt - tracked_prompt))
                    delta_completion = max(0, int(agg_completion - tracked_completion))
                    delta_cost = max(0.0, float(agg_cost - tracked_cost))
                    if delta_prompt or delta_completion or delta_cost:
                        await persistence_manager.update_session_metrics(
                            chat_id=chat_id,
                            enterprise_id=enterprise_id,
                            user_id=user_id or "unknown",
                            workflow_name=workflow_name,
                            prompt_tokens=delta_prompt,
                            completion_tokens=delta_completion,
                            cost_usd=delta_cost,
                            agent_name=None,
                            event_ts=datetime.utcnow(),
                        )
                except Exception as e:
                    logger.exception(
                        f"UsageSummaryEvent reconciliation failed: {e}"
                    )

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
                            f"⚠️ [{workflow_name_upper}] RunCompletionEvent early. Executed: {sorted(executed_agents)} | Pending after_work chain: {remaining_after_work}"
                        )
                except Exception as diag_err:
                    wf_logger.debug(
                        f"Early termination diagnostics failed: {diag_err}"
                    )
                wf_logger.info(
                    f"✅ [{workflow_name_upper}] Run complete chat_id={chat_id} events={sequence_counter} executed_agents={sorted(executed_agents)}"
                )
                break
    except Exception as loop_err:
        wf_logger.error(f"Event loop failure: {loop_err}")

    return {
        "response": response,
        "turn_agent": turn_agent,
        "turn_started": turn_started,
        "last_agent_usage": last_agent_usage,
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
    logger.info(f"🚀 [ORCHESTRATION] Starting {workflow_name} workflow")
    
    # Use existing workflow logger as session logger
    session_logger = wf_logger

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

    tracer = trace.get_tracer("mozaiks.workflow")
    result_payload: Optional[Dict[str, Any]] = None
    runtime_logging_started = False
    runtime_logging_session_id: Optional[str] = None
    runtime_mode = os.getenv("AUTOGEN_RUNTIME_LOGGING")  # any truthy value enables file logging
    if runtime_mode:
        try:
            fname = os.getenv("AUTOGEN_RUNTIME_LOG_FILE", "runtime.log")
            runtime_logging_session_id = runtime_logging.start(logger_type="file", config={"filename": fname})
            runtime_logging_started = True
            if runtime_mode.lower() not in ("file", "1", "true", "yes"):  # notify about forced file mode
                logger.info(f"AG2 runtime logging forcing file mode (requested '{runtime_mode}') session_id={runtime_logging_session_id}")
            else:
                logger.info(f"AG2 runtime logging started file session_id={runtime_logging_session_id}")
        except Exception as rl_err:  # pragma: no cover - non critical
            logger.warning(f"Failed to start AG2 runtime logging (file mode): {rl_err}")

    # -----------------------------------------------------------------
    # Reconnect handshake (optional) - if client supplies last_seen_sequence
    # kwargs key: last_seen_sequence (int). If provided we replay diff of
    # normalized events (sequence > last_seen_sequence) to the UI transport
    # BEFORE starting the AG2 pattern run. This is a best-effort replay; any
    # failures are logged and ignored (live stream then proceeds).
    # -----------------------------------------------------------------

    perf_mgr = await get_performance_manager()
    await perf_mgr.initialize()
    await perf_mgr.record_workflow_start(chat_id, enterprise_id, workflow_name, user_id or "unknown")

    with tracer.start_as_current_span(
        "workflow.run",
        attributes={
            "workflow_name": workflow_name,
            "chat_id": chat_id,
            "enterprise_id": enterprise_id,
            "user_id": user_id or "unknown"
        }
    ) as root_span:
        span_ctx = root_span.get_span_context()
        trace_id_hex = format(span_ctx.trace_id, '032x')
        # Fallback: some OTEL setups may yield 0 trace id if provider not initialized
        if trace_id_hex == '0' * 32:
            import uuid
            trace_id_hex = uuid.uuid4().hex
            logger.debug(f"Generated fallback trace_id for workflow {workflow_name}: {trace_id_hex}")
        try:
            await perf_mgr.attach_trace_id(chat_id, trace_id_hex)
        except Exception as e:
            logger.debug(f"trace attach failed: {e}")

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
            # 3) LLM config
            # -----------------------------------------------------------------
            llm_config = await _load_llm_config(workflow_name, wf_logger, workflow_name_upper)

            # -----------------------------------------------------------------
            # 3.5) Structured outputs preload (blocking)
            # -----------------------------------------------------------------
            try:
                from .structured_outputs import load_workflow_structured_outputs as _preload_so
                _preload_so(workflow_name)
                wf_logger.info(f"✅ [{workflow_name_upper}] Structured outputs preloaded")
            except Exception as so_err:
                # Do not fail the run, but surface misconfiguration early
                wf_logger.warning(f"⚠️ [{workflow_name_upper}] Structured outputs preload failed: {so_err}")

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
            with timed_span(
                "workflow.context_build",
                attributes={
                    "workflow_name": workflow_name,
                    "chat_id": chat_id,
                    "enterprise_id": enterprise_id,
                },
            ):
                context = await _build_context_blocking(
                    context_factory=context_factory,
                    workflow_name=workflow_name,
                    enterprise_id=enterprise_id,
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

            # Note: We intentionally do NOT inject context variables into prompts.
            # Per AG2 design, ContextVariables remain separate from LLM prompts and are
            # accessed via tools, system templates, or handoffs. This keeps prompts clean
            # and token-efficient.

            # -----------------------------------------------------------------
            # 6) Agents definition + tool registry
            # -----------------------------------------------------------------
            agents = await _define_agents(agents_factory, workflow_name)
            agents = agents or {}
            if not agents:
                raise RuntimeError(f"No agents defined for workflow '{workflow_name}'")

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
            wf_logger.info(f"🔧 [{workflow_name_upper}] Tools bound across agents: {total_tool_count}")
            
            # Log consolidated agent setup summary using existing logger
            try:
                wf_logger.info(
                    f"🏗️ [WORKFLOW_SETUP] {workflow_name}: agents={list(agents.keys())} tools={len(agent_tools)}"
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
                wf_logger.info(f"🪝 [{workflow_name_upper}] Hooks registered across agents: {total_hooks}")
                workflow_logger.debug(f"[ORCH][TRACE] Hooks snapshot: {hooks_snapshot}")
            except Exception as hook_snap_err:  # pragma: no cover
                wf_logger.debug(f"Hooks snapshot failed: {hook_snap_err}")

            # Defer start log until after agents + initiating agent known
            try:
                context_var_count = (len(context) if context is not None and hasattr(context, '__len__') else 0)
            except Exception:
                context_var_count = 0

            wf_logger.debug(
                f"🚀 [{workflow_name_upper}] Chat START chat_id={chat_id} agents={len(agents)} max_turns={max_turns} "
                f"startup_mode={startup_mode} human_in_loop={human_in_loop} context_vars={context_var_count} resumed={resumed_mode}"
            )

            # -----------------------------------------------------------------
            wf_logger.info(f"🔧 [{workflow_name_upper}] Tools already bound at agent creation; skipping runtime registration")

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
                f"🎯 [{workflow_name_upper}] Initial agent resolved: {getattr(initiating_agent,'name',None)}"
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
            pattern = await _create_pattern_and_handoffs(
                orchestration_pattern=orchestration_pattern,
                workflow_name=workflow_name,
                agents=agents,
                initiating_agent=initiating_agent,
                user_proxy_agent=user_proxy_agent,
                human_in_loop=human_in_loop,
                context=context,
                llm_config=llm_config,
                handoffs_factory=handoffs_factory,
                wf_logger=wf_logger,
            )
            # 10.5) Hook registration removed (was duplicate)
            # Hooks are now registered once inside define_agents() via workflow_manager.register_hooks.
            # This avoids duplicate log noise and ensures _hooks_loaded_workflows gating is respected.
            # -----------------------------------------------------------------
            # 11) Execute group chat with AG2's event streaming
            # -----------------------------------------------------------------
            # Log execution start with summary
            wf_lifecycle_logger.info(
                f"🚀 [{workflow_name_upper}] Starting workflow execution",
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
            )
            response = stream_state["response"]
            turn_agent = stream_state["turn_agent"]
            turn_started = stream_state["turn_started"]
            last_agent_usage = stream_state["last_agent_usage"]

            # Close last turn (even if loop errored) with final usage delta
            if turn_agent and turn_started is not None:
                duration = max(0.0, time.perf_counter() - turn_started)
                
                # Calculate final usage delta for the last agent
                prompt_delta = 0
                completion_delta = 0
                cost_delta = 0.0
                
                if turn_agent in agents and turn_agent in last_agent_usage:
                    agent = agents[turn_agent]
                    try:
                        if hasattr(agent, 'get_actual_usage'):
                            current_usage = agent.get_actual_usage()
                            if current_usage:
                                last_usage = last_agent_usage[turn_agent]
                                prompt_delta = current_usage.get('prompt_tokens', 0) - last_usage['prompt_tokens']
                                completion_delta = current_usage.get('completion_tokens', 0) - last_usage['completion_tokens']
                                cost_delta = current_usage.get('total_cost', 0.0) - last_usage['total_cost']
                    except Exception as e:
                        logger.debug(f"Failed to get final usage for agent {turn_agent}: {e}")
                
                safe_prompt = max(0, prompt_delta)
                safe_completion = max(0, completion_delta)
                safe_cost = max(0.0, cost_delta)
                if safe_prompt or safe_completion or safe_cost:
                    try:
                        await persistence_manager.update_session_metrics(
                            chat_id=chat_id,
                            enterprise_id=enterprise_id,
                            user_id=user_id or "unknown",
                            workflow_name=workflow_name,
                            prompt_tokens=safe_prompt,
                            completion_tokens=safe_completion,
                            cost_usd=safe_cost,
                            agent_name=turn_agent,
                            event_ts=datetime.utcnow()
                        )
                    except Exception as m_err:
                        logger.exception(f"Final metrics update failed for {turn_agent}: {m_err}")
                try:
                    await perf_mgr.record_agent_turn(
                        chat_id=chat_id,
                        agent_name=turn_agent,
                        duration_sec=duration,
                        model=None,
                        prompt_tokens=safe_prompt,
                        completion_tokens=safe_completion,
                        cost=safe_cost
                    )
                except Exception as e:
                    logger.warning(f"Failed to record final turn for {turn_agent}: {e}")
                # Final turn complete

            # Final usage reconciliation: Real-time billing already handled per-turn via record_agent_turn
            # No additional reconciliation needed since we track deltas throughout execution

            max_turns_reached = getattr(response, 'max_turns_reached', False)

            # Ensure termination handler is called to update status
            try:
                termination_result = await termination_handler.on_conversation_end(
                    max_turns_reached=max_turns_reached
                )
                try:
                    status_val = getattr(termination_result, 'status', 'completed')
                    logger.info(f"✅ Termination completed: {status_val}")
                except Exception:
                    logger.info("✅ Termination completed (offline mode)")
            except Exception as term_err:
                logger.error(f"❌ Termination handler failed: {term_err}")

            # Safely extract messages for logging
            try:
                messages_obj = getattr(response, 'messages', None)
                if asyncio.iscoroutine(messages_obj):
                    messages_obj = await messages_obj
                if messages_obj is not None:
                    await log_conversation_to_agent_chat_file(messages_obj, chat_id, enterprise_id, workflow_name)
            except Exception as log_err:
                logger.error(f"❌ Failed to log conversation to agent chat file for {chat_id}: {log_err}")

            # Log execution completion
            duration_sec = perf_counter() - start_time
            wf_logger.info(f"⏱️ [EXECUTION_COMPLETE] Duration: {duration_sec:.2f}s")

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
            logger.error(f"❌ [{workflow_name_upper}] Orchestration failed: {e}", exc_info=True)
            try:
                await termination_handler.on_conversation_end()
                logger.info("✅ Termination handler called for error case")
            except Exception as term_err:
                logger.error(f"❌ Termination handler error cleanup failed: {term_err}")
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
            if root_span.is_recording():
                root_span.set_attribute("workflow.duration_sec", duration_sec)
                root_span.set_attribute("agent.count", len(agents))
                root_span.set_attribute("orchestration.pattern", orchestration_pattern)
            if runtime_logging_started:
                try:
                    runtime_logging.stop()
                    logger.info(f"AG2 runtime logging stopped session_id={runtime_logging_session_id}")
                except Exception as rl_stop_err:  # pragma: no cover
                    logger.warning(f"Failed stopping AG2 runtime logging: {rl_stop_err}")

    # OUTSIDE span: final logging & cleanup
    try:
        duration = perf_counter() - start_time
        
        # Log workflow completion with summary
        wf_lifecycle_logger.info(
            f"✅ [{workflow_name_upper}] Workflow completed",
            duration_sec=duration,
            event_count=getattr(stream_state, 'sequence_counter', 0) if stream_state else 0,
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
        return result_payload


# ==============================================================================
# AG2 PATTERN FACTORY - Direct AG2 Pattern Usage
# ==============================================================================

def create_orchestration_pattern(
    pattern_name: str,
    initial_agent: ConversableAgent,
    agents: List[ConversableAgent],
    user_agent: Optional[UserProxyAgent] = None,
    context_variables: Optional[Any] = None,
    group_manager_args: Optional[Dict[str, Any]] = None,
    human_in_the_loop: bool = False,
    **pattern_kwargs
) -> Any:
    """
    Factory to create AG2's native orchestration patterns.
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

    logger.info(f"🎯 Creating {pattern_name} using AG2's native implementation")
    logger.info(f"🔍 Pattern setup - initial_agent: {initial_agent.name}")
    logger.info(f"🔍 Pattern setup - agents count: {len(agents)}")
    logger.info(f"🔍 Pattern setup - user_agent included: {user_agent is not None and human_in_the_loop}")
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
            logger.info(f"🔍 Pattern setup - context_variables: True | type={cv_type} | keys={cv_keys}")
        except Exception as _log_err:
            logger.info(f"🔍 Pattern setup - context_variables: True (keys unavailable: {_log_err})")
    else:
        logger.info(f"🔍 Pattern setup - context_variables: False")

    # Build pattern arguments - AG2 patterns need all core parameters
    pattern_args = {
        "initial_agent": initial_agent,
        "agents": agents,
        "context_variables": context_variables,  # Always pass context_variables (AG2 handles None case)
    }

    if human_in_the_loop and user_agent is not None:
        pattern_args["user_agent"] = user_agent
        logger.info(f"✅ User agent included in pattern (human_in_the_loop=true)")
    else:
        logger.info(f"ℹ️ User agent excluded from pattern (human_in_the_loop={human_in_the_loop})")

    # Pass group_manager_args to the pattern (not nested inside it)
    if group_manager_args is not None:
        pattern_args["group_manager_args"] = group_manager_args

    pattern_args.update(pattern_kwargs)

    try:
        pattern = pattern_class(**pattern_args)
        logger.info(f"✅ {pattern_name} AG2 pattern created successfully")
        # Verify context presence on the created pattern/manager
        try:
            gm = getattr(pattern, 'group_manager', None)
            cv = getattr(gm, 'context_variables', None) if gm else None
            if cv is not None:
                try:
                    keys = list(cv.data.keys()) if hasattr(cv, 'data') else list(cv.to_dict().keys()) if hasattr(cv, 'to_dict') else []
                except Exception:
                    keys = []
                logger.info(f"🧩 Pattern created with ContextVariables attached to group_manager | keys={keys}")
            else:
                logger.debug("Pattern created; group_manager.context_variables not exposed at pattern level (will be set up in prepare_group_chat)")
        except Exception as _post_err:
            logger.debug(f"ContextVariables post-create check skipped: {_post_err}")
        return pattern
    except Exception as e:
        logger.warning(f"⚠️ Failed to create {pattern_name} with all args, trying minimal: {e}")
        minimal_args = {
            "initial_agent": initial_agent,
            "agents": agents,
        }
        if human_in_the_loop and user_agent is not None:
            minimal_args["user_agent"] = user_agent

        # For minimal pattern, still try to include context_variables
        if context_variables is not None:
            minimal_args["context_variables"] = context_variables
            
        minimal_pattern = pattern_class(**minimal_args)
        logger.info(f"✅ {pattern_name} AG2 pattern created with minimal args (including context_variables)")
        
        return minimal_pattern

# ==============================================================================
# LOGGING HELPERS
# ==============================================================================

def log_agent_message_details(message, sender_name, recipient_name):
    """Logs agent message details for tracking."""
    message_content = getattr(message, 'content', None) or str(message)

    if message_content and sender_name != 'unknown':
        summary = message_content[:150] + '...' if len(message_content) > 150 else message_content
        chat_logger.info(f"🤖 [AGENT] {sender_name} → {recipient_name}: {summary}")
        chat_logger.debug(f"📋 [FULL] {sender_name} complete message:\n{'-'*50}\n{message_content}\n{'-'*50}")
        chat_logger.debug(f"📊 [META] Length: {len(message_content)} chars | Type: {type(message).__name__}")
    return message


async def log_conversation_to_agent_chat_file(conversation_history, chat_id: str, enterprise_id: str, workflow_name: str):
    """
    Log the complete AG2 conversation to the agent chat log file.
    """
    try:
        agent_chat_logger = get_chat_logger("agent_messages")

        if not conversation_history:
            agent_chat_logger.info(f"🔍 [{workflow_name}] No conversation history to log for chat {chat_id}")
            return

        msg_count = len(conversation_history) if hasattr(conversation_history, '__len__') else 0
        agent_chat_logger.info(f"📝 [{workflow_name}] Logging {msg_count} messages to agent chat file for chat {chat_id}")

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
                agent_chat_logger.error(f"❌ Failed to log message {i+1} in chat {chat_id}: {msg_error}")

        agent_chat_logger.info(f"✅ [{workflow_name}] Successfully logged {msg_count} messages for chat {chat_id}")

    except Exception as e:
        logger.error(f"❌ Failed to log conversation to agent chat file for {chat_id}: {e}")
        # Do not raise
