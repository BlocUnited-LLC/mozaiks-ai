# Handoffs.py Development Instructions

## Purpose
Define the agent handoff logic that determines when and how agents transfer control to each other during workflow execution.

## Template Structure

```python
"""
Agent handoff logic for {WORKFLOW_NAME} workflow
Defines transitions between agents based on context state
"""

from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass
import logging

from .context_variables import {WORKFLOW_NAME}Context

logger = logging.getLogger(__name__)

@dataclass
class HandoffRule:
    """Defines a single handoff rule between agents"""
    from_agent: str
    to_agent: str
    condition_name: str
    condition_func: Callable[[{WORKFLOW_NAME}Context], bool]
    priority: int = 0
    description: str = ""

class {WORKFLOW_NAME}HandoffManager:
    """Manages agent handoffs for {WORKFLOW_NAME} workflow"""
    
    def __init__(self):
        self.rules: List[HandoffRule] = []
        self._register_handoff_rules()
    
    def _register_handoff_rules(self):
        """Register all handoff rules for this workflow"""
        
        {HANDOFF_RULES_REGISTRATION}
    
    def should_handoff(self, current_agent: str, context: {WORKFLOW_NAME}Context) -> Optional[str]:
        """
        Determine if current agent should hand off control
        
        Args:
            current_agent: Name of the currently active agent
            context: Current workflow context
            
        Returns:
            Name of target agent if handoff should occur, None otherwise
        """
        
        # Find applicable rules for current agent
        applicable_rules = [
            rule for rule in self.rules 
            if rule.from_agent == current_agent
        ]
        
        # Sort by priority (higher priority first)
        applicable_rules.sort(key=lambda x: x.priority, reverse=True)
        
        # Check each rule until one matches
        for rule in applicable_rules:
            try:
                if rule.condition_func(context):
                    logger.info(f"Handoff triggered: {rule.from_agent} → {rule.to_agent} ({rule.condition_name})")
                    return rule.to_agent
            except Exception as e:
                logger.error(f"Error evaluating handoff rule {rule.condition_name}: {e}")
        
        return None
    
    def get_possible_handoffs(self, current_agent: str) -> List[str]:
        """Get list of possible target agents for current agent"""
        return list(set(
            rule.to_agent for rule in self.rules 
            if rule.from_agent == current_agent
        ))
    
    def get_handoff_rules(self, from_agent: str) -> List[HandoffRule]:
        """Get all handoff rules for a specific agent"""
        return [rule for rule in self.rules if rule.from_agent == from_agent]

# Handoff condition functions
{CONDITION_FUNCTIONS}

# Global handoff manager instance
handoff_manager = {WORKFLOW_NAME}HandoffManager()

def get_next_agent(current_agent: str, context: {WORKFLOW_NAME}Context) -> Optional[str]:
    """Main function for determining next agent"""
    return handoff_manager.should_handoff(current_agent, context)
```

## Configuration Fields

### WORKFLOW_NAME
- **Format**: PascalCase matching your workflow name
- **Purpose**: Creates consistent naming across workflow files
- **Example**: "ContentGenerator" → "ContentGeneratorHandoffManager"

### HANDOFF_RULES_REGISTRATION
Define the actual handoff rules using the HandoffRule dataclass:

```python
# Simple linear handoff
self.rules.extend([
    HandoffRule(
        from_agent="ConversationAgent",
        to_agent="ContentGeneratorAgent", 
        condition_name="requirements_collected",
        condition_func=requirements_collected,
        priority=10,
        description="Hand off when all requirements are collected"
    ),
    HandoffRule(
        from_agent="ContentGeneratorAgent",
        to_agent="ConversationAgent",
        condition_name="content_generated", 
        condition_func=content_generated,
        priority=10,
        description="Return to conversation after content generation"
    )
])

# Complex branching handoffs
self.rules.extend([
    HandoffRule(
        from_agent="ConversationAgent",
        to_agent="APISetupAgent",
        condition_name="needs_api_setup",
        condition_func=needs_api_setup,
        priority=20,
        description="Hand off for API credential setup"
    ),
    HandoffRule(
        from_agent="ConversationAgent", 
        to_agent="ContentGeneratorAgent",
        condition_name="ready_for_generation",
        condition_func=ready_for_generation,
        priority=10,
        description="Hand off for content generation"
    ),
    HandoffRule(
        from_agent="APISetupAgent",
        to_agent="ConversationAgent",
        condition_name="api_setup_complete",
        condition_func=api_setup_complete,
        priority=10,
        description="Return after API setup"
    )
])
```

### CONDITION_FUNCTIONS
Define the boolean functions that determine when handoffs occur:

```python
def requirements_collected(context: {WORKFLOW_NAME}Context) -> bool:
    """Check if all requirements have been collected"""
    return (
        context.content_type is not None and
        len(context.requirements) > 0 and
        context.target_audience is not None
    )

def content_generated(context: {WORKFLOW_NAME}Context) -> bool:
    """Check if content has been generated"""
    return len(context.generated_content) > 0

def needs_api_setup(context: {WORKFLOW_NAME}Context) -> bool:
    """Check if API setup is needed"""
    return (
        context.workflow_stage == "collecting_requirements" and
        not context.api_credentials.get("openai") and
        context.content_type in ["blog", "article"]
    )

def api_setup_complete(context: {WORKFLOW_NAME}Context) -> bool:
    """Check if API setup is complete"""
    return bool(context.api_credentials.get("openai"))

def ready_for_generation(context: {WORKFLOW_NAME}Context) -> bool:
    """Check if ready for content generation"""
    return (
        requirements_collected(context) and
        bool(context.api_credentials.get("openai"))
    )

def error_occurred(context: {WORKFLOW_NAME}Context) -> bool:
    """Check if an error occurred that needs human intervention"""
    return context.error_count > 2

def workflow_complete(context: {WORKFLOW_NAME}Context) -> bool:
    """Check if workflow is complete"""
    return context.completion_status == "completed"
```

## Handoff Patterns

### 1. Linear Sequential Handoffs
Each agent hands off to the next in sequence:

```python
# A → B → C → D
HandoffRule("AgentA", "AgentB", "step_1_complete", step_1_complete, 10),
HandoffRule("AgentB", "AgentC", "step_2_complete", step_2_complete, 10),
HandoffRule("AgentC", "AgentD", "step_3_complete", step_3_complete, 10),
```

### 2. Hub-and-Spoke Pattern
Central coordinator hands off to specialists:

```python
# Coordinator → Specialist → Coordinator
HandoffRule("CoordinatorAgent", "SpecialistA", "needs_specialty_a", needs_specialty_a, 10),
HandoffRule("CoordinatorAgent", "SpecialistB", "needs_specialty_b", needs_specialty_b, 10),
HandoffRule("SpecialistA", "CoordinatorAgent", "specialty_a_complete", specialty_a_complete, 10),
HandoffRule("SpecialistB", "CoordinatorAgent", "specialty_b_complete", specialty_b_complete, 10),
```

### 3. Conditional Branching
Different paths based on conditions:

```python
# Branch based on user choice or data
HandoffRule("DecisionAgent", "PathA_Agent", "chose_path_a", chose_path_a, 20),
HandoffRule("DecisionAgent", "PathB_Agent", "chose_path_b", chose_path_b, 20),
HandoffRule("DecisionAgent", "DefaultAgent", "no_specific_choice", no_specific_choice, 10),
```

### 4. Error Handling Handoffs
Special handoffs for error conditions:

```python
# Error recovery
HandoffRule("AnyAgent", "ErrorHandlerAgent", "error_occurred", error_occurred, 100),
HandoffRule("ErrorHandlerAgent", "ConversationAgent", "error_resolved", error_resolved, 10),
```

### 5. Iterative/Loop Handoffs
Agents that can hand back to previous steps:

```python
# Iterative refinement
HandoffRule("GeneratorAgent", "ReviewAgent", "content_generated", content_generated, 10),
HandoffRule("ReviewAgent", "GeneratorAgent", "needs_revision", needs_revision, 20),
HandoffRule("ReviewAgent", "DeliveryAgent", "content_approved", content_approved, 10),
```

## Condition Function Guidelines

### Simple State Checks
```python
def field_is_set(context: WorkflowContext) -> bool:
    """Check if a required field is set"""
    return context.field_name is not None

def list_has_items(context: WorkflowContext) -> bool:
    """Check if a list has required items"""
    return len(context.item_list) > 0

def stage_reached(context: WorkflowContext) -> bool:
    """Check if workflow reached specific stage"""
    return context.workflow_stage == "target_stage"
```

### Complex Logic Checks
```python
def all_requirements_met(context: WorkflowContext) -> bool:
    """Check multiple requirements"""
    return (
        context.user_preferences is not None and
        len(context.requirements) >= 2 and
        context.api_credentials.get("service") and
        context.workflow_stage in ["ready", "processing"]
    )

def threshold_reached(context: WorkflowContext) -> bool:
    """Check if numeric threshold is met"""
    return (
        context.error_count < 3 and
        len(context.generated_items) >= context.minimum_items and
        context.quality_score > 0.8
    )
```

### Time-Based Conditions
```python
def timeout_reached(context: WorkflowContext) -> bool:
    """Check if operation has timed out"""
    from datetime import datetime, timedelta
    timeout_limit = context.created_at + timedelta(minutes=30)
    return datetime.now() > timeout_limit

def retry_delay_passed(context: WorkflowContext) -> bool:
    """Check if enough time passed for retry"""
    if not context.last_error_time:
        return True
    from datetime import datetime, timedelta
    retry_delay = timedelta(seconds=30)
    return datetime.now() > context.last_error_time + retry_delay
```

## Priority System

Use priority to control handoff precedence:

```python
# Higher priority = checked first
HandoffRule("Agent", "ErrorHandler", "error_occurred", error_occurred, 100),  # Emergency
HandoffRule("Agent", "SpecialCase", "special_condition", special_condition, 50),  # Special case
HandoffRule("Agent", "NormalNext", "normal_condition", normal_condition, 10),   # Normal flow
```

## Validation and Testing

### Context Validation
```python
def validate_handoff_context(context: WorkflowContext) -> List[str]:
    """Validate context before handoff"""
    errors = []
    
    if not context.session_id:
        errors.append("session_id required for handoff")
    
    if context.workflow_stage == "error" and not context.last_error:
        errors.append("error stage requires error message")
    
    return errors
```

### Handoff Testing
```python
def test_handoff_rules():
    """Test handoff logic with sample contexts"""
    
    # Test normal flow
    context = WorkflowContext(requirements=["test"], content_type="blog")
    next_agent = get_next_agent("ConversationAgent", context)
    assert next_agent == "ContentGeneratorAgent"
    
    # Test error condition
    context.error_count = 5
    next_agent = get_next_agent("ContentGeneratorAgent", context)
    assert next_agent == "ErrorHandlerAgent"
```

## Common Handoff Scenarios

### 1. Data Collection → Processing
```python
def data_collection_complete(context: WorkflowContext) -> bool:
    return (
        len(context.user_inputs) >= context.minimum_inputs and
        all(field for field in context.required_fields if getattr(context, field)) and
        context.validation_passed
    )
```

### 2. API Setup → Execution
```python
def api_ready_for_execution(context: WorkflowContext) -> bool:
    return (
        all(key in context.api_credentials for key in context.required_apis) and
        context.api_test_results.get("status") == "success" and
        context.rate_limits_checked
    )
```

### 3. Generation → Review
```python
def content_ready_for_review(context: WorkflowContext) -> bool:
    return (
        len(context.generated_content) > 0 and
        all(item.get("status") == "complete" for item in context.generated_content) and
        context.quality_check_passed
    )
```

### 4. Review → Delivery or Revision
```python
def content_approved(context: WorkflowContext) -> bool:
    return context.review_status == "approved"

def content_needs_revision(context: WorkflowContext) -> bool:
    return context.review_status == "needs_revision"
```

## Best Practices

1. **Clear Conditions**: Make handoff conditions explicit and testable
2. **Priority Management**: Use priorities to handle overlapping conditions
3. **Error Handling**: Always include error recovery handoffs
4. **Logging**: Log all handoff decisions for debugging
5. **Validation**: Validate context state before handoffs
6. **Documentation**: Document each handoff rule's purpose
7. **Testing**: Test handoff logic with various context states
8. **Fallbacks**: Include fallback handoffs for unexpected states
9. **Performance**: Keep condition functions lightweight and fast
10. **Maintainability**: Group related handoff rules logically

## LLM Generation Prompt

```
Create handoff logic for a {workflow_name} workflow.

Agents: {AGENT_LIST}
Workflow Flow: {FLOW_DESCRIPTION}
Decision Points: {DECISION_CRITERIA}
Error Handling: {ERROR_SCENARIOS}

Generate complete handoff rules with condition functions and priority management.
```
