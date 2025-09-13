# ==============================================================================
# FILE: workflows/Generator/tools/action_plan.py
# DESCRIPTION: UI tool for presenting a ContextAgent-produced Action Plan
# CONTRACT:
#   - INPUT: action_plan (matches ActionPlan schema) from ContextAgent
#   - OUTPUT: emits the "ActionPlan" UI artifact, waits for user response,
#             and returns the response along with the (normalized) action_plan
# ==============================================================================

from typing import Any, Dict, List, Optional, Annotated  # Dict retained for internal helper signatures; runtime annotations use built-ins
import uuid
import re
import logging

from logs.logging_config import get_workflow_logger
from core.workflow.ui_tools import use_ui_tool, UIToolError


# ---------------------------
# Schema helpers (lightweight)
# ---------------------------

def _coerce_str(v: Any, default: str = "") -> str:
    return v if isinstance(v, str) else default

def _coerce_feature_list(v: Any) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    if isinstance(v, list):
        for item in v:
            if isinstance(item, dict):
                title = _coerce_str(item.get("feature_title"))
                desc = _coerce_str(item.get("description"))
                if title or desc:
                    out.append({"feature_title": title, "description": desc})
    return out

def _coerce_integration_list(v: Any) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    if isinstance(v, list):
        for item in v:
            if isinstance(item, dict):
                title = _coerce_str(item.get("technology_title"))
                desc = _coerce_str(item.get("description"))
                if title or desc:
                    out.append({"technology_title": title, "description": desc})
    return out

def _coerce_str_list(v: Any) -> List[str]:
    out: List[str] = []
    if isinstance(v, list):
        for item in v:
            if isinstance(item, str):
                s = item.strip()
                if s:
                    out.append(s)
    return out

# --- Enforce Mermaid sequenceDiagram style (linear) ---

def _linear_sequence_from_steps(steps: List[str]) -> str:
    actors = [s for s in steps if s][:4]  # up to 4 lifelines from feature titles
    if len(actors) < 2:
        actors = ["User", "System"]
    # Ensure unique simple Actor names
    norm = []
    seen = set()
    for a in actors:
        base = re.sub(r"[^A-Za-z0-9]", "", a) or "Actor"
        base = base[:16]
        if base in seen:
            i = 2
            while f"{base}{i}" in seen:
                i += 1
            base = f"{base}{i}"
        seen.add(base)
        norm.append(base)
    actors = norm
    lines = ["sequenceDiagram"]
    # Minimal ping-pong messages
    for i in range(len(actors) - 1):
        lines.append(f"  {actors[i]}->>{actors[i+1]}: step {i+1}")
    lines.append(f"  {actors[-1]}-->>{actors[0]}: result")
    return "\n".join(lines)

def _ensure_sequence_diagram(mermaid_flow: str, fallback_steps: List[str]) -> str:
    m = (mermaid_flow or "").strip()
    if not m:
        return _linear_sequence_from_steps(fallback_steps or ["User", "System", "Result"])
    # If already sequenceDiagram keep only allowed simple lines
    if re.match(r'^\s*sequenceDiagram', m, flags=re.IGNORECASE):
        # Remove disallowed constructs (alt/opt/loop) for simplicity
        cleaned = []
        for line in m.splitlines():
            if re.search(r'\b(alt|opt|loop|par|rect|critical)\b', line, flags=re.IGNORECASE):
                continue
            cleaned.append(line)
        return "\n".join(cleaned)
    # Convert simple flowchart LR into sequenceDiagram heuristic
    if re.search(r'^\s*flowchart\s+', m, flags=re.IGNORECASE):
        # Extract node labels in order
        labels = re.findall(r'\b([A-Za-z0-9_]+)\[[^\]]+\]', m)
        return _linear_sequence_from_steps(labels or fallback_steps)
    # Fallback: synthesize
    return _linear_sequence_from_steps(fallback_steps)

def _normalize_action_plan(ap: Dict[str, Any]) -> Dict[str, Any]:
    """
    Return a normalized dict conforming to ActionPlan schema.
    (We do not invent content; only coerce types and provide safe fallbacks.)
    """
    workflow_title = _coerce_str(ap.get("workflow_title"), "Proposed Workflow")
    workflow_description = _coerce_str(
        ap.get("workflow_description"),
        "High-level automation summarized for review."
    )
    suggested_features = _coerce_feature_list(ap.get("suggested_features"))
    third_party_integrations = _coerce_integration_list(ap.get("third_party_integrations"))
    constraints = _coerce_str_list(ap.get("constraints"))

    # Prefer author-provided mermaid but enforce sequenceDiagram linear style
    mermaid_flow = _ensure_sequence_diagram(
        _coerce_str(ap.get("mermaid_flow")),
        [f.get("feature_title", "") for f in suggested_features]
    )

    return {
        "workflow_title": workflow_title,
        "workflow_description": workflow_description,
        "suggested_features": suggested_features,
        "mermaid_flow": mermaid_flow,
        "third_party_integrations": third_party_integrations,
        "constraints": constraints,
    }


# ---------------------------
# Public tool entrypoint
# ---------------------------

async def action_plan(
    *,
    action_plan: Annotated[Optional[dict[str, Any]], "Action Plan object with workflow details. Must include keys: workflow_title, workflow_description, suggested_features (list of {feature_title, description}), mermaid_flow (sequenceDiagram), third_party_integrations (list of {technology_title, description}), constraints (list[str])."] = None,
    agent_message: Annotated[Optional[str], "Mandatory short sentence displayed in teh chat along with the artifact for context."] = None,
    # AG2-native context injection
    context_variables: Annotated[Optional[Any], "Context variables provided by AG2"] = None,
) -> dict[str, Any]:
    """
    PURPOSE:
        Present an Action Plan to the user via the ActionPlan UI artifact and await user response.

    PARAMETERS:
        action_plan (Annotated[dict[str, Any], ...], required):
            The Action Plan object. Expected keys:
              - workflow_title: str
              - workflow_description: str
              - suggested_features: list[{ feature_title: str, description: str }]
              - mermaid_flow: str (must start with 'sequenceDiagram')
              - third_party_integrations: list[{ technology_title: str, description: str }]
              - constraints: list[str]
        agent_message (Annotated[Optional[str], ...], optional):
            Short sentence shown above the artifact (context for the user).
        runtime (**kwargs):
            Provided by framework: chat_id, enterprise_id, workflow_name, context_variables.

    RETURNS:
        dict: {
          "status": "success" | "error",
          "ui_response": dict | null,
          "ui_event_id": str | null,
          "agent_message_id": str,
          "action_plan": dict,            # normalized action plan
          "workflow_name": str
        }

    ERROR MODES:
        - {"status":"error","message":"Invalid action_plan payload (expected object)"}
        - {"status":"error","message":"chat_id and enterprise_id are required"}

    SIDE EFFECTS:
        Emits a UI tool event (artifact) and waits for a single user response.
    """
    # Extract parameters from AG2 ContextVariables
    chat_id: Optional[str] = None
    enterprise_id: Optional[str] = None
    workflow_name: Optional[str] = None
    # Lightweight tool-local logger to verify tool invocation even when workflow-level
    # logger (get_workflow_logger) may not be initialised due to missing context.
    _tlog = logging.getLogger("tools.action_plan")
    try:
        _tlog.info(
            f"action_plan invoked: action_plan_type={type(action_plan).__name__} "
            f"agent_message_present={bool(agent_message)} context_variables_present={context_variables is not None}"
        )
        if isinstance(action_plan, dict):
            # Avoid logging large payloads; only keys
            _tlog.debug(f"action_plan keys: {list(action_plan.keys())}")
        else:
            _tlog.debug("action_plan not a dict or is None")
    except Exception:
        try:
            _tlog.exception("Failed to write initial action_plan logs")
        except Exception:
            pass
    
    if context_variables and hasattr(context_variables, 'get'):
        chat_id = context_variables.get('chat_id')
        enterprise_id = context_variables.get('enterprise_id')
        workflow_name = context_variables.get('workflow_name')

    if not chat_id or not enterprise_id:
        # We need chat_id + enterprise_id to route the UI event back properly.
        _tlog.warning("Missing routing keys: chat_id or enterprise_id not present on context_variables")
        return {"status": "error", "message": "chat_id and enterprise_id are required"}

    wf_name = workflow_name or "Generated_Workflow"
    wf_logger = get_workflow_logger(workflow_name=wf_name, chat_id=chat_id, enterprise_id=enterprise_id)
    # Lazy import tool logger to avoid static analysis issues if module path shifts
    try:
        from logs.tools_logs import get_tool_logger as _get_tool_logger, log_tool_event as _log_tool_event  # type: ignore
        tlog = _get_tool_logger(tool_name="ActionPlan", chat_id=chat_id, enterprise_id=enterprise_id, workflow_name=wf_name)
        _log_tool_event(tlog, action="start", status="ok")
    except Exception:
        tlog = None

    # Normalize/validate the provided Action Plan (do NOT invent new logic)
    if not isinstance(action_plan, dict):
        _tlog.warning("Invalid action_plan payload - not a dict")
        return {"status": "error", "message": "Invalid action_plan payload (expected object)"}

    ap_norm = _normalize_action_plan(action_plan)
    _tlog.info("action_plan normalized and ready to emit UI artifact")

    # Compose UI payload
    agent_message_id = f"ap_{uuid.uuid4().hex[:10]}"
    ui_payload = {
        **ap_norm,
        # Agent message for display in chat
        "agent_message": agent_message or "Please review this proposed Action Plan.",
        # Optional contextual line for the UI component to show above the artifact
        "description": agent_message or "Please review this proposed Action Plan.",
        "agent_message_id": agent_message_id,
        "workflow_name": wf_name,
    }

    # Emit UI artifact and wait for a response
    try:
        _tlog.info("Emitting ActionPlan UI artifact via use_ui_tool()")
        if tlog:
            from logs.tools_logs import log_tool_event as _log_tool_event  # type: ignore
            _log_tool_event(tlog, action="emit_ui", status="start", display="artifact", agent_message_id=agent_message_id)
        resp = await use_ui_tool(
            tool_id="ActionPlan",
            payload=ui_payload,
            chat_id=chat_id,
            workflow_name=wf_name,
            display="artifact",
        )
        _tlog.info("use_ui_tool() returned")
        # The UI layer adds 'ui_event_id' to its response in ui_tools.py
        ui_event_id = resp.get("ui_event_id") if isinstance(resp, dict) else None
        wf_logger.info("🧭 ActionPlan UI completed")
        if tlog:
            from logs.tools_logs import log_tool_event as _log_tool_event  # type: ignore
            _log_tool_event(tlog, action="emit_ui", status="done", ui_event_id=ui_event_id, result_status=resp.get("status", "unknown"))
        return {
            "status": "success",
            "ui_response": resp,
            "ui_event_id": ui_event_id,
            "agent_message_id": agent_message_id,
            "action_plan": ap_norm,
            "workflow_name": wf_name,
        }
    except UIToolError as e:
        wf_logger.error(f"❌ ActionPlan UI interaction failed: {e}")
        if tlog:
            try:
                from logs.tools_logs import log_tool_event as _log_tool_event  # type: ignore
                _log_tool_event(tlog, action="emit_ui", status="error", error=str(e))
            except Exception:
                pass
        return {"status": "error", "message": str(e), "agent_message_id": agent_message_id}
