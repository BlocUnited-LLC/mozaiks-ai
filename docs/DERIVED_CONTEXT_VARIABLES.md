Derived Context Variables
=========================

This document explains how the runtime derives workflow context variables from
events, and how to extend the mechanism with new variable types.

Overview
--------

Workflows declare three classes of context variables:

1. **Defined variables** – persisted fields backed by a database collection.
2. **Runtime variables** – ephemeral values kept in memory for a single run.
3. **Derived variables** – deterministic flags updated automatically when
   specific events occur (e.g., an agent produces the message *TERMINATE*).

Derived variables are stored in `context_variables.json` under the
`context_variables.derived_variables` key and interpreted by the runtime at
execution time. They allow workflows to toggle boolean state without adding
workflow-specific code to the orchestration core.

The `DerivedContextManager` (`core/workflow/derived_context.py`) is responsible
for:

- Reading the derived specification from `workflow_manager.get_config()`.
- Seeding default values into every AG2 `ContextVariables` provider (pattern,
  group manager, and agent-level contexts).
- Observing `TextEvent` emissions during `_stream_events` and flipping the
  variables when a trigger matches.

If no derived variables are declared, the manager is inert.

Current Schema
--------------

`DerivedContextManager` currently supports a single trigger type. The JSON
shape is intentionally minimal:

```
"derived_variables": [
  {
    "name": "interview_complete",
    "description": "True once the interview agent terminates the onboarding chat.",
    "default": false,
    "triggers": [
      {
        "type": "agent_text",
        "agent": "InterviewAgent",
        "match": { "equals": "TERMINATE" }
      }
    ]
  }
]
```

The runtime treats this as:

- `default` – boolean initial value seeded into all context providers.
- `triggers` – list of deterministic conditions:
  - `type`: currently only `agent_text` is supported.
  - `agent`: agent name, matching the name used in the workflow JSON.
  - `match.equals`: exact string the agent must emit (no case conversion or
    trimming).

When a matching `TextEvent` is observed, the manager sets the variable to
`true` (the system assumes a single assignment target for now).

Why exact matches only?
-----------------------

The goal is to keep derived state deterministic and easy to reason about. By
limiting the trigger to simple string equality, the runtime avoids subtle
heuristics (case folding, regexes, etc.) that can introduce non-determinism.
Future versions can add optional flags or alternative trigger types if more
flexibility is required.

Orchestration Hook Points
-------------------------

`core/workflow/orchestration_patterns.py` integrates the manager in three
places:

1. **After agent creation** – instantiate `DerivedContextManager` and seed
   defaults (`_create_agents` call site).
2. **After pattern creation** – register additional context providers from the
   pattern and group manager (so triggers update all scopes).
3. **During streaming** – route every `TextEvent` through the manager inside
   `_stream_events`.

These hooks keep the logic workflow-agnostic; the orchestration core simply
loads declarations and applies them.

Extending Derived Variables
---------------------------

You can add new capabilities without touching workflow-specific code:

1. **Add a trigger loader** in `derived_context.py`:
   - Create a new dataclass implementing `matches(event) -> bool`.
   - Register it in `TRIGGER_LOADERS` (e.g., `"agent_turn_count"`).
   - Update the schema to describe the new trigger type.

2. **Expand the structured output schema** so generator agents can emit the new
   trigger type (update `workflows/<workflow>/structured_outputs.json`).

3. **Document the new trigger** for generator agents (system messages and
   docs) and add validation rules as needed.

4. **Ensure determinism** – every trigger must map to data that is stable and
   observable inside `_stream_events` (e.g., event metadata, turn counters,
   usage summaries).

Future Ideas
------------

- `agent_turn_count`: set a flag when an agent reaches N turns.
- `tool_response`: update a variable when a specific tool returns success.
- `timer_expired`: integrate timers or scheduled events via transport hooks.
- `function`: map derived variables to small Python functions loaded from a
  workflow-specific stub (would require careful sandboxing).

Each of these features can be layered into the manager so long as the triggers
are expressed declaratively and run inside the runtime sandbox.

Workflow Author Guidance
------------------------

- Use derived variables sparingly; every new flag adds cognitive load to the
  agent roster.
- Prefer variable names that match the workflow semantics (`interview_complete`,
  `approval_requested`).
- Document the expected agent message in the relevant system message (e.g.,
  remind the InterviewAgent to emit `TERMINATE`).
- When adding a new derived variable, update structured outputs and context
  agent prompts so the generator agents are aware of the schema.

References
----------

- Runtime implementation: `core/workflow/derived_context.py`
- Orchestration integration: `core/workflow/orchestration_patterns.py`
- Example workflow config: `workflows/Generator/context_variables.json`
- Structured schema: `workflows/Generator/structured_outputs.json`
