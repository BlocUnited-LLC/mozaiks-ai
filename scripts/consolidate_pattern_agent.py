"""
Consolidate PatternAgent's extra sections into standard structure
"""
import json
from pathlib import Path

# Load
data = json.loads(Path('workflows/Generator/agents.json').read_text(encoding='utf-8'))
agent = data['agents']['PatternAgent']

# Extract content from sections to consolidate
sections_by_heading = {s['heading']: s for s in agent['prompt_sections']}

analysis_process = sections_by_heading.get('[ANALYSIS PROCESS]', {}).get('content', '')
critical_output = sections_by_heading.get('[CRITICAL OUTPUT COMPLIANCE]', {}).get('content', '')
important_notes = sections_by_heading.get('[IMPORTANT NOTES]', {}).get('content', '')

# Build new GUIDELINES (merge CRITICAL OUTPUT COMPLIANCE + IMPORTANT NOTES)
new_guidelines = f"""You must follow these guidelines strictly for legal reasons. Do not stray from them.

**Output Compliance**:
- Provide ONLY a valid JSON object matching the PatternSelectionCall schema
- No additional text, markdown, or commentary is allowed
- Required fields: selected_pattern (1-9), pattern_name
- Pattern Legend:
  * 1 = Context-Aware Routing
  * 2 = Escalation
  * 3 = Feedback Loop
  * 4 = Hierarchical
  * 5 = Organic
  * 6 = Pipeline
  * 7 = Redundant
  * 8 = Star
  * 9 = Triage with Tasks

**Analysis Guidelines**:
- Always analyze BOTH context_variables AND interview responses
- Consider workflow trigger type (chat_start, form_submit, schedule, etc.)
- Evaluate complexity and scale of the user's stated goal
- Look for keywords indicating pattern fit:
  * "review", "revise" → Feedback Loop
  * "stages", "sequential" → Pipeline
  * "routing", "classify" → Context-Aware Routing
  * "quality", "comparison" → Redundant
  * "tiers", "escalate" → Escalation
  * "coordinate", "specialists" → Star
  * "delegate", "managers" → Hierarchical
  * "tasks", "dependencies" → Triage with Tasks
  * "flexible", "exploratory" → Organic
- Default to simpler patterns (5, 6) when requirements are unclear or workflow is straightforward
- Use Hierarchical (4) or Redundant (7) only when complexity truly justifies the overhead
- Consider AG2 implementation complexity: Organic (simplest) → Pipeline → Context-Aware → Star → Escalation → Triage → Feedback Loop → Redundant → Hierarchical (most complex)

NOTE: Pattern-specific guidance (characteristics, flows, implementation details) will be automatically injected into downstream agents via update_agent_state hooks. Your job is ONLY to select the correct pattern ID and name."""

# Build new INSTRUCTIONS (merge ANALYSIS PROCESS + existing steps)
new_instructions = """**Step 1 - Extract Key Characteristics** from interview responses and context:
   - Workflow complexity (simple, moderate, complex)
   - Domain structure (single, multi-domain, hierarchical)
   - Execution requirements (sequential, nested, iterative)
   - Coordination needs (minimal, moderate, complex)
   - Quality requirements (single-pass, reviewed, verified)
   - Decision-making style (deterministic, adaptive, consensus)
   - Resource constraints (cost-sensitive, time-sensitive)
   - Task dependencies (independent, sequential, prerequisite chains)

**Step 2 - Map to Pattern Characteristics**:
   - Use [PATTERN SELECTION DECISION FRAMEWORK] to map extracted characteristics to pattern candidates
   - Score each pattern against the extracted characteristics
   - Match workflow requirements to pattern strengths
   - Identify primary and secondary pattern candidates
   - Consider pattern trade-offs (complexity vs flexibility, cost vs quality, determinism vs adaptability)

**Step 3 - Evaluate Pattern Fit**:
   - Choose the pattern with highest alignment score
   - Verify pattern addresses all critical requirements
   - Ensure pattern is implementable given constraints
   - Check for anti-patterns:
     * Using complex pattern (Hierarchical, Redundant, Feedback Loop) for simple single-domain workflow → downgrade to Pipeline or Organic
     * Using simple pattern (Organic, Pipeline) for complex multi-phase workflow with quality gates → upgrade to Feedback Loop or Hierarchical

**Step 4 - Output Pattern Selection**:
   - Format output as valid JSON matching PatternSelectionCall schema
   - Include selected_pattern (int 1-9) and pattern_name (string) from Pattern Legend
   - DO NOT include rationale, key_factors, or confidence fields in output (those are for your internal analysis only)
   - Output ONLY the JSON object with no markdown fences, no explanatory text, no additional commentary"""

# Build new sections list
new_sections = []

for section in agent['prompt_sections']:
    heading = section['heading']
    
    # Keep these as-is
    if heading in ['[ROLE]', '[OBJECTIVE]', '[CONTEXT]', 
                   '[AG2 PATTERN COOKBOOK - COMPREHENSIVE KNOWLEDGE BASE]',
                   '[PATTERN SELECTION DECISION FRAMEWORK]',
                   '[EXAMPLES]', '[JSON OUTPUT COMPLIANCE]', '[OUTPUT FORMAT]']:
        new_sections.append(section)
    
    # Replace GUIDELINES with consolidated version
    elif heading == '[GUIDELINES]':
        new_sections.append({
            'id': 'guidelines',
            'heading': '[GUIDELINES]',
            'content': new_guidelines
        })
    
    # Replace INSTRUCTIONS with consolidated version
    elif heading == '[INSTRUCTIONS]':
        new_sections.append({
            'id': 'instructions',
            'heading': '[INSTRUCTIONS]',
            'content': new_instructions
        })
    
    # Skip sections being consolidated
    elif heading in ['[ANALYSIS PROCESS]', '[CRITICAL OUTPUT COMPLIANCE]', '[IMPORTANT NOTES]']:
        print(f"Removing {heading} (consolidated into GUIDELINES/INSTRUCTIONS)")
        continue

# Update agent
agent['prompt_sections'] = new_sections
data['agents']['PatternAgent'] = agent

# Save
Path('workflows/Generator/agents.json').write_text(json.dumps(data, indent=2), encoding='utf-8')

print(f"\n✓ PatternAgent consolidated: {len(agent['prompt_sections'])} sections")
for i, s in enumerate(agent['prompt_sections'], 1):
    print(f"  {i}. {s['heading']}")
