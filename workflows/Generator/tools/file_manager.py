# ==============================================================================
# FILE: workflows/Generator/tools/file_manager.py
# DESCRIPTION: Backend handler for FileDownloadCenter component interactions
# ==============================================================================

import logging
from typing import Dict, Any, Optional
from pathlib import Path
from autogen.agentchat.group import ContextVariables

# Import enhanced logging
from logs.logging_config import get_business_logger

business_logger = get_business_logger("generator_file_manager")

async def handle_download(data: Dict[str, Any], context_variables: Optional[ContextVariables] = None) -> Dict[str, Any]:
    """
    Handle file download requests from FileDownloadCenter component
    
    Args:
        data: Component action data containing file info
        context_variables: AG2 ContextVariables for sharing state between agents
        
    Returns:
        Response dictionary with status and updated context
    """
    try:
        action_type = data.get('type', 'unknown')
        business_logger.info(f"📥 File manager received action: {action_type}")
        
        if action_type == 'download':
            return await handle_single_download(data, context_variables)
        elif action_type == 'download_all':
            return await handle_bulk_download(data, context_variables)
        else:
            business_logger.warning(f"Unknown action type: {action_type}")
            return {"status": "error", "message": f"Unknown action: {action_type}"}
            
    except Exception as e:
        business_logger.error(f"File manager error: {e}")
        return {"status": "error", "message": str(e)}


async def handle_single_download(data: Dict[str, Any], context_variables: Optional[ContextVariables] = None) -> Dict[str, Any]:
    """Handle individual file download"""
    file_id = data.get('fileId')
    filename = data.get('filename')
    
    business_logger.info(f"📁 Processing download: {filename} (ID: {file_id})")
    
    # Update context variables to track download
    if context_variables:
        downloaded_files = context_variables.get('downloaded_files', [])
        if downloaded_files is None:
            downloaded_files = []
        
        downloaded_files.append({
            'file_id': file_id,
            'filename': filename,
            'download_time': str(Path(__file__).stat().st_mtime),  # Simple timestamp
            'status': 'completed'
        })
        context_variables.set('downloaded_files', downloaded_files)
        context_variables.set('last_download', filename)
        
        business_logger.info(f"📝 Updated context: {len(downloaded_files)} files downloaded")
    
    # Simulate file processing/download logic
    # In real implementation, this would handle actual file serving
    
    return {
        "status": "success",
        "message": f"File '{filename}' downloaded successfully",
        "file_id": file_id,
        "filename": filename
    }


async def handle_bulk_download(data: Dict[str, Any], context_variables: Optional[ContextVariables] = None) -> Dict[str, Any]:
    """Handle bulk download of all files"""
    files = data.get('files', [])
    
    business_logger.info(f"📦 Processing bulk download: {len(files)} files")
    
    downloaded_files = []
    for file_info in files:
        downloaded_files.append({
            'file_id': file_info.get('id'),
            'filename': file_info.get('name'),
            'download_time': str(Path(__file__).stat().st_mtime),
            'status': 'completed'
        })
    
    # Update context variables
    if context_variables:
        all_downloads = context_variables.get('downloaded_files', [])
        if all_downloads is None:
            all_downloads = []
        
        all_downloads.extend(downloaded_files)
        context_variables.set('downloaded_files', all_downloads)
        context_variables.set('bulk_download_count', len(files))
        context_variables.set('last_bulk_download_time', str(Path(__file__).stat().st_mtime))
        
        business_logger.info(f"📝 Updated context: bulk download of {len(files)} files completed")
    
    return {
        "status": "success", 
        "message": f"Successfully downloaded {len(files)} files",
        "download_count": len(files),
        "files": downloaded_files
    }


def get_download_status(context_variables: ContextVariables) -> Dict[str, Any]:
    """Helper to retrieve download status from context variables"""
    downloaded_files = context_variables.get('downloaded_files', [])
    if downloaded_files is None:
        downloaded_files = []
        
    return {
        'downloaded_files': downloaded_files,
        'last_download': context_variables.get('last_download'),
        'bulk_download_count': context_variables.get('bulk_download_count', 0),
        'total_downloads': len(downloaded_files)
    }
