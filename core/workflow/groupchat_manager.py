# =============================================================================
# FILE: core/workflow/groupchat_manager.py
# DESCRIPTION: Core helper for starting or resuming AG2 group chats
#              Streamlined after persistence_manager.py and token_manager.py refactoring
# =============================================================================
import time
import logging
import asyncio
import inspect
import uuid
import threading
from typing import Optional, Any, TYPE_CHECKING, List, Dict
from datetime import datetime

from ..data.persistence_manager import PersistenceManager
from ..data.token_manager import get_observer, get_token_tracker
from .tool_registry import WorkflowToolRegistry
from .termination_handler import create_termination_handler
from logs.logging_config import (
    get_chat_logger,
    log_business_event,
    log_performance_metric,
    get_agent_logger,
    get_workflow_logger
)

# Initialize persistence manager
mongodb_manager = PersistenceManager()

# Streamlined logging
chat_logger = get_chat_logger("core_groupchat")
agent_logger = get_agent_logger("groupchat_manager")
workflow_logger = get_workflow_logger("groupchat")
logger = logging.getLogger(__name__)

# ==============================================================================
# SIMPLIFIED RESPONSE TRACKING (Analytics moved to token_manager.py)
# ==============================================================================

# Performance-focused logging - minimal overhead
function_call_logger = logging.getLogger("ag2_function_call_debug")
function_call_logger.setLevel(logging.ERROR)  # Only log critical errors

# Keep minimal deep logging for critical debugging when needed
deep_logger = logging.getLogger("ag2_deep_debug")
deep_logger.setLevel(logging.WARNING)  # Only warnings and errors

# Agent lifecycle logging for tool registration
agent_lifecycle_logger = logging.getLogger("ag2_agent_lifecycle")
agent_lifecycle_logger.setLevel(logging.INFO)  # Keep tool registration info

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
        
        # NOTE: UI routing is now handled by individual tools (api_manager.py, file_manager.py)
        # Tools emit UI events directly via emit_ui_tool_event() when needed
        
        # NOTE: Analytics tracking is handled by token_manager.py - no complex monitoring here
        
    return message


# ==============================================================================
# WORKFLOW ORCHESTRATION FUNCTIONS
# ==============================================================================

async def run_workflow_orchestration(
    workflow_name: str,
    llm_config: Dict[str, Any],
    enterprise_id: str,
    chat_id: str,
    user_id: Optional[str] = None,
    initial_message: Optional[str] = None,
    agents_factory: Optional[Any] = None,
    context_factory: Optional[Any] = None,
    handoffs_factory: Optional[Any] = None
) -> None:
    """
    AG2-compliant workflow orchestration using pattern-based approach.
    
    This function now follows the AG2 documentation pattern:
    1. Create an orchestration pattern (AutoPattern, DefaultPattern, etc.)
    2. Pass the pattern to initiate_group_chat()
    3. Let the pattern handle GroupChat/GroupChatManager creation
    
    SUPPORTED PATTERNS:
    - AutoPattern: Automatic speaker selection
    - DefaultPattern: Automatic with handoffs support  
    - RoundRobinPattern: Sequential agent rotation
    - RandomPattern: Random agent selection
    - ManualPattern: Manual speaker selection
    
    Args:
        workflow_name: Type of workflow (e.g., "generator", "analyzer")
        llm_config: LLM configuration
        enterprise_id: Enterprise identifier
        chat_id: Chat identifier
        user_id: User identifier (optional)
        initial_message: Initial message (optional)
        agents_factory: Function to create agents - must return Dict[str, Agent]
        context_factory: Function to get context - must return context object
        handoffs_factory: Function to wire handoffs - takes agents dict
    """
    
    # SimpleTransport singleton is used for all communication
    from core.transport.simple_transport import SimpleTransport
    transport = SimpleTransport._get_instance()
    if not transport:
        raise RuntimeError(f"SimpleTransport instance not available for {workflow_name} workflow")
    
    if not agents_factory:
        raise ValueError(f"agents_factory is required for {workflow_name} workflow")
    
    start_time = time.time()
    workflow_name_upper = workflow_name.upper()
    streaming_manager = None  # Initialize for cleanup
    
    # Initialize workflow-specific loggers
    from logs.logging_config import get_business_logger
    business_logger = get_business_logger(f"{workflow_name}_orchestration")
    
    try:
        # Get workflow configuration
        from ..workflow.workflow_config import workflow_config
        config = workflow_config.get_config(workflow_name)
        max_turns = config.get("max_turns", 50)
        initiating_agent_name = config.get("initiating_agent", "UserProxyAgent")
        orchestration_pattern = config.get("orchestration_pattern", "AutoPattern")
        
        # Handoffs are automatically enabled for DefaultPattern, disabled for others
        enable_handoffs = (orchestration_pattern == "DefaultPattern")
        
        business_logger.info(f"🚀 [{workflow_name_upper}] Starting AG2 pattern-based orchestration:")
        business_logger.info(f"   • max_turns: {max_turns}")
        business_logger.info(f"   • orchestration_pattern: {orchestration_pattern}")
        business_logger.info(f"   • handoffs: {'enabled' if enable_handoffs else 'disabled'} (auto-determined from pattern)")

        # Determine final initial message early for accurate logging
        final_initial_message = (
            config.get("initial_message") or 
            initial_message
        )
        
        # If still no message, provide a generic fallback
        if not final_initial_message:
            final_initial_message = f"Hello! Let's start the {workflow_name} workflow."
        
        # Log accurate initial message information
        log_business_event(
            event_type=f"{workflow_name_upper}_WORKFLOW_STARTED",
            description=f"{workflow_name} workflow orchestration initialized using AG2 patterns",
            context={
                "enterprise_id": enterprise_id,
                "chat_id": chat_id,
                "user_id": user_id,
                "pattern": orchestration_pattern,
                "final_message_determined": True,
                "final_message_source": (
                    "workflow_json_initial" if config.get("initial_message") else
                    "user_provided" if initial_message else
                    "fallback_default"
                ),
                "final_message_preview": final_initial_message[:100] + "..." if len(final_initial_message) > 100 else final_initial_message
            }
        )
        
        business_logger.info(f"🎯 [{workflow_name_upper}] Using AG2 {orchestration_pattern} pattern")

        # ===================================================================
        # RESUME LOGIC - Check if workflow can be resumed (VE-style)
        # ===================================================================
        can_resume = await mongodb_manager.can_resume_chat(chat_id, enterprise_id, workflow_name)
        
        if can_resume:
            business_logger.info(f"🔄 [{workflow_name_upper}] Resumable session found for {chat_id}")
            
            # Load resume data with workflow_name
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
                    return  # Exit - already completed
                
                # Resume active conversation (VE pattern)
                conversation_data = resume_data.get("conversation", [])
                status = resume_data.get("status", 0)
                
                business_logger.info(f"🔄 [{workflow_name_upper}] Resuming conversation with {len(conversation_data)} messages, status {status}")
                
                # Store conversation for state restoration
                if conversation_data:
                    # The persistence manager already provides the conversation history
                    # Frontend will automatically display this when WebSocket reconnects
                    # Visual agents will show their previous interactions
                    business_logger.info(f"✅ [{workflow_name_upper}] Conversation state available for visual agents restoration")
                    business_logger.debug(f"📋 [{workflow_name_upper}] Available conversation: {len(conversation_data)} messages from previous session")
                
                # Continue with workflow using existing session data
                # The conversation history will be automatically presented via transport layer
            else:
                business_logger.warning(f"❌ [{workflow_name_upper}] Resume failed - starting new session")
        
        # Initialize workflow with status 0 (VE pattern) - for new sessions or failed resumes
        await mongodb_manager.update_workflow_status(chat_id, enterprise_id, 0, workflow_name)
        business_logger.info(f"🆕 [{workflow_name_upper}] Starting new session (status=0)")

        # 1. Load concept from database
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

        # 2. Build context (if context factory provided)
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

        # 2.5. Set up AG2 streaming with custom IOStream (connects to ag2_iostream.py)
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
        
        # Ensure streaming is enabled in llm_config for all agents
        if not llm_config.get("stream"):
            llm_config["stream"] = True
            business_logger.info(f"✅ [{workflow_name_upper}] Enabled streaming in llm_config")
        
        streaming_setup_time = (time.time() - streaming_start) * 1000
        log_performance_metric(
            metric_name="ag2_streaming_setup_duration",
            value=streaming_setup_time,
            unit="ms",
            context={"enterprise_id": enterprise_id, "chat_id": chat_id}
        )
        business_logger.info(f"✅ [{workflow_name_upper}] AG2 streaming ready - custom IOStream active")

        # 3. Define agents using provided factory
        agents_start = time.time()
        business_logger.debug(f"🤖 [{workflow_name_upper}] Defining agents...")
        
        agents = await agents_factory()
        
        agents_build_time = (time.time() - agents_start) * 1000
        log_performance_metric(
            metric_name="agents_definition_duration", 
            value=agents_build_time,
            unit="ms",
            context={"enterprise_id": enterprise_id, "agent_count": len(agents)}
        )
        business_logger.info(f"✅ [{workflow_name_upper}] Agents defined: {len(agents)} total")

        # 4. Register tools using modular tool registry
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

        # 5. Create UserProxyAgent with proper startup_mode configuration
        user_proxy_agent = None
        user_proxy_exists = any(agent.name.lower() in ["user", "userproxy", "userproxyagent"] for agent in agents.values() if hasattr(agent, 'name'))
        
        if not user_proxy_exists:
            from autogen import UserProxyAgent
            
            # Get startup mode configuration
            startup_mode = config.get("startup_mode", "AgentDriven")  # BackendOnly, UserDriven, AgentDriven
            human_in_loop = config.get("human_in_the_loop", False)
            
            # Determine human_input_mode based on startup_mode and human_in_the_loop
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
                    startup_mode = config.get("startup_mode", "AgentDriven")
                    business_logger.info(f"✅ [{workflow_name_upper}] Using existing UserProxyAgent with startup_mode: {startup_mode}")
                    break

        # 6. Get initiating agent
        initiating_agent = agents.get(initiating_agent_name)
        if not initiating_agent:
            # Fallback to user proxy if initiating agent not found
            initiating_agent = user_proxy_agent
            if not initiating_agent:
                raise ValueError(f"Initiating agent '{initiating_agent_name}' not found and no user proxy available")
            business_logger.warning(f"⚠️ [{workflow_name_upper}] Initiating agent '{initiating_agent_name}' not found, using user proxy")
        else:
            business_logger.info(f"✅ [{workflow_name_upper}] Initiating agent: {initiating_agent.name}")

        # 7. Create AG2-style orchestration pattern
        pattern_start = time.time()
        startup_mode = config.get("startup_mode", "AgentDriven")
        business_logger.info(f"🎯 [{workflow_name_upper}] Creating {orchestration_pattern} with startup_mode: {startup_mode}...")
        
        # Import the pattern factory
        from .orchestration_patterns import create_orchestration_pattern
        
        # Create the pattern with all necessary components including startup_mode
        pattern = create_orchestration_pattern(
            pattern_name=orchestration_pattern,
            initial_agent=initiating_agent,
            agents=list(agents.values()),
            user_agent=user_proxy_agent,
            context_variables=context,
            group_manager_args={
                "llm_config": llm_config,
                "streaming_manager": streaming_manager  # Pass streaming manager for agent context
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
        
        # Log startup mode implications
        if startup_mode == "BackendOnly":
            business_logger.info(f"🔒 [{workflow_name_upper}] Backend-only processing: No websocket interface, pure backend execution")
        elif startup_mode == "UserDriven":
            business_logger.info(f"👤 [{workflow_name_upper}] User-driven interface: User initiates with their message")
        elif startup_mode == "AgentDriven":
            business_logger.info(f"🤖 [{workflow_name_upper}] Agent-driven interface: Agent initiates, user sees interface but message is hidden")

        # 8. Wire handoffs (if handoffs factory provided and pattern supports it)
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

        # 9. Start AG2-style group chat using the pattern
        chat_start = time.time()
        business_logger.info(f"🚀 [{workflow_name_upper}] Starting AG2-style group chat...")
        
        # Import the AG2-style initiation function
        from .orchestration_patterns import initiate_group_chat
        
        # Get the initial_message_to_user for UserDriven mode
        initial_message_to_user = config.get("initial_message_to_user")
        
        # For resume scenarios, the conversation history is already loaded and available
        effective_initial_message = final_initial_message
        
        # Start the chat using the AG2 pattern approach - configure components
        pattern_result, final_context, last_agent = await initiate_group_chat(
            pattern=pattern,
            messages=effective_initial_message,
            max_rounds=max_turns,
            chat_id=chat_id,
            enterprise_id=enterprise_id,
            user_id=user_id,
            workflow_name=workflow_name,
            initial_message_to_user=initial_message_to_user,
            startup_mode=startup_mode
        )
        
        # Extract configured components from pattern
        manager = pattern_result["manager"]
        groupchat = pattern_result["groupchat"]
        initiating_agent = pattern_result["initiating_agent"]
        final_initial_message = pattern_result["initial_message"]
        
        business_logger.info(f"🚀 [{workflow_name_upper}] Executing AG2 GroupChat directly with configured components")
        
        # Execute the GroupChat directly using the configured manager
        if final_initial_message and final_initial_message.strip():
            result = await manager.a_initiate_chat(
                initiating_agent,
                message=final_initial_message,
                max_turns=max_turns
            )
        else:
            business_logger.warning(f"⚠️ [{workflow_name_upper}] No initial message - creating empty conversation")
            result = {"summary": "GroupChat executed without initial message"}
        
        # Wrap result for consistency
        result = {
            "status": "completed", 
            "message": "AG2 GroupChat completed successfully",
            "ag2_result": result,
            "startup_mode": startup_mode
        }
        
        chat_time = (time.time() - chat_start) * 1000
        log_performance_metric(
            metric_name="ag2_groupchat_execution_duration",
            value=chat_time,
            unit="ms",
            context={"enterprise_id": enterprise_id, "chat_id": chat_id, "startup_mode": startup_mode}
        )
        business_logger.info(f"🎉 [{workflow_name_upper}] AG2-style workflow completed in {chat_time:.2f}ms")
        business_logger.info(f"📊 [{workflow_name_upper}] Result: {result.get('status', 'unknown')}")
        
        # ===================================================================
        # TERMINATION HANDLING - Update workflow status from 0 → 1 (VE-style)
        # ===================================================================
        try:
            # Create termination handler for proper status management
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
        
        # Analytics handled by token_manager.py - no complex cost monitoring in groupchat_manager
        business_logger.info(f"✅ [{workflow_name_upper}] Analytics tracking handled by token_manager.py")


        
        log_business_event(
            event_type=f"{workflow_name_upper}_WORKFLOW_COMPLETED",
            description=f"{workflow_name} workflow orchestration completed successfully using AG2 patterns",
            context={
                "enterprise_id": enterprise_id,
                "chat_id": chat_id,
                "total_duration_seconds": (time.time() - start_time),
                "agent_count": len(agents),
                "pattern_used": orchestration_pattern,
                "result_status": result.get("status", "unknown") if isinstance(result, dict) else "completed"
            }
        )
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"❌ [{workflow_name_upper}] Workflow orchestration failed after {duration:.2f}s: {e}", exc_info=True)
        log_business_event(
            event_type=f"{workflow_name_upper}_WORKFLOW_FAILED",
            description=f"{workflow_name} workflow orchestration failed using AG2 patterns",
            context={
                "enterprise_id": enterprise_id,
                "chat_id": chat_id,
                "error": str(e),
                "duration_seconds": duration,
                "pattern_attempted": "unknown"  # Safe fallback for exception context
            },
            level="ERROR"
        )
        raise
    finally:
        # ANALYTICS CLEANUP - Ensure data is captured even on failure
        try:
            business_logger.debug(f"🧹 [{workflow_name_upper}] Analytics cleanup starting...")
            
            # Clean up AG2 streaming first
            if streaming_manager is not None:
                try:
                    streaming_manager.cleanup()
                    business_logger.info(f"✅ [{workflow_name_upper}] AG2 streaming cleanup completed")
                except Exception as streaming_cleanup_error:
                    business_logger.error(f"❌ [{workflow_name_upper}] AG2 streaming cleanup failed: {streaming_cleanup_error}")
            
            # Try to finalize analytics even if workflow failed
            token_tracker = get_token_tracker(chat_id, enterprise_id, user_id or "unknown")
            
            # If session wasn't finalized yet (due to error), try to finalize now
            if hasattr(token_tracker, 'session_usage') and not getattr(token_tracker, '_session_finalized', False):
                business_logger.info(f"🔄 [{workflow_name_upper}] Attempting emergency analytics finalization...")
                emergency_summary = await token_tracker.finalize_session()
                if emergency_summary:
                    business_logger.info(f"✅ [{workflow_name_upper}] Emergency analytics finalization successful")
                    
        except Exception as cleanup_error:
            business_logger.error(f"❌ [{workflow_name_upper}] Analytics cleanup failed: {cleanup_error}")
            
        business_logger.debug(f"🧹 [{workflow_name_upper}] Workflow cleanup completed")


# =============================================================================
# END WORKFLOW ORCHESTRATION FUNCTIONS  
# =============================================================================