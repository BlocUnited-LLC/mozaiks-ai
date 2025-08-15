# ==============================================================================
# FILE: workflows/Generator/tools/request_file_download.py
# DESCRIPTION: File download request tool - single async function export
# NOTE: 'description' in the 'payload' must be a property to use to display the agent's instructions, making the whole system easier to extend.
# ==============================================================================

import asyncio
import uuid
import logging
from typing import Dict, Any, Optional, List, Union

# Import the centralized UI tool functions and exceptions
from core.workflow.ui_tools import emit_ui_tool_event, wait_for_ui_tool_response, UIToolError
from logs.logging_config import get_business_logger

business_logger = get_business_logger("generator_request_file_download")

async def request_file_download(
    files: Union[str, List[Dict[str, Any]]],
    download_type: str = "single",
    description: Optional[str] = None,
    workflow_name: str = "Generator",
    chat_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    AG2 tool function to request a file download from the user via a dynamic UI component.
    
    This tool follows the modern, modular pattern:
    1. It prints a message to the user, which appears in the chat log.
    2. It emits a UI tool event to render the 'FileDownloadCenter' component as an artifact.
    3. It waits for the user to interact with the component.
    
    Args:
        files: A list of file dictionaries or a single filename string.
        download_type: The type of download ("single" or "bulk").
        description: A message to display within the UI component.
        workflow_name: The name of the workflow initiating the request.
        chat_id: The ID of the current chat session.
        
    Returns:
        A dictionary containing the file download response data.
        
    Raises:
        UIToolError: If the UI interaction fails.
    """
    business_logger.info(f"📥 Requesting file download: {download_type} in chat {chat_id}")

    # 1. The agent "speaks" its request to the user via a standard print.
    agent_message = description or "I have prepared the files you requested. Please use the component below to download them."
    print(agent_message)

    # 2. Prepare the payload for the 'FileDownloadCenter' React component.
    if isinstance(files, str):
        file_list = [{"name": files, "size": "Unknown", "id": "file-0"}]
        component_description = f"Ready to download: {files}"
    else:
        # Multiple files or single file with metadata
        file_list = []
        if isinstance(files, list):
            for i, f in enumerate(files):
                if isinstance(f, dict):
                    # Create a copy and ensure it has a unique 'id' for the UI
                    f_copy = f.copy()
                    f_copy.setdefault("id", f"file-{i}")
                    file_list.append(f_copy)
        component_description = description or f"Ready to download {len(file_list)} file(s)."

    payload = {
        "downloadType": download_type,
        "files": file_list,
        "description": component_description,
        "title": "File Download Center"
    }
    
    try:
        # 3. Emit the UI tool event to render the component and wait for the response.
        event_id = await emit_ui_tool_event(
            tool_id="FileDownloadCenter",  # This MUST match the React component's name
            payload=payload,
            display="artifact",  # Rendered in the artifact panel, not inline
            chat_id=chat_id,
            workflow_name=workflow_name
        )
        
        response = await wait_for_ui_tool_response(event_id)
        
        business_logger.info(f"📥 File download request completed with status: {response.get('status', 'unknown')}")
        
        # Return the data submitted by the user from the UI component
        return response
    except UIToolError as e:
        business_logger.error(f"❌ UI tool interaction failed during file download: {e}")
        # Re-raise the error to be handled by the agent's error handling mechanism
        raise
    except Exception as e:
        business_logger.error(f"❌ An unexpected error occurred during file download request: {e}", exc_info=True)
        # Wrap unexpected errors in UIToolError to standardize error handling
        raise UIToolError(f"An unexpected error occurred while requesting the file download.")

