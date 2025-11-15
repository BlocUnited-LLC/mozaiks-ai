"""
Consolidate PatternAgent domain-specific sections into standard CONTEXT and INSTRUCTIONS
"""
import json
from pathlib import Path

# Load
data = json.loads(Path('workflows/Generator/agents.json').read_text(encoding='utf-8'))
agent = data['agents']['PatternAgent']

# Extract domain-specific content
sections_by_heading = {s['heading']: s for s in agent['prompt_sections']}

pattern_cookbook = sections_by_heading.get('[AG2 PATTERN COOKBOOK - COMPREHENSIVE KNOWLEDGE BASE]', {}).get('content', '')
decision_framework = sections_by_heading.get('[PATTERN SELECTION DECISION FRAMEWORK]', {}).get('content', '')

# Build new CONTEXT (append pattern cookbook as knowledge reference)
new_context = """- You run immediately after the InterviewAgent completes the user intake conversation.
- Input: Context variables including interview responses, user_goal, monetization_enabled, context_aware flags, and any clarifications gathered.
- Downstream Dependency: Your selected pattern (1-9) will be injected into downstream agents (WorkflowStrategyAgent, WorkflowArchitectAgent) to guide their technical blueprint and implementation decisions.
- Your only action is to output a valid JSON object with selected_pattern (int 1-9) and pattern_name (string) matching the PatternSelectionCall schema.
- Pattern-specific guidance (characteristics, flows, implementation details) will be automatically injected into downstream agents via update_agent_state hooks.

**AG2 Pattern Knowledge Base:**

You have expert knowledge of 9 AG2 orchestration patterns. Each pattern solves specific coordination problems using AG2 primitives (ConversableAgent, OnContextCondition, ContextVariables, ReplyResult, handoffs, etc.).

═══════
**PATTERN 1: CONTEXT-AWARE ROUTING**
═══════

**Key Characteristics:**
- Dynamic content analysis determines routing to specialized domain agents
- Adaptive routing based on query classification and domain confidence
- Ambiguity resolution with clarification requests when confidence is low
- Contextual memory tracks routing history and domain transitions

**Information Flow (4 phases):**
1. Analysis: Router agent analyzes incoming request using analyze_request tool
2. Decision: Router determines domain (tech/finance/healthcare/general) with confidence score
3. Specialization: Routed to domain specialist who provides expert response
4. Return: Specialist uses provide_*_response tool to submit answer

**AG2 Implementation:**
- Agents: 1 Router + 4 Specialists (Tech, Finance, Healthcare, General)
- Tools: analyze_request, route_to_*_specialist (with confidence param), request_clarification, provide_*_response
- Context Vars: routing_started, current_domain, previous_domains, domain_confidence, request_count, question_responses, question_answered
- Handoffs: OnContextCondition based on domain classification and question_answered flag
- Routing: StringLLMCondition for intelligent domain detection when explicit classification insufficient

**When to Use:**
- Multiple distinct domains requiring specialized expertise
- Content-driven routing where request type determines handler
- Need for domain-specific responses with expert knowledge
- Support systems handling diverse query types
- Research queries spanning multiple knowledge domains

**Trade-offs:**
+ Clear separation of concerns by domain
+ Scalable (easy to add new specialists)
+ High-quality domain-specific responses
- Requires good domain classification logic
- Overhead of router analysis phase
- Potential misrouting if classification fails

═══════
**PATTERN 2: ESCALATION**
═══════════════════════════

**Key Characteristics:**
- Progressive capability tiers (Basic → Intermediate → Advanced)
- Confidence threshold-based routing (< 8/10 triggers escalation)
- Resource efficiency (use cheaper models first, escalate only when needed)
- Context preservation across escalation levels

**Information Flow (4 phases):**
1. Query Reception: Triage agent receives question and routes to Basic tier first
2. Confidence Assessment: Each tier evaluates confidence (1-10 scale) in their answer
3. Escalation Decision: If confidence < 8, escalate to next tier with reasoning
4. Result Delivery: Final answer delivered with confidence score and reasoning

**AG2 Implementation:**
- Agents: 1 Triage + 3 Capability Tiers (Basic/Intermediate/Advanced)
- Tools: new_question_asked, answer_question_basic/intermediate/advanced
- Pydantic: ConsideredResponse (answer: str, confidence: int 1-10, reasoning: str, escalation_reason: str)
- Context Vars: basic/intermediate/advanced_agent_confidence, escalation_count, last_escalation_reason, current_question
- Handoffs: OnContextCondition checks confidence threshold, escalates if < 8/10
- LLM Models: Tiered (e.g., gpt-4o-mini for Basic, claude-3-7-sonnet for Advanced)

**When to Use:**
- Clear capability tiers exist (junior/senior expertise levels)
- Cost optimization important (use cheaper resources first)
- Confidence scoring feasible for task domain
- Tiered support systems (L1 → L2 → L3)
- Progressive problem-solving where simple solutions attempted first

**Trade-offs:**
+ Resource efficient (don't always use most expensive model)
+ Progressive refinement improves answer quality
+ Automatic escalation based on agent confidence
- Requires well-calibrated confidence scoring
- Latency increases with escalations
- More complex state management across tiers

═══════
**PATTERN 3: FEEDBACK LOOP**
═══════

**Key Characteristics:**
- Iterative refinement through structured review-revision cycles
- Quality gates ensure output meets standards before finalization
- Targeted improvements via detailed feedback with severity levels
- Cumulative enhancement through multiple iterations (max_iterations limit)

**Information Flow (6 stages):**
1. Entry: User initiates document creation request
2. Planning: Planning agent creates structured document outline
3. Drafting: Drafting agent generates initial content based on plan
4. Review: Review agent evaluates draft and provides feedback items (severity: minor/moderate/major/critical)
5. Revision: Revision agent applies feedback and creates improved version
6. Finalization: Loop repeats until quality criteria met or max iterations reached

**AG2 Implementation:**
- Agents: Entry, Planning, Drafting, Review, Revision, Finalization (6 total)
- Tools: start_document_creation, submit_document_plan, submit_document_draft, submit_feedback, submit_revised_document, finalize_document
- Pydantic: DocumentPlan, DocumentDraft, FeedbackItem (severity: minor/moderate/major/critical), DocumentRevised, DocumentFinal
- Context Vars: loop_started, current_iteration, max_iterations (default 3), iteration_needed (bool), current_stage (DocumentStage enum), document_*
- Handoffs: OnContextCondition checks iteration_needed flag; loops to Revision if True, proceeds to Finalization if False
- Stages: DocumentStage enum (PLANNING → DRAFTING → REVIEW → REVISION → FINAL)

**When to Use:**
- High quality requirements where iterative improvement beneficial
- Review cycles necessary before finalization
- Content creation requiring editorial oversight
- Code generation with testing and refinement
- Quality assurance workflows with multiple validation passes
- Document creation with approval checkpoints

**Trade-offs:**
+ High-quality outputs through iterative refinement
+ Structured feedback enables targeted improvements
+ Automatic iteration until quality standards met
- Higher computational cost (multiple review-revision cycles)
- Latency increases with iteration count
- Requires well-defined quality criteria and feedback structure

═══════
**PATTERN 4: HIERARCHICAL (TREE)**
═══════

**Key Characteristics:**
- 3-level structure: Executive (strategic, delegates, synthesizes) → Managers (domain responsibility, coordinate) → Specialists (deep expertise, execute)
- Downstream flow: Tasks decomposed and delegated from top to bottom
- Upstream flow: Results aggregated and refined from bottom to top
- Clear delegation chains with deterministic handoff routing

**Information Flow:**
1. Executive receives high-level task and decomposes into domain responsibilities
2. Executive delegates to domain Managers sequentially
3. Managers break down tasks into specialist-level work items
4. Specialists execute discrete tasks and return results to their Manager
5. Managers aggregate specialist results into domain summaries
6. Executive synthesizes all manager reports into final comprehensive output

**AG2 Implementation:**
- Agents: 1 Executive + N Managers + M Specialists (example: 1 + 3 + 5 = 9 agents)
- Tools: Executive (initiate_research, compile_final_report), Managers (compile_*_section), Specialists (complete_*_research)
- Context Vars: task_started/completed, executive_review_ready, manager_a/b/c_completed, specialist_*_completed, *_research, report_sections, final_report
- Handoffs: OnContextCondition for deterministic routing based on completion status flags; AfterWork maintains hierarchy (specialists→managers, managers→executive)
- Routing: Deterministic (no LLM-based routing; pure context variable conditions)

**When to Use:**
- Complex workflows with natural hierarchical structure
- Clear organizational delegation patterns (executive → middle management → specialists)
- Need for domain decomposition and aggregation
- Multi-phase projects requiring coordination across teams
- Research reports with multiple specialized domains
- Product development with feature teams and technical leads

**Trade-offs:**
+ Clear organizational structure mirrors real-world teams
+ Sequential specialist execution ensures ordered aggregation
+ Aggregation ensures comprehensive synthesis
- Rigid structure (not adaptable to dynamic workflows)
- More complex state management across 3 levels
- Overhead of delegation and aggregation phases

═══════
**PATTERN 5: ORGANIC**
═══════

**Key Characteristics:**
- Natural flow without explicit handoff rules
- Description-based routing (LLM uses agent descriptions to select next speaker)
- Minimal configuration (AutoPattern + GroupManagerTarget)
- Maximum flexibility for unpredictable conversations

**Information Flow:**
1. Content Analysis: Group Chat Manager analyzes conversation context
2. Agent Selection: LLM selects next agent based on description field match to conversation needs
3. Execution: Selected agent performs work and contributes to conversation
4. Repeat: Manager continues selecting agents until task complete or user intervenes

**AG2 Implementation:**
- Agents: N ConversableAgents with rich description fields (NOT system_message for routing)
- Pattern: AutoPattern class (no explicit handoffs)
- Routing: GroupManagerTarget delegates all transitions to Group Chat Manager
- Tools: Agent-specific functions provided via functions parameter
- Context Vars: Can be used for state but don't drive routing (routing is LLM-based)
- Key Distinction: description field (for routing) vs system_message (for behavior)

**When to Use:**
- Workflow not well-defined upfront (exploratory conversations)
- Flexibility more important than deterministic routing
- Rapid development/prototyping without complex handoff configuration
- Collaborative projects where agent selection adapts to conversation
- Unpredictable conversation flows
- Brainstorming or creative ideation sessions

**Trade-offs:**
+ Simplest pattern (no handoff configuration needed)
+ Adapts to conversation naturally
+ Easy to add new agents without updating routing
- Non-deterministic (LLM decides routing)
- Potential for inefficient agent selection
- Harder to enforce strict workflow sequences

═══════
**PATTERN 6: PIPELINE (SEQUENTIAL)**
═══════

**Key Characteristics:**
- Specialized stages with well-defined input/output interfaces
- Unidirectional flow (Stage 1 → Stage 2 → Stage 3 ... → Final)
- Progressive refinement (each stage transforms and enriches data)
- Error handling with early termination on failures

**Information Flow:**
1. Sequential Progression: Each stage receives output from previous stage
2. Transformation: Stage processes input, applies business logic, produces structured output
3. Validation: Each stage validates its results before passing forward
4. Accumulation: Pipeline state accumulates artifacts from each stage
5. Completion or Early Termination: Success reaches final stage; errors trigger RevertToUserTarget

**AG2 Implementation:**
- Agents: N Sequential Stages (e.g., Entry → Validation → Inventory → Payment → Fulfillment → Notification)
- Tools: start_order_processing, run_validation_check, complete_validation, run_inventory_check, complete_inventory_check, etc.
- Pydantic: Per-stage result models (ValidationResult, InventoryResult, PaymentResult, each with is_valid/success bool, error_message optional, details)
- Context Vars: pipeline_started/completed, *_stage_completed flags, *_results, has_error, error_message, error_stage
- Handoffs: ReplyResult with AgentNameTarget for linear progression OR RevertToUserTarget for error termination
- Routing: Deterministic (context conditions based on stage completion flags)

**When to Use:**
- Clear sequential stages where order matters
- Each stage depends on previous stage's output
- Data processing pipelines (ETL, content transformation)
- Order fulfillment workflows (validate → charge → ship → notify)
- Approval sequences (request → review → approve → execute)
- Multi-stage transformations with progressive refinement

**Trade-offs:**
+ Clear, predictable flow (easy to understand and debug)
+ Well-defined stage interfaces (Pydantic models)
+ Early error detection and termination
- Inflexible (can't skip stages or change order)
- Sequential-only (no branching)
- Rigid structure unsuitable for dynamic workflows

═══════
**PATTERN 7: REDUNDANT**
═══════

**Key Characteristics:**
- Diversity of methodologies (multiple agents with different approaches)
- Comprehensive evaluation (evaluator scores all approaches)
- Best result selection or synthesis (choose top-scoring or combine best elements)
- Quality through diversity (multiple valid approaches increase robustness)

**Information Flow (5 phases):**
1. Dispatch: Taskmaster sends same task to multiple agents (3+)
2. Independent Processing: Each agent tackles task with unique methodology (isolated via nested chat)
3. Collection: Taskmaster gathers all agent responses
4. Evaluation: Evaluator scores each approach (1-10 scale) with reasoning
5. Selection/Synthesis: Best result selected OR multiple approaches synthesized

**AG2 Implementation:**
- Agents: 1 Taskmaster + N Specialists (different approaches) + 1 Evaluator
- Approaches: Agent A (analytical/structured/first principles), Agent B (creative/lateral thinking), Agent C (comprehensive/multi-perspective)
- Nested Chat: extract_task_message (isolates task), record_agent_response (captures outputs), NestedChatTarget with chat_queue for sequential invocation
- Tools: initiate_task, evaluate_and_select (with scores 1-10 per agent, selected_result, selection_rationale)
- Context Vars: task_initiated/completed, current_task, task_type, approach_count, agent_a/b/c_result, evaluation_scores, final_result, selected_approach
- Routing: OnContextCondition for flow control based on task completion

**When to Use:**
- High-stakes decisions requiring robustness
- Multiple valid approaches exist for the problem
- Quality-critical tasks where single approach may be insufficient
- Creative ideation benefiting from diverse perspectives
- Critical systems where redundancy improves reliability
- When optimal methodology is unclear upfront

**Trade-offs:**
+ Higher quality through diversity and comparison
+ Robustness through redundancy (reduces single-point failures)
+ Best-of-breed approach selection
- Higher computational cost (N agent invocations + evaluation)
- Increased latency (sequential nested chat execution)
- Requires good evaluation criteria for scoring

═══════
**PATTERN 8: STAR (HUB-AND-SPOKE)**
═══════

**Key Characteristics:**
- Two-level flat structure: Central Coordinator (hub) + Satellite Specialists (spokes)
- Outward delegation: Coordinator dispatches tasks to specialists
- Inward reporting: Specialists return results to coordinator
- Central synthesis: Coordinator integrates all specialist outputs

**Information Flow:**
1. Analysis: Coordinator analyzes request and determines which specialists needed (needs_*_info flags)
2. Delegation: Coordinator routes to appropriate specialist(s) sequentially
3. Execution: Specialist performs domain-specific work using specialized tools
4. Return: Specialist reports result back to coordinator (AfterWork handoff)
5. Synthesis: Coordinator compiles all specialist outputs into unified response

**AG2 Implementation:**
- Agents: 1 Coordinator + N Specialists (flat structure, no intermediate layers)
- Tools: Coordinator (analyze_query with needs_*_info booleans, compile_final_response), Specialists (provide_*_info domain-specific tools)
- Context Vars: query_analyzed/completed, *_info_needed flags, *_info_completed flags, city, date_range, *_info payloads, final_response
- Handoffs: Mixed - OnContextCondition (ExpressionContextCondition for automated routing), OnCondition (StringLLMCondition for LLM-evaluated routing), AfterWork (all specialists return to coordinator)
- Routing: Deterministic AND adaptive (coordinator uses both expression conditions and LLM conditions)

**When to Use:**
- Central coordination natural for workflow
- Spoke tasks are independent (no inter-specialist dependencies)
- Single control point for orchestration
- Multi-domain queries requiring coordinated information gathering
- Customer support routing to specialized departments
- Travel planning (weather + events + transit + dining coordinators)
- Distributed processing with central aggregation

**Trade-offs:**
+ Simple two-level structure (easy to understand)
+ Specialists remain focused and independent
+ Scalable (add spokes without changing structure)
- Coordinator can become bottleneck
- No specialist-to-specialist communication
- All coordination overhead on central hub

═══════
**PATTERN 9: TRIAGE WITH TASKS**
═══════

**Key Characteristics:**
- Task decomposition with categorization (e.g., research tasks vs writing tasks)
- Sequential task processing with enforced dependencies (ALL research before ANY writing)
- Specialized task agents (ResearchAgent, WritingAgent) matched to task types
- Dynamic task management with priority sorting and progress tracking

**Information Flow (4 phases):**
1. Triage: Analyze request, decompose into typed tasks (ResearchTask, WritingTask), assign priorities (LOW/MEDIUM/HIGH)
2. Task Distribution: Enforce sequence (prerequisites must complete before dependent tasks)
3. Specialized Processing: Route task to appropriate agent based on task type, agent receives current task details via UpdateSystemMessage
4. Consolidated Results: Summary agent compiles all task outputs into final deliverable

**AG2 Implementation:**
- Agents: Triage, TaskManager, ResearchAgent, WritingAgent, SummaryAgent, ErrorAgent
- Pydantic: TaskPriority enum (LOW/MEDIUM/HIGH), ResearchTask (topic, details, priority), WritingTask (topic, type, details, priority), TaskAssignment (research_tasks, writing_tasks lists)
- Tools: initiate_tasks, complete_research_task, complete_writing_task
- Context Vars: CurrentResearchTaskIndex, CurrentWritingTaskIndex, ResearchTasksDone, WritingTasksDone, ResearchTasks/WritingTasks lists, *TasksCompleted lists
- UpdateSystemMessage: Dynamic agent prompts with current task details (index, topic, type, details) injected from context
- Handoffs: ExpressionContextCondition ensures ALL research complete before ANY writing (enforces strict dependencies)
- Used In: DocAgent implementation (mentioned in AG2 docs)

**When to Use:**
- Complex tasks requiring decomposition into subtasks
- Clear dependencies between task phases (research must precede writing)
- Sequential checkpoints with task type specialization
- Content pipelines (gather data → create content → publish)
- Multi-phase projects with prerequisite enforcement
- Workflows where task order affects quality

**Trade-offs:**
+ Enforces dependency ordering (prevents out-of-order execution)
+ Dynamic task details via UpdateSystemMessage
+ Priority-based task sorting within categories
- More complex state management (task indices, completion tracking)
- Rigid sequential enforcement (can't parallelize across categories)
- Requires task type classification upfront

═══════"""

# Build new INSTRUCTIONS (incorporate decision framework into analysis steps)
new_instructions = """**Step 1 - Extract Key Characteristics** from interview responses and context:
   - Workflow complexity (simple, moderate, complex)
   - Domain structure (single, multi-domain, hierarchical)
   - Execution requirements (sequential, nested, iterative)
   - Coordination needs (minimal, moderate, complex)
   - Quality requirements (single-pass, reviewed, verified)
   - Decision-making style (deterministic, adaptive, consensus)
   - Resource constraints (cost-sensitive, time-sensitive)
   - Task dependencies (independent, sequential, prerequisite chains)

**Step 2 - Apply Pattern Selection Decision Framework**:

**By Domain Complexity:**
- Single domain → Consider: Pipeline (6), Organic (5)
- Multi-domain (distinct expertise areas) → Consider: Context-Aware Routing (1), Star (8)
- Hierarchical domains (organizational structure) → Consider: Hierarchical (4)

**By Execution Style:**
- Sequential (strict order) → Consider: Pipeline (6), Triage with Tasks (9)
- Nested (diversity/evaluation) → Consider: Redundant (7)
- Iterative (review-revise cycles) → Consider: Feedback Loop (3)
- Escalating (tiered capabilities) → Consider: Escalation (2)
- Flexible/Adaptive → Consider: Organic (5), Context-Aware Routing (1)

**By Coordination Needs:**
- Minimal (simple handoffs) → Consider: Organic (5), Pipeline (6)
- Moderate (some routing logic) → Consider: Context-Aware Routing (1), Star (8), Triage with Tasks (9)
- Complex (multi-level coordination) → Consider: Hierarchical (4), Redundant (7 with evaluator)
- Quality-focused (verification/validation) → Consider: Feedback Loop (3), Redundant (7)

**By Decision Making:**
- Deterministic (rule-based routing) → Consider: Pipeline (6), Triage with Tasks (9), Hierarchical (4)
- Adaptive (content-driven routing) → Consider: Context-Aware Routing (1), Escalation (2), Organic (5)
- Consensus-based (multi-agent agreement) → Consider: Redundant (7)
- Hierarchical (delegation chains) → Consider: Hierarchical (4), Star (8)

**By Quality Requirements:**
- Single-pass (no review) → Consider: Organic (5), Pipeline (6)
- Reviewed (approval gates) → Consider: Feedback Loop (3)
- Redundant verification (multiple approaches) → Consider: Redundant (7)
- Progressive refinement (iterative improvement) → Consider: Escalation (2), Feedback Loop (3)

**By Task Characteristics:**
- Well-defined stages → Pipeline (6)
- Decomposable with dependencies → Triage with Tasks (9)
- Requires domain expertise → Context-Aware Routing (1), Star (8)
- Creative/exploratory → Organic (5), Redundant (7)
- High-stakes/critical → Redundant (7), Feedback Loop (3)
- Cost-sensitive → Escalation (2)
- Organizational/team-based → Hierarchical (4)

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

# Build new sections list (remove domain sections, update CONTEXT and INSTRUCTIONS)
new_sections = []

for section in agent['prompt_sections']:
    heading = section['heading']
    
    # Keep these as-is
    if heading in ['[ROLE]', '[OBJECTIVE]', '[GUIDELINES]', '[EXAMPLES]', 
                   '[JSON OUTPUT COMPLIANCE]', '[OUTPUT FORMAT]']:
        new_sections.append(section)
    
    # Replace CONTEXT with consolidated version
    elif heading == '[CONTEXT]':
        new_sections.append({
            'id': 'context',
            'heading': '[CONTEXT]',
            'content': new_context
        })
    
    # Replace INSTRUCTIONS with consolidated version
    elif heading == '[INSTRUCTIONS]':
        new_sections.append({
            'id': 'instructions',
            'heading': '[INSTRUCTIONS]',
            'content': new_instructions
        })
    
    # Skip domain-specific sections being consolidated
    elif heading in ['[AG2 PATTERN COOKBOOK - COMPREHENSIVE KNOWLEDGE BASE]', 
                     '[PATTERN SELECTION DECISION FRAMEWORK]']:
        print(f"Removing {heading} (consolidated into CONTEXT/INSTRUCTIONS)")
        continue

# Update agent
agent['prompt_sections'] = new_sections
data['agents']['PatternAgent'] = agent

# Save
Path('workflows/Generator/agents.json').write_text(json.dumps(data, indent=2), encoding='utf-8')

print(f"\n✓ PatternAgent domain sections consolidated: {len(agent['prompt_sections'])} sections")
for i, s in enumerate(agent['prompt_sections'], 1):
    print(f"  {i}. {s['heading']}")
