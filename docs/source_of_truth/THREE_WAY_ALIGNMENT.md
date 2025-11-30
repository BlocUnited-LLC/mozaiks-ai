# Three-Way Alignment Verification

> **Created**: 2025-11-30
> **Purpose**: Verify alignment between SOURCE_OF_TRUTH ↔ structured_outputs.json ↔ agents.json [OUTPUT FORMAT]

---

## Verification Methodology

For each design agent, we verify:
1. **SOURCE_OF_TRUTH.md** - What the doc says the output looks like
2. **structured_outputs.json** - What the Pydantic model actually enforces
3. **agents.json [OUTPUT FORMAT]** - What we tell the agent to produce

All three MUST be identical.

---

## 1. PatternAgent → PatternSelectionOutput

### SOURCE_OF_TRUTH.md (Section 3.1)
```json
{
  "PatternSelection": {
    "selected_pattern": 1,       // int (1-9)
    "pattern_name": "Context-Aware Routing"  // human-readable
  }
}
```

### structured_outputs.json
```json
"PatternSelection": {
  "type": "model",
  "fields": {
    "selected_pattern": { "type": "int", "description": "Pattern ID (1-9)..." },
    "pattern_name": { "type": "str", "description": "Human-readable pattern name..." }
  }
}
"PatternSelectionOutput": {
  "fields": {
    "PatternSelection": { "type": "PatternSelection", ... }
  }
}
```

### agents.json [OUTPUT FORMAT]
```json
{
  "PatternSelection": {
    "selected_pattern": <int 1-9>,
    "pattern_name": "<string matching pattern legend>"
  }
}
```

### ✅ ALIGNED
All three match exactly.

---

## 2. WorkflowStrategyAgent → WorkflowStrategyOutput

### SOURCE_OF_TRUTH.md (Section 3.2)
```json
{
  "WorkflowStrategy": {
    "workflow_name": "Customer Support Router",
    "workflow_description": "When [TRIGGER], workflow [ACTIONS], resulting in [VALUE]",
    "human_in_loop": true,
    "pattern": ["ContextAwareRouting"],
    "trigger": "chat",
    "initiated_by": "user",
    "modules": [
      {
        "module_name": "Module 1: Request Classification",
        "module_index": 0,
        "module_description": "...",
        "pattern_id": 1,
        "pattern_name": "Context-Aware Routing",
        "agents_needed": ["RouterAgent", "TechSpecialist", "FinanceSpecialist"]
      }
    ]
  }
}
```

### structured_outputs.json
```json
"WorkflowStrategy": {
  "fields": {
    "workflow_name": { "type": "str" },
    "workflow_description": { "type": "str" },
    "human_in_loop": { "type": "bool" },
    "pattern": { "type": "list", "items": "str" },
    "trigger": { "type": "literal", "values": ["chat", "form_submit", "schedule", "database_condition", "webhook"] },
    "initiated_by": { "type": "literal", "values": ["user", "system", "external_event"] },
    "modules": { "type": "list", "items": "WorkflowStrategyModule" }
  }
}
"WorkflowStrategyModule": {
  "fields": {
    "module_name": { "type": "str" },
    "module_index": { "type": "int" },
    "module_description": { "type": "str" },
    "pattern_id": { "type": "int" },
    "pattern_name": { "type": "str" },
    "agents_needed": { "type": "list", "items": "str" }
  }
}
```

### agents.json [OUTPUT FORMAT]
```json
{
  "WorkflowStrategy": {
    "workflow_name": "<string>",
    "workflow_description": "<string>",
    "trigger": "chat|form_submit|schedule|database_condition|webhook",
    "initiated_by": "user|system|external_event",
    "human_in_loop": true|false,
    "pattern": ["<string>"],
    "modules": [
      {
        "module_index": <int>,
        "module_name": "<string>",
        "module_description": "<string>",
        "pattern_id": <int>,
        "pattern_name": "<string>",
        "agents_needed": ["<string>", "<string>"]
      }
    ]
  }
}
```

### ✅ ALIGNED
All three match exactly.

---

## 3. WorkflowArchitectAgent → TechnicalBlueprintOutput

### SOURCE_OF_TRUTH.md (Section 3.3)
```json
{
  "TechnicalBlueprint": {
    "global_context_variables": [
      {
        "name": "current_domain",
        "type": "state",
        "purpose": "...",
        "trigger_hint": "..."
      }
    ],
    "ui_components": [
      {
        "module_name": "Module 1: Request Classification",
        "agent": "RouterAgent",
        "tool": "request_clarification",
        "label": "Need more information",
        "component": "ClarificationRequest",
        "display": "inline",
        "ui_pattern": "single_step",
        "summary": "..."
      }
    ],
    "before_chat_lifecycle": {
      "name": "initialize_context",
      "purpose": "...",
      "trigger": "before_chat",
      "integration": null
    },
    "after_chat_lifecycle": null,
    "workflow_dependencies": {
      "required_workflows": []
    }
  }
}
```

### structured_outputs.json

**TechnicalBlueprint**:
```json
"TechnicalBlueprint": {
  "fields": {
    "global_context_variables": { "type": "list", "items": "RequiredContextVariable" },
    "ui_components": { "type": "list", "items": "WorkflowUIComponent" },
    "before_chat_lifecycle": { "type": "union", "variants": ["WorkflowLifecycleToolRef", "null"] },
    "after_chat_lifecycle": { "type": "union", "variants": ["WorkflowLifecycleToolRef", "null"] },
    "workflow_dependencies": { "type": "union", "variants": ["WorkflowDependencies", "null"] }
  }
}
```

**RequiredContextVariable**:
```json
"RequiredContextVariable": {
  "fields": {
    "name": { "type": "str" },
    "type": { "type": "str", "allowed_values": ["config", "data_reference", "data_entity", "computed", "state", "external"] },
    "trigger_hint": { "type": "union", "variants": ["str", "null"] },
    "purpose": { "type": "str" }
  }
}
```

**WorkflowUIComponent**:
```json
"WorkflowUIComponent": {
  "fields": {
    "module_name": { "type": "str" },
    "agent": { "type": "str" },
    "tool": { "type": "str" },
    "label": { "type": "str" },
    "component": { "type": "str" },
    "display": { "type": "str" },     // NOTE: No allowed_values in schema!
    "ui_pattern": { "type": "str" },  // NOTE: No allowed_values in schema!
    "summary": { "type": "str" }
  }
}
```

**WorkflowLifecycleToolRef**:
```json
"WorkflowLifecycleToolRef": {
  "fields": {
    "name": { "type": "str" },
    "purpose": { "type": "str" },
    "trigger": { "type": "literal", "values": ["before_chat", "after_chat"] },
    "integration": { "type": "union", "variants": ["str", "null"] }
  }
}
```

### agents.json [OUTPUT FORMAT]
```json
{
  "TechnicalBlueprint": {
    "global_context_variables": [
      {
        "name": "<string>",
        "type": "config|data_reference|data_entity|computed|state|external",
        "purpose": "<string>",
        "trigger_hint": "<string|null>"
      }
    ],
    "ui_components": [
      {
        "module_name": "<string>",
        "agent": "<PascalCaseAgentName>",
        "tool": "<snake_case_tool>",
        "label": "<CTA or heading>",
        "component": "<PascalCaseComponent>",
        "display": "inline|artifact",
        "ui_pattern": "single_step|two_step_confirmation|multi_step",
        "summary": "<<=200 char narrative>"
      }
    ],
    "before_chat_lifecycle": {
      "name": "<string>",
      "purpose": "<string>",
      "trigger": "before_chat",
      "integration": "<string|null>"
    },
    "after_chat_lifecycle": {...} | null,
    "workflow_dependencies": {...} | null
  }
}
```

### ⚠️ MINOR ISSUES

1. **WorkflowUIComponent.display** - Schema says `type: "str"` but should have `allowed_values: ["inline", "artifact"]`
2. **WorkflowUIComponent.ui_pattern** - Schema says `type: "str"` but should have `allowed_values: ["single_step", "two_step_confirmation", "multi_step"]`

These are schema strictness issues. The prompt enforces the values correctly, but the schema doesn't validate them at runtime.

### Fix Needed in structured_outputs.json:
```json
"display": {
  "type": "literal",
  "values": ["inline", "artifact"],
  "description": "..."
},
"ui_pattern": {
  "type": "literal", 
  "values": ["single_step", "two_step_confirmation", "multi_step"],
  "description": "..."
}
```

---

## 4. WorkflowImplementationAgent → ModuleAgentsOutput

### SOURCE_OF_TRUTH.md (Section 3.4)
```json
{
  "ModuleAgents": [
    {
      "module_index": 0,
      "agents": [
        {
          "agent_name": "RouterAgent",
          "agent_type": "router",
          "objective": "...",
          "human_interaction": "context",
          "generation_mode": null,
          "max_consecutive_auto_reply": 20,
          "agent_tools": [
            {
              "name": "analyze_request",
              "integration": null,
              "purpose": "...",
              "interaction_mode": "none"
            }
          ],
          "lifecycle_tools": [],
          "system_hooks": []
        }
      ]
    }
  ]
}
```

### structured_outputs.json

**ModuleAgents**:
```json
"ModuleAgents": {
  "fields": {
    "module_index": { "type": "int" },
    "agents": { "type": "list", "items": "WorkflowAgent" }
  }
}
```

**WorkflowAgent**:
```json
"WorkflowAgent": {
  "fields": {
    "agent_name": { "type": "str" },
    "agent_type": { "type": "str", "allowed_values": ["router", "worker", "evaluator", "orchestrator", "intake", "generator"] },
    "objective": { "type": "str" },
    "agent_tools": { "type": "list", "items": "AgentTool" },
    "lifecycle_tools": { "type": "list", "items": "LifecycleTool" },
    "system_hooks": { "type": "list", "items": "SystemHook" },
    "human_interaction": { "type": "str", "allowed_values": ["none", "context", "approval", "feedback", "single"] },
    "generation_mode": { "type": "union", "variants": ["str", "null"] },
    "max_consecutive_auto_reply": { "type": "int" }
  }
}
```

**AgentTool**:
```json
"AgentTool": {
  "fields": {
    "name": { "type": "str" },
    "integration": { "type": "union", "variants": ["str", "null"] },
    "purpose": { "type": "str" },
    "interaction_mode": { "type": "literal", "values": ["inline", "artifact", "none"] }
  }
}
```

### agents.json [OUTPUT FORMAT]
```json
{
  "ModuleAgents": [
    {
      "module_index": <int>,
      "agents": [
        {
          "agent_name": "<PascalCaseAgentName>",
          "agent_type": "router|worker|evaluator|orchestrator|intake|generator",
          "objective": "<...>",
          "generation_mode": "text|image|video|audio|null",
          "agent_tools": [
            {
              "name": "<string>",
              "integration": "<string|null>",
              "purpose": "<string>",
              "interaction_mode": "inline|artifact|none"
            }
          ],
          "lifecycle_tools": [...],
          "system_hooks": ["<string>"],
          "human_interaction": "none|context|approval|feedback|single",
          "max_consecutive_auto_reply": <int>
        }
      ]
    }
  ]
}
```

### ⚠️ DISCREPANCY

1. **system_hooks** - Schema says `"type": "list", "items": "SystemHook"` where SystemHook has fields `{name, purpose}`, but:
   - SOURCE_OF_TRUTH.md shows `"system_hooks": []` (empty array, no detail)
   - agents.json shows `"system_hooks": ["<string>"]` (array of strings, not objects)

This is a mismatch. The schema expects objects, but the prompt teaches strings.

### Fix Needed:
Either update agents.json [OUTPUT FORMAT] to show:
```json
"system_hooks": [
  {
    "name": "<string>",
    "purpose": "<string>"
  }
]
```

Or update structured_outputs.json to accept strings.

---

## 5. ProjectOverviewAgent → MermaidSequenceDiagramOutput

### SOURCE_OF_TRUTH.md (Section 3.5)
```json
{
  "MermaidSequenceDiagram": {
    "workflow_name": "Customer Support Router",
    "mermaid_diagram": "sequenceDiagram\n    participant User\n    ...",
    "legend": ["M1: Request Classification"]
  },
  "agent_message": "Here's the workflow diagram. Review and approve to continue."
}
```

### structured_outputs.json
```json
"MermaidSequenceDiagram": {
  "fields": {
    "workflow_name": { "type": "str" },
    "mermaid_diagram": { "type": "str" },
    "legend": { "type": "list", "items": "str" }
  }
}
"MermaidSequenceDiagramOutput": {
  "fields": {
    "MermaidSequenceDiagram": { "type": "MermaidSequenceDiagram" },
    "agent_message": { "type": "str" }
  }
}
```

### agents.json [OUTPUT FORMAT]
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

### ✅ ALIGNED
All three match exactly.

---

## Summary of Findings

| Agent | Status | Issue |
|-------|--------|-------|
| PatternAgent | ✅ ALIGNED | - |
| WorkflowStrategyAgent | ✅ ALIGNED | - |
| WorkflowArchitectAgent | ✅ FIXED | Schema now enforces `display` and `ui_pattern` with literal values |
| WorkflowImplementationAgent | ✅ FIXED | `system_hooks` OUTPUT FORMAT now shows object structure matching schema |
| ProjectOverviewAgent | ✅ ALIGNED | - |

---

## Fixes Applied

### Fix 1: system_hooks OUTPUT FORMAT (agents.json)
**Before**: `"system_hooks": ["<string>"]`
**After**:
```json
"system_hooks": [
  {
    "name": "<string>",
    "purpose": "<string>"
  }
]
```

### Fix 2: WorkflowUIComponent schema strictness (structured_outputs.json)
**Before**: `display` and `ui_pattern` were `type: "str"` (no validation)
**After**:
```json
"display": {
  "type": "literal",
  "values": ["inline", "artifact"]
},
"ui_pattern": {
  "type": "literal",
  "values": ["single_step", "two_step_confirmation", "multi_step"]
}
```

### Fix 3: SystemHook definition (ACTION_PLAN_SOURCE_OF_TRUTH.md)
Added `SystemHook Fields` table defining `{name, purpose}` structure.

---

## ✅ All Three Sources Now Aligned
