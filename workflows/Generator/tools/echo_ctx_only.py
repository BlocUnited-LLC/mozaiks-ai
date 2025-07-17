# ==============================================================================
# FILE: Generator/tools/echo_ctx_only.py  
# DESCRIPTION: Simple Echo tool registered only for ContextVariablesAgent
# ==============================================================================
import logging
from typing import Annotated, Any

biz_log = logging.getLogger("business.tools.echo_ctx_only")

# AG2-compatible configuration - this tells our system which agents get this tool
APPLY_TO = ["ContextVariablesAgent"]  # Register only for ContextVariablesAgent


def echo_context(
    data: Annotated[Any, "Context data to echo back"]
) -> Any:
    """
    Echo context data - registered only for ContextVariablesAgent.
    
    This tool demonstrates agent-specific tool registration.
    
    Args:
        data: Context data to echo back
        
    Returns:
        The same data that was passed in
    """
    biz_log.info("echo_ctx_only called | data_type=%s | len=%s", type(data).__name__, len(str(data)))
    return data
