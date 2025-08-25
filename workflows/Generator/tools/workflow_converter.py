# ==============================================================================
# FILE: workflows/Generator/tools/workflow_converter.py
# DESCRIPTION: Self-contained workflow file creator for Generator workflow
# ==============================================================================

from typing import Dict, Any, Optional, List
from pathlib import Path
import sys
import yaml
import json

# Add the project root to the path for logging only
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from logs.logging_config import get_workflow_logger

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
        wf_logger = get_workflow_logger(workflow_name=workflow_name)
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
                    wf_logger.info(f"📄 [SAVE_WORKFLOW] Saved {section_name} to {filename}")

        # Save any extra files content if provided in config['extra_files']
        try:
            extra_files = config.get('extra_files')
            if isinstance(extra_files, list):
                inferred_py_deps = set()
                inferred_js_deps = set()
                for item in extra_files:
                    if not isinstance(item, dict):
                        continue
                    name = item.get('filename')
                    content = item.get('filecontent', '')
                    if not name:
                        continue
                    # Ensure relative path
                    safe_name = str(name).strip().lstrip('/').lstrip('\\')
                    extra_path = workflow_dir / safe_name
                    extra_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(extra_path, 'w', encoding='utf-8') as ef:
                        ef.write(content if isinstance(content, str) else str(content))
                    saved_files.append(safe_name)
                    wf_logger.info(f"🧩 [SAVE_WORKFLOW] Saved extra file: {safe_name}")

                    # Light dependency inference for code files
                    try:
                        lower = safe_name.lower()
                        if lower.endswith('.py') and isinstance(content, str):
                            import re
                            for m in re.finditer(r'^(?:from|import)\s+([\w\.]+)', content, re.MULTILINE):
                                mod = m.group(1).split('.')[0]
                                if mod and mod not in {'os','sys','re','json','typing','pathlib','asyncio','logging','time'}:
                                    inferred_py_deps.add(mod)
                        if lower.endswith('.js') and isinstance(content, str):
                            import re
                            # ES imports
                            for m in re.finditer(r'^\s*import\s+(?:.+?\s+from\s+)?[\"\"]([^\"\"]+)[\"\"]', content, re.MULTILINE):
                                dep = m.group(1)
                                if dep and not dep.startswith('.') and '/' not in dep:
                                    inferred_js_deps.add(dep)
                            # CommonJS requires
                            for m in re.finditer(r'require\(\s*[\"\"]([^\"\"]+)[\"\"]\s*\)', content):
                                dep = m.group(1)
                                if dep and not dep.startswith('.') and '/' not in dep:
                                    inferred_js_deps.add(dep)
                    except Exception:
                        pass

                # Optionally write minimal dependency manifests if we inferred any
                try:
                    if inferred_py_deps:
                        req = workflow_dir / 'requirements.txt'
                        if not req.exists():
                            req.write_text('\n'.join(sorted(inferred_py_deps)), encoding='utf-8')
                            saved_files.append('requirements.txt')
                            wf_logger.info(f"📦 [SAVE_WORKFLOW] Generated requirements.txt with {len(inferred_py_deps)} deps")
                    if inferred_js_deps:
                        pkg = workflow_dir / 'package.json'
                        if not pkg.exists():
                            pkg_obj = {
                                "name": workflow_name.replace(' ', '-').lower(),
                                "private": True,
                                "version": "0.1.0",
                                "type": "module",
                                "dependencies": {dep: "*" for dep in sorted(inferred_js_deps)}
                            }
                            import json as _json
                            pkg.write_text(_json.dumps(pkg_obj, indent=2), encoding='utf-8')
                            saved_files.append('package.json')
                            wf_logger.info(f"📦 [SAVE_WORKFLOW] Generated package.json with {len(inferred_js_deps)} deps")
                except Exception:
                    pass
        except Exception as ef_err:
            wf_logger.warning(f"⚠️ [SAVE_WORKFLOW] Failed to save extra files: {ef_err}")
        
        wf_logger.info(f"✅ [SAVE_WORKFLOW] Successfully saved {len(saved_files)} YAML files for workflow: {workflow_name}")
        return True
        
    except Exception as e:
        get_workflow_logger(workflow_name=workflow_name).error(f"❌ [SAVE_WORKFLOW] Failed to save workflow {workflow_name}: {e}")
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
        wf_logger = get_workflow_logger(workflow_name=workflow_name)
        
        if not config_to_save:
            return {
                "status": "error",
                "message": "No config provided to save"
            }
        
        wf_logger.info(f"💾 [SAVE_WORKFLOW] Saving modular config for: {workflow_name}")
        
        # Save provided config as modular files using self-contained function
        success = _save_modular_workflow(workflow_name, config_to_save)
        
        if success:
            wf_logger.info(f"✅ [SAVE_WORKFLOW] Successfully saved modular config for: {workflow_name}")
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
        get_workflow_logger(workflow_name=data.get('workflow_name', 'Generated_Workflow')).error(f"❌ [SAVE_WORKFLOW] Error: {e}")
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
        wf_logger = get_workflow_logger(workflow_name=workflow_name)
        wf_logger.info(f"📁 [CREATE_WORKFLOW_FILES] Creating modular YAML files for: {workflow_name}")
        
    # Build the complete config from agent outputs
        config = {}
        
        # Extract orchestrator settings from OrchestratorAgent output
        orchestrator_output = data.get('orchestrator_output', {})
        if orchestrator_output:
            # OrchestratorAgent outputs JSON with workflow settings
            config.update(orchestrator_output)
            wf_logger.info(f"📋 [CREATE_WORKFLOW_FILES] Added orchestrator config")
        
        # Extract agents from AgentsAgent output
        agents_output = data.get('agents_output', {})
        if agents_output and 'agents' in agents_output:
            # AgentsAgent outputs JSON like: {"agents": [...]}
            config['agents'] = agents_output['agents']
            wf_logger.info(f"📋 [CREATE_WORKFLOW_FILES] Added {len(agents_output['agents'])} agents")
        
        # Extract handoffs from HandoffsAgent output
        handoffs_output = data.get('handoffs_output', {})
        if handoffs_output and 'handoff_rules' in handoffs_output:
            # HandoffsAgent outputs JSON like: {"handoff_rules": [...]}
            config['handoffs'] = {'handoff_rules': handoffs_output['handoff_rules']}
            wf_logger.info(f"📋 [CREATE_WORKFLOW_FILES] Added {len(handoffs_output['handoff_rules'])} handoff rules")
        
        # Extract context variables from ContextVariablesAgent output
        context_vars_output = data.get('context_variables_output', {})
        if context_vars_output and 'context_variables' in context_vars_output:
            # ContextVariablesAgent outputs JSON like: {"context_variables": [...]}
            config['context_variables'] = context_vars_output
            wf_logger.info(f"📋 [CREATE_WORKFLOW_FILES] Added {len(context_vars_output['context_variables'])} context variables")
        
        # Add structured outputs (pre-defined or from StructuredOutputsAgent)
        structured_outputs = data.get('structured_outputs', {})
        structured_outputs_agent_output = data.get('structured_outputs_agent_output', {})
        
        if structured_outputs_agent_output and ('models' in structured_outputs_agent_output or 'registry' in structured_outputs_agent_output):
            # StructuredOutputsAgent outputs JSON like: {"models": [...], "registry": [...]}
            config['structured_outputs'] = structured_outputs_agent_output
            wf_logger.info(f"📋 [CREATE_WORKFLOW_FILES] Added dynamic structured outputs")
        elif structured_outputs:
            config['structured_outputs'] = structured_outputs
            wf_logger.info(f"📋 [CREATE_WORKFLOW_FILES] Added pre-defined structured outputs")
        
        # Add tools configuration from ToolsManagerAgent
        tools_manager_output = data.get('tools_manager_output', {})
        if tools_manager_output and 'tools_config' in tools_manager_output:
            # ToolsManagerAgent outputs JSON string in tools_config field
            tools_config_str = tools_manager_output['tools_config']
            if isinstance(tools_config_str, str):
                try:
                    tools_config = json.loads(tools_config_str)
                    config.update(tools_config)
                    wf_logger.info(f"📋 [CREATE_WORKFLOW_FILES] Added tools configuration")
                except json.JSONDecodeError as e:
                    wf_logger.warning(f"⚠️ [CREATE_WORKFLOW_FILES] Failed to parse tools_config JSON: {e}")
            elif isinstance(tools_config_str, dict):
                # Handle case where it's already parsed as dict
                config.update(tools_config_str)
                wf_logger.info(f"📋 [CREATE_WORKFLOW_FILES] Added tools configuration")
        
        # Legacy: Add tools configuration (fallback)
        tools_config = data.get('tools_config', {})
        if tools_config and not tools_manager_output:
            # Tools sections go at top level
            config.update(tools_config)
            wf_logger.info(f"📋 [CREATE_WORKFLOW_FILES] Added legacy tools configuration")
        
        # Add UI configuration
        ui_config = data.get('ui_config', {})
        if ui_config:
            # UI config sections go at top level
            config.update(ui_config)
            wf_logger.info(f"📋 [CREATE_WORKFLOW_FILES] Added UI configuration")

        # Add extra files to config so they can be saved
        extra_files = data.get('extra_files')
        
        # Extract files from ToolsAgent output
        tools_agent_output = data.get('tools_agent_output', {})
        if tools_agent_output and 'files' in tools_agent_output:
            # ToolsAgent outputs JSON like: {"files": [...]}
            tools_files = tools_agent_output['files']
            if isinstance(tools_files, list):
                if extra_files:
                    extra_files.extend(tools_files)
                else:
                    extra_files = tools_files
                wf_logger.info(f"📋 [CREATE_WORKFLOW_FILES] Added {len(tools_files)} files from ToolsAgent")
        
        if isinstance(extra_files, list) and extra_files:
            config['extra_files'] = extra_files
            wf_logger.info(f"📋 [CREATE_WORKFLOW_FILES] Added {len(extra_files)} extra files")
        
        # Apply backend defaults for orchestrator fields if missing
        def _apply_orchestrator_defaults(cfg: Dict[str, Any]):
            # Core defaults
            cfg.setdefault('max_turns', 25)
            cfg.setdefault('human_in_the_loop', False)
            cfg.setdefault('orchestration_pattern', 'DefaultPattern')
            cfg.setdefault('startup_mode', 'BackendOnly')
            # Message logic
            mode = cfg.get('startup_mode')
            if mode == 'UserDriven':
                # user provides initial input
                if 'initial_message_to_user' not in cfg or cfg.get('initial_message_to_user') is None:
                    cfg['initial_message_to_user'] = 'Please provide the required input to begin.'
                cfg['initial_message'] = None
            else:
                # AgentDriven / BackendOnly
                if 'initial_message' not in cfg or cfg.get('initial_message') is None:
                    cfg['initial_message'] = 'Initialize workflow sequence.'
                cfg['initial_message_to_user'] = None
            # Ensure arrays
            cfg.setdefault('visual_agents', [])
            cfg.setdefault('ui_capable_agents', [])
            return cfg

        _apply_orchestrator_defaults(config)

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

            # Include extra files saved
            try:
                if 'extra_files' in config:
                    for item in config['extra_files']:
                        if isinstance(item, dict) and item.get('filename'):
                            safe_name = str(item['filename']).strip().lstrip('/').lstrip('\\')
                            if (workflow_dir / safe_name).exists():
                                created_files.append(safe_name)
            except Exception:
                pass
            
            wf_logger.info(f"✅ [CREATE_WORKFLOW_FILES] Created {len(created_files)} modular YAML files for: {workflow_name}")
            
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
                
                wf_logger.info(f"📝 [CREATE_WORKFLOW_FILES] Updated context variables with workflow record")
            
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
        get_workflow_logger(workflow_name=data.get('workflow_name', 'Generated_Workflow')).error(f"❌ [CREATE_WORKFLOW_FILES] Error: {e}")
        return {"status": "error", "message": str(e)}


# Export the main functions for use in the workflow
__all__ = ['convert_workflow_to_modular', 'create_workflow_files']