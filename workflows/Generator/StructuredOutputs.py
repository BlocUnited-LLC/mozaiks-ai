# ==============================================================================
# FILE: Generator/StructuredOutputs.py
# DESCRIPTION: Structured output models for AG2 Generator agents
# ==============================================================================

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Literal
from core.core_config import make_llm_config, make_structured_config

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
    
# ContextVariablesAgent Output
class ContextVariablesDefinition(BaseModel):
    name: str = Field(description="Variable name (e.g., 'project_title', 'user_requirements')")
    extraction_code: str = Field(description="Python code to extract value (e.g., \"concept_data.get('ProjectTitle', '')\")")
    description: str = Field(description="Description of what this context variable represents")
    default_value: str = Field(default="''", description="Default value if extraction fails")

class ContextVariablesOutput(BaseModel):
    context_variables: List[ContextVariablesDefinition] = Field(description="All context variables for workflow")

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
class HookRule(BaseModel):
    name: str = Field(description="Hook function name")
    hook_type: Literal["process_message_before_send", "update_agent_state", "process_message_after_receive"] = Field(description="Type of hook")
    trigger_agents: List[str] = Field(default=[], description="List of agent names this hook applies to (empty = all agents)")
    description: str = Field(description="Description of what this hook does")
    function_code: str = Field(description="Complete Python function code for the hook")

class HooksOutput(BaseModel):
    hooks_rules: List[HookRule] = Field(description="All hook rules for the workflow")

class OrchestratorOutput(BaseModel):
    max_rounds: int = Field(default=8, description="Maximum conversation rounds")
    initial_agent: str = Field(description="Initial agent name")
    initial_message: str = Field(description="Default initial message")
    workflow_name: str = Field(description="Name of generated workflow")
    workflow_description: str = Field(description="Description of workflow purpose")

# APIKeyAgent Output
class APIKeyOutput(BaseModel):
    service_name: str = Field(description="Name of the API service (e.g., 'OpenAI', 'Anthropic')")
    required: bool = Field(description="Whether this API key is required for the workflow")
    help_url: str = Field(description="URL where users can obtain the API key")
    instructions: str = Field(description="Step-by-step instructions for obtaining the key")

# UserFeedbackAgent Output
class UserFeedbackOutput(BaseModel):
    workflow_name: str = Field(description="Name of the generated workflow")
    purpose: str = Field(description="What the workflow accomplishes")
    key_agents: List[str] = Field(description="List of main agents in the workflow")
    workflow_flow: str = Field(description="Description of the workflow progression")

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