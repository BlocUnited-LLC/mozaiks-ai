# ==============================================================================
# FILE: Generator/initializer.py
# DESCRIPTION: Generator initializer for the new SSE architecture
# ==============================================================================
import logging
import time
import os
from pathlib import Path
from typing import List, Callable, Optional, Dict, Any
from core.workflow.init_registry import add_initialization_coroutine, register_workflow
from core.workflow.workflow_config import WorkflowConfig
from .OrchestrationPattern import run_groupchat

# Auto-detect workflow type from directory structure
WORKFLOW_TYPE = Path(__file__).parent.name.lower()
workflow_config = WorkflowConfig()
WORKFLOW_NAME = workflow_config.get_workflow_name(WORKFLOW_TYPE)
WORKFLOW_NAME_UPPER = WORKFLOW_NAME.upper()

# Import enhanced logging
from logs.logging_config import (
    get_chat_logger,
    get_business_logger, 
    get_performance_logger,
    get_workflow_logger,
    get_component_logger,
    log_business_event,
    log_performance_metric,
    log_operation
)

# =============================================================================
# TOOL DISCOVERY AND REGISTRATION
# =============================================================================

# Get specialized loggers with dynamic names
chat_logger = get_chat_logger(f"{WORKFLOW_TYPE}_initializer")
workflow_logger = get_workflow_logger(WORKFLOW_TYPE)
component_logger = get_component_logger(f"{WORKFLOW_TYPE}_tools")
business_logger = get_business_logger(f"{WORKFLOW_TYPE}_initializer")
performance_logger = get_performance_logger(f"{WORKFLOW_TYPE}_initializer")
logger = logging.getLogger(__name__)


@add_initialization_coroutine
async def workflow_startup():
    f"""Initialize {WORKFLOW_NAME} workflow on server startup"""
    startup_start = time.time()
    
    log_business_event(
        event_type=f"{WORKFLOW_NAME_UPPER}_STARTUP_INITIATED",
        description=f"{WORKFLOW_NAME} workflow initialization started"
    )
    
    try:
        # Register export tools for the {WORKFLOW_NAME} workflow
        tools_start = time.time()
        business_logger.info(f"🪄 [{WORKFLOW_NAME_UPPER}] Initializing {WORKFLOW_NAME} workflow...")
        
        # --- DYNAMIC TOOL DISCOVERY ---
        # Critical: GroupchatTools (like on_start hooks) must be discovered at startup
        # so they're available when group chats are created. AgentTools can be discovered
        # later during workflow execution.
        
        from pathlib import Path
        from .Hooks import discover_all_tools
        
        business_logger.info(f"🔧 [{WORKFLOW_NAME_UPPER}] Pre-discovering GroupchatTools for group chat initialization...")
        
        # Discover tools early 
        workflow_dir = Path(__file__).parent
        all_tools = discover_all_tools()
        groupchat_tools = all_tools.get("GroupchatTools", {})
        
        business_logger.info(f"🔍 [{WORKFLOW_NAME_UPPER}] Pre-discovered {len(groupchat_tools)} GroupchatTools: {list(groupchat_tools.keys())}")
        
        # Register the GroupchatTools globally so they're available when group chats start
        # This ensures on_start hooks are registered before OrchestrationPattern runs
        if groupchat_tools:
            # Extract the actual functions from the tool info dictionaries
            groupchat_functions = [tool_info["func"] for tool_info in groupchat_tools.values()]
            
            # Store the discovered tools in the registry for later use
            from core.workflow.init_registry import register_workflow_tools
            register_workflow_tools(WORKFLOW_TYPE, groupchat_functions)
            business_logger.info(f"✅ [{WORKFLOW_NAME_UPPER}] Pre-registered {len(groupchat_functions)} GroupchatTools for early group chat hook setup")
        
        business_logger.info(f"🔧 [{WORKFLOW_NAME_UPPER}] AgentTools discovery will occur during workflow execution via OrchestrationPattern")

        tools_time = (time.time() - tools_start) * 1000
        log_performance_metric(
            metric_name="tool_registration_duration",
            value=tools_time,
            unit="ms",
            context={"workflow_type": WORKFLOW_TYPE}
        )
        
        business_logger.info(f"🔧 [{WORKFLOW_NAME_UPPER}] Tool registration completed ({tools_time:.1f}ms)")

        # Log successful startup
        startup_time = (time.time() - startup_start) * 1000
        log_performance_metric(
            metric_name=f"{WORKFLOW_TYPE}_startup_duration",
            value=startup_time,
            unit="ms"
        )
        
        log_business_event(
            event_type=f"{WORKFLOW_NAME_UPPER}_STARTUP_COMPLETED",
            description=f"{WORKFLOW_NAME} workflow initialization completed successfully",
            context={
                "startup_time_ms": startup_time
            }
        )
        
        business_logger.info(f"✅ [{WORKFLOW_NAME_UPPER}] {WORKFLOW_NAME} workflow initialized ({startup_time:.1f}ms)")

    except Exception as e:
        startup_time = (time.time() - startup_start) * 1000
        
        log_business_event(
            event_type=f"{WORKFLOW_NAME_UPPER}_STARTUP_FAILED",
            description=f"{WORKFLOW_NAME} workflow initialization failed",
            context={
                "error": str(e),
                "startup_time_ms": startup_time
            },
            level="ERROR"
        )
        
        business_logger.error(f"❌ [{WORKFLOW_NAME_UPPER}] {WORKFLOW_NAME} startup failed after {startup_time:.1f}ms: {e}")
        raise

@register_workflow(WORKFLOW_TYPE, human_loop=True, transport="sse")
async def run_workflow(
    enterprise_id: str, 
    chat_id: str, 
    user_id: str, 
    initial_message: str, 
    communication_channel=None  # Required unified transport parameter
):
    """
    Runs the {WORKFLOW_NAME} workflow with unified transport support.
    
    Args:
        enterprise_id: Enterprise identifier
        chat_id: Chat identifier
        user_id: User identifier  
        initial_message: Initial message from user
        communication_channel: Unified transport channel (required)
    """
    workflow_start = time.time()
    
    # communication_channel is required
    if not communication_channel:
        raise ValueError(f"communication_channel is required for {WORKFLOW_NAME} workflow")
        
    # Notify that the workflow has started
    log_business_event(
        event_type=f"{WORKFLOW_NAME_UPPER}_WORKFLOW_STARTED",
        description=f"{WORKFLOW_NAME} workflow execution started with unified transport",
        context={
            "enterprise_id": enterprise_id, 
            "chat_id": chat_id, 
            "user_id": user_id, 
            "initial_message_provided": initial_message is not None,
            "transport_type": "unified"
        }
    )
    
    try:
        with log_operation(workflow_logger, f"{WORKFLOW_TYPE}_workflow_execution", 
                         enterprise_id=enterprise_id, chat_id=chat_id, user_id=user_id):
            
            business_logger.info(f"🚀 [{WORKFLOW_NAME_UPPER}] Running workflow for Enterprise: {enterprise_id}, Chat: {chat_id}")
            
            # Use default LLM configuration from the communication channel
            if hasattr(communication_channel, 'default_llm_config'):
                llm_config = communication_channel.default_llm_config
                workflow_logger.info("Using transport-provided LLM config", extra={
                    "config_source": "communication_channel",
                    "has_config": True
                })
            else:
                # Fallback: create a basic config if transport doesn't provide one
                workflow_logger.warning("Transport channel missing LLM config, creating fallback", extra={
                    "config_source": "fallback",
                    "channel_type": type(communication_channel).__name__
                })
                from core.core_config import make_streaming_config
                _, llm_config = await make_streaming_config()
            
            business_logger.debug(f"🔧 [{WORKFLOW_NAME_UPPER}] Using LLM config: {llm_config}")
            
            # Execute the group chat orchestration
            await run_groupchat(
                llm_config=llm_config,
                enterprise_id=enterprise_id,
                chat_id=chat_id,
                user_id=user_id,
                initial_message=initial_message,
                communication_channel=communication_channel  # Use unified transport channel
            )
        
        # Measure and log duration
        workflow_duration = (time.time() - workflow_start) * 1000
        log_performance_metric(
            metric_name=f"{WORKFLOW_TYPE}_workflow_duration",
            value=workflow_duration,
            unit="ms",
            context={"enterprise_id": enterprise_id, "chat_id": chat_id}
        )
        log_business_event(
            event_type=f"{WORKFLOW_NAME_UPPER}_WORKFLOW_COMPLETED",
            description=f"{WORKFLOW_NAME} workflow completed successfully",
            context={"enterprise_id": enterprise_id, "chat_id": chat_id, "duration_ms": workflow_duration}
        )
        business_logger.info(f"✅ [{WORKFLOW_NAME_UPPER}] Workflow completed for Chat: {chat_id} ({workflow_duration:.1f}ms)")
        
    except Exception as e:
        workflow_duration = (time.time() - workflow_start) * 1000
        log_business_event(
            event_type=f"{WORKFLOW_NAME_UPPER}_WORKFLOW_FAILED",
            description=f"{WORKFLOW_NAME} workflow execution failed",
            context={"enterprise_id": enterprise_id, "chat_id": chat_id, "error": str(e), "duration_ms": workflow_duration},
            level="ERROR"
        )
        business_logger.error(f"❌ [{WORKFLOW_NAME_UPPER}] Workflow failed for Chat: {chat_id}: {e}", exc_info=True)
        raise

