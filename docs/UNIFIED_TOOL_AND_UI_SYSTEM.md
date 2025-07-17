# Unified Tool and UI System

## Overview

MozaiksAI has a unified system where both backend tools and frontend UI components are configured in `workflow.json`. This document explains how tools and UI components work together to create a seamless agent-driven experience.

---

## System Architecture

```mermaid
flowchart TD
    subgraph WF["📋 workflow.json"]
        AT[agent_tools]
        LH[lifecycle_hooks]
        UCA[ui_capable_agents]
        COMP[components]
    end
    
    subgraph Backend["⚙️ Backend"]
        AG[Agents]
        GCM[GroupChatManager]
        TF[Tool Functions]
        BH[Backend Handlers]
    end
    
    subgraph Frontend["🎨 Frontend"]
        DC[Dynamic Components]
        AP[Artifact Panel]
        IC[Inline Components]
    end
    
    AT --> AG
    LH --> GCM
    AG --> TF
    GCM --> TF
    
    UCA --> DC
    COMP --> AP
    COMP --> IC
    BH --> DC
```

---

## Two Types of Agent Capabilities

### 1. Backend Tools
**Purpose**: Pure backend functionality for agents
**Location**: `workflow.json → tools`
**AG2 Compatibility**: Full support for AG2 type annotations and LLM guidance
**Types**:
- **Agent Tools**: Functions registered with specific agents for conversation use (with AG2 LLM guidance)
- **Lifecycle Hooks**: Functions triggered by groupchat events

**Example**:
```json
{
  "tools": {
    "agent_tools": [
      {
        "name": "echo_all",
        "module": "workflows.Generator.tools.echo_all",
        "function": "echo",
        "apply_to": "all",
        "description": "Simple echo tool for all agents"
      }
    ],
    "lifecycle_hooks": [
      {
        "name": "on_start_echo",
        "module": "workflows.Generator.tools.on_start_echo",
        "function": "echo_on_start",
        "trigger": "on_start"
      }
    ]
  }
}
```

### 2. Frontend UI Components
**Purpose**: Dynamic UI elements that agents can control
**Location**: `workflow.json → ui_capable_agents → components`
**Types**:
- **Artifact Components**: Appear in the artifact panel
- **Inline Components**: Appear inline in the chat

**Example**:
```json
{
  "ui_capable_agents": [
    {
      "name": "UserFeedbackAgent",
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

---

## Key Differences

| Aspect | Backend Tools | Frontend UI Components |
|--------|---------------|------------------------|
| **Purpose** | Agent functionality | User interaction |
| **Execution** | Backend Python functions | React components |
| **Triggering** | Agents call during conversation | Agents request UI rendering |
| **User Interaction** | Indirect (through agent) | Direct (user clicks/inputs) |
| **Configuration** | `tools` section | `ui_capable_agents` section |

---

## Unified Loading System

Both systems use the same loading pattern:

### 1. Configuration Loading
```python
# From core/workflow/workflow_config.py
agent_tools = workflow_config.get_enabled_agent_tools(workflow_type)
ui_components = workflow_config.get_ui_capable_agents(workflow_type)
```

### 2. Dynamic Import
```python
# Tools: Import Python functions
module = importlib.import_module(tool["module"])
tool["function_obj"] = getattr(module, tool["function"])

# Components: Load React components from workflow folders
component_path = f"workflows/{workflow_type}/Components/{component_name}"
```

### 3. Registration
```python
# Tools: Register with agents or manager
agent.register_tool(tool_name, tool_function)
manager.register_hook(trigger, hook_function)

# Components: Make available to frontend
transport.send_ui_tool_event(component_definition)
```

---

## Interaction Flow

### Backend Tools Flow
1. **Agent decides** to use a tool during conversation
2. **Tool function executes** in Python backend
3. **Result is returned** to agent for processing
4. **Agent continues** conversation with result

### Frontend UI Flow
1. **Agent requests** UI component rendering
2. **Frontend receives** component definition via transport
3. **React component renders** in UI (artifact panel or inline)
4. **User interacts** with component (clicks, inputs)
5. **Frontend sends** action to backend handler
6. **Backend handler processes** action and returns result
7. **Agent receives** result and continues conversation

---

## Best Practices

### Tool Development
- **Keep tools pure**: Tools should be stateless Python functions
- **Use AG2 annotations**: Use `Annotated[type, "description"]` for LLM guidance
- **Write clear docstrings**: LLM uses docstrings to decide when to use tools
- **Use descriptive names**: Tool names should clearly indicate purpose
- **Handle errors gracefully**: Tools should not crash agents
- **Log tool usage**: Use business logging for tool calls

### UI Component Development
- **Design for agent control**: Components should respond to agent data
- **Handle all actions**: Define clear action handlers for user interactions
- **Provide feedback**: Components should show loading/success/error states
- **Keep data flowing**: Use onAction callbacks to send data back to agents

### Configuration Management
- **Group related tools**: Keep workflow-specific tools together
- **Use clear descriptions**: Help developers understand tool/component purpose
- **Enable/disable flags**: Use enabled flags for easy testing
- **Version compatibility**: Document any breaking changes in workflow.json

---

## Current Implementation Status

### ✅ Fully Implemented
- Workflow.json-based tool configuration
- Dynamic tool loading and registration
- Frontend component discovery from workflow folders
- Agent tool registration with apply_to patterns
- Lifecycle hook registration with trigger patterns
- UI component rendering and action handling
---

## Conclusion

The unified tool and UI system provides a clean separation of concerns while maintaining a consistent configuration approach. Backend tools handle pure functionality with full AG2 compatibility and LLM guidance, while frontend UI components handle user interaction, but both are configured in the same workflow.json file and follow similar loading patterns.

This design enables agents to have both computational capabilities (tools with LLM guidance) and user interaction capabilities (UI components) without mixing concerns or creating complex interdependencies.
