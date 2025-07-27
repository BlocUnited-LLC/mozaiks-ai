# Agent.py Development Instructions

## Purpose
Define AG2 (AutoGen) conversational agents with specific roles, capabilities, and tool access for your workflow.

## Template Structure

```python
"""
Agents for {WORKFLOW_NAME} workflow
"""

from autogen import ConversableAgent
from core.workflow.tool_registry import get_workflow_tools

class {AGENT_NAME}(ConversableAgent):
    """
    {AGENT_DESCRIPTION}
    
    Capabilities: {AGENT_CAPABILITIES}
    Role: {AGENT_ROLE}
    """
    
    def __init__(self, **kwargs):
        super().__init__(
            name="{AGENT_NAME}",
            llm_config={
                "model": "{MODEL_NAME}",  # e.g., "gpt-4", "claude-3"
                "api_type": "openai"
            },
            system_message="""{SYSTEM_MESSAGE}""",
            **kwargs
        )
        
        # Register tools for this agent
        self.tools = get_workflow_tools(
            workflow_name="{WORKFLOW_NAME}",
            agent_name="{AGENT_NAME}",
            capabilities={CAPABILITIES_LIST}
        )

# Export agents for workflow registry
AGENTS = {
    "{AGENT_NAME}": {AGENT_NAME},
}
```

## Configuration Fields

### AGENT_NAME
- **Format**: PascalCase (e.g., "ConversationAgent", "ContentGeneratorAgent")
- **Purpose**: Unique identifier for the agent
- **Rules**: No spaces, descriptive, ends with "Agent"

### AGENT_DESCRIPTION  
- **Format**: Clear, single sentence
- **Purpose**: Human-readable description of agent's role
- **Example**: "Handles user conversations and collects requirements"

### AGENT_CAPABILITIES
- **Options**: 
  - `["chat"]` - Basic conversation only
  - `["chat", "inline_components"]` - Can request inline UI components
  - `["artifacts"]` - Can create artifact components
  - `["chat", "inline_components", "artifacts"]` - Full UI capabilities
- **Purpose**: Determines which UI tools agent can access

### MODEL_NAME
- **Options**: "gpt-4", "gpt-3.5-turbo", "claude-3", "gemini-pro"
- **Purpose**: Which LLM model powers this agent
- **Default**: "gpt-4"

### SYSTEM_MESSAGE
- **Format**: Multi-line string with clear instructions
- **Purpose**: Defines agent behavior and personality
- **Guidelines**:
  - Be specific about the agent's role
  - Include UI interaction instructions if applicable
  - Mention handoff conditions to other agents
  - Use professional, clear language

## Example System Messages

### Conversational Agent
```
You are a helpful conversation agent that guides users through the {WORKFLOW_PURPOSE}.

Your responsibilities:
1. Greet users and understand their requirements
2. Collect necessary information using inline components when needed
3. Validate user inputs and preferences
4. Hand off to specialized agents when ready

UI Guidelines:
- Use inline components for forms, inputs, and user choices
- Always explain what information you're collecting and why
- Provide clear feedback on user actions

Handoff Rules:
- Hand off to {TARGET_AGENT} when you have collected: {REQUIRED_INFO}
- Always summarize what you've collected before handoff
```

### Specialist Agent
```
You are a {SPECIALTY} specialist agent focused on {SPECIFIC_TASK}.

Your responsibilities:
1. Receive requirements from conversational agents
2. Process and execute specialized tasks
3. Create artifacts and deliverables for users
4. Provide status updates during long operations

UI Guidelines:
- Use artifact components to display results, files, and outputs
- Show progress indicators for long-running tasks
- Provide download links and export options

Quality Standards:
- Always validate inputs before processing
- Provide clear error messages if something fails
- Include metadata and documentation with outputs
```

## Agent Interaction Patterns

### 1. Sequential Workflow
```python
# Agent A → Agent B → Agent C
system_message = """
Hand off to {NEXT_AGENT} when you have completed {COMPLETION_CRITERIA}.
Pass along: {DATA_TO_TRANSFER}
"""
```

### 2. Hub-and-Spoke
```python
# Central agent coordinates multiple specialists
system_message = """
You coordinate between specialist agents.
Hand off to:
- {AGENT_1} for {TASK_1}  
- {AGENT_2} for {TASK_2}
- {AGENT_3} for {TASK_3}
"""
```

### 3. Collaborative
```python
# Multiple agents work together
system_message = """
You collaborate with {OTHER_AGENTS} on {SHARED_TASK}.
Your focus: {YOUR_SPECIALTY}
"""
```

## Tool Access Patterns

### Chat-Only Agent
```python
capabilities = ["chat"]
# Can only send text messages, no UI components
```

### Form Collection Agent  
```python
capabilities = ["chat", "inline_components"]
# Can request API keys, forms, simple inputs
```

### Content Creation Agent
```python
capabilities = ["artifacts"]  
# Can create files, documents, complex outputs
```

### Full-Featured Agent
```python
capabilities = ["chat", "inline_components", "artifacts"]
# Can do everything - use sparingly
```

## Validation Checklist

- [ ] Agent name is unique and descriptive
- [ ] System message clearly defines role and responsibilities  
- [ ] Capabilities match the agent's intended UI usage
- [ ] Handoff conditions are clearly specified
- [ ] Model selection is appropriate for the task complexity
- [ ] Agent follows single responsibility principle

## Common Patterns

### API Key Collection Agent
```python
system_message = """
You collect and validate API keys from users.

Process:
1. Explain which API keys are needed and why
2. Use APIKeyInput component for secure collection
3. Validate keys are properly formatted
4. Confirm successful storage
5. Hand off to content generation agent

Always reassure users about security and encryption.
"""
```

### File Generation Agent
```python
system_message = """
You generate files and documents based on user requirements.

Process:
1. Receive requirements from conversation agent
2. Generate high-quality content
3. Create downloadable files using FileDownloadCenter
4. Provide previews and editing options
5. Handle regeneration requests

Always include metadata and clear file descriptions.
"""
```

## Best Practices

1. **Single Responsibility**: Each agent should have one clear purpose
2. **Clear Handoffs**: Specify exactly when and why to hand off
3. **User Communication**: Agents should explain their actions clearly
4. **Error Handling**: Include instructions for handling failures
5. **Context Preservation**: Agents should maintain conversation context
6. **Tool Usage**: Only grant capabilities the agent actually needs

## LLM Generation Prompt

```
Create an agent for a {workflow_name} workflow.

Agent Role: {ROLE_DESCRIPTION}
Capabilities Needed: {UI_CAPABILITIES}
Interaction Pattern: {WORKFLOW_PATTERN}
Target Users: {USER_TYPE}

Generate the complete agent class with appropriate system message and tool configuration.
```
