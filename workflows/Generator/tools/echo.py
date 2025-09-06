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
        A simple test tool that always responds with 'Tool Works!!'.

    PARAMETERS:
        message (str): Unused; kept for interface compatibility.

    RETURNS:
        Dict[str, str]: JSON-serializable dict with the fixed message.

    ERROR MODES:
        - Raises ValueError if message is not a string (type guard).

    SIDE EFFECTS:
        None – safe, idempotent.

    EXAMPLES:
        >>> await echo("anything")
        {"status": "ok", "echo": "Tool Works!!"}
    """
    if not isinstance(message, str):
        raise ValueError("Parameter 'message' must be a string")

    return {"status": "ok", "echo": "Tool Works!!"}
