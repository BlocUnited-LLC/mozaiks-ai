# Pattern Guidance Components - How They Work Together

## The Three Components in `inject_workflow_strategy_guidance`

When WorkflowStrategyAgent receives pattern guidance, it gets THREE distinct pieces of information that work together:

### 1. **phase_structure.coordination_pattern** 
**What it is:** A single descriptive sentence explaining HOW agents coordinate in this pattern.

**Example (Pipeline):**
```
"Sequential flow where each stage validates and transforms data before passing to next stage"
```

**Purpose:** 
- High-level mental model of the pattern's coordination logic
- Tells the agent "this is HOW agents talk to each other"
- NOT about specific phases - just the coordination philosophy

**Value:** Sets the framework for understanding WHY phases are structured a certain way.

---

### 2. **phase_structure.recommended_phases**
**What it is:** A **TEMPLATE** array of suggested phase structures with generic names.

**Example (Pipeline):**
```json
[
  {
    "name": "Entry & Validation Phase",
    "purpose": "Validate inputs and initialize pipeline",
    "typical_agents": ["Validator", "Entry Agent"]
  },
  {
    "name": "Processing Phase",
    "purpose": "Transform and enrich data",
    "typical_agents": ["Processor", "Transformer"]
  },
  {
    "name": "Finalization Phase",
    "purpose": "Complete pipeline and deliver results",
    "typical_agents": ["Finalizer", "Delivery Agent"]
  }
]
```

**Purpose:**
- **STARTING TEMPLATE** for phase design (not final answer!)
- Shows typical phase COUNT for this pattern (Pipeline = 3-5 stages, Hierarchical = 4 levels, etc.)
- Provides generic phase PURPOSES that should be adapted
- Suggests typical AGENT TYPES per phase

**What the agent MUST do:**
- READ the template
- ADAPT phase names to user's specific workflow ("Entry & Validation" → "Order Validation for E-Commerce")
- ADJUST phase count if needed (user might need 2 or 7 stages, template is just guidance)
- CUSTOMIZE specialist_domains to match user's actual domains
- USE the phase structure but RENAME everything to be workflow-specific

**Value:** Prevents the agent from designing phases from scratch. It has a proven template to start from.

---

### 3. **strategy_examples** (per pattern)
**What it is:** A **COMPLETE, REALISTIC EXAMPLE** of a `workflow_strategy(...)` call for a REAL workflow using this pattern.

**Example (Pipeline - Order Fulfillment):**
```python
workflow_strategy(
    workflow_name="Order Fulfillment Pipeline",
    workflow_description="When a customer submits an order, this workflow validates inventory, processes payment, and coordinates fulfillment to ensure accurate delivery.",
    trigger="form_submit",
    pattern="Pipeline",
    lifecycle_operations=[{
        "name": "Fraud Screening",
        "trigger": "before_agent",
        "target": null,
        "description": "Run fraud detection before initiating payment processing"
    }],
    phases=[
        {
            "phase_name": "Phase 1: Order Validation",
            "phase_description": "An intake processor verifies customer details, order completeness, and promotion eligibility.",
            "approval_required": false,
            "agents_needed": "single",
            "specialist_domains": ["order_intake"]
        },
        {
            "phase_name": "Phase 2: Inventory Confirmation",
            "phase_description": "A supply coordinator checks stock across warehouses, reserves items, and flags backorder scenarios.",
            "approval_required": false,
            "agents_needed": "single",
            "specialist_domains": ["inventory_management"]
        },
        {
            "phase_name": "Phase 3: Payment Processing",
            "phase_description": "A billing specialist charges the payment method, applies taxes, and records transaction receipts.",
            "approval_required": false,
            "agents_needed": "single",
            "specialist_domains": ["payment_operations"]
        },
        {
            "phase_name": "Phase 4: Fulfillment and Notification",
            "phase_description": "A logistics coordinator schedules shipment, updates tracking, and sends confirmation with next-step guidance.",
            "approval_required": false,
            "agents_needed": "single",
            "specialist_domains": ["logistics_management"]
        }
    ],
    strategy_notes="Each stage requires previous_stage_complete=true before handoff; errors raise has_error flag that routes customer to support remediation."
)
```

**Purpose:**
- Shows **EXACTLY** how to format the output
- Demonstrates **DOMAIN-SPECIFIC** naming (not generic!)
- Shows **REALISTIC** lifecycle_operations for this pattern
- Demonstrates **CONCRETE** specialist_domains (order_intake, inventory_management, payment_operations)
- Shows **PROPER** phase_description structure ("WHO does WHAT with WHAT outcome")
- Demonstrates strategy_notes that explain **PATTERN-SPECIFIC** coordination logic

**What the agent learns:**
- "Oh, phases should be named 'Phase N: Specific Purpose', not 'Phase 1: Entry'"
- "Phase descriptions should mention WHO (agent type) does WHAT (actions)"
- "specialist_domains should be workflow-specific domain tags (order_intake, not generic 'validation')"
- "lifecycle_operations should have business logic reasons, not generic 'validate inputs'"
- "strategy_notes should explain coordination mechanics specific to this pattern"

**Value:** Provides a CONCRETE REFERENCE so the agent doesn't guess at formatting or structure.

---

## How They Work Together (No Redundancy!)

### Step 1: Agent reads **coordination_pattern**
```
"Sequential flow where each stage validates and transforms data before passing to next stage"
```
**Agent thinks:** "Okay, this is a linear pipeline. Each phase must complete before the next starts. I need sequential handoffs."

---

### Step 2: Agent reads **recommended_phases** template
```json
[
  {"name": "Entry & Validation Phase", "purpose": "Validate inputs", "typical_agents": ["Validator"]},
  {"name": "Processing Phase", "purpose": "Transform data", "typical_agents": ["Processor"]},
  {"name": "Finalization Phase", "purpose": "Deliver results", "typical_agents": ["Finalizer"]}
]
```
**Agent thinks:** "Got it. Pipeline typically has 3-5 stages. Each stage has a clear input→transform→output flow. I'll need Entry, Processing, and Finalization phases at minimum."

---

### Step 3: Agent reads **strategy_example**
```python
phases=[
    {
        "phase_name": "Phase 1: Order Validation",
        "phase_description": "An intake processor verifies customer details, order completeness, and promotion eligibility.",
        "approval_required": false,
        "agents_needed": "single",
        "specialist_domains": ["order_intake"]
    },
    ...
]
```
**Agent thinks:** "Ah! So I don't use generic names. I adapt the template to the user's workflow. Instead of 'Entry & Validation Phase', I'll call it 'Phase 1: Customer Intake' or whatever fits the user's automation. And I need to be SPECIFIC about domains, not generic."

---

### Step 4: Agent produces OUTPUT (adapted to user's workflow)

**User's workflow:** "Automate blog post creation with review"

**Agent's output:**
```python
workflow_strategy(
    workflow_name="Blog Post Creation Pipeline",
    workflow_description="When a marketer requests blog content, this workflow drafts, reviews, and publishes posts to ensure quality and brand consistency.",
    trigger="chat",
    pattern="Pipeline",  # ← Came from upstream PatternAgent
    lifecycle_operations=[{
        "name": "SEO Validation",
        "trigger": "before_agent",
        "target": "PublishAgent",
        "description": "Verify SEO requirements met before publishing"
    }],
    phases=[
        {
            "phase_name": "Phase 1: Content Planning",  # ← Adapted "Entry & Validation"
            "phase_description": "A content strategist gathers topic requirements, target keywords, and audience goals to create a content brief.",  # ← Workflow-specific
            "approval_required": false,
            "agents_needed": "single",
            "specialist_domains": ["content_strategy"]  # ← Domain-specific, not generic "planning"
        },
        {
            "phase_name": "Phase 2: Draft Creation",  # ← Adapted "Processing"
            "phase_description": "A content writer generates the blog post draft following SEO guidelines and brand voice standards.",
            "approval_required": false,
            "agents_needed": "single",
            "specialist_domains": ["content_writing", "seo_optimization"]
        },
        {
            "phase_name": "Phase 3: Editorial Review",  # ← Added (user needs review)
            "phase_description": "An editor checks grammar, tone, and brand alignment, providing feedback for revisions if needed.",
            "approval_required": true,  # ← User-specific requirement
            "agents_needed": "single",
            "specialist_domains": ["editorial_review"]
        },
        {
            "phase_name": "Phase 4: Publication",  # ← Adapted "Finalization"
            "phase_description": "A publishing coordinator uploads the approved post to WordPress and schedules social media promotion.",
            "approval_required": false,
            "agents_needed": "single",
            "specialist_domains": ["content_publishing", "cms_integration"]
        }
    ],
    strategy_notes="Each phase requires previous_phase_complete flag; editorial approval blocks publication until approval_received=true; SEO validation runs before publish to ensure optimization standards met."
)
```

---

## Why This is NOT Redundant

### coordination_pattern
- **1 sentence** explaining the pattern's coordination philosophy
- **Generic** to the pattern, not workflow-specific
- **Mental model**, not a template

### recommended_phases
- **Template array** of 3-7 generic phases
- **Adaptable** - agent must rename and customize
- **Structure guidance**, not final answer

### strategy_examples
- **Complete realistic example** from a REAL workflow
- **Shows formatting**, naming conventions, and structure
- **Reference implementation**, not a template to copy

---

## Verification: Does This Align with ActionPlan?

**YES!** The ActionPlan expects:

```json
{
  "workflow": {
    "pattern": "Pipeline",  // ← From PatternAgent
    "phases": [
      {
        "phase_name": "Phase 1: Specific Purpose",  // ← From WorkflowStrategyAgent (adapted from recommended_phases template)
        "agents": [...]  // ← Populated by WorkflowArchitectAgent later
      }
    ]
  }
}
```

**Flow:**
1. **WorkflowStrategyAgent** uses recommended_phases as TEMPLATE → adapts to user's workflow → outputs workflow_strategy with customized phases
2. **WorkflowImplementationAgent** reads WorkflowStrategyAgent's output → creates ActionPlan with EXACT same phase structure
3. **Runtime** executes ActionPlan phases

**The injected guidance ensures WorkflowStrategyAgent produces phases that:**
- ✅ Match the pattern's typical structure (right phase count, right coordination flow)
- ✅ Are workflow-specific (not generic templates)
- ✅ Follow proper formatting (learned from strategy_examples)
- ✅ Align with ActionPlan structure downstream

---

## Summary

| Component | Purpose | Type | Example |
|-----------|---------|------|---------|
| **coordination_pattern** | Explain coordination philosophy | Descriptive sentence | "Sequential flow with validation gates" |
| **recommended_phases** | Provide phase structure template | Generic template array | [Entry Phase, Processing Phase, Final Phase] |
| **strategy_examples** | Show complete realistic example | Concrete reference implementation | Complete workflow_strategy(...) call for Order Fulfillment |

**No redundancy!** Each serves a distinct purpose:
- coordination_pattern = WHY (philosophy)
- recommended_phases = WHAT (structure template)
- strategy_examples = HOW (formatting + conventions)

All three together ensure the agent produces **explicit, domain-specific, properly-formatted workflow strategies** that work within the ActionPlan structure.
