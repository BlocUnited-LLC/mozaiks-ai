"""
phase_agents_plan tool - Called by WorkflowImplementationAgent to submit agent specs.

This tool receives phase_agents array from WorkflowImplementationAgent and forwards
it to action_plan tool which merges it with workflow_strategy from context.
"""

from typing import Dict, Any, List, Annotated, Optional
import logging
import sys
from pathlib import Path
import copy

# Add workflows/Generator/tools to path for absolute import
_tools_dir = Path(__file__).parent
if str(_tools_dir) not in sys.path:
    sys.path.insert(0, str(_tools_dir))

from action_plan import action_plan

_logger = logging.getLogger("tools.phase_agents_plan")

async def phase_agents_plan(
    *,
    phase_agents: Annotated[
        List[Dict[str, Any]],
        (
            "Array of agent specifications, one entry per phase from WorkflowStrategy. "
            "Each entry must have: phase_index (int, 0-based), agents (list of WorkflowAgent specs). "
            "Array length MUST match workflow_strategy.phases.length from context."
        )
    ],
    agent_message: Annotated[Optional[str], "Brief confirmation message (<=140 chars)"] = None,
    context_variables: Annotated[Optional[Any], "Context variables provided by AG2"] = None,
) -> Dict[str, Any]:
    """
    Submit agent specifications that will be merged with workflow_strategy phases.
    
    This tool:
    1. Receives phase_agents array from WorkflowImplementationAgent
    2. Reads workflow_strategy from context variables
    3. Merges them via action_plan tool
    4. Returns merged ActionPlan to UI
    
    Args:
        phase_agents: Array of {phase_index, agents[]} objects
        agent_message: Optional confirmation message
        context_variables: Runtime context with workflow_strategy
    
    Returns:
        Result from action_plan tool (merged workflow)
    """
    
    if not isinstance(phase_agents, list):
        _logger.error("phase_agents must be a list")
        return {"status": "error", "message": "phase_agents must be a list"}
    
    if len(phase_agents) == 0:
        _logger.error("phase_agents array is empty")
        return {"status": "error", "message": "phase_agents array cannot be empty"}
    
    _logger.info(
        "Received %d phase_agents entries from WorkflowImplementationAgent",
        len(phase_agents)
    )
    
    # Validate structure
    for idx, entry in enumerate(phase_agents):
        if not isinstance(entry, dict):
            _logger.error("phase_agents[%d] is not a dict", idx)
            return {"status": "error", "message": f"phase_agents[{idx}] must be a dict"}
        
        if "phase_index" not in entry:
            _logger.error("phase_agents[%d] missing phase_index field", idx)
            return {"status": "error", "message": f"phase_agents[{idx}] missing required field: phase_index"}
        
        if "agents" not in entry:
            _logger.error("phase_agents[%d] missing agents field", idx)
            return {"status": "error", "message": f"phase_agents[{idx}] missing required field: agents"}
        
        if not isinstance(entry["agents"], list):
            _logger.error("phase_agents[%d].agents is not a list", idx)
            return {"status": "error", "message": f"phase_agents[{idx}].agents must be a list"}
        
        if len(entry["agents"]) == 0:
            _logger.error("phase_agents[%d].agents is empty", idx)
            return {"status": "error", "message": f"phase_agents[{idx}].agents cannot be empty (at least 1 agent required per phase)"}
    
    sanitized_phase_agents: List[Dict[str, Any]] = []
    for entry in phase_agents:
        try:
            index = int(entry.get("phase_index", 0))
        except (TypeError, ValueError):
            _logger.debug(
                "Skipping phase_agents entry with non-integer phase_index: %s",
                entry.get("phase_index"),
            )
            continue

        agents_list = entry.get("agents", [])
        if isinstance(agents_list, list):
            sanitized_agents = [copy.deepcopy(agent) for agent in agents_list if isinstance(agent, dict)]
        else:
            sanitized_agents = []

        sanitized_phase_agents.append(
            {
                "phase_index": index,
                "agents": sanitized_agents,
            }
        )

    if context_variables and hasattr(context_variables, "set"):
        try:
            context_variables.set("workflow_phase_agents", sanitized_phase_agents)  # type: ignore[attr-defined]
            context_variables.set("phase_agents_ready", bool(sanitized_phase_agents))  # type: ignore[attr-defined]
            _logger.info("Cached %d phase_agents entries for downstream tools", len(sanitized_phase_agents))
        except Exception as ctx_err:
            _logger.debug("Failed to cache phase_agents in context variables: %s", ctx_err)

    # Forward to action_plan for merging
    _logger.info("Forwarding phase_agents to action_plan for merge with workflow_strategy")
    
    result = await action_plan(
        phase_agents=phase_agents,
        agent_message=agent_message,
        context_variables=context_variables
    )
    
    return result
