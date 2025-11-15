"""
Strategic update to WorkflowImplementationAgent: Add runtime capabilities reference for agent-level lifecycle tools.

PROBLEM:
- Agent may be duplicating functionality that runtime already provides
- Need to cross-reference agent RUNTIME INTEGRATION sections
- Agent-level lifecycle tools (before_agent/after_agent) are OPTIONAL, not required

SOLUTION:
- Add guidance to check upstream agents' RUNTIME INTEGRATION sections
- Clarify what the runtime already handles (don't duplicate)
- Emphasize that agent-level lifecycle tools are optional and pattern-dependent

APPROACH:
- Minimal targeted update to WorkflowImplementationAgent's runtime_integrations section
- Add cross-reference to other agents' runtime integration documentation
- Clarify when agent-level lifecycle tools are truly needed
"""

import json
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

AGENTS_JSON_PATH = Path("workflows/Generator/agents.json")


def update_workflow_implementation_runtime_integration():
    """Update WorkflowImplementationAgent runtime_integrations section with runtime capabilities reference."""
    
    if not AGENTS_JSON_PATH.exists():
        logger.error(f"agents.json not found at {AGENTS_JSON_PATH}")
        return False
    
    with open(AGENTS_JSON_PATH, 'r', encoding='utf-8') as f:
        agents_data = json.load(f)
    
    # Find WorkflowImplementationAgent
    agents = agents_data.get('agents', {})
    implementation_agent = agents.get('WorkflowImplementationAgent')
    if not implementation_agent:
        logger.error("WorkflowImplementationAgent not found in agents.json")
        return False
    
    # Find runtime_integrations section
    sections = implementation_agent.get('prompt_sections', [])
    runtime_section = None
    for idx, section in enumerate(sections):
        if section.get('id') == 'runtime_integrations':
            runtime_section = section
            break
    
    if not runtime_section:
        logger.error("runtime_integrations section not found in WorkflowImplementationAgent")
        return False
    
    # Find current content
    current_content = runtime_section.get('content', '')
    
    # Check if it already has runtime capabilities section
    if "runtime already manages" in current_content.lower():
        logger.info("Runtime capabilities section already exists, skipping update")
        return True
    
    # Updated content with runtime capabilities reference
    new_content = """You create phase-level agent specifications with tools and coordination logic.

The runtime already manages (DO NOT duplicate these):
- Agent creation, tool registration, and handoff orchestration (AG2 GroupChat)
- Conversation history tracking (conversation_history variable auto-managed)
- Session persistence (AG2PersistenceManager handles chat state)
- Token tracking (MozaiksStream tracks usage/costs per enterprise_id and user_id)
- Multi-tenant isolation (enterprise_id/user_id boundaries enforced)
- Default observability (logging, metrics, performance tracking)
- Tool invocation and response handling (AG2 native tool calling)
- Human-in-the-loop coordination (runtime manages user interaction wait states)

**CRITICAL: Cross-reference upstream agents' [RUNTIME INTEGRATION] sections**
Before creating agent-level lifecycle tools or custom logic, review what each agent's RUNTIME INTEGRATION section says the runtime already handles. Do not duplicate:
- Logging, metrics, or performance tracking
- Session or conversation persistence
- Token/cost attribution
- Multi-tenant boundaries
- Tool registration or calling mechanisms
- Context variable injection

Your responsibilities:
- Define agent roster with human_interaction modes derived from TechnicalBlueprint ui_components
- Map agent_tools from tools manifest (including interaction_mode: inline|artifact|none)
- Create agent-level lifecycle_tools ONLY when truly needed (see guidance below)
- Never author tool function signatures—reference manifests and let downstream generators handle implementation

**Agent-Level Lifecycle Tools (OPTIONAL - Use Sparingly)**

**before_agent lifecycle tools** are OPTIONAL and should be created ONLY when:
- Agent needs specialized setup unique to that agent (e.g., load agent-specific prompts from database)
- Agent requires external service initialization for its specific task (e.g., open database connection pool)
- Agent depends on context not available workflow-wide (e.g., fetch user profile when this specific agent runs)
- Pattern explicitly requires agent-level setup (e.g., Hierarchical pattern where lead agent needs team member discovery)

**after_agent lifecycle tools** are OPTIONAL and should be created ONLY when:
- Agent needs specialized cleanup unique to that agent (e.g., close database connections specific to this agent)
- Agent produces outputs that must be immediately processed (e.g., send interim notification, cache calculation result)
- Pattern explicitly requires agent-level teardown (e.g., Feedback Loop pattern where reviewer agent logs iteration metrics)

**When to omit agent-level lifecycle tools:**
- Most workflows don't need them
- Default to NO lifecycle_tools unless pattern or requirement explicitly demands them
- If workflow-wide initialization/cleanup suffices (before_chat/after_chat), don't add agent-level duplication

**Examples of legitimate agent-level lifecycle tools:**
```json
{
  "name": "load_agent_custom_instructions",
  "trigger": "before_agent",
  "purpose": "Fetch agent-specific prompt customizations from database based on user preferences",
  "integration": null
}
```
```json
{
  "name": "cache_analysis_results",
  "trigger": "after_agent",
  "purpose": "Store analysis output to Redis for downstream agent access and faster retrieval",
  "integration": "Redis"
}
```

**Examples of UNNECESSARY agent-level lifecycle tools (runtime handles these):**
❌ "log_agent_start" - runtime already logs agent lifecycle
❌ "persist_conversation" - AG2PersistenceManager handles this
❌ "track_token_usage" - MozaiksStream handles this
❌ "inject_context_variables" - runtime handles context injection
❌ "validate_enterprise_id" - runtime enforces multi-tenant boundaries

**When in doubt:** Omit agent-level lifecycle tools. They are the exception, not the rule.

Pattern guidance will specify when agent-level lifecycle tools are appropriate."""

    runtime_section['content'] = new_content
    
    # Write back to file
    with open(AGENTS_JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump(agents_data, f, indent=2, ensure_ascii=False)
    
    logger.info("✅ Updated WorkflowImplementationAgent runtime_integrations section")
    logger.info("   - Added runtime capabilities reference")
    logger.info("   - Clarified agent-level lifecycle tools are OPTIONAL")
    logger.info("   - Added cross-reference to upstream agents' RUNTIME INTEGRATION sections")
    logger.info("   - Provided examples of legitimate vs unnecessary lifecycle tools")
    
    return True


if __name__ == "__main__":
    success = update_workflow_implementation_runtime_integration()
    if success:
        logger.info("\n✅ Script completed successfully")
    else:
        logger.error("\n❌ Script failed")
