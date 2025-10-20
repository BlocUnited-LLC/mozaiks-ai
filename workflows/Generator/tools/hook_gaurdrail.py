# ==============================================================================
# FILE: workflows\Generator\tools\hook_gaurdrail.py
# PURPOSE: If the last inbound message appears to ask for dangerous actions, prepend a policy tag to guide the agent's reply.
# HOOK TYPE: process_last_received_message
# SIGNATURE: def your_function_name(content: Union[str, list[dict[str, Any]]], sender: Any = None) -> str:
# NOTE: AG2 passes 'sender' as a kwarg, so we must accept it even if unused
# ==============================================================================

from typing import Union, List, Dict, Any

DANGEROUS_HINTS = ("exploit", "malware", "bypass", "jailbreak", "phish", "ddos", "credential", "exfiltrate", 
                   "ransomware", "botnet", "keylogger", "trojan", "backdoor", "rootkit", "virus", "worm",
                   "hack into", "break into", "steal data", "illegal", "piracy", "fraud", "create virus",
                   "build weapon", "bomb making", "terrorist", "assassination")

def soft_policy_label(content: Union[str, List[Dict[str, Any]]], sender: Any = None) -> str:
    """
    Prepends [policy: restricted] to dangerous requests to guide agent responses away from harmful content.
    This helps prevent users from creating workflows that could be used for malicious purposes.
    
    Args:
        content: The message content (string or list of message dicts)
        sender: The sender agent (passed by AG2 but not used here)
    
    Returns a modified string that will permanently change the chat messages for this agent.
    """
    # Extract text from content
    if isinstance(content, list):
        # Get the last message content
        if not content:
            return ""
        last_msg = content[-1]
        text = last_msg.get("content", "") if isinstance(last_msg, dict) else str(last_msg)
    else:
        text = str(content)
    
    if not text.strip():
        return text
    
    # Check for dangerous patterns
    lower = text.lower()
    if any(token in lower for token in DANGEROUS_HINTS):
        # Add policy header if not already present
        if not text.lstrip().startswith("[policy: restricted]"):
            policy_header = "[policy: restricted] Please respond that this type of request is not something Mozaiks allows, and offer legitimate workflow alternatives instead. Users Message: "
            return policy_header + text
    
    return text
