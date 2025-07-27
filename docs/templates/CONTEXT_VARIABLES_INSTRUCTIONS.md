# ContextVariables.py Development Instructions

## Purpose
Define shared data structures that persist throughout the workflow conversation, enabling agents to share information and maintain state.

## Template Structure

```python
"""
Context variables for {WORKFLOW_NAME} workflow
Shared state and data structures for agent communication
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
import time

@dataclass
class {WORKFLOW_NAME}Context:
    """
    Context variables for {WORKFLOW_NAME} workflow
    
    Maintains shared state between agents during conversation
    """
    
    # Core workflow state
    workflow_stage: str = "initialized"
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    
    # User data
    {USER_DATA_FIELDS}
    
    # Workflow-specific data
    {WORKFLOW_SPECIFIC_FIELDS}
    
    # Generated outputs
    {OUTPUT_FIELDS}
    
    # System state
    error_count: int = 0
    last_error: Optional[str] = None
    completion_status: str = "in_progress"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for AG2 context"""
        return {
            "workflow_stage": self.workflow_stage,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "created_at": self.created_at.isoformat(),
            {DICT_FIELDS}
            "error_count": self.error_count,
            "last_error": self.last_error,
            "completion_status": self.completion_status,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "{WORKFLOW_NAME}Context":
        """Create context from dictionary"""
        created_at = datetime.fromisoformat(data.get("created_at", datetime.now().isoformat()))
        
        return cls(
            workflow_stage=data.get("workflow_stage", "initialized"),
            user_id=data.get("user_id"),
            session_id=data.get("session_id"),
            created_at=created_at,
            {FROM_DICT_FIELDS}
            error_count=data.get("error_count", 0),
            last_error=data.get("last_error"),
            completion_status=data.get("completion_status", "in_progress"),
        )
    
    def update_stage(self, new_stage: str):
        """Update workflow stage with validation"""
        valid_stages = {VALID_STAGES}
        if new_stage in valid_stages:
            self.workflow_stage = new_stage
        else:
            raise ValueError(f"Invalid stage: {new_stage}. Valid stages: {valid_stages}")
    
    def add_error(self, error_message: str):
        """Record an error"""
        self.error_count += 1
        self.last_error = error_message
    
    def mark_complete(self):
        """Mark workflow as completed"""
        self.completion_status = "completed"
        self.workflow_stage = "finished"
    
    def is_ready_for_handoff(self, target_agent: str) -> bool:
        """Check if context has required data for agent handoff"""
        {HANDOFF_VALIDATION_LOGIC}
        return True

# Context variable helpers
def create_context(user_id: str, session_id: str) -> {WORKFLOW_NAME}Context:
    """Create new context for workflow session"""
    return {WORKFLOW_NAME}Context(
        user_id=user_id,
        session_id=session_id
    )

def validate_context(context: {WORKFLOW_NAME}Context) -> List[str]:
    """Validate context and return list of missing required fields"""
    errors = []
    
    {VALIDATION_RULES}
    
    return errors

# ================================================================================
# CONTEXT ADJUSTMENT INTEGRATION (NEW)
# ================================================================================

## LLM Generation Prompt

```
Create context variables for a {workflow_name} workflow.

Workflow Purpose: {PURPOSE_DESCRIPTION}
Data Requirements: {DATA_FIELDS_NEEDED}
Workflow Stages: {STAGE_PROGRESSION}
Agent Handoffs: {HANDOFF_REQUIREMENTS}

Generate the complete context class with validation and helper methods.
```

## 🔄 Context Adjustment Integration Guide

### Overview
The context adjustment system allows UI components to automatically update AG2 ContextVariables without requiring separate backend handlers. When users interact with components, their actions are automatically processed and stored in the workflow's context.

### How It Works

1. **Component Action**: User interacts with component (submits form, downloads file, etc.)
2. **Core Routing**: Action routes through workflow-agnostic context adjustment bridge
3. **Context Update**: Your `context_update()` function processes the action
4. **AG2 Integration**: ContextVariables updated, agents can access data immediately

### Setup Requirements

#### 1. Enable in workflow.json
```json
{
  "ui_capable_agents": [
    {
      "name": "YourAgent",
      "components": [...]
    }
  ]
}
```

#### 2. Implement context_update() Function
```python
# workflows/YourWorkflow/ContextVariables.py
async def context_update(agent_name, component_name, action_data, context_variables):
    """Handle component actions and update context"""
    
    action_type = action_data.get('type')
    
    if component_name == 'AgentAPIKeyInput' and action_type == 'api_key_submit':
        # Store API key securely
        service = action_data.get('service')
        api_key = action_data.get('apiKey')
        
        secure_keys = context_variables.get('secure_api_keys', {}) or {}
        secure_keys[service] = api_key
        context_variables.set('secure_api_keys', secure_keys)
        context_variables.set('api_key_ready', True)
        
        return {"status": "success", "service": service}
    
    return {"status": "unhandled"}
```

#### 3. Component Uses Standard onAction
```javascript
// Component automatically integrates - no changes needed
const AgentAPIKeyInput = ({ onAction, service, agentId }) => {
  const handleSubmit = async (apiKey) => {
    await onAction({
      type: 'api_key_submit',
      agentId: agentId,
      data: { service, apiKey }
    });
  };
  
  return <form onSubmit={handleSubmit}>{/* UI */}</form>;
};
```

### Benefits

- ✅ **Automatic Integration**: No separate backend handlers needed
- ✅ **Workflow Agnostic**: Works with any workflow configuration
- ✅ **AG2 Native**: Uses standard ContextVariables for state management
- ✅ **Immediate Access**: Agents can use data right after component interaction
- ✅ **Fallback Support**: Generic updates if no custom logic provided

### Common Patterns

#### Secure Data Storage
```python
# Store sensitive data securely
secure_data = context_variables.get('secure_api_keys', {}) or {}
secure_data[service] = sensitive_value
context_variables.set('secure_api_keys', secure_data)
```

#### Public Metadata Storage
```python
# Store public metadata for UI/display
public_data = context_variables.get('api_keys', {}) or {}
public_data[service] = {
    'masked_key': f"{api_key[:6]}...{api_key[-4:]}",
    'status': 'active',
    'submitted_at': str(time.time())
}
context_variables.set('api_keys', public_data)
```

#### Boolean Flags for Agents
```python
# Set flags that agents can check
context_variables.set('api_key_ready', True)
context_variables.set('form_completed', True)
context_variables.set('files_downloaded', len(downloads) > 0)
```

### Testing Your Integration

Use the test system to verify your context adjustment is working:

```python
# Test your context_update function
python test_context_system.py
```

This will simulate component actions and verify that ContextVariables are updated correctly.

# ================================================================================
# END OF CONTEXT ADJUSTMENT INTEGRATION
# ================================================================================

async def context_update(agent_name: str, component_name: str, action_data: Dict[str, Any], context_variables) -> Dict[str, Any]:
    """
    Workflow-specific context update function for component actions
    
    This function is automatically called by the core context adjustment system
    when UI components perform actions that should update AG2 ContextVariables.
    
    Args:
        agent_name: Name of the AG2 agent that owns the component
        component_name: Name of the UI component that triggered the action
        action_data: Data from the component action (includes 'type' and component data)
        context_variables: AG2 ContextVariables object to update
        
    Returns:
        Dict with status and any response data for the component
    """
    
    # Extract action type and data
    action_type = action_data.get('type')
    component_data = action_data.get('data', {})
    
    # Handle component-specific actions
    if component_name == 'AgentAPIKeyInput':
        return handle_api_key_actions(action_type, component_data, context_variables)
    
    elif component_name == 'FileDownloadCenter':
        return handle_file_actions(action_type, component_data, context_variables)
    
    elif component_name in ['FormComponent', 'MultiStepForm']:
        return handle_form_actions(action_type, component_data, context_variables)
    
    # Add more component handlers as needed...
    
    # Generic fallback - let core system handle if no specific logic
    return {"status": "unhandled", "message": f"No specific handler for {component_name}.{action_type}"}

# Example component action handlers for different workflow types:

# API Key Management Handler
def handle_api_key_actions(action_type: str, component_data: Dict[str, Any], context_variables) -> Dict[str, Any]:
    """Handle API key component actions"""
    
    if action_type == 'api_key_submit':
        service = component_data.get('service')
        api_key = component_data.get('apiKey')
        
        if not service or not api_key:
            return {"status": "error", "message": "Missing service or API key"}
        
        # Store in secure context variables
        secure_keys = context_variables.get('secure_api_keys', {}) or {}
        secure_keys[service] = api_key
        context_variables.set('secure_api_keys', secure_keys)
        
        # Store public metadata
        api_keys = context_variables.get('api_keys', {}) or {}
        api_keys[service] = {
            'masked_key': f"{api_key[:6]}...{api_key[-4:]}",
            'status': 'active',
            'submitted_at': str(time.time())
        }
        context_variables.set('api_keys', api_keys)
        context_variables.set('last_api_key_service', service)
        context_variables.set('api_key_ready', True)
        
        return {"status": "success", "service": service, "message": f"{service} API key stored securely"}
    
    elif action_type == 'cancel':
        service = component_data.get('service')
        return {"status": "cancelled", "service": service}
    
    return {"status": "unhandled"}

# File Management Handler  
def handle_file_actions(action_type: str, component_data: Dict[str, Any], context_variables) -> Dict[str, Any]:
    """Handle file download/upload component actions"""
    
    if action_type == 'download':
        file_id = component_data.get('fileId')
        filename = component_data.get('filename')
        
        # Track download in context
        downloads = context_variables.get('downloaded_files', []) or []
        downloads.append({
            'file_id': file_id,
            'filename': filename,
            'download_time': str(time.time()),
            'status': 'completed'
        })
        context_variables.set('downloaded_files', downloads)
        context_variables.set('last_download', filename)
        
        return {"status": "success", "filename": filename, "message": f"Download tracked: {filename}"}
    
    elif action_type == 'upload':
        # Handle file upload logic
        pass
    
    return {"status": "unhandled"}

# Form Submission Handler
def handle_form_actions(action_type: str, component_data: Dict[str, Any], context_variables) -> Dict[str, Any]:
    """Handle form component actions"""
    
    if action_type == 'form_submit':
        form_data = component_data.get('formData', {})
        
        # Store form data in context
        forms = context_variables.get('submitted_forms', []) or []
        forms.append({
            'data': form_data,
            'submitted_at': str(time.time()),
            'is_valid': component_data.get('isValid', False)
        })
        context_variables.set('submitted_forms', forms)
        context_variables.set('last_form_data', form_data)
        
        return {"status": "success", "message": "Form data saved to context"}
    
    return {"status": "unhandled"}
