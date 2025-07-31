# ==============================================================================
# FILE: Generator/Handoffs.py
# DESCRIPTION: Modular handoff creation for AG2 Generator workflow
# SUPPORTS: Both manual configuration and structured output generation
# ==============================================================================
import logging
import time
import json
from typing import Dict, Any, List, TYPE_CHECKING, Optional
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

# Import enhanced logging
from logs.logging_config import (
    get_business_logger, 
    get_performance_logger,
    log_business_event,
    log_performance_metric
)

# Type imports
if TYPE_CHECKING:
    from .StructuredOutputs import HandoffsOutput, HandoffRule

# Get specialized loggers
business_logger = get_business_logger("generator_handoffs")
performance_logger = get_performance_logger("generator_handoffs")
logger = logging.getLogger(__name__)

class HandoffGenerator:
    """
    Generate AG2 handoffs from structured outputs.
    Provides consistency and validation while allowing agent-driven configuration.
    """
    
    def __init__(self):
        self.target_mapping = {
            "user": lambda: RevertToUserTarget(),
            "terminate": lambda: TerminateTarget(),
        }
    
    def generate_from_structured_output(self, handoffs_output: "HandoffsOutput", agents: Dict[str, Any]) -> None:
        """
        Generate handoffs from HandoffsAgent's structured output.
        
        Args:
            handoffs_output: Structured output from HandoffsAgent
            agents: Dictionary of agent instances
        """
        handoff_start = time.time()
        
        log_business_event(
            event_type="STRUCTURED_HANDOFF_GENERATION_STARTED",
            description="Starting handoff generation from structured outputs",
            context={
                "rules_count": len(handoffs_output.handoff_rules),
                "workflow_pattern": handoffs_output.workflow_pattern,
                "agent_count": len(agents)
            }
        )
        
        try:
            business_logger.info(f"🔗 [HANDOFFS] Generating from structured output - Pattern: {handoffs_output.workflow_pattern}")
            
            # Group rules by source agent for efficient processing
            agent_rules = {}
            for rule in handoffs_output.handoff_rules:
                if rule.source_agent not in agent_rules:
                    agent_rules[rule.source_agent] = {
                        "after_work": None,
                        "llm_conditions": [],
                        "context_conditions": []
                    }
                
                if rule.handoff_type == "after_work":
                    agent_rules[rule.source_agent]["after_work"] = rule
                elif rule.handoff_type == "llm_condition":
                    agent_rules[rule.source_agent]["llm_conditions"].append(rule)
                elif rule.handoff_type == "context_condition":
                    agent_rules[rule.source_agent]["context_conditions"].append(rule)
            
            # Apply handoffs to each agent
            for agent_name, rules in agent_rules.items():
                if agent_name not in agents:
                    business_logger.warning(f"⚠️ [HANDOFFS] Agent '{agent_name}' not found in agents dict")
                    continue
                
                agent = agents[agent_name]
                self._configure_agent_handoffs(agent, agent_name, rules, agents)
            
            total_time = (time.time() - handoff_start) * 1000
            
            log_performance_metric(
                metric_name="structured_handoff_generation_duration",
                value=total_time,
                unit="ms",
                context={
                    "rules_count": len(handoffs_output.handoff_rules),
                    "workflow_pattern": handoffs_output.workflow_pattern
                }
            )
            
            business_logger.info(f"🎉 [HANDOFFS] Structured handoff generation completed in {total_time:.1f}ms")
            
        except Exception as e:
            logger.error(f"❌ [HANDOFFS] Structured handoff generation failed: {e}", exc_info=True)
            log_business_event(
                event_type="STRUCTURED_HANDOFF_GENERATION_FAILED",
                description="Structured handoff generation failed",
                context={"error": str(e)},
                level="ERROR"
            )
            raise
    
    def _configure_agent_handoffs(self, agent: Any, agent_name: str, rules: Dict[str, Any], agents: Dict[str, Any]) -> None:
        """Configure handoffs for a single agent from rules"""
        
        # Set after-work behavior
        if rules["after_work"]:
            target = self._create_target(rules["after_work"], agents)
            agent.handoffs.set_after_work(target)
            business_logger.debug(f"🔗 [HANDOFFS] {agent_name} → {rules['after_work'].target_agent} (after work)")
        
        # Add LLM conditions
        if rules["llm_conditions"]:
            # Sort by priority (lower number = higher priority)
            sorted_conditions = sorted(rules["llm_conditions"], key=lambda r: r.priority)
            
            conditions = []
            for rule in sorted_conditions:
                target = self._create_target(rule, agents)
                condition = OnCondition(
                    target=target,
                    condition=StringLLMCondition(prompt=rule.condition)
                )
                conditions.append(condition)
                business_logger.debug(f"🔗 [HANDOFFS] {agent_name} → {rule.target_agent} (LLM: {rule.description})")
            
            agent.handoffs.add_llm_conditions(conditions)
        
        # Add context conditions
        if rules["context_conditions"]:
            for rule in rules["context_conditions"]:
                target = self._create_target(rule, agents)
                condition = OnContextCondition(
                    target=target,
                    condition=ExpressionContextCondition(
                        expression=ContextExpression(rule.context_expression)
                    )
                )
                agent.handoffs.add_context_condition(condition)
                business_logger.debug(f"🔗 [HANDOFFS] {agent_name} → {rule.target_agent} (Context: {rule.description})")
    
    def _create_target(self, rule: "HandoffRule", agents: Dict[str, Any]):
        """Create appropriate target from handoff rule"""
        target_agent = rule.target_agent
        
        # Special targets
        if target_agent in self.target_mapping:
            return self.target_mapping[target_agent]()
        
        # Agent targets
        if target_agent in agents:
            return AgentTarget(agents[target_agent])
        
        # Fallback: assume it's an agent name
        business_logger.warning(f"⚠️ [HANDOFFS] Target agent '{target_agent}' not found, using fallback")
        return RevertToUserTarget()

# Create global instance
handoff_generator = HandoffGenerator()

def wire_handoffs_from_structured_output(handoffs_output, agents: Dict[str, Any]) -> None:
    """
    Wire handoffs using structured output from HandoffsAgent.
    This is the recommended approach for consistency.
    
    Args:
        handoffs_output: HandoffsOutput from HandoffsAgent
        agents: Dictionary of agent instances
    """
    handoff_generator.generate_from_structured_output(handoffs_output, agents)

async def wire_handoffs(agents: Dict[str, Any]) -> None:
    """
    Core integration function called by groupchat_manager.py
    
    This function extracts HandoffsAgent's structured output and applies it to the agents.
    This is the entry point that the core system calls.
    
    Args:
        agents: Dictionary of agent instances from the workflow
    """
    try:
        business_logger.info(f"🔗 [HANDOFFS] Starting structured handoff integration...")
        
        # Check if HandoffsAgent exists and has generated output
        if "HandoffsAgent" not in agents:
            business_logger.warning(f"⚠️ [HANDOFFS] HandoffsAgent not found in agents dict - skipping handoffs")
            return
        
        handoffs_agent = agents["HandoffsAgent"]
        business_logger.info(f"🔗 [HANDOFFS] HandoffsAgent found - extracting structured output...")
        
        # Extract structured output from the HandoffsAgent
        # This implementation depends on how your agents store their outputs
        # For now, we'll implement a solution that checks the conversation history
        
        handoffs_output = await _extract_handoffs_output(handoffs_agent)
        
        if handoffs_output:
            business_logger.info(f"🔗 [HANDOFFS] Found structured output with {len(handoffs_output.handoff_rules)} rules")
            
            # Apply the structured handoffs to the agents
            wire_handoffs_from_structured_output(handoffs_output, agents)
            
            business_logger.info(f"✅ [HANDOFFS] Successfully applied structured handoffs")
        else:
            business_logger.warning(f"⚠️ [HANDOFFS] No structured output found from HandoffsAgent")
            business_logger.info(f"📝 [HANDOFFS] Agent may not have completed execution yet")
        
    except Exception as e:
        business_logger.error(f"❌ [HANDOFFS] Failed to wire handoffs: {e}", exc_info=True)
        # Don't raise - handoffs are optional and shouldn't break the workflow

async def _extract_handoffs_output(handoffs_agent: Any) -> Optional["HandoffsOutput"]:
    """
    Extract HandoffsOutput from the agent's conversation history
    
    This function searches the agent's last message or response for structured JSON output.
    
    Args:
        handoffs_agent: The HandoffsAgent instance
        
    Returns:
        HandoffsOutput if found, None otherwise
    """
    try:
        from .StructuredOutputs import HandoffsOutput
        
        business_logger.debug(f"🔍 [HANDOFFS] Extracting structured output from HandoffsAgent...")
        
        # Method 1: Check if the agent has a last_message attribute
        if hasattr(handoffs_agent, 'last_message') and handoffs_agent.last_message:
            content = handoffs_agent.last_message.get('content', '') if isinstance(handoffs_agent.last_message, dict) else str(handoffs_agent.last_message)
            output = _parse_json_from_content(content)
            if output:
                try:
                    return HandoffsOutput.model_validate(output)
                except Exception as e:
                    business_logger.warning(f"⚠️ [HANDOFFS] Failed to validate structured output from last_message: {e}")
        
        # Method 2: Check if the agent has a chat_messages attribute  
        if hasattr(handoffs_agent, 'chat_messages') and handoffs_agent.chat_messages:
            # Look through recent messages from this agent
            for message in reversed(handoffs_agent.chat_messages):
                if isinstance(message, dict) and message.get('name') == 'HandoffsAgent':
                    content = message.get('content', '')
                    output = _parse_json_from_content(content)
                    if output:
                        try:
                            return HandoffsOutput.model_validate(output)
                        except Exception as e:
                            business_logger.warning(f"⚠️ [HANDOFFS] Failed to validate structured output from chat_messages: {e}")
        
        # Method 3: Check if agent has a conversation attribute or similar
        for attr_name in ['conversation', '_conversation', 'messages', '_messages']:
            if hasattr(handoffs_agent, attr_name):
                messages = getattr(handoffs_agent, attr_name)
                if messages:
                    # Look for the last message from HandoffsAgent
                    for message in reversed(messages):
                        if isinstance(message, dict):
                            name = message.get('name', message.get('role', ''))
                            content = message.get('content', '')
                            if 'handoffs' in name.lower() and content:
                                output = _parse_json_from_content(content)
                                if output:
                                    try:
                                        return HandoffsOutput.model_validate(output)
                                    except Exception as e:
                                        business_logger.warning(f"⚠️ [HANDOFFS] Failed to validate structured output from {attr_name}: {e}")
        
        business_logger.info(f"📝 [HANDOFFS] No structured output found in agent's conversation history")
        business_logger.debug(f"🔍 [HANDOFFS] Agent attributes: {[attr for attr in dir(handoffs_agent) if not attr.startswith('_')]}")
        
        return None
        
    except Exception as e:
        business_logger.error(f"❌ [HANDOFFS] Failed to extract handoffs output: {e}")
        return None

def _parse_json_from_content(content: str) -> Optional[Dict[str, Any]]:
    """
    Parse JSON from agent message content, handling various formats
    
    With AG2 structured outputs, we expect clean JSON, but this handles edge cases.
    
    Args:
        content: The message content that may contain JSON
        
    Returns:
        Parsed JSON dict if found, None otherwise
    """
    try:
        if not content or not isinstance(content, str):
            return None
        
        # Method 1: Try parsing the entire content as JSON (AG2 structured output should be clean)
        try:
            parsed = json.loads(content.strip())
            # Validate it has the expected structure for handoffs
            if isinstance(parsed, dict) and "handoff_rules" in parsed:
                return parsed
        except:
            pass
        
        # Method 2: Look for JSON blocks in markdown code blocks (fallback for non-structured)
        import re
        
        # Find all JSON code blocks
        json_blocks = re.findall(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL | re.IGNORECASE)
        
        # Try each block and return the first valid handoffs structure
        for block in json_blocks:
            try:
                parsed = json.loads(block.strip())
                if isinstance(parsed, dict) and "handoff_rules" in parsed:
                    business_logger.debug(f"🔍 [HANDOFFS] Found valid handoffs JSON in code block")
                    return parsed
            except:
                continue
        
        # Method 3: Look for JSON objects that contain handoff_rules (more targeted)
        handoff_patterns = [
            r'\{[^{}]*"handoff_rules"[^{}]*\[[^\]]*\][^{}]*\}',  # Simple case
            r'\{(?:[^{}]|\{[^{}]*\})*"handoff_rules"(?:[^{}]|\{[^{}]*\})*\}',  # Nested case
        ]
        
        for pattern in handoff_patterns:
            matches = re.findall(pattern, content, re.DOTALL)
            for match in matches:
                try:
                    parsed = json.loads(match.strip())
                    if isinstance(parsed, dict) and "handoff_rules" in parsed:
                        business_logger.debug(f"🔍 [HANDOFFS] Found valid handoffs JSON via pattern matching")
                        return parsed
                except:
                    continue
        
        # Method 4: Extract JSON from mixed content (last resort)
        if '{' in content and '"handoff' in content:
            # Find the most complete JSON structure
            brace_count = 0
            start_pos = -1
            
            for i, char in enumerate(content):
                if char == '{':
                    if start_pos == -1:
                        start_pos = i
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0 and start_pos != -1:
                        # Found a complete JSON structure
                        candidate = content[start_pos:i+1]
                        try:
                            parsed = json.loads(candidate)
                            if isinstance(parsed, dict) and "handoff_rules" in parsed:
                                business_logger.debug(f"🔍 [HANDOFFS] Found valid handoffs JSON via brace matching")
                                return parsed
                        except:
                            pass
                        # Reset for next potential JSON
                        start_pos = -1
        
        business_logger.warning(f"⚠️ [HANDOFFS] No valid handoffs JSON found in content")
        return None
        
    except Exception as e:
        business_logger.debug(f"🔍 [HANDOFFS] JSON parsing failed: {e}")
        return None
