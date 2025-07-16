# Tool Usage Guide

## Overview

The MozaiksAI project uses a **JSON Manifest-based Tool System** for clean separation of tool definition from registration logic. This system replaces the old approach of using module-level variables (`APPLY_TO`, `TRIGGER`) with a centralized JSON configuration file.

## Architecture

### Core Components

1. **Tool Manifest** (`tool_manifest.json`) - Central configuration for all tools
2. **ManifestToolLoader** - Loads and validates tools from the manifest
3. **Hooks.py** - Registers tools with agents and group chat managers
4. **Tool Files** - Individual Python files containing tool functions

### Tool Types

The system supports two main categories of tools:

#### 1. AgentTools
Tools that are registered directly with individual agents and can be called by those agents during conversations.

**Supported `apply_to` values:**
- `"all"` - Register on every agent
- `"specific_agent_name"` - Register on a specific agent by name
- `["agent1", "agent2"]` - Register on a list of specific agents
- `"manager"` - Register on the manager agent only

#### 2. GroupchatTools
Tools that are triggered by group chat events and lifecycle hooks.

**Supported `trigger` values:**
- `"on_start"` - Runs once at the beginning of group chat
- `"on_end"` - Runs once at the end of group chat
- `"after_each_agent"` - Runs after every agent message
- `"before_each_agent"` - Runs before every agent message (future)
- `"after_all_agents"` - Runs after all agents have responded (future)

**Optional `trigger_agent`:**
- Can be combined with `after_each_agent` to trigger only for specific agents

## System Integration

### How Tools Are Loaded

1. **Manifest Loading:** `ManifestToolLoader` reads `tool_manifest.json`
2. **Function Import:** Each tool's module and function are dynamically imported
3. **Tool Registration:** 
   - AgentTools are registered with specific agents based on `apply_to`
   - GroupchatTools are registered as hooks based on `trigger`
4. **Execution:** Tools are called during conversation flow

### Registration Flow

```python
# In workflows/Generator/Hooks.py
def discover_all_tools():
    loader = ManifestToolLoader("tool_manifest.json")
    return {
        "AgentTools": loader.get_agent_tools(),
        "GroupchatTools": loader.get_groupchat_tools()
    }

# Tools are automatically registered during workflow initialization
tools = discover_all_tools()
register_agent_tools(agents, tools["AgentTools"])
register_groupchat_hooks(group_chat_manager, tools["GroupchatTools"])
```

## Component Configuration

### 📝 Manual Maintenance Required

**Edit these files directly:**

1. **`workflows/Generator/tool_manifest.json`** - Tool registration configuration
   - Purpose: Defines AgentTools and GroupchatTools registration patterns
   - When to edit: Adding/removing/modifying tools

2. **`workflows/Generator/workflow.json`** - Complete workflow configuration  
   - Purpose: Defines workflow settings, agents, and UI components
   - When to edit: Adding/removing agents, components, or changing workflow behavior

### 🎯 Single Source of Truth: workflow.json

All component configuration is now consolidated into `workflow.json` using a clean, modular structure:

```json
{
  "ui_capable_agents": [
    {
      "name": "UserFeedbackAgent",
      "role": "user_feedback_manager",
      "capabilities": ["chat", "artifacts"],
      "components": [
        {
          "name": "FileDownloadCenter",
          "type": "artifact",
          "description": "Download generated files", 
          "actions": ["download", "download_all"],
          "backend_handler": "file_manager.handle_download"
        }
      ]
    }
  ]
}
```

### 🔄 Component System Benefits

- **Single source of truth**: All component data in workflow.json
- **Modular design**: Each agent owns its components
- **No redundancy**: Components defined where they're used
- **Type safety**: Explicit `type: "inline"` or `"artifact"`
- **Clean APIs**: Simple methods in workflow_config.py