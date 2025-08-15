# ==============================================================================
# FILE: workflows/Generator/tools/request_api_key.py
# DESCRIPTION: API key request tool - single async function export
# NOTE: 'description' in the 'payload' must be a property to use to display the agent's instructions, making the whole system easier to extend.
# ==============================================================================

import logging
from typing import Dict, Any, Optional

# Import the centralized UI tool functions and exceptions
from core.workflow.ui_tools import emit_ui_tool_event, wait_for_ui_tool_response, UIToolError

# Import enhanced logging
from logs.logging_config import get_business_logger

business_logger = get_business_logger("generator_request_api_key")

async def request_api_key(
    service: str,
    description: Optional[str] = None,
    label: Optional[str] = None,
    placeholder: Optional[str] = None,
    required: bool = True,
    workflow_name: str = "generator",
    chat_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    AG2 tool function to request an API key from the user via a dynamic UI component.
    
    This tool follows the modern, modular pattern:
    1. It prints a message to the user, which appears in the chat log.
    2. It emits a UI tool event to render the 'AgentAPIKeyInput' component.
    3. It waits for the user to submit their key via the component.
    
    Args:
        service: The service name (e.g., "openai", "anthropic").
        description: A message to display within the UI component.
        label: The label for the input field in the UI component.
        placeholder: The placeholder text for the input field.
        required: Whether the API key is required.
        workflow_name: The name of the workflow initiating the request.
        chat_id: The ID of the current chat session.
        
    Returns:
        A dictionary containing the API key response data.
        
    Raises:
        UIToolError: If the UI interaction fails.
    """
    business_logger.info(f"🔑 Requesting API key for service: {service} in chat: {chat_id}")
    
    # 1. The agent "speaks" its request to the user via a standard print.
    # This message appears in the main chat log.
    agent_message = description or f"I need your {service.replace('_', ' ').title()} API key to proceed. Please enter it in the component below."
    print(agent_message)

    # 2. Prepare the payload for the 'AgentAPIKeyInput' React component.
    # The 'description' here is for the component itself, not the chat message.
    payload = {
        "service": service,
        "label": label or f"{service.replace('_', ' ').title()} API Key",
        "description": f"Please enter the API key for {service}.",
        "placeholder": placeholder or f"Your {service.upper()} API key",
        "required": required
    }
    
    try:
        # 3. Emit the UI tool event to render the component and wait for the response.
        event_id = await emit_ui_tool_event(
            tool_id="AgentAPIKeyInput",  # This MUST match the React component's name
            payload=payload,
            display="inline",
            chat_id=chat_id,
            workflow_name=workflow_name
        )
        
        response = await wait_for_ui_tool_response(event_id)
        
        business_logger.info(f"🔑 API key request for {service} completed with status: {response.get('status', 'unknown')}")
        
        # Return the data submitted by the user from the UI component
        return response
    except UIToolError as e:
        business_logger.error(f"❌ UI tool interaction failed for service {service}: {e}")
        # Re-raise the error to be handled by the agent's error handling mechanism
        raise
    except Exception as e:
        business_logger.error(f"❌ An unexpected error occurred during API key request for {service}: {e}", exc_info=True)
        # Wrap unexpected errors in UIToolError to standardize error handling
        raise UIToolError(f"An unexpected error occurred while requesting the API key for {service}.")