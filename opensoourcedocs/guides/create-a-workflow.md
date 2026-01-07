# Create a Workflow

Workflows are declarative definitions that MozaiksAI loads and executes.

In this repo, each workflow lives under:

```text
workflows/<workflow_id>/
```

## Folder Layout (Current Convention)

A typical workflow directory contains YAML files:

```text
workflows/<workflow_id>/
  agents.yaml
  tools.yaml
  handoffs.yaml
  hooks.yaml
  orchestrator.yaml
  structured_outputs.yaml
  context_variables.yaml
  ui_config.yaml
  tools/
    <tool_impl>.py
```

## Minimal Steps

1. Create `workflows/<workflow_id>/`.
2. Define agents in `agents.yaml`.
3. Declare tools in `tools.yaml`.
4. Implement tools in `workflows/<workflow_id>/tools/`.
5. Define orchestration in `orchestrator.yaml`.

## Tool Implementations

Tools are the extension point where your workflow can:

- generate artifacts
- read/write files in controlled ways
- call third-party APIs
- emit structured events

Keep the runtime boundary in mind:

- tools can do business actions
- the runtime should not contain business-specific tools

## Packs / Macro-Orchestration

This repo also supports a workflow pack graph under:

```text
workflows/_pack/workflow_graph.json
```

Use packs when you want “journeys” (multi-workflow progression).

## Next

- [Workflows (YAML)](../concepts/workflows-yaml.md)
- [Runtime API](../reference/runtime-api.md)
