# ==============================================================================
# FILE: Generator/StructuredOutputs.py
# DESCRIPTION: JSON-driven structured output models for AG2 Generator agents
# ==============================================================================

from pydantic import BaseModel, Field, create_model
from typing import List, Dict, Any, Optional, Literal, Union
from pathlib import Path
import json
from core.core_config import make_llm_config, make_structured_config

# Global cache for models and registry
_models_cache = {}
_registry_cache = {}
_config_loaded = False

def _load_structured_outputs_config():
    """Load structured outputs configuration from workflow.json"""
    global _models_cache, _registry_cache, _config_loaded
    
    if _config_loaded:
        return _models_cache, _registry_cache
    
    workflow_path = Path(__file__).parent / "workflow.json"
    with open(workflow_path, 'r', encoding='utf-8') as f:
        workflow_config = json.load(f)
    
    structured_config = workflow_config.get('structured_outputs', {})
    models_config = structured_config.get('models', {})
    registry_config = structured_config.get('registry', {})
    
    if not models_config:
        raise ValueError("No structured outputs models found in workflow.json")
    
    if not registry_config:
        raise ValueError("No structured outputs registry found in workflow.json")
    
    # Build Pydantic models dynamically from JSON configuration
    _models_cache = _build_pydantic_models(models_config)
    _registry_cache = {agent: _models_cache[model_name] for agent, model_name in registry_config.items()}
    
    _config_loaded = True
    return _models_cache, _registry_cache

def _build_pydantic_models(models_config: Dict[str, Any]) -> Dict[str, type]:
    """Build Pydantic models dynamically from JSON configuration"""
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
    """Convert JSON field definition to Pydantic field type and kwargs"""
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

# Load configuration at module import
models_cache, registry_cache = _load_structured_outputs_config()

# Registry mapping - now loaded from JSON
structured_outputs = registry_cache

async def get_llm(flow: str = "base", enable_streaming: bool = False, enable_token_tracking: bool = False):
    """Load LLM config with optional structured response model and streaming - now JSON-driven"""
    if flow in structured_outputs:
        # For structured outputs with streaming: add stream=True to extra_config
        extra_config = {"stream": True} if enable_streaming else None
        return await make_structured_config(structured_outputs[flow], extra_config=extra_config, enable_token_tracking=enable_token_tracking)
    # For base configurations with streaming
    return await make_llm_config(stream=enable_streaming, enable_token_tracking=enable_token_tracking)