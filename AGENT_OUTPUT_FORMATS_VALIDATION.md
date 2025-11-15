# Generator Agent Output Formats (Ground Truth from agents.json)

This document extracts the actual output format for each Generator agent based on their [OUTPUT FORMAT] sections in agents.json. This is the **ground truth** that structured_outputs.json schemas must match.

---

## 1. InterviewAgent

**Output Type**: Free-form text (conversational)  
**Structured Output Required**: No  
**Output Structure**: 
- String output containing either:
  - A single interview question
  - A clarifying question when ambiguity is detected
  - EXACTLY `NEXT` (uppercase, no extra text) once completion criteria are satisfied

**Example**:
```
"What parts of your work or business feel the most repetitive or time-consuming?"
```
OR
```
"NEXT"
```

**Notes**: 
- No JSON wrapper
- No structured fields
- Purely conversational turn-based output

---

## 2. PatternAgent

**Output Type**: Structured JSON  
**Structured Output Required**: Yes  
**Wrapper Key**: `PatternSelection`

**Full Output Structure**:
```json
{
  "PatternSelection": {
    "selected_pattern": <int 1-9>,
    "pattern_name": "<string matching pattern legend>"
  }
}
```

**Field Definitions**:
- `selected_pattern` (int): Pattern ID from 1-9
- `pattern_name` (str): Exact string matching pattern legend

**Pattern Legend Mapping**:
- 1 → "Context-Aware Routing"
- 2 → "Escalation"
- 3 → "Feedback Loop"
- 4 → "Hierarchical"
- 5 → "Organic"
- 6 → "Pipeline"
- 7 → "Redundant"
- 8 → "Star"
- 9 → "Triage with Tasks"

**Example**:
```json
{
  "PatternSelection": {
    "selected_pattern": 6,
    "pattern_name": "Pipeline"
  }
}
```

---

## 3. WorkflowStrategyAgent

**Output Type**: Structured JSON  
**Structured Output Required**: Yes  
**Wrapper Key**: `WorkflowStrategy`

**Full Output Structure**:
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

**Field Definitions**:
- `workflow_name` (str): Title Case, descriptive
- `workflow_description` (str): Plain-language summary of the automation
- `trigger` (str): One of five supported trigger types
- `initiated_by` (str): Who initiates execution (user/system/external_event)
- `pattern` (List[str]): Array of orchestration pattern identifiers
- `phases` (List[dict]): Sequential array describing each phase (0-based phase_index)

**Phase Object Fields**:
- `phase_index` (int): Sequential integer starting at 0
- `phase_name` (str): Human-readable label ("Phase N: ...")
- `phase_description` (str): Purpose of the phase
- `human_in_loop` (bool): true if a person participates
- `agents_needed` (str): "single", "sequential", or "nested"

---

## 4. WorkflowArchitectAgent (TechnicalBlueprint)

**Output Type**: Structured JSON  
**Structured Output Required**: Yes  
**Wrapper Key**: `TechnicalBlueprint`

**Full Output Structure**:
```json
{
  "TechnicalBlueprint": {
    "global_context_variables": [
      {
        "name": "<string>",
        "type": "static|environment|database|derived",
        "purpose": "<string>",
        "trigger_hint": "<string|null>"
      }
    ],
    "before_chat_lifecycle": {
      "name": "<string>",
      "purpose": "<string>",
      "trigger": "before_chat",
      "integration": "<string|null>"
    },
    "after_chat_lifecycle": {
      "name": "<string>",
      "purpose": "<string>",
      "trigger": "after_chat",
      "integration": "<string|null>"
    }
  }
}
```

**Field Definitions**:
- `global_context_variables` (List[dict]): Workflow-wide context variables. Provide an empty array when none are required.
- `before_chat_lifecycle` (dict | null): Initialization hook executed before the first agent runs. Use null when not needed.
- `after_chat_lifecycle` (dict | null): Finalization hook executed after the workflow completes. Use null when not needed.

---

## 5. WorkflowImplementationAgent (PhaseAgents)

**Output Type**: Structured JSON  
**Structured Output Required**: Yes  
**Wrapper Key**: `PhaseAgents`

**Full Output Structure**:
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
            "agent_tools": [
              {
                "name": "<string>",
                "integration": "<string|null>",
                "purpose": "<string>"
              }
            ],
            "lifecycle_tools": [
              {
                "name": "<string>",
                "purpose": "<string>",
                "trigger": "before_agent|after_agent",
                "integration": "<string|null>"
              }
            ],
            "system_hooks": [
              {
                "name": "<string>",
                "purpose": "<string>",
                "hook_type": "<update_agent_state|process_message_before_send|process_last_received_message|process_all_messages_before_reply>",
                "registration": "<constructor|runtime>",
                "integration": "<string|null>"
              }
            ],
            "integrations": ["<string>"],
            "human_interaction": "context|approval|none"
          }
        ]
      }
    ]
  }
}
```

**Field Definitions**:
- `phase_agents` (List[dict]): Array aligned to upstream WorkflowStrategy.phases by phase_index (0-based)
- `agents` (List[dict]): Each phase must include at least one agent entry
- `agent_tools` (List[dict]): Agent-specific tools (empty array when none required)
- `lifecycle_tools` (List[dict]): Agent lifecycle hooks (empty array when none required)
- `system_hooks` (List[dict]): AG2 system hooks (empty array when none required)
- `integrations` (List[str]): List of real third-party services (empty array allowed)
- `human_interaction` (str): Declare how agent engages with humans (context, approval, none)

---

## 6. ProjectOverviewAgent (MermaidSequenceDiagram)

**Output Type**: Structured JSON  
**Structured Output Required**: Yes  
**Wrapper Key**: `MermaidSequenceDiagram`

**Full Output Structure**:
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

**Field Definitions**:
- `workflow_name` (str): Human-readable workflow label for display
- `mermaid_diagram` (str): Mermaid sequence diagram text (must start with "sequenceDiagram")
- `legend` (List[str]): Array of short legend entries explaining diagram elements (empty array allowed)
- `agent_message` (str): Final synopsis delivered alongside the diagram

**Notes**:
- This is one of the few agents that emits BOTH a wrapper key AND agent_message at root level
- Mermaid diagram must be valid Mermaid syntax

---

## 7. ContextVariablesAgent

**Output Type**: Structured JSON  
**Structured Output Required**: Yes  
**Wrapper Key**: `ContextVariablesPlan`

**Full Output Structure**:
```json
{
  "ContextVariablesPlan": {
    "definitions": [
      {
        "name": "<string>",
        "type": "<string>",
        "description": "<string>",
        "source": {
          "type": "database|environment|static|derived",
          "database_name": "<string|null>",
          "collection": "<string|null>",
          "search_by": "<string|null>",
          "field": "<string|null>",
          "env_var": "<UPPER_SNAKE_CASE|null>",
          "default": "<any|null>",
          "value": "<any|null>",
          "triggers": [
            {
              "type": "agent_text|ui_response",
              "agent": "<AgentName|null>",
              "match": {"type": "equals|contains|regex", "value": "<string>"}|null,
              "tool": "<tool_name|null>",
              "response_key": "<string|null>"
            }
          ]|null
        }
      }
    ],
    "agents": [
      {
        "agent": "<PascalCaseAgentName>",
        "variables": ["<variable_name>"]
      }
    ]
  }
}
```

**Field Definitions**:
- `definitions` (List[dict]): Array of all context variables the workflow uses
- `definitions[].name` (str): snake_case variable name
- `definitions[].source.type` (str): Determines how variable is loaded/updated
- `definitions[].source.triggers` (List[dict]): ONLY for derived type (agent_text or ui_response)
- `agents` (List[dict]): Array mapping which variables each agent can read
- `agents[].agent` (str): PascalCase agent name from PhaseAgents output
- `agents[].variables` (List[str]): Array of variable names (empty array allowed)

**Trigger Type Rules**:
- `agent_text`: Runtime watches agent messages, sets variable when match detected
- `ui_response`: Tool code explicitly sets variable via runtime['context_variables'].set()

---

## 8. ToolsManagerAgent

**Output Type**: Structured JSON  
**Structured Output Required**: Yes  
**Wrapper Key**: NONE (root-level tools[] and lifecycle_tools[])

**Full Output Structure**:
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
  "lifecycle_tools": [
    {
      "trigger": "before_chat" | "after_chat" | "before_agent" | "after_agent",
      "target": "<AgentName>" | null,
      "file": "<snake_case>.py",
      "function": "<snake_case>",
      "description": "<purpose>"
    }
  ]
}
```

**Field Definitions**:
- `tools` (List[dict]): Array of tool specifications derived from Action Plan operations
- `agent` (str): PascalCase agent name that owns the tool
- `file` (str): Python filename (snake_case.py)
- `function` (str): Python function name (snake_case, matches filename)
- `description` (str): Tool purpose (<=140 chars, no secrets)
- `tool_type` (str): "Agent_Tool" for backend, "UI_Tool" for UI interactions
- `auto_invoke` (bool): true for context caching tools, false otherwise (default)
- `ui` (dict|null): null for Agent_Tool, object with component/mode for UI_Tool
- `lifecycle_tools` (List[dict]): Optional array of workflow-level hooks (usually empty)

**Notes**:
- This agent does NOT use a wrapper key
- Output is flat root-level arrays

---

## 9. UIFileGenerator

**Output Type**: Structured JSON  
**Structured Output Required**: Yes  
**Wrapper Key**: NONE (root-level tools[] array)

**Full Output Structure**:
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

**Field Definitions**:
- `tools` (List[dict]): Array with one entry per UI_Tool from tools manifest
- `tool_name` (str): Exact function name from manifest (snake_case) - basename only, NO path prefix
- `py_content` (str): Complete Python async function source code as string (no placeholders)
- `js_content` (str): Complete React component source code as string (no placeholders)

**Notes**:
- This agent does NOT use a wrapper key
- py_content must contain async function with await use_ui_tool()
- js_content must contain valid React component

---

## 10. AgentToolsFileGenerator

**Output Type**: Structured JSON  
**Structured Output Required**: Yes  
**Wrapper Key**: NONE (root-level tools[] array)

**Full Output Structure**:
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

**Field Definitions**:
- `tools` (List[dict]): Array with one entry per Agent_Tool from tools manifest
- `tool_name` (str): Exact function name from manifest (snake_case) - basename only, NO path prefix
- `py_content` (str): Complete Python function source code as string (no placeholders)

**Notes**:
- This agent does NOT use a wrapper key
- py_content can be sync or async depending on agent auto_tool_mode configuration

---

## 11. StructuredOutputsAgent

**Output Type**: Structured JSON  
**Structured Output Required**: Yes  
**Wrapper Key**: NONE (root-level models[] and registry[] arrays)

**Full Output Structure**:
```json
{
  "models": [
    {
      "model_name": "<PascalCase>",
      "fields": [
        {
          "name": "<snake_case>",
          "type": "str|int|bool|List[...]|Dict[...]",
          "description": "<field purpose and constraints>"
        }
      ]
    }
  ],
  "registry": [
    {
      "agent": "<PascalCaseAgentName>",
      "agent_definition": "<ModelName>" | null
    }
  ]
}
```

**Field Definitions**:
- `models` (List[dict]): Array of Pydantic model definitions for ALL agents with structured_outputs_required=true
- `model_name` (str): PascalCase model name (e.g., ReportGenerationCall, ActionPlan, PatternSelection)
- `fields` (List[dict]): Array of field definitions with name (snake_case), type, and description
- `registry` (List[dict]): Array mapping EVERY agent from ContextVariablesPlan.agents to either a model or null
- `agent_definition` (str|null): null = free-form text, ModelName = structured output required

**Notes**:
- This agent does NOT use a wrapper key
- Output is flat root-level arrays

---

## 12. AgentsAgent (RuntimeAgentsCall)

**Output Type**: Structured JSON  
**Structured Output Required**: Yes  
**Wrapper Key**: NONE (root-level agents[] array + agent_message)

**Full Output Structure**:
```json
{
  "agents": [
    {
      "name": "<PascalCaseAgentName>",
      "display_name": "<Display Name>",
      "prompt_sections": [
        {"id": "<section_id>", "heading": "[SECTION HEADING]", "content": "<section content>"}
      ],
      "max_consecutive_auto_reply": <int>,
      "auto_tool_mode": true|false,
      "structured_outputs_required": true|false
    }
  ],
  "agent_message": "<Summary>"
}
```

**Field Definitions**:
- `agents` (List[dict]): Array of runtime agent configurations
- `name` (str): PascalCase agent name
- `display_name` (str): Human-readable name
- `prompt_sections` (List[dict]): Array of prompt section objects (9 standard sections)
- `max_consecutive_auto_reply` (int): Integer (5-20 based on complexity)
- `auto_tool_mode` (bool): Whether to use AutoToolEventHandler
- `structured_outputs_required` (bool): Whether agent must emit JSON
- `agent_message` (str): Summary string

**Prompt Section Structure**:
- 9 standard sections: role, objective, context, runtime_integrations, guidelines, instructions, examples, json_output_compliance (conditional), output_format
- Each section has: `id` (str), `heading` (str), `content` (str)

**Notes**:
- This agent does NOT use a wrapper key
- Output includes both agents[] array AND agent_message at root level

---

## 13. HookAgent (HookImplementationCall)

**Output Type**: Structured JSON  
**Structured Output Required**: Yes  
**Wrapper Key**: NONE (root-level hook_files[] array + agent_message)

**Full Output Structure**:
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

**Field Definitions**:
- `hook_files` (List[dict]): Array of hook file objects (can be empty [] if no custom hooks needed)
- `filename` (str): Hook file name (e.g., "validate_budget.py", "audit_decisions.py")
- `hook_type` (str): One of "before_chat", "after_chat", "update_agent_state"
- `py_content` (str): Complete Python code for hook function
- `agent_message` (str): Summary (e.g., "Generated 2 custom lifecycle hooks" or "No custom hooks required")

**Notes**:
- This agent does NOT use a wrapper key
- Output includes both hook_files[] array AND agent_message at root level
- hook_files[] can be empty if no custom hooks are needed

---

## 14. HandoffsAgent

**Output Type**: Structured JSON  
**Structured Output Required**: Yes  
**Wrapper Key**: NONE (root-level handoff_rules[] array + agent_message)

**Full Output Structure**:
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

**Field Definitions**:
- `handoff_rules` (List[dict]): Array of handoff rule objects
- `source_agent` (str): Agent name or "user" (PascalCase)
- `target_agent` (str): Agent name or "TERMINATE" (PascalCase)
- `handoff_type` (str): "after_work" (unconditional) or "condition" (conditional)
- `condition_type` (str|null): "expression" (context var), "string_llm" (LLM eval), or null
- `condition_scope` (str|null): "pre" (ui_response triggers) or null (agent_text triggers / after_work)
- `condition` (str|null): Expression string (e.g., "${approved} == true") or null
- `transition_target` (str): Always "AgentTarget"
- `agent_message` (str): Summary (e.g., "Generated 12 handoff rules for 5-phase workflow")

**Notes**:
- This agent does NOT use a wrapper key
- Output includes both handoff_rules[] array AND agent_message at root level

---

## 15. OrchestratorAgent

**Output Type**: Structured JSON  
**Structured Output Required**: Yes  
**Wrapper Key**: NONE (root-level orchestration config fields + agent_message)

**Full Output Structure**:
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

**Field Definitions**:
- `workflow_name` (str): From action_plan (PascalCase)
- `max_turns` (int): Integer (typically 20-30)
- `human_in_the_loop` (bool): Boolean (true for workflows with user interaction)
- `startup_mode` (str): "AgentDriven" (agent speaks first) or "UserDriven" (user speaks first)
- `orchestration_pattern` (str): From action_plan.workflow.pattern
- `initial_message_to_user` (null): Always null (deprecated)
- `initial_message` (str|null): Greeting string for AgentDriven mode, null for UserDriven
- `recipient` (str): First agent name from action_plan.workflow.phases[0].agents[0]
- `visual_agents` (List[str]): Array of agent names that own UI_Tools or require human interaction
- `agent_message` (str): Summary (e.g., "Orchestration config for Content Pipeline workflow")

**Notes**:
- This agent does NOT use a wrapper key
- Output is flat root-level fields

---

## 16. DownloadAgent

**Output Type**: Structured JSON  
**Structured Output Required**: Yes  
**Wrapper Key**: NONE (root-level agent_message only)

**Full Output Structure**:
```json
{
  "agent_message": "<Brief context message for UI>"
}
```

**Field Definitions**:
- `agent_message` (str): Brief message (e.g., "Your workflow is ready for download")

**Notes**:
- This agent has the SIMPLEST output format
- Does NOT use a wrapper key
- Only emits agent_message to trigger download tool

---

## Summary Statistics

**Total Agents**: 16

**Agents Using Wrapper Keys**: 6
1. PatternAgent → `PatternSelection`
2. WorkflowStrategyAgent → `WorkflowStrategy`
3. WorkflowArchitectAgent → `TechnicalBlueprint`
4. WorkflowImplementationAgent → `PhaseAgents`
5. ProjectOverviewAgent → `MermaidSequenceDiagram`
6. ContextVariablesAgent → `ContextVariablesPlan`

**Agents WITHOUT Wrapper Keys**: 10
1. InterviewAgent (free-form text)
2. ToolsManagerAgent (root-level tools[] + lifecycle_tools[])
3. UIFileGenerator (root-level tools[])
4. AgentToolsFileGenerator (root-level tools[])
5. StructuredOutputsAgent (root-level models[] + registry[])
6. AgentsAgent (root-level agents[] + agent_message)
7. HookAgent (root-level hook_files[] + agent_message)
8. HandoffsAgent (root-level handoff_rules[] + agent_message)
9. OrchestratorAgent (root-level config fields + agent_message)
10. DownloadAgent (root-level agent_message)

**Agents with structured_outputs_required=false**: 1
- InterviewAgent (conversational)

**Agents with structured_outputs_required=true**: 15
- All agents except InterviewAgent

---

## Next Steps

1. **Compare against structured_outputs.json**: Cross-reference each agent's output format above with the corresponding model definition in structured_outputs.json
2. **Identify Misalignments**: Flag any missing fields, type mismatches, or structural differences
3. **Fix structured_outputs.json**: Update model definitions to match ground truth from agents.json
4. **Validate Pattern Guidance**: Ensure pattern guidance can reference correct inline schemas

---

## Validation Checklist

For each agent in structured_outputs.json, verify:
- [ ] Model name matches wrapper key (if wrapper key exists)
- [ ] All fields from agents.json [OUTPUT FORMAT] are present
- [ ] Field types match (str, int, bool, List, Dict)
- [ ] Field names use snake_case
- [ ] Nested objects are properly modeled
- [ ] Arrays of objects define child models
- [ ] No extra fields not in agents.json
- [ ] No missing fields from agents.json
