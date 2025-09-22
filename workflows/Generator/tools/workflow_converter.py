# ==============================================================================
# FILE: workflows/Generator/tools/workflow_converter.py
# DESCRIPTION: Self-contained workflow file creator for Generator workflow
# ==============================================================================

from typing import Dict, Any, Optional, List
from pathlib import Path
import sys
import json
import os

# Add the project root to the path for logging only
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from logs.logging_config import get_workflow_logger

# Standard JSON file mappings for workflows
WORKFLOW_FILE_MAPPINGS = {
    'orchestrator': 'orchestrator.json',
    'agents': 'agents.json',
    'handoffs': 'handoffs.json',
    'context_variables': 'context_variables.json',
    'structured_outputs': 'structured_outputs.json',
    'hooks': 'hooks.json', 
    'tools': 'tools.json',
    'ui_config': 'ui_config.json'
}


def _save_json_file(file_path: Path, data: Dict[str, Any]) -> None:
    """Save data to a JSON file"""
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _split_config_into_sections(config: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Split a unified config into sections for separate JSON files"""
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
    sections['hooks'] = config.get('hooks', {})
    sections['tools'] = config.get('tools', {})
    sections['ui_config'] = {k: v for k, v in config.items() if k in ['visual_agents', 'visual_agent']}

    return sections


# -----------------------------
# Structured outputs utilities
# -----------------------------

def _normalize_model_library(models: Any) -> Dict[str, Any]:
    """Normalize model library into dict form."""
    if isinstance(models, dict):
        return dict(models)

    lib: Dict[str, Any] = {}
    if isinstance(models, list):
        for md in models:
            if not isinstance(md, dict):
                continue
            name = md.get('model_name')
            fields_list = md.get('fields') or []
            if not name or not isinstance(fields_list, list):
                continue
            fields_dict: Dict[str, Any] = {}
            for f in fields_list:
                if not isinstance(f, dict):
                    continue
                fname = f.get('name')
                ftype = f.get('type')
                fdesc = f.get('description')
                if fname and ftype:
                    fields_dict[fname] = {"type": ftype}
                    if fdesc is not None:
                        fields_dict[fname]["description"] = fdesc
            lib[name] = {"type": "model", "fields": fields_dict}
    return lib


def _normalize_registry_map(registry: Any) -> Dict[str, Any]:
    """Normalize registry to dict form."""
    if isinstance(registry, dict):
        return dict(registry)

    reg: Dict[str, Any] = {}
    if isinstance(registry, list):
        for entry in registry:
            if not isinstance(entry, dict):
                continue
            agent = entry.get('agent')
            model = entry.get('agent_definition', None)
            if agent:
                reg[agent] = model
    return reg


def _extract_agent_names(agents_output: Dict[str, Any]) -> List[str]:
    """Return agent variable names from AgentsAgent output."""
    names: List[str] = []
    if isinstance(agents_output, dict) and isinstance(agents_output.get('agents'), list):
        for a in agents_output['agents']:
            if isinstance(a, dict):
                name = a.get('name')
                if isinstance(name, str) and name.strip():
                    names.append(name.strip())
    return names


def _merge_structured_outputs(
    static_so: Dict[str, Any],
    dynamic_so: Dict[str, Any],
    agent_names: List[str],
    wf_logger
) -> Dict[str, Any]:
    """Merge static and dynamic structured outputs."""
    static_models = _normalize_model_library(static_so.get('models', {}))
    static_registry = _normalize_registry_map(static_so.get('registry', {}))

    dynamic_models = _normalize_model_library(dynamic_so.get('models', []))
    dynamic_registry = _normalize_registry_map(dynamic_so.get('registry', []))

    merged_models = dict(static_models)
    for mname, mdef in dynamic_models.items():
        merged_models[mname] = mdef

    merged_registry = dict(static_registry)
    for agent, model in dynamic_registry.items():
        merged_registry[agent] = model

    for agent in agent_names:
        if agent not in merged_registry:
            merged_registry[agent] = None

    wf_logger.info(
        f"🧩 [STRUCTURED_OUTPUTS] models={len(merged_models)} registry={len(merged_registry)}"
    )

    return {"models": merged_models, "registry": merged_registry}


def _save_modular_workflow(workflow_name: str, config: Dict[str, Any]) -> bool:
    """Save a workflow config as modular JSON files"""
    try:
        wf_logger = get_workflow_logger(workflow_name=workflow_name)
        workflows_base_dir = Path(__file__).parent.parent.parent
        workflow_dir = workflows_base_dir / workflow_name
        workflow_dir.mkdir(parents=True, exist_ok=True)

        sections = _split_config_into_sections(config)
        saved_files = []

        for section_name, section_data in sections.items():
            filename = WORKFLOW_FILE_MAPPINGS.get(section_name)
            if not filename:
                continue

            # structured_outputs
            if section_name == "structured_outputs":
                if isinstance(section_data, dict):
                    section_data.setdefault("models", {})
                    section_data.setdefault("registry", {})
                    file_path = workflow_dir / filename
                    _save_json_file(file_path, section_data)
                    saved_files.append(filename)
                    wf_logger.info(f"📄 [SAVE] structured_outputs saved → {filename}")
                continue

            # context_variables (unwrap wrapper)
            if section_name == "context_variables":
                if isinstance(section_data, dict):
                    plan = section_data.get("ContextVariablesPlan") or section_data
                    # Support legacy (defined_variables/runtime_variables) and new (database_variables/environment_variables)
                    has_legacy = any(k in plan for k in ("defined_variables", "runtime_variables"))
                    has_new = any(k in plan for k in ("database_variables", "environment_variables", "derived_variables"))
                    if has_legacy or has_new:
                        file_path = workflow_dir / filename
                        _save_json_file(file_path, plan)
                        saved_files.append(filename)
                        if has_new:
                            wf_logger.info(
                                f"📄 [SAVE] context_variables saved → {filename} "
                                f"(db={len(plan.get('database_variables', []))}, env={len(plan.get('environment_variables', []))}, derived={len(plan.get('derived_variables', []))})"
                            )
                        else:
                            wf_logger.info(
                                f"📄 [SAVE] context_variables (legacy) saved → {filename} "
                                f"(defined={len(plan.get('defined_variables', []))}, runtime={len(plan.get('runtime_variables', []))}, derived={len(plan.get('derived_variables', []))})"
                            )
                continue

            if section_data:
                file_path = workflow_dir / filename
                _save_json_file(file_path, section_data)
                saved_files.append(filename)
                wf_logger.info(f"📄 [SAVE] {section_name} saved → {filename}")

        wf_logger.info(f"✅ [SAVE] Saved {len(saved_files)} sections for workflow={workflow_name}")
        return True

    except Exception as e:
        get_workflow_logger(workflow_name=workflow_name).error(
            f"❌ [SAVE] Failed to save workflow {workflow_name}: {e}"
        )
        return False


async def convert_workflow_to_modular(data: Dict[str, Any], context_variables: Optional[Any] = None) -> Dict[str, Any]:
    """Save a workflow configuration as modular JSON files"""
    try:
        workflow_name = data.get('workflow_name', 'Generated_Workflow')
        config_to_save = data.get('config')
        wf_logger = get_workflow_logger(workflow_name=workflow_name)

        if not config_to_save:
            return {"status": "error", "message": "No config provided to save"}

        wf_logger.info(f"💾 [CONVERT] Saving modular config for {workflow_name}")
        success = _save_modular_workflow(workflow_name, config_to_save)

        if success:
            return {"status": "success", "workflow_name": workflow_name, "action": "saved_modular"}
        else:
            return {"status": "error", "message": f"Failed to save {workflow_name}"}

    except Exception as e:
        get_workflow_logger(workflow_name=data.get('workflow_name', 'Generated_Workflow')).error(f"❌ [CONVERT] Error: {e}")
        return {"status": "error", "message": str(e)}


async def create_workflow_files(data: Dict[str, Any], context_variables: Optional[Any] = None) -> Dict[str, Any]:
    """
    Create individual workflow JSON files from agent outputs

    Args:
        data: Contains the various workflow sections from agent outputs
            Expected structure:
            {
                'workflow_name': 'MyWorkflow',
                'orchestrator_output': {...},        # OrchestratorAgent
                'agents_output': {...},              # AgentsAgent
                'handoffs_output': {...},            # HandoffsAgent
                'context_variables_output': {...},   # ContextVariablesAgent
                'hooks_output': {...},               # HookAgent (metadata + optional files)
                'structured_outputs': {...},         # Static base (model library + default registry)
                'structured_outputs_agent_output': {...}, # StructuredOutputsAgent (dynamic)
                'tools_manager_output': {...},       # ToolsManagerAgent (tools_config string)
                'tools_agent_output': {...},         # Legacy/other tools provider
                'ui_config': {...},                  # UI config (visual_agents, visual_agent)
                'extra_files': [...]                 # Additional arbitrary files
            }
        context_variables: AG2 ContextVariables for sharing state between agents

    Returns:
        Response dictionary with creation status and file paths
    """
    try:
        workflow_name = data.get('workflow_name', 'Generated_Workflow')
        wf_logger = get_workflow_logger(workflow_name=workflow_name)
        wf_logger.info(f"📁 [CREATE_WORKFLOW_FILES] Creating modular JSON files for: {workflow_name}")

        # Build the complete config from agent outputs
        config: Dict[str, Any] = {}

        # Extract orchestrator settings from OrchestratorAgent output
        orchestrator_output = data.get('orchestrator_output', {})
        if orchestrator_output:
            config.update(orchestrator_output)
            wf_logger.info(f"📋 [CREATE_WORKFLOW_FILES] Added orchestrator config")

        # Extract agents from AgentsAgent output
        agents_output = data.get('agents_output', {})
        agent_names = _extract_agent_names(agents_output)
        if agents_output and 'agents' in agents_output:
            config['agents'] = agents_output['agents']
            wf_logger.info(f"📋 [CREATE_WORKFLOW_FILES] Added {len(agents_output['agents'])} agents")

        # Extract handoffs from HandoffsAgent output
        handoffs_output = data.get('handoffs_output', {})
        if handoffs_output and 'handoff_rules' in handoffs_output:
            config['handoffs'] = {'handoff_rules': handoffs_output['handoff_rules']}
            wf_logger.info(f"📋 [CREATE_WORKFLOW_FILES] Added {len(handoffs_output['handoff_rules'])} handoff rules")

        # Extract hooks from HookAgent output (metadata only + optional filecontent -> extra_files)
        hooks_output = data.get('hooks_output', {})
        if hooks_output and 'hooks' in hooks_output:
            raw_hooks = hooks_output.get('hooks', [])
            metadata_hooks: List[Dict[str, Any]] = []
            hook_extra_files: List[Dict[str, Any]] = []
            for h in raw_hooks:
                if not isinstance(h, dict):
                    continue
                filename = h.get('filename') or h.get('file')  # prefer 'filename'
                fn = h.get('function')
                # Normalize function (strip module prefix if present)
                if isinstance(fn, str):
                    if ':' in fn:
                        fn = fn.split(':', 1)[1]
                    if '.' in fn:
                        fn = fn.split('.')[-1]
                    fn = fn.strip()
                metadata_hooks.append({
                    'hook_type': h.get('hook_type'),
                    'hook_agent': h.get('hook_agent'),
                    'filename': filename,
                    'function': fn,
                })
                # Prepare file write (tools/<filename>) if filecontent provided
                filecontent = h.get('filecontent')
                if filename and isinstance(filecontent, str) and filecontent.strip():
                    hook_extra_files.append({
                        'filename': f"tools/{filename}",
                        'filecontent': filecontent
                    })
            if metadata_hooks:
                config['hooks'] = {'hooks': metadata_hooks}
                wf_logger.info(f"📋 [CREATE_WORKFLOW_FILES] Added {len(metadata_hooks)} hook metadata entries")
            if hook_extra_files:
                existing_extra = data.get('extra_files') or []
                if not isinstance(existing_extra, list):
                    existing_extra = []
                existing_extra.extend(hook_extra_files)
                data['extra_files'] = existing_extra
                wf_logger.info(f"🧩 [CREATE_WORKFLOW_FILES] Collected {len(hook_extra_files)} hook implementation files")

        # Extract context variables from ContextVariablesAgent output
        context_variables_output = data.get('context_variables_output', {})
        if context_variables_output and 'context_variables' in context_variables_output:
            config['context_variables'] = context_variables_output
            wf_logger.info(f"📋 [CREATE_WORKFLOW_FILES] Added {len(context_variables_output['context_variables'])} context variables")

        # -----------------------------
        # Structured outputs (MERGE)
        # -----------------------------
        static_structured = data.get('structured_outputs', {}) or {}
        dynamic_structured = data.get('structured_outputs_agent_output', {}) or {}

        merged_structured = _merge_structured_outputs(static_structured, dynamic_structured, agent_names, wf_logger)

        # Guarantee presence of top-level keys even if empty
        if not isinstance(merged_structured.get('models'), dict):
            merged_structured['models'] = {}
        if not isinstance(merged_structured.get('registry'), dict):
            merged_structured['registry'] = {}

        config['structured_outputs'] = merged_structured
        wf_logger.info("📋 [CREATE_WORKFLOW_FILES] Prepared structured_outputs (merged static+dynamic and completed registry)")

        # Add tools configuration from ToolsManagerAgent (authoritative)
        tools_manager_output = data.get('tools_manager_output', {})
        if isinstance(tools_manager_output, dict):
            # Directly structured output case
            if "tools" in tools_manager_output and isinstance(tools_manager_output["tools"], list):
                config["tools"] = {"tools": tools_manager_output["tools"]}
                wf_logger.info(f"📋 [CREATE_WORKFLOW_FILES] Added tools configuration (tools_list={len(tools_manager_output['tools'])})")
            # tools_config string case
            elif "tools_config" in tools_manager_output:
                tools_config_str = tools_manager_output["tools_config"]
                parsed = None
                if isinstance(tools_config_str, str):
                    try:
                        parsed = json.loads(tools_config_str)
                    except json.JSONDecodeError as e:
                        wf_logger.error(f"❌ [CREATE_WORKFLOW_FILES] Invalid tools_config JSON: {e}")
                elif isinstance(tools_config_str, dict):
                    parsed = tools_config_str
                if isinstance(parsed, dict) and isinstance(parsed.get("tools"), list):
                    config["tools"] = {"tools": parsed["tools"]}
                    wf_logger.info(f"📋 [CREATE_WORKFLOW_FILES] Added tools configuration (tools_list={len(parsed['tools'])})")
                else:
                    wf_logger.warning("⚠️ [CREATE_WORKFLOW_FILES] tools_config missing 'tools' list; no tools saved")

        # Add UI configuration
        ui_config = data.get('ui_config', {})
        if ui_config:
            config.update(ui_config)
            wf_logger.info(f"📋 [CREATE_WORKFLOW_FILES] Added UI configuration")

        # Add extra files to config so they can be saved
        extra_files = data.get('extra_files')

        # Extract files from ToolsAgent output
        tools_agent_output = data.get('tools_agent_output', {})
        if tools_agent_output and 'files' in tools_agent_output:
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
                if 'initial_message_to_user' not in cfg or cfg.get('initial_message_to_user') is None:
                    cfg['initial_message_to_user'] = 'Please provide the required input to begin.'
                cfg['initial_message'] = None
            else:
                if 'initial_message' not in cfg or cfg.get('initial_message') is None:
                    cfg['initial_message'] = 'Initialize workflow sequence.'
                cfg['initial_message_to_user'] = None
            # Ensure arrays
            cfg.setdefault('visual_agents', [])
            cfg.setdefault('visual_agent', [])
            return cfg

        _apply_orchestrator_defaults(config)

        # Save as modular JSON files using self-contained function
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

            wf_logger.info(f"✅ [CREATE_WORKFLOW_FILES] Created {len(created_files)} modular JSON files for: {workflow_name}")

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
                "message": f"Successfully created {len(created_files)} modular JSON files for workflow '{workflow_name}'",
                "workflow_name": workflow_name,
                "files": created_files,
                "file_count": len(created_files),
                "workflow_dir": str(workflow_dir),
                "details": f"Created: {', '.join(created_files)}"
            }
        else:
            return {
                "status": "error",
                "message": f"Failed to create modular JSON files for workflow '{workflow_name}'"
            }

    except Exception as e:
        get_workflow_logger(workflow_name=data.get('workflow_name', 'Generated_Workflow')).error(f"❌ [CREATE_WORKFLOW_FILES] Error: {e}")
        return {"status": "error", "message": str(e)}


# Export the main functions for use in the workflow
__all__ = ['convert_workflow_to_modular', 'create_workflow_files']
