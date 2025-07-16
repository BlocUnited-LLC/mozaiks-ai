# ==============================================================================
# FILE: Generator/ContextVariables.py
# DESCRIPTION: Context variable factory for AG2 groupchat workflows
# ==============================================================================
from autogen.agentchat.group import ContextVariables

def get_context(concept_data=None):
    """Create context variables using enterprise concept info (workflow-agnostic)"""
    
    # Extract concept overview
    overview = concept_data.get('ConceptOverview', '') if concept_data else ''

    return ContextVariables(data={
        # Concept context (workflow-specific)
        "concept_overview": overview,
        
        # Component interaction context
        "api_keys": {},                    # Stores masked API key info
        "secure_api_keys": {},             # Stores actual API keys (should be encrypted in production)
        "downloaded_files": [],            # Tracks file downloads
        "component_interactions": 0,        # Count of component interactions
        "last_component_action": None,      # Last component action performed
        "active_components": [],           # Currently active components
        "api_key_ready": False,            # Whether API keys are available for use
        "cancelled_api_submissions": [],   # Track cancelled API key submissions
    })


async def context_update(
    agent_name: str,
    component_name: str,
    action_data: dict,
    context_variables
) -> dict:
    """
    Workflow-specific context update function for Generator workflow
    
    This function is called by the core context adjustment bridge when
    a component action needs to update ContextVariables.
    
    Args:
        agent_name: Name of the agent that owns the component
        component_name: Name of the component that sent the action  
        action_data: The action data from the frontend component
        context_variables: The AG2 ContextVariables to update
        
    Returns:
        Result of the context update
    """
    from logs.logging_config import get_business_logger
    
    logger = get_business_logger("generator_context_update")
    logger.info(f"🔄 Generator context update: {agent_name}.{component_name}")
    
    try:
        action_type = action_data.get('type', 'unknown')
        
        # Handle different component types
        if component_name == 'AgentAPIKeyInput':
            return await _handle_api_key_context(action_data, context_variables, logger)
            
        elif component_name == 'FileDownloadCenter':
            return await _handle_download_context(action_data, context_variables, logger)
            
        else:
            # Generic component handling
            return _handle_generic_component(agent_name, component_name, action_data, context_variables, logger)
            
    except Exception as e:
        logger.error(f"Context update failed for {component_name}: {e}")
        return {"status": "error", "message": str(e)}


async def _handle_api_key_context(action_data: dict, context_variables, logger) -> dict:
    """Handle API key component context updates"""
    action_type = action_data.get('type')
    
    if action_type == 'api_key_submit':
        service = action_data.get('service', 'unknown')
        api_key = action_data.get('apiKey', '')
        
        # Update API key context
        api_keys = context_variables.get('api_keys', {}) or {}
        api_keys[service] = {
            'masked_key': api_key[:8] + "..." + api_key[-4:] if len(api_key) > 12 else "***",
            'status': 'active',
            'submitted_at': str(__import__('time').time())
        }
        
        secure_keys = context_variables.get('secure_api_keys', {}) or {}
        secure_keys[service] = api_key
        
        context_variables.set('api_keys', api_keys)
        context_variables.set('secure_api_keys', secure_keys)
        context_variables.set('last_api_key_service', service)
        context_variables.set('api_key_ready', True)
        
        logger.info(f"🔑 API key context updated for {service}")
        return {"status": "success", "service": service, "action": "api_key_stored"}
        
    elif action_type == 'cancel':
        cancelled = context_variables.get('cancelled_api_submissions', []) or []
        cancelled.append({
            'service': action_data.get('service', 'unknown'),
            'cancelled_at': str(__import__('time').time())
        })
        context_variables.set('cancelled_api_submissions', cancelled)
        context_variables.set('api_key_ready', False)
        
        logger.info("❌ API key submission cancelled")
        return {"status": "success", "action": "api_key_cancelled"}
    
    return {"status": "unhandled", "action_type": action_type}


async def _handle_download_context(action_data: dict, context_variables, logger) -> dict:
    """Handle file download component context updates"""
    action_type = action_data.get('type')
    
    if action_type == 'download':
        file_id = action_data.get('fileId')
        filename = action_data.get('filename')
        
        downloaded_files = context_variables.get('downloaded_files', []) or []
        downloaded_files.append({
            'file_id': file_id,
            'filename': filename,
            'download_time': str(__import__('time').time()),
            'status': 'completed'
        })
        
        context_variables.set('downloaded_files', downloaded_files)
        context_variables.set('last_download', filename)
        
        logger.info(f"📁 Download context updated for {filename}")
        return {"status": "success", "filename": filename, "action": "file_downloaded"}
        
    elif action_type == 'download_all':
        files = action_data.get('files', [])
        bulk_count = len(files)
        
        context_variables.set('bulk_download_count', bulk_count)
        context_variables.set('last_bulk_download_time', str(__import__('time').time()))
        
        logger.info(f"📦 Bulk download context updated ({bulk_count} files)")
        return {"status": "success", "file_count": bulk_count, "action": "bulk_download"}
    
    return {"status": "unhandled", "action_type": action_type}


def _handle_generic_component(agent_name: str, component_name: str, action_data: dict, context_variables, logger) -> dict:
    """Handle generic component context updates"""
    
    # Store component interaction
    interactions = context_variables.get('component_interactions', 0)
    context_variables.set('component_interactions', interactions + 1)
    
    # Store last action
    context_variables.set('last_component_action', {
        'agent': agent_name,
        'component': component_name,
        'action_type': action_data.get('type', 'unknown'),
        'timestamp': str(__import__('time').time())
    })
    
    logger.info(f"🎯 Generic component context updated: {component_name}")
    return {
        "status": "success", 
        "action": "generic_component_interaction",
        "interactions_count": interactions + 1
    }