# ==============================================================================
# FILE: workflows\Generator\tools\generate_and_download.py
# DESCRIPTION: Generate and download workflow files - async UI tool with auto_tool_mode
# NOTE: 'generate_and_download' function adheres to AGENT CONTRACT for tool integration. 
# ==============================================================================

from typing import Any, Dict, List, Optional, Union, Annotated
import json
import uuid
from pathlib import Path
import shutil
import time
import zipfile
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
    DownloadRequest: Annotated[Dict[str, Any], "Download configuration with confirmation_only and storage_backend"],
    agent_message: Annotated[str, "Concise message (≤140 chars) shown to user in download UI"],
    context_variables: Annotated[Optional[Any], "Injected runtime context."] = None,
) -> Dict[str, Any]:
    """
    Generate workflow files and present a download UI to the user.
    
    This tool is automatically invoked when DownloadAgent emits a DownloadRequestCall structured output.
    The runtime extracts DownloadRequest and agent_message from the agent's JSON emission.

    Two operation modes (controlled by DownloadRequest.confirmation_only):
      - confirmation_only=true: Show confirmation UI first, create files after user confirms (two-step).
      - confirmation_only=false: Create files immediately, then show download UI (one-step).

    Args:
        DownloadRequest: Dict with keys:
            - confirmation_only (bool): If true, ask user before creating files.
            - storage_backend (str): Storage target ('none', 's3', 'local').
            - description (str|None): Optional description (reserved for future use).
        agent_message: Message shown to user in UI (e.g., "Ready to download your workflow bundle?").
        context_variables: Runtime context dict (chat_id, workflow_name, user_id, enterprise_id).

    Returns:
        Dict with status, ui_response, files, and any storage metadata.
    """
    # Extract parameters from DownloadRequest structured output
    confirmation_only = DownloadRequest.get("confirmation_only", True)
    storage_backend = DownloadRequest.get("storage_backend", "none")
    description = DownloadRequest.get("description")
    
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
    wf_logger.info(f"🏗️ Starting generate_and_download (confirmation_only={confirmation_only}) chat: {chat_id}")

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
    wf_logger.info(f"🔍 [GATHER] Calling gather_latest_agent_jsons for chat_id={chat_id} enterprise_id={enterprise_id}")
    collected = await pm.gather_latest_agent_jsons(chat_id=chat_id, enterprise_id=enterprise_id)
    wf_logger.info(f"🔍 [GATHER] Collected {len(collected)} agent outputs: {list(collected.keys())}")
    
    if not collected:
        wf_logger.error(f"❌ [GATHER] No agent outputs collected from persistence! This means either:")
        wf_logger.error(f"   1. Workflow status is not IN_PROGRESS")
        wf_logger.error(f"   2. No messages were persisted to MongoDB")
        wf_logger.error(f"   3. Messages don't have role='assistant' or agent_name field")
        wf_logger.error(f"   4. Message content doesn't contain valid JSON")
        wf_logger.error(f"   Check persistence_manager.py logs for [RESUME_CHAT] and [GATHER_AGENT_JSONS] details")
    
    # Save agent outputs to dedicated debug file
    try:
        from datetime import datetime
        debug_dir = Path("logs/agent_outputs")
        debug_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        debug_file = debug_dir / f"agent_outputs_{chat_id}_{timestamp}.json"
        
        debug_data = {
            "chat_id": chat_id,
            "enterprise_id": enterprise_id,
            "workflow_name": workflow_name,
            "timestamp": timestamp,
            "collected_agents": list(collected.keys()),
            "agent_outputs": {}
        }
        
        for agent_name, output_data in collected.items():
            debug_data["agent_outputs"][agent_name] = {
                "type": type(output_data).__name__,
                "data": output_data if isinstance(output_data, (dict, list, str, int, float, bool, type(None))) else str(output_data)
            }
        
        with open(debug_file, 'w', encoding='utf-8') as f:
            json.dump(debug_data, f, indent=2, ensure_ascii=False)
        
        abs_path = debug_file.resolve()
        wf_logger.info(f"📄 Agent outputs saved to: {abs_path}")
        print("\n" + "=" * 80)
        print(f"📄 AGENT OUTPUTS DEBUG FILE CREATED:")
        print(f"   {abs_path}")
        print("=" * 80 + "\n")
    except Exception as e:
        wf_logger.error(f"❌ Failed to save agent outputs debug file: {e}", exc_info=True)
        print(f"\n⚠️ Warning: Could not save agent outputs debug file: {e}\n")
    
    # Log summary to console
    wf_logger.info("=" * 80)
    wf_logger.info("📋 AGENT OUTPUTS COLLECTED FROM CHAT MESSAGES:")
    wf_logger.info("=" * 80)
    for agent_name, output_data in collected.items():
        wf_logger.info(f"🤖 {agent_name}:")
        if isinstance(output_data, dict):
            wf_logger.info(f"   Keys: {list(output_data.keys())}")
        else:
            wf_logger.info(f"   Type: {type(output_data).__name__}")
    wf_logger.info("=" * 80)
    
    # Extract workflow name from ActionPlanArchitect output (user-friendly name)
    # Then convert to PascalCase for folder/zip naming
    def _to_pascal_case(name: str) -> str:
        """Convert user-friendly name to PascalCase (e.g., 'Story Creator' -> 'StoryCreator')
        
        If already PascalCase with no spaces (e.g., 'ContentMarketingAutomation'), return as-is.
        If has spaces/hyphens/underscores, convert each word's first letter to uppercase.
        """
        if not name:
            return name
        
        # If no spaces/hyphens/underscores and starts with uppercase, assume already PascalCase
        if ' ' not in name and '-' not in name and '_' not in name and name[0].isupper():
            return name
        
        # Otherwise, split on delimiters and capitalize first letter of each word
        words = name.replace('_', ' ').replace('-', ' ').split()
        # Use title() to capitalize first letter while preserving internal capitals
        return ''.join(word.title() for word in words if word)
    
    wf_name_user_friendly = None
    wf_name_pascal = None
    
    # PRIORITY 1: Try to extract from context_variables.action_plan (for auto-tool agents)
    if context_variables and hasattr(context_variables, 'get'):
        action_plan_ctx = context_variables.get("action_plan")
        if isinstance(action_plan_ctx, dict):
            workflow_info = action_plan_ctx.get("workflow", {})
            if isinstance(workflow_info, dict):
                wf_name_user_friendly = workflow_info.get("name")
                if wf_name_user_friendly:
                    wf_name_pascal = _to_pascal_case(wf_name_user_friendly)
                    wf_logger.info(f"📝 Extracted workflow name from context.action_plan: '{wf_name_user_friendly}' → '{wf_name_pascal}'")
    
    # PRIORITY 2: Try to extract from collected agent JSONs (fallback for non-auto-tool agents)
    if not wf_name_pascal:
        action_plan_data = collected.get("ActionPlanArchitect")
        if isinstance(action_plan_data, dict):
            action_plan = action_plan_data.get("ActionPlan", {})
            if isinstance(action_plan, dict):
                workflow = action_plan.get("workflow", {})
                if isinstance(workflow, dict):
                    wf_name_user_friendly = workflow.get("name")
                    if wf_name_user_friendly:
                        wf_name_pascal = _to_pascal_case(wf_name_user_friendly)
                        wf_logger.info(f"📝 Extracted workflow name from collected.ActionPlanArchitect: '{wf_name_user_friendly}' → '{wf_name_pascal}'")
    
    # PRIORITY 3: Fallback to orchestrator or context workflow_name
    if not wf_name_pascal:
        wf_name_pascal = collected.get("workflow_name") or workflow_name or "GeneratedWorkflow"
        wf_logger.info(f"⚠️ No workflow name in ActionPlan, using fallback: '{wf_name_pascal}'")
    
    if not wf_name_pascal:
        return {"status": "error", "message": "workflow_name missing (not provided and not in persistence)"}
    
    # Use PascalCase name for all file operations
    wf_name = wf_name_pascal
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
    
    # UI Config (visual_agentsarrays)
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

    # Simplified logic: confirmation_only determines when files are created
    create_res: Dict[str, Any] = {}
    ui_files: List[Dict[str, Any]] = []
    workflow_dir: Optional[Path] = None

    def _format_bytes(num: int) -> str:  # local helper
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

    if not confirmation_only:
        # Immediate mode: Create files NOW, then show download UI
        wf_logger.info("📦 Creating workflow files immediately (confirmation_only=False)...")
        create_res = await create_workflow_files(payload, context_variables)
        if create_res.get("status") != "success":
            return {"status": "error", "message": create_res.get("message", "Failed to create files")}
        created_files = create_res.get("files", [])
        workflow_dir = Path(create_res.get("workflow_dir", "")) if create_res.get("workflow_dir") else None
        
        # Create zip file containing all workflow files
        if workflow_dir and workflow_dir.exists():
            try:
                zip_path = workflow_dir.parent / f"{wf_name}.zip"
                wf_logger.info(f"📦 Creating zip archive: {zip_path}")
                
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    # Add all workflow files
                    for file_name in created_files:
                        file_path = workflow_dir / file_name
                        if file_path.exists():
                            arcname = f"{wf_name}/{file_name}"
                            zipf.write(file_path, arcname=arcname)
                    
                    # Add tools directory if it exists
                    tools_dir = workflow_dir / "tools"
                    if tools_dir.exists() and tools_dir.is_dir():
                        for tool_file in tools_dir.rglob("*"):
                            if tool_file.is_file():
                                arcname = f"{wf_name}/tools/{tool_file.relative_to(tools_dir)}"
                                zipf.write(tool_file, arcname=arcname)
                
                zip_size = zip_path.stat().st_size
                wf_logger.info(f"✅ Created zip archive: {_format_bytes(zip_size)}")
                
                # Only add the zip file to ui_files
                ui_files.append({
                    "name": f"{wf_name}.zip",
                    "size": _format_bytes(zip_size),
                    "size_bytes": zip_size,
                    "path": str(zip_path.resolve()),
                    "id": "file-zip-bundle",
                    "type": "zip"
                })
                wf_logger.info(f"✅ Prepared zip bundle for download")
            except Exception as zip_err:
                wf_logger.error(f"Failed to create zip file: {zip_err}")
                return {"status": "error", "message": f"Failed to create zip: {zip_err}"}
        else:
            return {"status": "error", "message": "Workflow directory not found"}
    else:
        # Confirmation mode: Show UI first with empty files array, create after user confirms
        wf_logger.info("❓ Asking user confirmation before creating files (confirmation_only=True)...")
        ui_files = []

    ui_payload = {
        "downloadType": "single",  # Always single zip file
        "files": ui_files,
        "agent_message": agent_message_text,
        "description": agent_message_text,
        "title": "Workflow Bundle Ready" if confirmation_only else "Generated Workflow Files",
        "workflow_name": wf_name,
        "agent_message_id": agent_message_id,
        "stage": "confirm" if (confirmation_only and not ui_files) else "files_ready",
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

    # If user declined -> return early
    if response.get("status") == "cancelled":
        wf_logger.info("❌ User declined download")
        return {
            "status": "cancelled",
            "ui_response": response,
            "agent_message_id": agent_message_id,
            "ui_files": [],
            "message": "User declined download",
        }

    # If confirmation_only, now create the files (user has confirmed)
    if confirmation_only:
        wf_logger.info("✅ User confirmed! Creating files now...")
        create_res = await create_workflow_files(payload, context_variables)
        if create_res.get("status") != "success":
            return {"status": "error", "message": create_res.get("message", "Failed to create files post-confirmation")}
        created_files = create_res.get("files", [])
        workflow_dir = Path(create_res.get("workflow_dir", "")) if create_res.get("workflow_dir") else None
        ui_files = []
        
        # Create zip file containing all workflow files
        if workflow_dir and workflow_dir.exists():
            try:
                zip_path = workflow_dir.parent / f"{wf_name}.zip"
                wf_logger.info(f"📦 Creating zip archive: {zip_path}")
                
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    # Add all workflow files
                    for file_name in created_files:
                        file_path = workflow_dir / file_name
                        if file_path.exists():
                            arcname = f"{wf_name}/{file_name}"
                            zipf.write(file_path, arcname=arcname)
                    
                    # Add tools directory if it exists
                    tools_dir = workflow_dir / "tools"
                    if tools_dir.exists() and tools_dir.is_dir():
                        for tool_file in tools_dir.rglob("*"):
                            if tool_file.is_file():
                                arcname = f"{wf_name}/tools/{tool_file.relative_to(tools_dir)}"
                                zipf.write(tool_file, arcname=arcname)
                
                zip_size = zip_path.stat().st_size
                wf_logger.info(f"✅ Created zip archive: {_format_bytes(zip_size)}")
                
                # Only add the zip file to ui_files
                ui_files.append({
                    "name": f"{wf_name}.zip",
                    "size": _format_bytes(zip_size),
                    "size_bytes": zip_size,
                    "path": str(zip_path.resolve()),
                    "id": "file-zip-bundle",
                    "type": "zip"
                })
                wf_logger.info(f"✅ Prepared zip bundle for download")
            except Exception as zip_err:
                wf_logger.error(f"Failed to create zip file: {zip_err}")
                return {"status": "error", "message": f"Failed to create zip: {zip_err}"}
        else:
            return {"status": "error", "message": "Workflow directory not found"}
        
        # Inject files into response data so UI/agent can access them
        if isinstance(response, dict):
            if "data" not in response:
                response["data"] = {}
            if isinstance(response["data"], dict):
                response["data"]["files"] = ui_files
                response["data"]["fileCount"] = len(ui_files)
        if isinstance(response, dict) and "agentContext" not in response:
            response["agentContext"] = {}
        if isinstance(response, dict) and isinstance(response.get("agentContext"), dict):
            response["agentContext"]["files_created"] = True
            response["agentContext"]["file_count"] = len(ui_files)

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
    
    # Set download_complete context variable if user accepted download
    if context_variables and response.get("download_accepted"):
        try:
            context_variables.set('download_complete', True)
            wf_logger.info("✅ Set download_complete=True (user accepted download)")
        except Exception as ctx_err:
            wf_logger.warning(f"⚠️ Failed to set download_complete context variable: {ctx_err}")
    
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
