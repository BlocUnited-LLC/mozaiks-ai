# ==============================================================================
# FILE: workflows/Generator/tools/collect_api_keys.py  
# DESCRIPTION: Lifecycle tool to extract agent integrations from ActionPlan and collect API keys
# TRIGGER: before_agent (ContextVariablesAgent)
# ==============================================================================

"""
Lifecycle Tool: API Key Collection from Action Plan

This lifecycle tool executes before the ContextVariablesAgent runs, extracting
integrations from the ActionPlanArchitect's structured output and prompting
the user to provide any required API keys.

Flow:
1. Extract Action Plan from context (cached by ActionPlanArchitect)
2. Parse all integrations from workflow phases/agents
3. Deduplicate and normalize service names
4. For each service, prompt user for API key using request_api_key
5. Store collected keys in context for ContextVariablesAgent to use
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, UTC

from core.transport.simple_transport import SimpleTransport
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


def _extract_integrations_from_action_plan(action_plan: Dict[str, Any]) -> List[Dict[str, str]]:
    """
    Extract all integrations that require external API keys from the Action Plan.

    Args:
        action_plan: Action Plan workflow payload as cached by ActionPlanArchitect.

    Returns:
        Deduplicated list of service metadata dicts containing normalized identifier and display label.
    """
    services: Dict[str, str] = {}

    def _record_service(raw_value: Any) -> None:
        if not raw_value:
            return
        original = str(raw_value).strip()
        if not original:
            return
        normalized = _normalize_service_name(original)
        if not normalized:
            return
        if normalized not in services or not services[normalized]:
            services[normalized] = original or normalized.replace('_', ' ').title()

    try:
        if not isinstance(action_plan, dict):
            return []

        phases = action_plan.get('phases', [])
        if not isinstance(phases, list):
            phases = []

        for phase in phases:
            if not isinstance(phase, dict):
                continue

            agents = phase.get('agents', [])
            if not isinstance(agents, list):
                continue

            for agent in agents:
                if not isinstance(agent, dict):
                    continue
                integrations = agent.get('integrations', [])
                if not isinstance(integrations, list):
                    continue
                for service in integrations:
                    _record_service(service)
    except Exception as e:
        logger.warning(f"Failed to extract integrations from Action Plan: {e}")

    def _sort_key(item: Tuple[str, str]) -> Tuple[str, str]:
        normalized, display = item
        return (display.lower(), normalized)

    sorted_items = sorted(services.items(), key=_sort_key)
    return [
        {"service": normalized, "display_name": display or normalized.replace('_', ' ').title()}
        for normalized, display in sorted_items
    ]


async def collect_api_keys_from_action_plan(context_variables: Any = None) -> Dict[str, Any]:
    """
    Lifecycle tool: Extract integrations from the Action Plan and collect API keys.
    
    This function runs before ContextVariablesAgent executes, extracting all
    third-party services from the approved Action Plan and prompting the user
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
    
    # Extract integrations
    services = _extract_integrations_from_action_plan(action_plan)

    if not services:
        wf_logger.info("✓ No integrations requiring API keys found in Action Plan - skipping collection")
        return {"status": "no_services_required", "services_collected": []}
    
    wf_logger.info(
        "🔑 Found %s third-party services requiring API keys: %s",
        len(services),
        [svc["display_name"] for svc in services],
    )
    
    # Import request_api_key function (original UI tool function)
    try:
        from workflows.Generator.tools.request_api_key import request_api_key
    except ImportError:
        wf_logger.error("Failed to import request_api_key - cannot collect API keys")
        return {"status": "import_error", "services_collected": []}
    
    # Collect API keys for each service
    collected_services: List[str] = []
    failed_services: List[str] = []
    collected_details: List[Dict[str, Any]] = []
    failed_details: List[Dict[str, Any]] = []

    for service in services:
        service_identifier = service.get("service")
        service_display = service.get("display_name") or service_identifier
        if not service_identifier:
            continue
        try:
            wf_logger.info("🔑 Requesting API key for service: %s", service_display)

            # Call request_api_key with service name and context
            result = await request_api_key(
                service=service_identifier,
                service_display_name=service_display,
                agent_message=f"Please provide your {service_display} API key to continue.",
                description=f"API key for {service_display} integration",
                required=True,
                mask_input=True,
                context_variables=context_variables,
            )
            
            # Check result
            if result.get('status') == 'success':
                collected_services.append(service_identifier)
                collected_details.append({
                    "service": service_identifier,
                    "display_name": service_display,
                    "metadata_id": result.get("metadata_id"),
                })
                wf_logger.info("✓ Successfully collected API key for %s", service_display)
            elif result.get('status') == 'cancelled':
                wf_logger.warning("⚠️ User cancelled API key input for %s", service_display)
                failed_services.append(service_identifier)
                failed_details.append({
                    "service": service_identifier,
                    "display_name": service_display,
                    "reason": "cancelled",
                })
                # Continue to next service (don't break workflow)
            else:
                wf_logger.warning(
                    "⚠️ Failed to collect API key for %s: %s",
                    service_display,
                    result.get('message', 'unknown error'),
                )
                failed_services.append(service_identifier)
                failed_details.append({
                    "service": service_identifier,
                    "display_name": service_display,
                    "reason": result.get('message') or 'unknown error',
                })
        
        except Exception as e:
            wf_logger.error("❌ Error collecting API key for %s: %s", service_display, e, exc_info=True)
            failed_services.append(service_identifier)
            failed_details.append({
                "service": service_identifier,
                "display_name": service_display,
                "reason": str(e),
            })
    
    # Log summary
    wf_logger.info(
        f"🔑 API key collection complete: "
        f"{len(collected_services)} collected, {len(failed_services)} failed/skipped"
    )
    
    # Store collection status in context for downstream agents
    data['api_keys_collected'] = collected_services
    data['api_keys_collected_details'] = collected_details
    data['api_keys_failed'] = failed_services
    data['api_keys_failed_details'] = failed_details
    data['api_keys_collection_complete'] = True
    data['api_keys_collection_timestamp'] = datetime.now(UTC).isoformat()

    # Ensure acceptance flag stays affirmed after collection
    try:
        context_variables.set('action_plan_acceptance', "accepted")  # type: ignore[attr-defined]
    except Exception:
        pass

    # Kick the orchestrator so ContextVariablesAgent can resume
    try:
        transport = await SimpleTransport.get_instance()
        if transport and chat_id:
            await transport.handle_user_input_from_api(
                chat_id=chat_id,
                user_id=data.get('user_id'),
                workflow_name=workflow_name,
                message=None,
                enterprise_id=data.get('enterprise_id'),
            )
            wf_logger.info("[API_KEYS] Resumed workflow after API key collection")
    except Exception as resume_err:
        wf_logger.debug(f"[API_KEYS] Resume signal failed: {resume_err}")

    return {
        "status": "complete",
        "services_collected": collected_services,
        "services_failed": failed_services,
        "total_services": len(services),
        "services_details": {
            "collected": collected_details,
            "failed": failed_details,
        },
    }
