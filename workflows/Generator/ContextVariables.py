# ==============================================================================
# FILE: Generator/ContextVariables.py  
# DESCRIPTION: Simplified AG2-native context variables for Generator workflow
# ==============================================================================
from autogen.agentchat.group import ContextVariables
from typing import Dict, Any, Optional

def get_context(concept_data: Optional[Dict[str, Any]] = None) -> ContextVariables:
    """
    Create initial context variables for the Generator workflow.
    
    Context variables are simple key-value storage that all agents automatically receive.
    They are NOT tools - agents don't call functions to access them.
    """
    # Provide default concept overview if none exists
    if concept_data and 'ConceptOverview' in concept_data:
        overview = concept_data['ConceptOverview']
    else:
        overview = """
        Sample Project: AI-Powered Customer Support Dashboard
        
        Description: A web application that helps customer service teams manage and respond to customer inquiries more efficiently. The app currently includes basic ticket management, customer information display, and manual response templates.
        
        Current Features:
        - Ticket creation and tracking
        - Customer profile management  
        - Static response templates
        - Basic reporting dashboard
        
        Goals: Improve response times and accuracy while reducing manual workload for customer service representatives.
        """

    # Create context variables with concept overview
    context_vars = ContextVariables()
    
    # 1. CONCEPT OVERVIEW (core workflow input)
    context_vars.set("concept_overview", overview.strip())
    
    return context_vars
