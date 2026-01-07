# Creating Workflows

Learn how to create declarative workflows for MozaiksAI.

## Workflow Structure

Every workflow is a directory under `workflows/` with 8 YAML files:

```
workflows/YourWorkflow/
├── orchestrator.yaml       # Workflow metadata and strategy
├── agents.yaml             # Agent definitions
├── handoffs.yaml           # Agent transition rules
├── tools.yaml              # Available tools
├── context_variables.yaml  # Workflow state schema
├── structured_outputs.yaml # Required output formats
├── hooks.yaml              # Lifecycle event handlers
├── ui_config.yaml          # UI hints
└── tools/                  # Python tool implementations
    └── your_tools.py
```

## Minimal Example

### orchestrator.yaml

```yaml
workflow_name: SimpleChat
description: Basic conversational agent
orchestration_strategy: single_agent
max_turns: 10
primary_agent: ChatAgent
```

### agents.yaml

```yaml
agents:
  - name: ChatAgent
    role: conversational_assistant
    system_message: You are a helpful AI assistant.
    capabilities:
      - answer_questions
      - provide_information
    llm_config:
      model: gpt-4o-mini
      temperature: 0.7
      max_tokens: 1000
```

### handoffs.yaml

```yaml
handoffs: []  # No handoffs for single agent
```

### tools.yaml

```yaml
tools: []  # No tools needed for basic chat
```

### context_variables.yaml

```yaml
variables: {}  # No custom state
```

### structured_outputs.yaml

```yaml
outputs: []  # No structured outputs required
```

### hooks.yaml

```yaml
hooks: {}  # No lifecycle hooks
```

### ui_config.yaml

```yaml
ui:
  display_name: Simple Chat
  icon: 💬
  description: A basic conversational assistant
```

That's it! This workflow is ready to run.

## Multi-Agent Example

### orchestrator.yaml

```yaml
workflow_name: CustomerSupport
description: Customer support with escalation
orchestration_strategy: handoff_based
max_turns: 20
primary_agent: FrontlineAgent
```

### agents.yaml

```yaml
agents:
  - name: FrontlineAgent
    role: frontline_support
    system_message: |
      You are a customer support agent. Help with common questions.
      If the issue requires deeper investigation, hand off to TechnicalAgent.
    capabilities:
      - answer_faq
      - check_order_status
    llm_config:
      model: gpt-4o-mini
      temperature: 0.5

  - name: TechnicalAgent
    role: technical_support
    system_message: |
      You are a technical support specialist. Troubleshoot complex issues.
      If you need to escalate, hand off to EscalationAgent.
    capabilities:
      - debug_issues
      - access_logs
    llm_config:
      model: gpt-4o
      temperature: 0.3

  - name: EscalationAgent
    role: escalation_handler
    system_message: You handle escalated cases and create support tickets.
    capabilities:
      - create_ticket
      - notify_team
    llm_config:
      model: gpt-4o
      temperature: 0.0
```

### handoffs.yaml

```yaml
handoffs:
  - from_agent: FrontlineAgent
    to_agent: TechnicalAgent
    condition: technical_issue_detected
    condition_description: |
      Hand off when user mentions: errors, bugs, crashes, API issues

  - from_agent: TechnicalAgent
    to_agent: EscalationAgent
    condition: escalation_required
    condition_description: |
      Hand off when issue cannot be resolved or user requests manager

  - from_agent: EscalationAgent
    to_agent: FrontlineAgent
    condition: issue_resolved
    condition_description: |
      Return to frontline after ticket created
```

### tools.yaml

```yaml
tools:
  - name: check_order_status
    module: tools.support_tools
    description: Look up order status by order ID
    parameters:
      order_id:
        type: string
        required: true

  - name: create_support_ticket
    module: tools.support_tools
    description: Create a support ticket in the system
    parameters:
      title:
        type: string
        required: true
      description:
        type: string
        required: true
      priority:
        type: string
        enum: [low, medium, high, critical]
```

### context_variables.yaml

```yaml
variables:
  customer_tier:
    type: string
    description: Customer subscription tier (free, pro, enterprise)
    default: free
  
  issue_severity:
    type: string
    description: Current issue severity level
    default: low
  
  escalation_count:
    type: integer
    description: Number of times this issue has been escalated
    default: 0
```

## Adding Custom Tools

### 1. Create Tool Function

Create `workflows/CustomerSupport/tools/support_tools.py`:

```python
async def check_order_status(order_id: str) -> str:
    """Look up order status by order ID."""
    # In production, query your database or API
    # For now, mock response
    return f"Order {order_id} status: Shipped, arriving tomorrow"

async def create_support_ticket(
    title: str, 
    description: str, 
    priority: str = "medium"
) -> str:
    """Create a support ticket in the system."""
    # In production, call your ticketing API
    ticket_id = f"TICKET-{hash(title) % 10000}"
    return f"Created ticket {ticket_id} with priority {priority}"
```

### 2. Register in tools.yaml

Already done above in the `tools.yaml` example.

### 3. Use in Agent

The LLM will automatically see these tools and can call them when appropriate based on the descriptions.

## Using Context Variables

Context variables are shared state across all agents in a workflow.

### Access in Tools

```python
from core.workflow.execution.context_manager import get_context_variable

async def my_tool(customer_id: str) -> str:
    tier = get_context_variable("customer_tier")
    if tier == "enterprise":
        # Priority handling
        pass
```

### Update from Tools

```python
from core.workflow.execution.context_manager import set_context_variable

async def escalate_issue():
    current = get_context_variable("escalation_count")
    set_context_variable("escalation_count", current + 1)
    set_context_variable("issue_severity", "high")
```

## Structured Outputs

Require agents to produce specific output formats.

### structured_outputs.yaml

```yaml
outputs:
  - name: support_summary
    schema:
      type: object
      properties:
        issue_type:
          type: string
          enum: [billing, technical, account, other]
        resolved:
          type: boolean
        resolution_summary:
          type: string
        follow_up_required:
          type: boolean
      required: [issue_type, resolved]
    when: workflow_complete
```

This forces the final agent to output JSON matching the schema.

## Lifecycle Hooks

Run custom code at workflow lifecycle events.

### hooks.yaml

```yaml
hooks:
  on_workflow_start: hooks.logging.log_start
  on_workflow_complete: hooks.logging.log_complete
  on_agent_handoff: hooks.metrics.track_handoff
```

### Implementation

Create `workflows/CustomerSupport/hooks/logging.py`:

```python
async def log_start(context):
    """Called when workflow starts."""
    print(f"Starting workflow for user {context.user_id}")

async def log_complete(context):
    """Called when workflow completes."""
    print(f"Completed workflow in {context.duration_ms}ms")
```

Create `workflows/CustomerSupport/hooks/metrics.py`:

```python
async def track_handoff(context, from_agent, to_agent):
    """Called on agent handoffs."""
    # Send to analytics
    print(f"Handoff: {from_agent} → {to_agent}")
```

## Testing Your Workflow

### 1. Validate Config

```bash
python -m core.workflow.workflow_manager validate CustomerSupport
```

### 2. Test Locally

```python
# test_workflow.py
import asyncio
from core.workflow.workflow_manager import WorkflowManager

async def test():
    manager = WorkflowManager()
    await manager.execute_workflow(
        workflow_name="CustomerSupport",
        user_message="My order hasn't arrived",
        app_id="test",
        user_id="test-user",
        chat_id="test-session"
    )

asyncio.run(test())
```

### 3. Use WebSocket Client

See [WebSocket Protocol](websocket-protocol.md) for client integration.

## Best Practices

1. **Start Simple**: Begin with single agent, add complexity as needed
2. **Clear Handoff Conditions**: Make agent transitions explicit and testable
3. **Tool Documentation**: Write detailed tool descriptions for the LLM
4. **Error Handling**: Tools should return user-friendly error messages
5. **Context Variables**: Use sparingly, prefer stateless agents when possible
6. **Test Thoroughly**: Validate config and test with real messages before deploying

## Next Steps

- [YAML Schema Reference](yaml-schema.md) - Complete config reference
- [Custom Tools Guide](custom-tools.md) - Advanced tool patterns
- [WebSocket Protocol](websocket-protocol.md) - Frontend integration
