# Migration Guide: Old → New Contextual UI System

## Overview
The contextual UI system has been completely redesigned to be truly **dynamic, modular, and scalable** using AG2-native patterns.

## What Changed

### ❌ **REMOVED** (Old System)
- `context_adjustment.py` bridge system
- `"context_adjustment": true` configuration in workflow.json  
- Hardcoded component handlers
- Manual agent tool registration

### ✅ **NEW** (AG2-Native System)
- Direct AG2 ContextVariables integration
- Generic component action system
- Automatic tool registration
- Zero configuration required

## Migration Steps

### 1. Remove old configurations
```json
// Remove this from workflow.json:
"context_adjustment": true  // ← DELETE THIS LINE
```

### 2. Update component calls (if needed)
```javascript
// Old way (still works):
simpleTransport.sendComponentAction(componentId, actionType, actionData);

// New way (same API):
simpleTransport.sendComponentAction(componentId, actionType, actionData);
```

### 3. Agent access (same tools)
```python
# Agents can still use these tools:
get_ui_context_summary()    # Get overall UI state
check_component_state(componentId)  # Check specific component
```

## Benefits of New System

| Feature | Old System | New System |
|---------|------------|------------|
| **Configuration** | Required workflow.json setup | Zero config needed |
| **Scalability** | Hardcoded per component | Generic for any component |
| **Modularity** | Coupled to specific agents | Works with any agent |
| **AG2 Integration** | Bridge/wrapper system | Native AG2 tools |
| **Development** | Complex setup | Drop-in components |

## Testing
Run the test to verify everything works:
```bash
python test_ag2_contextual_ui.py
```

✅ **No code changes needed** - your existing components still work!  
✅ **Just remove** `"context_adjustment": true` from workflow.json  
✅ **System is now** truly dynamic, modular, and scalable
