# ======================================================================
# FILE: logs/logging_config.py (refactored)
# CHANGELOG: Unified setup, removed premature global logger creation,
# added secret redaction + safe_extra, clarified helpers.
# ======================================================================
from __future__ import annotations

import logging, logging.handlers, os, json, traceback, sys, time
from pathlib import Path
from typing import Sequence, Optional, Dict, Any, Iterable
from datetime import datetime, timezone
from contextlib import contextmanager

# ----------------------------------------------------------------------
# Directory & file paths
# ----------------------------------------------------------------------
LOGS_DIR = Path(__file__).parent / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

CHAT_LOG_FILE        = LOGS_DIR / "agent_chat.log"
BUSINESS_LOG_FILE    = LOGS_DIR / "business_logic.log"
ERROR_LOG_FILE       = LOGS_DIR / "errors.log"
PERFORMANCE_LOG_FILE = LOGS_DIR / "performance.log"
WEBSOCKET_LOG_FILE   = LOGS_DIR / "websocket.log"
TOKEN_LOG_FILE       = LOGS_DIR / "token_tracking.log"
WORKFLOW_LOG_FILE    = LOGS_DIR / "workflows.log"

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
        base = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "mod": record.module,
            "fn": record.funcName,
            "line": record.lineno,
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
_chat_kw        = ['agent_chat','conversation','reply','message_from','message_to','user_input','autogen.agentchat','handoff_executed','agent_response','group_chat','ag2','initiate_chat']
_business_kw    = ['business.','database','mongodb','workflow','generator','config','startup','registry','tools','file_manager','observability']
_perf_kw        = ['duration','performance','tokens','cost','usage','metrics']
_websocket_kw   = ['websocket','ws','transport','connection']
_token_kw       = ['token_tracking','total_tokens','prompt_tokens','completion_tokens']
_workflow_kw    = ['workflow','orchestration','handoff','workflow_execution']

ChatLogFilter       = lambda: KeywordFilter(_chat_kw, exclude_keywords=_business_kw)
BusinessLogicFilter = lambda: KeywordFilter(_business_kw)
PerformanceFilter   = lambda: KeywordFilter(_perf_kw)
ErrorFilter         = lambda: KeywordFilter([], min_level=logging.WARNING)
WebSocketFilter     = lambda: KeywordFilter(_websocket_kw)
TokenFilter         = lambda: KeywordFilter(_token_kw)
WorkflowFilter      = lambda: KeywordFilter(_workflow_kw)

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
    business_level: str = "INFO",
    console_level: str = "INFO",
    max_file_size: int = 10*1024*1024,      # 10 MB
    backup_count: int  = 5,
) -> None:
    """
    Configure root logger with five rotating file handlers + console,
    using DRY factories and generic filters.
    Prevents duplicate initialization with global flag.
    """
    global _logging_initialized
    if _logging_initialized: return
    _logging_initialized = True
    root = logging.getLogger(); root.handlers.clear(); root.setLevel(logging.DEBUG)
    detailed = ProductionJSONFormatter(); console_fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S")
    spec = [
        (CHAT_LOG_FILE,        getattr(logging, chat_level.upper()), ChatLogFilter()),
        (BUSINESS_LOG_FILE,    getattr(logging, business_level.upper()), BusinessLogicFilter()),
        (ERROR_LOG_FILE,       logging.WARNING,                      ErrorFilter()),
        (PERFORMANCE_LOG_FILE, logging.INFO,                         PerformanceFilter()),
        (WEBSOCKET_LOG_FILE,   logging.INFO,                         WebSocketFilter()),
        (TOKEN_LOG_FILE,       logging.INFO,                         TokenFilter()),
        (WORKFLOW_LOG_FILE,    logging.DEBUG,                        WorkflowFilter()),
    ]
    for path, lvl, flt in spec: root.addHandler(_make_handler(path, lvl, detailed, log_filter=flt, max_bytes=max_file_size, backup_count=backup_count))
    ch = logging.StreamHandler(); ch.setLevel(getattr(logging, console_level.upper())); ch.setFormatter(console_fmt); root.addHandler(ch)
    for noisy in ("openai","httpx","urllib3","azure","motor","pymongo","uvicorn.access","openlit"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    logging.getLogger(__name__).info("Logging initialized")

def reset_logging_state():
    """Reset logging initialization state for testing purposes"""
    global _logging_initialized; _logging_initialized = False

# Public getters -----------------------------------------------------
get_chat_logger = lambda name: logging.getLogger(f"chat.{name}")
get_business_logger = lambda name: logging.getLogger(f"business.{name}")
get_performance_logger = lambda name: logging.getLogger(f"performance.{name}")
get_token_manager_logger = lambda name: logging.getLogger(f"token.{name}")

# High-level event helpers (retain API) ------------------------------
def log_chat_interaction(
    *,
    chat_id: str,
    agent_name: str,
    message: str,
    workflow_name: str,
    level: str = "INFO",
) -> None:
    logger = get_chat_logger("interaction"); log_fn = getattr(logger, level.lower()); snippet = message[:200] + ("…" if len(message) > 200 else ""); log_fn("[%s] %s | %s: %s", workflow_name, chat_id, agent_name, snippet)

def log_business_event(
    *,
    log_event_type: str,
    description: str,
    context: dict | None = None,
    level: str = "INFO",
    use_dispatcher: bool = False,
) -> None:
    logger = get_business_logger("event"); log_fn = getattr(logger, level.lower()); ctx = f" | Context: {_maybe_redact_mapping(context)}" if context else ""; log_fn("%s: %s%s", log_event_type, description, ctx)

def log_performance_metric(
    *,
    metric_name: str,
    value: float,
    unit: str = "",
    context: dict | None = None,
) -> None:
    logger = get_performance_logger("metrics"); ctx = f" | {_maybe_redact_mapping(context)}" if context else ""; logger.info("%s: %s%s%s", metric_name, value, unit, ctx)

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

def get_context_logger(component: str, **context): return ContextLogger(logging.getLogger(f"mozaiks.{component}"), context)

def get_transport_logger(transport_type: str | None = None, chat_id: str | None = None, **context):
    ctx = {}; ctx.update({k:v for k,v in {"transport_type":transport_type, "chat_id":chat_id}.items() if v}); ctx.update(context); return get_context_logger('transport', **ctx)

def get_workflow_logger(workflow_name: str | None = None, chat_id: str | None = None, enterprise_id: str | None = None, **context):
    ctx = {k:v for k,v in {"workflow_name":workflow_name, "chat_id":chat_id, "enterprise_id":enterprise_id}.items() if v}; ctx.update(context); return get_context_logger('workflow', **ctx)

def get_agent_logger(agent_name: str | None = None, workflow_name: str | None = None, **context):
    ctx = {k:v for k,v in {"agent_name":agent_name, "workflow_name":workflow_name}.items() if v}; ctx.update(context); return get_context_logger('agent', **ctx)

def get_component_logger(component_name: str | None = None, workflow_name: str | None = None, **context):
    ctx = {k:v for k,v in {"component_name":component_name, "workflow_name":workflow_name}.items() if v}; ctx.update(context); return get_context_logger('component', **ctx)

def get_event_logger(event_type: str | None = None, chat_id: str | None = None, **context):
    ctx = {k:v for k,v in {"event_type":event_type, "chat_id":chat_id}.items() if v}; ctx.update(context); return get_context_logger('event', **ctx)

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
def setup_production_logging(): setup_logging(chat_level="INFO", business_level="INFO", console_level="WARNING", max_file_size=50*1024*1024, backup_count=10)

def setup_development_logging(): setup_logging(chat_level="DEBUG", business_level="DEBUG", console_level="INFO")
