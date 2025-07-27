# ==============================================================================
# FILE: core/workflow/workflow_config.py
# DESCRIPTION: Dynamic workflow configuration loader - no hardcoding
# ==============================================================================
import json
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# Global registry to prevent duplicate loading
_global_configs = {}
_configs_loaded = False

class WorkflowConfig:
    """Dynamic workflow configuration loader with singleton pattern"""
    
    def __init__(self):
        global _global_configs, _configs_loaded
        
        if _configs_loaded:
            # Use cached configs instead of reloading
            self._configs = _global_configs
        else:
            self._configs = {}
            self._load_all_workflows()
            # Cache the configs globally
            _global_configs = self._configs.copy()
            _configs_loaded = True
    
    def _load_all_workflows(self):
        """Load all workflow.json files from workflows directory"""
        workflows_dir = Path(__file__).parent.parent.parent / "workflows"
        
        if not workflows_dir.exists():
            logger.warning(f"Workflows directory not found: {workflows_dir}")
            return
        
        for workflow_dir in workflows_dir.iterdir():
            if workflow_dir.is_dir():
                config_file = workflow_dir / "workflow.json"
                if config_file.exists():
                    try:
                        with open(config_file, 'r') as f:
                            config = json.load(f)
                        
                        workflow_name = workflow_dir.name.lower()
                        self._configs[workflow_name] = config
                        logger.info(f"✅ Loaded workflow config: {workflow_name}")
                        
                    except Exception as e:
                        logger.error(f"❌ Failed to load {config_file}: {e}")
    
    def get_config(self, workflow_name: str) -> Dict[str, Any]:
        """Get configuration for a workflow type"""
        return self._configs.get(workflow_name.lower(), {})
    
    def has_human_in_the_loop(self, workflow_name: str) -> bool:
        """Check if workflow requires human interaction"""
        config = self.get_config(workflow_name)
        return config.get("human_in_the_loop", False)
    
    def get_chat_pane_agents(self, workflow_name: str) -> List[str]:
        """Get the agents that interact in the chat pane (inline components)"""
        config = self.get_config(workflow_name)
        ui_agents = config.get("ui_capable_agents", [])
        
        chat_agents = []
        for agent in ui_agents:
            capabilities = agent.get("capabilities", [])
            if "inline_components" in capabilities or "chat" in capabilities:
                chat_agents.append(agent.get("name"))
        
        return chat_agents
    
    def get_artifact_agents(self, workflow_name: str) -> List[str]:
        """Get the agents that handle artifacts"""
        config = self.get_config(workflow_name)
        ui_agents = config.get("ui_capable_agents", [])
        
        artifact_agents = []
        for agent in ui_agents:
            capabilities = agent.get("capabilities", [])
            if "artifacts" in capabilities:
                artifact_agents.append(agent.get("name"))
        
        return artifact_agents

    def get_initial_message(self, workflow_name: str) -> Optional[str]:
        """Get the initial message for a workflow type"""
        config = self.get_config(workflow_name)
        return config.get("initial_message", None)

    def get_visible_agents(self, workflow_name: str) -> List[str]:
        """Get the agents whose messages should appear in UI"""
        config = self.get_config(workflow_name)
        visible_agents = []
        
        # Check for explicit visual_agents configuration first
        visual_agents = config.get("visual_agents")
        if visual_agents:
            visible_agents.extend(visual_agents)
            logger.debug(f"Using explicit visual_agents for {workflow_name}: {visual_agents}")
        else:
            # Fallback to the old logic if visual_agents not specified
            # All ui_capable_agents are automatically visible
            ui_agents = config.get("ui_capable_agents", [])
            for agent in ui_agents:
                agent_name = agent.get("name")
                if agent_name and agent_name not in visible_agents:
                    visible_agents.append(agent_name)
            
            logger.debug(f"Using ui_capable_agents as visual agents for {workflow_name}: {visible_agents}")
        
        # Auto-include user if human_in_the_loop is true
        if config.get("human_in_the_loop", False):
            visible_agents.append("user")
        
        return visible_agents
    
    def is_visible_agent(self, agent_name: str, workflow_name: str) -> bool:
        """Check if an agent's messages should appear in the UI"""
        visible_agents = self.get_visible_agents(workflow_name)
        return agent_name in visible_agents
    
    def get_frontend_agents(self, workflow_name: str) -> List[str]:
        """Get all agents that should appear in the frontend UI"""
        chat_agents = self.get_chat_pane_agents(workflow_name)
        artifact_agents = self.get_artifact_agents(workflow_name)
        return list(set(chat_agents + artifact_agents))
    
    def is_frontend_agent(self, agent_name: str, workflow_name: str) -> bool:
        """Check if an agent should appear in the frontend UI"""
        frontend_agents = self.get_frontend_agents(workflow_name)
        return agent_name in frontend_agents
    
    def should_auto_start(self, workflow_name: str) -> bool:
        """
        Determine if workflow should auto-start or wait for user input.
        
        Logic:
        - auto_start: true → Start immediately with no message (autonomous workflow)
        - auto_start: false → Wait for user connection, then send initial_message if present
        
        Scenarios:
        1. Autonomous workflow: auto_start: true, initial_message: null → Start immediately
        2. Wizard/Navigator: auto_start: false, initial_message: "Hello!" → Send greeting on connect
        3. Continuation step: auto_start: false, initial_message: null → Wait for user input
        """
        config = self.get_config(workflow_name)
        
        # Use explicit auto_start setting if present
        if "auto_start" in config:
            return config["auto_start"]
            
        # Fallback: if no auto_start specified, use human_in_the_loop logic
        # human_in_the_loop: false → auto-start (autonomous)
        # human_in_the_loop: true → don't auto-start (wait for user)
        return not self.has_human_in_the_loop(workflow_name)
    
    def get_auto_start(self, workflow_name: str) -> bool:
        """Get auto_start setting for workflow, with fallback logic"""
        return self.should_auto_start(workflow_name)
    
    def get_all_workflow_names(self) -> list:
        """Get list of all available workflow types"""
        return list(self._configs.keys())
    
    def get_components_for_agent(self, workflow_name: str, agent_name: str) -> List[Dict[str, Any]]:
        """Get all components for a specific agent"""
        config = self.get_config(workflow_name)
        ui_agents = config.get("ui_capable_agents", [])
        
        for agent in ui_agents:
            if agent.get("name") == agent_name:
                return agent.get("components", [])
        
        return []
    
    def get_inline_components(self, workflow_name: str) -> List[Dict[str, Any]]:
        """Get all inline components across all agents"""
        config = self.get_config(workflow_name)
        ui_agents = config.get("ui_capable_agents", [])
        
        inline_components = []
        for agent in ui_agents:
            components = agent.get("components", [])
            for component in components:
                if component.get("type") == "inline":
                    inline_components.append(component)
        
        return inline_components
    
    def get_artifact_components(self, workflow_name: str) -> List[Dict[str, Any]]:
        """Get all artifact components across all agents"""
        config = self.get_config(workflow_name)
        ui_agents = config.get("ui_capable_agents", [])
        
        artifact_components = []
        for agent in ui_agents:
            components = agent.get("components", [])
            for component in components:
                if component.get("type") == "artifact":
                    artifact_components.append(component)
        
        return artifact_components
    
    def get_component_by_name(self, workflow_name: str, component_name: str) -> Optional[Dict[str, Any]]:
        """Get a specific component by name"""
        config = self.get_config(workflow_name)
        ui_agents = config.get("ui_capable_agents", [])
        
        for agent in ui_agents:
            components = agent.get("components", [])
            for component in components:
                if component.get("name") == component_name:
                    return component
        
        return None
    
    def get_agent_tools(self, workflow_name: str) -> List[Dict[str, Any]]:
        """Get all agent tools for a workflow"""
        config = self.get_config(workflow_name)
        tools = config.get("tools", {})
        return tools.get("agent_tools", [])
    
    def get_lifecycle_hooks(self, workflow_name: str) -> List[Dict[str, Any]]:
        """Get all lifecycle hooks for a workflow"""
        config = self.get_config(workflow_name)
        tools = config.get("tools", {})
        return tools.get("lifecycle_hooks", [])
    
    def get_enabled_agent_tools(self, workflow_name: str) -> List[Dict[str, Any]]:
        """Get only enabled agent tools"""
        return [tool for tool in self.get_agent_tools(workflow_name) if tool.get("enabled", True)]
    
    def get_enabled_lifecycle_hooks(self, workflow_name: str) -> List[Dict[str, Any]]:
        """Get only enabled lifecycle hooks"""
        return [hook for hook in self.get_lifecycle_hooks(workflow_name) if hook.get("enabled", True)]
    
    def get_workflow_name(self, workflow_name: str) -> str:
        """Get the workflow name from configuration, fallback to workflow_name if not specified"""
        config = self.get_config(workflow_name)
        return config.get("workflow_name", workflow_name)
    
    def get_max_turns(self, workflow_name: str) -> int:
        """Get the maximum turns for the workflow, default to 25 if not specified"""
        config = self.get_config(workflow_name)
        return config.get("max_turns", 25)
    
    def get_initiating_agent(self, workflow_name: str) -> str:
        """Get the initiating agent for the workflow, default to ContextVariablesAgent if not specified"""
        config = self.get_config(workflow_name)
        return config.get("initiating_agent", "ContextVariablesAgent")
    
    def reload_workflow(self, workflow_name: str):
        """Reload a specific workflow configuration from disk"""
        workflows_dir = Path(__file__).parent.parent.parent / "workflows"
        
        # Find the workflow directory by name (case-insensitive)
        workflow_dir = None
        for dir_item in workflows_dir.iterdir():
            if dir_item.is_dir() and dir_item.name.lower() == workflow_name.lower():
                workflow_dir = dir_item
                break
        
        if workflow_dir is None:
            logger.warning(f"⚠️ Workflow directory not found for: {workflow_name}")
            return {}
            
        config_file = workflow_dir / "workflow.json"
        
        if config_file.exists():
            try:
                with open(config_file, 'r') as f:
                    config = json.load(f)
                
                workflow_name = workflow_name.lower()
                self._configs[workflow_name] = config
                logger.info(f"🔄 Reloaded workflow config: {workflow_name} from {config_file}")
                return config
                
            except Exception as e:
                logger.error(f"❌ Failed to reload {config_file}: {e}")
                return {}
        else:
            logger.warning(f"⚠️ Workflow config not found: {config_file}")
            return {}
    
    def reload_all_workflows(self):
        """Reload all workflow configurations from disk"""
        global _global_configs, _configs_loaded
        
        self._configs.clear()
        _global_configs.clear()
        _configs_loaded = False
        
        # Reload fresh
        self._load_all_workflows()
        _global_configs = self._configs.copy()
        _configs_loaded = True
        
        logger.info("🔄 Reloaded all workflow configurations")
    
    @classmethod
    def reset_global_state(cls):
        """Reset global state for testing purposes"""
        global _global_configs, _configs_loaded
        _global_configs.clear()
        _configs_loaded = False
    
    def get_ui_capable_agents(self, workflow_name: str) -> List[Dict[str, Any]]:
        """Get ui_capable_agents for a workflow type"""
        config = self.get_config(workflow_name)
        return config.get("ui_capable_agents", [])

# Global instance
workflow_config = WorkflowConfig()
