"""Agent_Tool Tester.
Echo-style handler for `Agent_Tool` for ToolsManagerAgent.
"""

from typing import Annotated, Dict

TOOL_NAME = "echo"

async def echo(
    message: Annotated[str, "The message to echo back"]
) -> Dict[str, str]:
    """
    PURPOSE:
        A simple echo tool that returns the same message it receives.

    PARAMETERS:
        message (str): Any string input.

    RETURNS:
        Dict[str, str]: JSON-serializable dict with the echoed message.

    ERROR MODES:
        - Raises ValueError if message is not a string.

    SIDE EFFECTS:
        None – safe, idempotent.

    EXAMPLES:
        >>> await echo("hello")
        {"status": "ok", "echo": "hello"}
    """
    if not isinstance(message, str):
        raise ValueError("Parameter 'message' must be a string")

    return {"status": "ok", "echo": message}
