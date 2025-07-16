# ==============================================================================
# FILE: Generator/OrchestrationPattern.py
# DESCRIPTION: AG2 orchestration with modular handoffs and hooks
# ==============================================================================
import time
import logging

from core.workflow.groupchat_manager import start_or_resume_group_chat, create_enhanced_group_chat_manager
from .Agents import define_agents
from .ContextVariables import get_context
from .Handoffs import wire_handoffs
from .Hooks import wire_hooks, discover_all_tools, register_agent_tools, register_groupchat_hooks
logger = logging.getLogger(__name__)
from core.data.persistence_manager import persistence_manager as mongodb_manager
import logging
import time

# AG2 logging setup
import autogen
from autogen import runtime_logging

# Import enhanced logging
from logs.logging_config import (
    get_business_logger,
    get_chat_logger,
    get_performance_logger,
    log_business_event,
    log_performance_metric
)

# Use dynamic workflow name for consistent logging
def get_workflow_context():
    """Get workflow context from configuration"""
    workflow_name = WORKFLOW_CONFIG["workflow_type"]
    return workflow_name.lower(), workflow_name.upper()

# We'll initialize loggers after WORKFLOW_CONFIG is available
logger = logging.getLogger(__name__)

# Dynamic configuration from workflow.json
from core.workflow.workflow_config import workflow_config

def get_workflow_config():
    """Get workflow configuration - determines workflow type dynamically from file location"""
    from pathlib import Path
    
    # Auto-detect workflow type from the current file's parent directory
    current_file = Path(__file__)
    workflow_type = current_file.parent.name.lower()  # Gets "generator" from "Generator" folder
    
    return {
        "workflow_type": workflow_config.get_workflow_name(workflow_type),
        "max_turns": workflow_config.get_max_turns(workflow_type),
        "initiating_agent": workflow_config.get_initiating_agent(workflow_type)
    }

WORKFLOW_CONFIG = get_workflow_config()
WORKFLOW_MAX_TURNS = WORKFLOW_CONFIG["max_turns"]  # Dynamic max turns from workflow.json

# Initialize loggers with dynamic workflow name (now that WORKFLOW_CONFIG is available)
workflow_name_lower = WORKFLOW_CONFIG["workflow_type"].lower()
workflow_name_upper = WORKFLOW_CONFIG["workflow_type"].upper()
business_logger = get_business_logger(f"{workflow_name_lower}_orchestration")
chat_logger = get_chat_logger(f"{workflow_name_lower}_orchestration")
performance_logger = get_performance_logger(f"{workflow_name_lower}_orchestration")
wlog = business_logger  # Use business_logger as the primary workflow logger

async def run_groupchat(
    llm_config, 
    enterprise_id, 
    chat_id, 
    user_id=None, 
    initial_message=None, 
    communication_channel=None  # Required unified transport parameter
):
    """
    Run the Generator group chat with unified transport support.
    
    Args:
        llm_config: LLM configuration
        enterprise_id: Enterprise identifier
        chat_id: Chat identifier  
        user_id: User identifier (optional)
        initial_message: Initial message (optional)
        communication_channel: Unified transport channel (SSE or WebSocket) - Required
    """
    
    if not communication_channel:
        raise ValueError(f"communication_channel is required for {WORKFLOW_CONFIG['workflow_type']} workflow")
    
    start_time = time.time()
    workflow_name = WORKFLOW_CONFIG["workflow_type"]  # Define workflow_name early for error logging
    
    log_business_event(
        event_type=f"{workflow_name.upper()}_GROUPCHAT_STARTED",
        description=f"{workflow_name} groupchat with unified transport initialized",
        context={
            "enterprise_id": enterprise_id,
            "chat_id": chat_id,
            "user_id": user_id,
            "initial_message_provided": initial_message is not None
        }
    )
    
    try:
        wlog.info(f"Workflow max turns: {WORKFLOW_MAX_TURNS}")
        
        # Temporarily disable AG2 runtime logging to avoid ModelMetaclass serialization issues
        # We can re-enable this later with proper configuration
        logging_session_id = f"{workflow_name}_{chat_id}_{int(time.time())}"
        wlog.info(f"AG2 runtime logging disabled temporarily to avoid serialization issues: {logging_session_id}")

        # 1. Load concept from database
        concept_start = time.time()
        wlog.debug("Loading concept data...")
        
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
            wlog.info(f"Concept loaded: {concept_data.get('ConceptCode', 'unknown')}")
        else:
            wlog.warning("No concept data found")

        # 2. Build context
        wlog.debug("Building context...")
        context = get_context(concept_data)
        wlog.debug(f"Context variables: {list(context.data.keys()) if hasattr(context, 'data') else 'unknown'}")

        # 3. Dynamic Tool Discovery and Registration
        wlog.info("Discovering and registering tools...")
        tools_start = time.time()
        
        # Discover AgentTools (GroupchatTools were pre-discovered at startup)
        all_tools = discover_all_tools()
        agent_tools = all_tools.get("AgentTools", {})
        
        # GroupchatTools were already discovered and registered at server startup
        # This ensures on_start hooks are available before group chat creation
        groupchat_tools = all_tools.get("GroupchatTools", {})
        
        business_logger.info(f"🔍 [{workflow_name_upper}] Discovered {len(agent_tools)} agent tools, using {len(groupchat_tools)} pre-registered groupchat tools")
        
        tools_discovery_time = (time.time() - tools_start) * 1000
        log_performance_metric(
            metric_name="tools_discovery_duration",
            value=tools_discovery_time,
            unit="ms",
            context={
                "agent_tools_count": len(agent_tools),
                "groupchat_tools_count": len(groupchat_tools),
                "groupchat_tools_preregistered": True
            }
        )

        # 4. Define modular workflow: handoffs and hooks
        business_logger.info(f"⚙️ [{workflow_name_upper}] Defining modular workflow...")
        business_logger.debug(f"🔗 [{workflow_name_upper}] Handoff flow will be configured directly in wire_handoffs()")
        
        # Define hooks to be registered on agents (workflow-specific only)
        hooks_config = {}
        business_logger.info(f"🪝 [{workflow_name_upper}] Hooks configuration prepared")

        # 5. Define agents, passing the hooks for registration
        agents_start = time.time()
        business_logger.debug(f"🤖 [{workflow_name_upper}] Defining agents...")
        
        agents, group_chat_manager = await define_agents(
            base_llm_config=llm_config
        )
        
        agents_build_time = (time.time() - agents_start) * 1000
        log_performance_metric(
            metric_name="agents_definition_duration", 
            value=agents_build_time,
            unit="ms",
            context={"enterprise_id": enterprise_id, "agent_count": len(agents)}
        )
        business_logger.info(f"✅ [{workflow_name_upper}] Agents defined: {len(agents)} total")

        # 6. Register discovered tools dynamically
        tools_registration_start = time.time()
        
        # Enhance the group chat manager with hook registration capabilities
        enhanced_manager = create_enhanced_group_chat_manager(group_chat_manager, chat_id, enterprise_id)
        
        # Register agent tools based on APPLY_TO metadata
        register_agent_tools(agents, agent_tools)
        
        # Register groupchat hooks based on TRIGGER/TRIGGER_AGENT metadata
        register_groupchat_hooks(enhanced_manager, groupchat_tools)
        
        tools_registration_time = (time.time() - tools_registration_start) * 1000
        log_performance_metric(
            metric_name="tools_registration_duration",
            value=tools_registration_time,
            unit="ms",
            context={
                "agent_tools_registered": len(agent_tools),
                "groupchat_hooks_registered": len(groupchat_tools)
            }
        )
        business_logger.info(f"✅ [{workflow_name_upper}] Tools registered: {len(agent_tools)} agent tools, {len(groupchat_tools)} groupchat hooks")

        # 7. Wire handoffs and hooks
        wire_handoffs(agents)
        wire_hooks(agents, hooks_config)

        # 8. Start or resume chat via core helper
        chat_start = time.time()
        
        # Always start with the configured initiating agent - this is the correct AG2 pattern
        # The user's initial_message will be injected into the conversation flow
        initiating_agent_name = WORKFLOW_CONFIG["initiating_agent"]
        initiating_agent = agents.get(initiating_agent_name)
        if not initiating_agent:
            raise ValueError(f"Critical: {initiating_agent_name} not found, cannot initiate workflow.")
        
        # Load dynamic initial message from workflow.json
        try:
            # Use the same auto-detected workflow type
            from pathlib import Path
            workflow_type_for_config = Path(__file__).parent.name.lower()
            
            workflow_initial_message = workflow_config.get_initial_message(workflow_type_for_config)
            if workflow_initial_message:
                business_logger.info(f"🎯 [{workflow_name_upper}] Using system-led navigator message from workflow.json")
            else:
                business_logger.info(f"🎯 [{workflow_name_upper}] No initial message configured, using auto-start mode")
                workflow_initial_message = None
        except Exception as e:
            business_logger.error(f"❌ [{workflow_name_upper}] Failed to load initial message from workflow.json: {e}")
            workflow_initial_message = None
        
        # Use passed initial_message if workflow config doesn't have one, or fallback to generic prompt
        final_initial_message = workflow_initial_message or initial_message
        
        # If still no message, provide a generic fallback that tells agents to proceed
        if not final_initial_message:
            final_initial_message = "You have been tasked with an assignment. Please proceed per your instructions in your system message within the context of the context_variables."
        
        # Log the approach based on final message
        if workflow_initial_message:
            business_logger.info(f"🎯 [{workflow_name_upper}] Starting with {initiating_agent_name} (system-led navigator mode)")
        elif initial_message:
            business_logger.info(f"🎯 [{workflow_name_upper}] Starting with {initiating_agent_name} (user-provided message)")
        else:
            business_logger.info(f"🎯 [{workflow_name_upper}] Starting with {initiating_agent_name} (generic fallback prompt)")

        await start_or_resume_group_chat(
            manager=enhanced_manager,
            initiating_agent=initiating_agent,
            chat_id=chat_id,
            enterprise_id=enterprise_id,
            user_id=user_id,
            initial_message=final_initial_message,  # Use workflow.json message or passed parameter
            max_turns=WORKFLOW_MAX_TURNS,  # Dynamic max_turns from workflow.json
            workflow_type=WORKFLOW_CONFIG["workflow_type"],  # Dynamic workflow type from workflow.json
            communication_channel=communication_channel  # Use unified transport channel
        )
        
        chat_time = (time.time() - chat_start) * 1000
        
        log_performance_metric(
            metric_name="groupchat_execution_duration",
            value=chat_time,
            unit="ms",
            context={"enterprise_id": enterprise_id, "chat_id": chat_id}
        )
        
        chat_logger.info(f"🎉 [{workflow_name_upper}] Async group chat completed in {chat_time:.2f}ms")
        
        log_business_event(
            event_type=f"{workflow_name.upper()}_GROUPCHAT_COMPLETED",
            description=f"{workflow_name} groupchat with modular workflow completed successfully",
            context={
                "enterprise_id": enterprise_id,
                "chat_id": chat_id,
                "total_duration_seconds": (time.time() - start_time),
                "agent_count": len(agents)
            }
        )
        
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"❌ [{workflow_name.upper()}] Async groupchat failed after {duration:.2f}s: {e}", exc_info=True)
        log_business_event(
            event_type=f"{workflow_name.upper()}_GROUPCHAT_FAILED",
            description=f"{workflow_name} groupchat execution failed",
            context={
                "enterprise_id": enterprise_id,
                "chat_id": chat_id,
                "error": str(e),
                "duration_seconds": duration
            },
            level="ERROR"
        )
        raise
    finally:
        # AG2 logging cleanup (currently disabled)
        chat_logger.info(f"📄 [{workflow_name.upper()}] AG2 runtime logging cleanup (currently disabled)")