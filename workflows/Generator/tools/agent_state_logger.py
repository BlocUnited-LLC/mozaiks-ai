# ==============================================================================
# FILE: workflows/Generator/tools/agent_state_logger.py
# DESCRIPTION: Hook to log when agents update their state before replying
# ==============================================================================

from typing import Dict, Any

def log_agent_state_update(
    messages: Dict[str, Any]
) -> Dict[str, Any]:
    """AG2 Hook: Logs when any agent updates its state before generating a reply.
    
    This hook fires when an agent is about to generate a response and updates
    its internal state. Useful for tracking agent behavior and state changes.
    """
    print(f"🔄 STATE LOGGER: Agent updating state before reply (messages: {len(messages)})")
    
    # Return messages unchanged
    return messages
