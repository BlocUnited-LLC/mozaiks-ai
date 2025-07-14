# ==============================================================================
# FILE: Generator/ContextVariables.py
# DESCRIPTION: Context variable factory for AG2 groupchat workflows
# ==============================================================================
from autogen.agentchat.group import ContextVariables

def get_context(concept_data=None):
    """Create context variables using enterprise concept info (workflow-agnostic)"""
    
    # Extract concept overview
    overview = concept_data.get('ConceptOverview', '') if concept_data else ''

    return ContextVariables(data={
        # Concept context (workflow-specific)
        "concept_overview": overview,
    })