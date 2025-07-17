"""
Unified Tool Registry for AG2-Compatible Tool Discovery & Registration
Supports both workflow.json configuration and AG2 module-level variables for maximum compatibility
"""

import logging
import importlib
from pathlib import Path
from typing import List, Dict, Any, Callable
from .workflow_config import workflow_config

logger = logging.getLogger(__name__)
biz_log = logging.getLogger("business.tool_loader")

class UnifiedToolRegistry:
    """
    Unified tool registry that supports both AG2-compatible module-level variables
    and workflow.json configuration for clean, centralized tool management.
    """
    
    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.registered_tools = {}
    
    def discover_workflow_tools(self, workflow_type: str) -> Dict[str, Dict[str, Any]]:
        """
        Discover all tools for a workflow using both approaches:
        1. workflow.json configuration (preferred for centralized management)
        2. AG2 module-level variables (for AG2 compatibility)
        
        Returns:
            Dict with structure: {
                "agent_tools": {tool_name: tool_config_with_function_obj, ...},
                "lifecycle_hooks": {hook_name: hook_config_with_function_obj, ...}
            }
        """
        try:
            # Primary approach: Get tools from workflow.json
            agent_tools_list = workflow_config.get_enabled_agent_tools(workflow_type)
            lifecycle_hooks_list = workflow_config.get_enabled_lifecycle_hooks(workflow_type)
            
            # Load function objects and apply AG2 module-level overrides
            agent_tools = {}
            for tool in agent_tools_list:
                try:
                    module = importlib.import_module(tool["module"])
                    if not hasattr(module, tool["function"]):
                        logger.error(f"Function '{tool['function']}' not found in module '{tool['module']}'")
                        continue
                    
                    tool["function_obj"] = getattr(module, tool["function"])
                    
                    # AG2 Compatibility: Check for module-level APPLY_TO override
                    if hasattr(module, "APPLY_TO"):
                        module_apply_to = getattr(module, "APPLY_TO")
                        if module_apply_to != tool.get("apply_to"):
                            logger.info(f"Tool {tool['name']}: Using module-level APPLY_TO={module_apply_to} instead of workflow.json apply_to={tool.get('apply_to')}")
                            tool["apply_to"] = module_apply_to
                    
                    agent_tools[tool["name"]] = tool
                    logger.debug(f"✅ Loaded agent tool: {tool['name']} (apply_to: {tool.get('apply_to')})")
                except Exception as e:
                    logger.error(f"Failed to load agent tool {tool.get('name', 'unknown')}: {e}")
            
            # Load function objects for lifecycle hooks with AG2 module-level overrides
            lifecycle_hooks = {}
            for hook in lifecycle_hooks_list:
                try:
                    module = importlib.import_module(hook["module"])
                    if not hasattr(module, hook["function"]):
                        logger.error(f"Function '{hook['function']}' not found in module '{hook['module']}'")
                        continue
                    
                    hook["function_obj"] = getattr(module, hook["function"])
                    
                    # AG2 Compatibility: Check for module-level TRIGGER overrides
                    if hasattr(module, "TRIGGER"):
                        module_trigger = getattr(module, "TRIGGER")
                        if module_trigger != hook.get("trigger"):
                            logger.info(f"Hook {hook['name']}: Using module-level TRIGGER={module_trigger} instead of workflow.json trigger={hook.get('trigger')}")
                            hook["trigger"] = module_trigger
                    
                    if hasattr(module, "TRIGGER_AGENT"):
                        module_trigger_agent = getattr(module, "TRIGGER_AGENT")
                        if module_trigger_agent != hook.get("trigger_agent"):
                            logger.info(f"Hook {hook['name']}: Using module-level TRIGGER_AGENT={module_trigger_agent}")
                            hook["trigger_agent"] = module_trigger_agent
                    
                    lifecycle_hooks[hook["name"]] = hook
                    logger.debug(f"✅ Loaded lifecycle hook: {hook['name']} (trigger: {hook.get('trigger')}, agent: {hook.get('trigger_agent', 'all')})")
                except Exception as e:
                    logger.error(f"Failed to load lifecycle hook {hook.get('name', 'unknown')}: {e}")
            
            result = {
                "agent_tools": agent_tools,
                "lifecycle_hooks": lifecycle_hooks
            }
            
            total_tools = len(agent_tools) + len(lifecycle_hooks)
            logger.info(f"Discovered {total_tools} tools for workflow {workflow_type} ({len(agent_tools)} agent tools, {len(lifecycle_hooks)} hooks) with AG2 compatibility")
            return result
            
        except Exception as e:
            logger.error(f"Failed to discover tools for workflow {workflow_type}: {e}")
            return {"agent_tools": {}, "lifecycle_hooks": {}}
    
    def register_agent_tools(self, agents: Dict[str, Any], agent_tools: Dict[str, Any]):
        """
        Register agent-specific tools according to apply_to patterns.
        """
        for tool_name, tool_config in agent_tools.items():
            try:
                apply_to = tool_config.get("apply_to", [])
                tool_func = tool_config.get("function_obj")
                
                if not tool_func or not callable(tool_func):
                    logger.error(f"Tool {tool_name} has no valid function_obj")
                    continue
                
                if apply_to == "all":
                    targets = agents.values()
                    target_names = list(agents.keys())
                elif isinstance(apply_to, list):
                    targets = [agents[name] for name in apply_to if name in agents]
                    target_names = [name for name in apply_to if name in agents]
                elif isinstance(apply_to, str) and apply_to in agents:
                    targets = [agents[apply_to]]
                    target_names = [apply_to]
                else:
                    logger.warning(f"Invalid apply_to configuration for tool {tool_name}: {apply_to}")
                    continue

                for agent in targets:
                    try:
                        if hasattr(agent, 'register_tool'):
                            agent.register_tool(tool_name, tool_func)
                        else:
                            logger.warning(f"Agent {getattr(agent, 'name', 'unknown')} has no register_tool method")
                    except Exception as e:
                        logger.error(f"Failed to register {tool_name} on agent: {e}")
                
                biz_log.debug(f"🔧 agent-tool {tool_name} → {target_names}")
                
            except Exception as e:
                logger.error(f"Failed to process agent tool {tool_name}: {e}")

    def register_lifecycle_hooks(self, manager: Any, lifecycle_hooks: Dict[str, Any]):
        """
        Register lifecycle hooks according to trigger patterns.
        """
        for hook_name, hook_config in lifecycle_hooks.items():
            try:
                trigger = hook_config.get("trigger")
                hook_func = hook_config.get("function_obj")
                trigger_agent = hook_config.get("trigger_agent")
                
                if not hook_func or not callable(hook_func):
                    logger.error(f"Hook {hook_name} has no valid function_obj")
                    continue
                
                if not hasattr(manager, 'register_hook'):
                    logger.warning(f"Manager has no register_hook method, cannot register {hook_name}")
                    continue
                
                # Handle specific agent triggers
                if trigger_agent and trigger == "after_each_agent":
                    def _wrap(mgr, hist, _f=hook_func, _a=trigger_agent):
                        if hist and hist[-1].get("sender") == _a:
                            return _f(mgr, hist)
                    
                    manager.register_hook("after_each_agent", _wrap)
                    biz_log.debug(f"🪝 {hook_name} hooked for agent {trigger_agent}")
                elif trigger:
                    manager.register_hook(trigger, hook_func)
                    biz_log.debug(f"🪝 {hook_name} hooked at {trigger}")
                else:
                    logger.warning(f"Hook {hook_name} has no trigger specified")
                    
            except Exception as e:
                logger.error(f"Failed to process lifecycle hook {hook_name}: {e}")

# Global registry instance
_tool_registry = None

def get_unified_tool_registry() -> UnifiedToolRegistry:
    """Get the global unified tool registry instance."""
    global _tool_registry
    if _tool_registry is None:
        base_dir = Path(__file__).parent.parent.parent  # Get to project root
        _tool_registry = UnifiedToolRegistry(base_dir)
    return _tool_registry

async def discover_and_register_workflow_tools(
    manager: Any,
    workflow_type: str,
    chat_id: str,
    enterprise_id: str,
    agents: Dict[str, Any] | None = None
) -> List[str]:
    """
    Unified tool discovery and registration for workflows using workflow.json.
    Handles both agent-specific tools and lifecycle hooks.
    
    Args:
        manager: AG2 GroupChatManager instance
        workflow_type: Type of workflow (e.g., "Generator")
        chat_id: Chat identifier for context
        enterprise_id: Enterprise identifier for context
        agents: Dict of agent_name -> agent_instance for agent-specific tools
        
    Returns:
        List[str]: Names of successfully registered tools
    """
    registry = get_unified_tool_registry()
    all_tools = registry.discover_workflow_tools(workflow_type)
    
    registered_tools = []
    
    # 1. Register agent-specific tools (if agents provided)
    if agents:
        try:
            agent_tools = all_tools.get("agent_tools", {})
            if agent_tools:
                registry.register_agent_tools(agents, agent_tools)
                registered_tools.append(f"{len(agent_tools)} agent tools")
                logger.info(f"✅ Registered {len(agent_tools)} agent-specific tools")
            
            # Register lifecycle hooks
            lifecycle_hooks = all_tools.get("lifecycle_hooks", {})
            if lifecycle_hooks and hasattr(manager, 'register_hook'):
                registry.register_lifecycle_hooks(manager, lifecycle_hooks)
                registered_tools.append(f"{len(lifecycle_hooks)} lifecycle hooks")
                logger.info(f"✅ Registered {len(lifecycle_hooks)} lifecycle hooks")
                
        except Exception as e:
            logger.warning(f"⚠️ Tool registration failed: {e}")
    
    logger.info(f"Successfully registered tools for {workflow_type}: {registered_tools}")
    return registered_tools

def register_core_tools_only(manager: Any) -> List[str]:
    """
    Register only core infrastructure tools (fallback method).
    
    Currently returns empty list as all tools are workflow-specific and should
    be defined in workflow.json.
    
    Args:
        manager: AG2 GroupChatManager instance
        
    Returns:
        List[str]: Names of successfully registered core tools (currently empty)
    """
    logger.info("No core tools to register - using workflow-specific design")
    return []

# Legacy compatibility functions (for existing imports)
def discover_tools(workflow_dir: Path) -> Dict[str, Dict[str, Any]]:
    """Legacy compatibility - use workflow.json-based discovery instead."""
    logger.warning("discover_tools is deprecated - use workflow.json-based tool configuration")
    return {"AgentTools": {}, "GroupchatTools": {}}

def register_agent_tools(agents: Dict[str, Any], agent_tools: Dict[str, Any]):
    """Legacy compatibility - use UnifiedToolRegistry instead."""
    registry = get_unified_tool_registry()
    return registry.register_agent_tools(agents, agent_tools)

def register_groupchat_tools(manager: Any, groupchat_tools: Dict[str, Any]):
    """Legacy compatibility - use UnifiedToolRegistry instead."""
    registry = get_unified_tool_registry()
    return registry.register_lifecycle_hooks(manager, groupchat_tools)
