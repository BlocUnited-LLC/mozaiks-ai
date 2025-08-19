# Event Architecture Alignment Plan

## Current State Analysis

Your project currently uses "events" in three distinct contexts that need to be properly separated:

### 1. **Business Logic Events** (Logging/Monitoring)
- **Purpose**: Application lifecycle and monitoring
- **Location**: `core/events/unified_event_dispatcher.py` via `emit_business_event()`
- **Examples**: `SERVER_STARTUP_COMPLETED`, `WORKFLOW_SYSTEM_READY`
- **Type**: **Logging events** for observability (handled by BusinessLogHandler)

### 2. **AG2 Runtime Events** (Core Workflow Events)
- **Purpose**: Real AG2 agent communication and workflow execution
- **Location**: `orchestration_patterns.py`, `persistence_manager.py`
- **Examples**: `message`, `input_request`, `termination`
- **Type**: **Runtime events** from AG2's `result.events` stream

### 3. **UI Tool Events** (Interactive User Events)
- **Purpose**: Agent-to-UI communication for dynamic components
- **Location**: `simple_transport.py`, tool files
- **Examples**: `agent_api_key_input`, `file_download_center`
- **Type**: **UI interaction events** for user input collection

## Problems with Current Implementation

1. **Terminology Confusion**: All three use "event_type" but serve different purposes
2. **Mixed Responsibilities**: Events are used for logging, persistence, AND UI interaction
3. **Legacy Code**: `load_chat_state` is outdated and should be removed
4. **Inconsistent Patterns**: Different event handling patterns across the system

## Proposed Unified Architecture

### 1. **Rename Event Types for Clarity**

```python
# BEFORE (Confusing)
event_type="WORKFLOW_STARTED"           # Business logging
event_type="message"                    # AG2 runtime
event_type="agent_api_key_input"        # UI interaction

# AFTER (Clear separation)
log_event_type="WORKFLOW_STARTED"       # Business logging
ag2_event_type="message"                # AG2 runtime  
ui_tool_id="agent_api_key_input"        # UI interaction
```

### 2. **Centralized Event System Architecture**

```
┌─────────────────────────────────────────────────────────────────┐
│                     UNIFIED EVENT SYSTEM                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │  BUSINESS LOG   │  │  AG2 RUNTIME    │  │  UI INTERACTION │  │
│  │     EVENTS      │  │     EVENTS      │  │     EVENTS      │  │
│  │                 │  │                 │  │                 │  │
│  │ • Lifecycle     │  │ • Messages      │  │ • Tool Requests │  │
│  │ • Performance   │  │ • Handoffs      │  │ • User Input    │  │
│  │ • Errors        │  │ • Termination   │  │ • Responses     │  │
│  │ • Monitoring    │  │ • State Changes │  │ • Components    │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
│           │                     │                     │          │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │ Log Files       │  │ Event Stream    │  │ WebSocket/API   │  │
│  │ • business.log  │  │ • Persistence   │  │ • Transport     │  │
│  │ • performance   │  │ • Real-time     │  │ • Component     │  │
│  │ • workflows.log │  │ • Recovery      │  │   Registry      │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 3. **Implementation Plan**

#### Phase 1: Remove Legacy Code
- Remove `load_chat_state` from `shared_app.py` (only used for a deprecated debugging API)
- Remove any backward-compat shims and transitional branches

#### Phase 2: Rename Event Types for Clarity
- Business events: `log_event_type`
- AG2 events: `ag2_event_type` 
- UI events: `ui_tool_id`

#### Phase 3: Consolidate Event Handlers
- Create unified event dispatcher
- Separate concerns cleanly
- Do not retain backward-compat layers; migrate in place for simplicity

#### Phase 4: Documentation and Testing
- Update all documentation
- Create comprehensive examples
- Test each event type independently

## Benefits of Aligned Architecture

1. **Clear Separation**: Each event type has distinct purpose and handling
2. **Better Debugging**: Easy to trace events through specific channels
3. **Maintainability**: Clear patterns for adding new event types
4. **Performance**: Optimized handling for each event category
5. **Scalability**: Easy to extend each event system independently

## Next Steps

1. Confirm removal of `load_chat_state` 
2. Implement Phase 1 cleanup
3. Begin systematic renaming in Phase 2
4. Test each phase thoroughly before proceeding

This alignment will create a robust, maintainable event system that supports all your use cases without confusion.
