# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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
# Test schema alignment
python test_schema_alignment.py

# Test termination integration
python test_termination_integration.py

# Code quality check
flake8
```

## Architecture Overview

MozaiksAI is an event-driven AI workflow orchestration platform built on Microsoft's Autogen (AG2). The architecture follows a "strategically lean" philosophy with these key components:

### Core Architecture Pillars

1. **Event-Driven Core**: All system interactions flow through a unified event bus (`core/events/unified_event_dispatcher.py`) with three event categories:
   - Business Events: Application lifecycle and monitoring
   - Runtime Events: AG2 agent workflow execution  
   - UI Tool Events: Dynamic UI interactions

2. **Transport Layer**: `core/transport/simple_transport.py` handles real-time communication between backend and frontend via WebSocket/SSE with automatic fallback and message filtering.

3. **Workflow Orchestration**: `core/workflow/orchestration_patterns.py` serves as the single entry point for all AG2 workflow execution, handling streaming, persistence, and telemetry.

4. **Persistence**: `core/data/persistence_manager.py` and `core/data/chat_sessions_data.py` provide real-time MongoDB persistence for chat sessions, enabling seamless resumption.

### Key Directories

- **`core/`**: Backend platform systems
  - `transport/`: Communication layer with WebSocket/SSE support
  - `workflow/`: Workflow execution, tool registry, agent management
  - `data/`: MongoDB persistence and chat session management
  - `events/`: Unified event dispatcher and handlers
  - `observability/`: Performance monitoring and OpenTelemetry integration

- **`workflows/`**: Modular workflow definitions (YAML-based configuration)
  - Each workflow has agents, tools, handoffs, structured outputs
  - Example: `workflows/Generator/` contains complete workflow definition

- **`ChatUI/`**: React frontend application
  - `src/components/`: Dynamic UI components for agent interaction
  - `src/transport/`: Frontend transport integration
  - `src/workflows/`: Workflow-specific UI components

### Configuration System

- **Workflow Configuration**: Each workflow defines its behavior in YAML files (agents.yaml, tools.yaml, etc.)
- **Environment Variables**: `.env` file for MongoDB connections, API keys, logging format
- **Logging**: Controlled by `LOGS_AS_JSON` environment variable (JSON vs pretty text format)

### Integration Patterns

1. **Agent-UI Integration**: Agents can dynamically control React components through the transport layer
2. **Tool Registry**: JSON-based tool manifests enable dynamic agent capability extension
3. **Event Filtering**: Smart message filtering ensures users only see relevant agent communications
4. **Resume Capability**: Full AG2 groupchat state persistence across server restarts

### Performance & Observability

- **Real-time Metrics**: `core/observability/performance_manager.py` tracks token usage, costs, and agent performance
- **OpenTelemetry**: Optional telemetry export via `OPENLIT_ENABLED=true`
- **Structured Logging**: Dual-format logging (JSON/pretty) with workflow and chat separation

### Development Guidelines

- Follow the existing YAML-based workflow configuration patterns
- Use the unified event dispatcher for all internal events
- Leverage the transport layer for real-time UI updates
- Test with both local development and Docker deployment scenarios
- Ensure MongoDB connection for persistence features
- Use the existing logging infrastructure (`logs/logging_config.py`)