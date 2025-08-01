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
from autogen.agentchat.group.patterns import (
    DefaultPattern as AG2DefaultPattern,
    AutoPattern as AG2AutoPattern,
    RoundRobinPattern as AG2RoundRobinPattern,
    RandomPattern as AG2RandomPattern,
)
from autogen.agentchat.group.multi_agent_chat import run_group_chat, a_run_group_chat

# Import consolidated functionality (moved from groupchat_manager.py)
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
    llm_config: Dict[str, Any],
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
        llm_config: LLM configuration
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
        # ===================================================================
        # 1. LOAD YAML CONFIGURATION
        # ===================================================================
        from .workflow_config import workflow_config
        config = workflow_config.get_config(workflow_name)
        max_turns = config.get("max_turns", 50)
        initiating_agent_name = config.get("initiating_agent", "user")
        orchestration_pattern = config.get("orchestration_pattern", "AutoPattern")
        startup_mode = config.get("startup_mode", "AgentDriven")
        
        # Handoffs are automatically enabled for DefaultPattern, disabled for others
        enable_handoffs = (orchestration_pattern == "DefaultPattern")
        
        business_logger.info(f"🚀 [{workflow_name_upper}] Starting CONSOLIDATED AG2 orchestration:")
        business_logger.info(f"   • max_turns: {max_turns}")
        business_logger.info(f"   • orchestration_pattern: {orchestration_pattern}")
        business_logger.info(f"   • startup_mode: {startup_mode}")
        business_logger.info(f"   • handoffs: {'enabled' if enable_handoffs else 'disabled'} (auto-determined from pattern)")

        # Determine final initial message early for accurate logging
        final_initial_message = (
            config.get("initial_message") or 
            initial_message or
            f"Hello! Let's start the {workflow_name} workflow."
        )
        
        log_business_event(
            event_type=f"{workflow_name_upper}_WORKFLOW_STARTED",
            description=f"{workflow_name} workflow orchestration initialized using consolidated patterns",
            context={
                "enterprise_id": enterprise_id,
                "chat_id": chat_id,
                "user_id": user_id,
                "pattern": orchestration_pattern,
                "startup_mode": startup_mode,
                "final_message_preview": final_initial_message[:100] + "..." if len(final_initial_message) > 100 else final_initial_message
            }
        )

        # ===================================================================
        # 2. RESUME LOGIC - Check if workflow can be resumed (VE-style)
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
        # 3. LOAD CONCEPT DATA FROM DATABASE
        # ===================================================================
        concept_start = time.time()
        business_logger.debug("📊 Loading concept data...")
        
        concept_data = await mongodb_manager.find_latest_concept_for_enterprise(enterprise_id)
        concept_load_time = (time.time() - concept_start) * 1000
        
        log_performance_metric(
            metric_name="concept_data_load_duration",
            value=concept_load_time,
            unit="ms",
            context={
                "enterprise_id": enterprise_id,
                "concept_found": concept_data is not None
            }
        )
        
        if concept_data:
            business_logger.info(f"📊 [{workflow_name_upper}] Concept data loaded successfully")
        else:
            business_logger.warning(f"⚠️ [{workflow_name_upper}] No concept data found - using defaults")

        # ===================================================================
        # 4. BUILD CONTEXT (if context factory provided, or use concept data)
        # ===================================================================
        context = None
        if context_factory:
            context_start = time.time()
            business_logger.debug(f"🔄 [{workflow_name_upper}] Building context...")
            context = context_factory(concept_data)
            context_time = (time.time() - context_start) * 1000
            log_performance_metric(
                metric_name="context_build_duration",
                value=context_time,
                unit="ms",
                context={"enterprise_id": enterprise_id}
            )
            business_logger.info(f"✅ [{workflow_name_upper}] Context built successfully")
        elif concept_data:
            # Fallback: use concept data as context
            context = {"concept_data": concept_data}
            business_logger.info(f"✅ [{workflow_name_upper}] Using concept data as context")

        # ===================================================================
        # 5. SET UP AG2 STREAMING WITH CUSTOM IOSTREAM
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
        
        # Note: AG2 streaming is handled by IOStream system, not by llm_config parameters
        business_logger.info(f"✅ [{workflow_name_upper}] AG2 streaming handled by IOStream system")
        
        streaming_setup_time = (time.time() - streaming_start) * 1000
        log_performance_metric(
            metric_name="ag2_streaming_setup_duration",
            value=streaming_setup_time,
            unit="ms",
            context={"enterprise_id": enterprise_id, "chat_id": chat_id}
        )

        # ===================================================================
        # 6. DEFINE AGENTS (using provided factory or YAML)
        # ===================================================================
        agents_start = time.time()
        
        if agents_factory:
            business_logger.debug(f"🤖 [{workflow_name_upper}] Defining agents using provided factory...")
            agents = await agents_factory()
        else:
            business_logger.debug(f"🤖 [{workflow_name_upper}] Defining agents using YAML...")
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

        # ===================================================================
        # 7. REGISTER TOOLS USING MODULAR TOOL REGISTRY
        # ===================================================================
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

        # ===================================================================
        # 8. CREATE USERPROXYAGENT WITH PROPER STARTUP_MODE CONFIGURATION
        # ===================================================================
        user_proxy_agent = None
        user_proxy_exists = any(agent.name.lower() in ["user", "userproxy", "userproxyagent"] for agent in agents.values() if hasattr(agent, 'name'))
        
        if not user_proxy_exists:
            # Determine human_input_mode based on startup_mode and human_in_the_loop
            human_in_loop = config.get("human_in_the_loop", False)
            
            if startup_mode == "BackendOnly":
                human_input_mode = "NEVER"
                business_logger.info(f"🤖 [{workflow_name_upper}] BackendOnly mode: No user interface, pure backend processing")
            elif startup_mode == "UserDriven":
                human_input_mode = "ALWAYS" if human_in_loop else "TERMINATE"
                business_logger.info(f"👤 [{workflow_name_upper}] UserDriven mode: User initiates, interface enabled")
            elif startup_mode == "AgentDriven":
                human_input_mode = "TERMINATE" if human_in_loop else "NEVER"
                business_logger.info(f"🤖 [{workflow_name_upper}] AgentDriven mode: Agent initiates, interface enabled")
            else:
                human_input_mode = "TERMINATE"  # Safe fallback
                business_logger.warning(f"⚠️ [{workflow_name_upper}] Unknown startup_mode '{startup_mode}', using fallback")
            
            user_proxy_agent = UserProxyAgent(
                name="user",
                human_input_mode=human_input_mode,
                max_consecutive_auto_reply=0,
                code_execution_config=False,
                system_message="You are a helpful user proxy that facilitates communication between the user and the agents."
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
        # 9. GET INITIATING AGENT
        # ===================================================================
        initiating_agent = agents.get(initiating_agent_name)
        if not initiating_agent:
            # Fallback to user proxy if initiating agent not found
            initiating_agent = user_proxy_agent
            if not initiating_agent:
                raise ValueError(f"Initiating agent '{initiating_agent_name}' not found and no user proxy available")
            business_logger.warning(f"⚠️ [{workflow_name_upper}] Initiating agent '{initiating_agent_name}' not found, using user proxy")
        else:
            business_logger.info(f"✅ [{workflow_name_upper}] Initiating agent: {initiating_agent.name}")

        # ===================================================================
        # 10. CREATE AG2-STYLE ORCHESTRATION PATTERN
        # ===================================================================
        pattern_start = time.time()
        business_logger.info(f"🎯 [{workflow_name_upper}] Creating {orchestration_pattern} with startup_mode: {startup_mode}...")
        
        pattern = create_orchestration_pattern(
            pattern_name=orchestration_pattern,
            initial_agent=initiating_agent,
            agents=list(agents.values()),
            user_agent=user_proxy_agent,
            context_variables=context,
            group_manager_args={
                "llm_config": llm_config
                # Note: streaming_manager is handled separately by AG2 streaming infrastructure
            },
            max_rounds=max_turns,
            enable_handoffs=enable_handoffs  # For DefaultPattern
        )
        
        pattern_time = (time.time() - pattern_start) * 1000
        log_performance_metric(
            metric_name="orchestration_pattern_creation_duration",
            value=pattern_time,
            unit="ms",
            context={"enterprise_id": enterprise_id, "pattern": orchestration_pattern, "startup_mode": startup_mode}
        )
        business_logger.info(f"✅ [{workflow_name_upper}] {orchestration_pattern} created successfully with startup_mode: {startup_mode}")

        # ===================================================================
        # 11. WIRE HANDOFFS (if handoffs factory provided and pattern supports it)
        # ===================================================================
        if handoffs_factory and orchestration_pattern == "DefaultPattern" and enable_handoffs:
            handoffs_start = time.time()
            business_logger.info(f"🔗 [{workflow_name_upper}] Wiring handoffs...")
            
            try:
                await handoffs_factory(agents)
                handoffs_time = (time.time() - handoffs_start) * 1000
                log_performance_metric(
                    metric_name="handoffs_wiring_duration",
                    value=handoffs_time,
                    unit="ms",
                    context={"enterprise_id": enterprise_id}
                )
                business_logger.info(f"✅ [{workflow_name_upper}] Handoffs configured successfully")
            except Exception as e:
                business_logger.warning(f"⚠️ [{workflow_name_upper}] Handoffs configuration failed: {e}")
        elif not handoffs_factory:
            # Use YAML handoffs
            business_logger.info(f"🔗 [{workflow_name_upper}] Applying YAML handoffs...")
            try:
                from .handoffs import HandoffManager
                handoff_manager = HandoffManager()
                handoff_manager.apply_handoffs_from_yaml(workflow_name, agents)
                business_logger.info(f"✅ [{workflow_name_upper}] YAML handoffs applied successfully")
            except Exception as e:
                business_logger.warning(f"⚠️ [{workflow_name_upper}] YAML handoffs failed: {e}")
        else:
            business_logger.warning(f"⚠️ [{workflow_name_upper}] Handoffs skipped - factory={handoffs_factory is not None}, pattern={orchestration_pattern}, enable_handoffs={enable_handoffs}")

        # ===================================================================
        # 12. EXECUTE AG2 GROUP CHAT USING THE PATTERN
        # ===================================================================
        chat_start = time.time()
        business_logger.info(f"🚀 [{workflow_name_upper}] Starting AG2 group chat execution...")
        
        # Use AG2's native run_group_chat/a_run_group_chat based on startup_mode
        if startup_mode == "BackendOnly":
            # Synchronous execution - no streaming, pure backend processing
            business_logger.info("🔒 Using synchronous run_group_chat (BackendOnly)")
            
            result = run_group_chat(
                pattern=pattern,
                messages=final_initial_message,
                max_rounds=max_turns
            )
            
        else:
            # Asynchronous execution - AgentDriven or UserDriven with streaming
            business_logger.info(f"🌊 Using asynchronous a_run_group_chat ({startup_mode})")
            
            result = await a_run_group_chat(
                pattern=pattern,
                messages=final_initial_message,
                max_rounds=max_turns
            )
        
        chat_time = (time.time() - chat_start) * 1000
        log_performance_metric(
            metric_name="ag2_groupchat_execution_duration",
            value=chat_time,
            unit="ms",
            context={"enterprise_id": enterprise_id, "chat_id": chat_id, "startup_mode": startup_mode}
        )
        business_logger.info(f"🎉 [{workflow_name_upper}] AG2 workflow completed in {chat_time:.2f}ms")

        # ===================================================================
        # 13. TERMINATION HANDLING - Update workflow status from 0 → 1 (VE-style)
        # ===================================================================
        try:
            # Create termination handler for proper status management (from groupchat_manager.py)
            token_tracker = get_token_tracker(chat_id, enterprise_id, user_id or "unknown")
            
            termination_handler = create_termination_handler(
                chat_id=chat_id,
                enterprise_id=enterprise_id, 
                workflow_name=workflow_name,
                token_manager=token_tracker
            )
            
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
        # 14. RETURN FINAL RESULT
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
    max_rounds: Optional[int] = None,
    **pattern_kwargs
) -> Any:  # Returns AG2's native pattern
    """
    Factory function to create AG2's native orchestration patterns.
    
    Args:
        pattern_name: Name of the pattern ("AutoPattern", "DefaultPattern", etc.)
        initial_agent: Agent that starts the conversation
        agents: List of all agents in the conversation
        user_agent: Optional user proxy agent
        context_variables: Shared context for the conversation
        group_manager_args: Arguments for GroupChatManager (e.g., llm_config)
        max_rounds: Maximum number of conversation rounds
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
        logger.warning(f"⚠️ Unknown pattern '{pattern_name}', defaulting to AutoPattern")
        pattern_name = "AutoPattern"
    
    pattern_class = pattern_map[pattern_name]
    
    logger.info(f"🎯 Creating {pattern_name} using AG2's native implementation")
    
    # Build arguments that AG2 patterns actually accept
    pattern_args = {
        "initial_agent": initial_agent,
        "agents": agents,
        "user_agent": user_agent,
    }
    
    # Only add optional arguments if they're not None
    if context_variables is not None:
        pattern_args["context_variables"] = context_variables
    if group_manager_args is not None:
        pattern_args["group_manager_args"] = group_manager_args
    if max_rounds is not None:
        pattern_args["max_rounds"] = max_rounds
    
    # Add any additional pattern-specific kwargs
    pattern_args.update(pattern_kwargs)
    
    try:
        pattern = pattern_class(**pattern_args)
        logger.info(f"✅ {pattern_name} AG2 pattern created successfully")
        return pattern
    except Exception as e:
        logger.warning(f"⚠️ Failed to create {pattern_name} with all args, trying minimal: {e}")
        # Fallback to minimal arguments
        minimal_pattern = pattern_class(
            initial_agent=initial_agent,
            agents=agents,
            user_agent=user_agent
        )
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
