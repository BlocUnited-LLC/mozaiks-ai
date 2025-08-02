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
from .file_manager import workflow_file_manager
from logs.logging_config import get_business_logger

# Get logger
business_logger = get_business_logger("context_variables")

def get_context(workflow_name: str, enterprise_id: Optional[str] = None) -> ContextVariables:
    """
    Create context variables for any workflow.
    
    Features:
    1. Database schema information for agents
    2. Specific data extraction based on YAML configuration
    
    Args:
        workflow_name: Name of the workflow (e.g., 'Generator')
        enterprise_id: Enterprise ID for database queries
        
    Returns:
        ContextVariables populated with schema info and specific data
    """
    try:
        # Handle event loop issues
        try:
            loop = asyncio.get_running_loop()
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
    
    # When we're already in an event loop, we need to handle async operations differently
    try:
        # Try to get the current loop
        loop = asyncio.get_running_loop()
        
        # We're in an event loop, so we need to create a task and wait for it
        # But we can't await in a sync function, so we'll use a different approach
        business_logger.warning("⚠️ Already in event loop - using simplified sync loading")
        
        # Load basic context without database operations
        context = ContextVariables()
        if enterprise_id:
            context.set("enterprise_id", enterprise_id)
        
        # Load configuration but skip database operations
        config = _load_workflow_config(workflow_name)
        if config:
            context.set("config_loaded", True)
            
            # Handle schema_overview configuration  
            schema_config = config.get('schema_overview', {})
            if isinstance(schema_config, dict) and 'database_name' in schema_config:
                context.set("database_name", schema_config['database_name'])
            
            variables = config.get('variables', [])
            if variables:
                context.set("configured_variables", [v.get('name') for v in variables])
        
        business_logger.info(f"✅ Sync context loaded (basic): {len(context.data)} variables")
        return context
        
    except RuntimeError:
        # No running event loop, we can use asyncio.run
        return asyncio.run(_load_context_async(workflow_name, enterprise_id))
    except Exception as e:
        business_logger.error(f"❌ Sync context loading failed: {e}")
        # Return basic fallback
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
    
    # Handle schema_overview configuration
    schema_config = config.get('schema_overview', {})
    if isinstance(schema_config, dict) and schema_config.get('enabled', False) and internal_enterprise_id:
        schema_database = schema_config.get('database_name', 'autogen_ai_agents')
        schema_info = await _get_database_schema_async(schema_database, internal_enterprise_id)
        # Only add the schema_overview content, not database_name as separate variable
        if 'schema_overview' in schema_info:
            context.set("schema_overview", schema_info['schema_overview'])
    
    # Load specific variables from database
    variables = config.get('variables', [])
    if variables and internal_enterprise_id:
        # Use default database name if not specified in schema config
        default_db = config.get('database_name', 'autogen_ai_agents')
        if isinstance(schema_config, dict) and 'database_name' in schema_config:
            default_db = schema_config['database_name']
        
        loaded_data = await _load_specific_data_async(variables, default_db, internal_enterprise_id)
        for key, value in loaded_data.items():
            context.set(key, value)
    
    # Log the final context summary - only user-facing variables
    variable_names = list(context.data.keys())
    user_variables = [name for name in variable_names if name not in ['enterprise_id', 'database_name']]
    business_logger.info(f"✅ Context loaded: {len(user_variables)} user context variables: {user_variables}")
    
    # Add enterprise_id for internal use but don't count it in summary
    if internal_enterprise_id:
        context.set("enterprise_id", internal_enterprise_id)
    
    return context

def _load_workflow_config(workflow_name: str) -> Dict[str, Any]:
    """Load YAML configuration for workflow."""
    try:
        workflow_config = workflow_file_manager.load_workflow(workflow_name)
        
        if workflow_config and 'context_variables' in workflow_config:
            context_section = workflow_config['context_variables']
            
            # Handle double nesting if it exists
            if isinstance(context_section, dict) and 'context_variables' in context_section:
                result = context_section['context_variables']
            else:
                result = context_section
            
            return result
        return {}
    except Exception as e:
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

async def _load_specific_data_async(variables: List[Dict[str, Any]], default_database_name: str, enterprise_id: str) -> Dict[str, Any]:
    """
    FEATURE 2: Load specific data based on YAML configuration
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
