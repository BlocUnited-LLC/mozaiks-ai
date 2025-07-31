# ==============================================================================
# FILE: workflows/Generator/tools/workflow_converter.py
# DESCRIPTION: Self-contained workflow file creator for Generator workflow
# ==============================================================================

import logging
import yaml
from typing import Dict, Any, Optional
from pathlib import Path
import sys

# Add the project root to the path for logging only
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from logs.logging_config import get_business_logger

business_logger = get_business_logger("workflow_converter")

# Standard YAML file mappings for workflows
WORKFLOW_FILE_MAPPINGS = {
    'orchestrator': 'orchestrator.yaml',
    'agents': 'agents.yaml', 
    'handoffs': 'handoffs.yaml',
    'context_variables': 'context_variables.yaml',
    'structured_outputs': 'structured_outputs.yaml',
    'tools': 'tools.yaml',
    'ui_config': 'ui_config.yaml'
}

def _save_yaml_file(file_path: Path, data: Dict[str, Any]) -> None:
    """Save data to a YAML file"""
    with open(file_path, 'w', encoding='utf-8') as f:
        yaml.dump(data, f, default_flow_style=False, indent=2, sort_keys=False)

def _split_config_into_sections(config: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Split a unified config into sections for separate YAML files"""
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

def _save_modular_workflow(workflow_name: str, config: Dict[str, Any]) -> bool:
    """Save a workflow config as modular YAML files"""
    try:
        # Determine workflows directory (relative to this file)
        workflows_base_dir = Path(__file__).parent.parent.parent
        workflow_dir = workflows_base_dir / workflow_name
        workflow_dir.mkdir(parents=True, exist_ok=True)
        
        # Split config into sections
        sections = _split_config_into_sections(config)
        
        # Save each section to its YAML file
        saved_files = []
        for section_name, section_data in sections.items():
            if section_data:  # Only save non-empty sections
                filename = WORKFLOW_FILE_MAPPINGS.get(section_name)
                if filename:
                    file_path = workflow_dir / filename
                    _save_yaml_file(file_path, section_data)
                    saved_files.append(filename)
                    business_logger.info(f"📄 [SAVE_WORKFLOW] Saved {section_name} to {filename}")
        
        business_logger.info(f"✅ [SAVE_WORKFLOW] Successfully saved {len(saved_files)} YAML files for workflow: {workflow_name}")
        return True
        
    except Exception as e:
        business_logger.error(f"❌ [SAVE_WORKFLOW] Failed to save workflow {workflow_name}: {e}")
        return False


async def convert_workflow_to_modular(data: Dict[str, Any], context_variables: Optional[Any] = None) -> Dict[str, Any]:
    """
    Save a workflow configuration as modular YAML files
    
    Args:
        data: Contains workflow_name and the config to save
        context_variables: AG2 ContextVariables for sharing state between agents
        
    Returns:
        Response dictionary with save status
    """
    try:
        workflow_name = data.get('workflow_name', 'Generated_Workflow')
        config_to_save = data.get('config')
        
        if not config_to_save:
            return {
                "status": "error",
                "message": "No config provided to save"
            }
        
        business_logger.info(f"💾 [SAVE_WORKFLOW] Saving modular config for: {workflow_name}")
        
        # Save provided config as modular files using self-contained function
        success = _save_modular_workflow(workflow_name, config_to_save)
        
        if success:
            business_logger.info(f"✅ [SAVE_WORKFLOW] Successfully saved modular config for: {workflow_name}")
            return {
                "status": "success",
                "message": f"Successfully saved {workflow_name} as modular YAML files",
                "workflow_name": workflow_name,
                "action": "saved_modular"
            }
        else:
            return {
                "status": "error", 
                "message": f"Failed to save modular config for {workflow_name}"
            }
                
    except Exception as e:
        business_logger.error(f"❌ [SAVE_WORKFLOW] Error: {e}")
        return {"status": "error", "message": str(e)}


async def create_workflow_files(data: Dict[str, Any], context_variables: Optional[Any] = None) -> Dict[str, Any]:
    """
    Create individual workflow YAML files from agent outputs
    
    Args:
        data: Contains the various workflow sections from agent outputs
            Expected structure:
            {
                'workflow_name': 'MyWorkflow',
                'orchestrator_output': {...},      # From OrchestratorAgent
                'agents_output': {...},            # From AgentsAgent  
                'handoffs_output': {...},          # From HandoffsAgent
                'context_variables_output': {...}, # From ContextVariablesAgent
                'structured_outputs': {...},       # Pre-defined or from agent
                'tools_config': {...},             # Tool configurations
                'ui_config': {...}                 # UI configurations
            }
        context_variables: AG2 ContextVariables for sharing state between agents
        
    Returns:
        Response dictionary with creation status and file paths
    """
    try:
        workflow_name = data.get('workflow_name', 'Generated_Workflow')
        
        business_logger.info(f"📁 [CREATE_WORKFLOW_FILES] Creating modular YAML files for: {workflow_name}")
        
        # Build the complete config from agent outputs
        config = {}
        
        # Extract orchestrator settings from OrchestratorAgent output
        orchestrator_output = data.get('orchestrator_output', {})
        if orchestrator_output:
            # OrchestratorAgent outputs JSON with workflow settings
            config.update(orchestrator_output)
            business_logger.info(f"📋 [CREATE_WORKFLOW_FILES] Added orchestrator config")
        
        # Extract agents from AgentsAgent output
        agents_output = data.get('agents_output', {})
        if agents_output and 'agents' in agents_output:
            # AgentsAgent outputs JSON like: {"agents": [...]}
            config['agents'] = agents_output['agents']
            business_logger.info(f"📋 [CREATE_WORKFLOW_FILES] Added {len(agents_output['agents'])} agents")
        
        # Extract handoffs from HandoffsAgent output
        handoffs_output = data.get('handoffs_output', {})
        if handoffs_output and 'handoff_rules' in handoffs_output:
            # HandoffsAgent outputs JSON like: {"handoff_rules": [...]}
            config['handoffs'] = {'handoff_rules': handoffs_output['handoff_rules']}
            business_logger.info(f"📋 [CREATE_WORKFLOW_FILES] Added {len(handoffs_output['handoff_rules'])} handoff rules")
        
        # Extract context variables from ContextVariablesAgent output
        context_vars_output = data.get('context_variables_output', {})
        if context_vars_output and 'context_variables' in context_vars_output:
            # ContextVariablesAgent outputs JSON like: {"context_variables": [...]}
            config['context_variables'] = {'variables': context_vars_output['context_variables']}
            business_logger.info(f"📋 [CREATE_WORKFLOW_FILES] Added {len(context_vars_output['context_variables'])} context variables")
        
        # Add structured outputs (usually pre-defined)
        structured_outputs = data.get('structured_outputs', {})
        if structured_outputs:
            config['structured_outputs'] = structured_outputs
            business_logger.info(f"📋 [CREATE_WORKFLOW_FILES] Added structured outputs")
        
        # Add tools configuration
        tools_config = data.get('tools_config', {})
        if tools_config:
            # Tools sections go at top level
            config.update(tools_config)
            business_logger.info(f"📋 [CREATE_WORKFLOW_FILES] Added tools configuration")
        
        # Add UI configuration
        ui_config = data.get('ui_config', {})
        if ui_config:
            # UI config sections go at top level
            config.update(ui_config)
            business_logger.info(f"📋 [CREATE_WORKFLOW_FILES] Added UI configuration")
        
        # Save as modular YAML files using self-contained function
        success = _save_modular_workflow(workflow_name, config)
        
        if success:
            # Get the workflow directory to list created files
            workflows_base_dir = Path(__file__).parent.parent.parent
            workflow_dir = workflows_base_dir / workflow_name
            created_files = []
            
            for section, filename in WORKFLOW_FILE_MAPPINGS.items():
                file_path = workflow_dir / filename
                if file_path.exists():
                    created_files.append(filename)
            
            business_logger.info(f"✅ [CREATE_WORKFLOW_FILES] Created {len(created_files)} modular YAML files for: {workflow_name}")
            
            # Update context variables to track created workflow
            if context_variables:
                workflow_files = context_variables.get('generated_workflow_files', [])
                if workflow_files is None:
                    workflow_files = []
                    
                workflow_record = {
                    'workflow_name': workflow_name,
                    'files': created_files,
                    'file_count': len(created_files),
                    'workflow_dir': str(workflow_dir),
                    'created_at': str(__import__('time').time())
                }
                
                workflow_files.append(workflow_record)
                context_variables.set('generated_workflow_files', workflow_files)
                context_variables.set('latest_workflow', workflow_record)
                
                business_logger.info(f"📝 [CREATE_WORKFLOW_FILES] Updated context variables with workflow record")
            
            return {
                "status": "success",
                "message": f"Successfully created {len(created_files)} modular YAML files for workflow '{workflow_name}'",
                "workflow_name": workflow_name,
                "files": created_files,
                "file_count": len(created_files),
                "workflow_dir": str(workflow_dir),
                "details": f"Created: {', '.join(created_files)}"
            }
        else:
            return {
                "status": "error",
                "message": f"Failed to create modular YAML files for workflow '{workflow_name}'"
            }
            
    except Exception as e:
        business_logger.error(f"❌ [CREATE_WORKFLOW_FILES] Error: {e}")
        return {"status": "error", "message": str(e)}


# Export the main functions for use in the workflow
__all__ = ['convert_workflow_to_modular', 'create_workflow_files']
