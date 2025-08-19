# ==============================================================================
# FILE: core/workflow/workflow_config.py
# DESCRIPTION: CLEAN configuration engine - ONLY loads and caches YAML configs
#              NO handlers, NO factories, NO discovery - just pure configuration
# ==============================================================================

import json
import logging
import yaml
from typing import Dict, Any, List, Optional
from pathlib import Path
from .file_manager import workflow_file_manager
from logs.logging_config import get_workflow_logger

logger = logging.getLogger(__name__)

# Global configuration cache
_global_configs: Dict[str, Dict[str, Any]] = {}
_configs_loaded: bool = False

class CleanWorkflowConfig:
    """
    CLEAN configuration engine - ONLY handles YAML loading and caching.
    
    This class has ONE job: load workflow configurations from disk and cache them.
    It does NOT create handlers, factories, or do discovery.
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        global _global_configs, _configs_loaded
        
        if _configs_loaded:
            self._configs = _global_configs
            # Contextual workflow logger for config engine
            self.wf_logger = get_workflow_logger(
                workflow_name="workflow.config",
                component="workflow_config",
            )
            self.wf_logger.debug("🔄 Using cached workflow configurations")
        else:
            self._configs = {}
            self._load_all_workflows()
            _global_configs = self._configs.copy()
            _configs_loaded = True
            # Initialize after load to ensure logger is available regardless
            self.wf_logger = get_workflow_logger(
                workflow_name="workflow.config",
                component="workflow_config",
            )
            self.wf_logger.debug(f"Loaded {len(self._configs)} workflow configurations")
    
    def _load_all_workflows(self) -> None:
        """Load all workflow configs using the file manager"""
        try:
            workflow_names = workflow_file_manager.list_workflows()
            
            if not workflow_names:
                self.wf_logger.warning("⚠️ No workflows found in the workflows directory")
                return
            
            for workflow_name in workflow_names:
                try:
                    config = workflow_file_manager.load_workflow(workflow_name)
                    
                    if config:
                        normalized_name = workflow_name.lower()
                        self._configs[normalized_name] = config
                    else:
                        self.wf_logger.warning(f"⚠️ Empty config for workflow: {workflow_name}")
                    
                except Exception as e:
                    self.wf_logger.error(f"❌ Failed to load workflow {workflow_name}: {e}")
                    
        except Exception as e:
            self.wf_logger.error(f"❌ Critical error loading workflows: {e}")
    
    # ========================================================================
    # CLEAN CONFIGURATION API - NO HANDLERS, NO FACTORIES
    # ========================================================================
    
    def get_config(self, workflow_name: str) -> Dict[str, Any]:
        """Get configuration for a workflow type"""
        normalized_name = workflow_name.lower()
        return self._configs.get(normalized_name, {})
    
    def has_human_in_the_loop(self, workflow_name: str) -> bool:
        """Check if workflow requires human interaction"""
        config = self.get_config(workflow_name)
        return config.get("human_in_the_loop", False)
    
    def get_inline_agents(self, workflow_name: str) -> List[str]:
        """Get list of agents that should appear in chat pane"""
        config = self.get_config(workflow_name)
        return config.get("chat_pane_agents", [])
    
    def get_artifact_agents(self, workflow_name: str) -> List[str]:
        """Get list of agents that produce artifacts"""
        config = self.get_config(workflow_name)
        return config.get("artifact_agents", [])
    
    def get_initial_message(self, workflow_name: str) -> Optional[str]:
        """Get initial message for workflow"""
        config = self.get_config(workflow_name)
        return config.get("initial_message")
    
    def get_ui_capable_agents(self, workflow_name: str) -> List[Dict[str, Any]]:
        """Get agents with UI capabilities"""
        config = self.get_config(workflow_name)
        return config.get("ui_capable_agents", [])
    
    def get_visible_agents(self, workflow_name: str) -> List[str]:
        """Get list of agents visible to users"""
        config = self.get_config(workflow_name)
        return config.get("visible_agents", [])
    
    def get_all_workflow_names(self) -> List[str]:
        """Get list of all loaded workflow names"""
        return list(self._configs.keys())
    
    def reload_workflow(self, workflow_name: str) -> Dict[str, Any]:
        """Reload a specific workflow configuration"""
        try:
            config = workflow_file_manager.load_workflow(workflow_name)
            if config:
                normalized_name = workflow_name.lower()
                self._configs[normalized_name] = config
                _global_configs[normalized_name] = config
                self.wf_logger.debug(f"Reloaded config: {workflow_name}")
                return config
            else:
                self.wf_logger.warning(f"⚠️ Failed to reload config: {workflow_name}")
                return {}
        except Exception as e:
            self.wf_logger.error(f"❌ Error reloading {workflow_name}: {e}")
            return {}

# ========================================================================
# CLEAN GLOBAL INSTANCE
# ========================================================================

# Single global instance for configuration only
clean_workflow_config = CleanWorkflowConfig()

# Export clean API
workflow_config = clean_workflow_config

__all__ = [
    "CleanWorkflowConfig",
    "clean_workflow_config", 
    "workflow_config"
]
