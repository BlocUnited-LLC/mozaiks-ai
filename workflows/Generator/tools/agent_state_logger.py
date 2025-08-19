# ==============================================================================
# FILE: workflows/Generator/tools/agent_state_logger.py
# DESCRIPTION: Hook to log when agents update their state before replying
# ==============================================================================

from typing import Dict, Any
from logs.logging_config import get_workflow_logger

async def log_agent_state_update(
    agent,
    messages
) -> Any:
    """AG2 Hook: Logs when any agent updates its state before generating a reply.
    
    This hook fires when an agent is about to generate a response and updates
    its internal state. Useful for tracking agent behavior and state changes.
    
    Args:
        agent: The agent that is updating its state
        messages: The conversation messages
    """
    agent_name = getattr(agent, 'name', 'Unknown') if agent else 'Unknown'
    message_count = len(messages) if messages else 0
    wf_logger = get_workflow_logger(workflow_name="Generator", agent_name=agent_name)
    wf_logger.debug("AGENT_STATE_UPDATE", agent_name=agent_name, message_count=message_count)
    # Keep minimal console trace for developers
    print(f"🔄 STATE LOGGER: {agent_name} updating state before reply (messages: {message_count})")
    
    # Return messages unchanged (or None for state updates)
    return messages
