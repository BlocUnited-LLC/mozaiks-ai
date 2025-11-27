# Agent Prompt Refactoring Guide

**Purpose**: Standardized checklist and principles for refactoring Generator agent system messages to ensure consistency, semantic coupling, and runtime contract compliance.

**Audience**: Engineers refactoring agent prompts in `workflows/Generator/agents.json`

**Last Updated**: 2025-11-02

---

## Core Principles

### 1. Semantic Referencing (CRITICAL)
**Always reference upstream outputs by their structured output wrapper keys, NEVER by agent names or lowercase variable names.**

#### ✅ CORRECT - Use Semantic Wrapper Keys
```
- Read ActionPlan.workflow.phases[] from conversation history
- Extract PhaseAgents.phase_agents[].agents[] for agent roster
- Locate TechnicalBlueprint.phase_technical_requirements[]
- Access PatternSelection.selected_pattern
- Reference WorkflowStrategy.phases[]
```

#### ❌ WRONG - Agent Names or Variable Names
```
- Read action_plan from context variables (set by action_plan.py tool)
- Get output from ActionPlanAgent
- Locate the phase_agents_plan tool output
- Access pattern_selection variable
- Read from WorkflowStrategyAgent output
```

**Why**: Semantic keys enable loose coupling. Agents consume outputs without knowing which specific agent produced them. This allows runtime flexibility and prevents brittle agent-to-agent dependencies.

**Reference**: See `ACTION_PLAN_OWNERSHIP.md` for authoritative structured output schemas.

---

### 2. Structured Output Schema Alignment

Every agent that produces structured outputs must:

1. **Define the wrapper structure** in `[CONTEXT]` section:
   ```
   Output: ActionPlanCall with wrapper structure:
   {
     "ActionPlan": {
       "workflow": {...}
     }
   }
   ```

2. **Reference upstream inputs** by their wrapper keys:
   ```
   Input: PatternSelection.selected_pattern (from PatternSelectionCall)
   ```

3. **Document the semantic key** agents will use to reference this output:
   ```
   Reference: Use semantic key "ActionPlan" (NOT agent name, NOT variable name)
   ```

**Structured Output Wrappers** (from ACTION_PLAN_OWNERSHIP.md):
- `WorkflowStrategyCall` → wrapper: `WorkflowStrategy`
- `TechnicalBlueprintCall` → wrapper: `TechnicalBlueprint`
- `PhaseAgentsCall` → wrapper: `PhaseAgents`
- `ProjectOverviewCall` → wrapper: `MermaidSequenceDiagram` (or similar)
- `ContextVariablesAgentOutput` → wrapper: `ContextVariablesPlan`
- `ActionPlanCall` → wrapper: `ActionPlan`
- `PatternSelectionCall` → wrapper: `PatternSelection`

---

### 3. Standard 9-Section Structure

All Generator agents must have exactly 9 sections (or 8 if `json_output_compliance` omitted for free-form agents):

1. **role** - Single sentence identity
2. **objective** - Bulleted deliverables list (2-4 items)
3. **context** - Workflow position, upstream inputs (by semantic key), downstream outputs, runtime storage
4. **runtime_integrations** - What runtime handles automatically (don't duplicate effort)
5. **guidelines** - Compliance rules, legal requirements, output standards
6. **instructions** - Step-by-step execution algorithm
7. **pattern_guidance_and_examples** - `{{PATTERN_GUIDANCE_AND_EXAMPLES}}` placeholder (for pattern-aware agents) OR hardcoded examples (for DownloadAgent only)
8. **json_output_compliance** - JSON escaping rules (ONLY if `structured_outputs_required=true`)
9. **output_format** - Expected output structure with schema

**Section ID Requirements**:
- Use exact IDs: `role`, `objective`, `context`, `runtime_integrations`, `guidelines`, `instructions`, `pattern_guidance_and_examples`, `json_output_compliance`, `output_format`
- NO custom section IDs (e.g., `responsibilities`, `notes`, `background`)

---

### 4. Pattern Guidance Injection

**Pattern-aware agents** (those that need pattern-specific examples):
- Use `pattern_guidance_and_examples` section with `{{PATTERN_GUIDANCE_AND_EXAMPLES}}` placeholder
- Runtime replaces placeholder via `update_agent_state_pattern.py` hook
- Examples adapt to selected workflow pattern (Pipeline, Hierarchical, Star, etc.)

**Agents using pattern injection**:
- WorkflowStrategyAgent
- WorkflowArchitectAgent
- WorkflowImplementationAgent
- ProjectOverviewAgent
- ContextVariablesAgent
- ToolsManagerAgent
- StructuredOutputsAgent
- AgentsAgent
- InterviewAgent
- OrchestratorAgent

**Agents NOT using pattern injection**:
- DownloadAgent (has workflow-agnostic download examples)
- PatternAgent (teaches patterns, doesn't follow one)
- HandoffsAgent (no examples section at all - was already standardized without one)

---

### 5. Context Section Requirements

The `[CONTEXT]` section must clearly document:

#### Upstream Inputs (Read Operations)
```
**Upstream Inputs** (read from conversation history):
1. **PatternSelection** (from PatternSelectionCall):
   - Wrapper: {"PatternSelection": {"selected_pattern": <int>, ...}}
   - What to extract: selected_pattern, pattern_name
   - Why: Determines pattern-specific guidance to inject
   - Reference: Use semantic key "PatternSelection"

2. **WorkflowStrategy** (from WorkflowStrategyCall):
   - Wrapper: {"WorkflowStrategy": {"phases": [...], ...}}
   - What to extract: phases[], pattern, workflow metadata
   - Why: Provides phase structure for agent design
   - Reference: Use semantic key "WorkflowStrategy"
```

#### Output Contract (Write Operations)
```
**Output Contract**:
- Structured output: PhaseAgentsCall with wrapper {"PhaseAgents": {...}}
- Storage: Persisted to context variables as `phase_agents`
- Downstream consumers: AgentsAgent, HandoffsAgent, ContextVariablesAgent
- Semantic reference: Downstream agents use "PhaseAgents.phase_agents[]"
```

#### RUNTIME INTEGRATION (What to NOT implement)
```
**Runtime handles automatically**:
- Context variable initialization from DB/environment/static
- Tool registration and invocation
- Handoff routing compilation to AG2 primitives
- Pattern guidance injection via update_agent_state hooks
```

---

### 6. Instructions Section Best Practices

#### Step Numbering
- Use sequential step numbers: `Step 1`, `Step 2`, etc.
- Each step should be atomic and verifiable
- Final step is always output emission

#### Reading Upstream Outputs
```
**Step 1 - Read ActionPlan Structured Output**:
- Locate ActionPlan from conversation history (semantic wrapper key)
- Extract: ActionPlan.workflow.phases[], flow_type, approval gates
- Note which agents exist per phase for coordination tokens
```

#### Validation Steps
```
**Step N - Validate Output**:
- Ensure all required fields present
- Ensure phase_index values sequential (0, 1, 2, ...)
- Ensure agent names reference valid agents from PhaseAgents output
```

#### Output Emission
```
**Step N+1 - Emit JSON**:
- Output [AgentName]Output as valid JSON matching schema
- Structure: {"WrapperKey": {...}}
- NO markdown fences, NO explanatory text
```

---

### 7. Output Format Section Requirements

Must include:

1. **Complete schema example** with all fields
2. **Field rules** explaining constraints
3. **Wrapper structure** showing semantic key
4. **Critical reminder** about no markdown fences

#### Template:
```
Output MUST be a valid JSON object matching the [SchemaName] schema with NO additional text:

```json
{
  "[WrapperKey]": {
    "field1": "<type>",
    "field2": [...]
  },
  "agent_message": "<Summary for UI>"
}
```

**Field Rules**:
- field1: Description of constraints
- field2: Description of structure

**CRITICAL**: Output ONLY the raw JSON object. NO markdown fences, NO explanatory text, NO commentary.
```

---

### 8. Agent-Specific Ownership (ACTION_PLAN_OWNERSHIP.md)

Each agent has exclusive ownership of specific Action Plan fields:

#### WorkflowStrategyAgent
- Owns: `workflow_name`, `workflow_description`, `trigger`, `initiated_by`, `pattern`
- Owns: Phase scaffolding (`phase_index`, `phase_name`, `phase_description`, `human_in_loop`, `agents_needed`)
- Does NOT: Define agents, tools, or integrations

#### WorkflowArchitectAgent
- Owns: `global_context_variables`, `before_chat_lifecycle`, `after_chat_lifecycle`
- Provides: Technical requirements (WHAT tools/variables/hooks needed)
- Does NOT: Design agents or implement tools

#### WorkflowImplementationAgent
- Owns: `phases[].agents[]` with full agent specifications
- Owns: `agent_tools`, `lifecycle_tools`, `system_hooks`, `integrations`, `human_interaction`
- Does NOT: Modify phase structure or top-level metadata

#### ProjectOverviewAgent
- Owns: `mermaid_diagram`, `agent_message` (final synopsis)
- Does NOT: Modify phases or agent configurations

#### ContextVariablesAgent
- Reads: ActionPlan, PhaseAgents, ToolsManifest
- Produces: ContextVariablesPlan (definitions + agent exposure mappings)
- Does NOT: Modify workflow structure

#### ToolsManagerAgent
- Reads: ActionPlan, ContextVariablesPlan
- Produces: Tools manifest (tools[] + lifecycle_tools[])
- Does NOT: Implement tool functions (that's downstream code generation)

#### StructuredOutputsAgent
- Reads: ActionPlan, ContextVariablesPlan, ToolsManifest, UI/tool file generator outputs
- Produces: Pydantic models + registry
- Does NOT: Implement validation logic (runtime handles)

#### AgentsAgent
- Reads: All upstream outputs (ActionPlan, ContextVariablesPlan, StructuredOutputs, etc.)
- Produces: Runtime agent configurations with prompt_sections arrays
- Does NOT: Use system_message strings (ONLY prompt_sections arrays)

#### HandoffsAgent
- Reads: ActionPlan, ContextVariablesPlan, AgentsAgent output
- Produces: Handoff rules (source→target, conditions, scopes)
- Does NOT: Implement routing logic (runtime compiles to AG2 primitives)

---

### 9. Common Issues to Fix

#### Issue 1: Agent Name References
```diff
- Read output from ActionPlanAgent
+ Read ActionPlan structured output from conversation history
```

#### Issue 2: Lowercase Variable References
```diff
- Access action_plan from context variables
+ Access ActionPlan.workflow from conversation history
```

#### Issue 3: Missing Wrapper Documentation
```diff
[CONTEXT] section:
- Input: Action Plan with phases and agents
+ Input: ActionPlan (from ActionPlanCall structured output)
+   Wrapper: {"ActionPlan": {"workflow": {...}}}
+   Reference: Use semantic key "ActionPlan"
```

#### Issue 4: Incomplete Output Format
```diff
- [TODO: define output format]
+ Output MUST be a valid JSON object matching...
+ [Full schema with wrapper structure]
```

#### Issue 5: Missing Pattern Guidance Placeholder
```diff
- "id": "examples",
- "heading": "[EXAMPLES]",
- "content": "{\"hardcoded\": \"example\"}"
+ "id": "pattern_guidance_and_examples",
+ "heading": "[PATTERN GUIDANCE AND EXAMPLES]",
+ "content": "{{PATTERN_GUIDANCE_AND_EXAMPLES}}"
```

#### Issue 6: Non-Standard Section IDs
```diff
- "id": "responsibilities"
+ "id": "objective"

- "id": "background"
+ "id": "context"
```

#### Issue 7: Duplicate Sections
```diff
Remove duplicate "guidelines" or "instructions" sections
Ensure only ONE of each section ID exists
```

#### Issue 8: Wrong auto_tool_mode Settings
```diff
For agents with UI_Tools:
- "auto_tool_mode": false
+ "auto_tool_mode": true

For agents with ONLY Agent_Tools:
- "auto_tool_mode": true
+ "auto_tool_mode": false
```

---

### 10. Validation Checklist

Before marking an agent as "complete", verify:

- [ ] Uses semantic wrapper keys for ALL upstream references
- [ ] Has exactly 9 sections (or 8 if free-form agent)
- [ ] Section IDs match standard list exactly
- [ ] [CONTEXT] documents upstream inputs with wrapper structures
- [ ] [CONTEXT] documents output contract with semantic reference
- [ ] [INSTRUCTIONS] uses semantic keys in all steps
- [ ] [OUTPUT FORMAT] is complete (not TODO)
- [ ] [OUTPUT FORMAT] shows wrapper structure
- [ ] Pattern guidance uses placeholder (if pattern-aware)
- [ ] auto_tool_mode matches tool ownership (true for UI_Tools)
- [ ] structured_outputs_required matches registry
- [ ] No agent name references anywhere
- [ ] No lowercase variable references (use wrapper keys)
- [ ] Guidelines start with legal compliance statement
- [ ] Instructions have clear step-by-step flow
- [ ] Output format includes field rules and examples

---

### 11. Runtime Contract Alignment

Agents must align with these runtime contracts:

#### Structured Outputs
- `structured_outputs_required=true` → Include `json_output_compliance` section
- `structured_outputs_required=false` → Omit `json_output_compliance` section
- All structured outputs must use wrapper pattern for semantic referencing

#### Auto Tool Mode
- `auto_tool_mode=true` → Agent owns UI_Tools (async, auto-invoked by AutoToolEventHandler)
- `auto_tool_mode=false` → Agent has Agent_Tools only OR no tools
- UI_Tool owners MUST set `auto_tool_mode=true` (AG2 native calling doesn't await async)

#### Context Variables
- Agent exposure mappings control which variables each agent can read
- Triggers determine condition_scope in handoffs:
  - `agent_text` → `condition_scope=null` (runtime watches, sets on match)
  - `ui_response` → `condition_scope="pre"` (tool code sets explicitly)

#### Handoffs
- `handoff_type="after_work"` → Unconditional sequential flow
- `handoff_type="condition"` + `condition_type="expression"` → Context variable condition
- `handoff_type="condition"` + `condition_type="string_llm"` → LLM evaluation

#### Lifecycle Operations
- Workflow-level: `before_chat`, `after_chat` (chat session boundaries)
- Agent-level: `before_agent`, `after_agent` (wrap agent LLM call)
- System hooks: `update_agent_state`, `process_message_before_send`, etc. (AG2 hook system)

---

### 12. Pattern Injection Architecture

Pattern guidance injection enables agents to receive pattern-specific examples at runtime:

#### How It Works
1. User selects workflow pattern (PatternAgent outputs PatternSelection)
2. Runtime stores `selected_pattern` in context
3. When agent is initialized, `update_agent_state_pattern.py` hook runs
4. Hook reads agent's system message, finds `{{PATTERN_GUIDANCE_AND_EXAMPLES}}` placeholder
5. Hook replaces placeholder with pattern-specific content from pattern library
6. Agent receives tailored examples matching selected pattern

#### Pattern Library Structure
```python
PATTERN_GUIDANCE = {
    1: {  # Context-Aware Routing
        "WorkflowStrategyAgent": "...",
        "WorkflowArchitectAgent": "...",
        # etc.
    },
    6: {  # Pipeline
        "WorkflowStrategyAgent": "...",
        # etc.
    }
}
```

#### Benefits
- Agents adapt to different workflow patterns without config changes
- Examples stay relevant to user's chosen pattern
- No hardcoded pattern assumptions in agent prompts
- Consistent pattern application across all Generator agents

---

### 13. Reference Documents

When refactoring agents, consult:

1. **ACTION_PLAN_OWNERSHIP.md** - Authoritative schema definitions and ownership matrix
2. **HOOK_SYSTEM_DEEP_DIVE.md** - AG2 hook system contracts (update_agent_state, process_message_before_send, etc.)
3. **workflows/Generator/agents.json** - Current agent configurations
4. **workflows/Generator/tools/update_agent_state_pattern.py** - Pattern injection implementation
5. **core/workflow/action_plan.py** - Assembly pipeline and merge logic

---

### 14. Refactoring Workflow

For each agent:

1. **Read current configuration** - Understand what it does
2. **Check upstream inputs** - Identify what outputs it reads
3. **Verify semantic references** - Replace agent names with wrapper keys
4. **Standardize sections** - Ensure 9-section structure
5. **Complete [CONTEXT]** - Document inputs/outputs with wrappers
6. **Update [INSTRUCTIONS]** - Use semantic keys in all steps
7. **Fill [OUTPUT FORMAT]** - Complete schema with wrapper structure
8. **Add pattern guidance** - Replace examples with placeholder (if pattern-aware)
9. **Validate checklist** - Run through validation checklist
10. **Test compilation** - Ensure no syntax errors in JSON

---

### 15. Example: Before & After

#### ❌ BEFORE (ActionPlanAgent - hypothetical bad example)
```json
{
  "id": "context",
  "content": "Read the pattern selection from context variables. Get agent list from phase_agents_plan tool output. Access workflow strategy from upstream agent."
}
```

#### ✅ AFTER (Properly refactored)
```json
{
  "id": "context",
  "content": "(READ FROM CONVERSATION ARTIFACTS)\nYou MUST locate and read these exact structured output artifacts:\n\n1. **PatternSelection** (from PatternSelectionCall):\n   - Wrapper: {\"PatternSelection\": {\"selected_pattern\": <int>, ...}}\n   - What to extract: selected_pattern, pattern_name\n   - Reference: Use semantic key \"PatternSelection\"\n\n2. **PhaseAgents** (from PhaseAgentsCall):\n   - Wrapper: {\"PhaseAgents\": {\"phase_agents\": [...]}}\n   - What to extract: Agent roster with tools, hooks, integrations\n   - Reference: Use semantic key \"PhaseAgents\"\n\n3. **WorkflowStrategy** (from WorkflowStrategyCall):\n   - Wrapper: {\"WorkflowStrategy\": {\"phases\": [...], ...}}\n   - What to extract: Phase structure, pattern, metadata\n   - Reference: Use semantic key \"WorkflowStrategy\""
}
```

---

## Quick Reference Table

| Agent | Reads | Produces | Auto Tool Mode | Structured Outputs |
|-------|-------|----------|----------------|-------------------|
| InterviewAgent | concept_overview (context var) | Free-form conversation | false | false |
| PatternAgent | concept_overview, interview | PatternSelection | true | true |
| WorkflowStrategyAgent | PatternSelection | WorkflowStrategy | true | true |
| WorkflowArchitectAgent | WorkflowStrategy, PatternSelection | TechnicalBlueprint | true | true |
| WorkflowImplementationAgent | WorkflowStrategy, PatternSelection | PhaseAgents | true | true |
| ProjectOverviewAgent | ActionPlan | MermaidSequenceDiagram | true | true |
| ContextVariablesAgent | ActionPlan, PhaseAgents, ToolsManagerOutput | ContextVariablesPlan | false | true |
| ToolsManagerAgent | ActionPlan, ContextVariablesPlan | ToolsManagerOutput | false | true |
| StructuredOutputsAgent | ActionPlan, ContextVariablesPlan, Tools, UI/Tool files | StructuredOutputsOutput | false | true |
| AgentsAgent | All upstream outputs | RuntimeAgentsCall | false | true |
| HandoffsAgent | ActionPlan, ContextVariablesPlan, Agents | HandoffsCall | false | true |
| OrchestratorAgent | ActionPlan, Agents, Handoffs | OrchestratorCall | false | true |
| DownloadAgent | (all prior complete) | DownloadRequest | true | true |

---

## Common Patterns

### Reading Multiple Upstream Outputs
```
**Step 1 - Read Upstream Structured Outputs**:
- Locate ActionPlan from conversation history
- Locate PhaseAgents from conversation history
- Locate ToolsManagerOutput from conversation history
- Extract necessary fields from each wrapper
```

### Validation Pattern
```
**Step N - Validate Output**:
- Ensure output.length == upstream.length (where applicable)
- Ensure all references point to valid upstream entities
- Ensure required fields present and properly typed
- Ensure wrapper structure matches schema
```

### Pattern Guidance Reference
```
**Step 2 - Locate Pattern Guidance**:
- Scroll to bottom of system message
- Find [INJECTED PATTERN GUIDANCE - {PatternName}] section
- Read pattern-specific requirements and examples
- Adapt guidance to workflow specifics from ActionPlan
```

---

## Remember

🎯 **Primary Goal**: Loose coupling through semantic wrapper keys
🎯 **Secondary Goal**: Complete, production-ready prompts (no TODOs)
🎯 **Tertiary Goal**: Consistent structure across all agents

💡 **Key Insight**: Agents should reference WHAT (semantic keys) not WHO (agent names). This enables runtime flexibility and prevents brittle dependencies.

⚠️ **Common Mistake**: Using agent names or lowercase variable names instead of structured output wrapper keys.

✅ **Success Criteria**: Agent can execute correctly even if upstream agent is replaced, as long as the semantic wrapper structure remains the same.
