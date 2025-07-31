# ==============================================================================
# FILE: core/workflow/file_manager.py
# DESCRIPTION: Modular workflow file manager - handles YAML/JSON config files
# ==============================================================================

import logging
import yaml
from typing import Dict, Any, List, Optional, Union
from pathlib import Path
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

@dataclass
class WorkflowFiles:
    """Container for workflow configuration files"""
    workflow_dir: Path
    agents: Dict[str, Any] = field(default_factory=dict)
    handoffs: Dict[str, Any] = field(default_factory=dict) 
    context_variables: Dict[str, Any] = field(default_factory=dict)
    orchestrator: Dict[str, Any] = field(default_factory=dict)
    structured_outputs: Dict[str, Any] = field(default_factory=dict)
    tools: Dict[str, Any] = field(default_factory=dict)
    ui_config: Dict[str, Any] = field(default_factory=dict)
    
    def merge_to_dict(self) -> Dict[str, Any]:
        """Merge all config sections into a single dictionary"""
        merged = {}
        
        # Core orchestrator settings (top-level)
        merged.update(self.orchestrator)
        
        # Main sections
        if self.agents:
            merged['agents'] = self.agents
        if self.handoffs:
            merged['handoffs'] = self.handoffs
        if self.context_variables:
            merged['context_variables'] = self.context_variables
        if self.structured_outputs:
            merged['structured_outputs'] = self.structured_outputs
        if self.tools:
            merged.update(self.tools)  # Tools sections go at top level
        if self.ui_config:
            merged.update(self.ui_config)  # UI config sections go at top level
            
        return merged


class WorkflowFileManager:
    """Manages loading and saving of modular workflow configuration files"""
    
    # Standard file names for each config section
    FILE_MAPPINGS = {
        'orchestrator': 'orchestrator.yaml',
        'agents': 'agents.yaml', 
        'handoffs': 'handoffs.yaml',
        'context_variables': 'context_variables.yaml',
        'structured_outputs': 'structured_outputs.yaml',
        'tools': 'tools.yaml',
        'ui_config': 'ui_config.yaml'
    }
    
    def __init__(self, workflows_base_dir: Optional[Path] = None):
        """Initialize file manager with base workflows directory"""
        if workflows_base_dir is None:
            workflows_base_dir = Path(__file__).parent.parent.parent / "workflows"
        self.workflows_base_dir = Path(workflows_base_dir)
        
    def load_workflow(self, workflow_name: str) -> Dict[str, Any]:
        """Load a complete workflow configuration from modular YAML files"""
        workflow_dir = self.workflows_base_dir / workflow_name
        
        if not workflow_dir.exists():
            logger.warning(f"Workflow directory not found: {workflow_dir}")
            return {}
            
        # Load from modular YAML files
        if self._has_modular_files(workflow_dir):
            logger.info(f"Loading modular workflow config for: {workflow_name}")
            return self._load_modular_workflow(workflow_dir)
            
        logger.warning(f"No modular workflow config found for: {workflow_name}")
        return {}
    
    def _has_modular_files(self, workflow_dir: Path) -> bool:
        """Check if workflow has modular YAML files"""
        # At minimum, we need orchestrator.yaml to consider it modular
        return (workflow_dir / self.FILE_MAPPINGS['orchestrator']).exists()
    
    def _load_modular_workflow(self, workflow_dir: Path) -> Dict[str, Any]:
        """Load workflow from modular YAML files"""
        workflow_files = WorkflowFiles(workflow_dir=workflow_dir)
        
        # Load each config section
        for section, filename in self.FILE_MAPPINGS.items():
            file_path = workflow_dir / filename
            if file_path.exists():
                try:
                    data = self._load_yaml_file(file_path)
                    setattr(workflow_files, section, data)
                    logger.debug(f"Loaded {section} from {filename}")
                except Exception as e:
                    logger.error(f"Failed to load {filename}: {e}")
                    
        return workflow_files.merge_to_dict()
    
    def _load_yaml_file(self, file_path: Path) -> Dict[str, Any]:
        """Load a single YAML file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.error(f"Failed to load YAML file {file_path}: {e}")
            return {}
    
    def save_modular_workflow(self, workflow_name: str, config: Dict[str, Any]) -> bool:
        """Split a workflow config into modular YAML files"""
        workflow_dir = self.workflows_base_dir / workflow_name
        workflow_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # Split config into sections
            sections = self._split_config(config)
            
            # Save each section to its YAML file
            for section_name, section_data in sections.items():
                if section_data:  # Only save non-empty sections
                    filename = self.FILE_MAPPINGS.get(section_name)
                    if filename:
                        file_path = workflow_dir / filename
                        self._save_yaml_file(file_path, section_data)
                        logger.info(f"Saved {section_name} to {filename}")
            
            logger.info(f"Successfully saved modular workflow: {workflow_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save modular workflow {workflow_name}: {e}")
            return False
    
    def _split_config(self, config: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """Split a unified config into sections"""
        sections = {}
        
        # Orchestrator section (top-level workflow settings)
        orchestrator_keys = [
            'workflow_name', 'max_turns', 'human_in_the_loop', 'startup_mode',
            'orchestration_pattern', 'initial_message_to_user', 'initial_message', 'recipient'
        ]
        sections['orchestrator'] = {k: v for k, v in config.items() if k in orchestrator_keys}
        
        # Direct mappings
        sections['agents'] = config.get('agents', {})
        sections['handoffs'] = config.get('handoffs', {})
        sections['context_variables'] = config.get('context_variables', {})
        sections['structured_outputs'] = config.get('structured_outputs', {})
        
        # Tools section (includes backend_tools, ui_tools, lifecycle_tools)
        tools_keys = ['backend_tools', 'ui_tools', 'lifecycle_tools']
        sections['tools'] = {k: v for k, v in config.items() if k in tools_keys}
        
        # UI config section (includes visual_agents and other UI settings)
        ui_keys = ['visual_agents', 'ui_capable_agents']
        sections['ui_config'] = {k: v for k, v in config.items() if k in ui_keys}
        
        return sections
    
    def _save_yaml_file(self, file_path: Path, data: Dict[str, Any]) -> None:
        """Save data to a YAML file"""
        with open(file_path, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, default_flow_style=False, indent=2, sort_keys=False)
    
    def list_workflows(self) -> List[str]:
        """List all available modular workflows"""
        workflows = []
        
        if not self.workflows_base_dir.exists():
            return workflows
            
        for item in self.workflows_base_dir.iterdir():
            if item.is_dir():
                # Check if it has modular files
                has_modular = self._has_modular_files(item)
                
                if has_modular:
                    workflows.append(item.name)
                    
        return sorted(workflows)
    
    def workflow_type(self, workflow_name: str) -> str:
        """Return 'modular' or 'missing' for a workflow"""
        workflow_dir = self.workflows_base_dir / workflow_name
        
        if not workflow_dir.exists():
            return 'missing'
            
        if self._has_modular_files(workflow_dir):
            return 'modular'
        else:
            return 'missing'


# Global instance
workflow_file_manager = WorkflowFileManager()
