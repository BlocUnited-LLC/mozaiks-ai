# AG2 UI Tool Standardization Guide

## Overview

This document outlines the standardized approach for UI tool functions and agent message handling across the MozaiksAI platform.

## Mandatory Function Signature for UI Tools

All UI tools must now include these two mandatory parameters:

```python
async def tool_name(
    # ... other tool-specific parameters ...
    agent_message: Annotated[Optional[str], "Mandatory short sentence displayed in the chat along with the artifact for context."] = None,
    context_variables: Annotated[Optional[Any], "Context variables provided by AG2"] = None,
) -> Dict[str, Any]:
```

## Function Signature for Agent Tools

All agent tools must include:

```python
async def tool_name(
    # ... other tool-specific parameters ...
    context_variables: Annotated[Optional[Any], "Context variables provided by AG2"] = None,
) -> Dict[str, Any]:
```

## UI Tool Payload Requirements

All UI tools must include `agent_message` in their payload to the UI:

```python
payload = {
    # ... other payload fields ...
    "agent_message": agent_message or "Default message describing the UI tool action",
    "description": agent_message or "Default message",  # fallback for legacy components
    "agent_message_id": agent_message_id,
}
```

## Chat UI Integration

The `UIToolEventRenderer` component in `ChatInterface.js` now automatically:

1. **Extracts agent messages** from `uiToolEvent.payload.agent_message` or `uiToolEvent.payload.description`
2. **Displays agent messages** above UI tools using standard chat message styling
3. **Shows completion indicators** for inline tools
4. **Maintains consistent styling** with regular agent messages

## Updated Agent System Messages

The `UIFileGenerator` agent now instructs agents to:

- Always include `agent_message` and `context_variables` parameters in generated UI tools
- Use AG2-native dependency injection instead of manual parameter extraction
- Include `agent_message` in UI tool payloads for proper display

## Examples

### UI Tool Implementation
```python
async def example_ui_tool(
    service: str,
    agent_message: Annotated[Optional[str], "Message displayed in chat"] = None,
    context_variables: Annotated[Optional[Any], "AG2 context"] = None,
) -> Dict[str, Any]:
    # Extract context
    chat_id = context_variables.get('chat_id') if context_variables else None
    
    # Build payload with agent message
    payload = {
        "service": service,
        "agent_message": agent_message or "Please provide the required information.",
        "agent_message_id": f"msg_{uuid.uuid4().hex[:10]}",
    }
    
    # Emit UI tool
    return await use_ui_tool("ExampleTool", payload, chat_id=chat_id, ...)
```

### Agent Tool Implementation
```python
async def example_agent_tool(
    data: dict,
    context_variables: Annotated[Optional[Any], "AG2 context"] = None,
) -> Dict[str, Any]:
    # Extract context safely
    enterprise_id = context_variables.get('enterprise_id') if context_variables else None
    
    # Process data and return result
    return {"status": "success", "data": processed_data}
```

## Migration Checklist

For existing tools, ensure:

- [ ] Function signatures include mandatory parameters
- [ ] Context extraction uses `context_variables.get()` pattern
- [ ] UI tool payloads include `agent_message` field
- [ ] No `**runtime` or manual parameter injection patterns remain
- [ ] All tools are AG2-native compatible

## Benefits

1. **Consistent UX**: All UI tools show clear agent messages in chat
2. **AG2 Native**: Full compatibility with AG2's dependency injection
3. **Clean Architecture**: No manual parameter injection complexity
4. **Better Context**: Agent messages provide clear context for UI actions
5. **Maintainable**: Standardized patterns across all tools

## Testing

Test that:
- Agent messages appear above UI tools in chat
- Context variables are properly accessible in tools
- UI tools complete successfully with proper status indication
- No runtime errors from missing parameters
