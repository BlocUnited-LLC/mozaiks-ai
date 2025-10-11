# ==============================================================================
# FILE: workflows/Generator/tools/action_plan.py
# DESCRIPTION: UI tool for presenting an ActionPlanArchitect-produced Action Plan
# CONTRACT:
#   - INPUT: action_plan (matches ActionPlan schema) from ActionPlanArchitect
#   - OUTPUT: emits the "ActionPlan" UI artifact, waits for user response,
#             and returns the response along with the (normalized) action_plan
# ==============================================================================

from typing import Any, Dict, List, Optional, Annotated
import uuid
import re
import json
import logging
import copy

from logs.logging_config import get_workflow_logger
from core.workflow.ui_tools import UIToolError, use_ui_tool


MAX_IDENTIFIER_LENGTH = 32
_logger = logging.getLogger("tools.action_plan")


# ---------------------------
# Schema helpers (lightweight)
# ---------------------------

def _coerce_str(value: Any, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "y", "1"}:
            return True
        if lowered in {"false", "no", "n", "0"}:
            return False
    return default


def _coerce_list_of_str(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    result: List[str] = []
    for item in value:
        if isinstance(item, str):
            trimmed = item.strip()
            if trimmed:
                result.append(trimmed)
    return result


def _clean_label(label: str) -> str:
    cleaned = label.strip()
    if not cleaned:
        return ""
    cleaned = cleaned.replace("[", "(").replace("]", ")")
    cleaned = cleaned.replace("{", "(").replace("}", ")")
    cleaned = cleaned.replace("<", "(").replace(">", ")")
    cleaned = cleaned.replace("|", "/")
    return cleaned


def _make_identifier(label: str, prefix: str, index: int, seen: set[str]) -> str:
    base = re.sub(r"[^A-Za-z0-9]", "", label) or f"{prefix}{index}"
    base = base[:MAX_IDENTIFIER_LENGTH]
    candidate = base
    suffix = 2
    while candidate in seen:
        candidate = f"{base}{suffix}"
        suffix += 1
    seen.add(candidate)
    return candidate


def _extract_agent_name(container: Any) -> Optional[str]:
    if not container or not hasattr(container, "get"):
        return None

    candidate_keys = (
        "agent_name",
        "agentName",
        "turn_agent_name",
        "turn_agent",
        "auto_tool_agent_name",
        "auto_tool_agent",
        "last_agent_name",
        "speaker",
        "sender",
    )

    for key in candidate_keys:
        try:
            value = container.get(key)
        except Exception:  # pragma: no cover - defensive access
            continue
        normalized = _coerce_str(value)
        if normalized:
            return normalized
    return None


def _normalize_agents(value: Any, phase_index: int) -> List[Dict[str, Any]]:
    agents: List[Dict[str, Any]] = []
    if not isinstance(value, list):
        return agents
    for idx, raw_agent in enumerate(value):
        if not isinstance(raw_agent, dict):
            continue
        name = _coerce_str(raw_agent.get("name"), f"Agent {phase_index + 1}-{idx + 1}").strip()
        description = _coerce_str(raw_agent.get("description"))
        
        # Handle human_interaction field with validation
        human_interaction = _coerce_str(raw_agent.get("human_interaction"), "none").lower()
        if human_interaction not in ("none", "context", "approval"):
            human_interaction = "none"
        
        integrations = _coerce_list_of_str(raw_agent.get("integrations"))
        operations = _coerce_list_of_str(raw_agent.get("operations"))
        agents.append({
            "name": name,
            "description": description,
            "human_interaction": human_interaction,
            "integrations": integrations,
            "operations": operations,
        })
    return agents


def _normalize_phases(value: Any) -> List[Dict[str, Any]]:
    phases: List[Dict[str, Any]] = []
    if not isinstance(value, list):
        return phases
    for idx, raw_phase in enumerate(value):
        if not isinstance(raw_phase, dict):
            continue
        name = _coerce_str(raw_phase.get("name"), f"Phase {idx + 1}").strip()
        description = _coerce_str(raw_phase.get("description"))
        agents = _normalize_agents(raw_phase.get("agents"), idx)
        phases.append({
            "name": name,
            "description": description,
            "agents": agents,
        })
    return phases


def _agent_tool_labels(agent: Dict[str, Any]) -> List[str]:
    labels: List[str] = []
    integrations = agent.get("integrations", [])
    operations = agent.get("operations", [])

    if isinstance(integrations, list):
        for tool_name in integrations:
            if isinstance(tool_name, str):
                trimmed = tool_name.strip()
                if trimmed:
                    labels.append(trimmed)

    if isinstance(operations, list):
        for op_name in operations:
            if isinstance(op_name, str):
                trimmed = op_name.strip()
                if trimmed:
                    labels.append(trimmed)

    return labels


def _ensure_flowchart(mermaid_value: Any, phases: List[Dict[str, Any]], workflow_name: str) -> str:
    raw = _coerce_str(mermaid_value).strip()
    if raw:
        lines = raw.splitlines()
        if lines:
            header = lines[0].strip().lower()
            if header.startswith("flowchart"):
                lines[0] = "flowchart LR"
                return "\n".join(lines)
    lines: List[str] = ["flowchart LR"]
    seen: set[str] = set()
    previous_phase_id: Optional[str] = None
    for phase_index, phase in enumerate(phases):
        phase_label = _clean_label(phase.get("name") or f"Phase {phase_index + 1}") or f"Phase {phase_index + 1}"
        phase_id = _make_identifier(phase_label, "Phase", phase_index + 1, seen)
        lines.append(f"    {phase_id}[{phase_label}]")
        if previous_phase_id:
            lines.append(f"    {previous_phase_id} --> {phase_id}")
        previous_phase_id = phase_id
        for agent_index, agent in enumerate(phase.get("agents", [])):
            agent_label = _clean_label(agent.get("name") or f"Agent {phase_index + 1}-{agent_index + 1}") or f"Agent {phase_index + 1}-{agent_index + 1}"
            agent_id = _make_identifier(agent_label, f"Agent{phase_index + 1}", agent_index + 1, seen)
            lines.append(f"    {phase_id} --> {agent_id}" + "{" + agent_label + "}")
            tool_labels = _agent_tool_labels(agent)
            for tool_index, tool_label_raw in enumerate(tool_labels):
                tool_label = _clean_label(tool_label_raw or f"Tool {tool_index + 1}") or f"Tool {tool_index + 1}"
                tool_id = _make_identifier(tool_label, f"Tool{phase_index + 1}{agent_index + 1}", tool_index + 1, seen)
                lines.append(f"    {agent_id} --> {tool_id}[" + tool_label + "]")
    if len(lines) == 1:
        title = _clean_label(workflow_name) or "Workflow"
        lines.append(f"    start([{title}])")
        lines.append("    start --> review((Review))")
    return "\n".join(lines)


def _normalize_workflow(raw_workflow: Dict[str, Any]) -> Dict[str, Any]:
    workflow_name = _coerce_str(raw_workflow.get("name"), "Generated Workflow").strip()
    initiated_by = _coerce_str(raw_workflow.get("initiated_by"), "user").strip()
    trigger_type = _coerce_str(raw_workflow.get("trigger_type"), "chat_start").strip()
    interaction_mode = _coerce_str(raw_workflow.get("interaction_mode"), "conversational").strip()
    model = _coerce_str(raw_workflow.get("model"), "gpt-4o-mini").strip()
    description = _coerce_str(raw_workflow.get("description"))
    phases = _normalize_phases(raw_workflow.get("phases"))
    return {
        "name": workflow_name,
        "initiated_by": initiated_by,
        "trigger_type": trigger_type,
        "interaction_mode": interaction_mode,
        "model": model,
        "description": description,
        "phases": phases,
    }


def _normalize_action_plan(ap: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize Action Plan payloads to ensure the output structure:
    { "workflow": {...} }

    Handles multiple cases:
    - Proper ActionPlan dict { "workflow": {...} }
    - Bare workflow dict {...}
    - Wrapped under "ActionPlan"
    """
    raw_workflow: Dict[str, Any] = {}

    if isinstance(ap, dict):
        if "workflow" in ap and isinstance(ap["workflow"], dict):
            raw_workflow = ap["workflow"]
        elif "ActionPlan" in ap and isinstance(ap["ActionPlan"], dict):
            raw_workflow = ap["ActionPlan"].get("workflow", {})
        elif all(k in ap for k in ("name", "description", "phases")) and any(k in ap for k in ("initiated_by", "trigger_type", "trigger")):
            raw_workflow = ap

    if not isinstance(raw_workflow, dict):
        _logger.warning("No valid workflow detected; using empty workflow object")
        raw_workflow = {}

    workflow = _normalize_workflow(raw_workflow)
    result: Dict[str, Any] = {"workflow": workflow}
    legacy_mermaid = raw_workflow.get("mermaid_flow")
    if isinstance(legacy_mermaid, str) and legacy_mermaid.strip():
        result["legacy_mermaid_flow"] = legacy_mermaid.strip()
    return result


# ---------------------------
# Public tool entrypoint (canonical: ActionPlan + agent_message)
# ---------------------------

async def action_plan(
    *,
    ActionPlan: Annotated[Optional[dict[str, Any]], "Action Plan object with workflow details. Expected keys: { 'workflow': { name, trigger, description, phases[...] } }"] = None,
    MermaidSequenceDiagram: Annotated[
        Optional[Dict[str, Any]],
        "Optional Mermaid sequence diagram payload merged into the Action Plan before display.",
    ] = None,
    agent_message: Annotated[Optional[str], "Short sentence displayed with the artifact for context."] = None,
    # AG2-native context injection
    context_variables: Annotated[Optional[Any], "Context variables provided by AG2"] = None,
) -> dict[str, Any]:
    """Render the Action Plan artifact with optional Mermaid sequence diagram and await approval.

    Summary:
        Normalize the ActionPlan payload, merge any provided Mermaid diagram (either via
        explicit MermaidSequenceDiagram argument or context cache), emit the ActionPlan UI
        artifact, and persist the user's acceptance decision to context variables.

    Payload Contract:
        field | type | description
        ------|------|------------
        ActionPlan | dict | Canonical Action Plan wrapper containing the workflow object.
        MermaidSequenceDiagram | dict | Optional Mermaid payload with keys: workflow_name, diagram, legend, notes, agent_message.
        agent_message | str | Optional short prompt shown alongside the artifact.

    Parameters:
        ActionPlan (dict, required):
            Canonical shape:
                {
                    "workflow": {
                        "name": str,
                        "initiated_by": "user"|"system"|"external_event",
                        "trigger_type": "form_submit"|"chat_start"|"cron_schedule"|"webhook"|"database_condition",
                        "interaction_mode": "autonomous"|"checkpoint_approval"|"conversational",
                        "model": str,
                        "description": str,
                        "phases": [
                            {
                                "name": str,
                                "description": str,
                                "agents": [
                                    {
                                        "name": str,
                                        "description": str,
                                        "human_interaction": "none"|"context"|"approval",
                                        "integrations": [str],
                                        "operations": [str]
                                    }
                                ]
                            }
                        ]
                    }
                }

            Notes:
                - Semantic model uses three orthogonal dimensions: initiated_by, trigger_type, interaction_mode
                - "integrations" contains third-party APIs/services (PascalCase)
                - "operations" contains internal workflow logic (snake_case)
                - "human_interaction" is agent-level field: none=automated, context=info gathering, approval=decision gate
                - UI presentation derives display labels from structured lists

            Tolerated variants (auto-normalized):
                - {"action_plan": {"workflow": {...}}}
                - {"ActionPlan": {"workflow": {...}}}
                - {"workflow": {...}} (bare workflow)

        MermaidSequenceDiagram (dict, optional):
            {
                "workflow_name": str,
                "diagram": str (starts with 'sequenceDiagram'),
                "legend": list[str],
                "notes": str,
                "agent_message": str,
            }

        agent_message (str, optional):
            One-line message displayed in the chat next to the artifact. Defaults to a
            combined review prompt when omitted.
    """

    chat_id = enterprise_id = workflow_name = agent_name = None
    stored_plan: Dict[str, Any] = {}
    stored_diagram: Optional[str] = None
    stored_diagram_ready = False
    stored_diagram_meta: Dict[str, Any] = {}

    if context_variables and hasattr(context_variables, "get"):
        try:
            chat_id = context_variables.get("chat_id")
            enterprise_id = context_variables.get("enterprise_id")
            workflow_name = context_variables.get("workflow_name")
            agent_name = _extract_agent_name(context_variables)

            raw_plan = context_variables.get("action_plan")
            if isinstance(raw_plan, dict):
                stored_plan = raw_plan

            stored_diagram = context_variables.get("mermaid_sequence_diagram")
            stored_diagram_ready = bool(context_variables.get("mermaid_diagram_ready"))

            meta_candidate = context_variables.get("mermaid_diagram_metadata")
            if isinstance(meta_candidate, dict):
                stored_diagram_meta = meta_candidate
        except Exception as ctx_err:  # pragma: no cover - defensive logging
            _logger.debug("Unable to read planning context: %s", ctx_err)

    if not chat_id or not enterprise_id:
        _logger.warning("Missing routing keys: chat_id or enterprise_id not present on context_variables")
        return {"status": "error", "message": "chat_id and enterprise_id are required"}

    # --- Action Plan normalization -------------------------------------------------
    plan_input: Any = ActionPlan
    if plan_input is None and stored_plan:
        plan_input = stored_plan

    if isinstance(plan_input, str):
        try:
            decoded = json.loads(plan_input.strip())
            if isinstance(decoded, dict):
                plan_input = decoded
                _logger.info("Decoded string ActionPlan payload into dict")
        except json.JSONDecodeError:
            _logger.warning("Failed to decode string ActionPlan payload; will proceed with placeholder")

    plan_payload: Dict[str, Any] = copy.deepcopy(plan_input) if isinstance(plan_input, dict) else {}

    if "ActionPlan" in plan_payload and isinstance(plan_payload["ActionPlan"], dict):
        plan_payload = plan_payload["ActionPlan"]
    elif "action_plan" in plan_payload and isinstance(plan_payload["action_plan"], dict):
        plan_payload = plan_payload["action_plan"]

    plan_agent_message = _coerce_str(plan_payload.get("agent_message"))

    ap_norm = _normalize_action_plan(plan_payload)
    plan_workflow = copy.deepcopy(ap_norm.get("workflow", {}) or {})
    legacy_mermaid_flow = _coerce_str(ap_norm.get("legacy_mermaid_flow"))

    # --- Mermaid diagram handling --------------------------------------------------
    diagram_payload_raw: Any = MermaidSequenceDiagram
    if diagram_payload_raw is None and stored_diagram_ready:
        diagram_payload_raw = {
            "diagram": stored_diagram,
            **stored_diagram_meta,
        }

    if isinstance(diagram_payload_raw, str):
        try:
            decoded = json.loads(diagram_payload_raw.strip())
            if isinstance(decoded, dict):
                diagram_payload_raw = decoded
                _logger.info("Decoded MermaidSequenceDiagram string payload into dict")
        except json.JSONDecodeError:
            _logger.warning("Failed to decode MermaidSequenceDiagram string payload")

    diagram_payload: Dict[str, Any] = copy.deepcopy(diagram_payload_raw) if isinstance(diagram_payload_raw, dict) else {}
    diagram_text = _coerce_str(diagram_payload.get("diagram")).strip()

    if not diagram_text and isinstance(stored_diagram, str):
        diagram_text = stored_diagram.strip()

    legend_items = _coerce_list_of_str(diagram_payload.get("legend"))
    if not legend_items:
        legend_items = _coerce_list_of_str(stored_diagram_meta.get("legend"))

    notes_text = _coerce_str(diagram_payload.get("notes")) or _coerce_str(stored_diagram_meta.get("notes"))
    diagram_agent_message = _coerce_str(diagram_payload.get("agent_message")) or _coerce_str(stored_diagram_meta.get("agent_message"))
    diagram_workflow_name = _coerce_str(diagram_payload.get("workflow_name")) or _coerce_str(stored_diagram_meta.get("workflow_name"))

    diagram_ready = bool(diagram_text)
    if diagram_ready:
        plan_workflow["mermaid_flow"] = diagram_text
    elif legacy_mermaid_flow and not plan_workflow.get("mermaid_flow"):
        plan_workflow["mermaid_flow"] = legacy_mermaid_flow

    if legacy_mermaid_flow:
        ap_norm["legacy_mermaid_flow"] = legacy_mermaid_flow

    # Determine workflow name preference order: diagram payload > plan > context > fallback
    wf_name = diagram_workflow_name or _coerce_str(plan_workflow.get("name")) or _coerce_str(workflow_name) or "Generated_Workflow"
    plan_workflow["name"] = wf_name
    ap_norm["workflow"] = plan_workflow

    wf_logger = get_workflow_logger(workflow_name=wf_name, chat_id=chat_id, enterprise_id=enterprise_id)

    _log_tool_event = None
    try:  # Optional telemetry logger
        from logs.tools_logs import get_tool_logger as _get_tool_logger, log_tool_event as _lte  # type: ignore

        tlog = _get_tool_logger(
            tool_name="ActionPlan",
            chat_id=chat_id,
            enterprise_id=enterprise_id,
            workflow_name=wf_name,
        )
        _log_tool_event = _lte
        _log_tool_event(tlog, action="start", status="ok")
    except Exception:
        tlog = None

    final_agent_message = (
        _coerce_str(agent_message)
        or diagram_agent_message
        or plan_agent_message
        or "Review the workflow plan and confirm before we proceed."
    )

    diagram_metadata: Dict[str, Any] = {"workflow_name": wf_name}
    if legend_items:
        diagram_metadata["legend"] = legend_items
    if notes_text:
        diagram_metadata["notes"] = notes_text
    if diagram_agent_message:
        diagram_metadata["agent_message"] = diagram_agent_message

    if context_variables and hasattr(context_variables, "set"):
        try:
            context_variables.set("action_plan", copy.deepcopy(plan_workflow))  # type: ignore[attr-defined]
            context_variables.set("action_plan_acceptance", "pending")  # type: ignore[attr-defined]

            if diagram_ready:
                context_variables.set("mermaid_sequence_diagram", diagram_text)  # type: ignore[attr-defined]
                context_variables.set("mermaid_diagram_ready", True)  # type: ignore[attr-defined]
                context_variables.set("mermaid_diagram_metadata", diagram_metadata)  # type: ignore[attr-defined]
            else:
                context_variables.set("mermaid_sequence_diagram", "")  # type: ignore[attr-defined]
                context_variables.set("mermaid_diagram_ready", False)  # type: ignore[attr-defined]
                context_variables.set("mermaid_diagram_metadata", {})  # type: ignore[attr-defined]
        except Exception as ctx_err:  # pragma: no cover - defensive logging
            wf_logger.debug("Failed to persist planning context: %s", ctx_err)

    if not diagram_ready:
        wf_logger.info("Action plan normalized and cached; waiting for diagram synthesis before user review")
        if tlog and _log_tool_event:
            try:
                _log_tool_event(tlog, action="emit_ui", status="skipped", reason="diagram_pending")
            except Exception:  # pragma: no cover - telemetry best-effort
                pass
        return {
            "status": "success",
            "action_plan": ap_norm,
            "workflow_name": wf_name,
            "agent_message": final_agent_message,
            "diagram_ready": False,
            "reason": "waiting_for_diagram",
        }

    agent_message_id = f"ap_{uuid.uuid4().hex[:12]}"

    ui_payload: Dict[str, Any] = {
        "workflow": plan_workflow,
        "agent_message": final_agent_message,
        "workflow_name": wf_name,
        "agent_message_id": agent_message_id,
    }
    if legacy_mermaid_flow:
        ui_payload["legacy_mermaid_flow"] = legacy_mermaid_flow
    if diagram_text:
        ui_payload["diagram"] = diagram_text
    if legend_items:
        ui_payload["legend"] = legend_items
    if notes_text:
        ui_payload["notes"] = notes_text
    if diagram_metadata:
        ui_payload["mermaid"] = {**diagram_metadata, "diagram": diagram_text}
    if agent_name:
        ui_payload["agent_name"] = agent_name
        ui_payload["agentName"] = agent_name
        ui_payload["agent"] = agent_name

    try:
        if tlog and _log_tool_event:
            _log_tool_event(tlog, action="emit_ui", status="start", display="artifact", agent_message_id=agent_message_id)

        response = await use_ui_tool(
            tool_id="ActionPlan",
            payload=ui_payload,
            chat_id=chat_id,
            workflow_name=wf_name,
            display="artifact",
        )

        wf_logger.info("Action Plan artifact displayed; awaiting user decision", extra={"diagram": bool(diagram_text)})

        if tlog and _log_tool_event:
            _log_tool_event(
                tlog,
                action="emit_ui",
                status="done",
                result_status=response.get("status", "unknown"),
                agent_message_id=agent_message_id,
            )
    except UIToolError as exc:
        wf_logger.error("Action Plan UI interaction failure: %s", exc)
        return {
            "status": "error",
            "message": str(exc),
            "workflow_name": wf_name,
            "agent_message_id": agent_message_id,
        }
    except Exception as exc:  # pragma: no cover - defensive logging
        wf_logger.exception("Unexpected failure while rendering Action Plan UI: %s", exc)
        return {
            "status": "error",
            "message": "Unexpected error while rendering Action Plan UI",
            "workflow_name": wf_name,
            "agent_message_id": agent_message_id,
        }

    plan_acceptance = bool(response.get("plan_acceptance"))
    action_name = _coerce_str(response.get("action"))
    acceptance_state = "accepted" if plan_acceptance or action_name == "accept_workflow" else "pending"

    if action_name in {"request_changes", "request_revision", "revise_workflow"}:
        acceptance_state = "adjustments_requested"

    if context_variables and hasattr(context_variables, "set"):
        try:
            context_variables.set("action_plan_acceptance", acceptance_state)  # type: ignore[attr-defined]
            context_variables.set("action_plan_ui_response", response)  # type: ignore[attr-defined]
        except Exception as ctx_err:  # pragma: no cover - defensive logging
            wf_logger.debug("Failed to persist action plan acceptance state: %s", ctx_err)

    wf_logger.info(
        "Action Plan review completed",
        extra={
            "plan_acceptance": acceptance_state,
            "ui_status": response.get("status"),
            "action": action_name or "",
        },
    )

    return {
        "status": response.get("status", "success"),
        "plan_acceptance": plan_acceptance,
        "acceptance_state": acceptance_state,
        "ui_response": response,
        "action_plan": ap_norm,
        "workflow_name": wf_name,
        "diagram_ready": True,
        "diagram": diagram_text,
        "legend": legend_items,
        "notes": notes_text,
        "agent_message": final_agent_message,
        "agent_message_id": agent_message_id,
    }
