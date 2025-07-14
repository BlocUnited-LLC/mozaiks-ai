# ==============================================================================
# FILE: Generator/tools/echo_all.py  
# DESCRIPTION: Simple Echo tool that is registered for every agent
# ==============================================================================
import logging
biz_log = logging.getLogger("business.tools.echo_all")


def echo(*args, **kwargs):
    """
    Return (args, kwargs) unchanged and write one log line so you can
    see that the tool was called.
    """
    biz_log.info("echo_all called | args=%s | kwargs=%s", args, kwargs)
    return args, kwargs
