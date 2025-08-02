# ==============================================================================
# FILE: core/workflow/orchestration_patterns.py
# DESCRIPTION: COMPLETE AG2 execution engine - CONSOLIDATED from groupchat_manager.py
#              Single-responsibility pattern for all workflow orchestration
# ==============================================================================

from typing import Dict, List, Optional, Any, Union, Callable
import logging
import time
import asyncio
import threading
from datetime import datetime

from autogen import ConversableAgent, UserProxyAgent
from autogen.agentchat import run_group_chat, a_run_group_chat
from autogen.agentchat.group.patterns import (
    DefaultPattern as AG2DefaultPattern,
    AutoPattern as AG2AutoPattern,
    RoundRobinPattern as AG2RoundRobinPattern,
    RandomPattern as AG2RandomPattern,
)

from ..data.persistence_manager import PersistenceManager
from ..data.token_manager import get_token_tracker
from .tool_registry import WorkflowToolRegistry
from .termination_handler import create_termination_handler
from logs.logging_config import (
    get_chat_logger,
    log_business_event,
    log_performance_metric,
    get_agent_logger,
    get_workflow_logger,
    get_business_logger
)

logger = logging.getLogger(__name__)

# Initialize persistence manager (moved from groupchat_manager.py)
mongodb_manager = PersistenceManager()

# Consolidated logging (moved from groupchat_manager.py)
chat_logger = get_chat_logger("orchestration_patterns")
agent_logger = get_agent_logger("orchestration_patterns")
workflow_logger = get_workflow_logger("orchestration_patterns")

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
    business_logger = get_business_logger("ag2_debug")
    business_logger.warning("🚨 AG2 DEBUG LOGGING ENABLED - Output will be very verbose!")
else:
    # Keep AG2 loggers at INFO level for production
    logging.getLogger("autogen.agentchat").setLevel(logging.INFO)
    logging.getLogger("autogen.io").setLevel(logging.INFO)

# ===================================================================

# ==============================================================================
# SIMPLIFIED RESPONSE TRACKING (Analytics moved to token_manager.py)
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
    COMPLETE REPLACEMENT for groupchat_manager.py run_workflow_orchestration().
    
    This is the ONLY function you need to call to run any MozaiksAI workflow.
    It handles ALL setup, execution, and cleanup that groupchat_manager.py used to do.
    
    Args:
        workflow_name: Type of workflow (e.g., "generator", "analyzer")
        enterprise_id: Enterprise identifier
        chat_id: Chat identifier
        user_id: User identifier (optional)
        initial_message: Initial message (optional)
        agents_factory: Function to create agents (optional - will use YAML if None)
        context_factory: Function to get context (optional - will use YAML if None)
        handoffs_factory: Function to wire handoffs (optional - will use YAML if None)
        **kwargs: Additional arguments
    
    Returns:
        Same format as groupchat_manager.py for compatibility
    """
    start_time = time.time()
    workflow_name_upper = workflow_name.upper()
    orchestration_pattern = "unknown"  # Initialize early to avoid unbound variable
    
    logger.info(f"🚀 CONSOLIDATED workflow orchestration: {workflow_name}")
    business_logger = get_business_logger(f"{workflow_name}_orchestration")
    
    # Check transport availability (from groupchat_manager.py)
    from core.transport.simple_transport import SimpleTransport
    transport = SimpleTransport._get_instance()
    if not transport:
        raise RuntimeError(f"SimpleTransport instance not available for {workflow_name} workflow")
    
    try:
        # Load YAML configuration
        from .workflow_config import workflow_config
        config = workflow_config.get_config(workflow_name)
        max_turns = config.get("max_turns", 50)
        orchestration_pattern = config.get("orchestration_pattern", "AutoPattern")
        startup_mode = config.get("startup_mode", "AgentDriven")
        human_in_loop = config.get("human_in_the_loop", False)
        
        # Get initial agent from orchestrator.yaml - this is simply the agent that gets the first turn
        # regardless of startup_mode. The initial_message is sent to the group chat context,
        # and the initial_agent gets the first opportunity to respond.
        initial_agent = config.get("initial_agent", "ContextAgent")
        
        # ===================================================================
        # 2. LOAD LLM CONFIGURATION FOR THIS WORKFLOW (using existing system)
        # ===================================================================
        from .structured_outputs import get_llm_for_workflow
        try:
            # Try to get workflow-specific LLM config first
            _, llm_config = await get_llm_for_workflow(workflow_name, "base")
            business_logger.info(f"✅ [{workflow_name.upper()}] Using workflow-specific LLM config")
        except (ValueError, FileNotFoundError):
            # Fallback to core config if workflow doesn't have specific config
            from core.core_config import make_llm_config
            _, llm_config = await make_llm_config()
            business_logger.info(f"✅ [{workflow_name.upper()}] Using default LLM config")
        
        business_logger.info(f"🚀 [{workflow_name_upper}] Starting AG2 orchestration: {max_turns} turns, {orchestration_pattern}, {startup_mode}")

        # Determine final initial message
        final_initial_message_text = (
            config.get("initial_message") or 
            initial_message or
            f"Hello! Let's start the {workflow_name} workflow."
        )
        
        # AG2 expects messages as a list of message objects
        final_initial_message = [{"role": "user", "content": final_initial_message_text}]
        
        log_business_event(
            event_type=f"{workflow_name_upper}_WORKFLOW_STARTED",
            description=f"{workflow_name} workflow orchestration initialized using consolidated patterns",
            context={
                "enterprise_id": enterprise_id,
                "chat_id": chat_id,
                "user_id": user_id,
                "pattern": orchestration_pattern,
                "startup_mode": startup_mode,
                "final_message_preview": final_initial_message_text[:100] + "..." if len(final_initial_message_text) > 100 else final_initial_message_text
            }
        )

        # ===================================================================
        # 3. RESUME LOGIC - Check if workflow can be resumed (VE-style)
        # ===================================================================
        can_resume = await mongodb_manager.can_resume_chat(chat_id, enterprise_id, workflow_name)
        
        if can_resume:
            business_logger.info(f"🔄 [{workflow_name_upper}] Resumable session found for {chat_id}")
            
            success, resume_data = await mongodb_manager.resume_chat(chat_id, enterprise_id, workflow_name)
            
            if success and resume_data:
                # Check if already complete (VE pattern)
                if resume_data.get("already_complete"):
                    status = resume_data.get("status", 0)
                    business_logger.info(f"✅ [{workflow_name_upper}] Workflow already completed with status {status}")
                    
                    # Send completion message to WebSocket if available
                    await transport.send_simple_text_message(
                        f"{workflow_name.title()} workflow already completed successfully.",
                        chat_id=chat_id,
                        agent_name="system"
                    )
                    return {"status": "already_completed", "message": f"{workflow_name} workflow already completed"}
                
                # Resume active conversation (VE pattern)
                conversation_data = resume_data.get("conversation", [])
                status = resume_data.get("status", 0)
                business_logger.info(f"🔄 [{workflow_name_upper}] Resuming conversation with {len(conversation_data)} messages, status {status}")
            else:
                business_logger.warning(f"❌ [{workflow_name_upper}] Resume failed - starting new session")
        
        # Initialize workflow with status 0 (VE pattern) - for new sessions or failed resumes
        await mongodb_manager.update_workflow_status(chat_id, enterprise_id, 0, workflow_name)
        business_logger.info(f"🆕 [{workflow_name_upper}] Starting new session (status=0)")

        # ===================================================================
        # 4. BUILD CONTEXT (if context factory provided, or use context variables)
        # ===================================================================
        context = None
        if context_factory:
            context_start = time.time()
            business_logger.debug(f"🔄 [{workflow_name_upper}] Building context...")
            context = context_factory()
            context_time = (time.time() - context_start) * 1000
            log_performance_metric(
                metric_name="context_build_duration",
                value=context_time,
                unit="ms",
                context={"enterprise_id": enterprise_id}
            )
            business_logger.info(f"✅ [{workflow_name_upper}] Context built successfully")
        else:
            # DEFAULT: Load context variables from YAML configuration
            context_start = time.time()
            business_logger.debug(f"🔄 [{workflow_name_upper}] Loading context variables from YAML...")
            
            try:
                from .context_variables import get_context
                context = get_context(workflow_name, enterprise_id)  # Updated function signature
                context_time = (time.time() - context_start) * 1000
                
                log_performance_metric(
                    metric_name="context_variables_load_duration",
                    value=context_time,
                    unit="ms",
                    context={"enterprise_id": enterprise_id, "workflow_name": workflow_name}
                )
                
                # Log context variables loaded
                if context:
                    var_count = len(context.data) if hasattr(context, 'data') else 0
                    business_logger.info(f"✅ [{workflow_name_upper}] Context variables loaded: {var_count} variables")
                    
                    # Debug log the actual variables
                    try:
                        if hasattr(context, 'data'):
                            for var_name, var_value in context.data.items():
                                if isinstance(var_value, str) and len(var_value) > 100:
                                    preview = f"{var_value[:100]}..."
                                else:
                                    preview = str(var_value)
                                business_logger.debug(f"🔧 [{workflow_name_upper}] Context variable '{var_name}': {preview}")
                    except Exception as e:
                        business_logger.warning(f"⚠️ [{workflow_name_upper}] Could not inspect context variables: {e}")
                        
                else:
                    business_logger.warning(f"⚠️ [{workflow_name_upper}] No context variables loaded")
                    
            except Exception as e:
                business_logger.error(f"❌ [{workflow_name_upper}] Failed to load context variables: {e}")
                business_logger.info(f"✅ [{workflow_name_upper}] Context variables system is the primary data source")

        # ===================================================================
        # 6. SET UP AG2 STREAMING WITH CUSTOM IOSTREAM
        # ===================================================================
        streaming_start = time.time()
        business_logger.info(f"🔄 [{workflow_name_upper}] Setting up AG2 streaming...")
        
        # Get the existing streaming manager from transport connection if available
        streaming_manager = None
        if transport and hasattr(transport, 'connections') and chat_id in transport.connections:
            connection = transport.connections[chat_id]
            streaming_manager = connection.get('ag2_streaming_manager')
            
        # If no existing streaming manager, create a new one (fallback)
        if not streaming_manager:
            business_logger.info(f"📝 [{workflow_name_upper}] Creating new AG2 streaming manager...")
            from ..transport.ag2_iostream import AG2StreamingManager
            streaming_manager = AG2StreamingManager(
                chat_id=chat_id,
                enterprise_id=enterprise_id,
                user_id=user_id or "unknown",
                workflow_name=workflow_name
            )
            # Set up the custom IOStream globally for AG2
            streaming_manager.setup_streaming()
        else:
            business_logger.info(f"♻️ [{workflow_name_upper}] Using existing AG2 streaming manager from transport")
        
        business_logger.info(f"✅ [{workflow_name_upper}] AG2 streaming handled by IOStream system")
        
        streaming_setup_time = (time.time() - streaming_start) * 1000
        log_performance_metric(
            metric_name="ag2_streaming_setup_duration",
            value=streaming_setup_time,
            unit="ms",
            context={"enterprise_id": enterprise_id, "chat_id": chat_id}
        )

        # Define agents
        agents_start = time.time()
        
        if agents_factory:
            agents = await agents_factory()
        else:
            from .agents import define_agents
            agents = await define_agents(workflow_name)
        
        agents_build_time = (time.time() - agents_start) * 1000
        log_performance_metric(
            metric_name="agents_definition_duration", 
            value=agents_build_time,
            unit="ms",
            context={"enterprise_id": enterprise_id, "agent_count": len(agents)}
        )
        business_logger.info(f"✅ [{workflow_name_upper}] Agents defined: {len(agents)} total")

        # Register tools
        tools_start = time.time()
        business_logger.info("🔧 Registering tools using modular tool registry...")
        
        tool_registry = WorkflowToolRegistry(workflow_name)
        tool_registry.load_configuration()
        tool_registry.register_agent_tools(list(agents.values()))
        
        tools_registration_time = (time.time() - tools_start) * 1000
        log_performance_metric(
            metric_name="modular_tools_registration_duration",
            value=tools_registration_time,
            unit="ms",
            context={"workflow_name": workflow_name}
        )
        business_logger.info(f"✅ [{workflow_name_upper}] Modular tool registration completed")

        # Create UserProxyAgent with proper startup_mode configuration
        user_proxy_agent = None
        user_proxy_exists = any(agent.name.lower() in ["user", "userproxy", "userproxyagent"] for agent in agents.values() if hasattr(agent, 'name'))
        
        if not user_proxy_exists:
            human_in_loop = config.get("human_in_the_loop", False)
            
            if startup_mode == "BackendOnly":
                human_input_mode = "NEVER"
                business_logger.info(f"🤖 [{workflow_name_upper}] BackendOnly mode: No user interface, pure backend processing")
            elif startup_mode == "UserDriven":
                human_input_mode = "ALWAYS"  # User drives the conversation
                business_logger.info(f"👤 [{workflow_name_upper}] UserDriven mode: User initiates, interface enabled")
            elif startup_mode == "AgentDriven":
                human_input_mode = "ALWAYS"  # Agent starts, but human can interact
                business_logger.info(f"🤖 [{workflow_name_upper}] AgentDriven mode: Agent initiates, interface enabled")
            else:
                human_input_mode = "ALWAYS"  # Safe fallback - allow human interaction
                business_logger.warning(f"⚠️ [{workflow_name_upper}] Unknown startup_mode '{startup_mode}', using fallback")
            
            # Create UserProxyAgent with existing llm_config system
            user_proxy_agent = UserProxyAgent(
                name="user",
                human_input_mode=human_input_mode,
                max_consecutive_auto_reply=0,
                code_execution_config={"use_docker": False},  # Explicitly disable Docker
                system_message="You are a helpful user proxy that facilitates communication between the user and the agents.",
                llm_config=llm_config  # Use existing llm_config dict
            )
            
            # Add to agents dict for easy access
            agents["user"] = user_proxy_agent
            business_logger.info(f"✅ [{workflow_name_upper}] UserProxyAgent created with startup_mode: {startup_mode}, human_input_mode: {human_input_mode}")
        else:
            # Find existing user proxy
            for agent in agents.values():
                if hasattr(agent, 'name') and agent.name.lower() in ["user", "userproxy", "userproxyagent"]:
                    user_proxy_agent = agent
                    business_logger.info(f"✅ [{workflow_name_upper}] Using existing UserProxyAgent with startup_mode: {startup_mode}")
                    break

        # ===================================================================
        # 10. GET INITIATING AGENT
        # ===================================================================
        initiating_agent = agents.get(initial_agent)
        if not initiating_agent:
            # Fallback: try to find the agent by checking if any agent's name matches
            for agent_name, agent in agents.items():
                if hasattr(agent, 'name') and agent.name == initial_agent:
                    initiating_agent = agent
                    break
            
            if not initiating_agent:
                # Final fallback to the first available agent
                initiating_agent = next(iter(agents.values())) if agents else None
                if not initiating_agent:
                    raise ValueError(f"No agents available and initiating agent '{initial_agent}' not found")
                business_logger.warning(f"⚠️ [{workflow_name_upper}] Initiating agent '{initial_agent}' not found, using first available agent: {getattr(initiating_agent, 'name', 'unknown')}")
        else:
            business_logger.info(f"✅ [{workflow_name_upper}] Initiating agent: {getattr(initiating_agent, 'name', initial_agent)}")

        # ===================================================================
        # 11. CREATE AG2-STYLE ORCHESTRATION PATTERN (ALIGNED TO SPECS)
        # ===================================================================
        # PATTERN SETUP FORMAT AS SPECIFIED:
        # pattern = {orchestration_pattern}(
        #     initial_agent={initial_agent},
        #     agents=[ {agents}  ],
        #     user_agent=user, #only shows if human_in_the_loop = true 
        #     context_variables={context_variables},
        #     group_manager_args = {"llm_config": {default_llm_config}},
        # )
        # ===================================================================
        pattern_start = time.time()
        business_logger.info(f"🎯 [{workflow_name_upper}] Creating {orchestration_pattern}...")
        
        # Prepare agents list - exclude user agent if it will be passed separately
        agents_list = []
        for agent_name, agent in agents.items():
            # Skip user agent if we'll pass it separately to avoid duplication
            if agent_name == 'user' and human_in_loop and user_proxy_agent is not None:
                business_logger.debug(f"🔍 [{workflow_name_upper}] Excluding 'user' from agents list (will be passed as user_agent)")
                continue
            agents_list.append(agent)
        
        business_logger.debug(f"🔍 [{workflow_name_upper}] Agent setup: {len(agents_list)} agents + user_agent: {user_proxy_agent.name if user_proxy_agent and human_in_loop else 'None'}")
        
        pattern = create_orchestration_pattern(
            pattern_name=orchestration_pattern,
            initial_agent=initiating_agent,
            agents=agents_list,  # Use filtered list to avoid duplication
            user_agent=user_proxy_agent,
            context_variables=context,
            human_in_the_loop=human_in_loop,  # Pass from orchestrator.yaml
            group_manager_args={
                "llm_config": llm_config  # Only llm_config in group_manager_args
            }
        )
        
        pattern_time = (time.time() - pattern_start) * 1000
        log_performance_metric(
            metric_name="orchestration_pattern_creation_duration",
            value=pattern_time,
            unit="ms",
            context={"enterprise_id": enterprise_id, "pattern": orchestration_pattern, "startup_mode": startup_mode}
        )
        business_logger.info(f"✅ [{workflow_name_upper}] {orchestration_pattern} created successfully")

        # ===================================================================
        # AG2 PATTERN DEBUGGING - Verify pattern configuration at AG2 level
        # ===================================================================
        try:
            business_logger.info(f"🔍 [{workflow_name_upper}] AG2 Pattern Debug - Inspecting pattern configuration...")
            
            # Basic pattern info
            pattern_type = type(pattern).__name__
            business_logger.info(f"   🎯 Pattern type: {pattern_type}")
            
            # Check pattern attributes
            pattern_attrs = [attr for attr in dir(pattern) if not attr.startswith('_')]
            business_logger.info(f"   📋 Pattern attributes: {pattern_attrs[:10]}...")  # Show first 10 to avoid clutter
            
            # Verify agents in pattern
            if hasattr(pattern, 'agents') and pattern.agents:
                pattern_agent_names = []
                for agent in pattern.agents:
                    name = getattr(agent, 'name', 'unnamed')
                    pattern_agent_names.append(name)
                business_logger.info(f"   🤖 Pattern agents ({len(pattern.agents)}): {pattern_agent_names}")
            else:
                business_logger.warning(f"   ⚠️ Pattern has no 'agents' attribute or empty agents list")
            
            # Check initial speaker/agent
            if hasattr(pattern, 'initial_speaker') and pattern.initial_speaker:
                initial_name = getattr(pattern.initial_speaker, 'name', 'unnamed')
                business_logger.info(f"   🎬 Initial speaker: {initial_name}")
            elif hasattr(pattern, 'initial_agent') and pattern.initial_agent:
                initial_name = getattr(pattern.initial_agent, 'name', 'unnamed')
                business_logger.info(f"   🎬 Initial agent: {initial_name}")
            else:
                business_logger.warning(f"   ⚠️ Pattern has no initial speaker/agent configured")
            
            # Check user agent if applicable
            if hasattr(pattern, 'user_agent') and pattern.user_agent:
                user_name = getattr(pattern.user_agent, 'name', 'unnamed')
                business_logger.info(f"   👤 User agent: {user_name}")
            elif human_in_loop:
                business_logger.warning(f"   ⚠️ Human-in-loop enabled but pattern has no user_agent")
            
            # Check group manager if available
            if hasattr(pattern, 'group_manager') and pattern.group_manager:
                group_mgr_type = type(pattern.group_manager).__name__
                business_logger.info(f"   🏢 Group manager: {group_mgr_type}")
                
                # Check group manager config if available
                if hasattr(pattern.group_manager, 'llm_config'):
                    business_logger.info(f"   🧠 Group manager has LLM config: {pattern.group_manager.llm_config is not None}")
            
            # Check for any selection policy
            if hasattr(pattern, 'selection_policy'):
                policy_type = type(pattern.selection_policy).__name__ if pattern.selection_policy else 'None'
                business_logger.info(f"   🎯 Selection policy: {policy_type}")
            
            # Pattern readiness check
            readiness_issues = []
            if not hasattr(pattern, 'agents') or not pattern.agents:
                readiness_issues.append("No agents configured")
            if human_in_loop and (not hasattr(pattern, 'user_agent') or not pattern.user_agent):
                readiness_issues.append("Human-in-loop enabled but no user agent")
            if not hasattr(pattern, 'initial_speaker') and not hasattr(pattern, 'initial_agent'):
                readiness_issues.append("No initial speaker/agent configured")
            
            if readiness_issues:
                business_logger.error(f"   🚨 Pattern readiness issues: {readiness_issues}")
                business_logger.error(f"   🚨 These issues may cause AG2 to fail or terminate immediately!")
            else:
                business_logger.info(f"   ✅ Pattern appears ready for AG2 execution")
            
        except Exception as e:
            business_logger.error(f"❌ [{workflow_name_upper}] AG2 pattern debugging failed: {e}")

        # ===================================================================
        # AG2 HANDOFF INTROSPECTION - Verify what each agent holds BEFORE wiring
        # ===================================================================
        try:
            business_logger.info(f"🔍 [{workflow_name_upper}] AG2 Handoff Introspection - BEFORE wiring...")
            
            all_agents_to_check = list(pattern.agents)
            if hasattr(pattern, 'user_agent') and pattern.user_agent:
                all_agents_to_check.append(pattern.user_agent)

            for ag in all_agents_to_check:
                if not hasattr(ag, "handoffs"):
                    business_logger.warning(f"⚠️ [{workflow_name_upper}] {ag.name} lacks .handoffs attribute")
                    continue

                h = ag.handoffs
                # Corrected attributes for AG2 v0.9.7+
                after_works_count = len(getattr(h, "after_works", []))
                llm_conds_count = len(getattr(h, "llm_conditions", []))
                ctx_conds_count = len(getattr(h, "context_conditions", []))

                business_logger.info(
                    f"🔍 [{workflow_name_upper}] {ag.name} HANDOFF SUMMARY (BEFORE) → "
                    f"after_work: {after_works_count}, "
                    f"LLM_conditions: {llm_conds_count}, "
                    f"context_conditions: {ctx_conds_count}"
                )
                
        except Exception as e:
            business_logger.error(f"❌ [{workflow_name_upper}] AG2 handoff introspection (BEFORE) failed: {e}")

        # ===================================================================
        # 12. WIRE HANDOFFS (using explicit AG2 handoff conditions)
        # ===================================================================
        handoff_success = False
        handoff_details = {"attempted": False, "configured_agents": 0, "failed": False, "error": None}
        
        if orchestration_pattern == "DefaultPattern":
            business_logger.info(f"🔗 [{workflow_name_upper}] Setting up explicit handoff conditions...")
            handoff_details["attempted"] = True
            
            try:
                # Apply explicit handoffs using AG2's handoff system
                # Example from specification:
                # agent.handoffs.add_llm_conditions([
                #     OnCondition(
                #         target=AgentTarget(target_agent),
                #         condition=StringLLMCondition(prompt="When condition is met."),
                #     )
                # ])
                
                if handoffs_factory:
                    handoffs_start = time.time()
                    business_logger.info(f"🔗 [{workflow_name_upper}] Applying custom handoffs...")
                    await handoffs_factory(agents)
                    handoffs_time = (time.time() - handoffs_start) * 1000
                    log_performance_metric(
                        metric_name="handoffs_wiring_duration",
                        value=handoffs_time,
                        unit="ms",
                        context={"enterprise_id": enterprise_id}
                    )
                    handoff_success = True
                    handoff_details["configured_agents"] = len(agents)  # Estimate
                else:
                    # Use YAML handoffs with explicit AG2 conditions
                    business_logger.info(f"🔗 [{workflow_name_upper}] Applying YAML handoffs...")
                    from .handoffs import wire_handoffs_with_debugging
                    
                    # Use enhanced handoff wiring with detailed feedback
                    handoff_result = wire_handoffs_with_debugging(workflow_name, agents)
                    handoff_success = handoff_result["success"]
                    handoff_details.update(handoff_result)
                
                if handoff_success:
                    business_logger.info(f"✅ [{workflow_name_upper}] Explicit handoff conditions configured successfully")
                    business_logger.info(f"📊 [{workflow_name_upper}] Handoff Summary: {handoff_details['configured_agents']} agents configured")
                else:
                    business_logger.warning(f"⚠️ [{workflow_name_upper}] Handoffs FAILED - workflow may have termination/flow issues!")
                    business_logger.warning(f"🔍 [{workflow_name_upper}] Handoff failure details: {handoff_details}")
                    
            except Exception as e:
                handoff_details["failed"] = True
                handoff_details["error"] = str(e)
                business_logger.error(f"❌ [{workflow_name_upper}] Handoffs configuration FAILED: {e}", exc_info=True)
                business_logger.error(f"🚨 [{workflow_name_upper}] CRITICAL: Workflow may terminate early or behave unexpectedly!")
        else:
            business_logger.info(f"ℹ️ [{workflow_name_upper}] Handoffs skipped - pattern: {orchestration_pattern} (handoffs only available for DefaultPattern)")
            
        # Log handoff status for debugging
        log_business_event(
            event_type=f"{workflow_name_upper}_HANDOFF_STATUS",
            description="Handoff configuration status for debugging",
            context={
                "handoff_attempted": handoff_details["attempted"],
                "handoff_success": handoff_success,
                "handoff_details": handoff_details,
                "pattern": orchestration_pattern
            }
        )

        # ===================================================================
        # AG2 HANDOFF VERIFICATION - Verify handoffs are registered at AG2 level
        # ===================================================================
        if orchestration_pattern == "DefaultPattern":
            try:
                business_logger.info(f"🔍 [{workflow_name_upper}] Verifying handoffs at AG2 engine level...")
                from .handoffs import handoff_manager
                
                verification_result = handoff_manager.verify_handoffs(agents)
                
                business_logger.info(f"📊 [{workflow_name_upper}] Handoff Verification Results:")
                business_logger.info(f"   🤖 Total agents: {verification_result['total_agents']}")
                business_logger.info(f"   ✅ Agents with handoffs: {verification_result['agents_with_handoffs']}")
                
                if verification_result["issues"]:
                    business_logger.warning(f"   ⚠️ Handoff issues found ({len(verification_result['issues'])}):")
                    for issue in verification_result["issues"][:5]:  # Show first 5 to avoid clutter
                        business_logger.warning(f"      • {issue}")
                else:
                    business_logger.info(f"   ✅ All agents passed handoff verification")
                
                # Critical check for agents without handoffs
                agents_without_handoffs = verification_result['total_agents'] - verification_result['agents_with_handoffs']
                if agents_without_handoffs > 0:
                    business_logger.error(f"🚨 [{workflow_name_upper}] CRITICAL: {agents_without_handoffs} agents missing handoffs!")
                    business_logger.error(f"🚨 [{workflow_name_upper}] This will likely cause immediate termination or flow issues!")
                
            except Exception as e:
                business_logger.error(f"❌ [{workflow_name_upper}] Handoff verification failed: {e}")

        # ===================================================================
        # AG2 HANDOFF INTROSPECTION - Verify what each agent holds AFTER wiring
        # ===================================================================
        try:
            business_logger.info(f"🔍 [{workflow_name_upper}] AG2 Handoff Introspection - AFTER wiring...")
            
            all_agents_to_check = list(pattern.agents)
            if hasattr(pattern, 'user_agent') and pattern.user_agent:
                all_agents_to_check.append(pattern.user_agent)

            for ag in all_agents_to_check:
                if not hasattr(ag, "handoffs"):
                    business_logger.warning(f"⚠️ [{workflow_name_upper}] {ag.name} lacks .handoffs attribute")
                    continue

                h = ag.handoffs
                # Corrected attributes for AG2 v0.9.7+
                after_works_count = len(getattr(h, "after_works", []))
                llm_conds_count = len(getattr(h, "llm_conditions", []))
                ctx_conds_count = len(getattr(h, "context_conditions", []))
                total_handoffs = after_works_count + llm_conds_count + ctx_conds_count

                business_logger.info(
                    f"🔍 [{workflow_name_upper}] {ag.name} HANDOFF SUMMARY (AFTER) → "
                    f"after_work: {after_works_count}, "
                    f"LLM_conditions: {llm_conds_count}, "
                    f"context_conditions: {ctx_conds_count}"
                )
                
                if total_handoffs == 0:
                    business_logger.warning(f"🚨 [{workflow_name_upper}] {ag.name} has NO handoffs after wiring - this will cause issues!")
                    handoffs_vars = vars(h) if hasattr(h, '__dict__') else {}
                    business_logger.debug(f"🔍 [{workflow_name_upper}] {ag.name} handoffs internal vars: {list(handoffs_vars.keys())}")

        except Exception as e:
            business_logger.error(f"❌ [{workflow_name_upper}] AG2 handoff introspection (AFTER) failed: {e}")

        # ===================================================================
        # 13. EXECUTE AG2 GROUP CHAT USING THE PATTERN (ALIGNED TO SPECS)
        # ===================================================================
        # EXECUTION FORMAT AS SPECIFIED:
        # result, final_context, last_agent = run_group_chat(
        #     pattern=pattern,
        #     messages="{initial_message}",
        #     max_rounds={max_turns}
        # )
        # 
        # KEY UNDERSTANDING (from AG2 source analysis):
        # - initial_agent: Gets the first turn to speak (from orchestrator.yaml)
        # - initial_message: Sent to entire group chat context, not specifically to initial_agent
        # - Pattern logic determines conversation flow after the initial turn
        # ===================================================================
        chat_start = time.time()
        business_logger.info(f"🚀 [{workflow_name_upper}] Starting AG2 group chat execution...")

        # ===================================================================
        # PATTERN INTERNALS INSPECTION - Check rotation and selection state
        # ===================================================================
        try:
            business_logger.info(f"🔍 [{workflow_name_upper}] Pattern Internals Inspection...")
            
            if hasattr(pattern, "_turn_index"):
                business_logger.debug(f"🔄 [{workflow_name_upper}] Current turn index: {pattern._turn_index}")
            else:
                business_logger.debug(f"🔄 [{workflow_name_upper}] No _turn_index attribute found")

            if hasattr(pattern, "_speaker_selector"):
                business_logger.debug(f"🗺️ [{workflow_name_upper}] Speaker-selection strategy: {pattern._speaker_selector}")
            else:
                business_logger.debug(f"🗺️ [{workflow_name_upper}] No _speaker_selector attribute found")
                
            # Check for other relevant pattern internals
            if hasattr(pattern, "_current_speaker"):
                business_logger.debug(f"🎤 [{workflow_name_upper}] Current speaker: {pattern._current_speaker}")
                
            if hasattr(pattern, "_initial_speaker"):
                business_logger.debug(f"🎬 [{workflow_name_upper}] Initial speaker: {pattern._initial_speaker}")
                
            # Inspect pattern state
            pattern_vars = vars(pattern) if hasattr(pattern, '__dict__') else {}
            business_logger.debug(f"🔍 [{workflow_name_upper}] Pattern internal vars: {list(pattern_vars.keys())}")
            
        except Exception as e:
            business_logger.error(f"❌ [{workflow_name_upper}] Pattern internals inspection failed: {e}")

        # Configuration validation - only log issues
        valid_patterns = ["AutoPattern", "DefaultPattern", "RoundRobinPattern", "RandomPattern"]
        if orchestration_pattern not in valid_patterns:
            business_logger.warning(f"⚠️ [{workflow_name_upper}] Invalid orchestration pattern '{orchestration_pattern}'")

        if not agents or len(agents) == 0:
            business_logger.error(f"❌ [{workflow_name_upper}] No agents loaded - check agents.yaml")

        if orchestration_pattern == "DefaultPattern" and not handoff_success:
            business_logger.error(f"❌ [{workflow_name_upper}] Handoff configuration failed: {handoff_details.get('error', 'Unknown')}")

        # Pattern summary
        total_agents_in_pattern = len(agents_list) + (1 if human_in_loop and user_proxy_agent else 0)
        business_logger.info(f"🔍 [{workflow_name_upper}] Pattern: {total_agents_in_pattern} agents, initial: {initiating_agent.name}")
        
        # Initialize termination handler for conversation tracking
        termination_handler = create_termination_handler(
            chat_id=chat_id,
            enterprise_id=enterprise_id, 
            workflow_name=workflow_name,
            token_manager=get_token_tracker(chat_id, enterprise_id, user_id or "unknown")
        )
        await termination_handler.on_conversation_start()
        business_logger.info(f"✅ [{workflow_name_upper}] Conversation tracking initialized")
        
        # ALIGNED EXECUTION
        try:
            # Debug logging before AG2 execution
            business_logger.info(f"🔍 [{workflow_name_upper}] Pre-execution summary:")
            business_logger.info(f"   🎯 Pattern: {type(pattern).__name__} | Agents: {len(agents_list)} | User: {user_proxy_agent is not None and human_in_loop}")
            
            if startup_mode == "BackendOnly":
                business_logger.info(f"🔍 [{workflow_name_upper}] Using run_group_chat (sync)")
                result = run_group_chat(
                    pattern=pattern,
                    messages=final_initial_message,
                    max_rounds=max_turns
                )
                business_logger.info(f"🔍 [{workflow_name_upper}] Processing AG2 events to execute conversation...")
                result.process()
                business_logger.info(f"✅ [{workflow_name_upper}] AG2 event processing completed")
                
                # Log conversation history for sync execution too
                try:
                    conversation_history = getattr(result, 'messages', [])
                    business_logger.info(f"📋 [{workflow_name_upper}] Sync conversation completed with {len(conversation_history)} messages")
                    
                    agent_logger = logging.getLogger('chat.agent_messages')
                    for i, msg in enumerate(conversation_history):
                        sender = msg.get('name', msg.get('role', 'unknown'))
                        content = msg.get('content', '')
                        msg_preview = content[:200] + "..." if len(content) > 200 else content
                        agent_logger.info(f"SYNC_MSG_{i+1} | Chat: {chat_id} | Agent: {sender} | Content: {msg_preview}")
                except Exception as e:
                    business_logger.warning(f"⚠️ [{workflow_name_upper}] Could not extract sync conversation history: {e}")
            else:  # AgentDriven or UserDriven
                business_logger.info(f"🔍 [{workflow_name_upper}] Using a_run_group_chat (async)")
                business_logger.info(f"🔍 [{workflow_name_upper}] About to call a_run_group_chat...")
                
                # Debug the AG2 call parameters
                business_logger.info(f"🔍 [{workflow_name_upper}] AG2 call parameters:")
                business_logger.info(f"   📝 Messages: {final_initial_message}")
                business_logger.info(f"   🔢 Max rounds: {max_turns}")
                business_logger.info(f"   🎯 Pattern type: {pattern}")
                business_logger.info(f"   📊 Pattern agents count: {len(getattr(pattern, 'agents', []))}")
                
                # Try to get more info about the pattern
                try:
                    if hasattr(pattern, 'agents'):
                        agent_names = [getattr(agent, 'name', 'unnamed') for agent in pattern.agents]
                        business_logger.info(f"   🤖 Pattern agent names: {agent_names}")
                    if hasattr(pattern, 'initial_speaker'):
                        business_logger.info(f"   🎬 Initial speaker: {getattr(pattern.initial_speaker, 'name', 'unnamed')}")
                except Exception as e:
                    business_logger.warning(f"   ⚠️ Could not inspect pattern details: {e}")
                
                result = await a_run_group_chat(
                    pattern=pattern,
                    messages=final_initial_message,
                    max_rounds=max_turns
                )
                business_logger.info(f"🔍 [{workflow_name_upper}] a_run_group_chat returned: type={type(result).__name__}")
                
                # ===================================================================
                # CRITICAL: PROCESS EVENTS TO ACTUALLY EXECUTE THE CONVERSATION
                # ===================================================================
                business_logger.info(f"🔍 [{workflow_name_upper}] Processing AG2 events to execute conversation...")
                await result.process()
                business_logger.info(f"✅ [{workflow_name_upper}] AG2 event processing completed")
                
                # ===================================================================
                # ENHANCED CONVERSATION LOGGING - Log the actual agent messages
                # ===================================================================
                try:
                    # Get the conversation history from the result
                    conversation_history = getattr(result, 'messages', [])
                    business_logger.info(f"📋 [{workflow_name_upper}] Conversation completed with {len(conversation_history)} messages")
                    
                    # Log each message for debugging
                    agent_logger = logging.getLogger('chat.agent_messages')
                    for i, msg in enumerate(conversation_history):
                        sender = msg.get('name', msg.get('role', 'unknown'))
                        content = msg.get('content', '')
                        msg_preview = content[:200] + "..." if len(content) > 200 else content
                        agent_logger.info(f"MSG_{i+1} | Chat: {chat_id} | Agent: {sender} | Content: {msg_preview}")
                    
                    business_logger.info(f"🎯 [{workflow_name_upper}] Full conversation logged to agent_messages logger")
                    
                except Exception as e:
                    business_logger.warning(f"⚠️ [{workflow_name_upper}] Could not extract conversation history: {e}")
                
                # ===================================================================
                # AG2 EVENT TAP - Stream live engine events in real time
                # ===================================================================
                async def _stream_ag2_events(resp):
                    try:
                        business_logger.info(f"📡 [{workflow_name_upper}] Starting AG2 event stream monitoring...")
                        event_count = 0
                        async for ev in resp.events:
                            event_count += 1
                            # Typical ev.type values: 'agent_started', 'agent_finished', 'message'
                            business_logger.debug(
                                f"📡 [{workflow_name_upper}] EVENT #{event_count} {ev.type} :: {ev.data}"
                            )
                        business_logger.info(f"📡 [{workflow_name_upper}] AG2 event stream completed with {event_count} events")
                    except Exception as e:
                        business_logger.error(f"⚠️ [{workflow_name_upper}] Event stream error: {e}")

                # Fire-and-forget (don't await, just schedule)
                import asyncio
                asyncio.create_task(_stream_ag2_events(result))
                business_logger.info(f"📡 [{workflow_name_upper}] AG2 event monitoring task started")
                
                # CRITICAL: Await the messages coroutine to get actual conversation
                # Check for messages attribute without triggering the coroutine
                try:
                    business_logger.info(f"🔍 [{workflow_name_upper}] Awaiting messages coroutine...")
                    # This is the key - we need to await the messages to get the actual conversation
                    actual_messages = await result.messages
                    
                    # Count messages safely
                    message_count = 'unknown'
                    try:
                        if hasattr(actual_messages, '__len__'):
                            message_count = len(actual_messages)  # type: ignore
                        elif hasattr(actual_messages, '__iter__'):
                            message_count = sum(1 for _ in actual_messages)
                    except Exception:
                        pass
                    
                    business_logger.info(f"🔍 [{workflow_name_upper}] Conversation completed with {message_count} messages")
                    
                    # If we got 0 messages, let's investigate why
                    if message_count == 0:
                        business_logger.warning(f"⚠️ [{workflow_name_upper}] AG2 returned 0 messages - investigating...")
                        
                        # Inspect the result object more closely
                        business_logger.info(f"🔍 [{workflow_name_upper}] Result object type: {type(result)}")
                        business_logger.info(f"🔍 [{workflow_name_upper}] Result object attributes:")
                        for attr in dir(result):
                            if not attr.startswith('_'):
                                try:
                                    value = getattr(result, attr)
                                    if not callable(value):
                                        business_logger.info(f"   {attr}: {type(value)} = {value}")
                                    else:
                                        business_logger.info(f"   {attr}: {type(value)} (callable)")
                                except Exception as e:
                                    business_logger.info(f"   {attr}: Error accessing - {e}")
                    
                    # Log some message details for debugging
                    if hasattr(actual_messages, '__iter__') and message_count and message_count != 0:
                        for i, msg in enumerate(actual_messages):
                            if i < 3:  # Log first 3 messages
                                sender = getattr(msg, 'name', 'unknown') if hasattr(msg, 'name') else 'unknown'
                                content_preview = str(getattr(msg, 'content', ''))[:100] if hasattr(msg, 'content') else 'no content'
                                business_logger.info(f"🔍 [{workflow_name_upper}] Message {i+1}: {sender} -> {content_preview}...")
                except AttributeError:
                    business_logger.warning(f"⚠️ [{workflow_name_upper}] No messages property found on result")
                except Exception as e:
                    business_logger.error(f"❌ [{workflow_name_upper}] Failed to await messages: {e}")
                    import traceback
                    business_logger.error(f"❌ [{workflow_name_upper}] Traceback: {traceback.format_exc()}")
                
            # Debug the result
            try:
                if hasattr(result, '__len__'):
                    business_logger.info(f"🔍 [{workflow_name_upper}] Result length: {len(result)}")  # type: ignore
            except Exception:
                pass
            business_logger.info(f"🔍 [{workflow_name_upper}] Full result: {str(result)[:200]}...")
                
            business_logger.info(f"🎉 [{workflow_name_upper}] Group chat execution completed successfully")
        except Exception as e:
            business_logger.error(f"❌ [{workflow_name_upper}] Group chat execution failed: {e}")
            import traceback
            business_logger.error(f"❌ [{workflow_name_upper}] Traceback: {traceback.format_exc()}")
            raise
        
        chat_time = (time.time() - chat_start) * 1000
        log_performance_metric(
            metric_name="ag2_groupchat_execution_duration",
            value=chat_time,
            unit="ms",
            context={"enterprise_id": enterprise_id, "chat_id": chat_id, "startup_mode": startup_mode}
        )
        business_logger.info(f"🎉 [{workflow_name_upper}] AG2 workflow completed in {chat_time:.2f}ms")

        # ===================================================================
        # 14. TERMINATION HANDLING - Update workflow status from 0 → 1 (VE-style)
        # ===================================================================
        try:
            # Use the existing termination handler that was initialized before conversation
            # Handle conversation termination (0 → 1)
            termination_result = await termination_handler.on_conversation_end(
                termination_reason="workflow_completed",
                final_status=1  # VE pattern: 1 = completed
            )
            
            if termination_result.terminated:
                business_logger.info(f"✅ [{workflow_name_upper}] Workflow status updated: 0 → 1 (completed)")
            else:
                business_logger.warning(f"⚠️ [{workflow_name_upper}] Failed to update termination status")
                
        except Exception as termination_error:
            business_logger.error(f"❌ [{workflow_name_upper}] Termination handling failed: {termination_error}")
        
        # Analytics handled by token_manager.py - no complex cost monitoring in orchestration_patterns
        business_logger.info(f"✅ [{workflow_name_upper}] Analytics tracking handled by token_manager.py")

        # ===================================================================
        # 15. RETURN FINAL RESULT
        # ===================================================================
        log_business_event(
            event_type=f"{workflow_name_upper}_WORKFLOW_COMPLETED",
            description=f"{workflow_name} workflow orchestration completed successfully using consolidated patterns",
            context={
                "enterprise_id": enterprise_id,
                "chat_id": chat_id,
                "total_duration_seconds": (time.time() - start_time),
                "agent_count": len(agents),
                "pattern_used": orchestration_pattern,
                "result_status": "completed"
            }
        )
        
        business_logger.info(f"✅ [{workflow_name_upper}] CONSOLIDATED workflow orchestration completed successfully")
        return result  # Return AG2's native result directly
        
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"❌ [{workflow_name_upper}] Workflow orchestration failed after {duration:.2f}s: {e}", exc_info=True)
        log_business_event(
            event_type=f"{workflow_name_upper}_WORKFLOW_FAILED",
            description=f"{workflow_name} workflow orchestration failed using consolidated patterns",
            context={
                "enterprise_id": enterprise_id,
                "chat_id": chat_id,
                "error": str(e),
                "duration_seconds": duration,
                "pattern_attempted": orchestration_pattern
            },
            level="ERROR"
        )
        raise
    finally:
        # ANALYTICS CLEANUP - Ensure data is captured even on failure (from groupchat_manager.py)
        try:
            business_logger.debug(f"🧹 [{workflow_name_upper}] Analytics cleanup starting...")
            
            # Clean up AG2 streaming first - check if streaming_manager was created
            streaming_manager = locals().get('streaming_manager')
            if streaming_manager is not None:
                try:
                    streaming_manager.cleanup()
                    business_logger.info(f"✅ [{workflow_name_upper}] AG2 streaming cleanup completed")
                except Exception as streaming_cleanup_error:
                    business_logger.error(f"❌ [{workflow_name_upper}] AG2 streaming cleanup failed: {streaming_cleanup_error}")
            
            # Try to finalize analytics even if workflow failed
            try:
                token_tracker = get_token_tracker(chat_id, enterprise_id, user_id or "unknown")
                
                # If session wasn't finalized yet (due to error), try to finalize now
                if hasattr(token_tracker, 'session_usage') and not getattr(token_tracker, '_session_finalized', False):
                    business_logger.info(f"🔄 [{workflow_name_upper}] Attempting emergency analytics finalization...")
                    emergency_summary = await token_tracker.finalize_session()
                    if emergency_summary:
                        business_logger.info(f"✅ [{workflow_name_upper}] Emergency analytics finalization successful")
            except Exception as token_cleanup_error:
                business_logger.error(f"❌ [{workflow_name_upper}] Token cleanup failed: {token_cleanup_error}")
                    
        except Exception as cleanup_error:
            logger.warning(f"⚠️ [{workflow_name_upper}] Cleanup warning: {cleanup_error}")
            
        business_logger.debug(f"🧹 [{workflow_name_upper}] Workflow cleanup completed")

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
# LOGGING HELPERS (Moved from groupchat_manager.py)
# ==============================================================================

def log_agent_message_details(message, sender_name, recipient_name):
    """Logs agent message details for tracking (moved from groupchat_manager.py)."""
    message_content = getattr(message, 'content', None) or str(message)
    
    if message_content and sender_name != 'unknown':
        # Log a summary for readability
        summary = message_content[:150] + '...' if len(message_content) > 150 else message_content
        chat_logger.info(f"🤖 [AGENT] {sender_name} → {recipient_name}: {summary}")
        
        # Log full content at debug level for complete tracking
        chat_logger.debug(f"📋 [FULL] {sender_name} complete message:\n{'-'*50}\n{message_content}\n{'-'*50}")
        
        # Log message metadata
        chat_logger.debug(f"📊 [META] Length: {len(message_content)} chars | Type: {type(message).__name__}")
        
        # NOTE: UI routing is now handled by individual tools (api_manager.py, file_manager.py)
        # Tools emit UI events directly via emit_ui_tool_event() when needed
        
        # NOTE: Analytics tracking is handled by token_manager.py - no complex monitoring here
        
    return message

# ==============================================================================
# END CONSOLIDATED ORCHESTRATION PATTERNS
# ==============================================================================
