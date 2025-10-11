Context Variables System (Database, Environment, Static, Derived)
=================================================================

This document is the authoritative description of the MozaiksAI runtime context
variables subsystem. It consolidates what were previously separate notions of
"defined", "runtime", and "derived" variables into a unified taxonomy that the
runtime enforces without workflow‑specific code. The configuration is validated
by `core/workflow/context_schema.py` (Pydantic models) before execution, so an
invalid `context_variables.json` fails fast with a warning and an empty context
rather than unpredictable behaviour.

Taxonomy (Four Categories)
-------------------------
1. **database**
  Persisted values loaded on demand from MongoDB collections. They expose stable
  descriptive or configuration data that agents can *read* to shape reasoning,
  tool arguments, or user messaging. They are **not** intended for branching
  logic unless the value is inherently boolean or a tight enum.

2. **environment**
  Deployment/runtime feature flags sourced from OS environment variables
  (e.g., CONTEXT_AWARE, MONETIZATION_ENABLED). These are small booleans or short
  scalars that gate *capabilities* (enable/disable a feature) rather than carry
  descriptive content. In **production** mode (ENVIRONMENT=production) the runtime
  hard-suppresses all environment variables: they are removed at load time and
  purged defensively before the final context is returned. Generator agents are
  instructed to emit an empty list for this category in production. In non-production
  (development/testing) only the minimal necessary flags should be declared.

3. **static** (formerly called declarative variables)
  Workflow-authored constant values embedded directly in the workflow JSON. They:
  - Do not depend on environment or database state.
  - Are versioned with the workflow (change requires commit/regeneration).
  - Should remain small (labels, numeric limits, feature descriptors, canonical names).
  - Are advisory/descriptive and generally not used for branching (treat them like constants in code).
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
  They are represented internally with `source.type = static`. Choose this instead of an environment variable when operators do *not* need to toggle it per deployment.

4. **derived**
  Deterministic, ephemeral values flipped automatically by observing runtime
  signals. They are never persisted; they exist solely inside the AG2 ContextVariables
  providers for the lifetime of a workflow run. Derived variables model phase transitions
  or milestone completion without ad hoc orchestration code.

  Derived triggers come in two flavours:
  - `agent_text`: Passive detection of exact/substring/regex matches emitted by agents (handled by `DerivedContextManager`).
  - `ui_response`: Active UI interactions handled by tool code that calls `use_ui_tool()`, awaits a user response, and updates the variable with the returned payload.

  Both trigger types live under the same `source.type = "derived"` entry and may be mixed within the same variable if needed.

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

```json
{
  "context_variables": {
    "definitions": {
      "product_tier": {
        "type": "string",
        "description": "Static tier label shipped with the workflow (not env or db)",
        "source": {
          "type": "static",
          "value": "beta"
        }
      },
      "max_items": {
        "type": "integer",
        "description": "Static numeric cap used in prompts or pagination logic",
        "source": {
          "type": "static",
          "value": 25
        }
      },
      "concept_overview": {
        "type": "string",
        "description": "Main project description and overview from the database",
        "source": {
          "type": "database",
          "database_name": "autogen_ai_agents",
          "collection": "Concepts",
          "search_by": "enterprise_id",
          "field": "ConceptOverview"
        }
      },
      "context_aware": {
        "type": "boolean",
        "description": "Flag indicating if workflow should use context-aware behavior",
        "source": {
          "type": "environment",
          "env_var": "CONTEXT_AWARE",
          "default": true
        }
      },
      "monetization_enabled": {
        "type": "boolean",
        "description": "Flag indicating if monetization features are enabled",
        "source": {
          "type": "environment",
          "env_var": "MONETIZATION_ENABLED",
          "default": false
        }
      },
      "interview_complete": {
        "type": "boolean",
        "description": "True once InterviewAgent has enough context to proceed to the next stage",
        "source": {
          "type": "derived",
          "default": false,
          "triggers": [
            {
              "type": "agent_text",
              "agent": "InterviewAgent",
              "match": {
                "equals": "NEXT"
              }
            }
          ]
        }
      },
      "action_plan_acceptance": {
        "type": "string",
        "description": "User's response to action plan: 'accepted', 'adjustments_requested', or 'pending'",
        "source": {
          "type": "derived",
          "default": "pending",
          "triggers": [
            {
              "type": "ui_response",
              "tool": "action_plan",
              "response_key": "plan_acceptance"
            }
          ]
        }
      }
    },
    "agents": {
      "InterviewAgent": {
        "variables": ["context_aware", "concept_overview", "monetization_enabled"]
      },
      "ActionPlanArchitect": {
        "variables": ["concept_overview", "interview_complete", "action_plan_acceptance", "action_plan"]
      },
      "ProjectOverviewAgent": {
        "variables": ["action_plan", "action_plan_acceptance", "mermaid_sequence_diagram", "mermaid_diagram_ready"]
      }
    }
  }
}
```

**Key Structure Changes (AG2-Native Pattern):**
- **`definitions`**: Unified variable definitions (all types in one place, source.type determines category)
- **`agents`**: Per-agent variable lists for AG2's UpdateSystemMessage injection (replaces deprecated "exposures" field)
- **No UI fields**: Context variables are ALWAYS hidden from frontend UI; visibility handled in .js/.py presentation layer
- **AG2 Integration**: Runtime builds UpdateSystemMessage templates from `agents.<AgentName>.variables` list

Runtime Loading (core/workflow/context_variables.py)
---------------------------------------------------
1. **Minimal base**: `_create_minimal_context` seeds `enterprise_id`,
   `workflow_name`, and two baked-in flags (`context_aware`,
   `monetization_enabled`) from environment variables **unless**
   `ENVIRONMENT=production`.

2. **Config fetch + validation**: `_load_workflow_config` resolves the workflow block,
   extracts the `context_variables` section, and validates it with Pydantic
   schema (`core/workflow/context_schema.py`). Legacy keys raise a warning and are ignored.

3. **Gating switches**:
   - **Production gating**: if `ENVIRONMENT=production`, the loader suppresses all
     variables with `source.type == "environment"` immediately and performs a final
     defensive purge before returning the context.
   - **Schema gating**: if `CONTEXT_INCLUDE_SCHEMA` is falsy, all variables with
     `source.type == "database"` are suppressed (useful for extremely lean runs).

4. **Variable resolution by source type**:
   - **`source.type == "environment"`**: Pull `env_var` from `os.environ`, apply
     light coercion based on declared `type` (`boolean`, `integer`, otherwise string).
     Schema defaults applied when env var is unset.
   - **`source.type == "static"`**: Inject `value` verbatim (never gated or mutated).
   - **`source.type == "database"`**: Fetch configured documents/fields via
     `_load_specific_data_async`. Per-variable `database_name` overrides supported;
     workflow-level default used otherwise.
   - **`source.type == "derived"`**: Initialize to `default` value.
     - `agent_text` triggers are monitored by `DerivedContextManager`, which flips values automatically when matches occur.
     - `ui_response` triggers are updated by tool code after UI interactions (`use_ui_tool()` response payloads). Tools call `context_variables.set()` with the extracted value specified by `response_key`.

5. **Agent variable lists**: After loading all definitions, the runtime reads
   `agents.<AgentName>.variables` arrays and stores them as `_mozaiks_context_agents`
   metadata for UpdateSystemMessage template building at agent initialization time.

6. **Logging**: Safe summaries (length limited) emitted for observability without
   leaking large blobs or secrets. Verbose diffing enabled with `CONTEXT_VERBOSE_DEBUG=1`.

Derived Variable Engine (core/workflow/derived_context.py)
---------------------------------------------------------
`DerivedContextManager` orchestrates derived variables that use `agent_text` triggers:
- Loads definitions with `source.type == "derived"`.
- Builds trigger dataclasses for every `agent_text` entry (ignores `ui_response` triggers since tools handle them).
- Seeds defaults across all AG2 context providers (pattern + each agent context).
- Monitors streamed `TextEvent`s; when all trigger predicates match, sets the
  variable to `True` (or provided literal) across providers (idempotent flip).

Agent Text Trigger Example
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

UI Response Trigger Example (tool-handled)
```
{
  "type": "ui_response",
  "tool": "action_plan",
  "response_key": "plan_acceptance"
}
```
Tool code awaits the `use_ui_tool()` response, extracts `plan_acceptance`, and calls
`context_variables.set("action_plan_acceptance", value)` to update runtime state.

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
**Adding a new database variable:**
1. Add entry to `context_variables.definitions` with fully specified `source`:
   ```json
   "user_profile": {
     "type": "document",
     "description": "User account details from database",
     "source": {
       "type": "database",
       "database_name": "autogen_ai_agents",
       "collection": "Users",
       "search_by": "user_id",
       "field": "Profile"
     }
   }
   ```
2. Keep fields narrow; avoid dumping entire nested documents unless required.
3. To expose to an agent, add variable name to `agents.<AgentName>.variables` array.

**Adding a new environment variable:**
1. Declare minimally in non-production with clear boolean/numeric purpose:
   ```json
   "feature_x_enabled": {
     "type": "boolean",
     "description": "Flag to enable experimental feature X (dev/testing only)",
     "source": {
       "type": "environment",
       "env_var": "FEATURE_X_ENABLED",
       "default": false
     }
   }
   ```
2. Provide `default` value so runtime can seed deterministic behavior when env var unset.
3. Remember: suppressed in production (ENVIRONMENT=production).

**Adding a new derived variable (agent text trigger):**
1. Add trigger spec to `context_variables.definitions`:
   ```json
   "approval_received": {
     "type": "boolean",
     "description": "True when InterviewAgent emits approval signal",
     "source": {
       "type": "derived",
       "default": false,
       "triggers": [
         {
           "type": "agent_text",
           "agent": "InterviewAgent",
           "match": {"equals": "APPROVED"}
         }
       ]
     }
   }
   ```
2. **Use case**: Passive detection of agent outputs (no user interaction required).
3. `DerivedContextManager` monitors `TextEvent` stream and automatically sets variable to `True` when match detected.
4. Keep triggers purely declarative and observable (no hidden state, no timers yet).

**Adding a new derived variable (ui_response trigger):**
1. Add to `context_variables.definitions` with `source.type == "derived"` and a `ui_response` trigger:
   ```json
   "form_submission": {
     "type": "object",
     "description": "User-submitted form data from configuration wizard",
     "source": {
       "type": "derived",
       "default": null,
       "triggers": [
         {
           "type": "ui_response",
           "tool": "config_wizard",
           "response_key": "form_data"
         }
       ]
     }
   }
   ```
2. **Use case**: Active UI interaction requiring user input (button click, form submit, dropdown selection).
3. Tool code must call `use_ui_tool()`, await response, extract `response_key`, then call `context_variables.set()`.
4. `DerivedContextManager` ignores `ui_response` triggers; tool code has full control over update timing/value.
5. Example tool pattern:
   ```python
   resp = await use_ui_tool(tool_id="config_wizard", payload=wizard_data, ...)
   form_data = resp.get("form_data")  # Extract using response_key from config
   if form_data is not None:
       context_variables.set("form_submission", form_data)
   ```

**Derived Trigger Types: When to Use Which?**
- **`agent_text` trigger**: Agent outputs text that signals a state change (e.g., "NEXT", "APPROVED", "READY"). Passive, config-driven, automatic.
- **`ui_response` trigger**: User clicks button, submits form, or makes a UI selection that updates context. Active, initiated by tool code after `use_ui_tool()` response.
- Combine triggers when appropriate (e.g., allow either agent text or UI confirmation to flip the same variable).

**Adding a new declarative (static) variable:**
1. Add to `context_variables.definitions` with `source.type == "static"`:
   ```json
   "product_tier": {
     "type": "string",
     "description": "Static tier label shipped with workflow",
     "source": {
       "type": "static",
       "value": "beta"
     }
   }
   ```
2. Do NOT source from env or database; if you need dynamic mutation, reclassify accordingly.
3. Prefer lower_snake_case names; keep values small (avoid large blobs).
4. Avoid using declarative values in branching; if you need a branch, use derived/environment flag.

**Exposing variables to agents (UpdateSystemMessage):**
1. Add variable name(s) to `agents.<AgentName>.variables` array:
   ```json
   "agents": {
     "MyAgent": {
       "variables": ["enterprise_id", "feature_x_enabled", "user_profile"]
     }
   }
   ```
2. Runtime automatically builds UpdateSystemMessage template from this list.
3. LLM receives injected context before each reply (AG2-native mechanism).
4. No custom "exposures" logic—pure AG2 UpdateSystemMessage.

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
- **database**: descriptive, persisted, non-branching by default.
- **environment**: feature flags (dev/testing only), fully suppressed in prod.
- **static** (aka declarative): workflow constants (advisory, non-branching, always loaded, not gated).
- **derived**: event-driven, ephemeral. Supports both `agent_text` (passive) and `ui_response` (tool-driven) triggers.
- Only environment + derived variables appear in handoff conditions; database & static values stay advisory.

This document supersedes all prior context variable docs; no other .md should be
consulted for logic definitions.

Decision Guide: Choosing the Right Variable Category
----------------------------------------------------
Use this quick matrix when adding a new piece of context:

| I need… | Characteristics | Pick |
|---------|-----------------|------|
| A tenant-specific field (plan, quota, industry) | Comes from persistent data; may change outside a run | database |
| A deployment toggle (enable X in dev, off in prod) | Controlled by ops; should vanish in production context | environment |
| A static constant for prompts (product_tier="beta") | Versioned with workflow; not environment-dependent | static |
| A flag that flips when an agent outputs a trigger phrase | Derived from runtime events; ephemeral | derived (agent_text trigger) |
| A value set after a UI approval button is clicked | Comes from `use_ui_tool()` payload; tied to a tool response | derived (ui_response trigger) |
| A large blob / full document you just want to inspect | Potentially heavy, rarely needed each turn | Avoid (summarize into smaller database value or derived summary) |

Heuristics:
1. If ops need to change it without a PR → environment.
2. If it depends on tenant data → database.
3. If it changes *during* the conversation → derived (decide between `agent_text` and `ui_response`).
4. If it never changes and is conceptually part of the workflow spec → static.
5. If you can derive it cheaply from another already-present value → don’t add it (derive on-demand in a tool or agent logic).

Anti‑Patterns to Avoid:
* Storing secrets in any context variable (use a secure secret manager; never echo secret env vars here).
* Using environment variables for static brand names or version labels (use static instead).
* Branching on high‑cardinality database values (convert them into a derived boolean/enum during run if needed).
* Adding verbose documents (convert to summarized form before insertion; context is for lightweight guidance, not archival data).

Future-Proofing:
When adding a brand-new *trigger type* for derived variables, ensure:
* It’s deterministic and replayable from the event log.
* It doesn’t need hidden timers or external mutable state.
* It can be represented declaratively (no inline Python logic in JSON).

If these conditions fail, consider implementing a tool that writes a derived variable explicitly instead of a passive trigger.
