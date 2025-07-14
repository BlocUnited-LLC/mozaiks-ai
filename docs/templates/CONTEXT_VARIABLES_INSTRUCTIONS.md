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
```

## Configuration Fields

### WORKFLOW_NAME
- **Format**: PascalCase (e.g., "ContentGenerator", "DataAnalysis")
- **Purpose**: Creates the context class name
- **Example**: "ContentGenerator" → "ContentGeneratorContext"

### USER_DATA_FIELDS
Define fields that store user-provided information:

```python
# User preferences and settings
user_preferences: Dict[str, Any] = field(default_factory=dict)
user_email: Optional[str] = None
user_role: Optional[str] = None

# User inputs and requirements
requirements: List[str] = field(default_factory=list)
selected_options: Dict[str, Any] = field(default_factory=dict)
uploaded_files: List[Dict[str, Any]] = field(default_factory=list)
```

### WORKFLOW_SPECIFIC_FIELDS
Define fields specific to your workflow's domain:

```python
# Content generation workflow
content_type: Optional[str] = None
target_audience: Optional[str] = None
content_length: Optional[int] = None
style_preferences: Dict[str, Any] = field(default_factory=dict)

# Data analysis workflow  
dataset_info: Dict[str, Any] = field(default_factory=dict)
analysis_type: Optional[str] = None
selected_columns: List[str] = field(default_factory=list)
visualization_preferences: Dict[str, Any] = field(default_factory=dict)

# API integration workflow
api_credentials: Dict[str, str] = field(default_factory=dict)
endpoint_config: Dict[str, Any] = field(default_factory=dict)
request_parameters: Dict[str, Any] = field(default_factory=dict)
```

### OUTPUT_FIELDS
Define fields that store generated results:

```python
# Generated content
generated_content: List[Dict[str, Any]] = field(default_factory=list)
generated_files: List[Dict[str, Any]] = field(default_factory=list)
download_urls: Dict[str, str] = field(default_factory=dict)

# Analysis results
analysis_results: Dict[str, Any] = field(default_factory=dict)
visualizations: List[Dict[str, Any]] = field(default_factory=list)
summary_report: Optional[str] = None

# API responses
api_responses: List[Dict[str, Any]] = field(default_factory=list)
processed_data: Dict[str, Any] = field(default_factory=dict)
export_data: Dict[str, Any] = field(default_factory=dict)
```

### VALID_STAGES
Define the workflow progression stages:

```python
# Simple linear workflow
{"initialized", "collecting_requirements", "processing", "generating", "completed"}

# Complex branching workflow
{"initialized", "user_onboarding", "requirements_gathering", "api_setup", 
 "data_processing", "content_generation", "review", "finalization", "completed"}

# Iterative workflow
{"initialized", "planning", "execution", "review", "revision", "approval", "completed"}
```

### HANDOFF_VALIDATION_LOGIC
Define when agents can hand off to each other:

```python
if target_agent == "ContentGeneratorAgent":
    return (self.content_type is not None and 
            len(self.requirements) > 0 and
            bool(self.api_credentials.get("openai")))

elif target_agent == "ReviewAgent":
    return (len(self.generated_content) > 0 and
            self.workflow_stage == "generating")

elif target_agent == "ConversationAgent":
    return True  # Can always hand back to conversation agent
```

## Field Type Guidelines

### Simple Values
```python
# Use for single values
name: Optional[str] = None
count: int = 0
is_enabled: bool = False
timestamp: datetime = field(default_factory=datetime.now)
```

### Collections
```python
# Use for lists of items
items: List[str] = field(default_factory=list)
metadata: Dict[str, Any] = field(default_factory=dict)
file_mappings: Dict[str, str] = field(default_factory=dict)
```

### Complex Objects
```python
# Use for structured data
user_profile: Dict[str, Any] = field(default_factory=dict)
generation_config: Dict[str, Any] = field(default_factory=lambda: {
    "model": "gpt-4",
    "temperature": 0.7,
    "max_tokens": 1000
})
```

## Validation Rules Examples

### Required Fields Validation
```python
if not context.user_id:
    errors.append("user_id is required")

if not context.requirements:
    errors.append("At least one requirement must be specified")

if context.content_type not in ["blog", "article", "social", "email"]:
    errors.append("Invalid content_type")
```

### Data Consistency Validation
```python
if context.api_credentials and not context.api_credentials.get("openai"):
    errors.append("OpenAI API key required for content generation")

if context.generated_files and not context.download_urls:
    errors.append("Download URLs missing for generated files")
```

### Workflow Stage Validation
```python
if context.workflow_stage == "generating" and not context.requirements:
    errors.append("Cannot generate content without requirements")

if context.completion_status == "completed" and context.workflow_stage != "finished":
    errors.append("Workflow stage must be 'finished' when completed")
```

## Usage Patterns

### Simple Data Collection Workflow
```python
@dataclass
class SimpleFormContext:
    # User inputs
    name: Optional[str] = None
    email: Optional[str] = None
    message: Optional[str] = None
    
    # System state
    form_completed: bool = False
    validation_errors: List[str] = field(default_factory=list)
```

### Multi-Step Content Generation
```python
@dataclass
class ContentGenerationContext:
    # Step 1: Requirements
    content_type: Optional[str] = None
    target_audience: Optional[str] = None
    tone: Optional[str] = None
    
    # Step 2: Configuration
    api_keys: Dict[str, str] = field(default_factory=dict)
    generation_params: Dict[str, Any] = field(default_factory=dict)
    
    # Step 3: Generation
    generated_content: List[Dict[str, Any]] = field(default_factory=list)
    revision_history: List[Dict[str, Any]] = field(default_factory=list)
    
    # Step 4: Delivery
    final_files: List[Dict[str, Any]] = field(default_factory=list)
    download_links: Dict[str, str] = field(default_factory=dict)
```

### API Integration Workflow
```python
@dataclass  
class APIIntegrationContext:
    # Connection setup
    api_credentials: Dict[str, str] = field(default_factory=dict)
    endpoint_config: Dict[str, Any] = field(default_factory=dict)
    
    # Request configuration
    request_templates: List[Dict[str, Any]] = field(default_factory=list)
    parameter_mappings: Dict[str, str] = field(default_factory=dict)
    
    # Execution results
    test_results: List[Dict[str, Any]] = field(default_factory=list)
    api_responses: List[Dict[str, Any]] = field(default_factory=list)
    error_log: List[str] = field(default_factory=list)
```

## Best Practices

1. **Start Simple**: Begin with minimal fields, add complexity as needed
2. **Use Type Hints**: Always specify types for better IDE support and validation
3. **Default Factories**: Use `field(default_factory=dict)` for mutable defaults
4. **Clear Naming**: Use descriptive field names that explain the data's purpose
5. **Validation**: Include validation methods to ensure data consistency
6. **Documentation**: Add docstrings explaining each field's purpose
7. **Immutable IDs**: Don't change user_id or session_id after creation
8. **Stage Management**: Use clear, descriptive stage names
9. **Error Tracking**: Include error handling and logging capabilities
10. **Serialization**: Ensure all fields can be serialized to/from JSON

## LLM Generation Prompt

```
Create context variables for a {WORKFLOW_TYPE} workflow.

Workflow Purpose: {PURPOSE_DESCRIPTION}
Data Requirements: {DATA_FIELDS_NEEDED}
Workflow Stages: {STAGE_PROGRESSION}
Agent Handoffs: {HANDOFF_REQUIREMENTS}

Generate the complete context class with validation and helper methods.
```
