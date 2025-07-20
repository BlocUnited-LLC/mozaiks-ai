# ==============================================================================
# FILE: Generator/ContextVariables.py
# DESCRIPTION: AG2-native context variables for Generator workflow
# ==============================================================================
from autogen.agentchat.group import ContextVariables
from typing import Annotated, Dict, Any, Optional, List
import time

def get_context(concept_data: Optional[Dict[str, Any]] = None) -> ContextVariables:
    """Create initial context variables for the Generator workflow"""
    overview = concept_data.get('ConceptOverview', '') if concept_data else ''

    return ContextVariables(data={
        "concept_overview": overview,
        "ui_interactions": [],           # Track all UI component interactions
        "component_states": {},          # Current state of each component
        "user_preferences": {},          # User-set preferences and settings
        "session_metadata": {            # Session tracking
            "interaction_count": 0
        }
    })

# AG2 Tool: Update context from UI component actions
def update_context_from_ui(
    component_id: Annotated[str, "Unique identifier for the UI component"],
    action_type: Annotated[str, "Type of action performed (submit, download, etc.)"],
    action_data: Annotated[Dict[str, Any], "Data associated with the action"],
    context_variables: ContextVariables
) -> str:
    """
    AG2 tool to update ContextVariables when UI components send actions.
    This tool is called automatically by the transport layer when components
    send actions, providing agents with contextual awareness.
    """
    # Create interaction record
    interaction = {
        "timestamp": time.time(),
        "component_id": component_id,
        "action_type": action_type,
        "action_data": action_data
    }
    
    # Add to interaction history
    interactions = context_variables.get("ui_interactions") or []
    interactions.append(interaction)
    context_variables.set("ui_interactions", interactions)
    
    # Update component state
    component_states = context_variables.get("component_states") or {}
    component_states[component_id] = {
        "last_action": action_type,
        "last_action_time": time.time(),
        "action_data": action_data
    }
    context_variables.set("component_states", component_states)
    
    # Update session metadata
    session_meta = context_variables.get("session_metadata") or {}
    session_meta["interaction_count"] = len(interactions)
    context_variables.set("session_metadata", session_meta)
    
    return f"✅ Context updated: {component_id} performed {action_type}"

# AG2 Tool: Get current UI context summary
def get_ui_context_summary(context_variables: ContextVariables) -> str:
    """
    AG2 tool for agents to get a summary of current UI interactions and state.
    Agents can call this tool to understand what the user has been doing.
    """
    interactions = context_variables.get("ui_interactions") or []
    component_states = context_variables.get("component_states") or {}
    session_meta = context_variables.get("session_metadata") or {}
    
    if not interactions:
        return "No UI interactions yet."
    
    summary = f"UI Context Summary:\n"
    summary += f"- Total interactions: {session_meta.get('interaction_count', 0)}\n"
    summary += f"- Active components: {len(component_states)}\n"
    
    # Recent interactions
    recent = interactions[-3:] if len(interactions) > 3 else interactions
    summary += f"- Recent actions:\n"
    for interaction in recent:
        component_id = interaction['component_id']
        action_type = interaction['action_type']
        summary += f"  • {component_id}: {action_type}\n"
    
    return summary

# AG2 Tool: Check specific component state
def check_component_state(
    component_id: Annotated[str, "Component identifier to check"],
    context_variables: ContextVariables
) -> str:
    """
    AG2 tool for agents to check the current state of a specific UI component.
    """
    component_states = context_variables.get("component_states") or {}
    
    if component_id not in component_states:
        return f"Component '{component_id}' has not been interacted with yet."
    
    state = component_states[component_id]
    return f"Component '{component_id}' last action: {state['last_action']} with data: {state['action_data']}"
