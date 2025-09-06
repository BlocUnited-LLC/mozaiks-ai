# ======================================================================
# FILE: logs/logging_config.py (refactored)
# CHANGELOG: Unified setup, removed premature global logger creation,
# added secret redaction + safe_extra, clarified helpers.
# ======================================================================
from __future__ import annotations

import logging, logging.handlers, os, json, traceback, sys, time, re
from time import perf_counter
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
AUTOGEN_LOG_FILE     = LOGS_DIR / "autogen_agentchat.log"

# Enhanced logging files
ALL_CORE_LOG_FILE    = LOGS_DIR / "all_core.log"
CORE_DATA_LOG_FILE   = LOGS_DIR / "core_data.log"
CORE_EVENTS_LOG_FILE = LOGS_DIR / "core_events.log"
CORE_OBSERVABILITY_LOG_FILE = LOGS_DIR / "core_observability.log"
CORE_TRANSPORT_LOG_FILE = LOGS_DIR / "core_transport.log"
CORE_WORKFLOW_LOG_FILE = LOGS_DIR / "core_workflow.log"
CORE_ROOT_LOG_FILE   = LOGS_DIR / "core_root.log"

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
        raw_msg = record.getMessage()
        # Sanitize highly specific secrets / tenant GUIDs from noisy third-party libs (msal)
        raw_msg = _sanitize_log_message(raw_msg)
        base = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": raw_msg,
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
    if "websocket" in name or "transport" in name or "mon" in msg:
        return "🔌"
    if "workflow" in name:
        return "🧩"
    if "event_dispatcher" in name or "business_event" in msg:
        return "🎯"
    # Level-based fallback
    return {"DEBUG": "🐛", "INFO": "ℹ️", "WARNING": "⚠️", "ERROR": "❌", "CRITICAL": "🚨"}.get(level, "•")

# ----------------------------------------------------------------------
# Message sanitization helper (tenant/client IDs, GUIDs from msal noise)
# ----------------------------------------------------------------------
_GUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE)

def _sanitize_log_message(message: str) -> str:
    if not isinstance(message, str) or not message:
        return message
    # Redact GUIDs that appear in Azure tenant / client logs
    msg = _GUID_RE.sub(lambda m: m.group(0)[:4] + "***REDACTED***" + m.group(0)[-4:], message)
    # Collapse excessive whitespace from large JSON dumps
    if len(msg) > 2000:
        msg = msg[:2000] + "...<truncated>"
    return msg

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
        msg = _sanitize_log_message(record.getMessage())
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

# Core module filters for granular logging
CoreDataFilter = lambda: KeywordFilter(['core.data', 'persistence', 'models', 'mongodb'])
CoreEventsFilter = lambda: KeywordFilter(['core.events', 'unified_event', 'event_dispatcher'])
CoreObservabilityFilter = lambda: KeywordFilter(['core.observability', 'performance', 'otel', 'token_logger'])
CoreTransportFilter = lambda: KeywordFilter(['core.transport', 'websocket', 'simple_transport'])
CoreWorkflowFilter = lambda: KeywordFilter(['core.workflow', 'agents', 'tools', 'handoffs', 'orchestration'])
CoreRootFilter = lambda: KeywordFilter(['core.core_config'])
AllCoreFilter = lambda: KeywordFilter(['core.'])

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

    # Optional clearing of existing log files (pre-handler creation) ------------------
    cleared_files: list[str] = []
    clear_flag = os.getenv("CLEAR_LOGS_ON_START", "0").lower() in ("1","true","yes","on")
    if clear_flag:
        all_log_files = (
            CHAT_LOG_FILE, WORKFLOW_LOG_FILE, ERRORS_LOG_FILE, AUTOGEN_LOG_FILE,
            ALL_CORE_LOG_FILE, CORE_DATA_LOG_FILE, CORE_EVENTS_LOG_FILE,
            CORE_OBSERVABILITY_LOG_FILE, CORE_TRANSPORT_LOG_FILE, 
            CORE_WORKFLOW_LOG_FILE, CORE_ROOT_LOG_FILE
        )
        for f in all_log_files:
            try:
                if f.exists():
                    try:
                        f.unlink()  # remove so RotatingFileHandler starts fresh
                    except Exception:
                        # Fallback: truncate if unlink fails (e.g. locked on Windows)
                        with open(f, 'w', encoding='utf-8') as fp:
                            fp.truncate(0)
                    cleared_files.append(str(f))
            except Exception:
                pass  # silent; not critical

    root = logging.getLogger(); root.handlers.clear(); root.setLevel(logging.DEBUG)
    # Choose file formatter based on env; console remains pretty
    file_fmt = ProductionJSONFormatter() if LOGS_AS_JSON else PrettyConsoleFormatter(no_color=True)
    console_fmt = PrettyConsoleFormatter()
    
    # Original handlers
    spec = [
        (CHAT_LOG_FILE,        getattr(logging, chat_level.upper()), ChatLogFilter()),
        (WORKFLOW_LOG_FILE,    logging.DEBUG,                        WorkflowFilter()),
    ]
    for path, lvl, flt in spec:
        root.addHandler(_make_handler(path, lvl, file_fmt, log_filter=flt, max_bytes=max_file_size, backup_count=backup_count))
    
    # Enhanced core logging handlers
    core_handlers_spec = [
        (ALL_CORE_LOG_FILE,           logging.DEBUG, AllCoreFilter()),
        (CORE_DATA_LOG_FILE,          logging.DEBUG, CoreDataFilter()),
        (CORE_EVENTS_LOG_FILE,        logging.DEBUG, CoreEventsFilter()),
        (CORE_OBSERVABILITY_LOG_FILE, logging.DEBUG, CoreObservabilityFilter()),
        (CORE_TRANSPORT_LOG_FILE,     logging.DEBUG, CoreTransportFilter()),
        (CORE_WORKFLOW_LOG_FILE,      logging.DEBUG, CoreWorkflowFilter()),
        (CORE_ROOT_LOG_FILE,          logging.DEBUG, CoreRootFilter()),
    ]
    for path, lvl, flt in core_handlers_spec:
        root.addHandler(_make_handler(path, lvl, file_fmt, log_filter=flt, max_bytes=max_file_size, backup_count=backup_count))
    # Dedicated autogen handler so AG2/internal autogen logs have their own file
    try:
        # Allow overriding autogen log level via env var; default to DEBUG so users actually see AG2 internals.
        autogen_level_env = os.getenv("AUTOGEN_LOG_LEVEL", "DEBUG").upper()
        autogen_level = getattr(logging, autogen_level_env, logging.DEBUG)
        autogen_handler = _make_handler(
            AUTOGEN_LOG_FILE,
            autogen_level,
            file_fmt,
            log_filter=None,
            max_bytes=max_file_size,
            backup_count=backup_count
        )
        autogen_logger = logging.getLogger('autogen')
        autogen_logger.setLevel(autogen_level)
        autogen_logger.addHandler(autogen_handler)
    except Exception:
        # Non-fatal: if we cannot create autogen handler, continue with default handlers
        logging.getLogger(__name__).warning('Failed to initialize autogen dedicated log handler')
    # Dedicated errors log capturing all ERROR+ across all categories
    err_handler = _make_handler(ERRORS_LOG_FILE, logging.ERROR, file_fmt, log_filter=None, max_bytes=max_file_size, backup_count=backup_count)
    root.addHandler(err_handler)
    ch = logging.StreamHandler(); ch.setLevel(getattr(logging, console_level.upper())); ch.setFormatter(console_fmt); root.addHandler(ch)
    for noisy in ("openai","httpx","urllib3","azure","motor","pymongo","uvicorn.access","openlit","msal"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    logging.getLogger(__name__).info(
        "Logging initialized",
        extra={
            "logs_dir": str(LOGS_DIR),
            "files_as_json": LOGS_AS_JSON,
            "file_extension": ".log",
            "file_format": "jsonl" if LOGS_AS_JSON else "pretty",
            "cleared_on_start": clear_flag,
            "cleared_files_count": len(cleared_files),
        },
    )
    if clear_flag and cleared_files:
        logging.getLogger(__name__).info(
            "Cleared existing log files", extra={"cleared_files": cleared_files}
        )
    
    # Log information about the enhanced core logging system
    log_core_system_info()

def reset_logging_state():
    """Reset logging initialization state for testing purposes"""
    global _logging_initialized; _logging_initialized = False

# Public getters -----------------------------------------------------
get_chat_logger = lambda name: logging.getLogger(f"chat.{name}")

# Enhanced core module loggers
def get_core_logger(module_name: str) -> logging.Logger:
    """Get a logger for a specific core module file.
    
    Args:
        module_name: Name of the module (e.g., 'persistence_manager', 'simple_transport')
                    or full path like 'core.data.persistence_manager'
    
    Returns:
        Logger configured for the specified core module
    """
    if module_name.startswith('core.'):
        logger_name = module_name
    else:
        # Auto-detect the module category based on common patterns
        if module_name in ['models', 'persistence_manager']:
            logger_name = f"core.data.{module_name}"
        elif module_name in ['unified_event_dispatcher']:
            logger_name = f"core.events.{module_name}"
        elif module_name in ['otel_helpers', 'performance_manager', 'performance_store', 'realtime_token_logger']:
            logger_name = f"core.observability.{module_name}"
        elif module_name in ['simple_transport']:
            logger_name = f"core.transport.{module_name}"
        elif module_name in ['agents', 'agent_tools', 'context_variables', 'db_manager', 'handoffs', 
                            'hooks_loader', 'llm_config', 'orchestration_patterns', 'structured_outputs',
                            'termination_handler', 'ui_tools', 'workflow_manager']:
            logger_name = f"core.workflow.{module_name}"
        elif module_name == 'core_config':
            logger_name = f"core.{module_name}"
        else:
            logger_name = f"core.{module_name}"
    
    return logging.getLogger(logger_name)

# Convenience functions for each core module
get_data_logger = lambda name="data": logging.getLogger(f"core.data.{name}")
get_events_logger = lambda name="events": logging.getLogger(f"core.events.{name}")  
get_observability_logger = lambda name="observability": logging.getLogger(f"core.observability.{name}")
get_transport_logger = lambda name="transport": logging.getLogger(f"core.transport.{name}")
get_workflow_logger_detailed = lambda name="workflow": logging.getLogger(f"core.workflow.{name}")
get_core_config_logger = lambda: logging.getLogger("core.core_config")

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
    start = perf_counter()
    op_ctx = {"operation": operation_name, **context}
    if isinstance(logger, ContextLogger):
        logger.info(f"Starting {operation_name}", **op_ctx)
    else:
        logging.getLogger(__name__).info(f"Starting {operation_name}", extra=op_ctx)
    try:
        yield logger
        dur = perf_counter() - start
        op_ctx_done = {**op_ctx, "duration_seconds": dur, "status": "success"}
        if isinstance(logger, ContextLogger):
            logger.info(f"Completed {operation_name}", **op_ctx_done)
        else:
            logging.getLogger(__name__).info(f"Completed {operation_name}", extra=op_ctx_done)
    except Exception as e:
        dur = perf_counter() - start
        op_ctx_err = {**op_ctx, "duration_seconds": dur, "status": "error", "error_type": type(e).__name__}
        if isinstance(logger, ContextLogger):
            logger.error(f"Failed {operation_name}: {e}", **op_ctx_err)
        else:
            logging.getLogger(__name__).error(f"Failed {operation_name}: {e}", extra=op_ctx_err)
        raise

# Environment presets ------------------------------------------------
def setup_production_logging(): setup_logging(chat_level="INFO", console_level="WARNING", max_file_size=50*1024*1024, backup_count=10)

def setup_development_logging(): setup_logging(chat_level="DEBUG", console_level="INFO")

# ----------------------------------------------------------------------
# Auto-discovered Core File Loggers
# ----------------------------------------------------------------------
def get_core_file_loggers() -> Dict[str, logging.Logger]:
    """
    Returns a dictionary of all discovered core module loggers.
    This is useful for debugging or getting an overview of all core loggers.
    
    Returns:
        Dict mapping file paths to their logger instances
    """
    import os
    import pathlib
    
    core_files = {}
    project_root = pathlib.Path(__file__).parent.parent
    core_dir = project_root / "core"
    
    if not core_dir.exists():
        return core_files
    
    for py_file in core_dir.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue
        
        # Create relative path from core directory
        rel_path = py_file.relative_to(core_dir)
        module_parts = []
        
        for part in rel_path.parts[:-1]:  # All parts except filename
            module_parts.append(part)
        
        # Add filename without .py extension
        module_parts.append(py_file.stem)
        
        # Create logger name
        logger_name = f"core.{'.'.join(module_parts)}"
        core_files[str(rel_path)] = logging.getLogger(logger_name)
    
    return core_files

def log_core_system_info():
    """Log information about the enhanced core logging system"""
    logger = logging.getLogger(__name__)
    core_loggers = get_core_file_loggers()
    
    logger.info(
        "Enhanced core logging system initialized",
        extra={
            "total_core_files": len(core_loggers),
            "log_files": [
                "all_core.log (consolidated)",
                "core_data.log (data module)",
                "core_events.log (events module)", 
                "core_observability.log (observability module)",
                "core_transport.log (transport module)",
                "core_workflow.log (workflow module)",
                "core_root.log (root config)"
            ],
            "usage_example": "from logs.logging_config import get_core_logger; logger = get_core_logger('persistence_manager')"
        }
    )

# ----------------------------------------------------------------------
# Consolidated Workflow Logging (replaces separate workflow_logging.py)
# ----------------------------------------------------------------------
class WorkflowLogger:
    """Consolidated logging for AG2 workflows to reduce verbosity and duplication."""
    
    def __init__(self, workflow_name: str, chat_id: str | None = None):
        self.workflow_name = workflow_name
        self.chat_id = chat_id
        self.workflow_logger = logging.getLogger("mozaiks.workflow")
        self.chat_logger = logging.getLogger("chat.workflow")
    
    def log_agent_setup_summary(self, agents: dict, agent_tools: dict, hooks_count: int = 0):
        """Log a consolidated summary of agent setup instead of verbose individual logs."""
        total_tools = sum(len(tools) for tools in agent_tools.values())
        agent_summary = []
        
        for name, agent in agents.items():
            tool_count = len(agent_tools.get(name, []))
            agent_summary.append(f"{name}({tool_count})")
        
        summary = f"🏗️ [WORKFLOW_SETUP] {self.workflow_name}: agents=[{', '.join(agent_summary)}] hooks={hooks_count} total_tools={total_tools}"
        
        self.workflow_logger.info(summary)
        if self.chat_id:
            self.chat_logger.info(f"💼 [SESSION] {summary} | chat_id={self.chat_id}")
    
    def log_execution_start(self, pattern_name: str, message_count: int, max_turns: int, is_resume: bool):
        """Log AG2 execution start with key parameters."""
        mode = "RESUME" if is_resume else "FRESH"
        summary = f"🚀 [AG2_{mode}] {self.workflow_name}: pattern={pattern_name} messages={message_count} max_turns={max_turns}"
        
        self.workflow_logger.info(summary)
        if self.chat_id:
            self.chat_logger.info(f"▶️ [EXECUTION] {summary} | chat_id={self.chat_id}")
    
    def log_execution_complete(self, duration_sec: float, event_count: int = 0):
        """Log AG2 execution completion with metrics."""
        summary = f"✅ [AG2_COMPLETE] {self.workflow_name}: duration={duration_sec:.2f}s events={event_count}"
        
        self.workflow_logger.info(summary)
        if self.chat_id:
            self.chat_logger.info(f"🏁 [COMPLETE] {summary} | chat_id={self.chat_id}")
    
    def log_tool_binding_summary(self, agent_name: str, tool_count: int, tool_names: list | None = None):
        """Log tool binding results for debugging."""
        tools_str = f"[{', '.join(tool_names)}]" if tool_names else f"({tool_count} tools)"
        summary = f"🔧 [TOOLS] {agent_name}: {tools_str}"
        
        self.workflow_logger.debug(summary)
    
    def log_hook_registration_summary(self, workflow_name: str, hook_count: int):
        """Log hook registration summary."""
        summary = f"🪝 [HOOKS] {workflow_name}: registered {hook_count} hooks"
        
        self.workflow_logger.info(summary)

def get_workflow_session_logger(workflow_name: str, chat_id: str | None = None) -> WorkflowLogger:
    """Factory function to create a WorkflowLogger instance."""
    return WorkflowLogger(workflow_name, chat_id)

# ----------------------------------------------------------------------
# Lightweight AG2 runtime log summarizer (file-only, no pandas/sqlite)
# ----------------------------------------------------------------------
def summarize_autogen_runtime_file(  # pragma: no cover - utility
    logging_session_id: str | None = None,
    filename: str | None = None,
    *,
    limit: int | None = None,
    emit_log: bool = True,
    logger: logging.Logger | None = None,
) -> dict[str, Any]:
    """Summarize AG2 runtime logging (file mode) without pandas/sqlite.

    Expects lines of JSON produced when AUTOGEN_RUNTIME_LOGGING=file was used:
      runtime_logging.start(logger_type="file", config={"filename": "runtime.log"})

    Returns dict with totals. If logging_session_id provided, adds per-session figures.

    Parameters
    ----------
    logging_session_id: optional session id (string) to isolate per-session totals.
    filename: path to runtime log file (defaults to AUTOGEN_RUNTIME_LOG_FILE or runtime.log).
    limit: stop after processing N lines (for quick checks).
    emit_log: if True, writes a one-line summary via provided logger (or root).
    logger: optional logger (defaults to root if None).
    """
    import json, os
    path = filename or os.getenv("AUTOGEN_RUNTIME_LOG_FILE", "runtime.log")
    stats = {
        "file": path,
        "records": 0,
        "total_tokens": 0,
        "total_cost": 0.0,
        "session_tokens": 0,
        "session_cost": 0.0,
        "session_id": logging_session_id,
    }
    lg = logger or logging.getLogger("autogen.runtime.summary")
    if not os.path.exists(path):
        if emit_log:
            lg.warning(f"Runtime log file not found: {path}")
        return stats
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for i, line in enumerate(f):
                if limit and i >= limit:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                stats["records"] += 1
                # Extract cost if present
                cost = rec.get("cost")
                if isinstance(cost, (int, float)):
                    stats["total_cost"] += float(cost)
                # Parse response usage if present
                resp = rec.get("response")
                if isinstance(resp, str):
                    try:
                        resp_json = json.loads(resp)
                    except Exception:
                        resp_json = None
                else:
                    resp_json = resp if isinstance(resp, dict) else None
                if isinstance(resp_json, dict):
                    usage = resp_json.get("usage") or {}
                    tks = usage.get("total_tokens")
                    if isinstance(tks, (int, float)):
                        stats["total_tokens"] += int(tks)
                # Session-specific accumulation
                if logging_session_id is not None:
                    sid = rec.get("session_id") or rec.get("session") or rec.get("sid")
                    if sid and str(sid) == str(logging_session_id):
                        if isinstance(cost, (int, float)):
                            stats["session_cost"] += float(cost)
                        if isinstance(resp_json, dict):
                            usage = resp_json.get("usage") or {}
                            tks = usage.get("total_tokens")
                            if isinstance(tks, (int, float)):
                                stats["session_tokens"] += int(tks)
        # Rounding for readability
        stats["total_cost"] = round(stats["total_cost"], 6)
        stats["session_cost"] = round(stats["session_cost"], 6)
        if emit_log:
            lg.info(
                "AG2_RUNTIME_SUMMARY file=%s records=%s total_tokens=%s total_cost=%s session_id=%s session_tokens=%s session_cost=%s",
                stats["file"], stats["records"], stats["total_tokens"], stats["total_cost"],
                stats["session_id"], stats["session_tokens"], stats["session_cost"],
            )
    except Exception as e:  # pragma: no cover - defensive
        if emit_log:
            lg.error(f"Failed summarizing runtime log {path}: {e}")
    return stats

