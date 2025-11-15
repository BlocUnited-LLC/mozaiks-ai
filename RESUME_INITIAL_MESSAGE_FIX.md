# Resume Initial Message Fix

## Problem Statement

When users reconnect to a WebSocket after leaving the site, AgentDriven workflows were showing the hidden UserProxy initial_message in the chat history. This caused:

1. **All messages showing as agent messages**: The UserProxy's initial_message (which should be hidden in AgentDriven mode) was appearing as a regular message
2. **Duplicate/confusing first message**: The kickstart message meant only for AG2 orchestration was visible to users on reconnect

## Root Cause

### Issue 1: No Filtering During Resume
The `GroupChatResumer._replay_messages()` function was not checking:
- The workflow's `startup_mode` (AgentDriven vs UserDriven vs BackendOnly)
- The message's `_mozaiks_seed_kind` metadata field

### Issue 2: visual_agents Configuration
Some workflows had `"user"` (UserProxy) in their `visual_agents` list, which is incorrect for AgentDriven workflows where the initial UserProxy message should be hidden.

## Solution Implemented

### 1. Pass startup_mode to Resume Flow

**File: `core/transport/resume_groupchat.py`**

Added `startup_mode` parameter to:
- `auto_resume_if_needed()` 
- `_replay_messages()`

### 2. Filter initial_message During Replay

**File: `core/transport/resume_groupchat.py` - `_replay_messages()`**

```python
# Filter out initial_message from UserProxy in AgentDriven mode during reconnect
# This prevents the hidden kickstart message from appearing in the UI on resume
should_skip = False
if startup_mode == "AgentDriven":
    # Check if this is the initial_message seed (hidden user proxy kickstart)
    seed_kind = message.get("_mozaiks_seed_kind")
    metadata = message.get("metadata", {})
    metadata_seed_kind = metadata.get("_mozaiks_seed_kind") if isinstance(metadata, dict) else None
    
    if seed_kind == "initial_message" or metadata_seed_kind == "initial_message":
        self.logger.debug(
            "[AUTO_RESUME] Skipping initial_message for AgentDriven workflow (index=%d, chat_id=%s)",
            absolute_index, chat_id
        )
        should_skip = True

if not should_skip:
    await send_event(
        self._build_text_event(message=message, index=absolute_index, chat_id=chat_id),
        chat_id,
    )
```

### 3. Retrieve startup_mode in simple_transport

**File: `core/transport/simple_transport.py` - `_auto_resume_if_needed()`**

```python
# Get workflow name and startup_mode from connection
workflow_name = None
startup_mode = None
if chat_id in self.connections:
    workflow_name = self.connections[chat_id].get("workflow_name")
    if workflow_name:
        try:
            config = workflow_manager.get_config(workflow_name)
            startup_mode = config.get("startup_mode", "AgentDriven")
            logger.debug(f"[AUTO_RESUME] Retrieved startup_mode={startup_mode} for workflow={workflow_name}")
        except Exception as cfg_err:
            logger.warning(f"[AUTO_RESUME] Failed to get workflow config: {cfg_err}")

# Use GroupChatResumer with startup_mode filtering
from core.transport.resume_groupchat import GroupChatResumer
resumer = GroupChatResumer()

await resumer.auto_resume_if_needed(
    chat_id=chat_id,
    enterprise_id=enterprise_id,
    send_event=send_event_wrapper,
    startup_mode=startup_mode,  # ← Pass to resumer for filtering
)
```

## Behavior After Fix

### AgentDriven Workflows
- **First Connection**: User sees only agent messages (UserProxy initial_message is hidden)
- **Reconnection**: User sees same view - initial_message is filtered during replay
- **Example**: Generator workflow where AI greets user first

### UserDriven Workflows
- **First Connection**: User sees their input and agent responses
- **Reconnection**: All messages replayed including user's first message
- **Example**: Standard chat workflows where user initiates

### BackendOnly Workflows
- **First Connection**: No UI interaction expected
- **Reconnection**: Full history replayed (though typically no frontend)
- **Example**: Automated background processing workflows

## Metadata Field: _mozaiks_seed_kind

This field is added during orchestration to track the source of initial messages:

```python
# In orchestration_patterns.py
initial_messages.append({
    "role": "user", 
    "name": "user", 
    "content": initial_message, 
    "_mozaiks_seed_kind": "initial_message"  # ← Marks as hidden kickstart
})
```

Values:
- `"initial_message"` - From config.initial_message (AgentDriven mode, should be hidden in UI)
- `"initial_message_to_user"` - From config.initial_message_to_user (UserDriven mode, should be shown)

## Visual Agents Configuration

### Correct Pattern for AgentDriven:

```json
{
  "visual_agents": [
    "InterviewAgent",
    "ProjectOverviewAgent",
    "APIKeyAgent"
    // NO "user" or "UserProxy" in list
  ]
}
```

### Correct Pattern for UserDriven:

```json
{
  "visual_agents": [
    "user",  // Include UserProxy since user messages should be visible
    "AssistantAgent",
    "HelperAgent"
  ]
}
```

## Files Modified

1. `core/transport/resume_groupchat.py`
   - Added `startup_mode` parameter to resume methods
   - Added filtering logic in `_replay_messages()`

2. `core/transport/simple_transport.py`
   - Updated `_auto_resume_if_needed()` to retrieve and pass `startup_mode`
   - Refactored to use `GroupChatResumer` instead of inline replay logic

## Testing Checklist

- [ ] AgentDriven workflow: First connect → only agent messages visible
- [ ] AgentDriven workflow: Disconnect → Reconnect → same messages, no UserProxy initial message
- [ ] UserDriven workflow: First connect → user input visible
- [ ] UserDriven workflow: Disconnect → Reconnect → all messages including first user input
- [ ] Verify structured outputs persist across reconnection
- [ ] Verify artifact state persists across reconnection

## Related Issues

- Previous issue: All messages showing as "agent" messages instead of proper sender
- Previous issue: UserProxy first message appearing on resume when it shouldn't
- Previous issue: Structured outputs not matching across resume

## Future Enhancements

Consider:
1. Add visual indicator for "resumed session" in UI
2. Cache startup_mode in connection metadata to avoid config lookups
3. Add telemetry for resume success/failure rates
