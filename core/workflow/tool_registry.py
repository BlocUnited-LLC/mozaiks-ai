"""
Unified Tool Registry for Workflow-Specific Tool Discovery & Registration
Combines both manager-level and agent-specific tool registration patterns
"""

import logging
import importlib
import inspect
import pkgutil
from pathlib import Path
from types import ModuleType
from typing import List, Dict, Any, Callable

logger = logging.getLogger(__name__)
biz_log = logging.getLogger("business.tool_loader")

class UnifiedToolRegistry:
    """
    Unified tool registry that handles both AG2 manager-level and agent-specific tool registration.
    Combines the functionality of both tool_registry and tool_loader systems.
    """
    
    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.registered_tools = {}
    
    def discover_workflow_tools(self, workflow_type: str) -> Dict[str, Dict[str, Callable]]:
        """
        Discover all tools for a workflow using the enhanced discovery system.
        
        Returns:
            Dict with structure: {
                "core_tools": {...},
                "AgentTools": {...}, 
                "GroupchatTools": {...}
            }
        """
        workflow_path = self.base_dir / "workflows" / workflow_type
        
        if not workflow_path.exists():
            logger.warning(f"Workflow path does not exist: {workflow_path}")
            return {"core_tools": {}, "AgentTools": {}, "GroupchatTools": {}}
        
        # 1. Core Infrastructure Tools (always available)
        core_tools = self._get_core_tools()
        
        # 2. Use enhanced tool_loader discovery for workflow-specific tools
        workflow_tools = self._discover_tools_enhanced(workflow_path)
        
        result = {
            "core_tools": core_tools,
            **workflow_tools
        }
        
        total_tools = sum(len(tools) for tools in result.values())
        logger.info(f"Discovered {total_tools} tools for workflow {workflow_type}")
        return result
    
    def _get_core_tools(self) -> Dict[str, Callable]:
        """Get core infrastructure tools that are always available and workflow-agnostic."""
        tools = {}
        
        # Core infrastructure tools should be truly generic and workflow-agnostic
        # Currently no truly core tools defined - workflow-specific tools should be 
        # discovered via the dynamic discovery system
        
        logger.debug("Core tools: Using workflow-agnostic approach - no hardcoded tools")
        
        return tools
    
    def _discover_tools_enhanced(self, workflow_dir: Path) -> Dict[str, Dict[str, Callable]]:
        """
        Enhanced tool discovery using tool_loader logic.
        Scan workflow_dir/AgentTools/ and workflow_dir/GroupchatTools/
        """
        def _walk(sub: str) -> Dict[str, Callable]:
            subdir = workflow_dir / sub
            if not subdir.is_dir():
                return {}
            
            # Build package name: workflows.{workflow_type}.AgentTools
            pkg_name = ".".join(workflow_dir.parts[-2:] + (sub,))
            found: Dict[str, Callable] = {}
            
            for m in pkgutil.iter_modules([str(subdir)]):
                try:
                    module = importlib.import_module(f"{pkg_name}.{m.name}")
                    found.update(self._collect_callables(module))
                    biz_log.debug("🔎 loaded %s", module.__name__)
                except Exception as e:
                    logger.warning(f"Failed to import {pkg_name}.{m.name}: {e}")
            
            return found

        return {
            "AgentTools": _walk("AgentTools"),
            "GroupchatTools": _walk("GroupchatTools"),
        }
    
    def _collect_callables(self, module: ModuleType) -> Dict[str, Callable]:
        """Return {attr_name: attr} for every public callable in module."""
        items: Dict[str, Callable] = {}
        for attr_name in dir(module):
            if attr_name.startswith("_") or attr_name[0].isupper():
                continue
            attr = getattr(module, attr_name)
            if callable(attr):
                items[attr_name] = attr
        return items
    
    def register_agent_tools(self, agents: Dict[str, Any], agent_tools: Dict[str, Callable]):
        """
        Register agent-specific tools according to APPLY_TO patterns.
        """
        for func in agent_tools.values():
            try:
                mod = importlib.import_module(func.__module__)
                usage = getattr(mod, "APPLY_TO", "all")

                if usage == "all":
                    targets = agents.values()
                else:  # list of agent names
                    targets = (agents[n] for n in usage if n in agents)

                for ag in targets:
                    try:
                        ag.register_tool(func.__name__, func)
                        biz_log.debug("🔧 agent-tool %s → %s", func.__name__, ag.name)
                    except Exception as e:
                        biz_log.error("❌ failed to register %s on %s: %s", func.__name__, ag.name, e)
            except Exception as e:
                logger.error(f"Failed to process agent tool {func.__name__}: {e}")

    def register_groupchat_tools(self, manager: Any, groupchat_tools: Dict[str, Callable]):
        """
        Register groupchat hooks according to TRIGGER patterns.
        """
        for func in groupchat_tools.values():
            try:
                mod = importlib.import_module(func.__module__)

                # Preset trigger
                if hasattr(mod, "TRIGGER"):
                    trig = mod.TRIGGER
                    manager.register_hook(trig, func)
                    biz_log.debug("🪝 %s hooked at %s", func.__name__, trig)
                    continue

                # Single-agent trigger
                if hasattr(mod, "TRIGGER_AGENT"):
                    agent_name = mod.TRIGGER_AGENT

                    def _wrap(mgr, hist, _f=func, _a=agent_name):
                        if hist and hist[-1].get("sender") == _a:
                            _f(mgr, hist)

                    manager.register_hook("after_each_agent", _wrap)
                    biz_log.debug("🪝 %s hooked for agent %s", func.__name__, agent_name)
                    continue

                # Default (nothing specified)
                biz_log.warning("⚠️ %s has no TRIGGER / TRIGGER_AGENT", func.__module__)
                
            except Exception as e:
                logger.error(f"Failed to process groupchat tool {func.__name__}: {e}")

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
    Unified tool discovery and registration for workflows.
    Handles both manager-level and agent-specific tool registration.
    
    Args:
        manager: AG2 GroupChatManager instance
        workflow_type: Type of workflow (e.g., "MyWorkflow")
        chat_id: Chat identifier for context
        enterprise_id: Enterprise identifier for context
        agents: Dict of agent_name -> agent_instance for agent-specific tools
        
    Returns:
        List[str]: Names of successfully registered tools
    """
    registry = get_unified_tool_registry()
    all_tools = registry.discover_workflow_tools(workflow_type)
    
    registered_tools = []
    
    # 1. Register core tools at manager level (always available to all agents)
    core_tools = all_tools.get("core_tools", {})
    for tool_name, tool_func in core_tools.items():
        try:
            manager.register_tool(
                name=tool_name,
                func=tool_func
            )
            registered_tools.append(f"{tool_name}(core)")
            logger.debug(f"✅ Registered core tool: {tool_name}")
        except Exception as e:
            logger.error(f"❌ Failed to register core tool {tool_name}: {e}")
    
    # 2. Register manager-level tools from GroupchatTools (with APPLY_TO="manager")
    groupchat_tools = all_tools.get("GroupchatTools", {})
    for tool_name, tool_func in groupchat_tools.items():
        try:
            if _should_register_at_manager_level(tool_func):
                manager.register_tool(
                    name=tool_name,
                    func=tool_func
                )
                registered_tools.append(f"{tool_name}(manager)")
                logger.debug(f"✅ Registered manager tool: {tool_name}")
        except Exception as e:
            logger.error(f"❌ Failed to register manager tool {tool_name}: {e}")
    
    # 3. Register agent-specific tools (if agents provided)
    if agents:
        try:
            # Register agent-specific tools using APPLY_TO patterns
            agent_tools = all_tools.get("AgentTools", {})
            if agent_tools:
                registry.register_agent_tools(agents, agent_tools)
                registered_tools.append(f"{len(agent_tools)} agent tools")
                logger.info(f"✅ Registered {len(agent_tools)} agent-specific tools")
            
            # Register groupchat hooks using TRIGGER patterns
            if groupchat_tools and hasattr(manager, 'register_hook'):
                registry.register_groupchat_tools(manager, groupchat_tools)
                registered_tools.append(f"{len(groupchat_tools)} groupchat hooks")
                logger.info(f"✅ Registered {len(groupchat_tools)} groupchat hooks")
                
        except Exception as e:
            logger.warning(f"⚠️ Agent-specific tool registration failed: {e}")
    
    logger.info(f"Successfully registered tools for {workflow_type}: {registered_tools}")
    return registered_tools

def _should_register_at_manager_level(tool_func: Callable) -> bool:
    """
    Determine if a tool should be registered at manager level vs agent level.
    Manager-level tools are available to all agents automatically.
    """
    try:
        module = importlib.import_module(tool_func.__module__)
        apply_to = getattr(module, "APPLY_TO", "agent")
        
        # If APPLY_TO is "manager" or "all", register at manager level
        return apply_to in ["manager", "all"]
        
    except Exception:
        # Default to agent level for workflow-specific tools
        return False

def register_core_tools_only(manager: Any) -> List[str]:
    """
    Register only core infrastructure tools (fallback method).
    
    This is a workflow-agnostic fallback that registers only truly generic tools.
    Currently returns empty list as all tools are workflow-specific and should
    be discovered via the dynamic discovery system.
    
    Args:
        manager: AG2 GroupChatManager instance
        
    Returns:
        List[str]: Names of successfully registered core tools (currently empty)
    """
    registry = get_unified_tool_registry()
    core_tools = registry._get_core_tools()
    
    registered_tools = []
    
    if not core_tools:
        logger.info("No core tools to register - using workflow-agnostic design")
        return registered_tools
    
    for tool_name, tool_func in core_tools.items():
        try:
            manager.register_tool(
                name=tool_name,
                func=tool_func
            )
            
            registered_tools.append(tool_name)
            logger.debug(f"✅ Registered core tool: {tool_name}")
            
        except Exception as e:
            logger.error(f"❌ Failed to register core tool {tool_name}: {e}")
    
    return registered_tools

# Legacy compatibility functions (for existing imports)
def discover_tools(workflow_dir: Path) -> Dict[str, Dict[str, Callable]]:
    """Legacy compatibility - use UnifiedToolRegistry instead."""
    registry = get_unified_tool_registry()
    return registry._discover_tools_enhanced(workflow_dir)

def register_agent_tools(agents: Dict[str, Any], agent_tools: Dict[str, Callable]):
    """Legacy compatibility - use UnifiedToolRegistry instead."""
    registry = get_unified_tool_registry()
    return registry.register_agent_tools(agents, agent_tools)

def register_groupchat_tools(manager: Any, groupchat_tools: Dict[str, Callable]):
    """Legacy compatibility - use UnifiedToolRegistry instead."""
    registry = get_unified_tool_registry()
    return registry.register_groupchat_tools(manager, groupchat_tools)
