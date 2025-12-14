"""
technical_blueprint tool - caches architectural blueprint output from WorkflowArchitectAgent.

This tool persists the TechnicalBlueprint payload into context variables so that downstream
agents (WorkflowImplementationAgent, ProjectOverviewAgent, ActionPlan UI pipeline) can access
global context variables, UI Components, and chat-level lifecycle hooks.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Annotated
import logging

# Re-use normalization helpers from the Action Plan tool to keep schema alignment consistent.
from workflows.Generator.tools.action_plan import (
    _normalize_global_context_variables,
    _normalize_ui_components,
    _normalize_blueprint_lifecycle,
    _normalize_lifecycle_operations,
)

_logger = logging.getLogger("tools.technical_blueprint")


def _build_normalized_blueprint(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize TechnicalBlueprint payload into a stable structure."""
    normalized: Dict[str, Any] = {
        "global_context_variables": _normalize_global_context_variables(
            raw.get("global_context_variables")
        ),
        "ui_components": _normalize_ui_components(raw.get("ui_components")),
    }

    before_chat = _normalize_blueprint_lifecycle(raw.get("before_chat_lifecycle"), "before_chat")
    after_chat = _normalize_blueprint_lifecycle(raw.get("after_chat_lifecycle"), "after_chat")
    if before_chat:
        normalized["before_chat_lifecycle"] = before_chat
    if after_chat:
        normalized["after_chat_lifecycle"] = after_chat

    lifecycle_ops = _normalize_lifecycle_operations(raw.get("lifecycle_operations"))
    if lifecycle_ops:
        normalized["lifecycle_operations"] = lifecycle_ops

    workflow_dependencies = raw.get("workflow_dependencies")
    if isinstance(workflow_dependencies, dict):
        normalized["workflow_dependencies"] = workflow_dependencies

    return normalized


async def technical_blueprint(
    *,
    TechnicalBlueprint: Annotated[
        Optional[Dict[str, Any]],
        (
            "Workflow-wide technical blueprint produced by WorkflowArchitectAgent. "
            "Contains global_context_variables, ui_components, and lifecycle hooks."
        ),
    ] = None,
    agent_message: Annotated[Optional[str], "Optional confirmation message echoed to chat"] = None,
    context_variables: Annotated[Optional[Any], "Context variables provided by AG2"] = None,
) -> Dict[str, Any]:
    """Persist TechnicalBlueprint payload for downstream agents and UI renderers."""

    if TechnicalBlueprint is None:
        _logger.error("TechnicalBlueprint payload missing from tool invocation")
        return {"status": "error", "message": "TechnicalBlueprint payload is required"}
    if not isinstance(TechnicalBlueprint, dict):
        _logger.error(
            "TechnicalBlueprint payload must be a dictionary, received %s",
            type(TechnicalBlueprint).__name__,
        )
        return {"status": "error", "message": "TechnicalBlueprint payload must be an object"}

    normalized_blueprint = _build_normalized_blueprint(TechnicalBlueprint)

    global_ctx_count = len(normalized_blueprint.get("global_context_variables") or [])
    component_count = len(normalized_blueprint.get("ui_components") or [])
    before_chat = bool(normalized_blueprint.get("before_chat_lifecycle"))
    after_chat = bool(normalized_blueprint.get("after_chat_lifecycle"))

    _logger.info(
        "Caching TechnicalBlueprint: global_ctx=%d components=%d before_chat=%s after_chat=%s",
        global_ctx_count,
        component_count,
        before_chat,
        after_chat,
    )

    if context_variables and hasattr(context_variables, "set"):
        try:
            context_variables.set("technical_blueprint", normalized_blueprint)  # type: ignore[attr-defined]
        except Exception as ctx_err:  # pragma: no cover - defensive logging
            _logger.warning("Failed to persist technical_blueprint to context: %s", ctx_err)
            return {
                "status": "error",
                "message": "Unable to persist technical_blueprint to context_variables",
            }

    confirmation = (
        agent_message.strip()
        if isinstance(agent_message, str) and agent_message.strip()
        else "Technical blueprint cached for downstream agents."
    )

    return {
        "status": "success",
        "message": confirmation,
        "technical_blueprint": normalized_blueprint,
        "counts": {
            "global_context_variables": global_ctx_count,
            "ui_components": component_count,
            "before_chat_lifecycle": before_chat,
            "after_chat_lifecycle": after_chat,
        },
    }
