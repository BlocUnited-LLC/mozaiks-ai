# Pattern Guidance Symbiotic Relationships Analysis

## Executive Summary

The pattern guidance implementation plan was **INCOMPLETE** because it treated guidance as isolated content injection without accounting for the **structural contracts** that bind the Generator workflow together. This document maps the symbiotic relationships that pattern guidance MUST integrate with.

---

## 1. The Semantic Chain of Thought

### Data Flow Through Generator Workflow

```
User Interview
    ↓ (produces Interview wrapper)
PatternAgent
    ↓ (reads Interview, produces PatternSelection wrapper)
WorkflowStrategyAgent
    ↓ (reads PatternSelection, produces WorkflowStrategy wrapper)
WorkflowArchitectAgent (TechnicalBlueprint)
    ↓ (reads WorkflowStrategy, produces TechnicalBlueprint wrapper)
WorkflowImplementationAgent (PhaseAgents)
    ↓ (reads WorkflowStrategy + TechnicalBlueprint, produces PhaseAgents wrapper)
ProjectOverviewAgent
    ↓ (reads WorkflowStrategy + PhaseAgents, produces MermaidSequenceDiagram wrapper)
ContextVariablesAgent
    ↓ (reads ActionPlan + PhaseAgents + ToolsManifest, produces ContextVariablesPlan wrapper)
ToolsManagerAgent
    ↓ (reads WorkflowStrategy + TechnicalBlueprint + PhaseAgents, produces ToolsManifest wrapper)
StructuredOutputsAgent
    ↓ (reads PhaseAgents, produces StructuredOutputsRegistry wrapper)
AgentsAgent
    ↓ (reads ALL upstream wrappers, produces AgentDefinitions wrapper)
HandoffsAgent
    ↓ (reads PhaseAgents + ContextVariablesPlan, produces HandoffRules wrapper)
OrchestratorAgent
    ↓ (reads ALL upstream wrappers, produces OrchestrationConfig wrapper)
DownloadAgent
    ↓ (verifies completeness, triggers workflow ZIP download)
```

### Critical Wrapper Keys (Semantic References)

Each agent reads **wrapper keys**, NOT agent names:

| Agent Output | Wrapper Key | Schema Model (structured_outputs.json) |
|--------------|-------------|----------------------------------------|
| PatternAgent | `PatternSelection` | PatternSelectionCall |
| WorkflowStrategyAgent | `WorkflowStrategy` | WorkflowStrategyCall |
| WorkflowArchitectAgent | `TechnicalBlueprint` | TechnicalBlueprintCall |
| WorkflowImplementationAgent | `PhaseAgents` | PhaseAgentsCall |
| ProjectOverviewAgent | `MermaidSequenceDiagram` | MermaidSequenceDiagramCall |
| ContextVariablesAgent | `ContextVariablesPlan` | ContextVariablesPlanCall |
| ToolsManagerAgent | `ToolsManifest` | ToolsManifestCall |
| StructuredOutputsAgent | `StructuredOutputsRegistry` | StructuredOutputsRegistryCall |
| AgentsAgent | `AgentDefinitions` | AgentDefinitionsCall |
| HandoffsAgent | `HandoffRules` | HandoffRulesCall |
| OrchestratorAgent | `OrchestrationConfig` | OrchestrationConfigCall |

### Pattern Propagation Through Chain

1. **PatternAgent** emits: `PatternSelection.selected_pattern` (int or str)
2. **WorkflowStrategyAgent** reads `PatternSelection.selected_pattern` to determine:
   - Phase count (2-6 phases depending on pattern)
   - Phase structure (linear vs. nested vs. hierarchical)
   - Phase names/descriptions matching pattern topology
3. **WorkflowArchitectAgent** reads `WorkflowStrategy.phases[]` to determine:
   - Tools per phase (scope: shared vs. phase_specific)
   - Context variables per phase
   - Lifecycle operations (before_chat, after_agent, etc.)
4. **WorkflowImplementationAgent** reads `WorkflowStrategy.phases[]` to determine:
   - Agent count per phase (1 for Pipeline, multiple for Star/Triage)
   - Agent capabilities (integrations[], operations[])
   - Agent human_interaction mode (approval vs. context vs. none)
5. **All Downstream Agents** read phase structure, agent roster, tools, and context variables to build runtime artifacts

---

## 2. Symbiotic Relationship: structured_outputs.json ↔ agents.json ↔ Pattern Guidance

### The Contract Chain

```
structured_outputs.json (SCHEMA DEFINITIONS)
    ↓ defines
json_output_compliance.output_type (SCHEMA REFERENCE)
    ↓ enforces
Agent Output Structure (RUNTIME VALIDATION)
    ↓ guides
Pattern Guidance (TEACHING MATERIAL)
```

### Example: WorkflowStrategyAgent

**structured_outputs.json defines:**
```json
{
  "WorkflowStrategyCall": {
    "type": "model",
    "fields": {
      "WorkflowStrategy": {
        "type": "WorkflowStrategyOutput",
        "description": "High-level workflow architecture"
      }
    }
  },
  "WorkflowStrategyOutput": {
    "type": "model",
    "fields": {
      "workflow_name": {"type": "str"},
      "workflow_description": {"type": "str"},
      "trigger": {"type": "literal", "values": ["chat|form_submit|schedule|database_condition|webhook"]},
      "initiated_by": {"type": "literal", "values": ["user|system|external_event"]},
      "pattern": {"type": "list", "items": "str"},
      "phases": {"type": "list", "items": "PhaseStrategy"},
      "lifecycle_operations": {"type": "list", "items": "LifecycleOperationStrategy"}
    }
  }
}
```

**agents.json references:**
```json
{
  "WorkflowStrategyAgent": {
    "structured_outputs_required": true,
    "json_output_compliance": {
      "output_type": "WorkflowStrategyCall"
    }
  }
}
```

**Pattern Guidance MUST teach:**
- **Schema Awareness**: "Your output must match the WorkflowStrategyCall schema"
- **Field Constraints**: "trigger must be one of: chat, form_submit, schedule, database_condition, webhook"
- **Pattern-Specific Variations**: 
  - Pipeline pattern → 3-5 linear phases
  - Feedback Loop pattern → 4-6 phases with iteration
  - Hierarchical pattern → 3-4 phases with tier structure
- **Upstream Dependencies**: "Read PatternSelection.selected_pattern from context"
- **Downstream Impact**: "Your phases[] array determines TechnicalBlueprint and PhaseAgents structure"

---

## 3. Pattern-Specific Output Variations

### WorkflowStrategy.phases[] Count by Pattern

| Pattern | Typical Phase Count | Structure |
|---------|---------------------|-----------|
| Context-Aware Routing | 2-4 | Linear with conditional branching |
| Escalation | 3-4 | Tiered (L1 → L2 → L3 → Expert) |
| Feedback Loop | 4-6 | Iterative (Intake → Process → Review → Iterate → Finalize) |
| Hierarchical | 3-4 | Pyramid (Strategy → Tactical → Execution) |
| Organic | 2-3 | Emergent (Ideation → Refinement) |
| Pipeline | 3-5 | Sequential (Stage 1 → Stage 2 → ... → Output) |
| Redundant | 2-3 | Parallel validation phases |
| Star | 2-3 | Hub-and-spoke (Coordinator + Specialists) |
| Triage with Tasks | 3-4 | Classification → Assignment → Execution → QA |

### TechnicalBlueprint.required_tools Variations by Pattern

| Pattern | Tool Scope Strategy | Example |
|---------|---------------------|---------|
| Pipeline | Mostly phase_specific | Each stage has dedicated tools |
| Star | Mostly shared | Coordinator distributes shared toolset |
| Hierarchical | Mixed | High-level phases share tools, execution phases have specific |
| Triage with Tasks | phase_specific | Each task type needs different tools |

### PhaseAgents.agents[] Roster Variations by Pattern

| Pattern | Agent Count Strategy | Example |
|---------|----------------------|---------|
| Pipeline | 1 agent per phase | Linear handoff |
| Star | 1 coordinator + N specialists | Hub distributes to spokes |
| Triage with Tasks | 1 classifier + N executors | Router → Workers |
| Feedback Loop | Multiple reviewers + iterators | Collaborative refinement |

---

## 4. ActionPlan: The Integration Point

### ActionPlan Structure (from structured_outputs.json)

```json
{
  "ActionPlan": {
    "workflow": {  // WorkflowSpec
      "name": "...",
      "description": "...",
      "initiated_by": "user|system|external_event",
      "trigger_type": "form_submit|chat_start|cron_schedule|webhook|database_condition",
      "pattern": "ContextAwareRouting|Escalation|...",
      "lifecycle_operations": [...],
      "phases": [  // WorkflowPhase[]
        {
          "name": "Phase 1: Intake",
          "description": "...",
          "agents": [  // WorkflowAgent[]
            {
              "name": "IntakeAgent",
              "description": "...",
              "integrations": ["Slack"],
              "operations": ["validate_input"],
              "human_interaction": "context"
            }
          ]
        }
      ]
    }
  }
}
```

### ActionPlan Assembly Process

1. **ActionPlanArchitect** tool (called by WorkflowImplementationAgent) merges:
   - `WorkflowStrategy.workflow_name` → `ActionPlan.workflow.name`
   - `WorkflowStrategy.workflow_description` → `ActionPlan.workflow.description`
   - `WorkflowStrategy.trigger` → `ActionPlan.workflow.trigger_type`
   - `WorkflowStrategy.pattern` → `ActionPlan.workflow.pattern`
   - `WorkflowStrategy.lifecycle_operations` → `ActionPlan.workflow.lifecycle_operations`
   - `WorkflowStrategy.phases[]` + `PhaseAgents.phase_agents[]` → `ActionPlan.workflow.phases[]`

2. **Runtime Execution** (core/workflow/orchestration_patterns.py):
   - Reads `ActionPlan.workflow.pattern` → determines AG2 GroupChat topology
   - Reads `ActionPlan.workflow.phases[].agents[]` → instantiates AG2 agents
   - Reads `HandoffRules` → wires AG2 handoffs
   - Reads `ContextVariablesPlan` → initializes AG2 context_variables
   - Reads `OrchestrationConfig` → configures AG2 GroupChat settings

---

## 5. AG2 Runtime Execution: The Final Link

### From Declarative JSON to AG2 GroupChat

**Pattern Determines GroupChat Topology:**

```python
# core/workflow/orchestration_patterns.py

async def build_groupchat_from_pattern(workflow_config: dict) -> GroupChat:
    pattern = workflow_config["workflow"]["pattern"]
    phases = workflow_config["workflow"]["phases"]
    
    if pattern == "Pipeline":
        # Sequential speaker selection: Phase 1 Agent → Phase 2 Agent → ...
        return build_linear_groupchat(phases)
    
    elif pattern == "Star":
        # Hub-and-spoke: Coordinator → Specialist → Coordinator
        return build_star_groupchat(phases)
    
    elif pattern == "Hierarchical":
        # Tiered: Strategy agents → Tactical agents → Execution agents
        return build_hierarchical_groupchat(phases)
    
    # ... other patterns
```

**Handoffs Wire Agent-to-Agent Transitions:**

```python
# core/workflow/handoffs.py

def apply_handoffs_from_config(workflow_name: str, agents: Dict[str, Any]):
    handoffs_config = load_config(workflow_name, "handoffs.json")
    
    for rule in handoffs_config["handoffs"]["handoff_rules"]:
        source_agent = agents[rule["source"]]
        target_agent = agents[rule["target"]]
        
        if rule["handoff_type"] == "after_work":
            source_agent.handoffs = [target_agent]
        
        elif rule["handoff_type"] == "condition":
            # Context-aware routing based on context_variables
            condition = rule["condition"]
            source_agent.handoffs.append(
                ConditionalHandoff(target=target_agent, condition=condition)
            )
```

**Context Variables Enable Coordination:**

```python
# Context variables are set by:
# 1. UI tools (ui_response triggers): runtime['context_variables'].set(var_name, value)
# 2. Agent messages (agent_text triggers): pattern matching in agent replies
# 3. Database queries (database source): fetched on workflow start
# 4. Environment vars (environment source): read from .env

# Agents read via:
exposed_vars = runtime['context_variables'].get_exposed_for_agent(agent_name)
```

---

## 6. What Pattern Guidance MUST Now Include

### Current Guidance Structure (INCOMPLETE)

```python
WORKFLOW_STRATEGY_PATTERN_GUIDANCE = {
    1: """
    **Pattern 1: Context-Aware Routing**
    
    Topology: Linear phases with conditional branching
    Phase Count: 2-4
    Example JSON: {...}
    """
}
```

### REQUIRED Guidance Structure (COMPLETE)

```python
WORKFLOW_STRATEGY_PATTERN_GUIDANCE = {
    1: f"""
**Pattern 1: Context-Aware Routing**

**YOUR OUTPUT WRAPPER KEY**: "WorkflowStrategy"

**INPUT DEPENDENCIES**:
- Read `PatternSelection.selected_pattern` from upstream workflow outputs
- Extract user requirements from `Interview` wrapper
- Validate pattern choice matches user's workflow needs

**PATTERN-SPECIFIC STRUCTURE**:
- **Phase Count**: 2-4 phases (typical: Intake → Route → Execute → Finalize)
- **Phase Naming**: Use "Phase N:" prefix (e.g., "Phase 1: Intake & Classification")
- **Coordination Style**: 
  - Phase 1: single agent (intake)
  - Phase 2: single agent (routing logic)
  - Phase 3+: nested agents (conditional execution paths)
- **Trigger Types**: Best suited for chat_start, form_submit (user-initiated)
- **Lifecycle Operations**: Typically includes before_agent hooks for routing decisions

**SCHEMA COMPLIANCE**:
```json
{{
  "WorkflowStrategy": {{
    "workflow_name": "<string>",  // REQUIRED
    "workflow_description": "<string>",  // REQUIRED, 400-600 chars
    "trigger": "chat|form_submit|schedule|database_condition|webhook",  // REQUIRED
    "initiated_by": "user|system|external_event",  // REQUIRED
    "pattern": ["ContextAwareRouting"],  // MUST include selected pattern
    "phases": [  // REQUIRED, 2-4 entries for this pattern
      {{
        "phase_index": 0,  // REQUIRED, zero-based sequential
        "phase_name": "Phase 1: <name>",  // REQUIRED, include "Phase N:" prefix
        "phase_description": "<string>",  // REQUIRED
        "human_in_loop": true|false,  // Based on approval requirements
        "agents_needed": "single|sequential|nested"  // For this pattern: Phase 1-2 = single, Phase 3+ = nested
      }}
    ],
    "lifecycle_operations": [...]  // Optional, omit when not needed
  }}
}}
```

**PATTERN-SPECIFIC EXAMPLE** (Context-Aware Routing for Customer Support):
```json
{{
  "WorkflowStrategy": {{
    "workflow_name": "Customer Support Ticket Router",
    "workflow_description": "When a customer submits a support ticket via form, the workflow classifies the issue, routes to the appropriate specialist team, executes the resolution workflow, and confirms completion. Delivers faster resolution times through intelligent routing.",
    "trigger": "form_submit",
    "initiated_by": "user",
    "pattern": ["ContextAwareRouting"],
    "phases": [
      {{
        "phase_index": 0,
        "phase_name": "Phase 1: Ticket Intake",
        "phase_description": "Capture ticket details and classify issue type. Single agent collects structured data.",
        "human_in_loop": false,
        "agents_needed": "single"
      }},
      {{
        "phase_index": 1,
        "phase_name": "Phase 2: Routing Logic",
        "phase_description": "Determine specialist team based on issue classification. Single routing agent makes decision.",
        "human_in_loop": false,
        "agents_needed": "single"
      }},
      {{
        "phase_index": 2,
        "phase_name": "Phase 3: Specialist Execution",
        "phase_description": "Route to technical, billing, or account specialist. Nested agents handle domain-specific resolution. Hands off to Phase 4 upon resolution.",
        "human_in_loop": false,
        "agents_needed": "nested"
      }},
      {{
        "phase_index": 3,
        "phase_name": "Phase 4: Confirmation & Close",
        "phase_description": "Notify customer of resolution and close ticket. Single agent finalizes.",
        "human_in_loop": false,
        "agents_needed": "single"
      }}
    ],
    "lifecycle_operations": [
      {{
        "hook": "before_agent",
        "target": "RoutingAgent",
        "purpose": "Evaluate ticket classification context variable to determine routing path"
      }}
    ]
  }}
}}
```

**HOW YOUR OUTPUT IS USED**:
- Downstream agents read your `WorkflowStrategy.phases[]` wrapper to determine:
  - How many phase_technical_requirements entries to create (count MUST match your phases.length)
  - Which tools are shared vs. phase_specific (single-agent phases typically use shared, nested use phase_specific)
  - Which context variables are needed (routing decisions require derived variables with triggers)
- Your `WorkflowStrategy.phases[]` array merges with `PhaseAgents.phase_agents[]` to create the final workflow definition
- The runtime uses your `pattern` field to configure execution topology and handoff routing
- Your phase structure determines the entire downstream workflow architecture

**ANTI-PATTERNS** (DO NOT DO):
❌ Phase count mismatch: Don't emit 5 phases for Context-Aware Routing (max 4)
❌ Missing "Phase N:" prefix in phase_name
❌ agents_needed="nested" in intake/routing phases (should be "single")
❌ Omitting lifecycle_operations when routing requires before_agent hooks
❌ Using schedule/webhook triggers (pattern optimized for user-initiated workflows)
❌ Pattern array mismatch: Don't include ["Pipeline"] when PatternSelection chose ContextAwareRouting
"""
}
```

---

## 7. Revised Implementation Requirements

### Pattern Guidance Must Now Address:

1. **Inline Schema Structure**:
   - Show exact JSON structure with wrapper key as top-level field
   - Inline field-level comments explaining each field
   - Highlight REQUIRED vs. optional fields
   - Explain allowed values for literal types
   - NO references to external files (structured_outputs.json, agents.json, etc.)

2. **Upstream Dependency Teaching**:
   - Which wrapper keys to read from upstream outputs (e.g., `PatternSelection`, `Interview`)
   - Which specific fields to extract (e.g., `PatternSelection.selected_pattern`)
   - How to validate upstream data before using it
   - Use semantic wrapper key names, NEVER agent names

3. **Pattern-Specific Structural Variations**:
   - Phase count ranges for this pattern
   - Phase naming conventions (must include "Phase N:" prefix)
   - Coordination style per phase (single vs. sequential vs. nested)
   - Trigger type recommendations
   - Lifecycle operation patterns

4. **Downstream Impact Explanation**:
   - How wrapper key output is consumed (use passive voice: "is read by", "determines")
   - Which fields downstream workflows depend on (e.g., phases.length, phase_index sequence)
   - How pattern choice cascades through outputs
   - NEVER mention specific agent names

5. **Runtime Execution Mapping**:
   - How pattern determines execution topology
   - How phases map to handoff routing
   - How context variables enable coordination
   - How outputs link to runtime execution (declarative JSON → running workflow)

6. **Anti-Patterns & Validation**:
   - Common mistakes specific to this pattern
   - Validation checklist before emitting output
   - Schema compliance warnings

---

## 8. Gap Analysis: Current vs. Required

### ✅ Currently Implemented

- Two-layer architecture (static framework + dynamic injection)
- AG2 update_agent_state hooks for runtime injection
- Pattern resolution from context_variables (PatternSelection.selected_pattern)
- Comprehensive guidance for patterns 1-3 (Context-Aware Routing, Escalation, Feedback Loop)

### ❌ Missing from Current Implementation

1. **Inline Schema Teaching**: Guidance doesn't show complete inline JSON structure with wrapper keys
2. **Wrapper Key Emphasis**: Guidance doesn't emphasize wrapper keys as the primary semantic identifiers
3. **No Agent Name References**: Must ensure guidance NEVER mentions agent names (only wrapper keys)
4. **No External File References**: Must ensure guidance NEVER references structured_outputs.json, agents.json, etc.
5. **Upstream Dependencies**: Guidance doesn't show which upstream wrapper keys to read
6. **Downstream Impact**: Guidance doesn't explain how wrapper key output flows to downstream workflows (using passive voice)
7. **Field-Level Constraints**: Guidance doesn't explain allowed values, REQUIRED fields inline
8. **Output Assembly**: Guidance doesn't show how wrapper keys merge into final workflow definition
9. **Runtime Mapping**: Guidance doesn't connect pattern to execution topology
10. **Pattern Variations**: Guidance doesn't explain structural differences (phase counts, coordination styles)

### Critical Example of Gap

**Current guidance for Pattern 1 (workflow_strategy_patterns.py):**
```python
WORKFLOW_STRATEGY_PATTERN_GUIDANCE = {
    1: """**Pattern 1: Context-Aware Routing**
    
Characteristics: Linear phases with conditional branching based on context
Topology: 2-4 phases (Intake → Route → Execute → Finalize)

[Example JSON with 4 phases]
"""
}
```

**MISSING**:
- ❌ "Your output wrapper key is 'WorkflowStrategy'"
- ❌ "Read `PatternSelection.selected_pattern` from upstream outputs"
- ❌ "Downstream workflows will create phase_technical_requirements.length == your phases.length"
- ❌ "Field constraints: trigger MUST be one of [chat, form_submit, ...]"
- ❌ "Routing patterns require before_agent lifecycle hooks for routing logic"
- ❌ "Your phases[] array merges with PhaseAgents wrapper to create final workflow definition"
- ❌ References to agent names (TechnicalBlueprintAgent, PhaseAgentsAgent, etc.)
- ❌ References to external files (structured_outputs.json)

---

## 9. Corrected Guidance Principles

### CRITICAL RULES

**❌ NEVER mention agent names in guidance:**
```
WRONG: "TechnicalBlueprintAgent reads your WorkflowStrategy..."
RIGHT: "Downstream workflows read your WorkflowStrategy wrapper..."
```

**❌ NEVER reference external files:**
```
WRONG: "Your output_type is WorkflowStrategyCall from structured_outputs.json"
RIGHT: "Your output wrapper key is 'WorkflowStrategy'. Output MUST match this structure: {...inline JSON...}"
```

**✅ ALWAYS use wrapper keys as semantic identifiers:**
```
- Read `PatternSelection.selected_pattern` from upstream outputs
- Emit `WorkflowStrategy` wrapper
- Reference `PhaseAgents.phase_agents[]` when explaining downstream usage
```

**✅ ALWAYS use passive voice for downstream impact:**
```
- "Your phases[] array is used to determine phase_technical_requirements count"
- "The pattern field configures execution topology"
- "Your output merges with PhaseAgents wrapper to create final workflow definition"
```

**✅ ALWAYS inline schema structure:**
```json
{
  "WorkflowStrategy": {  // ← Wrapper key as top-level field
    "workflow_name": "<string>",  // REQUIRED - Human-readable name
    "phases": [...],  // REQUIRED - Array of phase objects
    ...
  }
}
```

---

## 10. Conclusion

The original pattern guidance plan was **architecturally sound** (dynamic injection via AG2 hooks) but **semantically incomplete** (didn't integrate with structural contracts).

Pattern guidance is NOT just "helpful examples" — it's the **teaching layer** that helps agents navigate:
- **What to produce** (inline schema structure with wrapper keys)
- **What to read** (upstream wrapper keys)
- **How pattern affects structure** (phase counts, coordination styles, structural variations)
- **How output flows** (downstream wrapper consumption, workflow assembly, runtime execution)

**WITHOUT ever mentioning:**
- ❌ Agent names (use wrapper keys and passive voice)
- ❌ External files (inline all schema structures)
- ❌ Implementation details (focus on semantic contracts)

### Next Steps

1. **Revise guidance structure** to include all 6 required sections (see section 7)
2. **Complete workflow_strategy_patterns.py** with revised structure for patterns 4-9
3. **Create pattern modules** for 8 remaining agents (following same structure)
4. **Update injection functions** to use revised guidance
5. **Validate against semantic chain** by tracing data flow through Generator workflow
