# ==============================================================================
# FILE: core/workflow/context_variables.py  
# DESCRIPTION: Simple context variables system for workflow agents
# REQUIREMENTS:
# 1. Provide database schema as context to agents
# 2. Allow extraction of specific data from existing schema
# ==============================================================================

import asyncio
from typing import Dict, Any, Optional, List
from autogen.agentchat.group import ContextVariables

# Import existing infrastructure
from .workflow_manager import workflow_manager
from logs.logging_config import get_workflow_logger

# Get logger
business_logger = get_workflow_logger("context_variables")


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
    """
    try:
        # Handle event loop issues
        try:
            # Running loop detected; call the sync-safe loader which will schedule async work
            asyncio.get_running_loop()
            return _load_context_sync(workflow_name, enterprise_id)
        except RuntimeError:
            return asyncio.run(_load_context_async(workflow_name, enterprise_id))
    except Exception as e:
        business_logger.error(f"❌ Context loading failed: {e}")
        # Return basic fallback
        context = ContextVariables()
        if enterprise_id:
            context.set("enterprise_id", enterprise_id)
        return context

def _load_context_sync(workflow_name: str, enterprise_id: Optional[str]) -> ContextVariables:
    """Synchronous context loading - handles existing event loop properly."""
    business_logger.info(f"🔧 Loading context for {workflow_name} (sync)")
    # If this function is reached, we're running inside an event loop (get_context checked).
    # Schedule the async loader in the background so it can populate richer context when ready.
    try:
        business_logger.debug("Detected running event loop; scheduling async context load in background")
        # Schedule without awaiting — background population will happen when task completes
        asyncio.create_task(_load_context_async(workflow_name, enterprise_id))
    except Exception:
        # If scheduling failed, fall back to returning minimal context synchronously
        business_logger.debug("Could not schedule background context loader; returning minimal context")

    # Load basic context synchronously (no DB operations) so callers get immediate context
    try:
        context = ContextVariables()
        if enterprise_id:
            context.set("enterprise_id", enterprise_id)

        # Load configuration but skip blocking DB operations
        config = _load_workflow_config(workflow_name)
        if config:
            context.set("config_loaded", True)

            schema_config = config.get('schema_overview', {})
            if isinstance(schema_config, dict) and 'database_name' in schema_config:
                context.set("database_name", schema_config['database_name'])

            variables = config.get('variables', [])
            if variables:
                context.set("configured_variables", [v.get('name') for v in variables])

        business_logger.info(f"✅ Sync context loaded (basic): {len(context.data)} variables")
        return context
    except Exception as e:
        business_logger.error(f"❌ Sync context loading failed: {e}")
        context = ContextVariables()
        if enterprise_id:
            context.set("enterprise_id", enterprise_id)
        return context

async def _load_context_async(workflow_name: str, enterprise_id: Optional[str]) -> ContextVariables:
    """Async context loading - properly handles async MongoDB operations."""
    business_logger.info(f"🔧 Loading context for {workflow_name} (async)")
    
    context = ContextVariables()
    
    # Store enterprise_id internally (used for queries but not exposed as context variable)
    internal_enterprise_id = enterprise_id
    
    # Load workflow configuration  
    config = _load_workflow_config(workflow_name)
    
    # NOTE: By product decision, do NOT expose 'schema_overview' as a user context variable.
    # If configured, we skip loading/setting it entirely to keep context minimal and focused.
    # (Previously this populated a large text blob that isn't needed by agents.)
    schema_config = config.get('schema_overview', {})
    
    # Load specific variables from database
    variables = config.get('variables', [])
    if variables and internal_enterprise_id:
        # Determine default database name strictly from config; do NOT fall back to a hardcoded default
        default_db = config.get('database_name')
        if isinstance(schema_config, dict) and 'database_name' in schema_config and schema_config.get('database_name'):
            default_db = schema_config.get('database_name')

        if not default_db:
            business_logger.warning("⚠️ No default database_name configured for context variables; each variable must specify database.database_name explicitly.")

        loaded_data = await _load_specific_data_async(variables, default_db, internal_enterprise_id)
        for key, value in loaded_data.items():
            context.set(key, value)
            business_logger.info(f"🧩 ContextVar {key} = {_format_for_log(value)}")
    
    # Log the final context summary - only user-facing variables
    variable_names = list(context.data.keys())
    user_variables = [name for name in variable_names if name not in ['enterprise_id', 'database_name']]
    business_logger.info(f"✅ Context loaded: {len(user_variables)} user context variables: {user_variables}")
    # Print each user-visible variable with a safe value preview
    for _var in user_variables:
        try:
            business_logger.debug(f"   • {_var} => {_format_for_log(context.data.get(_var))}")
        except Exception:
            pass
    
    # Add enterprise_id for internal use but don't count it in summary
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
        return {}
    except Exception as e:  # pragma: no cover
        business_logger.warning(f"⚠️ Could not load config for {workflow_name}: {e}")
        return {}

async def _get_database_schema_async(database_name: str, enterprise_id: str) -> Dict[str, Any]:
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
                schema_lines.append(f"🔍 {collection_name.upper()}{is_enterprise}:")
                schema_lines.append("  Fields:")
                
                # List each field with its type
                for field_name, field_type in fields.items():
                    schema_lines.append(f"    • {field_name}: {field_type}")
                
                schema_lines.append("")  # Add spacing between collections
        
        # Store only the clean schema overview - no redundant data
        schema_info["schema_overview"] = "\n".join(schema_lines)
        
        business_logger.info(f"📊 Schema loaded: {len(collection_names)} collections, {len(enterprise_collections)} enterprise-specific")
        
    except Exception as e:
        business_logger.error(f"❌ Database schema loading failed: {e}")
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
                    business_logger.warning(f"⚠️ Skipping '{var_name}' - no database_name provided and no default configured")
                    continue
                
                if not collection_name:
                    business_logger.warning(f"⚠️ No collection specified for {var_name}")
                    continue
                
                # Connect to the specific database for this variable
                db = client[variable_database_name]
                business_logger.info(f"🔍 Loading {var_name} from database: {variable_database_name}")
                
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
                        business_logger.info(f"✅ Loaded {var_name} from {variable_database_name}.{collection_name}.{field}")
                    else:
                        loaded_data[var_name] = document
                        business_logger.info(f"✅ Loaded {var_name} document from {variable_database_name}.{collection_name}")
                else:
                    business_logger.info(f"📝 No data found for {var_name} in {variable_database_name}.{collection_name}")
                    
            except Exception as e:
                business_logger.error(f"❌ Error loading {var_name}: {e}")
                continue
        
    except Exception as e:
        business_logger.error(f"❌ Specific data loading failed: {e}")
    
    return loaded_data
