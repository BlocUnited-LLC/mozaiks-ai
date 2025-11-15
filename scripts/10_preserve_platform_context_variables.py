"""
Strategic update to WorkflowArchitectAgent: Add guidance to preserve platform context variables across workflow iterations.

PROBLEM:
- When user requests workflow modifications, WorkflowArchitectAgent creates fresh context variables
- Platform-level context (CONCEPT_OVERVIEW, MONETIZATION_ENABLED) gets dropped between iterations
- This breaks context-aware features and platform continuity

SOLUTION:
- Add explicit guidance to ALWAYS preserve platform context variables when CONTEXT_AWARE=true
- Ensure concept_overview and monetization_enabled appear in every workflow iteration
- Position this guidance at the start of "Decision Logic for Context Variables" section

APPROACH:
- Insert new bullet point at beginning of Decision Logic section
- Emphasize CRITICAL importance for platform context preservation
- Provide exact variable names, types, and purposes to use
"""

import json
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

AGENTS_JSON_PATH = Path("workflows/Generator/agents.json")


def update_workflow_architect_context_preservation():
    """Add platform context preservation guidance to WorkflowArchitectAgent."""
    
    if not AGENTS_JSON_PATH.exists():
        logger.error(f"agents.json not found at {AGENTS_JSON_PATH}")
        return False
    
    with open(AGENTS_JSON_PATH, 'r', encoding='utf-8') as f:
        agents_data = json.load(f)
    
    # Find WorkflowArchitectAgent
    agents = agents_data.get('agents', {})
    architect_agent = agents.get('WorkflowArchitectAgent')
    if not architect_agent:
        logger.error("WorkflowArchitectAgent not found in agents.json")
        return False
    
    # Find instructions section
    sections = architect_agent.get('prompt_sections', [])
    instructions_section = None
    for idx, section in enumerate(sections):
        if section.get('id') == 'instructions':
            instructions_section = section
            break
    
    if not instructions_section:
        logger.error("instructions section not found in WorkflowArchitectAgent")
        return False
    
    current_content = instructions_section.get('content', '')
    
    # Check if already updated
    if "CRITICAL - Preserve Platform Context" in current_content:
        logger.info("Platform context preservation guidance already exists, skipping update")
        return True
    
    # Find the Decision Logic for Context Variables section
    decision_logic_marker = "**Decision Logic for Context Variables**:\n"
    if decision_logic_marker not in current_content:
        logger.error("Could not find 'Decision Logic for Context Variables' marker")
        return False
    
    # Split at the marker and insert new guidance
    parts = current_content.split(decision_logic_marker, 1)
    if len(parts) != 2:
        logger.error("Failed to split content at Decision Logic marker")
        return False
    
    new_guidance = """**Decision Logic for Context Variables**:
- **CRITICAL - Preserve Platform Context**: If CONCEPT_OVERVIEW or MONETIZATION_ENABLED appear in runtime context variables (visible in agent messages):
  * ALWAYS include these as static variables in EVERY workflow iteration, even when user modifies the workflow
  * Required platform variables:
    - "concept_overview" (type="static", trigger_hint=null, purpose="Platform concept and vision that informs all content generation and feature development")
    - "monetization_enabled" (type="static", trigger_hint=null, purpose="Flag indicating whether monetization features are enabled for this platform")
  * These variables provide essential platform context that agents rely on across workflow revisions
  * Do NOT drop these variables when user requests workflow changes - they are platform-level, not workflow-specific
- **CRITICAL - Database Context Required**: If CONTEXT_INCLUDE_SCHEMA=true appears in runtime context (check for CONTEXT_AWARE flag in agent messages):
  * ALWAYS include at least ONE database variable to enable "Connected" status in UI
  * If workflow mentions user data, customer info, or platform entities, create appropriate database variables
  * Example database variables based on workflow domain:
    - For user-focused workflows: "user_profile" (type="database", trigger_hint=null, purpose="User account data and preferences from database")
    - For content workflows: "content_library" (type="database", trigger_hint=null, purpose="Existing content assets and templates from database")
    - For e-commerce: "product_catalog" (type="database", trigger_hint=null, purpose="Product inventory and pricing data from database")
  * Database variables signal to UI that database connection is configured and active
- """
    
    updated_content = parts[0] + new_guidance + parts[1]
    
    instructions_section['content'] = updated_content
    
    # Write back to file
    with open(AGENTS_JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump(agents_data, f, indent=2, ensure_ascii=False)
    
    logger.info("✅ Updated WorkflowArchitectAgent instructions section")
    logger.info("   - Added CRITICAL platform context preservation guidance")
    logger.info("   - Positioned at start of Decision Logic for Context Variables")
    logger.info("   - Ensures concept_overview and monetization_enabled persist across iterations")
    
    return True


if __name__ == "__main__":
    success = update_workflow_architect_context_preservation()
    if success:
        logger.info("\n✅ Script completed successfully")
    else:
        logger.error("\n❌ Script failed")
