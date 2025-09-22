Context Variables System (Database, Environment, Derived)
=========================================================

This document is the authoritative description of the MozaiksAI runtime context
variables subsystem. It consolidates what were previously separate notions of
"defined", "runtime", and "derived" variables into a unified taxonomy that the
runtime enforces without workflow‑specific code. The configuration is validated
by `core/workflow/context_schema.py` (Pydantic models) before execution, so an
invalid `context_variables.json` fails fast with a warning and an empty context
rather than unpredictable behaviour.

Taxonomy (Four Categories)
--------------------------
1. database_variables
   Persisted values loaded on demand from MongoDB collections. They expose stable
   descriptive or configuration data that agents can *read* to shape reasoning,
   tool arguments, or user messaging. They are **not** intended for branching
   logic unless the value is inherently boolean or a tight enum.

2. environment_variables
   Deployment/runtime feature flags sourced from OS environment variables
   (e.g., CONTEXT_AWARE, MONETIZATION_ENABLED). These are small booleans or short
   scalars that gate *capabilities* (enable/disable a feature) rather than carry
   descriptive content. In **production** mode (ENVIRONMENT=production) the runtime
   hard‑suppresses all environment_variables: they are removed at load time and
   purged defensively before the final context is returned. Generator agents are
   instructed to emit an empty list for this category in production. In non‑production
   (development/testing) only the minimal necessary flags should be declared.

3. derived_variables
   Deterministic, ephemeral flags flipped automatically by observing runtime
   events (currently only agent text emissions) – e.g., interview_complete.
   They are never persisted; they exist solely inside the AG2 ContextVariables
   providers for the lifetime of a workflow run. They model phase transitions
   or milestone completion without requiring ad hoc orchestration code.

4. declarative_variables (aka static variables)
  Workflow-authored constant values embedded directly in the workflow JSON. They:
  - Do not depend on environment or database state.
  - Are versioned with the workflow (change requires commit/regeneration).
  - Should remain small (labels, numeric limits, feature descriptors, canonical names).
  - Are advisory / descriptive and generally not used for branching (treat them like constants in code).
  Example entries:
  ```json
  {
    "name": "product_tier",
    "value": "beta"
  },
  {
    "name": "max_items",
    "type": "integer",
    "value": 25
  }
  ```
  They are represented internally as `declarative_variables` with `source.type = static` (see schema). A new one should be chosen instead of an environment variable when operators do *not* need to toggle it per deployment.

Design Principles
-----------------
Determinism: Every variable’s value must be derivable from declarative config +
observable runtime state. No heuristic or fuzzy matching.
Separation of Concerns: Only environment_variables & derived_variables can appear
in handoff (routing) conditions. database_variables remain descriptive.
Minimalism: Each conceptual piece of state appears exactly once; avoid synonyms.
Production Safety: Production deployments eliminate environment-based branching
variability by suppressing environment_variables.

Configuration Shape
-------------------
`workflows/<Workflow>/context_variables.json`:

```
{
  "context_variables": {
    "declarative_variables": [
      {
        "name": "product_tier",
        "type": "string",
        "description": "Static tier label shipped with the workflow (not env or db)",
        "value": "beta"
      },
      {
        "name": "max_items",
        "type": "integer",
        "description": "Static numeric cap used in prompts or pagination logic",
        "value": 25
      }
    ],
    "database_variables": [
      {
        "name": "concept_overview",
        "type": "string",
        "description": "Main project description and overview from the database",
        "source": {
          "type": "database",
          "database_name": "autogen_ai_agents",
          "collection": "Concepts",
          "search_by": "enterprise_id",
          "field": "ConceptOverview"
        }
      }
    ],
    "environment_variables": [
      {
        "name": "context_aware",
        "type": "boolean",
        "description": "Flag indicating if workflow should use context-aware behavior",
        "source": { "type": "environment", "env_var": "CONTEXT_AWARE" }
      },
      {
        "name": "monetization_enabled",
        "type": "boolean",
        "description": "Flag indicating if monetization features are enabled",
        "source": { "type": "environment", "env_var": "MONETIZATION_ENABLED" }
      }
    ],
    "derived_variables": [
      {
        "name": "interview_complete",
        "type": "boolean",
        "description": "True once InterviewAgent has enough context to proceed to the next stage",
        "default": false,
        "triggers": [
          {
            "type": "agent_text",
            "agent": "InterviewAgent",
            "match": { "equals": "NEXT" }
          }
        ]
      }
    ]
  }
}
```

Runtime Loading (core/workflow/context_variables.py)
---------------------------------------------------
1. Minimal base: `_create_minimal_context` seeds `enterprise_id`,
   `workflow_name`, and two baked-in flags (`context_aware`,
   `monetization_enabled`) from environment variables **unless**
   `ENVIRONMENT=production`.
2. Config fetch + validation: `_load_workflow_config` resolves the workflow block,
   extracts the `context_variables` section, and validates it with the Pydantic
   schema. Legacy keys raise a warning and are ignored.
3. Gating switches:
   - Production gating: if `ENVIRONMENT=production`, the loader clears the
     `environment_variables` list immediately and performs a final defensive
     purge before returning the context.
   - Schema gating: if `CONTEXT_INCLUDE_SCHEMA` is falsy, all
     `database_variables` are suppressed (useful for extremely lean runs).
4. Environment variable resolution: each entry with `source.type == "environment"`
   pulls `env_var` from `os.environ`, applying light coercion based on the
   declared `type` (`boolean`, `integer`, otherwise string). Schema defaults are
   applied when the env var is unset.
5. Declarative variable seeding: `declarative_variables` are injected verbatim.
   They are never gated or mutated.
6. Database variable resolution: `_load_specific_data_async` fetches configured
   documents/fields. Per-variable `database_name` overrides are supported; the
   workflow-level default is used otherwise.
7. Logging: safe summaries (length limited) are emitted for observability without
   leaking large blobs or secrets. Verbose diffing can be enabled with
   `CONTEXT_VERBOSE_DEBUG=1`.

Derived Variable Engine (core/workflow/derived_context.py)
---------------------------------------------------------
`DerivedContextManager` orchestrates derived_variables:
- Loads `derived_variables` list from config (flat or nested key supported).
- Creates trigger dataclasses (currently only `agent_text`).
- Seeds defaults across all AG2 context providers (pattern + each agent context).
- Monitors streamed `TextEvent`s; when all trigger predicates match, sets the
  variable to `True` across providers (idempotent flip).

Current Trigger Type
```
{
  "type": "agent_text",
  "agent": "InterviewAgent",
  "match": { "equals": "NEXT" }
}
```
Matching Logic:
- Extract sender name (string or object.name) from the event.
- Compare trimmed, case-insensitive text content against the configured value.

Handoff Routing Constraints
---------------------------
- Only environment_variables + derived_variables are valid in conditional handoff expressions.
- Conditions are positive, conjunctive (at most one AND), no negation.
- Example: "When interview_complete is true" or
           "When monetization_enabled is true AND interview_complete is true" (dev only).
- In production monetization_enabled would be absent, preventing that condition (design choice for deterministic prod flows).
 - Declarative and database variables are intentionally excluded from routing logic (advisory/descriptive only).

Production Mode Summary
-----------------------
ENVIRONMENT=production effects:
1. Context loader suppresses environment_variables (both early and at return).
2. ContextVariablesAgent system prompt enforces emitting an empty env list.
3. Database variables remain fully accessible for agents (descriptive use, tool argument construction, summaries). Branching policy still discourages using database_variables in conditions unless a value is an intentional, documented boolean/enum gate; derived_variables therefore become the primary (but not sole possible) branching inputs.
4. Reduces configuration surface and accidental drift across deployments.

Extensibility Guidelines
------------------------
Adding a new database variable: declare it under database_variables with a fully
specified `source` mapping (database_name, collection, search_by, field). Keep
fields narrow; avoid dumping entire nested documents unless required.

Adding a new environment variable: declare minimally in non-production with a
clear boolean or numeric purpose. Provide a `default` value when possible so the
runtime can seed deterministic behaviour when the env var is unset. Ensure agents
that read it treat absence as a safe default (usually false).

Adding a new derived variable:
1. Add a trigger spec in `context_variables.json`.
2. If a new trigger type is needed, implement a trigger dataclass with `matches(event)`
   and register it in `TRIGGER_LOADERS`.
3. Update generator prompts (ContextVariablesAgent / HandoffsAgent) to reference
   the new semantics if branching is expected.
4. Keep triggers purely declarative and observable (no hidden state, no timers yet).

 Adding a new declarative variable:
 1. Insert it into the `declarative_variables` list with a `name`, optional `type`,
   and a `value` (primitive: string/number/boolean) plus an explanatory description.
 2. Do NOT source it from env or database; if you find yourself needing dynamic
   mutation, it is not declarative—reclassify accordingly.
 3. Prefer lower_snake_case names; keep values small (avoid large blobs—summarize instead).
 4. Avoid using declarative values in branching; if you need a branch, mirror it
   as an explicit derived/environment flag.

Operational Safety & Observability
----------------------------------
- Logs use safe previews to avoid large payloads and secret leakage.
- Boolean coercion restricted to common truthy indicators: 1, true, yes, on.
- Unknown legacy keys (`variables`) produce a warning and are ignored.
- Production gating is logged: informational on suppression, warning on defensive purge.
- Verbose context diffing can be enabled by setting `CONTEXT_VERBOSE_DEBUG=1`.

AG2 Integration & Agent Consumption
-----------------------------------
All context variables ultimately live inside AG2’s native `ContextVariables`
object. The runtime attaches the populated instance to the pattern’s
`group_manager` and to every agent before execution, so downstream access stays
AG2-native—no bespoke Mozaiks plumbing is required.

Common access patterns:

- **Tools** – Include `context_variables: ContextVariables` in a tool signature.
  AG2 injects the live context automatically. Use this for programmatic lookups
  or when you need multiple values inside a single response.
- **`UpdateSystemMessage` / `update_agent_state_before_reply`** – When an agent
  must surface context values in its system prompt each turn, declare a template
  (e.g., `"Assisting enterprise {enterprise_id} (context aware: {context_aware})"`).
  The runtime does not mutate prompts implicitly; the workflow author (Generator
  layer) decides which agents opt into this pattern.
- **Context-aware handoffs** – `OnContextCondition` and `ContextStrLLMCondition`
  reference variables (e.g., `${interview_complete}`) to drive routing without
  additional code.
- **Summary tools** – For complex contexts, provide a tool that returns a concise
  digest instead of dumping the entire context into prompts.

Key points:

- Context variables are **not** injected into LLM prompts automatically. Choose
  one of the mechanisms above when the LLM must see a value.
- Because every agent shares the same `ContextVariables`, one declaration makes
  the value globally accessible. To make that value visible to the LLM, add an
  UpdateSystemMessage entry or a dedicated tool call.
- Structured outputs (e.g., `ContextVariablesAgentOutput`) should document which
  variables exist and how downstream agents should reference them so prompt
  builders stay aligned.
- When new context requirements emerge, prefer updating the declarative JSON and
  regenerating prompts via the Generator over hand-editing runtime code.

Future Evolution (Non-binding)
------------------------------
Potential trigger types (must remain deterministic):
- agent_turn_count
- tool_response
- timer_expired (requires transport integration)
- function (sandboxed, pre-approved pure evaluation)

Contract Summary
----------------
- database_variables: descriptive, persisted, non-branching by default.
- environment_variables: feature flags (dev/testing only), fully suppressed in prod.
- declarative_variables: static workflow constants (advisory, non-branching, always loaded, not gated).
- derived_variables: event-driven, ephemeral, support branching safely.
- Only environment + derived appear in handoff conditions; database & declarative values stay advisory.

This document supersedes all prior context variable docs; no other .md should be
consulted for logic definitions.

Decision Guide: Choosing the Right Variable Category
----------------------------------------------------
Use this quick matrix when adding a new piece of context:

| I need… | Characteristics | Pick |
|---------|-----------------|------|
| A tenant-specific field (plan, quota, industry) | Comes from persistent data; may change outside a run | database_variable |
| A deployment toggle (enable X in dev, off in prod) | Controlled by ops; should vanish in production context | environment_variable |
| A static constant for prompts (product_tier="beta") | Versioned with workflow; not environment-dependent | declarative_variable (static) |
| A flag that flips when an agent outputs a trigger phrase | Derived from runtime events; ephemeral | derived_variable |
| A large blob / full document you just want to inspect | Potentially heavy, rarely needed each turn | Avoid (summarize into smaller database_variable or derived summary) |

Heuristics:
1. If ops need to change it without a PR → environment.
2. If it depends on tenant data → database.
3. If it changes *during* the conversation → derived.
4. If it never changes and is conceptually part of the workflow spec → declarative.
5. If you can derive it cheaply from another already-present value → don’t add it (derive on-demand in a tool or agent logic).

Anti‑Patterns to Avoid:
* Storing secrets in any context variable (use a secure secret manager; never echo secret env vars here).
* Using environment variables for static brand names or version labels (use declarative instead).
* Branching on high‑cardinality database values (convert them into a derived boolean/enum during run if needed).
* Adding verbose documents (convert to summarized form before insertion; context is for lightweight guidance, not archival data).

Future-Proofing:
When adding a brand-new *trigger type* for derived variables, ensure:
* It’s deterministic and replayable from the event log.
* It doesn’t need hidden timers or external mutable state.
* It can be represented declaratively (no inline Python logic in JSON).

If these conditions fail, consider implementing a tool that writes a derived variable explicitly instead of a passive trigger.
