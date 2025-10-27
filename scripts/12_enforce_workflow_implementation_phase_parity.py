"""
Phase 4 update script: reinforce WorkflowImplementationAgent phase parity validation
requirements so Action Plans always mirror strategy phases.
"""
from pathlib import Path
import json
import textwrap


def main() -> None:
    repo_root = Path(__file__).parent.parent
    agents_path = repo_root / "workflows" / "Generator" / "agents.json"

    with agents_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    impl_agent = data["agents"].get("WorkflowImplementationAgent")
    if not impl_agent:
        raise KeyError("WorkflowImplementationAgent definition not found in agents.json")

    system_message: str = impl_agent["system_message"]
    marker = "## 1. PHASE-LEVEL DETAILS"
    parity_header = "## 1.B PHASE PARITY & COUNT VALIDATION (CRITICAL)"

    if parity_header in system_message:
        print("⚠️  Parity block already present; no changes applied")
        return

    if marker not in system_message:
        raise ValueError("Expected phase details marker not found in WorkflowImplementationAgent prompt")

    parity_block = textwrap.dedent(
        """## 1.B PHASE PARITY & COUNT VALIDATION (CRITICAL)
Before designing any agent specifications, enforce the strategic phase contract so the Action Plan mirrors WorkflowStrategyAgent exactly.

**Non-negotiable validation steps:**
1. Read `workflow_strategy` from context variables. If it is missing or malformed, stop and request that the upstream strategy be regenerated.
2. Extract `strategy_phases = workflow_strategy.get("phases", [])` and build `strategy_phase_names = [phase.get("phase_name", "").strip() for phase in strategy_phases]`.
3. Ensure `strategy_phase_names` is non-empty, ordered, unique, and each entry starts with `Phase {index}:`. If numbering or naming is inconsistent, surface an error instead of proceeding.
4. While drafting the Action Plan, maintain `implementation_phase_names` that reflect the phases you have completed so far. Do not skip phases, rename them, or reorder them.
5. Before calling `action_plan(...)`, compare `implementation_phase_names` to `strategy_phase_names` (exact match including spacing, casing, and order). Also confirm each phase preserves the original `approval_required`, `agents_needed`, and `specialist_domains` semantics unless the strategy explicitly directs otherwise.
6. If any mismatch exists (count, order, spelling, or approval flags), stop and respond with a corrective explanation rather than invoking the tool. Direct the upstream agent to repair the discrepancy.

**Example parity contract (FeedbackLoop pattern with five phases):**
Strategy phases:
1. Phase 1: Content Ideation and Planning
2. Phase 2: AI Content Generation
3. Phase 3: Review and Approval
4. Phase 4: Content Revision and Finalization
5. Phase 5: Scheduling and Distribution

Implementation must emit those same five `phase_name` values, in order, when calling `action_plan(...)`. Any deviation (missing Phase 2, renamed Phase 3, altered numbering, etc.) is a fatal error. Never rely on downstream agents to repair parity.
"""
    ).strip()

    updated_message = system_message.replace(marker, f"{marker}\n\n{parity_block}\n\n")
    impl_agent["system_message"] = updated_message

    with agents_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print("✅ Added phase parity enforcement block to WorkflowImplementationAgent")


if __name__ == "__main__":
    main()
