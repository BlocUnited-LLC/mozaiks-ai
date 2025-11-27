# Human Interaction Consistency Strategy for Stateless Zero-Shot Agents

**Status**: Strategic Blueprint  
**Date**: January 2025  
**Problem**: Three stateless agents (WorkflowStrategy, WorkflowArchitect, WorkflowImplementation) must maintain perfect consistency in human interaction design without access to shared state or external files

---

## Executive Summary

### Two Critical Clarifications

#### 1. Validation Strategy: Agent Self-Validation (NOT Adjustment Loops)

**Question**: "Does validation mean validate-and-adjust loops? That would require handoff changes."

**Answer**: **NO adjustment loops.** We use **Agent Self-Validation** embedded in prompts:
- Agents validate their OWN outputs BEFORE emitting JSON (mental self-check during generation)
- Validation rules embedded as checklists in `[SELF-VALIDATION]` prompt sections
- If validation fails, agent corrects within same turn (no handoff back)
- NO runtime validation loops, NO handoff modifications needed
- Optional: Lightweight logging for telemetry (doesn't block execution)

**Why not validation loops?**
- Would require bidirectional handoffs (major architecture change)
- Adds latency + token cost for re-generation cycles
- Complex error handling (what if agent fails 3 times?)
- Agent self-validation achieves 80-95% effectiveness with ZERO infrastructure changes

**Why not placeholders?**
- Silently breaks user intent (workflow runs but does wrong thing)
- Hard to debug (hides real problems)
- Doesn't actually solve consistency

**Implementation**: Add `[SELF-VALIDATION CHECKLIST]` sections to agent prompts with embedded IF-THEN validation logic agents execute before emitting JSON.

---

#### 2. Pattern System: AG2 Orchestration Patterns (NOT Separate Approval/Feedback Patterns)

**Question**: "Where are these patterns? workflows/Generator/patterns/{pattern_name}.json? I don't think we have separate patterns or a PatternAgent that generates patterns."

**Answer**: You're right to be confused. Let me clarify:

**What "Patterns" Actually Are**:
- **AG2 Pattern Cookbook** orchestration patterns (9 total): Context-Aware Routing, Escalation, Feedback Loop, Hierarchical, Organic, Pipeline, Redundant, Star, Triage with Tasks
- These are AGENT COORDINATION patterns (how agents pass information, who talks to whom, sequential vs nested)
- **NOT** UI UI patterns or human approval workflows

**Where Pattern Examples Live**:
- ❌ **NOT** in `workflows/Generator/patterns/{pattern_name}.json` (this doesn't exist)
- ✅ **YES** in `workflows/Generator/tools/update_agent_state_pattern.py` (lines 200-4334)
- Pattern examples are **HARDCODED Python dictionaries** embedded in the tool file
- Each AG2 pattern (1-9) has example WorkflowStrategy/WorkflowArchitect/WorkflowImplementation outputs showing how to structure phases/agents for that orchestration pattern

**How Pattern Injection Works**:
1. **PatternAgent** (exists in agents.json line 55) selects AG2 pattern (1-9) based on user requirements
2. PatternAgent outputs: `{"PatternSelection": {"selected_pattern": 3, "pattern_name": "Feedback Loop"}}`
3. Runtime calls `update_agent_state_pattern.py` which reads selected pattern from context
4. Tool injects pattern-specific examples into downstream agents' `[PATTERN GUIDANCE AND EXAMPLES]` placeholder sections
5. Examples show how to structure phases/agents for that AG2 orchestration pattern (e.g., Feedback Loop = Phase 1 intake, Phase 2 generation, Phase 3 iterative refinement)

**What Pattern Examples DON'T Include**:
- ❌ Human interaction three-layer alignment examples (human_in_loop → ui_components → human_interaction)
- ❌ Display mode decision logic (inline vs artifact)
- ❌ UI pattern guidance (single_step vs two_step vs multi_step)
- ❌ Validation checklists for consistency

**Why Current Pattern Guidance Doesn't Solve Human Interaction Consistency**:
- Pattern guidance focuses on AG2 orchestration (phase structure, agent coordination)
- Human interaction logic is UNIVERSAL across all patterns (same rules apply whether Pipeline, Star, or Feedback Loop)
- Therefore: Embed human interaction decision trees DIRECTLY in agent prompts (not pattern-specific injection)

**Strategy**: Treat human interaction consistency as **universal logic** (not pattern-specific), embed in all three agents' prompts as canonical schemas + decision algorithms + validation checklists.

---

## Table of Contents

1. [Problem Statement](#problem-statement)
2. [Core Challenge](#core-challenge)
3. [Current Three-Layer Model](#current-three-layer-model)
4. [Why Inconsistency Happens](#why-inconsistency-happens)
5. [Solution Architecture](#solution-architecture)
6. [Implementation Strategy](#implementation-strategy)
7. [Validation Framework](#validation-framework)
8. [Pattern Injection System](#pattern-injection-system)
9. [Agent Prompt Design](#agent-prompt-design)
10. [Testing and Verification](#testing-and-verification)

---

## Problem Statement

### The Challenge

Human interaction is THE most crucial part of every workflow, yet maintaining consistency across three separate stateless agents is "nearly impossible" because:

1. **Stateless Constraint**: Agents are zero-shot prompts with NO access to:
   - External .md files or documentation
   - Previous execution history
   - Shared memory or state
   - File system

2. **Sequential Dependencies**: Each agent depends on upstream outputs:
   - WorkflowStrategy → defines `human_in_loop` (boolean intent)
   - WorkflowArchitect → defines `ui_components[]` (binding contracts)
   - WorkflowImplementation → defines `human_interaction` (execution mode)

3. **Complexity**: Human interaction involves multiple interconnected concepts:
   - Strategic intent (does phase need humans?)
   - UI surface contracts (what interactions, where, how complex?)
   - Agent execution mode (how does agent involve humans?)
   - Display modes (inline vs artifact)
   - UI patterns (single_step, two_step_confirmation, multi_step)
   - Tool types (UI_Tool vs Agent_Tool)

4. **Failure Modes**: Small deviations cascade:
   - Strategy says `human_in_loop=true` but Architect creates no UI components
   - Architect creates UI component with `display="artifact"` but Implementation creates `interaction_mode="none"` tool
   - Implementation sets `human_interaction="approval"` but no UI component exists
   - UI patterns don't match actual tool behavior

### Current State

Agents have documentation in:
- `HUMAN_INTERACTION_CONCEPTUAL_MODEL.md` (in root, not accessible to agents)
- `docs/workflows/UI_ui_patternS.md` (agents can't read files)
- Inline guidance in prompt sections (inconsistent, verbose)
- Pattern-specific examples (injected but may be incomplete)

**Result**: Inconsistencies slip through because each agent interprets the model slightly differently.

---

## Core Challenge

### The Stateless Zero-Shot Constraint

**What agents CANNOT do:**
- ❌ Read external markdown files
- ❌ Access documentation
- ❌ Query shared state
- ❌ Learn from past executions
- ❌ Coordinate with each other during execution

**What agents CAN do:**
- ✅ Read structured outputs from upstream agents (semantic wrappers)
- ✅ Follow inline guidance in their system prompts
- ✅ Execute decision trees based on upstream data
- ✅ Validate outputs against inline rules
- ✅ Receive pattern-specific examples injected at runtime

### The Intertwined Nature

Human interaction design requires THREE agents to work in perfect harmony:

```
WorkflowStrategy (Layer 1: Strategic Intent)
    ↓ human_in_loop: true/false per phase
    
WorkflowArchitect (Layer 2: UI Surface Contracts)
    ↓ ui_components: [{phase, agent, tool, display, ui_pattern}]
    
WorkflowImplementation (Layer 3: Agent Execution Mode)
    ↓ human_interaction: "context"|"approval"|"none" per agent
    + agent_tools: [{name, interaction_mode: "inline"|"artifact"|"none"}]
```

**The Contract**: These three layers MUST align perfectly or workflows break.

---

## Current Three-Layer Model

### Layer 1: Strategic Intent (WorkflowStrategy)

**Field**: `human_in_loop: boolean` (per phase)

**Decision Logic**:
```
Does this phase involve ANY human participation?
- User provides input/context → YES
- User reviews/approves content → YES
- User makes decisions → YES
- Fully automated (no human) → NO
```

**Example**:
```json
{
  "phases": [
    {"phase_name": "Phase 1: Interview", "human_in_loop": true},
    {"phase_name": "Phase 2: Processing", "human_in_loop": false},
    {"phase_name": "Phase 3: Review", "human_in_loop": true}
  ]
}
```

**Output**: Boolean flag signaling "this phase needs humans"

---

### Layer 2: UI Surface Contracts (WorkflowArchitect)

**Field**: `ui_components[]` (array of UI interaction specifications)

**Schema**:
```json
{
  "phase_name": "Phase 1: Interview",
  "agent": "InterviewAgent",
  "tool": "collect_requirements",
  "label": "Provide Requirements",
  "component": "RequirementsForm",
  "display": "inline|artifact",
  "ui_pattern": "single_step|two_step_confirmation|multi_step",
  "summary": "User provides project requirements via inline form"
}
```

**Key Fields**:

**`display`** (WHERE UI appears):
- `inline` → Embedded in chat flow (contextual, lightweight)
- `artifact` → Separate panel/tray (rich content, reviewed asynchronously)

**`ui_pattern`** (HOW complex):
- `single_step` → User acts immediately (submit form, click button)
- `two_step_confirmation` → User previews then confirms/rejects
- `multi_step` → Sequential wizard or iterative feedback loop

**Decision Logic**:
```
FOR EACH phase WHERE human_in_loop=true:
  - Determine if structured UI is needed (beyond plain text chat)
  - If yes:
    * Choose display: inline (simple) or artifact (complex)
    * Choose ui_pattern: single_step|two_step|multi_step
    * Define tool name, component name, labels
  - If no (just plain text chat):
    * Skip UI component creation
```

**Output**: Binding contracts that WorkflowImplementation MUST honor

---

### Layer 3: Agent Execution Mode (WorkflowImplementation)

**Field**: `human_interaction: "context"|"approval"|"none"` (per agent)

**Values**:
- `"context"` → Agent collects data from user (Q&A session)
- `"approval"` → Agent presents content for review/decision
- `"none"` → Agent operates autonomously (no human)

**Tool Field**: `interaction_mode: "inline"|"artifact"|"none"` (per tool)

**Decision Logic**:
```
FOR EACH agent:
  1. Check TechnicalBlueprint.ui_components for this phase + agent
  
  2. IF ui_component exists:
     - ui_pattern="single_step" → human_interaction="context"
     - ui_pattern="two_step_confirmation" → human_interaction="approval"
     - ui_pattern="multi_step" → human_interaction="approval"
     - Set tool.interaction_mode = ui_component.display value
  
  3. IF NO ui_component:
     - human_interaction="none"
     - Set tool.interaction_mode = "none"
```

**Output**: Agent execution specifications with tool interaction modes

---

## Why Inconsistency Happens

### 1. Interpretation Drift

Each agent interprets "human interaction" slightly differently:

**WorkflowStrategy thinks**:
- "Human in loop means user types in chat" → Sets `human_in_loop=true`
- But doesn't specify HOW user interacts

**WorkflowArchitect thinks**:
- "Human in loop means structured UI component needed"
- Creates UI component even when plain chat would work
- OR: "Doesn't seem complex enough" → Skips UI component creation

**WorkflowImplementation thinks**:
- "No UI component found, so human_interaction=none"
- Even though Strategy intended human participation via chat

**Result**: Layer 1 says YES, Layer 2 creates nothing, Layer 3 says NO → Inconsistent workflow

---

### 2. Display Mode Confusion

**What "inline" actually means**:
- Embedded in chat flow (not a separate panel)
- Can still be interactive (forms, buttons, cards)
- Doesn't interrupt conversation flow

**What "artifact" actually means**:
- Separate panel/tray delivery
- For rich, complex content
- Reviewed asynchronously

**Common mistake**:
- Architect creates `display="inline"` for simple input via text
- Implementation creates `interaction_mode="artifact"` tool
- UI renders in wrong location

---

### 3. UI pattern Misalignment

**What patterns mean**:
- `single_step`: User provides data once, agent continues (→ `human_interaction="context"`)
- `two_step_confirmation`: User reviews then approves/rejects (→ `human_interaction="approval"`)
- `multi_step`: Sequential wizard (→ `human_interaction="approval"`)

**Common mistakes**:
- Architect says `ui_pattern="single_step"`
- Implementation says `human_interaction="approval"`
- Runtime expects immediate continuation but agent waits for approval

---

### 4. Chat Interface vs UI Components

**The Confusion**:
- Chat interface = Transport mechanism (NOT a UI component)
- UI components = Interactive elements WITHIN chat

**Common mistake**:
- Strategy: `human_in_loop=true` (user types in chat)
- Architect: Creates UI component for "chat interaction"
- Implementation: Confused about whether agent uses plain text or structured UI

**Truth**:
- Plain text chat does NOT require a UI component
- UI components only for structured interactions beyond text

---

## Solution Architecture

### Core Principle: Inline Decision Trees

Since agents can't access external files, we embed **complete decision trees** directly in prompts that:

1. **Are self-contained**: No external references
2. **Are executable**: Step-by-step with concrete examples
3. **Cross-validate**: Each agent validates against upstream outputs
4. **Fail fast**: Detect inconsistencies and raise errors

### Three-Part Strategy

#### Part 1: Standardized Semantic Contracts

Define a **canonical schema** that all three agents understand identically:

```typescript
// Layer 1: Strategic Intent (WorkflowStrategy output)
interface Phase {
  phase_index: number;
  phase_name: string;
  phase_description: string;
  human_in_loop: boolean;  // "Does this phase need humans?"
  agents_needed: "single" | "sequential" | "nested";
}

// Layer 2: UI Surface Contract (WorkflowArchitect output)
interface UIComponent {
  phase_name: string;  // MUST match Phase.phase_name
  agent: string;       // PascalCase agent name
  tool: string;        // snake_case tool function name
  label: string;       // User-facing CTA
  component: string;   // React component name
  display: "inline" | "artifact";  // WHERE it renders
  ui_pattern: "single_step" | "two_step_confirmation" | "multi_step";  // HOW complex
  summary: string;     // User-facing description (<=200 chars)
}

// Layer 3: Agent Execution Mode (WorkflowImplementation output)
interface Agent {
  agent_name: string;  // MUST match UIComponent.agent if UI exists
  description: string;
  agent_tools: Tool[];
  human_interaction: "context" | "approval" | "none";  // Derived FROM ui_pattern
}

interface Tool {
  name: string;  // MUST match UIComponent.tool if UI exists
  integration: string | null;
  purpose: string;
  interaction_mode: "inline" | "artifact" | "none";  // MUST match UIComponent.display
}
```

**Key Insight**: These schemas are THE source of truth. Embed them in ALL three agent prompts.

---

#### Part 2: Deterministic Decision Algorithms

Each agent follows a **decision algorithm** that produces IDENTICAL results given the same inputs.

**WorkflowStrategy Decision Algorithm**:
```
FOR EACH phase:
  1. Analyze phase_description for keywords:
     - "review", "approve", "decide", "input", "feedback" → human_in_loop=TRUE
     - "analyze", "process", "generate" (automation only) → human_in_loop=FALSE
  
  2. If monetization_enabled=true AND phase delivers value to end user:
     → human_in_loop=TRUE (potential paywall)
  
  3. Default: If unsure, lean toward human_in_loop=FALSE
```

**WorkflowArchitect Decision Algorithm**:
```
FOR EACH phase WHERE human_in_loop=true:
  1. Determine if structured UI is needed:
     - Keywords in phase_description: "form", "input", "approval", "review", "wizard"
       → YES, structured UI
     - Otherwise (just "chat", "conversation", "dialogue")
       → NO, plain text chat (skip UI component)
  
  2. IF structured UI needed:
     a) Choose display mode:
        - Simple/quick interaction (1-3 fields, single action)
          → display="inline"
        - Complex/rich content (multi-section, detailed review, heavy data)
          → display="artifact"
     
     b) Choose ui_pattern:
        - User provides data once, agent continues
          → ui_pattern="single_step"
        - User reviews content then approves/rejects
          → ui_pattern="two_step_confirmation"
        - Sequential multi-step wizard or iterative feedback
          → ui_pattern="multi_step"
     
     c) Create UIComponent with:
        - phase_name = exact Phase.phase_name
        - agent = descriptive PascalCase name (e.g., "ApprovalAgent")
        - tool = descriptive snake_case name (e.g., "submit_approval")
        - component = React component name (e.g., "ApprovalCard")
        - display = inline|artifact (from step a)
        - ui_pattern = single_step|two_step|multi_step (from step b)
        - label = user-facing CTA (e.g., "Review & Approve")
        - summary = user-facing description (<= 200 chars)
  
  3. IF NO structured UI needed (plain chat):
     - Skip UIComponent creation
     - Let WorkflowImplementation know via absence of ui_component
```

**WorkflowImplementation Decision Algorithm**:
```
FOR EACH agent:
  1. Search TechnicalBlueprint.ui_components for entry matching:
     - ui_component.phase_name = this agent's phase
     - ui_component.agent = this agent's name
  
  2. IF ui_component FOUND:
     a) Derive human_interaction from ui_pattern:
        - ui_pattern="single_step"
          → human_interaction="context"
        - ui_pattern="two_step_confirmation"
          → human_interaction="approval"
        - ui_pattern="multi_step"
          → human_interaction="approval"
     
     b) Create agent_tool matching ui_component.tool:
        - name = ui_component.tool (exact match)
        - interaction_mode = ui_component.display (exact match: inline|artifact)
        - integration = null (UI tools don't use external services)
        - purpose = ui_component.summary
  
  3. IF NO ui_component FOUND:
     a) Check if phase has human_in_loop=true:
        - If YES → Agent uses plain text chat (no structured UI)
          * human_interaction="context" (conversational Q&A)
          * agent_tools = [] (no special tools, just chat)
        - If NO → Agent is fully autonomous
          * human_interaction="none"
          * agent_tools = backend/API tools only
  
  4. Validation:
     - IF ui_component exists BUT agent_tool NOT created → ERROR
     - IF agent_tool.name != ui_component.tool → ERROR
     - IF agent_tool.interaction_mode != ui_component.display → ERROR
     - IF agent.human_interaction conflicts with ui_pattern → ERROR
```

---

#### Part 3: Cross-Agent Validation

Each agent **validates** its output against upstream outputs using embedded validation rules.

**WorkflowStrategy Self-Validation**:
```python
# Embedded in WorkflowStrategy prompt
VALIDATION_RULES = """
Before emitting WorkflowStrategy output:
1. Count phases with human_in_loop=true
2. Verify phase_description justifies human_in_loop decision
3. Ensure at least ONE phase has human_in_loop=true (unless fully automated)
4. Flag: If monetization_enabled=true, expect human_in_loop in value-delivery phases
"""
```

**WorkflowArchitect Cross-Validation**:
```python
# Embedded in WorkflowArchitect prompt
VALIDATION_RULES = """
Before emitting TechnicalBlueprint output:
1. FOR EACH Phase WHERE human_in_loop=true:
   - Verify: Either ui_component exists OR phase_description clearly indicates plain chat
   - If ui_component created: Verify phase_name matches exactly
   - If no ui_component: Add note explaining "plain text chat used"

2. FOR EACH ui_component:
   - Verify: phase_name matches a real Phase.phase_name
   - Verify: display is "inline" OR "artifact" (not null)
   - Verify: ui_pattern is one of three valid values
   - Verify: summary field is <=200 chars and describes user action

3. Consistency Check:
   - Count ui_components vs count of human_in_loop=true phases
   - If mismatch: Document reason in agent_message
"""
```

**WorkflowImplementation Cross-Validation**:
```python
# Embedded in WorkflowImplementation prompt
VALIDATION_RULES = """
Before emitting PhaseAgents output:
1. FOR EACH ui_component from TechnicalBlueprint:
   - Verify: Agent exists with agent_name = ui_component.agent
   - Verify: Agent has tool with name = ui_component.tool
   - Verify: tool.interaction_mode = ui_component.display
   - Verify: agent.human_interaction matches ui_component.ui_pattern:
     * single_step → human_interaction="context"
     * two_step_confirmation|multi_step → human_interaction="approval"

2. FOR EACH agent with human_interaction != "none":
   - Verify: Either ui_component exists OR phase.human_in_loop=true
   - If no ui_component: Agent uses plain text chat (document in description)

3. FOR EACH agent with human_interaction="none":
   - Verify: NO ui_component exists for this agent
   - Verify: Phase.human_in_loop=false OR agent is backend/automation

4. Misalignment Detection:
   - IF ui_component exists BUT agent NOT found → ERROR (raise in output)
   - IF agent.human_interaction != expected_from_ui_pattern → ERROR
   - IF tool.interaction_mode != ui_component.display → ERROR
"""
```

---

## Implementation Strategy

### Phase 1: Embed Canonical Schemas (Week 1)

**Goal**: Ensure all three agents understand the same data structures

**Actions**:
1. Add schema definitions to ALL three agent prompts in `[CONTEXT]` sections
2. Use TypeScript-style interfaces for clarity (agents understand these)
3. Include examples showing correct vs incorrect usage

**Template for each agent**:
```markdown
## [CONTEXT]

### Canonical Schema Definitions (THE SOURCE OF TRUTH)

You MUST understand these exact structures when reading upstream outputs and creating your own:

**Layer 1: Strategic Intent (WorkflowStrategy output)**
```typescript
interface Phase {
  phase_index: number;           // Sequential 0-based index
  phase_name: string;            // "Phase N: Purpose"
  phase_description: string;     // What happens in this phase
  human_in_loop: boolean;        // Does this phase need ANY human participation?
  agents_needed: "single" | "sequential" | "nested";
}
```

INTERPRETATION RULES:
- human_in_loop=true: Phase expects human input, review, or decision
- human_in_loop=false: Phase is fully automated (no human interaction)
- This is STRATEGIC INTENT, not implementation details
- Downstream agents decide HOW humans participate

**Layer 2: UI Surface Contract (WorkflowArchitect output)**
```typescript
interface UIComponent {
  phase_name: string;         // MUST match Phase.phase_name exactly
  agent: string;              // PascalCase agent name
  tool: string;               // snake_case tool function name
  label: string;              // User-facing button/action text
  component: string;          // React component name (PascalCase)
  display: "inline" | "artifact";  // WHERE UI renders
  ui_pattern: "single_step" | "two_step_confirmation" | "multi_step";  // HOW complex
  summary: string;            // User-facing description (<=200 chars)
}
```

INTERPRETATION RULES:
- display="inline": Embedded in chat flow (contextual, lightweight)
- display="artifact": Separate tray/panel (rich content, async review)
- ui_pattern="single_step": User acts, agent continues (→ human_interaction="context")
- ui_pattern="two_step_confirmation": User reviews then approves/rejects (→ human_interaction="approval")
- ui_pattern="multi_step": Sequential wizard or iterative loop (→ human_interaction="approval")
- BINDING CONTRACT: WorkflowImplementation MUST honor these exact specifications

**Layer 3: Agent Execution Mode (WorkflowImplementation output)**
```typescript
interface Agent {
  agent_name: string;         // MUST match UIComponent.agent if UI exists
  description: string;
  agent_tools: Tool[];
  human_interaction: "context" | "approval" | "none";  // Derived FROM ui_pattern
}

interface Tool {
  name: string;               // MUST match UIComponent.tool if UI exists
  integration: string | null;
  purpose: string;
  interaction_mode: "inline" | "artifact" | "none";  // MUST match UIComponent.display
}
```

INTERPRETATION RULES:
- human_interaction="context": Agent collects data from user (Q&A, forms)
- human_interaction="approval": Agent presents content for review/decision
- human_interaction="none": Agent operates autonomously (no human)
- interaction_mode MUST match ui_component.display (inline|artifact) OR be "none" if no UI
- Tool name MUST match ui_component.tool if UI exists
```

**Validation**: Grep agents.json to confirm schemas appear in all three agents' `[CONTEXT]` sections

---

### Phase 2: Embed Decision Algorithms (Week 2)

**Goal**: Provide executable step-by-step logic each agent follows

**Actions**:
1. Replace vague guidance with concrete decision trees
2. Add "IF-THEN" logic that's deterministic
3. Include validation checkpoints

**Template additions**:

**For WorkflowStrategy** (add to `[INSTRUCTIONS]` section):
```markdown
### Step X - Determine human_in_loop for Each Phase

DECISION ALGORITHM:

FOR EACH phase in your workflow design:
  1. Analyze phase_description for keywords indicating human participation:
     
     HUMAN PARTICIPATION INDICATORS (→ human_in_loop=TRUE):
     - "review", "approve", "reject", "decide", "choose", "select"
     - "input", "provide", "submit", "enter", "fill out"
     - "feedback", "comment", "revise", "adjust", "modify"
     - "confirm", "validate", "verify", "check"
     
     AUTOMATION INDICATORS (→ human_in_loop=FALSE):
     - "analyze", "process", "calculate", "compute", "generate"
     - "fetch", "query", "load", "retrieve", "extract"
     - "transform", "parse", "format", "normalize"
     - "send" (automated notification), "update" (automated DB write)
  
  2. Apply special rules:
     - IF monetization_enabled=true AND phase delivers value to end user:
       → Consider human_in_loop=TRUE (potential paywall/approval gate)
     
     - IF phase involves external API calls that require user credentials:
       → human_in_loop=TRUE (user provides API keys)
     
     - IF phase produces content user MUST review before proceeding:
       → human_in_loop=TRUE (approval gate)
  
  3. Default logic:
     - When in doubt, favor human_in_loop=FALSE (automation by default)
     - ONLY set TRUE when human participation is EXPLICIT in requirements
  
  4. Validate phase-level consistency:
     - At least ONE phase should have human_in_loop=TRUE (unless fully automated)
     - Final phase typically has human_in_loop=TRUE (results delivery)

EXAMPLE CORRECT DECISIONS:
- "Phase 1: User Interview" → human_in_loop=TRUE (user provides context)
- "Phase 2: Data Processing" → human_in_loop=FALSE (automated analysis)
- "Phase 3: Review & Approval" → human_in_loop=TRUE (user reviews results)
```

**For WorkflowArchitect** (add to `[INSTRUCTIONS]` section):
```markdown
### Step X - Design UI Components for human_in_loop Phases

DECISION ALGORITHM:

FOR EACH phase WHERE WorkflowStrategy.human_in_loop=TRUE:
  
  STEP 1: Determine if structured UI is needed
  ----------------------------------------
  Analyze phase_description for interaction type:
  
  STRUCTURED UI REQUIRED (create ui_component):
  - "form", "input fields", "wizard", "multi-step"
  - "approval card", "review panel", "feedback form"
  - "dropdown", "checkbox", "radio button", "file upload"
  - "scoring", "rating", "ranking", "selection grid"
  
  PLAIN TEXT CHAT SUFFICIENT (skip ui_component):
  - "chat", "conversation", "dialogue", "discuss"
  - "ask questions", "clarify", "explain" (conversational Q&A)
  - No mention of forms, buttons, or structured inputs
  
  IF structured UI NOT needed:
    - Do NOT create ui_component entry
    - Document in agent_message: "Phase X uses plain text chat interaction"
    - STOP here for this phase
  
  IF structured UI IS needed:
    → Continue to STEP 2
  
  STEP 2: Choose display mode
  ----------------------------
  Assess interaction complexity from phase_description:
  
  USE display="inline" WHEN:
  - Simple interaction (1-5 fields max)
  - Quick action (single button click, short form)
  - Contextual input (appears naturally in conversation flow)
  - Examples: API key input, simple confirmation, short feedback form
  
  USE display="artifact" WHEN:
  - Complex content (multi-section, rich formatting)
  - Detailed review needed (long documents, comprehensive data)
  - Async review expected (user needs time to digest)
  - Examples: Full action plan review, detailed analytics dashboard, multi-page report
  
  STEP 3: Choose ui_pattern
  -----------------------------------
  Determine interaction cadence from phase_description:
  
  USE ui_pattern="single_step" WHEN:
  - User provides data once, agent continues immediately
  - No approval/review cycle needed
  - Examples: "User enters budget amount and continues", "User uploads file"
  
  USE ui_pattern="two_step_confirmation" WHEN:
  - User reviews content THEN approves/rejects
  - Approval gate or decision point
  - Examples: "Review action plan and approve to proceed", "Confirm payment details"
  
  USE ui_pattern="multi_step" WHEN:
  - Sequential wizard (Step 1 → Step 2 → Step 3)
  - Iterative refinement (user provides feedback multiple times)
  - Examples: "3-step campaign setup wizard", "Iterative design review cycle"
  
  STEP 4: Create UIComponent entry
  ---------------------------------
  Populate fields:
  - phase_name: Exact Phase.phase_name from WorkflowStrategy
  - agent: Descriptive PascalCase name (e.g., "ApprovalAgent", "InputAgent")
  - tool: Descriptive snake_case name (e.g., "submit_approval", "collect_requirements")
  - label: User-facing CTA (e.g., "Review & Approve", "Enter Requirements")
  - component: React component name (e.g., "ApprovalCard", "RequirementsForm")
  - display: "inline" or "artifact" (from STEP 2)
  - ui_pattern: "single_step", "two_step_confirmation", or "multi_step" (from STEP 3)
  - summary: User-facing description explaining what happens (<=200 chars)
  
  STEP 5: Validate UIComponent
  -----------------------------
  - Verify phase_name matches a real phase from WorkflowStrategy
  - Verify display is "inline" OR "artifact" (not null, not other values)
  - Verify ui_pattern is one of three valid values
  - Verify summary is concise and user-friendly

VALIDATION BEFORE OUTPUT:
- Count ui_components created
- Count phases with human_in_loop=true
- IF counts don't match: Document reason in agent_message
- Reason examples: "Phase 2 uses plain text chat (no UI component needed)"
```

**For WorkflowImplementation** (add to `[INSTRUCTIONS]` section):
```markdown
### Step X - Determine human_interaction Mode for Each Agent

DECISION ALGORITHM:

FOR EACH agent you design:
  
  STEP 1: Search for UIComponent
  -------------------------------
  Query TechnicalBlueprint.ui_components[] for entry matching:
  - ui_component.phase_name = this agent's phase name
  - ui_component.agent = this agent's name
  
  STEP 2: IF UIComponent FOUND:
  ------------------------------
  Derive human_interaction from ui_component.ui_pattern:
  
  MAPPING RULES (MUST FOLLOW EXACTLY):
  - ui_pattern="single_step"
    → human_interaction="context"
    → Rationale: User provides data, agent continues
  
  - ui_pattern="two_step_confirmation"
    → human_interaction="approval"
    → Rationale: User reviews then approves/rejects
  
  - ui_pattern="multi_step"
    → human_interaction="approval"
    → Rationale: Multi-step typically involves review cycles
  
  Create agent_tool matching ui_component:
  - name: ui_component.tool (EXACT MATCH - no variations)
  - interaction_mode: ui_component.display (EXACT MATCH: "inline" or "artifact")
  - integration: null (UI tools don't use external services)
  - purpose: ui_component.summary (copy description)
  
  STEP 3: IF NO UIComponent FOUND:
  ---------------------------------
  Check phase-level human_in_loop flag:
  
  IF Phase.human_in_loop=TRUE:
    - Agent uses plain text chat (no structured UI)
    - human_interaction="context" (conversational Q&A)
    - agent_tools: Empty array OR backend tools only
    - Document in description: "Agent engages in conversational interaction"
  
  IF Phase.human_in_loop=FALSE:
    - Agent is fully autonomous
    - human_interaction="none"
    - agent_tools: Backend/API tools only (interaction_mode="none")
    - Document in description: "Agent operates autonomously"
  
  STEP 4: Create Agent Tools
  ---------------------------
  FOR EACH agent_tool:
  - IF matches ui_component: Use ui_component.tool name and display mode
  - IF backend tool: Use descriptive snake_case name, interaction_mode="none"
  
  STEP 5: Validate Agent Specification
  -------------------------------------
  Run these checks before emitting:
  
  CRITICAL VALIDATION RULES:
  1. IF ui_component exists for this agent:
     - MUST have agent_tool with name = ui_component.tool
     - MUST have agent_tool.interaction_mode = ui_component.display
     - MUST have human_interaction matching ui_pattern mapping
  
  2. IF human_interaction="approval":
     - MUST have ui_component with ui_pattern="two_step_confirmation" OR "multi_step"
  
  3. IF human_interaction="context" AND ui_component exists:
     - MUST have ui_component with ui_pattern="single_step"
  
  4. IF human_interaction="none":
     - MUST NOT have any ui_component for this agent
     - MUST have Phase.human_in_loop=FALSE OR agent is backend support
  
  ERROR CONDITIONS (raise in output):
  - ui_component exists but agent_tool NOT created → ERROR
  - agent_tool.name != ui_component.tool → ERROR
  - agent_tool.interaction_mode != ui_component.display → ERROR
  - human_interaction conflicts with ui_pattern mapping → ERROR

EXAMPLE VALIDATION SCENARIOS:

SCENARIO A: Correct Alignment
- UIComponent: {agent="ApprovalAgent", tool="submit_approval", display="artifact", ui_pattern="two_step_confirmation"}
- Agent: {agent_name="ApprovalAgent", human_interaction="approval"}
- Tool: {name="submit_approval", interaction_mode="artifact"}
✅ VALID - Everything aligns

SCENARIO B: Misalignment Error
- UIComponent: {agent="InputAgent", tool="collect_data", display="inline", ui_pattern="single_step"}
- Agent: {agent_name="InputAgent", human_interaction="approval"}  ❌ WRONG
- Tool: {name="collect_data", interaction_mode="inline"}
❌ ERROR - human_interaction should be "context" for single_step pattern

SCENARIO C: Missing Tool Error
- UIComponent: {agent="ReviewAgent", tool="submit_review", display="artifact", ui_pattern="multi_step"}
- Agent: {agent_name="ReviewAgent", human_interaction="approval"}
- Tool: MISSING  ❌ WRONG
❌ ERROR - Agent must have tool named "submit_review"
```

**Validation**: Test with sample inputs to ensure deterministic outputs

---

### Phase 3: Pattern-Specific Examples (Week 3)

**Goal**: Provide complete working examples for common patterns

**Strategy**: Inject pattern-specific guidance showing correct three-layer alignment

**Example for "Approval Workflow" Pattern**:

```markdown
## [PATTERN GUIDANCE] Approval Workflow Pattern

This pattern coordinates human approval gates across workflow phases.

### Three-Layer Alignment Example

**Layer 1: WorkflowStrategy**
```json
{
  "phases": [
    {"phase_index": 0, "phase_name": "Phase 1: Draft Generation", "human_in_loop": false},
    {"phase_index": 1, "phase_name": "Phase 2: Review & Approval", "human_in_loop": true},
    {"phase_index": 2, "phase_name": "Phase 3: Publication", "human_in_loop": false}
  ]
}
```

**Layer 2: WorkflowArchitect**
```json
{
  "ui_components": [
    {
      "phase_name": "Phase 2: Review & Approval",
      "agent": "ApprovalAgent",
      "tool": "submit_approval_decision",
      "label": "Review & Approve",
      "component": "ApprovalCard",
      "display": "artifact",
      "ui_pattern": "two_step_confirmation",
      "summary": "User reviews generated draft in artifact tray and approves or requests revisions"
    }
  ]
}
```

**Layer 3: WorkflowImplementation**
```json
{
  "phase_agents": [
    {
      "phase_index": 1,
      "agents": [
        {
          "agent_name": "ApprovalAgent",
          "human_interaction": "approval",
          "agent_tools": [
            {
              "name": "submit_approval_decision",
              "interaction_mode": "artifact",
              "integration": null,
              "purpose": "User reviews generated draft and approves or requests revisions"
            }
          ]
        }
      ]
    }
  ]
}
```

### Validation Checklist for Approval Pattern

✅ Phase 2 has human_in_loop=true (approval phase needs human)  
✅ UI component exists for Phase 2  
✅ UI component has display="artifact" (complex content review)  
✅ UI component has ui_pattern="two_step_confirmation" (review→approve/reject)  
✅ Agent has human_interaction="approval" (matches two_step pattern)  
✅ Agent tool has name="submit_approval_decision" (matches ui_component.tool)  
✅ Agent tool has interaction_mode="artifact" (matches ui_component.display)  
```

**Implementation**: Create pattern-specific examples for:
- Approval Workflow
- Feedback Loop
- Wizard Flow
- Data Collection
- Content Review

---

### Phase 4: Validation Framework (Week 4)

**Goal**: Provide agents with inline self-validation logic (NOT runtime validation loops)

**CRITICAL CLARIFICATION - Two Validation Approaches**:

#### Approach A: Agent Self-Validation (Embedded in Prompts) ✅ RECOMMENDED
**What it is**: Agents validate their OWN outputs before emitting JSON using embedded checklists
**How it works**:
- Agent prompt contains validation rules like: "Before emitting output, verify human_interaction matches ui_pattern mapping"
- Agent performs mental self-check during generation
- If validation fails, agent corrects within same turn
- NO handoff adjustments needed; NO external validation loops

**Pros**:
- Zero infrastructure changes
- Works with current handoff system
- Agents self-correct before output
- No coordination complexity

**Cons**:
- Relies on LLM following instructions
- Can't guarantee 100% compliance
- May need stronger prompting to enforce

#### Approach B: Runtime Validation with Adjustment Loops ❌ NOT RECOMMENDED
**What it is**: Runtime validates outputs between agents and forces re-generation if misaligned
**How it works**:
1. WorkflowStrategy emits output → Runtime validates → If errors, send back to WorkflowStrategy with correction instructions
2. WorkflowArchitect emits output → Runtime validates against Strategy → If errors, send back with correction instructions
3. WorkflowImplementation emits output → Runtime validates against Architect → If errors, send back

**Pros**:
- Guaranteed validation enforcement
- Can catch ALL inconsistencies
- Provides real error messages

**Cons**:
- **REQUIRES MAJOR HANDOFF CHANGES**: Current handoffs are one-way; would need bidirectional feedback loops
- Adds latency (re-generation cycles)
- Complex error handling (what if agent fails validation 3 times?)
- Token cost multiplier (each re-gen burns tokens)

#### Approach C: Runtime Validation with Placeholders ⚠️ POSSIBLE BUT RISKY
**What it is**: Runtime detects misalignments and inserts safe placeholder values to prevent crashes
**How it works**:
- WorkflowImplementation emits agent with `human_interaction="approval"` but no UI component
- Runtime detects mismatch, injects placeholder: `{name: "placeholder_tool", interaction_mode: "none"}`
- Workflow continues but may not function correctly

**Pros**:
- No handoff changes needed
- Prevents runtime crashes
- Allows workflow completion

**Cons**:
- **SILENTLY BREAKS USER INTENT**: Workflow runs but does the wrong thing
- Hard to debug (placeholders hide real problems)
- User sees broken workflow behavior with no error message
- Doesn't actually solve consistency problem

---

### RECOMMENDED STRATEGY: Approach A (Agent Self-Validation)

**Implementation**: Embed validation checklists in agent prompts

**Example for WorkflowImplementation**:

**1. Add Validation Section to Prompt**:
```markdown
### [SELF-VALIDATION CHECKLIST]

Before emitting your final JSON output, mentally verify:

✅ **FOR EACH agent with ui_component**:
   - Agent has tool with name = ui_component.tool (EXACT MATCH)
   - Tool has interaction_mode = ui_component.display (EXACT MATCH)
   - Agent has human_interaction matching this mapping:
     * ui_pattern="single_step" → human_interaction="context"
     * ui_pattern="two_step_confirmation" → human_interaction="approval"
     * ui_pattern="multi_step" → human_interaction="approval"

✅ **FOR EACH agent with human_interaction="approval"**:
   - Agent MUST have ui_component with ui_pattern="two_step_confirmation" OR "multi_step"
   - If no ui_component exists → ERROR, change to human_interaction="none"

✅ **FOR EACH agent with human_interaction="none"**:
   - NO ui_component should exist for this agent
   - Phase should have human_in_loop=false OR agent is backend support

❌ **IF ANY CHECK FAILS**:
   - DO NOT emit the JSON yet
   - Correct the error within this turn
   - Re-run validation checklist
   - Only emit when ALL checks pass
```

**2. Optional: Add Error Detection Instruction**:
```markdown
### [ERROR HANDLING]

If you detect validation errors during self-check:
1. Identify the specific misalignment (e.g., "Agent 'ReviewAgent' has human_interaction='approval' but no ui_component exists")
2. Determine root cause:
   - Did WorkflowArchitect forget to create ui_component? → Assume plain text chat, change to human_interaction="context"
   - Did I misread the ui_pattern? → Re-check mapping and correct
3. Apply correction and re-validate
4. Emit corrected JSON

NEVER emit JSON that fails validation checks.
```

**No Runtime Validation Code Needed** - Just stronger agent prompts

---

### Alternative: Lightweight Runtime Logging (Not Validation)

If you want visibility into consistency WITHOUT adjustment loops:

**Post-Generation Logging**:
```python
def log_consistency_metrics(strategy, blueprint, phase_agents):
    """Log consistency issues for monitoring (does NOT block or adjust)."""
    issues = []
    
    # Check ui_component alignment
    ui_components_map = {(uc["phase_name"], uc["agent"]): uc for uc in blueprint["ui_components"]}
    
    for phase in phase_agents["phase_agents"]:
        phase_name = strategy["phases"][phase["phase_index"]]["phase_name"]
        for agent in phase["agents"]:
            key = (phase_name, agent["agent_name"])
            ui_component = ui_components_map.get(key)
            
            if ui_component:
                # Check tool existence
                tool_names = [t["name"] for t in agent["agent_tools"]]
                if ui_component["tool"] not in tool_names:
                    issues.append(f"⚠️ Agent {agent['agent_name']}: missing tool '{ui_component['tool']}'")
                
                # Check interaction_mode
                tool = next((t for t in agent["agent_tools"] if t["name"] == ui_component["tool"]), None)
                if tool and tool["interaction_mode"] != ui_component["display"]:
                    issues.append(f"⚠️ Agent {agent['agent_name']}: tool interaction_mode mismatch")
    
    if issues:
        logger.warning(f"Consistency issues detected:\n" + "\n".join(issues))
        # Store in observability metrics for dashboard
    else:
        logger.info("✅ All consistency checks passed")
```

**Use case**: Telemetry/monitoring to track how often inconsistencies happen, but doesn't block workflow execution

---

### Summary: Validation Strategy Decision

| Approach | Implementation Effort | Handoff Changes | Effectiveness | Recommendation |
|----------|----------------------|-----------------|---------------|----------------|
| A: Agent Self-Validation | Low (prompt updates) | None | 80-95% | ✅ **USE THIS** |
| B: Runtime Validation Loops | High (bidirectional handoffs) | Major | 99%+ | ❌ Too complex |
| C: Runtime Placeholders | Medium (detection + injection) | None | 0% (hides bugs) | ❌ Silently breaks |
| Logging Only | Low (add metrics) | None | 0% (monitoring only) | ✅ Supplement to A |

**Final Recommendation**: Use **Approach A (Agent Self-Validation)** with optional logging for telemetry

**2. Post-Architect Validation**:
```python
def validate_technical_blueprint(blueprint, strategy):
    """Cross-validate TechnicalBlueprint against WorkflowStrategy."""
    errors = []
    
    # Check ui_components align with human_in_loop phases
    human_phases = [p for p in strategy["phases"] if p["human_in_loop"]]
    ui_phase_names = [uc["phase_name"] for uc in blueprint["ui_components"]]
    
    for phase in human_phases:
        if phase["phase_name"] not in ui_phase_names:
            # Not an error if plain text chat is used, but should be documented
            errors.append(f"INFO: Phase '{phase['phase_name']}' has human_in_loop=true but no UI component. Using plain chat?")
    
    # Validate ui_component fields
    for uc in blueprint["ui_components"]:
        # Check phase_name exists
        if uc["phase_name"] not in [p["phase_name"] for p in strategy["phases"]]:
            errors.append(f"UI component references unknown phase: {uc['phase_name']}")
        
        # Check display mode
        if uc["display"] not in ["inline", "artifact"]:
            errors.append(f"Invalid display mode: {uc['display']} (must be inline or artifact)")
        
        # Check ui_pattern
        valid_patterns = ["single_step", "two_step_confirmation", "multi_step"]
        if uc["ui_pattern"] not in valid_patterns:
            errors.append(f"Invalid ui_pattern: {uc['ui_pattern']}")
        
        # Check summary length
        if len(uc["summary"]) > 200:
            errors.append(f"UI component summary too long: {len(uc['summary'])} chars (max 200)")
    
    return errors
```

**3. Post-Implementation Validation**:
```python
def validate_phase_agents(phase_agents, blueprint, strategy):
    """Cross-validate PhaseAgents against TechnicalBlueprint and WorkflowStrategy."""
    errors = []
    
    # Build lookup maps
    ui_components_map = {}
    for uc in blueprint["ui_components"]:
        key = (uc["phase_name"], uc["agent"])
        ui_components_map[key] = uc
    
    # Validate each agent
    for phase in phase_agents["phase_agents"]:
        phase_name = strategy["phases"][phase["phase_index"]]["phase_name"]
        
        for agent in phase["agents"]:
            agent_name = agent["agent_name"]
            key = (phase_name, agent_name)
            
            # Check if UI component exists
            ui_component = ui_components_map.get(key)
            
            if ui_component:
                # UI component exists - validate alignment
                
                # Check human_interaction mapping
                ui_pattern = ui_component["ui_pattern"]
                expected_human_interaction = {
                    "single_step": "context",
                    "two_step_confirmation": "approval",
                    "multi_step": "approval"
                }[ui_pattern]
                
                if agent["human_interaction"] != expected_human_interaction:
                    errors.append(
                        f"Agent {agent_name}: human_interaction='{agent['human_interaction']}' "
                        f"doesn't match ui_pattern='{ui_pattern}' "
                        f"(expected '{expected_human_interaction}')"
                    )
                
                # Check tool exists
                tool_names = [t["name"] for t in agent["agent_tools"]]
                if ui_component["tool"] not in tool_names:
                    errors.append(
                        f"Agent {agent_name}: missing tool '{ui_component['tool']}' "
                        f"required by UI component"
                    )
                else:
                    # Check tool interaction_mode
                    tool = next(t for t in agent["agent_tools"] if t["name"] == ui_component["tool"])
                    if tool["interaction_mode"] != ui_component["display"]:
                        errors.append(
                            f"Agent {agent_name}: tool '{tool['name']}' has "
                            f"interaction_mode='{tool['interaction_mode']}' but "
                            f"UI component has display='{ui_component['display']}'"
                        )
            
            else:
                # No UI component - check consistency
                if agent["human_interaction"] != "none":
                    # Agent has human interaction but no UI component
                    # This is OK if using plain text chat
                    phase_human_in_loop = strategy["phases"][phase["phase_index"]]["human_in_loop"]
                    if not phase_human_in_loop:
                        errors.append(
                            f"Agent {agent_name}: has human_interaction='{agent['human_interaction']}' "
                            f"but phase has human_in_loop=false and no UI component exists"
                        )
    
    return errors
```

**4. Master Validation Runner**:
```python
def validate_generator_workflow(strategy, blueprint, phase_agents):
    """Run all validation checks and report errors."""
    all_errors = []
    
    all_errors.extend(validate_workflow_strategy(strategy))
    all_errors.extend(validate_technical_blueprint(blueprint, strategy))
    all_errors.extend(validate_phase_agents(phase_agents, blueprint, strategy))
    
    if all_errors:
        print("❌ VALIDATION ERRORS FOUND:")
        for error in all_errors:
            print(f"  - {error}")
        return False
    else:
        print("✅ All validation checks passed!")
        return True
```

---

## Pattern Injection System

### How Pattern Guidance Works

Pattern-specific examples are **injected at runtime** via the `update_agent_state_pattern` hook:

**Current Mechanism**:
1. PatternAgent selects pattern (1-9) from AG2 Pattern Cookbook (Context-Aware Routing, Pipeline, Feedback Loop, etc.)
2. Runtime executes `update_agent_state_pattern.py` which contains HARDCODED pattern-specific examples (embedded in Python file, lines 200-4334)
3. `update_agent_state_pattern` hook injects guidance into subsequent agents' `[PATTERN GUIDANCE AND EXAMPLES]` placeholder sections
4. Agents receive complete examples showing correct three-layer alignment for the selected AG2 orchestration pattern

**IMPORTANT CLARIFICATION**:
- There are NO separate JSON pattern files in `workflows/Generator/patterns/`
- Pattern examples are EMBEDDED as Python dictionaries inside `update_agent_state_pattern.py`
- Each AG2 pattern (1-9) has hardcoded examples for WorkflowStrategy, WorkflowArchitect, and WorkflowImplementation
- These examples show how to structure phases/agents for that specific orchestration pattern (e.g., Pipeline → sequential phases, Star → hub coordinator + spoke specialists)

**What Pattern Guidance Currently Includes** (from `update_agent_state_pattern.py`):

Pattern guidance is **AG2 orchestration-focused**, not human interaction-focused. Current examples show:
- How to structure phases for each AG2 pattern (e.g., Pipeline = sequential phases, Star = hub coordinator + spoke specialists)
- Agent coordination patterns (single agent, sequential, nested)
- Information flow between agents

**Example for Pattern 3 (Feedback Loop)**:
```python
strategy_examples = {
    3: """{
  "WorkflowStrategy": {
    "workflow_name": "Product Launch Copy Refinement",
    "pattern": ["Feedback Loop"],
    "phases": [
      {
        "phase_index": 0,
        "phase_name": "Phase 1: Stakeholder Interview",
        "phase_description": "Intake agent gathers campaign goals, brand voice, target audience, and high-level messaging themes from the user via conversational Q&A.",
        "human_in_loop": true,
        "agents_needed": "single"
      },
      {
        "phase_index": 1,
        "phase_name": "Phase 2: Initial Draft Generation",
        "phase_description": "Content agent synthesizes interview data into a first-pass draft covering all required pillars and channels.",
        "human_in_loop": false,
        "agents_needed": "single"
      },
      {
        "phase_index": 2,
        "phase_name": "Phase 3: Iterative Feedback and Refinement",
        "phase_description": "User reviews draft in structured form, scores each pillar, provides targeted revisions, and approves or requests next iteration.",
        "human_in_loop": true,
        "agents_needed": "sequential"
      }
    ]
  }
}"""
}
```

**CRITICAL GAPS IN CURRENT PATTERN GUIDANCE**:
1. ❌ **No human interaction consistency examples**: Current examples show AG2 orchestration (phases/agents) but NOT three-layer alignment (human_in_loop → ui_components → human_interaction)
2. ❌ **No validation checklists**: Examples don't include "what to verify" before emitting
3. ❌ **No display mode / ui_pattern guidance**: WorkflowArchitect examples exist but don't explain WHY inline vs artifact or single_step vs two_step

**Enhancement Recommendation**: 
**EITHER**:
- **Option A**: Extend existing pattern guidance with human interaction alignment examples (modify `update_agent_state_pattern.py` lines 200-4334)
- **Option B**: Create separate human interaction guidance that's injected alongside pattern guidance (new placeholder in agents.json)
- **Option C**: Embed human interaction decision trees directly in agent prompts (no pattern-specific injection needed)

**Recommendation**: Use **Option C** (embed in prompts) because human interaction logic is UNIVERSAL across all AG2 patterns, not pattern-specific

---

## Agent Prompt Design

### Universal Sections (All Three Agents)

Every agent should have these sections in their prompts:

**1. [CANONICAL SCHEMA DEFINITIONS]**
- Complete TypeScript-style interfaces
- Interpretation rules for each field
- Examples showing correct usage

**2. [THREE-LAYER MODEL OVERVIEW]**
- Brief explanation of Layer 1, 2, 3
- How layers connect and depend on each other
- This agent's role in the model

**3. [DECISION ALGORITHM]**
- Step-by-step executable logic
- IF-THEN rules with concrete examples
- Default behaviors when uncertain

**4. [VALIDATION RULES]**
- Self-validation checklist (before emitting output)
- Cross-validation rules (against upstream outputs)
- Error conditions that must be raised

**5. [PATTERN GUIDANCE AND EXAMPLES]**
- {{INJECTED_AT_RUNTIME}} placeholder
- Runtime injects complete pattern-specific examples
- Shows correct three-layer alignment for selected pattern

**6. [COMMON MISTAKES]**
- Examples of incorrect decisions
- Why they're wrong
- How to avoid them

---

### Agent-Specific Additions

**WorkflowStrategy Additional Sections**:
- `[HUMAN_IN_LOOP_DECISION_TREE]`: Keyword analysis rules
- `[PHASE_DESIGN_PATTERNS]`: Common phase structures

**WorkflowArchitect Additional Sections**:
- `[UI_COMPONENT_DECISION_TREE]`: When to create vs skip UI components
- `[DISPLAY_MODE_RULES]`: Inline vs artifact decision logic
- `[ui_pattern_RULES]`: Single vs two-step vs multi-step
- `[SUMMARY_WRITING_GUIDE]`: How to write user-facing descriptions

**WorkflowImplementation Additional Sections**:
- `[HUMAN_INTERACTION_MAPPING]`: ui_pattern → human_interaction rules
- `[TOOL_CREATION_RULES]`: When to create tools, naming conventions
- `[CROSS_VALIDATION_ALGORITHM]`: Complete validation logic with error handling

---

## Testing and Verification

### Test Cases

**Test Case 1: Simple Approval Workflow**
```
INPUT: User wants workflow where they review and approve generated content

EXPECTED OUTPUT:
- Strategy: Phase 1 (human_in_loop=false), Phase 2 (human_in_loop=true)
- Architect: UI component with display="artifact", ui_pattern="two_step_confirmation"
- Implementation: Agent with human_interaction="approval", tool with interaction_mode="artifact"

VALIDATION:
✅ All three layers align
✅ Tool name matches UI component tool
✅ Interaction modes match display modes
✅ human_interaction matches ui_pattern
```

**Test Case 2: Wizard Flow**
```
INPUT: User wants multi-step form collecting information progressively

EXPECTED OUTPUT:
- Strategy: Phase 1 (human_in_loop=true)
- Architect: UI component with display="inline", ui_pattern="multi_step"
- Implementation: Agent with human_interaction="approval", tool with interaction_mode="inline"

VALIDATION:
✅ Multi-step pattern maps to approval interaction
✅ Inline display for step-by-step progression
✅ Summary describes sequential steps
```

**Test Case 3: Plain Text Chat**
```
INPUT: User wants conversational Q&A with no forms

EXPECTED OUTPUT:
- Strategy: Phase 1 (human_in_loop=true)
- Architect: NO UI component (plain chat)
- Implementation: Agent with human_interaction="context", no UI tools

VALIDATION:
✅ No UI component created
✅ Agent uses conversational interaction
✅ No mismatch errors raised
```

**Test Case 4: Fully Automated**
```
INPUT: User wants background data processing with no human interaction

EXPECTED OUTPUT:
- Strategy: All phases (human_in_loop=false)
- Architect: NO UI components
- Implementation: All agents with human_interaction="none"

VALIDATION:
✅ No UI components created
✅ All agents autonomous
✅ Only backend tools present
```

---

### Validation Matrix

| Layer 1 | Layer 2 | Layer 3 | Expected Result |
|---------|---------|---------|-----------------|
| human_in_loop=true | UI component exists | human_interaction=context/approval | ✅ VALID |
| human_in_loop=true | NO UI component | human_interaction=context | ✅ VALID (plain chat) |
| human_in_loop=true | NO UI component | human_interaction=none | ❌ ERROR |
| human_in_loop=false | UI component exists | human_interaction=approval | ❌ ERROR |
| human_in_loop=false | NO UI component | human_interaction=none | ✅ VALID |
| ui_pattern=single_step | - | human_interaction=context | ✅ VALID |
| ui_pattern=two_step | - | human_interaction=approval | ✅ VALID |
| ui_pattern=multi_step | - | human_interaction=approval | ✅ VALID |
| ui_pattern=single_step | - | human_interaction=approval | ❌ ERROR |
| display=inline | - | interaction_mode=inline | ✅ VALID |
| display=artifact | - | interaction_mode=artifact | ✅ VALID |
| display=inline | - | interaction_mode=artifact | ❌ ERROR |

---

## Success Criteria

### Immediate Goals (Phase 1-2: 2 weeks)

1. ✅ All three agents have identical canonical schema definitions in prompts
2. ✅ All three agents have deterministic decision algorithms
3. ✅ Cross-validation logic embedded in each agent
4. ✅ Pattern-specific examples injected at runtime

### Medium-term Goals (Phase 3-4: 4 weeks)

1. ✅ 10+ pattern-specific examples created and tested
2. ✅ Runtime validation catches 95%+ of inconsistencies
3. ✅ Zero manual intervention needed for common patterns
4. ✅ Error messages guide agents to fix misalignments

### Long-term Goals (8+ weeks)

1. ✅ Self-healing: Agents detect and auto-correct inconsistencies
2. ✅ Learning: Pattern library grows from successful workflows
3. ✅ Metrics: Track consistency rate over time
4. ✅ Documentation: Auto-generate pattern guides from successful examples

---

## Appendix: Quick Reference

### Three-Layer Mapping Rules

```
ui_pattern → human_interaction
- single_step → context
- two_step_confirmation → approval
- multi_step → approval

display → interaction_mode
- inline → inline
- artifact → artifact
- (no UI component) → none

human_in_loop → UI component requirement
- true + plain chat → no UI component
- true + structured UI → UI component required
- false → no UI component
```

### Common Patterns

**Approval Gate**:
- human_in_loop=true
- display=artifact
- ui_pattern=two_step_confirmation
- human_interaction=approval
- interaction_mode=artifact

**Data Input**:
- human_in_loop=true
- display=inline
- ui_pattern=single_step
- human_interaction=context
- interaction_mode=inline

**Wizard**:
- human_in_loop=true
- display=inline
- ui_pattern=multi_step
- human_interaction=approval
- interaction_mode=inline

**Conversational**:
- human_in_loop=true
- NO UI component
- human_interaction=context
- NO UI tools

**Autonomous**:
- human_in_loop=false
- NO UI component
- human_interaction=none
- Backend tools only

---

**End of Document**

This strategy provides a complete roadmap for achieving consistency across stateless zero-shot agents by embedding decision trees, validation rules, and pattern examples directly into agent prompts. No external files needed—everything self-contained and deterministic.
