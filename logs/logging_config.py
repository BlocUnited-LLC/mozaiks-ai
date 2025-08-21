# ======================================================================
# FILE: logs/logging_config.py (refactored)
# CHANGELOG: Unified setup, removed premature global logger creation,
# added secret redaction + safe_extra, clarified helpers.
# ======================================================================
from __future__ import annotations

import logging, logging.handlers, os, json, traceback, sys, time
from pathlib import Path
import os
from typing import Sequence, Optional, Dict, Any, Iterable
from datetime import datetime, timezone
from contextlib import contextmanager

# ----------------------------------------------------------------------
# Directory & file paths
# ----------------------------------------------------------------------
# Allow an explicit base directory via env var so Docker and local runs can point
# logs to an absolute path (for example Windows host path or container mount).
_env_logs_base = os.getenv("LOGS_BASE_DIR")
if _env_logs_base:
    LOGS_DIR = Path(_env_logs_base)
else:
    LOGS_DIR = Path(__file__).parent / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Toggle file format via env: when true, file contents are JSON lines; otherwise, human-readable text.
LOGS_AS_JSON = os.getenv("LOGS_AS_JSON", "").lower() in ("1", "true", "yes", "on")

CHAT_LOG_FILE        = LOGS_DIR / "agent_chat.log"
WORKFLOW_LOG_FILE    = LOGS_DIR / "workflows.log"
ERRORS_LOG_FILE      = LOGS_DIR / "errors.log"

# Sensitive key substrings for redaction
_SENSITIVE_KEYS = {"api_key", "apikey", "authorization", "auth", "secret", "password", "token"}

def _redact(value: Any) -> Any:
    if value is None:
        return value
    if isinstance(value, str):
        if len(value) <= 8:
            return "***" if any(k in value.lower() for k in ["sk-", "key", "tok"]) else value
        return value[:4] + "***" + value[-4:]
    return value

def _maybe_redact_mapping(data: Dict[str, Any]) -> Dict[str, Any]:
    if not data:
        return data
    redacted = {}
    for k, v in data.items():
        if any(sens in k.lower() for sens in _SENSITIVE_KEYS):
            redacted[k] = _redact(v)
        elif isinstance(v, dict):
            redacted[k] = _maybe_redact_mapping(v)
        else:
            redacted[k] = v
    return redacted

# ----------------------------------------------------------------------
# Production JSON Formatter
# ----------------------------------------------------------------------
class ProductionJSONFormatter(logging.Formatter):
    """Structured JSON logging for production systems"""
    
    def format(self, record: logging.LogRecord) -> str:
        # Choose an emoji based on logger/level/content for quick visual scan (also useful to surface in readers)
        emoji = _pick_emoji(record)
        base = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "mod": record.module,
            "fn": record.funcName,
            "line": record.lineno,
            "file": getattr(record, "filename", None),
            "path": getattr(record, "pathname", None),
            "source": f"{getattr(record,'filename', '')}:{record.lineno} {record.funcName}",
            "emoji": emoji,
        }
        if record.exc_info:
            base["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "trace": traceback.format_exception(*record.exc_info)
            }
        # Harvest extras
        extras: Dict[str, Any] = {}
        for k, v in record.__dict__.items():
            if k not in {"name","msg","args","levelname","levelno","pathname","filename","module","exc_info","exc_text","stack_info","lineno","funcName","created","msecs","relativeCreated","thread","threadName","processName","process","message"}:
                extras[k] = v
        if extras:
            base["extra"] = _maybe_redact_mapping(extras)
        return json.dumps(base, ensure_ascii=False)

# ----------------------------------------------------------------------
# Pretty, emoji-enhanced console formatter for developers
# ----------------------------------------------------------------------
_LEVEL_COLORS = {
    "DEBUG": "\x1b[38;5;244m",   # gray
    "INFO": "\x1b[38;5;39m",    # blue
    "WARNING": "\x1b[38;5;214m", # orange
    "ERROR": "\x1b[38;5;196m",   # red
    "CRITICAL": "\x1b[48;5;196m\x1b[97m", # white on red
}
_RESET = "\x1b[0m"

def _pick_emoji(record: logging.LogRecord) -> str:
    name = (record.name or "").lower()
    msg = (record.getMessage() or "").lower()
    level = record.levelname.upper()
    # Category-based
    if name.startswith("chat.") or "conversation" in msg:
        return "💬"
    if name.startswith("performance.") or "performance" in msg or "duration" in msg:
        return "⏱️"
    if name.startswith("token.") or "token" in msg:
        return "🪙"
    if "websocket" in name or "transport" in name or "ws" in msg:
        return "🔌"
    if "workflow" in name:
        return "🧩"
    if "event_dispatcher" in name or "business_event" in msg:
        return "🎯"
    # Level-based fallback
    return {"DEBUG": "🐛", "INFO": "ℹ️", "WARNING": "⚠️", "ERROR": "❌", "CRITICAL": "🚨"}.get(level, "•")

class PrettyConsoleFormatter(logging.Formatter):
    """Human-friendly console formatter with emojis, colors, and file context.

    Format:  HH:MM:SS.mmm [LEVEL] EMOJI logger  msg  (file.py:123 func)
    Includes select extras (chat_id, workflow_name, enterprise_id) inline.
    """
    def __init__(self, no_color: Optional[bool] = None):
        super().__init__(datefmt="%H:%M:%S")
        env_no_color = os.getenv("NO_COLOR", "0").lower() in ("1", "true", "yes")
        self.no_color = env_no_color if no_color is None else bool(no_color)

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created).strftime("%H:%M:%S.%f")[:-3]
        level = record.levelname
        emoji = _pick_emoji(record)
        color = _LEVEL_COLORS.get(level, "") if not self.no_color else ""
        reset = _RESET if color else ""
        logger_name = record.name
        msg = record.getMessage()
        file = getattr(record, "filename", "")
        line = record.lineno
        func = record.funcName
        # Pull a few common context keys into the line if present
        extras = []
        for k in ("workflow_name", "chat_id", "enterprise_id", "agent_name", "transport_type"):
            v = getattr(record, k, None)
            if v is not None:
                extras.append(f"{k}={v}")
        extra_str = f" | {' '.join(extras)}" if extras else ""
        base = f"{ts} [{color}{level:>5}{reset}] {emoji} {logger_name} - {msg}{extra_str}  ({file}:{line} {func})"
        if record.exc_info:
            base += "\n" + "".join(traceback.format_exception(*record.exc_info)).rstrip()
        return base

# ----------------------------------------------------------------------
# Generic keyword / level filter
# ----------------------------------------------------------------------
class KeywordFilter(logging.Filter):
    """
    Keep the record if it contains *any* of the supplied keywords
    (case-insensitive) and optionally satisfies a minimum level.
    Can also exclude records containing certain keywords.
    """
    def __init__(
        self,
        keywords: Sequence[str] = (),
        exclude_keywords: Sequence[str] = (),
        *,
        min_level: int | None = None,
    ):
        super().__init__(); self.kw = tuple(k.lower() for k in keywords); self.ex = tuple(k.lower() for k in exclude_keywords); self.min = min_level

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: D401
        if self.min and record.levelno < self.min: return False
        msg = record.getMessage().lower(); name = record.name.lower()
        if self.ex and any(k in msg or k in name for k in self.ex): return False
        if not self.kw: return True
        return any(k in msg or k in name for k in self.kw)

# Domain-specific filters (lambdas keep the file short & declarative)
_chat_kw        = ['agent_chat','conversation','reply','message_from','message_to','user_input','autogen.agentchat','handoff_executed','agent_response','group_chat','ag2','initiate_chat','chat.']
# Keep workflow logs clean by excluding chat-related noise. All operational logs should use the workflow logger name.
_workflow_kw    = ['workflow','orchestration','handoff','workflow_execution','transport','performance','token','observability','tools','file_manager']

ChatLogFilter   = lambda: KeywordFilter(_chat_kw)
# Exclude chat keywords from workflows log
_exclude_chat_kw    = _chat_kw + ['chat.', 'groupchat']
WorkflowFilter  = lambda: KeywordFilter(_workflow_kw, exclude_keywords=_exclude_chat_kw)

# ----------------------------------------------------------------------
# Handler factory
# ----------------------------------------------------------------------
def _make_handler(
    path: Path,
    level: int,
    formatter: logging.Formatter,
    *,
    log_filter: Optional[logging.Filter],
    max_bytes: int,
    backup_count: int,
) -> logging.Handler:
    """Return a RotatingFileHandler with common defaults pre-applied."""
    h = logging.handlers.RotatingFileHandler(
        path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding='utf-8',
    )
    h.setLevel(level)
    h.setFormatter(formatter)
    h.addFilter(log_filter) if log_filter else None
    return h

# Global flag to prevent duplicate logging setup
_logging_initialized = False

# ----------------------------------------------------------------------
# Public configuration function
# ----------------------------------------------------------------------
def setup_logging(
    *,
    chat_level: str = "INFO",
    console_level: str = "INFO",
    max_file_size: int = 10*1024*1024,      # 10 MB
    backup_count: int  = 5,
) -> None:
    """
    Configure root logger with two rotating file handlers (chat + workflows) + console.
    Prevents duplicate initialization with global flag.
    """
    global _logging_initialized
    if _logging_initialized: return
    _logging_initialized = True
    root = logging.getLogger(); root.handlers.clear(); root.setLevel(logging.DEBUG)
    # Choose file formatter based on env; console remains pretty
    file_fmt = ProductionJSONFormatter() if LOGS_AS_JSON else PrettyConsoleFormatter(no_color=True)
    console_fmt = PrettyConsoleFormatter()
    spec = [
        (CHAT_LOG_FILE,        getattr(logging, chat_level.upper()), ChatLogFilter()),
        (WORKFLOW_LOG_FILE,    logging.DEBUG,                        WorkflowFilter()),
    ]
    for path, lvl, flt in spec:
        root.addHandler(_make_handler(path, lvl, file_fmt, log_filter=flt, max_bytes=max_file_size, backup_count=backup_count))
    # Dedicated errors log capturing all ERROR+ across all categories
    err_handler = _make_handler(ERRORS_LOG_FILE, logging.ERROR, file_fmt, log_filter=None, max_bytes=max_file_size, backup_count=backup_count)
    root.addHandler(err_handler)
    ch = logging.StreamHandler(); ch.setLevel(getattr(logging, console_level.upper())); ch.setFormatter(console_fmt); root.addHandler(ch)
    for noisy in ("openai","httpx","urllib3","azure","motor","pymongo","uvicorn.access","openlit"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    logging.getLogger(__name__).info(
        "Logging initialized",
        extra={
            "logs_dir": str(LOGS_DIR),
            "files_as_json": LOGS_AS_JSON,
            "file_extension": ".log",
            "file_format": "jsonl" if LOGS_AS_JSON else "pretty",
        },
    )

def reset_logging_state():
    """Reset logging initialization state for testing purposes"""
    global _logging_initialized; _logging_initialized = False

# Public getters -----------------------------------------------------
get_chat_logger = lambda name: logging.getLogger(f"chat.{name}")

# Context logger -----------------------------------------------------
class ContextLogger:
    def __init__(self, base: logging.Logger, ctx: Dict[str, Any]): self._base = base; self._ctx = ctx
    def _log(self, lvl, msg, **extra): merged = {**self._ctx, **extra}; self._base.log(lvl, msg, extra=_maybe_redact_mapping(merged))
    def info(self, msg, **extra): self._log(logging.INFO, msg, **extra)
    def debug(self, msg, **extra): self._log(logging.DEBUG, msg, **extra)
    def warning(self, msg, **extra): self._log(logging.WARNING, msg, **extra)
    def error(self, msg, exc_info=False, **extra): self._log(logging.ERROR, msg, **extra); \
        (self._base.exception(msg, extra=_maybe_redact_mapping({**self._ctx, **extra})) if exc_info else None)
    def with_context(self, **more): return ContextLogger(self._base, {**self._ctx, **more})

def get_workflow_logger(workflow_name: str | None = None, chat_id: str | None = None, enterprise_id: str | None = None, **context):
    ctx = {k:v for k,v in {"workflow_name":workflow_name, "chat_id":chat_id, "enterprise_id":enterprise_id}.items() if v}
    ctx.update(context)
    return ContextLogger(logging.getLogger("mozaiks.workflow"), ctx)

# Operation timing ---------------------------------------------------
@contextmanager
def log_operation(logger: ContextLogger | logging.Logger, operation_name: str, **context):
    start = time.time()
    op_ctx = {"operation": operation_name, **context}
    if isinstance(logger, ContextLogger):
        logger.info(f"Starting {operation_name}", **op_ctx)
    else:
        logging.getLogger(__name__).info(f"Starting {operation_name}", extra=op_ctx)
    try:
        yield logger
        dur = time.time() - start
        op_ctx_done = {**op_ctx, "duration_seconds": dur, "status": "success"}
        if isinstance(logger, ContextLogger):
            logger.info(f"Completed {operation_name}", **op_ctx_done)
        else:
            logging.getLogger(__name__).info(f"Completed {operation_name}", extra=op_ctx_done)
    except Exception as e:
        dur = time.time() - start
        op_ctx_err = {**op_ctx, "duration_seconds": dur, "status": "error", "error_type": type(e).__name__}
        if isinstance(logger, ContextLogger):
            logger.error(f"Failed {operation_name}: {e}", **op_ctx_err)
        else:
            logging.getLogger(__name__).error(f"Failed {operation_name}: {e}", extra=op_ctx_err)
        raise

# Environment presets ------------------------------------------------
def setup_production_logging(): setup_logging(chat_level="INFO", console_level="WARNING", max_file_size=50*1024*1024, backup_count=10)

def setup_development_logging(): setup_logging(chat_level="DEBUG", console_level="INFO")
