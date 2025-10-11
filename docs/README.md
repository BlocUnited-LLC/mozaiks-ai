# 📚 MozaiksAI Documentation Portal

<div align="center">

**Complete guide to building, deploying, and extending the MozaiksAI Runtime**

[Overview](#-overview) • [Getting Started](#-getting-started) • [Documentation Tracks](#-documentation-tracks) • [Quick Links](#-quick-links)

</div>

---

## 🎯 Overview

Welcome to the **MozaiksAI Runtime Documentation**! This portal provides comprehensive guides, references, and examples for understanding, using, and extending the MozaiksAI orchestration engine.

### What You'll Find Here

- **🏗️ Architecture Fundamentals** – System design, component interactions, and design principles
- **🚀 Runtime Deep Dives** – Transport, persistence, orchestration, and observability
- **🎯 Workflow Guides** – Creating declarative multi-agent workflows
- **⚛️ Frontend Integration** – React ChatUI and dynamic UI components
- **🔧 Operations** – Deployment, monitoring, and troubleshooting
- **📖 Reference** – API specs, database schemas, and environment variables

---

## 🚀 Getting Started

### New to MozaiksAI?

Start here to understand what MozaiksAI is and how it works:

1. **[Architecture Overview](overview/architecture.md)** – System design and core subsystems
2. **[Request Lifecycle](overview/lifecycle.md)** – End-to-end trace from HTTP to WebSocket
3. **[Quick Start Guide](../README.md#-quick-start)** – Installation and first workflow

### Ready to Build Workflows?

Jump into workflow authoring:

1. **[Workflow Authoring Guide](workflows/workflow_authoring.md)** – Complete workflow creation walkthrough
2. **[Tool Manifest System](workflows/tool_manifest.md)** – Define UI and agent tools
3. **[Context Variables](workflows/context_variables.md)** – Database queries and derived state

### Deploying to Production?

Follow these operational guides:

1. **[Deployment Guide](operations/deployment.md)** – Docker and production setup
2. **[Monitoring Guide](operations/monitoring.md)** – Metrics, logging, and alerting
3. **[Troubleshooting](operations/troubleshooting.md)** – Common issues and solutions

---

## 📂 Documentation Tracks

### 1️⃣ Overview – Platform Fundamentals

**Audience:** Developers new to MozaiksAI, architects evaluating the platform

| Document | Description |
|----------|-------------|
| **[Architecture Overview](overview/architecture.md)** | System layers, subsystems, transport, events, persistence, observability |
| **[Request Lifecycle](overview/lifecycle.md)** | End-to-end trace: HTTP request → AG2 execution → WebSocket response |
| **[Multi-Tenancy & Security](overview/tenancy_and_security.md)** | Enterprise isolation, cache seeds, secret handling, context boundaries |

**Start here if:** You're new to MozaiksAI and want to understand the big picture.

---

### 2️⃣ Runtime – Backend Deep Dives

**Audience:** Backend developers, platform engineers, runtime contributors

| Document | Description |
|----------|-------------|
| **[Runtime Overview](runtime/runtime_overview.md)** | Workflow manager, orchestration engine, AG2 patterns, execution flow |
| **[Event Pipeline](runtime/event_pipeline.md)** | UnifiedEventDispatcher, business events, UI tool events, AG2 serialization |
| **[Transport & Streaming](runtime/transport_and_streaming.md)** | WebSocket/SSE, message filtering, event envelopes, correlation IDs |
| **[Persistence & Resume](runtime/persistence_and_resume.md)** | MongoDB integration, AG2 state serialization, session resume |
| **[Observability](runtime/observability.md)** | Structured logging, performance metrics, AG2 runtime logger, Prometheus |
| **[Token Management](runtime/token_management.md)** | Real-time token tracking, cost calculation, billing integration |
| **[Configuration Reference](runtime/configuration_reference.md)** | Runtime settings, feature toggles, environment variables |

**Start here if:** You're building runtime features or debugging backend behavior.

---

### 3️⃣ Workflows – Authoring Guides

**Audience:** Workflow developers, AI engineers, tool creators

| Document | Description |
|----------|-------------|
| **[Workflow Authoring Guide](workflows/workflow_authoring.md)** | Complete workflow creation: agents, tools, context vars, orchestration |
| **[Tool Manifest System](workflows/tool_manifest.md)** | Define UI_Tool and Agent_Tool in tools.json |
| **[UI Tool Pipeline](workflows/ui_tool_pipeline.md)** | Agent → UI tool invocation → frontend component rendering |
| **[Context Variables](workflows/context_variables.md)** | Database queries, environment vars, derived state, triggers |
| **[Structured Outputs](workflows/structured_outputs.md)** | Pydantic schemas for validated agent responses |
| **[Auto-Tool Execution](workflows/auto_tool_execution.md)** | Agent auto-tool mode, suppression rules, UI filtering |

**Start here if:** You're creating workflows or adding tools to existing workflows.

---

### 4️⃣ Frontend – React ChatUI Integration

**Audience:** Frontend developers, UI/UX engineers, component authors

| Document | Description |
|----------|-------------|
| **[Unified UI Tools & Design](frontend/unified_ui_tools_and_design.md)** | Complete reference: UI tool generation, design system, auto-tool flow, theming |
| **[ChatUI Architecture](frontend/chatui_architecture.md)** | WorkflowUIRouter, EventDispatcher, dynamic component loading |
| **[UI Components](frontend/ui_components.md)** | Building workflow-specific UI components |
| **[Workflow Integration](frontend/workflow_integration.md)** | Connecting ChatUI to backend workflows |

**Start here if:** You're building React components or integrating UI features.

---

### 5️⃣ Operations – Deployment & Monitoring

**Audience:** DevOps engineers, SREs, platform operators

| Document | Description |
|----------|-------------|
| **[Deployment Guide](operations/deployment.md)** | Docker setup, environment configuration, production best practices |
| **[Monitoring Guide](operations/monitoring.md)** | Metrics endpoints, Prometheus integration, log aggregation |
| **[Performance Tuning](operations/performance_tuning.md)** | Optimization strategies, caching, resource limits |
| **[Troubleshooting](operations/troubleshooting.md)** | Common issues, debugging techniques, error patterns |

**Start here if:** You're deploying or operating MozaiksAI in production.

---

### 6️⃣ Reference – API Specs & Schemas

**Audience:** All developers (quick lookup reference)

| Document | Description |
|----------|-------------|
| **[API Reference](reference/api_reference.md)** | HTTP endpoints, request/response schemas, error codes |
| **[Database Schema](reference/database_schema.md)** | MongoDB collections, document structures, indexes |
| **[Environment Variables](reference/environment_variables.md)** | Complete list of env vars with descriptions and defaults |
| **[Event Reference](reference/event_reference.md)** | Event types, payloads, routing rules |

**Start here if:** You need quick lookup for APIs, schemas, or configuration.

---

## 🔍 Quick Links

### Common Tasks

**Workflow Development:**
- [Create a new workflow](workflows/workflow_authoring.md#creating-a-new-workflow)
- [Add a UI tool](workflows/ui_tool_pipeline.md#creating-a-ui-tool)
- [Add an agent tool](workflows/tool_manifest.md#agent-tools)
- [Define context variables](workflows/context_variables.md#variable-types)
- [Configure orchestration patterns](runtime/runtime_overview.md#ag2-patterns)

**Runtime Configuration:**
- [Set up MongoDB persistence](runtime/persistence_and_resume.md#setup)
- [Configure logging](runtime/observability.md#structured-logging)
- [Enable metrics endpoints](runtime/observability.md#metrics-endpoints)
- [Set up WebSocket transport](runtime/transport_and_streaming.md#websocket-setup)

**Frontend Integration:**
- [Build a workflow UI component](frontend/ui_components.md#component-structure)
- [Integrate design system](frontend/unified_ui_tools_and_design.md#design-system)
- [Handle UI tool events](frontend/workflow_integration.md#event-handling)
- [Customize themes](frontend/unified_ui_tools_and_design.md#theming)

**Operations:**
- [Deploy with Docker](operations/deployment.md#docker-deployment)
- [Set up monitoring](operations/monitoring.md#prometheus-grafana)
- [View logs](operations/monitoring.md#log-aggregation)
- [Debug common issues](operations/troubleshooting.md#common-issues)

---

## 🎯 Learning Paths

### Path 1: Backend Developer

**Goal:** Build and extend runtime features

1. [Architecture Overview](overview/architecture.md) – Understand system design
2. [Request Lifecycle](overview/lifecycle.md) – Trace execution flow
3. [Runtime Overview](runtime/runtime_overview.md) – Learn orchestration patterns
4. [Event Pipeline](runtime/event_pipeline.md) – Master event dispatching
5. [Persistence & Resume](runtime/persistence_and_resume.md) – Work with MongoDB

**Next Steps:** Contribute to runtime enhancements or build custom orchestration patterns.

---

### Path 2: Workflow Developer

**Goal:** Create declarative multi-agent workflows

1. [Workflow Authoring Guide](workflows/workflow_authoring.md) – Learn manifest structure
2. [Tool Manifest System](workflows/tool_manifest.md) – Define tools
3. [Context Variables](workflows/context_variables.md) – Manage state
4. [UI Tool Pipeline](workflows/ui_tool_pipeline.md) – Invoke frontend components
5. [Structured Outputs](workflows/structured_outputs.md) – Validate responses

**Next Steps:** Build production workflows or contribute example templates.

---

### Path 3: Frontend Developer

**Goal:** Build React UI components for workflows

1. [ChatUI Architecture](frontend/chatui_architecture.md) – Understand component routing
2. [Unified UI Tools & Design](frontend/unified_ui_tools_and_design.md) – Master design system
3. [UI Components](frontend/ui_components.md) – Build workflow components
4. [Workflow Integration](frontend/workflow_integration.md) – Connect to backend

**Next Steps:** Create reusable UI components or contribute to the design system.

---

### Path 4: Platform Operator

**Goal:** Deploy and monitor MozaiksAI in production

1. [Deployment Guide](operations/deployment.md) – Set up Docker environment
2. [Environment Variables](reference/environment_variables.md) – Configure runtime
3. [Monitoring Guide](operations/monitoring.md) – Set up metrics and logging
4. [Troubleshooting](operations/troubleshooting.md) – Debug production issues

**Next Steps:** Optimize performance or integrate with enterprise monitoring stacks.

---

## 🛠️ Advanced Topics

### Special Runtime Features

| Topic | Document |
|-------|----------|
| **Cache Seed Propagation** | [Multi-Tenancy & Security](overview/tenancy_and_security.md#cache-seed-mechanics) |
| **Auto-Tool Mode** | [Auto-Tool Execution](workflows/auto_tool_execution.md) |
| **Agent Visibility Filtering** | [Transport & Streaming](runtime/transport_and_streaming.md#message-filtering) |
| **Structured Output Handling** | [Structured Outputs](workflows/structured_outputs.md) |
| **Context Variable Triggers** | [Context Variables](workflows/context_variables.md#derived-variables) |
| **AG2 Runtime Logger** | [Observability](runtime/observability.md#ag2-runtime-logger) |

---

## 📖 Document Conventions

### Format Guidelines

All documentation follows these conventions:

- **Code Examples**: Inline code uses `backticks`, blocks use triple backticks with language
- **File Paths**: Absolute paths from repo root (e.g., `core/transport/simple_transport.py`)
- **Module References**: Python dotted notation (e.g., `core.events.unified_event_dispatcher`)
- **Endpoints**: HTTP endpoints prefixed with `/` (e.g., `/api/chats/{enterprise}/{workflow}/start`)
- **JSON Schemas**: Include TypeScript-style type annotations for clarity

### Terminology

| Term | Definition |
|------|------------|
| **Workflow** | Self-contained multi-agent pipeline with JSON manifests |
| **Agent** | AG2 ConversableAgent configured from `agents.json` |
| **UI Tool** | Tool that triggers frontend component rendering |
| **Agent Tool** | Backend-only tool (no UI component) |
| **Context Variable** | Shared state managed by `ContextVariableManager` |
| **Visual Agent** | Agent whose messages appear in the chat UI |
| **Cache Seed** | Deterministic per-chat seed for reproducibility |
| **Enterprise ID** | Multi-tenant isolation boundary |

---

## 🤝 Contributing to Documentation

We welcome documentation improvements! Here's how:

### Reporting Issues

Found an error or missing information?

1. Check if issue already exists in [GitHub Issues](https://github.com/BlocUnited-LLC/MozaiksAI/issues)
2. Create new issue with label `documentation`
3. Include document name and section

### Submitting Updates

Want to improve documentation?

1. Fork repository and create feature branch
2. Edit Markdown files in `docs/`
3. Follow format guidelines and conventions
4. Submit pull request with clear description

### Documentation Standards

- **Accuracy**: Verify against current code implementation
- **Clarity**: Use simple language and clear examples
- **Completeness**: Include all parameters, options, and edge cases
- **Examples**: Provide real-world code snippets
- **Links**: Cross-reference related documents

---

## 📝 Documentation Roadmap

### Coming Soon

- [ ] **Contributing Guide** – Development workflow, testing, code standards
- [ ] **Architecture Decision Records (ADRs)** – Historical design decisions
- [ ] **Migration Guides** – Version upgrade paths
- [ ] **Video Tutorials** – Visual walkthroughs of key concepts
- [ ] **Interactive Examples** – Live workflow demos
- [ ] **API Playground** – Interactive HTTP endpoint testing

### Requests

Have a documentation request? [Open an issue](https://github.com/BlocUnited-LLC/MozaiksAI/issues/new) with the `documentation` label.

---

## 🔗 External Resources

### AG2 (Autogen) Framework

- [AG2 Documentation](https://microsoft.github.io/autogen/)
- [AG2 GitHub Repository](https://github.com/microsoft/autogen)
- [AG2 Examples](https://microsoft.github.io/autogen/docs/Examples/)

### Related Technologies

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [MongoDB Documentation](https://www.mongodb.com/docs/)
- [React Documentation](https://react.dev/)
- [WebSocket API](https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API)

---

## 📄 License

All documentation is proprietary and confidential to **BlocUnited LLC**.

For licensing inquiries, contact: [email protected]

---

<div align="center">

**[Main README](../README.md)** • **[Architecture](overview/architecture.md)** • **[Quick Start](../README.md#-quick-start)** • **[GitHub](https://github.com/BlocUnited-LLC/MozaiksAI)**

📚 Complete, accurate, and always up-to-date documentation

</div>
