# ==============================================================================
# FILE: workflows/Generator/tools/handle_file_download.py
# DESCRIPTION: File download handler tool - single async function export
# ==============================================================================

import logging
from typing import Dict, Any, Optional
from pathlib import Path
from autogen.agentchat.group import ContextVariables

# Import enhanced logging
from logs.logging_config import get_business_logger

business_logger = get_business_logger("generator_handle_file_download")

async def handle_file_download(data: Dict[str, Any], context_variables: Optional[ContextVariables] = None) -> Dict[str, Any]:
    """
    Handle file download requests from AgentFileDownload component
    
    Args:
        data: Component action data containing download info
        context_variables: AG2 ContextVariables for sharing state between agents
        
    Returns:
        Response dictionary with status and updated context
    """
    try:
        action_type = data.get('type', 'unknown')
        download_type = data.get('downloadType', 'single')
        
        business_logger.info(f"📥 [HANDLE_FILE_DOWNLOAD] Received action: {action_type} (type: {download_type})")
        
        if action_type == 'download':
            if download_type == 'single':
                return await handle_single_download(data, context_variables)
            elif download_type == 'bulk':
                return await handle_bulk_download(data, context_variables)
            else:
                return {"status": "error", "message": f"Unknown download type: {download_type}"}
        elif action_type == 'cancel':
            return await handle_download_cancellation(data, context_variables)
        else:
            business_logger.warning(f"Unknown action type: {action_type}")
            return {"status": "error", "message": f"Unknown action: {action_type}"}
            
    except Exception as e:
        business_logger.error(f"[HANDLE_FILE_DOWNLOAD] Error: {e}")
        return {"status": "error", "message": str(e)}


async def handle_single_download(data: Dict[str, Any], context_variables: Optional[ContextVariables] = None) -> Dict[str, Any]:
    """Handle single file download"""
    filename = data.get('filename', 'unknown')
    selected_path = data.get('selectedPath', '')
    agent_id = data.get('agentId', 'unknown')
    
    business_logger.info(f"📄 [HANDLE_FILE_DOWNLOAD] Processing single download: {filename} to {selected_path}")
    
    # Update context variables to track download
    if context_variables:
        downloads = context_variables.get('file_downloads', [])
        if downloads is None:
            downloads = []
            
        download_record = {
            'type': 'single',
            'filename': filename,
            'path': selected_path,
            'agent_id': agent_id,
            'status': 'completed',
            'downloaded_at': str(__import__('time').time())
        }
        
        downloads.append(download_record)
        context_variables.set('file_downloads', downloads)
        context_variables.set('last_download', download_record)
        
        business_logger.info(f"📝 [HANDLE_FILE_DOWNLOAD] Recorded single download: {filename}")
    
    return {
        "status": "success",
        "message": f"File {filename} downloaded successfully",
        "filename": filename,
        "path": selected_path,
        "download_type": "single",
        "agent_id": agent_id
    }


async def handle_bulk_download(data: Dict[str, Any], context_variables: Optional[ContextVariables] = None) -> Dict[str, Any]:
    """Handle bulk file download"""
    files = data.get('files', [])
    selected_path = data.get('selectedPath', '')
    agent_id = data.get('agentId', 'unknown')
    
    file_count = len(files)
    business_logger.info(f"📦 [HANDLE_FILE_DOWNLOAD] Processing bulk download: {file_count} files to {selected_path}")
    
    # Update context variables to track bulk download
    if context_variables:
        downloads = context_variables.get('file_downloads', [])
        if downloads is None:
            downloads = []
            
        download_record = {
            'type': 'bulk',
            'files': [f.get('name', 'unknown') for f in files],
            'file_count': file_count,
            'path': selected_path,
            'agent_id': agent_id,
            'status': 'completed',
            'downloaded_at': str(__import__('time').time())
        }
        
        downloads.append(download_record)
        context_variables.set('file_downloads', downloads)
        context_variables.set('last_download', download_record)
        
        business_logger.info(f"📝 [HANDLE_FILE_DOWNLOAD] Recorded bulk download: {file_count} files")
    
    return {
        "status": "success",
        "message": f"Bulk download of {file_count} files completed successfully",
        "file_count": file_count,
        "files": files,
        "path": selected_path,
        "download_type": "bulk",
        "agent_id": agent_id
    }


async def handle_download_cancellation(data: Dict[str, Any], context_variables: Optional[ContextVariables] = None) -> Dict[str, Any]:
    """Handle download cancellation"""
    download_type = data.get('downloadType', 'single')
    agent_id = data.get('agentId', 'unknown')
    
    business_logger.info(f"❌ [HANDLE_FILE_DOWNLOAD] Download cancelled: {download_type} (Agent: {agent_id})")
    
    # Update context to track cancellation
    if context_variables:
        cancelled_downloads = context_variables.get('cancelled_downloads', [])
        if cancelled_downloads is None:
            cancelled_downloads = []
            
        cancelled_downloads.append({
            'type': download_type,
            'agent_id': agent_id,
            'cancelled_at': str(__import__('time').time())
        })
        
        context_variables.set('cancelled_downloads', cancelled_downloads)
        
        business_logger.info(f"📝 [HANDLE_FILE_DOWNLOAD] Recorded cancellation: {download_type}")
    
    return {
        "status": "cancelled",
        "message": f"Download was cancelled",
        "download_type": download_type,
        "agent_id": agent_id
    }
