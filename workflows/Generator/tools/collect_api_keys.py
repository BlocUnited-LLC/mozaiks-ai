# ==============================================================================
# FILE: workflows/Generator/tools/collect_api_keys.py  
# DESCRIPTION: Lifecycle tool to extract third_party_apis from ActionPlan and collect API keys
# TRIGGER: before_agent (ContextVariablesAgent)
# ==============================================================================

"""
Lifecycle Tool: API Key Collection from Action Plan

This lifecycle tool executes before the ContextVariablesAgent runs, extracting
third_party_apis from the ActionPlanArchitect's structured output and prompting
the user to provide any required API keys.

Flow:
1. Extract Action Plan from context (cached by ActionPlanArchitect)
2. Parse all third_party_apis from workflow phases/agents
3. Deduplicate and normalize service names
4. For each service, prompt user for API key using request_api_key
5. Store collected keys in context for ContextVariablesAgent to use
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional, Set
from datetime import datetime, UTC

from logs.logging_config import get_workflow_logger

logger = logging.getLogger(__name__)


def _normalize_service_name(service: str) -> str:
    """Normalize service name to lowercase snake_case."""
    if not service:
        return ""
    # Convert PascalCase to snake_case
    import re
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', service)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()


def _extract_third_party_apis_from_action_plan(action_plan: Dict[str, Any]) -> List[str]:
    """
    Extract all third_party_apis from Action Plan workflow phases.
    
    Args:
        action_plan: Action Plan JSON (ActionPlanCall.ActionPlan structure)
    
    Returns:
        Deduplicated list of normalized service names
    """
    services: Set[str] = set()
    
    try:
        # Navigate to workflow.phases
        workflow = action_plan.get('workflow', {})
        phases = workflow.get('phases', [])
        
        for phase in phases:
            agents = phase.get('agents', [])
            for agent in agents:
                third_party_apis = agent.get('third_party_apis', [])
                for service in third_party_apis:
                    if service:
                        normalized = _normalize_service_name(service)
                        if normalized:
                            services.add(normalized)
    except Exception as e:
        logger.warning(f"Failed to extract third_party_apis from Action Plan: {e}")
    
    return sorted(list(services))  # Sort for deterministic ordering


async def collect_api_keys_from_action_plan(context_variables: Any = None) -> Dict[str, Any]:
    """
    Lifecycle tool: Extract third_party_apis from Action Plan and collect API keys.
    
    This function runs before ContextVariablesAgent executes, extracting all
    third_party services from the approved Action Plan and prompting the user
    to provide API keys for each service.
    
    Args:
        context_variables: AG2 ContextVariables instance with:
            - action_plan: Cached Action Plan from ActionPlanArchitect
            - chat_id, workflow_name, enterprise_id, user_id
    
    Returns:
        Status dict with collected service list
    """
    if not context_variables:
        logger.warning("collect_api_keys_from_action_plan called without context_variables")
        return {"status": "no_context", "services_collected": []}
    
    # Extract context data
    data = getattr(context_variables, 'data', {})
    workflow_name = data.get('workflow_name', 'Generator')
    chat_id = data.get('chat_id')
    
    wf_logger = get_workflow_logger(workflow_name=workflow_name, chat_id=chat_id)
    
    # Get cached Action Plan from context
    action_plan = data.get('action_plan')
    if not action_plan:
        wf_logger.warning("⚠️ No action_plan found in context - skipping API key collection")
        return {"status": "no_action_plan", "services_collected": []}
    
    # Extract third_party_apis
    services = _extract_third_party_apis_from_action_plan(action_plan)
    
    if not services:
        wf_logger.info("✓ No third-party services found in Action Plan - skipping API key collection")
        return {"status": "no_services_required", "services_collected": []}
    
    wf_logger.info(f"🔑 Found {len(services)} third-party services requiring API keys: {services}")
    
    # Import request_api_key function (original UI tool function)
    try:
        from workflows.Generator.tools.request_api_key import request_api_key
    except ImportError:
        wf_logger.error("Failed to import request_api_key - cannot collect API keys")
        return {"status": "import_error", "services_collected": []}
    
    # Collect API keys for each service
    collected_services = []
    failed_services = []
    
    for service in services:
        try:
            wf_logger.info(f"🔑 Requesting API key for service: {service}")
            
            # Call request_api_key with service name and context
            result = await request_api_key(
                service=service,
                agent_message=f"Please provide your {service.replace('_', ' ').title()} API key to continue.",
                description=f"API key for {service.replace('_', ' ').title()} integration",
                required=True,
                mask_input=True,
                context_variables=context_variables,
            )
            
            # Check result
            if result.get('status') == 'success':
                collected_services.append(service)
                wf_logger.info(f"✓ Successfully collected API key for {service}")
            elif result.get('status') == 'cancelled':
                wf_logger.warning(f"⚠️ User cancelled API key input for {service}")
                failed_services.append(service)
                # Continue to next service (don't break workflow)
            else:
                wf_logger.warning(f"⚠️ Failed to collect API key for {service}: {result.get('message', 'unknown error')}")
                failed_services.append(service)
        
        except Exception as e:
            wf_logger.error(f"❌ Error collecting API key for {service}: {e}", exc_info=True)
            failed_services.append(service)
    
    # Log summary
    wf_logger.info(
        f"🔑 API key collection complete: "
        f"{len(collected_services)} collected, {len(failed_services)} failed/skipped"
    )
    
    # Store collection status in context for downstream agents
    data['api_keys_collected'] = collected_services
    data['api_keys_failed'] = failed_services
    data['api_keys_collection_complete'] = True
    data['api_keys_collection_timestamp'] = datetime.now(UTC).isoformat()
    
    return {
        "status": "complete",
        "services_collected": collected_services,
        "services_failed": failed_services,
        "total_services": len(services),
    }
