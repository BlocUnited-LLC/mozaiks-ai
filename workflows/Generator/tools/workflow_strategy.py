"""
workflow_strategy tool - Caches high-level workflow architecture from WorkflowStrategyAgent.

This tool stores the strategic workflow plan in context variables, triggering
handoff to WorkflowImplementationAgent for detailed agent/tool design.
"""

from typing import Dict, Any, Annotated, Optional
import logging

_logger = logging.getLogger("tools.workflow_strategy")

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
            trigger, interaction mode, and phase definitions.
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
    interaction_mode = str(WorkflowStrategy.get("interaction_mode") or "").strip()
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
    if not interaction_mode:
        raise ValueError("WorkflowStrategy.interaction_mode is required")

    strategy = {
        "workflow_name": workflow_name,
        "workflow_description": workflow_description,
        "trigger": trigger,
        "interaction_mode": interaction_mode,
        "pattern": pattern,
        "phases": phases,
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
        f"Interaction: {interaction_mode}\n"
        f"Phases: {phase_count} ({approval_phases} require approval)\n\n"
        "Handing off to WorkflowImplementationAgent for detailed implementation..."
    )

