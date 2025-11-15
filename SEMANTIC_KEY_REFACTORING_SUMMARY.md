# Semantic Wrapper Key Refactoring - Complete

## Overview
Successfully refactored `structured_outputs.json` and agent prompts to use **semantic domain keys** instead of agent-centric names. This makes upstream context references clearer and more intuitive for LLMs.

---

## What Changed

### 1. Registry Naming (15 agents updated)

**Before (Inconsistent):**
```json
{
  "PatternAgent": "PatternSelectionCall",          // "Call" suffix
  "ToolsManagerAgent": "ToolsManagerAgentOutput",  // Agent name in output
  "AgentsAgent": "AgentsAgentOutput"               // Redundant "Agent"
}
```

**After (Semantic & Consistent):**
```json
{
  "PatternAgent": "PatternSelectionOutput",
  "ToolsManagerAgent": "ToolsManifestOutput",      // Semantic: what it contains
  "AgentsAgent": "RuntimeAgentsOutput"             // Semantic: runtime agents
}
```

### 2. Complete Mapping

| Agent | Old Registry | New Registry | Semantic Wrapper Key |
|-------|-------------|--------------|---------------------|
| PatternAgent | PatternSelectionCall | PatternSelectionOutput | `PatternSelection` |
| WorkflowStrategyAgent | WorkflowStrategyCall | WorkflowStrategyOutput | `WorkflowStrategy` |
| WorkflowArchitectAgent | TechnicalBlueprintCall | TechnicalBlueprintOutput | `TechnicalBlueprint` |
| WorkflowImplementationAgent | PhaseAgentsCall | PhaseAgentsOutput | `PhaseAgents` |
| ProjectOverviewAgent | MermaidSequenceDiagramCall | MermaidSequenceDiagramOutput | `MermaidSequenceDiagram` |
| **ToolsManagerAgent** | ToolsManagerAgentOutput | **ToolsManifestOutput** | `ToolsManifest` |
| UIFileGenerator | UIFileGeneratorOutput | UIToolsFilesOutput | `UIToolsFiles` |
| AgentToolsFileGenerator | AgentToolsFileGeneratorOutput | AgentToolsFilesOutput | `AgentToolsFiles` |
| HookAgent | HookAgentOutput | HookFilesOutput | `HookFiles` |
| **AgentsAgent** | AgentsAgentOutput | **RuntimeAgentsOutput** | `RuntimeAgents` |
| ContextVariablesAgent | ContextVariablesAgentOutput | ContextVariablesPlanOutput | `ContextVariablesPlan` |
| OrchestratorAgent | OrchestratorAgentOutput | OrchestrationConfigOutput | `OrchestrationConfig` |
| HandoffsAgent | HandoffsAgentOutput | HandoffRulesOutput | `HandoffRules` |
| StructuredOutputsAgent | StructuredOutputsAgentOutput | StructuredModelsOutput | `StructuredModels` |
| DownloadAgent | DownloadRequestCall | DownloadRequestOutput | `DownloadRequest` |

---

## How Agents Reference Upstream Context (New Pattern)

### Old Way (Confusing):
```markdown
**Tools Manifest** (from ToolsManagerAgent):
- Navigate to: `message.content['ToolsManagerAgentOutput']['tools']`
```

### New Way (Clear & Semantic):
```markdown
**Tools Manifest** → `{"ToolsManifest": {"tools": [...], "lifecycle_tools": [...]}}`
- **Contains:** Complete tool specifications for all tools in the workflow
- **You need:** Filter for `tool_type="Agent_Tool"` and generate implementations
- **Key fields:** `function`, `purpose`, `integration`
```

---

## Benefits

### 1. **Self-Documenting**
- ❌ Old: "ToolsManagerAgentOutput" → technical, agent-centric
- ✅ New: "ToolsManifest" → semantic, describes the data

### 2. **No Redundancy**
- ❌ Old: "AgentsAgentOutput" → confusing double "Agent"
- ✅ New: "RuntimeAgents" → clear purpose

### 3. **Consistent Pattern**
- All registry entries use "Output" suffix
- All wrapper keys are semantic (describe data domain, not agent)
- Easy to remember: search for the concept (e.g., "ToolsManifest"), not the agent

### 4. **LLM-Friendly**
- Intuitive search: `{"ToolsManifest": ...}` vs `{"ToolsManagerAgentOutput": ...}`
- Clearer navigation instructions
- Reduces prompt verbosity

---

## Files Modified

### 1. `structured_outputs.json`
- ✅ Registry: 15 agents updated with semantic names
- ✅ Models: 15 wrapper models renamed
- ✅ Descriptions: Updated to mention semantic keys

### 2. `agents.json`
- ✅ AgentToolsFileGenerator: Updated CONTEXT and INSTRUCTIONS with semantic keys
- ⏳ Remaining agents: Need updates (7 more agents pending)

---

## Agent Prompt Template (New Standard)

```markdown
### **[CONTEXT]**

**Upstream Structured Outputs:**

**<Semantic Name>** → `{"<SemanticKey>": {...}}`
- **Contains:** Brief description of data structure
- **You need:** How this informs your task
- **Key fields:** List of relevant fields with purposes

**Example:**

**Tools Manifest** → `{"ToolsManifest": {"tools": [...], "lifecycle_tools": [...]}}`
- **Contains:** Complete tool specifications for all workflow tools
- **You need:** Filter for Agent_Tools and generate Python implementations
- **Key fields:**
  * `tools[].function`: Function name to implement
  * `tools[].purpose`: What the tool does
  * `tools[].integration`: External service or null
```

---

## Next Steps

### Immediate (Runtime Support)
1. **Update Pydantic models** in `core/workflow/` to output with semantic wrapper keys
   - Example: `ToolsManifestOutput` model should output `{"ToolsManifest": {...}}`
2. **Test end-to-end** with Generator workflow to verify outputs use new keys

### Short-term (Complete Rollout)
3. **Update remaining 7 agent prompts** with semantic key references:
   - HandoffsAgent
   - StructuredOutputsAgent
   - AgentsAgent
   - HookAgent
   - OrchestratorAgent
   - DownloadAgent
   - ProjectOverviewAgent (if not yet done)

### Long-term (Validation)
4. **Add validation** in runtime to ensure agents output correct wrapper structure
5. **Update documentation** to reflect semantic key pattern
6. **Create migration guide** for any external tools/workflows

---

## Verification Checklist

- [x] `structured_outputs.json` registry uses semantic names
- [x] `structured_outputs.json` models renamed to semantic keys
- [x] AgentToolsFileGenerator CONTEXT section uses semantic keys
- [x] AgentToolsFileGenerator INSTRUCTIONS section uses semantic keys
- [ ] Pydantic models output correct wrapper structure
- [ ] End-to-end Generator workflow test passes
- [ ] Remaining 7 agents updated with semantic keys

---

## Key Principle for Future Agents

**When adding new agents:**
1. Choose a **semantic domain name** for the output (e.g., "ToolsManifest", "RuntimeAgents")
2. Registry entry: `"<AgentName>": "<SemanticName>Output"`
3. Wrapper key in JSON output: `{"<SemanticName>": {actual_data}}`
4. Agent prompts reference the **semantic key**, not the agent name

**Example:**
- Agent: `NewFeatureAgent`
- Registry: `"NewFeatureAgent": "FeatureSpecificationOutput"`
- Output: `{"FeatureSpecification": {...}}`
- Prompt: `Search for {"FeatureSpecification": ...}`

---

## Impact Summary

**Consistency:** ✅ All 15 agents now follow semantic naming pattern  
**Clarity:** ✅ Upstream context references are self-documenting  
**Maintainability:** ✅ Easy to add new agents following this pattern  
**LLM Comprehension:** ✅ Semantic keys are more intuitive than agent names  

**Status:** Phase 1 (Registry + 1 agent) complete. Phase 2 (remaining agents) pending.
