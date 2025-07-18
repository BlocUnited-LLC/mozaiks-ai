# ==============================================================================
# FILE: workflows/Generator/tools/echo_ctx_only.py
# DESCRIPTION: Context echo tool registered only for ContextVariablesAgent
# ==============================================================================
from typing import Annotated, Any

def echo_context(data: Annotated[Any, "Context data to echo and validate"]) -> str:
    """Echo context data with validation - registered only for ContextVariablesAgent.
    
    Use this tool to validate, confirm, or debug context data during workflow
    initialization and context variable processing.
    """
    return f"Context Echo: {data}"
