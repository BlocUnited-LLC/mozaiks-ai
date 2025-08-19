# ==============================================================================
# FILE: core/workflow/orchestration_patterns.py
# DESCRIPTION: COMPLETE AG2 execution engine - CONSOLIDATED from groupchat_manager.py
#              Single-responsibility pattern for all workflow orchestration
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

Notes
- No functional changes in this pass; documentation and inline organization only.
"""

from typing import Dict, List, Optional, Any, Union, Callable
import logging
import time
import asyncio
import threading
import traceback
from datetime import datetime
from opentelemetry import trace  # Lean OpenTelemetry usage for root workflow span

from autogen import ConversableAgent, UserProxyAgent
from autogen.agentchat.group.patterns import (
    DefaultPattern as AG2DefaultPattern,
    AutoPattern as AG2AutoPattern,
    RoundRobinPattern as AG2RoundRobinPattern,
    RandomPattern as AG2RandomPattern,
)

from ..data.persistence_manager import AG2PersistenceManager
from .tool_registry import WorkflowToolRegistry
from .termination_handler import create_termination_handler
from logs.logging_config import (
    get_chat_logger,
    get_workflow_logger,
)
from core.observability.performance_manager import get_performance_manager

logger = logging.getLogger(__name__)

# Consolidated logging (moved from groupchat_manager.py)
chat_logger = get_chat_logger("orchestration")
workflow_logger = get_workflow_logger("orchestration")
performance_logger = get_workflow_logger("performance.orchestration")

# ===================================================================
# AG2 INTERNAL LOGGING CONFIGURATION
# ===================================================================
# Enable AG2's own debug loggers for deep internal visibility
# WARNING: This is very noisy - only enable for debugging
AG2_DEBUG_ENABLED = False  # Set to True for deep AG2 debugging

if AG2_DEBUG_ENABLED:
    logging.getLogger("autogen.agentchat").setLevel(logging.DEBUG)
    logging.getLogger("autogen.io").setLevel(logging.DEBUG)
    logging.getLogger("autogen.agentchat.group").setLevel(logging.DEBUG)
    workflow_logger.warning("🚨 AG2 DEBUG LOGGING ENABLED - Output will be very verbose!")
else:
    # Keep AG2 loggers at INFO level for production
    logging.getLogger("autogen.agentchat").setLevel(logging.INFO)
    logging.getLogger("autogen.io").setLevel(logging.INFO)

# ===================================================================

# ==============================================================================
# SIMPLIFIED RESPONSE TRACKING (Now uses simple_tracking.py)
# ==============================================================================

# Performance-focused logging - minimal overhead (from groupchat_manager.py)
function_call_logger = logging.getLogger("ag2_function_call_debug")
function_call_logger.setLevel(logging.ERROR)  # Only log critical errors

# Keep minimal deep logging for critical debugging when needed (from groupchat_manager.py)
deep_logger = logging.getLogger("ag2_deep_debug")
deep_logger.setLevel(logging.WARNING)  # Only warnings and errors

# Agent lifecycle logging for tool registration (from groupchat_manager.py)
agent_lifecycle_logger = logging.getLogger("ag2_agent_lifecycle")
agent_lifecycle_logger.setLevel(logging.INFO)  # Keep tool registration info

# ==============================================================================
# SINGLE ENTRY POINT - REPLACES groupchat_manager.py ENTIRELY
# ==============================================================================

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
    """
    Run a workflow orchestration with lean OpenTelemetry root span.

    Contract
    - Inputs: workflow_name, enterprise_id, chat_id, user_id?, initial_message?, factories?
    - Output: dict payload with response metadata (messages, termination, etc.)
    - Side effects:
        • Persists chat session/messages and usage via AG2 UIEventProcessor + Persistence
        • Streams tokens/messages to transport and logs to agent_chat/workflows
        • Emits OpenTelemetry spans and performance metrics
    - Error modes: propagates fatal orchestration errors; logs and continues for non-critical paths
    """
    start_time = time.time()
    workflow_name_upper = workflow_name.upper()
    orchestration_pattern = "unknown"
    agents: Dict[str, Any] = {}
    # Context-aware workflow logger for this run
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
    streaming_manager = None

    perf_mgr = await get_performance_manager()
    await perf_mgr.initialize()  # Ensure OpenTelemetry is initialized
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
        # Attach trace to performance manager and DB
        try:
            await perf_mgr.attach_trace_id(chat_id, trace_id_hex)
        except Exception as e:
            logger.debug(f"trace attach failed: {e}")
        try:
            # -----------------------------------------------------------------
            # 1) Load configuration (workflow_config)
            # -----------------------------------------------------------------
            from .workflow_config import workflow_config
            config = workflow_config.get_config(workflow_name)
            max_turns = config.get("max_turns", 50)
            orchestration_pattern = config.get("orchestration_pattern", "AutoPattern")
            startup_mode = config.get("startup_mode", "AgentDriven")
            human_in_loop = config.get("human_in_the_loop", False)
            initial_agent_name = config.get("initial_agent", None)

            # -----------------------------------------------------------------
            # 2) Resume or start chat (PersistenceManager.resume_chat / termination handler)
            # -----------------------------------------------------------------
            resumed_messages = await persistence_manager.resume_chat(chat_id, enterprise_id)
            if resumed_messages and len(resumed_messages) > 0:
                logger.info(f"🔄 Resuming chat {chat_id} with {len(resumed_messages)} messages.")
                initial_messages = resumed_messages
                if initial_message:
                    initial_messages.append({"role": "user", "content": initial_message})
            else:
                logger.info(f"🚀 Starting new chat session for {chat_id}")
                initial_messages = [{"role": "user", "content": initial_message}] if initial_message else []
                current_user_id = user_id or "system_user"
                if not user_id:
                    logger.warning(f"Starting chat {chat_id} without a specific user_id. Defaulting to 'system_user'.")
                await termination_handler.on_conversation_start(user_id=current_user_id)
                # trace_id persistence is handled by PerformanceManager.attach_trace_id

            # If no initial messages yet, seed from workflow config's initial_message
            if not initial_messages:
                seed = config.get("initial_message") or config.get("initial_message_to_user")
                if seed:
                    initial_messages = [{"role": "user", "content": seed}]

            # -----------------------------------------------------------------
            # 3) LLM config (workflow-specific or default)
            # -----------------------------------------------------------------
            from .structured_outputs import get_llm_for_workflow
            try:
                _, llm_config = await get_llm_for_workflow(workflow_name, "base")
                wf_logger.info(f"✅ [{workflow_name_upper}] Using workflow-specific LLM config")
            except (ValueError, FileNotFoundError):
                from core.core_config import make_llm_config
                _, llm_config = await make_llm_config()
                wf_logger.info(f"✅ [{workflow_name_upper}] Using default LLM config")

            # Log start to chat and workflow logs
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
            # 4) Context build / variables (retain performance metric logging)
            # -----------------------------------------------------------------
            context = None
            context_start = time.time()
            if context_factory:
                context = context_factory()
            else:
                try:
                    from .context_variables import get_context
                    context = get_context(workflow_name, enterprise_id)
                except Exception as e:
                    wf_logger.error(f"❌ [{workflow_name_upper}] Context load failed: {e}")
            context_time = (time.time() - context_start) * 1000
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
            # 5) Streaming setup (AG2StreamingManager on SimpleTransport connection)
            # -----------------------------------------------------------------
            if transport and hasattr(transport, 'connections') and chat_id in transport.connections:
                connection = transport.connections[chat_id]
                streaming_manager = connection.get('ag2_streaming_manager')
            if not streaming_manager:
                from ..transport.ag2_iostream import AG2StreamingManager
                streaming_manager = AG2StreamingManager(
                    chat_id=chat_id,
                    enterprise_id=enterprise_id,
                    user_id=user_id or "unknown",
                    workflow_name=workflow_name
                )
                streaming_manager.setup_streaming()

            # -----------------------------------------------------------------
            # 6) Agents definition (define + tool registry)
            # -----------------------------------------------------------------
            if agents_factory:
                agents = await agents_factory()
            else:
                from .agents import define_agents
                agents = await define_agents(workflow_name)
            agents = agents or {}

            # Register tools on agents via modular registry (includes UI tool surfacing)
            try:
                registry = WorkflowToolRegistry(workflow_name)
                registry.load_configuration()
                registry.register_agent_tools(list(agents.values()))
                wf_logger.info(f"🔧 [{workflow_name_upper}] Registered tools for {len(agents)} agents")
            except Exception as reg_err:
                wf_logger.warning(f"⚠️ [{workflow_name_upper}] Tool registration skipped/failed: {reg_err}")

            # Store agents on transport connection for real-time token tracking (used by PerformanceManager)
            try:
                if transport and hasattr(transport, 'connections') and chat_id in transport.connections:
                    transport.connections[chat_id]['agents'] = agents
            except Exception as _agents_store_err:
                wf_logger.debug(f"agent store failed: {_agents_store_err}")

            # User proxy agent
            user_proxy_agent = None
            user_proxy_exists = any(a.name.lower() in ["user", "userproxy", "userproxyagent"] for a in agents.values() if hasattr(a, 'name'))
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
                    if a.name.lower() in ["user", "userproxy", "userproxyagent"]:
                        user_proxy_agent = a
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
            # 8) Pattern creation (AG2 pattern factory)
            # -----------------------------------------------------------------
            agents_list = [a for n,a in agents.items() if not (n == 'user' and human_in_loop and user_proxy_agent is not None)]
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
            # 9) Handoffs (only DefaultPattern)
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
            # 10) Execute group chat (a_run_group_chat) with timeout
            # -----------------------------------------------------------------
            from autogen.agentchat import a_run_group_chat
            try:
                response = await asyncio.wait_for(
                    a_run_group_chat(
                        pattern=pattern,
                        messages=initial_messages,
                        max_rounds=max_turns
                    ),
                    timeout=300.0
                )
            except asyncio.TimeoutError:
                raise Exception("AG2 workflow execution timed out (300s)")

            # Process response events directly (preferred): iterate response.events
            from core.transport.ui_event_processor import UIEventProcessor
            ui_processor = UIEventProcessor(
                chat_id=chat_id,
                enterprise_id=enterprise_id,
                user_id=user_id or "unknown",
                workflow_name=workflow_name
            )
            event_count = 0
            usage_events_seen = False
            try:
                async for ev in response.events:
                    event_count += 1
                    await ui_processor.process_event(ev)
                    # Mark that UsageSummaryEvent-based accounting was seen
                    try:
                        from autogen.events.client_events import UsageSummaryEvent as _UsageSummaryEvent
                        if isinstance(ev, _UsageSummaryEvent):
                            usage_events_seen = True
                    except Exception:
                        pass
                wf_logger.info(f"✅ [{workflow_name_upper}] Processed {event_count} AG2 events")
            except Exception as pe:
                wf_logger.error(f"❌ [{workflow_name_upper}] Iterating response.events failed: {pe}")

            # -----------------------------------------------------------------
            # 11) Accounting: enforce UsageSummaryEvent as source of truth (no fallbacks)
            # -----------------------------------------------------------------
            if not usage_events_seen:
                wf_logger.error(
                    f"❌ [{workflow_name_upper}] No UsageSummaryEvent observed. Event-driven accounting did not run."
                )


            termination_reason = getattr(response, 'termination_reason', None) or "completed"
            max_turns_reached = getattr(response, 'max_turns_reached', False)
            await termination_handler.on_conversation_end(
                termination_reason=termination_reason,
                max_turns_reached=max_turns_reached
            )
            # Safely extract messages from response (may be coroutine in some AG2 builds)
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
            except Exception:
                pass
            raise
        finally:
            # End-of-workflow bookkeeping
            status = "completed"
            try:
                await perf_mgr.record_workflow_end(chat_id, status)
                await perf_mgr.flush(chat_id)
            except Exception as e:
                logger.debug(f"perf finalize failed: {e}")
            # Attach duration to root span
            duration_sec = time.time() - start_time
            if root_span.is_recording():
                root_span.set_attribute("workflow.duration_sec", duration_sec)
                root_span.set_attribute("agent.count", len(agents))
                root_span.set_attribute("orchestration.pattern", orchestration_pattern)

    # OUTSIDE span: final logging & cleanup
    try:
        duration = time.time() - start_time
        logger.info(f"✅ [{workflow_name_upper}] orchestration completed in {duration:.2f}s")
        # Log completion to chat and workflow logs
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
        # Streaming cleanup
        if streaming_manager is not None:
            try:
                streaming_manager.cleanup()
            except Exception:
                pass
    finally:
        pass

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
) -> Any:  # Returns AG2's native pattern
    """
    Factory function to create AG2's native orchestration patterns.
    ALIGNED TO SPECIFICATION FORMAT:
    
    pattern = {orchestration_pattern}(
        initial_agent={initial_agent},
        agents=[ {agents}  ],
        user_agent=user, #only shows if human_in_the_loop = true 
        context_variables={context_variables},
        group_manager_args = {"llm_config": {default_llm_config}},
    )
    
    Args:
        pattern_name: Name of the pattern ("AutoPattern", "DefaultPattern", etc.)
        initial_agent: Agent that starts the conversation (from orchestrator.yaml)
        agents: List of all agents in the conversation
        user_agent: Optional user proxy agent (only if human_in_the_loop = true)
        context_variables: Shared context for the conversation
        group_manager_args: Arguments for GroupChatManager (e.g., llm_config)
        human_in_the_loop: Whether to include user_agent in pattern
        **pattern_kwargs: Additional pattern-specific arguments
    
    Returns:
        AG2's native pattern instance
    """
    
    # Use AG2's native pattern implementations directly
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
    
    # Build arguments exactly as specified
    pattern_args = {
        "initial_agent": initial_agent,
        "agents": agents,
    }
    
    # Only add user_agent if human_in_the_loop = true 
    if human_in_the_loop and user_agent is not None:
        pattern_args["user_agent"] = user_agent
        logger.info(f"✅ User agent included in pattern (human_in_the_loop=true)")
    else:
        logger.info(f"ℹ️ User agent excluded from pattern (human_in_the_loop={human_in_the_loop})")
    
    # Add context_variables if provided
    if context_variables is not None:
        pattern_args["context_variables"] = context_variables
        
    # Add group_manager_args if provided
    if group_manager_args is not None:
        pattern_args["group_manager_args"] = group_manager_args
    
    # Add any additional pattern-specific kwargs
    pattern_args.update(pattern_kwargs)
    
    try:
        pattern = pattern_class(**pattern_args)
        logger.info(f"✅ {pattern_name} AG2 pattern created successfully")
        return pattern
    except Exception as e:
        logger.warning(f"⚠️ Failed to create {pattern_name} with all args, trying minimal: {e}")
        # Fallback to minimal arguments
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
# YAML INTEGRATION - NOW HANDLED BY PRODUCTION CONFIG SYSTEM
# ==============================================================================
# NOTE: All workflow component loading is now handled by the optimized production
# config system in workflow_config.py - no duplicate functions needed

# ==============================================================================
# LOGGING HELPERS
# ==============================================================================

def log_agent_message_details(message, sender_name, recipient_name):
    """Logs agent message details for tracking."""
    message_content = getattr(message, 'content', None) or str(message)
    
    if message_content and sender_name != 'unknown':
        # Log a summary for readability
        summary = message_content[:150] + '...' if len(message_content) > 150 else message_content
        chat_logger.info(f"🤖 [AGENT] {sender_name} → {recipient_name}: {summary}")
        
        # Log full content at debug level for complete tracking
        chat_logger.debug(f"📋 [FULL] {sender_name} complete message:\n{'-'*50}\n{message_content}\n{'-'*50}")
        
        # Log message metadata
        chat_logger.debug(f"📊 [META] Length: {len(message_content)} chars | Type: {type(message).__name__}")
        
        # NOTE: UI routing is now handled by individual tools
        # Tools emit UI events directly via emit_ui_tool_event() when needed
        
    return message


async def log_conversation_to_agent_chat_file(conversation_history, chat_id: str, enterprise_id: str, workflow_name: str):
    """
    Log the complete AG2 conversation to the agent chat log file.
    
    This function processes the conversation_history from result.messages after result.process()
    and writes all agent messages to logs/logs/agent_chat.log for debugging and UI display.
    
    Args:
        conversation_history: List of messages from AG2's ChatResult.messages
        chat_id: Chat identifier for tracking
        enterprise_id: Enterprise identifier
        workflow_name: Name of the workflow for context
    """
    try:
        # Get the agent chat logger (specifically for agent conversations)
        agent_chat_logger = get_chat_logger("agent_messages")
        
        if not conversation_history:
            agent_chat_logger.info(f"🔍 [{workflow_name}] No conversation history to log for chat {chat_id}")
            return
        
        msg_count = len(conversation_history) if hasattr(conversation_history, '__len__') else 0
        agent_chat_logger.info(f"📝 [{workflow_name}] Logging {msg_count} messages to agent chat file for chat {chat_id}")
        
        # Process each message in the conversation
        for i, message in enumerate(conversation_history):
            try:
                # Extract message details from AG2 message format
                sender_name = "Unknown"
                content = ""
                
                # Handle different AG2 message formats (check for dict first to avoid attribute errors)
                if isinstance(message, dict):
                    # Handle dictionary format first
                    if 'name' in message and message['name']:
                        sender_name = message['name']
                    elif 'sender' in message and message['sender']:
                        sender_name = message['sender']
                    elif 'from' in message and message['from']:
                        sender_name = message['from']
                    
                    # Extract content from dictionary
                    if 'content' in message and message['content']:
                        content = message['content']
                    elif 'message' in message and message['message']:
                        content = message['message']
                    elif 'text' in message and message['text']:
                        content = message['text']
                elif isinstance(message, str):
                    content = message
                elif hasattr(message, 'name') and hasattr(message, 'content'):
                    # Handle object format (AG2 message objects)
                    sender_name = getattr(message, 'name', 'Unknown')
                    content = getattr(message, 'content', '')
                elif hasattr(message, 'sender') and hasattr(message, 'message'):
                    # Alternative object format
                    sender_name = getattr(message, 'sender', 'Unknown')
                    content = getattr(message, 'message', '')
                else:
                    # Fallback for any other format
                    content = str(message)
                
                # Clean up content for logging
                clean_content = content.strip() if content else ""
                
                if clean_content:
                    # Log to agent chat file with proper format
                    agent_chat_logger.info(f"AGENT_MESSAGE | Chat: {chat_id} | Enterprise: {enterprise_id} | Agent: {sender_name} | Message #{i+1}: {clean_content}")
                    
                    # Also send to UI via SimpleTransport if available
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
                        # Don't fail logging if UI sending fails
                        logger.debug(f"UI forwarding failed for message {i+1}: {ui_error}")
                        
                else:
                    agent_chat_logger.debug(f"EMPTY_MESSAGE | Chat: {chat_id} | Agent: {sender_name} | Message #{i+1}: (empty)")
                    
            except Exception as msg_error:
                agent_chat_logger.error(f"❌ Failed to log message {i+1} in chat {chat_id}: {msg_error}")
        
        agent_chat_logger.info(f"✅ [{workflow_name}] Successfully logged {msg_count} messages for chat {chat_id}")
        
    except Exception as e:
        logger.error(f"❌ Failed to log conversation to agent chat file for {chat_id}: {e}")
        # Don't raise - logging failure shouldn't break the workflow

# ==============================================================================
# END CONSOLIDATED ORCHESTRATION PATTERNS
# ==============================================================================
