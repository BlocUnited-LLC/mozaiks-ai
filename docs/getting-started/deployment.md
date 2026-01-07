# MozaiksAI Runtime — Deployment & Integration Guide

> **For**: Platform engineers, SaaS builders, and open-source integrators  
> **Purpose**: Deploy and integrate the MozaiksAI stateless execution runtime

---

## What is MozaiksAI Runtime?

MozaiksAI Runtime is a **stateless, multi-tenant execution engine** for declarative AI workflows powered by AG2 (Autogen).

Think of it as a containerized workflow runner that:
- Accepts authenticated execution requests
- Runs multi-agent workflows declaratively
- Streams events back to your frontend
- Measures and reports usage
- Scales horizontally without state

**What it is NOT:**
- A user authentication system (you bring your own)
- A billing/subscription service (you manage entitlements)
- A workflow designer UI (you define workflows as JSON)

---

## Architecture Overview

```
┌─────────────────┐
│  Your Control   │  Issues launch tokens
│     Plane       │  Enforces policy/limits
│  (Auth, Billing)│  Manages workflows
└────────┬────────┘
         │
         │ Launch Token (JWT)
         │ + Workflow JSON
         ▼
┌─────────────────┐
│  MozaiksAI      │  Validates token
│    Runtime      │  Executes workflow
│                 │  Streams events
│                 │  Emits usage
└────────┬────────┘
         │
         │ WebSocket events
         ▼
┌─────────────────┐
│   Your UI       │
│  (React, etc.)  │
└─────────────────┘
```

**Key principle:** The runtime is **downstream-only**. Your control plane authorizes and issues tokens; the runtime executes blindly within token scope.

---

## Deployment

### 1. Prerequisites

- Python 3.11+
- MongoDB instance (for persistence)
- OpenAI API key (or compatible LLM endpoint)
- JWT signing keys (for launch token validation)

### 2. Installation

```bash
git clone https://github.com/your-org/mozaiks-runtime.git
cd mozaiks-runtime
pip install -r requirements.txt
```

### 3. Configuration

Create a `.env` file:

```env
# LLM Configuration
OPENAI_API_KEY=sk-...
DEFAULT_MODEL=gpt-4

# Database
MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE=mozaiks_runtime

# JWT Validation
JWT_SECRET=your-jwt-secret-key
JWT_ISSUER=your-control-plane.com
JWT_AUDIENCE=mozaiks-runtime

# Optional: Feature Flags
CONTEXT_AWARE=false
MONETIZATION_ENABLED=true
LOG_LEVEL=INFO
```

### 4. Start the Runtime

```bash
python run_server.py
```

The runtime exposes:
- `ws://localhost:8000/ws/chat` — WebSocket for workflow execution
- `http://localhost:8000/health` — Health check endpoint
- `http://localhost:8000/metrics` — Prometheus-compatible metrics

---

## Integration

### Launch Token (JWT)

Your control plane issues a launch token for each workflow execution:

```json
{
  "iss": "your-control-plane.com",
  "aud": "mozaiks-runtime",
  "exp": 1704672000,
  "scope": "workflow:execute",
  "user_id": "user_123",
  "app_id": "app_456",
  "workflow_id": "onboarding_flow",
  "chat_id": "chat_789",
  "max_tokens": 50000
}
```

**Required fields:**
- `iss`, `aud`, `exp` — Standard JWT claims
- `scope` — Must be `workflow:execute`
- `user_id` — Unique user identifier (for tenancy)
- `app_id` — Application/workspace identifier
- `workflow_id` — Which workflow to execute
- `chat_id` — Session identifier (for message history)

**Optional fields:**
- `max_tokens` — Advisory limit (runtime measures but does not enforce)
- Custom context fields (passed to workflow)

**Signing:** Use RS256 or HS256. Runtime validates signature, issuer, audience, and expiration.

---

## Workflow Definition

Workflows are declarative YAML files stored in `workflows/<workflow_id>/`:

**Example: `workflows/onboarding_flow/orchestrator.yaml`**
```yaml
workflow_name: Customer Onboarding
max_turns: 10
human_in_the_loop: false
startup_mode: UserDriven
orchestration_pattern: DefaultPattern
```

**Example: `workflows/onboarding_flow/agents.yaml`**
```yaml
agents:
  - name: DataCollector
    role: Gather customer information
    system_message: You collect user details step by step.
    llm_config:
      model: gpt-4
      temperature: 0.7
  - name: Validator
    role: Validate collected data
    system_message: You validate completeness and correctness.
```

**Example: `workflows/onboarding_flow/tools.yaml`**
```yaml
tools:
  - agent: DataCollector
    file: email_tools.py
    function: send_email
    description: Send welcome email
    tool_type: Agent_Tool
```

Place these files in `workflows/onboarding_flow/`.

---

## Client Integration

### WebSocket Protocol

**1. Connect**
```javascript
const token = await yourControlPlane.issueToken({
  user_id: "user_123",
  app_id: "app_456",
  workflow_id: "onboarding_flow"
});

const ws = new WebSocket(
  `ws://runtime.example.com/ws/chat?token=${token}`
);
```

**2. Send Message**
```javascript
ws.send(JSON.stringify({
  type: "user_message",
  content: "I want to onboard a new customer",
  chat_id: "chat_789",
  user_id: "user_123"
}));
```

**3. Receive Events**
```javascript
ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  
  switch(msg.type) {
    case "agent_message":
      // Display assistant response
      console.log(msg.content);
      break;
    
    case "tool_call":
      // Show tool execution
      console.log(`Calling ${msg.name}...`);
      break;
    
    case "workflow_complete":
      // Execution finished
      console.log("Done!");
      break;
    
    case "usage_update":
      // Token consumption (informational)
      console.log(`Tokens used: ${msg.total_tokens}`);
      break;
  }
};
```

---

## Usage Tracking

The runtime emits usage events after each workflow execution:

```json
{
  "type": "usage_update",
  "event_id": "evt_abc123",
  "chat_id": "chat_789",
  "user_id": "user_123",
  "app_id": "app_456",
  "workflow_id": "onboarding_flow",
  "tokens": {
    "prompt_tokens": 1200,
    "completion_tokens": 800,
    "total_tokens": 2000
  },
  "cost_usd": 0.042,
  "timestamp": "2026-01-07T10:30:00Z"
}
```

**How to use this:**
1. Stream to your analytics pipeline
2. Store in your billing database
3. Reconcile against user quotas

**What the runtime does NOT do:**
- Stop execution if tokens exceed `max_tokens`
- Check if user has credits
- Enforce rate limits

You handle enforcement in your control plane **before issuing the launch token**.

---

## Multi-Tenancy

The runtime enforces strict isolation:

| Boundary | Mechanism |
|----------|-----------|
| **User isolation** | Separate `cache_seed` per `user_id` |
| **App isolation** | Workflows scoped to `app_id` |
| **Session isolation** | Message history tied to `chat_id` |

No user can access another user's messages, workflows, or state.

---

## Scaling

**Horizontal scaling:**
- Runtime is stateless (except MongoDB for message history)
- Run multiple instances behind a load balancer
- WebSocket connections are sticky per session
- No shared memory or local state

**Recommended setup:**
```
┌─────────────┐
│   LB/Ingress│
└──────┬──────┘
       │
   ┌───┴────┬──────────┬──────────┐
   ▼        ▼          ▼          ▼
 Pod 1    Pod 2      Pod 3      Pod N
   │        │          │          │
   └────────┴──────────┴──────────┘
              │
              ▼
         ┌─────────┐
         │ MongoDB │
         └─────────┘
```

**Autoscaling triggers:**
- CPU > 70%
- Active WebSocket connections
- Queue depth (if using message queue)

---

## Observability

### Logs
Structured JSON logs to stdout:
```json
{
  "timestamp": "2026-01-07T10:30:00Z",
  "level": "INFO",
  "message": "Workflow execution started",
  "user_id": "user_123",
  "app_id": "app_456",
  "workflow_id": "onboarding_flow",
  "chat_id": "chat_789"
}
```

### Metrics
Prometheus endpoint at `/metrics`:
- `workflow_executions_total{workflow_id, status}`
- `workflow_duration_seconds{workflow_id}`
- `token_usage_total{user_id, app_id}`
- `websocket_connections_active`

### Traces
OpenTelemetry-compatible spans (optional):
- Workflow execution
- LLM calls
- Tool invocations

---

## Security

### Transport Authentication
- Runtime validates JWT signature on every connection
- Expired tokens are rejected at WebSocket handshake
- No token = no execution

### Data Isolation
- MongoDB queries filtered by `user_id` and `app_id`
- No cross-user data leakage
- Message history scoped to `chat_id`

### Secrets Management
- Never log JWT tokens or API keys
- Use environment variables or secret managers
- Rotate JWT signing keys regularly

### What You Must Provide
- Secure JWT issuance in your control plane
- User authentication (OAuth, SAML, etc.)
- Authorization logic (who can execute which workflows)

---

## Advanced: Custom Tools

Add domain-specific tools as Python callables:

**1. Create tool stub:**
```python
# workflows/my_workflow/stubs.py

def query_database(query: str) -> dict:
    """Execute SQL query and return results."""
    # Your implementation
    return {"rows": [...]}
```

**2. Declare in workflow:**
```json
{
  "tools": [
    {
      "name": "query_database",
      "implementation": "stubs.query_database",
      "description": "Query the customer database",
      "parameters": {
        "type": "object",
        "properties": {
          "query": {"type": "string"}
        }
      }
    }
  ]
}
```

**3. Runtime auto-registers and calls it when agents request.**

---

## Advanced: Custom Agent Types

Override agent behavior by providing custom classes:

```python
# workflows/my_workflow/custom_agents.py

from autogen import ConversableAgent

class DataAnalystAgent(ConversableAgent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Custom initialization
```

Reference in workflow:
```json
{
  "agents": [
    {
      "name": "Analyst",
      "class": "custom_agents.DataAnalystAgent",
      "system_message": "..."
    }
  ]
}
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| **401 Unauthorized** | Check JWT signature, issuer, audience, expiration |
| **Workflow not found** | Ensure `workflows/<workflow_id>/config.json` exists |
| **Tool not registered** | Verify `implementation` path in workflow JSON |
| **High latency** | Scale horizontally, check LLM endpoint latency |
| **Message history missing** | Check MongoDB connection, `chat_id` consistency |

---

## Example: Complete Integration

### Your Control Plane (Python/FastAPI)
```python
import jwt
from datetime import datetime, timedelta

@app.post("/api/launch-workflow")
async def launch_workflow(user_id: str, workflow_id: str):
    # 1. Authorize user (your business logic)
    if not user_has_access(user_id, workflow_id):
        raise HTTPException(403, "Access denied")
    
    # 2. Check quota (your business logic)
    if not user_has_credits(user_id):
        raise HTTPException(402, "Insufficient credits")
    
    # 3. Issue launch token
    token = jwt.encode({
        "iss": "your-control-plane.com",
        "aud": "mozaiks-runtime",
        "exp": datetime.utcnow() + timedelta(hours=1),
        "scope": "workflow:execute",
        "user_id": user_id,
        "app_id": "default",
        "workflow_id": workflow_id,
        "chat_id": generate_chat_id()
    }, JWT_SECRET, algorithm="HS256")
    
    return {"token": token, "runtime_url": "ws://runtime/ws/chat"}
```

### Your Frontend (React)
```javascript
async function startWorkflow() {
  // Get token from your control plane
  const res = await fetch('/api/launch-workflow', {
    method: 'POST',
    body: JSON.stringify({
      user_id: currentUser.id,
      workflow_id: 'onboarding_flow'
    })
  });
  const {token, runtime_url} = await res.json();
  
  // Connect to runtime
  const ws = new WebSocket(`${runtime_url}?token=${token}`);
  
  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (msg.type === 'agent_message') {
      addMessageToChat(msg.content);
    }
  };
  
  ws.send(JSON.stringify({
    type: 'user_message',
    content: 'Start onboarding',
    chat_id: token.chat_id,
    user_id: currentUser.id
  }));
}
```

---

## FAQ

**Q: Can the runtime enforce usage limits?**  
A: No. Limits are enforced in your control plane before issuing tokens. The runtime measures and reports usage but does not block execution.

**Q: How do I handle payment failures?**  
A: In your control plane. Don't issue tokens for users with expired subscriptions.

**Q: Can I use this without MongoDB?**  
A: Not currently. MongoDB stores message history and session state. A pluggable persistence layer is planned.

**Q: Does this work with Anthropic/Azure OpenAI?**  
A: Yes. Configure `OPENAI_API_KEY` and `OPENAI_API_BASE` to point to your LLM provider.

**Q: Can I run multiple workflows per user?**  
A: Yes. Issue separate tokens with different `chat_id` values.

**Q: Is this production-ready?**  
A: The core runtime is stable. Add monitoring, secrets management, and disaster recovery per your requirements.

---

## Contributing

We welcome contributions! See `CONTRIBUTING.md` for:
- Code style guidelines
- Testing requirements
- Pull request process

Join the discussion: [Discord](https://discord.gg/mozaiks) | [GitHub Issues](https://github.com/your-org/mozaiks-runtime/issues)

---

## License

MozaiksAI Runtime is released under the [MIT License](LICENSE).

---

## Support

- **Documentation**: [docs.mozaiks.ai](https://docs.mozaiks.ai)
- **Community**: [Discord](https://discord.gg/mozaiks)
- **Issues**: [GitHub](https://github.com/your-org/mozaiks-runtime/issues)
- **Commercial support**: [enterprise@mozaiks.ai](mailto:enterprise@mozaiks.ai)

---

**Remember:** The runtime executes. Your control plane decides *what* and *when* to execute.
