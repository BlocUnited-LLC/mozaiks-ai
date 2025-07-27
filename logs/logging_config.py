# ======================================================================
# FILE: logs/logging_config.py
# DESCRIPTION: Production-ready logging configuration with structured output
# ======================================================================

from __future__ import annotations

import logging
import logging.handlers
import os
import json
import traceback
import sys
from pathlib import Path
from typing import Sequence, Optional, Dict, Any
from datetime import datetime, timezone

# ----------------------------------------------------------------------
# Directory & file paths
# ----------------------------------------------------------------------
LOGS_DIR = Path(__file__).parent / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

CHAT_LOG_FILE        = LOGS_DIR / "agent_chat.log"
BUSINESS_LOG_FILE    = LOGS_DIR / "business_logic.log"
ERROR_LOG_FILE       = LOGS_DIR / "errors.log"
PERFORMANCE_LOG_FILE = LOGS_DIR / "performance.log"
WEBSOCKET_LOG_FILE    = LOGS_DIR / "websocket.log"
TOKEN_LOG_FILE       = LOGS_DIR / "token_tracking.log"
LLM_LOG_FILE         = LOGS_DIR / "llm_operations.log"
SECURITY_LOG_FILE    = LOGS_DIR / "security.log"
COMPONENT_LOG_FILE   = LOGS_DIR / "components.log"
WORKFLOW_LOG_FILE    = LOGS_DIR / "workflows.log"
EVENT_LOG_FILE       = LOGS_DIR / "events.log"

# ----------------------------------------------------------------------
# Production JSON Formatter
# ----------------------------------------------------------------------
class ProductionJSONFormatter(logging.Formatter):
    """Structured JSON logging for production systems"""
    
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "thread_id": record.thread,
            "process_id": record.process
        }
        
        # Add exception information if present
        if record.exc_info:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "traceback": traceback.format_exception(*record.exc_info)
            }
        
        # Add extra fields if present
        for key, value in record.__dict__.items():
            if key not in ['name', 'msg', 'args', 'levelname', 'levelno', 'pathname', 'filename',
                          'module', 'exc_info', 'exc_text', 'stack_info', 'lineno', 'funcName',
                          'created', 'msecs', 'relativeCreated', 'thread', 'threadName',
                          'processName', 'process', 'message']:
                if 'extra' not in log_entry:
                    log_entry['extra'] = {}
                log_entry['extra'][key] = value
            
        return json.dumps(log_entry, ensure_ascii=False)

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
        super().__init__()
        self.keywords = tuple(k.lower() for k in keywords)
        self.exclude_keywords = tuple(k.lower() for k in exclude_keywords)
        self.min_level = min_level

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: D401
        if self.min_level and record.levelno < self.min_level:
            return False

        msg = record.getMessage().lower()
        mod = record.name.lower()
        
        # First check exclusions
        if self.exclude_keywords:
            if any(k in msg or k in mod for k in self.exclude_keywords):
                return False
        
        # Then check inclusions
        if not self.keywords:
            return True  # no keyword filtering
        
        return any(k in msg or k in mod for k in self.keywords)

# Domain-specific filters (lambdas keep the file short & declarative)
_chat_kw        = ['agent_chat', 'conversation', 'reply', 'message_from', 'message_to', 
                   'user_input', 'autogen.agentchat', 'handoff_executed', 'agent_response',
                   'chat.', 'core_groupchat', 'group_chat', 'ag2', 'initiate_chat',
                   'chat_manager', 'agent_conversation', 'agent_observability']
_business_kw    = ['business.', 'database', 'mongodb', 'workflow', 'generator', 'config',
                   'token', 'api', 'initialization', 'startup', 'health', 'GENERATOR_',
                   'HANDOFF_WIRING', 'HOOK_WIRING', 'orchestration', 'registry', 'tools',
                   'file_manager', 'observability']          # ← ADDED so YAML exporter logs appear
_perf_kw        = ['duration', 'time', 'performance', 'tokens', 'cost',
                   'usage', 'efficiency', 'memory', 'timeout', 'metrics']
_websocket_kw   = ['websocket', 'ws', 'socket', 'transport', 'connection',
                   'transport_manager', 'simple_event']
_token_kw       = ['token_tracking', 'TOKEN', 'cost', 'usage', 'openai', 'model_usage']
_component_kw   = ['component', 'manifest', 'artifact', 'inline', 'ui_component', 
                   'component_loading', 'workflow_component']
_workflow_kw    = ['workflow', 'generator', 'orchestration', 'agent_handoff', 
                   'workflow_execution', 'workflow_name']
_event_kw       = ['simple_event', 'route_to_artifact', 'route_to_chat', 'ui_tool_action',
                   'event_processing', 'event_type']

ChatLogFilter       = lambda: KeywordFilter(_chat_kw, exclude_keywords=_business_kw)
BusinessLogicFilter = lambda: KeywordFilter(_business_kw)
PerformanceFilter   = lambda: KeywordFilter(_perf_kw)
ErrorFilter         = lambda: KeywordFilter([], min_level=logging.WARNING)
WebSocketFilter     = lambda: KeywordFilter(_websocket_kw)
TokenFilter         = lambda: KeywordFilter(_token_kw)
ComponentFilter     = lambda: KeywordFilter(_component_kw)
WorkflowFilter      = lambda: KeywordFilter(_workflow_kw)
EventFilter         = lambda: KeywordFilter(_event_kw)

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
    if log_filter is not None:
        h.addFilter(log_filter)
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
    max_file_size: int = 10 * 1024 * 1024,      # 10 MB
    backup_count: int  = 5,
) -> None:
    """
    Configure root logger with five rotating file handlers + console,
    using DRY factories and generic filters.
    Prevents duplicate initialization with global flag.
    """
    global _logging_initialized
    
    # Prevent duplicate logging setup
    if _logging_initialized:
        return
        
    _logging_initialized = True
    
    root = logging.getLogger()
    root.handlers.clear()           # nuke any prior config (uvicorn etc.)
    root.setLevel(logging.DEBUG)    # capture *everything*; handlers filter

    # --------------------------------------------------------------
    # Formatters
    # --------------------------------------------------------------
    detailed_fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)-30s | "
        "%(funcName)-20s:%(lineno)-4d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # --------------------------------------------------------------
    # File handlers (spec-driven loop = zero copy-paste)
    # --------------------------------------------------------------
    spec = [
        (CHAT_LOG_FILE,        getattr(logging, chat_level.upper()),          ChatLogFilter()),
        (BUSINESS_LOG_FILE,    getattr(logging, business_level.upper()),      BusinessLogicFilter()),
        (ERROR_LOG_FILE,       logging.WARNING,                               ErrorFilter()),
        (PERFORMANCE_LOG_FILE, logging.INFO,                                  PerformanceFilter()),
        (WEBSOCKET_LOG_FILE,   logging.INFO,                                  WebSocketFilter()),
        (TOKEN_LOG_FILE,       logging.INFO,                                  TokenFilter()),
        (COMPONENT_LOG_FILE,   logging.DEBUG,                                 ComponentFilter()),
        (WORKFLOW_LOG_FILE,    logging.DEBUG,                                 WorkflowFilter()),
        (EVENT_LOG_FILE,       logging.DEBUG,                                 EventFilter()),
    ]

    for path, lvl, fltr in spec:
        root.addHandler(_make_handler(
            path=path,
            level=lvl,
            formatter=detailed_fmt,
            log_filter=fltr,
            max_bytes=max_file_size,
            backup_count=backup_count,
        ))

    # --------------------------------------------------------------
    # Console handler
    # --------------------------------------------------------------
    ch = logging.StreamHandler()
    ch.setLevel(getattr(logging, console_level.upper()))
    ch.setFormatter(console_fmt)
    root.addHandler(ch)

    # --------------------------------------------------------------
    # Silence noisy externals
    # --------------------------------------------------------------
    for noisy in ("openai", "httpx", "urllib3", "azure",
                  "motor", "pymongo", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    
    logging.getLogger("autogen").setLevel(logging.INFO)
    logging.getLogger("autogen.oai").setLevel(logging.WARNING)
    logging.getLogger("autogen.runtime_logging").setLevel(logging.WARNING)

    # Startup banner
    logger = logging.getLogger(__name__)
    logger.info("🎯 Logging system initialised")
    logger.info("📁 Chat logs:        %s", CHAT_LOG_FILE)
    logger.info("🏢 Business logs:    %s", BUSINESS_LOG_FILE)
    logger.info("❌ Error logs:       %s", ERROR_LOG_FILE)
    logger.info("⚡ Performance logs: %s", PERFORMANCE_LOG_FILE)
    logger.info("📡 WebSocket logs:   %s", WEBSOCKET_LOG_FILE)
    logger.info("💰 Token logs:       %s", TOKEN_LOG_FILE)
    logger.info("🧩 Component logs:   %s", COMPONENT_LOG_FILE)
    logger.info("🔄 Workflow logs:    %s", WORKFLOW_LOG_FILE)
    logger.info("📧 Event logs:       %s", EVENT_LOG_FILE)


def reset_logging_state():
    """Reset logging initialization state for testing purposes"""
    global _logging_initialized
    _logging_initialized = False
# ----------------------------------------------------------------------
# Convenience helpers
# ----------------------------------------------------------------------
def get_chat_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"chat.{name}")

def get_business_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"business.{name}")

def get_performance_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"performance.{name}")

def get_token_manager_logger(name: str) -> logging.Logger:
    """Get consolidated token logger for all token-related activities."""
    logger = logging.getLogger(f"token.{name}")
    if not logger.handlers:
        handler = logging.handlers.RotatingFileHandler(
            TOKEN_LOG_FILE,  # Use consolidated token log file
            maxBytes=10 * 1024 * 1024,
            backupCount=5
        )
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)-30s | %(funcName)-15s:%(lineno)-4s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
    return logger

# ----------------------------------------------------------------------
# Convenience wrapper functions
# ----------------------------------------------------------------------
def log_chat_interaction(
    *,
    chat_id: str,
    agent_name: str,
    message: str,
    workflow_name: str,
    level: str = "INFO",
) -> None:
    logger  = get_chat_logger("interaction")
    log_fn  = getattr(logger, level.lower())
    snippet = message[:200] + ("…" if len(message) > 200 else "")
    log_fn("💬 [%s] %s | %s: %s", workflow_name, chat_id, agent_name, snippet)

def log_business_event(
    *,
    event_type: str,
    description: str,
    context: dict | None = None,
    level: str = "INFO",
) -> None:
    logger = get_business_logger("event")
    log_fn = getattr(logger, level.lower())
    ctx    = f" | Context: {context}" if context else ""
    log_fn("🏢 %s: %s%s", event_type, description, ctx)

def log_performance_metric(
    *,
    metric_name: str,
    value: float,
    unit: str = "",
    context: dict | None = None,
) -> None:
    logger = get_performance_logger("metrics")
    ctx    = f" | {context}" if context else ""
    logger.info("⚡ %s: %s%s%s", metric_name, value, unit, ctx)

# ----------------------------------------------------------------------
# Environment-specific helpers
# ----------------------------------------------------------------------
def setup_production_logging() -> None:
    setup_logging(
        chat_level="INFO",
        business_level="INFO",
        console_level="WARNING",
        max_file_size=50 * 1024 * 1024,
        backup_count=10,
    )

def setup_development_logging() -> None:
    setup_logging(
        chat_level="DEBUG",
        business_level="DEBUG",
        console_level="INFO",
        max_file_size=10 * 1024 * 1024,
        backup_count=3,
    )

# ----------------------------------------------------------------------
# Production Logger Setup
# ----------------------------------------------------------------------
def setup_logger(name: str, level: str = "INFO") -> logging.Logger:
    """Setup production logger with proper formatting and handlers"""
    logger = logging.getLogger(name)
    
    # Avoid duplicate handlers
    if logger.handlers:
        return logger
    
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    
    # Console handler with UTF-8 encoding for emoji support
    try:
        # Try to create a UTF-8 console handler
        import io
        import codecs
        
        # Create a UTF-8 wrapped stdout for Windows emoji support
        if sys.platform.startswith('win'):
            utf8_stdout = codecs.getwriter('utf-8')(sys.stdout.buffer)
            console_handler = logging.StreamHandler(utf8_stdout)
        else:
            console_handler = logging.StreamHandler(sys.stdout)
    except (AttributeError, ImportError):
        # Fallback to regular handler
        console_handler = logging.StreamHandler()
    
    console_handler.setFormatter(ProductionJSONFormatter())
    logger.addHandler(console_handler)
    
    # File handlers with UTF-8 encoding
    error_handler = logging.handlers.RotatingFileHandler(
        ERROR_LOG_FILE, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(ProductionJSONFormatter())
    logger.addHandler(error_handler)
    
    # Business logic file handler
    business_handler = logging.handlers.RotatingFileHandler(
        BUSINESS_LOG_FILE, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8'
    )
    business_handler.setLevel(logging.INFO)
    business_handler.setFormatter(ProductionJSONFormatter())
    logger.addHandler(business_handler)
    
    return logger

# Global logger instances for commonly used modules
core_logger = setup_logger("core")
transport_logger = setup_logger("transport")
ui_logger = setup_logger("ui")
workflow_logger = setup_logger("workflow")

# ----------------------------------------------------------------------
# Enhanced Context-Aware Logging Helpers
# ----------------------------------------------------------------------
def log_with_context(logger, level, message, **context):
    """Enhanced logging with context data"""
    # Handle ContextLogger objects
    if hasattr(logger, '_logger'):
        actual_logger = logger._logger
        # Merge contexts
        if hasattr(logger, '_context'):
            context.update(logger._context)
    else:
        actual_logger = logger
    
    if context:
        # Add context to the log record
        extra_data = {
            'context': context,
            **context  # Also add directly for filtering
        }
        actual_logger.log(level, message, extra=extra_data)
    else:
        actual_logger.log(level, message)

def get_context_logger(component: str, **context):
    """Get a logger with built-in context"""
    logger = setup_logger(f"mozaiks.{component}")
    
    # Create a wrapper that automatically includes context
    class ContextLogger:
        def __init__(self, base_logger, context):
            self._logger = base_logger
            self._context = context
            
        def info(self, msg, **extra):
            log_with_context(self._logger, logging.INFO, msg, **{**self._context, **extra})
            
        def debug(self, msg, **extra):
            log_with_context(self._logger, logging.DEBUG, msg, **{**self._context, **extra})
            
        def warning(self, msg, **extra):
            log_with_context(self._logger, logging.WARNING, msg, **{**self._context, **extra})
            
        def error(self, msg, exc_info=False, **extra):
            log_with_context(self._logger, logging.ERROR, msg, **{**self._context, **extra})
            if exc_info:
                self._logger.exception(msg, extra={**self._context, **extra})
                
        def with_context(self, **new_context):
            """Add more context"""
            return ContextLogger(self._logger, {**self._context, **new_context})
    
    return ContextLogger(logger, context)

# Component-specific logger factories
def get_transport_logger(transport_type: str | None = None, chat_id: str | None = None, **context):
    """Get transport-specific logger with context"""
    ctx = {}
    if transport_type:
        ctx['transport_type'] = transport_type
    if chat_id:
        ctx['chat_id'] = chat_id
    ctx.update(context)
    return get_context_logger('transport', **ctx)

def get_workflow_logger(workflow_name: str | None = None, chat_id: str | None = None, enterprise_id: str | None = None, **context):
    """Get workflow-specific logger with context"""
    ctx = {}
    if workflow_name:
        ctx['workflow_name'] = workflow_name
    if chat_id:
        ctx['chat_id'] = chat_id
    if enterprise_id:
        ctx['enterprise_id'] = enterprise_id
    ctx.update(context)
    return get_context_logger('workflow', **ctx)

def get_agent_logger(agent_name: str | None = None, workflow_name: str | None = None, **context):
    """Get agent-specific logger with context"""
    ctx = {}
    if agent_name:
        ctx['agent_name'] = agent_name
    if workflow_name:
        ctx['workflow_name'] = workflow_name
    ctx.update(context)
    return get_context_logger('agent', **ctx)

def get_component_logger(component_name: str | None = None, workflow_name: str | None = None, **context):
    """Get UI component logger with context"""
    ctx = {}
    if component_name:
        ctx['component_name'] = component_name
    if workflow_name:
        ctx['workflow_name'] = workflow_name
    ctx.update(context)
    return get_context_logger('component', **ctx)

def get_event_logger(event_type: str | None = None, chat_id: str | None = None, **context):
    """Get event system logger with context"""
    ctx = {}
    if event_type:
        ctx['event_type'] = event_type
    if chat_id:
        ctx['chat_id'] = chat_id
    ctx.update(context)
    return get_context_logger('event', **ctx)

# Enhanced business event logging
def log_business_event_enhanced(event_type: str, description: str, context: dict | None = None, logger=None, **extra_context):
    """Enhanced business event logging with context"""
    if logger is None:
        logger = get_business_logger("enhanced_business")
    
    all_context = {}
    if context:
        all_context.update(context)
    all_context.update(extra_context)
    
    log_with_context(logger, logging.INFO, f"🔵 {event_type}: {description}", 
                    event_type=event_type, **all_context)

# Operation timing helper
import time
from contextlib import contextmanager

@contextmanager
def log_operation(logger, operation_name: str, **context):
    """Context manager for operation logging with timing"""
    start_time = time.time()
    logger.info(f"🚀 Starting {operation_name}", operation="start", **context)
    
    try:
        yield logger
        duration = time.time() - start_time
        logger.info(f"✅ Completed {operation_name}", 
                   operation="success", duration_seconds=duration, **context)
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"❌ Failed {operation_name}: {e}", 
                    operation="error", duration_seconds=duration, 
                    error_type=type(e).__name__, **context)
        raise
