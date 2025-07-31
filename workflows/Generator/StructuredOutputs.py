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
    agent_type: Literal["ConversableAgent", "UserProxyAgent", "AssistantAgent"]
    system_message: str = Field(description="Complete system message for the agent")
    human_input_mode: Literal["ALWAYS", "NEVER", "TERMINATE"]
    max_consecutive_auto_reply: int = Field(default=1)

class AgentsOutput(BaseModel):
    agent_list: List[AgentDefinition]
    
# ContextVariablesAgent Output
class ContextVariablesDefinition(BaseModel):
    database_endpoint: str = Field(description="Variable name (e.g., 'user_requirements')")
    description: str = Field(description="Description of what this context variable represents")

class ContextVariablesOutput(BaseModel):
    context_variables: List[ContextVariablesDefinition]

# HandoffsAgent Output
class HandoffRule(BaseModel):
    source_agent: str = Field(description="Source agent name")
    target_agent: str = Field(description="Target agent name, 'user', or 'terminate'") 
    handoff_type: Literal["llm_condition", "after_work", "context_condition"] = Field(description="Type of handoff condition")
    condition: Optional[str] = Field(default=None, description="LLM condition prompt if handoff_type is llm_condition")
    context_expression: Optional[str] = Field(default=None, description="Context expression if handoff_type is context_condition")
    priority: int = Field(default=1, description="Priority for LLM conditions (lower = higher priority)")
    description: str = Field(description="Human-readable description of this handoff rule")

class HandoffsOutput(BaseModel):
    handoff_rules: List[HandoffRule] = Field(description="All handoff rules between agents")
    workflow_pattern: str = Field(default="sequential", description="Overall workflow pattern (sequential, parallel, conditional)")
    termination_strategy: Literal["manual", "automatic", "conditional"] = Field(default="automatic", description="How the workflow should terminate")

class OrchestratorOutput(BaseModel):
    max_rounds: int = Field(default=8, description="Maximum conversation rounds")
    initial_agent: str = Field(description="Initial agent name")
    initial_message: str = Field(description="Default initial message")
    workflow_name: str = Field(description="Name of generated workflow")
    workflow_description: str = Field(description="Description of workflow purpose")

# Registry mapping
structured_outputs = {
    "ContextVariablesAgent": ContextVariablesOutput,
    "AgentsAgent": AgentsOutput,
    "HandoffsAgent": HandoffsOutput,
    "OrchestratorAgent": OrchestratorOutput,
}

async def get_llm(flow: str = "base", enable_streaming: bool = False, enable_token_tracking: bool = False):
    """Load LLM config with optional structured response model and streaming"""
    if flow in structured_outputs:
        # For structured outputs with streaming: add stream=True to extra_config
        extra_config = {"stream": True} if enable_streaming else None
        return await make_structured_config(structured_outputs[flow], extra_config=extra_config, enable_token_tracking=enable_token_tracking)
    # For base configurations with streaming
    return await make_llm_config(stream=enable_streaming, enable_token_tracking=enable_token_tracking)