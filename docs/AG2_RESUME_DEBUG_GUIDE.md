# AG2 Resume & Group Chat Debugging Guide

## Overview
This refactor adds proper AG2 resume support and debugging capabilities to handle message schema mismatches, user agent inclusion, and terminal tail handling.

## Environment Variables

### GROUPCHAT_DEBUG
- **Values**: `true` | `false` (default: `false`)
- **Purpose**: Enable detailed debugging for AG2 group chat resume
- **When enabled**:
  - Increases AG2 internal logging verbosity (`autogen.agentchat`, `autogen.io`, `autogen.agentchat.group`)
  - Logs normalized message list passed to `a_run_group_chat`
  - Shows agent name mappings and resume path taken

### GROUPCHAT_EXPLICIT_RESUME
- **Values**: `true` | `false` (default: `false`)
- **Purpose**: Use explicit resume path for debugging instead of standard `a_run_group_chat`
- **When enabled**:
  - Calls `pattern.prepare_group_chat()` and `group_manager.a_resume()` directly
  - Logs the `last_agent.name` and `last_message` returned by `a_resume`
  - Falls back to standard path if explicit resume fails

### GROUPCHAT_NAME_ALIASES
- **Values**: JSON string mapping, e.g. `{"StoredAgentName":"ActualAgentName"}`
- **Purpose**: **Optional** manual override for edge cases where auto-mapping fails
- **Default**: Auto-mapping handles most name mismatches automatically
- **Example**: `GROUPCHAT_NAME_ALIASES='{"SpecialBot":"assistant"}'`

## Automatic Name Mapping (Workflow Agnostic)

The system now **automatically** maps stored agent names to actual agent names using intelligent strategies:

### Auto-Mapping Strategies (in order):

1. **Exact Match**: `"user"` stored → `"user"` agent ✅
2. **Case-Insensitive**: `"User"` stored → `"user"` agent ✅  
3. **Partial/Contains**: `"UserFeedbackAgent"` stored → `"user"` agent ✅
4. **Pattern Recognition**: 
   - `"CustomerServiceBot"` → `"assistant"` 
   - `"AdminAgent"` → `"admin"`
   - Strips common suffixes: `Agent`, `Bot`, `Proxy`, `Assistant`
5. **Role-Based Fallback**:
   - Messages with user indicators (`user`, `human`, `customer`) → user proxy agent
   - Other messages → first available assistant agent

### Examples of Auto-Mapping:

```
Stored Name              → Mapped To
"UserFeedbackAgent"      → "user" 
"CustomerServiceBot"     → "assistant"
"AdminAssistant"         → "admin"
"SupportAgent"           → "support"  
"Human"                  → "user"
"ChatBot"                → "assistant"
```

### Manual Override (Edge Cases Only):

Only needed for complex cases where auto-mapping fails:

```bash
# Only if auto-mapping doesn't work
export GROUPCHAT_NAME_ALIASES='{"WeirdAgentName":"actual_agent"}'
```

## Message Schema Fixes

### Before (problematic for resume)
```json
{
  "sender": "UserFeedbackAgent",
  "agent_name": "UserFeedbackAgent", 
  "content_text": "Hello",
  "content_json": {},
  "role": "assistant"
}
```

### After (AG2 resume compatible)
```json
{
  "role": "user",
  "name": "user", 
  "content": "Hello"
}
```

## Key Changes

### 1. Message Normalization (`_to_ag2_messages`)
- **Workflow-agnostic**: Automatically maps stored names to actual agent names
- Converts persisted messages to AG2 resume schema
- **Auto-mapping strategies**: exact match → fuzzy match → pattern recognition → role-based fallback
- Maps `agent_name`/`sender` → `name` (with intelligent name resolution)
- Maps `content_text`/`content`/`content_json` → `content`
- **No manual configuration needed** for most workflows

### 2. Terminal Tail Stripping (`_strip_terminal_tail`)
- Removes trailing "TERMINATE" messages
- Removes handoff terminal targets (`{"transition_target": "TerminateTarget"}`)
- Prevents instant workflow termination on resume

### 3. User Agent Inclusion
- Detects user turns in message history (`"role": "user"`)
- Forces `human_in_the_loop=True` if user turns found
- Maps user message names to actual user proxy agent name

### 4. Canonical Name Field
- Added `name` field to persisted messages (same as `agent_name`)
- Future-proofs resume compatibility
- Eliminates need for name guessing during normalization

## Usage Examples

### Basic Debugging (No Setup Required)
```bash
export GROUPCHAT_DEBUG=true
# Auto-mapping handles name mismatches across all workflows
```

### Explicit Resume Testing  
```bash
export GROUPCHAT_DEBUG=true
export GROUPCHAT_EXPLICIT_RESUME=true
# Will use explicit resume path and show binding details
```

### Manual Override (Only if Auto-Mapping Fails)
```bash
export GROUPCHAT_NAME_ALIASES='{"WeirdStoredName":"actual_agent_name"}'
# Only needed for edge cases where auto-mapping doesn't work
```

## Verification

### Resume Path Detection
Look for these log messages when `GROUPCHAT_DEBUG=true`:

- `"[DEBUG] Detected user turns in history - forcing human_in_the_loop=True"`
- `"[DEBUG] Normalized messages for resume (count=X): [...]"`
- `"[DEBUG] Added alias mapping 'StoredName' -> 'ActualName' for resume compatibility"`

### Explicit Resume Path
When `GROUPCHAT_EXPLICIT_RESUME=true`:

- `"[DEBUG] Using explicit resume path for debugging"`
- `"[DEBUG] a_resume bound last_agent=AgentName last_message=..."`

### Success Indicators
- AG2 calls `GroupChatManager.a_resume` instead of starting fresh
- User turns in history are properly handled with correct agent binding
- No instant termination when resuming from terminal states

## Troubleshooting

### Issue: Resume doesn't engage
- Check that normalized messages have proper `{"role", "name", "content"}` structure
- Verify user agent names match message names or use alias mapping
- Ensure no terminal tail messages remain

### Issue: User agent misbinding
- Set alias mapping: `GROUPCHAT_NAME_ALIASES='{"StoredUserName":"user"}'`
- Check that `human_in_the_loop=True` when user turns exist

### Issue: Instant termination on resume
- Verify terminal tail stripping removes `"TERMINATE"` and `TerminateTarget` messages
- Check last message in normalized list isn't terminal
