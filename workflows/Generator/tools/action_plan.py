# ==============================================================================
# FILE: workflows/Generator/tools/action_plan.py
# DESCRIPTION: Normalize and cache ActionPlan semantic wrapper output for Mermaid enrichment
# CONTRACT:
#   - INPUT: action_plan (matches ActionPlan schema) from upstream agent
#   - OUTPUT: stores normalized workflow + metadata in context for downstream UI tool
# ==============================================================================

from typing import Any, Dict, List, Optional, Annotated
import uuid
import re
import json
import logging
import copy

from logs.logging_config import get_workflow_logger


MAX_IDENTIFIER_LENGTH = 32
_logger = logging.getLogger("tools.action_plan")
PLAN_SNAPSHOT_MAX_CHARS = 8000
_LIFECYCLE_TRIGGERS = {"before_chat", "after_chat", "before_agent", "after_agent"}
_TRIGGER_ALIAS_MAP = {
    "chat": "chat_start",
    "chat_start": "chat_start",
    "conversation": "chat_start",
    "form": "form_submit",
    "form_submit": "form_submit",
    "schedule": "cron_schedule",
    "cron": "cron_schedule",
    "cron_schedule": "cron_schedule",
    "database": "database_condition",
    "database_condition": "database_condition",
    "webhook": "webhook",
}


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


def _parse_database_schema_info(
    schema_overview: Optional[str],
    collections_first_docs: Optional[Dict[str, Any]],
    context_schema_db: Optional[str],
    context_include_schema: bool
) -> Dict[str, Any]:
    """Parse schema_overview text and collections_first_docs into structured database info for UI."""
    database_info: Dict[str, Any] = {
        "enabled": context_include_schema,
        "database_name": context_schema_db,
        "collections": [],
        "total_collections": 0
    }
    
    if not context_include_schema or not schema_overview:
        return database_info
    
    try:
        # Parse schema_overview text format:
        # DATABASE: MozaiksCore
        # TOTAL COLLECTIONS: 5
        # 
        # USERS [Enterprise-specific]:
        #   Fields:
        #     - user_id: str
        #     - email: str
        
        lines = schema_overview.split('\n')
        current_collection: Optional[Dict[str, Any]] = None
        
        for line in lines:
            line = line.strip()
            
            # Extract database name
            if line.startswith("DATABASE:"):
                database_info["database_name"] = line.replace("DATABASE:", "").strip()
            
            # Extract total collections
            elif line.startswith("TOTAL COLLECTIONS:"):
                try:
                    database_info["total_collections"] = int(line.replace("TOTAL COLLECTIONS:", "").strip())
                except ValueError:
                    pass
            
            # New collection header (UPPERCASE: or UPPERCASE [Enterprise-specific]:)
            elif line and ":" in line and line[0].isupper() and not line.startswith("Fields:"):
                if current_collection:
                    database_info["collections"].append(current_collection)
                
                collection_name = line.split(":")[0].strip()
                is_enterprise = "[Enterprise-specific]" in line
                collection_name = collection_name.replace("[Enterprise-specific]", "").strip()
                
                current_collection = {
                    "name": collection_name,
                    "is_enterprise": is_enterprise,
                    "fields": []
                }
            
            # Field line (  - field_name: field_type)
            elif current_collection and line.startswith("- ") and ":" in line:
                field_parts = line[2:].split(":", 1)
                if len(field_parts) == 2:
                    field_name = field_parts[0].strip()
                    field_type = field_parts[1].strip()
                    current_collection["fields"].append({
                        "name": field_name,
                        "type": field_type
                    })
        
        # Add last collection
        if current_collection:
            database_info["collections"].append(current_collection)
        
        # Enhance with sample data from collections_first_docs if available
        if collections_first_docs and isinstance(collections_first_docs, dict):
            for collection in database_info["collections"]:
                collection_name = collection["name"]
                if collection_name in collections_first_docs:
                    sample_doc = collections_first_docs[collection_name]
                    if sample_doc:
                        collection["has_sample_data"] = True
                        collection["sample_doc_keys"] = list(sample_doc.keys())[:10]  # Limit to 10 keys
    
    except Exception as e:
        _logger.debug(f"Failed to parse database schema info: {e}")
    
    return database_info


def _sanitize_optional_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        trimmed = value.strip()
        if not trimmed:
            return None
        lowered = trimmed.lower()
        if lowered in {"null", "none"}:
            return None
        return trimmed
    return str(value)


def _dedupe_preserve_order(items: List[str]) -> List[str]:
    seen: set[str] = set()
    ordered: List[str] = []
    for item in items:
        if not item:
            continue
        if item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def _normalize_agent_tools(value: Any) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    if not isinstance(value, list):
        return normalized

    for idx, raw in enumerate(value):
        if not isinstance(raw, dict):
            continue
        name = _coerce_str(raw.get("name"), f"Tool {idx + 1}").strip()
        if not name:
            name = f"Tool {idx + 1}"
        integration = _sanitize_optional_str(raw.get("integration"))
        purpose = _coerce_str(raw.get("purpose"))
        entry: Dict[str, Any] = {
            "name": name,
            "integration": integration,
            "purpose": purpose,
        }
        normalized.append(entry)
    return normalized


def _normalize_lifecycle_tools(value: Any) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    if not isinstance(value, list):
        return normalized

    for idx, raw in enumerate(value):
        if not isinstance(raw, dict):
            continue
        name = _coerce_str(raw.get("name"), f"Lifecycle {idx + 1}").strip()
        if not name:
            name = f"Lifecycle {idx + 1}"
        trigger = _coerce_str(raw.get("trigger"), "before_agent").strip().lower()
        if trigger not in _LIFECYCLE_TRIGGERS:
            trigger = "before_agent"
        purpose = _coerce_str(raw.get("purpose"))
        integration = _sanitize_optional_str(raw.get("integration"))
        entry: Dict[str, Any] = {
            "name": name,
            "trigger": trigger,
            "purpose": purpose,
            "integration": integration,
        }
        normalized.append(entry)
    return normalized


def _normalize_system_hooks(value: Any) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    if not isinstance(value, list):
        return normalized

    for idx, raw in enumerate(value):
        if not isinstance(raw, dict):
            continue
        name = _coerce_str(raw.get("name"), f"system_hook_{idx + 1}").strip()
        if not name:
            name = f"system_hook_{idx + 1}"
        purpose = _coerce_str(raw.get("purpose"))
        normalized.append({
            "name": name,
            "purpose": purpose,
        })
    return normalized


def _extract_blueprint(*candidates: Any) -> Optional[Dict[str, Any]]:
    """Locate a TechnicalBlueprint payload from multiple possible wrapper shapes."""

    def _unwrap(candidate: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(candidate, dict):
            return None
        wrapped = candidate.get("TechnicalBlueprint")
        if isinstance(wrapped, dict):
            return wrapped
        wrapped = candidate.get("technical_blueprint")
        if isinstance(wrapped, dict):
            return wrapped
        keys = set(candidate.keys()) if isinstance(candidate, dict) else set()
        if keys.intersection({"global_context_variables", "ui_components", "before_chat_lifecycle", "after_chat_lifecycle"}):
            return candidate  # Already the blueprint payload
        return None

    for source in candidates:
        unwrapped = _unwrap(source)
        if unwrapped:
            return unwrapped
    return None


def _normalize_global_context_variables(value: Any) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    if not isinstance(value, list):
        return normalized

    for idx, raw in enumerate(value):
        if not isinstance(raw, dict):
            continue
        name = _coerce_str(raw.get("name"), f"context_variable_{idx + 1}").strip()
        if not name:
            name = f"context_variable_{idx + 1}"
        var_type = _coerce_str(raw.get("type"), "computed").strip() or "computed"
        purpose = _coerce_str(raw.get("purpose"))
        trigger_hint = _sanitize_optional_str(raw.get("trigger_hint"))

        normalized.append(
            {
                "name": name,
                "type": var_type,
                "purpose": purpose,
                "trigger_hint": trigger_hint,
            }
        )
    return normalized


def _enrich_context_variable_definitions(value: Any) -> Dict[str, Any]:
    """Enrich context variables with full metadata for Data tab visualization.
    
    Extracts source information, triggers, and classifications for UI display.
    Returns a dict mapping variable name to enriched definition.
    """
    enriched: Dict[str, Any] = {}
    if not isinstance(value, list):
        return enriched

    for idx, raw in enumerate(value):
        if not isinstance(raw, dict):
            continue
        
        name = _coerce_str(raw.get("name"), f"context_variable_{idx + 1}").strip()
        if not name:
            name = f"context_variable_{idx + 1}"
        
        var_type = _coerce_str(raw.get("type"), "computed").strip() or "computed"
        purpose = _coerce_str(raw.get("purpose"))
        trigger_hint = _sanitize_optional_str(raw.get("trigger_hint"))
        
        # Extract source information (six-type taxonomy)
        source_info: Dict[str, Any] = {"type": var_type}
        
        # Extract trigger information for computed and state variables
        if var_type in ("computed", "state"):
            triggers = []
            if trigger_hint:
                hint_lower = trigger_hint.lower()
                if "ui" in hint_lower or "user" in hint_lower or "component" in hint_lower:
                    triggers.append({"type": "ui_response", "description": trigger_hint})
                elif "agent" in hint_lower or "says" in hint_lower or "emits" in hint_lower:
                    triggers.append({"type": "agent_text", "description": trigger_hint})
            if triggers:
                source_info["triggers"] = triggers
        
        enriched[name] = {
            "name": name,
            "type": var_type,
            "purpose": purpose,
            "trigger_hint": trigger_hint,
            "source": source_info,
        }
    
    return enriched


def _normalize_ui_components(value: Any) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    if not isinstance(value, list):
        return normalized

    for idx, raw in enumerate(value):
        if not isinstance(raw, dict):
            continue
        module_name = _coerce_str(raw.get("module_name"), f"Module {idx + 1}")
        agent = _coerce_str(raw.get("agent"), "Agent")
        tool = _coerce_str(raw.get("tool"), f"tool_{idx + 1}")
        label = _coerce_str(raw.get("label"))
        component = _coerce_str(raw.get("component"))
        display = _coerce_str(raw.get("display"), "inline")
        ui_pattern = _coerce_str(raw.get("ui_pattern"), "single_step")
        summary = _coerce_str(raw.get("summary"))

        normalized.append(
            {
                "module_name": module_name,
                "agent": agent,
                "tool": tool,
                "label": label,
                "component": component,
                "display": display,
                "ui_pattern": ui_pattern,
                "summary": summary,
            }
        )
    return normalized


def _normalize_blueprint_lifecycle(entry: Any, trigger: str) -> Optional[Dict[str, Any]]:
    if not isinstance(entry, dict):
        return None
    name = _coerce_str(entry.get("name"), f"{trigger}_hook").strip()
    if not name:
        name = f"{trigger}_hook"
    purpose = _coerce_str(entry.get("purpose"))
    integration = _sanitize_optional_str(entry.get("integration"))

    normalized: Dict[str, Any] = {
        "name": name,
        "trigger": trigger,
        "description": purpose,
    }
    if integration:
        normalized["integration"] = integration
    return normalized


def _normalize_trigger_fields(raw_workflow: Dict[str, Any]) -> tuple[str, str]:
    trigger_candidate = raw_workflow.get("trigger_type")
    if not isinstance(trigger_candidate, str) or not trigger_candidate.strip():
        trigger_candidate = raw_workflow.get("trigger")
    trigger_raw = _coerce_str(trigger_candidate).strip()
    trigger_lookup = trigger_raw.lower()
    normalized = _TRIGGER_ALIAS_MAP.get(trigger_lookup, trigger_lookup)
    if not normalized:
        normalized = "chat_start"
    if not trigger_raw:
        trigger_raw = normalized
    return trigger_raw, normalized


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


def _normalize_agents(value: Any, module_index: int) -> List[Dict[str, Any]]:
    agents: List[Dict[str, Any]] = []
    if not isinstance(value, list):
        return agents
    for idx, raw_agent in enumerate(value):
        if not isinstance(raw_agent, dict):
            continue
        base_name = raw_agent.get("agent_name") or raw_agent.get("name")
        name = _coerce_str(base_name, f"Agent {module_index + 1}-{idx + 1}").strip()
        if not name:
            name = f"Agent {module_index + 1}-{idx + 1}"
        description = _coerce_str(raw_agent.get("objective") or raw_agent.get("description"))

        human_interaction = _coerce_str(raw_agent.get("human_interaction"), "none").strip().lower()
        if human_interaction not in {"none", "context", "approval", "feedback", "single"}:
            human_interaction = "none"

        agent_tools = _normalize_agent_tools(raw_agent.get("agent_tools"))
        lifecycle_tools = _normalize_lifecycle_tools(raw_agent.get("lifecycle_tools"))
        system_hooks = _normalize_system_hooks(raw_agent.get("system_hooks"))

        integration_names = _dedupe_preserve_order(
            [
                tool["integration"]
                for tool in agent_tools
                if isinstance(tool.get("integration"), str) and tool["integration"]
            ]
        )
        if not integration_names:
            integration_names = _coerce_list_of_str(raw_agent.get("integrations"))

        tool_names: List[str] = []
        for tool in agent_tools:
            candidate = _coerce_str(tool.get("name"))
            if candidate:
                tool_names.append(candidate)
        operation_names = _dedupe_preserve_order(tool_names)
        if not operation_names:
            operation_names = _coerce_list_of_str(raw_agent.get("operations"))

        agent_payload: Dict[str, Any] = {
            "agent_name": name,
            "name": name,
            "description": description,
            "human_interaction": human_interaction,
            "agent_tools": agent_tools,
            "lifecycle_tools": lifecycle_tools,
            "system_hooks": system_hooks,
            "integrations": integration_names,
            "operations": operation_names,
        }

        agents.append(agent_payload)
    return agents


def _normalize_modules(value: Any) -> List[Dict[str, Any]]:
    modules: List[Dict[str, Any]] = []
    if not isinstance(value, list):
        return modules
    for idx, raw_module in enumerate(value):
        if not isinstance(raw_module, dict):
            continue
        module_name = _coerce_str(raw_module.get("module_name") or raw_module.get("name"), f"Module {idx + 1}").strip()
        module_description = _coerce_str(raw_module.get("module_description") or raw_module.get("description"))
        agents = _normalize_agents(raw_module.get("agents"), idx)
        module_index_raw = raw_module.get("module_index")
        try:
            module_index = int(module_index_raw)
        except (TypeError, ValueError):
            module_index = idx

        modules.append({
            "module_name": module_name,
            "module_description": module_description,
            "module_index": module_index,
            "agents": agents,
        })
    return modules


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


def _normalize_lifecycle_operations(value: Any) -> List[Dict[str, Any]]:
    """Normalize lifecycle operations emitted by WorkflowStrategy semantic wrapper or downstream merges."""
    normalized: List[Dict[str, Any]] = []
    if not isinstance(value, list):
        return normalized

    for idx, raw in enumerate(value):
        if not isinstance(raw, dict):
            continue
        name = _coerce_str(raw.get("name"), f"Lifecycle {idx + 1}").strip()
        trigger = _coerce_str(raw.get("trigger")).strip().lower()
        target = _coerce_str(raw.get("target")).strip()
        description = _coerce_str(raw.get("description")).strip()

        if trigger not in _LIFECYCLE_TRIGGERS:
            _logger.debug("Skipping lifecycle operation '%s' with invalid trigger '%s'", name, trigger)
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


def _normalize_workflow(raw_workflow: Dict[str, Any]) -> Dict[str, Any]:
    workflow_name = _coerce_str(raw_workflow.get("name"), "Generated Workflow").strip()
    initiated_by = _coerce_str(raw_workflow.get("initiated_by"), "user").strip().lower() or "user"
    trigger_raw, trigger_type = _normalize_trigger_fields(raw_workflow)

    pattern_field = raw_workflow.get("pattern")
    pattern_variants_field = raw_workflow.get("pattern_variants")
    pattern_variants: List[str] = []
    if isinstance(pattern_variants_field, list):
        pattern_variants = [entry.strip() for entry in pattern_variants_field if isinstance(entry, str) and entry.strip()]
    if isinstance(pattern_field, list):
        derived_variants = [entry.strip() for entry in pattern_field if isinstance(entry, str) and entry.strip()]
        pattern_variants = pattern_variants or derived_variants
        pattern = derived_variants[0] if derived_variants else (pattern_variants[0] if pattern_variants else "Pipeline")
    elif isinstance(pattern_field, str) and pattern_field.strip():
        pattern = pattern_field.strip()
        if not pattern_variants:
            pattern_variants = [pattern]
    elif pattern_variants:
        pattern = pattern_variants[0]
    else:
        pattern = "Pipeline"
    description = _coerce_str(raw_workflow.get("description"))
    human_in_loop = _coerce_bool(raw_workflow.get("human_in_loop"), False)
    modules = _normalize_modules(raw_workflow.get("modules"))
    lifecycle_operations = _normalize_lifecycle_operations(raw_workflow.get("lifecycle_operations"))
    workflow_payload: Dict[str, Any] = {
        "name": workflow_name,
        "initiated_by": initiated_by,
        "trigger": trigger_raw,
        "trigger_type": trigger_type,
        "pattern": pattern,
        "description": description,
        "human_in_loop": human_in_loop,
        "modules": modules,
        "lifecycle_operations": lifecycle_operations,
    }
    if pattern_variants:
        workflow_payload["pattern_variants"] = pattern_variants
    return workflow_payload


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
        elif all(k in ap for k in ("name", "description", "modules")) and any(k in ap for k in ("initiated_by", "trigger_type", "trigger")):
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


def _serialize_plan_snapshot(workflow: Dict[str, Any]) -> str:
    """Serialize a trimmed snapshot of the workflow for debugging/context storage."""
    try:
        snapshot = json.dumps(workflow, default=str)
    except Exception:
        snapshot = str(workflow)
    if len(snapshot) > PLAN_SNAPSHOT_MAX_CHARS:
        snapshot = snapshot[:PLAN_SNAPSHOT_MAX_CHARS] + "..."
    return snapshot



# ---------------------------
# Public tool entrypoint (canonical: ActionPlan + agent_message)
# ---------------------------

async def action_plan(
    *,
    ActionPlan: Annotated[
        Optional[dict[str, Any]],
        "Array of modules and agents; will be constructed from workflow_strategy + module_agents when provided."
    ] = None,
    module_agents: Annotated[
        Optional[List[Dict[str, Any]]],
        (
            "Array of {module_index, agents[]} objects from ModuleAgents semantic wrapper. "
            "Will be merged with workflow_strategy from context to build complete ActionPlan. "
            "Each entry must have module_index (int) and agents (list of WorkflowAgent specs)."
        ),
    ] = None,
    MermaidSequenceDiagram: Annotated[
        Optional[Dict[str, Any]],
        "Optional Mermaid sequence diagram payload merged into the Action Plan before display.",
    ] = None,
    agent_message: Annotated[Optional[str], "Short sentence displayed with the artifact for context."] = None,
    # AG2-native context injection
    context_variables: Annotated[Optional[Any], "Context variables provided by AG2"] = None,
) -> dict[str, Any]:
    """Normalize and cache Action Plan data for downstream Mermaid-based UI rendering.

    Summary:
        Normalize the ActionPlan payload, merge any provided Mermaid diagram (either via
        explicit MermaidSequenceDiagram argument or context cache), and persist the merged
        artifact state to context variables so `mermaid_sequence_diagram.py` can emit the UI.

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
                        "pattern": "ContextAwareRouting"|"Escalation"|"FeedbackLoop"|"Hierarchical"|"Organic"|"Pipeline"|"Redundant"|"Star"|"TriageWithTasks",
                        "description": str,
                        "lifecycle_operations": [
                            {
                                "name": str,
                                "trigger": "before_chat"|"after_chat"|"before_agent"|"after_agent",
                                "target": "AgentName"|null,
                                "description": str
                            }
                        ],
                        "modules": [
                            {
                                "module_index": int,
                                "module_name": str,
                                "module_description": str,
                                "agents": [
                                    {
                                        "agent_name": str,
                                        "agent_type": "router"|"worker"|"evaluator"|"orchestrator"|"intake"|"generator",
                                        "objective": str,
                                        "human_interaction": "none"|"context"|"approval"|"feedback"|"single",
                                        "generation_mode": "text"|"image"|"video"|"audio"|null,
                                        "agent_tools": [
                                            {
                                                "name": str,
                                                "integration": str|null,
                                                "purpose": str,
                                                "interaction_mode": "none"|"inline"|"artifact"
                                            }
                                        ],
                                        "lifecycle_tools": [],
                                        "system_hooks": []
                                    }
                                ]
                            }
                        ]
                    }
                }

            Notes:
                - Modules MUST preserve the exact names and ordering provided by the upstream WorkflowStrategy semantic wrapper (e.g., "Module 1: Discovery", "Module 2: Drafting").
                - Multi-module workflows are expected; do not collapse loops or approvals into single entries.
                - Semantic model uses three orthogonal dimensions: initiated_by, trigger_type, pattern
                - lifecycle_operations capture orchestration hooks between agents (before/after chat or agent triggers)
                - "integrations" contains third-party APIs/services (PascalCase)
                - "operations" contains internal workflow logic (snake_case)
                - "human_interaction" is agent-level field: none=automated, context=info gathering, approval=decision gate
                - LLM/runtime model metadata is intentionally excluded from the normalized workflow payload
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
    workflow_strategy: Optional[Dict[str, Any]] = None
    stored_blueprint: Optional[Dict[str, Any]] = None

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
            
            # Extract workflow_strategy for module merging
            strategy_candidate = context_variables.get("workflow_strategy")
            if isinstance(strategy_candidate, dict):
                workflow_strategy = strategy_candidate
            blueprint_candidate = context_variables.get("technical_blueprint")
            if isinstance(blueprint_candidate, dict):
                stored_blueprint = blueprint_candidate
            
            # Extract database schema information for Data tab display
            schema_overview = context_variables.get("schema_overview")
            collections_first_docs = context_variables.get("collections_first_docs_full")
            context_include_schema = context_variables.get("context_include_schema", False)
            context_schema_db = context_variables.get("context_schema_db")
            schema_capability_flag = bool(context_variables.get("database_schema_available"))
            schema_capability_db = context_variables.get("database_schema_db") or context_schema_db
            
        except Exception as ctx_err:  # pragma: no cover - defensive logging
            _logger.debug("Unable to read planning context: %s", ctx_err)
            schema_overview = None
            collections_first_docs = None
            context_include_schema = False
            context_schema_db = None
            schema_capability_flag = False
            schema_capability_db = None

    if not chat_id or not enterprise_id:
        _logger.warning("Missing routing keys: chat_id or enterprise_id not present on context_variables")
        return {"status": "error", "message": "chat_id and enterprise_id are required"}

    # --- Module Agents Merge Logic ---------------------------------------------
    # If module_agents is provided, merge with workflow_strategy to build ActionPlan
    if module_agents is not None and workflow_strategy is not None:
        _logger.info("Merging module_agents with workflow_strategy to construct ActionPlan")

        strategy_modules = workflow_strategy.get("modules", [])
        if not isinstance(strategy_modules, list):
            _logger.error("workflow_strategy.modules is not a list")
            return {"status": "error", "message": "Invalid workflow_strategy: modules must be a list"}

        if not isinstance(module_agents, list):
            _logger.error("module_agents is not a list")
            return {"status": "error", "message": "Invalid module_agents: must be a list"}

        if len(module_agents) != len(strategy_modules):
            _logger.error(
                "Module count mismatch: strategy has %d modules, implementation has %d module_agents",
                len(strategy_modules),
                len(module_agents)
            )
            return {
                "status": "error",
                "message": f"Module count mismatch: strategy has {len(strategy_modules)} modules, implementation has {len(module_agents)} module_agents"
            }

        # Build merged modules
        merged_modules = []
        for idx, strategy_module in enumerate(strategy_modules):
            if not isinstance(strategy_module, dict):
                _logger.warning("Skipping non-dict strategy module at index %d", idx)
                continue

            # Find matching module_agents entry
            module_agent_entry = None
            for pa in module_agents:
                if not isinstance(pa, dict):
                    continue
                pa_index = pa.get("module_index")
                if pa_index == idx:
                    module_agent_entry = pa
                    break

            if module_agent_entry is None:
                _logger.error("No module_agents entry found for module_index %d", idx)
                return {"status": "error", "message": f"Missing module_agents entry for module_index {idx}"}

            agents_list = module_agent_entry.get("agents", [])
            if not isinstance(agents_list, list):
                _logger.error("module_agents[%d].agents is not a list", idx)
                return {"status": "error", "message": f"Invalid agents for module_index {idx}: must be a list"}

            normalized_agents = [copy.deepcopy(agent) for agent in agents_list if isinstance(agent, dict)]

            # Merge: module metadata from strategy + agents from implementation
            module_name = strategy_module.get("module_name") or strategy_module.get("name") or f"Module {idx + 1}"
            module_description = strategy_module.get("module_description") or strategy_module.get("description") or ""
            module_index_raw = strategy_module.get("module_index")
            try:
                module_index = int(module_index_raw)
            except (TypeError, ValueError):
                module_index = idx
            
            merged_module = {
                "module_name": _coerce_str(module_name, f"Module {idx + 1}").strip() or f"Module {idx + 1}",
                "module_description": _coerce_str(module_description),
                "module_index": module_index,
                "agents": normalized_agents,
            }
            merged_modules.append(merged_module)
            _logger.debug(
                "Merged module %d: %s with %d agents",
                idx,
                merged_module["module_name"],
                len(agents_list)
            )

        # Construct ActionPlan from merged data
        pattern_field = workflow_strategy.get("pattern")
        if isinstance(pattern_field, list):
            pattern_value = next((p.strip() for p in pattern_field if isinstance(p, str) and p.strip()), "Pipeline")
            pattern_variants = [p.strip() for p in pattern_field if isinstance(p, str) and p.strip()]
        elif isinstance(pattern_field, str) and pattern_field.strip():
            pattern_value = pattern_field.strip()
            pattern_variants = [pattern_value]
        else:
            pattern_value = "Pipeline"
            pattern_variants = []

        trigger_raw, trigger_type = _normalize_trigger_fields(workflow_strategy)
        initiated_by_raw = _coerce_str(workflow_strategy.get("initiated_by"), "user").strip().lower() or "user"
        ActionPlan = {
            "workflow": {
                "name": workflow_strategy.get("workflow_name", "Generated Workflow"),
                "description": workflow_strategy.get("workflow_description", ""),
                "initiated_by": initiated_by_raw,
                "trigger": trigger_raw,
                "trigger_type": trigger_type,
                "pattern": pattern_value,
                "lifecycle_operations": workflow_strategy.get("lifecycle_operations", []),
                "modules": merged_modules
            }
        }
        if pattern_variants:
            ActionPlan["workflow"]["pattern_variants"] = pattern_variants
        _logger.info(
            "Successfully merged %d modules from strategy + implementation",
            len(merged_modules)
        )

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

    blueprint_payload = _extract_blueprint(plan_payload, stored_blueprint, plan_input)
    _logger.info("Blueprint extraction result: found=%s, keys=%s", 
                 blueprint_payload is not None,
                 list(blueprint_payload.keys()) if blueprint_payload else "None")

    ap_norm = _normalize_action_plan(plan_payload)
    plan_workflow = copy.deepcopy(ap_norm.get("workflow", {}) or {})
    legacy_mermaid_flow = _coerce_str(ap_norm.get("legacy_mermaid_flow"))

    normalized_blueprint: Optional[Dict[str, Any]] = None
    if blueprint_payload:
        _logger.info("Processing TechnicalBlueprint payload with keys: %s", list(blueprint_payload.keys()) if isinstance(blueprint_payload, dict) else "not a dict")
        _logger.info("Raw before_chat_lifecycle from blueprint: %s", blueprint_payload.get("before_chat_lifecycle"))
        _logger.info("Raw after_chat_lifecycle from blueprint: %s", blueprint_payload.get("after_chat_lifecycle"))
        global_context = _normalize_global_context_variables(blueprint_payload.get("global_context_variables"))
        components = _normalize_ui_components(blueprint_payload.get("ui_components"))
        designer_lifecycle = _normalize_lifecycle_operations(blueprint_payload.get("lifecycle_operations"))
        before_chat = _normalize_blueprint_lifecycle(blueprint_payload.get("before_chat_lifecycle"), "before_chat")
        after_chat = _normalize_blueprint_lifecycle(blueprint_payload.get("after_chat_lifecycle"), "after_chat")
        
        # Enrich context variables with full metadata for Data tab
        enriched_definitions = _enrich_context_variable_definitions(blueprint_payload.get("global_context_variables"))
        
        _logger.info("Normalized blueprint lifecycle: before_chat=%s, after_chat=%s, global_context_count=%d, component_count=%d", 
                    before_chat, after_chat, len(global_context), len(components))

        normalized_blueprint = {
            "global_context_variables": global_context,
            "ui_components": components,
            "before_chat_lifecycle": before_chat,
            "after_chat_lifecycle": after_chat,
        }

        if global_context:
            plan_workflow["global_context_variables"] = global_context
        if components:
            plan_workflow["ui_components"] = components
        
        # Add enriched context variable definitions for Data tab
        if enriched_definitions:
            plan_workflow["context_variable_definitions"] = enriched_definitions
            _logger.info("Added %d enriched context variable definitions", len(enriched_definitions))

        lifecycle_ops = plan_workflow.get("lifecycle_operations")
        if not isinstance(lifecycle_ops, list):
            lifecycle_ops = []

        existing_triggers = {str(op.get("trigger", "")).lower(): op for op in lifecycle_ops if isinstance(op, dict)}
        for entry in (before_chat, after_chat):
            if not entry:
                continue
            trigger = str(entry.get("trigger", "")).lower()
            if not trigger:
                continue
            existing = existing_triggers.get(trigger)
            if existing is None:
                lifecycle_ops.append(entry)
                existing_triggers[trigger] = entry
            else:
                if entry.get("description") and not existing.get("description"):
                    existing["description"] = entry["description"]
                if entry.get("integration"):
                    existing["integration"] = entry["integration"]

        if designer_lifecycle:
            for entry in designer_lifecycle:
                if not isinstance(entry, dict):
                    continue
                trigger = str(entry.get("trigger", "")).lower()
                if trigger not in _LIFECYCLE_TRIGGERS:
                    continue
                target = str(entry.get("target") or "").strip().lower()
                key = (trigger, target)
                match = None
                for existing in lifecycle_ops:
                    if not isinstance(existing, dict):
                        continue
                    existing_trigger = str(existing.get("trigger", "")).lower()
                    existing_target = str(existing.get("target") or "").strip().lower()
                    if (existing_trigger, existing_target) == key:
                        match = existing
                        break
                if match is None:
                    lifecycle_ops.append(entry)
                else:
                    if entry.get("description") and not match.get("description"):
                        match["description"] = entry["description"]
                    if entry.get("name") and not match.get("name"):
                        match["name"] = entry["name"]

        if lifecycle_ops:
            plan_workflow["lifecycle_operations"] = lifecycle_ops
            _logger.info("Final lifecycle_operations count in plan_workflow: %d", len(lifecycle_ops))

        plan_workflow["technical_blueprint"] = normalized_blueprint

    # --- Database Schema Information -----------------------------------------------
    # Parse and include database schema info for Data tab display
    database_schema_info = _parse_database_schema_info(
        schema_overview=schema_overview,
        collections_first_docs=collections_first_docs,
        context_schema_db=context_schema_db,
        context_include_schema=context_include_schema
    )
    
    if database_schema_info.get("enabled"):
        plan_workflow["database_schema"] = database_schema_info
        _logger.info(
            "Added database schema info: db=%s, collections=%d",
            database_schema_info.get("database_name"),
            len(database_schema_info.get("collections", []))
        )

    schema_capability: Dict[str, Any] = {
        "enabled": bool(schema_capability_flag or database_schema_info.get("enabled")),
        "database_name": database_schema_info.get("database_name") or schema_capability_db or context_schema_db,
        "has_schema_details": bool(database_schema_info.get("collections")),
        "collections_reported": database_schema_info.get("total_collections") or len(database_schema_info.get("collections", [])) or 0,
    }
    plan_workflow["database_capability"] = schema_capability

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
            context_variables.set("action_plan_snapshot", _serialize_plan_snapshot(plan_workflow))  # type: ignore[attr-defined]
            context_variables.set("action_plan_acceptance", "pending")  # type: ignore[attr-defined]
            if normalized_blueprint:
                context_variables.set("technical_blueprint", copy.deepcopy(normalized_blueprint))  # type: ignore[attr-defined]
            
            # Persist database schema info for downstream agents
            if database_schema_info.get("enabled"):
                context_variables.set("database_schema_info", copy.deepcopy(database_schema_info))  # type: ignore[attr-defined]
            context_variables.set("database_capability", copy.deepcopy(schema_capability))  # type: ignore[attr-defined]

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

    if tlog and _log_tool_event:
        try:
            _log_tool_event(
                tlog,
                action="cache",
                status="done",
                diagram_ready=True,
                agent_message_id=agent_message_id,
            )
        except Exception:  # pragma: no cover - telemetry best-effort
            pass

    wf_logger.info(
        "Action plan cached for Mermaid enrichment",
        extra={
            "diagram_ready": True,
            "workflow": wf_name,
        },
    )

    return {
        "status": "success",
        "action_plan": ap_norm,
        "workflow_name": wf_name,
        "diagram_ready": True,
        "diagram": diagram_text,
        "legend": legend_items,
        "notes": notes_text,
        "agent_message": final_agent_message,
        "agent_message_id": agent_message_id,
    }
