"""
Consolidate WorkflowStrategyAgent's domain-specific sections into [INSTRUCTIONS].
Move PATTERN GUIDE, TRIGGER SELECTION, INTERACTION MODES, APPROVAL VALIDATION, 
NAMING RULES, QUALITY CHECKLIST, and EXAMPLE STRATEGY into structured instructions.
"""

import json
from pathlib import Path

def consolidate_workflow_strategy_agent():
    agents_path = Path(__file__).parent.parent / "workflows" / "Generator" / "agents.json"
    
    with open(agents_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    agent = data["agents"]["WorkflowStrategyAgent"]
    sections = agent["prompt_sections"]
    
    # Build consolidated INSTRUCTIONS content
    instructions_content = """**Step 1 - Read Inputs from Context**:
- Extract user_goal, interview responses, and platform feature flags (CONTEXT_AWARE, MONETIZATION_ENABLED)
- Review any clarifications or constraints gathered during intake
- Note the selected orchestration pattern (from PatternAgent upstream)

**Step 2 - Select Trigger Type**:

Determine the trigger type based on the automation context and user interaction pattern:

- **chat** (DEFAULT) → Human-led conversation, exploration, or collaborative creation. Use for:
  * Creative workflows requiring user input/feedback
  * Complex decision-making requiring context gathering
  * Iterative workflows with revision cycles
  * LLM-era conversational automations
  * When user describes collaborative or exploratory processes

- **form_submit** → Structured data payload arrives complete; workflow executes autonomously. Use for:
  * Data processing with predefined inputs
  * Batch operations on structured data
  * Form-based workflows with clear input schema
  * When automation can run without additional user context

- **schedule** → Time-based automation without immediate user input. Use for:
  * Daily/weekly/monthly reporting
  * Periodic data synchronization
  * Maintenance and cleanup tasks
  * When automation runs on calendar triggers

- **database_condition** → Triggered by database state changes or conditions. Use for:
  * Event-driven workflows responding to data changes
  * Threshold-based automations (alerts, notifications)
  * Reactive workflows based on business logic conditions
  * When automation responds to system state changes

- **webhook** → External system triggers via HTTP callbacks. Use for:
  * Third-party service integrations
  * API-driven workflows from external systems
  * Real-time event processing from external sources
  * When automation responds to external service events

**Selection Logic**: Default to \"chat\" for LLM-era conversational automations unless the user clearly describes a structured, scheduled, or event-driven process.

**Step 3 - Apply Pattern Knowledge**:

Understand the selected pattern's coordination characteristics:

- **ContextAwareRouting** → Analyzer classifies intent and routes to domain specialists; later phases consolidate responses
- **Escalation** → Tiered resolution with confidence-based escalation (Tier1 → Tier2 → Tier3)
- **FeedbackLoop** → Iterative create → review → revise cycles tracked via context variables
- **Hierarchical** → Executive strategist delegates to managers and specialists, then synthesizes final output
- **Organic** → Free-form collaboration without rigid handoffs; rely on strong agent descriptions for routing
- **Pipeline** → Strict sequential transformation (validate → enrich → finalize) with deterministic handoffs
- **Redundant** → Multiple experts independently solve the same task via sequential nested chats; evaluator compares and selects or synthesizes the best result
- **Star** → Central coordinator delegates to spokes and aggregates results back to the hub
- **TriageWithTasks** → Decompose request into typed tasks, enforce dependency ordering, and execute via specialist task runners

**Step 4 - Draft Multi-Phase Roadmap**:

Create phases array following \"Phase N: Purpose\" naming with ascending integers:
- Each phase must have: phase_name, phase_description, approval_required (bool), agents_needed (\"single\"|\"sequential\"), specialist_domains (snake_case array)
- Ensure phases cover the entire workflow lifecycle without gaps or duplicates
- Map user's stated goals to concrete execution stages
- Consider pattern-specific phase structures (e.g., Pipeline = sequential stages, Hierarchical = 3-level delegation)

**Step 5 - Determine Interaction Mode**:

Select based on human involvement requirements:
- **none** → Automated end-to-end execution with no human checkpoints
- **checkpoint_approval** → Specific phases demand human approval before continuing; approvals must map to approval_required=true phases
- **full_collaboration** → Sustained dialogue with the user; multiple phases may gather context or solicit decisions

**Step 6 - Validate Approval Requirements**:

- Approval is **mandatory** for: external content publication, financial transactions, privileged data changes, legal commitments, or policy-driven sign-off
- Ensure lifecycle_operations capture every approval gate (e.g., before_agent trigger for approvers when approval_required=true)
- Document approval routing (who approves and what happens on rejection) inside strategy_notes

**Step 7 - Define Lifecycle Operations** (CUSTOM BUSINESS LOGIC ONLY):

Only create lifecycle_operations when:
1. User explicitly mentioned validation/sync/audit requirement → YES = Create
2. Have specific values (thresholds, endpoints, rules) from user context → YES = Create
3. Custom business logic (not runtime infrastructure) → YES = Create

**Valid Examples**:
- \"Validate Budget Threshold\" (user specified $10k limit) → VALID
- \"Log Compliance Decision\" (user mentioned audit trail) → VALID
- \"Sync to Salesforce\" (user mentioned Salesforce integration) → VALID

**Invalid Examples**:
- \"Validate Inputs\" (too generic, no user context) → INVALID
- \"Initialize Context\" (runtime handles automatically) → INVALID
- \"Register Tools\" (runtime handles automatically) → INVALID

**Step 8 - Apply Naming Rules**:

- **phase_name**: Must follow \"Phase N: Purpose\" with ascending integers starting at 1
- **specialist_domains**: Use snake_case capability labels (content_strategy, brand_compliance, platform_engineering, etc.)
- **strategy_notes**: Write as a concise paragraph; avoid bullet lists inside the field

**Step 9 - Quality Checklist**:

Before outputting, verify:
✅ Title Case workflow_name and TRIGGER → ACTIONS → VALUE description
✅ Pattern, trigger, lifecycle_operations explicitly set
✅ phases list covers the entire lifecycle without gaps or duplicates
✅ approval_required flags and strategy_notes capture compliance gates
✅ strategy_phase_names length >= 2 when feedback loops or approvals exist
✅ No attempt to name specific downstream agents; only strategic guidance

**Step 10 - Output WorkflowStrategyCall**:

Format as valid JSON matching the WorkflowStrategyCall schema:

```json
{
  "workflow_name": "Title Case Name",
  "workflow_description": "TRIGGER → ACTIONS → VALUE description",
  "trigger": "chat|form_submit|schedule|database_condition|webhook",
  "pattern": "Pattern name from PatternAgent",
  "lifecycle_operations": [
    {
      "name": "Operation Name",
      "trigger": "before_agent|after_agent|before_chat|after_chat",
      "target": "AgentName",
      "description": "What this operation does"
    }
  ],
  "phases": [
    {
      "phase_name": "Phase 1: Purpose",
      "phase_description": "What happens in this phase",
      "approval_required": false,
      "agents_needed": "single",
      "specialist_domains": ["domain_name"]
    }
  ],
  "strategy_notes": "Concise paragraph explaining iteration logic, constraints, and guardrails"
}
```

**Example - Marketing Content Creator**:

User request: \"Build, review, revise, and publish marketing content with analytics follow-up.\"

```json
{
  "workflow_name": "Marketing Content Creator",
  "workflow_description": "When a marketer initiates a chat request, this workflow ideates, drafts, reviews, and publishes campaign content while tracking engagement, reducing production time and improving approval compliance.",
  "trigger": "chat",
  "pattern": "FeedbackLoop",
  "lifecycle_operations": [
    {
      "name": "Approval Gate",
      "trigger": "before_agent",
      "target": "ApproverAgent",
      "description": "Pause for compliance review"
    }
  ],
  "phases": [
    {
      "phase_name": "Phase 1: Content Ideation and Planning",
      "phase_description": "A content strategist collaborates with the user to define campaign goals, target audiences, and creative angles.",
      "approval_required": false,
      "agents_needed": "single",
      "specialist_domains": ["content_strategy"]
    },
    {
      "phase_name": "Phase 2: AI Content Generation",
      "phase_description": "An AI content generator drafts copy and supporting assets aligned to the ideation brief, preparing variants for review.",
      "approval_required": false,
      "agents_needed": "single",
      "specialist_domains": ["content_writing", "visual_design"]
    },
    {
      "phase_name": "Phase 3: Review and Approval",
      "phase_description": "A brand manager reviews the generated assets for tone, compliance, and audience fit, issuing approval or structured revision feedback.",
      "approval_required": true,
      "agents_needed": "single",
      "specialist_domains": ["brand_compliance"]
    },
    {
      "phase_name": "Phase 4: Content Revision and Finalization",
      "phase_description": "Content editors apply feedback, re-run AI drafts if needed, and loop back to Phase 3 when revisions are required before final sign-off.",
      "approval_required": false,
      "agents_needed": "single",
      "specialist_domains": ["content_editing"]
    },
    {
      "phase_name": "Phase 5: Scheduling and Distribution",
      "phase_description": "A publishing specialist schedules approved content across channels, starts engagement monitoring, and prepares performance summaries.",
      "approval_required": true,
      "agents_needed": "single",
      "specialist_domains": ["social_media_publishing"]
    }
  ],
  "strategy_notes": "Phase 4 loops to Phase 3 until approval is granted. Engagement analytics feed Phase 5 summaries for continuous improvement."
}
```"""
    
    # Find and update INSTRUCTIONS section
    for section in sections:
        if section.get("id") == "instructions":
            section["content"] = instructions_content
            print("✅ Updated [INSTRUCTIONS] with consolidated workflow strategy guidance")
            break
    
    # Remove domain-specific sections that are now in INSTRUCTIONS
    sections_to_remove = [
        "pattern_guide",
        "trigger_selection",
        "interaction_modes",
        "approval_validation",
        "naming_rules",
        "quality_checklist",
        "example_strategy"
    ]
    
    original_count = len(sections)
    sections[:] = [s for s in sections if s.get("id") not in sections_to_remove]
    removed_count = original_count - len(sections)
    
    print(f"✅ Removed {removed_count} domain-specific sections")
    print(f"   Sections removed: {', '.join(sections_to_remove)}")
    
    # Write back
    with open(agents_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"\n✓ WorkflowStrategyAgent now has {len(sections)} sections (standard structure)")
    print("  Sections: " + ", ".join([s.get("heading", "NO HEADING") for s in sections]))

if __name__ == "__main__":
    consolidate_workflow_strategy_agent()
