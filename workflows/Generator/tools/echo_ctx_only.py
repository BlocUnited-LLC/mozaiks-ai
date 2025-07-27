# ==============================================================================
# FILE: workflows/Generator/tools/echo_ctx_only.py
# DESCRIPTION: Context echo tool registered only for ContextVariablesAgent
# ==============================================================================
from typing import Annotated, Any

async def echo_context(data: Annotated[Any, "Context data to echo and validate"]) -> str:
    """Echo context data with validation - registered only for ContextVariablesAgent.
    """
    return f"Context Echo: {data}"
