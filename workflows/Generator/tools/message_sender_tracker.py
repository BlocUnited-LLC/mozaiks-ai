# ==============================================================================
# FILE: workflows/Generator/tools/message_sender_tracker.py
# DESCRIPTION: Hook to track when agents are about to send messages
# ==============================================================================

from typing import Dict, Any, Union
from autogen import ConversableAgent, Agent

async def track_message_sending(
    sender: ConversableAgent,
    message: Union[Dict[str, Any], str],
    recipient: Agent,
    silent: bool
) -> Union[Dict[str, Any], str]:
    """AG2 Hook: Tracks when any agent is about to send a message to another agent.
    
    This hook fires right before an agent sends a message, allowing us to
    track message flow and communication patterns between agents.
    Also detects and logs handoffs when they occur.
    
    Args:
        sender: The agent that is sending the message
        message: The message being sent (dict or string)
        recipient: The agent that will receive the message
        silent: Whether the message is being sent silently
        
    Returns:
        The message (potentially modified)
    """
    from logs.logging_config import get_workflow_logger
    
    sender_name = getattr(sender, 'name', 'Unknown') if sender else 'Unknown'
    recipient_name = getattr(recipient, 'name', 'Unknown') if recipient else 'Unknown'
    
    wf_logger = get_workflow_logger(workflow_name="Generator", agent_sender=sender_name, agent_recipient=recipient_name)
    
    # Check if this looks like a handoff (different agent types, not just chat manager)
    is_potential_handoff = (
        sender_name != recipient_name and  # Different agents
        sender_name not in ['chat_manager', 'Unknown'] and  # Not system agents
        recipient_name not in ['chat_manager', 'Unknown'] and
        sender_name != 'user' and recipient_name != 'user'  # Not user interactions
    )
    
    if is_potential_handoff:
        # This looks like a handoff between agents
        wf_logger.info(f"🤝 HANDOFF DETECTED: {sender_name} → {recipient_name}")
        
        # Extract handoff reason from message if possible
        handoff_reason = "direct_message"
        if isinstance(message, dict) and 'content' in message:
            content = str(message['content'])
            if any(keyword in content.lower() for keyword in ['transfer', 'handoff', 'pass to', 'delegate']):
                handoff_reason = "explicit_transfer"
        elif isinstance(message, str):
            if any(keyword in message.lower() for keyword in ['transfer', 'handoff', 'pass to', 'delegate']):
                handoff_reason = "explicit_transfer"
        
        # Log context-rich workflow event
        wf_logger.info(
            "AGENT_HANDOFF_DETECTED",
            sender_agent=sender_name,
            target_agent=recipient_name,
            handoff_reason=handoff_reason,
            handoff_type="message_based",
            silent=silent,
        )
    else:
        # Regular message tracking
        wf_logger.debug(f"📤 MESSAGE: {sender_name} → {recipient_name} (silent: {silent})")
    
    # Return message unchanged
    return message