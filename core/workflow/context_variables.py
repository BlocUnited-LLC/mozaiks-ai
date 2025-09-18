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
from typing import Dict, Any, Optional, List
from autogen.agentchat.group import ContextVariables

# Import existing infrastructure
from .workflow_manager import workflow_manager
from logs.logging_config import get_workflow_logger

# Get logger
business_logger = get_workflow_logger("context_variables")

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

def get_context(workflow_name: str, enterprise_id: Optional[str] = None) -> ContextVariables:
    """
    Create context variables for any workflow.
    
    Features:
    1. Database schema information for agents
    2. Specific data extraction based on json configuration
    
    Args:
        workflow_name: Name of the workflow (e.g., 'ChatWorkflow', 'AnalysisWorkflow')
        enterprise_id: Enterprise ID for database queries
        
    Returns:
        ContextVariables populated with schema info and specific data
        
    Note: This function is legacy and only used for backwards compatibility.
    The orchestrator now calls _load_context_async directly.
    """
    try:
        # Handle event loop issues - simplified approach
        try:
            # Running loop detected; return minimal context and log warning
            asyncio.get_running_loop()
            business_logger.warning(f"âš ï¸ get_context called from async context - consider using _load_context_async directly")
            return _create_minimal_context(workflow_name, enterprise_id)
        except RuntimeError:
            # No running loop; safe to run async
            return asyncio.run(_load_context_async(workflow_name, enterprise_id))
    except Exception as e:
        business_logger.error(f"âŒ Context loading failed: {e}")
        return _create_minimal_context(workflow_name, enterprise_id)

def _create_minimal_context(workflow_name: str, enterprise_id: Optional[str]) -> ContextVariables:
    """Create minimal fallback context with basic parameters only."""
    context = ContextVariables()
    if enterprise_id:
        context.set("enterprise_id", enterprise_id)
    if workflow_name:
        context.set("workflow_name", workflow_name)
    business_logger.info(f"âœ… Created minimal context: enterprise_id={enterprise_id}, workflow_name={workflow_name}")
    return context

async def _load_context_async(workflow_name: str, enterprise_id: Optional[str]) -> ContextVariables:
    """Async context loading - properly handles async MongoDB operations."""
    business_logger.info(f"ðŸ”§ Loading context for {workflow_name} (async)")
    
    context = ContextVariables()
    
    # Store enterprise_id internally (used for queries but not exposed as context variable)
    internal_enterprise_id = enterprise_id
    
    # Load workflow configuration  
    config = _load_workflow_config(workflow_name)
    
    # Optionally attach a compact schema overview based on env toggle (default off).
    # Toggle: CONTEXT_INCLUDE_SCHEMA=true|false (default false)
    # DB source precedence for schema: CONTEXT_SCHEMA_DB env -> JSON schema_overview.database_name -> single DB from variables
    schema_config = config.get('schema_overview', {})
    try:
        include_schema_env = os.getenv("CONTEXT_INCLUDE_SCHEMA", "false").lower() in ("1", "true", "yes", "on")
        if include_schema_env:
            # Decide database used for schema extraction
            db_name = os.getenv("CONTEXT_SCHEMA_DB")
            if not db_name and isinstance(schema_config, dict):
                db_name = schema_config.get('database_name')
            if not db_name:
                # Infer from unique variable database reference
                var_dbs = set()
                for v in config.get('variables', []) or []:
                    dbn = ((v or {}).get('database') or {}).get('database_name')
                    if dbn:
                        var_dbs.add(dbn)
                if len(var_dbs) == 1:
                    db_name = next(iter(var_dbs))
            if db_name:
                overview_info = await _get_database_schema_async(db_name)
                overview_text = overview_info.get("schema_overview")
                if overview_text:
                    if len(overview_text) > TRUNCATE_CHARS:
                        overview_text = f"{overview_text[:TRUNCATE_CHARS]}... [truncated {len(overview_text)-TRUNCATE_CHARS} chars]"
                    context.set("schema_overview", overview_text)
                    business_logger.info(f"ðŸ“˜ Attached schema_overview to context (db={db_name}, len={len(overview_text)})")
                # Always attach full collection first-doc map when schema flag true
                try:
                    first_docs_full = await _get_all_collections_first_docs(db_name)
                    context.set("collections_first_docs_full", first_docs_full)
                    business_logger.info(f"ðŸ“— Attached collections_first_docs_full (collections={len(first_docs_full)})")
                except Exception as fd_err:
                    business_logger.debug(f"collections_first_docs_full attachment failed: {fd_err}")
            else:
                business_logger.debug("Schema overview requested but no database_name could be determined; skipping")
    except Exception as _sch_err:
        business_logger.debug(f"Schema overview attachment skipped: {_sch_err}")
    
    # Load specific variables from database
    variables = config.get('variables', [])
    if variables and internal_enterprise_id:
        # Determine default database name strictly from config; do NOT fall back to a hardcoded default
        default_db = config.get('database_name')
        if isinstance(schema_config, dict) and 'database_name' in schema_config and schema_config.get('database_name'):
            default_db = schema_config.get('database_name')

        if not default_db:
            business_logger.warning("No default database_name configured for context variables; each variable must specify database.database_name explicitly.")


        try:
            loaded_data = await _load_specific_data_async(variables, default_db, internal_enterprise_id)
            for key, value in loaded_data.items():
                context.set(key, value)
                business_logger.info(f"ðŸ§© ContextVar {key} = {_format_for_log(value)}")
        except Exception as load_err:
            business_logger.error(f"âŒ Failed loading specific context variables: {load_err}")
    
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

def _load_workflow_config(workflow_name: str) -> Dict[str, Any]:
    """Load json configuration for workflow."""
    try:
        workflow_config = workflow_manager.get_config(workflow_name)
        if workflow_config and 'context_variables' in workflow_config:
            context_section = workflow_config['context_variables']
            # Handle possible nesting
            if isinstance(context_section, dict) and 'context_variables' in context_section:
                return context_section['context_variables']
            return context_section
        # If no context_variables section in main config, try loading a separate context_variables.json file
        try:
            from pathlib import Path
            import json
            # workflow_manager._workflows stores WorkflowInfo with path to workflow folder
            wf_info = getattr(workflow_manager, '_workflows', {}).get(workflow_name.lower())
            if wf_info and hasattr(wf_info, 'path'):
                ext_file = Path(wf_info.path) / 'context_variables.json'
                if ext_file.exists():
                    business_logger.info(f"ðŸ” Loading external context_variables.json for {workflow_name}")
                    raw = ext_file.read_text(encoding='utf-8')
                    data = json.loads(raw)
                    return data.get('context_variables', {}) or {}
        except Exception as ext_err:  # pragma: no cover
            business_logger.debug(f"âš ï¸ External context_variables.json load failed: {ext_err}")
        return {}
    except Exception as e:  # pragma: no cover
        business_logger.warning(f"âš ï¸ Could not load config for {workflow_name}: {e}")
        return {}

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

async def _load_specific_data_async(variables: List[Dict[str, Any]], default_database_name: Optional[str], enterprise_id: str) -> Dict[str, Any]:
    """
    FEATURE 2: Load specific data based on json configuration
    Allows users to extract specific endpoints/data without full schema.
    Now supports per-variable database_name for multi-database enterprises.
    """
    loaded_data = {}
    
    try:
        from core.core_config import get_mongo_client
        from bson import ObjectId
        
        client = get_mongo_client()
        
        for var_config in variables:
            var_name = var_config.get('name')
            if not var_name:
                continue
                
            try:
                # Get database configuration - support per-variable database names
                db_config = var_config.get('database', {})
                collection_name = db_config.get('collection')
                search_by = db_config.get('search_by', 'enterprise_id')
                field = db_config.get('field')
                
                # Use variable-specific database name if provided, otherwise use default
                variable_database_name = db_config.get('database_name', default_database_name)
                if not variable_database_name:
                    business_logger.warning(f"âš ï¸ Skipping '{var_name}' - no database_name provided and no default configured")
                    continue
                
                if not collection_name:
                    business_logger.warning(f"âš ï¸ No collection specified for {var_name}")
                    continue
                
                # Connect to the specific database for this variable
                db = client[variable_database_name]
                business_logger.info(f"ðŸ” Loading {var_name} from database: {variable_database_name}")
                
                # Build query
                if search_by == 'enterprise_id':
                    try:
                        query = {'enterprise_id': ObjectId(enterprise_id)}
                    except:
                        query = {'enterprise_id': enterprise_id}
                else:
                    query = {search_by: enterprise_id}
                
                # Execute query (await the async operation)
                collection = db[collection_name]
                document = await collection.find_one(query)
                
                if document:
                    if field and field in document:
                        loaded_data[var_name] = document[field]
                        business_logger.info(f"âœ… Loaded {var_name} from {variable_database_name}.{collection_name}.{field}")
                    else:
                        loaded_data[var_name] = document
                        business_logger.info(f"âœ… Loaded {var_name} document from {variable_database_name}.{collection_name}")
                else:
                    business_logger.info(f"ðŸ“ No data found for {var_name} in {variable_database_name}.{collection_name}")
                    
            except Exception as e:
                business_logger.error(f"âŒ Error loading {var_name}: {e}")
                continue
        
    except Exception as e:
        business_logger.error(f"âŒ Specific data loading failed: {e}")
    
    return loaded_data
