# Modular Tool System: agent_tools, ui_tools + hooks

This doc describes the lean post-refactor tooling model.

## Core Principles
1. Single-function modules (one async function per Python file)
2. Two tool categories only: `agent_tools` and `ui_tools`
3. Execution hooks are NOT tools. They are declared in `hooks.json` (or `hooks.yaml` during migration) and registered with `agent.register_hook(hook_type, fn)`
4. UI tool events use a unified helper (`use_ui_tool`) for emit+await
5. Minimal surface: no lifecycle tool category, no normalization layer duplication

## Data Sources
```
workflow.json (agent_tools/ui_tools + core orchestrator fields)
hooks.json    (declarative hook registrations; legacy `hooks.yaml` supported during migration)
```

## Categories
### agent_tools
Direct callable utilities for agents (I/O, business logic, transformations).

Example snippet:
```yaml
agent_tools:
    ALL_AGENTS:
        - path: workflows.Generator.tools.echo_all.echo
            description: Simple echo
```

### ui_tools
Emit UI components and wait for user interaction.
Required fields in workflow.json entry (example):
```yaml
ui_tools:
    OrchestratorAgent:
        - path: workflows.Generator.tools.request_api_key.request_api_key
            component: AgentAPIKeyInput
            mode: inline   # or artifact
            description: Request an API key from the user
```

UI emission is centralized; the tool implementation just returns data or calls `use_ui_tool` internally.

### hooks (hooks.json)
Supported hook types:
* process_message_before_send(sender, message, recipient, silent)
* update_agent_state(agent, messages)
* process_last_received_message(message)
* process_all_messages_before_reply(messages)

Example hooks.json:
```yaml
hooks:
    - hook_type: process_message_before_send
        hook_agent: HookAgent
        file: redaction.py
        function: redact_before_send
    - hook_type: update_agent_state
        hook_agent: UserFeedbackAgent
        file: state.py
        function: update_state
```

## Flow (First Turn Synopsis)
1. Orchestrator seeds initial message (or user provides one)
2. process_message_before_send hooks run on outbound message
3. Recipient receives message; pre-reply phase runs: update_agent_state, process_last_received_message, process_all_messages_before_reply
4. Reply functions execute (tool calls, code exec, LLM, etc.)
5. Outbound reply again passes process_message_before_send
6. Loop continues until termination

## Module Shape
```python
# agent tool
async def echo(text: str) -> str:
        return text

# ui tool (example simplified)
from core.workflow.ui_tools import use_ui_tool

async def request_api_key(service: str) -> dict:
        return await use_ui_tool(
                tool_id="api_key_input",
                workflow_name="Generator",
                payload={"service": service}
        )

# hook function (state.py)
def update_state(agent, messages):
        agent.state["message_count"] = len(messages)
```

## Registry (Conceptual)
The legacy registry tracked backend/ui/lifecycle. Now:
* Parse workflow.json -> agent_tools/ui_tools
* Normalize `agent_tools`
* hooks_loader processes hooks.json (or hooks.yaml during migration) and calls `agent.register_hook(...)`

## Directory Layout Example
```
workflows/Generator/
    orchestrator.json
    agents.json
    tools.json
    hooks.json
    tools/
        echo_all.py
        request_api_key.py
        state.py
        redaction.py
```
## Benefits
* Smaller surface / less indirection
* Declarative hooks separate from tool list
* Cleaner payload (workflow_name carried explicitly)
* Easier diff & audit of execution behaviors

## Adding Something New
1. Create `tools/my_new_tool.py` with single async function
2. Reference it in `tools.json` under `agent_tools` or `ui_tools` (legacy `tools.yaml` supported during migration)
3. (If hook) add entry to `hooks.json` (or `hooks.yaml` during migration) referencing file+function
4. Run workflow; loader auto-registers hooks and exposes tools

## Deprecations
* Normalization/event translation previously in ui_tools removed
* Implicit default workflow "generator" removed – must pass explicit workflow_name

## Future Enhancements (Optional)
* Auto-generate docs from `tools.json` + `hooks.json` (or legacy YAML sources)
* Add tests asserting hook firing order and UI tool emission contract

---
This reflects the current minimal tool + hook architecture.