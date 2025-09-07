"""
Shared logging helpers for backend tool implementations.
"""

import logging
import os
from pathlib import Path
from logging.handlers import RotatingFileHandler
from typing import Optional, Dict, Any

try:
    # Prefer project workflow logger if present
    from logs.logging_config import get_workflow_logger  # type: ignore
except Exception:  # pragma: no cover
    get_workflow_logger = None  # type: ignore

SENSITIVE_KEYS = {"api_key", "apikey", "authorization", "auth", "secret", "password", "token"}


def _redact_extras(extras: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    data = extras or {}
    out: Dict[str, Any] = {}
    for k, v in data.items():
        if any(s in k.lower() for s in SENSITIVE_KEYS):
            out[k] = "***"
        else:
            out[k] = v
    return out


class ToolLoggerAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):  # type: ignore[override]
        extra = kwargs.get("extra") or {}
        base = dict(self.extra) if isinstance(self.extra, dict) else {}
        other = dict(extra) if isinstance(extra, dict) else {}
        merged = {**base, **other}
        kwargs["extra"] = _redact_extras(merged)
        return msg, kwargs


_TOOLS_HANDLER_SETUP = False


def _ensure_tools_file_handler() -> None:
    """Attach a rotating file handler to the 'core.tools' logger writing to logs/logs/tools.log.
    Safe to call multiple times; applies once.
    """
    global _TOOLS_HANDLER_SETUP
    if _TOOLS_HANDLER_SETUP:
        return
    try:
        # Derive logs directory relative to this file: ../logs/tools.log
        base_dir = Path(__file__).resolve().parent / "logs"
        # If project uses logs/logs/, maintain that structure
        if base_dir.name != "logs":
            base_dir = Path(__file__).resolve().parent
        # Prefer nested logs/logs folder if it exists; else create it
        nested_dir = base_dir / "logs"
        target_dir = nested_dir if nested_dir.exists() or True else base_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        file_path = target_dir / "tools.log"

        handler = RotatingFileHandler(str(file_path), maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
        fmt = logging.Formatter(
            fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s | extra=%(tool_name)s %(workflow_name)s %(chat_id)s %(ui_event_id)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(fmt)

        tools_root = logging.getLogger("core.tools")
        # Avoid adding duplicate similar handlers
        if not any(isinstance(h, RotatingFileHandler) and getattr(h, "baseFilename", None) == handler.baseFilename for h in tools_root.handlers):
            tools_root.addHandler(handler)
        # Keep propagate True so logs also reach the main mozaiks log
        tools_root.setLevel(logging.INFO)
        _TOOLS_HANDLER_SETUP = True
    except Exception:
        # Do not break logging on failures; main logger still works
        _TOOLS_HANDLER_SETUP = True


def get_tool_logger(
    *,
    tool_name: str,
    chat_id: Optional[str] = None,
    enterprise_id: Optional[str] = None,
    workflow_name: Optional[str] = None,
    agent_message_id: Optional[str] = None,
    ui_event_id: Optional[str] = None,
    base_logger: Optional[logging.Logger] = None,
) -> ToolLoggerAdapter:
    # Ensure dedicated tools file logging is attached once
    _ensure_tools_file_handler()
    name = f"core.tools.{tool_name}"
    if base_logger is not None:
        logger = base_logger
    elif get_workflow_logger and (workflow_name or chat_id or enterprise_id):
        logger = get_workflow_logger(workflow_name=workflow_name, chat_id=chat_id, enterprise_id=enterprise_id)  # type: ignore
    else:
        logger = logging.getLogger(name)

    extra = {
        "logger_type": "tool",
        "tool_name": tool_name,
        "chat_id": chat_id,
        "enterprise_id": enterprise_id,
        "workflow_name": workflow_name,
        "agent_message_id": agent_message_id,
        "ui_event_id": ui_event_id,
    }
    return ToolLoggerAdapter(logger, extra)


def log_tool_event(
    logger: ToolLoggerAdapter,
    *,
    action: str,
    status: str = "info",
    message: Optional[str] = None,
    level: int = logging.INFO,
    **fields: Any,
) -> None:
    payload = {"event": "tool_event", "action": action, "status": status, **fields}
    logger.log(level, message or f"tool:{action} ({status})", extra=payload)
