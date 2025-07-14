# ==============================================================================
# FILE: Generator/StructuredOutputs.py
# DESCRIPTION: Structured output models for AG2 Generator agents
# ==============================================================================

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Literal
from core.core_config import make_llm_config, make_structured_config

# ContextVariablesAgent Output
class ContextVariablesDefinition(BaseModel):
    name: str = Field(description="Variable name (e.g., 'project_title', 'user_requirements')")
    extraction_code: str = Field(description="Python code to extract value (e.g., \"concept_data.get('ProjectTitle', '')\")")
    description: str = Field(description="Description of what this context variable represents")
    default_value: str = Field(default="''", description="Default value if extraction fails")

class ContextVariablesOutput(BaseModel):
    context_variables: List[ContextVariablesDefinition] = Field(description="All context variables for workflow")

# AgentsAgent Output
class AgentDefinition(BaseModel):
    name: str = Field(description="Agent variable name")
    display_name: str = Field(description="Agent display name")
    agent_type: Literal["ConversableAgent", "UserProxyAgent", "AssistantAgent"] = Field(description="AG2 agent class")
    system_message: str = Field(description="Complete system message for the agent")
    human_input_mode: Literal["ALWAYS", "NEVER", "TERMINATE"] = Field(default="NEVER")
    max_consecutive_auto_reply: int = Field(default=10)  # Increased to allow workflow to complete

class AgentsOutput(BaseModel):
    agent_list: List[AgentDefinition] = Field(description="All agent definitions for workflow")

# HandoffsAgent Output
class HandoffRule(BaseModel):
    source_agent: str = Field(description="Source agent name")
    target_agent: str = Field(description="Target agent name or 'user' for user handoff") 
    handoff_type: Literal["llm_condition", "after_work"] = Field(description="Type of handoff condition")
    condition: Optional[str] = Field(default=None, description="LLM condition prompt if handoff_type is llm_condition")
    description: str = Field(description="Human-readable description of the handoff rule")

class HandoffsOutput(BaseModel):
    handoff_rules: List[HandoffRule] = Field(description="All handoff rules between agents")

# HooksAgent Output
class HookFunction(BaseModel):
    name: str = Field(description="Hook function name")
    hook_type: Literal["process_message_before_send", "update_agent_state", "process_message_after_receive"] = Field(description="Type of hook")
    trigger_agents: List[str] = Field(default=[], description="List of agent names this hook applies to (empty = all agents)")
    description: str = Field(description="Description of what this hook does")
    function_code: str = Field(description="Complete Python function code for the hook")

class HookRegistration(BaseModel):
    agent_name: str = Field(description="Name of agent to register hooks on")
    hook_names: List[str] = Field(description="List of hook names to register on this agent")

class HooksOutput(BaseModel):
    hook_functions: List[HookFunction] = Field(description="All hook functions for the workflow")
    hook_registrations: List[HookRegistration] = Field(description="Hook registration mappings per agent")
    workflow_specific_features: List[str] = Field(default=[], description="List of workflow-specific features the hooks provide")

# OrchestratorAgent Output
class OrchestrationConfig(BaseModel):
    max_rounds: int = Field(default=8, description="Maximum conversation rounds")
    initial_agent: str = Field(description="Initial agent name")
    initial_message: str = Field(description="Default initial message")

class OrchestratorOutput(BaseModel):
    orchestration_config: OrchestrationConfig = Field(description="Orchestration settings")
    workflow_name: str = Field(description="Name of generated workflow")
    workflow_description: str = Field(description="Description of workflow purpose")

# APIKeyAgent Output
class APIService(BaseModel):
    service_name: str = Field(description="Name of the API service (e.g., 'OpenAI', 'Anthropic')")
    required: bool = Field(description="Whether this API key is required for the workflow")
    key_format: str = Field(description="Expected format of the API key (e.g., 'sk-...')")
    help_url: str = Field(description="URL where users can obtain the API key")
    instructions: str = Field(description="Step-by-step instructions for obtaining the key")
    validation_pattern: Optional[str] = Field(default=None, description="Regex pattern for validation")

class APIKeyComponentData(BaseModel):
    service: str = Field(description="Service name for component")
    placeholder: str = Field(description="Placeholder text")
    description: str = Field(description="Description for user")
    validation_pattern: Optional[str] = Field(default=None, description="Validation regex")
    help_url: str = Field(description="Help URL")

class APIKeyOutput(BaseModel):
    required_services: List[APIService] = Field(description="List of API services needed for the workflow")
    collection_status: Literal["pending", "collecting", "completed"] = Field(default="pending")
    current_service: Optional[str] = Field(default=None, description="Currently collecting service")
    component_data: Optional[APIKeyComponentData] = Field(default=None, description="Data for AgentAPIKeyInput component")
    security_notes: List[str] = Field(default=[], description="Security reminders for API key handling")
    next_action: Literal["collect_key", "validate_key", "complete"] = Field(description="Next action to take")

# UserFeedbackAgent Output
class MissingRequirement(BaseModel):
    requirement_type: Literal["api_key", "file_upload", "oauth", "configuration"] = Field(description="Type of missing requirement")
    description: str = Field(description="Description of what is needed")
    priority: Literal["high", "medium", "low"] = Field(description="Priority level")
    component_needed: str = Field(description="UI component to collect this requirement")

class WorkflowFile(BaseModel):
    name: str = Field(description="File name")
    size: int = Field(description="File size in bytes")
    type: str = Field(description="File type/extension")
    content: str = Field(description="File content")
    description: str = Field(description="Description of what this file does")

class WorkflowSummary(BaseModel):
    workflow_name: str = Field(description="Name of the generated workflow")
    purpose: str = Field(description="What the workflow accomplishes")
    key_agents: List[str] = Field(description="List of main agents in the workflow")
    workflow_flow: str = Field(description="Description of the workflow progression")

class FileDownloadComponentData(BaseModel):
    files: List[WorkflowFile] = Field(description="Files available for download")
    title: str = Field(description="Title for the download center")
    description: str = Field(description="Description of the files")

class UserFeedbackOutput(BaseModel):
    analysis_complete: bool = Field(description="Whether analysis of workflow is complete")
    missing_requirements: List[MissingRequirement] = Field(default=[], description="List of missing requirements")
    workflow_summary: Optional[WorkflowSummary] = Field(default=None, description="Summary if workflow is complete")
    generated_files: List[WorkflowFile] = Field(default=[], description="Generated workflow files")
    component_data: Optional[FileDownloadComponentData] = Field(default=None, description="Data for FileDownloadCenter component")
    ready_for_approval: bool = Field(description="Whether workflow is ready for user approval")
    feedback_request: str = Field(description="Message to present to user")
    next_action: Literal["collect_requirements", "present_files", "request_approval", "complete"] = Field(description="Next action to take")

# Registry mapping
structured_outputs = {
    "ContextVariablesAgent": ContextVariablesOutput,
    "AgentsAgent": AgentsOutput,
    "HandoffsAgent": HandoffsOutput,
    "HooksAgent": HooksOutput,
    "OrchestratorAgent": OrchestratorOutput,
    "APIKeyAgent": APIKeyOutput,
    "UserFeedbackAgent": UserFeedbackOutput,
}

async def get_llm(flow: str = "base"):
    """Load LLM config with optional structured response model"""
    if flow in structured_outputs:
        return await make_structured_config(structured_outputs[flow])
    return await make_llm_config()