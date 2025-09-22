# ==============================================================================
# FILE: core/workflow/context_variables.py  
# DESCRIPTION: Simple context variables system for workflow agents
# REQUIREMENTS:
# 1. Provide database schema as context to agents
# 2. Allow extraction of specific data from existing schema
# ==============================================================================

import asyncio
import os
import re
from typing import Dict, Any, Optional, List, Union, Sequence
from autogen.agentchat.group import ContextVariables

# Import existing infrastructure
from .context_schema import (
    ContextVariablesConfig,
    DeclarativeVariableSpec,
    DatabaseVariableSpec,
    EnvironmentVariableSpec,
    load_context_variables_config,
)
from .workflow_manager import workflow_manager
from logs.logging_config import get_workflow_logger

# Get logger
business_logger = get_workflow_logger("context_variables")

_TRUE_FLAG_VALUES = {"1", "true", "yes", "on"}


def _get_bool_env(name: str, default: bool = False) -> bool:
    """Parse boolean environment flags safely."""

    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in _TRUE_FLAG_VALUES

# ---------------------------------------------------------------------------
# ENV FLAGS (minimal â€“ only what we actively use during testing)
# ---------------------------------------------------------------------------
# CONTEXT_INCLUDE_SCHEMA  -> when true: include schema_overview + collections_first_docs_full
# CONTEXT_SCHEMA_DB       -> explicit database name to introspect (takes precedence)
# ---------------------------------------------------------------------------

TRUNCATE_CHARS = int(os.getenv("CONTEXT_SCHEMA_TRUNCATE_CHARS", "4000") or 4000)
 
# # Sensitive field name patterns (lowercased match)
# SENSITIVE_PATTERNS = re.compile(r"(password|secret|api[_-]?key|token|credential|private|auth|session)")

# # ---------------------------------------------------------------------------
# # Helper: scrub / summarize values for safe context injection
# # ---------------------------------------------------------------------------
# def _scrub_value(v: Any) -> Any:
#     try:
    # ------------------------------------------------------------------
    # VARIABLE TAXONOMY (NEW ONLY)
    # Enforce explicit separation: database_variables[], environment_variables[]
#         if v is None:
#             return None
#         if isinstance(v, (int, float, bool)):
#             return v
#         if isinstance(v, str):
#             if len(v) > 256:
#                 return v[:128] + "... [truncated]"
#             return v
#         if isinstance(v, list):
#             return f"list(len={len(v)})"
#         if isinstance(v, dict):
#             return f"dict(keys={list(v.keys())[:6]})"
#         return type(v).__name__
#     except Exception:
#         return "<unserializable>"


## Removed: previous AUTO_DISCOVERY minimal introspection helper (kept code lean for testing)

async def _get_all_collections_first_docs(database_name: str) -> Dict[str, Any]:
    """Return a mapping of every collection name -> first document (raw except _id removed).

    This is a direct, unfiltered snapshot (single document per collection) intended
    for generation-time inspection. Uses no caps; if the database has a very large
    number of collections this could expand context size, so it's only invoked
    when CONTEXT_INCLUDE_SCHEMA is explicitly enabled by the user.
    """
    from core.core_config import get_mongo_client  # local import
    result: Dict[str, Any] = {}
    try:
        client = get_mongo_client()
        db = client[database_name]
        try:
            names = await db.list_collection_names()
        except Exception as e:  # pragma: no cover
            business_logger.error(f"âŒ list_collection_names failed for {database_name}: {e}")
            return result
        for cname in names:
            try:
                doc = await db[cname].find_one()
                if not doc:
                    result[cname] = {"_note": "empty_collection"}
                else:
                    # remove raw ObjectId for portability but keep other fields untouched
                    cleaned = {k: v for k, v in doc.items() if k != '_id'}
                    result[cname] = cleaned
            except Exception as ce:
                result[cname] = {"_error": str(ce)}
    except Exception as outer:
        business_logger.error(f"âŒ Failed collecting first docs for {database_name}: {outer}")
    return result


def _format_for_log(value: Any) -> str:
    """Best-effort, safe formatter for logging context variable values.

    - Truncates long strings
    - Summarizes lists/dicts to avoid huge log lines
    - Falls back to repr for other types
    """
    try:
        if isinstance(value, str):
            if len(value) > 400:
                return f"{value[:200]}... [truncated {len(value)-200} chars]"
            return value
        if isinstance(value, list):
            return f"list(len={len(value)})"
        if isinstance(value, dict):
            keys_preview = list(value.keys())[:10]
            extra = "" if len(value) <= 10 else f", +{len(value)-10} more"
            return f"dict(keys={keys_preview}{extra})"
        return repr(value)
    except Exception:
        return "<unloggable>"

def _create_minimal_context(workflow_name: str, enterprise_id: Optional[str]) -> ContextVariables:
    """Create minimal fallback context with basic parameters only."""
    context = ContextVariables()
    if enterprise_id:
        context.set("enterprise_id", enterprise_id)
    if workflow_name:
        context.set("workflow_name", workflow_name)
    env_mode = (os.getenv('ENVIRONMENT') or '').strip().lower()
    if env_mode != 'production':
        context.set("context_aware", _get_bool_env("CONTEXT_AWARE", False))
        context.set("monetization_enabled", _get_bool_env("MONETIZATION_ENABLED", False))
    else:
        business_logger.info("Production mode: skipping seeding of environment feature flags in minimal context")
    business_logger.info(f"âœ… Created minimal context: enterprise_id={enterprise_id}, workflow_name={workflow_name}, env_mode={env_mode}")
    return context

async def _load_context_async(workflow_name: str, enterprise_id: Optional[str]) -> ContextVariables:
    """Async context loading - properly handles async MongoDB operations."""
    business_logger.info(f"🔧 Loading context for {workflow_name} (async)")
    context = _create_minimal_context(workflow_name, enterprise_id)
    internal_enterprise_id = enterprise_id
    config_model, raw_context_section = _load_workflow_config(workflow_name)
    config = config_model.model_dump_runtime()

    # Schema overview (optional)
    schema_config = raw_context_section.get('schema_overview', {}) if isinstance(raw_context_section, dict) else {}
    try:
        include_schema_env = os.getenv("CONTEXT_INCLUDE_SCHEMA", "false").lower() in ("1", "true", "yes", "on")
        if include_schema_env:
            db_name = os.getenv("CONTEXT_SCHEMA_DB")
            if not db_name and isinstance(schema_config, dict):
                db_name = schema_config.get('database_name')
            if db_name:
                overview_info = await _get_database_schema_async(db_name)
                overview_text = overview_info.get("schema_overview")
                if overview_text:
                    if len(overview_text) > TRUNCATE_CHARS:
                        overview_text = f"{overview_text[:TRUNCATE_CHARS]}... [truncated {len(overview_text)-TRUNCATE_CHARS} chars]"
                    context.set("schema_overview", overview_text)
                    business_logger.info(f"📄 Attached schema_overview (db={db_name}, len={len(overview_text)})")
                try:
                    first_docs_full = await _get_all_collections_first_docs(db_name)
                    context.set("collections_first_docs_full", first_docs_full)
                    business_logger.info(f"📘 Attached collections_first_docs_full (collections={len(first_docs_full)})")
                except Exception as fd_err:
                    business_logger.debug(f"collections_first_docs_full attachment failed: {fd_err}")
            else:
                business_logger.debug("Schema overview requested but no database_name; skipping")
    except Exception as _sch_err:
        business_logger.debug(f"Schema overview attachment skipped: {_sch_err}")

    # New taxonomy only; legacy flat 'variables' support removed intentionally.
    db_variables: List[DatabaseVariableSpec] = list(config_model.database_variables)
    # Optional schema/database context gating: if CONTEXT_INCLUDE_SCHEMA is falsy, suppress database_variables.
    include_schema_flag = (os.getenv('CONTEXT_INCLUDE_SCHEMA') or '').strip().lower() in _TRUE_FLAG_VALUES
    if not include_schema_flag and db_variables:
        business_logger.info("CONTEXT_INCLUDE_SCHEMA disabled -> suppressing all database_variables from context plan")
        db_variables = []
    env_variables: List[EnvironmentVariableSpec] = list(config_model.environment_variables)
    # Production safeguard: if ENVIRONMENT == production, suppress environment_variables entirely.
    env_mode = (os.getenv('ENVIRONMENT') or '').strip().lower()
    if env_mode == 'production' and env_variables:
        business_logger.info("ENVIRONMENT=production -> suppressing all environment_variables from context plan")
        env_variables = []
    declarative_variables: List[DeclarativeVariableSpec] = list(config_model.declarative_variables)

    # Load environment variables first (simple flags / small values)
    for env_var in env_variables:
        try:
            name = env_var.name
            env_key = env_var.source.env_var
            if not name or not env_key:
                continue
            raw_val = os.getenv(env_key)
            default_value = env_var.source.default
            declared_type = (env_var.type or '').strip().lower() if env_var.type else ''
            if raw_val is None:
                if default_value is not None:
                    context.set(name, default_value)
                    business_logger.info(
                        f"🧩 EnvContextVar {name} defaulted -> {default_value!r} (env={env_key} missing)"
                    )
                continue
            normalized = raw_val.strip()
            lowered = normalized.lower()
            if declared_type == 'boolean' or lowered in _TRUE_FLAG_VALUES.union({'0', 'false', 'off', 'no'}):
                coerced = lowered in _TRUE_FLAG_VALUES
                context.set(name, coerced)
            elif declared_type == 'integer':
                try:
                    coerced = int(normalized)
                    context.set(name, coerced)
                except Exception:
                    if default_value is not None:
                        context.set(name, default_value)
                        business_logger.info(
                            f"🧩 EnvContextVar {name} fallback default -> {default_value!r} (invalid int)"
                        )
                    continue
            else:
                context.set(name, raw_val)
            stored_value = context.data.get(name) if hasattr(context, 'data') else None  # type: ignore[attr-defined]
            business_logger.info(
                f"🧩 EnvContextVar {name} (env={env_key}) loaded -> {_format_for_log(stored_value)}"
            )
        except Exception as e:  # pragma: no cover
            business_logger.debug(f"Env variable load skipped: {e}")

    for decl_var in declarative_variables:
        try:
            context.set(decl_var.name, decl_var.source.value)
            business_logger.info(
                f"🧱 DeclarativeContextVar {decl_var.name} = {_format_for_log(decl_var.source.value)}"
            )
        except Exception as e:  # pragma: no cover
            business_logger.debug(f"Declarative variable load skipped: {e}")

    # Load database variables (requires enterprise)
    if db_variables and internal_enterprise_id:
        # Determine default database name strictly from config; do NOT fall back to a hardcoded default
        default_db = raw_context_section.get('database_name') if isinstance(raw_context_section, dict) else None
        if isinstance(schema_config, dict) and schema_config.get('database_name'):
            default_db = schema_config.get('database_name')

        if not default_db:
            business_logger.debug("No global database_name; each database variable must specify its own reference.")

        try:
            loaded_data = await _load_specific_data_async(db_variables, default_db, internal_enterprise_id)
            for key, value in loaded_data.items():
                context.set(key, value)
                business_logger.info(f"🧬 DbContextVar {key} = {_format_for_log(value)}")
        except Exception as load_err:
            business_logger.error(f"❌ Failed loading database context variables: {load_err}")
    
    # Log the final context summary - workflow-specific variables only
    # Note: Core WebSocket parameters (workflow_name, enterprise_id, chat_id, user_id) 
    # are auto-injected by the orchestrator, so we focus on workflow-specific data here
    variable_names = list(context.data.keys())
    workflow_variables = [name for name in variable_names if name not in ['enterprise_id']]
    business_logger.info(f"âœ… Context loaded: {len(workflow_variables)} workflow context variables: {workflow_variables}")
    # Print each workflow-specific variable with a safe value preview
    for _var in workflow_variables:
        try:
            business_logger.debug(f"   â€¢ {_var} => {_format_for_log(context.data.get(_var))}")
        except Exception:
            pass
    
    # Keep enterprise_id for database queries (orchestrator will handle user_id, chat_id, workflow_name)
    if internal_enterprise_id:
        context.set("enterprise_id", internal_enterprise_id)
    
    return context

def _load_workflow_config(workflow_name: str) -> tuple[ContextVariablesConfig, Dict[str, Any]]:
    """Load context variable configuration and validate with Pydantic."""

    raw_section: Dict[str, Any] = {}
    try:
        workflow_config = workflow_manager.get_config(workflow_name) or {}
        context_section = workflow_config.get('context_variables') or {}
        if isinstance(context_section, dict):
            raw_section = context_section
        if not raw_section:
            from pathlib import Path
            import json
            wf_info = getattr(workflow_manager, '_workflows', {}).get(workflow_name.lower())
            if wf_info and hasattr(wf_info, 'path'):
                ext_file = Path(wf_info.path) / 'context_variables.json'
                if ext_file.exists():
                    raw = ext_file.read_text(encoding='utf-8')
                    data = json.loads(raw)
                    ctx_section = data.get('context_variables') or data
                    if isinstance(ctx_section, dict):
                        raw_section = ctx_section
    except Exception as e:  # pragma: no cover
        business_logger.warning(f"⚠️ Could not load config for {workflow_name}: {e}")

    try:
        model = load_context_variables_config(raw_section)
    except ValueError as err:
        business_logger.warning(
            f"⚠️ Context variables config validation failed for {workflow_name}: {err}"
        )
        model = ContextVariablesConfig()
        raw_section = {}
    return model, raw_section

async def _get_database_schema_async(database_name: str) -> Dict[str, Any]:
    """
    FEATURE 1: Provide database schema as context
    Returns clean, field-focused schema info for LLMs.
    """
    schema_info = {}
    
    try:
        from core.core_config import get_mongo_client
        
        client = get_mongo_client()
        db = client[database_name]
        
        # Get collection names
        collection_names = await db.list_collection_names()
        schema_info["database_name"] = database_name
        
        # Create clean collection schemas - focus on fields only
        collection_schemas = {}
        enterprise_collections = []
        
        for collection_name in collection_names:
            try:
                collection = db[collection_name]
                sample_doc = await collection.find_one()
                
                if sample_doc:
                    # Clean field mapping
                    field_types = {}
                    for key, value in sample_doc.items():
                        if key == '_id':
                            continue  # Skip MongoDB internal ID
                        
                        field_type = type(value).__name__
                        # Simplify type names
                        if field_type == 'ObjectId':
                            field_type = 'ObjectId'
                        elif field_type == 'datetime':
                            field_type = 'DateTime'
                        elif field_type == 'NoneType':
                            field_type = 'null'
                        elif field_type == 'bool':
                            field_type = 'boolean'
                        
                        field_types[key] = field_type
                    
                    collection_schemas[collection_name] = field_types
                    
                    # Track enterprise-specific collections
                    if "enterprise_id" in sample_doc:
                        enterprise_collections.append(collection_name)
                else:
                    collection_schemas[collection_name] = {"note": "No sample data available"}
                    
            except Exception as e:
                business_logger.debug(f"Could not analyze {collection_name}: {e}")
                collection_schemas[collection_name] = {"error": f"Analysis failed: {str(e)}"}
        
        # Create a clean, structured schema summary for LLMs
        schema_lines = []
        schema_lines.append(f"DATABASE: {database_name}")
        schema_lines.append(f"TOTAL COLLECTIONS: {len(collection_names)}")
        schema_lines.append("")
        
        # Add detailed field information for each collection
        for collection_name, fields in collection_schemas.items():
            if isinstance(fields, dict) and "note" not in fields and "error" not in fields:
                is_enterprise = " [Enterprise-specific]" if collection_name in enterprise_collections else ""
                schema_lines.append(f"ðŸ” {collection_name.upper()}{is_enterprise}:")
                schema_lines.append("  Fields:")
                
                # List each field with its type
                for field_name, field_type in fields.items():
                    schema_lines.append(f"    â€¢ {field_name}: {field_type}")
                
                schema_lines.append("")  # Add spacing between collections
        
        # Store only the clean schema overview - no redundant data
        schema_info["schema_overview"] = "\n".join(schema_lines)
        
        business_logger.info(f"ðŸ“Š Schema loaded: {len(collection_names)} collections, {len(enterprise_collections)} enterprise-specific")
        
    except Exception as e:
        business_logger.error(f"âŒ Database schema loading failed: {e}")
        schema_info["error"] = f"Could not load schema: {e}"
    
    return schema_info

async def _load_specific_data_async(
    variables: Sequence[Union[DatabaseVariableSpec, Dict[str, Any]]],
    default_database_name: Optional[str],
    enterprise_id: str,
) -> Dict[str, Any]:
    """Load specific data based on declarative context configuration."""

    loaded_data: Dict[str, Any] = {}

    try:
        from core.core_config import get_mongo_client
        from bson import ObjectId

        client = get_mongo_client()

        for var_config in variables:
            if isinstance(var_config, DatabaseVariableSpec):
                var_name = var_config.name
            elif isinstance(var_config, dict):
                var_name = var_config.get('name')
            else:
                continue

            if not var_name:
                continue

            try:
                if isinstance(var_config, DatabaseVariableSpec):
                    db_config: Dict[str, Any] = {
                        'database_name': var_config.source.database_name or default_database_name,
                        'collection': var_config.source.collection,
                        'search_by': var_config.source.search_by or 'enterprise_id',
                        'field': var_config.source.field,
                    }
                else:
                    source_config = var_config.get('source', {}) if isinstance(var_config, dict) else {}
                    source_type = source_config.get('type') if isinstance(source_config, dict) else None

                    if source_type == 'environment':
                        env_var = source_config.get('env_var')
                        default_value = source_config.get('default')
                        if env_var:
                            env_value = os.getenv(env_var)
                            if env_value is not None:
                                var_type = var_config.get('type', 'string') if isinstance(var_config, dict) else 'string'
                                if var_type == 'boolean':
                                    loaded_data[var_name] = env_value.lower() in ('true', '1', 'yes', 'on')
                                elif var_type == 'integer':
                                    try:
                                        loaded_data[var_name] = int(env_value)
                                    except Exception:
                                        loaded_data[var_name] = default_value
                                else:
                                    loaded_data[var_name] = env_value
                            else:
                                loaded_data[var_name] = default_value
                            business_logger.info(
                                f"🌍 Loaded {var_name} from environment: {env_var}={loaded_data[var_name]}"
                            )
                        continue

                    if source_type == 'static':
                        static_value = source_config.get('value')
                        loaded_data[var_name] = static_value
                        business_logger.info(f"📊 Loaded {var_name} from static value: {static_value}")
                        continue

                    if source_type == 'database':
                        db_config = source_config
                    elif isinstance(var_config, dict) and 'database' in var_config:
                        db_config = var_config.get('database', {})
                    else:
                        business_logger.warning(
                            f"⚠️ No valid source configuration for variable '{var_name}'"
                        )
                        continue

                if not isinstance(db_config, dict):
                    business_logger.warning(f"⚠️ Invalid database config for '{var_name}'")
                    continue

                collection_name = db_config.get('collection')
                search_by = db_config.get('search_by', 'enterprise_id')
                field = db_config.get('field')

                variable_database_name = db_config.get('database_name', default_database_name)
                if not variable_database_name:
                    business_logger.warning(
                        f"⛔️ Skipping '{var_name}' - no database_name provided and no default configured"
                    )
                    continue

                if not collection_name:
                    business_logger.warning(f"⛔️ No collection specified for {var_name}")
                    continue

                db = client[variable_database_name]
                business_logger.info(f"🔍 Loading {var_name} from database: {variable_database_name}")

                if search_by == 'enterprise_id':
                    try:
                        query = {'enterprise_id': ObjectId(enterprise_id)}
                    except Exception:
                        query = {'enterprise_id': enterprise_id}
                else:
                    query = {search_by: enterprise_id}

                collection = db[collection_name]
                document = await collection.find_one(query)

                if document:
                    if field and field in document:
                        loaded_data[var_name] = document[field]
                        business_logger.info(
                            f"✅ Loaded {var_name} from {variable_database_name}.{collection_name}.{field}"
                        )
                    else:
                        loaded_data[var_name] = document
                        business_logger.info(
                            f"✅ Loaded {var_name} document from {variable_database_name}.{collection_name}"
                        )
                else:
                    business_logger.info(
                        f"📝 No data found for {var_name} in {variable_database_name}.{collection_name}"
                    )

            except Exception as e:
                business_logger.error(f"❌ Error loading {var_name}: {e}")
                continue

    except Exception as e:
        business_logger.error(f"❌ Specific data loading failed: {e}")

    return loaded_data

# Add public symbols export for context utilities
__all__ = ["_create_minimal_context", "_load_context_async"]
