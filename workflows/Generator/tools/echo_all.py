# ==============================================================================
# FILE: Generator/tools/echo_all.py  
# DESCRIPTION: Simple Echo tool that is registered for every agent
# ==============================================================================
import logging
from typing import Annotated

biz_log = logging.getLogger("business.tools.echo_all")

# AG2-compatible configuration - this tells our system which agents get this tool
APPLY_TO = "all"  # Register this tool on all agents


def echo(
    message: Annotated[str, "The message to echo back"]
) -> str:
    """
    Return the message unchanged and write one log line so you can
    see that the tool was called.
    
    This is a simple echo tool that demonstrates basic AG2 tool functionality.
    """
    biz_log.info("echo_all called | message=%s", message)
    return f"Echo: {message}"
