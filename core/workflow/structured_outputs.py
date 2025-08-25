# ==============================================================================
# FILE: core/workflow/structured_outputs.py
# DESCRIPTION: Workflow-agnostic structured output models - loads from modular YAML configs
# ==============================================================================

from pydantic import BaseModel, Field, create_model
from typing import List, Dict, Any, Optional, Literal, Union
from pathlib import Path
from core.core_config import make_llm_config, make_structured_config
from .file_manager import workflow_file_manager

# Global cache for models and registry per workflow
_workflow_caches = {}

def _load_structured_outputs_config(workflow_name: str):
    """Load structured outputs configuration from workflow YAML files"""
    global _workflow_caches
    
    if workflow_name in _workflow_caches:
        return _workflow_caches[workflow_name]['models'], _workflow_caches[workflow_name]['registry']
    
    # Load workflow configuration
    workflow_config = workflow_file_manager.load_workflow(workflow_name)
    
    if not workflow_config:
        raise ValueError(f"No configuration found for workflow: {workflow_name}")
    
    structured_config = workflow_config.get('structured_outputs', {})
    models_config = structured_config.get('models', {})
    registry_config = structured_config.get('registry', {})
    
    if not models_config:
        raise ValueError(f"No structured outputs models found for workflow: {workflow_name}")
    
    if not registry_config:
        raise ValueError(f"No structured outputs registry found for workflow: {workflow_name}")
    
    # Build Pydantic models dynamically from YAML configuration
    models_cache = _build_pydantic_models(models_config)
    registry_cache = {agent: models_cache[model_name] for agent, model_name in registry_config.items()}
    
    # Cache the results
    _workflow_caches[workflow_name] = {
        'models': models_cache,
        'registry': registry_cache
    }
    
    return models_cache, registry_cache

def _build_pydantic_models(models_config: Dict[str, Any]) -> Dict[str, type]:
    """Build Pydantic models dynamically from YAML configuration"""
    models = {}
    
    # Single pass: create all models with forward references
    for model_name, model_def in models_config.items():
        if model_def.get('type') == 'model':
            fields = {}
            for field_name, field_def in model_def.get('fields', {}).items():
                try:
                    field_type, field_kwargs = _convert_field_definition(field_def, models)
                    fields[field_name] = (field_type, field_kwargs)
                except ValueError as e:
                    # Handle forward references by using string type hints
                    if "Unknown model reference" in str(e):
                        # For now, treat as Any - will be resolved in second pass
                        from typing import Any
                        field_kwargs = {}
                        if 'description' in field_def:
                            field_kwargs['description'] = field_def['description']
                        if 'default' in field_def:
                            field_kwargs['default'] = field_def['default']
                        fields[field_name] = (Any, Field(**field_kwargs))
                    else:
                        raise
            
            # Create the model
            models[model_name] = create_model(model_name, **fields)
    
    # Second pass: recreate models with proper type resolution
    for model_name, model_def in models_config.items():
        if model_def.get('type') == 'model':
            fields = {}
            for field_name, field_def in model_def.get('fields', {}).items():
                field_type, field_kwargs = _convert_field_definition(field_def, models)
                fields[field_name] = (field_type, field_kwargs)
            
            # Recreate the model with resolved references
            models[model_name] = create_model(model_name, **fields)
    
    return models

def _convert_field_definition(field_def: Dict[str, Any], models: Optional[Dict[str, type]] = None) -> tuple:
    """Convert YAML field definition to Pydantic field type and kwargs"""
    if models is None:
        models = {}
    
    field_type = field_def.get('type')
    field_kwargs = {}
    
    # Add description if present
    if 'description' in field_def:
        field_kwargs['description'] = field_def['description']
    
    # Add default if present
    if 'default' in field_def:
        if field_def['default'] is None:
            field_kwargs['default'] = None
        else:
            field_kwargs['default'] = field_def['default']
    
    # Convert type to Python type
    if field_type == 'str':
        return (str, Field(**field_kwargs))
    elif field_type == 'int':
        return (int, Field(**field_kwargs))
    elif field_type == 'bool':
        return (bool, Field(**field_kwargs))
    elif field_type == 'optional_str':
        return (Optional[str], Field(**field_kwargs))
    elif field_type == 'literal':
        values = field_def.get('values', [])
        return (Literal[tuple(values)], Field(**field_kwargs))
    elif field_type == 'list':
        items_type = field_def.get('items')
        if items_type == 'str':
            return (List[str], Field(**field_kwargs))
        elif items_type == 'int':
            return (List[int], Field(**field_kwargs))
        elif items_type == 'bool':
            return (List[bool], Field(**field_kwargs))
        elif isinstance(items_type, dict) and items_type.get('type') == 'model':
            # Inline model definition - create an anonymous model
            inline_fields = {}
            for inline_field_name, inline_field_def in items_type.get('fields', {}).items():
                inline_field_type, inline_field_kwargs = _convert_field_definition(inline_field_def, models)
                inline_fields[inline_field_name] = (inline_field_type, inline_field_kwargs)
            
            # Create anonymous model with a unique name
            model_name = f"AnonymousModel_{hash(str(items_type)) % 10000}"
            inline_model = create_model(model_name, **inline_fields)
            return (List[inline_model], Field(**field_kwargs))
        elif isinstance(items_type, str) and items_type in models:
            return (List[models[items_type]], Field(**field_kwargs))
        else:
            raise ValueError(f"Unknown model reference in list field: {items_type}")
    else:
        # Check if it's a reference to another model
        if field_type in models:
            return (models[field_type], Field(**field_kwargs))
        else:
            raise ValueError(f"Unknown field type or model reference: {field_type}")

def get_structured_outputs_for_workflow(workflow_name: str) -> Dict[str, type]:
    """Get structured outputs registry for a specific workflow"""
    _, registry = _load_structured_outputs_config(workflow_name)
    return registry

def _parse_list_type(type_str: str) -> Optional[str]:
    """Parse list type strings like 'list[ModelName]' and return the inner type name."""
    type_str = type_str.strip()
    if type_str.startswith('list[') and type_str.endswith(']'):
        return type_str[len('list['):-1].strip()
    return None

def _build_dynamic_models_from_spec(
    spec_models: List[Dict[str, Any]],
    existing_models: Dict[str, type]
) -> Dict[str, type]:
    """Build Pydantic models dynamically from a StructuredAgentOutputs.models list.

    The expected shape of each entry in spec_models:
      { model_name: str, fields: [ { name, type, description?, items? } ] }

    Supported field types:
      - 'str', 'int', 'bool', 'optional_str'
      - references to existing/dynamic models by name
      - lists: either {'type': 'list', 'items': 'ModelName'} or 'list[ModelName]'
    """
    dynamic_models: Dict[str, type] = {}

    def resolve_field(field: Dict[str, Any]) -> tuple:
        f_type_str = field.get('type', '').strip()
        f_desc = field.get('description')
        field_kwargs = {}
        if f_desc:
            field_kwargs['description'] = f_desc

        # Primitives
        if f_type_str in ('str', 'string'):
            return (str, Field(**field_kwargs))
        if f_type_str == 'int':
            return (int, Field(**field_kwargs))
        if f_type_str == 'bool':
            return (bool, Field(**field_kwargs))
        if f_type_str in ('optional_str', 'Optional[str]'):
            return (Optional[str], Field(**field_kwargs))

        # list[...] shorthand
        inner = _parse_list_type(f_type_str)
        if inner:
            # inner can be an existing model name or will be resolved in second pass
            inner_model = existing_models.get(inner) or dynamic_models.get(inner)
            if inner_model is not None:
                return (List[inner_model], Field(**field_kwargs))
            # unresolved for now; caller will re-run after more models are created
            raise LookupError(inner)

        # explicit {'type': 'list', 'items': 'ModelName'} form
        if f_type_str == 'list':
            items = field.get('items')
            if not items:
                raise ValueError("List field requires 'items' to specify element type")
            inner_model = existing_models.get(items) or dynamic_models.get(items)
            if inner_model is not None:
                return (List[inner_model], Field(**field_kwargs))
            raise LookupError(items)

        # Model reference by name
        ref = existing_models.get(f_type_str) or dynamic_models.get(f_type_str)
        if ref is not None:
            return (ref, Field(**field_kwargs))

        # Unknown at this point; mark unresolved by raising LookupError with the ref name
        raise LookupError(f_type_str)

    # First pass: create models with resolvable fields, skip unresolved
    pending: List[Dict[str, Any]] = []
    for m in spec_models:
        if not isinstance(m, dict):
            continue
        name_raw = m.get('model_name')
        if not isinstance(name_raw, str) or not name_raw:
            # Skip invalid entries
            continue
        name: str = name_raw
        fields_spec_raw = m.get('fields', [])
        fields_spec: List[Dict[str, Any]] = fields_spec_raw if isinstance(fields_spec_raw, list) else []
        fields: Dict[str, Any] = {}
        unresolved = False
        for f in fields_spec:
            if not isinstance(f, dict):
                continue
            fname_raw = f.get('name')
            if not isinstance(fname_raw, str) or not fname_raw:
                raise ValueError("Dynamic model field is missing a valid 'name'")
            fname: str = fname_raw
            try:
                ftype = resolve_field(f)
                fields[fname] = ftype
            except LookupError:
                unresolved = True
                break
        if unresolved:
            pending.append({"model_name": name, "fields": fields_spec})
        else:
            dynamic_models[name] = create_model(name, **fields)

    # Second pass: attempt to resolve remaining models now that some dynamics exist
    if pending:
        still_pending: List[Dict[str, Any]] = []
        for m in pending:
            name_raw = m.get('model_name')
            if not isinstance(name_raw, str) or not name_raw:
                continue
            name: str = name_raw
            fields_spec_raw = m.get('fields', [])
            fields_spec: List[Dict[str, Any]] = fields_spec_raw if isinstance(fields_spec_raw, list) else []
            fields: Dict[str, Any] = {}
            unresolved = False
            for f in fields_spec:
                if not isinstance(f, dict):
                    continue
                fname_raw = f.get('name')
                if not isinstance(fname_raw, str) or not fname_raw:
                    raise ValueError("Dynamic model field is missing a valid 'name'")
                fname: str = fname_raw
                try:
                    ftype = resolve_field(f)
                    fields[fname] = ftype
                except LookupError as le:
                    unresolved = True
                    break
            if unresolved:
                still_pending.append(m)
            else:
                dynamic_models[name] = create_model(name, **fields)

        if still_pending:
            unresolved_names = [m.get('model_name') for m in still_pending if isinstance(m.get('model_name'), str)]
            raise ValueError(f"Unresolved model references in dynamic models: {unresolved_names}")

    return dynamic_models

def apply_dynamic_structured_outputs(
    workflow_name: str,
    structured_agent_outputs: Union[Dict[str, Any], BaseModel]
) -> Dict[str, type]:
    """Merge dynamically proposed models and registry entries for a workflow.

    This enables the StructuredOutputsAgent to define new Pydantic models and
    agent→model mappings at runtime (e.g., when AgentsAgent proposes new agents).

    The expected payload shape matches the StructuredAgentOutputs model:
      {
        "models": [ {"model_name": str, "fields": [ {"name", "type", "description?", "items?"} ]} ],
        "registry": [ {"agent": str, "agent_defnition"|"agent_definition": str } ]
      }
    Returns the updated registry mapping after merge.
    """
    # Ensure the workflow cache is initialized
    models_cache, registry_cache = _load_structured_outputs_config(workflow_name)

    # Normalize payload to dict
    if isinstance(structured_agent_outputs, BaseModel):
        payload = structured_agent_outputs.model_dump()
    else:
        payload = dict(structured_agent_outputs or {})

    spec_models = payload.get('models', []) or []
    spec_registry = payload.get('registry', []) or []

    if not spec_models and not spec_registry:
        return registry_cache

    # Build dynamic models referencing existing + newly created ones
    dynamic_models = _build_dynamic_models_from_spec(spec_models, existing_models=models_cache)

    # Merge models into cache (override on conflict)
    for name, model_cls in dynamic_models.items():
        models_cache[name] = model_cls

    # Merge registry entries
    for entry in spec_registry:
        if not isinstance(entry, dict):
            continue
        agent = entry.get('agent')
        def_name = entry.get('agent_definition') or entry.get('agent_defnition')
        if not agent or not def_name:
            continue
        model_cls = models_cache.get(def_name)
        if not model_cls:
            raise ValueError(f"Dynamic registry references unknown model '{def_name}' for agent '{agent}'")
        registry_cache[agent] = model_cls

    # Update cache
    _workflow_caches[workflow_name] = {
        'models': models_cache,
        'registry': registry_cache,
    }

    return registry_cache

async def get_llm_for_workflow(
    workflow_name: str,
    flow: str = "base",
    agent_name: Optional[str] = None,
) -> tuple:
    """Create an LLM config for an agent with optional structured response model.

    Parameters:
    - workflow_name: The workflow to look up YAML configuration for.
    - flow: The llm_config_type for the agent (e.g. 'base'). Used only for streaming toggle logic.
    - agent_name: The concrete agent name to look up in the structured outputs registry.

    Behavior:
    - Streaming toggle is based on llm_config_type (flow == 'base').
    - Structured output model selection is based on agent_name if provided; otherwise falls back to `flow`.
    """

    # Toggle streaming for default/base llm config type
    should_stream = (flow == "base")

    # Try to load a structured response model for this specific agent
    try:
        structured_registry = get_structured_outputs_for_workflow(workflow_name)

    # Prefer explicit agent_name; otherwise use `flow`
        lookup_key = agent_name or flow
        if lookup_key in structured_registry:
            extra_config = {"stream": True} if should_stream else None
            return await make_structured_config(
                structured_registry[lookup_key],
                extra_config=extra_config,
            )

    except (ValueError, FileNotFoundError):
        # No structured outputs configured for this workflow; continue to plain LLM config
        pass

    # Fallback to plain LLM config
    return await make_llm_config(stream=should_stream)
