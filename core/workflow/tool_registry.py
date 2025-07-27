"""
Modular Tool Registry for JSON-Driven Agent Tools with Lifecycle Control
Supports workflow.json configuration for clean, centralized tool management with timing control
"""

import json
import logging
import importlib
import inspect
from pathlib import Path
from typing import List, Dict, Any, Callable, Optional
from enum import Enum

# Import AG2's modern Tool system
try:
    from autogen.tools import Tool
except ImportError:
    # Fallback for older AG2 versions
    Tool = None

logger = logging.getLogger(__name__)

class ToolTrigger(str, Enum):
    """Defines when tools should be executed"""
    ON_DEMAND = "on_demand"                    # Agent calls when needed
    BEFORE_GROUPCHAT_START = "before_groupchat_start"
    AFTER_GROUPCHAT_START = "after_groupchat_start"
    BEFORE_AGENT_SPEAKS = "before_agent_speaks"
    AFTER_AGENT_SPEAKS = "after_agent_speaks"
    END_OF_CHAT = "end_of_chat"
    ON_ERROR = "on_error"
    ON_USER_INPUT = "on_user_input"

class ToolConfig:
    """Configuration for a single tool
    
    🔧 TOOL CONFIG DEBUGGING:
    - If new tool fields aren't being recognized, check the __init__ method below
    - The **kwargs pattern captures UI-specific fields like tool_id, display, etc.
    - This was essential for supporting the transition from agent_tool_map to backend_tools/ui_tools schema
    """
    def __init__(self, path: str, trigger: str = "on_demand", description: str = "", **kwargs):
        self.path = path
        self.trigger = ToolTrigger(trigger)
        self.description = description
        self.function = None  # Will be loaded dynamically
        
        # Store additional UI-specific fields (for ui_tools in workflow.json)
        self.tool_id = kwargs.get('tool_id', None)
        self.display = kwargs.get('display', None)
        
        # Store any other additional parameters from workflow.json
        # This ensures new tool config fields don't break the system
        for key, value in kwargs.items():
            if key not in ['tool_id', 'display']:
                setattr(self, key, value)
        
    def load_function(self) -> Callable:
        """Dynamically import and return the tool function"""
        if self.function is None:
            try:
                module_path, function_name = self.path.rsplit('.', 1)
                module = importlib.import_module(module_path)
                self.function = getattr(module, function_name)
                logger.info(f"✅ Loaded tool function: {self.path}")
            except (ImportError, AttributeError, ValueError) as e:
                logger.error(f"❌ Failed to load tool function '{self.path}': {e}")
                raise
        return self.function

class WorkflowToolRegistry:
    """Central registry for workflow tools with timing control"""
    
    def __init__(self, workflow_name: str):
        self.workflow_name = workflow_name
        self.agent_tools: Dict[str, List[ToolConfig]] = {}
        self.lifecycle_tools: Dict[ToolTrigger, List[ToolConfig]] = {}
        self.config_path = Path("workflows") / workflow_name / "workflow.json"
        
    def load_configuration(self):
        """Load tool configuration from workflow.json"""
        if not self.config_path.exists():
            logger.warning(f"No workflow.json found at '{self.config_path}'")
            return
            
        try:
            with open(self.config_path, 'r') as f:
                config = json.load(f)
                
            # Load agent tools from multiple possible schemas
            self._load_agent_tools_from_config(config)
                    
            # Load lifecycle tools
            lifecycle_tools = config.get("lifecycle_tools", {})
            for tool_name, tool_config in lifecycle_tools.items():
                # Support the original schema with lifecycle_event field
                if isinstance(tool_config, dict) and "lifecycle_event" in tool_config:
                    trigger_value = tool_config["lifecycle_event"]
                    try:
                        trigger_enum = ToolTrigger(trigger_value)
                    except ValueError:
                        logger.error(f"❌ Invalid lifecycle_event '{trigger_value}' for tool '{tool_name}'. Valid values: {[t.value for t in ToolTrigger]}")
                        continue
                        
                    if trigger_enum not in self.lifecycle_tools:
                        self.lifecycle_tools[trigger_enum] = []
                        
                    tool = ToolConfig(
                        path=tool_config["path"],
                        trigger=trigger_value,
                        description=tool_config.get("description", "")
                    )
                    self.lifecycle_tools[trigger_enum].append(tool)
                    logger.info(f"📌 Registered lifecycle tool '{tool_name}' for trigger '{trigger_value}'")
                    
            logger.info(f"📋 Loaded configuration for workflow '{self.workflow_name}': {len(self.agent_tools)} agent mappings, {len(self.lifecycle_tools)} lifecycle triggers")
            
        except Exception as e:
            logger.error(f"❌ Failed to load workflow configuration: {e}")

    def _load_agent_tools_from_config(self, config):
        """Load agent tools from various configuration schemas"""
        
        # Schema 1: New backend_tools + ui_tools format
        backend_tools = config.get("backend_tools", {})
        ui_tools = config.get("ui_tools", {})
        
        # Merge backend and UI tools
        all_tools = {}
        for agent_name, tools in backend_tools.items():
            if agent_name not in all_tools:
                all_tools[agent_name] = []
            all_tools[agent_name].extend(tools)
            
        for agent_name, tools in ui_tools.items():
            if agent_name not in all_tools:
                all_tools[agent_name] = []
            all_tools[agent_name].extend(tools)
        
        # Process all collected tools
        for agent_name, tools in all_tools.items():
            self.agent_tools[agent_name] = []
            for tool_config in tools:
                # Handle both string paths and dict configs
                if isinstance(tool_config, str):
                    tool = ToolConfig(path=tool_config)
                else:
                    tool = ToolConfig(**tool_config)
                self.agent_tools[agent_name].append(tool)
                
        logger.info(f"🔧 Processed tools for {len(all_tools)} agent types: {list(all_tools.keys())}")
            
    def register_agent_tools(self, agents: List[Any]):
        """Register tools for specific agents"""
        agent_dict = {agent.name: agent for agent in agents}
        
        for agent_name, tools in self.agent_tools.items():
            if agent_name == "ALL_AGENTS":
                # Register for all agents
                for agent in agents:
                    self._register_tools_for_agent(agent, tools)
            elif agent_name in agent_dict:
                agent = agent_dict[agent_name]
                self._register_tools_for_agent(agent, tools)
            else:
                logger.warning(f"Agent '{agent_name}' not found in agent list")
                
    def _register_tools_for_agent(self, agent: Any, tools: List[ToolConfig]):
        """Register a list of tools for a specific agent using AG2's modern Tool system
        
        🔧 TOOL REGISTRATION DEBUGGING:
        - If tools aren't registering properly, set ENABLE_TOOL_DEBUG = True below
        - This will show detailed registration steps and any failures
        - Essential for diagnosing AG2 tool system issues
        """
        ENABLE_TOOL_DEBUG = False  # Set to True for detailed tool registration debugging
        
        for tool_config in tools:
            try:
                function = tool_config.load_function()
                
                if ENABLE_TOOL_DEBUG:
                    logger.info(f"🔍 [TOOL-DEBUG] Registering '{function.__name__}' for agent '{agent.name}'")
                    logger.info(f"🔍 [TOOL-DEBUG] Tool description: {tool_config.description}")
                    logger.info(f"🔍 [TOOL-DEBUG] Agent type: {type(agent).__name__}")
                
                # Use AG2's modern Tool class if available
                if Tool is not None:
                    # Create a Tool instance from the function
                    tool = Tool(
                        name=function.__name__,
                        description=tool_config.description or function.__doc__ or f"Tool: {function.__name__}",
                        func_or_tool=function
                    )
                    
                    # Register for both LLM and execution (full tool registration)
                    tool.register_tool(agent)
                    
                    if ENABLE_TOOL_DEBUG:
                        logger.info(f"🔧 [TOOL-DEBUG] Successfully registered modern Tool '{function.__name__}'")
                    else:
                        logger.info(f"🔧 [MODERN] Registered Tool '{function.__name__}' for agent '{agent.name}' (LLM + execution)")
                    
                else:
                    # Fallback to old registration method
                    function_map = {function.__name__: function}
                    agent.register_function(function_map)
                    
                    if ENABLE_TOOL_DEBUG:
                        logger.info(f"🔧 [TOOL-DEBUG] Successfully registered function '{function.__name__}'")
                    else:
                        logger.info(f"🔧 Registered function '{function.__name__}' for agent '{agent.name}'")
                    
            except Exception as e:
                logger.error(f"❌ Failed to register tool for agent '{agent.name}': {e}")
                logger.error(f"   Tool path: {tool_config.path}")
                logger.error(f"   Tool description: {tool_config.description}")
                if ENABLE_TOOL_DEBUG:
                    import traceback
                    logger.error(f"   Full traceback: {traceback.format_exc()}")
                
    def get_lifecycle_tools(self, trigger: ToolTrigger) -> List[ToolConfig]:
        """Get tools for specific lifecycle trigger"""
        return self.lifecycle_tools.get(trigger, [])
        
    async def execute_lifecycle_tools(self, trigger: ToolTrigger, context: Optional[Dict[str, Any]] = None):
        """Execute all tools for a specific lifecycle trigger"""
        tools = self.get_lifecycle_tools(trigger)
        if not tools:
            return
            
        logger.info(f"🎯 Executing {len(tools)} lifecycle tools for trigger '{trigger}'")
        for tool in tools:
            try:
                function = tool.load_function()
                if context:
                    # Pass context as kwargs if function accepts them
                    sig = inspect.signature(function)
                    if len(sig.parameters) > 0:
                        result = await function(**context) if inspect.iscoroutinefunction(function) else function(**context)
                    else:
                        result = await function() if inspect.iscoroutinefunction(function) else function()
                else:
                    result = await function() if inspect.iscoroutinefunction(function) else function()
                
                # Log the result if available
                if result is not None:
                    logger.info(f"✅ Executed lifecycle tool '{function.__name__}' for trigger '{trigger}': {result}")
                else:
                    logger.info(f"✅ Executed lifecycle tool '{function.__name__}' for trigger '{trigger}'")
            except Exception as e:
                logger.error(f"❌ Failed to execute lifecycle tool '{tool.path}': {e}")

    def get_agent_tool_info(self, agent) -> Dict:
        """Get detailed tool information for debugging"""
        info = {
            'agent_name': getattr(agent, 'name', 'Unknown'),
            'agent_type': type(agent).__name__,
            'function_map': {},
            'llm_config_tools': [],
            'modern_tools': [],
            'has_registered_tools': False,
            'total_tools': 0
        }
        
        # Check for function registration
        if hasattr(agent, 'function_map'):
            info['function_map'] = dict(agent.function_map) if agent.function_map else {}
            info['has_registered_tools'] = len(info['function_map']) > 0
            info['total_tools'] += len(info['function_map'])
        
        # Check for modern AG2 tool registration
        if hasattr(agent, '_tool_calls'):
            info['modern_tools'] = list(agent._tool_calls.keys()) if agent._tool_calls else []
            info['has_registered_tools'] = info['has_registered_tools'] or len(info['modern_tools']) > 0
            info['total_tools'] += len(info['modern_tools'])
        
        # Check for tools in llm_config
        if hasattr(agent, 'llm_config') and agent.llm_config:
            tools = agent.llm_config.get('tools', [])
            info['llm_config_tools'] = [t.get('function', {}).get('name', 'Unknown') for t in tools]
            info['has_registered_tools'] = info['has_registered_tools'] or len(info['llm_config_tools']) > 0
            info['total_tools'] += len(info['llm_config_tools'])
        
        return info
