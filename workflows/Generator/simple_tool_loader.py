# ==============================================================================
# FILE: workflows/Generator/simple_tool_loader.py
# DESCRIPTION: Simple tool loader that reads from workflow.json
# ==============================================================================

import importlib
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path
from core.workflow.workflow_config import workflow_config

# Import enhanced logging
from logs.logging_config import (
    get_business_logger,
    get_performance_logger,
    log_performance_metric,
)

# Auto-detect workflow for logging context
WORKFLOW_TYPE = Path(__file__).parent.name.lower()
WORKFLOW_NAME = workflow_config.get_workflow_name(WORKFLOW_TYPE).lower()

business_logger = get_business_logger(f"{WORKFLOW_NAME}_tool_loader")
performance_logger = get_performance_logger(f"{WORKFLOW_NAME}_tool_loader")
logger = logging.getLogger(__name__)

def load_tools_from_workflow(workflow_type: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]:
    """
    Load tools directly from workflow.json - much simpler than the old manifest system.
    
    Args:
        workflow_type: Workflow type to load. If None, auto-detects from file location.
        
    Returns:
        Dictionary with 'agent_tools' and 'lifecycle_hooks' lists
    """
    try:
        # Auto-detect workflow type if not provided
        if workflow_type is None:
            from pathlib import Path
            workflow_type = Path(__file__).parent.name.lower()
            
        from core.workflow.workflow_config import workflow_config
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
                module = importlib.import_module(hook["module"])
                hook["function_obj"] = getattr(module, hook["function"])
            except Exception as e:
                business_logger.error(f"Failed to import lifecycle hook {hook['name']}: {e}")
                hook["enabled"] = False
        
        business_logger.info(f"✅ Loaded {len(agent_tools)} agent tools and {len(lifecycle_hooks)} lifecycle hooks from workflow.json")
        
        return {
            "agent_tools": [t for t in agent_tools if t.get("enabled", True)],
            "lifecycle_hooks": [h for h in lifecycle_hooks if h.get("enabled", True)]
        }
        
    except Exception as e:
        business_logger.error(f"Failed to load tools from workflow.json: {e}")
        return {"agent_tools": [], "lifecycle_hooks": []}


def register_agent_tools(agents: Dict[str, Any], agent_tools: List[Dict[str, Any]]):
    """Register agent tools with specific agents based on apply_to configuration"""
    for tool in agent_tools:
        if not tool.get("enabled", True) or "function_obj" not in tool:
            continue
            
        apply_to = tool.get("apply_to", [])
        tool_name = tool.get("name")
        tool_func = tool["function_obj"]
        
        if apply_to == "all":
            # Register on all agents
            for agent in agents.values():
                if hasattr(agent, 'register_tool'):
                    agent.register_tool(name=tool_name, func=tool_func)
        elif isinstance(apply_to, list):
            # Register on specific agents
            for agent_name in apply_to:
                if agent_name in agents and hasattr(agents[agent_name], 'register_tool'):
                    agents[agent_name].register_tool(name=tool_name, func=tool_func)
        elif isinstance(apply_to, str) and apply_to in agents:
            # Register on single specific agent
            if hasattr(agents[apply_to], 'register_tool'):
                agents[apply_to].register_tool(name=tool_name, func=tool_func)
        
        business_logger.info(f"🔧 Registered agent tool: {tool_name} -> {apply_to}")


def register_lifecycle_hooks(manager: Any, lifecycle_hooks: List[Dict[str, Any]]):
    """Register lifecycle hooks with the group chat manager"""
    for hook in lifecycle_hooks:
        if not hook.get("enabled", True) or "function_obj" not in hook:
            continue
            
        trigger = hook.get("trigger")
        hook_name = hook.get("name")
        hook_func = hook["function_obj"]
        
        if hasattr(manager, 'register_hook'):
            manager.register_hook(trigger, hook_func)
            business_logger.info(f"🪝 Registered lifecycle hook: {hook_name} -> {trigger}")
