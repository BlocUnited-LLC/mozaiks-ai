# 🎯 MozaiksAI Runtime

<div align="center">

![MozaiksAI Logo](ChatUI/public/mozaik_logo.svg)

**Enterprise-Grade AG2 Orchestration Engine**  
*Event-Driven • Declarative • Multi-Tenant • Production-Ready*

[![AG2 Framework](https://img.shields.io/badge/AG2-Autogen-green?style=flat&logo=microsoft)](https://microsoft.github.io/autogen/)
[![Python](https://img.shields.io/badge/Python-3.9+-blue?style=flat&logo=python)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-Latest-009688?style=flat&logo=fastapi)](https://fastapi.tiangolo.com/)
[![MongoDB](https://img.shields.io/badge/MongoDB-Persistence-47A248?style=flat&logo=mongodb)](https://www.mongodb.com/)

**Production-grade runtime for multi-agent AI workflows built on Microsoft's AG2 framework.**

[Quick Start](#-quick-start) • [Documentation](#-documentation) • [Architecture](#-architecture) • [Features](#-features)

</div>

---

## 🎯 What is MozaiksAI?

**MozaiksAI Runtime** is a production-ready orchestration engine that transforms AG2 (Microsoft Autogen) into an enterprise-grade platform with:

- ✅ **Event-Driven Architecture** → Every action flows through unified event pipeline
- ✅ **Real-Time WebSocket Transport** → Live streaming to React frontends
- ✅ **Persistent State Management** → Resume conversations exactly where they left off
- ✅ **Multi-Tenant Isolation** → Enterprise-scoped data and execution contexts
- ✅ **Dynamic UI Integration** → Agents can invoke React components during workflows
- ✅ **Declarative Workflows** → JSON manifests, no code changes needed
- ✅ **Comprehensive Observability** → Built-in metrics, logging, and token tracking

**MozaiksAI = AG2 + Production Infrastructure + Event-Driven Core**

---

## ✨ Features

### 🎨 Declarative Workflow System
Define complete multi-agent workflows in JSON—drop a new folder in `workflows/` and the runtime discovers it automatically.

```json
{
  "agents": {
    "InterviewAgent": {
      "system_message": "You are an expert intake specialist...",
      "auto_tool_mode": false
    }
  },
  "tools": {
    "action_plan": {
      "type": "UI_Tool",
      "description": "Display interactive action plan artifact"
    }
  },
  "orchestration": {
    "pattern": "Default",
    "max_turns": 50,
    "visual_agents": ["InterviewAgent"]
  }
}
```

### ⚡ Real-Time Event Streaming
Every agent message, tool call, and state change flows through WebSocket to your frontend.

- **Dual Protocol Support** → WebSocket with SSE fallback
- **Message Filtering** → Show only relevant agents to end users
- **Event Correlation** → Track request/response flows with unique IDs
- **Bi-Directional** → Frontend can trigger backend handlers

### 💾 Persistent State Management
Never lose context—every workflow execution is fully persisted and resumable.

- **AG2 State Serialization** → Complete groupchat state to MongoDB
- **Message History** → Full chat transcripts with metadata
- **Session Resume** → Pick up any conversation exactly where it left off
- **Token Tracking** → Real-time cost metrics per chat/agent/workflow

### 🔐 Multi-Tenant by Design
Enterprise-grade isolation and security built from the ground up.

- **Enterprise Isolation** → Separate MongoDB collections per `enterprise_id`
- **Cache Seed Propagation** → Deterministic per-chat seeds prevent state bleed
- **Secret Management** → Secure credential collection and storage
- **Context Boundaries** → No data leakage across tenants

### 📊 Enterprise Observability
Comprehensive monitoring, metrics, and analytics out of the box.

- **Performance Metrics** → `/metrics/perf/*` endpoints for monitoring
- **Structured Logging** → JSON Lines or pretty text format
- **AG2 Runtime Logger** → SQLite-backed execution traces
- **Real-Time Analytics** → Live token usage and cost tracking

### 🎯 Dynamic UI Integration
Agents can invoke React components dynamically during workflow execution.

- **UI Tools** → Agents call `display_action_plan()` → frontend renders artifact
- **Auto-Tool Mode** → Execute tools without asking permission
- **Context Sync** → Shared state between agents and UI components
- **Theme System** → Per-enterprise design system customization

---

## 🏗️ Architecture

MozaiksAI follows a **clean, modular architecture** where every component has a single responsibility.

```
┌─────────────────────────────────────────────────────────┐
│              ChatUI (React Frontend)                    │
│  • WebSocket Client                                     │
│  • Dynamic Component Renderer                           │
│  • Artifact Design System                               │
└──────────────────┬──────────────────────────────────────┘
                   │ WebSocket/HTTP
┌──────────────────▼──────────────────────────────────────┐
│         MozaiksAI Runtime (FastAPI + AG2)               │
│                                                         │
│  ┌────────────────────────────────────────────────┐     │
│  │  Transport Layer (WebSocket)                   │     │
│  │  • Connection lifecycle                        │     │
│  │  • Message filtering (visual_agents)           │     │
│  └────────────────────────────────────────────────┘     │
│  ┌────────────────────────────────────────────────┐     │
│  │  Unified Event Dispatcher                      │     │
│  │  • Business Events → Logging                   │     │
│  │  • UI Tool Events → WebSocket                  │     │
│  │  • AG2 Events → Serialization                  │     │
│  └────────────────────────────────────────────────┘     │
│  ┌────────────────────────────────────────────────┐     │
│  │  Orchestration Engine                          │     │
│  │  • Workflow discovery & loading                │     │
│  │  • AG2 pattern execution                       │     │
│  │  • Tool registry & binding                     │     │
│  └────────────────────────────────────────────────┘     │
│  ┌────────────────────────────────────────────────┐     │
│  │  Persistence Layer (MongoDB)                   │     │
│  │  • Chat sessions & message history             │     │
│  │  • Groupchat state serialization               │     │
│  │  • Token & cost tracking                       │     │
│  └────────────────────────────────────────────────┘     │
└──────────────────┬──────────────────────────────────────┘
                   │ MongoDB Protocol
┌──────────────────▼──────────────────────────────────────┐
│              MongoDB (Atlas / Local)                    │
│  • chat_sessions                                        │
│  • workflow_stats_{enterprise}_{workflow}               │
│  • enterprise_themes                                    │
└─────────────────────────────────────────────────────────┘
```

### 🗂️ Project Structure (New & Improved!)

```
MozaiksAI/
├── 📁 core/                        # Runtime engine (newly organized!)
│   ├── core_config.py              # Global configuration
│   │
│   ├── 📁 data/                    # Data & persistence
│   │   ├── models.py               # Pydantic data models
│   │   ├── persistence/            # ✨ NEW organized structure
│   │   │   ├── persistence_manager.py  # MongoDB operations
│   │   │   └── db_manager.py           # Database utilities
│   │   └── themes/                 # ✨ NEW theme system
│   │       ├── theme_manager.py        # Theme management
│   │       └── theme_validation.py     # Theme validation
│   │
│   ├── 📁 events/                  # Event system
│   │   ├── unified_event_dispatcher.py  # Central event router
│   │   ├── event_serialization.py       # AG2 → JSON conversion
│   │   ├── event_payload_builder.py     # UI event construction
│   │   └── auto_tool_handler.py         # UI tool execution
│   │
│   ├── 📁 observability/           # Monitoring & logging
│   │   ├── performance_manager.py       # Metrics collection
│   │   ├── ag2_runtime_logger.py        # AG2 execution traces
│   │   └── realtime_token_logger.py     # Live token tracking
│   │
│   ├── 📁 transport/               # WebSocket layer
│   │   ├── simple_transport.py          # Connection management
│   │   ├── websocket.py                 # WebSocket handlers
│   │   └── resume_groupchat.py          # Session resume
│   │
│   └── 📁 workflow/                # Workflow orchestration (reorganized!)
│       ├── workflow_manager.py          # Workflow discovery
│       ├── orchestration_patterns.py    # Main execution engine
│       │
│       ├── agents/                 # ✨ NEW agent management
│       │   ├── factory.py              # Agent creation
│       │   ├── tools.py                # Tool registration
│       │   └── handoffs.py             # Agent handoffs
│       │
│       ├── context/                # ✨ NEW context management
│       │   ├── adapter.py              # Context adapter
│       │   ├── schema.py               # Context schema
│       │   ├── variables.py            # Context variables
│       │   └── derived.py              # Derived context
│       │
│       ├── execution/              # ✨ NEW runtime execution
│       │   ├── patterns.py             # AG2 pattern factory
│       │   ├── lifecycle.py            # Lifecycle hooks
│       │   ├── termination.py          # Termination handling
│       │   └── hooks.py                # Hook loading
│       │
│       ├── messages/               # ✨ NEW message handling
│       │   └── utils.py                # Message normalization
│       │
│       ├── outputs/                # ✨ NEW output handling
│       │   ├── structured.py           # Structured outputs
│       │   └── ui_tools.py             # UI tool integration
│       │
│       └── validation/             # ✨ NEW validation utilities
│           ├── llm_config.py           # LLM configuration
│           └── tools.py                # Tool validation
│
├── 📁 workflows/                   # Declarative workflows
│   └── Generator/                  # Example workflow
│       ├── agents.json             # Agent definitions
│       ├── tools.json              # Tool registry
│       ├── structured_outputs.json # Pydantic schemas
│       ├── context_variables.json  # Variable definitions
│       ├── orchestrator.json       # Runtime config
│       └── tools/                  # Python implementations
│
├── 📁 ChatUI/                      # React frontend (optional)
│   ├── src/
│   │   ├── core/                   # WorkflowUIRouter, EventDispatcher
│   │   ├── workflows/              # Per-workflow UI components
│   │   └── components/             # Shared UI components
│   └── public/
│
├── 📁 docs/                        # Comprehensive documentation
│   ├── overview/                   # Architecture, lifecycle, security
│   ├── runtime/                    # Deep dives into subsystems
│   ├── workflows/                  # Workflow authoring guides
│   ├── frontend/                   # ChatUI integration
│   ├── operations/                 # Deployment and monitoring
│   └── reference/                  # API specs and schemas
│
├── 📁 logs/                        # Runtime logs
│   ├── logging_config.py           # Structured logging setup
│   └── logs/                       # Log files (mozaiks.log)
│
├── 📄 shared_app.py                # FastAPI app entry point
├── 📄 run_server.py                # Server launcher
├── 📄 requirements.txt             # Python dependencies
└── 📄 .env                         # Environment configuration
```
---

## 🚀 Quick Start

### Prerequisites

- **Python 3.9+** with pip
- **MongoDB** (local or Atlas cluster)
- **Node.js 16+** (for ChatUI, optional)
- **OpenAI API Key** or compatible LLM provider

### Installation

```bash
# Clone the repository
git clone https://github.com/BlocUnited-LLC/MozaiksAI.git
cd MozaiksAI

# Install Python dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your MongoDB URI, OpenAI key, etc.
```

### Configuration

Create `.env` file:

```env
# MongoDB
MONGODB_URI=mongodb://localhost:27017
MONGODB_DB_NAME=mozaiksai

# LLM Configuration
OPENAI_API_KEY=sk-...
LLM_DEFAULT_CACHE_SEED=42

# Logging
LOGS_AS_JSON=false
LOGS_BASE_DIR=logs/logs

# Runtime Options
CONTEXT_AWARE=true
CLEAR_TOOL_CACHE_ON_START=true
```

### Run the Runtime

**Recommended: Start with a clean slate**

```powershell
# 1️⃣ Complete clean (clears MongoDB, logs, caches)
.\scripts\cleanse.ps1 -Full

# 2️⃣ Start fresh (no -FreshRun needed since cleanse already did everything)
.\start-dev.ps1 -Mode docker -TailInPlace -StartFrontend
```

**Alternative: Direct Python execution**

```bash
# Start the FastAPI backend directly
python run_server.py
```

The runtime will:
- 🔍 Discover workflows in `workflows/` directory
- 🔧 Load tool manifests and register callables
- 🚀 Start FastAPI server on `http://localhost:8000`
- 📡 Enable WebSocket at `ws://localhost:8000/ws/{workflow}/{enterprise}/{chat}/{user}`

### Run with ChatUI (Optional)

```bash
# In a separate terminal
cd ChatUI
npm install
npm start
```

Visit `http://localhost:3000` to interact with workflows through the React interface.

### Docker Deployment

```bash
# From repo root
docker compose -f infra/compose/docker-compose.yml up --build
```

---

## 📊 API Endpoints

### Health & Metrics

| Endpoint | Description |
|----------|-------------|
| `GET /api/health` | Health check with MongoDB ping |
| `GET /health/active-runs` | Active workflow runs summary |
| `GET /metrics/perf/aggregate` | Platform-wide performance metrics |
| `GET /metrics/perf/chats` | Per-chat performance snapshots |
| `GET /metrics/perf/chats/{chat_id}` | Single chat metrics |

### Chat Management

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/chats/{enterprise}/{workflow}/start` | POST | Start new chat session |
| `/api/chats/{enterprise}/{workflow}` | GET | List recent chats |
| `/api/chats/exists/{enterprise}/{workflow}/{chat}` | GET | Check if chat exists |
| `/api/chats/meta/{enterprise}/{workflow}/{chat}` | GET | Get chat metadata |
| `/ws/{workflow}/{enterprise}/{chat}/{user}` | WebSocket | Real-time connection |

### Workflow Information

| Endpoint | Description |
|----------|-------------|
| `GET /api/workflows` | Get all workflow configurations |
| `GET /api/workflows/{workflow}/transport` | Get transport info |
| `GET /api/workflows/{workflow}/tools` | Get UI tools manifest |

---

## 🎯 Creating a Workflow

### 1. Create Workflow Directory

```bash
mkdir -p workflows/MyWorkflow/tools
```

### 2. Define Agents (`agents.json`)

```json
{
  "agents": {
    "HelperAgent": {
      "system_message": "You are a helpful assistant that...",
      "max_consecutive_auto_reply": 20,
      "auto_tool_mode": false,
      "structured_outputs_required": false
    }
  }
}
```

### 3. Register Tools (`tools.json`)

```json
{
  "tools": {
    "my_ui_tool": {
      "type": "UI_Tool",
      "description": "Display interactive component",
      "auto_execute": true,
      "category": "visualization"
    },
    "my_backend_tool": {
      "type": "Agent_Tool",
      "description": "Backend processing only",
      "auto_execute": false
    }
  }
}
```

### 4. Configure Orchestration (`orchestrator.json`)

```json
{
  "startup_mode": "Default",
  "max_turns": 50,
  "visual_agents": ["HelperAgent"],
  "termination_conditions": {
    "max_consecutive_auto_replies": 3
  }
}
```

### 5. Implement Tools (`tools/my_tool.py`)

```python
async def execute(
    chat_id: str,
    user_id: str,
    enterprise_id: str,
    **kwargs
):
    """Tool implementation."""
    return {
        "status": "success",
        "data": {"message": "Tool executed!"}
    }
```

### 6. Restart Runtime

```bash
python run_server.py
```

**That's it!** Your workflow is automatically discovered and ready to use.

---

## 📚 Documentation

Comprehensive documentation organized by use case:

👉 **[Documentation Portal](docs/README.md)** 👈

### Quick Links

| Topic | Document |
|-------|----------|
| **Architecture** | [Platform Architecture](docs/overview/architecture.md) |
| **Request Lifecycle** | [End-to-End Flow](docs/overview/lifecycle.md) |
| **Multi-Tenancy** | [Security & Isolation](docs/overview/tenancy_and_security.md) |
| **Event System** | [Event Pipeline](docs/runtime/event_pipeline.md) |
| **Transport** | [WebSocket](docs/runtime/transport_and_streaming.md) |
| **Persistence** | [MongoDB & Resume](docs/runtime/persistence_and_resume.md) |
| **Observability** | [Metrics & Logging](docs/runtime/observability.md) |
| **Workflow Authoring** | [Creating Workflows](docs/workflows/workflow_authoring.md) |
| **UI Integration** | [Unified UI Tools](docs/frontend/unified_ui_tools_and_design.md) |
| **Deployment** | [Docker & Production](docs/operations/deployment.md) |

---

## 🔧 Development

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

### Logging

**Toggle log format:**
```bash
# JSON Lines (for parsing)
export LOGS_AS_JSON=true
python run_server.py

# Pretty text (for development)
export LOGS_AS_JSON=false
python run_server.py
```

**Tail logs:**
```powershell
# PowerShell
Get-Content logs/logs/mozaiks.log -Wait -Tail 50
```

---

## 🤝 Contributing

We welcome contributions! Whether you're interested in:

- 🔧 **Runtime Enhancements** → Improving core systems
- 🎯 **Workflow Development** → Creating example workflows
- 📚 **Documentation** → Improving guides and examples
- 🐛 **Bug Fixes** → Identifying and resolving issues

### Development Guidelines

1. **Modular Design** → Keep subsystems decoupled
2. **Declarative First** → Prefer JSON manifests over code
3. **Event-Driven** → All interactions through `UnifiedEventDispatcher`
4. **Multi-Tenant Safe** → Ensure enterprise isolation
5. **AG2-Native** → Extend AG2 without forking

---

## 📄 License

**Proprietary and Confidential**  
© 2025 BlocUnited LLC. All rights reserved.

For licensing inquiries: [email protected]

---

## 🏆 Credits

**Developed with ❤️ by [BlocUnited LLC](https://blocunited.com)**

Special thanks to the [Microsoft AG2 (Autogen)](https://microsoft.github.io/autogen/) team for foundational agent orchestration patterns.

---

<div align="center">

**[Documentation](docs/README.md)** • **[Quick Start](#-quick-start)** • **[Architecture](#-architecture)** • **[GitHub](https://github.com/BlocUnited-LLC/MozaiksAI)**

Made with 🎯 for the future of AI orchestration

</div>
