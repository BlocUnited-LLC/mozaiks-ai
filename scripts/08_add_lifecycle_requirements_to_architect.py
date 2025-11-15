"""
Strategic update to WorkflowArchitectAgent: Clarify before_chat and after_chat lifecycle requirements.

PROBLEM:
- Users not seeing before_chat and after_chat lifecycle hooks consistently
- Agent needs to understand these are ALMOST ALWAYS needed
- Need to clarify what the runtime already handles vs what needs custom hooks

SOLUTION:
- Add explicit guidance: ALWAYS include before_chat and after_chat lifecycle hooks
- Enumerate what the runtime already provides (don't duplicate)
- Provide clear examples of legitimate use cases for these hooks

APPROACH:
- Minimal targeted update to WorkflowArchitectAgent's runtime_integrations section
- Add specific guidance about lifecycle hook requirements
- Reference existing RUNTIME INTEGRATION patterns
"""

import json
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

AGENTS_JSON_PATH = Path("workflows/Generator/agents.json")


def update_workflow_architect_runtime_integration():
    """Update WorkflowArchitectAgent runtime_integrations section with lifecycle hook guidance."""
    
    if not AGENTS_JSON_PATH.exists():
        logger.error(f"agents.json not found at {AGENTS_JSON_PATH}")
        return False
    
    with open(AGENTS_JSON_PATH, 'r', encoding='utf-8') as f:
        agents_data = json.load(f)
    
    # Find WorkflowArchitectAgent
    agents = agents_data.get('agents', {})
    architect_agent = agents.get('WorkflowArchitectAgent')
    if not architect_agent:
        logger.error("WorkflowArchitectAgent not found in agents.json")
        return False
    
    # Find runtime_integrations section
    sections = architect_agent.get('prompt_sections', [])
    runtime_section = None
    for idx, section in enumerate(sections):
        if section.get('id') == 'runtime_integrations':
            runtime_section = section
            break
    
    if not runtime_section:
        logger.error("runtime_integrations section not found in WorkflowArchitectAgent")
        return False
    
    # Current content
    current_content = runtime_section.get('content', '')
    
    # Updated content with lifecycle hook requirements
    new_content = """You define workflow-wide scaffolding. Downstream agents expand it into per-phase execution.

The runtime already manages (DO NOT duplicate these):
- Agent creation, tool registration, and handoff orchestration
- Phase-level coordination authored by WorkflowImplementationAgent
- Default observability hooks (logging, metrics, performance tracking)
- Conversation history tracking (conversation_history variable auto-managed for chat workflows)
- Session persistence (AG2PersistenceManager handles chat state automatically)
- Token tracking (MozaiksStream tracks usage/costs per enterprise_id and user_id)
- Multi-tenant isolation (enterprise_id/user_id boundaries enforced by runtime)

Your responsibilities:
- Surface ONLY the context variables every phase depends on (shared state, approvals, thresholds)
- DO NOT create conversation_history variable - runtime manages this automatically for all chat workflows
- Forecast ui_components so Action Plan copy can preview inline vs artifact experiences without waiting for the tool manifest
- Request lifecycle hooks for custom initialization and cleanup logic

**LIFECYCLE HOOK REQUIREMENTS (CRITICAL)**:

**before_chat lifecycle hook is REQUIRED for workflows that need:**
- Loading external data/configuration before first agent runs (e.g., user preferences, feature flags, pricing tiers)
- Initializing third-party service connections (e.g., Stripe session, SendGrid client, analytics setup)
- Pre-populating context variables from database queries
- Setting up workflow-specific state that agents will reference
- Validating preconditions (e.g., user has required subscription tier, API keys are configured)

**Example before_chat hooks:**
```json
{
  "name": "load_user_preferences",
  "purpose": "Load user settings and feature flags from database before workflow starts",
  "trigger": "before_chat",
  "integration": null
}
```
```json
{
  "name": "initialize_stripe_session",
  "purpose": "Create Stripe checkout session and inject session_id into context",
  "trigger": "before_chat",
  "integration": "Stripe"
}
```

**after_chat lifecycle hook is REQUIRED for workflows that need:**
- Sending notifications/emails after workflow completes (e.g., confirmation email, Slack notification)
- Persisting final results to external systems (e.g., CRM update, analytics event)
- Cleanup of temporary resources (e.g., S3 file deletion, cache clearing)
- Triggering downstream workflows or webhooks
- Finalizing transactions or billing events

**Example after_chat hooks:**
```json
{
  "name": "send_completion_email",
  "purpose": "Send workflow completion notification to user via SendGrid",
  "trigger": "after_chat",
  "integration": "SendGrid"
}
```
```json
{
  "name": "sync_to_crm",
  "purpose": "Update customer record in Salesforce with workflow results",
  "trigger": "after_chat",
  "integration": "Salesforce"
}
```

**When to omit lifecycle hooks:**
- Simple conversational workflows with no external dependencies
- Workflows where all state is managed via agent outputs and context variables
- Workflows with no post-processing or notification requirements

**When in doubt:** Include before_chat and after_chat hooks with clear purpose statements. It's better to have them defined for future use than to omit them when needed.

**What NOT to create lifecycle hooks for:**
- Logging, metrics, or performance tracking (runtime handles this automatically)
- Session persistence or conversation history (AG2PersistenceManager handles this)
- Token tracking or cost attribution (MozaiksStream handles this)
- Multi-tenant isolation (runtime enforces enterprise_id/user_id boundaries)
- Tool registration or handoff coordination (runtime manages this)

Skip agent-level tools, lifecycle operations, or system hooks—that belongs to WorkflowImplementationAgent."""

    runtime_section['content'] = new_content
    
    # Write back to file
    with open(AGENTS_JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump(agents_data, f, indent=2, ensure_ascii=False)
    
    logger.info("✅ Updated WorkflowArchitectAgent runtime_integrations section")
    logger.info("   - Added lifecycle hook requirements and examples")
    logger.info("   - Clarified what runtime already handles")
    logger.info("   - Provided guidance on when to include before_chat/after_chat hooks")
    
    return True


if __name__ == "__main__":
    success = update_workflow_architect_runtime_integration()
    if success:
        logger.info("\n✅ Script completed successfully")
    else:
        logger.error("\n❌ Script failed")
