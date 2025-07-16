# ==============================================================================
# FILE: Generator/Hooks.py
# DESCRIPTION: Simple tool discovery and wiring for AG2 Generator workflow
# ==============================================================================

from __future__ import annotations
import logging
import time
from pathlib import Path
from typing import Any, Callable, Dict, List

from logs.logging_config import (
    get_business_logger,
    get_performance_logger,
    log_performance_metric,
)

# Dynamic configuration from workflow.json
from core.workflow.workflow_config import workflow_config
from pathlib import Path

# Auto-detect workflow type from current file's parent directory
WORKFLOW_TYPE = Path(__file__).parent.name.lower()  # Gets "generator" from "Generator" folder
WORKFLOW_NAME = workflow_config.get_workflow_name(WORKFLOW_TYPE).lower()

business_logger    = get_business_logger(f"{WORKFLOW_NAME}_hooks")
performance_logger = get_performance_logger(f"{WORKFLOW_NAME}_hooks")
logger             = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
#  Manifest-based tool discovery                                              #
# --------------------------------------------------------------------------- #
def discover_all_tools() -> Dict[str, Dict[str, Dict[str, Any]]]:
    """
    Load tools from workflow.json instead of separate manifest - much simpler approach.
    Returns {"AgentTools": {...}, "GroupchatTools": {...}} with tool metadata.
    """
    try:
        from .simple_tool_loader import load_tools_from_workflow
        
        tools = load_tools_from_workflow(WORKFLOW_TYPE)
        
        # Convert to old format for backwards compatibility
        agent_tools = {tool["name"]: tool for tool in tools["agent_tools"]}
        groupchat_tools = {hook["name"]: hook for hook in tools["lifecycle_hooks"]}
        
        business_logger.info(f"✅ Loaded {len(agent_tools)} agent tools and {len(groupchat_tools)} groupchat tools from workflow.json")
        
        return {
            "AgentTools": agent_tools,
            "GroupchatTools": groupchat_tools,
        }
        
    except Exception as e:
        business_logger.error(f"❌ [HOOKS] Failed to discover tools: {e}")
        return {"AgentTools": {}, "GroupchatTools": {}}


def register_agent_tools(agents: Dict[str, Any], agent_tools: Dict[str, Dict[str, Any]]) -> None:
    """
    Register agent tools based on manifest apply_to metadata.
    """
    business_logger.debug(f"🔧 register_agent_tools called with {len(agent_tools)} tools")
    
    for tool_name, tool_info in agent_tools.items():
        business_logger.debug(f"🔧 Processing tool {tool_name}")
        
        if not tool_info.get("enabled", True):
            business_logger.info(f"Skipping disabled tool {tool_name}")
            continue
            
        func = tool_info.get("function_obj")  # Updated to use function_obj
        apply_to = tool_info.get("apply_to")
        
        business_logger.debug(f"🔧 Tool {tool_name}: func={type(func)}, apply_to={apply_to}")
        
        if func is None:
            business_logger.error(f"Tool {tool_name} has no function_obj - tool may have failed to load")
            continue
            
        if not callable(func):
            business_logger.error(f"Tool {tool_name} function_obj is not callable: {type(func)}")
            continue
        
        if not apply_to:
            business_logger.warning(f"Tool {tool_name} has no apply_to metadata, skipping")
            continue
            
        # Handle "all" case
        if apply_to == "all":
            target_agents = list(agents.keys())
        elif isinstance(apply_to, list):
            target_agents = apply_to
        else:
            target_agents = [apply_to]
            
        # Register tool on target agents
        for agent_name in target_agents:
            agent = agents.get(agent_name)
            if not agent:
                business_logger.warning(f"Agent '{agent_name}' not found for tool {tool_name}")
                continue
                
            # Skip agents without LLM config (e.g., user agents)
            if hasattr(agent, 'llm_config') and agent.llm_config is False:
                business_logger.debug(f"Skipping tool registration for {tool_name} on {agent_name} - agent has no LLM config")
                continue
                
            try:
                # Try a different approach - skip update_tool_signature for now and just use register_for_execution
                if hasattr(agent, "register_for_execution"):
                    # Use register_for_execution which is simpler and more reliable
                    agent.register_for_execution(tool_name)(func)
                    business_logger.info(f"🔧 Registered tool {tool_name} on agent {agent_name} (register_for_execution)")
                elif hasattr(agent, "_function_map"):
                    # Direct function map registration as fallback
                    agent._function_map[tool_name] = func
                    business_logger.info(f"🔧 Registered tool {tool_name} directly on agent {agent_name}")
                else:
                    # Skip tool registration for now to avoid errors
                    business_logger.warning(f"Skipping tool registration for {tool_name} on {agent_name} - no compatible method found")
            except Exception as e:
                business_logger.error(f"Failed to register tool {tool_name} on agent {agent_name}: {type(e).__name__}: {e}")
                business_logger.error(f"Tool info: {tool_info}")
                business_logger.error(f"Agent info: name={agent_name}, type={type(agent)}, hasattr(update_tool_signature)={hasattr(agent, 'update_tool_signature')}")
                import traceback
                business_logger.error(f"Full traceback:\n{traceback.format_exc()}")


def register_groupchat_hooks(group_chat_manager: Any, groupchat_tools: Dict[str, Dict[str, Any]]) -> None:
    """
    Register group chat hooks based on manifest trigger metadata.
    """
    for tool_name, tool_info in groupchat_tools.items():
        if not tool_info.get("enabled", True):
            business_logger.info(f"Skipping disabled groupchat tool {tool_name}")
            continue
            
        func = tool_info.get("function_obj")  # Updated to use function_obj
        trigger = tool_info.get("trigger")
        trigger_agent = tool_info.get("trigger_agent")
        
        try:
            if trigger == "after_each_agent":
                # Register for after each agent message
                if hasattr(group_chat_manager, "register_hook"):
                    group_chat_manager.register_hook("after_each_agent", func)
                    business_logger.info(f"🪝 Registered hook {tool_name} for after_each_agent")
                    
            elif trigger == "on_end":
                # Register for group chat end
                if hasattr(group_chat_manager, "register_hook"):
                    group_chat_manager.register_hook("on_end", func)
                    business_logger.info(f"🪝 Registered hook {tool_name} for on_end")
                    
            elif trigger == "on_start":
                # Register for group chat start
                if hasattr(group_chat_manager, "register_hook"):
                    group_chat_manager.register_hook("on_start", func)
                    business_logger.info(f"🪝 Registered hook {tool_name} for on_start")
                    
            elif trigger_agent:
                # Register for specific agent
                if hasattr(group_chat_manager, "register_agent_hook"):
                    group_chat_manager.register_agent_hook(trigger_agent, func)
                    business_logger.info(f"🪝 Registered hook {tool_name} for agent {trigger_agent}")
                elif hasattr(group_chat_manager, "register_hook"):
                    # Fallback: register with agent filter
                    def create_agent_filtered_hook(target_func, target_agent):
                        def agent_filtered_hook(manager, message_history):
                            if message_history and message_history[-1].get("sender") == target_agent:
                                return target_func(manager, message_history)
                        return agent_filtered_hook
                    
                    filtered_hook = create_agent_filtered_hook(func, trigger_agent)
                    group_chat_manager.register_hook("after_each_agent", filtered_hook)
                    business_logger.info(f"🪝 Registered filtered hook {tool_name} for agent {trigger_agent}")
            else:
                business_logger.warning(f"Hook {tool_name} has no valid trigger or trigger_agent metadata")
                
        except Exception as e:
            logger.error(f"Failed to register hook {tool_name}: {e}")

# --------------------------------------------------------------------------- #
#  Hook wiring utility                                                        #
# --------------------------------------------------------------------------- #
def wire_hooks(
    agents: Dict[str, Any],
    hooks_config: Dict[str, Dict[str, List[Callable]]],
) -> None:
    """
    hooks_config format:
    {
        "AgentName": {
            "<hook_type>": [func1, func2, ...],
            ...
        },
        ...
    }
    """
    t0 = time.time()
    for agent_name, hook_map in hooks_config.items():
        agent = agents.get(agent_name)
        if not agent:
            business_logger.warning(f"⚠️  Agent '{agent_name}' not found; skipping hooks")
            continue
        for hook_type, funcs in hook_map.items():
            for func in funcs:
                try:
                    if hasattr(agent, "register_hook"):
                        agent.register_hook(hook_type, func)
                        business_logger.debug(f"🪝 Registered {hook_type} on {agent_name}")
                except Exception as e:
                    logger.error("Failed to register %s on %s: %s", hook_type, agent_name, e)

    ms = (time.time() - t0) * 1000
    log_performance_metric(
        metric_name="total_hook_wiring_duration",
        value=ms,
        unit="ms",
        context={"agent_count": len(agents)},
    )
    business_logger.info(f"🎉 Hook wiring completed in {ms:.1f} ms")
