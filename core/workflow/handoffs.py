# ==============================================================================
# FILE: core/workflow/handoffs.py
# DESCRIPTION: Workflow-agnostic handoff manager - converts YAML configs to AG2 handoffs
# ==============================================================================
import time
import logging
from typing import Dict, Any, List, Optional
from autogen.agentchat.group import (
    AgentTarget,
    RevertToUserTarget,
    OnCondition,
    StringLLMCondition,
    OnContextCondition,
    ExpressionContextCondition,
    ContextExpression,
    TerminateTarget
)

from .file_manager import workflow_file_manager

# Import enhanced logging
from logs.logging_config import (
    get_business_logger, 
    get_performance_logger,
    log_business_event,
    log_performance_metric
)

# Get specialized loggers
business_logger = get_business_logger("workflow_handoffs")
performance_logger = get_performance_logger("workflow_handoffs")
logger = logging.getLogger(__name__)

class HandoffManager:
    """
    Converts handoffs.yaml configuration into AG2 handoff rules.
    Completely workflow-agnostic - works with any workflow's handoffs.yaml file.
    """
    
    def __init__(self):
        self.target_mapping = {
            "user": lambda: RevertToUserTarget(),
            "terminate": lambda: TerminateTarget(),
        }
    
    def apply_handoffs_from_yaml(self, workflow_name: str, agents: Dict[str, Any]) -> None:
        """
        Load handoffs.yaml and apply the rules to AG2 agents.
        
        Args:
            workflow_name: Name of the workflow (determines which handoffs.yaml to load)
            agents: Dictionary of agent instances to apply handoffs to
        """
        handoff_start = time.time()
        
        try:
            business_logger.info(f"🔗 [HANDOFFS] Loading handoffs configuration for workflow: {workflow_name}")
            
            # Load workflow configuration from YAML files
            workflow_config = workflow_file_manager.load_workflow(workflow_name)
            
            if not workflow_config:
                business_logger.error(f"❌ [HANDOFFS] No configuration found for workflow: {workflow_name}")
                return
            
            handoffs_config = workflow_config.get('handoffs', {})
            handoff_rules = handoffs_config.get('handoff_rules', [])
            
            if not handoff_rules:
                business_logger.warning(f"⚠️ [HANDOFFS] No handoff rules found in {workflow_name}/handoffs.yaml")
                return
            
            business_logger.info(f"🔗 [HANDOFFS] Found {len(handoff_rules)} handoff rules for {workflow_name}")
            
            log_business_event(
                event_type="HANDOFFS_YAML_LOADING_STARTED",
                description="Starting handoff application from YAML configuration",
                context={
                    "workflow_name": workflow_name,
                    "rules_count": len(handoff_rules),
                    "agent_count": len(agents)
                }
            )
            
            # Group rules by source agent for efficient processing
            agent_rules = {}
            for rule in handoff_rules:
                source_agent = rule.get('source_agent')
                if not source_agent:
                    business_logger.warning(f"⚠️ [HANDOFFS] Skipping rule with missing source_agent: {rule}")
                    continue
                    
                if source_agent not in agent_rules:
                    agent_rules[source_agent] = {
                        "after_work": None,
                        "llm_conditions": [],
                        "context_conditions": []
                    }
                
                handoff_type = rule.get('handoff_type', 'after_work')
                if handoff_type == "after_work":
                    agent_rules[source_agent]["after_work"] = rule
                elif handoff_type == "condition":
                    agent_rules[source_agent]["llm_conditions"].append(rule)
                elif handoff_type == "context_condition":
                    agent_rules[source_agent]["context_conditions"].append(rule)
                else:
                    business_logger.warning(f"⚠️ [HANDOFFS] Unknown handoff_type '{handoff_type}' in rule: {rule}")
            
            # Apply handoffs to each agent
            applied_count = 0
            for agent_name, rules in agent_rules.items():
                if agent_name not in agents:
                    business_logger.warning(f"⚠️ [HANDOFFS] Agent '{agent_name}' not found in workflow agents")
                    continue
                
                agent = agents[agent_name]
                self._configure_agent_handoffs(agent, agent_name, rules, agents)
                applied_count += 1
            
            total_time = (time.time() - handoff_start) * 1000
            
            log_performance_metric(
                metric_name="handoffs_yaml_application_duration",
                value=total_time,
                unit="ms",
                context={
                    "workflow_name": workflow_name,
                    "rules_count": len(handoff_rules),
                    "agents_configured": applied_count
                }
            )
            
            business_logger.info(f"✅ [HANDOFFS] Successfully applied handoffs to {applied_count} agents in {total_time:.1f}ms")
            
            log_business_event(
                event_type="HANDOFFS_YAML_LOADING_COMPLETED",
                description="Handoff application from YAML completed successfully",
                context={
                    "workflow_name": workflow_name,
                    "rules_applied": len(handoff_rules),
                    "agents_configured": applied_count,
                    "duration_ms": total_time
                }
            )
            
        except Exception as e:
            business_logger.error(f"❌ [HANDOFFS] Failed to apply handoffs for {workflow_name}: {e}", exc_info=True)
            log_business_event(
                event_type="HANDOFFS_YAML_LOADING_FAILED",
                description="Handoff application from YAML failed",
                context={
                    "workflow_name": workflow_name,
                    "error": str(e)
                },
                level="ERROR"
            )
            # Don't raise - handoffs are optional and shouldn't break the workflow
    
    def _configure_agent_handoffs(self, agent: Any, agent_name: str, rules: Dict[str, Any], agents: Dict[str, Any]) -> None:
        """Configure handoffs for a single agent from rules"""
        
        # Set after-work behavior
        if rules["after_work"]:
            target = self._create_target(rules["after_work"], agents)
            agent.handoffs.set_after_work(target)
            target_name = rules["after_work"].get('target_agent', 'unknown')
            business_logger.debug(f"🔗 [HANDOFFS] {agent_name} → {target_name} (after work)")
        
        # Add LLM conditions
        if rules["llm_conditions"]:
            # Sort by priority (lower number = higher priority)
            sorted_conditions = sorted(rules["llm_conditions"], key=lambda r: r.get('priority', 1))
            
            conditions = []
            for rule in sorted_conditions:
                target = self._create_target(rule, agents)
                condition_text = rule.get('condition', '')
                
                if condition_text:
                    condition = OnCondition(
                        target=target,
                        condition=StringLLMCondition(prompt=condition_text)
                    )
                    conditions.append(condition)
                    target_name = rule.get('target_agent', 'unknown')
                    business_logger.debug(f"🔗 [HANDOFFS] {agent_name} → {target_name} (LLM condition)")
            
            if conditions:
                agent.handoffs.add_llm_conditions(conditions)
        
        # Add context conditions
        if rules["context_conditions"]:
            for rule in rules["context_conditions"]:
                target = self._create_target(rule, agents)
                context_expr = rule.get('context_expression', '')
                
                if context_expr:
                    condition = OnContextCondition(
                        target=target,
                        condition=ExpressionContextCondition(
                            expression=ContextExpression(context_expr)
                        )
                    )
                    agent.handoffs.add_context_condition(condition)
                    target_name = rule.get('target_agent', 'unknown')
                    business_logger.debug(f"🔗 [HANDOFFS] {agent_name} → {target_name} (Context condition)")
    
    def _create_target(self, rule: Dict[str, Any], agents: Dict[str, Any]):
        """Create appropriate target from handoff rule dictionary"""
        target_agent = rule.get('target_agent')
        
        # Special targets
        if target_agent in self.target_mapping:
            return self.target_mapping[target_agent]()
        
        # Agent targets
        if target_agent in agents:
            return AgentTarget(agents[target_agent])
        
        # Fallback: revert to user for unknown targets
        business_logger.warning(f"⚠️ [HANDOFFS] Target agent '{target_agent}' not found, reverting to user")
        return RevertToUserTarget()

# Create global instance
handoff_manager = HandoffManager()

def wire_handoffs(workflow_name: str, agents: Dict[str, Any]) -> None:
    """
    Main entry point - wire handoffs for a workflow using its handoffs.yaml file.
    
    This is the core function that should be called by workflow systems.
    It reads the handoffs.yaml file and applies the rules to AG2 agents.
    
    Args:
        workflow_name: Name of the workflow (determines which handoffs.yaml to load)
        agents: Dictionary of agent instances from the workflow
    """
    try:
        business_logger.info(f"🔗 [HANDOFFS] Wiring handoffs for workflow: {workflow_name}")
        handoff_manager.apply_handoffs_from_yaml(workflow_name, agents)
        business_logger.info(f"✅ [HANDOFFS] Handoff wiring completed for {workflow_name}")
        
    except Exception as e:
        business_logger.error(f"❌ [HANDOFFS] Failed to wire handoffs for {workflow_name}: {e}", exc_info=True)
        # Don't raise - handoffs are optional and shouldn't break the workflow
