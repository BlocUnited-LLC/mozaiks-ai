# ==============================================================================
# FILE: Generator/Handoffs.py
# DESCRIPTION: Modular handoff creation for AG2 Generator workflow
# ==============================================================================
import logging
import time
from autogen.agentchat.group import (
    AgentTarget,
    RevertToUserTarget,
    OnCondition,
    StringLLMCondition,
    TerminateTarget
)

# Import enhanced logging
from logs.logging_config import (
    get_business_logger, 
    get_performance_logger,
    log_business_event,
    log_performance_metric
)

# Get specialized loggers
business_logger = get_business_logger("generator_handoffs")
performance_logger = get_performance_logger("generator_handoffs")
logger = logging.getLogger(__name__)

def wire_handoffs(agents: dict):
    """
    Configure agent handoffs using AG2's proper handoff mechanisms.
    Uses LLM-based conditions and after-work behavior to create the workflow flow.
    
    Args:
        agents: Dictionary of agents in the workflow.
    """
    handoff_start = time.time()
    
    log_business_event(
        event_type="HANDOFF_WIRING_STARTED",
        description="Starting AG2-compliant handoff configuration",
        context={"agent_count": len(agents), "agent_names": list(agents.keys())}
    )
    
    try:
        business_logger.info("🔗 [HANDOFFS] Configuring AG2-style handoffs...")
        
        # Configure AgentsAgent to hand off to ContextVariablesAgent when done
        if "AgentsAgent" in agents and "ContextVariablesAgent" in agents:
            agents["AgentsAgent"].handoffs.set_after_work(
                AgentTarget(agents["ContextVariablesAgent"])
            )
            business_logger.debug("🔗 [HANDOFFS] AgentsAgent → ContextVariablesAgent (after work)")
        
        # Configure ContextVariablesAgent to hand off to HandoffsAgent when done
        if "ContextVariablesAgent" in agents and "HandoffsAgent" in agents:
            agents["ContextVariablesAgent"].handoffs.set_after_work(
                AgentTarget(agents["HandoffsAgent"])
            )
            business_logger.debug("🔗 [HANDOFFS] ContextVariablesAgent → HandoffsAgent (after work)")
        
        # Configure HandoffsAgent to hand off to HooksAgent when done
        if "HandoffsAgent" in agents and "HooksAgent" in agents:
            agents["HandoffsAgent"].handoffs.set_after_work(
                AgentTarget(agents["HooksAgent"])
            )
            business_logger.debug("🔗 [HANDOFFS] HandoffsAgent → HooksAgent (after work)")
        
        # Configure HooksAgent to hand off to OrchestratorAgent when done
        if "HooksAgent" in agents and "OrchestratorAgent" in agents:
            agents["HooksAgent"].handoffs.set_after_work(
                AgentTarget(agents["OrchestratorAgent"])
            )
            business_logger.debug("🔗 [HANDOFFS] HooksAgent → OrchestratorAgent (after work)")

        # Configure OrchestratorAgent to hand off to UserFeedbackAgent when done
        if "OrchestratorAgent" in agents and "UserFeedbackAgent" in agents:
            agents["OrchestratorAgent"].handoffs.set_after_work(
                AgentTarget(agents["UserFeedbackAgent"])
            )
            business_logger.debug("🔗 [HANDOFFS] OrchestratorAgent → UserFeedbackAgent (after work)")

        # Configure UserFeedbackAgent - ALWAYS revert to user after presenting outputs
        if "UserFeedbackAgent" in agents:
            # Primary handoff: Always return to user after presenting workflow outputs
            agents["UserFeedbackAgent"].handoffs.set_after_work(
                RevertToUserTarget()
            )
            business_logger.debug("🔗 [HANDOFFS] UserFeedbackAgent → RevertToUser (after presenting outputs)")
            
            # Add conditional handoffs that can override the after-work behavior
            handoff_conditions = []
            
            # If API keys are needed, hand off to APIKeyAgent first
            if "APIKeyAgent" in agents:
                handoff_conditions.append(
                    OnCondition(
                        target=AgentTarget(agents["APIKeyAgent"]),
                        condition=StringLLMCondition(prompt="The system should prompt for API key setup only when it is explicitly required based on the features included in the user's request, or when missing API credentials block the execution of those features. ")
                    )
                )
                business_logger.debug("🔗 [HANDOFFS] UserFeedbackAgent → APIKeyAgent (when API keys explicitly needed)")
            
            # If user wants to restart/modify workflow, go back to AgentsAgent
            if "AgentsAgent" in agents:
                handoff_conditions.append(
                    OnCondition(
                        target=AgentTarget(agents["AgentsAgent"]),
                        condition=StringLLMCondition(prompt="When the user wants to restart the workflow generation, modify requirements, or start over with a different approach. This includes requests to change the workflow design or requirements.")
                    )
                )
                business_logger.debug("🔗 [HANDOFFS] UserFeedbackAgent → AgentsAgent (when user wants to restart)")
            
            # Add the conditional handoffs if any were defined
            if handoff_conditions:
                agents["UserFeedbackAgent"].handoffs.add_llm_conditions(handoff_conditions)
                business_logger.debug(f"🔗 [HANDOFFS] UserFeedbackAgent configured with {len(handoff_conditions)} conditional handoffs")

        # Configure APIKeyAgent to return to UserFeedbackAgent after collecting keys
        if "APIKeyAgent" in agents and "UserFeedbackAgent" in agents:
            agents["APIKeyAgent"].handoffs.set_after_work(
                AgentTarget(agents["UserFeedbackAgent"])
            )
            business_logger.debug("🔗 [HANDOFFS] APIKeyAgent → UserFeedbackAgent (after collecting credentials)")

        # Configure user decision points for web UI workflow control
        business_logger.info("🔗 [HANDOFFS] Configuring user decision points for web UI...")
        if "user" in agents and "AgentsAgent" in agents:
            # Default: Start workflow from the beginning when user provides input
            agents["user"].handoffs.set_after_work(
                AgentTarget(agents["AgentsAgent"])
            )
            business_logger.debug("🔗 [HANDOFFS] User → AgentsAgent (default workflow start)")
            
            # Conditional handoffs based on user intent
            user_conditions = []
            
            # If user wants to restart or modify requirements
            user_conditions.append(
                OnCondition(
                    target=AgentTarget(agents["AgentsAgent"]),
                    condition=StringLLMCondition(prompt="When the user wants to start a new workflow, modify requirements, restart the process, or change their original request. This includes phrases like 'start over', 'change', 'modify', 'new workflow', or providing different requirements.")
                )
            )
            
            # If user approves the workflow and wants to finish
            user_conditions.append(
                OnCondition(
                    target=TerminateTarget(),
                    condition=StringLLMCondition(prompt="When the user explicitly approves the workflow, says they're satisfied, confirms completion, or clearly indicates they want to end the conversation. This includes phrases like 'looks good', 'approve', 'finished', 'done', 'thank you', or explicit completion statements.")
                )
            )
            
            # If user has questions or wants to see something specific
            if "UserFeedbackAgent" in agents:
                user_conditions.append(
                    OnCondition(
                        target=AgentTarget(agents["UserFeedbackAgent"]),
                        condition=StringLLMCondition(prompt="When the user has questions about the workflow, wants clarification, asks for explanations, or requests to see specific parts of the generated workflow without wanting to restart.")
                    )
                )
            
            agents["user"].handoffs.add_llm_conditions(user_conditions)
            business_logger.debug(f"🔗 [HANDOFFS] User configured with {len(user_conditions)} conditional handoffs")
        else:
            business_logger.warning("⚠️ [HANDOFFS] User or AgentsAgent not found for decision points")

        
        total_handoff_time = (time.time() - handoff_start) * 1000
        
        log_performance_metric(
            metric_name="total_handoff_wiring_duration",
            value=total_handoff_time,
            unit="ms",
            context={"agent_count": len(agents)}
        )
        
        log_business_event(
            event_type="HANDOFF_WIRING_COMPLETED",
            description="AG2-compliant handoff configuration completed",
            context={
                "agent_count": len(agents),
                "total_time_ms": total_handoff_time,
                "handoff_type": "after_work_and_conditions"
            }
        )
        
        business_logger.info(f"🎉 [HANDOFFS] AG2 handoff wiring completed in {total_handoff_time:.1f}ms")
        
    except Exception as e:
        logger.error(f"❌ [HANDOFFS] Handoff wiring failed: {e}", exc_info=True)
        log_business_event(
            event_type="HANDOFF_WIRING_FAILED",
            description="Handoff wiring process failed",
            context={"error": str(e)},
            level="ERROR"
        )
        raise