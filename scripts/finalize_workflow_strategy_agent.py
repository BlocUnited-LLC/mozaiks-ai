"""
Add [EXAMPLES] section and populate [OUTPUT FORMAT] for WorkflowStrategyAgent.
"""

import json
from pathlib import Path

def finalize_workflow_strategy_agent():
    agents_path = Path(__file__).parent.parent / "workflows" / "Generator" / "agents.json"
    
    with open(agents_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    agent = data["agents"]["WorkflowStrategyAgent"]
    sections = agent["prompt_sections"]
    
    # Find JSON OUTPUT COMPLIANCE section index
    json_compliance_index = None
    for i, section in enumerate(sections):
        if section.get("id") == "json_output_compliance":
            json_compliance_index = i
            break
    
    if json_compliance_index is None:
        print("❌ Could not find [JSON OUTPUT COMPLIANCE] section")
        return
    
    # Create EXAMPLES section
    examples_section = {
        "id": "examples",
        "heading": "[EXAMPLES]",
        "content": """**Example 1: E-Commerce Order Processing (Pipeline Pattern)**

User Goal: \"Automate order fulfillment from validation through shipping notification\"
Interview reveals: Sequential stages with clear dependencies, error handling critical

WorkflowStrategy Output:
```json
{
  "workflow_name": "E-Commerce Order Fulfillment",
  "workflow_description": "When an order form is submitted, this workflow validates payment, reserves inventory, processes shipping, and sends notifications, reducing fulfillment time and preventing overselling.",
  "trigger": "form_submit",
  "pattern": "Pipeline",
  "lifecycle_operations": [],
  "phases": [
    {
      "phase_name": "Phase 1: Order Validation",
      "phase_description": "Validation agent verifies order completeness, payment method, and customer eligibility",
      "approval_required": false,
      "agents_needed": "single",
      "specialist_domains": ["order_validation"]
    },
    {
      "phase_name": "Phase 2: Inventory Check",
      "phase_description": "Inventory agent confirms stock availability and reserves items",
      "approval_required": false,
      "agents_needed": "single",
      "specialist_domains": ["inventory_management"]
    },
    {
      "phase_name": "Phase 3: Payment Processing",
      "phase_description": "Payment agent charges customer via Stripe integration",
      "approval_required": false,
      "agents_needed": "single",
      "specialist_domains": ["payment_processing"]
    },
    {
      "phase_name": "Phase 4: Shipping Dispatch",
      "phase_description": "Fulfillment agent generates shipping labels and updates tracking",
      "approval_required": false,
      "agents_needed": "single",
      "specialist_domains": ["shipping_logistics"]
    }
  ],
  "strategy_notes": "Each stage must complete successfully before proceeding. Payment failures trigger inventory release and error notifications."
}
```

**Example 2: Blog Content Creation (Feedback Loop Pattern)**

User Goal: \"Create, review, and publish blog posts with editorial oversight\"
Interview reveals: Iterative revision cycles, approval gates required, quality focus

WorkflowStrategy Output:
```json
{
  "workflow_name": "Blog Content Creator",
  "workflow_description": "When a writer initiates a chat request, this workflow drafts, reviews, revises, and publishes blog content with editorial approval, ensuring quality and brand consistency.",
  "trigger": "chat",
  "pattern": "FeedbackLoop",
  "lifecycle_operations": [
    {
      "name": "Editorial Approval Gate",
      "trigger": "before_agent",
      "target": "EditorAgent",
      "description": "Pause for editorial sign-off before publication"
    }
  ],
  "phases": [
    {
      "phase_name": "Phase 1: Topic Ideation",
      "phase_description": "Content strategist collaborates with writer to define topic, angle, and target audience",
      "approval_required": false,
      "agents_needed": "single",
      "specialist_domains": ["content_strategy"]
    },
    {
      "phase_name": "Phase 2: Draft Generation",
      "phase_description": "AI writer generates initial draft based on topic brief",
      "approval_required": false,
      "agents_needed": "single",
      "specialist_domains": ["content_writing"]
    },
    {
      "phase_name": "Phase 3: Editorial Review",
      "phase_description": "Editor reviews draft for clarity, tone, and factual accuracy, providing structured feedback",
      "approval_required": true,
      "agents_needed": "single",
      "specialist_domains": ["editorial_review"]
    },
    {
      "phase_name": "Phase 4: Revision",
      "phase_description": "Revision agent applies editorial feedback and loops back to Phase 3 if needed",
      "approval_required": false,
      "agents_needed": "single",
      "specialist_domains": ["content_editing"]
    },
    {
      "phase_name": "Phase 5: Publication",
      "phase_description": "Publishing agent schedules and publishes approved content to WordPress",
      "approval_required": true,
      "agents_needed": "single",
      "specialist_domains": ["content_publishing"]
    }
  ],
  "strategy_notes": "Phase 4 loops to Phase 3 until editor approval granted. Maximum 3 revision cycles enforced to prevent infinite loops."
}
```

**Example 3: Customer Support Routing (Context-Aware Routing Pattern)**

User Goal: \"Route customer inquiries to specialized support agents based on topic\"
Interview reveals: Multi-domain support (billing, technical, account), content-driven routing needed

WorkflowStrategy Output:
```json
{
  "workflow_name": "Smart Customer Support Router",
  "workflow_description": "When a customer submits a support request, this workflow classifies the inquiry and routes to specialized domain agents, improving resolution time and customer satisfaction.",
  "trigger": "form_submit",
  "pattern": "Context-Aware Routing",
  "lifecycle_operations": [],
  "phases": [
    {
      "phase_name": "Phase 1: Request Analysis",
      "phase_description": "Routing agent classifies customer inquiry into billing, technical, or account domains with confidence scoring",
      "approval_required": false,
      "agents_needed": "single",
      "specialist_domains": ["request_classification"]
    },
    {
      "phase_name": "Phase 2: Specialized Response",
      "phase_description": "Domain specialists (billing, technical, account) provide expert responses based on routing decision",
      "approval_required": false,
      "agents_needed": "sequential",
      "specialist_domains": ["billing_support", "technical_support", "account_management"]
    },
    {
      "phase_name": "Phase 3: Response Delivery",
      "phase_description": "Consolidation agent formats specialist response and sends to customer via email",
      "approval_required": false,
      "agents_needed": "single",
      "specialist_domains": ["customer_communication"]
    }
  ],
  "strategy_notes": "Low-confidence classifications trigger clarification requests before specialist routing. All responses logged for quality assurance."
}
```"""
    }
    
    # Insert EXAMPLES section before JSON OUTPUT COMPLIANCE
    sections.insert(json_compliance_index, examples_section)
    print("✅ Added [EXAMPLES] section before [JSON OUTPUT COMPLIANCE]")
    
    # Update OUTPUT FORMAT section
    output_format_content = """Output MUST be a valid JSON object matching the WorkflowStrategyCall schema with NO additional text:

```json
{
  "workflow_name": "<Title Case Name>",
  "workflow_description": "<TRIGGER → ACTIONS → VALUE description>",
  "trigger": "chat|form_submit|schedule|database_condition|webhook",
  "pattern": "<Pattern name from PatternAgent>",
  "lifecycle_operations": [
    {
      "name": "<Operation Name>",
      "trigger": "before_agent|after_agent|before_chat|after_chat",
      "target": "<AgentName>",
      "description": "<What this operation does>"
    }
  ],
  "phases": [
    {
      "phase_name": "Phase N: <Purpose>",
      "phase_description": "<What happens in this phase>",
      "approval_required": true|false,
      "agents_needed": "single|sequential",
      "specialist_domains": ["domain_name"]
    }
  ],
  "strategy_notes": "<Concise paragraph explaining iteration logic, constraints, and guardrails>"
}
```

**Required Fields**:
- workflow_name: Title Case, descriptive
- workflow_description: Must follow TRIGGER → ACTIONS → VALUE pattern
- trigger: One of the 5 trigger types
- pattern: Exact pattern name from PatternAgent (e.g., "Pipeline", "FeedbackLoop")
- lifecycle_operations: Array (can be empty [])
- phases: Array with at least 1 phase, sequential phase_name numbering
- strategy_notes: Concise paragraph (not bullet list)

**Phase Fields**:
- phase_name: "Phase N: Purpose" format with ascending N
- phase_description: Clear description of what happens
- approval_required: Boolean (true for approval gates)
- agents_needed: "single" or "sequential"
- specialist_domains: Array of snake_case domain names

**CRITICAL**: Output ONLY the raw JSON object. NO markdown fences, NO explanatory text, NO commentary."""
    
    for section in sections:
        if section.get("id") == "output_format":
            section["content"] = output_format_content
            print("✅ Updated [OUTPUT FORMAT] with complete schema specification")
            break
    
    # Write back
    with open(agents_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"\n✓ WorkflowStrategyAgent finalized with {len(sections)} sections")
    print("  Standard structure: [ROLE] → [OBJECTIVE] → [CONTEXT] → [RUNTIME INTEGRATION] → [GUIDELINES] → [INSTRUCTIONS] → [EXAMPLES] → [JSON OUTPUT COMPLIANCE] → [OUTPUT FORMAT]")

if __name__ == "__main__":
    finalize_workflow_strategy_agent()
