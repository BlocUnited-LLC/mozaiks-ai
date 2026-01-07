# Workflows (YAML)

Workflows are discovered under `workflows/<WorkflowName>/`.

MozaiksAI loads **YAML** configs (no JSON fallback).

Typical files:

- `orchestrator.yaml`
- `agents.yaml`
- `handoffs.yaml`
- `tools.yaml`
- `context_variables.yaml`
- `structured_outputs.yaml`
- `hooks.yaml`
- `ui_config.yaml`

## Minimal example

```yaml
# orchestrator.yaml
workflow_name: HelloWorld
orchestration_strategy: single_agent
max_turns: 8
primary_agent: Assistant
```

```yaml
# agents.yaml
agents:
  - name: Assistant
    system_message: You are helpful.
    llm_config:
      model: gpt-4o-mini
```
