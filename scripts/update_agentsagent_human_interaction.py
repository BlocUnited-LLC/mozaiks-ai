"""
Update AgentsAgent system message to include human_interaction alignment guidance.
"""
import json
from pathlib import Path

agents_json_path = Path("workflows/Generator/agents.json")

# Read the current agents.json
with open(agents_json_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

# Get the AgentsAgent system message
system_message = data['agents']['AgentsAgent']['system_message']

# Find Step 2 and replace through Step 4
step2_start = system_message.find("Step 2 - Gather Candidate Agents")
step5_start = system_message.find("Step 5 - Validate")

if step2_start == -1 or step5_start == -1:
    print("❌ Could not find Step 2 or Step 5 markers")
    exit(1)

# New content for Steps 2-4
new_steps = """Step 2 - Gather Candidate Agents
  - Extract agent names from Action Plan phases.agents lists
  - For EACH agent, extract the human_interaction field value ("none", "context", or "approval")
  - Cross-reference with Tool Registry for auto_tool_mode determination
  - Include Generator workflow meta-agents (ToolsManagerAgent, UIFileGenerator, etc.)
  
Step 3 - For Each Agent, Draft System Message
  a) Standard Sections: [ROLE], [OBJECTIVE], [CONTEXT], [GUIDELINES], [INSTRUCTIONS]
  b) Check trigger mapping from Step 1:
     - If agent has trigger requirements ΓåÆ add explicit output constraints in [GUIDELINES] or [INSTRUCTIONS]
     - Document exact trigger_value in [OUTPUT FORMAT] section
  c) For auto_tool_mode=true agents:
     - Cite React component path and Python tool path
     - Include agent_message requirement if UI tool needs user context
  d) For Agent_Tool owners:
     - Add precise tool call instructions in [INSTRUCTIONS]
  e) CRITICAL - Align agent system_message with human_interaction value from Action Plan:
     - human_interaction="context":
       * Agent MUST ask user for information, clarification, or preferences
       * Include conversational instructions: "Ask the user about...", "Collect details regarding..."
       * System message should emphasize dialogue and information gathering
       * Example role: "You are a requirements gathering agent responsible for collecting project scope from the user through natural dialogue."
     - human_interaction="approval":
       * Agent MUST present information/plan and wait for user approval/rejection
       * Include review instructions: "Present the [artifact] and ask the user to approve or request changes"
       * System message should emphasize review, presentation, and decision capture
       * Example role: "You are a review agent responsible for presenting the action plan and capturing user approval before execution."
     - human_interaction="none":
       * Agent executes autonomously with NO user interaction
       * Include execution instructions: "Process the data", "Generate the report", "Execute the workflow step"
       * System message should emphasize autonomous execution without pausing for input
       * Example role: "You are a data processing agent that transforms input data into structured reports autonomously."
  
Step 4 - Assign Configuration Flags
  - max_consecutive_auto_reply:
    * human_interaction="context": 2-3 (prioritize user engagement, avoid long autonomous turns)
    * human_interaction="approval": 3-4 (allow clarifications before final decision)
    * human_interaction="none": 4-7 based on task complexity (can operate autonomously longer)
  - auto_tool_mode: true if agent owns UI_Tool, false otherwise
  - structured_outputs_required: true if agent in structured outputs registry, false otherwise
  
"""

# Replace the section
new_system_message = system_message[:step2_start] + new_steps + system_message[step5_start:]

# Update the data
data['agents']['AgentsAgent']['system_message'] = new_system_message

# Write back
with open(agents_json_path, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print("✅ Successfully updated AgentsAgent system message")
print(f"   - Added human_interaction alignment guidance in Step 3e")
print(f"   - Updated max_consecutive_auto_reply guidelines in Step 4")
print(f"   - New system_message length: {len(new_system_message)} characters")
