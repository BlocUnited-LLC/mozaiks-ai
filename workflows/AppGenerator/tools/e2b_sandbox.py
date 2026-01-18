"""
E2B Sandbox Tool for validating generated applications.

This tool can:
- Resolve generated files from an explicit `files` mapping OR by reading persisted agent outputs
- Create an E2B sandbox
- Write the generated files into the sandbox filesystem
- Run build/test commands (Node.js)
- Optionally start a dev server and return a preview URL
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import PurePosixPath
from typing import Any, Dict, List, Optional, Tuple

from mozaiksai.core.data.persistence.persistence_manager import AG2PersistenceManager
from logs.logging_config import get_workflow_logger

try:
    from e2b_code_interpreter import Sandbox  # type: ignore
except Exception:  # pragma: no cover
    Sandbox = None  # type: ignore


def _create_sandbox(*, timeout_seconds: int) -> Any:
    """Create an E2B sandbox across SDK variants.

    Supports:
    - Newer SDKs: Sandbox.create(timeout=...)
    - Older / test doubles: Sandbox(api_key=..., timeout=...)
    """

    if Sandbox is None:
        raise RuntimeError("Sandbox SDK not available")

    create_fn = getattr(Sandbox, "create", None)
    if callable(create_fn):
        return create_fn(timeout=timeout_seconds)

    # Unit tests patch Sandbox to a dummy class that expects ctor args.
    try:
        return Sandbox(api_key=os.getenv("E2B_API_KEY", "").strip(), timeout=timeout_seconds)
    except TypeError:
        return Sandbox(timeout_seconds)


def _sandbox_filesystem(sandbox: Any) -> Any:
    return getattr(sandbox, "files", None) or getattr(sandbox, "filesystem", None)


def _sandbox_run_command(sandbox: Any, cmd: str, *, background: bool = False) -> Any:
    commands = getattr(sandbox, "commands", None)
    if commands is not None and callable(getattr(commands, "run", None)):
        return commands.run(cmd, background=background)
    process = getattr(sandbox, "process", None)
    if process is not None and callable(getattr(process, "start", None)):
        return process.start(cmd, background=background)
    raise AttributeError("Sandbox has no command runner")


def _sandbox_get_host(sandbox: Any, port: int) -> Optional[str]:
    fn = getattr(sandbox, "get_host", None)
    if callable(fn):
        try:
            return str(fn(port))
        except Exception:
            return None

    fn = getattr(sandbox, "get_hostname", None)
    if callable(fn):
        try:
            return str(fn(port))
        except Exception:
            return None
    return None


def _safe_relpath(raw: str) -> Optional[str]:
    if not isinstance(raw, str):
        return None
    path = raw.replace("\\", "/").strip()
    if not path or path.startswith("/"):
        return None
    p = PurePosixPath(path)
    if p.is_absolute():
        return None
    if any(part in {".."} for part in p.parts):
        return None
    return str(p)


def _extract_code_files(collected: Dict[str, Any]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for _agent_name, data in (collected or {}).items():
        if not isinstance(data, dict):
            continue
        code_files = data.get("code_files")
        if not isinstance(code_files, list):
            continue
        for item in code_files:
            if not isinstance(item, dict):
                continue
            filename = item.get("filename") or item.get("path")
            content = item.get("content") or item.get("filecontent")
            if not filename or content is None:
                continue
            safe = _safe_relpath(str(filename))
            if not safe:
                continue
            out[safe] = str(content)
    return out


def parse_build_errors(build_output: str) -> List[Dict[str, Any]]:
    """Parse build output into structured errors.

    Returns a list of dicts:
      {"file": "src/App.tsx", "line": 42, "column": 10, "message": "..."}
    """
    if not isinstance(build_output, str) or not build_output:
        return []

    errors: List[Dict[str, Any]] = []

    # Pattern: src/file.js:42:10 - error TS1234: message
    ts_pattern = r"([^\s]+):(\d+):(\d+)\s*[-–]\s*error\s+\w+:\s*(.+)"
    for match in re.finditer(ts_pattern, build_output):
        errors.append(
            {
                "file": match.group(1),
                "line": int(match.group(2)),
                "column": int(match.group(3)),
                "message": match.group(4).strip(),
            }
        )

    # Pattern: ERROR in src/file.js\n ... \n 42:10 message
    webpack_pattern = r"ERROR in ([^\s]+)\s*\n.*?(\d+):(\d+)\s*(.+)"
    for match in re.finditer(webpack_pattern, build_output, re.MULTILINE | re.DOTALL):
        errors.append(
            {
                "file": match.group(1),
                "line": int(match.group(2)),
                "column": int(match.group(3)),
                "message": match.group(4).strip(),
            }
        )

    return errors


async def _resolve_files(
    *,
    files: Optional[Dict[str, str]],
    context_variables: Optional[Any],
    wf_logger,
) -> Tuple[Dict[str, str], Optional[str], Optional[str]]:
    if isinstance(files, dict) and files:
        safe_files: Dict[str, str] = {}
        for raw_path, content in files.items():
            safe = _safe_relpath(str(raw_path))
            if not safe:
                continue
            safe_files[safe] = str(content)
        return safe_files, None, None

    # Try context variables first
    chat_id = None
    app_id = None
    try:
        if context_variables is not None and hasattr(context_variables, "get"):
            chat_id = context_variables.get("chat_id")
            app_id = context_variables.get("app_id")
            ctx_files = context_variables.get("generated_files")
            if isinstance(ctx_files, dict) and ctx_files:
                safe_ctx: Dict[str, str] = {}
                for raw_path, content in ctx_files.items():
                    safe = _safe_relpath(str(raw_path))
                    if not safe:
                        continue
                    safe_ctx[safe] = str(content)
                if safe_ctx:
                    return safe_ctx, chat_id, app_id
    except Exception:
        pass

    if not chat_id or not app_id:
        return {}, chat_id, app_id

    # Fall back to persistence scrape for code_files lists
    pm = AG2PersistenceManager()
    collected = await pm.gather_latest_agent_jsons(chat_id=str(chat_id), app_id=str(app_id))
    resolved = _extract_code_files(collected)
    if not resolved:
        wf_logger.warning("No code_files found in persisted agent outputs for validation.")
    return resolved, str(chat_id), str(app_id)


async def validate_app_in_sandbox(
    files: Dict[str, str],
    commands: Optional[List[str]] = None,
    start_dev_server: bool = True,
    timeout_seconds: int = 120,
    context_variables: Optional[Any] = None,
) -> Dict[str, Any]:
    """Validate generated app code in an E2B sandbox."""

    e2b_api_key = os.getenv("E2B_API_KEY", "").strip()
    if not e2b_api_key:
        return {
            "success": False,
            "build_output": "",
            "errors": ["E2B_API_KEY not configured"],
            "warnings": [],
            "preview_url": None,
            "test_results": None,
        }

    if Sandbox is None:
        return {
            "success": False,
            "build_output": "",
            "errors": ["e2b_code_interpreter is not installed"],
            "warnings": [],
            "preview_url": None,
            "test_results": None,
        }

    try:
        env_timeout = os.getenv("E2B_TIMEOUT")
        if env_timeout and timeout_seconds == 120:
            timeout_seconds = int(env_timeout)
    except Exception:
        pass

    workflow_name = "AppGenerator"
    chat_id = None
    app_id = None
    try:
        if context_variables is not None and hasattr(context_variables, "get"):
            workflow_name = context_variables.get("workflow_name") or workflow_name
            chat_id = context_variables.get("chat_id")
            app_id = context_variables.get("app_id")
    except Exception:
        pass

    wf_logger = get_workflow_logger(workflow_name=workflow_name, chat_id=chat_id, app_id=app_id)

    resolved_files, chat_id, app_id = await _resolve_files(
        files=files,
        context_variables=context_variables,
        wf_logger=wf_logger,
    )
    if not resolved_files:
        return {
            "success": False,
            "build_output": "",
            "errors": ["No files provided/resolved for sandbox validation"],
            "warnings": [],
            "preview_url": None,
            "test_results": None,
        }

    result: Dict[str, Any] = {
        "success": True,
        "build_output": "",
        "errors": [],
        "warnings": [],
        "preview_url": None,
        "test_results": None,
        "parsed_errors": [],
    }

    sandbox = None
    try:
        sandbox = _create_sandbox(timeout_seconds=timeout_seconds)

        fs = _sandbox_filesystem(sandbox)
        if fs is None:
            raise RuntimeError("Sandbox filesystem unavailable")

        # Write all generated files into the sandbox
        for filepath, content in resolved_files.items():
            dir_path = str(PurePosixPath(filepath).parent)
            if dir_path and dir_path != ".":
                try:
                    fs.make_dir(dir_path)
                except Exception:
                    pass
            fs.write(filepath, content)

        # Default commands for a Node/React app
        if commands is None:
            commands = ["npm install", "npm run build"]

        for cmd in commands:
            proc = _sandbox_run_command(sandbox, cmd)
            
            stdout = proc.stdout or ""
            stderr = proc.stderr or ""
            exit_code = proc.exit_code

            result["build_output"] += f"\n=== {cmd} ===\n"
            result["build_output"] += stdout
            if stderr:
                result["build_output"] += "\n" + stderr

            if int(exit_code) != 0:
                result["success"] = False
                result["errors"].append(f"{cmd} failed: {stderr or stdout}")
                break

            if stderr and "warning" in stderr.lower():
                result["warnings"].append(stderr)

        result["parsed_errors"] = parse_build_errors(result.get("build_output", ""))

        # Run tests if present and build succeeded
        if result["success"]:
            try:
                pkg_json = fs.read("package.json")
                pkg = json.loads(pkg_json) if isinstance(pkg_json, str) else {}
                scripts = pkg.get("scripts") if isinstance(pkg, dict) else None
                if isinstance(scripts, dict) and "test" in scripts:
                    test_proc = _sandbox_run_command(sandbox, "npm test -- --watchAll=false")
                    result["test_results"] = test_proc.stdout or ""
                    if int(test_proc.exit_code) != 0:
                        result["warnings"].append(f"Tests failed: {test_proc.stderr or ''}")
            except Exception:
                pass

        # Start dev server if requested and build succeeded
        if result["success"] and start_dev_server:
            try:
                # Default to port 3000 for consistent sandbox previews (matches ChatUI config).
                try:
                    preview_port = int(os.getenv("E2B_PREVIEW_PORT", "3000"))
                except Exception:
                    preview_port = 3000

                # Best-effort: choose the right script and force the port for Vite/Cra-style apps.
                scripts: dict = {}
                try:
                    pkg_json = fs.read("package.json")
                    pkg = json.loads(pkg_json) if isinstance(pkg_json, str) else {}
                    scripts = pkg.get("scripts") if isinstance(pkg, dict) else {}
                    scripts = scripts if isinstance(scripts, dict) else {}
                except Exception:
                    scripts = {}

                if "dev" in scripts:
                    server_cmd = f"npm run dev -- --host 0.0.0.0 --port {preview_port}"
                elif "start" in scripts:
                    server_cmd = f"HOST=0.0.0.0 PORT={preview_port} npm start"
                else:
                    server_cmd = f"npm run dev -- --host 0.0.0.0 --port {preview_port}"

                _sandbox_run_command(sandbox, server_cmd, background=True)
                await asyncio.sleep(3)
                
                host = _sandbox_get_host(sandbox, preview_port)
                if host and host.strip():
                    preview_url = host.strip()
                    if not preview_url.startswith("http"):
                        preview_url = f"https://{preview_url}"
                else:
                    preview_url = None
                
                result["preview_url"] = preview_url
            except Exception as server_err:
                result["warnings"].append(f"Dev server not started: {server_err}")

        # Persist key outcomes for handoff routing (best-effort)
        if context_variables is not None and hasattr(context_variables, "set"):
            try:
                context_variables.set("app_validation_passed", bool(result.get("success")))
                context_variables.set("app_validation_preview_url", result.get("preview_url"))
                app_validation_result = dict(result)
                build_out = app_validation_result.get("build_output")
                try:
                    max_chars = int(os.getenv("APP_VALIDATION_BUILD_OUTPUT_MAX_CHARS", "20000"))
                except Exception:
                    max_chars = 20000
                if isinstance(build_out, str):
                    if max_chars <= 0:
                        app_validation_result.pop("build_output", None)
                    elif len(build_out) > max_chars:
                        app_validation_result["build_output"] = build_out[-max_chars:]
                        app_validation_result["build_output_truncated"] = True
                else:
                    app_validation_result.pop("build_output", None)
                context_variables.set("app_validation_result", app_validation_result)
            except Exception:
                pass

        return result
    except Exception as e:
        wf_logger.warning(f"Sandbox validation error: {e}")
        return {
            "success": False,
            "build_output": result.get("build_output", "") if isinstance(result, dict) else "",
            "errors": [f"Sandbox error: {str(e)}"],
            "warnings": [],
            "preview_url": None,
            "test_results": None,
        }
    finally:
        try:
            if sandbox is not None and hasattr(sandbox, "close"):
                sandbox.close()
        except Exception:
            pass
