# MozaiksAI

MozaiksAI is an **AG2-based execution runtime** for declarative, multi-agent workflows.

It’s built to sit inside *your* ecosystem as the execution layer:

- Your app (control plane) decides **who can run what**.
- MozaiksAI runs the workflow, invokes tools, persists session state, and streams events.

This documentation is intentionally open-source friendly and published from `opensoourcedocs/` (the repo’s internal `/docs` folder is not part of the public site).

## What MozaiksAI Does

- Loads workflows from `workflows/<workflow_id>/` (YAML configs + tool implementations)
- Orchestrates AG2 agents / GroupChat
- Streams events over WebSocket
- Persists chat/session state (MongoDB)
- Emits usage signals (for observability and downstream reconciliation)

## What MozaiksAI Does Not Do

- Authorization (subscriptions/entitlements/quotas)
- Product policy or billing enforcement
- Business-specific “platform” logic

## Start Here

### Embed it in your product

- [Embed MozaiksAI In Your App](guides/embed-in-your-app.md)
- [MozaiksAI In Your Ecosystem](concepts/ecosystem.md)
- [Auth Boundary](concepts/auth-boundary.md)
- [Multi-Tenancy](concepts/multi-tenancy.md)

### Author workflows

- [Create a Workflow](guides/create-a-workflow.md)
- [Workflows (YAML)](concepts/workflows-yaml.md)

### Operations

- [Self-Hosting](guides/self-hosting.md)
