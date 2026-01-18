# Open Source Example Workflows

This folder contains example workflows for the MozaiksAI runtime.

## Available Examples

| Example | Description |
|---------|-------------|
| `_hello-world/` | Minimal single-agent workflow |
| `_customer-support/` | Basic support bot with handoffs |

## Creating Your Own Workflow

```
workflows/
└── MyWorkflow/
    ├── orchestrator.yaml    # Workflow configuration
    ├── agents.yaml          # Agent definitions
    ├── handoffs.yaml        # Handoff rules
    └── tools/               # Custom tools (optional)
        └── my_tool.py
```

See the [Workflow Authoring Guide](../../docs/workflows/workflow_authoring.md) for details.
