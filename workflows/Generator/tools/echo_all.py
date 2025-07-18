# ==============================================================================
# FILE: workflows/Generator/tools/echo_all.py
# DESCRIPTION: Simple echo tool registered for all agents
# ==============================================================================
from typing import Annotated

def echo(message: Annotated[str, "The message to echo back to the user"]) -> str:
    """Simple echo tool that returns the input message with an 'Echo:' prefix.
    
    Use this tool when you need to repeat, confirm, or acknowledge information
    provided by the user or another agent.
    """
    return f"Echo: {message}"
