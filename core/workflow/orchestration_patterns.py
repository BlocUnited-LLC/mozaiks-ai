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

from typing import Dict, List, Optional, Any, Callable
import logging
import time
from time import perf_counter
import asyncio
import os
from datetime import datetime
from opentelemetry import trace
from core.observability.otel_helpers import timed_span

from autogen import ConversableAgent, UserProxyAgent, gather_usage_summary
from autogen.agentchat.group.patterns import (
    DefaultPattern as AG2DefaultPattern,
    AutoPattern as AG2AutoPattern,
    RoundRobinPattern as AG2RoundRobinPattern,
    RandomPattern as AG2RandomPattern,
)
from autogen.events.agent_events import (
    FunctionCallEvent, 
    ToolCallEvent,
    SelectSpeakerEvent, 
    GroupChatResumeEvent,
    ErrorEvent,
    RunCompletionEvent,
)
from autogen.events.client_events import UsageSummaryEvent

from ..data.persistence_manager import AG2PersistenceManager
from .tool_registry import WorkflowToolRegistry
from .termination_handler import create_termination_handler
from logs.logging_config import (
    get_chat_logger,
    get_workflow_logger,
)
from core.observability.performance_manager import get_performance_manager, InsufficientTokensError

logger = logging.getLogger(__name__)

# Consolidated logging
chat_logger = get_chat_logger("orchestration")
workflow_logger = get_workflow_logger("orchestration")
performance_logger = get_workflow_logger("performance.orchestration")

from .ui_tools import event_to_ui_payload, InputTimeoutEvent, normalize_event, handle_tool_call_for_ui_interaction  # consolidated source

__all__ = [
    'run_workflow_orchestration',
    'create_orchestration_pattern',
    'event_to_ui_payload',
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

# ===================================================================
# SINGLE ENTRY POINT
# ===================================================================

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

    wf_logger = get_workflow_logger(workflow_name, chat_id=chat_id, enterprise_id=enterprise_id)
    logger.info(f"🚀 CONSOLIDATED workflow orchestration: {workflow_name}")

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
    # legacy streaming manager removed; context manager based install only

    # -----------------------------------------------------------------
    # Reconnect handshake (optional) - if client supplies last_seen_sequence
    # kwargs key: last_seen_sequence (int). If provided we replay diff of
    # normalized events (sequence > last_seen_sequence) to the UI transport
    # BEFORE starting the AG2 pattern run. This is a best-effort replay; any
    # failures are logged and ignored (live stream then proceeds).
    # -----------------------------------------------------------------
    last_seen_sequence = None
    try:
        if 'last_seen_sequence' in kwargs and kwargs['last_seen_sequence'] is not None:
            last_seen_sequence = int(kwargs['last_seen_sequence'])
    except Exception:
        last_seen_sequence = None

    if last_seen_sequence is not None:
        try:
            # Fetch diff from persistence (normalized envelopes)
            fetch_diff = getattr(persistence_manager, 'fetch_event_diff', None)
            if callable(fetch_diff):
                diff = await fetch_diff(chat_id=chat_id, enterprise_id=enterprise_id, last_sequence=last_seen_sequence)  # type: ignore[arg-type]
                if diff:
                    # Annotate replay flag and send in order
                    for env in diff:
                        payload = {
                            "kind": "replay_event",
                            "sequence": env.get("sequence"),
                            "event_type": env.get("event_type"),
                            "role": env.get("role"),
                            "name": env.get("name"),
                            "content": env.get("content"),
                            "meta": env.get("meta"),
                            "replay": True,
                        }
                        try:
                            if transport:
                                await transport.send_event_to_ui(payload, chat_id)  # type: ignore[arg-type]
                        except Exception:
                            pass
                    # Notify UI that replay complete and live stream will follow
                    try:
                        if transport:
                            await transport.send_event_to_ui({
                                "kind": "replay_complete",
                                "last_replayed_sequence": diff[-1]["sequence"],
                                "event_type": "ReplayComplete"
                            }, chat_id)  # type: ignore[arg-type]
                    except Exception:
                        pass
        except Exception as e:
            wf_logger.error(f"Reconnect replay failed: {e}")

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
        trace_id_hex = format(root_span.get_span_context().trace_id, '032x')
        try:
            await perf_mgr.attach_trace_id(chat_id, trace_id_hex)
        except Exception as e:
            logger.debug(f"trace attach failed: {e}")

        try:
            # -----------------------------------------------------------------
            # 1) Load configuration
            # -----------------------------------------------------------------
            from .workflow_config import workflow_config
            config = workflow_config.get_config(workflow_name)
            max_turns = config.get("max_turns", 50)
            orchestration_pattern = config.get("orchestration_pattern", "AutoPattern")
            startup_mode = config.get("startup_mode", "AgentDriven")
            human_in_loop = config.get("human_in_the_loop", False)
            initial_agent_name = config.get("initial_agent", None)

            # -----------------------------------------------------------------
            # 2) Resume or start chat
            # -----------------------------------------------------------------
            resumed_messages = await persistence_manager.resume_chat(chat_id, enterprise_id)

            if resumed_messages and len(resumed_messages) > 0:
                logger.info(f"🔄 Resuming chat {chat_id} with {len(resumed_messages)} messages.")
                initial_messages: List[Dict[str, Any]] = resumed_messages
                # Allow an extra incoming user message on resume
                if initial_message:
                    initial_messages.append({"role": "user", "name": "user", "content": initial_message})
            else:
                logger.info(f"🚀 Starting new chat session for {chat_id}")
                initial_messages = []
                if initial_message:
                    # Seed strict user message
                    initial_messages.append({"role": "user", "name": "user", "content": initial_message})

                current_user_id = user_id or "system_user"
                if not user_id:
                    logger.warning(f"Starting chat {chat_id} without a specific user_id. Defaulting to 'system_user'.")

                try:
                    await termination_handler.on_conversation_start(user_id=current_user_id)
                    logger.info(f"✅ Termination handler started for new conversation")
                except Exception as start_err:
                    logger.error(f"❌ Termination handler start failed: {start_err}")

            # If still empty, optionally seed from workflow config
            if not initial_messages:
                seed = config.get("initial_message") or config.get("initial_message_to_user")
                if seed:
                    # Always seed as a user turn named "user" to keep schema strict
                    initial_messages = [{"role": "user", "name": "user", "content": seed}]

            # -----------------------------------------------------------------
            # 3) LLM config
            # -----------------------------------------------------------------
            from .structured_outputs import get_llm_for_workflow
            try:
                _, llm_config = await get_llm_for_workflow(workflow_name, "base")
                wf_logger.info(f"✅ [{workflow_name_upper}] Using workflow-specific LLM config")
            except (ValueError, FileNotFoundError):
                from core.core_config import make_llm_config
                _, llm_config = await make_llm_config()
                wf_logger.info(f"✅ [{workflow_name_upper}] Using default LLM config")

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
            with timed_span("workflow.context_build", attributes={
                "workflow_name": workflow_name,
                "chat_id": chat_id,
                "enterprise_id": enterprise_id,
            }):
                if context_factory:
                    context = context_factory()
                else:
                    try:
                        from .context_variables import get_context
                        context = get_context(workflow_name, enterprise_id)
                    except Exception as e:
                        wf_logger.error(f"❌ [{workflow_name_upper}] Context load failed: {e}")
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

            # (Removed legacy AG2StreamingManager usage; streaming handled by context manager when needed)

            # -----------------------------------------------------------------
            # 6) Agents definition + tool registry
            # -----------------------------------------------------------------
            if agents_factory:
                agents = await agents_factory()
            else:
                from .agents import define_agents
                agents = await define_agents(workflow_name)
            agents = agents or {}

            try:
                registry = WorkflowToolRegistry(workflow_name)
                registry.load_configuration()
                registry.register_agent_tools(list(agents.values()))
                wf_logger.info(f"🔧 [{workflow_name_upper}] Registered tools for {len(agents)} agents")
            except Exception as reg_err:
                wf_logger.warning(f"⚠️ [{workflow_name_upper}] Tool registration skipped/failed: {reg_err}")

            # Store agents on transport
            try:
                if transport and hasattr(transport, 'connections') and chat_id in transport.connections:
                    transport.connections[chat_id]['agents'] = agents
            except Exception as _agents_store_err:
                wf_logger.debug(f"agent store failed: {_agents_store_err}")

            # Ensure user proxy presence (always named "user")
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
                    llm_config=llm_config
                )
                agents["user"] = user_proxy_agent
                human_in_loop = human_in_loop_flag
            else:
                for a in agents.values():
                    if hasattr(a, "name") and a.name.lower() in ("user", "userproxy", "userproxyagent"):
                        user_proxy_agent = a  # type: ignore[assignment]
                        break

            # -----------------------------------------------------------------
            # 7) Initiating agent (explicit or first available)
            # -----------------------------------------------------------------
            initiating_agent = None
            if initial_agent_name:
                initiating_agent = agents.get(initial_agent_name)
                if not initiating_agent:
                    for a in agents.values():
                        if getattr(a, 'name', None) == initial_agent_name:
                            initiating_agent = a
                            break
            if not initiating_agent:
                initiating_agent = next(iter(agents.values())) if agents else None
                if not initiating_agent:
                    raise ValueError(f"No agents available for workflow {workflow_name}")

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
            agents_list = [
                a for n, a in agents.items()
                if not (n == "user" and human_in_loop and user_proxy_agent is not None)
            ]
            pattern = create_orchestration_pattern(
                pattern_name=orchestration_pattern,
                initial_agent=initiating_agent,
                agents=agents_list,
                user_agent=user_proxy_agent,
                context_variables=context,
                human_in_the_loop=human_in_loop,
                group_manager_args={"llm_config": llm_config}
            )

            # -----------------------------------------------------------------
            # 10) Handoffs (DefaultPattern only)
            # -----------------------------------------------------------------
            if orchestration_pattern == "DefaultPattern":
                try:
                    if handoffs_factory:
                        await handoffs_factory(agents)
                    else:
                        from .handoffs import wire_handoffs_with_debugging
                        wire_handoffs_with_debugging(workflow_name, agents)
                except Exception as he:
                    wf_logger.warning(f"Handoffs wiring failed: {he}")

            # -----------------------------------------------------------------
            # 11) Execute group chat with AG2's event streaming
            # -----------------------------------------------------------------
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
            from core.transport.ag2_iostream import install_streaming_iostream

            # Install minimal streaming IOStream only if streaming configured
            should_stream = bool(llm_config and isinstance(llm_config, dict) and llm_config.get("stream"))
            # Production input timeout: 120 seconds
            input_timeout_seconds = 120.0
            iostream_cm = install_streaming_iostream(
                chat_id,
                enterprise_id,
                user_id=user_id or "unknown",
                workflow_name=workflow_name,
                input_timeout_seconds=input_timeout_seconds,
            ) if should_stream else None

            async def _run_chat() -> Any:
                return await asyncio.wait_for(
                    a_run_group_chat(
                        pattern=pattern,
                        messages=initial_messages,
                        max_rounds=max_turns
                    ),
                    timeout=300.0
                )

            if iostream_cm:
                with iostream_cm:  # type: ignore[arg-type]
                    response = await _run_chat()
            else:
                response = await _run_chat()

            # Refactored event loop (dispatcher + normalized persistence + registry)
            from core.transport.simple_transport import SimpleTransport
            transport = SimpleTransport._get_instance()
            # If we supplied multiple initial messages, expect a replay boundary event.
            # Otherwise (fresh conversation) we can persist immediately.
            resume_boundary_reached = not (len(initial_messages) > 1)
            turn_agent: Optional[str] = None
            turn_started: Optional[float] = None
            sequence_counter = 0
            usage_seen = False

            try:
                # Main event consumption loop
                async for ev in response.events:  # type: ignore[attr-defined]
                    # Detect resume boundary (skip persistence before it)
                    if isinstance(ev, GroupChatResumeEvent):
                        resume_boundary_reached = True
                        sequence_counter = 0
                        if transport:
                            try:
                                await transport.send_event_to_ui({  # type: ignore[arg-type]
                                    "type": "resume_boundary",
                                    "chat_id": chat_id,
                                }, chat_id)
                            except Exception:
                                pass
                        continue

                    # Skip replayed history events emitted before boundary
                    if not resume_boundary_reached:
                        continue

                    sequence_counter += 1
                    # Persist normalized envelope (delegates to persistence manager util if available)
                    try:
                        envelope = normalize_event(ev, sequence=sequence_counter, chat_id=chat_id)
                        save_norm = getattr(persistence_manager, 'save_normalized_event', None)
                        if callable(save_norm):
                            await save_norm(
                                envelope=envelope,
                                chat_id=chat_id,
                                enterprise_id=enterprise_id,
                                workflow_name=workflow_name,
                                user_id=user_id or "unknown",
                            )  # type: ignore[arg-type]
                        else:  # fallback to legacy method if present
                            await persistence_manager.save_event(  # type: ignore[call-arg]
                                event=ev,
                                chat_id=chat_id,
                                enterprise_id=enterprise_id,
                                workflow_name=workflow_name,
                                user_id=user_id or "unknown",
                            )
                    except Exception:
                        pass

                    # Turn timing using SelectSpeakerEvent boundaries
                    if isinstance(ev, SelectSpeakerEvent):
                        # Close previous turn
                        if turn_agent and turn_started is not None:
                            try:
                                duration = max(0.0, time.perf_counter() - turn_started)
                                await perf_mgr.record_agent_turn(
                                    chat_id=chat_id,
                                    agent_name=turn_agent,
                                    duration_sec=duration,
                                    model=None,
                                )
                            except Exception:
                                pass
                        # Start new turn
                        turn_agent = getattr(ev, "sender", None) or getattr(ev, "agent", None)
                        turn_started = time.perf_counter()

                    # Stream / forward events via dispatcher
                    if transport:
                        try:
                            payload = event_to_ui_payload(ev)
                            await transport.send_event_to_ui(payload, chat_id)
                        except Exception:
                            pass

                    # Handle interactive tool calls that require UI interaction
                    if isinstance(ev, (FunctionCallEvent, ToolCallEvent)):
                        try:
                            ui_response = await handle_tool_call_for_ui_interaction(ev, chat_id)
                            if ui_response:
                                # Send the UI response back through the transport for the agent to see
                                if transport:
                                    try:
                                        await transport.send_event_to_ui({
                                            "kind": "tool_ui_response",
                                            "tool_name": getattr(ev, "tool_name", None) or getattr(ev, "function_name", None),
                                            "response": ui_response,
                                            "chat_id": chat_id,
                                        }, chat_id)
                                    except Exception:
                                        pass
                        except Exception as tool_err:
                            wf_logger.debug(f"Tool UI interaction error: {tool_err}")

                    if isinstance(ev, UsageSummaryEvent):
                        usage_seen = True
                        try:
                            await perf_mgr.record_final_usage_from_agents(
                                chat_id=chat_id,
                                enterprise_id=enterprise_id,
                                user_id=user_id or "unknown",
                                agents=list(agents.values())
                            )
                        except Exception:
                            pass

                    if isinstance(ev, ErrorEvent):
                        # Optionally could escalate termination here
                        pass

                    if isinstance(ev, RunCompletionEvent):
                        break
            except Exception as loop_err:
                # Log and proceed to finalization steps below
                wf_logger.error(f"Event loop failure: {loop_err}")

            # Close last turn (even if loop errored)
            if turn_agent and turn_started is not None:
                try:
                    duration = max(0.0, time.perf_counter() - turn_started)
                    await perf_mgr.record_agent_turn(
                        chat_id=chat_id,
                        agent_name=turn_agent,
                        duration_sec=duration,
                        model=None,
                    )
                except Exception:
                    pass

            # Final usage reconciliation if UsageSummaryEvent absent
            try:
                if not usage_seen:
                    final_summary = gather_usage_summary(list(agents.values()))
                    if final_summary:
                        await perf_mgr.record_final_usage_from_agents(
                            chat_id=chat_id,
                            enterprise_id=enterprise_id,
                            user_id=user_id or "unknown",
                            agents=list(agents.values())
                        )
            except InsufficientTokensError:
                await termination_handler.on_conversation_end(termination_reason="insufficient_tokens")
                return
            except Exception:
                pass

            termination_reason = getattr(response, 'termination_reason', None) or "completed"
            max_turns_reached = getattr(response, 'max_turns_reached', False)

            # Ensure termination handler is called to update status
            try:
                termination_result = await termination_handler.on_conversation_end(
                    termination_reason=termination_reason,
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

            result_payload = {
                "workflow_name": workflow_name,
                "chat_id": chat_id,
                "enterprise_id": enterprise_id,
                "user_id": user_id,
                "messages": getattr(response, 'messages', None),
                "termination_reason": termination_reason,
                "max_turns_reached": max_turns_reached,
                "response": response
            }
        except Exception as e:
            logger.error(f"❌ [{workflow_name_upper}] Orchestration failed: {e}", exc_info=True)
            try:
                await termination_handler.on_conversation_end(termination_reason="error")
                logger.info("✅ Termination handler called for error case")
            except Exception as term_err:
                logger.error(f"❌ Termination handler error cleanup failed: {term_err}")
            raise
        finally:
            status = "completed"
            try:
                await perf_mgr.record_workflow_end(chat_id, status)
                await perf_mgr.flush(chat_id)
            except Exception as e:
                logger.debug(f"perf finalize failed: {e}")
            duration_sec = perf_counter() - start_time
            if root_span.is_recording():
                root_span.set_attribute("workflow.duration_sec", duration_sec)
                root_span.set_attribute("agent.count", len(agents))
                root_span.set_attribute("orchestration.pattern", orchestration_pattern)

    # OUTSIDE span: final logging & cleanup
    try:
        duration = perf_counter() - start_time
        logger.info(f"✅ [{workflow_name_upper}] orchestration completed in {duration:.2f}s")
        chat_logger.info(f"[{workflow_name_upper}] WORKFLOW_COMPLETED chat_id={chat_id} duration={duration:.2f}s")
        wf_logger.info(
            "WORKFLOW_COMPLETED",
            event_type=f"{workflow_name_upper}_WORKFLOW_COMPLETED",
            description=f"{workflow_name} workflow orchestration completed",
            enterprise_id=enterprise_id,
            chat_id=chat_id,
            total_duration_seconds=duration,
            agent_count=len(agents),
            pattern_used=orchestration_pattern,
            result_status="completed" if result_payload else "error",
        )
    # (No legacy streaming manager cleanup required)
    finally:
        ...

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
        logger.warning(f"⚠️ Unknown pattern '{pattern_name}', defaulting to DefaultPattern")
        pattern_name = "DefaultPattern"

    pattern_class = pattern_map[pattern_name]

    logger.info(f"🎯 Creating {pattern_name} using AG2's native implementation")
    logger.info(f"🔍 Pattern setup - initial_agent: {initial_agent.name}")
    logger.info(f"🔍 Pattern setup - agents count: {len(agents)}")
    logger.info(f"🔍 Pattern setup - user_agent included: {user_agent is not None and human_in_the_loop}")
    logger.info(f"🔍 Pattern setup - context_variables: {context_variables is not None}")

    pattern_args = {
        "initial_agent": initial_agent,
        "agents": agents,
    }

    if human_in_the_loop and user_agent is not None:
        pattern_args["user_agent"] = user_agent
        logger.info(f"✅ User agent included in pattern (human_in_the_loop=true)")
    else:
        logger.info(f"ℹ️ User agent excluded from pattern (human_in_the_loop={human_in_the_loop})")

    if context_variables is not None:
        pattern_args["context_variables"] = context_variables

    if group_manager_args is not None:
        pattern_args["group_manager_args"] = group_manager_args

    pattern_args.update(pattern_kwargs)

    try:
        pattern = pattern_class(**pattern_args)
        logger.info(f"✅ {pattern_name} AG2 pattern created successfully")
        return pattern
    except Exception as e:
        logger.warning(f"⚠️ Failed to create {pattern_name} with all args, trying minimal: {e}")
        minimal_args = {
            "initial_agent": initial_agent,
            "agents": agents,
        }
        if human_in_the_loop and user_agent is not None:
            minimal_args["user_agent"] = user_agent

        minimal_pattern = pattern_class(**minimal_args)
        logger.info(f"✅ {pattern_name} AG2 pattern created with minimal args")
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
                        transport = SimpleTransport._get_instance()
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
