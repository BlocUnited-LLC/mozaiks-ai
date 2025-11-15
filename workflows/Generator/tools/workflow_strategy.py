"""
workflow_strategy tool - Caches high-level workflow architecture from WorkflowStrategyAgent.

This tool stores the strategic workflow plan in context variables, triggering
handoff to WorkflowImplementationAgent for detailed agent/tool design.
"""

from typing import Dict, Any, Annotated, Optional
import logging

_logger = logging.getLogger("tools.workflow_strategy")
_LIFECYCLE_TRIGGERS = {"before_chat", "after_chat", "before_agent", "after_agent"}


def _normalize_lifecycle_operations(value: Any) -> list[dict[str, Any]]:
    """Sanitize lifecycle operations emitted by WorkflowStrategyAgent."""
    normalized: list[dict[str, Any]] = []
    if not isinstance(value, list):
        return normalized

    for idx, entry in enumerate(value):
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or f"Lifecycle {idx + 1}").strip()
        trigger = str(entry.get("trigger") or "").strip().lower()
        target = str(entry.get("target") or "").strip()
        description = str(entry.get("description") or "").strip()

        if trigger not in _LIFECYCLE_TRIGGERS:
            _logger.debug("Skipping lifecycle entry '%s' with invalid trigger '%s'", name, trigger)
            continue

        normalized.append(
            {
                "name": name or f"{trigger.title()} operation",
                "trigger": trigger,
                "target": target or None,
                "description": description,
            }
        )
    return normalized

def workflow_strategy(
    *,
    WorkflowStrategy: Annotated[Optional[Dict[str, Any]], "High-level workflow architecture payload produced by WorkflowStrategyAgent"],
    agent_message: Annotated[Optional[str], "Optional confirmation message echoed to the chat"] = None,
    context_variables: Annotated[Optional[Any], "Context variables provided by AG2"] = None,
) -> str:
    """
    Cache workflow strategy from WorkflowStrategyAgent.
    
    This stores the high-level workflow architecture in context variables,
    triggering handoff to WorkflowImplementationAgent for implementation.
    
    Args:
        WorkflowStrategy: Structured payload containing workflow metadata, orchestration pattern,
            trigger, lifecycle operations, and phase definitions.
        agent_message: Optional short confirmation message included in the chat transcript.
        context_variables: Runtime context manager (injected by AG2) used to persist strategy state.
    
    Returns:
        Confirmation message
    """
    
    if not WorkflowStrategy:
        raise ValueError("WorkflowStrategy payload is required")
    if not isinstance(WorkflowStrategy, dict):
        raise ValueError("WorkflowStrategy payload must be a dictionary")

    workflow_name = str(WorkflowStrategy.get("workflow_name") or "").strip()
    workflow_description = str(WorkflowStrategy.get("workflow_description") or "").strip()
    pattern = str(WorkflowStrategy.get("pattern") or "").strip()
    trigger = str(
        WorkflowStrategy.get("trigger")
        or WorkflowStrategy.get("trigger_type")
        or ""
    ).strip()
    lifecycle_ops_payload = WorkflowStrategy.get("lifecycle_operations")
    lifecycle_operations = _normalize_lifecycle_operations(lifecycle_ops_payload)
    strategy_notes = str(WorkflowStrategy.get("strategy_notes") or "").strip()
    phases_payload = WorkflowStrategy.get("phases")
    phases: list[Dict[str, Any]] = []
    if isinstance(phases_payload, list):
        for idx, raw in enumerate(phases_payload):
            if isinstance(raw, dict):
                phases.append(raw)
            else:
                _logger.debug("Skipping non-dict phase payload at index %s", idx)

    if not workflow_name:
        raise ValueError("WorkflowStrategy.workflow_name is required")
    if not workflow_description:
        raise ValueError("WorkflowStrategy.workflow_description is required")
    if not trigger:
        raise ValueError("WorkflowStrategy.trigger is required")
    if not pattern:
        raise ValueError("WorkflowStrategy.pattern is required")

    strategy = {
        "workflow_name": workflow_name,
        "workflow_description": workflow_description,
        "trigger": trigger,
        "trigger_type": trigger,  # Add trigger_type for UI compatibility
        "pattern": pattern,
        "phases": phases,
        "lifecycle_operations": lifecycle_operations,
        "strategy_notes": strategy_notes,
    }
    
    # Cache in context variables
    if context_variables and hasattr(context_variables, "set"):
        try:
            context_variables.set("workflow_strategy", strategy)  # type: ignore[attr-defined]
            context_variables.set("strategy_ready", True)  # type: ignore[attr-defined]
            _logger.info(f"Cached workflow strategy for '{workflow_name}' with pattern '{pattern}'")
        except Exception as e:
            _logger.error(f"Failed to cache workflow strategy: {e}")
            return f"Error caching strategy: {str(e)}"
    else:
        _logger.warning("context_variables not available or missing 'set' method")
    
    phase_count = len(phases)
    approval_phases = sum(1 for p in phases if p.get("approval_required", False))
    lifecycle_count = len(lifecycle_operations)

    confirmation_message = agent_message.strip() if isinstance(agent_message, str) else ""
    if not confirmation_message:
        confirmation_message = (
            "Workflow strategy cached successfully."
        )

    return (
        f"{confirmation_message}\n\n"
        f"Workflow: {workflow_name}\n"
        f"Pattern: {pattern}\n"
        f"Trigger: {trigger}\n"
        f"Lifecycle Ops: {lifecycle_count}\n"
        f"Phases: {phase_count} ({approval_phases} require approval)\n\n"
        "Handing off to WorkflowImplementationAgent for detailed implementation..."
    )

