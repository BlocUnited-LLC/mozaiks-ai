# ==============================================================================
# FILE: workflows/Generator/tools/api_manager.py
# DESCRIPTION: Backend handler for AgentAPIKeyInput component interactions
# ==============================================================================

import logging
from typing import Dict, Any, Optional
from autogen.agentchat.group import ContextVariables

# Import enhanced logging
from logs.logging_config import get_business_logger

business_logger = get_business_logger("generator_api_manager")

async def store_api_key(data: Dict[str, Any], context_variables: Optional[ContextVariables] = None) -> Dict[str, Any]:
    """
    Handle API key submission from AgentAPIKeyInput component
    
    Args:
        data: Component action data containing API key info
        context_variables: AG2 ContextVariables for sharing state between agents
        
    Returns:
        Response dictionary with status and updated context
    """
    try:
        action_type = data.get('type', 'unknown')
        business_logger.info(f"🔑 API manager received action: {action_type}")
        
        if action_type == 'api_key_submit':
            return await handle_api_key_submission(data, context_variables)
        elif action_type == 'cancel':
            return await handle_api_key_cancellation(data, context_variables)
        else:
            business_logger.warning(f"Unknown action type: {action_type}")
            return {"status": "error", "message": f"Unknown action: {action_type}"}
            
    except Exception as e:
        business_logger.error(f"API manager error: {e}")
        return {"status": "error", "message": str(e)}


async def handle_api_key_submission(data: Dict[str, Any], context_variables: Optional[ContextVariables] = None) -> Dict[str, Any]:
    """Handle API key submission"""
    api_key = data.get('apiKey', '').strip()
    service = data.get('service', 'unknown')
    agent_id = data.get('agentId', 'unknown')
    
    if not api_key:
        return {"status": "error", "message": "API key cannot be empty"}
    
    business_logger.info(f"🔐 Processing API key for service: {service} (Agent: {agent_id})")
    
    # Update context variables to store API key securely
    if context_variables:
        # Store API keys in context (in production, encrypt these!)
        api_keys = context_variables.get('api_keys', {})
        if api_keys is None:
            api_keys = {}
            
        api_keys[service] = {
            'key': api_key[:8] + "..." + api_key[-4:],  # Masked for logging
            'agent_id': agent_id,
            'service': service,
            'status': 'active',
            'submitted_at': str(__import__('time').time())
        }
        
        # Store the actual key separately (should be encrypted in production)
        secure_keys = context_variables.get('secure_api_keys', {})
        if secure_keys is None:
            secure_keys = {}
        secure_keys[service] = api_key
        
        context_variables.set('api_keys', api_keys)
        context_variables.set('secure_api_keys', secure_keys)
        context_variables.set('last_api_key_service', service)
        context_variables.set('api_key_ready', True)
        
        business_logger.info(f"🔑 Stored API key for {service} (masked: {api_keys[service]['key']})")
    
    return {
        "status": "success",
        "message": f"API key for {service} stored successfully",
        "service": service,
        "agent_id": agent_id,
        "masked_key": api_key[:8] + "..." + api_key[-4:] if len(api_key) > 12 else "***"
    }


async def handle_api_key_cancellation(data: Dict[str, Any], context_variables: Optional[ContextVariables] = None) -> Dict[str, Any]:
    """Handle API key submission cancellation"""
    service = data.get('service', 'unknown')
    agent_id = data.get('agentId', 'unknown')
    
    business_logger.info(f"❌ API key submission cancelled for service: {service} (Agent: {agent_id})")
    
    # Update context to track cancellation
    if context_variables:
        cancelled_submissions = context_variables.get('cancelled_api_submissions', [])
        if cancelled_submissions is None:
            cancelled_submissions = []
            
        cancelled_submissions.append({
            'service': service,
            'agent_id': agent_id,
            'cancelled_at': str(__import__('time').time())
        })
        
        context_variables.set('cancelled_api_submissions', cancelled_submissions)
        context_variables.set('api_key_ready', False)
        
        business_logger.info(f"📝 Recorded cancellation for {service}")
    
    return {
        "status": "cancelled",
        "message": f"API key submission for {service} was cancelled",
        "service": service,
        "agent_id": agent_id
    }


def get_api_key(service: str, context_variables: ContextVariables) -> Optional[str]:
    """Helper to retrieve stored API key for a service"""
    secure_keys = context_variables.get('secure_api_keys', {})
    if secure_keys is None:
        return None
    return secure_keys.get(service)


def get_api_key_status(context_variables: ContextVariables) -> Dict[str, Any]:
    """Helper to retrieve API key status from context variables"""
    api_keys = context_variables.get('api_keys', {})
    if api_keys is None:
        api_keys = {}
        
    cancelled_submissions = context_variables.get('cancelled_api_submissions', [])
    if cancelled_submissions is None:
        cancelled_submissions = []
        
    return {
        'api_keys': api_keys,
        'last_service': context_variables.get('last_api_key_service'),
        'api_key_ready': context_variables.get('api_key_ready', False),
        'total_keys': len(api_keys),
        'cancelled_submissions': len(cancelled_submissions)
    }


def is_api_key_available(service: str, context_variables: ContextVariables) -> bool:
    """Check if API key is available for a specific service"""
    secure_keys = context_variables.get('secure_api_keys', {})
    if secure_keys is None:
        return False
    return service in secure_keys and bool(secure_keys[service])
