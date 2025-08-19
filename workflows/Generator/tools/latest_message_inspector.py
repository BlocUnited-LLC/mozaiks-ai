# ==============================================================================
# FILE: workflows/Generator/tools/latest_message_inspector.py
# DESCRIPTION: Hook to inspect the latest message received by agents
# ==============================================================================

from typing import Dict, Any
from logs.logging_config import get_workflow_logger

async def inspect_latest_message(
    message
):
    """AG2 Hook: Inspects the latest message received by any agent.
    
    This hook fires when an agent processes the last received message.
    Useful for message inspection, content analysis, and debugging message flow.
    
    Args:
        message: The message content that was received
    """
    content = message.get('content', '') if isinstance(message, dict) else str(message)
    content_preview = content[:50] + '...' if len(content) > 50 else content
    wf_logger = get_workflow_logger(workflow_name="Generator")
    wf_logger.debug("LATEST_MESSAGE_INSPECT", content_preview=content_preview)
    
    print(f"📩 MESSAGE INSPECTOR: Processing message: '{content_preview}'")
    
    return message
