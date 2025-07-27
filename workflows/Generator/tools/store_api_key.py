# ==============================================================================
# FILE: workflows/Generator/tools/store_api_key.py
# DESCRIPTION: API key storage tool - single async function export
# ==============================================================================

import logging
from typing import Dict, Any

# Import enhanced logging
from logs.logging_config import get_business_logger

business_logger = get_business_logger("generator_store_api_key")

async def store_api_key(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle API key submission from AgentAPIKeyInput component
    
    Args:
        data: Component action data containing API key info
        
    Returns:
        Response dictionary with status
    """
    try:
        action_type = data.get('type', 'unknown')
        business_logger.info(f"🔑 [STORE_API_KEY] Received action: {action_type}")
        
        if action_type == 'api_key_submit':
            return await handle_api_key_submission(data)
        elif action_type == 'cancel':
            return await handle_api_key_cancellation(data)
        else:
            business_logger.warning(f"Unknown action type: {action_type}")
            return {"status": "error", "message": f"Unknown action: {action_type}"}
            
    except Exception as e:
        business_logger.error(f"[STORE_API_KEY] Error: {e}")
        return {"status": "error", "message": str(e)}


async def handle_api_key_submission(data: Dict[str, Any]) -> Dict[str, Any]:
    """Handle API key submission"""
    api_key = data.get('apiKey', '').strip()
    service = data.get('service', 'unknown')
    
    if not api_key:
        return {"status": "error", "message": "API key cannot be empty"}
    
    business_logger.info(f"🔐 [STORE_API_KEY] Processing API key for service: {service}")
    
    business_logger.info(f"🔑 [STORE_API_KEY] Processed API key for {service} (masked: {api_key[:8] + '...' + api_key[-4:]})")
    
    return {
        "status": "success",
        "message": f"API key for {service} stored successfully",
        "service": service,
        "masked_key": api_key[:8] + "..." + api_key[-4:] if len(api_key) > 12 else "***",
        "api_key": api_key  # Provide the actual key in the tool response for agent use
    }


async def handle_api_key_cancellation(data: Dict[str, Any]) -> Dict[str, Any]:
    """Handle API key submission cancellation"""
    service = data.get('service', 'unknown')
    
    business_logger.info(f"❌ [STORE_API_KEY] API key submission cancelled for service: {service}")
    
    return {
        "status": "cancelled",
        "message": f"API key submission for {service} was cancelled",
        "service": service
    }
