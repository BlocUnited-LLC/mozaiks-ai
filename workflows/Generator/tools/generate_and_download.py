"""
Unified Generator tool: gather outputs -> create YAML files -> open download UI and await user action.
Consolidates all file generation, UI interaction, and storage logic in one tool.
"""
from typing import Any, Dict, List, Optional, Union
import json
from pathlib import Path
import shutil
import time

from logs.logging_config import get_workflow_logger
from core.data.persistence_manager import AG2PersistenceManager
from core.workflow.ui_tools import emit_ui_tool_event, wait_for_ui_tool_response, UIToolError

from .workflow_converter import create_workflow_files

_DEFAULT_WORKFLOW_NAME = "Generator"

# Tool name constant
TOOL_NAME = "generate_and_download"


async def generate_and_download(
    *,
    chat_id: Optional[str] = None,
    enterprise_id: Optional[str] = None,
    workflow_name: Optional[str] = None,
    files: Optional[Union[str, List[Dict[str, Any]]]] = None,
    description: Optional[str] = None,
    storage_backend: str = "local",
    context_variables: Optional[Any] = None,
) -> Dict[str, Any]:
    """Consolidated workflow file generation and download tool.

    This tool follows the modern, unified pattern like request_api_key:
    1. Gathers latest agent JSON outputs from persistence
    2. Creates modular YAML files for the workflow  
    3. Renders FileDownloadCenter UI and waits for user interaction
    4. Performs storage action based on UI response and storage_backend setting

    Args:
        chat_id: Chat session ID
        enterprise_id: Enterprise ID  
        workflow_name: Optional workflow name override
        files: Optional file list override (uses created files by default)
        description: Message for the UI component
        storage_backend: "local" | "none" (future: "gridfs", "github")
        context_variables: AG2 context variables

    Returns:
        Dictionary with status, UI response, created files, and optional storage results
    """
    wf_logger = get_workflow_logger(workflow_name=workflow_name or _DEFAULT_WORKFLOW_NAME, chat_id=chat_id, enterprise_id=enterprise_id)
    wf_logger.info(f"🏗️ Starting workflow generation for chat: {chat_id}")
    
    # 1. The agent "speaks" its intention to the user via print
    agent_message = description or "I'm creating your workflow files. Please use the download center below when ready."
    print(agent_message)
    # Resolve identifiers from context if missing
    if (not chat_id or not enterprise_id) and context_variables is not None:
        try:
            chat_id = chat_id or context_variables.get("chat_id")
            enterprise_id = enterprise_id or context_variables.get("enterprise_id")
        except Exception:
            pass

    if not chat_id or not enterprise_id:
        return {"status": "error", "message": "chat_id and enterprise_id are required"}

    # 2. Gather outputs and create workflow files
    pm = AG2PersistenceManager()
    collected = await pm.gather_latest_agent_jsons(chat_id=chat_id, enterprise_id=enterprise_id)

    wf_name = collected.get("workflow_name") or workflow_name or "Generated_Workflow"
    # refresh logger with resolved workflow name
    wf_logger = get_workflow_logger(workflow_name=wf_name or _DEFAULT_WORKFLOW_NAME, chat_id=chat_id, enterprise_id=enterprise_id)

    payload: Dict[str, Any] = {
        "workflow_name": wf_name,
        "orchestrator_output": collected.get("orchestrator_output", {}),
        "agents_output": collected.get("agents_output", {}),
        "handoffs_output": collected.get("handoffs_output", {}),
        "context_variables_output": collected.get("context_variables_output", {}),
        "structured_outputs": collected.get("structured_outputs", {}),
    }

    # Integrate ToolsManagerAgent outputs if present
    tools_manager = None
    try:
        tools_manager = collected.get("ToolsManagerAgent") or collected.get("tools_manager_agent")
    except Exception:
        tools_manager = None
    if isinstance(tools_manager, dict):
        tc = tools_manager.get("tools_config")
        uc = tools_manager.get("ui_config")
        # Accept dict or JSON string
        if isinstance(tc, str):
            try:
                tc = json.loads(tc)
            except Exception:
                tc = None
        if isinstance(uc, str):
            try:
                uc = json.loads(uc)
            except Exception:
                uc = None
        if isinstance(tc, dict):
            payload["tools_config"] = tc
        if isinstance(uc, dict):
            payload["ui_config"] = uc

    tools_agent = None
    try:
        tools_agent = collected.get("ToolsAgent") or collected.get("tools_agent")
    except Exception:
        tools_agent = None
    if isinstance(tools_agent, dict):
        extra_files = tools_agent.get("files")
        if isinstance(extra_files, list) and extra_files:
            payload["extra_files"] = extra_files

    # Scan collected agent outputs for generic code_files patterns and merge into extra_files
    def _collect_code_files_from_outputs(col: Dict[str, Any]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        try:
            for agent_name, data in col.items():
                if not isinstance(data, (dict, list, str)):
                    continue
                # Direct dict with code_files
                if isinstance(data, dict):
                    cf = data.get("code_files")
                    if isinstance(cf, list):
                        for item in cf:
                            if isinstance(item, dict) and item.get("filename") and item.get("content"):
                                out.append({
                                    "filename": str(item["filename"]),
                                    "filecontent": str(item["content"]),
                                    "purpose": f"from {agent_name}",
                                })
                # String that might be JSON containing code_files
                if isinstance(data, str):
                    try:
                        parsed = json.loads(data)
                        if isinstance(parsed, dict) and isinstance(parsed.get("code_files"), list):
                            for item in parsed.get("code_files", []):
                                if isinstance(item, dict) and item.get("filename") and item.get("content"):
                                    out.append({
                                        "filename": str(item["filename"]),
                                        "filecontent": str(item["content"]),
                                        "purpose": f"from {agent_name}",
                                    })
                    except Exception:
                        pass
        except Exception:
            return out
        return out

    discovered_code_files = _collect_code_files_from_outputs(collected)
    if discovered_code_files:
        existing = payload.get("extra_files", []) or []
        # Deduplicate by filename preference: ToolsAgent wins
        seen = {ef.get("filename"): True for ef in existing if isinstance(ef, dict)}
        for cf in discovered_code_files:
            fname = cf.get("filename")
            if fname and fname not in seen:
                existing.append(cf)
        if existing:
            payload["extra_files"] = existing

    # Create files first; if it fails, bubble up the error
    create_res = await create_workflow_files(payload, context_variables)
    if create_res.get("status") != "success":
        return {"status": "error", "message": create_res.get("message", "Failed to create files")}

    # 3. Prepare UI payload with created files
    ui_files: Union[str, List[Dict[str, Any]]] = []
    if files is None:
        # Use the created YAML files by default
        created_files = create_res.get("files", [])
        # Convert to full paths for accurate file info
        workflow_dir = Path(create_res.get("workflow_dir", ""))
        tmp_list: List[Dict[str, Any]] = []
        for f in created_files:
            file_path = workflow_dir / f if workflow_dir.exists() else Path(f)
            size = file_path.stat().st_size if file_path.exists() else 0
            tmp_list.append({"name": f, "size": f"{size} bytes", "path": str(file_path)})
        ui_files = tmp_list
    else:
        # files is not None here by branch; accept str or list override
        ui_files = files

    if isinstance(ui_files, str):
        file_list = [{"name": ui_files, "size": "unknown", "id": "file-0"}]
    else:
        # Ensure list of dicts each with an id
        file_list = []
        if isinstance(ui_files, list):
            for i, f in enumerate(ui_files):
                if isinstance(f, dict):
                    item = f.copy()
                    item.setdefault("id", f"file-{i}")
                    file_list.append(item)

    ui_payload = {
        "downloadType": "bulk" if len(file_list) > 1 else "single",
        "files": file_list,
        "description": description or "Your generated workflow files are ready for download.",
        "title": "Generated Workflow Files",
        "workflow_name": wf_name,
    }

    # 4. Emit UI and wait for response
    try:
        event_id = await emit_ui_tool_event(
            tool_id="FileDownloadCenter",
            payload=ui_payload,
            display="artifact",
            chat_id=chat_id,
            workflow_name=workflow_name or "Generator",
        )
        response = await wait_for_ui_tool_response(event_id)

        wf_logger.info(f"📥 File download UI completed with status: {response.get('status', 'unknown')}")

        # 5. Perform storage action based on storage_backend and UI response
        storage_result = None
        if storage_backend != "none" and isinstance(response, dict) and response.get("status") == "success":
            try:
                storage_result = await _handle_storage_action(
                    storage_backend=storage_backend,
                    response=response,
                    created_files=create_res.get("files", []),
                    workflow_dir=create_res.get("workflow_dir"),
                    context_variables=context_variables
                )
                if storage_result:
                    response = {**response, "storage": storage_result}
                    wf_logger.info(f"✅ Storage completed: {storage_result.get('status')}")
            except Exception as se:
                wf_logger.warning(f"⚠️ Storage action failed: {se}")

        return {"status": "success", "ui_response": response, **create_res}
    except UIToolError as e:
        wf_logger.error(f"❌ UI flow failed: {e}")
        raise
    except Exception as e:
        wf_logger.error(f"❌ An unexpected error occurred during file generation: {e}", exc_info=True)
        raise UIToolError(f"An unexpected error occurred while generating workflow files.")


async def _handle_storage_action(
    storage_backend: str,
    response: Dict[str, Any], 
    created_files: List[str],
    workflow_dir: Optional[str],
    context_variables: Optional[Any] = None
) -> Optional[Dict[str, Any]]:
    """Handle storage action based on backend type and UI response."""
    
    if storage_backend == "local":
        return await _store_files_local(response, created_files, workflow_dir, context_variables)
    elif storage_backend == "gridfs":
        # Future: implement GridFS storage
        return {"status": "error", "message": "GridFS storage not yet implemented"}
    elif storage_backend == "github":
        # Future: implement GitHub storage  
        return {"status": "error", "message": "GitHub storage not yet implemented"}
    else:
        return {"status": "error", "message": f"Unknown storage backend: {storage_backend}"}


async def _store_files_local(
    response: Dict[str, Any],
    created_files: List[str], 
    workflow_dir: Optional[str],
    context_variables: Optional[Any] = None
) -> Dict[str, Any]:
    """Store files to local filesystem based on UI response."""
    
    # Extract selectedPath from UI response (top-level or nested under data)
    selected_path = None
    if isinstance(response, dict):
        selected_path = response.get("selectedPath") or (
            response.get("data", {}).get("selectedPath") if isinstance(response.get("data"), dict) else None
        )
    
    if not selected_path:
        return {"status": "skipped", "message": "No selectedPath provided by UI"}
    
    if not created_files:
        return {"status": "skipped", "message": "No files to copy"}
    
    try:
        dest = Path(selected_path)
        dest.mkdir(parents=True, exist_ok=True)
        copied: List[str] = []
        base_dir = Path(workflow_dir) if workflow_dir else Path.cwd()
        
        for f in created_files:
            try:
                # Handle both relative and absolute paths
                src = Path(f) if Path(f).is_absolute() else base_dir / f
                if src.exists():
                    target = dest / src.name
                    shutil.copy2(src, target)
                    copied.append(str(target))
                    wf_logger = get_workflow_logger(workflow_name=create_workflow_files.__name__ if isinstance(create_workflow_files, object) else _DEFAULT_WORKFLOW_NAME, chat_id=None)
                    wf_logger.info(f"📋 Copied {src.name} to {target}")
            except Exception as e:
                wf_logger = get_workflow_logger(workflow_name=_DEFAULT_WORKFLOW_NAME)
                wf_logger.warning(f"⚠️ Failed to copy {f}: {e}")
                # Best-effort: continue with other files
                continue
        
        # Update context variables to track the copy operation
        if context_variables:
            try:
                downloads = context_variables.get('file_downloads', []) or []
                download_record = {
                    'type': 'local_copy',
                    'files': copied,
                    'file_count': len(copied),
                    'dest_path': str(dest),
                    'copied_at': str(time.time()),
                    'source_files': created_files
                }
                downloads.append(download_record)
                context_variables.set('file_downloads', downloads)
                context_variables.set('last_download', download_record)
            except Exception:
                # Non-fatal context update failure
                pass
        
        return {
            "status": "success",
            "message": f"Copied {len(copied)} files to {selected_path}",
            "copied_files": copied,
            "dest_path": str(dest),
            "copy_count": len(copied)
        }
        
    except Exception as e:
        wf_logger = get_workflow_logger(workflow_name=_DEFAULT_WORKFLOW_NAME)
        wf_logger.error(f"❌ Local storage failed: {e}")
        return {"status": "error", "message": f"Failed to copy files: {e}"}


def get_tool_config() -> Dict[str, Any]:
    """Return tool configuration for AG2 registration"""
    return {
        "name": TOOL_NAME,
        "description": "Generate workflow files and open download UI",
        "version": "1.0.0",
        "type": "ui_tool",
        "python_callable": "workflows.Generator.tools.generate_and_download.generate_and_download",
        "tags": ["ui", "interactive", "download", "artifact", "workflow", "generation"],
        "expects_ui": True,
        "component_type": "artifact"
    }


__all__ = ["generate_and_download"]
