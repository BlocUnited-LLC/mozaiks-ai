from __future__ import annotations

from typing import Dict, Any, List, Optional
from autogen.agentchat.group import (
    AgentTarget,
    RevertToUserTarget,
    OnCondition,
    StringLLMCondition,
    OnContextCondition,
    ExpressionContextCondition,
    ContextExpression,
    TerminateTarget,
)
from .workflow_manager import workflow_manager
from logs.logging_config import get_workflow_logger

log = get_workflow_logger("handoffs")

"""Production handoff integration for AG2 group orchestration.

Standardized JSON schema (handoffs.json):
  handoffs:
    handoff_rules:
      - source_agent: <name>
        target_agent: <name|user|terminate>
        handoff_type: after_work | condition
        condition: <natural language or context expression with ${...}> | null

Rules:
  - Multiple condition rules per source preserved in order.
  - condition containing '${' becomes a context expression condition.
  - Last after_work wins per source.
  - Unknown agents logged & skipped (won't raise).
"""


class HandoffManager:
    def __init__(self) -> None:
        # Canonical special target names
        self._special = {
            "user": lambda: RevertToUserTarget(),
            "terminate": lambda: TerminateTarget(),
        }
        # Accept common variants for robustness
        self._special_aliases = {
            "user": {"user", "User", "USER", "user_proxy", "userproxy", "UserProxy", "user-agent", "UserAgent"},
            "terminate": {"terminate", "Terminate", "TERMINATE", "end", "End", "END", "stop", "Stop", "STOP"},
        }

    def apply_handoffs_from_config(self, workflow_name: str, agents: Dict[str, Any]) -> Dict[str, Any]:
        summary = {
            "workflow": workflow_name,
            "rules_total": 0,
            "agents_with_rules": set(),
            "after_work_set": 0,
            "llm_conditions": 0,
            "context_conditions": 0,
            "missing_source_agents": [],
            "missing_target_agents": [],
            "errors": []
        }
        config = workflow_manager.get_config(workflow_name) or {}
        handoffs_block = config.get("handoffs", {})
        if "handoffs" in handoffs_block:  # tolerate nested key structure
            handoffs_block = handoffs_block["handoffs"]
        rules: List[Dict[str, Any]] = handoffs_block.get("handoff_rules", []) or []
        summary["rules_total"] = len(rules)
        if not rules:
            log.warning(f"⚠️ [HANDOFFS] No handoff_rules found for workflow {workflow_name}")
            summary["agents_with_rules"] = []
            return summary

            grouped: Dict[str, List[Dict[str, Any]]] = {}
            for r in rules:
                sa = r.get("source_agent")
                ta = r.get("target_agent")
                if not sa or not ta:
                    summary["errors"].append(f"Rule missing source/target: {r}")
                    continue
                grouped.setdefault(sa, []).append(r)

            for source, src_rules in grouped.items():
                agent_obj = agents.get(source)
                if not agent_obj:
                    summary["missing_source_agents"].append(source)
                    log.warning(f"⚠️ [HANDOFFS] Source agent '{source}' not present; skipping its rules")
                    continue
                if not hasattr(agent_obj, "handoffs"):
                    summary["errors"].append(f"Agent {source} lacks .handoffs attribute")
                    log.error(f"❌ [HANDOFFS] Agent {source} lacks .handoffs attribute")
                    continue

                llm_list: List[OnCondition] = []
                ctx_list: List[OnContextCondition] = []
                after_work_target = None

                for rule in src_rules:
                    t_name = rule.get("target_agent")
                    h_type = (rule.get("handoff_type") or "after_work").strip()
                    cond_text = rule.get("condition")
                    target = self._build_target(t_name, agents, summary)
                    if not target:
                        continue
                    if h_type == "after_work":
                        if after_work_target is not None:
                            log.info(f"🔁 [HANDOFFS] Overriding after_work for {source} -> {t_name}")
                        after_work_target = target
                    elif h_type == "condition":
                        if not cond_text:
                            log.warning(f"⚠️ [HANDOFFS] condition rule without condition text skipped: {rule}")
                            continue
                        if "${" in cond_text:  # context expression
                            try:
                                ctx_list.append(
                                    OnContextCondition(
                                        target=target,
                                        condition=ExpressionContextCondition(expression=ContextExpression(cond_text))
                                    )
                                )
                                summary["context_conditions"] += 1
                            except Exception as e:
                                summary["errors"].append(f"Context condition build failed ({source}): {e}")
                                log.error(f"❌ [HANDOFFS] Context condition build failed for {source}: {e}")
                        else:
                            try:
                                llm_list.append(
                                    OnCondition(
                                        target=target,
                                        condition=StringLLMCondition(prompt=cond_text)
                                    )
                                )
                                summary["llm_conditions"] += 1
                            except Exception as e:
                                summary["errors"].append(f"LLM condition build failed ({source}): {e}")
                                log.error(f"❌ [HANDOFFS] LLM condition build failed for {source}: {e}")
                    else:
                        log.warning(f"⚠️ [HANDOFFS] Unknown handoff_type '{h_type}' skipped (rule={rule})")

                applied = False
                try:
                    if llm_list:
                        agent_obj.handoffs.add_llm_conditions(llm_list)  # type: ignore[attr-defined]
                        applied = True
                    if ctx_list:
                        agent_obj.handoffs.add_context_conditions(ctx_list)  # type: ignore[attr-defined]
                        applied = True
                    if after_work_target is not None:
                        agent_obj.handoffs.set_after_work(after_work_target)  # type: ignore[attr-defined]
                        summary["after_work_set"] += 1
                        applied = True
                except Exception as e:
                    summary["errors"].append(f"Apply failed ({source}): {e}")
                    log.error(f"❌ [HANDOFFS] Failed applying rules for {source}: {e}")

                if applied:
                    summary["agents_with_rules"].add(source)
                    log.info(
                        f"✅ [HANDOFFS] {source}: llm={len(llm_list)} ctx={len(ctx_list)} after_work={'yes' if after_work_target else 'no'}"
                    )

        summary["agents_with_rules"] = list(summary["agents_with_rules"])
        if summary["errors"]:
            log.warning(f"⚠️ [HANDOFFS] Completed with {len(summary['errors'])} errors")
        return summary

    def verify(self, agents: Dict[str, Any]) -> Dict[str, Any]:  # optional health snapshot
        out = {"total": len(agents), "configured": 0, "details": {}}
        for name, a in agents.items():
            if not hasattr(a, "handoffs"):
                continue
            h = a.handoffs
            llm_rules = getattr(h, "llm_conditions", None) or getattr(h, "_llm_conditions", [])
            ctx_rules = getattr(h, "context_conditions", None) or getattr(h, "_context_conditions", [])
            after_work = getattr(h, "after_works", None) or getattr(h, "_after_work", None)
            out["details"][name] = {
                "llm": len(llm_rules) if hasattr(llm_rules, "__len__") else 0,
                "ctx": len(ctx_rules) if hasattr(ctx_rules, "__len__") else 0,
                "after_work": bool(after_work)
            }
            if any([out["details"][name]["llm"], out["details"][name]["ctx"], out["details"][name]["after_work"]]):
                out["configured"] += 1
        return out

    def _build_target(self, target_name: Optional[str], agents: Dict[str, Any], summary: Dict[str, Any]):
        if not target_name:
            return None
        # Normalize special aliases first
        for canonical, aliases in self._special_aliases.items():
            if target_name in aliases:
                return self._special[canonical]()
        # Case-insensitive agent name match fallback
        if target_name in self._special:
            return self._special[target_name]()
        if target_name in agents:
            return AgentTarget(agents[target_name])
        # Try case-insensitive match for agent keys
        lower_map = {k.lower(): k for k in agents.keys()}
        tgt_key = lower_map.get(target_name.lower()) if isinstance(target_name, str) else None
        if tgt_key and tgt_key in agents:
            return AgentTarget(agents[tgt_key])
        summary["missing_target_agents"].append(target_name)
        log.warning(f"⚠️ [HANDOFFS] Target agent '{target_name}' not found; skipping")
        return None


handoff_manager = HandoffManager()


def wire_handoffs(workflow_name: str, agents: Dict[str, Any]) -> None:
    try:
        summary = handoff_manager.apply_handoffs_from_config(workflow_name, agents)
        log.info(
            f"HANDOFFS_APPLIED rules={summary['rules_total']} agents={len(summary['agents_with_rules'])} "
            f"after_work={summary['after_work_set']} llm={summary['llm_conditions']} ctx={summary['context_conditions']}"
        )
    except Exception as e:
        log.error(f"❌ [HANDOFFS] Wiring failed: {e}", exc_info=True)


def wire_handoffs_with_debugging(workflow_name: str, agents: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return handoff_manager.apply_handoffs_from_config(workflow_name, agents)
    except Exception as e:
        return {"success": False, "error": str(e)}


__all__ = ["wire_handoffs", "wire_handoffs_with_debugging", "handoff_manager", "HandoffManager"]
