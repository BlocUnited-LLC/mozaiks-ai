"""
Add runtime system capabilities awareness to Generator agents.

Updates ActionPlanArchitect, ToolsManagerAgent, and AgentToolsFileGenerator
to reference the runtime system capabilities documentation and understand
what NOT to generate (image generation, code execution, web search, etc.)
"""

import json
import sys
from pathlib import Path

def load_agents():
    """Load Generator agents.json."""
    agents_path = Path("workflows/Generator/agents.json")
    with open(agents_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_agents(data):
    """Save Generator agents.json."""
    agents_path = Path("workflows/Generator/agents.json")
    with open(agents_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def update_actionplan_architect(agents_data):
    """Add runtime system awareness to ActionPlanArchitect."""
    agent = agents_data["agents"]["ActionPlanArchitect"]
    
    # Find position after PLATFORM-SPECIFIC INTEGRATION RULE section
    system_message = agent["system_message"]
    
    # Add new section after integration rule, before GUIDELINES
    runtime_section = """

[RUNTIME SYSTEM CAPABILITIES] (CRITICAL - UNDERSTAND PLATFORM FEATURES)
The MozaiksAI platform provides built-in capabilities that require NO tool generation or custom operations:

**AG2 Native Capabilities** (Enable via agent flags, NOT operations):
- **image_generation_enabled: true** → Agent describes images conversationally → AG2 generates via DALL-E automatically
  * DO NOT add operations like "generate_image", "generate_thumbnail", "create_visualization"
  * DO add operations for POST-PROCESSING: "save_thumbnail", "save_to_storage", "attach_to_document"
  * Pattern: Agent says "Generate a vibrant thumbnail..." → AG2 handles generation → Tool extracts and saves

- **code_execution_enabled: true** → Agent writes code → AG2 executes in sandboxed environment
  * DO NOT add operations like "execute_code", "run_python", "eval_javascript"
  * DO add operations for RESULT PROCESSING: "save_analysis", "cache_output", "export_dataset"

- **web_search_enabled: true** → Agent describes query → AG2 searches web → Returns results
  * DO NOT add operations like "search_web", "google_search", "find_information"
  * DO add operations for RESULT FILTERING: "filter_results", "save_findings", "extract_citations"

**Runtime System Features** (Built-in, NEVER generate tools for these):
- Agent handoffs and routing: Managed by handoffs.json expressions
- Human interaction checkpoints: Controlled by human_interaction field ("none", "context", "approval")
- Workflow lifecycle hooks: Defined in lifecycle_tools array (NOT agent tools)
- Conversation persistence and resume: Automatic via PersistenceManager
- Observability and logging: Automatic via AG2RuntimeLogger

**What TO Generate**:
1. Third-party API interactions: "send_slack_message", "create_hubspot_contact", "charge_mozaikspay_payment"
2. Domain-specific business logic: "calculate_tax", "validate_email", "format_invoice_pdf"
3. Data transformations: "parse_csv_upload", "merge_documents", "compile_report"
4. Post-processing AG2 capabilities: "save_thumbnail" (after image generation), "cache_analysis" (after code execution)
5. UI interactions for approval/input: Domain-specific preview/approval tools

**Decision Rule for Operations**:
- Is this an AG2 capability (image gen, code exec, search)? 
  → Set agent flag (image_generation_enabled: true), NO "generate" operation
  → Add POST-PROCESSING operations ONLY: "save_thumbnail", "cache_analysis"
- Is this runtime system feature (context, handoffs, persistence)? 
  → NO operations needed (runtime provides automatically)
- Is this domain logic or third-party API? 
  → Add to operations array (becomes tool via downstream ToolsManagerAgent)

**Your Role in the Generation Pipeline**:
You architect the Action Plan that defines which capabilities agents need and what operations they should perform. Downstream agents will implement your design by:
1. Mapping operations to tool manifest entries
2. Generating the actual tool code
3. Writing agent system messages that explain how to use the capabilities

YOUR DECISION: Set capability flags (image_generation_enabled, code_execution_enabled, etc.) and define operations correctly. If an agent needs image generation, set the flag to true and add POST-PROCESSING operations only (like "save_thumbnail"), NOT generation operations.
"""

    # Insert after the MozaiksPay integration rule, before the NEVER return multiple vendors line
    insert_marker = "- In descriptions, refer to it naturally as the payment or billing system (e.g., \"Processes customer payments securely through MozaiksPay\")."
    
    if insert_marker in system_message:
        system_message = system_message.replace(
            insert_marker,
            insert_marker + runtime_section
        )
        agent["system_message"] = system_message
        print("✓ Updated ActionPlanArchitect with runtime system awareness")
        return True
    else:
        print("✗ Could not find insertion point in ActionPlanArchitect")
        return False

def fix_toolsmanager_example(agents_data):
    """Fix ThumbnailAgent example in ToolsManagerAgent to use save_thumbnail instead of generate_thumbnail."""
    agent = agents_data["agents"]["ToolsManagerAgent"]
    system_message = agent["system_message"]
    
    # Replace the incorrect generate_thumbnail example
    old_example = '''{
      "agent": "ThumbnailAgent",
      "file": "generate_thumbnail.py",
      "function": "generate_thumbnail",
      "description": "Generate eye-catching thumbnail using AG2's multimodalilty capabilties",
      "tool_type": "Agent_Tool",
      "ui": null
    }'''
    
    new_example = '''{
      "agent": "ThumbnailAgent",
      "file": "save_thumbnail.py",
      "function": "save_thumbnail",
      "description": "Extract AG2-generated thumbnail from conversation and save to MongoDB",
      "tool_type": "Agent_Tool",
      "ui": null
    }'''
    
    if old_example in system_message:
        system_message = system_message.replace(old_example, new_example)
        agent["system_message"] = system_message
        print("✓ Fixed ToolsManagerAgent ThumbnailAgent example (generate_thumbnail → save_thumbnail)")
        return True
    else:
        print("✗ Could not find ThumbnailAgent example in ToolsManagerAgent")
        return False

def add_toolsmanager_runtime_awareness(agents_data):
    """Add runtime system capabilities awareness to ToolsManagerAgent."""
    agent = agents_data["agents"]["ToolsManagerAgent"]
    system_message = agent["system_message"]
    
    runtime_section = """

[RUNTIME SYSTEM CAPABILITIES AWARENESS] (CRITICAL - AVOID REDUNDANT TOOLS)
Before generating tools, check if the responsibility is already provided by the platform:

**AG2 NATIVE CAPABILITIES** (Set agent flags, DON'T generate tools):
- Image Generation (image_generation_enabled: true):
  * Agent describes image → AG2 generates via DALL-E conversationally
  * NEVER create: "generate_image", "generate_thumbnail", "create_visual"
  * DO create: "save_thumbnail", "save_to_storage" (post-processing tools that extract from conversation)
  * Tool pattern: `extract_images_from_conversation()` utility → save to MongoDB/storage

- Code Execution (code_execution_enabled: true):
  * Agent writes code → AG2 executes in sandbox
  * NEVER create: "execute_code", "run_python", "eval_script"
  * DO create: "process_results", "save_analysis", "cache_output"

- Web Search (web_search_enabled: true):
  * Agent describes query → AG2 searches web
  * NEVER create: "search_web", "google_search", "find_information"
  * DO create: "filter_results", "extract_citations", "save_findings"

**RUNTIME SYSTEM FEATURES** (Built-in, NEVER generate tools):
- Context variables: Platform provides via runtime['context_variables'] (get/set/remove methods)
- Agent routing: Managed by handoffs.json (NEVER create "route_to_agent" tools)
- Approval gates: Handled by human_interaction field (NEVER create generic "get_approval" tools)
- Persistence: Automatic conversation/state saving (NEVER create "save_state" tools)
- Logging: Automatic via AG2RuntimeLogger (NEVER create "log_event" tools)

**TOOL GENERATION DECISION TREE**:
1. Check upstream Action Plan agents for capability flags (image_generation_enabled, code_execution_enabled, etc.)
   → If flag is TRUE, SKIP any operations for generation (agent uses AG2 capability conversationally)
   → Only generate tools for POST-PROCESSING operations (save, extract, persist)
2. Check if operation is runtime system feature (set_context, route_agent, log_event, etc.)
   → If YES, SKIP tool generation (runtime provides these automatically)
3. Check if operation is third-party API interaction (send_slack_message, create_hubspot_contact)
   → If YES, generate Agent_Tool with API integration logic
4. Check if operation is domain-specific business logic (calculate_tax, validate_email)
   → If YES, generate Agent_Tool with calculation/validation/transformation logic
5. Check if operation is post-processing AG2 output (save_thumbnail, cache_analysis)
   → If YES, generate Agent_Tool that extracts from conversation and persists

**YOUR RESPONSIBILITY**: Map operations → tools (NOT write system messages, NOT write code, NOT decide what operations should exist)

You receive an operations list from the upstream Action Plan. Your job is ONLY to:
1. Check if operation is for AG2 generation (generate_image, execute_code) → SKIP (shouldn't exist in valid plan)
2. Check if operation is for runtime system (set_context, route_agent) → SKIP (shouldn't exist in valid plan)
3. For all valid operations → Create Agent_Tool manifest entry with correct naming

**NAMING PATTERN FOR POST-PROCESSING TOOLS**:
- AG2 generated images → "save_thumbnail", "save_to_storage", "attach_image"
- AG2 execution results → "cache_analysis", "save_output", "export_dataset"
- AG2 search results → "filter_results", "save_findings", "extract_citations"

If you see operations like "generate_thumbnail" or "set_context", the upstream plan has an error (SKIP these invalid operations).
"""

    # Insert before [CONTEXT VARIABLE COORDINATION] section
    insert_marker = "[CONTEXT VARIABLE COORDINATION]"
    
    if insert_marker in system_message:
        system_message = system_message.replace(
            insert_marker,
            runtime_section + "\n" + insert_marker
        )
        agent["system_message"] = system_message
        print("✓ Added runtime system awareness to ToolsManagerAgent")
        return True
    else:
        print("✗ Could not find insertion point in ToolsManagerAgent")
        return False

def add_agenttoolsfilegenerator_runtime_awareness(agents_data):
    """Add runtime system capabilities awareness to AgentToolsFileGenerator."""
    agent = agents_data["agents"]["AgentToolsFileGenerator"]
    system_message = agent["system_message"]
    
    runtime_section = """

[RUNTIME SYSTEM CAPABILITIES] (CRITICAL - UNDERSTAND PLATFORM UTILITIES)
The MozaiksAI platform provides built-in utilities for common patterns:

**AG2 Capability Post-Processing Utilities**:
- `extract_images_from_conversation(sender, recipient)` (from core.workflow.agents.factory):
  * Extracts PIL Image objects from AG2 conversation history (GPT-4V format)
  * Use when: Agent has image_generation_enabled=true and needs to save generated images
  * Pattern: Agent describes image → AG2 generates → Your tool extracts and saves
  * Returns: List[PIL.Image] or raises ValueError if no images found
  * Import: `from core.workflow.agents.factory import extract_images_from_conversation`

- Context Variables API (from runtime dict):
  * `runtime['context_variables'].get(key, default)` - Read variable
  * `runtime['context_variables'].set(key, value)` - Write variable
  * `runtime['context_variables'].remove(key)` - Delete variable
  * Use when: Tool needs to read workflow state or set completion flags

- WebSocket Chat ID (from runtime dict):
  * `runtime['chat_id']` - Current conversation ID
  * `runtime['workflow_name']` - Current workflow name
  * Use when: Tool needs to emit UI events or log messages

**TOOL IMPLEMENTATION PATTERNS**:

1. Image Generation Post-Processing (for agents with image_generation_enabled=true):
```python
from core.workflow.agents.factory import extract_images_from_conversation
from typing import Dict, Any

async def save_thumbnail(*, story_id: str, **runtime) -> Dict[str, Any]:
    # Extract images AG2 generated conversationally
    sender = runtime.get('sender')  # The agent that generated images
    recipient = runtime.get('recipient')  # The agent receiving images
    
    images = extract_images_from_conversation(sender, recipient)
    
    # Get most recent image
    thumbnail = images[-1]
    
    # Save to MongoDB/storage
    # ... storage logic ...
    
    return {'status': 'success', 'thumbnail_url': url}
```

2. Code Execution Post-Processing (for agents with code_execution_enabled=true):
```python
async def save_analysis(*, analysis_name: str, **runtime) -> Dict[str, Any]:
    # Code execution results are in conversation history
    # Extract and persist to storage
    # ... implementation ...
    return {'status': 'success', 'analysis_id': id}
```

3. Context Variable Integration (for workflow state management):
```python
async def compile_report(*, report_type: str, **runtime) -> Dict[str, Any]:
    # Read context
    context_vars = runtime.get('context_variables', {})
    data = context_vars.get('collected_data')
    
    if not data:
        raise ValueError('collected_data not found in context')
    
    # Process data
    report = generate_report(data, report_type)
    
    # Set completion flag
    if 'context_variables' in runtime:
        runtime['context_variables'].set('report_complete', True)
    
    return {'status': 'success', 'report': report}
```

**TOOL GENERATION DECISION** (Use these utilities when appropriate):
- Does the upstream Action Plan show an agent has image_generation_enabled=true?
  → Generate save/extract tools using extract_images_from_conversation utility (shown above)
  → DO NOT generate "generate_image" tools (AG2 handles generation)

- Does operation involve workflow state?
  → Use runtime['context_variables'] API (shown above in pattern 3)
  → DO NOT create custom state management tools

- Does operation need user interaction?
  → This is a UI_Tool (generated by another component, not you)

**YOUR RESPONSIBILITY**: Generate Python tool code using the patterns above. Tools must be production-ready with no placeholders.
"""

    # Insert before [OBJECTIVE] section
    insert_marker = "[OBJECTIVE]"
    
    if insert_marker in system_message:
        system_message = system_message.replace(
            insert_marker,
            runtime_section + "\n" + insert_marker
        )
        agent["system_message"] = system_message
        print("✓ Added runtime system awareness to AgentToolsFileGenerator")
        return True
    else:
        print("✗ Could not find insertion point in AgentToolsFileGenerator")
        return False

def main():
    """Main execution."""
    print("=== Adding Runtime System Capabilities Awareness ===\n")
    
    # Load agents
    print("Loading workflows/Generator/agents.json...")
    agents_data = load_agents()
    
    # Update agents
    success_count = 0
    
    if update_actionplan_architect(agents_data):
        success_count += 1
    
    if fix_toolsmanager_example(agents_data):
        success_count += 1
        
    if add_toolsmanager_runtime_awareness(agents_data):
        success_count += 1
        
    if add_agenttoolsfilegenerator_runtime_awareness(agents_data):
        success_count += 1
    
    # Save if any updates succeeded
    if success_count > 0:
        print(f"\nSaving updates ({success_count} changes)...")
        save_agents(agents_data)
        print("✓ Successfully updated workflows/Generator/agents.json")
    else:
        print("\n✗ No updates applied (all insertion points failed)")
        return 1
    
    print("\n=== Summary ===")
    print(f"✓ Created docs/RUNTIME_SYSTEM_CAPABILITIES.md (comprehensive capability catalog)")
    print(f"✓ Updated ActionPlanArchitect (runtime system capabilities section)")
    print(f"✓ Fixed ToolsManagerAgent example (generate_thumbnail → save_thumbnail)")
    print(f"✓ Updated ToolsManagerAgent (runtime awareness section)")
    print(f"✓ Updated AgentToolsFileGenerator (platform utilities section)")
    print("\nAll Generator agents now understand what NOT to generate!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
