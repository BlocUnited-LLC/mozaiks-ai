# MozaiksAI In Your Ecosystem

MozaiksAI is the **execution runtime** for agentic workflows.

If you’re adopting MozaiksAI, the key mental model is:

- **Your app (control plane)** decides *who* can run *what*.
- **MozaiksAI (runtime)** executes the workflow and streams events.
- **Your UI (client)** renders chat + artifacts, or embeds the included ChatUI.

## Reference Architecture

```text
┌───────────────────────────────┐
│ Your App / Control Plane      │
│ (you own this)                │
│                               │
│ - Users/orgs/apps             │
│ - Entitlements & policy       │
│ - Capability → workflow mapping│
│ - Token issuance              │
└───────────────┬───────────────┘
                │
                │ launch (app_id, user_id, workflow_id)
                │ + signed token
                ▼
┌───────────────────────────────┐
│ MozaiksAI Runtime              │
│ (this repo)                    │
│                               │
│ - Load workflow YAML           │
│ - Orchestrate AG2 agents       │
│ - Invoke tools                 │
│ - Persist chat state           │
│ - Stream events over WebSocket │
└───────────────┬───────────────┘
                │
                │ events / artifacts
                ▼
┌───────────────────────────────┐
│ Your UI / Client               │
│ (embed ChatUI or BYO UI)       │
│                               │
│ - Connect WS                   │
│ - Render transcript + artifacts│
└───────────────────────────────┘
```

## What You Need To Build (As The Adopter)

To “create your own ecosystem” around MozaiksAI, you typically implement:

1. **A control plane**
   - Authenticates users
   - Enforces product policy (subscriptions, quotas, entitlement)
   - Maps capabilities (product features) to **workflow IDs**
   - Issues **runtime access tokens**

2. **A client**
   - Either embed the included ChatUI
   - Or implement your own WebSocket client for the runtime event protocol

3. **Your workflows**
   - Write declarative workflow configs under `workflows/<workflow_id>/`
   - Add tools under `workflows/<workflow_id>/tools/`

## What MozaiksAI Intentionally Does Not Do

MozaiksAI is designed to stay product-agnostic.

- It **authenticates** incoming requests.
- It **does not authorize** business behavior (subscriptions, entitlements, pricing).

See: [Auth Boundary](auth-boundary.md) and [Runtime Boundaries](runtime-boundaries.md).
