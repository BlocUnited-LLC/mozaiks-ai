# ==============================================================================
# FILE: core/workflow/workflow_config.py
# DESCRIPTION: Dynamic workflow configuration loader - no hardcoding
# ==============================================================================
import json
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

class WorkflowConfig:
    """Dynamic workflow configuration loader"""
    
    def __init__(self):
        self._configs = {}
        self._load_all_workflows()
    
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
    
    def get_config(self, workflow_type: str) -> Dict[str, Any]:
        """Get configuration for a workflow type"""
        return self._configs.get(workflow_type.lower(), {})
    
    def has_human_in_the_loop(self, workflow_type: str) -> bool:
        """Check if workflow requires human interaction"""
        config = self.get_config(workflow_type)
        return config.get("human_in_the_loop", False)
    
    def get_chat_pane_agents(self, workflow_type: str) -> List[str]:
        """Get the agents that interact in the chat pane (inline components)"""
        config = self.get_config(workflow_type)
        ui_agents = config.get("ui_capable_agents", [])
        
        chat_agents = []
        for agent in ui_agents:
            capabilities = agent.get("capabilities", [])
            if "inline_components" in capabilities or "chat" in capabilities:
                chat_agents.append(agent.get("name"))
        
        return chat_agents
    
    def get_artifact_agents(self, workflow_type: str) -> List[str]:
        """Get the agents that handle artifacts"""
        config = self.get_config(workflow_type)
        ui_agents = config.get("ui_capable_agents", [])
        
        artifact_agents = []
        for agent in ui_agents:
            capabilities = agent.get("capabilities", [])
            if "artifacts" in capabilities:
                artifact_agents.append(agent.get("name"))
        
        return artifact_agents

    def get_initial_message(self, workflow_type: str) -> Optional[str]:
        """Get the initial message for a workflow type"""
        config = self.get_config(workflow_type)
        return config.get("initial_message", None)

    def get_visible_agents(self, workflow_type: str) -> List[str]:
        """Get the agents whose messages should appear in UI"""
        config = self.get_config(workflow_type)
        visible_agents = []
        
        # Auto-include user if human_in_the_loop is true
        if config.get("human_in_the_loop", False):
            visible_agents.append("user")
        
        # All ui_capable_agents are automatically visible
        ui_agents = config.get("ui_capable_agents", [])
        for agent in ui_agents:
            agent_name = agent.get("name")
            if agent_name and agent_name not in visible_agents:
                visible_agents.append(agent_name)
        
        return visible_agents
    
    def is_visible_agent(self, agent_name: str, workflow_type: str) -> bool:
        """Check if an agent's messages should appear in the UI"""
        visible_agents = self.get_visible_agents(workflow_type)
        return agent_name in visible_agents
    
    def get_frontend_agents(self, workflow_type: str) -> List[str]:
        """Get all agents that should appear in the frontend UI"""
        chat_agents = self.get_chat_pane_agents(workflow_type)
        artifact_agents = self.get_artifact_agents(workflow_type)
        return list(set(chat_agents + artifact_agents))
    
    def is_frontend_agent(self, agent_name: str, workflow_type: str) -> bool:
        """Check if an agent should appear in the frontend UI"""
        frontend_agents = self.get_frontend_agents(workflow_type)
        return agent_name in frontend_agents
    
    def should_auto_start(self, workflow_type: str) -> bool:
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
        config = self.get_config(workflow_type)
        
        # Use explicit auto_start setting if present
        if "auto_start" in config:
            return config["auto_start"]
            
        # Fallback: if no auto_start specified, use human_in_the_loop logic
        # human_in_the_loop: false → auto-start (autonomous)
        # human_in_the_loop: true → don't auto-start (wait for user)
        return not self.has_human_in_the_loop(workflow_type)
    
    def get_auto_start(self, workflow_type: str) -> bool:
        """Get auto_start setting for workflow, with fallback logic"""
        return self.should_auto_start(workflow_type)
    
    def get_all_workflow_types(self) -> list:
        """Get list of all available workflow types"""
        return list(self._configs.keys())
    
    def get_components_for_agent(self, workflow_type: str, agent_name: str) -> List[Dict[str, Any]]:
        """Get all components for a specific agent"""
        config = self.get_config(workflow_type)
        ui_agents = config.get("ui_capable_agents", [])
        
        for agent in ui_agents:
            if agent.get("name") == agent_name:
                return agent.get("components", [])
        
        return []
    
    def get_inline_components(self, workflow_type: str) -> List[Dict[str, Any]]:
        """Get all inline components across all agents"""
        config = self.get_config(workflow_type)
        ui_agents = config.get("ui_capable_agents", [])
        
        inline_components = []
        for agent in ui_agents:
            components = agent.get("components", [])
            for component in components:
                if component.get("type") == "inline":
                    inline_components.append(component)
        
        return inline_components
    
    def get_artifact_components(self, workflow_type: str) -> List[Dict[str, Any]]:
        """Get all artifact components across all agents"""
        config = self.get_config(workflow_type)
        ui_agents = config.get("ui_capable_agents", [])
        
        artifact_components = []
        for agent in ui_agents:
            components = agent.get("components", [])
            for component in components:
                if component.get("type") == "artifact":
                    artifact_components.append(component)
        
        return artifact_components
    
    def get_component_by_name(self, workflow_type: str, component_name: str) -> Optional[Dict[str, Any]]:
        """Get a specific component by name"""
        config = self.get_config(workflow_type)
        ui_agents = config.get("ui_capable_agents", [])
        
        for agent in ui_agents:
            components = agent.get("components", [])
            for component in components:
                if component.get("name") == component_name:
                    return component
        
        return None
    
    def get_agent_tools(self, workflow_type: str) -> List[Dict[str, Any]]:
        """Get all agent tools for a workflow"""
        config = self.get_config(workflow_type)
        tools = config.get("tools", {})
        return tools.get("agent_tools", [])
    
    def get_lifecycle_hooks(self, workflow_type: str) -> List[Dict[str, Any]]:
        """Get all lifecycle hooks for a workflow"""
        config = self.get_config(workflow_type)
        tools = config.get("tools", {})
        return tools.get("lifecycle_hooks", [])
    
    def get_enabled_agent_tools(self, workflow_type: str) -> List[Dict[str, Any]]:
        """Get only enabled agent tools"""
        return [tool for tool in self.get_agent_tools(workflow_type) if tool.get("enabled", True)]
    
    def get_enabled_lifecycle_hooks(self, workflow_type: str) -> List[Dict[str, Any]]:
        """Get only enabled lifecycle hooks"""
        return [hook for hook in self.get_lifecycle_hooks(workflow_type) if hook.get("enabled", True)]
    
    def get_workflow_name(self, workflow_type: str) -> str:
        """Get the workflow name from configuration, fallback to workflow_type if not specified"""
        config = self.get_config(workflow_type)
        return config.get("workflow_name", workflow_type)
    
    def get_max_turns(self, workflow_type: str) -> int:
        """Get the maximum turns for the workflow, default to 25 if not specified"""
        config = self.get_config(workflow_type)
        return config.get("max_turns", 25)
    
    def get_initiating_agent(self, workflow_type: str) -> str:
        """Get the initiating agent for the workflow, default to ContextVariablesAgent if not specified"""
        config = self.get_config(workflow_type)
        return config.get("initiating_agent", "ContextVariablesAgent")
    
    def reload_workflow(self, workflow_type: str):
        """Reload a specific workflow configuration from disk"""
        workflows_dir = Path(__file__).parent.parent.parent / "workflows"
        
        # Find the workflow directory by name (case-insensitive)
        workflow_dir = None
        for dir_item in workflows_dir.iterdir():
            if dir_item.is_dir() and dir_item.name.lower() == workflow_type.lower():
                workflow_dir = dir_item
                break
        
        if workflow_dir is None:
            logger.warning(f"⚠️ Workflow directory not found for: {workflow_type}")
            return {}
            
        config_file = workflow_dir / "workflow.json"
        
        if config_file.exists():
            try:
                with open(config_file, 'r') as f:
                    config = json.load(f)
                
                workflow_name = workflow_type.lower()
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
        self._configs.clear()
        self._load_all_workflows()
        logger.info("🔄 Reloaded all workflow configurations")
    
    def get_ui_capable_agents(self, workflow_type: str) -> List[Dict[str, Any]]:
        """Get ui_capable_agents for a workflow type"""
        config = self.get_config(workflow_type)
        return config.get("ui_capable_agents", [])

    def get_context_adjustment_agents(self, workflow_type: str) -> List[Dict[str, Any]]:
        """Get agents that have context_adjustment enabled"""
        ui_agents = self.get_ui_capable_agents(workflow_type)
        context_agents = []
        
        for agent in ui_agents:
            if agent.get("context_adjustment", False):
                context_agents.append(agent)
        
        return context_agents

    def has_context_adjustment_enabled(self, workflow_type: str, agent_name: str) -> bool:
        """Check if specific agent has context_adjustment enabled"""
        ui_agents = self.get_ui_capable_agents(workflow_type)
        
        for agent in ui_agents:
            if agent.get("name") == agent_name:
                return agent.get("context_adjustment", False)
        
        return False

# Global instance
workflow_config = WorkflowConfig()
