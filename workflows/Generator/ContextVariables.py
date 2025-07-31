# ==============================================================================
# FILE: Generator/ContextVariables.py  
# DESCRIPTION: JSON-driven context variables for Generator workflow with Azure Key Vault integration
# ==============================================================================
import json
import logging
import asyncio
from pathlib import Path
from autogen.agentchat.group import ContextVariables
from typing import Dict, Any, Optional, List

# Import enhanced logging
from logs.logging_config import get_business_logger

# Get specialized logger
business_logger = get_business_logger("generator_context_variables")

def get_context(concept_data: Optional[Dict[str, Any]] = None) -> ContextVariables:
    """
    Create context variables for the Generator workflow - now fully JSON-driven.
    
    Reads context variable definitions from workflow.json and dynamically extracts
    data from MongoDB via Azure Key Vault or provided concept_data.
    
    Args:
        concept_data: Optional data dictionary to extract context from
        
    Returns:
        ContextVariables instance populated with extracted data
    """
    try:
        business_logger.info("🔧 [CONTEXT] Creating JSON-driven context variables...")
        
        # Load context variable configuration from workflow.json
        workflow_path = Path(__file__).parent / "workflow.json"
        with open(workflow_path, 'r', encoding='utf-8') as f:
            workflow_config = json.load(f)
        
        context_config = workflow_config.get('context_variables', {})
        variable_definitions = context_config.get('variables', [])
        
        business_logger.info(f"🔧 [CONTEXT] Found {len(variable_definitions)} context variable definitions")
        
        # Create context variables instance
        context_vars = ContextVariables()
        
        # Load concept data from database if variables have database config
        if concept_data is None:
            # Check if any variables have database configuration
            has_database_vars = any(var_def.get('database') for var_def in variable_definitions)
            if has_database_vars:
                # Run async function in sync context
                concept_data = asyncio.run(_load_concept_data(variable_definitions))
        
        # Ensure concept_data is not None for variable extraction
        if concept_data is None:
            concept_data = {}
        
        # Process each variable definition from JSON
        for var_def in variable_definitions:
            var_name = var_def.get('name')
            default_value = var_def.get('default_value', '')
            description = var_def.get('description', '')
            
            if not var_name:
                business_logger.warning(f"⚠️ [CONTEXT] Variable definition missing name: {var_def}")
                continue
            
            # Extract value directly from concept_data using variable name as key
            extracted_value = concept_data.get(var_name, default_value)
            
            # Set the context variable
            context_vars.set(var_name, extracted_value)
            business_logger.debug(f"🔧 [CONTEXT] Set '{var_name}': {description}")
        
        business_logger.info(f"✅ [CONTEXT] Created {len(variable_definitions)} context variables from JSON configuration")
        return context_vars
        
    except Exception as e:
        business_logger.error(f"❌ [CONTEXT] Failed to create context variables: {e}")
        # Return minimal fallback context
        context_vars = ContextVariables()
        context_vars.set("concept_overview", "Error loading context - using minimal fallback")
        return context_vars

async def _load_concept_data(variable_definitions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Load concept data from database via Azure Key Vault based on variable definitions.
    
    Args:
        variable_definitions: List of variable definitions with database config
        
    Returns:
        Dictionary containing loaded concept data
    """
    concept_data = {}
    
    try:
        # Load concept data from database via Azure Key Vault
        business_logger.info("🔧 [CONTEXT] Loading from database via Azure Key Vault...")
        db_data = await _load_from_database(variable_definitions)
        if db_data:
            concept_data.update(db_data)
            business_logger.info("✅ [CONTEXT] Loaded concept data from database")
        else:
            business_logger.info("📝 [CONTEXT] No data from database - will use defaults")
                
    except Exception as e:
        business_logger.warning(f"⚠️ [CONTEXT] Error loading from database: {e}")
    
    return concept_data

async def _load_from_database(variable_definitions: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Load concept data from MongoDB using Azure Key Vault secrets.
    
    Args:
        variable_definitions: List of variable definitions with database config
        
    Returns:
        Loaded data or None if not available
    """
    try:
        # Import the existing core configuration
        from core.core_config import get_mongo_client, get_secret
        
        # Get database name from Azure Key Vault or fallback to environment
        try:
            # Try to get from Azure Key Vault first
            database_name = get_secret('MongoDBName')
        except:
            # Fallback to environment variable
            import os
            database_name = os.getenv('MONGODB_DATABASE_NAME', 'autogen_ai_agents')
        
        business_logger.info(f"🔧 [CONTEXT] Connecting to MongoDB database via Azure Key Vault: {database_name}")
        
        # Use the existing MongoDB client from core_config (handles Key Vault automatically)
        mongo_client = get_mongo_client()
        
        # Test the connection
        try:
            await mongo_client.admin.command('ping')
            business_logger.info("✅ [CONTEXT] MongoDB connection successful via Azure Key Vault")
        except Exception as e:
            business_logger.warning(f"⚠️ [CONTEXT] MongoDB connection failed: {e}")
            return None
        
        database = mongo_client[database_name]
        concept_data = {}
        
        # Query each variable that has database configuration
        for var_def in variable_definitions:
            var_name = var_def.get('name')
            db_config = var_def.get('database')
            
            if not db_config or not var_name:
                continue
                
            try:
                collection_name = db_config.get('collection')
                query = db_config.get('query', {})
                field = db_config.get('field', 'content')
                
                if not collection_name:
                    business_logger.warning(f"⚠️ [CONTEXT] No collection specified for variable: {var_name}")
                    continue
                
                collection = database[collection_name]
                
                # Execute the query (using async motor client)
                business_logger.debug(f"🔧 [CONTEXT] Querying {collection_name} for {var_name} with: {query}")
                
                document = await collection.find_one(query)
                
                if document:
                    # Extract the specified field or the whole document
                    if field and field in document:
                        concept_data[var_name] = document[field]
                    else:
                        concept_data[var_name] = document
                    
                    business_logger.info(f"✅ [CONTEXT] Found data for {var_name} in {collection_name}")
                else:
                    business_logger.info(f"📝 [CONTEXT] No data found for {var_name} in {collection_name}")
                    
            except Exception as e:
                business_logger.warning(f"⚠️ [CONTEXT] Failed to query {var_name}: {e}")
                continue
        
        # Close the connection
        mongo_client.close()
        
        if concept_data:
            business_logger.info(f"✅ [CONTEXT] Successfully loaded {len(concept_data)} variables from MongoDB")
            return concept_data
        else:
            business_logger.info("📝 [CONTEXT] No data found in any MongoDB queries")
            return None
        
    except Exception as e:
        business_logger.warning(f"⚠️ [CONTEXT] MongoDB loading failed: {e}")
        return None