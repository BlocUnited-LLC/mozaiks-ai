# ==============================================================================
# FILE: workflows/Generator/tools/echo_all.py
# DESCRIPTION: Simple echo tool registered for all agents
# ==============================================================================
from typing import Annotated

async def echo(message: Annotated[str, "Context data to echo and validate"]) -> str:
    """Simple echo tool that returns the input message with an 'Echo:' prefix.
    """
    return f"Echo: {message}"
