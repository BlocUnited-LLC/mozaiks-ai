# Schema Alignment Fix Proposal

## Overview
15 of 16 agents have misalignments between their [OUTPUT FORMAT] prompts and registered schemas.

## Fix Strategy
For each misalignment, we have two options:
1. **Update the schema** to match the prompt (simpler, validates what agents currently output)
2. **Update the prompt** to match the schema (more disruptive, requires prompt rewrites)

**RECOMMENDATION**: Update schemas to match prompts (less risky, preserves agent behavior)

---

## Critical Misalignments (Fix First)

### 1. PatternAgent
**Current Prompt Output**:
```json
{
  "selected_pattern": 6,
  "pattern_name": "Pipeline"
}
```

**Current Schema Expects**:
```json
{
  "PatternSelection": {
    "selected_pattern": 6,
    "pattern_name": "Pipeline"
  }
}
```

**FIX**: Update schema to remove wrapper, make fields top-level in `PatternSelectionCall`

---

### 2. WorkflowStrategyAgent
**Current Prompt Output**:
```json
{
  "workflow_name": "...",
  "workflow_description": "...",
  "trigger": "chat",
  "pattern": "Pipeline",
  "lifecycle_operations": [...],
  "phases": [...],
  "strategy_notes": "..."
}
```

**Current Schema Expects**:
```json
{
  "WorkflowStrategy": {
    "workflow_name": "...",
    ...
  }
}
```

**FIX**: Update schema - make `WorkflowStrategyCall` have all fields at top level (remove `WorkflowStrategy` wrapper)

---

### 3. ProjectOverviewAgent
**Current Prompt Output**:
```json
{
  "mermaid_code": "sequenceDiagram...",
  "agent_message": "Generated diagram..."
}
```

**Current Schema Expects**:
```json
{
  "MermaidSequenceDiagram": {
    "workflow_name": "...",
    "mermaid_diagram": "...",
    "legend": [...]
  },
  "agent_message": "..."
}
```

**FIX OPTIONS**:
- Option A: Update prompt to output full `MermaidSequenceDiagram` object
- Option B: Update schema to accept `mermaid_code` field directly

**RECOMMEND**: Option B (simpler, matches current behavior)

---

### 4. WorkflowArchitectAgent
**Current Prompt Output**:
```json
{
  "phase_technical_requirements": [...],
  "shared_requirements": {
    "workflow_context_variables": [...],
    "shared_tools": [...],
    "third_party_integrations": [...]
  },
  "agent_message": "..."
}
```

**Current Schema Expects**:
```json
{
  "phase_technical_requirements": [...],
  "shared_requirements": {...}
}
```

**FIX**: Add `agent_message` field to `TechnicalBlueprintCall` schema

---

### 5. WorkflowImplementationAgent
**Current Prompt Output**:
```json
{
  "phase_agents": [
    {
      "phase_index": 0,
      "agents": [
        {
          "name": "AgentName",
          "description": "...",
          "integrations": [...],
          "operations": [...],
          "human_interaction": "context"
        }
      ]
    }
  ],
  "agent_message": "..."
}
```

**Current Schema Expects**:
```json
{
  "phase_agents": [...]
}
```

**FIX**: Add `agent_message` field to `PhaseAgentsCall` schema

---

### 6. DownloadAgent
**Current Prompt Output**:
```json
{
  "confirmation_only": true,
  "storage_backend": "none",
  "description": "...",
  "agent_message": "..."
}
```

**Current Schema Expects**:
```json
{
  "DownloadRequest": {
    "confirmation_only": true,
    "storage_backend": "none",
    "description": "..."
  },
  "agent_message": "..."
}
```

**FIX OPTIONS**:
- Option A: Update prompt to wrap fields in `DownloadRequest` object
- Option B: Flatten schema to remove `DownloadRequest` wrapper

**RECOMMEND**: Option B (consistent with other fixes)

---

## Agents with TODO Placeholders (Need Prompt Completion)

### 7. ToolsManagerAgent
- Has TODO in `[OUTPUT FORMAT]`
- Schema expects: `ToolsManagerAgentOutput` with `tools` and `lifecycle_tools` arrays

**FIX**: Write complete [OUTPUT FORMAT] section matching schema

---

### 8. ContextVariablesAgent
- Has TODO in `[OUTPUT FORMAT]`
- Schema expects: `ContextVariablesAgentOutput` with `ContextVariablesPlan`

**FIX**: Write complete [OUTPUT FORMAT] section matching schema

---

### 9. UIFileGenerator
- Has TODO in `[OUTPUT FORMAT]`
- Schema expects: `UIFileGeneratorOutput` with `code_files` array

**FIX**: Write complete [OUTPUT FORMAT] section matching schema

---

### 10. AgentToolsFileGenerator
- Has TODO in `[OUTPUT FORMAT]`
- Schema expects: `AgentToolsFileGeneratorOutput` with `code_files` array

**FIX**: Write complete [OUTPUT FORMAT] section matching schema

---

### 11. StructuredOutputsAgent
- Has TODO in `[OUTPUT FORMAT]`
- Schema expects: `StructuredOutputsAgentOutput` with `models` and `registry` arrays

**FIX**: Write complete [OUTPUT FORMAT] section matching schema

---

## Minor Misalignments (Low Priority)

### 12. AgentsAgent
- Schema mismatch due to TODO placeholder
- Schema expects: `AgentsAgentOutput` with `agents` array

**FIX**: Write complete [OUTPUT FORMAT] section

---

### 13. HandoffsAgent
- Schema mismatch due to TODO placeholder
- Schema expects: `HandoffsAgentOutput` with `handoff_rules` array

**FIX**: Write complete [OUTPUT FORMAT] section

---

### 14. HookAgent
- Prompt shows `hook_files` array, schema expects `code_files` array
- Field name inconsistency

**FIX**: Align on single field name (recommend `code_files` for consistency with other generators)

---

### 15. OrchestratorAgent
- Missing `agent_message` field in schema

**FIX**: Add `agent_message` to `OrchestratorAgentOutput` schema

---

## Recommended Action Plan

### Phase 1: Schema Updates (Low Risk)
Update schemas to match current prompt outputs:
1. Flatten wrapper objects in:
   - `PatternSelectionCall`
   - `WorkflowStrategyCall`
   - `DownloadRequestCall`
   - `MermaidSequenceDiagramCall` (change `mermaid_diagram` → `mermaid_code`)
2. Add `agent_message` field to:
   - `TechnicalBlueprintCall`
   - `PhaseAgentsCall`
   - `OrchestratorAgentOutput`

### Phase 2: Complete TODO Sections (Medium Risk)
Write [OUTPUT FORMAT] sections for:
- ToolsManagerAgent
- ContextVariablesAgent
- UIFileGenerator
- AgentToolsFileGenerator
- StructuredOutputsAgent
- AgentsAgent
- HandoffsAgent

### Phase 3: Validation
Run validation script again to confirm 16/16 aligned

---

## Risk Assessment

**LOW RISK** (Schema updates):
- Changes don't affect agent behavior
- Only affects validation/parsing
- Easy to revert

**MEDIUM RISK** (Prompt completions):
- Need to write new content matching existing schemas
- Could introduce inconsistencies if not careful
- Requires testing

**HIGH RISK** (Prompt rewrites):
- Changes agent output format
- Could break downstream tools/runtime
- NOT RECOMMENDED unless absolutely necessary

---

## Next Steps

1. **Review this proposal** - Confirm approach
2. **Create schema update script** - Automate Phase 1 changes
3. **Run validation** - Verify alignment
4. **Complete TODOs manually** - Phase 2 (requires domain knowledge)
5. **Final validation** - Ensure 16/16 pass
