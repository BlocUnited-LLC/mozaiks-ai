"""
Update ActionPlanArchitect system message to reinforce context + approval pattern.
Uses raw text replacement to avoid JSON parsing issues.
"""
from pathlib import Path

agents_path = Path(__file__).parent.parent / "workflows" / "Generator" / "agents.json"

# Read the file as raw text
with open(agents_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Define the old text to replace (using \\n for JSON-escaped newlines)
old_text = r"""**CRITICAL RULE - Approval Gates:**\nWhen a workflow collects user context AND will execute external actions, it MUST include BOTH:\n1. context agent(s) for gathering requirements/inputs\n2. approval agent(s) BEFORE executing those external actions\n\n**Rules by interaction_mode:**\n- autonomous \u2192 only \"none\" (no human interaction at any point)\n- checkpoint_approval \u2192 MUST include at least one \"approval\" agent\n- conversational \u2192 MUST include at least one \"context\" agent + MUST include \"approval\" agent IF workflow executes external actions\n\n**When approval is NOT required (rare exceptions):**\n- Pure informational workflows (chatbots, Q&A assistants, tutoring)\n- Guided input workflows (wizards, form builders) where user controls every step interactively"""

# Define the new text (using \\n for JSON-escaped newlines)
new_text = r"""**CRITICAL RULE - Context + Execution = Approval Required:**\n\n**95% of workflows follow this pattern: Context \u2192 Processing \u2192 Approval \u2192 Execution**\n\nIF a workflow collects user context (human_interaction: \"context\") AND will execute external actions, it MUST include BOTH:\n1. **context agent(s)** early in the plan for gathering requirements/inputs\n2. **approval agent(s)** BEFORE executing those external actions\n\n**Decision Framework - Does my workflow need approval?**\n\nAsk: \"Will this workflow execute actions with external consequences?\"\n- Send emails/messages \u2192 YES, need approval\n- Process payments/transactions \u2192 YES, need approval\n- Create/send documents \u2192 YES, need approval\n- Trigger third-party APIs \u2192 YES, need approval\n- Store data to external systems \u2192 YES, need approval\n- Only provide information/answers \u2192 NO, context only\n\n**Rules by interaction_mode:**\n- autonomous \u2192 only \"none\" (no human interaction at any point)\n- checkpoint_approval \u2192 MUST include at least one \"approval\" agent before execution\n- conversational \u2192 MUST include at least one \"context\" agent + MUST include \"approval\" agent BEFORE executing external actions\n\n**When approval is NOT required (rare exceptions - <5% of workflows):**\n- Pure informational workflows: chatbots, Q&A assistants, tutoring, search assistants\n  * Pattern: User asks \u2192 AI answers \u2192 User refines \u2192 AI answers (no external actions)\n  * Example: \"ChatGPT-style assistant providing information only\"\n- Guided input workflows: wizards, form builders where user controls every step interactively\n  * Pattern: User inputs data \u2192 System validates \u2192 User confirms \u2192 Repeat\n  * Example: \"Interactive form builder with real-time validation\""""

# Perform replacement
if old_text in content:
    content = content.replace(old_text, new_text)
    
    # Write back
    with open(agents_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("✅ Successfully updated ActionPlanArchitect system message")
    print("\nKey changes:")
    print("- Added explicit '95% of workflows' statistic")
    print("- Added decision framework: 'Does my workflow need approval?'")
    print("- Listed specific execution types requiring approval")
    print("- Emphasized rare exceptions are <5% of workflows")
    print("- Clarified pattern with examples")
else:
    print("❌ Could not find the exact text to replace.")
    print("The prompt may have already been updated or formatting has changed.")
