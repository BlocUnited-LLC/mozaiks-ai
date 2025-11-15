# Agent Upstream Dependencies Matrix

## Completion Status

**Action Plan Agents (Foundation → Architecture)**: ✅ **5/5 COMPLETE**
- ✅ InterviewAgent (no dependencies - foundation)
- ✅ PatternAgent (no dependencies - foundation)  
- ✅ WorkflowStrategyAgent (pattern guidance injection)
- ✅ WorkflowArchitectAgent (WorkflowStrategy + PatternSelection field references)
- ✅ ProjectOverviewAgent (ActionPlan + PhaseAgents + TechnicalBlueprint)

**Implementation Agents (Spec-Dependent)**: ⚠️ **4/11 COMPLETE**
- ✅ WorkflowImplementationAgent (WorkflowStrategy + TechnicalBlueprint)
- ✅ ContextVariablesAgent (ActionPlan + PhaseAgents + ToolsManagerAgentOutput)
- ✅ ToolsManagerAgent (PhaseAgents + TechnicalBlueprint)
- ✅ UIFileGenerator (ToolsManagerAgentOutput + TechnicalBlueprint + StructuredOutputsRegistry)
- ⚠️ 7 agents pending (AgentTools, Coordination, Final)

---

## Generator Workflow Agents

### Tier 1 - Foundation Agents (No Dependencies)
1. **InterviewAgent**
   - Upstream: None (starts conversation)
   - Output: Interview responses

2. **PatternAgent**
   - Upstream: Interview responses, concept_overview (context vars)
   - Output: PatternSelection

---

### Tier 2 - Strategy Agents (Pattern-Dependent)
3. **WorkflowStrategyAgent** ✅ DONE (has pattern guidance injection)
   - Upstream: PatternSelection, Interview responses
   - Output: WorkflowStrategy (workflow_name, pattern, trigger, initiated_by, phases[])
   - Current: Pattern-specific guidance injected ✓

---

### Tier 3 - Architecture Agents (Strategy-Dependent)
4. **WorkflowArchitectAgent** ✅ DONE
   - Upstream: 
     * WorkflowStrategy (workflow_name, pattern, trigger, initiated_by, phases[])
     * PatternSelection (injected pattern guidance)
   - Output: TechnicalBlueprint (ui_components[], global_context_variables[], lifecycle hooks)
   - Current: Complete WorkflowStrategy + PatternSelection field references ✓

5. **WorkflowImplementationAgent** ✅ DONE
   - Upstream:
     * WorkflowStrategy (workflow_name, pattern, phases[])
     * TechnicalBlueprint (ui_components[])
   - Output: PhaseAgents (phase_agents[].agents[])
   - Current: Complete field references added ✓

---

### Tier 4 - Visualization & Context Agents (Multi-Dependency)
6. **ProjectOverviewAgent** ✅ DONE
   - Upstream:
     * ActionPlan (workflow-level + phases + agents)
     * PhaseAgents (detailed agent specs)
     * TechnicalBlueprint (ui_components[])
   - Output: MermaidSequenceDiagram
   - Current: Complete field references with all 3 sources ✓

7. **ContextVariablesAgent** ✅ DONE
   - Upstream:
     * ActionPlan (phases[], pattern[], trigger, initiated_by)
     * PhaseAgents (complete agent roster with tools)
     * ToolsManagerAgentOutput (tools[], lifecycle_tools[])
   - Output: ContextVariablesPlan
   - Current: Complete field references with all 4 sources ✓

---

### Tier 5 - Implementation Agents (Spec-Dependent)
8. **ToolsManagerAgent** ✅ DONE
   - Upstream:
     * PhaseAgents (phase_agents[].agents[].agent_tools[], lifecycle_tools[])
     * TechnicalBlueprint (ui_components[], before_chat_lifecycle, after_chat_lifecycle)
   - Output: ToolsManagerAgentOutput (tools[], lifecycle_tools[])
   - Current: Complete PhaseAgents + TechnicalBlueprint field references ✓

9. **UIFileGenerator** ⚠️ NEEDS REVIEW
   - Upstream:
     * ToolsManagerAgentOutput (tools[] filtered to UI_Tools)
     * TechnicalBlueprint (ui_components[] for component specs)
   - Output: UIFileGeneratorOutput (Python + React code)
   - TODO: Add complete upstream field references

10. **AgentToolsFileGenerator** ⚠️ NEEDS REVIEW
    - Upstream:
      * ToolsManagerAgentOutput (tools[] filtered to Agent_Tools)
      * PhaseAgents (for agent context and integration details)
    - Output: AgentToolsFileGeneratorOutput (Python code)
    - TODO: Add complete upstream field references

11. **HandoffsAgent** ⚠️ NEEDS REVIEW
    - Upstream:
      * PhaseAgents (complete agent roster, human_interaction types)
      * ContextVariablesPlan (derived variables with triggers)
      * ActionPlan (phases[], pattern for routing logic)
    - Output: HandoffRules
    - TODO: Add complete upstream field references

12. **StructuredOutputsAgent** ⚠️ NEEDS REVIEW
    - Upstream:
      * PhaseAgents (agents[] needing structured outputs)
      * ToolsManagerAgentOutput (tools[] that produce structured data)
    - Output: StructuredOutputsAgentOutput (Pydantic models, registry)
    - TODO: Add complete upstream field references

13. **AgentsAgent** ⚠️ NEEDS REVIEW
    - Upstream:
      * PhaseAgents (complete agent specifications)
      * StructuredOutputsAgentOutput (model registry)
      * ToolsManagerAgentOutput (tools[] ownership)
    - Output: RuntimeAgentsCall (runtime agent configs)
    - TODO: Add complete upstream field references

14. **HookAgent** ⚠️ NEEDS REVIEW
    - Upstream:
      * PhaseAgents (agents[] with system_hooks[])
      * TechnicalBlueprint (lifecycle hooks)
    - Output: HookImplementationCall (hook code)
    - TODO: Add complete upstream field references

15. **OrchestratorAgent** ⚠️ NEEDS REVIEW
    - Upstream:
      * ActionPlan (workflow_name, pattern)
      * PhaseAgents (visual_agents list)
      * PatternSelection (orchestration_pattern)
    - Output: OrchestratorAgentOutput (startup config)
    - TODO: Add complete upstream field references

16. **DownloadAgent** ⚠️ NEEDS REVIEW
    - Upstream:
      * All previous outputs (for packaging)
    - Output: DownloadRequestCall
    - TODO: Add complete upstream field references

---

## Recommended Execution Order

### Batch 1: Architecture Agents (1 agent)
- WorkflowArchitectAgent (add WorkflowStrategy reference)

### Batch 2: Tool Agents (3 agents)
- ToolsManagerAgent (add PhaseAgents + TechnicalBlueprint)
- UIFileGenerator (add ToolsManagerAgentOutput + TechnicalBlueprint)
- AgentToolsFileGenerator (add ToolsManagerAgentOutput + PhaseAgents)

### Batch 3: Coordination Agents (2 agents)
- HandoffsAgent (add PhaseAgents + ContextVariablesPlan + ActionPlan)
- StructuredOutputsAgent (add PhaseAgents + ToolsManagerAgentOutput)

### Batch 4: Final Agents (3 agents)
- AgentsAgent (add PhaseAgents + StructuredOutputsAgentOutput + ToolsManagerAgentOutput)
- HookAgent (add PhaseAgents + TechnicalBlueprint)
- OrchestratorAgent (add ActionPlan + PhaseAgents + PatternSelection)
- DownloadAgent (add references to all previous outputs)

---

## Common Patterns to Apply

For each agent, add to CONTEXT section:

```
**UPSTREAM OUTPUT EXTRACTION INSTRUCTIONS**:

1. **[UpstreamSource1]** (Semantic wrapper: 'key' → 'path'):
   - **How to access**: [Navigation instructions]
   - **[Section]** fields:
     * field_name (type): Description - usage notes
     * field_name2 (type): Description - usage notes
   - **Use for**:
     * [Specific use case 1]
     * [Specific use case 2]

2. **[UpstreamSource2]** ...

**CRITICAL EXTRACTION PATTERNS**:
- **For [use case]**: [Extraction pattern]
- **For [use case]**: [Extraction pattern]

**VALIDATION CHECKS**:
- ✓ [Check 1]
- ✓ [Check 2]
```

Add to INSTRUCTIONS section:

```
**Step 1 - Extract [UpstreamSource1] from Conversation History**:
- Scan conversation history for message containing '[Wrapper]' semantic wrapper
- Navigate to: message.content['[Wrapper]']['[Path]']
- Extract [field category] fields:
  * field_name → [How to use in this agent's output]
  * field_name2 → [How to use in this agent's output]
- **Purpose**: [Why this extraction matters]
- **Critical**: [Any validation or cross-referencing needed]

**Step 2 - Extract [UpstreamSource2]** ...
```
