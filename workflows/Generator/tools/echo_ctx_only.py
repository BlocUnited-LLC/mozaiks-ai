# ==============================================================================
# FILE: Generator/tools/echo_ctx_only.py  
# DESCRIPTION: Simple Echo tool registered only for ContextVariablesAgent
# ==============================================================================
import logging
biz_log = logging.getLogger("business.tools.echo_ctx_only")


def echo_context(data):
    """
    Echo context data - registered only for ContextVariablesAgent.
    
    Args:
        data: Context data to echo back
        
    Returns:
        The same data that was passed in
    """
    biz_log.info("echo_ctx_only called | len=%s", len(str(data)))
    return data
