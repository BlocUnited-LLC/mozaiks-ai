# AG2 (AutoGen) Unified Runtime Logging System

## Overview

This document describes the unified AG2 runtime logging system that consolidates all AG2/AutoGen logging functionality into a single, coherent system. This replaces the previous scattered logging approaches with one unified solution.

## What Was Fixed

### Previous Problems:
1. **Duplicate Systems**: Multiple AG2 logging systems (`runtime_logging` + `realtime_token_logger`) 
2. **Scattered Configuration**: Multiple env vars (`AUTOGEN_RUNTIME_LOGGING`, `AUTOGEN_RUNTIME_LOG_FILE`)
3. **OpenAIWrapper Issues**: Runtime logs showing OpenAIWrapper serialization failures
4. **Inconsistent Setup**: AG2 logging scattered across multiple files with different patterns
5. **Manual Cleanup**: Complex manual start/stop logic in orchestration_patterns.py

### Solution Implemented:
- **Single System**: `core/observability/ag2_runtime_logger.py` handles all AG2 logging
- **Unified Configuration**: Single `AG2_RUNTIME_LOGGING` environment variable
- **Automatic Management**: Context manager handles start/stop automatically
- **Integrated Token Tracking**: Works with existing `realtime_token_logger.py`
- **Smart Defaults**: Intelligent file path resolution and directory creation
- **Secret Sanitization**: Automatic log sanitization after sessions

## Configuration

### Environment Variables

```bash
# Enable AG2 runtime logging (replaces old AUTOGEN_RUNTIME_LOGGING)
AG2_RUNTIME_LOGGING=true

# Optional: Override default log file path  
# Default: logs/logs/ag2_runtime.log (or LOGS_BASE_DIR/ag2_runtime.log if set)
AG2_RUNTIME_LOG_FILE=logs/logs/ag2_runtime.log
```

### Supported Values for AG2_RUNTIME_LOGGING:
- `true`, `1`, `on`, `enabled`, `file` → Enable logging
- `false`, `0`, `off`, `disabled`, (empty) → Disable logging

## Usage

### In Workflow Code (Automatic)

The system automatically integrates with your workflow orchestration:

```python
# In core/workflow/orchestration_patterns.py - ALREADY INTEGRATED
from core.observability.ag2_runtime_logger import ag2_logging_session

with ag2_logging_session(chat_id, workflow_name, enterprise_id):
    # Your AG2 workflow code here
    # All OpenAI API calls, token usage, costs are automatically logged
    result = await run_group_chat(...)
```

### Manual Usage (For Custom Scripts)

```python
from core.observability.ag2_runtime_logger import get_ag2_runtime_logger, ag2_logging_session

# Context manager approach (recommended)
with ag2_logging_session(chat_id="chat_123", workflow_name="my_workflow"):
    # Your AG2 code here
    pass

# Manual control approach
logger = get_ag2_runtime_logger()
if logger.start_session(chat_id="chat_123", workflow_name="my_workflow"):
    try:
        # Your AG2 code here
        pass
    finally:
        logger.stop_session()
```

## What Gets Logged

The unified system captures:

1. **OpenAI API Calls**: All chat completions, embeddings, etc.
2. **Token Usage**: Prompt tokens, completion tokens, total tokens
3. **Cost Tracking**: Real-time cost calculation based on model pricing  
4. **Session Metadata**: Chat ID, workflow name, enterprise ID, timestamps
5. **Agent Events**: AG2 agent interactions and tool calls
6. **Error Handling**: Failed API calls and retry attempts

### Log File Format

```
Started new session with Session ID: 12345678-1234-1234-1234-123456789abc
# MOZAIKS SESSION START: {"event_type": "session_start", "session_info": {...}}
{"client_id": 123, "wrapper_id": 456, "session_id": "...", "class": "OpenAI", ...}
[Additional AG2 runtime events...]
```

## Integration Points

### With Performance Manager
- Token counts and costs are sent to your performance tracking system
- Session summaries include aggregated metrics
- Integrated with AG2 runtime logging (sqlite/file)

### With Realtime Token Logger  
- Automatically starts/stops `RealtimeTokenLogger` alongside AG2 runtime logging
- Provides real-time token tracking through AG2's BaseLogger interface
- Consolidated reporting across both systems

### With Existing Logging
- Uses your existing log configuration from `logs/logging_config.py`
- Respects `LOGS_BASE_DIR` and other environment settings
- Emits structured logs with proper context (chat_id, workflow_name, etc.)

## File Locations

### Default Paths:
- **AG2 Runtime Log**: `logs/logs/ag2_runtime.log`
- **Main Application Log**: `logs/logs/mozaiks.log` (unchanged)
- **Legacy Runtime Log**: `logs/logs/runtime.log` (no longer used)

### With LOGS_BASE_DIR:
If you set `LOGS_BASE_DIR=/app/logs`, then:
- **AG2 Runtime Log**: `/app/logs/ag2_runtime.log`

## Migration from Old System

### What Was Removed:
1. Manual `runtime_logging.start()` and `runtime_logging.stop()` calls
2. `AUTOGEN_RUNTIME_LOGGING=file` requirement (now accepts `true`)
3. `AUTOGEN_RUNTIME_LOG_FILE` (replaced with `AG2_RUNTIME_LOG_FILE`)
4. Complex path resolution and directory creation logic
5. Manual secret sanitization calls

### What Was Kept:
1. Your existing `realtime_token_logger.py` (now integrated)
2. Log summarization functions in `logs/logging_config.py`
3. Secret sanitization via `logs/runtime_sanitizer.py`
4. Performance manager integration

### Breaking Changes:
- **Environment Variables**: Update your `.env`:
  ```bash
  # OLD
  AUTOGEN_RUNTIME_LOGGING=file
  AUTOGEN_RUNTIME_LOG_FILE=/app/logs/autogen_runtime.log
  
  # NEW  
  AG2_RUNTIME_LOGGING=true
  AG2_RUNTIME_LOG_FILE=/app/logs/ag2_runtime.log
  ```

## Troubleshooting

### Common Issues:

1. **AG2 logging not starting**:
   - Check `AG2_RUNTIME_LOGGING` is set to a truthy value
   - Verify autogen package is installed: `pip install autogen`
   - Check logs for import errors

2. **Log file not created**:
   - Verify directory permissions for `logs/logs/` or your `LOGS_BASE_DIR`
   - Check disk space
   - Look for path-related errors in main log

3. **OpenAIWrapper serialization errors**:
   - These are expected and handled automatically
   - AG2 logs the wrapper state without the non-serializable parts
   - Your actual API calls and tokens are still tracked correctly

4. **High log file size**:
   - AG2 logs every API call in detail
   - Consider log rotation if running high-volume workflows
   - Summary statistics are available via `summarize_autogen_runtime_file()`

### Debug Mode:
Enable debug logging to see AG2 system internals:
```python
import logging
logging.getLogger('core.observability.ag2_runtime').setLevel(logging.DEBUG)
logging.getLogger('autogen').setLevel(logging.DEBUG)
```

## Performance Impact

- **Minimal**: AG2 runtime logging uses file I/O with buffering
- **Real-time**: Token tracking provides immediate feedback
- **Asynchronous**: Log processing doesn't block workflow execution
- **Efficient**: Session summaries avoid parsing large files repeatedly

## Security

- **Secret Redaction**: Automatic sanitization of API keys, tokens, credentials
- **Local Storage**: Logs stay on your infrastructure (no external transmission)
- **Session Isolation**: Each workflow session has separate tracking
- **Cleanup**: Old sessions are cleaned up automatically

## Future Enhancements

Planned improvements:
1. **Real-time Dashboard**: Live token/cost monitoring via WebSocket
2. **Cost Budgets**: Automatic workflow throttling based on cost limits
3. **Model Comparison**: Side-by-side efficiency metrics across models
4. **Exporters**: Direct integration with external monitoring (Datadog, etc.)
5. **Historical Analysis**: Trend analysis and optimization recommendations