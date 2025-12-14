# ==============================================================================
# FILE: workflows/AgentGenerator/tools/workflow_converter.py
# DESCRIPTION: Self-contained workflow file creator for Generator workflow
# ==============================================================================

from typing import Dict, Any, Optional, List
from pathlib import Path
import json
import re
import textwrap


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


def clean_agent_content(content: str, agent_name: str = None) -> Optional[str]:
    """
    Remove Markdown code fences and clean JSON content.
    Based on proven pattern from previous project's file_manager.py.
    
    Handles:
    - Markdown code fences (```json ... ```)
    - Language identifiers (json, JSON)
    - Trailing commas before closing brackets
    - Invalid escape sequences
    - Extra whitespace
    """
    if not content:
        return None
        
    try:
        content = content.strip()
        
        # Remove Markdown code fences (```json ... ```)
        if content.startswith("```") and content.endswith("```"):
            content = content[3:-3].strip()
        
        # Remove "json" or "JSON" prefix if present
        if content.lower().startswith("json"):
            content = content[4:].strip()
        
        # Remove trailing commas before closing brackets
        content = re.sub(r',\s*([\]}])', r'\1', content)
        
        # Detect and extract JSON correctly
        json_start = content.find("{") if "{" in content else content.find("[")
        if json_start != -1:
            content = content[json_start:]
        
        # Find the last closing bracket
        json_end = content.rfind("}") if "}" in content else content.rfind("]")
        if json_end != -1:
            content = content[:json_end + 1]
        
        # Validate final JSON format
        json.loads(content)  # Raises an exception if invalid
        return content
        
    except json.JSONDecodeError as e:
        wf_logger = get_workflow_logger()
        wf_logger.error(f"❌ [CLEAN_AGENT_CONTENT] JSON Parsing Error for {agent_name or 'unknown agent'}: {e}")
        wf_logger.error(f"❌ [CLEAN_AGENT_CONTENT] Content preview: {content[:500]}...")
        return None


def _save_json_file(file_path: Path, data: Dict[str, Any]) -> None:
    """Save data to a JSON file"""
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _strip_markdown_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 2:
            lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            stripped = "\n".join(lines).strip()
    return stripped


def _convert_object_ids(text: str) -> str:
    return re.sub(r'ObjectId\(["\']?([0-9a-fA-F]{24})["\']?\)', r'{"$oid": "\1"}', text)


def _ensure_newlines(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if text and not text.endswith("\n"):
        text += "\n"
    return text


def _fix_jsx_syntax(content: str) -> str:
    try:
        text = content
        if "import React" not in text:
            text = "import React from \"react\";\n" + text

        text = re.sub(r"<\s*n\s*>", "", text)
        text = re.sub(r"</\s*n\s*>", "", text)

        self_closing = r"(<(area|base|br|col|embed|hr|img|input|link|meta|param|source|track|wbr)([^>]*)>)"
        text = re.sub(self_closing, lambda m: m.group(1).rstrip(">") + " />", text)
        return text
    except Exception:
        return content


def _normalize_json_text(raw: str) -> Optional[str]:
    try:
        parsed = json.loads(raw)
        return json.dumps(parsed, indent=2, ensure_ascii=False)
    except Exception:
        return None


def _normalize_file_content(rel_path: str, content: Any, agent_name: Optional[str] = None) -> Any:
    if isinstance(content, (dict, list)):
        try:
            return json.dumps(content, indent=2, ensure_ascii=False)
        except Exception:
            return content

    if not isinstance(content, str):
        return content

    text = content.strip("\ufeff")
    text = _strip_markdown_fences(text)
    lowered = text.strip().lower()
    if lowered.startswith("json"):
        text = text.strip()[4:].lstrip()

    text = _convert_object_ids(text)
    text = textwrap.dedent(text)
    text = _ensure_newlines(text)

    suffix = Path(rel_path).suffix.lower()
    if suffix == ".json":
        normalized = _normalize_json_text(text.strip())
        if normalized is not None:
            return _ensure_newlines(normalized)

    if suffix in {".jsx", ".tsx"}:
        text = _fix_jsx_syntax(text)

    return _ensure_newlines(text)


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
    sections['ui_config'] = {k: v for k, v in config.items() if k in ['visual_agents']}

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
        
        # Backend workflow directory (workflows/{workflow}/)
        workflows_base_dir = Path(__file__).parent.parent.parent
        workflow_dir = workflows_base_dir / workflow_name
        workflow_dir.mkdir(parents=True, exist_ok=True)
        
        # Frontend workflow directory (ChatUI/src/workflows/{workflow}/)
        project_root = workflows_base_dir.parent  # Go up from workflows/ to project root
        chatui_workflow_dir = project_root / 'ChatUI' / 'src' / 'workflows' / workflow_name
        chatui_components_dir = chatui_workflow_dir / 'components'

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

        # Handle extra files (tools, UI components, lifecycle hooks, etc.)
        extra_files = config.get('extra_files')
        if isinstance(extra_files, list) and extra_files:
            tools_dir = workflow_dir / 'tools'
            tools_dir.mkdir(parents=True, exist_ok=True)
            
            extra_saved = 0
            js_files_saved = 0
            py_files_saved = 0
            
            for item in extra_files:
                if not isinstance(item, dict):
                    continue
                    
                # Support both 'path' and 'filename' fields
                rel_path = item.get('path') or item.get('filename')
                content = item.get('content') or item.get('filecontent')
                
                if not rel_path or content is None:
                    continue
                    
                # Normalize path separators and remove leading slashes
                rel_path = str(rel_path).replace('\\', '/').lstrip('/')
                
                # Route files based on path prefix
                normalized_content = _normalize_file_content(rel_path, content, item.get('agent'))

                if rel_path.startswith('ChatUI/'):
                    # Frontend file - save relative to project root
                    file_path = project_root / rel_path
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    if isinstance(normalized_content, bytes):
                        file_path.write_bytes(normalized_content)
                    else:
                        file_path.write_text(str(normalized_content), encoding='utf-8')
                    js_files_saved += 1
                    saved_files.append(rel_path)
                    wf_logger.info(f"📄 [SAVE] Frontend file saved → {rel_path}")
                else:
                    # Backend file - save relative to workflow directory
                    file_path = workflow_dir / rel_path
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    if isinstance(normalized_content, bytes):
                        file_path.write_bytes(normalized_content)
                    else:
                        file_path.write_text(str(normalized_content), encoding='utf-8')
                    py_files_saved += 1
                    saved_files.append(rel_path)
                    wf_logger.info(f"📄 [SAVE] Backend file saved → {rel_path}")
                
                extra_saved += 1
            
            if js_files_saved > 0:
                wf_logger.info(f"✅ [SAVE] Saved {js_files_saved} React component files to ChatUI/src/workflows/{workflow_name}/components/")
            if py_files_saved > 0:
                wf_logger.info(f"✅ [SAVE] Saved {py_files_saved} Python files to workflows/{workflow_name}/tools/")
            wf_logger.info(f"✅ [SAVE] Saved {extra_saved} total extra files")

        wf_logger.info(f"✅ [SAVE] Saved {len(saved_files)} total files for workflow={workflow_name}")
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
                'tools_manager_output': {...},       # ToolsManagerAgent (tools + lifecycle_tools manifest)
                'ui_file_generator_output': {...},   # UIFileGenerator (UI tool implementations)
                'agent_tools_file_generator_output': {...}, # AgentToolsFileGenerator (agent tools + lifecycle tools implementations)
                'ui_config': {...},                  # UI config (visual_agents)
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
        
        # Log incoming data for debugging
        wf_logger.info("=" * 80)
        wf_logger.info("📦 RAW DATA RECEIVED BY workflow_converter:")
        wf_logger.info("=" * 80)
        
        # Save detailed input to file for inspection
        try:
            from pathlib import Path
            import json as _json
            from datetime import datetime
            
            converter_logs_dir = Path("logs/workflow_converter")
            converter_logs_dir.mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            input_file = converter_logs_dir / f"converter_input_{workflow_name}_{timestamp}.json"
            
            with open(input_file, 'w', encoding='utf-8') as f:
                _json.dump(data, f, indent=2, ensure_ascii=False)
            
            wf_logger.info(f"📄 Saved converter input to: {input_file.resolve()}")
        except Exception as e:
            wf_logger.debug(f"Failed to save converter input: {e}")
        
        for key, value in data.items():
            if key == 'workflow_name':
                wf_logger.info(f"   workflow_name: {value}")
            elif isinstance(value, dict):
                wf_logger.info(f"   {key}: {list(value.keys())}")
            elif isinstance(value, list):
                wf_logger.info(f"   {key}: [{len(value)} items]")
            else:
                wf_logger.info(f"   {key}: {type(value).__name__}")
        wf_logger.info("=" * 80)

        # Build the complete config from agent outputs
        config: Dict[str, Any] = {}

        # Extract orchestrator settings from OrchestratorAgent output
        orchestrator_output = data.get('orchestrator_output', {})
        if orchestrator_output:
            config.update(orchestrator_output)
            wf_logger.info(f"📋 [CREATE_WORKFLOW_FILES] Added orchestrator config: {list(orchestrator_output.keys())}")
        else:
            wf_logger.warning("⚠️ [CREATE_WORKFLOW_FILES] No orchestrator_output provided")

        # Extract agents from AgentsAgent output (already contains auto_tool_mode)
        # AgentsAgent determines auto_tool_mode by analyzing the tools array
        # Transform agents list into dict keyed by agent name for agents.json format
        agents_output = data.get('agents_output', {})
        agent_names = _extract_agent_names(agents_output)
        if agents_output and 'agents' in agents_output:
            agents_list = agents_output['agents']
            
            # Transform list to dict: [{"name": "Agent1", ...}] -> {"Agent1": {...}}
            # Exclude fields that don't belong in agents.json runtime config
            excluded_fields = {'name', 'display_name', 'agent_type'}
            agents_dict = {}
            
            for agent in agents_list:
                if isinstance(agent, dict) and 'name' in agent:
                    agent_name = agent['name']
                    # Remove excluded fields (name is the key, display_name/agent_type are metadata)
                    agent_config = {k: v for k, v in agent.items() if k not in excluded_fields}
                    agents_dict[agent_name] = agent_config
                else:
                    wf_logger.warning(f"⚠️ [CREATE_WORKFLOW_FILES] Skipping malformed agent entry: {agent}")
            
            config['agents'] = agents_dict
            wf_logger.info(f"📋 [CREATE_WORKFLOW_FILES] Added {len(agents_dict)} agents (auto_tool_mode determined by AgentsAgent)")
            wf_logger.info(f"   Agent names: {list(agents_dict.keys())}")
        else:
            wf_logger.warning("⚠️ [CREATE_WORKFLOW_FILES] No agents in agents_output")

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

        # Extract tools configuration from ToolsManagerAgent
        tools_manager_output = data.get('tools_manager_output', {})

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
        # Note: agent_modes extracted separately above and merged into agents.json
        if isinstance(tools_manager_output, dict):
            # Directly structured output case
            if "tools" in tools_manager_output or "lifecycle_tools" in tools_manager_output:
                tools_config = {}
                if "tools" in tools_manager_output and isinstance(tools_manager_output["tools"], list):
                    tools_config["tools"] = tools_manager_output["tools"]
                    wf_logger.info(f"📋 [CREATE_WORKFLOW_FILES] Added tools configuration (tools_list={len(tools_manager_output['tools'])})")
                if "lifecycle_tools" in tools_manager_output and isinstance(tools_manager_output["lifecycle_tools"], list):
                    tools_config["lifecycle_tools"] = tools_manager_output["lifecycle_tools"]
                    wf_logger.info(f"📋 [CREATE_WORKFLOW_FILES] Added lifecycle_tools configuration (lifecycle_tools_list={len(tools_manager_output['lifecycle_tools'])})")
                # NOTE: agent_modes intentionally NOT added to tools.json - it belongs in agents.json
                if tools_config:
                    config["tools"] = tools_config
            # tools_config string case (legacy fallback)
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
                if isinstance(parsed, dict):
                    tools_config = {}
                    if isinstance(parsed.get("tools"), list):
                        tools_config["tools"] = parsed["tools"]
                        wf_logger.info(f"📋 [CREATE_WORKFLOW_FILES] Added tools configuration (tools_list={len(parsed['tools'])})")
                    if isinstance(parsed.get("lifecycle_tools"), list):
                        tools_config["lifecycle_tools"] = parsed["lifecycle_tools"]
                        wf_logger.info(f"📋 [CREATE_WORKFLOW_FILES] Added lifecycle_tools configuration (lifecycle_tools_list={len(parsed['lifecycle_tools'])})")
                    # NOTE: agent_modes intentionally NOT added to tools.json - it belongs in agents.json
                    if tools_config:
                        config["tools"] = tools_config
                    else:
                        wf_logger.warning("⚠️ [CREATE_WORKFLOW_FILES] tools_config missing 'tools'/'lifecycle_tools' lists; no tools saved")

        # Add UI configuration
        ui_config = data.get('ui_config', {})
        if ui_config:
            config.update(ui_config)
            wf_logger.info("📋 [CREATE_WORKFLOW_FILES] Added UI configuration")

        # Add extra files to config so they can be saved
        extra_files = data.get('extra_files')

        # Inject runtime-generated attachments (e.g., API key env snapshot) from context variables
        if context_variables and hasattr(context_variables, 'get'):
            try:
                env_attachment = context_variables.get('api_keys_env_attachment')
            except Exception:
                env_attachment = None
            if isinstance(env_attachment, dict):
                env_filename = (env_attachment.get('filename') or 'api_keys.env').strip()
                env_content = env_attachment.get('filecontent')
                if env_content is None:
                    env_content = env_attachment.get('content')
                if env_filename and env_content is not None:
                    if not isinstance(extra_files, list):
                        extra_files = []
                    already_present = any(
                        isinstance(item, dict) and item.get('filename') == env_filename
                        for item in extra_files
                    )
                    if not already_present:
                        extra_files.append({'filename': env_filename, 'filecontent': env_content})
                        wf_logger.info("🧩 [CREATE_WORKFLOW_FILES] Added API key env attachment to extra_files")

        # Extract files from UIFileGenerator output (UI tools - Python + React)
        ui_file_generator_output = data.get('ui_file_generator_output', {})
        if ui_file_generator_output:
            ui_tools = ui_file_generator_output.get('tools', [])
            if isinstance(ui_tools, list) and ui_tools:
                ui_tool_files = []
                for tool_obj in ui_tools:
                    if not isinstance(tool_obj, dict):
                        continue
                    tool_name = tool_obj.get('tool_name')
                    if not tool_name:
                        continue
                    
                    # Python backend file (tool_name is snake_case)
                    py_content = tool_obj.get('py_content')
                    if py_content:
                        ui_tool_files.append({
                            'path': f"tools/{tool_name}.py",
                            'content': py_content
                        })
                    
                    # React component file (extract PascalCase component name from js_content)
                    js_content = tool_obj.get('js_content')
                    if js_content:
                        # Extract component name from "const ComponentName = ({" pattern
                        component_name = None
                        for line in js_content.split('\n'):
                            if 'const ' in line and ' = ({' in line:
                                # Extract: "const ActionPlan = ({" -> "ActionPlan"
                                match = line.strip().split('const ')[1].split(' = ({')[0].strip()
                                component_name = match
                                break
                        
                        # Fallback: convert tool_name to PascalCase if pattern not found
                        if not component_name:
                            # Convert snake_case to PascalCase (e.g., "action_plan" -> "ActionPlan")
                            component_name = ''.join(word.capitalize() for word in tool_name.split('_'))
                        
                        ui_tool_files.append({
                            'path': f"ChatUI/src/workflows/{workflow_name}/components/{component_name}.jsx",
                            'content': js_content
                        })
                
                if ui_tool_files:
                    if extra_files:
                        extra_files.extend(ui_tool_files)
                    else:
                        extra_files = ui_tool_files
                    wf_logger.info(f"📋 [CREATE_WORKFLOW_FILES] Added {len(ui_tool_files)} UI tool files from UIFileGenerator (Python + React)")

        # Extract files from AgentToolsFileGenerator output
        agent_tools_output = data.get('agent_tools_file_generator_output', {})
        if agent_tools_output:
            # Process agent tools
            agent_tools = agent_tools_output.get('tools', [])
            if isinstance(agent_tools, list) and agent_tools:
                tool_files = []
                for tool_obj in agent_tools:
                    if isinstance(tool_obj, dict) and 'tool_name' in tool_obj and 'py_content' in tool_obj:
                        tool_files.append({
                            'path': f"tools/{tool_obj['tool_name']}.py",
                            'content': tool_obj['py_content']
                        })
                if tool_files:
                    if extra_files:
                        extra_files.extend(tool_files)
                    else:
                        extra_files = tool_files
                    wf_logger.info(f"📋 [CREATE_WORKFLOW_FILES] Added {len(tool_files)} agent tool .py files from AgentToolsFileGenerator")

            # Process lifecycle tools
            lifecycle_tools = agent_tools_output.get('lifecycle_tools', [])
            if isinstance(lifecycle_tools, list) and lifecycle_tools:
                lifecycle_files = []
                for tool_obj in lifecycle_tools:
                    if isinstance(tool_obj, dict) and 'tool_name' in tool_obj and 'py_content' in tool_obj:
                        lifecycle_files.append({
                            'path': f"tools/{tool_obj['tool_name']}.py",
                            'content': tool_obj['py_content']
                        })
                if lifecycle_files:
                    if extra_files:
                        extra_files.extend(lifecycle_files)
                    else:
                        extra_files = lifecycle_files
                    wf_logger.info(f"📋 [CREATE_WORKFLOW_FILES] Added {len(lifecycle_files)} lifecycle tool .py files from AgentToolsFileGenerator")

        if isinstance(extra_files, list) and extra_files:
            config['extra_files'] = extra_files
            wf_logger.info(f"📋 [CREATE_WORKFLOW_FILES] Total extra files to save: {len(extra_files)}")

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

                wf_logger.info("📝 [CREATE_WORKFLOW_FILES] Updated context variables with workflow record")

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
