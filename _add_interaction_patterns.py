import json

with open('workflows/Generator/agents.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# New section to add
new_section = """
[COMMON INTERACTION PATTERNS]

**B2B/Internal Workflows** (Most MozaiksAI workflows):
- Pattern: Start with context → End with approval
- Typical flow: Gather requirements (context) → Process data (none) → Confirm action (approval) → Execute (none)
- Why: Workflows with business consequences (invoicing, payments, contracts, emails) require final human confirmation before execution
- Examples:
  * Invoice workflow: Collect client details (context) → Generate draft (none) → Manager approves (approval) → Process payment (none)
  * Email campaign: Gather campaign details (context) → Draft content (none) → Review and approve (approval) → Send emails (none)
  * Contract generator: Collect terms (context) → Draft contract (none) → Legal review (approval) → Send to client (none)

**Consumer-Facing/Assistive Workflows** (Informational/Educational):
- Pattern: Context throughout, no approval
- Typical flow: User asks → AI responds → User refines → AI responds (iterative dialogue)
- Why: No external actions triggered; user consumes information directly without business consequences
- Examples:
  * ChatGPT-style assistant: User asks questions (context) → AI provides answers (none) → User asks follow-ups (context)
  * Recipe assistant: User describes ingredients (context) → AI suggests recipes (none) → User asks modifications (context)
  * Tutoring bot: User asks for explanations (context) → AI teaches concepts (none) → User requests clarification (context)

**Decision Rule:**
- Does workflow trigger external actions (send email, charge payment, create/send documents)? → Add approval gate before execution
- Does workflow only provide information/content consumed by user? → Context only, no approval needed

"""

# Get ActionPlanArchitect system message
system_message = data['agents']['ActionPlanArchitect']['system_message']

# Find the insertion point (after Rules section, before [INSTRUCTIONS])
marker = "- conversational → must include at least one \"context\"\n\n\n[INSTRUCTIONS]"

if marker in system_message:
    # Insert the new section
    system_message = system_message.replace(
        marker,
        f"- conversational → must include at least one \"context\"\n{new_section}\n[INSTRUCTIONS]"
    )
    data['agents']['ActionPlanArchitect']['system_message'] = system_message
    print("✓ Added [COMMON INTERACTION PATTERNS] section")
    print("\nPlacement: After [HUMAN INTERACTION SEMANTICS], before [INSTRUCTIONS]")
    print("\nContent added:")
    print("  - B2B/Internal Workflows pattern (context → approval)")
    print("  - Consumer-Facing/Assistive Workflows pattern (context only)")
    print("  - Decision rule for choosing pattern")
else:
    print("❌ Could not find insertion marker")
    print("Looking for:", repr(marker[:50]))

# Write back to file
with open('workflows/Generator/agents.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print("\n✓ Saved workflows/Generator/agents.json")
