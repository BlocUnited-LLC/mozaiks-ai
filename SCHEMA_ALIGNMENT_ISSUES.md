# Schema Alignment Issues: agents.json vs structured_outputs.json

**Date**: 2025-11-03  
**Comparison Source**: AGENT_OUTPUT_FORMATS_VALIDATION.md (ground truth from agents.json [OUTPUT FORMAT]) vs structured_outputs.json

---

## Executive Summary

**Total Agents Analyzed**: 16  
**Agents with Misalignments**: 10  
**Agents Perfectly Aligned**: 6  
**Critical Issues**: 8  
**Minor Issues**: 12

### Critical Findings

1. **ToolsManagerAgent**: Missing `description` field in ToolSpec model (agents.json requires it)
2. **UIFileGenerator**: Wrong structure - uses `code_files[]` instead of `tools[]`
3. **AgentToolsFileGenerator**: Wrong structure - uses `code_files[]` instead of `tools[]`
4. **ProjectOverviewAgent**: Missing `agent_message` at root level
5. **AgentsAgent**: Missing `agent_message` at root level
6. **HookAgent**: Wrong structure - uses `code_files[]` instead of `hook_files[]` + missing `agent_message`
7. **HandoffsAgent**: Missing `agent_message` at root level
8. **OrchestratorAgent**: Missing `agent_message` at root level

---

## Agent-by-Agent Comparison

### ✅ 1. InterviewAgent - ALIGNED

**Ground Truth** (agents.json):
- Free-form text output (no structured JSON)
- structured_outputs_required = false

**structured_outputs.json**:
- Registry: `"InterviewAgent": null` ✅

**Status**: Perfect alignment

---

### ✅ 2. PatternAgent - ALIGNED

**Ground Truth** (agents.json):
```json
{
  "PatternSelection": {
    "selected_pattern": <int 1-9>,
    "pattern_name": "<string>"
  }
}
```

**structured_outputs.json**:
- Model: `PatternSelection` with fields `selected_pattern` (int), `pattern_name` (str) ✅
- Wrapper: `PatternSelectionCall` with field `PatternSelection` ✅
- Registry: `"PatternAgent": "PatternSelectionCall"` ✅

**Status**: Perfect alignment

---

### ⚠️ 3. WorkflowStrategyAgent - MISALIGNMENT

**Ground Truth** (agents.json):
```json
{
  "WorkflowStrategy": {
    "workflow_name": "<string>",
    "workflow_description": "<string>",
    "trigger": "chat|form_submit|schedule|database_condition|webhook",
    "initiated_by": "user|system|external_event",
    "pattern": ["<string>"],
    "phases": [
      {
        "phase_index": <int>,
        "phase_name": "<string>",
        "phase_description": "<string>",
        "human_in_loop": true|false,
        "agents_needed": "single|sequential|nested"
      }
    ]
  }
}
```

**structured_outputs.json**:
- Model: `WorkflowStrategy`
  - ❌ **EXTRA FIELD**: `lifecycle_operations` (NOT in agents.json [OUTPUT FORMAT])
  - ❌ **EXTRA FIELD**: `strategy_notes` (NOT in agents.json [OUTPUT FORMAT])
  - ❌ **MISSING FIELD**: `initiated_by` (present in agents.json)
  - ⚠️ **WRONG TYPE**: `trigger` (agents.json shows enum values, structured_outputs uses generic str)
  - ⚠️ **WRONG TYPE**: `pattern` (agents.json shows array `["<string>"]`, structured_outputs uses single str)
  
- Phase model: `WorkflowStrategyPhase`
  - ❌ **WRONG FIELD NAME**: `approval_required` (agents.json uses `human_in_loop`)
  - ❌ **EXTRA FIELD**: `specialist_domains` (NOT in agents.json [OUTPUT FORMAT])
  - ❌ **MISSING FIELD**: `phase_index` (present in agents.json)
  - ⚠️ **INCOMPLETE VALUES**: `agents_needed` (agents.json allows "single|sequential|nested", structured_outputs also lists "parallel" which is not used)

**Issues**:
1. Extra fields bloating the model
2. Missing `initiated_by` field
3. `trigger` should be enum, not generic str
4. `pattern` should be array of strings, not single string
5. Phase model has wrong field name (`approval_required` vs `human_in_loop`)
6. Phase missing `phase_index` field

---

### ⚠️ 4. WorkflowArchitectAgent (TechnicalBlueprint) - MISALIGNMENT

**Ground Truth** (agents.json):
```json
{
  "TechnicalBlueprint": {
    "phase_technical_requirements": [
      {
        "phase_index": <int>,
        "phase_name": "<string>",
        "required_tools": [
          {
            "name": "<string>",
            "type": "Agent_Tool|UI_Tool",
            "scope": "shared|phase_specific",
            "purpose": "<string>",
            "integration": "<string|null>"
          }
        ],
        "required_context_variables": [
          {
            "name": "<string>",
            "type": "static|environment|database|derived",
            "purpose": "<string>",
            "trigger_hint": "<string|null>"
          }
        ],
        "required_lifecycle_operations": [
          {
            "name": "<string>",
            "purpose": "<string>",
            "trigger": "before_chat|after_chat|before_agent|after_agent",
            "integration": "<string|null>"
          }
        ]
      }
    ],
    "shared_requirements": {
      "workflow_context_variables": ["<string>"],
      "shared_tools": ["<string>"],
      "third_party_integrations": ["<string>"]
    }
  }
}
```

**structured_outputs.json**:
- Model: `TechnicalBlueprint` ✅ (wrapper exists)
- Phase requirements model: `PhaseTechnicalRequirements` ✅ (structure matches)
- Required tools model: `RequiredTool`
  - ❌ **EXTRA FIELDS**: `owner_role`, `parameters`, `returns` (NOT in agents.json)
  - Field names match otherwise ✅

- Required context variables model: `RequiredContextVariable`
  - ❌ **EXTRA FIELDS**: `default`, `trigger`, `exposed_to` (NOT in agents.json)
  - ❌ **MISSING FIELD**: `trigger_hint` (present in agents.json)
  - ⚠️ **WRONG STRUCTURE**: agents.json uses `trigger_hint` (simple string), structured_outputs has complex `trigger` JSON field

- Required lifecycle operations model: `RequiredLifecycleOperation`
  - ❌ **MISSING FIELD**: `integration` (present in agents.json)
  - Fields otherwise match ✅

- Shared requirements model: `SharedRequirements`
  - ⚠️ **WRONG TYPE**: `workflow_context_variables` (agents.json shows array of strings, structured_outputs uses array of RequiredContextVariable objects)
  - ⚠️ **WRONG TYPE**: `shared_tools` (agents.json shows array of strings, structured_outputs uses array of RequiredTool objects)
  - ⚠️ **WRONG TYPE**: `third_party_integrations` (agents.json shows array of strings, structured_outputs uses array of ThirdPartyIntegration objects)

**Issues**:
1. RequiredTool has extra fields not in ground truth
2. RequiredContextVariable has wrong structure (complex trigger vs simple trigger_hint)
3. RequiredLifecycleOperation missing `integration` field
4. SharedRequirements uses wrong types (object arrays instead of string arrays)

---

### ⚠️ 5. WorkflowImplementationAgent (PhaseAgents) - MISALIGNMENT

**Ground Truth** (agents.json):
```json
{
  "PhaseAgents": {
    "phase_agents": [
      {
        "phase_index": <int>,
        "agents": [
          {
            "agent_name": "<PascalCaseAgentName>",
            "description": "<Comprehensive role description>",
            "agent_tools": [...],
            "lifecycle_tools": [...],
            "system_hooks": [...],
            "integrations": ["<string>"],
            "human_interaction": "context|approval|none"
          }
        ]
      }
    ]
  }
}
```

**structured_outputs.json**:
- Wrapper model: `PhaseAgentsCall` ✅
- Core model: Uses array of `PhaseAgents` objects ✅
- Agent model: `WorkflowAgent`
  - ❌ **WRONG FIELD NAME**: `name` (agents.json uses `agent_name`)
  - ❌ **MISSING FIELDS**: `agent_tools`, `lifecycle_tools`, `system_hooks` (present in agents.json)
  - ❌ **EXTRA FIELD**: `operations` (NOT in agents.json [OUTPUT FORMAT])
  - Fields match: `description`, `integrations`, `human_interaction` ✅

**Issues**:
1. WorkflowAgent field name mismatch (`name` vs `agent_name`)
2. Missing critical fields: `agent_tools`, `lifecycle_tools`, `system_hooks`
3. Extra field: `operations` not in ground truth

---

### ⚠️ 6. ProjectOverviewAgent (MermaidSequenceDiagram) - MISALIGNMENT

**Ground Truth** (agents.json):
```json
{
  "MermaidSequenceDiagram": {
    "workflow_name": "<string>",
    "mermaid_diagram": "<Mermaid sequence diagram string>",
    "legend": ["<string>"]
  },
  "agent_message": "<Summary for the user-facing UI>"
}
```

**structured_outputs.json**:
- Core model: `MermaidSequenceDiagram`
  - Field `workflow_name` ✅
  - Field `mermaid_diagram` ✅
  - Field `legend` ✅

- Wrapper model: `MermaidSequenceDiagramCall`
  - Field `MermaidSequenceDiagram` ✅
  - Field `agent_message` ✅

**Status**: ✅ **ALIGNED** (wrapper correctly includes agent_message)

---

### ✅ 7. ContextVariablesAgent - ALIGNED

**Ground Truth** (agents.json):
```json
{
  "ContextVariablesPlan": {
    "definitions": [...],
    "agents": [...]
  }
}
```

**structured_outputs.json**:
- Model: `ContextVariablesPlan` with `definitions` and `agents` arrays ✅
- Wrapper: `ContextVariablesAgentOutput` with `ContextVariablesPlan` field ✅
- Registry: `"ContextVariablesAgent": "ContextVariablesAgentOutput"` ✅

**Status**: Perfect alignment

---

### ❌ 8. ToolsManagerAgent - CRITICAL MISALIGNMENT

**Ground Truth** (agents.json):
```json
{
  "tools": [
    {
      "agent": "<PascalCaseAgentName>",
      "file": "<snake_case>.py",
      "function": "<snake_case>",
      "description": "<<=140 chars>",
      "tool_type": "Agent_Tool" | "UI_Tool",
      "auto_invoke": true | false,
      "ui": {
        "component": "<PascalCaseComponent>",
        "mode": "artifact" | "inline"
      } | null
    }
  ],
  "lifecycle_tools": [...]
}
```

**structured_outputs.json**:
- Model: `ToolsManagerAgentOutput` ✅
- Tool model: `ToolSpec`
  - Field `agent` ✅
  - Field `file` ✅
  - Field `function` ✅
  - ❌ **MISSING FIELD**: `description` (present in agents.json, required field)
  - Field `tool_type` ✅
  - Field `auto_invoke` ✅
  - Field `ui` (UIConfig model) ✅

**Issues**:
1. **CRITICAL**: Missing `description` field in ToolSpec - this is a required field in ground truth

---

### ❌ 9. UIFileGenerator - CRITICAL MISALIGNMENT

**Ground Truth** (agents.json):
```json
{
  "tools": [
    {
      "tool_name": "<snake_case>",
      "py_content": "<complete_python_async_function>",
      "js_content": "<complete_react_component>"
    }
  ]
}
```

**structured_outputs.json**:
- Model: `UIFileGeneratorOutput`
  - ❌ **WRONG FIELD NAME**: `code_files` (agents.json uses `tools`)
  - Uses `CodeFile` model with `filename` and `content` fields
  - ❌ **WRONG STRUCTURE**: CodeFile has `filename`, `content`, `installRequirements`
  - ✅ **CORRECT STRUCTURE**: Should have `tool_name`, `py_content`, `js_content`

**Issues**:
1. **CRITICAL**: Wrong root field name (`code_files` vs `tools`)
2. **CRITICAL**: Wrong nested structure (CodeFile vs tool object)
3. **CRITICAL**: Missing `py_content` and `js_content` fields
4. **CRITICAL**: Extra `installRequirements` field

---

### ❌ 10. AgentToolsFileGenerator - CRITICAL MISALIGNMENT

**Ground Truth** (agents.json):
```json
{
  "tools": [
    {
      "tool_name": "<snake_case>",
      "py_content": "<complete_python_function>"
    }
  ]
}
```

**structured_outputs.json**:
- Model: `AgentToolsFileGeneratorOutput`
  - ❌ **WRONG FIELD NAME**: `code_files` (agents.json uses `tools`)
  - Uses `CodeFile` model with `filename`, `content`, `installRequirements`
  - ❌ **WRONG STRUCTURE**: Should have `tool_name`, `py_content`

**Issues**:
1. **CRITICAL**: Wrong root field name (`code_files` vs `tools`)
2. **CRITICAL**: Wrong nested structure (CodeFile vs tool object)
3. **CRITICAL**: Missing `py_content` field
4. **CRITICAL**: Extra `installRequirements` field

---

### ✅ 11. StructuredOutputsAgent - ALIGNED

**Ground Truth** (agents.json):
```json
{
  "models": [...],
  "registry": [...]
}
```

**structured_outputs.json**:
- Model: `StructuredOutputsAgentOutput` with `models` and `registry` arrays ✅
- Registry: `"StructuredOutputsAgent": "StructuredOutputsAgentOutput"` ✅

**Status**: Perfect alignment

---

### ⚠️ 12. AgentsAgent (RuntimeAgentsCall) - MISALIGNMENT

**Ground Truth** (agents.json):
```json
{
  "agents": [
    {
      "name": "<PascalCaseAgentName>",
      "display_name": "<Display Name>",
      "prompt_sections": [...],
      "max_consecutive_auto_reply": <int>,
      "auto_tool_mode": true|false,
      "structured_outputs_required": true|false
    }
  ],
  "agent_message": "<Summary>"
}
```

**structured_outputs.json**:
- Model: `AgentsAgentOutput`
  - Field `agents` (array of AgentDefinition) ✅
  - ❌ **MISSING FIELD**: `agent_message` (present in agents.json at root level)

- AgentDefinition model:
  - Field `name` ✅
  - Field `display_name` ✅
  - Field `prompt_sections` (PromptSections model) ✅
  - Field `max_consecutive_auto_reply` ✅
  - Field `auto_tool_mode` ✅
  - Field `structured_outputs_required` ✅
  - ⚠️ **EXTRA FIELDS**: `agent_type`, `prompt_sections_custom`, `image_generation_enabled` (NOT in agents.json [OUTPUT FORMAT])

**Issues**:
1. Missing root-level `agent_message` field
2. Extra fields in AgentDefinition not present in ground truth

---

### ❌ 13. HookAgent (HookImplementationCall) - CRITICAL MISALIGNMENT

**Ground Truth** (agents.json):
```json
{
  "hook_files": [
    {
      "filename": "<hook_name>.py",
      "hook_type": "before_chat|after_chat|update_agent_state",
      "py_content": "<Python hook function code>"
    }
  ],
  "agent_message": "<Summary of hook generation>"
}
```

**structured_outputs.json**:
- Model: `HookAgentOutput`
  - ❌ **WRONG FIELD NAME**: `code_files` (agents.json uses `hook_files`)
  - ❌ **MISSING FIELD**: `agent_message` (present in agents.json at root level)
  - Uses `CodeFile` model ❌ (wrong structure)

- Hook model: `Hook`
  - ❌ **EXTRA FIELDS**: `hook_agent`, `function`, `filecontent` (NOT in agents.json)
  - ❌ **MISSING FIELD**: `py_content` (present in agents.json)
  - Field `hook_type` ✅
  - Field `filename` ✅

**Issues**:
1. **CRITICAL**: Wrong root field name (`code_files` vs `hook_files`)
2. **CRITICAL**: Missing root-level `agent_message` field
3. Wrong nested model (uses Hook + CodeFile, should be simpler structure)
4. Extra and missing fields in hook object

---

### ⚠️ 14. HandoffsAgent - MISALIGNMENT

**Ground Truth** (agents.json):
```json
{
  "handoff_rules": [
    {
      "source_agent": "<AgentName>|user",
      "target_agent": "<AgentName>|TERMINATE",
      "handoff_type": "after_work|condition",
      "condition_type": "expression|string_llm|null",
      "condition_scope": "pre|null",
      "condition": "<expression string>|null",
      "transition_target": "AgentTarget"
    }
  ],
  "agent_message": "<Summary of handoff rules>"
}
```

**structured_outputs.json**:
- Model: `HandoffsAgentOutput`
  - Field `handoff_rules` (array of HandoffRule) ✅
  - ❌ **MISSING FIELD**: `agent_message` (present in agents.json at root level)

- HandoffRule model:
  - Field `source_agent` ✅
  - Field `target_agent` ✅
  - Field `handoff_type` ✅
  - Field `condition` ✅
  - Field `condition_type` ✅
  - Field `condition_scope` ✅
  - Field `transition_target` ✅

**Issues**:
1. Missing root-level `agent_message` field

---

### ⚠️ 15. OrchestratorAgent - MISALIGNMENT

**Ground Truth** (agents.json):
```json
{
  "workflow_name": "<WorkflowName>",
  "max_turns": <int>,
  "human_in_the_loop": true,
  "startup_mode": "AgentDriven|UserDriven",
  "orchestration_pattern": "<PatternName>",
  "initial_message_to_user": null,
  "initial_message": "<greeting string>|null",
  "recipient": "<FirstAgentName>",
  "visual_agents": ["<AgentName1>", "<AgentName2>"],
  "agent_message": "<Summary of orchestration config>"
}
```

**structured_outputs.json**:
- Model: `OrchestratorAgentOutput`
  - Field `workflow_name` ✅
  - Field `max_turns` ✅
  - Field `human_in_the_loop` ✅
  - Field `startup_mode` ✅ (has extra value "BackendOnly" not in agents.json)
  - Field `orchestration_pattern` ✅
  - Field `initial_message_to_user` ✅
  - Field `initial_message` ✅
  - Field `recipient` ✅
  - Field `visual_agents` ✅
  - ❌ **MISSING FIELD**: `agent_message` (present in agents.json at root level)

**Issues**:
1. Missing root-level `agent_message` field
2. Extra startup_mode value "BackendOnly" not documented in ground truth

---

### ⚠️ 16. DownloadAgent (DownloadRequestCall) - MISALIGNMENT

**Ground Truth** (agents.json):
```json
{
  "agent_message": "<Brief context message for UI>"
}
```

**structured_outputs.json**:
- Wrapper model: `DownloadRequestCall`
  - ❌ **EXTRA FIELD**: `DownloadRequest` (NOT in agents.json [OUTPUT FORMAT])
  - Field `agent_message` ✅

- DownloadRequest model:
  - ❌ **EXTRA FIELDS**: `confirmation_only`, `storage_backend`, `description` (NOT in ground truth)

**Issues**:
1. Extra wrapper field `DownloadRequest` not present in ground truth
2. Ground truth shows only `agent_message` at root level

---

## Summary of Issues by Category

### Missing Fields (agents.json has, structured_outputs.json doesn't)

1. **WorkflowStrategy**: `initiated_by`
2. **WorkflowStrategyPhase**: `phase_index`, `human_in_loop` (has `approval_required` instead)
3. **RequiredContextVariable**: `trigger_hint`
4. **RequiredLifecycleOperation**: `integration`
5. **WorkflowAgent**: `agent_name` (has `name`), `agent_tools`, `lifecycle_tools`, `system_hooks`
6. **ToolSpec**: `description`
7. **AgentsAgentOutput**: `agent_message` (root level)
8. **HookAgentOutput**: `agent_message` (root level), `hook_files` (has `code_files`), `py_content`
9. **HandoffsAgentOutput**: `agent_message` (root level)
10. **OrchestratorAgentOutput**: `agent_message` (root level)

### Extra Fields (structured_outputs.json has, agents.json doesn't)

1. **WorkflowStrategy**: `lifecycle_operations`, `strategy_notes`
2. **WorkflowStrategyPhase**: `approval_required` (should be `human_in_loop`), `specialist_domains`
3. **RequiredTool**: `owner_role`, `parameters`, `returns`
4. **RequiredContextVariable**: `default`, `trigger`, `exposed_to`
5. **WorkflowAgent**: `operations`
6. **AgentDefinition**: `agent_type`, `prompt_sections_custom`, `image_generation_enabled`
7. **Hook**: `hook_agent`, `function`, `filecontent`
8. **DownloadRequestCall**: `DownloadRequest` wrapper
9. **DownloadRequest**: `confirmation_only`, `storage_backend`, `description`

### Wrong Types

1. **WorkflowStrategy.trigger**: Should be enum, not generic str
2. **WorkflowStrategy.pattern**: Should be array of strings, not single string
3. **SharedRequirements** fields: Should be string arrays, not object arrays

### Wrong Structure

1. **UIFileGenerator**: Uses `code_files` + `CodeFile` instead of `tools` + tool object with `py_content`/`js_content`
2. **AgentToolsFileGenerator**: Uses `code_files` + `CodeFile` instead of `tools` + tool object with `py_content`
3. **HookAgent**: Uses `code_files` + `Hook` + `CodeFile` instead of `hook_files` + simpler hook object

---

## Recommended Fixes

### Priority 1: Critical Structural Fixes

1. **UIFileGenerator**: Replace `code_files` with `tools`, add `tool_name`, `py_content`, `js_content` fields
2. **AgentToolsFileGenerator**: Replace `code_files` with `tools`, add `tool_name`, `py_content` fields
3. **HookAgent**: Replace `code_files` with `hook_files`, simplify structure, add `agent_message`
4. **ToolsManagerAgent**: Add `description` field to ToolSpec

### Priority 2: Missing Root-Level Fields

5. **AgentsAgent**: Add `agent_message` to AgentsAgentOutput
6. **HandoffsAgent**: Add `agent_message` to HandoffsAgentOutput
7. **OrchestratorAgent**: Add `agent_message` to OrchestratorAgentOutput

### Priority 3: Field Name/Type Corrections

8. **WorkflowStrategy**: Add `initiated_by`, fix `trigger` to enum, fix `pattern` to array
9. **WorkflowStrategyPhase**: Rename `approval_required` to `human_in_loop`, add `phase_index`, remove `specialist_domains`
10. **WorkflowAgent**: Rename `name` to `agent_name`, add `agent_tools`/`lifecycle_tools`/`system_hooks`, remove `operations`

### Priority 4: Clean Up Extra Fields

11. Remove extra fields from models where they don't match ground truth
12. Simplify SharedRequirements to use string arrays instead of object arrays

---

## Next Steps

1. Apply fixes to structured_outputs.json in priority order
2. Validate each fix against AGENT_OUTPUT_FORMATS_VALIDATION.md
3. Run schema validation tests
4. Update pattern guidance to reference corrected inline schemas
