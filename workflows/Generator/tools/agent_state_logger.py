# ==============================================================================
# FILE: workflows/Generator/tools/agent_state_logger.py
# DESCRIPTION: Hook to log when agents update their state before replying
# ==============================================================================

from typing import Dict, Any

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
    
    print(f"🔄 STATE LOGGER: {agent_name} updating state before reply (messages: {message_count})")
    
    # Return messages unchanged (or None for state updates)
    return messages
