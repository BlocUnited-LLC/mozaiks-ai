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
    'hooks': 'hooks.json',  # store hook metadata ONLY (no filecontents)
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
    sections['hooks'] = config.get('hooks', {})  # Hook metadata

    # Tools section: Only honor canonical flat list form
    if isinstance(config.get('tools'), list):
        sections['tools'] = {'tools': config['tools']}
    else:
        sections['tools'] = {}

    # UI config section (includes visual_agents and other UI settings)
    ui_keys = ['visual_agents', 'ui_capable_agents']
    sections['ui_config'] = {k: v for k, v in config.items() if k in ui_keys}

    return sections


# -----------------------------
# Structured outputs utilities
# -----------------------------

def _normalize_model_library(models: Any) -> Dict[str, Any]:
    """
    Normalize a model library into dict form:
      { "<ModelName>": { "type": "model", "fields": { ... } }, ... }

    Accepts either:
      - dict library (already normalized) OR
      - list of StructuredModelDefinition entries:
          [{"model_name": "...", "fields": [{"name": "...", "type": "...", "description": "..."}, ...]}, ...]
    """
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
            lib[name] = {
                "type": "model",
                "fields": fields_dict
            }
    return lib


def _normalize_registry_map(registry: Any) -> Dict[str, Any]:
    """
    Normalize registry to dict form:
      { "<AgentName>": "<ModelName or None>", ... }

    Accepts either:
      - dict (already normalized) OR
      - list of entries: [{"agent": "...", "agent_definition": "<ModelName or None>"}]
    """
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
    """
    Merge static structured outputs (model library + default registry)
    with dynamic outputs (list-style models + list-style registry),
    and ensure every agent is listed in registry (defaulting to null).

    Priority:
      - Models: union; dynamic models added to library (do not overwrite unless same name – dynamic wins).
      - Registry: start with static map, overlay dynamic entries, then ensure all agent_names exist (null by default).
    """
    static_models = _normalize_model_library(static_so.get('models', {}))
    static_registry = _normalize_registry_map(static_so.get('registry', {}))

    dynamic_models = _normalize_model_library(dynamic_so.get('models', []))
    dynamic_registry = _normalize_registry_map(dynamic_so.get('registry', []))

    # Merge models: dynamic overrides static on name conflicts
    merged_models = dict(static_models)
    for mname, mdef in dynamic_models.items():
        merged_models[mname] = mdef

    # Merge registry: overlay dynamic onto static
    merged_registry = dict(static_registry)
    for agent, model in dynamic_registry.items():
        merged_registry[agent] = model

    # Ensure every defined agent is present
    for agent in agent_names:
        if agent not in merged_registry:
            merged_registry[agent] = None

    # Log helpful stats
    wf_logger.info(
        f"🧩 [STRUCTURED_OUTPUTS] models: static={len(static_models)} + dynamic={len(dynamic_models)} => merged={len(merged_models)}"
    )
    wf_logger.info(
        f"🧩 [STRUCTURED_OUTPUTS] registry: static={len(static_registry)} + dynamic={len(dynamic_registry)} + fill_missing={len([a for a in agent_names if a not in static_registry and a not in dynamic_registry])} => merged={len(merged_registry)}"
    )

    return {
        "models": merged_models,
        "registry": merged_registry
    }


def _save_modular_workflow(workflow_name: str, config: Dict[str, Any]) -> bool:
    """Save a workflow config as modular JSON files"""
    try:
        wf_logger = get_workflow_logger(workflow_name=workflow_name)
        # Determine workflows directory (relative to this file)
        workflows_base_dir = Path(__file__).parent.parent.parent
        workflow_dir = workflows_base_dir / workflow_name
        workflow_dir.mkdir(parents=True, exist_ok=True)

        # Split config into sections
        sections = _split_config_into_sections(config)

        # Save each section to its JSON file
        saved_files = []
        for section_name, section_data in sections.items():
            if section_name == 'structured_outputs':
                # Always save structured_outputs if the key exists (even if empty dict),
                # but try to keep it in a meaningful shape (has 'models' and 'registry').
                if isinstance(section_data, dict) and ('models' in section_data or 'registry' in section_data):
                    filename = WORKFLOW_FILE_MAPPINGS.get(section_name)
                    if filename:
                        file_path = workflow_dir / filename
                        _save_json_file(file_path, section_data)
                        saved_files.append(filename)
                        wf_logger.info(f"📄 [SAVE_WORKFLOW] Saved {section_name} to {filename}")
                continue

            if section_data:  # Only save non-empty sections
                filename = WORKFLOW_FILE_MAPPINGS.get(section_name)
                if filename:
                    file_path = workflow_dir / filename
                    _save_json_file(file_path, section_data)
                    saved_files.append(filename)
                    wf_logger.info(f"📄 [SAVE_WORKFLOW] Saved {section_name} to {filename}")

        # Save any extra files content if provided in config['extra_files'] (with dedup + optional global hooks copy)
        try:
            extra_files = config.get('extra_files')
            if isinstance(extra_files, list):
                # Deduplicate by normalized filename (first occurrence kept)
                deduped: Dict[str, Dict[str, Any]] = {}
                for item in extra_files:
                    if not isinstance(item, dict):
                        continue
                    name = item.get('filename')
                    if not name:
                        continue
                    safe_name = str(name).strip().lstrip('/').lstrip('\\')
                    if safe_name in deduped:
                        # If content differs, log a warning
                        prev_content = deduped[safe_name].get('filecontent')
                        new_content = item.get('filecontent')
                        if prev_content != new_content:
                            wf_logger.warning(f"⚠️ [SAVE_WORKFLOW] Duplicate file '{safe_name}' with differing content encountered. Keeping first instance.")
                        continue
                    deduped[safe_name] = item

                extra_files = list(deduped.values())

                inferred_py_deps = set()
                inferred_js_deps = set()
                global_hooks_dir = os.environ.get('GLOBAL_HOOKS_DIR')
                global_hooks_dir_path: Optional[Path] = None
                if global_hooks_dir:
                    try:
                        global_hooks_dir_path = Path(global_hooks_dir).expanduser().resolve()
                        global_hooks_dir_path.mkdir(parents=True, exist_ok=True)
                    except Exception as ghe:
                        wf_logger.warning(f"⚠️ [SAVE_WORKFLOW] Could not create GLOBAL_HOOKS_DIR '{global_hooks_dir}': {ghe}")
                        global_hooks_dir_path = None

                for item in extra_files:
                    name = item.get('filename')
                    content = item.get('filecontent', '')
                    safe_name = str(name).strip().lstrip('/').lstrip('\\')

                    # Write into workflow-specific area
                    extra_path = workflow_dir / safe_name
                    extra_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(extra_path, 'w', encoding='utf-8') as ef:
                        ef.write(content if isinstance(content, str) else str(content))
                    saved_files.append(safe_name)
                    wf_logger.info(f"🧩 [SAVE_WORKFLOW] Saved extra file: {safe_name}")

                    # Optional global hooks copy (only for tools/<hook>.py style)
                    if global_hooks_dir_path and safe_name.startswith('tools/') and safe_name.endswith('.py'):
                        try:
                            global_copy_path = global_hooks_dir_path / Path(safe_name).name
                            if not global_copy_path.exists():
                                global_copy_path.write_text(content if isinstance(content, str) else str(content), encoding='utf-8')
                                wf_logger.info(f"🌐 [SAVE_WORKFLOW] Wrote global hook file: {global_copy_path}")
                        except Exception as gc_err:
                            wf_logger.warning(f"⚠️ [SAVE_WORKFLOW] Failed writing global hook copy for {safe_name}: {gc_err}")

                    # Light dependency inference for code files
                    try:
                        lower = safe_name.lower()
                        if lower.endswith('.py') and isinstance(content, str):
                            import re
                            for m in re.finditer(r'^(?:from|import)\s+([\w\.]+)', content, re.MULTILINE):
                                mod = m.group(1).split('.')[0]
                                if mod and mod not in {'os', 'sys', 're', 'json', 'typing', 'pathlib', 'asyncio', 'logging', 'time'}:
                                    inferred_py_deps.add(mod)
                        if lower.endswith('.js') and isinstance(content, str):
                            import re
                            for m in re.finditer(r'^\s*import\s+(?:.+?\s+from\s+)?["\"]([^"\"]+)["\"]', content, re.MULTILINE):
                                dep = m.group(1)
                                if dep and not dep.startswith('.') and '/' not in dep:
                                    inferred_js_deps.add(dep)
                            for m in re.finditer(r'require\(\s*["\"]([^"\"]+)["\"]\s*\)', content):
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

        wf_logger.info(f"✅ [SAVE_WORKFLOW] Successfully saved {len(saved_files)} JSON files for workflow: {workflow_name}")
        return True

    except Exception as e:
        get_workflow_logger(workflow_name=workflow_name).error(f"❌ [SAVE_WORKFLOW] Failed to save workflow {workflow_name}: {e}")
        return False


async def convert_workflow_to_modular(data: Dict[str, Any], context_variables: Optional[Any] = None) -> Dict[str, Any]:
    """
    Save a workflow configuration as modular JSON files

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
                "message": f"Successfully saved {workflow_name} as modular JSON files",
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
                'ui_config': {...},                  # UI config (visual_agents, ui_capable_agents)
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
        if tools_manager_output and 'tools_config' in tools_manager_output:
            tools_config_str = tools_manager_output['tools_config']
            parsed = None
            if isinstance(tools_config_str, str):
                try:
                    parsed = json.loads(tools_config_str)
                except json.JSONDecodeError as e:
                    wf_logger.error(f"❌ [CREATE_WORKFLOW_FILES] Invalid tools_config JSON: {e}")
            elif isinstance(tools_config_str, dict):
                parsed = tools_config_str
            if isinstance(parsed, dict) and isinstance(parsed.get('tools'), list):
                config['tools'] = parsed['tools']
                wf_logger.info(f"📋 [CREATE_WORKFLOW_FILES] Added tools configuration (tools_list={len(parsed['tools'])})")
            else:
                wf_logger.warning("⚠️ [CREATE_WORKFLOW_FILES] tools_config missing 'tools' list; no tools saved")
        # Optional direct tools_config (only supports new format)
        elif 'tools_config' in data:
            direct_tc = data.get('tools_config')
            if isinstance(direct_tc, dict) and isinstance(direct_tc.get('tools'), list):
                config['tools'] = direct_tc['tools']
                wf_logger.info(f"📋 [CREATE_WORKFLOW_FILES] Added direct tools configuration (tools_list={len(direct_tc['tools'])})")

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
            cfg.setdefault('ui_capable_agents', [])
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
