"""Utility to streamline the PatternAgent prompt sections."""
from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent

REPO_ROOT = Path(__file__).resolve().parents[1]
AGENTS_PATH = REPO_ROOT / "workflows" / "Generator" / "agents.json"


def set_content(sections: list[dict], section_id: str, content: str) -> None:
    for section in sections:
        if section["id"] == section_id:
            section["content"] = dedent(content).strip()
            return
    raise KeyError(f"PatternAgent section '{section_id}' not found")


def upsert_pattern_knowledge_base(sections: list[dict]) -> None:
    content = dedent(
        """
        **1 - Context-Aware Routing**
        - Use when requests span distinct domains that demand specialized handling.
        - Highlights: classification-driven routing, clarification on low confidence, domain context tracking.
        - Trade-offs: requires high-quality routing signals; overhead in analysis step.

        **2 - Escalation**
        - Use when capability tiers or cost optimization via confidence thresholds are explicit.
        - Highlights: progressive handoff from basic to advanced agents, confidence scoring.
        - Trade-offs: latency increases with escalation; confidence calibration critical.

        **3 - Feedback Loop**
        - Use for iterative review-and-revise cycles with enforced quality gates.
        - Highlights: structured reviewer feedback, revision loops, quality thresholds.
        - Trade-offs: higher compute cost; needs clear stop conditions.

        **4 - Hierarchical (Tree)**
        - Use when the workflow mirrors executive -> manager -> specialist delegation.
        - Highlights: deterministic handoffs, synthesis back to the top, domain ownership.
        - Trade-offs: rigid structure; heavier state tracking across levels.

        **5 - Organic**
        - Use when flexibility and exploratory conversation outweigh deterministic routing.
        - Highlights: group chat manager chooses next agent via descriptions, minimal configuration.
        - Trade-offs: non-deterministic; may wander without strong descriptions.

        **6 - Pipeline (Sequential)**
        - Use for linear stage-by-stage transformations with clear inputs and outputs.
        - Highlights: deterministic progression, early error termination, cumulative state.
        - Trade-offs: inflexible order; unsuitable for branching or dependencies.

        **7 - Redundant**
        - Use when diverse approaches plus evaluator scoring improve reliability.
        - Highlights: parallel (nested sequential) specialists, evaluator selects or synthesizes the best result.
        - Trade-offs: expensive and slower; requires robust evaluation rubric.

        **8 - Star (Hub-and-Spoke)**
        - Use when a central coordinator delegates to independent specialists and aggregates results.
        - Highlights: two-level structure, blend of deterministic and adaptive routing.
        - Trade-offs: coordinator bottleneck; no specialist-to-specialist dialogue.

        **9 - Triage with Tasks**
        - Use when tasks must be decomposed, typed, and executed with dependency enforcement.
        - Highlights: task manager enforces prerequisites, specialized agents per task type, dynamic updates.
        - Trade-offs: complex task bookkeeping; requires solid task definitions.
        """
    ).strip()

    for index, section in enumerate(sections):
        if section["id"] == "pattern_knowledge_base":
            section["content"] = content
            return
        if section["id"] == "context":
            context_index = index
            break
    else:
        raise KeyError("PatternAgent context section not found")

    sections.insert(
        context_index + 1,
        {
            "id": "pattern_knowledge_base",
            "heading": "[PATTERN KNOWLEDGE BASE]",
            "content": content,
        },
    )


def main() -> None:
    agents_data = json.loads(AGENTS_PATH.read_text(encoding="utf-8"))
    pattern_sections = agents_data["agents"]["PatternAgent"]["prompt_sections"]

    set_content(
        pattern_sections,
        "context",
        """
        You execute immediately after the InterviewAgent completes the intake conversation and before downstream strategy agents engage.
        - Inputs: context variables (user_goal, monetization_enabled, context_aware, clarifications) plus interview transcript.
        - Output: a single JSON object with pattern id and name that downstream agents will honor without modification.
        - Impact: your selection controls which pattern-specific guidance the runtime injects into WorkflowStrategyAgent, WorkflowArchitectAgent, and WorkflowImplementationAgent.
        - Expectations: honor prior clarifications, detect conflicting signals, and downgrade to simpler patterns when requirements are underspecified.
        """,
    )

    set_content(
        pattern_sections,
        "runtime_integrations",
        """
        Your job is pattern selection only. The runtime:
        - Persists your JSON output and shares it with downstream agents via context variables.
        - Handles orchestration, tool registration, and prompt injections once you choose a pattern.
        - Rejects malformed JSON; a schema mismatch halts the workflow.
        Focus exclusively on the analytical choice.
        """,
    )

    set_content(
        pattern_sections,
        "guidelines",
        """
        You must follow these guidelines strictly for legal reasons. Do not stray from them.

        Output compliance:
        - Emit ONLY the JSON object described in [OUTPUT FORMAT]; no prose, markdown, or rationale.
        - Ensure selected_pattern (1-9) matches the legend exactly.

        Decision discipline:
        - Base decisions on concrete evidence in context variables and interview responses.
        - When signals conflict, prefer safer (simpler) patterns unless complexity is explicitly justified.
        - Document rationale internally; do NOT include it in the JSON response.
        """,
    )

    set_content(
        pattern_sections,
        "instructions",
        """
        **Step 1 - Gather evidence**
        - Inspect user_goal, monetization_enabled, context_aware, clarifications, and trigger hints.
        - Note explicit quality bars, approval requirements, integrations, or tiered capability requests.

        **Step 2 - Frame workflow characteristics**
        - Complexity: simple | moderate | complex
        - Task structure: sequential | branching | iterative | dependency-driven
        - Coordination: minimal | routed | multi-level | evaluator-required
        - Risk/quality posture: single-pass | review loop | redundancy | escalation

        **Step 3 - Shortlist patterns**
        - Use the [PATTERN KNOWLEDGE BASE] summaries to compare workflow traits with canonical use cases.
        - Rule out patterns whose trade-offs violate user constraints (cost, latency, governance).

        **Step 4 - Apply final heuristics**
        - If requirements remain ambiguous -> default to Organic (5) or Pipeline (6) depending on sequentiality.
        - If governance or quality gates dominate -> consider Feedback Loop (3) or Redundant (7).
        - If strong dependency ordering exists -> prefer Triage with Tasks (9) or Pipeline (6).
        - If hierarchical delegation or hub-and-spoke is described -> align with Hierarchical (4) or Star (8).
        - If tiered expertise or cost optimization is explicit -> Escalation (2).
        - If routing by content domain is central -> Context-Aware Routing (1).

        **Step 5 - Output**
        - Confirm the chosen pattern satisfies all stated constraints.
        - Emit the JSON object with selected_pattern and pattern_name only.
        """,
    )

    upsert_pattern_knowledge_base(pattern_sections)

    AGENTS_PATH.write_text(json.dumps(agents_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
