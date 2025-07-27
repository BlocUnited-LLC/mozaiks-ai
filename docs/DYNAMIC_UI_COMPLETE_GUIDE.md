# Dynamic UI System: Complete Implementation Guide

## Overview

Our Dynamic UI System enables seamless interaction between AG2 agents and React components through a workflow-agnostic event-driven architecture. This system allows agents to request user input, display complex interfaces, and collect responses without knowing anything about frontend implementation details.

## Core Philosophy

**Separation of Concerns:**
- **Agents focus on business logic** - They know *what* they need from users
- **Frontend handles presentation** - It knows *how* to collect and display information
- **Transport layer bridges communication** - Events flow bidirectionally with guaranteed delivery

**Event-Driven Architecture:**
- Agents emit UI events when they need user interaction
- Frontend renders appropriate components based on `tool_id` mapping
- User responses flow back through the transport layer to waiting agents
- No tight coupling between backend logic and frontend components

## System Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   AG2 Agent     │    │  Transport Layer │    │  React Frontend │
│                 │    │                  │    │                 │
│ ┌─────────────┐ │    │ ┌──────────────┐ │    │ ┌─────────────┐ │
│ │Tool Function│ │───→│ │Event Emission│ │───→│ │UI Component │ │
│ └─────────────┘ │    │ └──────────────┘ │    │ └─────────────┘ │
│                 │    │                  │    │                 │
│ ┌─────────────┐ │    │ ┌──────────────┐ │    │ ┌─────────────┐ │
│ │Wait Response│ │←───│ │Response Queue│ │←───│ │User Response│ │
│ └─────────────┘ │    │ └──────────────┘ │    │ └─────────────┘ │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

## Complete Flow Breakdown

### 1. Agent Decision Making

**System Message Integration:**
```python
# Agent system message includes UI tool guidance
system_message = """
You are an API integration assistant. When you need API credentials from the user:

1. Use request_api_key(service, description) to request credentials
2. The UI will handle secure input collection
3. Wait for the user response before proceeding
4. Store credentials using store_api_key() if needed

Available UI tools:
- request_api_key: Secure credential collection
- request_file_download: File delivery to user
- display_progress: Show long-running operation status
"""
```

**Best Practices for Agent Instructions:**
- Be specific about when to use UI tools
- Explain the expected user experience
- Provide fallback instructions if UI fails
- Include validation requirements

### 2. Tool Function Implementation

**Complete UI Tool Pattern:**
```python
# workflows/Generator/tools/request_api_key.py
import asyncio
import uuid
import logging
from typing import Dict, Any, Optional
from datetime import datetime

async def request_api_key(
    service: str,
    description: Optional[str] = None,
    required: bool = True,
    workflow_name: str = "generator"
) -> Dict[str, Any]:
    """
    Request an API key from the user via secure UI component.
    
    Args:
        service: The service name (e.g., 'openai', 'anthropic')
        description: Custom description for the user
        required: Whether the key is mandatory
        workflow_name: Current workflow context
        
    Returns:
        Dict containing api_key, service, and metadata
    """
    # Import transport layer
    from core.transport.simple_transport import SimpleTransport
    transport = SimpleTransport()
    
    # Generate unique event ID for response tracking
    event_id = f"api_key_input_{str(uuid.uuid4())[:8]}"
    
    # Log the UI tool request
    logging.info(f"🔑 Requesting API key for {service} (Event: {event_id})")
    
    # Construct UI tool event following spec
    ui_tool_event = {
        "type": "ui_tool_event",
        "toolId": "api_key_input",          # Maps to React component
        "eventId": event_id,                # Unique identifier
        "workflowname": workflow_name,      # Context for frontend
        "timestamp": datetime.utcnow().isoformat(),
        "payload": {
            "service": service,
            "label": f"{service.replace('_', ' ').title()} API Key",
            "description": description or f"Enter your {service} API key to continue",
            "required": required,
            "placeholder": "sk-...",
            "inputType": "password",
            "validationHint": "API keys typically start with 'sk-' or similar"
        }
    }
    
    try:
        # Emit event to frontend via transport
        await transport.send_tool_event(ui_tool_event)
        logging.info(f"✅ UI event sent for {service}")
        
        # Wait for user response with timeout
        response = await transport.wait_for_ui_tool_response(
            event_id, 
            timeout=300  # 5 minute timeout
        )
        
        logging.info(f"📥 Received response for {service}: {response.get('success', False)}")
        return response
        
    except asyncio.TimeoutError:
        logging.warning(f"⏰ UI tool timeout for {service}")
        return {
            "success": False,
            "error": "User input timeout",
            "service": service
        }
    except Exception as e:
        logging.error(f"❌ UI tool error for {service}: {e}")
        return {
            "success": False,
            "error": str(e),
            "service": service
        }
```

### 3. Transport Layer Implementation

**Event Emission:**
```python
# core/transport/simple_transport.py
class SimpleTransport:
    def __init__(self):
        self.pending_responses = {}  # event_id -> Future
        self.websocket_connections = set()
        
    async def send_tool_event(self, event_data: Dict[str, Any]):
        """Send UI tool event to all connected frontends"""
        message = {
            "type": "ui_tool_event",
            "data": event_data
        }
        
        # Send to all WebSocket connections
        if self.websocket_connections:
            await asyncio.gather(
                *[ws.send_json(message) for ws in self.websocket_connections],
                return_exceptions=True
            )
        else:
            logging.warning("No WebSocket connections available for UI event")
            
    async def wait_for_ui_tool_response(
        self, 
        event_id: str, 
        timeout: int = 300
    ) -> Dict[str, Any]:
        """Wait for user response to UI tool event"""
        future = asyncio.Future()
        self.pending_responses[event_id] = future
        
        try:
            response = await asyncio.wait_for(future, timeout=timeout)
            return response
        except asyncio.TimeoutError:
            raise
        finally:
            self.pending_responses.pop(event_id, None)
            
    async def submit_ui_tool_response(self, event_id: str, response_data: Dict[str, Any]):
        """Handle response from frontend"""
        if event_id in self.pending_responses:
            future = self.pending_responses[event_id]
            if not future.done():
                future.set_result(response_data)
                logging.info(f"✅ Resolved UI tool response: {event_id}")
```

### 4. Frontend Component Registry

**Central Registry System:**
```javascript
// ChatUI/src/uiToolRegistry.js
class UiToolRegistry {
    constructor() {
        this.registry = new Map();
        this.metadata = new Map();
    }
    
    register(toolId, component, options = {}) {
        this.registry.set(toolId, component);
        this.metadata.set(toolId, {
            workflow: options.workflow || 'default',
            category: options.category || 'input',
            description: options.description || '',
            version: options.version || '1.0.0',
            registeredAt: new Date().toISOString()
        });
        
        console.log(`📋 Registered UI tool: ${toolId}`, options);
    }
    
    get(toolId) {
        return this.registry.get(toolId);
    }
    
    list() {
        return Array.from(this.registry.keys());
    }
    
    getMetadata(toolId) {
        return this.metadata.get(toolId);
    }
}

export const uiToolRegistry = new UiToolRegistry();
export const registerUiTool = (toolId, component, options) => 
    uiToolRegistry.register(toolId, component, options);
export const getUiToolComponent = (toolId) => uiToolRegistry.get(toolId);
```

**Event Dispatcher:**
```javascript
// ChatUI/src/eventDispatcher.js
import React from 'react';
import { getUiToolComponent } from './uiToolRegistry';

export class EventDispatcher {
    constructor() {
        this.activeEvents = new Map();
        this.eventHistory = [];
    }
    
    handleUiToolEvent(event) {
        const { toolId, eventId, payload, workflowname } = event;
        
        // Get registered component
        const Component = getUiToolComponent(toolId);
        if (!Component) {
            console.error(`❌ No component registered for toolId: ${toolId}`);
            return null;
        }
        
        // Track active event
        this.activeEvents.set(eventId, {
            toolId,
            payload,
            workflowname,
            startTime: Date.now()
        });
        
        // Create response handler
        const handleResponse = (responseData) => {
            this.submitResponse(eventId, responseData);
            this.activeEvents.delete(eventId);
        };
        
        // Render component with payload and response handler
        return React.createElement(Component, {
            ...payload,
            eventId,
            workflowname,
            onResponse: handleResponse,
            onCancel: () => handleResponse({ success: false, cancelled: true })
        });
    }
    
    submitResponse(eventId, responseData) {
        // Send response back to backend
        fetch('/api/ui-tool/submit', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                eventId,
                response: responseData,
                timestamp: new Date().toISOString()
            })
        }).catch(error => {
            console.error('Failed to submit UI tool response:', error);
        });
        
        // Update history
        this.eventHistory.push({
            eventId,
            response: responseData,
            completedAt: new Date().toISOString()
        });
    }
}

export const eventDispatcher = new EventDispatcher();
```

### 5. React Component Implementation

**Best Practices for UI Components:**
```javascript
// ChatUI/src/workflows/generator/components/AgentAPIKeyInput.js
import React, { useState, useEffect } from 'react';

export default function AgentAPIKeyInput({
    service,
    label,
    description,
    required = true,
    placeholder = "Enter API key...",
    inputType = "password",
    validationHint,
    eventId,
    workflowname,
    onResponse,
    onCancel
}) {
    const [apiKey, setApiKey] = useState('');
    const [isValid, setIsValid] = useState(false);
    const [showKey, setShowKey] = useState(false);
    const [isSubmitting, setIsSubmitting] = useState(false);
    
    // Validation logic
    useEffect(() => {
        const validateKey = (key) => {
            if (!key || key.length < 10) return false;
            if (service === 'openai' && !key.startsWith('sk-')) return false;
            return true;
        };
        setIsValid(validateKey(apiKey));
    }, [apiKey, service]);
    
    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!isValid || isSubmitting) return;
        
        setIsSubmitting(true);
        
        try {
            // Submit response with comprehensive data
            const response = {
                success: true,
                api_key: apiKey,
                service: service,
                metadata: {
                    submittedAt: new Date().toISOString(),
                    validated: isValid,
                    keyLength: apiKey.length,
                    workflowname: workflowname
                }
            };
            
            onResponse(response);
            
        } catch (error) {
            console.error('Error submitting API key:', error);
            onResponse({
                success: false,
                error: error.message,
                service: service
            });
        } finally {
            setIsSubmitting(false);
        }
    };
    
    return (
        <div className="ui-tool-container api-key-input">
            <div className="ui-tool-header">
                <h3>{label}</h3>
                <p className="description">{description}</p>
            </div>
            
            <form onSubmit={handleSubmit} className="api-key-form">
                <div className="input-group">
                    <input
                        type={showKey ? "text" : inputType}
                        value={apiKey}
                        onChange={(e) => setApiKey(e.target.value)}
                        placeholder={placeholder}
                        required={required}
                        className={`api-key-input ${isValid ? 'valid' : 'invalid'}`}
                        autoFocus
                    />
                    <button 
                        type="button"
                        onClick={() => setShowKey(!showKey)}
                        className="visibility-toggle"
                        aria-label={showKey ? "Hide key" : "Show key"}
                    >
                        {showKey ? "🙈" : "👁️"}
                    </button>
                </div>
                
                {validationHint && (
                    <p className="validation-hint">{validationHint}</p>
                )}
                
                <div className="action-buttons">
                    <button
                        type="button"
                        onClick={() => onCancel()}
                        className="cancel-button"
                        disabled={isSubmitting}
                    >
                        Cancel
                    </button>
                    <button
                        type="submit"
                        className="submit-button"
                        disabled={!isValid || isSubmitting}
                    >
                        {isSubmitting ? 'Submitting...' : 'Submit API Key'}
                    </button>
                </div>
            </form>
            
            {/* Debug info in development */}
            {process.env.NODE_ENV === 'development' && (
                <div className="debug-info">
                    <small>Event ID: {eventId}</small>
                    <small>Workflow: {workflowname}</small>
                    <small>Valid: {isValid ? 'Yes' : 'No'}</small>
                </div>
            )}
        </div>
    );
}
```

## Workflow Registration Pattern

**Workflow-Specific Registration:**
```javascript
// ChatUI/src/workflows/generator/index.js
import { registerUiTool } from '../../uiToolRegistry';
import AgentAPIKeyInput from './components/AgentAPIKeyInput';
import FileDownloadCenter from './components/FileDownloadCenter';

// Register all Generator workflow components
export function registerGeneratorComponents() {
    registerUiTool('api_key_input', AgentAPIKeyInput, {
        workflow: 'generator',
        category: 'input',
        description: 'Secure API key collection component',
        version: '1.2.0'
    });
    
    registerUiTool('file_download_center', FileDownloadCenter, {
        workflow: 'generator',
        category: 'artifact',
        description: 'File download and delivery component',
        version: '1.1.0'
    });
    
    console.log('✅ Generator workflow UI components registered');
}
```

## Best Practices for Agent System Messages

### 1. UI Tool Integration in Prompts

**Core Principles:**
- **Be explicit about when to use UI tools** - Don't assume the agent will figure it out
- **Set clear expectations for user experience** - Explain what the UI will do
- **Provide fallback instructions** - What to do if UI fails
- **Include timing guidance** - When in the workflow to request UI input

**Prompt Structure Template:**
```
ROLE: [Agent's primary function]

UI TOOL GUIDELINES:
1. When to use: [Specific scenarios that require UI tools]
2. User experience: [What the user will see/experience]
3. Failure handling: [What to do if UI tool fails]
4. Timing: [When in conversation flow to use tools]

AVAILABLE UI TOOLS:
- [tool_name]: [when to use] | [what user experiences] | [expected response]

VALIDATION REQUIREMENTS:
- [What to check in responses]
- [How to handle invalid input]

ERROR SCENARIOS:
- [Common failures and responses]
```

### 2. Effective Tool Instruction Patterns

**❌ Vague Instructions:**
```
"Use request_api_key when you need an API key"
```

**✅ Specific Instructions:**
```
"Use request_api_key(service, description) when:
- User mentions needing to integrate with external APIs
- You need credentials to complete a requested task  
- User asks about connecting to services like OpenAI, Anthropic, etc.
The UI will show a secure input field. Wait for the response before proceeding."
```

**❌ No Context Setting:**
```
"Call request_file_download to give files to users"
```

**✅ Context-Rich Instructions:**
```
"Use request_file_download(filename, content) when:
- You've generated code, configs, or documents the user should save
- User requests downloadable deliverables
- You've completed a workflow that produces files
The UI will render in the artifact panel with download options."
```

### 3. Prompt Engineering for UI Tool Success

**Expectation Setting:**
- Tell the agent what the user will see: "The UI will show a secure password field"
- Explain the interaction flow: "User clicks submit, you'll receive the API key"
- Set timing expectations: "This may take 1-2 minutes for user input"

**Validation Instructions:**
- Specify what constitutes valid input
- Define required vs optional fields
- Explain how to handle partial or invalid responses

**Error Recovery Patterns:**
- Primary approach: Use UI tool
- Secondary approach: Ask in chat if UI fails
- Tertiary approach: Provide instructions for manual setup

**Flow Control Guidelines:**
- When to wait for UI responses vs continue
- How to handle concurrent UI requests
- Sequencing multiple UI interactions

### 4. Context and State Management

**Pre-UI Tool Context:**
- Explain to user what's about to happen
- Set expectations for the upcoming UI
- Provide context about why the input is needed

**Post-UI Tool Handling:**
- Acknowledge receipt of user input
- Confirm what was received (without exposing sensitive data)
- Explain next steps in the workflow

**State Persistence:**
- How to remember UI tool responses across conversation
- When to re-request information vs use cached data
- Handling session continuity

### 5. Common Prompt Anti-Patterns to Avoid

**❌ Tool Overuse:**
```
"Use UI tools for any user input" 
```
**✅ Selective Usage:**
```
"Use UI tools only for sensitive data, file downloads, or complex forms"
```

**❌ No Failure Planning:**
```
"Call request_api_key to get the API key"
```
**✅ Robust Planning:**
```
"Try request_api_key first. If it fails or times out, ask user to paste the key in chat"
```

**❌ Unclear Timing:**
```
"You can request API keys when needed"
```
**✅ Clear Timing:**
```
"Request API keys immediately when user mentions wanting to integrate with a service"
```

**❌ Missing Context:**
```
"Use request_file_download for files"
```
**✅ Rich Context:**
```
"Use request_file_download when you've created files the user should save locally"
```

### 6. Workflow-Specific Prompt Strategies

**For Multi-Step Workflows:**
- Explain the overall process upfront
- Number the steps that will involve UI
- Set expectations for total interaction time

**For Conditional UI:**
- Define the conditions that trigger UI tools
- Explain alternative paths when UI isn't needed
- Handle branching logic clearly

**For Error-Prone Workflows:**
- Acknowledge potential failure points
- Provide clear retry instructions
- Offer manual alternatives

### 7. User Experience Considerations in Prompts

**Accessibility:**
- Mention keyboard navigation options
- Explain screen reader compatibility
- Provide text alternatives for visual elements

**Performance:**
- Warn about potential loading times
- Explain what happens during processing
- Provide progress indicators when possible

**Security:**
- Reassure users about data handling
- Explain what is/isn't stored
- Clarify data transmission security

## Conclusion

This dynamic UI system provides a powerful, scalable foundation for agent-frontend interaction. Key benefits include:

1. **Workflow Agnostic** - Works with any agent workflow
2. **Type Safe** - Clear event contracts and response patterns
3. **Error Resilient** - Graceful fallbacks and comprehensive error handling
4. **Performance Optimized** - Debouncing, memory management, and cleanup
5. **Developer Friendly** - Rich debugging tools and testing interfaces
6. **User Focused** - Consistent, accessible UI components

The system enables complex, multi-step user interactions while maintaining clean separation between agent logic and UI presentation, making it easy to add new workflows and components as your application grows.
