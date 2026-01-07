# MozaiksAI Runtime

**The world's first open-source declarative workflow runtime for AI agents.**

MozaiksAI is a stateless execution engine built on [AG2 (Autogen)](https://github.com/ag2ai/ag2) that turns declarative YAML workflows into running multi-agent systems. It's designed for developers who want predictable, observable, and production-ready AI agent orchestration.

## Key Features

- **Declarative Workflows**: Define agents, tools, handoffs, and orchestration in YAML
- **AG2-Powered**: Built on the proven Autogen framework with GroupChat coordination
- **Multi-Tenant**: Isolated execution contexts per app_id and user_id
- **Event-Driven**: WebSocket transport with structured event streaming
- **Observable**: Built-in logging, metrics, and runtime telemetry
- **Stateless**: No authorization, billing, or policy enforcement—pure execution
- **Production-Ready**: Async I/O, MongoDB persistence, JWT authentication

## Quick Example

```yaml
# orchestrator.yaml
workflow_name: CustomerSupport
description: AI customer support with escalation
orchestration_strategy: handoff_based
max_turns: 20
```

```yaml
# agents.yaml
agents:
  - name: SupportAgent
    role: frontline_support
    capabilities: [answer_questions, check_status]
    llm_config:
      model: gpt-4o-mini
```

```yaml
# handoffs.yaml
handoffs:
  - from_agent: SupportAgent
    to_agent: EscalationAgent
    condition: user_requests_human
```

Start the runtime, send a WebSocket message, and your workflow executes with full observability.

## Use Cases

- **AI-Native Applications**: Build products with agentic features (code generation, data analysis, creative workflows)
- **Multi-Agent Automation**: Coordinate specialist agents with declarative handoffs
- **Custom AI Backends**: Drop-in runtime for your React/Next.js chat interfaces
- **Research & Prototyping**: Test agent coordination patterns without infrastructure overhead

## Architecture

MozaiksAI is the **execution layer only**:
- ✅ Loads and runs declarative workflows
- ✅ Manages AG2 agents and GroupChat coordination
- ✅ Provides WebSocket transport and event streaming
- ✅ Persists messages and session state (via MongoDB)
- ✅ Emits usage metrics for downstream billing

What it **doesn't** do:
- ❌ User authentication/authorization (validates JWT signatures only)
- ❌ Billing or usage enforcement
- ❌ Workflow generation (bring your own YAML or use a generator)
- ❌ Policy enforcement (rate limits, content moderation, etc.)

This separation makes it perfect for open-source use: you control the platform features, MozaiksAI handles execution.

## Getting Started

```bash
# Clone and install
git clone https://github.com/yourusername/MozaiksAI.git
cd MozaiksAI
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your MongoDB URI and OpenAI key

# Run
python run_server.py
```

Your runtime is now listening on `ws://localhost:8000/ws`. See the [Quickstart Guide](getting-started/quickstart.md) for details.

## Documentation

- [Quickstart](getting-started/quickstart.md) - Get running in 5 minutes
- [Deployment Guide](getting-started/deployment.md) - Production deployment patterns
- [Architecture](architecture/overview.md) - How MozaiksAI works
- [YAML Schema](guides/yaml-schema.md) - Workflow definition reference
- [WebSocket Protocol](guides/websocket-protocol.md) - Client integration guide

## Community & Support

- **GitHub Issues**: Bug reports and feature requests
- **Discussions**: Architecture questions and use cases
- **Contributing**: See CONTRIBUTING.md

## License

MIT License - see LICENSE file for details.

Built with ❤️ for the AI agent community.
