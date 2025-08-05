# Modular UI Component Integration with AG2 Agents

## Overview

The modular UI event processor (`core/transport/ui_event_processor.py`) provides rich payload information back to AG2 agents, enabling intelligent decision making for workflow control, handoffs, and termination.

## Supported UI Component Types

### 1. File Download (`agent_file_download`)
**Use Case**: When agents generate files and need user feedback
**Component**: `FileDownloadCenter`

#### Agent Response Examples:
```python
# Single file download success
"DOWNLOAD_SUCCESS: example.py | NEXT: continue_workflow | USER_ENGAGEMENT: positive"

# Bulk download success (workflow completion signal)  
"BULK_DOWNLOAD_SUCCESS: 5 files | COMPLETION_SIGNAL: True | SATISFACTION: high | WORKFLOW_COMPLETE: True"

# User cancellation (need alternative approach)
"DOWNLOAD_CANCELLED: user_cancelled | SUGGESTED_RECOVERY: offer_different_format_or_content | USER_ENGAGEMENT: disengaged"
```

#### Agent Decision Logic:
```python
if "BULK_DOWNLOAD_SUCCESS" in response and "WORKFLOW_COMPLETE: True" in response:
    # User got all files - terminate workflow successfully
    return terminate_chat("Task completed successfully. All files delivered.")
    
elif "DOWNLOAD_CANCELLED" in response:
    # User rejected files - offer alternatives
    return handoff_to_agent("content_adaptation_agent", 
                          "User rejected files. Need alternative format or content.")
                          
elif "DOWNLOAD_SUCCESS" in response and "continue_workflow" in response:
    # Single file downloaded - continue with more content
    continue_generating_content()
```

### 2. API Key Input (`agent_api_key_input`) 
**Use Case**: When agents need API keys for services
**Component**: `AgentAPIKeyInput`

#### Agent Response Examples:
```python
# Success
"Valid API key received (length: 51)"

# Timeout/Failure  
"API key request timed out"
```

### 3. Confirmation (`agent_confirmation`)
**Use Case**: When agents need yes/no decisions
**Component**: `AgentConfirmation` (to be implemented)

#### Agent Response Examples:
```python
"User confirmed: Yes"
"User cancelled: No" 
```

### 4. Selection (`agent_selection`)
**Use Case**: When agents need user to choose from options
**Component**: `AgentSelection` (to be implemented)

#### Agent Response Examples:
```python
"User selected: Option A (value: option_a)"
"Selection request timed out"
```

### 5. File Upload (`agent_file_upload`)  
**Use Case**: When agents need files from user
**Component**: `AgentFileUpload` (to be implemented)

#### Agent Response Examples:
```python
"File uploaded successfully: document.pdf (2.3MB)"
"File upload request timed out"
```

## Agent Context Information

Each UI component response includes an `agentContext` object with decision-making data:

```python
agentContext = {
    "nextAction": "continue_workflow",     # What agent should do next
    "userEngagement": "positive",          # User engagement level
    "workflowStage": "file_delivery",      # Current workflow stage
    "shouldContinue": True,               # Whether to continue workflow
    "completionSignal": False,            # Whether user's needs are met
    "satisfactionLevel": "high",          # User satisfaction indicator
    "errorRecovery": "retry",             # How to handle errors
    "suggestedRecovery": "offer_alternatives" # Recovery suggestions
}
```

## Workflow Control Patterns

### 1. Termination Based on User Satisfaction
```python
if "BULK_DOWNLOAD_SUCCESS" in response and "COMPLETION_SIGNAL: True" in response:
    terminate_chat("Mission accomplished! All files delivered successfully.")
```

### 2. Handoff Based on User Rejection  
```python
if "CANCELLED" in response and "SUGGESTED_RECOVERY: offer_different_format" in response:
    handoff_to_agent("format_converter_agent", 
                   "User rejected current format. Need file format conversion.")
```

### 3. Adaptive Content Based on Engagement
```python  
if "USER_ENGAGEMENT: disengaged" in response:
    handoff_to_agent("engagement_specialist", 
                   "User showing low engagement. Need re-engagement strategy.")
```

### 4. Error Recovery Routing
```python
if "DOWNLOAD_ERROR" in response and "RECOVERY: offer_individual_downloads" in response:
    # Switch from bulk to individual file strategy
    switch_to_individual_file_mode()
```

## Adding New UI Component Types

### 1. Add Component Type Detection
In `ui_event_processor.py`, update `_detect_ui_component_type()`:

```python
# New component detection
if any(keyword in prompt_lower for keyword in ['your_keywords']):
    return "your_component_type"
```

### 2. Add Component Handler
```python
async def _handle_your_component_request(self, event, prompt, is_password):
    # Your component logic here
    pass
```

### 3. Register Frontend Component
In `ChatUI/src/workflows/Generator/index.js`:

```javascript
registerUiTool(
  'your_tool_id',
  YourComponent,
  { /* metadata */ }
);
```

### 4. Add Response Processing
Update the handler to process rich responses and provide structured agent feedback.

## Best Practices

1. **Always provide `agentContext`** - Helps agents make informed decisions
2. **Use structured response formats** - Makes parsing easier for agents  
3. **Include completion signals** - Helps agents know when to terminate
4. **Provide recovery suggestions** - Helps agents handle failures gracefully
5. **Indicate user engagement levels** - Helps agents adapt their approach

## Example Agent Integration

```python
async def handle_file_generation_complete(files):
    """Example of how an agent handles file generation completion"""
    
    # Use the modular UI system to offer downloads
    response = await request_file_download(files, download_type="bulk")
    
    # Parse the rich response for decision making
    if "WORKFLOW_COMPLETE: True" in response:
        # User got everything they needed - terminate successfully
        return terminate_chat("Great! I've delivered all your files. Is there anything else you need?")
        
    elif "DOWNLOAD_CANCELLED" in response:
        # User rejected files - try different approach
        if "offer_different_format" in response:
            return handoff_to_agent("format_converter", 
                                  "User wants different file format")
        else:
            return "I see you don't need the files right now. What would you prefer instead?"
            
    elif "DOWNLOAD_SUCCESS" in response and "continue_workflow" in response:
        # Single file downloaded - offer more
        return "File downloaded! Would you like me to generate additional variations?"
        
    else:
        # Default continuation
        return "How else can I help you with your files?"
```

This modular system enables sophisticated agent decision-making based on rich UI interaction data, supporting complex workflow patterns including intelligent termination, handoffs, and adaptive responses.
