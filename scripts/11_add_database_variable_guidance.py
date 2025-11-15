"""
Script 11: Add Database Variable Guidance to WorkflowArchitectAgent

PURPOSE:
- Update WorkflowArchitectAgent Decision Logic for Context Variables section
- Add guidance to check context_include_schema and create database-type variables
- Ensures UI connection status displays "Connected" when database access is enabled

APPROACH:
- Load agents.json
- Find WorkflowArchitectAgent instructions section
- Locate "Do NOT drop these variables when user requests workflow changes" marker
- Insert new database schema access guidance after platform context preservation
- Write back to file

RATIONALE:
- Agents now see context_include_schema and context_schema_db as context variables
- Need explicit guidance to create database-type variables when schema access is enabled
- UI connection status requires presence of database-type variables in workflow
"""

import json
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

def add_database_variable_guidance():
    """Add database variable creation guidance to WorkflowArchitectAgent"""
    
    agents_file = Path(__file__).parent.parent / "workflows" / "Generator" / "agents.json"
    
    if not agents_file.exists():
        logging.error(f"❌ File not found: {agents_file}")
        return False
    
    # Load agents.json
    with open(agents_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # Find WorkflowArchitectAgent
    agents_dict = data.get("agents", {})
    workflow_architect = agents_dict.get("WorkflowArchitectAgent")
    
    if not workflow_architect:
        logging.error("❌ WorkflowArchitectAgent not found in agents.json")
        return False
    
    # Find instructions section
    instructions_section = None
    for section in workflow_architect.get("prompt_sections", []):
        if section.get("id") == "instructions":
            instructions_section = section
            break
    
    if not instructions_section:
        logging.error("❌ Instructions section not found in WorkflowArchitectAgent")
        return False
    
    content = instructions_section.get("content", "")
    
    # Check if database guidance already exists
    if "Database Schema Access" in content:
        logging.info("ℹ️  Database variable guidance already present")
        return True
    
    # Find the insertion point (after platform context preservation)
    marker = "  * Do NOT drop these variables when user requests workflow changes - they are platform-level, not workflow-specific"
    
    if marker not in content:
        logging.error("❌ Platform context marker not found")
        return False
    
    # Database guidance to insert
    database_guidance = """
- **Database Schema Access**: If context_include_schema=true (visible in runtime context variables):
  * MUST create at least one database-type variable when workflow requires data persistence, retrieval, or user-specific data
  * Use context_schema_db value as the database_name in variable source configuration
  * Common database variable patterns:
    - User profiles: "user_profile" (collection="Users", search_by="user_id", field="profile_data")
    - Transaction history: "transaction_history" (collection="Transactions", search_by="user_id", field="history")
    - Workflow state: "workflow_state" (collection="WorkflowStates", search_by="chat_id", field="state_data")
    - Domain-specific data: Create variables matching interview requirements (e.g., "customer_tier", "order_status")
  * This ensures UI connection status displays "Connected" and agents can access schema_overview for accurate data modeling
  * If workflow is purely computational or stateless, database variables are optional even when schema access is enabled"""
    
    # Insert after marker, before the "- - Review" line
    # Replace "- - Review" with database guidance + "- Review"
    old_text = f"{marker}\n- - Review pattern guidance example for recommended context variables"
    new_text = f"{marker}\n{database_guidance}\n- Review pattern guidance example for recommended context variables"
    
    updated_content = content.replace(old_text, new_text)
    
    if updated_content == content:
        logging.error("❌ Failed to insert database guidance - text not found")
        logging.info(f"Looking for: {old_text[:100]}...")
        return False
    
    # Update the section
    instructions_section["content"] = updated_content
    
    # Write back to file
    with open(agents_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    logging.info("✅ Updated WorkflowArchitectAgent instructions section")
    logging.info("   - Added Database Schema Access guidance")
    logging.info("   - Positioned after platform context preservation")
    logging.info("   - Instructs agent to create database variables when context_include_schema=true")
    logging.info("   - Ensures UI connection status displays 'Connected' when database access enabled")
    
    return True

if __name__ == "__main__":
    success = add_database_variable_guidance()
    exit(0 if success else 1)
