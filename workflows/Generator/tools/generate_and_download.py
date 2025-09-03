# ==============================================================================
# FILE: workflows\Generator\tools\generate_and_download.py
# DESCRIPTION: Generate and download workflow files - single async function export
# NOTE: 'generate_and_download' function adheres to AGENT CONTRACT for tool integration. 
# ==============================================================================

from typing import Any, Dict, List, Optional, Union, Annotated
import json
import uuid
from pathlib import Path
import shutil
import time

from logs.logging_config import get_workflow_logger
from core.data.persistence_manager import AG2PersistenceManager
from core.workflow.ui_tools import use_ui_tool, UIToolError
from workflows.Generator.tools.workflow_converter import create_workflow_files

async def generate_and_download(
    description: Optional[str] = None,
    storage_backend: Annotated[str, "Persistence mode: 'local' copies files to user selectedPath; 'none' skips. Future: gridfs, github."] = "local",
    files: Annotated[Optional[Union[str, List[Dict[str, Any]]]], "Advanced override: custom file metadata list for UI. Provide list[{'name','size','path'}] or single path string. Generally omit."] = None,
    **runtime: Any,
) -> Dict[str, Any]:
    """AGENT CONTRACT: Generate workflow artifact files and present a download UI.

Primary Objective:
    Derive JSON / config artifact files from the latest persisted agent JSON outputs and
    present them to the user via the FileDownloadCenter UI component for download.

STRICT EXECUTION STEPS (do not reorder):
    1. Resolve chat_id, enterprise_id, workflow_name from runtime or context_variables; abort with status=error if missing ids.
    2. Gather freshest agent outputs via AG2PersistenceManager.gather_latest_agent_jsons (read-only).
    3. Build aggregation payload including (orchestrator_output, agents_output, handoffs_output,
         context_variables_output, structured_outputs) plus optional tools_config/ui_config/extra_files.
    4. Discover code_files patterns in ANY agent output and merge unique files into extra_files (dedupe by filename).
    5. Call create_workflow_files(payload, context_variables) to materialize files on disk. On failure return status=error.
    6. Construct UI file metadata list ONLY (name, size, path, id). NEVER return raw file contents.
    7. Emit FileDownloadCenter UI event (display='artifact') with correlation agent_message_id; await user response.
    8. If storage_backend == 'local' AND response.status == 'success', copy generated files to user-selectedPath.
    9. Return a dict containing: status, ui_response, agent_message_id, workflow_dir, files, ui_files (UI metadata), and optional storage result.

SECURITY / PRIVACY:
    - Never print or return file bodies; restrict to metadata.
    - Do not leak internal runtime/context variables beyond those required in return.
    - Gracefully continue discovery even if individual agent payloads are malformed.

ERROR HANDLING:
    - Missing chat_id or enterprise_id -> early status=error (no exception).
    - UI tool emission or wait failures -> raise UIToolError (caller decides retry policy).
    - File creation failure -> return status=error with message.

NON-GOALS / DECLINED BEHAVIORS:
    - Do not mutate source persistence data.
    - Do not introduce side-channel storage beyond optional local copy when requested.
    - Do not expand archive bundles (zipping not implemented here).
    """
    chat_id: Optional[str] = runtime.get("chat_id")
    enterprise_id: Optional[str] = runtime.get("enterprise_id")
    # Capture provided workflow name without default; missing should surface as error later.
    workflow_name: Optional[str] = runtime.get("workflow_name") or runtime.get("workflow")
    context_variables: Optional[Any] = runtime.get("context_variables")

    wf_logger = get_workflow_logger(workflow_name=(workflow_name or "missing"), chat_id=chat_id, enterprise_id=enterprise_id)
    wf_logger.info(f"🏗️ Starting workflow generation for chat: {chat_id}")

    agent_message = description or "I'm creating your workflow files. Please use the download center below when ready."
    agent_message_id = f"msg_{uuid.uuid4().hex[:10]}"
    print(agent_message)

    if (not chat_id or not enterprise_id) and context_variables is not None:
        try:
            chat_id = chat_id or context_variables.get("chat_id")
            enterprise_id = enterprise_id or context_variables.get("enterprise_id")
        except Exception:
            pass
    if not chat_id or not enterprise_id:
        return {"status": "error", "message": "chat_id and enterprise_id are required"}

    # 1. Gather latest agent JSON outputs
    pm = AG2PersistenceManager()
    collected = await pm.gather_latest_agent_jsons(chat_id=chat_id, enterprise_id=enterprise_id)
    wf_name = collected.get("workflow_name") or workflow_name
    if not wf_name:
        return {"status": "error", "message": "workflow_name missing (not provided and not in persistence)"}
    wf_logger = get_workflow_logger(workflow_name=wf_name, chat_id=chat_id, enterprise_id=enterprise_id)

    # 2. Build payload
    payload: Dict[str, Any] = {
        "workflow_name": wf_name,
        "orchestrator_output": collected.get("orchestrator_output", {}),
        "agents_output": collected.get("agents_output", {}),
        "handoffs_output": collected.get("handoffs_output", {}),
        "context_variables_output": collected.get("context_variables_output", {}),
        "structured_outputs": collected.get("structured_outputs", {}),
    }

    # Optional: integrate tools / ui config
    tools_manager = collected.get("ToolsManagerAgent") or collected.get("tools_manager_agent")
    if isinstance(tools_manager, dict):
        for k, key in (("tools_config", "tools_config"), ("ui_config", "ui_config")):
            val = tools_manager.get(key)
            if isinstance(val, str):
                try:
                    val = json.loads(val)
                except Exception:
                    val = None
            if isinstance(val, dict):
                payload[key] = val

    # UIToolsAgent + ToolsAgent extra files (both may contribute file stubs)
    ui_tools_agent = collected.get("UIToolsAgent") or collected.get("ui_tools_agent")
    std_tools_agent = collected.get("ToolsAgent") or collected.get("tools_agent")
    merged_extra: List[Dict[str, Any]] = []
    for agent_blob in (ui_tools_agent, std_tools_agent):
        if isinstance(agent_blob, dict):
            extra_files = agent_blob.get("files")
            if isinstance(extra_files, list):
                for f in extra_files:
                    if isinstance(f, dict):
                        merged_extra.append(f)
    if merged_extra:
        payload["extra_files"] = merged_extra

    # Generic discovery of code_files in any agent output
    def _discover_code_files(col: Dict[str, Any]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for agent_name, data in col.items():
            try:
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
                elif isinstance(data, str):
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
                continue
        return out

    discovered = _discover_code_files(collected)
    if discovered:
        existing = payload.get("extra_files", []) or []
        seen = {f.get("filename") for f in existing if isinstance(f, dict)}
        for item in discovered:
            fn = item.get("filename")
            if fn and fn not in seen:
                existing.append(item)
        if existing:
            payload["extra_files"] = existing

    # 3. Create workflow files
    create_res = await create_workflow_files(payload, context_variables)
    if create_res.get("status") != "success":
        return {"status": "error", "message": create_res.get("message", "Failed to create files")}

    # 4. Prepare UI file list
    def _format_bytes(num: int) -> str:
        # Simple human-readable bytes (KiB, MiB, GiB) with 1 decimal
        try:
            value: float = float(num)
            for unit in ['bytes', 'KB', 'MB', 'GB', 'TB']:
                if value < 1024 or unit == 'TB':
                    if unit == 'bytes':
                        # Show integer bytes
                        return f"{int(value)} bytes"
                    return f"{value:.1f} {unit}"
                value /= 1024.0
        except Exception:
            return f"{num} bytes"
        return f"{num} bytes"
    if files is None:
        created_files = create_res.get("files", [])
        workflow_dir = Path(create_res.get("workflow_dir", ""))
        ui_files: List[Dict[str, Any]] = []
        for f in created_files:
            fp = workflow_dir / f if workflow_dir.exists() else Path(f)
            size_bytes = fp.stat().st_size if fp.exists() else 0
            ui_files.append({
                "name": f,
                "size": _format_bytes(size_bytes),
                "size_bytes": size_bytes,
                "path": str(fp),
                "id": f"file-{len(ui_files)}",
            })
    else:
        if isinstance(files, str):
            ui_files = [{"name": files, "size": "unknown", "size_bytes": None, "id": "file-0"}]
        else:
            ui_files = []
            for i, item in enumerate(files):
                if isinstance(item, dict):
                    cp = item.copy()
                    cp.setdefault("id", f"file-{i}")
                    # Derive size_bytes if possible
                    if "size_bytes" not in cp:
                        sb = None
                        if isinstance(cp.get("size"), (int, float)):
                            sb = int(cp["size"])
                        elif isinstance(cp.get("size"), str):
                            digits = ''.join(ch for ch in cp["size"] if ch.isdigit())
                            if digits.isdigit():
                                try:
                                    sb = int(digits)
                                except Exception:
                                    sb = None
                        path_val = cp.get("path")
                        if sb is None and isinstance(path_val, str) and path_val:
                            try:
                                p = Path(path_val)
                                if p.exists():
                                    sb = p.stat().st_size
                            except Exception:
                                pass
                        cp["size_bytes"] = sb
                        if sb is not None and ("size" not in cp or cp.get("size") == "unknown"):
                            cp["size"] = _format_bytes(sb)
                    ui_files.append(cp)

    ui_payload = {
        "downloadType": "bulk" if len(ui_files) > 1 else "single",
        "files": ui_files,
        "description": description or "Your generated workflow files are ready for download.",
        "title": "Generated Workflow Files",
        "workflow_name": wf_name,
        "agent_message_id": agent_message_id,
    }

    # 5. Emit UI + wait
    try:
        response = await use_ui_tool(
            tool_id="FileDownloadCenter",
            payload=ui_payload,
            chat_id=chat_id,
            workflow_name=wf_name,
            display="artifact",
        )
        wf_logger.info(f"📥 File download UI completed with status: {response.get('status', 'unknown')}")
    except UIToolError:
        raise
    except Exception as e:
        wf_logger.error(f"❌ UI interaction failed: {e}", exc_info=True)
        raise UIToolError("Failed during file download UI interaction")

    # 6. Optional storage
    if storage_backend != "none" and isinstance(response, dict) and response.get("status") == "success":
        try:
            storage_result = await _handle_storage_action(
                storage_backend=storage_backend,
                response=response,
                created_files=create_res.get("files", []),
                workflow_dir=create_res.get("workflow_dir"),
                context_variables=context_variables,
                workflow_name=wf_name,
            )
            if storage_result:
                response = {**response, "storage": storage_result}
                wf_logger.info(f"✅ Storage completed: {storage_result.get('status')}")
        except Exception as se:
            wf_logger.warning(f"⚠️ Storage action failed: {se}")

    return {
        "status": "success",
        "ui_response": response,
        "agent_message_id": agent_message_id,
        "ui_files": ui_files,
        **create_res,
    }


async def _handle_storage_action(
    storage_backend: str,
    response: Dict[str, Any],
    created_files: List[str],
    workflow_dir: Optional[str],
    context_variables: Optional[Any] = None,
    workflow_name: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    if storage_backend == "local":
        return await _store_files_local(
            response=response,
            created_files=created_files,
            workflow_dir=workflow_dir,
            context_variables=context_variables,
            workflow_name=workflow_name,
        )
    if storage_backend == "none":
        return None
    return {"status": "error", "message": f"Unsupported storage backend: {storage_backend}"}


async def _store_files_local(
    response: Dict[str, Any],
    created_files: List[str],
    workflow_dir: Optional[str],
    context_variables: Optional[Any] = None,
    workflow_name: Optional[str] = None,
) -> Dict[str, Any]:
    selected_path = None
    if isinstance(response, dict):
        selected_path = response.get("selectedPath") or (
            response.get("data", {}).get("selectedPath") if isinstance(response.get("data"), dict) else None
        )
    if not selected_path:
        return {"status": "skipped", "message": "No selectedPath provided by UI"}
    if not created_files:
        return {"status": "skipped", "message": "No files to copy"}

    # Use workflow-specific storage logger
    wf_logger = get_workflow_logger(workflow_name=(workflow_name or "generator"), chat_id=None, enterprise_id=None)
    try:
        dest = Path(selected_path)
        dest.mkdir(parents=True, exist_ok=True)
        copied: List[str] = []
        base_dir = Path(workflow_dir) if workflow_dir else Path.cwd()
        for f in created_files:
            try:
                src = Path(f) if Path(f).is_absolute() else base_dir / f
                if src.exists():
                    target = dest / src.name
                    shutil.copy2(src, target)
                    copied.append(str(target))
                    wf_logger.info(f"📋 Copied {src.name} -> {target}")
            except Exception as e:
                wf_logger.warning(f"⚠️ Failed to copy {f}: {e}")
                continue

        if context_variables:
            try:
                downloads = context_variables.get('file_downloads', []) or []
                rec = {
                    'type': 'local_copy',
                    'files': copied,
                    'file_count': len(copied),
                    'dest_path': str(dest),
                    'copied_at': str(time.time()),
                    'source_files': created_files,
                }
                downloads.append(rec)
                context_variables.set('file_downloads', downloads)
                context_variables.set('last_download', rec)
            except Exception:
                pass

        return {
            "status": "success",
            "message": f"Copied {len(copied)} files to {selected_path}",
            "copied_files": copied,
            "dest_path": str(dest),
            "copy_count": len(copied),
        }
    except Exception as e:
        wf_logger.error(f"❌ Local storage failed: {e}")
        return {"status": "error", "message": f"Failed to copy files: {e}"}
