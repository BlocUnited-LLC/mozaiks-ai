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
        
        # Configure ContextVariablesAgent to hand off to AgentsAgent when done
        if "ContextVariablesAgent" in agents and "AgentsAgent" in agents:
            agents["ContextVariablesAgent"].handoffs.set_after_work(
                AgentTarget(agents["AgentsAgent"])
            )
            business_logger.debug("🔗 [HANDOFFS] ContextVariablesAgent → AgentsAgent (after work)")
        
        # Configure AgentsAgent to hand off to HandoffsAgent when done
        if "AgentsAgent" in agents and "HandoffsAgent" in agents:
            agents["AgentsAgent"].handoffs.set_after_work(
                AgentTarget(agents["HandoffsAgent"])
            )
            business_logger.debug("🔗 [HANDOFFS] AgentsAgent → HandoffsAgent (after work)")
        
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

        # Configure UserFeedbackAgent conditional handoffs based on what's needed
        if "UserFeedbackAgent" in agents:
            # Add conditional handoffs from UserFeedbackAgent
            handoff_conditions = []
            
            # If API keys are needed, hand off to APIKeyAgent
            if "APIKeyAgent" in agents:
                handoff_conditions.append(
                    OnCondition(
                        target=AgentTarget(agents["APIKeyAgent"]),
                        condition=StringLLMCondition(prompt="When API keys or authentication credentials are needed for the workflow to function. This includes any mention of requiring API access, authentication tokens, or service credentials.")
                    )
                )
                business_logger.debug("🔗 [HANDOFFS] UserFeedbackAgent → APIKeyAgent (when API keys needed)")
            
            # Default: return to user for approval/feedback
            handoff_conditions.append(
                OnCondition(
                    target=RevertToUserTarget(),
                    condition=StringLLMCondition(prompt="When all required information is collected and the workflow is ready for user approval, or when user input/feedback is needed.")
                )
            )
            
            agents["UserFeedbackAgent"].handoffs.add_llm_conditions(handoff_conditions)
            business_logger.debug("🔗 [HANDOFFS] UserFeedbackAgent → APIKeyAgent (conditional) OR user (approval)")

        # Configure APIKeyAgent to return to UserFeedbackAgent after collecting keys
        if "APIKeyAgent" in agents and "UserFeedbackAgent" in agents:
            agents["APIKeyAgent"].handoffs.set_after_work(
                AgentTarget(agents["UserFeedbackAgent"])
            )
            business_logger.debug("🔗 [HANDOFFS] APIKeyAgent → UserFeedbackAgent (after collecting credentials)")

        # Configure user decision points for web UI workflow control
        business_logger.info("🔗 [HANDOFFS] Configuring user decision points for web UI...")
        if "user" in agents and "ContextVariablesAgent" in agents:
            # Default handoff from user to the start of the workflow
            agents["user"].handoffs.set_after_work(
                AgentTarget(agents["ContextVariablesAgent"])
            )
            business_logger.debug("🔗 [HANDOFFS] User → ContextVariablesAgent (default workflow start)")
            
            # Conditional handoffs based on user web UI input
            agents["user"].handoffs.add_llm_conditions([
                OnCondition(
                    target=AgentTarget(agents["ContextVariablesAgent"]),
                    condition=StringLLMCondition(prompt="When the user wants to restart, revise, or create a new workflow from the beginning. This includes requests to modify the workflow requirements or start over.")
                ),
                OnCondition(
                    target=TerminateTarget(),
                    condition=StringLLMCondition(prompt="When the user is satisfied with the workflow, confirms approval, or wants to finish the conversation. This includes expressions of satisfaction, approval, or completion.")
                )
            ])
            business_logger.debug("🔗 [HANDOFFS] User web UI conditions: restart workflow OR approve/terminate")
        else:
            business_logger.warning("⚠️ [HANDOFFS] User or ContextVariablesAgent not found for decision points")

        
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