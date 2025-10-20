# ==============================================================================
# FILE: workflows/Generator/tools/mermaid_sequence_diagram.py
# DESCRIPTION: UI tool responsible for rendering the Mermaid sequence diagram
#              produced by ProjectOverviewAgent after the Action Plan is approved.
# ==============================================================================

from __future__ import annotations

import copy
import json
import logging
import uuid
from typing import Annotated, Any, Dict, List, Optional, Tuple

from core.workflow.outputs.ui_tools import UIToolError, use_ui_tool
from logs.logging_config import get_workflow_logger

_logger = logging.getLogger("tools.mermaid_sequence_diagram")
MANDATORY_PREFIX = "sequenceDiagram"


def _coerce_str(value: Any, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _coerce_list_of_str(value: Any) -> List[str]:
    if isinstance(value, list):
        result = []
        for item in value:
            if isinstance(item, str):
                trimmed = item.strip()
                if trimmed:
                    result.append(trimmed)
        return result
    return []

def _normalize_mermaid_diagram(diagram_text: str) -> str:
    """Normalize Mermaid diagram text and enforce required prefix/spacing."""
    if not isinstance(diagram_text, str):
        return ""

    normalized = diagram_text.replace("\r\n", "\n").strip()
    if not normalized:
        return ""

    if not normalized.startswith(MANDATORY_PREFIX):
        normalized = f"{MANDATORY_PREFIX}\n{normalized}"

    # Ensure we carry trailing newline consistency for Mermaid parser reliability
    normalized = _fix_mermaid_syntax(normalized)

    return normalized.strip("\n")


def _generate_fallback_diagram(legend: List[str], workflow_name: str) -> str:
    """Generate a simple, guaranteed-valid Mermaid diagram from legend entries.
    
    This is a fallback when the LLM-generated diagram has unfixable syntax errors.
    Creates a basic linear flow: User -> P1 -> P2 -> ... -> User
    """
    if not legend:
        return f"{MANDATORY_PREFIX}\n    participant User\n\n    User->>User: No phases defined"
    
    # Parse legend entries (format: "P1: Phase Name")
    participants = []
    for entry in legend:
        parts = entry.split(":", 1)
        if len(parts) == 2:
            alias = parts[0].strip()
            name = parts[1].strip()
            participants.append((alias, name))
    
    if not participants:
        return f"{MANDATORY_PREFIX}\n    participant User\n\n    User->>User: Invalid legend format"
    
    # Build diagram
    lines = [MANDATORY_PREFIX, "    participant User"]
    
    # Declare all participants
    for alias, name in participants:
        # Truncate name to 12 chars max for Mermaid compatibility
        short_name = name if len(name) <= 12 else name[:12]
        lines.append(f"    participant {alias} as {short_name}")
    
    # Add blank line after participants (Mermaid requirement)
    lines.append("")
    
    # Create simple linear flow
    if len(participants) == 1:
        alias, name = participants[0]
        lines.append(f"    User->>{alias}: Start {workflow_name}")
        lines.append(f"    {alias}->>User: Complete")
    else:
        # User -> P1
        lines.append(f"    User->>{participants[0][0]}: Start {workflow_name}")
        
        # P1 -> P2 -> P3 -> ...
        for i in range(len(participants) - 1):
            curr_alias = participants[i][0]
            next_alias = participants[i + 1][0]
            lines.append(f"    {curr_alias}->>{next_alias}: Continue")
        
        # PN -> User
        last_alias = participants[-1][0]
        lines.append(f"    {last_alias}->>User: Complete")
    
    return "\n".join(lines)


def _fix_mermaid_syntax(diagram_text: str) -> str:
    """Apply the Mermaid Diagram Reliability Rule by fixing common Mermaid sequence diagram syntax errors.

    Reliability guarantees:
    - Ensure a blank line exists between participant declarations and the first arrow so Mermaid renders consistently
    - Replace 'opt...else' with 'alt...else' (opt doesn't support else)
    - Remove duplicate/invalid deactivate calls
    - Ensure activate/deactivate pairs are balanced
    - Strip non-standard 'legend' sections (legend metadata should be in separate payload.legend array)
    """
    if not diagram_text or not isinstance(diagram_text, str):
        return diagram_text
    
    lines = diagram_text.splitlines()
    fixed_lines = []
    in_opt_block = False
    opt_indent = 0
    in_legend_block = False
    
    # Track activation state for each participant
    active_participants = set()
    
    # Track participant section to insert blank line
    last_participant_index = -1
    found_participant_section = False
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        
        # Detect start of legend block (non-standard, should be stripped)
        if stripped.lower() == 'legend' or stripped.lower().startswith('legend '):
            in_legend_block = True
            _logger.debug("Fixed Mermaid syntax: stripping legend block (use payload.legend array instead)")
            continue
        
        # Skip lines inside legend block until we hit a blank line or start of new section
        if in_legend_block:
            # Legend block ends at blank line or when we see standard Mermaid syntax
            if not stripped or stripped.startswith(('participant ', 'sequenceDiagram', 'Note ', 'Note:', 'activate ', 'deactivate ')) or '-->' in stripped or '->>' in stripped:
                in_legend_block = False
                # Don't skip this line, process it normally below (unless it's an invalid Note: line)
            else:
                # Skip legend content lines
                continue
        
        # Strip standalone "Note:" lines (invalid Mermaid syntax - should be "Note over", "Note left of", etc.)
        if stripped.startswith('Note:'):
            _logger.debug(f"Fixed Mermaid syntax: stripped invalid 'Note:' line (must be 'Note over/left_of/right_of'): {stripped[:60]}")
            continue
        
        # Track participant declarations
        if stripped.startswith('participant '):
            found_participant_section = True
            last_participant_index = len(fixed_lines)
            fixed_lines.append(line)
            continue
        
        # If we just finished participant section and next line is not blank, insert blank line
        if found_participant_section and last_participant_index >= 0:
            # Check if this is the first non-participant, non-blank line
            if stripped and not stripped.startswith('participant '):
                # Check if previous line is not already blank
                if fixed_lines and fixed_lines[-1].strip():
                    # Insert blank line before this line (after last participant)
                    fixed_lines.append('')
                    _logger.debug("Fixed Mermaid syntax: inserted blank line after participant declarations")
                found_participant_section = False
        
        # Track opt blocks
        if stripped.startswith('opt '):
            in_opt_block = True
            opt_indent = len(line) - len(line.lstrip())
            fixed_lines.append(line)
            continue
        
        # If we see 'else' inside an opt block, change the 'opt' to 'alt'
        if in_opt_block and stripped.startswith('else'):
            # Go back and fix the 'opt' line
            for i in range(len(fixed_lines) - 1, -1, -1):
                if fixed_lines[i].strip().startswith('opt '):
                    fixed_lines[i] = fixed_lines[i].replace('opt ', 'alt ', 1)
                    _logger.debug("Fixed Mermaid syntax: replaced 'opt' with 'alt' to support 'else' clause")
                    break
            in_opt_block = False
            fixed_lines.append(line)
            continue
        
        # Track end of opt block
        if in_opt_block and stripped == 'end':
            current_indent = len(line) - len(line.lstrip())
            if current_indent == opt_indent:
                in_opt_block = False
        
        # Track activate/deactivate state
        if stripped.startswith('activate '):
            participant = stripped.split('activate ', 1)[1].strip()
            active_participants.add(participant)
            fixed_lines.append(line)
            continue
        
        if stripped.startswith('deactivate '):
            participant = stripped.split('deactivate ', 1)[1].strip()
            if participant not in active_participants:
                # Skip invalid deactivate - participant is not active
                _logger.debug(f"Fixed Mermaid syntax: removed invalid 'deactivate {participant}' (participant not active)")
                continue
            else:
                active_participants.discard(participant)
                fixed_lines.append(line)
                continue
        
        fixed_lines.append(line)
    
    return '\n'.join(fixed_lines)


async def mermaid_sequence_diagram(
    *,
    MermaidSequenceDiagram: Annotated[
        Optional[Dict[str, Any]],
        "Mermaid sequence diagram payload with keys: workflow_name, legend.",
    ] = None,
    agent_name: Annotated[
        Optional[str],
        "Optional agent name supplied by AG2 auto-tool event (preferred source for attribution).",
    ] = None,
    agent_message: Annotated[
        Optional[str],
        "Concise invitation for the user to review the generated diagram.",
    ] = None,
    context_variables: Annotated[Optional[Any], "Context variables provided by AG2"] = None,
) -> Dict[str, Any]:
    """Persist a Mermaid sequence diagram supplied by ProjectOverviewAgent.

        Summary:
            Validates and normalizes the Mermaid diagram emitted by ProjectOverviewAgent,
            attaches it to the cached action plan payload, and surfaces the combined Action
            Plan + sequence diagram artifact. Falls back to legend-based auto-generation only
            when the diagram is missing or invalid.

        Payload Contract:
            field | type | description
            ------|------|------------
            MermaidSequenceDiagram | dict | Requires workflow_name and mermaid_diagram; legend optional.
            agent_name | str | Optional agent label supplied by AG2 auto-tool event.
            agent_message | str | Optional hint that accompanies the eventual artifact.

        Behavior:
            - Validates routing metadata (chat_id, enterprise_id).
            - Ensures a normalized action plan exists in context for augmentation.
            - Normalizes the provided mermaid_diagram text (prefix, spacing, reliability fixes).
            - Falls back to legend-based generation only when the provided diagram is unusable.
            - Writes the diagram text, source metadata, and readiness flag to context variables.
            - Embeds the diagram into the stored action plan for later emission by the
              ActionPlan UI tool.

        Returns:
            dict containing the mutated action plan, mermaid diagram text, diagram source, and readiness flag.

        Errors:
            Returns status="error" when required routing keys are missing or both diagram and legend are absent.
        """

    chat_id = enterprise_id = workflow_name = None
    if context_variables and hasattr(context_variables, "get"):
        try:
            chat_id = context_variables.get("chat_id")
            enterprise_id = context_variables.get("enterprise_id")
            workflow_name = context_variables.get("workflow_name")
        except Exception as ctx_err:
            _logger.debug("Unable to read routing context: %s", ctx_err)

    if not chat_id or not enterprise_id:
        _logger.warning("Missing routing context for MermaidSequenceDiagram tool")
        return {
            "status": "error",
            "message": "chat_id and enterprise_id are required",
        }

    wf_name = workflow_name or "Generated_Workflow"
    wf_logger = get_workflow_logger(workflow_name=wf_name, chat_id=chat_id, enterprise_id=enterprise_id)

    diagram_payload: Dict[str, Any] = {}
    if isinstance(MermaidSequenceDiagram, str):
        try:
            decoded = json.loads(MermaidSequenceDiagram)
            if isinstance(decoded, dict):
                diagram_payload = decoded
                _logger.info("Decoded MermaidSequenceDiagram string payload into dict")
        except json.JSONDecodeError:
            _logger.warning("Failed to decode MermaidSequenceDiagram string payload")
    elif isinstance(MermaidSequenceDiagram, dict):
        diagram_payload = MermaidSequenceDiagram

    if not isinstance(diagram_payload, dict):
        diagram_payload = {}

    # Extract legend, diagram, and workflow name from payload
    payload_workflow_name = _coerce_str(diagram_payload.get("workflow_name")) or wf_name
    legend = _coerce_list_of_str(diagram_payload.get("legend"))
    provided_diagram = _normalize_mermaid_diagram(diagram_payload.get("mermaid_diagram"))

    # Only honor an explicit agent_name argument or an agent_name/agentName field in the payload.
    # Do NOT attempt to extract attribution from the broader context here — attribution should be
    # resolved by the transport/UI layer so this tool remains workflow-agnostic.
    payload_agent_name = _coerce_str(agent_name) or _coerce_str(diagram_payload.get("agent_name")) or _coerce_str(
        diagram_payload.get("agentName")
    )

    resolved_agent_name = payload_agent_name or _coerce_str(diagram_payload.get("agent")) or None
    agent_name_source = "payload" if payload_agent_name else ("payload.agent" if diagram_payload.get("agent") else "unspecified")

    if not resolved_agent_name:
        # If no explicit agent was supplied, use a neutral default label but only log at DEBUG
        resolved_agent_name = "Agent"
        wf_logger.debug("[MERMAID] No explicit agent_name supplied; using default label 'Agent' (attribution should be supplied by UI/transport layer)")

    wf_logger.debug("🔍 [MERMAID] agent_name resolved (%s): %s", agent_name_source, resolved_agent_name)

    diagram_source = "provided"
    diagram_text = provided_diagram

    if not diagram_text:
        diagram_source = "fallback_from_legend" if legend else "missing"
        if legend:
            diagram_text = _generate_fallback_diagram(legend, payload_workflow_name)
            wf_logger.warning(
                "⚠️ [MERMAID] Provided mermaid_diagram missing or invalid; generated fallback from legend (%s phases)",
                len(legend),
            )
        else:
            wf_logger.error("No mermaid_diagram supplied and legend unavailable - cannot render diagram")
            return {
                "status": "error",
                "message": "Mermaid diagram text or legend is required",
                "reason": "missing_diagram",
            }
    else:
        wf_logger.info("✅ [MERMAID] Using provided mermaid_diagram text (%s characters)", len(diagram_text))

    stored_plan: Dict[str, Any] = {}
    if context_variables and hasattr(context_variables, "get"):
        try:
            raw_plan = context_variables.get("action_plan")
            if isinstance(raw_plan, dict):
                stored_plan = raw_plan
        except Exception as ctx_err:
            wf_logger.debug("Unable to retrieve stored action plan: %s", ctx_err)

    if not stored_plan:
        fallback_workflow = diagram_payload.get("workflow")
        if isinstance(fallback_workflow, dict):
            stored_plan = fallback_workflow

    if not stored_plan:
        wf_logger.warning("No action plan available to merge with Mermaid diagram")
        return {
            "status": "error",
            "message": "Unable to locate action plan for diagram enrichment",
            "reason": "missing_action_plan",
        }

    workflow_with_diagram = copy.deepcopy(stored_plan)
    try:
        workflow_with_diagram["mermaid_flow"] = diagram_text
        workflow_with_diagram["mermaid_diagram_source"] = diagram_source
    except Exception as ctx_err:
        wf_logger.debug("Failed to augment workflow with diagram: %s", ctx_err)
        workflow_with_diagram = copy.deepcopy(stored_plan)
        workflow_with_diagram["mermaid_flow"] = diagram_text
        workflow_with_diagram["mermaid_diagram_source"] = diagram_source

    display_message = agent_message or _coerce_str(diagram_payload.get("agent_message"))
    if not display_message:
        display_message = "Review the action plan with its sequence diagram and confirm before we continue."

    agent_message_id = f"msd_{uuid.uuid4().hex[:10]}"

    diagram_metadata: Dict[str, Any] = {
        "workflow_name": payload_workflow_name,
        "diagram": diagram_text,
        "source": diagram_source,
        "agent_name": resolved_agent_name,
    }
    if legend:
        diagram_metadata["legend"] = legend
    if display_message:
        diagram_metadata["agent_message"] = display_message

    try:
        if context_variables and hasattr(context_variables, "set"):
            try:
                context_variables.set("mermaid_sequence_diagram", diagram_text)  # type: ignore[attr-defined]
                context_variables.set("mermaid_diagram_ready", True)  # type: ignore[attr-defined]
                context_variables.set("action_plan", workflow_with_diagram)  # type: ignore[attr-defined]
                context_variables.set("mermaid_diagram_metadata", diagram_metadata)  # type: ignore[attr-defined]
            except Exception as ctx_err:
                wf_logger.debug("Failed to persist mermaid diagram context: %s", ctx_err)

        wf_logger.info("Rendering ActionPlan artifact with merged diagram via use_ui_tool", extra={"workflow": payload_workflow_name})

        # Build complete UI payload for ActionPlan artifact
        ui_payload: Dict[str, Any] = {
            "workflow": workflow_with_diagram,
            "agent_message": display_message,
            "workflow_name": payload_workflow_name,
            "agent_message_id": agent_message_id,
            "diagram": diagram_text,
            "mermaid_diagram": diagram_text,
            "diagram_ready": True,
            "diagram_source": diagram_source,
        }
        # Include agent_name for proper frontend attribution
        ui_payload["agent_name"] = resolved_agent_name
        ui_payload["agentName"] = resolved_agent_name
        ui_payload["agent"] = resolved_agent_name
        wf_logger.info(
            "✅ [MERMAID] Added agent_name to ui_payload (%s): %s",
            agent_name_source,
            resolved_agent_name,
        )
        if legend:
            ui_payload["legend"] = legend
        ui_payload["mermaid"] = diagram_metadata

        try:
            response = await use_ui_tool(
                tool_id="ActionPlan",
                payload=ui_payload,
                chat_id=chat_id,
                workflow_name=payload_workflow_name,
                display="artifact",
            )

            wf_logger.info("ActionPlan artifact with diagram displayed; awaiting user decision")

            plan_acceptance = bool(response.get("plan_acceptance"))
            action_name = str(response.get("action", ""))
            acceptance_state = "accepted" if plan_acceptance or action_name == "accept_workflow" else "pending"

            if action_name in {"request_changes", "request_revision", "revise_workflow"}:
                acceptance_state = "adjustments_requested"

            if context_variables and hasattr(context_variables, "set"):
                try:
                    context_variables.set("action_plan_acceptance", acceptance_state)  # type: ignore[attr-defined]
                    context_variables.set("action_plan_ui_response", response)  # type: ignore[attr-defined]
                except Exception as ctx_err:
                    wf_logger.debug("Failed to persist action plan acceptance state: %s", ctx_err)
            lifecycle_triggered = False
            if acceptance_state == "accepted" and context_variables and hasattr(context_variables, "get"):
                try:
                    already_complete = bool(context_variables.get("api_keys_collection_complete"))
                except Exception:
                    already_complete = False
                if not already_complete:
                    try:
                        from core.workflow.execution.lifecycle import get_lifecycle_manager

                        lifecycle_workflow_name = None
                        try:
                            lifecycle_workflow_name = context_variables.get("workflow_name")  # type: ignore[attr-defined]
                        except Exception:
                            lifecycle_workflow_name = None
                        lifecycle_manager = get_lifecycle_manager(lifecycle_workflow_name or "Generator")
                        await lifecycle_manager.trigger_before_agent(
                            agent_name="ContextVariablesAgent",
                            context_variables=context_variables,
                        )
                        lifecycle_triggered = True
                        wf_logger.info(
                            "[MERMAID] Triggered before_agent lifecycle for ContextVariablesAgent after plan acceptance",
                            extra={"workflow": payload_workflow_name, "chat_id": chat_id},
                        )
                    except Exception as lc_err:  # pragma: no cover - defensive logging
                        wf_logger.warning(
                            "[MERMAID] Failed to trigger ContextVariablesAgent lifecycle after acceptance: %s",
                            lc_err,
                        )

            return {
                "status": response.get("status", "success"),
                "plan_acceptance": plan_acceptance,
                "acceptance_state": acceptance_state,
                "ui_response": response,
                "workflow_name": payload_workflow_name,
                "action_plan": workflow_with_diagram,
                "diagram": diagram_text,
                "mermaid_diagram": diagram_text,
                "legend": legend,
                "agent_message": display_message,
                "agent_message_id": agent_message_id,
                "diagram_ready": True,
                "diagram_source": diagram_source,
                "lifecycle_triggered": lifecycle_triggered,
            }
        except UIToolError as exc:
            wf_logger.error("ActionPlan UI interaction failed during diagram merge: %s", exc)
            return {
                "status": "error",
                "message": str(exc),
                "workflow_name": payload_workflow_name,
                "agent_message_id": agent_message_id,
                "diagram_source": diagram_source,
            }
    except Exception as exc:  # pragma: no cover - defensive logging
        wf_logger.exception("Unexpected failure in MermaidSequenceDiagram tool: %s", exc)
        return {
            "status": "error",
            "message": "Unexpected error in MermaidSequenceDiagram tool",
            "workflow_name": payload_workflow_name,
            "agent_message_id": agent_message_id,
            "diagram_source": diagram_source if "diagram_source" in locals() else "unknown",
        }

