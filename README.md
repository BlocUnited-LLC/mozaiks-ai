# 🎯 MozaiksAI Runtime# 🏭 MozaiksAI Runtime



<div align="center"><div align="center">



![MozaiksAI Logo](ChatUI/public/mozaik_logo.svg)![MozaiksAI Logo](ChatUI/public/mozaik_logo.svg)



**Production-Grade AG2 Orchestration Engine**  **Enterprise-Grade AI Agent Orchestration Runtime**  

*Event-Driven • Declarative • Multi-Tenant**Event-Driven • Declarative • Multi-Tenant*



[![AG2 Framework](https://img.shields.io/badge/AG2-Autogen-green?style=flat&logo=microsoft)](https://microsoft.github.io/autogen/)[![AG2 Framework](https://img.shields.io/badge/AG2-Autogen-green?style=flat&logo=microsoft)](https://microsoft.github.io/autogen/)

[![Python](https://img.shields.io/badge/Python-3.9+-blue?style=flat&logo=python)](https://www.python.org/)[![Python](https://img.shields.io/badge/Python-3.9+-blue?style=flat&logo=python)](https://www.python.org/)

[![FastAPI](https://img.shields.io/badge/FastAPI-Latest-009688?style=flat&logo=fastapi)](https://fastapi.tiangolo.com/)[![FastAPI](https://img.shields.io/badge/FastAPI-Latest-009688?style=flat&logo=fastapi)](https://fastapi.tiangolo.com/)

[![MongoDB](https://img.shields.io/badge/MongoDB-Persistence-47A248?style=flat&logo=mongodb)](https://www.mongodb.com/)[![MongoDB](https://img.shields.io/badge/MongoDB-Persistence-47A248?style=flat&logo=mongodb)](https://www.mongodb.com/)

[![WebSocket](https://img.shields.io/badge/WebSocket-Real--time-orange?style=flat)](https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API)[![WebSocket](https://img.shields.io/badge/WebSocket-Real--time-orange?style=flat)](https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API)



**The declarative, event-driven execution layer for multi-agent AI workflows.**</div>



[Quick Start](#-quick-start) • [Documentation](#-documentation) • [Architecture](#️-architecture) • [Examples](#-workflow-examples)---



</div>## 📋 Table of Contents



---- [🎯 What is MozaiksAI?](#-what-is-mozaiksai)

- [✨ Key Features](#-key-features)

## 📋 Table of Contents- [🏗️ Architecture Overview](#️-architecture-overview)

- [🚀 Quick Start](#-quick-start)

- [🎯 What is MozaiksAI Runtime?](#-what-is-mozaiksai-runtime)- [📂 Project Structure](#-project-structure)

- [✨ Key Features](#-key-features)- [🔧 Core Systems](#-core-systems)

- [🏗️ Architecture](#️-architecture)- [🎯 Workflow System](#-workflow-system)

- [🚀 Quick Start](#-quick-start)- [📊 Observability & Analytics](#-observability--analytics)

- [📂 Project Structure](#-project-structure)- [🔐 Multi-Tenancy & Security](#-multi-tenancy--security)

- [🔧 Core Systems](#-core-systems)- [⚡ Development Guide](#-development-guide)

- [🎯 Workflow System](#-workflow-system)- [🐳 Docker Deployment](#-docker-deployment)

- [📊 Observability](#-observability)- [📚 Documentation](#-documentation)

- [🔐 Multi-Tenancy](#-multi-tenancy)- [🤝 Contributing](#-contributing)

- [📚 Documentation](#-documentation)

- [🤝 Contributing](#-contributing)---



---## 🎯 What is MozaiksAI?



## 🎯 What is MozaiksAI Runtime?MozaiksAI is a **production-grade, event-driven runtime** for orchestrating complex AI agent workflows. Built on Microsoft's AG2 (Autogen) framework, it provides the foundation for the world's first AI-driven startup foundry.



**MozaiksAI Runtime** is a production-grade orchestration engine built on Microsoft's **AG2 (Autogen)** framework. It adds **event-driven persistence**, **real-time WebSocket streaming**, **multi-tenant isolation**, **dynamic UI integration**, and **enterprise-scale observability** to AG2's agent collaboration model.### 🌟 The Vision



### The Problem We Solve**MozaiksAI powers the new AI-native app economy.** With one prompt, users create fully functional, monetizable applications with built-in agentic features—running on a modular, multi-tenant runtime that handles all the complexity.



AG2 provides powerful multi-agent orchestration, but lacks:### 🎭 What Makes This Special

- ❌ Real-time streaming to frontend applications

- ❌ Persistent state management across sessionsUnlike traditional agent frameworks that require extensive coding and configuration:

- ❌ Multi-tenant isolation for enterprise deployments

- ❌ Dynamic UI component invocation from agents- **Declarative Workflows**: Define agents, tools, and UI components in JSON—no code changes needed

- ❌ Comprehensive observability and cost tracking- **Hot-Swappable**: Load and execute workflows dynamically without server restarts

- ❌ Declarative workflow authoring (requires code for every workflow)- **Event-Driven Core**: Every action flows through a unified event pipeline for perfect observability

- **Multi-Tenant by Design**: Isolated execution contexts with enterprise-grade security

### Our Solution- **Real-Time Everything**: WebSocket transport, live persistence, streaming token metrics



```mermaid## Key Architectural Pillars

graph LR

    A[Declarative JSON] -->|Workflows| B[MozaiksAI Runtime]1.  **Event-Driven Core**: At the heart of MozaiksAI is a powerful event bus. Every action—from an agent sending a message to token usage being calculated—is an event. This allows for decoupled components, real-time data processing, and extreme flexibility.

    B -->|AG2 Engine| C[Multi-Agent Orchestration]2.  **Centralized Event Processing**: All events generated by the AG2 engine flow through a single event `UIEventProcessor`. This central hub is responsible for delegating tasks like data persistence, UI updates, and logging, ensuring a single, predictable path for all system events.

    C -->|Events| D[WebSocket Transport]3.  **Real-Time Persistence**: We've eliminated batch processing. The `AG2PersistenceManager` listens to the event stream and saves every message, token count, and cost metric to our MongoDB database the moment it occurs. This enables live dashboards, accurate cost tracking, and flawless chat session resumption.

    C -->|State| E[MongoDB Persistence]4.  **Modular & Composable Workflows**: Workflows, agents, and tools are defined in simple YAML files, allowing for rapid development and easy modification without changing core application code. This "configuration-as-code" approach makes the system highly adaptable.

    C -->|Metrics| F[Observability Layer]

    D --> G[React ChatUI]## Features

    E --> H[Session Resume]

    F --> I[Analytics Dashboard]-   **Seamless Chat Resumption**: Never lose context. Any chat session can be picked up exactly where it left off, with the full message history loaded instantly.

```-   **Live Performance Tracking**: Monitor token usage and costs in real-time as agents work, not after the fact.

-   **Dynamic UI**: The frontend is driven by events, allowing for rich, real-time user experiences that reflect the agent's activities.

**MozaiksAI Runtime = AG2 + Production Infrastructure + Event-Driven Architecture**-   **Modular Tooling**: Easily add new tools and capabilities to your agents. Our tool registry system makes it simple to extend agent functionality.

-   **Production-Ready**: With built-in logging, error handling, and a scalable architecture, MozaiksAI is designed for real-world deployment.

---

## Getting Started

## ✨ Key Features

### Prerequisites

### 🎨 Declarative Workflow Authoring

-   Python 3.10+

Define complete multi-agent workflows in JSON—no code changes to the runtime needed.-   MongoDB instance

-   Node.js and npm (for the ChatUI)

```json-   An OpenAI API key (or other LLM provider)

{

  "agents": {### Installation

    "InterviewAgent": {

      "system_message": "You are an expert intake specialist...",1.  **Clone the repository:**

      "auto_tool_mode": false    ```bash

    }    git clone https://github.com/BlocUnited-LLC/MozaiksAI.git

  },    cd MozaiksAI

  "tools": {    ```

    "action_plan": {

      "type": "UI_Tool",2.  **Install Python dependencies:**

      "description": "Display interactive action plan artifact"    ```bash

    }    pip install -r requirements.txt

  }    ```

}

```3.  **Configure Environment Variables:**

    Create a `.env` file in the root directory and add your configuration, including your MongoDB connection string and LLM API keys.

**Just drop a new folder in `workflows/` and the runtime discovers it automatically.**

    Logging format toggle:

### ⚡ Real-Time Event Streaming    - Set `LOGS_AS_JSON=true` to write structured JSON lines to the `.log` files (content changes, filenames stay `.log`)

    - Leave it unset or `false` for human-readable pretty text in the `.log` files

Every agent message, tool call, and state change flows through a unified event pipeline to your frontend.    - Console output is always pretty and colorized in development



- **WebSocket/SSE Transport**: Dual-protocol support with automatic fallback4.  **Run the ChatUI:**

- **Message Filtering**: Show only relevant agents to end users (hide internal coordinators)    ```bash

- **Bi-Directional**: Frontend can trigger backend handlers and update context variables    cd ChatUI

- **Event Correlation**: Track request/response flows with unique event IDs    npm install

    npm start

### 💾 Persistent State Management    ```



Never lose context. Every workflow execution is fully persisted and resumable.5.  **Run the Backend Server:**

    In the root directory, run:

- **AG2 State Persistence**: Full groupchat state serialization via `AG2PersistenceManager`    ```bash

- **Message History**: Complete chat transcripts stored in MongoDB    python run_server.py

- **Session Resume**: Pick up any conversation exactly where it left off    ```

- **Token Tracking**: Real-time cost metrics per chat, agent, and workflow

### Run with Docker (optional)

### 🔐 Multi-Tenant by Design

You can run the backend with Docker Compose:

Isolated execution contexts with enterprise-grade security.

```powershell

- **Enterprise Isolation**: Separate MongoDB collections per `enterprise_id`# From repo root (Windows PowerShell)

- **Cache Seed Propagation**: Deterministic per-chat seeds prevent state bleeddocker compose -f infra/compose/docker-compose.yml up --build

- **Secret Management**: Secure credential collection and storage```

- **Context Boundaries**: No data leakage across tenants or workflows

Notes:

### 📊 Enterprise Observability- Dockerfile is at `infra/docker/Dockerfile`.

- Compose file only starts the FastAPI app and mounts `logs/logs` so you can tail runtime output.

Comprehensive monitoring, metrics, and analytics out of the box.- AG2 runtime logging (sqlite/file) is enabled by default.



- **Performance Metrics**: Track latency, token usage, and costs in real-time### Metrics & Usage Tracking Quick Reference

- **Structured Logging**: JSON logs with context correlation

- **AG2 Runtime Logger**: SQLite-backed execution traces for debuggingRuntime surfaces two data paths:

- **Prometheus Export**: Standard metrics endpoint for monitoring stacks

1. **AG2 runtime logger (sqlite/file)** ? provides per-request start/end timestamps and token usage.

### 🎯 Dynamic UI Integration2. **WorkflowStats rollups** ? real-time MongoDB documents with per-chat and per-agent totals (tokens, cost, duration).



Agents can invoke React components dynamically during workflow execution.HTTP endpoints (no auth in dev):



- **UI Tools**: Agents call `display_action_plan()` → frontend renders `ActionPlan` artifact| Endpoint | Purpose |

- **Auto-Tool Mode**: Agents execute tools without asking permission (configurable per agent)|----------|---------|

- **Context Synchronization**: Shared state between agents and UI components| `/metrics/perf/aggregate` | JSON aggregate (turns, tool calls, tokens, cost) |

- **Theme System**: Per-enterprise design system customization| `/metrics/perf/chats` | JSON array of per-chat snapshots |

| `/metrics/perf/chats/{chat_id}` | Single chat snapshot |

---| `/metrics/prometheus` | Minimal Prometheus exposition for quick scrapes |



## 🏗️ ArchitectureMinimal local verification (PowerShell):

```powershell

MozaiksAI follows a **strategically lean** architecture where every component serves a clear, non-overlapping purpose.Invoke-RestMethod http://localhost:8000/metrics/perf/aggregate | ConvertTo-Json -Depth 4

Invoke-WebRequest http://localhost:8000/metrics/prometheus | Select -Expand Content

``````

┌─────────────────────────────────────────────────────────┐

│              ChatUI (React Frontend)                    │Cost, token, and duration fields are accumulated live in the WorkflowStats document (`mon_<enterprise>_<workflow>`).

│  • WebSocket/SSE Client                                 │Duration per agent/chat is derived from the AG2 runtime logger start/end timestamps captured by the realtime logger shim.

│  • Dynamic Component Renderer                           │

│  • Artifact Design System                               │### Viewing Logs

└──────────────────┬──────────────────────────────────────┘

                   │ WebSocket/HTTP- Files: `logs/logs/*.log` (filenames are constant)

┌──────────────────▼──────────────────────────────────────┐- Content format:

│         MozaiksAI Runtime (FastAPI + AG2)               │    - Pretty text (default)

│  ┌────────────────────────────────────────────────┐     │    - JSON Lines (when `LOGS_AS_JSON=true`)

│  │  SimpleTransport (WebSocket/SSE)               │     │- Console: pretty, emoji-enhanced output with file and line context

│  │  • Connection Lifecycle                        │     │

│  │  • Message Filtering (visual_agents)           │     │Example (Windows PowerShell):

│  │  • Event Envelope Construction                 │     │

│  └────────────────────────────────────────────────┘     │```powershell

│  ┌────────────────────────────────────────────────┐     │$env:LOGS_AS_JSON = "1"; python run_server.py

│  │  UnifiedEventDispatcher                        │     │# or

│  │  • Business Events → Logging                   │     │Remove-Item Env:LOGS_AS_JSON; python run_server.py

│  │  • UI Tool Events → WebSocket                  │     │```

│  │  • AG2 Events → Serialization                  │     │

│  └────────────────────────────────────────────────┘     │### Logging quickstart

│  ┌────────────────────────────────────────────────┐     │

│  │  Orchestration Engine                          │     │- Two file sinks only:

│  │  • Workflow Discovery & Loading                │     │    - `mozaiks.log` — operational workflow/runtime logs (no chat transcripts)

│  │  • AG2 Pattern Execution (Default/Auto/RR)     │     │- Filenames are fixed; content switches between pretty text and JSON via `LOGS_AS_JSON`.

│  │  • Tool Registry & Binding                     │     │- Override the logs folder with `LOGS_BASE_DIR` (default is `logs/logs` relative to this repo).

│  │  • Context Variable Management                 │     │

│  └────────────────────────────────────────────────┘     │Windows PowerShell examples:

│  ┌────────────────────────────────────────────────┐     │

│  │  AG2PersistenceManager (MongoDB)               │     │```powershell

│  │  • Chat Sessions & Message History             │     │# Write JSONL to the default location

│  │  • Groupchat State Serialization               │     │$env:LOGS_AS_JSON = "true"; python run_server.py

│  │  • Token & Cost Tracking                       │     │

│  └────────────────────────────────────────────────┘     │# Write pretty text logs to a custom folder

│  ┌────────────────────────────────────────────────┐     │$env:LOGS_AS_JSON = "false"; $env:LOGS_BASE_DIR = "C:\MozaiksLogs"; python run_server.py

│  │  Observability Layer                           │     │```

│  │  • Performance Metrics (Prometheus)            │     │

│  │  • Structured Logging (JSON/Pretty)            │     │Docker Compose volume mapping tips:

│  │  • AG2 Runtime Logger (SQLite)                 │     │

│  └────────────────────────────────────────────────┘     │- If you do not set `LOGS_BASE_DIR`, map the container folder `/app/logs/logs` to a host folder.

└──────────────────┬──────────────────────────────────────┘- If you set `LOGS_BASE_DIR` (for example `/data/logs` inside the container), map that path instead.

                   │ MongoDB Protocol

┌──────────────────▼──────────────────────────────────────┐Examples (compose snippet):

│              MongoDB (Atlas / Local)                    │

│  Collections:                                           │```yaml

│  • chat_sessions (session metadata + messages)          │services:

│  • workflow_stats_{enterprise}_{workflow}               │    app:

│  • enterprise_themes (per-tenant design tokens)         │        environment:

└─────────────────────────────────────────────────────────┘            - LOGS_AS_JSON=true

``````



### Core Design Principles### Frontend/Backend Cache Seed Alignment



1. **Event-Driven**: All interactions flow through the `UnifiedEventDispatcher` for perfect observabilityThe backend assigns a deterministic per-chat `cache_seed` (stored in the `ChatSessions` doc and derived from the first 32 bits of SHA-256 of `enterprise_id:chat_id`). This value:

2. **Declarative**: Workflows are JSON manifests, not code—hot-swappable without restarts

3. **Modular**: Each subsystem (transport, persistence, orchestration) is independently replaceable1. Is returned in the `/api/chats/{enterprise}/{workflow}/start` response under `cache_seed`.

4. **Multi-Tenant**: Enterprise-scoped isolation with deterministic cache seeds and collection routing2. Is emitted immediately after WebSocket connection as a `chat_meta` event (kind `chat_meta`).

5. **AG2-Native**: Built on stable AG2 APIs—extends without forking or patching vendor code3. Is persisted client-side in `localStorage` under `mozaiks.current_chat_id.cache_seed.<chatId>`.

4. Is included in dynamic UI component cache keys: `<chatId>:<cache_seed>:<workflow>:<component>` to prevent cross-chat component state bleed.

---

Process-wide defaults:

## 🚀 Quick Start- `LLM_DEFAULT_CACHE_SEED` → hard override for the default (used only if per-chat seed not provided).

- `RANDOMIZE_DEFAULT_CACHE_SEED=1` → randomizes the process default seed (does not affect per-chat seeds).

### Prerequisites

Why this matters:

- **Python 3.9+** with pip- Ensures reproducibility when resuming a chat (same seed regenerates identical deterministic behaviors beneath AG2 caching layers).

- **MongoDB** (local or Atlas cluster)- Prevents UI component instances from leaking across chats that share workflow/component names.

- **Node.js 16+** with npm (for ChatUI)- Provides a single seed you can thread through future caching or memoization layers (LLM adapters, vector lookups, layout decisions) for consistent variance control.

- **OpenAI API Key** (or compatible LLM provider)

Implementation notes:

### Installation- Backend emits via `send_event_to_ui` with `kind: 'chat_meta'`.

- Frontend listens in `ChatPage.js` and stores/applies the seed before loading workflow components.

```bash- `WorkflowUIRouter` incorporates the seed into its internal `componentCache` key.

# Clone the repository

git clone https://github.com/BlocUnited-LLC/MozaiksAI.gitIf you add additional caches, prefer reusing the existing `cache_seed` rather than introducing new entropy variables.

cd MozaiksAI            # Optional: redirect logs inside the container

            # - LOGS_BASE_DIR=/data/logs

# Install Python dependencies        volumes:

pip install -r requirements.txt            # Default location (no LOGS_BASE_DIR):

            - ./logs/logs:/app/logs/logs

# Configure environment variables            # Or, when using LOGS_BASE_DIR=/data/logs

cp .env.example .env            # - ./logs/logs:/data/logs

# Edit .env with your MongoDB URI, OpenAI key, etc.```

```

## 📚 Documentation

### Configuration

**NEW:** Comprehensive documentation has been reorganized for clarity and depth.

Create a `.env` file in the root directory:

👉 **[Start Here: Documentation Portal](docs/README.md)** 👈

```env

# MongoDB### Quick Links

MONGODB_URI=mongodb://localhost:27017

MONGODB_DB_NAME=mozaiksai- **[Platform Architecture](docs/overview/architecture.md)** - System design, subsystems, and special runtime features

- **[Request Lifecycle](docs/overview/lifecycle.md)** - End-to-end trace from HTTP request to WebSocket response

# LLM Configuration- **[Multi-Tenancy & Security](docs/overview/tenancy_and_security.md)** - Isolation, cache seed mechanics, and secret handling

OPENAI_API_KEY=sk-...- **[Unified UI Tools & Design Guide](docs/frontend/unified_ui_tools_and_design.md)** - Complete reference for UI tool generation, design system, auto-tool flow, and theming

LLM_DEFAULT_CACHE_SEED=42

### Documentation Tracks

# Logging

LOGS_AS_JSON=falseThe `docs/` folder is organized by audience and use case:

LOGS_BASE_DIR=logs/logs

| Track | Purpose | Key Documents |

# Runtime Options|-------|---------|---------------|

CONTEXT_AWARE=true| **Overview** | Platform fundamentals | Architecture, lifecycle, security |

CLEAR_TOOL_CACHE_ON_START=true| **Runtime** | Deep dives into backend systems | Event pipeline, transport, persistence, observability, token management |

```| **Workflows** | Authoring agent workflows | Tool manifests, structured outputs, UI tool pipeline |

| **Frontend** | React ChatUI integration | **Unified UI tools & design**, component system, transport client |

### Run the Runtime| **Operations** | Deployment and monitoring | Docker setup, logging, metrics, troubleshooting |

| **Reference** | API specs and schemas | MongoDB collections, environment variables, event types |

```bash

# Start the FastAPI backend**Note:** Legacy scattered UI/design/auto-tool/theme docs have been consolidated into the **Unified UI Tools & Design Guide** for a single authoritative reference.

python run_server.py

```---



The runtime will:## 🧩 Key Features

- 🔍 Discover workflows in `workflows/` directory

- 🔧 Load tool manifests and register callables### Dynamic Agent-UI Integration

- 🚀 Start FastAPI server on `http://localhost:8000`- **Real-Time Component Control:** Agents can dynamically render, update, and control React components based on conversation context

- 📡 Enable WebSocket endpoint at `ws://localhost:8000/ws/{enterprise_id}/{workflow_name}/{chat_id}`- **Bidirectional Communication:** UI components can trigger backend handlers, creating interactive workflows

- **Context Variable Synchronization:** Seamless state sharing between agents and frontend components

### Run with ChatUI (Optional)

### Unified Transport System

```bash- **Protocol Flexibility:** Automatic WebSocket/SSE negotiation with graceful fallback

# In a separate terminal- **Message Filtering:** Smart filtering ensures users only see relevant agent communications

cd ChatUI- **Event-Driven Architecture:** Six standardized event types for consistent frontend-backend communication

npm install

npm start### Manifest-Driven Development

```- **Tool Registration:** JSON-based tool manifests for dynamic agent capability extension

- **Workflow Configuration:** Complete workflow definitions in `workflow.json` with UI component integration

Visit `http://localhost:3000` to interact with workflows through the React interface.- **Hot-Reload Support:** Add or modify agents, tools, and components without server restart



### Docker Deployment### Enterprise-Grade Persistence

- **Conversation Continuity:** Full groupchat state persistence across server restarts

```bash- **AG2 Resume:** Official AutoGen resume patterns for seamless conversation restoration

# From repo root- **Data Isolation:** Secure enterprise and chat ID validation for multi-tenant deployments

docker compose -f infra/compose/docker-compose.yml up --build

```### 📊 Real-Time Analytics & Performance Monitoring

- **Chat-Level Aggregation:** Comprehensive analytics across all workflow uses with session-by-session tracking

See [Deployment Guide](docs/operations/deployment.md) for production configuration.- **Agent Performance Metrics:** Response time analysis, token usage patterns, and efficiency monitoring

- **Live Cost Intelligence:** Real-time threshold monitoring with automated alerts and budget management

---- **Workflow Optimization:** Historical performance comparison and optimization recommendations

- **Business Intelligence:** Enterprise-level insights for resource planning and cost forecasting

## 📂 Project Structure

---

```

MozaiksAI/## 📂 Project Structure

├── 📁 core/                    # Runtime engine and infrastructure

│   ├── transport/              # WebSocket/SSE transport layer```

│   │   ├── simple_transport.py # Connection lifecycle and message filteringMozaiksAI/

│   │   └── websocket.py        # WebSocket endpoint handlers├── 📁 workflows/          # Modular agent workflows and configurations

│   ├── events/                 # Event system and dispatcher│   └── Generator/         # Example workflow with tool manifests

│   │   ├── unified_event_dispatcher.py  # Central event router├── 📁 core/              # Core platform backend systems

│   │   ├── event_serialization.py       # AG2 → JSON conversion│   ├── transport/        # SimpleTransport and event handling

│   │   └── auto_tool_handler.py         # UI tool execution handler│   ├── events/           # UnifiedEventDispatcher and event handlers

│   ├── workflow/               # Workflow discovery and execution│   ├── data/            # Persistence and database management

│   │   ├── orchestration_patterns.py  # AG2 pattern implementations│   └── workflow/        # Workflow loading and tool registry

│   │   ├── agent_tools.py             # Tool registry and binding├── 📁 ChatUI/           # React frontend application

│   │   ├── context_variables.py       # Context var management│   ├── src/components/  # Dynamic UI components

│   │   └── workflow_manager.py        # Workflow loading and validation│   ├── src/services/    # Transport and API integration

│   ├── data/                   # Persistence layer│   └── src/context/     # Frontend state management

│   │   ├── persistence_manager.py  # AG2PersistenceManager (MongoDB)└── 📁 docs/             # Comprehensive technical documentation

│   │   └── models.py               # Pydantic data models    ├── overview/        # Platform fundamentals (architecture, lifecycle, security)

│   └── observability/          # Monitoring and logging    ├── runtime/         # Backend deep dives (coming soon)

│       ├── performance_manager.py   # Metrics collection    ├── workflows/       # Workflow authoring guides (coming soon)

│       ├── ag2_runtime_logger.py    # AG2 execution traces    ├── frontend/        # React ChatUI docs (coming soon)

│       └── realtime_token_logger.py # Live token tracking    ├── operations/      # Deployment and monitoring (coming soon)

│    ├── reference/       # API specs and schemas (coming soon)

├── 📁 workflows/               # Declarative workflow definitions    └── contributing/    # Development guidelines (coming soon)

│   ├── Generator/              # Example: workflow generation workflow```

│   │   ├── agents.json         # Agent system messages and config

│   │   ├── tools.json          # Tool registry (UI_Tool + Agent_Tool)### Key Directories

│   │   ├── structured_outputs.json  # Pydantic schemas

│   │   ├── context_variables.json   # Variable definitions- **`workflows/`** – Self-contained agent workflows with tool manifests and UI component definitions

│   │   ├── orchestrator.json   # Runtime configuration- **`core/`** – Platform backend including transport, persistence, event dispatching, and workflow systems

│   │   └── tools/              # Python tool implementations- **`ChatUI/`** – React frontend with dynamic component system and real-time transport integration  

│   │       ├── action_plan.py- **`docs/`** – Comprehensive technical documentation organized by use case (see [Documentation Portal](docs/README.md))

│   │       ├── request_api_key.py

│   │       └── generate_and_download.py---

│   └── YourWorkflow/           # Add your workflow here!

│## 📖 Legacy Documentation References

├── 📁 ChatUI/                  # React frontend (optional)

│   ├── src/The following documents are being phased out in favor of the new structured documentation in `docs/`:

│   │   ├── core/               # WorkflowUIRouter, EventDispatcher

│   │   ├── workflows/          # Per-workflow UI components### Core System Documentation (Legacy - See docs/overview/ for current versions)

│   │   └── components/         # Shared UI components- **[Transport & Events](docs/TRANSPORT_AND_EVENTS.md)** – Unified transport system with SSE/WebSocket support and event filtering

│   └── public/- **[Dynamic UI System](docs/DYNAMIC_UI_SYSTEM.md)** – How agents dynamically control frontend components with visual flowcharts

│- **[Tool Manifest System](docs/TOOL_MANIFEST_SYSTEM.md)** – JSON-based tool registration and agent capability extension

├── 📁 docs/                    # Comprehensive documentation- **[Workflow Configuration](docs/WORKFLOW_CONFIG.md)** – Complete workflow.json configuration with UI component integration

│   ├── overview/               # Architecture, lifecycle, security- **[Persistence & Resume](docs/PERSISTENCE_AND_RESUME.md)** – MongoDB integration and AG2 groupchat state restoration

│   ├── runtime/                # Deep dives into subsystems- **[Workflow Analytics System](docs/WORKFLOW_ANALYTICS_SYSTEM.md)** – Real-time performance monitoring, cost analysis, and chat-level aggregation

│   ├── workflows/              # Workflow authoring guides- **[Token Architecture Mapping](docs/TOKEN_ARCHITECTURE_MAPPING.md)** – Billing architecture integration with analytics capabilities

│   ├── frontend/               # ChatUI integration- **[Event Architecture](docs/EVENT_ARCHITECTURE.md)** – Overview of unified event system, dispatcher, events, and handlers

│   ├── operations/             # Deployment and monitoring

│   └── reference/              # API specs and schemas### Development Guides (Legacy - See docs/workflows/ and docs/contributing/ for current versions)

│- **[Unified Tool and UI System](docs/UNIFIED_TOOL_AND_UI_SYSTEM.md)** – How backend tools and frontend components work together through workflow.json

├── 📁 logs/                    # Runtime logs- **[Workflow Development Framework](docs/WORKFLOW_DEVELOPMENT_FRAMEWORK.md)** – Plugin contracts, templates, and best practices for modular workflows

│   ├── logging_config.py       # Structured logging setup- **[Frontend-Backend Alignment](docs/FRONTEND_BACKEND_ALIGNMENT.md)** – Ensuring seamless data flow and UI rendering between systems

│   └── logs/                   # Log files (mozaiks.log)

│**Recommendation:** Start with the new [Documentation Portal](docs/README.md) for the most up-to-date information.

├── 📄 shared_app.py            # FastAPI app and HTTP endpoints

├── 📄 run_server.py            # Server entry point---

├── 📄 requirements.txt         # Python dependencies

└── 📄 .env                     # Environment configuration## 🚀 Quick Start

```

### Prerequisites

### Key Directories Explained- Python 3.9+ with pip

- Node.js 16+ with npm

| Directory | Purpose |- MongoDB (local or remote)

|-----------|---------|

| `core/` | Runtime engine—transport, events, orchestration, persistence, observability |### Backend Setup

| `workflows/` | Declarative workflow manifests—drop in a new folder to add a workflow |```bash

| `ChatUI/` | React frontend for interactive agent UIs (optional) |# Install Python dependencies

| `docs/` | Comprehensive documentation organized by use case |pip install -r requirements.txt

| `logs/` | Structured logging configuration and output files |

# Start the MozaiksAI backend

---python run_server.py

```

## 🔧 Core Systems

### Frontend Setup

### 1️⃣ Transport Layer```bash

# Navigate to React frontend

**Real-time bidirectional communication between runtime and frontend.**cd ChatUI



**Module:** `core/transport/simple_transport.py`# Install dependencies

npm install

**Responsibilities:**

- WebSocket connection lifecycle (connect, heartbeat, disconnect)# Start development server

- Message filtering based on `visual_agents` (hide internal coordinators)npm start

- Event envelope construction (AG2 `kind` → frontend `type`)```

- Pre-connection buffering (queue messages before WebSocket ready)

- Input request correlation (link user responses to orchestration callbacks)### Access MozaiksAI

Visit [http://localhost:3000](http://localhost:3000) to interact with your AI agents through the dynamic UI system.

**Special Logic:**

- **Agent Visibility Filtering**: Only agents in `orchestrator.json` → `visual_agents` array emit to UI### Configuration

- **Auto-Tool Deduplication**: Agents with `auto_tool_mode: true` suppress duplicate text messages- **Workflow Configuration:** Edit `workflows/{workflow_name}/workflow.json` to customize agent behavior and define components

- **UI_HIDDEN Triggers**: Context variable triggers marked `ui_hidden: true` set `_mozaiks_hide: true` for frontend suppression- **Transport Settings:** Configure WebSocket/SSE preferences in `core/transport/simple_transport.py`

- **Comprehensive Guides:** See the [Documentation Portal](docs/README.md) for detailed configuration references

**Example:**

```python---

from core.transport.simple_transport import SimpleTransport

## 🧩 Architecture Principles

transport = SimpleTransport(

    enterprise_id="acme_corp",MozaiksAI is built on a foundation of modularity, event-driven design, and declarative workflows:

    workflow_name="Generator",

    chat_id="chat_123"- **Modularity:** Each component is self-contained and replaceable without affecting the system

)- **Event-Driven:** UnifiedEventDispatcher centralizes all Business, Runtime, and UI Tool events

- **Protocol-Agnostic:** Transport layer abstracts WebSocket/SSE communication details  

# Send message to UI (if agent is visual)- **AG2 Integration:** Full support for Microsoft Autogen groupchat and IOStream patterns

await transport.send_to_ui({- **Manifest-Driven:** Tools, agents, and components registered via declarative JSON configuration

    "type": "agent_message",- **Multi-Tenant:** Enterprise-level isolation with deterministic cache seed propagation

    "content": "Here's your action plan...",

    "sender": "InterviewAgent",For detailed architecture documentation, see [Platform Architecture](docs/overview/architecture.md).

    "eventId": "evt_abc123"

})---

```

## 🤝 Contributing

**Documentation:** [Transport & Streaming](docs/runtime/transport_and_streaming.md)

We welcome contributions to MozaiksAI! Whether you're interested in:

---

- **Agent Development:** Creating new AI workflows and agent behaviors

### 2️⃣ Event Dispatcher- **UI Components:** Building dynamic React components for agent interaction  

- **Transport Enhancements:** Improving real-time communication protocols

**Centralized routing for all event types in the platform.**- **Documentation:** Helping others understand and use the platform

- **Bug Fixes:** Identifying and resolving issues

**Module:** `core/events/unified_event_dispatcher.py`

### Getting Involved

**Event Categories:**1. **Fork the repository** and create a feature branch

2. **Review the [Documentation Portal](docs/README.md)** for architecture guidelines and coding standards

1. **Business Events** (`BusinessLogEvent`)3. **Follow the manifest-driven patterns** for adding tools and components

   - Monitoring, logging, and audit trails4. **Test your changes** with both backend and frontend systems

   - Examples: `SERVER_STARTUP_COMPLETED`, `WORKFLOW_EXECUTION_STARTED`5. **Submit a pull request** with clear description of your contributions

   - Handler: `BusinessLogHandler` → structured logs

For detailed development guidelines, see the Contributing section in the [Documentation Portal](docs/README.md) (coming soon).

2. **UI Tool Events** (`UIToolEvent`)

   - Agent-triggered UI component rendering---

   - Examples: `agent_api_key_input`, `action_plan`, `file_download_center`

   - Handler: `UIToolHandler` → WebSocket transport## 🏆 Credits



3. **AG2 Runtime Events**Developed with ❤️ by **BlocUnited LLC** - Advancing the future of modular AI agent platforms.

   - Messages, tool calls, structured outputs from AG2 engine

   - Examples: `text`, `tool_call`, `structured_output_ready`Special thanks to the AutoGen (AG2) community for foundational patterns in agent orchestration and groupchat systems.

   - Flow: AG2 → `event_serialization.py` → Transport

---

**Example:**

```python## 📄 License

from core.events.unified_event_dispatcher import get_dispatcher

**EXCLUSIVE LICENSE AGREEMENT**

dispatcher = get_dispatcher()

This software is proprietary and confidential. All rights reserved by BlocUnited LLC.
# Emit business event (for logging)
await dispatcher.emit_business_event(
    log_event_type="WORKFLOW_EXECUTION_STARTED",
    description="Starting Generator workflow",
    context={"chat_id": "chat_123", "user_id": "user_456"}
)

# Emit UI tool event (for frontend)
await dispatcher.emit_ui_tool_event(
    ui_tool_id="action_plan",
    payload={"steps": [...], "theme": "success"},
    workflow_name="Generator",
    transport=transport
)
```

**Documentation:** [Event Pipeline](docs/runtime/event_pipeline.md)

---

### 3️⃣ Orchestration Engine

**Executes AG2 workflows with multi-agent patterns.**

**Module:** `core/workflow/orchestration_patterns.py`

**Responsibilities:**
- Load workflow configs from JSON manifests
- Configure AG2 agents (system messages, LLM configs, tool bindings)
- Execute orchestration patterns (Default, Auto, RoundRobin, Random)
- Handle termination conditions and max turns
- Stream events in real-time during execution
- Capture structured outputs when agents complete

**AG2 Patterns Supported:**

| Pattern | Description | Use Case |
|---------|-------------|----------|
| `Default` | Sequential agent execution with handoffs | Multi-step workflows with clear routing |
| `Auto` | Autonomous agent selection based on context | Dynamic routing (requires Speaker Selection) |
| `RoundRobin` | Fixed rotation through agent list | Equal participation workflows |
| `Random` | Random agent selection | Exploration or fuzzing |

**Example:**
```python
from core.workflow.orchestration_patterns import run_workflow_orchestration

result = await run_workflow_orchestration(
    enterprise_id="acme_corp",
    chat_id="chat_123",
    workflow_name="Generator",
    user_id="user_456",
    initial_message="Build me a CRM system",
    transport=transport,
    workflow_config=workflow_config,
    cache_seed=42
)

# result contains:
# - final_message: Last agent response
# - structured_output: Pydantic model if defined
# - execution_metadata: Tokens, costs, duration
```

**Documentation:** [Orchestration Patterns](docs/runtime/runtime_overview.md)

---

### 4️⃣ Persistence Manager

**MongoDB-backed state management with AG2 groupchat serialization.**

**Module:** `core/data/persistence_manager.py`

**Responsibilities:**
- Store chat sessions and message history
- Persist AG2 groupchat state for resume
- Track token usage and costs per chat/agent/workflow
- Manage enterprise themes and preferences
- Provide query APIs for analytics

**Collections:**

| Collection | Purpose |
|------------|---------|
| `chat_sessions` | Session metadata, messages, groupchat state |
| `workflow_stats_{enterprise}_{workflow}` | Aggregated metrics (tokens, cost, duration) |
| `enterprise_themes` | Per-tenant design system tokens |

**Example:**
```python
from core.data.persistence_manager import AG2PersistenceManager

pm = AG2PersistenceManager(
    enterprise_id="acme_corp",
    workflow_name="Generator"
)

# Save message
await pm.save_message(
    chat_id="chat_123",
    sender="InterviewAgent",
    content="What problem are you solving?",
    tokens={"prompt_tokens": 120, "completion_tokens": 25}
)

# Resume groupchat state
groupchat_state = await pm.load_groupchat_state("chat_123")
if groupchat_state:
    # Restore AG2 agents with previous context
    groupchat.resume(groupchat_state["messages"])
```

**Documentation:** [Persistence & Resume](docs/runtime/persistence_and_resume.md)

---

### 5️⃣ Observability Layer

**Comprehensive monitoring, metrics, and logging.**

**Modules:**
- `core/observability/performance_manager.py` – Prometheus metrics
- `core/observability/ag2_runtime_logger.py` – AG2 execution traces (SQLite)
- `core/observability/realtime_token_logger.py` – Live token tracking
- `logs/logging_config.py` – Structured logging setup

**Metrics Endpoints:**

| Endpoint | Description |
|----------|-------------|
| `/metrics/perf/aggregate` | Platform-wide totals (turns, tokens, cost) |
| `/metrics/perf/chats` | Per-chat performance snapshots |
| `/metrics/perf/chats/{chat_id}` | Single chat metrics |
| `/metrics/prometheus` | Prometheus exposition format |

**Example:**
```bash
# Get aggregate metrics
curl http://localhost:8000/metrics/perf/aggregate | jq

# Prometheus scrape
curl http://localhost:8000/metrics/prometheus
```

**Logging:**

- **Format**: JSON Lines (when `LOGS_AS_JSON=true`) or pretty text
- **Outputs**: `logs/logs/mozaiks.log`
- **Context**: File, line, function, correlation IDs

**Documentation:** [Observability](docs/runtime/observability.md)

---

## 🎯 Workflow System

### What is a Workflow?

A **workflow** is a self-contained multi-agent automation pipeline defined in JSON manifests. Each workflow specifies:

- **Agents**: System messages, LLM configs, auto-tool modes
- **Tools**: UI tools (frontend rendering) and agent tools (backend logic)
- **Context Variables**: Database queries, environment vars, derived computations
- **Orchestration**: Startup mode (Default/Auto/RR), max turns, visual agents
- **Structured Outputs**: Pydantic schemas for validated agent responses

### Workflow Anatomy

```
workflows/Generator/
├── agents.json              # Agent definitions
├── tools.json               # Tool registry
├── structured_outputs.json  # Pydantic schemas
├── context_variables.json   # Variable definitions
├── orchestrator.json        # Runtime config
└── tools/                   # Python implementations
    ├── action_plan.py       # UI_Tool: render artifact
    ├── request_api_key.py   # UI_Tool: secure input
    └── echo.py              # Agent_Tool: backend only
```

### Example: `agents.json`

```json
{
  "agents": {
    "InterviewAgent": {
      "system_message": "You are an expert conversational intake specialist...",
      "max_consecutive_auto_reply": 20,
      "auto_tool_mode": false,
      "structured_outputs_required": false
    },
    "ActionPlannerAgent": {
      "system_message": "You are a senior solutions architect...",
      "max_consecutive_auto_reply": 10,
      "auto_tool_mode": true,
      "structured_outputs_required": false
    }
  }
}
```

### Example: `tools.json`

```json
{
  "tools": {
    "action_plan": {
      "type": "UI_Tool",
      "description": "Display an interactive action plan artifact with steps, timeline, and resources",
      "auto_execute": true,
      "category": "visualization"
    },
    "request_api_key": {
      "type": "UI_Tool",
      "description": "Request secure API key input from user",
      "auto_execute": false,
      "category": "input"
    },
    "echo": {
      "type": "Agent_Tool",
      "description": "Echo back a message (backend only)",
      "auto_execute": false
    }
  }
}
```

### Example: `orchestrator.json`

```json
{
  "startup_mode": "Default",
  "max_turns": 50,
  "visual_agents": ["InterviewAgent", "ActionPlannerAgent"],
  "termination_conditions": {
    "context_variable_trigger": "interview_complete",
    "max_consecutive_auto_replies": 3
  }
}
```

### Creating a New Workflow

1. **Create directory**: `workflows/YourWorkflow/`
2. **Add manifests**: `agents.json`, `tools.json`, `orchestrator.json`, etc.
3. **Implement tools**: `tools/your_tool.py` with `async def execute(...)` function
4. **Restart runtime**: Workflow auto-discovered on next startup

**That's it!** No code changes to the runtime layer needed.

**Documentation:** [Workflow Authoring Guide](docs/workflows/workflow_authoring.md)

---

## 📊 Observability

### Real-Time Metrics

MozaiksAI provides comprehensive observability out of the box:

#### 1. Performance Metrics

**Endpoint:** `/metrics/perf/aggregate`

```json
{
  "total_chats": 142,
  "total_turns": 1853,
  "total_tool_calls": 476,
  "total_tokens": 892451,
  "total_cost_usd": 12.47,
  "avg_tokens_per_turn": 481.5,
  "avg_cost_per_chat_usd": 0.088
}
```

#### 2. Per-Chat Metrics

**Endpoint:** `/metrics/perf/chats/{chat_id}`

```json
{
  "chat_id": "chat_123",
  "enterprise_id": "acme_corp",
  "workflow_name": "Generator",
  "total_turns": 12,
  "total_tokens": 5832,
  "total_cost_usd": 0.42,
  "duration_seconds": 47.3,
  "agents": {
    "InterviewAgent": {
      "turns": 8,
      "tokens": 3421,
      "cost_usd": 0.28
    },
    "ActionPlannerAgent": {
      "turns": 4,
      "tokens": 2411,
      "cost_usd": 0.14
    }
  }
}
```

#### 3. Prometheus Metrics

**Endpoint:** `/metrics/prometheus`

```
# HELP mozaiks_total_chats Total number of chat sessions
# TYPE mozaiks_total_chats gauge
mozaiks_total_chats 142.0

# HELP mozaiks_total_tokens Total tokens consumed
# TYPE mozaiks_total_tokens gauge
mozaiks_total_tokens 892451.0

# HELP mozaiks_total_cost_usd Total cost in USD
# TYPE mozaiks_total_cost_usd gauge
mozaiks_total_cost_usd 12.47
```

### Structured Logging

**Format Toggle:** Set `LOGS_AS_JSON=true` for JSON Lines or `false` for pretty text.

**Example JSON Log:**
```json
{
  "timestamp": "2025-10-02T14:32:15.123Z",
  "level": "INFO",
  "logger": "core.workflow.orchestration_patterns",
  "message": "Workflow execution started",
  "context": {
    "enterprise_id": "acme_corp",
    "chat_id": "chat_123",
    "workflow_name": "Generator",
    "correlation_id": "cor_abc123"
  },
  "file": "orchestration_patterns.py",
  "line": 145,
  "function": "run_workflow_orchestration"
}
```

**Example Pretty Log:**
```
2025-10-02 14:32:15 | INFO     | 🚀 Workflow execution started
  enterprise_id: acme_corp
  chat_id: chat_123
  workflow_name: Generator
  📁 core/workflow/orchestration_patterns.py:145 (run_workflow_orchestration)
```

### AG2 Runtime Logger

**SQLite-backed execution traces** for deep debugging.

- Captures all AG2 LLM requests/responses
- Stores start/end timestamps, token counts, costs
- Queryable via SQL for custom analytics

**Documentation:** [Observability](docs/runtime/observability.md)

---

## 🔐 Multi-Tenancy

### Enterprise Isolation

Every workflow execution is scoped to an `enterprise_id` ensuring complete data isolation:

- **MongoDB Collections**: Separate collections per enterprise (e.g., `workflow_stats_acme_corp_Generator`)
- **Cache Seeds**: Deterministic per-chat seeds prevent component state bleed
- **Context Boundaries**: Variables never leak across tenants
- **Secret Storage**: Encrypted credential storage per enterprise

### Cache Seed Propagation

**Problem:** Multiple chats for the same workflow might share UI component instances, causing state bleed.

**Solution:** Deterministic cache seed per chat.

```python
# Backend generates seed from enterprise_id + chat_id
cache_seed = int.from_bytes(
    hashlib.sha256(f"{enterprise_id}:{chat_id}".encode()).digest()[:4],
    byteorder="big"
)

# Frontend stores in localStorage
localStorage.setItem(
    `mozaiks.current_chat_id.cache_seed.${chatId}`,
    cache_seed
)

# UI components incorporate seed in cache keys
componentCacheKey = `${chatId}:${cacheSeed}:${workflow}:${component}`
```

**Result:** Each chat has isolated UI component state, even for the same workflow.

**Documentation:** [Multi-Tenancy & Security](docs/overview/tenancy_and_security.md)

---

## 📚 Documentation

**Comprehensive documentation organized by use case:**

👉 **[Start Here: Documentation Portal](docs/README.md)** 👈

### Documentation Tracks

| Track | Purpose | Key Documents |
|-------|---------|---------------|
| **Overview** | Platform fundamentals | [Architecture](docs/overview/architecture.md), [Lifecycle](docs/overview/lifecycle.md), [Security](docs/overview/tenancy_and_security.md) |
| **Runtime** | Backend deep dives | [Event Pipeline](docs/runtime/event_pipeline.md), [Transport](docs/runtime/transport_and_streaming.md), [Persistence](docs/runtime/persistence_and_resume.md), [Observability](docs/runtime/observability.md) |
| **Workflows** | Authoring guides | [Workflow Authoring](docs/workflows/workflow_authoring.md), [Tool Manifests](docs/workflows/tool_manifest.md), [Context Variables](docs/workflows/context_variables.md) |
| **Frontend** | React ChatUI | [Unified UI Tools & Design](docs/frontend/unified_ui_tools_and_design.md), [ChatUI Architecture](docs/frontend/chatui_architecture.md) |
| **Operations** | Deployment & monitoring | [Deployment](docs/operations/deployment.md), [Monitoring](docs/operations/monitoring.md), [Troubleshooting](docs/operations/troubleshooting.md) |
| **Reference** | API specs & schemas | [API Reference](docs/reference/api_reference.md), [Database Schema](docs/reference/database_schema.md), [Environment Variables](docs/reference/environment_variables.md) |

### Quick Reference

**Common Tasks:**

- [Create a new workflow](docs/workflows/workflow_authoring.md)
- [Add a UI tool](docs/workflows/ui_tool_pipeline.md)
- [Configure orchestration patterns](docs/runtime/runtime_overview.md)
- [Set up persistence](docs/runtime/persistence_and_resume.md)
- [Monitor performance](docs/runtime/observability.md)
- [Deploy to production](docs/operations/deployment.md)

---

## 🎯 Workflow Examples

### Example 1: Simple Echo Workflow

**Scenario:** Single agent that echoes user input.

**`workflows/Echo/agents.json`:**
```json
{
  "agents": {
    "EchoAgent": {
      "system_message": "You are a helpful echo agent. Repeat what the user says in a friendly way.",
      "max_consecutive_auto_reply": 10,
      "auto_tool_mode": false
    }
  }
}
```

**`workflows/Echo/tools.json`:**
```json
{
  "tools": {}
}
```

**`workflows/Echo/orchestrator.json`:**
```json
{
  "startup_mode": "Default",
  "max_turns": 20,
  "visual_agents": ["EchoAgent"]
}
```

**Run:**
```bash
# Start chat
curl -X POST http://localhost:8000/api/chats/demo/Echo/start \
  -H "Content-Type: application/json" \
  -d '{"user_id": "user_123"}'

# Send message
# Connect to WebSocket and send:
{"action": "user_message", "content": "Hello world!"}

# Agent responds:
{"type": "agent_message", "sender": "EchoAgent", "content": "Hello world! 👋"}
```

---

### Example 2: Multi-Agent Interview Workflow

**Scenario:** Two agents coordinate to interview user and generate action plan.

**Agents:**
- `InterviewAgent`: Asks questions to understand requirements
- `PlannerAgent`: Generates action plan artifact when interview is complete

**Key Features:**
- Context variable trigger (`interview_complete`) for handoff
- UI tool (`action_plan`) renders interactive artifact
- Auto-tool mode for PlannerAgent (executes tools without asking)

**See:** `workflows/Generator/` for full implementation

**Documentation:** [Workflow Authoring Guide](docs/workflows/workflow_authoring.md)

---

## ⚡ Development Guide

### Prerequisites

- Python 3.9+ with pip
- MongoDB (local or Atlas)
- Node.js 16+ (for ChatUI)
- Git

### Setup Development Environment

```bash
# Clone repo
git clone https://github.com/BlocUnited-LLC/MozaiksAI.git
cd MozaiksAI

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your settings
```

### Running in Development Mode

```bash
# Terminal 1: Backend with hot-reload
uvicorn shared_app:app --reload --host 0.0.0.0 --port 8000

# Terminal 2: ChatUI dev server
cd ChatUI
npm start

# Terminal 3: MongoDB (if local)
mongod --dbpath ./data/db
```

### Development Workflow

1. **Create feature branch**: `git checkout -b feature/your-feature`
2. **Make changes**: Edit code, manifests, or docs
3. **Test locally**: Verify with sample workflows
4. **Run tests**: `pytest tests/` (when available)
5. **Commit changes**: `git commit -m "feat: your feature"`
6. **Push and PR**: `git push origin feature/your-feature`

### Logging Tips

**Toggle log format:**
```bash
# JSON Lines (for parsing)
export LOGS_AS_JSON=true
python run_server.py

# Pretty text (for development)
export LOGS_AS_JSON=false
python run_server.py
```

**Custom log directory:**
```bash
export LOGS_BASE_DIR=/custom/path/logs
python run_server.py
```

**Tail logs in real-time:**
```bash
# PowerShell
Get-Content logs/logs/mozaiks.log -Wait -Tail 50

# Bash
tail -f logs/logs/mozaiks.log
```

### Adding a New Workflow

1. Create directory: `workflows/YourWorkflow/`
2. Add manifests:
   - `agents.json` – Agent definitions
   - `tools.json` – Tool registry
   - `structured_outputs.json` – Pydantic schemas
   - `context_variables.json` – Variable definitions
   - `orchestrator.json` – Runtime config
3. Create `tools/` directory with Python implementations
4. Restart runtime (auto-discovery)
5. Test via HTTP/WebSocket

**See:** [Workflow Authoring Guide](docs/workflows/workflow_authoring.md)

---

## 🐳 Docker Deployment

### Quick Start with Docker Compose

```bash
# From repo root
docker compose -f infra/compose/docker-compose.yml up --build
```

**Dockerfile:** `infra/docker/Dockerfile`  
**Compose File:** `infra/compose/docker-compose.yml`

### Docker Compose Configuration

```yaml
services:
  mozaiksai:
    build:
      context: .
      dockerfile: infra/docker/Dockerfile
    ports:
      - "8000:8000"
    environment:
      - MONGODB_URI=mongodb://mongo:27017
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - LOGS_AS_JSON=true
    volumes:
      - ./logs/logs:/app/logs/logs
    depends_on:
      - mongo

  mongo:
    image: mongo:7
    ports:
      - "27017:27017"
    volumes:
      - mongo_data:/data/db

volumes:
  mongo_data:
```

### Production Deployment

**Recommendations:**
- Use MongoDB Atlas for managed database
- Set `LOGS_AS_JSON=true` for structured logging
- Configure `LLM_DEFAULT_CACHE_SEED` for reproducibility
- Enable HTTPS with reverse proxy (nginx, Caddy)
- Set up monitoring with Prometheus + Grafana

**See:** [Deployment Guide](docs/operations/deployment.md)

---

## 🤝 Contributing

We welcome contributions to MozaiksAI! Whether you're interested in:

- 🔧 **Runtime Enhancements**: Improving transport, persistence, or orchestration
- 🎯 **Workflow Development**: Creating example workflows or patterns
- 📚 **Documentation**: Improving guides, examples, or API references
- 🐛 **Bug Fixes**: Identifying and resolving issues
- ✨ **Feature Requests**: Proposing new capabilities

### Getting Involved

1. **Fork the repository** and create a feature branch
2. **Review the documentation** to understand the architecture
3. **Follow declarative patterns** for workflows and tools
4. **Test your changes** with both backend and frontend
5. **Submit a pull request** with clear description

### Development Guidelines

- **Modular Design**: Keep subsystems decoupled and independently replaceable
- **Declarative First**: Prefer JSON manifests over code changes
- **Event-Driven**: All interactions flow through `UnifiedEventDispatcher`
- **Multi-Tenant Safe**: Ensure enterprise isolation and no data leakage
- **AG2-Native**: Extend AG2 patterns without forking vendor code
- **Observable**: Add structured logging and metrics for new features
- **Documented**: Update relevant docs in `docs/` directory

**See:** [Contributing Guide](docs/CONTRIBUTING.md) *(coming soon)*

---

## 📄 License

**Proprietary and Confidential**

This software is proprietary to **BlocUnited LLC**. All rights reserved.

For licensing inquiries, contact: [email protected]

---

## 🏆 Credits

**Developed with ❤️ by [BlocUnited LLC](https://blocunited.com)**

Special thanks to the [Microsoft AG2 (Autogen)](https://microsoft.github.io/autogen/) team for foundational patterns in agent orchestration.

---

<div align="center">

**[Documentation](docs/README.md)** • **[Quick Start](#-quick-start)** • **[Examples](#-workflow-examples)** • **[GitHub](https://github.com/BlocUnited-LLC/MozaiksAI)**

Made with 🎯 for the future of AI orchestration

</div>
