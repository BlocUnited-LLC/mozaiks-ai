# AG2-Native Tools Guide

With our new AG2-native approach, tools no longer need complex parameter injection. AG2 handles ContextVariables dependency injection automatically.

## How to Write Tools

### Option 1: Accept Full ContextVariables (Recommended)

```python
async def my_tool(user_input: str, context_variables) -> str:
    """Example tool that uses AG2's native ContextVariables dependency injection."""
    
    # Access any context data from ContextVariables
    workflow_name = context_variables.get('workflow_name')
    enterprise_id = context_variables.get('enterprise_id')
    chat_id = context_variables.get('chat_id')
    concept_overview = context_variables.get('concept_overview')
    
    # Your tool logic here
    result = f"Processing {user_input} in {workflow_name} for enterprise {enterprise_id}"
    
    return result
```

### Option 2: No Context Needed

```python
async def simple_tool(user_input: str) -> str:
    """Simple tool that doesn't need context."""
    
    # Just do your work
    result = f"Processed: {user_input}"
    
    return result
```

## Available Context Variables

The orchestrator automatically injects these into ContextVariables:

- `workflow_name`: Current workflow (e.g., "Generator")
- `enterprise_id`: Enterprise ID from WebSocket path
- `chat_id`: Chat session ID from WebSocket path  
- `user_id`: User ID from WebSocket path (optional)

Plus workflow-specific data from `context_variables.json`:

- `concept_overview`: Loaded from MongoDB for Generator workflow
- `schema_overview`: Database schema if enabled
- Any other configured variables

## Migration from Old Approach

### Before (Complex Manual Injection)
```python
async def old_tool(user_input: str, chat_id: str, enterprise_id: str, workflow_name: str) -> str:
    # Had to manually specify each parameter
    pass
```

### After (AG2-Native)
```python
async def new_tool(user_input: str, context_variables) -> str:
    # AG2 automatically injects ContextVariables
    chat_id = context_variables.get('chat_id')
    enterprise_id = context_variables.get('enterprise_id')
    workflow_name = context_variables.get('workflow_name')
    # Plus access to workflow-specific data like concept_overview
    pass
```

## Key Benefits

1. **Simplicity**: No complex parameter injection logic
2. **Reliability**: AG2 handles dependency injection robustly
3. **Flexibility**: Tools can access any context data without changing signatures
4. **Performance**: No wrapper overhead or complex context lookups
5. **AG2 Compliance**: Uses AG2's native patterns throughout
