# Action Plan Schema V2

> ⚠️ **PARTIALLY DEPRECATED**: This document has useful reference content but some details are outdated.
> 
> **Canonical Reference**: See `docs/ACTION_PLAN_SOURCE_OF_TRUTH.md`
>
> **What's still valid**:
> - Module terminology is correct
> - Basic agent flow concept is accurate
> - Human interaction modes are correct
>
> **What's outdated**:
> - Agent execution order has WorkflowArchitectAgent BEFORE WorkflowImplementationAgent (not after)
> - Some field names don't match current structured_outputs.json
> - References deprecated models like `PhaseAgentsOutput`
>
> Always verify against structured_outputs.json for authoritative field names.

---

This document defines the new schema for the Action Plan agents, replacing "phases" with "modules" and restructuring the agent flow.

## Agent Execution Order (NEW)

```
1. InterviewAgent        → Gather requirements
2. PatternAgent          → Select pattern(s)
3. WorkflowStrategyAgent → High-level strategy with modules
4. WorkflowImplementationAgent → Expand modules into agents (MOVE UP)
5. WorkflowArchitectAgent → Technical blueprint (context vars, UI, lifecycle)
6. ProjectOverviewAgent  → Mermaid diagram + user approval
```

**Key Change:** WorkflowImplementationAgent now runs BEFORE WorkflowArchitectAgent because you can't define context variables until you know what agents exist.

---

## 1. PatternSelectionOutput

```json
{
  "PatternSelection": {
    "is_multi_workflow": false,
    "decomposition_reason": null,
    "pack_name": "Customer Support Router",
    "resume_agent": null,
    "workflows": [
      {
        "name": "CustomerSupportRouter",
        "role": "primary",
        "description": "Routes support requests to the right specialists",
        "pattern_id": 1,
        "pattern_name": "Context-Aware Routing",
        "initial_agent": null,
        "initial_message": null
      }
    ]
  }
}
```

---

## 2. WorkflowStrategyOutput (UPDATE)

**Changes:**
- `phases` → `modules`
- Add `pattern_id` and `pattern_name` per module
- Add `agents_needed` array per module
- Remove `agents_needed: "single|parallel|sequential"` (redundant with pattern)

```json
{
  "WorkflowStrategy": {
    "workflow_name": "Customer Support Router",
    "workflow_description": "When a user submits a support request, the workflow analyzes the query content and routes it to the appropriate specialist, resulting in expert-level responses across multiple domains.",
    "human_in_loop": true,
    "trigger": "chat",
    "initiated_by": "user",
    "modules": [
      {
        "module_index": 0,
        "module_name": "Request Analysis & Routing",
        "module_description": "Analyze incoming requests and route to appropriate domain specialists based on content classification.",
        "pattern_id": 1,
        "pattern_name": "Context-Aware Routing",
        "agents_needed": ["RouterAgent", "TechSpecialist", "FinanceSpecialist", "HealthcareSpecialist", "GeneralSpecialist"]
      }
    ]
  }
}
```

### WorkflowStrategyModule Schema

| Field | Type | Description |
|-------|------|-------------|
| `module_index` | int | Zero-based index (0 = Module 1) |
| `module_name` | string | Human-readable module name |
| `module_description` | string | What this module accomplishes |
| `pattern_id` | int (1-9) | AG2 pattern ID |
| `pattern_name` | string | AG2 pattern name |
| `agents_needed` | string[] | Agent names this module requires |

---

## 3. ModuleAgentsOutput (RENAME from PhaseAgentsOutput)

**Changes:**
- `PhaseAgents` → `ModuleAgents`
- `phase_index` → `module_index`
- `description` → `objective`
- Add new `agent_type` values: `intake`, `generator`
- Add new `human_interaction` values: `feedback`, `single`
- Add `generation_mode` for generator agents
- `agent_tools` now includes `interaction_mode`

```json
{
  "ModuleAgents": [
    {
      "module_index": 0,
      "agents": [
        {
          "agent_name": "RouterAgent",
          "agent_type": "intake",
          "objective": "Analyze user requests and route to appropriate domain specialists",
          "human_interaction": "context",
          "generation_mode": null,
          "max_consecutive_auto_reply": 20,
          "agent_tools": [
            {
              "name": "analyze_request",
              "integration": null,
              "purpose": "Parse user request to determine domain classification",
              "interaction_mode": "none"
            },
            {
              "name": "route_to_specialist",
              "integration": null,
              "purpose": "Transfer conversation to selected domain specialist",
              "interaction_mode": "none"
            }
          ],
          "lifecycle_tools": [],
          "system_hooks": []
        },
        {
          "agent_name": "TechSpecialist",
          "agent_type": "worker",
          "objective": "Provide expert responses on technology-related queries",
          "human_interaction": "none",
          "generation_mode": null,
          "max_consecutive_auto_reply": 10,
          "agent_tools": [
            {
              "name": "provide_tech_response",
              "integration": null,
              "purpose": "Submit technology specialist response",
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

### Agent Types

| Type | Description |
|------|-------------|
| `router` | Control flow agent, routes to other agents |
| `intake` | Router + human context gathering (human_interaction=context) |
| `worker` | Executes tasks |
| `evaluator` | QA/decision/critique |
| `orchestrator` | Sub-team lead |
| `generator` | Single-shot LLM (text/image/video/audio) |

### Human Interaction Modes

| Mode | Description | max_consecutive_auto_reply |
|------|-------------|---------------------------|
| `none` | Fully automated | 10-30 (medium-high) |
| `context` | Conversational interview | 15-25 (high) |
| `approval` | UI-based gate (has ui_tools) | 3-5 (low) |
| `feedback` | Non-UI loop gate (chat-based feedback) | 3-5 (low) |
| `single` | One-shot LLM call | 1 |

### Generation Mode (for `agent_type: "generator"`)

| Mode | Description |
|------|-------------|
| `text` | Text generation (default) |
| `image` | Image generation (DALL-E, Midjourney) |
| `video` | Video generation (Veo3, Sora) |
| `audio` | Audio generation (TTS, music) |
| `null` | Not a generator agent |

### Agent Tool Schema

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Tool function name (snake_case) |
| `integration` | string\|null | Third-party service (null for internal) |
| `purpose` | string | What this tool does (<=140 chars) |
| `interaction_mode` | string | `inline` \| `artifact` \| `none` |

---

## 4. TechnicalBlueprintOutput (UPDATE)

**Changes:**
- `phase_name` → `module_name` in ui_components
- Simplify `workflow_dependencies` to just `required_workflows`
- Remove `required_context_vars` and `required_artifacts` (inferred from workflow completion)

```json
{
  "TechnicalBlueprint": {
    "global_context_variables": [
      {
        "name": "current_domain",
        "type": "state",
        "purpose": "Tracks which domain specialist is currently handling the request",
        "trigger_hint": "Set by RouterAgent when routing decision is made"
      },
      {
        "name": "question_answered",
        "type": "state",
        "purpose": "Indicates whether the current question has been answered",
        "trigger_hint": "Set to true when specialist provides response"
      }
    ],
    "ui_components": [
      {
        "module_name": "Request Analysis & Routing",
        "agent": "RouterAgent",
        "tool": "request_clarification",
        "label": "Need more information",
        "component": "ClarificationRequest",
        "display": "inline",
        "ui_pattern": "single_step",
        "summary": "Asks user for clarification when query is ambiguous"
      }
    ],
    "before_chat_lifecycle": null,
    "after_chat_lifecycle": null,
    "workflow_dependencies": {
      "required_workflows": []
    }
  }
}
```

### Context Variable Types

| Type | Description |
|------|-------------|
| `config` | Deployment configuration from env vars |
| `data_reference` | Read existing MongoDB data |
| `data_entity` | Create new MongoDB data |
| `computed` | Business logic outputs |
| `state` | Workflow orchestration state |
| `external` | Third-party API data |

---

## 5. MermaidSequenceDiagramOutput (unchanged structure)

```json
{
  "MermaidSequenceDiagram": {
    "workflow_name": "Customer Support Router",
    "mermaid_diagram": "sequenceDiagram\n    participant User\n    participant RouterAgent\n    participant TechSpecialist\n    participant FinanceSpecialist\n    participant HealthcareSpecialist\n    participant GeneralSpecialist\n    participant ToolExecutor\n\n    User->>RouterAgent: Submit query\n    RouterAgent->>ToolExecutor: analyze_request()\n    ...",
    "legend": ["M1: Request Analysis & Routing"]
  },
  "agent_message": "Here's the workflow diagram. Does this look correct? Reply 'approve' to continue or describe any changes needed."
}
```

**Mermaid Diagram Rules:**
1. User (Participant 1) appears first
2. ToolExecutor appears last
3. All workflow agents appear in sequence between them
4. Notes indicate module boundaries

---

## Summary of Terminology Changes

| Old Term | New Term |
|----------|----------|
| `phases` | `modules` |
| `phase_index` | `module_index` |
| `phase_name` | `module_name` |
| `phase_description` | `module_description` |
| `PhaseAgents` | `ModuleAgents` |
| `WorkflowPhase` | `WorkflowModule` |
| `WorkflowStrategyPhase` | `WorkflowStrategyModule` |
| `phase_agents_plan` | `module_agents_plan` |
| `per_phase` | `per_module` |
| `on_phase_transition` | `on_module_transition` |
| `phase_specific` | `module_specific` |

---

## Files to Update

1. `workflows/Generator/structured_outputs.json` - Schema definitions
2. `workflows/Generator/tools.json` - Tool references
3. `workflows/Generator/agents.json` - Agent prompts
4. `workflows/Generator/handoffs.json` - Handoff order (Implementation before Architect)
5. `workflows/Generator/tools/*.py` - Tool implementations
6. Any prompts referencing "phase"

---

## Agent Registry Updates

```json
{
  "registry": {
    "InterviewAgent": null,
    "PatternAgent": "PatternSelectionOutput",
    "WorkflowStrategyAgent": "WorkflowStrategyOutput",
    "WorkflowImplementationAgent": "ModuleAgentsOutput",
    "WorkflowArchitectAgent": "TechnicalBlueprintOutput",
    "ProjectOverviewAgent": "MermaidSequenceDiagramOutput",
    ...
  }
}
```

Note: `PhaseAgentsOutput` → `ModuleAgentsOutput`
