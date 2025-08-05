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
    
    # First pass: create all models without dependencies
    for model_name, model_def in models_config.items():
        if model_def.get('type') == 'model':
            fields = {}
            for field_name, field_def in model_def.get('fields', {}).items():
                field_type, field_kwargs = _convert_field_definition(field_def)
                fields[field_name] = (field_type, field_kwargs)
            
            # Create the model
            models[model_name] = create_model(model_name, **fields)
    
    # Second pass: resolve references to other models
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
        if items_type in models:
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

async def get_llm_for_workflow(workflow_name: str, flow: str = "base", enable_token_tracking: bool = False):
    """Load LLM config with optional structured response model for a specific workflow.
    Streaming is automatically enabled for agents with llm_config_type: 'base'"""
    
    # Check if this flow/agent should have streaming enabled (only for llm_config_type: 'base')
    should_stream = (flow == "base")
    
    try:
        structured_outputs = get_structured_outputs_for_workflow(workflow_name)
        
        if flow in structured_outputs:
            # For structured outputs: add stream=True only for base config type
            extra_config = {"stream": True} if should_stream else None
            return await make_structured_config(structured_outputs[flow], extra_config=extra_config, enable_token_tracking=enable_token_tracking)
        
    except (ValueError, FileNotFoundError):
        # If workflow doesn't have structured outputs, fall back to base config
        pass
    
    # For base configurations: enable streaming only for base config type
    return await make_llm_config(stream=should_stream, enable_token_tracking=enable_token_tracking)
