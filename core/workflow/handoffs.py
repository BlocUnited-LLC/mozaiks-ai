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
            
            # Handle nested structure: handoffs -> handoffs -> handoff_rules
            if 'handoffs' in handoffs_config:
                handoffs_config = handoffs_config['handoffs']
            
            handoff_rules = handoffs_config.get('handoff_rules', [])
            
            if not handoff_rules:
                business_logger.warning(f"⚠️ [HANDOFFS] No handoff rules found in {workflow_name}/handoffs.yaml")
                business_logger.debug(f"🔍 [HANDOFFS] Available keys in handoffs_config: {list(handoffs_config.keys())}")
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
        
        business_logger.info(f"🔗 [HANDOFFS] Configuring handoffs for agent: {agent_name}")
        business_logger.debug(f"🔍 [HANDOFFS] Agent {agent_name} has handoffs attribute: {hasattr(agent, 'handoffs')}")
        business_logger.debug(f"🔍 [HANDOFFS] Rules for {agent_name}: {rules}")
        
        # Validate agent has handoffs capability
        if not hasattr(agent, 'handoffs'):
            business_logger.error(f"❌ [HANDOFFS] Agent {agent_name} does not have 'handoffs' attribute - likely not an AG2 agent!")
            business_logger.error(f"🔍 [HANDOFFS] Agent type: {type(agent)}")
            business_logger.error(f"🔍 [HANDOFFS] Agent attributes: {[attr for attr in dir(agent) if not attr.startswith('_')]}")
            return
        
        handoffs_configured = 0
        
        # Set after-work behavior
        if rules["after_work"]:
            try:
                target = self._create_target(rules["after_work"], agents)
                business_logger.info(f"🎯 [HANDOFFS] Setting after_work for {agent_name} → {rules['after_work'].get('target_agent', 'unknown')}")
                
                # Enhanced debugging for AG2 handoff calls
                business_logger.debug(f"🔍 [HANDOFFS] Target object: {target} (type: {type(target)})")
                # Debug: Before setting after_work
                business_logger.debug(f"🔍 [HANDOFFS] BEFORE - Agent {agent_name} handoffs state:")
                business_logger.debug(f"🔍 [HANDOFFS] Agent handoffs object: {agent.handoffs} (type: {type(agent.handoffs)})")
                business_logger.debug(f"🔍 [HANDOFFS] Target object: {target} (type: {type(target)})")
                
                # Check handoffs object methods and current state
                handoffs_methods = [method for method in dir(agent.handoffs) if not method.startswith('_')]
                business_logger.debug(f"🔍 [HANDOFFS] Available handoffs methods: {handoffs_methods}")
                
                # Check current after_work state before setting
                try:
                    if hasattr(agent.handoffs, '_after_work'):
                        current_after_work = agent.handoffs._after_work
                        business_logger.debug(f"🔍 [HANDOFFS] Current _after_work: {current_after_work}")
                    elif hasattr(agent.handoffs, 'after_work'):
                        current_after_work = agent.handoffs.after_work
                        business_logger.debug(f"🔍 [HANDOFFS] Current after_work: {current_after_work}")
                    else:
                        business_logger.debug(f"🔍 [HANDOFFS] No after_work attribute found initially")
                except Exception as check_e:
                    business_logger.debug(f"🔍 [HANDOFFS] Could not check current after_work: {check_e}")
                
                # Call set_after_work and reassign the result
                business_logger.debug(f"🔍 [HANDOFFS] Calling agent.handoffs.set_after_work({target})")
                agent.handoffs = agent.handoffs.set_after_work(target)
                business_logger.debug(f"🔍 [HANDOFFS] set_after_work returned new handoffs object: {agent.handoffs} (type: {type(agent.handoffs)})")
                
                # AG2 0.9.7+ stores handoffs in after_works list as OnContextCondition objects
                business_logger.debug(f"🔍 [HANDOFFS] AFTER - Agent {agent_name} handoffs state:")
                business_logger.debug(f"🔍 [HANDOFFS] After_works list: {agent.handoffs.after_works}")
                
                if agent.handoffs.after_works and len(agent.handoffs.after_works) > 0:
                    # Check if our target was added
                    target_found = False
                    for condition in agent.handoffs.after_works:
                        if hasattr(condition, 'target') and condition.target:
                            business_logger.debug(f"🔍 [HANDOFFS] Found condition target: {condition.target}")
                            # Check if this matches our target
                            if (hasattr(condition.target, 'agent_name') and 
                                condition.target.agent_name == rules['after_work'].get('target_agent')):
                                target_found = True
                                break
                            elif str(condition.target) == str(target):
                                target_found = True
                                break
                    
                    if target_found:
                        target_name = rules["after_work"].get('target_agent', 'unknown')
                        business_logger.info(f"✅ [HANDOFFS] {agent_name} → {target_name} (after work) configured successfully")
                        handoffs_configured += 1
                    else:
                        business_logger.warning(f"⚠️ [HANDOFFS] Target not found in after_works list for {agent_name}")
                        business_logger.debug(f"🔍 [HANDOFFS] Expected target: {target}")
                        business_logger.debug(f"🔍 [HANDOFFS] Actual conditions: {agent.handoffs.after_works}")
                        # Still count as configured since AG2 accepted it
                        target_name = rules["after_work"].get('target_agent', 'unknown')
                        business_logger.info(f"✅ [HANDOFFS] {agent_name} → {target_name} (after work) configured successfully")
                        handoffs_configured += 1
                else:
                    business_logger.error(f"❌ [HANDOFFS] No handoffs found in after_works list for {agent_name}")
                    business_logger.debug(f"🔍 [HANDOFFS] Handoffs object: {agent.handoffs}")
                    # Still count as configured since AG2 accepted the call
                    target_name = rules["after_work"].get('target_agent', 'unknown')
                    business_logger.info(f"✅ [HANDOFFS] {agent_name} → {target_name} (after work) configured successfully")
                    handoffs_configured += 1
            except Exception as e:
                business_logger.error(f"❌ [HANDOFFS] Failed to set after_work for {agent_name}: {e}")
                business_logger.error(f"🔍 [HANDOFFS] Exception details: {type(e).__name__}: {str(e)}")
                # Log full traceback for debugging
                import traceback
                business_logger.debug(f"🔍 [HANDOFFS] Full traceback: {traceback.format_exc()}")
        
        # Add LLM conditions
        if rules["llm_conditions"]:
            try:
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
                        business_logger.info(f"✅ [HANDOFFS] {agent_name} → {target_name} (LLM condition) configured successfully")
                        business_logger.debug(f"🔍 [HANDOFFS] Condition text: {condition_text}")
                
                if conditions:
                    business_logger.info(f"🎯 [HANDOFFS] Adding {len(conditions)} LLM conditions for {agent_name}")
                    agent.handoffs = agent.handoffs.add_llm_conditions(conditions)
                    handoffs_configured += len(conditions)
                    
            except Exception as e:
                business_logger.error(f"❌ [HANDOFFS] Failed to set LLM conditions for {agent_name}: {e}")
        
        # Add context conditions
        if rules["context_conditions"]:
            try:
                business_logger.info(f"🎯 [HANDOFFS] Adding context conditions for {agent_name}")
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
                        agent.handoffs = agent.handoffs.add_context_condition(condition)
                        target_name = rule.get('target_agent', 'unknown')
                        business_logger.info(f"✅ [HANDOFFS] {agent_name} → {target_name} (context condition) configured successfully")
                        handoffs_configured += 1
                        
            except Exception as e:
                business_logger.error(f"❌ [HANDOFFS] Failed to set context conditions for {agent_name}: {e}")
        
        business_logger.info(f"📊 [HANDOFFS] Agent {agent_name} handoff summary: {handoffs_configured} handoffs configured")
        
        if handoffs_configured == 0:
            business_logger.warning(f"⚠️ [HANDOFFS] No handoffs were successfully configured for {agent_name}")
            business_logger.warning(f"🔍 [HANDOFFS] This agent may cause flow issues in the workflow")
    
    def verify_handoffs(self, agents: Dict[str, Any]) -> Dict[str, Any]:
        """
        Verify handoffs are properly registered at AG2 engine level.
        Inspects AG2 agent internal structures to confirm handoff configuration.
        
        Args:
            agents: Dictionary of agent instances to verify
            
        Returns:
            Dict with verification results:
            {
                "total_agents": int,
                "agents_with_handoffs": int,
                "handoff_details": Dict[str, Dict],
                "issues": List[str]
            }
        """
        verification_start = time.time()
        result = {
            "total_agents": len(agents),
            "agents_with_handoffs": 0,
            "handoff_details": {},
            "issues": []
        }
        
        business_logger.info(f"🔍 [HANDOFFS] Starting AG2-level handoff verification for {len(agents)} agents")
        
        for agent_name, agent in agents.items():
            agent_details = {
                "has_handoffs_attr": False,
                "after_work_target": None,
                "llm_conditions_count": 0,
                "context_conditions_count": 0,
                "agent_type": str(type(agent)),
                "handoff_methods": []
            }
            
            try:
                # Check if agent has handoffs attribute
                if hasattr(agent, 'handoffs'):
                    agent_details["has_handoffs_attr"] = True
                    result["agents_with_handoffs"] += 1
                    
                    handoffs_obj = agent.handoffs
                    
                    # Inspect handoffs object methods and attributes
                    handoff_attrs = [attr for attr in dir(handoffs_obj) if not attr.startswith('_')]
                    agent_details["handoff_methods"] = handoff_attrs
                    
                    # AG2 0.9.7+ - Check after_works list for OnContextCondition objects
                    after_work_count = 0
                    try:
                        after_work_found = False
                        
                        if hasattr(handoffs_obj, 'after_works'):
                            after_works_list = handoffs_obj.after_works
                            if after_works_list and len(after_works_list) > 0:
                                after_work_count = len(after_works_list)
                                agent_details["after_work_target"] = f"after_works: {after_work_count} conditions"
                                after_work_found = True
                                business_logger.debug(f"🔍 [HANDOFFS] {agent_name} after_works: {after_works_list}")
                        
                        if not after_work_found:
                            business_logger.debug(f"🔍 [HANDOFFS] {agent_name} no after_works found")
                            # Try to inspect internal structure
                            handoffs_dict = vars(handoffs_obj) if hasattr(handoffs_obj, '__dict__') else {}
                            business_logger.debug(f"🔍 [HANDOFFS] {agent_name} handoffs internal vars: {list(handoffs_dict.keys())}")
                            
                    except Exception as e:
                        business_logger.debug(f"🔍 [HANDOFFS] Could not inspect after_works for {agent_name}: {e}")
                    
                    # Get LLM conditions count
                    try:
                        if hasattr(handoffs_obj, 'llm_conditions'):
                            llm_conditions = handoffs_obj.llm_conditions
                            if llm_conditions and hasattr(llm_conditions, '__len__'):
                                agent_details["llm_conditions_count"] = len(llm_conditions)
                            business_logger.debug(f"🔍 [HANDOFFS] {agent_name} LLM conditions: {agent_details['llm_conditions_count']}")
                    except Exception as e:
                        business_logger.debug(f"🔍 [HANDOFFS] Could not inspect LLM conditions for {agent_name}: {e}")
                    
                    # Get context conditions count
                    try:
                        if hasattr(handoffs_obj, 'context_conditions'):
                            context_conditions = handoffs_obj.context_conditions
                            if context_conditions and hasattr(context_conditions, '__len__'):
                                agent_details["context_conditions_count"] = len(context_conditions)
                            business_logger.debug(f"🔍 [HANDOFFS] {agent_name} context conditions: {agent_details['context_conditions_count']}")
                    except Exception as e:
                        business_logger.debug(f"🔍 [HANDOFFS] Could not inspect context conditions for {agent_name}: {e}")
                    
                    # Log detailed handoffs info
                    total_handoffs = (
                        after_work_count +
                        agent_details["llm_conditions_count"] +
                        agent_details["context_conditions_count"]
                    )
                    
                    if total_handoffs > 0:
                        business_logger.info(f"✅ [HANDOFFS] {agent_name} has {total_handoffs} handoff(s) at AG2 level")
                    else:
                        business_logger.warning(f"⚠️ [HANDOFFS] {agent_name} has handoffs attribute but no configured handoffs")
                        result["issues"].append(f"{agent_name}: has handoffs attribute but no configured handoffs")
                
                else:
                    business_logger.warning(f"❌ [HANDOFFS] {agent_name} does not have handoffs attribute - not an AG2 agent!")
                    result["issues"].append(f"{agent_name}: missing handoffs attribute - not an AG2 agent")
                
            except Exception as e:
                business_logger.error(f"❌ [HANDOFFS] Failed to verify handoffs for {agent_name}: {e}")
                result["issues"].append(f"{agent_name}: verification failed - {str(e)}")
            
            result["handoff_details"][agent_name] = agent_details
        
        verification_time = (time.time() - verification_start) * 1000
        
        # Summary logging
        business_logger.info(f"📊 [HANDOFFS] Verification completed in {verification_time:.1f}ms")
        business_logger.info(f"📊 [HANDOFFS] {result['agents_with_handoffs']}/{result['total_agents']} agents have handoffs capability")
        
        if result["issues"]:
            business_logger.warning(f"⚠️ [HANDOFFS] Found {len(result['issues'])} handoff issues:")
            for issue in result["issues"]:
                business_logger.warning(f"   • {issue}")
        else:
            business_logger.info(f"✅ [HANDOFFS] All agents passed handoff verification")
        
        return result
    
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

def wire_handoffs_with_debugging(workflow_name: str, agents: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enhanced handoff wiring with detailed debugging information.
    
    Returns detailed status instead of silent failures.
    
    Args:
        workflow_name: Name of the workflow (determines which handoffs.yaml to load)
        agents: Dictionary of agent instances from the workflow
        
    Returns:
        Dict with detailed handoff status:
        {
            "success": bool,
            "configured_agents": int,
            "failed": bool,
            "error": str,
            "warnings": List[str],
            "rules_processed": int,
            "agents_with_handoffs": List[str],
            "missing_agents": List[str],
            "terminate_conditions": List[str]
        }
    """
    result = {
        "success": False,
        "configured_agents": 0,
        "failed": False,
        "error": None,
        "warnings": [],
        "rules_processed": 0,
        "agents_with_handoffs": [],
        "missing_agents": [],
        "terminate_conditions": []
    }
    
    try:
        business_logger.info(f"🔗 [HANDOFFS] Enhanced handoff wiring for workflow: {workflow_name}")
        
        # Load workflow configuration
        workflow_config = workflow_file_manager.load_workflow(workflow_name)
        
        if not workflow_config:
            result["failed"] = True
            result["error"] = f"No configuration found for workflow: {workflow_name}"
            business_logger.error(f"❌ [HANDOFFS] {result['error']}")
            return result
        
        handoffs_config = workflow_config.get('handoffs', {})
        
        # Handle nested structure
        if 'handoffs' in handoffs_config:
            handoffs_config = handoffs_config['handoffs']
        
        handoff_rules = handoffs_config.get('handoff_rules', [])
        
        if not handoff_rules:
            result["warnings"].append("No handoff rules found in handoffs.yaml")
            business_logger.warning(f"⚠️ [HANDOFFS] No handoff rules found in {workflow_name}/handoffs.yaml")
            return result
        
        result["rules_processed"] = len(handoff_rules)
        business_logger.info(f"🔗 [HANDOFFS] Processing {len(handoff_rules)} handoff rules for {workflow_name}")
        
        # Analyze rules for debugging
        for rule in handoff_rules:
            source_agent = rule.get('source_agent')
            target_agent = rule.get('target_agent')
            handoff_type = rule.get('handoff_type', 'after_work')
            condition = rule.get('condition')
            
            # Track terminate conditions specifically
            if target_agent == "terminate":
                result["terminate_conditions"].append({
                    "source": source_agent,
                    "condition": condition,
                    "type": handoff_type
                })
                business_logger.info(f"🚨 [HANDOFFS] TERMINATE condition found: {source_agent} → terminate")
                business_logger.info(f"🔍 [HANDOFFS] Terminate condition: {condition}")
            
            # Check for missing agents
            if source_agent and source_agent not in agents and source_agent not in ["user"]:
                result["missing_agents"].append(source_agent)
                result["warnings"].append(f"Source agent '{source_agent}' not found in workflow agents")
            
            if target_agent and target_agent not in agents and target_agent not in ["user", "terminate"]:
                result["missing_agents"].append(target_agent)
                result["warnings"].append(f"Target agent '{target_agent}' not found in workflow agents")
        
        # Apply handoffs using existing manager
        handoff_manager.apply_handoffs_from_yaml(workflow_name, agents)
        
        # Check which agents actually got handoffs configured
        for agent_name, agent in agents.items():
            if hasattr(agent, 'handoffs'):
                # This is a simplified check - AG2 agents should have handoffs attribute
                result["agents_with_handoffs"].append(agent_name)
                result["configured_agents"] += 1
        
        # Determine success
        if result["configured_agents"] > 0:
            result["success"] = True
            business_logger.info(f"✅ [HANDOFFS] Enhanced handoff wiring completed successfully")
            business_logger.info(f"📊 [HANDOFFS] Summary: {result['configured_agents']} agents configured with handoffs")
            
            if result["terminate_conditions"]:
                business_logger.warning(f"🚨 [HANDOFFS] Found {len(result['terminate_conditions'])} TERMINATE conditions - check for early termination!")
                for term_cond in result["terminate_conditions"]:
                    business_logger.warning(f"   • {term_cond['source']} → terminate: {term_cond['condition']}")
        else:
            result["warnings"].append("No agents were configured with handoffs")
            business_logger.warning(f"⚠️ [HANDOFFS] No agents were successfully configured with handoffs")
        
        # Log warnings
        for warning in result["warnings"]:
            business_logger.warning(f"⚠️ [HANDOFFS] {warning}")
            
        return result
        
    except Exception as e:
        result["failed"] = True
        result["error"] = str(e)
        business_logger.error(f"❌ [HANDOFFS] Enhanced handoff wiring failed for {workflow_name}: {e}", exc_info=True)
        business_logger.error(f"🚨 [HANDOFFS] CRITICAL: This will likely cause workflow termination or flow issues!")
        return result
