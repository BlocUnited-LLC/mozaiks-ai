# ==============================================================================
# FILE: Generator/OrchestrationPattern.py
# DESCRIPTION: Simplified AG2 orchestration using core workflow system
# ==============================================================================
import logging
from core.workflow.groupchat_manager import run_workflow_orchestration
from .Agents import define_agents
from .ContextVariables import get_context
from .Handoffs import wire_handoffs

logger = logging.getLogger(__name__)

async def run_groupchat(
    llm_config, 
    enterprise_id, 
    chat_id, 
    user_id=None, 
    initial_message=None, 
    communication_channel=None
):
    """
    Run the Generator group chat using the standardized workflow orchestration.
    
    This is now much simpler since most logic is handled by the core workflow system
    based on workflow.json configuration.
    """
    
    # Use the universal workflow orchestration function
    await run_workflow_orchestration(
        workflow_type="generator",
        llm_config=llm_config,
        enterprise_id=enterprise_id,
        chat_id=chat_id,
        user_id=user_id,
        initial_message=initial_message,
        communication_channel=communication_channel,
        agents_factory=define_agents,       # Our workflow-specific agent factory
        context_factory=get_context,        # Our workflow-specific context factory  
        handoffs_factory=wire_handoffs      # Our workflow-specific handoffs factory
    )