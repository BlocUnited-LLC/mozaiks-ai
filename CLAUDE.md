# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Scope for Claude Code
---------------------
Be aware that this repository is part of a larger Mozaiks platform. For clarity, there are two distinct layers involved:

There are two layers at play:

1. The Mozaiks build process (which uses the Generator workflow + its own MozaiksAI instance) to create any agentic functionality for the app the user wishes to create.

2. The user's own app runtime (which ends up with its own MozaiksAI instance, running workflows defined in JSON and .py/.js stubs created by the generator during the mozaiks build process)

Important instruction for Claude Code: focus your code analysis, changes, and refactors on the MozaiksAI runtime code within this repository and the Generator workflow (the build-time components that output JSON and .py/.js stubs). Do NOT modify or assume responsibility for other platform layers described in `PLATFORM_ARCHITECTURE_FINAL.md` unless explicitly requested.

Refer to `PLATFORM_ARCHITECTURE_FINAL.md` for the full platform context if needed, but keep proposed code changes scoped to the runtime and generator pieces.

## Development Commands

### Backend Development
```bash
# Install Python dependencies
pip install -r requirements.txt

# Run the backend server
python run_server.py

# Run with Docker (PowerShell on Windows)
./start-app.ps1
# Skip build step with -NoBuild flag
./start-app.ps1 -NoBuild
```

### Frontend Development
```bash
# Navigate to React frontend
cd ChatUI

# Install dependencies  
npm install

# Start development server
npm start

# Build for production
npm run build

# Run tests
npm test
```

### Testing
```bash
# Run single test file
python -m pytest tests/test_transport_core.py -v

# Run all tests  
python -m pytest tests/ -v

# Code quality check
flake8

# Demo script for realtime billing
python demo_realtime_billing.py
```

## Architecture Overview

MozaiksAI is an event-driven AI workflow orchestration platform built on AG2 (the opensource version of Microsoft's Autogen). It provides a robust framework for creating production-grade, multi-agent systems with real-time persistence, seamless chat resumption, and comprehensive observability, via natural language. Not only does it support complex agent workflows, but it also enables the development tools for dynamic UI interactions. The 'core' provides a flexible runtime for executing AG2 workflows defined in JSON and .py/.js stubs, while the 'ChatUI' frontend offers a rich user experience with dynamic components that agents can control.

The architecture follows a "strategically lean" philosophy with these key components:

### Core Architecture Pillars

1. **Event-Driven Core**: All system interactions flow through a unified event bus (`core/events/unified_event_dispatcher.py`) with three event categories:
   - Business Events: Application lifecycle and monitoring
   - Runtime Events: AG2 agent workflow execution  
   - UI Tool Events: Dynamic UI interactions

2. **Transport Layer**: `core/transport/simple_transport.py` handles real-time communication between backend and frontend via WebSocket/SSE with automatic fallback and message filtering.

3. **Workflow Orchestration**: `core/workflow/orchestration_patterns.py` serves as the single entry point for all AG2 workflow execution, handling streaming, persistence, and telemetry.

Hot-swappable workflows (WebSocket runtime)
------------------------------------------
Workflows are hot-swappable and discovered/loaded at runtime rather than being statically compiled into the server. The FastAPI app in `shared_app.py` exposes a WebSocket endpoint that is the primary runtime ingress for workflows:

`/ws/{workflow_name}/{enterprise_id}/{chat_id}/{user_id}`

At runtime the server will load or create a workflow handler on demand (see `core/workflow/init_registry.py` and `core/workflow/orchestration_patterns.py`). This means:
- The Generator outputs JSON and optional `.py/.js` stubs at build-time.
- When a client connects over the WebSocket, the MozaiksAI runtime can load that workflow's JSON/stubs and start the workflow dynamically.
- Different workflows can be swapped or routed by changing the `workflow_name` path segment or the transport configuration — enabling hot swaps without restarting the server.

Refer to `shared_app.py` for the WebSocket handler and auto-start behavior, and `init_registry.py` for how dynamic handlers are created and cached.

4. **Persistence**: `core/data/persistence_manager.py` provides real-time MongoDB persistence for chat sessions, enabling seamless resumption.

### Key Directories

- **`core/`**: Backend platform systems
  - `transport/`: Communication layer with WebSocket/SSE support
  - `workflow/`: Workflow execution, tool registry, agent management to interface with AG2 Groupchat.
  - `data/`: MongoDB persistence and chat session management
  - `events/`: Unified event dispatcher and handlers
  - `observability/`: Performance monitoring and OpenTelemetry integration

- **`workflows/`**: Modular workflow definitions (JSON-based configuration and .py/.js stubs)
  - Each workflow has agents, tools, handoffs, structured outputs
  - Example: `workflows/Generator/` contains complete workflow definition

- **`ChatUI/`**: React frontend application
  - `src/components/`: Dynamic UI components for agent/user interaction
  - `src/transport/`: Frontend transport integration
  - `src/workflows/`: Workflow-specific UI components

### Configuration System

- **Workflow Configuration**: Each workflow defines its behavior in JSON files (agents.json, tools.json, etc.) and can include .py/.js stubs for custom logic (workflows\{workflow}\tools)
- **Environment Variables**: `.env` file for MongoDB connections, API keys, logging format
- **Logging**: Controlled by `LOGS_AS_JSON` environment variable (JSON vs pretty text format)

### Integration Patterns

1. **Agent-UI Integration**: Agents can dynamically call React components and interact with the user via these components through the transport layer
2. **Tool Registry**: JSON-based tool manifests enable dynamic agent capability extension via AG2 tool logic
3. **Event Filtering**: Smart message filtering ensures users only see relevant agent communications
4. **Resume Capability**: Full AG2 groupchat state persistence across server restarts

### Performance & Observability

- **Real-time Metrics**: `core/observability/performance_manager.py` tracks token usage, costs, and agent performance
- **OpenTelemetry**: Optional telemetry export via `OPENLIT_ENABLED=true`
- **Structured Logging**: Dual-format logging (JSON/pretty) with workflow and chat separation

### Development Guidelines

- Follow the existing JSON-based workflow configuration patterns and .py/.js stubs for custom logic
- Use the unified event dispatcher for all internal events
- Leverage the transport layer for real-time UI updates
- Test with both local development and Docker deployment scenarios
- Ensure MongoDB connection for persistence features
- Use the existing logging infrastructure (`logs/logging_config.py`)
- Control log format with `LOGS_AS_JSON` environment variable (JSON vs pretty text)
- Set `LOGS_BASE_DIR` to customize log directory location