"""
Add stronger emphasis on context + approval pattern to ActionPlanArchitect prompt.
"""
from pathlib import Path

agents_path = Path(__file__).parent.parent / "workflows" / "Generator" / "agents.json"

# Read file
with open(agents_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Find the section to replace - the bullet points about human_interaction
old_section = """- Every agent must set `human_interaction` to exactly one of "none", "context", or "approval"; no other values or omissions are permitted.
- Phase 1 MUST include a discovery/context agent with `human_interaction: "context"` so the workflow always begins with human intake.
- Place a review/approval agent with `human_interaction: "approval"` before any phase that executes external actions or final delivery.
- Whenever integrations are invoked or operations imply external side effects, insert that approval agent immediately before the action executes.
- Never emit a plan that lacks both the required context intake and approval review checkpoints; revise the phases until both are present."""

# New section with stronger emphasis
new_section = """- Every agent must set `human_interaction` to exactly one of "none", "context", or "approval"; no other values or omissions are permitted.
- **95% OF WORKFLOWS REQUIRE BOTH CONTEXT AND APPROVAL:** If a workflow collects user input (context agent) AND executes external actions (sends emails, processes payments, triggers APIs, creates/sends documents), you MUST include BOTH a context agent early AND an approval agent before execution.
- Phase 1 MUST include a discovery/context agent with `human_interaction: "context"` so the workflow always begins with human intake.
- Place a review/approval agent with `human_interaction: "approval"` BEFORE any phase that executes external actions or final delivery.
- **DECISION RULE:** Does the workflow execute actions with external consequences? (send emails, charge payments, create documents, trigger third-party APIs, store data externally) → YES means approval is REQUIRED before execution.
- **RARE EXCEPTIONS (<5%):** Only pure informational workflows (chatbots, Q&A, tutoring providing answers with no external actions) can skip the approval agent.
- Never emit a plan that lacks both the required context intake and approval review checkpoints; revise the phases until both are present."""

# Perform replacement
if old_section in content:
    content = content.replace(old_section, new_section)
    
    # Write back
    with open(agents_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("✅ Successfully updated ActionPlanArchitect prompt")
    print("\nKey changes:")
    print("- Added '95% OF WORKFLOWS' statistic")
    print("- Added explicit decision rule for when approval is needed")
    print("- Listed specific execution types requiring approval")
    print("- Noted rare exceptions are <5% of workflows")
    print("- Emphasized BOTH context AND approval pattern")
else:
    print("❌ Could not find the exact section to replace")
    print("The prompt structure may have changed")
