# ==============================================================================
# FILE: workflows/Generator/tools/request_file_download.py
# DESCRIPTION: File download request tool - single async function export
# NOTE: 'description' in the 'payload' must be a property to use to display the agent's instructions, making the whole system easier to extend.
# ==============================================================================

import asyncio
import uuid
import logging
from typing import Dict, Any, Optional, List, Union
from datetime import datetime
from pathlib import Path

# Import enhanced logging
from logs.logging_config import get_business_logger

business_logger = get_business_logger("generator_request_file_download")

class UIToolError(Exception):
    """Custom exception for UI tool errors"""
    pass

async def emit_ui_tool_event(
    tool_id: str,
    payload: Dict[str, Any],
    event_id: Optional[str] = None
) -> str:
    """
    Core function to emit UI tool events to the frontend.
    
    This follows the ag2_dynamicUI.md specification for workflow-agnostic event emission.
    """
    # Generate event ID if not provided
    if not event_id:
        event_id = f"{tool_id}_{str(uuid.uuid4())[:8]}"
    
    # Import transport to send events
    try:
        from core.transport.simple_transport import SimpleTransport
        transport = SimpleTransport()
    except ImportError:
        raise UIToolError("SimpleTransport not available for event emission")
    
    business_logger.info(f"🎯 [REQUEST_FILE_DOWNLOAD] Emitting UI tool event: {tool_id} (event: {event_id})")
    business_logger.debug(f"🔍 [REQUEST_FILE_DOWNLOAD] Event payload: {payload}")
    
    try:
        # Send the UI tool event through the transport system
        await transport.send_ui_tool_event(
            ui_tool_id=tool_id,
            payload=payload,
            display="inline"
        )
        
        business_logger.info(f"✅ [REQUEST_FILE_DOWNLOAD] Successfully emitted UI tool event: {event_id}")
        return event_id
        
    except Exception as e:
        business_logger.error(f"❌ [REQUEST_FILE_DOWNLOAD] Failed to emit UI tool event: {e}")
        raise UIToolError(f"Failed to emit UI tool event: {e}")

async def wait_for_ui_tool_response(event_id: str) -> Dict[str, Any]:
    """
    Wait indefinitely for a response from a UI tool event.
    No timeout - users can take their time to respond.
    """
    business_logger.info(f"⏳ [REQUEST_FILE_DOWNLOAD] Waiting for UI tool response: {event_id}")
    
    try:
        # Import here to avoid circular imports
        from core.transport.simple_transport import SimpleTransport
        
        # Wait indefinitely for the UI tool response - no timeout
        response = await SimpleTransport.wait_for_ui_tool_response(event_id)
        
        business_logger.info(f"✅ [REQUEST_FILE_DOWNLOAD] Received UI tool response: {event_id}")
        business_logger.debug(f"🔍 [REQUEST_FILE_DOWNLOAD] Response data: {response}")
        
        return response
        
    except Exception as e:
        business_logger.error(f"❌ [REQUEST_FILE_DOWNLOAD] Error waiting for UI tool response: {e}")
        raise UIToolError(f"Error waiting for UI tool response: {e}")

async def request_file_download(
    files: Union[str, List[Dict[str, Any]]],
    download_type: str = "single",
    description: Optional[str] = None
) -> Dict[str, Any]:
    """
    AG2 tool function to request file download from the user via UI.
    
    This tool emits a UI event that displays the AgentFileDownload component
    in the frontend and waits for the user's response.
    
    Args:
        files: Either a single filename string or list of file dictionaries with metadata
        download_type: "single" or "bulk" download
        description: Custom description for the download request
        
    Returns:
        Dict containing the download response data
        
    Raises:
        UIToolError: If the request fails or times out
    """
    business_logger.info(f"📥 [REQUEST_FILE_DOWNLOAD] Requesting file download: {download_type}")

    # DEV NOTE: The 'description' key is the standardized way to pass the agent's
    # contextual message to the corresponding UI component. All dynamic UI tools
    # should follow this convention.
    # Prepare payload for AgentFileDownload component
    if isinstance(files, str):
        # Single file as string
        payload = {
            "downloadType": "single",
            "filename": files,
            "description": description or f"Download {files}",
            "files": [{"name": files, "size": "Unknown"}]
        }
    else:
        # Multiple files or single file with metadata
        payload = {
            "downloadType": download_type,
            "files": files,
            "description": description or f"Download {len(files)} file(s)",
            "totalSize": sum(f.get('size', 0) for f in files if isinstance(f.get('size'), int))
        }
    
    # Emit the UI tool event
    event_id = await emit_ui_tool_event(
        tool_id="agent_file_download",  # Must match ui_event_processor.py toolId
        payload=payload
    )
    
    # Wait for user response
    response = await wait_for_ui_tool_response(event_id)
    
    business_logger.info(f"📥 [REQUEST_FILE_DOWNLOAD] File download request completed: {response.get('status', 'unknown')}")
    
    return response
