# Action Plan Schema & Ownership (Runtime Contract)

Purpose
- Define who owns which parts of the Action Plan across the four ActionPlan agents (Strategy, Architect, Implementation, ProjectOverview).
- Keep responsibilities narrow per agent while ensuring the final Action Plan is complete, confirmable by the user, and fully consumable by downstream spec agents to produce runtime manifests.
- Make integrations and lifecycle operations explicit and traceable.

Non-goals
- Business/tool payload schemas (produced by Generator/stubs) are out of scope.
- UI component shapes are out of scope; runtime only forwards events.


## Action Plan Schema (DesignActionPlan)

We adopted a unified specification that exposes only the information required for user confirmation while still giving downstream agents the data they need to expand into runtime manifests. The schema mirrors the proposal from the user feedback.

```
DesignActionPlan = {
  "workflow_name": str,
  "workflow_description": str,
  "trigger": "chat" | "form_submit" | "schedule" | "database_condition" | "webhook",
  "initiated_by": "user" | "system" | "external_event",
  "pattern": list[str],
  "phases": list[Phase],
  "before_chat_lifecycle": WorkflowLifecycleToolRef | null,
  "after_chat_lifecycle": WorkflowLifecycleToolRef | null,
  "global_context_variables": list[ContextVarRef],
  "mermaid_diagram": MermaidSequenceDiagram | null,
  "agent_message": str
}

ContextVarRef = {
  "name": str,
  "type": "static" | "environment" | "database" | "derived",
  "purpose": str,
  "trigger_hint": str | null
}

WorkflowLifecycleToolRef = {
  "name": str,
  "purpose": str,
  "trigger": "before_chat" | "after_chat",
  "integration": str | null
}

MermaidSequenceDiagram = {
  "workflow_name": str,
  "mermaid_diagram": str,
  "legend": list[str]
}

Phase = {
  "phase_index": int,
  "phase_name": str,
  "phase_description": str,
  "human_in_loop": bool,
  "agents_needed": "single" | "sequential" | "nested",
  "agents": list[PhaseAgentRef]
}

PhaseAgentRef = {
  "agent_name": str,
  "description": str,
  "agent_tools": list[AgentToolRef],
  "lifecycle_tools": list[AgentLifecycleToolRef],
  "system_hooks": list[AgentSystemHookRef],
  "integrations": list[str],
  "human_interaction": "context" | "approval" | "none"
}

AgentToolRef = {
  "name": str,
  "integration": str | null,
  "purpose": str
}

AgentLifecycleToolRef = {
  "name": str,
  "purpose": str,
  "trigger": "before_agent" | "after_agent",
  "integration": str | null
}

AgentSystemHookRef = {
  "name": str,
  "purpose": str,
  "hook_type": "update_agent_state" | "process_message_before_send" | "process_last_received_message" | "process_all_messages_before_reply",
  "registration": "constructor" | "runtime",
  "integration": str | null
}
```

Key simplifications
- No parameter schemas, return contracts, response_key fields, or exposed_to arrays are required at this stage.
- Context variables simply note purpose and (optionally) a natural language trigger hint; downstream ContextVariablesAgent will derive precise trigger definitions.
- Lifecycle operations surface only name/purpose/trigger/integration so the user understands why they exist. Specific targets/parameters can be inferred later.
- Each agent lists the tools it will use, the lifecycle hooks it depends on, and the system hooks it requires. `registration` communicates whether the hook must be wired via constructor (e.g., `update_agent_state`) or can use `register_hook()` at runtime (e.g., `process_message_before_send`). Third-party services are tracked through the `integration` field.
- The mermaid diagram block remains optional but recommended for visualization.

Hook system alignment
- `AgentSystemHookRef.hook_type="update_agent_state"` captures the pattern-guidance injectors documented in `docs/HOOK_SYSTEM_DEEP_DIVE.md`. Because these functions must execute before the first reply, `registration` must be `constructor` so the assembler passes them through `update_agent_state_before_reply` during agent creation.
- `hook_type="process_message_before_send"` covers reply transformers like the InterviewAgent auto-NEXT block. These hooks return a message payload and can be registered via `agent.register_hook()` after construction, so `registration` is `runtime`.
- `hook_type="process_last_received_message"` and `hook_type="process_all_messages_before_reply"` are available for future conversation-history adjustments. They also register at runtime unless a new requirement demands constructor wiring.
- `AgentLifecycleToolRef` represents explicit tool executions (e.g., fetch context, persist output) that wrap the LLM call. They are separate from AG2 hooks even if they execute before or after the agent speaks.

Downstream expectations
- After user approval, spec agents (ToolsManager, ContextVariablesAgent, etc.) expand agent_tools and lifecycle_operations into detailed manifests (parameters, return types, trigger schemas, exposed_to, etc.).
- The assembler keeps the same ownership model (Strategy seeds phases, Architect adds WHAT, Implementation adds WHO, ProjectOverview adds diagram) but now writes into the simplified design schema.
- Compiler steps can still project a richer internal structure if needed, but the user-facing contract remains the DesignActionPlan above.


## Ownership matrix (single source of truth)

- **WorkflowStrategyAgent**
  - Sets `workflow_name`, `workflow_description`, `trigger`, `initiated_by`, `pattern` (primary pattern list)
  - Seeds `phases[]` with `phase_index`, `phase_name`, `phase_description`, `human_in_loop`, `agents_needed`

- **WorkflowArchitectAgent**
  - Appends/updates `global_context_variables`
  - Defines workflow-level lifecycle tools (`before_chat_lifecycle`, `after_chat_lifecycle`)
  - For each phase, may append architectural notes that Implementation will convert into agent responsibilities (but does not author agents)

- **WorkflowImplementationAgent**
  - Fills each phase’s `agents[]` array with `PhaseAgentRef` objects
  - Populates `agent_tools`, `lifecycle_tools` (per-agent), `system_hooks`, `integrations`, and `human_interaction`
  - Ensures each `system_hooks[]` entry is annotated with the correct `hook_type` and `registration` (constructor vs runtime) based on AG2 hook expectations
  - Ensures `agent_name`/`description` explain how tools/hooks leverage integrations

- **ProjectOverviewAgent**
  - Generates `mermaid_diagram` (MermaidSequenceDiagram)
  - Sets `agent_message` with the final synopsis (sole owner)

Compile-time guards
- Each agent only writes the fields in its ownership scope; the assembler merges by field-level ownership (no wholesale overwrites).

## Agent output contracts

Each agent returns a structured payload that maps directly to the DesignActionPlan fields it controls. The assembler treats every payload as authoritative only for the sections listed below.

| Agent | Context variable | Required sections | Optional sections | Notes |
|-------|------------------|-------------------|-------------------|-------|
| WorkflowStrategyAgent | `strategy` (`WorkflowStrategyCall`) | `workflow_name`, `workflow_description`, `trigger`, `initiated_by`, `pattern`, phase scaffolding (`phase_index`, `phase_name`, `phase_description`, `human_in_loop`, `agents_needed`) | Additional pattern rationale (narrative only) | Phases contain no agent/tool data yet. Strategy should align with pattern guidance injected via `update_agent_state` hooks. |
| WorkflowArchitectAgent | `blueprint` (`TechnicalBlueprintCall`) | `global_context_variables`, `before_chat_lifecycle`, `after_chat_lifecycle` | Phase-level architecture notes for Implementation | Lifecycle tools are workflow-scope operations that execute before/after the entire chat session. |
| WorkflowImplementationAgent | `phase_agents` (`PhaseAgentsCall`) | `phases[].agents[]` including `agent_name`, `description`, `agent_tools`, `lifecycle_tools`, `system_hooks`, `integrations`, `human_interaction` | Additional per-agent commentary | `system_hooks` must include `hook_type`/`registration` so the runtime can split constructor vs runtime wiring. `lifecycle_tools` wrap agent execution and are distinct from AG2 hooks. |
| ProjectOverviewAgent | `project_overview` (`ProjectOverviewCall`) | `mermaid_diagram`, `agent_message` | None | Diagram must reflect the final phase/agent/tool layout for downstream viewers. |

### Field exclusivity rules
- Strategy is the only writer for top-level metadata and phase scaffolding; later agents cannot overwrite these fields except where explicitly owned.
- Architect controls workflow-wide lifecycle tooling and shared context variables. Implementation may reference them but does not modify them.
- Implementation authoritatively populates each phase’s `agents[]` roster. ProjectOverview must not mutate `phases[]`.
- ProjectOverview owns visualization artifacts and the final `agent_message`; other agents may reference the diagram conceptually but do not edit the stored Mermaid structure or message.


## Agent structured outputs

Each Action Plan agent emits a structured payload matching the fields it owns. The assembler uses these models to populate the DesignActionPlan incrementally.

### WorkflowStrategyAgent output

**JSON format**
```jsonc
{
  "workflow_name": "<string>",
  "workflow_description": "<string>",
  "trigger": "<chat|form_submit|schedule|database_condition|webhook>",
  "initiated_by": "<user|system|external_event>",
  "pattern": ["<string>"],
  "phases": [
    {
      "phase_index": <int>,
      "phase_name": "<string>",
      "phase_description": "<string>",
      "human_in_loop": <bool>,
      "agents_needed": "<single|sequential|nested>"
    }
  ]
}
```

**Pydantic model**
```python
from typing import Literal
from pydantic import BaseModel


class StrategyPhase(BaseModel):
  phase_index: int
  phase_name: str
  phase_description: str
  human_in_loop: bool
  agents_needed: Literal["single", "sequential", "nested"]


class WorkflowStrategyOutput(BaseModel):
  workflow_name: str
  workflow_description: str
  trigger: Literal["chat", "form_submit", "schedule", "database_condition", "webhook"]
  initiated_by: Literal["user", "system", "external_event"]
  pattern: list[str]
  phases: list[StrategyPhase]
```


### WorkflowArchitectAgent output

**JSON format**
```jsonc
{
  "global_context_variables": [
    {
      "name": "<string>",
      "type": "<static|environment|database|derived>",
      "purpose": "<string>",
      "trigger_hint": "<string|null>"
    }
  ],
  "before_chat_lifecycle": {
    "name": "<string>",
    "purpose": "<string>",
    "trigger": "<before_chat|after_chat>",
    "integration": "<string|null>"
  },
  "after_chat_lifecycle": {
    "name": "<string>",
    "purpose": "<string>",
    "trigger": "<before_chat|after_chat>",
    "integration": "<string|null>"
  }
}
```

**Pydantic model**
```python
class ContextVarRef(BaseModel):
    name: str
    type: Literal["static", "environment", "database", "derived"]
    purpose: str
    trigger_hint: str | None = None


class WorkflowLifecycleToolRef(BaseModel):
    name: str
    purpose: str
    trigger: Literal["before_chat", "after_chat"]
    integration: str | None = None


class WorkflowArchitectOutput(BaseModel):
    global_context_variables: list[ContextVarRef]
    before_chat_lifecycle: WorkflowLifecycleToolRef | None = None
    after_chat_lifecycle: WorkflowLifecycleToolRef | None = None
```


### WorkflowImplementationAgent output

**JSON format**
```jsonc
{
  "phases": [
    {
      "phase_index": <int>,
      "agents": [
        {
          "agent_name": "<string>",
          "description": "<string>",
          "human_interaction": "<context|approval|none>"
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
              "trigger": "<before_agent|after_agent>",
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
          "integrations": ["<string>"]
        }
      ]
    }
  ]
}
```

**Pydantic model**
```python
class AgentToolRef(BaseModel):
    name: str
    integration: str | None = None
    purpose: str


class AgentLifecycleToolRef(BaseModel):
    name: str
    purpose: str
    trigger: Literal["before_agent", "after_agent"]
    integration: str | None = None


class AgentSystemHookRef(BaseModel):
    name: str
    purpose: str
    hook_type: Literal[
        "update_agent_state",
        "process_message_before_send",
        "process_last_received_message",
        "process_all_messages_before_reply"
    ]
    registration: Literal["constructor", "runtime"]
    integration: str | None = None


class PhaseAgentRef(BaseModel):
    agent_name: str
    description: str
    agent_tools: list[AgentToolRef]
    lifecycle_tools: list[AgentLifecycleToolRef]
    system_hooks: list[AgentSystemHookRef]
    integrations: list[str]
    human_interaction: Literal["context", "approval", "none"]


class ImplementationPhase(BaseModel):
    phase_index: int
    agents: list[PhaseAgentRef]


class WorkflowImplementationOutput(BaseModel):
    phases: list[ImplementationPhase]
```


### ProjectOverviewAgent output

**JSON format**
```jsonc
{
  "mermaid_diagram": {
    "workflow_name": "<string>",
    "mermaid_diagram": "<string>",
    "legend": ["<string>"]
  },
  "agent_message": "<string>"
}
```

**Pydantic model**
```python
class MermaidSequenceDiagram(BaseModel):
    workflow_name: str
    mermaid_diagram: str
    legend: list[str]


class ProjectOverviewOutput(BaseModel):
    mermaid_diagram: MermaidSequenceDiagram
    agent_message: str | None = None
```


## Assembly pipeline (runtime)

Input artifacts (stored in context variables)
- strategy: WorkflowStrategyCall
- blueprint: TechnicalBlueprintCall
- phase_agents: PhaseAgentsCall
- project_overview: ProjectOverviewCall

Merge algorithm (idempotent)
1. **Seed DesignActionPlan (Strategy output)**
  - Copy top-level fields and `phases[]` skeleton into a fresh DesignActionPlan object.
  - Initialize `agent_message` to an empty string (ProjectOverview will populate later).

2. **Apply Architect output**
  - Replace/append `global_context_variables`.
  - Set `before_chat_lifecycle` / `after_chat_lifecycle` from blueprint (if present).
  - Store per-phase architectural notes in a temporary structure (`phase_architecture[i]`) for Implementation guidance.

3. **Apply Implementation output**
  - For each `phase_index`, replace `agents[]` with Implementation’s PhaseAgentRef list.
  - Ensure each agent entry includes `agent_tools`, `lifecycle_tools`, `system_hooks`, `integrations`, and `human_interaction`.
  - Partition `system_hooks` by `registration` so constructor-registered hooks feed the agent factory (`update_agent_state_before_reply`) and runtime hooks queue for `agent.register_hook()` after instantiation.
  - Drop temporary architectural notes once agents are in place.

4. **Apply ProjectOverview output**
  - Set `mermaid_diagram` and populate `agent_message` with the final synopsis.

5. **Derive MinimalActionPlan view**
  - Project DesignActionPlan into UI-friendly summary: phases with human-readable highlights, approval summary, tool/integration lists, `mermaid_diagram`, `agent_message`.
  - Persist MinimalActionPlan separately for front-end rendering.

Validation
- Phase counts match across all artifacts.
- `phase_index` sequences are contiguous 0..N-1.
- Every agent lists at least one capability (tool, lifecycle tool, or hook).
- Integrations referenced by agents align with architect-supplied services.
- MinimalActionPlan contains only summary fields (no hidden schemas).

Observability
- Log each stage (strategy seed → architect merge → implementation merge → overview merge → minimal projection) with outcome status.
- Persist both DesignActionPlan and MinimalActionPlan snapshots.


## Downstream manifest generation (spec agents)

- tools.json
  - From phases[].required_tools + shared_requirements.shared_tools
  - Include ownership and scope for correct module/agent wiring
- context_variables.json
  - From phases[].required_context_variables + shared_requirements.workflow_context_variables
  - Preserve trigger semantics (agent_text vs ui_response)
- integrations.json
  - From shared_requirements.third_party_integrations
  - Cross-reference with phases[].agents[].agent_tools[].integration and lifecycle_operations[].integration for usage map
- handoffs.json
  - From Strategy pattern + ContextVariablesPlan triggers and approval gates
  - Phase transitions + condition scopes (ui_response → pre)
- diagram.json (or inline storage)
  - From mermaid_code


## Prompt contracts (delta summary)

- Strategy: unchanged except strategy_notes removed (use agent_message downstream when needed). Keep outputs high-level for MinimalActionPlan.
- Architect: unchanged schema + ensure third_party_integrations collected only when grounded.
- Implementation: replace "operations" with "agent_tools" and add agent-level lifecycle_operations with optional integration. Description must explain how tools/ops tie to integrations. Parameters/returns are optional at design-time; spec agents can expand later.
- ProjectOverview: unchanged.


## Edge cases & rules
- No integrations assumed by default. Arrays may be empty.
- If approval_required=true and no agent with human_interaction=approval exists, assembler raises validation error.
- Shared tools are compiled once; phase_specific tools compiled per-agent.
- agent_text vs ui_response triggers determine condition_scope in handoffs (null vs "pre").

## Acceptance flow hooks
- UI approval button sets context variable action_plan_acceptance=true via UI tool (ui_response trigger).
- Assembler watches for acceptance and only then runs compiler/spec agents to produce manifests.


## Next steps
- Update structured_outputs.json and prompts for ImplementationAgent to adopt agent_tools + lifecycle_operations.
- Update pattern injection examples where they show ImplementationAgent examples to use the new fields and include integration mapping.
- Add assembler function (core/workflow/action_plan.py) with merge + validation + logs.
- Update spec agents/readers to consume ActionPlan for manifest generation, especially integrations.json and tools.json.
