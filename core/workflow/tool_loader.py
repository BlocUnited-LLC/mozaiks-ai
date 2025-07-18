# ==============================================================================
# FILE: core/workflow/tool_loader.py
# DESCRIPTION: Universal tool loader that reads from workflow.json configurations
# ==============================================================================

import importlib
import logging
from typing import Dict, Any, List, Optional
from core.workflow.workflow_config import workflow_config

# Import enhanced logging
from logs.logging_config import (
    get_business_logger,
    get_performance_logger,
    log_performance_metric,
)

logger = logging.getLogger(__name__)

def load_tools_from_workflow(workflow_type: str) -> Dict[str, List[Dict[str, Any]]]:
    """
    Load tools directly from workflow.json - universal tool loading for all workflows.
    
    Args:
        workflow_type: Workflow type to load (e.g., 'generator', 'analyzer')
        
    Returns:
        Dictionary with 'agent_tools' and 'lifecycle_hooks' lists
    """
    try:
        # Get business logger for this specific workflow
        business_logger = get_business_logger(f"{workflow_type}_tool_loader")
        
        agent_tools = workflow_config.get_enabled_agent_tools(workflow_type)
        lifecycle_hooks = workflow_config.get_enabled_lifecycle_hooks(workflow_type)
        
        # Dynamically import and attach the actual functions
        for tool in agent_tools:
            try:
                if "module" not in tool:
                    business_logger.error(f"Tool {tool.get('name', 'unknown')} missing 'module' field")
                    tool["enabled"] = False
                    continue
                    
                if "function" not in tool:
                    business_logger.error(f"Tool {tool.get('name', 'unknown')} missing 'function' field")
                    tool["enabled"] = False
                    continue
                
                module = importlib.import_module(tool["module"])
                if not hasattr(module, tool["function"]):
                    business_logger.error(f"Function '{tool['function']}' not found in module '{tool['module']}'")
                    tool["enabled"] = False
                    continue
                    
                tool["function_obj"] = getattr(module, tool["function"])
                business_logger.debug(f"✅ Successfully loaded tool {tool['name']} from {tool['module']}.{tool['function']}")
            except Exception as e:
                business_logger.error(f"Failed to import agent tool {tool.get('name', 'unknown')}: {e}")
                business_logger.error(f"Tool config: {tool}")
                tool["enabled"] = False
        
        for hook in lifecycle_hooks:
            try:
                if "module" not in hook or "function" not in hook:
                    business_logger.error(f"Hook {hook.get('name', 'unknown')} missing module or function field")
                    hook["enabled"] = False
                    continue
                    
                module = importlib.import_module(hook["module"])
                if not hasattr(module, hook["function"]):
                    business_logger.error(f"Function '{hook['function']}' not found in module '{hook['module']}'")
                    hook["enabled"] = False
                    continue
                    
                hook["function_obj"] = getattr(module, hook["function"])
                business_logger.debug(f"✅ Successfully loaded hook {hook['name']} from {hook['module']}.{hook['function']}")
            except Exception as e:
                business_logger.error(f"Failed to import lifecycle hook {hook.get('name', 'unknown')}: {e}")
                hook["enabled"] = False
        
        business_logger.info(f"✅ Loaded {len(agent_tools)} agent tools and {len(lifecycle_hooks)} lifecycle hooks from workflow.json")
        
        return {
            "agent_tools": [t for t in agent_tools if t.get("enabled", True)],
            "lifecycle_hooks": [h for h in lifecycle_hooks if h.get("enabled", True)]
        }
        
    except Exception as e:
        logger.error(f"Failed to load tools from workflow.json for {workflow_type}: {e}")
        return {"agent_tools": [], "lifecycle_hooks": []}


def register_agent_tools(agents: Dict[str, Any], agent_tools: List[Dict[str, Any]], workflow_type: str = "unknown"):
    """Register agent tools with specific agents based on apply_to configuration"""
    business_logger = get_business_logger(f"{workflow_type}_tool_loader")
    
    for tool in agent_tools:
        if not tool.get("enabled", True) or "function_obj" not in tool:
            continue
            
        apply_to = tool.get("apply_to", [])
        tool_name = tool.get("name")
        tool_func = tool["function_obj"]
        
        # Get list of target agents
        target_agents = []
        if apply_to == "all":
            target_agents = list(agents.values())
        elif isinstance(apply_to, list):
            target_agents = [agents[name] for name in apply_to if name in agents]
        elif isinstance(apply_to, str) and apply_to in agents:
            target_agents = [agents[apply_to]]
        
        # Register with AG2's proper methods
        for agent in target_agents:
            try:
                # Register for execution (makes function callable)
                agent.register_for_execution(name=tool_name)(tool_func)
                # Register for LLM (makes function available to LLM)
                agent.register_for_llm(name=tool_name, description=tool.get("description", ""))(tool_func)
                business_logger.info(f"🔧 Registered AG2 tool: {tool_name} -> {agent.name}")
            except Exception as e:
                business_logger.error(f"Failed to register tool {tool_name} with agent {agent.name}: {e}")


def register_lifecycle_hooks(agents: Dict[str, Any], lifecycle_hooks: List[Dict[str, Any]], workflow_type: str = "unknown"):
    """Register lifecycle hooks with agents using AG2's register_hook method"""
    business_logger = get_business_logger(f"{workflow_type}_tool_loader")
    
    for hook in lifecycle_hooks:
        if not hook.get("enabled", True) or "function_obj" not in hook:
            continue
            
        trigger = hook.get("trigger")
        hook_name = hook.get("name")
        hook_func = hook["function_obj"]
        apply_to = hook.get("apply_to", [])
        
        # Skip if trigger is None
        if trigger is None:
            business_logger.error(f"Hook {hook_name} has no trigger defined")
            continue
        
        # Map workflow.json trigger names to AG2 hook names
        ag2_hook_mapping = {
            "process_last_received_message": "process_last_received_message",
            "process_all_messages_before_reply": "process_all_messages_before_reply", 
            "process_message_before_send": "process_message_before_send",
            "update_agent_state": "update_agent_state"
        }
        
        ag2_hook_name = ag2_hook_mapping.get(trigger, trigger)
        
        # Get list of target agents
        target_agents = []
        if apply_to == "all":
            target_agents = list(agents.values())
        elif isinstance(apply_to, list):
            target_agents = [agents[name] for name in apply_to if name in agents]
        elif isinstance(apply_to, str) and apply_to in agents:
            target_agents = [agents[apply_to]]
        
        # Register hooks with AG2's proper methods
        for agent in target_agents:
            try:
                agent.register_hook(ag2_hook_name, hook_func)
                business_logger.info(f"🪝 Registered AG2 hook: {hook_name} ({ag2_hook_name}) -> {agent.name}")
            except Exception as e:
                business_logger.error(f"Failed to register hook {hook_name} with agent {agent.name}: {e}")
