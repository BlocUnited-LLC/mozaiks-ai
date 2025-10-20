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
from core.data.persistence.persistence_manager import AG2PersistenceManager
from core.workflow.outputs.ui_tools import use_ui_tool, UIToolError
from workflows.Generator.tools.workflow_converter import create_workflow_files
try:
    from logs.tools_logs import get_tool_logger as _get_tool_logger, log_tool_event as _log_tool_event  # type: ignore
except Exception:
    _get_tool_logger = None  # type: ignore
    _log_tool_event = None  # type: ignore

async def generate_and_download(
    agent_message: Annotated[Optional[str], "Short sentence shown with confirmation UI."] = None,
    description: Optional[str] = None,
    storage_backend: Annotated[str, "'local' copies after confirm; 'none' disables copy."] = "local",
    files: Annotated[Optional[Union[str, List[Dict[str, Any]]]], "(Legacy) Pre-supplied file metadata list."] = None,
    confirmation_only: Annotated[bool, "If true, ask user Yes/No before creating files."] = True,
    prebuild: Annotated[bool, "If true AND confirmation_only, still pre-create files for immediate availability (legacy behavior)."] = False,
    context_variables: Annotated[Optional[Any], "Injected runtime context."] = None,
) -> Dict[str, Any]:
    """AGENT CONTRACT (Two-Phase Compatible): Prompt user to confirm download; only build artifacts upon confirmation.

Execution Modes:
  A) confirmation_only=True (default):
     1) Collect high-level metadata only.
     2) Emit inline confirmation (Yes/No) via FileDownloadCenter.
     3) On 'confirm_download' (Yes): create files, optionally copy to storage, return success + file list.
     4) On 'decline_download' (No): return cancelled.
  B) confirmation_only=False: Preserve legacy single-phase behavior (build first, then UI) — used for backward compatibility.

Security & Constraints:
  - Never return raw file content.
  - Metadata only: names, sizes, paths after creation.
  - Graceful handling of malformed persisted outputs.

Error Handling:
  - Missing IDs -> early error result (status=error).
  - UI emission failure -> UIToolError.
  - File creation failure -> status=error.

Parameters:
  confirmation_only: Enables new lightweight confirmation UX.
  prebuild: Allows building files before confirmation (optimization / legacy bridging).
  storage_backend: Local copy only performed after user confirmation success.
    """
    # Extract parameters from AG2 ContextVariables
    chat_id: Optional[str] = None
    enterprise_id: Optional[str] = None
    workflow_name: Optional[str] = None
    
    if context_variables and hasattr(context_variables, 'get'):
        chat_id = context_variables.get('chat_id')
        enterprise_id = context_variables.get('enterprise_id')
        workflow_name = context_variables.get('workflow_name')

    wf_logger = get_workflow_logger(workflow_name=(workflow_name or "missing"), chat_id=chat_id, enterprise_id=enterprise_id)
    tlog = None
    if _get_tool_logger:
        try:
            tlog = _get_tool_logger(tool_name="GenerateAndDownload", chat_id=chat_id, enterprise_id=enterprise_id, workflow_name=(workflow_name or "missing"))
            if _log_tool_event:
                _log_tool_event(tlog, action="start", status="ok")
        except Exception:
            tlog = None
    wf_logger.info(f"🏗️ Starting generate_and_download (confirmation_only={confirmation_only}, prebuild={prebuild}) chat: {chat_id}")

    agent_message_text = agent_message or description or (
        "Would you like to download the generated workflow bundle now?"
        if confirmation_only else
        "Preparing your workflow files. Use the download panel when ready."
    )
    agent_message_id = f"msg_{uuid.uuid4().hex[:10]}"
    print(agent_message_text)

    if not chat_id or not enterprise_id:
        return {"status": "error", "message": "chat_id and enterprise_id are required"}

    # PHASE 1: Gather latest agent JSON outputs (always needed for metadata or file creation)
    pm = AG2PersistenceManager()
    collected = await pm.gather_latest_agent_jsons(chat_id=chat_id, enterprise_id=enterprise_id)
    wf_name = collected.get("workflow_name") or workflow_name
    if not wf_name:
        return {"status": "error", "message": "workflow_name missing (not provided and not in persistence)"}
    wf_logger = get_workflow_logger(workflow_name=wf_name, chat_id=chat_id, enterprise_id=enterprise_id)

    # Build aggregation payload (used later if/when we create files)
    # Map all Generator workflow agent outputs according to structured_outputs.json registry
    payload: Dict[str, Any] = {
        "workflow_name": wf_name,
    }
    
    # Map agent outputs by their structured output names
    # OrchestratorAgent -> OrchestratorAgentOutput
    orchestrator_data = collected.get("OrchestratorAgent") or collected.get("orchestrator_output", {})
    if isinstance(orchestrator_data, dict):
        payload["orchestrator_output"] = orchestrator_data
    
    # AgentsAgent -> AgentsAgentOutput  
    agents_data = collected.get("AgentsAgent") or collected.get("agents_output", {})
    if isinstance(agents_data, dict):
        payload["agents_output"] = agents_data
    
    # HandoffsAgent -> HandoffsAgentOutput
    handoffs_data = collected.get("HandoffsAgent") or collected.get("handoffs_output", {})
    if isinstance(handoffs_data, dict):
        payload["handoffs_output"] = handoffs_data
    
    # ContextVariablesAgent -> ContextVariablesAgentOutput
    context_vars_data = collected.get("ContextVariablesAgent") or collected.get("context_variables_output", {})
    if isinstance(context_vars_data, dict):
        payload["context_variables_output"] = context_vars_data
    
    # ToolsManagerAgent -> ToolsManagerAgentOutput (tools + lifecycle_tools manifest)
    tools_manager_data = collected.get("ToolsManagerAgent") or collected.get("tools_manager_output", {})
    if isinstance(tools_manager_data, dict):
        payload["tools_manager_output"] = tools_manager_data
    
    # UIFileGenerator -> UIFileGeneratorOutput (UI tool implementations)
    ui_file_gen_data = collected.get("UIFileGenerator") or collected.get("ui_file_generator_output", {})
    if isinstance(ui_file_gen_data, dict):
        payload["ui_file_generator_output"] = ui_file_gen_data
    
    # AgentToolsFileGenerator -> AgentToolsFileGeneratorOutput (agent tools + lifecycle tools)
    agent_tools_data = collected.get("AgentToolsFileGenerator") or collected.get("agent_tools_file_generator_output", {})
    if isinstance(agent_tools_data, dict):
        payload["agent_tools_file_generator_output"] = agent_tools_data
    
    # HookAgent -> HookAgentOutput (lifecycle hooks metadata + files)
    hooks_data = collected.get("HookAgent") or collected.get("hooks_output", {})
    if isinstance(hooks_data, dict):
        payload["hooks_output"] = hooks_data
    
    # StructuredOutputsAgent -> StructuredOutputsAgentOutput (dynamic models)
    structured_dynamic = collected.get("StructuredOutputsAgent") or collected.get("structured_outputs_agent_output", {})
    if isinstance(structured_dynamic, dict):
        payload["structured_outputs_agent_output"] = structured_dynamic
    
    # Static structured outputs from Generator workflow itself
    static_structured = collected.get("structured_outputs", {})
    if isinstance(static_structured, dict):
        payload["structured_outputs"] = static_structured
    
    # UI Config (visual_agents, visual_agent arrays)
    ui_config_data = collected.get("ui_config", {})
    if isinstance(ui_config_data, dict):
        payload["ui_config"] = ui_config_data

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

    # Decide whether to prebuild files BEFORE asking (legacy compatibility)
    create_res: Dict[str, Any] = {}
    ui_files: List[Dict[str, Any]] = []
    workflow_dir: Optional[Path] = None

    def _format_bytes(num: int) -> str:  # local helper (moved earlier for dual-phase use)
        try:
            value: float = float(num)
            for unit in ['bytes', 'KB', 'MB', 'GB', 'TB']:
                if value < 1024 or unit == 'TB':
                    if unit == 'bytes':
                        return f"{int(value)} bytes"
                    return f"{value:.1f} {unit}"
                value /= 1024.0
        except Exception:
            return f"{num} bytes"
        return f"{num} bytes"

    if not confirmation_only or (confirmation_only and prebuild):
        # Build now (legacy single-phase or optimized confirmation)
        create_res = await create_workflow_files(payload, context_variables)
        if create_res.get("status") != "success":
            return {"status": "error", "message": create_res.get("message", "Failed to create files")}
        created_files = create_res.get("files", [])
        workflow_dir = Path(create_res.get("workflow_dir", "")) if create_res.get("workflow_dir") else None
        for f in created_files:
            fp = (workflow_dir / f) if workflow_dir and workflow_dir.exists() else Path(f)
            size_bytes = fp.stat().st_size if fp.exists() else 0
            ui_files.append({
                "name": f,
                "size": _format_bytes(size_bytes),
                "size_bytes": size_bytes,
                "path": str(fp),
                "id": f"file-{len(ui_files)}",
            })
    else:
        # Defer file creation until user confirms; minimal metadata only
        ui_files = []

    # Prepare initial UI payload (confirmation-focused when confirmation_only True)
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
    if files is not None and ui_files:  # legacy override path still allowed
        pass  # ui_files already populated

    ui_payload = {
        "downloadType": "bulk" if len(ui_files) > 1 else "single",
        "files": ui_files,  # empty list if waiting for confirmation
        "agent_message": agent_message_text,
        "description": agent_message_text,
        "title": "Workflow Bundle Ready" if confirmation_only else "Generated Workflow Files",
        "workflow_name": wf_name,
        "agent_message_id": agent_message_id,
    }

    # 5. Emit UI + wait (display mode auto-resolved from tools.json)
    try:
        if tlog and _log_tool_event:
            _log_tool_event(tlog, action="emit_ui", status="start", agent_message_id=agent_message_id)
        response = await use_ui_tool(
            tool_id="FileDownloadCenter",
            payload=ui_payload,
            chat_id=chat_id,
            workflow_name=wf_name,
            # display parameter omitted - auto-resolved from tools.json
        )
        wf_logger.info(f"📥 File download UI completed with status: {response.get('status', 'unknown')}")
        if tlog and _log_tool_event:
            _log_tool_event(tlog, action="emit_ui", status="done", result_status=response.get('status', 'unknown'))
    except UIToolError:
        raise
    except Exception as e:
        wf_logger.error(f"❌ UI interaction failed: {e}", exc_info=True)
        raise UIToolError("Failed during file download UI interaction")

    # If confirmation_only and user declined -> return early
    if confirmation_only and response.get("status") == "cancelled":
        return {
            "status": "cancelled",
            "ui_response": response,
            "agent_message_id": agent_message_id,
            "ui_files": [],
            "message": "User declined download",
        }

    # If confirmation_only and we have not yet created files (and user confirmed)
    if confirmation_only and not prebuild:
        wf_logger.info("🛠️ User confirmed download; creating files now...")
        create_res = await create_workflow_files(payload, context_variables)
        if create_res.get("status") != "success":
            return {"status": "error", "message": create_res.get("message", "Failed to create files post-confirmation")}
        created_files = create_res.get("files", [])
        workflow_dir = Path(create_res.get("workflow_dir", "")) if create_res.get("workflow_dir") else None
        ui_files = []
        for f in created_files:
            fp = (workflow_dir / f) if workflow_dir and workflow_dir.exists() else Path(f)
            size_bytes = fp.stat().st_size if fp.exists() else 0
            ui_files.append({
                "name": f,
                "size": _format_bytes(size_bytes),
                "size_bytes": size_bytes,
                "path": str(fp),
                "id": f"file-{len(ui_files)}",
            })

    # Optional storage only if success & files built
    if storage_backend != "none" and create_res.get("status") == "success" and ui_files:
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
                if tlog and _log_tool_event:
                    _log_tool_event(tlog, action="storage", status=str(storage_result.get('status', 'unknown')))
        except Exception as se:
            wf_logger.warning(f"⚠️ Storage action failed: {se}")
            if tlog and _log_tool_event:
                _log_tool_event(tlog, action="storage", status="error", error=str(se))

    final_status = create_res.get("status") if create_res else (response.get("status") or "success")
    return {
        "status": final_status,
        "ui_response": response,
        "agent_message_id": agent_message_id,
        "ui_files": ui_files,
        **({k: v for k, v in create_res.items() if k not in {"status"}} if create_res else {}),
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

