# Structured Outputs JSON Audit

**Date**: November 19, 2025  
**Purpose**: Identify unused models in `workflows/Generator/structured_outputs.json`

---

## Summary

The `structured_outputs.json` file contains **orphaned models** that are NOT referenced by any agent output or downstream model. These should be removed to reduce maintenance burden and prevent confusion.

---

## Registry Analysis (What Agents Actually Output)

From `structured_outputs.json` lines 1637-1656:

```json
"registry": {
  "InterviewAgent": null,
  "PatternAgent": "PatternSelectionOutput",
  "WorkflowStrategyAgent": "WorkflowStrategyOutput",
  "WorkflowArchitectAgent": "TechnicalBlueprintOutput",
  "WorkflowImplementationAgent": "PhaseAgentsOutput",
  "ProjectOverviewAgent": "MermaidSequenceDiagramOutput",
  "ToolsManagerAgent": "ToolsManifestOutput",
  "UIFileGenerator": "UIToolsFilesOutput",
  "AgentToolsFileGenerator": "AgentToolsFilesOutput",
  "HookAgent": "HookFilesOutput",
  "AgentsAgent": "RuntimeAgentsOutput",
  "ContextVariablesAgent": "ContextVariablesPlanOutput",
  "OrchestratorAgent": "OrchestrationConfigOutput",
  "HandoffsAgent": "HandoffRulesOutput",
  "StructuredOutputsAgent": "StructuredModelsOutput",
  "DownloadAgent": "DownloadRequestOutput"
}
```

---

## Model Dependency Chain

### **ContextVariablesAgent Output Chain** ✅ IN USE

```
ContextVariablesPlanOutput
  └─ ContextVariablesPlan
      ├─ definitions[] → ContextVariableDefinitionEntry
      │   └─ source → ContextVariableSource ⚠️ NEEDS UPDATE (4 types → 6 types)
      │       └─ triggers[] → DerivedTrigger
      │           └─ match → DerivedTriggerMatch
      └─ agents[] → ContextVariableAgentExposure
```

**Status**: All models in this chain are USED

---

### **WorkflowArchitectAgent Output Chain** ✅ IN USE

```
TechnicalBlueprintOutput
  └─ TechnicalBlueprint
      ├─ global_context_variables[] → RequiredContextVariable ✅ USED
      ├─ ui_components[] → WorkflowUIComponent ✅ USED
      ├─ before_chat_lifecycle → WorkflowLifecycleToolRef ✅ USED
      ├─ after_chat_lifecycle → WorkflowLifecycleToolRef ✅ USED
      ├─ workflow_dependencies → WorkflowDependencies ✅ USED
```

**Status**: Uses `RequiredContextVariable` (NOT `PhaseTechnicalRequirements` or `SharedRequirements`)

---

### **WorkflowImplementationAgent Output Chain** ✅ IN USE

```
PhaseAgentsOutput
  └─ PhaseAgents[] (array of PhaseAgents models)
      └─ agents[] → AgentDefinition
          ├─ agent_tools[] → RequiredTool ✅ USED
          ├─ lifecycle_tools[] → RequiredLifecycleOperation ✅ USED
          └─ integrations[] → ThirdPartyIntegration ✅ USED
```

**Status**: Uses `RequiredTool`, `RequiredLifecycleOperation`, NOT `PhaseTechnicalRequirements`

---

## Orphaned Models ❌ NOT USED ANYWHERE

### 1. **PhaseTechnicalRequirements** (Lines 1227-1253)

```json
"PhaseTechnicalRequirements": {
  "type": "model",
  "fields": {
    "phase_index": {"type": "int"},
    "phase_name": {"type": "str"},
    "required_tools": {"type": "list", "items": "RequiredTool"},
    "required_context_variables": {"type": "list", "items": "RequiredContextVariable"},
    "required_lifecycle_operations": {"type": "list", "items": "RequiredLifecycleOperation"}
  }
}
```

**Why Orphaned**:
- NOT referenced by any agent output model
- NOT used in TechnicalBlueprint (uses `global_context_variables[]` directly)
- NOT used in PhaseAgents (uses inline `agent_tools[]` and `lifecycle_tools[]`)
- Seems like an abandoned intermediate design

**Search Results**:
- Only appears in `structured_outputs.json` definition
- No Python code references
- No agent prompt references
- No runtime references

---

### 2. **SharedRequirements** (Lines 1255-1278)

```json
"SharedRequirements": {
  "type": "model",
  "fields": {
    "shared_tools": {"type": "list", "items": "RequiredTool"},
    "shared_context_variables": {"type": "list", "items": "RequiredContextVariable"},
    "shared_lifecycle_operations": {"type": "list", "items": "RequiredLifecycleOperation"}
  }
}
```

**Why Orphaned**:
- NOT referenced by any agent output model
- TechnicalBlueprint uses `global_context_variables[]` instead
- Concept of "shared" vs "phase-specific" moved to `RequiredTool.scope` field
- Abandoned intermediate design

**Search Results**:
- Only appears in `structured_outputs.json` definition
- No Python code references
- No agent prompt references
- No runtime references

---

## Legacy Models (Backwards Compatibility) ⚠️ DEPRECATED BUT KEPT

### **DatabaseRef, DatabaseVariable, EnvironmentVariable, DeclarativeVariable** (Lines 175-350)

These models have DEPRECATION NOTES:

```json
"DatabaseRef": {
  "description": "Kept for backwards compatibility. New context variables use definitions+agents structure with source.type discrimination via ContextVariableSource"
}
```

**Status**: Kept for backwards compatibility but NOT used by Generator agents  
**Runtime**: Uses `core/workflow/context/schema.py` with SIX-TYPE taxonomy instead  
**Action**: Leave in place (marked as deprecated)

---

## Recommendations

### ✅ **Remove Immediately** (No Dependencies)

1. **PhaseTechnicalRequirements** - Completely unused, no references
2. **SharedRequirements** - Completely unused, replaced by other patterns

### ⚠️ **Keep (Backwards Compatibility)**

1. **DatabaseRef, DatabaseVariable, EnvironmentVariable, DeclarativeVariable** - Already marked deprecated, leave for legacy runtime support

### 🔧 **Update (Current Task)**

1. **ContextVariableSource** - Update from 4-type to 6-type taxonomy (lines 440-530)

---

## Impact Assessment

### Removing PhaseTechnicalRequirements & SharedRequirements:

**Risk**: ✅ **ZERO**  
**Reason**: 
- Not in agent registry
- Not referenced by any output models
- Not used in runtime validation
- Not used in agent prompts

**Benefits**:
- Reduced JSON file size
- Less confusion about which models to use
- Cleaner schema for future agents

---

## Context Variables Model Usage Summary

**CURRENT PRODUCTION FLOW**:

```
WorkflowArchitectAgent
  ↓ outputs TechnicalBlueprint
  ├─ global_context_variables[] (RequiredContextVariable)
  │   └─ Contains: name, type (6-type taxonomy), trigger_hint, purpose
  │
ContextVariablesAgent  
  ↓ reads global_context_variables[]
  ↓ outputs ContextVariablesPlan
  ├─ definitions[] (ContextVariableDefinitionEntry)
  │   └─ source (ContextVariableSource) ⚠️ Currently 4-type, needs 6-type
  │       └─ type: "database"|"environment"|"static"|"derived" ❌ LEGACY
  │       └─ type: "config"|"data_reference"|"data_entity"|"computed"|"state"|"external" ✅ TARGET
  │
Runtime
  ↓ validates against core/workflow/context/schema.py
  └─ Already uses 6-type ContextVariableSource ✅
```

**KEY FINDING**: Runtime schema (`core/workflow/context/schema.py`) ALREADY supports 6-type taxonomy! Only `structured_outputs.json` needs updating for Generator agent validation.

---

## Next Actions

### Phase 1: Cleanup (Optional)
1. Remove `PhaseTechnicalRequirements` (lines 1227-1253)
2. Remove `SharedRequirements` (lines 1255-1278)
3. Validate JSON syntax still correct

### Phase 2: Context Variables Alignment (Primary Task)
1. Update `ContextVariableSource.type` from 4 literals to 6 literals
2. Add type-specific fields (refresh_strategy, write_strategy, etc.)
3. Follow alignment strategy from `CONTEXT_VARIABLES_SIX_TYPE_ALIGNMENT.md`

---

## Validation Commands

```bash
# Validate JSON syntax
python -c "import json; json.load(open('workflows/Generator/structured_outputs.json')); print('✅ Valid JSON')"

# Check for orphaned model references
grep -r "PhaseTechnicalRequirements" workflows/ core/
grep -r "SharedRequirements" workflows/ core/

# Verify no runtime dependencies
grep -r "PhaseTechnicalRequirements\|SharedRequirements" core/workflow/outputs/structured.py
```

---

## Conclusion

**Orphaned Models Found**: 2 (PhaseTechnicalRequirements, SharedRequirements)  
**Safe to Remove**: ✅ YES (zero dependencies)  
**Primary Task**: Update ContextVariableSource to 6-type taxonomy  
**Runtime Alignment**: Runtime already supports 6-type, only Generator validation needs updating
