"""
AG2 update_agent_state hooks for injecting pattern guidance into agent system messages.
    {
      "tool_name": "collect_structured_feedback",
      "py_content": "import logging\nfrom typing import Any, Dict\n\nfrom core.workflow.ui_tools import UIToolError, use_ui_tool\n\nlogger = logging.getLogger(__name__)\n\nasync def collect_structured_feedback(StructuredOutput: Dict[str, Any], agent_message: str, **runtime) -> Dict[str, Any]:\n    data = StructuredOutput or {}\n    if 'chat_id' not in runtime:\n        raise ValueError('chat_id missing from runtime context')\n    workflow_name = runtime.get('workflow_name', 'Product Launch Copy Refinement')\n    payload = {\n        'campaignBrief': data.get('campaign_brief_snapshot', ''),\n        'draftSummary': data.get('draft_summary', {}),\n        'pillarPrompts': data.get('pillar_prompts', []),\n        'iteration': data.get('iteration', 1),\n        'agentMessage': agent_message\n    }\n    try:\n        response = await use_ui_tool('FeedbackForm', payload, chat_id=runtime['chat_id'], workflow_name=workflow_name)\n    except UIToolError as error:\n        logger.exception('Feedback form failed to render', exc_info=error)\n        raise\n    if not isinstance(response, dict):\n        raise TypeError('Feedback form must return a dict payload')\n    missing_fields = {'needs_revision', 'pillar_scores', 'review_notes'} - set(response.keys())\n    if missing_fields:\n        raise ValueError(f'Feedback form response missing fields: {missing_fields}')\n    return response\n",
"""
import json
import logging
from pathlib import Path
from typing import Any, List, Dict

from core.workflow.agents.factory import _compose_prompt_sections

logger = logging.getLogger(__name__)


# Simplified pattern registry: remove external taxonomy dependency
# Canonical order maps to examples/guidance blocks across this module
PATTERN_ID_BY_NAME = {
    "contextawarerouting": 1,
    "escalation": 2,
    "feedbackloop": 3,
    "hierarchical": 4,
    "organic": 5,
    "pipeline": 6,
    "redundant": 7,
    "star": 8,
    "triagewithtasks": 9,
}

PATTERN_NAME_BY_ID = {v: k for k, v in PATTERN_ID_BY_NAME.items()}

PATTERN_DISPLAY_NAME_BY_ID = {
  1: "Context-Aware Routing",
  2: "Escalation",
  3: "Feedback Loop",
  4: "Hierarchical",
  5: "Organic",
  6: "Pipeline",
  7: "Redundant",
  8: "Star",
  9: "Triage with Tasks",
}

PATTERN_GUIDANCE_PLACEHOLDER = "{{PATTERN_GUIDANCE_AND_EXAMPLES}}"
PATTERN_GUIDANCE_SECTION_IDS = {"pattern_guidance_and_examples"}
PATTERN_GUIDANCE_SECTION_HEADING = "[PATTERN GUIDANCE AND EXAMPLES]"


def _apply_pattern_guidance(agent, guidance: str) -> bool:
    """Insert pattern guidance into the agent's PATTERN GUIDANCE AND EXAMPLES section."""
    try:
        normalized = (guidance or "").strip()
        if not normalized:
            logger.debug(f"No guidance content supplied for {getattr(agent, 'name', 'unknown')}" )
            return False

        sections = getattr(agent, "_mozaiks_prompt_sections", None)
        placeholder = PATTERN_GUIDANCE_PLACEHOLDER
        section_updated = False

        if isinstance(sections, list):
            for section in sections:
                if not isinstance(section, dict):
                    continue
                section_id = section.get("id")
                heading = section.get("heading")
                if section_id in PATTERN_GUIDANCE_SECTION_IDS or heading == PATTERN_GUIDANCE_SECTION_HEADING:
                    content = section.get("content") or ""
                    if placeholder in content:
                        section["content"] = content.replace(placeholder, normalized)
                    else:
                        section["content"] = normalized
                    section_updated = True

            if section_updated:
                try:
                    recomposed = _compose_prompt_sections(sections)
                    if hasattr(agent, "_system_message"):
                        agent._system_message = recomposed
                    elif hasattr(agent, "update_system_message") and callable(agent.update_system_message):
                        agent.update_system_message(recomposed)
                    setattr(agent, "_mozaiks_prompt_sections", sections)
                    setattr(agent, "_mozaiks_base_system_message", recomposed)
                    logger.debug(f"Applied pattern guidance via prompt section for {getattr(agent, 'name', 'unknown')}")
                    return True
                except Exception as compose_err:
                    logger.error(
                        f"Failed to recompose prompt sections after inserting pattern guidance for {getattr(agent, 'name', 'unknown')}: {compose_err}",
                        exc_info=True,
                    )

        current_message = getattr(agent, "_system_message", "") or ""
        if placeholder and placeholder in current_message:
            updated = current_message.replace(placeholder, normalized)
            if hasattr(agent, "_system_message"):
                agent._system_message = updated
            elif hasattr(agent, "update_system_message") and callable(agent.update_system_message):
                agent.update_system_message(updated)
            setattr(agent, "_mozaiks_base_system_message", updated)
            logger.debug(f"Applied pattern guidance via string replacement for {getattr(agent, 'name', 'unknown')}")
            return True

        if hasattr(agent, "_system_message"):
            separator = "\n\n" if current_message else ""
            agent._system_message = f"{current_message}{separator}{normalized}".strip()
            setattr(agent, "_mozaiks_base_system_message", agent._system_message)
            logger.debug(f"Appended pattern guidance to system_message for {getattr(agent, 'name', 'unknown')} (placeholder missing)" )
            return True

        logger.warning(f"Unable to apply pattern guidance for {getattr(agent, 'name', 'unknown')}: no accessible system message")
        return False

    except Exception as err:
        logger.error(f"Unhandled error applying pattern guidance for {getattr(agent, 'name', 'unknown')}: {err}", exc_info=True)
        return False

def _get_pattern_from_context(agent) -> Dict[str, Any]:
    """Extract selected pattern (by name or id) from context_variables without external taxonomy.

    Returns a minimal dict: {"id": int, "name": str}
    """
    try:
        # Access context_variables from agent (AG2 provides this)
        if not hasattr(agent, '_context_variables') and not hasattr(agent, 'context_variables'):
            logger.debug("Agent has no context_variables attribute")
            return {}

        context = getattr(agent, 'context_variables', None) or getattr(agent, '_context_variables', None)
        if context is None:
            logger.debug("Agent context_variables is None")
            return {}

        # Get PatternSelection from context data
        if hasattr(context, 'data'):
            pattern_selection = context.data.get('PatternSelection', {})
        elif isinstance(context, dict):
            pattern_selection = context.get('PatternSelection', {})
        else:
            logger.debug(f"Unexpected context type: {type(context)}")
            return {}

        if not pattern_selection:
            logger.debug("No PatternSelection found in context")
            return {}

        selected = pattern_selection.get('selected_pattern')
        if selected is None:
            logger.debug("PatternSelection missing selected_pattern field")
            return {}

        # Accept either an integer id or a string name/slug
        pattern_id: int | None = None
        pattern_name: str | None = None

        if isinstance(selected, int):
            pattern_id = selected if selected in PATTERN_NAME_BY_ID else None
            if pattern_id is None:
                logger.warning(f"Unknown pattern id provided: {selected}")
                return {}
            pattern_name = PATTERN_NAME_BY_ID[pattern_id]
        elif isinstance(selected, str):
            norm = selected.strip().lower().replace(" ", "").replace("_", "").replace("-", "")
            pattern_id = PATTERN_ID_BY_NAME.get(norm)
            if pattern_id is None:
                logger.warning(f"Unknown pattern name provided: {selected}")
                return {}
            pattern_name = norm
        else:
            logger.debug(f"selected_pattern has unexpected type: {type(selected)}")
            return {}

        # Return minimal structure used by downstream guidance functions
        display_name = PATTERN_DISPLAY_NAME_BY_ID.get(pattern_id)
        if not display_name and pattern_name:
            display_name = pattern_name.replace("_", " ").title()

        result = {"id": pattern_id, "name": pattern_name, "display_name": display_name}
        logger.info(f"✓ Pattern resolved for {agent.name}: id={pattern_id}, name={pattern_name}")
        return result

    except Exception as e:
        logger.error(f"Error extracting pattern from context: {e}", exc_info=True)
        return {}


def inject_workflow_strategy_guidance(agent, messages: List[Dict[str, Any]]) -> None:
    """
    AG2 update_agent_state hook for WorkflowStrategyAgent.
    Injects comprehensive pattern-specific guidance into system message.
    
    WorkflowStrategyAgent OUTPUT FORMAT (WorkflowStrategyCall JSON):
    {
      "WorkflowStrategy": {
        "workflow_name": "<string>",
        "workflow_description": "<string>",
        "trigger": "chat|form_submit|schedule|database_condition|webhook",
        "initiated_by": "user|system|external_event",
        "pattern": ["<string>"],
        "phases": [
          {
            "phase_index": <int>,
            "phase_name": "<string>",
            "phase_description": "<string>",
            "human_in_loop": true|false,
            "agents_needed": "single|sequential|nested"
          }
        ]
      }
    }
    """
    try:
        pattern = _get_pattern_from_context(agent)
        if not pattern:
            logger.debug(f"No pattern available for {agent.name}, skipping guidance injection")
            return

        pattern_id = pattern.get('id')
        pattern_name = pattern.get('name')
        pattern_display_name = pattern.get('display_name', pattern_name)

        # Pattern-specific WorkflowStrategy examples (complete JSON payloads)
        strategy_examples = {
            1: """{
  "WorkflowStrategy": {
    "workflow_name": "SaaS Support Domain Router",
    "workflow_description": "When a customer opens a support chat, the workflow classifies the request by product surface and routes the highest-confidence specialist so issues reach the right expert on the first try.",
    "trigger": "chat",
    "initiated_by": "user",
    "pattern": ["Context-Aware Routing"],
    "phases": [
      {
        "phase_index": 0,
        "phase_name": "Phase 1: Automated Intake & Signal Capture",
        "phase_description": "Router agent gathers account metadata, parses the first message for domain cues, and records confidence scores.",
        "human_in_loop": false,
        "agents_needed": "single"
      },
      {
        "phase_index": 1,
        "phase_name": "Phase 2: Specialist Routing & Engagement",
        "phase_description": "Orchestrator selects the best specialist queue, invites the right agent, and hands off the enriched context payload.",
        "human_in_loop": false,
        "agents_needed": "sequential"
      },
      {
        "phase_index": 2,
        "phase_name": "Phase 3: Resolution & Post-Chat Summary",
        "phase_description": "Specialist resolves the issue, Router agent validates satisfaction, and final disposition is synced to CRM.",
        "human_in_loop": false,
        "agents_needed": "single"
      }
    ]
  }
}""",
            2: """{
  "WorkflowStrategy": {
    "workflow_name": "Cloud Incident Escalation Ladder",
    "workflow_description": "When monitoring detects a P1 outage, the workflow applies confidence thresholds and escalates the investigation through tiered responders so the right expert owns remediation without losing context.",
    "trigger": "webhook",
    "initiated_by": "system",
    "pattern": ["Escalation"],
    "phases": [
      {
        "phase_index": 0,
        "phase_name": "Phase 1: Alert Intake & Baseline Diagnostics",
        "phase_description": "Automated triage agent ingests the alert, correlates recent deployments, and attempts scripted remediation steps.",
        "human_in_loop": false,
        "agents_needed": "single"
      },
      {
        "phase_index": 1,
        "phase_name": "Phase 2: Tier Promotion & Context Packaging",
        "phase_description": "Escalation coordinator assesses recovery confidence; if under 0.85 it bundles findings and pages the next responder tier.",
        "human_in_loop": false,
        "agents_needed": "sequential"
      },
      {
        "phase_index": 2,
        "phase_name": "Phase 3: Expert Mitigation & Stakeholder Updates",
        "phase_description": "Site reliability lead executes advanced playbooks, involves human commander as needed, and publishes status to leadership.",
        "human_in_loop": true,
        "agents_needed": "single"
      }
    ]
  }
}""",
            3: """{
  "WorkflowStrategy": {
    "workflow_name": "Product Launch Copy Refinement",
    "workflow_description": "When marketing requests launch copy, the workflow drafts messaging, gathers structured stakeholder feedback, and iterates until approval so content quality steadily improves.",
    "trigger": "chat",
    "initiated_by": "user",
    "pattern": ["Feedback Loop"],
    "phases": [
      {
        "phase_index": 0,
        "phase_name": "Phase 1: Brief Capture & Acceptance Criteria",
        "phase_description": "Facilitator agent collects campaign goals, tone, audience data, and defines done criteria with stakeholders.",
        "human_in_loop": true,
        "agents_needed": "single"
      },
      {
        "phase_index": 1,
        "phase_name": "Phase 2: Draft Creation",
        "phase_description": "Authoring agent generates initial announcement copy and attaches rationale mapped to the brief.",
        "human_in_loop": false,
        "agents_needed": "single"
      },
      {
        "phase_index": 2,
        "phase_name": "Phase 3: Structured Review",
        "phase_description": "Review agent (or PMM) scores messaging pillars, leaves line-level comments, and flags blockers or minor tweaks.",
        "human_in_loop": true,
        "agents_needed": "single"
      },
      {
        "phase_index": 3,
        "phase_name": "Phase 4: Revision & Approval",
        "phase_description": "Authoring agent applies accepted feedback, rechecks criteria, and loops until reviewers sign off.",
        "human_in_loop": false,
        "agents_needed": "sequential"
      }
    ]
  }
}""",
            4: """{
  "WorkflowStrategy": {
    "workflow_name": "Market Entry Intelligence Stack",
    "workflow_description": "When an executive team explores a new market, the workflow cascades research tasks through managers and specialists so each layer tackles the right depth of analysis.",
    "trigger": "chat",
    "initiated_by": "user",
    "pattern": ["Hierarchical"],
    "phases": [
      {
        "phase_index": 0,
        "phase_name": "Phase 1: Executive Briefing & Workstream Plan",
        "phase_description": "Strategy lead clarifies objectives, splits work into demand, competitor, and regulatory streams, and assigns managers.",
        "human_in_loop": false,
        "agents_needed": "single"
      },
      {
        "phase_index": 1,
        "phase_name": "Phase 2: Manager Task Framing",
        "phase_description": "Each manager designs research backlogs, defines success metrics, and syncs expectations with their specialist pods.",
        "human_in_loop": false,
        "agents_needed": "nested"
      },
      {
        "phase_index": 2,
        "phase_name": "Phase 3: Specialist Deep Dives",
        "phase_description": "Specialists execute assigned analyses, share interim findings upward, and surface blockers requiring executive decisions.",
        "human_in_loop": false,
        "agents_needed": "nested"
      },
      {
        "phase_index": 3,
        "phase_name": "Phase 4: Executive Synthesis & Go/No-Go",
        "phase_description": "Executive aggregates insights, prepares the narrative deck, and secures leadership approval on the market decision.",
        "human_in_loop": true,
        "agents_needed": "single"
      }
    ]
  }
}""",
            5: """{
  "WorkflowStrategy": {
    "workflow_name": "Omnichannel Campaign Content Studio",
    "workflow_description": "When marketing launches a campaign sprint, the workflow orchestrates collaborative idea generation, automated draft creation, and cross-channel packaging so content is ready for every surface in one pass.",
    "trigger": "chat",
    "initiated_by": "user",
    "pattern": ["Organic"],
    "phases": [
      {
        "phase_index": 0,
        "phase_name": "Phase 1: Brief Alignment & Inspiration",
        "phase_description": "Facilitator agent gathers campaign goals, target personas, and product messaging while seeding the room with prior high-performing assets.",
        "human_in_loop": true,
        "agents_needed": "single"
      },
      {
        "phase_index": 1,
        "phase_name": "Phase 2: Collaborative Concept Jam",
        "phase_description": "Copy, design, and growth contributors brainstorm in an open thread while ideation agents capture hooks, tag emerging themes, and surface gaps to the group.",
        "human_in_loop": true,
        "agents_needed": "sequential"
      },
      {
        "phase_index": 2,
        "phase_name": "Phase 3: Asset Assembly & Channel Packaging",
        "phase_description": "Workflow compiles the strongest concepts into draft emails, social copy, and landing page variants, then routes them for stakeholder preview and scheduling.",
        "human_in_loop": true,
        "agents_needed": "single"
      }
    ]
  }
}""",
            6: """{
  "WorkflowStrategy": {
    "workflow_name": "Digital Loan Application Pipeline",
    "workflow_description": "When a borrower submits an online loan form, the workflow performs sequential validation, risk checks, underwriting, and customer notifications so decisions are consistent and auditable.",
    "trigger": "form_submit",
    "initiated_by": "user",
    "pattern": ["Pipeline"],
    "phases": [
      {
        "phase_index": 0,
        "phase_name": "Phase 1: Intake Validation",
        "phase_description": "Intake agent verifies required documents, normalizes applicant data, and halts if mandatory fields are missing.",
        "human_in_loop": false,
        "agents_needed": "single"
      },
      {
        "phase_index": 1,
        "phase_name": "Phase 2: Risk & Compliance Screening",
        "phase_description": "Workflow runs credit, fraud, and KYC checks sequentially, annotating the application with risk scores.",
        "human_in_loop": false,
        "agents_needed": "sequential"
      },
      {
        "phase_index": 2,
        "phase_name": "Phase 3: Underwriting Decision",
        "phase_description": "Underwriting agent evaluates policy rules, calculates terms, and flags edge cases for manual review.",
        "human_in_loop": false,
        "agents_needed": "single"
      },
      {
        "phase_index": 3,
        "phase_name": "Phase 4: Offer & Fulfillment",
        "phase_description": "Fulfillment agent generates the offer packet, notifies the borrower, and syncs status back to servicing systems.",
        "human_in_loop": true,
        "agents_needed": "single"
      }
    ]
  }
}""",
            7: """{
  "WorkflowStrategy": {
    "workflow_name": "Demand Forecast Comparison",
    "workflow_description": "When the weekly planning cycle runs, the workflow commissions multiple forecasting approaches and compares them so planners adopt the most reliable projection.",
    "trigger": "schedule",
    "initiated_by": "system",
    "pattern": ["Redundant"],
    "phases": [
      {
        "phase_index": 0,
        "phase_name": "Phase 1: Scenario Brief",
        "phase_description": "Coordinator agent summarizes the upcoming sales window, constraints, and evaluation metrics for downstream models.",
        "human_in_loop": false,
        "agents_needed": "single"
      },
      {
        "phase_index": 1,
        "phase_name": "Phase 2: Parallel Forecast Generation",
        "phase_description": "Distinct specialist agents build statistical, causal, and heuristic forecasts in parallel with documented assumptions.",
        "human_in_loop": false,
        "agents_needed": "nested"
      },
      {
        "phase_index": 2,
        "phase_name": "Phase 3: Comparative Evaluation",
        "phase_description": "Evaluator agent scores each forecast against hold-out accuracy, volatility, and narrative fit, involving planner review when diverging.",
        "human_in_loop": true,
        "agents_needed": "single"
      },
      {
        "phase_index": 3,
        "phase_name": "Phase 4: Recommendation Delivery",
        "phase_description": "Coordinator selects the preferred forecast, documents rationale, and distributes the planning brief to stakeholders.",
        "human_in_loop": true,
        "agents_needed": "single"
      }
    ]
  }
}""",
            8: """{
  "WorkflowStrategy": {
    "workflow_name": "Vendor Onboarding Hub",
    "workflow_description": "When a new vendor submits onboarding forms, the workflow routes required checks to finance, security, and legal spokes so every team completes their review while the hub tracks status.",
    "trigger": "form_submit",
    "initiated_by": "user",
    "pattern": ["Star"],
    "phases": [
      {
        "phase_index": 0,
        "phase_name": "Phase 1: Hub Intake",
        "phase_description": "Coordinator agent validates vendor details, determines which spokes must be engaged, and packages briefing packets.",
        "human_in_loop": false,
        "agents_needed": "single"
      },
      {
        "phase_index": 1,
        "phase_name": "Phase 2: Spoke Reviews",
        "phase_description": "Finance, security, and legal spokes perform their assessments independently while posting status updates to the hub.",
        "human_in_loop": false,
        "agents_needed": "nested"
      },
      {
        "phase_index": 2,
        "phase_name": "Phase 3: Risk Alignment",
        "phase_description": "Coordinator monitors spoke progress, resolves conflicts, and summarizes outstanding blockers or additional requirements.",
        "human_in_loop": false,
        "agents_needed": "sequential"
      },
      {
        "phase_index": 3,
        "phase_name": "Phase 4: Hub Approval & Handoff",
        "phase_description": "Coordinator compiles approvals, triggers account provisioning, and delivers the final onboarding summary to the requester.",
        "human_in_loop": true,
        "agents_needed": "single"
      }
    ]
  }
}""",
            9: """{
  "WorkflowStrategy": {
    "workflow_name": "Rapid App Foundry",
    "workflow_description": "When an internal team requests a lightweight application, the workflow decomposes requirements into typed tasks, coordinates design-to-build handoffs, and ships a usable app scaffold with minimal manual project management.",
    "trigger": "chat",
    "initiated_by": "user",
    "pattern": ["Triage with Tasks"],
    "phases": [
      {
        "phase_index": 0,
        "phase_name": "Phase 1: Requirement Breakdown",
        "phase_description": "Triage agent captures personas, critical features, and integrations, then emits ResearchTask[], DesignTask[], and BuildTask[] queues with priority codes.",
        "human_in_loop": false,
        "agents_needed": "single"
      },
      {
        "phase_index": 1,
        "phase_name": "Phase 2: Dependency Planning",
        "phase_description": "Task manager enforces research-before-design and design-before-build dependencies, sequencing work and flagging prerequisites.",
        "human_in_loop": false,
        "agents_needed": "single"
      },
      {
        "phase_index": 2,
        "phase_name": "Phase 3: Research & Design Execution",
        "phase_description": "Research agents gather domain data and competitor benchmarks while UX agents draft wireframes that satisfy functional findings.",
        "human_in_loop": false,
        "agents_needed": "sequential"
      },
      {
        "phase_index": 3,
        "phase_name": "Phase 4: App Scaffolding & Integration",
        "phase_description": "Implementation agents generate the app skeleton, configure integrations, and log automated test coverage for each module.",
        "human_in_loop": false,
        "agents_needed": "sequential"
      },
      {
        "phase_index": 4,
        "phase_name": "Phase 5: Review & Handoff",
        "phase_description": "Lead agent assembles the runnable build, demo script, and backlog of stretch enhancements, then secures stakeholder approval.",
        "human_in_loop": true,
        "agents_needed": "single"
      }
    ]
  }
}"""
        }

        example_json = strategy_examples.get(pattern_id)

        if not example_json:
            logger.warning(f"No strategy example found for pattern_id {pattern_id}")
            return

        guidance = (
            f"[PATTERN EXAMPLE - {pattern_display_name}]\n"
            f"Here is a complete WorkflowStrategy JSON example aligned with the {pattern_display_name} pattern.\n\n"
            f"```json\n{example_json}\n```\n"
        )

        if _apply_pattern_guidance(agent, guidance):
            logger.info(f"✓ Injected WorkflowStrategy example for {pattern_display_name} into {agent.name}")
        else:
            logger.warning(f"Pattern guidance injection failed for {agent.name}")

    except Exception as e:
        logger.error(f"Error in inject_workflow_strategy_guidance: {e}", exc_info=True)

def inject_workflow_architect_guidance(agent, messages: List[Dict[str, Any]]) -> None:
    """
  AG2 update_agent_state hook for WorkflowArchitectAgent.
  Injects pattern-specific workflow-wide context variables and lifecycle hooks.

    WorkflowArchitectAgent OUTPUT FORMAT (TechnicalBlueprint JSON):
    {
      "TechnicalBlueprint": {
        "global_context_variables": [
          {
            "name": "<string>",
            "type": "static|environment|database|derived",
            "purpose": "<string>",
            "trigger_hint": "<string|null>"
          }
        ],
        "ui_components": [
          {
            "phase_name": "<string>",
            "agent": "<PascalCaseAgentName>",
            "tool": "<snake_case_tool>",
            "label": "<CTA or heading>",
            "component": "<PascalCaseComponent>",
            "display": "inline|artifact",
            "interaction_pattern": "single_step|two_step_confirmation|multi_step",
            "summary": "<<=200 char narrative>"
          }
        ],
        "before_chat_lifecycle": {
          "name": "<string>",
          "purpose": "<string>",
          "trigger": "before_chat",
          "integration": "<string|null>"
        },
        "after_chat_lifecycle": {
          "name": "<string>",
          "purpose": "<string>",
          "trigger": "after_chat",
          "integration": "<string|null>"
        }
      }
    }

    Set ui_components to [] when the workflow exposes no UI tools.
    Set before_chat_lifecycle or after_chat_lifecycle to null when the workflow does not require that hook.
    """
    try:
        pattern = _get_pattern_from_context(agent)
        if not pattern:
            logger.debug(f"No pattern available for {agent.name}, skipping guidance injection")
            return

        pattern_id = pattern.get('id')
        pattern_name = pattern.get('name')
        pattern_display_name = pattern.get('display_name', pattern_name)

        # Pattern-specific complete JSON examples matching TechnicalBlueprintCall schema
        architect_examples = {
            1: """{
  "TechnicalBlueprint": {
    "global_context_variables": [
      {
        "name": "intake_confidence",
        "type": "derived",
        "purpose": "Stores confidence score assigned to the detected support domain",
        "trigger_hint": "Set when RouterAgent emits CONFIDENCE:<value>"
      },
      {
        "name": "routed_specialist",
        "type": "derived",
        "purpose": "Captures the specialist queue that received the conversation",
        "trigger_hint": "Set when RouterAgent outputs ROUTED_TO:<queue>"
      },
      {
        "name": "resolution_disposition",
        "type": "derived",
        "purpose": "Summarizes final resolution status and satisfaction rating",
        "trigger_hint": "Set when SpecialistAgent issues RESOLUTION:<status>"
      }
    ],
    "ui_components": [
      {
        "phase_name": "Phase 0 - Intake & Routing",
        "agent": "RouterAgent",
        "tool": "confirm_routing_decision",
        "label": "Confirm routing destination",
        "component": "RoutingDecisionPanel",
        "display": "inline",
        "interaction_pattern": "two_step_confirmation",
        "summary": "An inline routing card appears in chat showing the detected support queue (Billing, Technical, or Account) with confidence score. User sees the proposed destination highlighted with a brief explanation, then clicks Approve to proceed or Override to manually select a different queue."
      },
      {
        "phase_name": "Phase 2 - Specialist Resolution",
        "agent": "SpecialistAgent",
        "tool": "share_resolution_summary",
        "label": "Review resolution package",
        "component": "ResolutionSummaryArtifact",
        "display": "artifact",
        "interaction_pattern": "single_step",
        "summary": "A side tray slides open displaying the complete resolution summary with three sections: Issue Description, Steps Taken, and Verification Results. User scrolls through the structured resolution package, reviews screenshots and logs, then clicks Acknowledge to close and complete the ticket."
      }
    ],
    "before_chat_lifecycle": {
      "name": "reset_support_routing_state",
      "purpose": "Clear prior routing metadata and prepare intake buffers",
      "trigger": "before_chat",
      "integration": null
    },
    "after_chat_lifecycle": {
      "name": "sync_support_summary",
      "purpose": "Push routing outcome and disposition metrics to CRM",
      "trigger": "after_chat",
      "integration": "CustomerSupportCRM"
    }
  }
}""",
            2: """{
  "TechnicalBlueprint": {
    "global_context_variables": [
      {
        "name": "incident_severity",
        "type": "derived",
        "purpose": "Tracks live severity rating for the outage response",
        "trigger_hint": "Updated when TriageAgent posts SEVERITY:<level>"
      },
      {
        "name": "active_response_tier",
        "type": "derived",
        "purpose": "Identifies which escalation tier currently owns remediation",
        "trigger_hint": "Set when EscalationCoordinator announces TIER_OWNER:<group>"
      },
      {
        "name": "remediation_status",
        "type": "derived",
        "purpose": "Aggregates mitigation steps, ETA, and rollback decisions",
        "trigger_hint": "Set when SRELead outputs REMEDIATION_STATUS:<state>"
      }
    ],
    "ui_components": [
      {
        "phase_name": "Phase 0 - Intake & Severity Check",
        "agent": "TriageAgent",
        "tool": "acknowledge_incident_brief",
        "label": "Confirm incident details",
        "component": "IncidentIntakeInline",
        "display": "inline",
        "interaction_pattern": "two_step_confirmation",
        "summary": "TriageAgent posts an inline card summarizing alerts and requests a quick confirmation before escalation tiering begins."
      },
      {
        "phase_name": "Phase 3 - Resolution Review",
        "agent": "SRELead",
        "tool": "publish_postmortem_outline",
        "label": "Review incident wrap-up",
        "component": "PostmortemSummaryArtifact",
        "display": "artifact",
        "interaction_pattern": "single_step",
        "summary": "SRELead delivers an artifact outlining remediation, open follow-ups, and next actions for stakeholder sign-off."
      }
    ],
    "before_chat_lifecycle": {
      "name": "initialize_incident_context",
      "purpose": "Seed incident timeline, clear stale responders, and load alert metadata",
      "trigger": "before_chat",
      "integration": null
    },
    "after_chat_lifecycle": {
      "name": "publish_incident_postmortem_stub",
      "purpose": "Archive incident summary and auto-draft postmortem notes",
      "trigger": "after_chat",
      "integration": "StatusPage"
    }
  }
}""",
            3: """{
  "TechnicalBlueprint": {
    "global_context_variables": [
      {
        "name": "campaign_brief_snapshot",
        "type": "derived",
        "purpose": "Normalized brief containing personas, tone, and acceptance criteria",
        "trigger_hint": "Set when FacilitatorAgent outputs BRIEF_FINALIZED"
      },
      {
        "name": "feedback_log",
        "type": "derived",
        "purpose": "Structured array of review comments with severity tags",
        "trigger_hint": "Appended when ReviewAgent emits FEEDBACK_BUNDLE"
      },
      {
        "name": "approval_gate_status",
        "type": "derived",
        "purpose": "Tracks stakeholder approval state for the launch copy",
        "trigger_hint": "Set when StakeholderTool returns APPROVAL_STATUS:<value>"
      }
    ],
    "ui_components": [
      {
        "phase_name": "Phase 1 - Draft Creation",
        "agent": "CreatorAgent",
        "tool": "collect_structured_feedback",
        "label": "Submit revision feedback",
        "component": "FeedbackForm",
        "display": "artifact",
        "interaction_pattern": "multi_step",
        "summary": "A side tray opens showing the complete draft copy with an interactive feedback form overlay. Step 1: User scores messaging pillars (Value Prop, Differentiation, CTA) on 1-5 scales with real-time validation. Step 2: User highlights specific sections and adds inline revision comments. Step 3: User reviews feedback summary and clicks Submit Feedback to trigger revision cycle."
      },
      {
        "phase_name": "Phase 3 - Approval Gate",
        "agent": "StakeholderAgent",
        "tool": "approve_final_copy",
        "label": "Approve launch copy",
        "component": "ApprovalDecisionInline",
        "display": "inline",
        "interaction_pattern": "two_step_confirmation",
        "summary": "An inline approval card appears in chat displaying the revised launch copy summary with key changes highlighted in yellow. User sees before/after comparison snippets for major edits, then clicks either Approve for Launch (green button) or Request Final Revisions (amber button) to proceed."
      }
    ],
    "before_chat_lifecycle": {
      "name": "prime_campaign_workspace",
      "purpose": "Provision shared folders and ingest reference assets for the sprint",
      "trigger": "before_chat",
      "integration": "ContentHub"
    },
    "after_chat_lifecycle": {
      "name": "archive_campaign_package",
      "purpose": "Export approved copy, feedback history, and metrics to CMS",
      "trigger": "after_chat",
      "integration": "ContentHub"
    }
  }
}""",
            4: """{
  "TechnicalBlueprint": {
    "global_context_variables": [
      {
        "name": "workstream_assignments",
        "type": "derived",
        "purpose": "Mapping of demand, competitor, and regulatory owners",
        "trigger_hint": "Set when ExecutiveAgent issues WORKSTREAM_PLAN"
      },
      {
        "name": "manager_status_updates",
        "type": "derived",
        "purpose": "Rolling status objects from each manager with risk flags",
        "trigger_hint": "Appended when ManagerAgent sends STATUS_BULLETIN"
      },
      {
        "name": "go_no_go_recommendation",
        "type": "derived",
        "purpose": "Executive decision package combining insights and rationale",
        "trigger_hint": "Set when ExecutiveAgent outputs DECISION_BRIEF"
      }
    ],
    "ui_components": [
      {
        "phase_name": "Phase 1 - Executive Briefing",
        "agent": "ExecutiveAgent",
        "tool": "share_strategy_overview",
        "label": "Review market entry brief",
        "component": "StrategyBriefArtifact",
        "display": "artifact",
        "interaction_pattern": "single_step",
        "summary": "ExecutiveAgent publishes an artifact summarizing objectives and assigns managers before downstream workstreams begin."
      },
      {
        "phase_name": "Phase 2 - Manager Updates",
        "agent": "ManagerAgent",
        "tool": "capture_risk_update",
        "label": "Submit risk update",
        "component": "ManagerStatusInline",
        "display": "inline",
        "interaction_pattern": "two_step_confirmation",
        "summary": "Managers log risk updates inline so the executive hub can escalate blockers in real time."
      }
    ],
    "before_chat_lifecycle": {
      "name": "distribute_strategy_brief",
      "purpose": "Share objective summary and research templates with managers",
      "trigger": "before_chat",
      "integration": null
    },
    "after_chat_lifecycle": {
      "name": "store_market_entry_decision",
      "purpose": "Persist recommendation, supporting data, and follow-up actions",
      "trigger": "after_chat",
      "integration": "StrategyVault"
    }
  }
}""",
            5: """{
  "TechnicalBlueprint": {
    "global_context_variables": [
      {
        "name": "idea_pool",
        "type": "derived",
        "purpose": "Live collection of campaign hooks with contributor attributions",
        "trigger_hint": "Updated when IdeationAgent records IDEA_CAPTURE"
      },
      {
        "name": "asset_draft_registry",
        "type": "derived",
        "purpose": "Status map of draft emails, social posts, and landing variants",
        "trigger_hint": "Set when ContentAssembler outputs ASSET_DRAFT:<channel>"
      },
      {
        "name": "stakeholder_notes",
        "type": "derived",
        "purpose": "Aggregated reviewer reactions and launch readiness flags",
        "trigger_hint": "Appended when ReviewerTool sends NOTE_ENTRY"
      }
    ],
    "ui_components": [
      {
        "phase_name": "Phase 1 - Ideation Jam",
        "agent": "IdeationAgent",
        "tool": "submit_brainstorm_ideas",
        "label": "Add campaign idea",
        "component": "IdeaCaptureInline",
        "display": "inline",
        "interaction_pattern": "multi_step",
        "summary": "IdeationAgent opens an inline capture panel so participants can log ideas, tags, and inspiration without leaving the flow."
      },
      {
        "phase_name": "Phase 3 - Asset Review",
        "agent": "ReviewerAgent",
        "tool": "review_asset_variants",
        "label": "Review creative variants",
        "component": "CreativeBoardArtifact",
        "display": "artifact",
        "interaction_pattern": "single_step",
        "summary": "ReviewerAgent posts an artifact of drafted assets so the user can skim highlights and decide which to advance."
      }
    ],
    "before_chat_lifecycle": {
      "name": "open_campaign_workspace",
      "purpose": "Create collaboration space and preload prior performance benchmarks",
      "trigger": "before_chat",
      "integration": "MarketingNotion"
    },
    "after_chat_lifecycle": {
      "name": "push_campaign_package",
      "purpose": "Deliver approved assets and notes to scheduling automations",
      "trigger": "after_chat",
      "integration": "CampaignScheduler"
    }
  }
}""",
            6: """{
  "TechnicalBlueprint": {
    "global_context_variables": [
      {
        "name": "application_status",
        "type": "derived",
        "purpose": "Current stage marker for the applicant journey",
        "trigger_hint": "Updated when PipelineAgent emits STAGE_ADVANCE:<stage>"
      },
      {
        "name": "risk_flags",
        "type": "derived",
        "purpose": "Consolidated fraud, compliance, and credit findings",
        "trigger_hint": "Appended when RiskScreening tool posts FLAG_PAYLOAD"
      },
      {
        "name": "underwriting_result",
        "type": "derived",
        "purpose": "Decision payload including terms, APR, and decline reasons",
        "trigger_hint": "Set when UnderwritingAgent outputs DECISION_PACKAGE"
      }
    ],
    "ui_components": [
      {
        "phase_name": "Phase 0 - Intake",
        "agent": "PipelineAgent",
        "tool": "collect_supporting_documents",
        "label": "Upload financial documents",
        "component": "DocumentChecklistInline",
        "display": "inline",
        "interaction_pattern": "multi_step",
        "summary": "PipelineAgent walks the applicant through an inline checklist to upload identity, income, and banking statements before downstream reviews."
      },
      {
        "phase_name": "Phase 2 - Decision Review",
        "agent": "UnderwritingAgent",
        "tool": "share_underwriting_package",
        "label": "Review underwriting decision",
        "component": "DecisionSummaryArtifact",
        "display": "artifact",
        "interaction_pattern": "single_step",
        "summary": "UnderwritingAgent posts an artifact summarizing approval terms or decline reasons so the applicant and banker can finalize next steps."
      }
    ],
    "before_chat_lifecycle": {
      "name": "initialize_application_record",
      "purpose": "Create applicant shell record and attach submission documents",
      "trigger": "before_chat",
      "integration": "LoanCRM"
    },
    "after_chat_lifecycle": {
      "name": "finalize_decision_export",
      "purpose": "Sync decision, funding status, and notifications to core banking",
      "trigger": "after_chat",
      "integration": "LoanCore"
    }
  }
}""",
            7: """{
  "TechnicalBlueprint": {
    "global_context_variables": [
      {
        "name": "forecast_submissions",
        "type": "derived",
        "purpose": "Dictionary of submitted forecasts keyed by modeling approach",
        "trigger_hint": "Set when SpecialistAgent emits FORECAST_READY"
      },
      {
        "name": "evaluation_matrix",
        "type": "derived",
        "purpose": "Scoring table with accuracy, volatility, and narrative fit columns",
        "trigger_hint": "Updated when EvaluatorAgent posts SCORE_UPDATE"
      },
      {
        "name": "selected_forecast_summary",
        "type": "derived",
        "purpose": "Chosen forecast metadata and rationale for planners",
        "trigger_hint": "Set when CoordinatorAgent issues FORECAST_SELECTION"
      }
    ],
    "ui_components": [
      {
        "phase_name": "Phase 1 - Model Submission",
        "agent": "SpecialistAgent",
        "tool": "submit_forecast_bundle",
        "label": "Upload forecast bundle",
        "component": "ForecastUploadInline",
        "display": "inline",
        "interaction_pattern": "multi_step",
        "summary": "SpecialistAgent opens an inline uploader so each modeling approach can attach projections, assumptions, and diagnostics side by side."
      },
      {
        "phase_name": "Phase 2 - Cross-Evaluation",
        "agent": "EvaluatorAgent",
        "tool": "compare_forecasts",
        "label": "Compare forecast scenarios",
        "component": "ForecastComparisonArtifact",
        "display": "artifact",
        "interaction_pattern": "single_step",
        "summary": "EvaluatorAgent publishes an artifact ranking submissions on accuracy and resilience, helping coordinators pick the strongest outlook."
      }
    ],
    "before_chat_lifecycle": {
      "name": "prepare_forecast_cycle",
      "purpose": "Reset prior submissions and load upcoming planning window parameters",
      "trigger": "before_chat",
      "integration": null
    },
    "after_chat_lifecycle": {
      "name": "publish_forecast_summary",
      "purpose": "Distribute selected forecast package to planning stakeholders",
      "trigger": "after_chat",
      "integration": "PlanningHub"
    }
  }
}""",
            8: """{
  "TechnicalBlueprint": {
    "global_context_variables": [
      {
        "name": "spoke_status_registry",
        "type": "derived",
        "purpose": "Tracks completion state for finance, security, and legal reviews",
        "trigger_hint": "Updated when SpokeAgent emits REVIEW_STATUS:<state>"
      },
      {
        "name": "risk_exception_notes",
        "type": "derived",
        "purpose": "Catalog of open blockers or requested mitigations",
        "trigger_hint": "Appended when any spoke posts RISK_EXCEPTION"
      },
      {
        "name": "required_document_matrix",
        "type": "derived",
        "purpose": "Checklist of documents received versus outstanding",
        "trigger_hint": "Set when CoordinatorAgent updates DOCUMENT_STATUS"
      }
    ],
    "ui_components": [
      {
        "phase_name": "Phase 0 - Vendor Intake",
        "agent": "CoordinatorAgent",
        "tool": "capture_vendor_profile",
        "label": "Enter vendor profile",
        "component": "VendorProfileInline",
        "display": "inline",
        "interaction_pattern": "multi_step",
        "summary": "CoordinatorAgent uses an inline wizard to capture company basics and route downstream review requests to each spoke."
      },
      {
        "phase_name": "Phase 2 - Risk Decision",
        "agent": "RiskLeadAgent",
        "tool": "publish_risk_clearance",
        "label": "Review consolidated findings",
        "component": "RiskClearanceArtifact",
        "display": "artifact",
        "interaction_pattern": "single_step",
        "summary": "RiskLeadAgent shares an artifact aggregating finance, security, and legal determinations so stakeholders can approve onboarding."
      }
    ],
    "before_chat_lifecycle": {
      "name": "seed_spoke_registry",
      "purpose": "Initialize branch tracking and clear previous vendor context",
      "trigger": "before_chat",
      "integration": null
    },
    "after_chat_lifecycle": {
      "name": "archive_vendor_package",
      "purpose": "Bundle approvals, risk notes, and onboarding summary for handoff",
      "trigger": "after_chat",
      "integration": "VendorPortal"
    }
  }
}""",
            9: """{
  "TechnicalBlueprint": {
    "global_context_variables": [
      {
        "name": "task_queue_snapshot",
        "type": "derived",
        "purpose": "Categorized backlog of research, design, build, and QA tasks",
        "trigger_hint": "Set when TriageAgent emits TASK_QUEUE_UPDATE"
      },
      {
        "name": "dependency_graph",
        "type": "derived",
        "purpose": "Directed graph showing prerequisite relationships across tasks",
        "trigger_hint": "Updated when TaskManagerAgent outputs DEPENDENCY_SYNC"
      },
      {
        "name": "release_candidate_metadata",
        "type": "derived",
        "purpose": "Summarizes build artifacts, test coverage, and open follow-ups",
        "trigger_hint": "Set when ImplementationAgent issues RELEASE_CANDIDATE"
      }
    ],
    "ui_components": [
      {
        "phase_name": "Phase 0 - Intake Triage",
        "agent": "TriageAgent",
        "tool": "classify_incoming_requests",
        "label": "Categorize new requests",
        "component": "TaskIntakeInline",
        "display": "inline",
        "interaction_pattern": "multi_step",
        "summary": "TriageAgent prompts the user inline to confirm priority, owner, and due dates for new backlog entries before dispatching them."
      },
      {
        "phase_name": "Phase 3 - Release Review",
        "agent": "ImplementationAgent",
        "tool": "share_release_candidate",
        "label": "Review release bundle",
        "component": "ReleaseBundleArtifact",
        "display": "artifact",
        "interaction_pattern": "single_step",
        "summary": "ImplementationAgent posts a release artifact covering demo links, QA status, and pending tasks to get stakeholder approval."
      }
    ],
    "before_chat_lifecycle": {
      "name": "initialize_app_foundry_state",
      "purpose": "Clear prior queues, reprovision project repositories, and seed templates",
      "trigger": "before_chat",
      "integration": "InternalGit"
    },
    "after_chat_lifecycle": {
      "name": "deliver_app_bundle",
      "purpose": "Publish runnable build, demo script, and backlog to stakeholders",
      "trigger": "after_chat",
      "integration": "InternalAppStore"
    }
  }
}"""
        }
        
        example_json = architect_examples.get(pattern_id)

        if not example_json:
            logger.warning(f"No architect example found for pattern_id {pattern_id}")
            return

        guidance = (
            f"[PATTERN EXAMPLE - {pattern_display_name}]\n"
            f"Here is a complete TechnicalBlueprint JSON example aligned with the {pattern_display_name} pattern.\n\n"
            f"```json\n{example_json}\n```\n"
        )

        if _apply_pattern_guidance(agent, guidance):
            logger.info(f"✓ Injected TechnicalBlueprint example for {pattern_display_name} into {agent.name}")
        else:
            logger.warning(f"Pattern guidance injection failed for {agent.name}")

    except Exception as e:
        logger.error(f"Error in inject_workflow_architect_guidance: {e}", exc_info=True)


def inject_workflow_implementation_guidance(agent, messages: List[Dict[str, Any]]) -> None:
    """
    AG2 update_agent_state hook for WorkflowImplementationAgent.
    Injects pattern-specific agent coordination guidance into system message.

    WorkflowImplementationAgent OUTPUT FORMAT (PhaseAgents JSON):
    {
      "PhaseAgents": {
        "phase_agents": [
          {
            "phase_index": <int>,
            "agents": [
              {
                "agent_name": "<string>",
                "description": "<string>",
                "human_interaction": "context|approval|none",
                "agent_tools": [
                  {
                    "name": "<string>",
                    "integration": "<string>|null",
                    "purpose": "<string>",
                    "interaction_mode": "inline|artifact|none"  // Optional, defaults to "none" when omitted
                  }
                ],
                "lifecycle_tools": [
                  {
                    "name": "<string>",
                    "integration": "<string>|null",
                    "purpose": "<string>",
                    "trigger": "before_agent|after_agent"
                  }
                ],
                "system_hooks": [
                  {
                    "name": "<string>",
                    "purpose": "<string>"
                  }
                ]
              }
            ]
          }
        ]
      }
    }
    """
    try:
        pattern = _get_pattern_from_context(agent)
        if not pattern:
            logger.debug(f"No pattern available for {agent.name}, skipping guidance injection")
            return

        pattern_id = pattern.get('id')
        pattern_name = pattern.get('name')
        pattern_display_name = pattern.get('display_name', pattern_name)

        # Pattern-specific complete PhaseAgentsCall JSON examples
        implementation_examples = {
            1: """{
  "PhaseAgents": {
    "phase_agents": [
      {
        "phase_index": 0,
        "agents": [
          {
            "agent_name": "SupportIntakeRouter",
            "description": "Parses the opening chat, collects account context, classifies the request domain, and seeds routing metrics for downstream specialists.",
            "human_interaction": "none",
            "agent_tools": [
              {"name": "capture_account_context", "integration": "Zendesk", "purpose": "Retrieve account metadata and history", "interaction_mode": "none"},
              {"name": "classify_request_domain", "integration": null, "purpose": "Categorize request type", "interaction_mode": "none"},
              {"name": "calculate_routing_confidence", "integration": null, "purpose": "Score routing certainty", "interaction_mode": "none"},
              {"name": "confirm_routing_decision", "integration": "Zendesk", "purpose": "Surface detected destination for human confirm/override before dispatch", "interaction_mode": "inline"}
            ],
            "lifecycle_tools": [],
            "system_hooks": []
          }
        ]
      },
      {
        "phase_index": 1,
        "agents": [
          {
            "agent_name": "SpecialistOrchestrator",
            "description": "Scores eligible queues, dispatches the highest-fit specialist, and hands off enriched context bundles with routing confidence attached.",
            "human_interaction": "none",
            "agent_tools": [
              {"name": "score_specialist_queues", "integration": null, "purpose": "Rank available specialists", "interaction_mode": "none"},
              {"name": "dispatch_specialist", "integration": "Zendesk", "purpose": "Route to best-fit agent", "interaction_mode": "none"}
            ],
            "lifecycle_tools": [],
            "system_hooks": []
          }
        ]
      },
      {
        "phase_index": 2,
        "agents": [
          {
            "agent_name": "ResolutionSpecialist",
            "description": "Works the issue end-to-end, captures disposition details, and syncs the post-chat summary back into CRM analytics.",
            "human_interaction": "none",
            "agent_tools": [
              {"name": "resolve_customer_issue", "integration": "Notion", "purpose": "Access solution articles", "interaction_mode": "none"},
              {"name": "share_resolution_summary", "integration": "Zendesk", "purpose": "Deliver resolution package for user acknowledgement and CRM logging", "interaction_mode": "artifact"}
            ],
            "lifecycle_tools": [],
            "system_hooks": []
          }
        ]
      }
    ]
  }
}""",
            2: """{
  "PhaseAgents": {
    "phase_agents": [
      {
        "phase_index": 0,
        "agents": [
          {
            "agent_name": "IncidentTriageAgent",
            "description": "Ingests P1 alerts, runs baseline diagnostics, and attempts scripted remediation before any escalation.",
            "human_interaction": "none",
            "agent_tools": [
              {"name": "ingest_p1_alert", "integration": "Datadog", "purpose": "Pull alert metadata and context", "interaction_mode": "none"},
              {"name": "run_baseline_diagnostics", "integration": null, "purpose": "Execute standard diagnostics", "interaction_mode": "none"},
              {"name": "attempt_auto_remediation", "integration": null, "purpose": "Run automated fixes", "interaction_mode": "none"},
              {"name": "acknowledge_incident_brief", "integration": null, "purpose": "Render inline incident card for responder confirmation before tiering", "interaction_mode": "inline"}
            ],
            "lifecycle_tools": [],
            "system_hooks": []
          }
        ]
      },
      {
        "phase_index": 1,
        "agents": [
          {
            "agent_name": "EscalationCoordinator",
            "description": "Evaluates recovery confidence, packages investigation context, and triggers the next response tier when thresholds are missed.",
            "human_interaction": "none",
            "agent_tools": [
              {"name": "evaluate_recovery_confidence", "integration": null, "purpose": "Score recovery likelihood", "interaction_mode": "none"},
              {"name": "package_incident_context", "integration": null, "purpose": "Bundle incident details", "interaction_mode": "none"},
              {"name": "promote_response_tier", "integration": "PagerDuty", "purpose": "Escalate to next level", "interaction_mode": "none"}
            ],
            "lifecycle_tools": [],
            "system_hooks": []
          }
        ]
      },
      {
        "phase_index": 2,
        "agents": [
          {
            "agent_name": "SRELeadAgent",
            "description": "Runs advanced mitigation playbooks, coordinates with the human incident commander, and publishes stakeholder status updates.",
            "human_interaction": "approval",
            "agent_tools": [
              {"name": "execute_mitigation_playbook", "integration": null, "purpose": "Run advanced remediation", "interaction_mode": "none"},
              {"name": "publish_status_update", "integration": "Slack", "purpose": "Broadcast incident status", "interaction_mode": "none"},
              {"name": "publish_postmortem_outline", "integration": "StatusPage", "purpose": "Deliver artifact summarizing mitigation and follow-ups for sign-off", "interaction_mode": "artifact"}
            ],
            "lifecycle_tools": [
              {"name": "allocate_incident_db_connection", "integration": null, "purpose": "Establish database connection pool for incident data retrieval", "trigger": "before_agent"},
              {"name": "release_incident_db_connection", "integration": null, "purpose": "Close database connections and log query metrics", "trigger": "after_agent"}
            ],
            "system_hooks": [
              {"name": "update_agent_state", "purpose": "Inject live incident severity data and SRE runbook references into system message"}
            ]
          }
        ]
      }
    ]
  }
}""",
            3: """{
  "PhaseAgents": {
    "phase_agents": [
      {
        "phase_index": 0,
        "agents": [
          {
            "agent_name": "CampaignBriefFacilitator",
            "description": "Captures campaign goals, personas, and acceptance criteria while logging inspiration assets for the sprint.",
            "human_interaction": "context",
            "agent_tools": [
              {"name": "capture_campaign_brief", "integration": "Notion", "purpose": "Gather campaign requirements", "interaction_mode": "none"},
              {"name": "log_reference_assets", "integration": "Notion", "purpose": "Store inspiration materials", "interaction_mode": "none"}
            ],
            "lifecycle_tools": [],
            "system_hooks": []
          }
        ]
      },
      {
        "phase_index": 1,
        "agents": [
          {
            "agent_name": "LaunchCopyGenerator",
            "description": "Generates messaging variants aligned to the brief and stores rationale for each headline and CTA.",
            "human_interaction": "none",
            "agent_tools": [
              {"name": "generate_launch_copy", "integration": "OpenAI", "purpose": "Create campaign copy variants", "interaction_mode": "none"},
              {"name": "record_generation_rationale", "integration": "Notion", "purpose": "Log creative decisions", "interaction_mode": "none"}
            ],
            "lifecycle_tools": [],
            "system_hooks": []
          }
        ]
      },
      {
        "phase_index": 2,
        "agents": [
          {
            "agent_name": "StakeholderReviewAgent",
            "description": "Collects structured reviewer feedback, scores messaging pillars, and flags blockers requiring human attention.",
            "human_interaction": "approval",
            "agent_tools": [
              {"name": "collect_structured_feedback", "integration": "GoogleDocs", "purpose": "Render artifact form so reviewers can score pillars and submit revisions", "interaction_mode": "artifact"},
              {"name": "score_messaging_pillars", "integration": null, "purpose": "Evaluate content quality", "interaction_mode": "none"},
              {"name": "flag_campaign_blockers", "integration": "GoogleDocs", "purpose": "Surface approval issues", "interaction_mode": "none"}
            ],
            "lifecycle_tools": [],
            "system_hooks": [
              {"name": "update_agent_state", "purpose": "Inject dynamic brand guidelines and approval criteria from campaign context"},
              {"name": "process_message_before_send", "purpose": "Format feedback summaries with color-coded severity indicators before display"}
            ]
          }
        ]
      },
      {
        "phase_index": 3,
        "agents": [
          {
            "agent_name": "StakeholderApprovalAgent",
            "description": "Presents the approval gate summary, collects sign-off decisions, and logs rationale for audit.",
            "human_interaction": "approval",
            "agent_tools": [
              {"name": "approve_final_copy", "integration": "Notion", "purpose": "Inline approval widget capturing decision and rationale", "interaction_mode": "inline"}
            ],
            "lifecycle_tools": [],
            "system_hooks": []
          },
          {
            "agent_name": "LaunchRevisionAgent",
            "description": "Applies accepted feedback, updates approval gate status, and re-triggers the review loop when needed.",
            "human_interaction": "none",
            "agent_tools": [
              {"name": "apply_feedback_actions", "integration": "Notion", "purpose": "Update content based on feedback", "interaction_mode": "none"},
              {"name": "update_approval_status", "integration": "Notion", "purpose": "Track approval state", "interaction_mode": "none"}
            ],
            "lifecycle_tools": [],
            "system_hooks": []
          }
        ]
      }
    ]
  }
}""",
            4: """{
  "PhaseAgents": {
    "phase_agents": [
      {
        "phase_index": 0,
        "agents": [
          {
            "agent_name": "ExecutiveStrategyLead",
            "description": "Breaks down market entry objectives, assigns workstreams, and broadcasts governance guidance to managers.",
            "human_interaction": "none",
            "agent_tools": [
              {"name": "decompose_market_objectives", "integration": "Notion", "purpose": "Structure market analysis tasks", "interaction_mode": "none"},
              {"name": "assign_workstream_managers", "integration": null, "purpose": "Delegate research workstreams", "interaction_mode": "none"},
              {"name": "publish_governance_brief", "integration": "Notion", "purpose": "Share strategy guidelines", "interaction_mode": "none"},
              {"name": "share_strategy_overview", "integration": "Notion", "purpose": "Deliver artifact briefing executives and managers on objectives and guardrails", "interaction_mode": "artifact"}
            ],
            "lifecycle_tools": [],
            "system_hooks": []
          }
        ]
      },
      {
        "phase_index": 1,
        "agents": [
          {
            "agent_name": "DemandResearchManager",
            "description": "Designs demand research backlog, sets metrics, and synchronizes expectations with specialists.",
            "human_interaction": "none",
            "agent_tools": [
              {"name": "plan_demand_research", "integration": "Notion", "purpose": "Define demand analysis scope", "interaction_mode": "none"},
              {"name": "define_success_metrics", "integration": null, "purpose": "Set research KPIs", "interaction_mode": "none"}
            ],
            "lifecycle_tools": [],
            "system_hooks": []
          },
          {
            "agent_name": "RegulatoryResearchManager",
            "description": "Frames regulatory investigation tasks, collects compliance questions, and aligns review cadence.",
            "human_interaction": "none",
            "agent_tools": [
              {"name": "plan_regulatory_research", "integration": "Notion", "purpose": "Structure compliance review", "interaction_mode": "none"},
              {"name": "log_compliance_questions", "integration": "Notion", "purpose": "Track regulatory queries", "interaction_mode": "none"}
            ],
            "lifecycle_tools": [],
            "system_hooks": []
          },
          {
            "agent_name": "WorkstreamStatusManager",
            "description": "Collects inline risk updates from managers and escalates blockers back to the executive hub.",
            "human_interaction": "context",
            "agent_tools": [
              {"name": "capture_risk_update", "integration": "Notion", "purpose": "Inline capture of risk updates with severity and owner", "interaction_mode": "inline"}
            ],
            "lifecycle_tools": [],
            "system_hooks": []
          },
          {
            "agent_name": "CompetitiveLandscapeManager",
            "description": "Structures competitive analysis workstream and tracks interim insights coming up from specialists.",
            "human_interaction": "none",
            "agent_tools": [
              {"name": "plan_competitive_analysis", "integration": "Notion", "purpose": "Define competitor research tasks", "interaction_mode": "none"},
              {"name": "track_specialist_updates", "integration": null, "purpose": "Monitor research progress", "interaction_mode": "none"}
            ],
            "lifecycle_tools": [],
            "system_hooks": []
          }
        ]
      },
      {
        "phase_index": 2,
        "agents": [
          {
            "agent_name": "DemandSpecialist",
            "description": "Executes demand-side research, benchmarks TAM/SAM, and passes synthesized notes back to managers.",
            "human_interaction": "none",
            "agent_tools": [
              {"name": "collect_demand_signals", "integration": "Perplexity", "purpose": "Gather market data", "interaction_mode": "none"},
              {"name": "benchmark_market_size", "integration": null, "purpose": "Quantify TAM/SAM", "interaction_mode": "none"}
            ],
            "lifecycle_tools": [],
            "system_hooks": [],
            "integrations": ["Perplexity"]
          },
          {
            "agent_name": "RegulatorySpecialist",
            "description": "Analyzes regulatory filings, identifies licensing hurdles, and escalates risks to managers.",
            "human_interaction": "none",
            "agent_tools": [
              {"name": "analyze_regulatory_climate", "integration": "Perplexity", "purpose": "Review compliance landscape", "interaction_mode": "none"},
              {"name": "log_license_requirements", "integration": "Notion", "purpose": "Document licensing needs", "interaction_mode": "none"}
            ],
            "lifecycle_tools": [],
            "system_hooks": []
          },
          {
            "agent_name": "CompetitiveSpecialist",
            "description": "Profiles competitors, tracks pricing models, and relays differentiators for executive synthesis.",
            "human_interaction": "none",
            "agent_tools": [
              {"name": "profile_competitors", "integration": "Perplexity", "purpose": "Analyze competitor landscape", "interaction_mode": "none"},
              {"name": "analyze_pricing_models", "integration": null, "purpose": "Study pricing strategies", "interaction_mode": "none"}
            ],
            "lifecycle_tools": [],
            "system_hooks": []
          }
        ]
      },
      {
        "phase_index": 3,
        "agents": [
          {
            "agent_name": "ExecutiveDecisionAgent",
            "description": "Aggregates manager findings, prepares the go/no-go briefing, and captures final decision rationale.",
            "human_interaction": "approval",
            "agent_tools": [
              {"name": "aggregate_workstream_findings", "integration": "Notion", "purpose": "Synthesize research outputs", "interaction_mode": "none"},
              {"name": "prepare_go_no_go_brief", "integration": "Notion", "purpose": "Generate decision document", "interaction_mode": "none"}
            ],
            "lifecycle_tools": [],
            "system_hooks": []
          }
        ]
      }
    ]
  }
}""",
            5: """{
  "PhaseAgents": {
    "phase_agents": [
      {
        "phase_index": 0,
        "agents": [
          {
            "agent_name": "CampaignFacilitator",
            "description": "Aligns campaign goals, surfaces prior high performers, and seeds the inspiration backlog for collaborators.",
            "human_interaction": "context",
            "agent_tools": [
              {"name": "collect_campaign_goals", "integration": "Notion", "purpose": "Gather campaign objectives", "interaction_mode": "inline"},
              {"name": "surface_reference_assets", "integration": "Notion", "purpose": "Pull previous successes", "interaction_mode": "none"}
            ],
            "lifecycle_tools": [],
            "system_hooks": []
          }
        ]
      },
      {
        "phase_index": 1,
        "agents": [
          {
            "agent_name": "CopyIdeationPartner",
            "description": "Generates copy hooks, tags emerging themes, and maintains the shared idea pool for the room.",
            "human_interaction": "context",
            "agent_tools": [
              {"name": "generate_copy_hooks", "integration": null, "purpose": "Create messaging variants", "interaction_mode": "none"},
              {"name": "tag_emerging_themes", "integration": "Notion", "purpose": "Categorize ideas", "interaction_mode": "none"},
              {"name": "update_idea_pool", "integration": "Notion", "purpose": "Track brainstorm progress", "interaction_mode": "none"},
              {"name": "submit_brainstorm_ideas", "integration": "Notion", "purpose": "Inline idea capture so contributors can log hooks without leaving chat", "interaction_mode": "inline"}
            ],
            "lifecycle_tools": [],
            "system_hooks": []
          },
          {
            "agent_name": "DesignIdeationPartner",
            "description": "Proposes visual directions, drafts quick wireframes, and syncs with the copy stream on core concepts.",
            "human_interaction": "context",
            "agent_tools": [
              {"name": "propose_visual_directions", "integration": "Figma", "purpose": "Generate design concepts", "interaction_mode": "artifact"},
              {"name": "draft_wireframe_sketches", "integration": "Figma", "purpose": "Create visual mockups", "interaction_mode": "artifact"}
            ],
            "lifecycle_tools": [],
            "system_hooks": []
          },
          {
            "agent_name": "GrowthSignalsSynthesizer",
            "description": "Pulls performance signals, spots gaps, and posts optimization prompts to guide the jam.",
            "human_interaction": "none",
            "agent_tools": [
              {"name": "pull_performance_signals", "integration": "GoogleAnalytics", "purpose": "Retrieve campaign metrics", "interaction_mode": "none"},
              {"name": "identify_theme_gaps", "integration": null, "purpose": "Detect missing coverage", "interaction_mode": "none"}
            ],
            "lifecycle_tools": [],
            "system_hooks": []
          }
        ]
      },
      {
        "phase_index": 2,
        "agents": [
          {
            "agent_name": "ContentAssemblerAgent",
            "description": "Builds draft channel assets, coordinates stakeholder previews, and records readiness notes for each surface.",
            "human_interaction": "approval",
            "agent_tools": [
              {"name": "assemble_channel_assets", "integration": "HubSpot", "purpose": "Compile campaign materials", "interaction_mode": "artifact"},
              {"name": "coordinate_stakeholder_preview", "integration": null, "purpose": "Gather final feedback", "interaction_mode": "inline"},
              {"name": "review_asset_variants", "integration": "HubSpot", "purpose": "Deliver artifact board of creative variants for quick stakeholder decisions", "interaction_mode": "artifact"}
            ],
            "lifecycle_tools": [],
            "system_hooks": []
          },
          {
            "agent_name": "ChannelPackagingAgent",
            "description": "Formats assets for email, social, and landing pages while queuing scheduling metadata.",
            "human_interaction": "none",
            "agent_tools": [
              {"name": "format_multi_channel_assets", "integration": "HubSpot", "purpose": "Prepare platform-specific content", "interaction_mode": "artifact"},
              {"name": "queue_scheduling_metadata", "integration": "HubSpot", "purpose": "Set publication timing", "interaction_mode": "none"}
            ],
            "lifecycle_tools": [],
            "system_hooks": []
          }
        ]
      }
    ]
  }
}""",
            6: """{
  "PhaseAgents": {
    "phase_agents": [
      {
        "phase_index": 0,
        "agents": [
          {
            "agent_name": "ApplicationIntakeAgent",
            "description": "Validates submitted documents, normalizes applicant data, and halts the run when mandatory inputs are missing.",
            "human_interaction": "none",
            "agent_tools": [
              {"name": "validate_required_documents", "integration": "Salesforce", "purpose": "Check document completeness", "interaction_mode": "none"},
              {"name": "normalize_applicant_profile", "integration": "Salesforce", "purpose": "Standardize applicant data", "interaction_mode": "none"},
              {"name": "collect_supporting_documents", "integration": "Salesforce", "purpose": "Inline checklist prompting applicant for missing uploads", "interaction_mode": "inline"}
            ],
            "lifecycle_tools": [
              {"name": "validate_intake_prerequisites", "integration": null, "purpose": "Verify all required integrations are available before processing", "trigger": "before_agent"},
              {"name": "log_intake_metrics", "integration": null, "purpose": "Record intake success rate and processing time", "trigger": "after_agent"}
            ],
            "system_hooks": []
          }
        ]
      },
      {
        "phase_index": 1,
        "agents": [
          {
            "agent_name": "RiskComplianceAgent",
            "description": "Runs credit, fraud, and KYC checks sequentially and annotates the application with risk findings.",
            "human_interaction": "none",
            "agent_tools": [
              {"name": "run_credit_report", "integration": "Experian", "purpose": "Pull credit history", "interaction_mode": "none"},
              {"name": "execute_fraud_screen", "integration": null, "purpose": "Detect fraud signals", "interaction_mode": "none"},
              {"name": "log_kyc_findings", "integration": "Salesforce", "purpose": "Document KYC results", "interaction_mode": "none"}
            ],
            "lifecycle_tools": [],
            "system_hooks": []
          }
        ]
      },
      {
        "phase_index": 2,
        "agents": [
          {
            "agent_name": "UnderwritingDecisionAgent",
            "description": "Applies underwriting policy, calculates proposed terms, and escalates edge cases for manual review.",
            "human_interaction": "none",
            "agent_tools": [
              {"name": "apply_underwriting_policy", "integration": null, "purpose": "Evaluate loan eligibility", "interaction_mode": "none"},
              {"name": "calculate_offer_terms", "integration": null, "purpose": "Determine loan parameters", "interaction_mode": "none"},
              {"name": "share_underwriting_package", "integration": "Salesforce", "purpose": "Deliver artifact summarizing approval or decline rationale for review", "interaction_mode": "artifact"}
            ],
            "lifecycle_tools": [],
            "system_hooks": []
          }
        ]
      },
      {
        "phase_index": 3,
        "agents": [
          {
            "agent_name": "OfferFulfillmentAgent",
            "description": "Generates the borrower offer packet, triggers borrower notifications, and syncs fulfillment status back to core banking.",
            "human_interaction": "approval",
            "agent_tools": [
              {"name": "generate_offer_packet", "integration": "Salesforce", "purpose": "Create loan offer document", "interaction_mode": "artifact"},
              {"name": "notify_borrower", "integration": "Twilio", "purpose": "Send offer to applicant", "interaction_mode": "none"},
              {"name": "sync_fulfillment_status", "integration": "Salesforce", "purpose": "Update loan status", "interaction_mode": "none"}
            ],
            "lifecycle_tools": [],
            "system_hooks": []
          }
        ]
      }
    ]
  }
}""",
            7: """{
  "PhaseAgents": {
    "phase_agents": [
      {
        "phase_index": 0,
        "agents": [
          {
            "agent_name": "PlanningCoordinator",
            "description": "Prepares the scenario brief, distributes constraints, and locks evaluation metrics for downstream models.",
            "human_interaction": "none",
            "agent_tools": [
              {"name": "compile_scenario_brief", "integration": "Notion", "purpose": "Structure forecast requirements", "interaction_mode": "none"},
              {"name": "lock_evaluation_metrics", "integration": "Notion", "purpose": "Define comparison criteria", "interaction_mode": "none"}
            ],
            "lifecycle_tools": [],
            "system_hooks": []
          }
        ]
      },
      {
        "phase_index": 1,
        "agents": [
          {
            "agent_name": "StatisticalForecastAgent",
            "description": "Builds statistical projections, documents methodology, and posts forecast payload for comparison.",
            "human_interaction": "none",
            "agent_tools": [
              {"name": "train_statistical_model", "integration": null, "purpose": "Build time-series model", "interaction_mode": "none"},
              {"name": "generate_statistical_projection", "integration": null, "purpose": "Create forecast output", "interaction_mode": "none"},
              {"name": "publish_forecast_payload", "integration": "Notion", "purpose": "Share results", "interaction_mode": "artifact"},
              {"name": "submit_forecast_bundle", "integration": "Notion", "purpose": "Inline uploader bundling assumptions, charts, and diagnostics per model", "interaction_mode": "inline"}
            ],
            "lifecycle_tools": [],
            "system_hooks": []
          },
          {
            "agent_name": "CausalForecastAgent",
            "description": "Constructs causal models, incorporates exogenous signals, and outputs scenario-aware forecasts.",
            "human_interaction": "none",
            "agent_tools": [
              {"name": "ingest_exogenous_signals", "integration": null, "purpose": "Load external variables", "interaction_mode": "none"},
              {"name": "generate_causal_projection", "integration": null, "purpose": "Build causal forecast", "interaction_mode": "none"}
            ],
            "lifecycle_tools": [],
            "system_hooks": []
          },
          {
            "agent_name": "HeuristicForecastAgent",
            "description": "Applies heuristics, stress-tests edge cases, and contributes alternative forecast bands.",
            "human_interaction": "none",
            "agent_tools": [
              {"name": "apply_heuristic_rules", "integration": null, "purpose": "Generate rule-based forecast", "interaction_mode": "none"},
              {"name": "stress_test_edge_cases", "integration": null, "purpose": "Test extreme scenarios", "interaction_mode": "none"}
            ],
            "lifecycle_tools": [],
            "system_hooks": []
          }
        ]
      },
      {
        "phase_index": 2,
        "agents": [
          {
            "agent_name": "ForecastEvaluator",
            "description": "Scores each forecast against accuracy and volatility thresholds, then recommends the winning model.",
            "human_interaction": "approval",
            "agent_tools": [
              {"name": "score_forecast_accuracy", "integration": null, "purpose": "Evaluate model performance", "interaction_mode": "none"},
              {"name": "analyze_volatility", "integration": null, "purpose": "Assess forecast stability", "interaction_mode": "none"},
              {"name": "recommend_preferred_model", "integration": "Notion", "purpose": "Select best forecast", "interaction_mode": "artifact"},
              {"name": "compare_forecasts", "integration": "Notion", "purpose": "Deliver artifact table comparing submissions side-by-side for decision", "interaction_mode": "artifact"}
            ],
            "lifecycle_tools": [],
            "system_hooks": [
              {"name": "process_message_before_send", "purpose": "Transform forecast comparison tables into user-friendly visualizations before display"}
            ]
          }
        ]
      },
      {
        "phase_index": 3,
        "agents": [
          {
            "agent_name": "RecommendationPublisher",
            "description": "Publishes the selected forecast, documents rationale, and distributes the planning brief to stakeholders.",
            "human_interaction": "context",
            "agent_tools": [
              {"name": "publish_selected_forecast", "integration": "Notion", "purpose": "Share final forecast", "interaction_mode": "artifact"},
              {"name": "document_selection_rationale", "integration": "Notion", "purpose": "Explain choice", "interaction_mode": "none"}
            ],
            "lifecycle_tools": [],
            "system_hooks": []
          }
        ]
      }
    ]
  }
}""",
            8: """{
  "PhaseAgents": {
    "phase_agents": [
      {
        "phase_index": 0,
        "agents": [
          {
            "agent_name": "VendorIntakeCoordinator",
            "description": "Validates onboarding submissions, determines required spokes, and assembles briefing packets for reviewers.",
            "human_interaction": "none",
            "agent_tools": [
              {"name": "validate_vendor_submission", "integration": "Salesforce", "purpose": "Check submission completeness", "interaction_mode": "none"},
              {"name": "determine_required_spokes", "integration": null, "purpose": "Identify review tracks", "interaction_mode": "none"},
              {"name": "assemble_briefing_packet", "integration": "Salesforce", "purpose": "Package review materials", "interaction_mode": "artifact"},
              {"name": "capture_vendor_profile", "integration": "Salesforce", "purpose": "Inline intake wizard capturing company facts before dispatch", "interaction_mode": "inline"}
            ],
            "lifecycle_tools": [],
            "system_hooks": []
          }
        ]
      },
      {
        "phase_index": 1,
        "agents": [
          {
            "agent_name": "FinanceReviewAgent",
            "description": "Runs financial risk checks, verifies banking details, and reports status back to the hub.",
            "human_interaction": "none",
            "agent_tools": [
              {"name": "run_financial_due_diligence", "integration": null, "purpose": "Assess financial risk", "interaction_mode": "none"},
              {"name": "verify_banking_details", "integration": "Stripe", "purpose": "Validate payment info", "interaction_mode": "none"},
              {"name": "post_finance_status", "integration": "Salesforce", "purpose": "Update review status", "interaction_mode": "none"}
            ],
            "lifecycle_tools": [],
            "system_hooks": []
          },
          {
            "agent_name": "SecurityReviewAgent",
            "description": "Performs security questionnaire analysis, assesses risk exceptions, and updates the hub registry.",
            "human_interaction": "none",
            "agent_tools": [
              {"name": "analyze_security_questionnaire", "integration": "Salesforce", "purpose": "Review security posture", "interaction_mode": "none"},
              {"name": "assess_security_risk", "integration": null, "purpose": "Score security compliance", "interaction_mode": "none"},
              {"name": "post_security_status", "integration": "Salesforce", "purpose": "Update review status", "interaction_mode": "none"}
            ],
            "lifecycle_tools": [],
            "system_hooks": []
          },
          {
            "agent_name": "LegalReviewAgent",
            "description": "Reviews contract terms, flags compliance gaps, and publishes legal clearance status.",
            "human_interaction": "none",
            "agent_tools": [
              {"name": "review_contract_terms", "integration": "DocuSign", "purpose": "Analyze legal agreements", "interaction_mode": "none"},
              {"name": "flag_compliance_gaps", "integration": "Salesforce", "purpose": "Identify legal issues", "interaction_mode": "none"},
              {"name": "post_legal_status", "integration": "Salesforce", "purpose": "Update review status", "interaction_mode": "none"}
            ],
            "lifecycle_tools": [],
            "system_hooks": []
          }
        ]
      },
      {
        "phase_index": 2,
        "agents": [
          {
            "agent_name": "RiskAlignmentMediator",
            "description": "Monitors spoke progress, resolves conflicting decisions, and surfaces outstanding blockers.",
            "human_interaction": "none",
            "agent_tools": [
              {"name": "monitor_spoke_progress", "integration": "Salesforce", "purpose": "Track review completion", "interaction_mode": "none"},
              {"name": "resolve_risk_conflicts", "integration": null, "purpose": "Mediate cross-spoke issues", "interaction_mode": "none"},
              {"name": "publish_risk_clearance", "integration": "Salesforce", "purpose": "Deliver artifact summarizing finance/security/legal findings for approval", "interaction_mode": "artifact"}
            ],
            "lifecycle_tools": [],
            "system_hooks": []
          }
        ]
      },
      {
        "phase_index": 3,
        "agents": [
          {
            "agent_name": "OnboardingFinalizer",
            "description": "Compiles approvals, triggers account provisioning, and delivers the onboarding summary to the requester.",
            "human_interaction": "approval",
            "agent_tools": [
              {"name": "compile_final_approvals", "integration": "Salesforce", "purpose": "Aggregate review decisions", "interaction_mode": "artifact"},
              {"name": "trigger_account_provisioning", "integration": "Salesforce", "purpose": "Activate vendor account", "interaction_mode": "none"}
            ],
            "lifecycle_tools": [],
            "system_hooks": []
          }
        ]
      }
    ]
  }
}""",
            9: """{
  "PhaseAgents": {
    "phase_agents": [
      {
        "phase_index": 0,
        "agents": [
          {
            "agent_name": "AppTriageAgent",
            "description": "Captures personas, critical features, and integrations, then emits prioritized research, design, and build task queues.",
            "human_interaction": "none",
            "agent_tools": [
              {"name": "capture_app_requirements", "integration": "Jira", "purpose": "Gather app specifications", "interaction_mode": "none"},
              {"name": "emit_typed_task_queues", "integration": "Jira", "purpose": "Create categorized task lists", "interaction_mode": "none"},
              {"name": "prioritize_foundry_backlog", "integration": "Jira", "purpose": "Sequence work items", "interaction_mode": "none"},
              {"name": "classify_incoming_requests", "integration": "Jira", "purpose": "Inline triage to label new requests with stream and urgency", "interaction_mode": "inline"}
            ],
            "lifecycle_tools": [],
            "system_hooks": []
          }
        ]
      },
      {
        "phase_index": 1,
        "agents": [
          {
            "agent_name": "DependencyPlanner",
            "description": "Links task dependencies, sequences execution order, and flags prerequisite gaps to unblock delivery.",
            "human_interaction": "none",
            "agent_tools": [
              {"name": "link_task_dependencies", "integration": "Jira", "purpose": "Map task relationships", "interaction_mode": "none"},
              {"name": "sequence_execution_order", "integration": "Jira", "purpose": "Define build sequence", "interaction_mode": "none"}
            ],
            "lifecycle_tools": [
              {"name": "load_task_dependency_graph", "integration": null, "purpose": "Load existing task graph from cache before planning", "trigger": "before_agent"},
              {"name": "persist_dependency_state", "integration": null, "purpose": "Save updated dependency graph to cache for downstream agents", "trigger": "after_agent"}
            ],
            "system_hooks": []
          }
        ]
      },
      {
        "phase_index": 2,
        "agents": [
          {
            "agent_name": "ResearchScout",
            "description": "Executes research tasks, summarizes competitor benchmarks, and archives findings for design alignment.",
            "human_interaction": "none",
            "agent_tools": [
              {"name": "conduct_domain_research", "integration": "Perplexity", "purpose": "Gather domain intelligence", "interaction_mode": "none"},
              {"name": "summarize_competitor_benchmarks", "integration": "Perplexity", "purpose": "Analyze competitor features", "interaction_mode": "none"}
            ],
            "lifecycle_tools": [],
            "system_hooks": []
          },
          {
            "agent_name": "UXWireframeAgent",
            "description": "Drafts wireframes that map to research insights and exports assets for build-ready handoff.",
            "human_interaction": "none",
            "agent_tools": [
              {"name": "draft_wireframes", "integration": "Figma", "purpose": "Create UI mockups", "interaction_mode": "artifact"},
              {"name": "export_design_assets", "integration": "Figma", "purpose": "Package design files", "interaction_mode": "artifact"}
            ],
            "lifecycle_tools": [],
            "system_hooks": []
          }
        ]
      },
      {
        "phase_index": 3,
        "agents": [
          {
            "agent_name": "AppScaffoldBuilder",
            "description": "Generates the application skeleton, applies integration stubs, and runs scaffold unit tests.",
            "human_interaction": "none",
            "agent_tools": [
              {"name": "generate_app_skeleton", "integration": "GitHub", "purpose": "Create code structure", "interaction_mode": "none"},
              {"name": "apply_integration_stubs", "integration": "GitHub", "purpose": "Wire API placeholders", "interaction_mode": "none"},
              {"name": "run_scaffold_tests", "integration": "GitHubActions", "purpose": "Validate build", "interaction_mode": "none"},
              {"name": "share_release_candidate", "integration": "GitHub", "purpose": "Deliver artifact with build status, docs, and open tasks for approval", "interaction_mode": "artifact"}
            ],
            "lifecycle_tools": [],
            "system_hooks": []
          },
          {
            "agent_name": "IntegrationAutomationAgent",
            "description": "Configures required integrations, provisions environment secrets, and logs coverage for each module.",
            "human_interaction": "none",
            "agent_tools": [
              {"name": "configure_integrations", "integration": null, "purpose": "Set up API connections", "interaction_mode": "none"},
              {"name": "provision_environment_secrets", "integration": "GitHub", "purpose": "Configure credentials", "interaction_mode": "none"}
            ],
            "lifecycle_tools": [],
            "system_hooks": []
          }
        ]
      },
      {
        "phase_index": 4,
        "agents": [
          {
            "agent_name": "FoundryLeadReviewer",
            "description": "Compiles the runnable build, authors the demo script, and curates the stretch enhancement backlog for stakeholders.",
            "human_interaction": "approval",
            "agent_tools": [
              {"name": "compile_release_bundle", "integration": "GitHubActions", "purpose": "Package deployable artifact", "interaction_mode": "artifact"},
              {"name": "author_demo_script", "integration": "Notion", "purpose": "Create demo documentation", "interaction_mode": "artifact"}
            ],
            "lifecycle_tools": [],
            "system_hooks": []
          }
        ]
      }
    ]
  }
}"""
        }

        example_json = implementation_examples.get(pattern_id)

        if not example_json:
            logger.warning(f"No implementation example found for pattern_id {pattern_id}")
            return

        guidance = (
            f"[PATTERN EXAMPLE - {pattern_display_name}]\n"
            f"Cross-check every TechnicalBlueprint.ui_components entry and mirror it with an agent_tool that uses the same tool name and UI cadence. Set `interaction_mode` to `inline` for structured inputs, `artifact` when the tool renders a review surface, and `none` for agent-only operations.\n"
            f"Here is a complete PhaseAgents JSON example aligned with the {pattern_display_name} pattern.\n\n"
            f"```json\n{example_json}\n```\n"
        )

        if _apply_pattern_guidance(agent, guidance):
            logger.info(f"✓ Injected PhaseAgents example for {pattern_display_name} into {agent.name}")
        else:
            logger.warning(f"Pattern guidance injection failed for {agent.name}")

    except Exception as e:
        logger.error(f"Error in inject_workflow_implementation_guidance: {e}", exc_info=True)


def inject_project_overview_guidance(agent, messages: List[Dict[str, Any]]) -> None:
    """
    AG2 update_agent_state hook for ProjectOverviewAgent.
    Injects comprehensive pattern-specific Mermaid diagram guidance into system message.

    ProjectOverviewAgent OUTPUT FORMAT (MermaidSequenceDiagram JSON):
    {
      "MermaidSequenceDiagram": {
        "workflow_name": "<string>",
        "mermaid_diagram": "<sequence diagram string>",
        "legend": ["<string>"]
      },
      "agent_message": "<string>"
    }
    """
    try:
        pattern = _get_pattern_from_context(agent)
        if not pattern:
            logger.debug(f"No pattern available for {agent.name}, skipping guidance injection")
            return

        pattern_id = pattern.get('id')
        pattern_name = pattern.get('name')
        pattern_display_name = pattern.get('display_name', pattern_name)
        
        # Pattern-specific topology guidance and Mermaid structure
        topology_guidance = {
            1: """**Context-Aware Routing Topology**:
- Hub agent classifies incoming requests and routes to domain-specific specialists
- Use `alt` blocks to represent routing decisions based on domain classification
- Show confidence scoring and specialist selection logic
- Participants: IntakeRouter (hub), DomainSpecialists (spokes), Orchestrator (coordinator)
- Key interactions: Domain classification → Confidence scoring → Specialist routing → Resolution""",
            
            2: """**Escalation Topology**:
- Tier-based escalation with automatic promotion when confidence thresholds not met
- Use nested `alt` blocks to show tier transitions (Tier 1 → Tier 2 → Tier 3)
- Each tier attempts resolution, then escalates if recovery_confidence is low
- Participants: TriageAgent (Tier 1), CoordinatorAgent (Tier 2), ExpertAgent (Tier 3)
- Key interactions: Initial triage → Auto-remediation attempt → Confidence check → Escalate → Expert resolution""",
            
            3: """**Feedback Loop Topology**:
- Single artifact iteratively refined through review cycles until approval
- Use `loop` blocks to show iteration with `alt` blocks inside for approval decisions
- Show draft generation → review → feedback → revision cycle
- Participants: Generator, Reviewer, Reviser
- Key interactions: Generate draft → Review artifact → alt(Approved → Done | Rejected → Revise) → Loop back""",
            
            4: """**Hierarchical Topology**:
- Multi-tier delegation: Executive → Managers → Specialists → Back to Executive
- Show workstream decomposition with parallel specialist execution
- Use Note blocks to show manager coordination and specialist deep dives
- Participants: ExecutiveLead (top), Managers (middle), Specialists (bottom)
- Key interactions: Decompose → Delegate to managers → Managers assign specialists → Specialists report → Synthesize""",
            
            5: """**Organic Topology**:
- Flexible, exploratory conversation without fixed sequence
- Show optional transitions and dynamic routing with multiple possible paths
- Use Note blocks to indicate flexible collaboration points
- Participants: Facilitator, Multiple collaborative partners
- Key interactions: Brief → Collaborative exploration (flexible order) → Synthesis""",
            
            6: """**Pipeline Topology**:
- Linear sequential phases where each step depends on the previous
- Show clear phase transitions with validation gates
- Use `alt` blocks for approval/rejection paths at gate points
- Participants: One agent per phase in strict sequence
- Key interactions: Phase0 → Validate → Phase1 → Validate → Phase2 → Complete""",
            
            7: """**Redundant Topology**:
- Multiple specialists generate independent solutions in parallel (shown sequentially)
- Coordinator dispatches to all specialists, then evaluator compares results
- Show parallel execution as sequential nested calls with Note indicating independence
- Participants: Coordinator, Multiple specialists (parallel), Evaluator
- Key interactions: Dispatch → Specialist1 generates → Specialist2 generates → Specialist3 generates → Evaluate → Select best""",
            
            8: """**Star Topology**:
- Hub-and-spoke: Central coordinator gathers data from independent spokes
- Spokes execute in parallel (shown sequentially) then report back to hub
- Hub mediates, synthesizes, and delivers final output
- Participants: Hub (coordinator), Multiple spokes (specialists), Finalizer
- Key interactions: Hub dispatches → Spoke1 gathers → Spoke2 gathers → Spoke3 gathers → Hub synthesizes → Finalize""",
            
            9: """**Triage with Tasks Topology**:
- Task decomposition with strict dependency sequencing
- Show task queues, dependency linking, and staged execution
- Use Note blocks to show task gates (research → design → build dependencies)
- Participants: TriageAgent, DependencyPlanner, Task executors (ordered by dependency)
- Key interactions: Decompose → Link dependencies → Execute Research → Gate → Execute Design → Gate → Execute Build → Review"""
        }
        
        # Pattern-specific complete MermaidSequenceDiagramCall JSON examples
        mermaid_examples = {
            1: """{
  "MermaidSequenceDiagram": {
    "workflow_name": "SaaS Support Domain Router",
    "mermaid_diagram": "sequenceDiagram\\n    participant User\\n    participant SupportIntakeRouter\\n    participant SpecialistOrchestrator\\n    participant ResolutionSpecialist\\n\\n    Note over User,ResolutionSpecialist: Phase 1: Automated Intake & Signal Capture\\n    User->>SupportIntakeRouter: Submit support request\\n    SupportIntakeRouter->>SupportIntakeRouter: capture_account_context (Zendesk)\\n    SupportIntakeRouter->>SupportIntakeRouter: classify_request_domain\\n    SupportIntakeRouter->>SupportIntakeRouter: calculate_routing_confidence\\n    Note over SupportIntakeRouter: Domain classified with confidence score\\n\\n    Note over SupportIntakeRouter,ResolutionSpecialist: Phase 2: Specialist Routing & Engagement\\n    SupportIntakeRouter->>SpecialistOrchestrator: Hand off enriched context\\n    SpecialistOrchestrator->>SpecialistOrchestrator: score_specialist_queues\\n    SpecialistOrchestrator->>SpecialistOrchestrator: dispatch_specialist (Zendesk)\\n    Note over SpecialistOrchestrator: Route to best-fit specialist\\n\\n    Note over SpecialistOrchestrator,ResolutionSpecialist: Phase 3: Resolution & Post-Chat Summary\\n    SpecialistOrchestrator->>ResolutionSpecialist: Transfer to specialist\\n    ResolutionSpecialist->>ResolutionSpecialist: resolve_customer_issue (Notion)\\n    ResolutionSpecialist->>ResolutionSpecialist: sync_resolution_summary (Zendesk)\\n    ResolutionSpecialist->>User: Issue resolved + summary",
    "legend": ["Phase 1: SupportIntakeRouter classifies and scores request", "Phase 2: SpecialistOrchestrator routes to best specialist", "Phase 3: ResolutionSpecialist resolves and logs"]
  },
  "agent_message": "Ready to build this workflow? The routing system will intelligently direct support inquiries through intake, orchestration, and resolution phases. Review the Action Plan above and approve to proceed with implementation."
}""",
            2: """{
  "MermaidSequenceDiagram": {
    "workflow_name": "Cloud Incident Escalation Ladder",
    "mermaid_diagram": "sequenceDiagram\\n    participant User\\n    participant IncidentTriageAgent\\n    participant EscalationCoordinator\\n    participant SRELeadAgent\\n\\n    Note over User,SRELeadAgent: Phase 1: Alert Intake & Baseline Diagnostics\\n    User->>IncidentTriageAgent: P1 alert triggered\\n    IncidentTriageAgent->>IncidentTriageAgent: ingest_p1_alert (Datadog)\\n    IncidentTriageAgent->>IncidentTriageAgent: run_baseline_diagnostics\\n    IncidentTriageAgent->>IncidentTriageAgent: attempt_auto_remediation\\n    Note over IncidentTriageAgent: Attempt automated fixes\\n\\n    Note over IncidentTriageAgent,SRELeadAgent: Phase 2: Tier Promotion & Context Packaging\\n    IncidentTriageAgent->>EscalationCoordinator: Escalate (recovery confidence low)\\n    EscalationCoordinator->>EscalationCoordinator: evaluate_recovery_confidence\\n    EscalationCoordinator->>EscalationCoordinator: package_incident_context\\n    EscalationCoordinator->>EscalationCoordinator: promote_response_tier (PagerDuty)\\n    Note over EscalationCoordinator: Page next tier responder\\n\\n    Note over EscalationCoordinator,SRELeadAgent: Phase 3: Expert Mitigation & Stakeholder Updates\\n    EscalationCoordinator->>SRELeadAgent: Transfer to SRE lead\\n    Note over SRELeadAgent: Human approval required\\n    SRELeadAgent->>SRELeadAgent: execute_mitigation_playbook\\n    SRELeadAgent->>SRELeadAgent: publish_status_update (Slack)\\n    SRELeadAgent->>User: Incident resolved + postmortem",
    "legend": ["Phase 1: IncidentTriageAgent attempts auto-remediation", "Phase 2: EscalationCoordinator evaluates and escalates", "Phase 3: SRELeadAgent executes expert mitigation"]
  },
  "agent_message": "This tiered incident response system coordinates automated triage, escalation, and expert remediation across 4 phases. Review the sequence diagram and approve to begin building your automation."
}""",
            3: """{
  "MermaidSequenceDiagram": {
    "workflow_name": "Product Launch Copy Refinement",
    "mermaid_diagram": "sequenceDiagram\\n    participant User\\n    participant CampaignBriefFacilitator\\n    participant LaunchCopyGenerator\\n    participant StakeholderReviewAgent\\n    participant LaunchRevisionAgent\\n\\n    Note over User,LaunchRevisionAgent: Phase 1: Brief Capture & Acceptance Criteria\\n    User->>CampaignBriefFacilitator: Initiate campaign\\n    Note over CampaignBriefFacilitator: Human context gathering\\n    CampaignBriefFacilitator->>CampaignBriefFacilitator: capture_campaign_brief (Notion)\\n    CampaignBriefFacilitator->>CampaignBriefFacilitator: log_reference_assets (Notion)\\n\\n    Note over CampaignBriefFacilitator,LaunchRevisionAgent: Phase 2: Draft Creation\\n    CampaignBriefFacilitator->>LaunchCopyGenerator: Brief ready\\n    LaunchCopyGenerator->>LaunchCopyGenerator: generate_launch_copy (OpenAI)\\n    LaunchCopyGenerator->>LaunchCopyGenerator: record_generation_rationale (Notion)\\n\\n    Note over LaunchCopyGenerator,LaunchRevisionAgent: Phase 3: Structured Review\\n    LaunchCopyGenerator->>StakeholderReviewAgent: Draft ready\\n    Note over StakeholderReviewAgent: Human approval required\\n    StakeholderReviewAgent->>StakeholderReviewAgent: collect_structured_feedback (GoogleDocs)\\n    StakeholderReviewAgent->>StakeholderReviewAgent: score_messaging_pillars\\n    StakeholderReviewAgent->>StakeholderReviewAgent: flag_campaign_blockers (GoogleDocs)\\n\\n    alt Revision Needed\\n        Note over StakeholderReviewAgent,LaunchRevisionAgent: Phase 4: Revision & Approval\\n        StakeholderReviewAgent->>LaunchRevisionAgent: Feedback provided\\n        LaunchRevisionAgent->>LaunchRevisionAgent: apply_feedback_actions (Notion)\\n        LaunchRevisionAgent->>LaunchRevisionAgent: update_approval_status (Notion)\\n        LaunchRevisionAgent->>StakeholderReviewAgent: Re-submit for review\\n    else Approved\\n        StakeholderReviewAgent->>User: Campaign copy approved\\n    end",
    "legend": ["Phase 1: CampaignBriefFacilitator gathers requirements", "Phase 2: LaunchCopyGenerator creates draft", "Phase 3: StakeholderReviewAgent reviews and scores", "Phase 4: LaunchRevisionAgent applies feedback (loop)"]
  },
  "agent_message": "Action Plan complete: This feedback loop workflow enables brief capture, copy generation, stakeholder review, and iterative revision. Confirm to move forward with agent implementation and tool generation."
}""",
            4: """{
  "MermaidSequenceDiagram": {
    "workflow_name": "Market Entry Intelligence Stack",
    "mermaid_diagram": "sequenceDiagram\\n    participant User\\n    participant ExecutiveStrategyLead\\n    participant DemandMgr as DemandResearchManager\\n    participant RegMgr as RegulatoryResearchManager\\n    participant CompMgr as CompetitiveLandscapeManager\\n    participant DemandSpec as DemandSpecialist\\n    participant RegSpec as RegulatorySpecialist\\n    participant CompSpec as CompetitiveSpecialist\\n    participant ExecutiveDecisionAgent\\n\\n    Note over User,ExecutiveDecisionAgent: Phase 1: Executive Briefing & Workstream Plan\\n    User->>ExecutiveStrategyLead: Request market analysis\\n    ExecutiveStrategyLead->>ExecutiveStrategyLead: decompose_market_objectives (Notion)\\n    ExecutiveStrategyLead->>ExecutiveStrategyLead: assign_workstream_managers\\n    ExecutiveStrategyLead->>ExecutiveStrategyLead: publish_governance_brief (Notion)\\n\\n    Note over ExecutiveStrategyLead,CompSpec: Phase 2: Manager Task Framing\\n    ExecutiveStrategyLead->>DemandMgr: Delegate demand workstream\\n    ExecutiveStrategyLead->>RegMgr: Delegate regulatory workstream\\n    ExecutiveStrategyLead->>CompMgr: Delegate competitive workstream\\n    DemandMgr->>DemandMgr: plan_demand_research (Notion)\\n    RegMgr->>RegMgr: plan_regulatory_research (Notion)\\n    CompMgr->>CompMgr: plan_competitive_analysis (Notion)\\n\\n    Note over DemandMgr,ExecutiveDecisionAgent: Phase 3: Specialist Deep Dives\\n    DemandMgr->>DemandSpec: Assign demand research\\n    RegMgr->>RegSpec: Assign regulatory research\\n    CompMgr->>CompSpec: Assign competitive research\\n    DemandSpec->>DemandSpec: collect_demand_signals (Perplexity)\\n    DemandSpec->>DemandMgr: Report findings\\n    RegSpec->>RegSpec: analyze_regulatory_climate (Perplexity)\\n    RegSpec->>RegMgr: Report findings\\n    CompSpec->>CompSpec: profile_competitors (Perplexity)\\n    CompSpec->>CompMgr: Report findings\\n\\n    Note over CompMgr,ExecutiveDecisionAgent: Phase 4: Executive Synthesis & Go/No-Go\\n    DemandMgr->>ExecutiveDecisionAgent: Demand findings\\n    RegMgr->>ExecutiveDecisionAgent: Regulatory findings\\n    CompMgr->>ExecutiveDecisionAgent: Competitive findings\\n    Note over ExecutiveDecisionAgent: Human approval required\\n    ExecutiveDecisionAgent->>ExecutiveDecisionAgent: aggregate_workstream_findings (Notion)\\n    ExecutiveDecisionAgent->>ExecutiveDecisionAgent: prepare_go_no_go_brief (Notion)\\n    ExecutiveDecisionAgent->>User: Strategic decision brief",
    "legend": ["Phase 1: ExecutiveStrategyLead decomposes objectives", "Phase 2: Managers frame research tasks", "Phase 3: Specialists execute deep dives", "Phase 4: ExecutiveDecisionAgent synthesizes and decides"]
  },
  "agent_message": "The workflow is mapped out with executive delegation, manager coordination, specialist research, and executive synthesis. Review the Action Plan and approve to proceed with implementation."
}""",
            5: """{
  "MermaidSequenceDiagram": {
    "workflow_name": "Omnichannel Campaign Content Studio",
    "mermaid_diagram": "sequenceDiagram\\n    participant User\\n    participant CampaignFacilitator\\n    participant CopyIdeationPartner\\n    participant DesignIdeationPartner\\n    participant GrowthSignalsSynthesizer\\n    participant ContentAssemblerAgent\\n    participant ChannelPackagingAgent\\n\\n    Note over User,ChannelPackagingAgent: Phase 1: Brief Alignment & Inspiration\\n    User->>CampaignFacilitator: Launch campaign sprint\\n    Note over CampaignFacilitator: Human context gathering\\n    CampaignFacilitator->>CampaignFacilitator: collect_campaign_goals (Notion)\\n    CampaignFacilitator->>CampaignFacilitator: surface_reference_assets (Notion)\\n\\n    Note over CampaignFacilitator,ChannelPackagingAgent: Phase 2: Collaborative Concept Jam\\n    CampaignFacilitator->>CopyIdeationPartner: Brief ready\\n    CampaignFacilitator->>DesignIdeationPartner: Brief ready\\n    CampaignFacilitator->>GrowthSignalsSynthesizer: Brief ready\\n    Note over CopyIdeationPartner,GrowthSignalsSynthesizer: Organic collaboration\\n    CopyIdeationPartner->>CopyIdeationPartner: generate_copy_hooks\\n    CopyIdeationPartner->>CopyIdeationPartner: tag_emerging_themes (Notion)\\n    DesignIdeationPartner->>DesignIdeationPartner: propose_visual_directions (Figma)\\n    DesignIdeationPartner->>DesignIdeationPartner: draft_wireframe_sketches (Figma)\\n    GrowthSignalsSynthesizer->>GrowthSignalsSynthesizer: pull_performance_signals (GoogleAnalytics)\\n    GrowthSignalsSynthesizer->>GrowthSignalsSynthesizer: identify_theme_gaps\\n\\n    Note over GrowthSignalsSynthesizer,ChannelPackagingAgent: Phase 3: Asset Assembly & Channel Packaging\\n    CopyIdeationPartner->>ContentAssemblerAgent: Copy concepts\\n    DesignIdeationPartner->>ContentAssemblerAgent: Design concepts\\n    GrowthSignalsSynthesizer->>ContentAssemblerAgent: Performance insights\\n    Note over ContentAssemblerAgent: Human approval required\\n    ContentAssemblerAgent->>ContentAssemblerAgent: assemble_channel_assets (HubSpot)\\n    ContentAssemblerAgent->>ChannelPackagingAgent: Draft assets\\n    ChannelPackagingAgent->>ChannelPackagingAgent: format_multi_channel_assets (HubSpot)\\n    ChannelPackagingAgent->>ChannelPackagingAgent: queue_scheduling_metadata (HubSpot)\\n    ChannelPackagingAgent->>User: Campaign ready for launch",
    "legend": ["Phase 1: CampaignFacilitator gathers goals and inspiration", "Phase 2: Copy, Design, Growth agents collaborate organically", "Phase 3: ContentAssembler and ChannelPackaging finalize assets"]
  },
  "agent_message": "Ready to build this organic collaborative workflow? The system coordinates brief alignment, multi-agent ideation, and asset assembly. Approve the Action Plan to begin implementation."
}""",
            6: """{
  "MermaidSequenceDiagram": {
    "workflow_name": "Digital Loan Application Pipeline",
    "mermaid_diagram": "sequenceDiagram\\n    participant User\\n    participant ApplicationIntakeAgent\\n    participant RiskComplianceAgent\\n    participant UnderwritingDecisionAgent\\n    participant OfferFulfillmentAgent\\n\\n    Note over User,OfferFulfillmentAgent: Phase 1: Intake Validation\\n    User->>ApplicationIntakeAgent: Submit loan application\\n    ApplicationIntakeAgent->>ApplicationIntakeAgent: validate_required_documents (Salesforce)\\n    ApplicationIntakeAgent->>ApplicationIntakeAgent: normalize_applicant_profile (Salesforce)\\n\\n    alt Valid Application\\n        Note over ApplicationIntakeAgent,OfferFulfillmentAgent: Phase 2: Risk & Compliance Screening\\n        ApplicationIntakeAgent->>RiskComplianceAgent: Proceed to screening\\n        RiskComplianceAgent->>RiskComplianceAgent: run_credit_report (Experian)\\n        RiskComplianceAgent->>RiskComplianceAgent: execute_fraud_screen\\n        RiskComplianceAgent->>RiskComplianceAgent: log_kyc_findings (Salesforce)\\n\\n        Note over RiskComplianceAgent,OfferFulfillmentAgent: Phase 3: Underwriting Decision\\n        RiskComplianceAgent->>UnderwritingDecisionAgent: Risk checks complete\\n        UnderwritingDecisionAgent->>UnderwritingDecisionAgent: apply_underwriting_policy\\n        UnderwritingDecisionAgent->>UnderwritingDecisionAgent: calculate_offer_terms\\n\\n        alt Approved\\n            Note over UnderwritingDecisionAgent,OfferFulfillmentAgent: Phase 4: Offer & Fulfillment\\n            UnderwritingDecisionAgent->>OfferFulfillmentAgent: Loan approved\\n            Note over OfferFulfillmentAgent: Human approval required\\n            OfferFulfillmentAgent->>OfferFulfillmentAgent: generate_offer_packet (Salesforce)\\n            OfferFulfillmentAgent->>OfferFulfillmentAgent: notify_borrower (Twilio)\\n            OfferFulfillmentAgent->>OfferFulfillmentAgent: sync_fulfillment_status (Salesforce)\\n            OfferFulfillmentAgent->>User: Loan offer delivered\\n        else Declined\\n            UnderwritingDecisionAgent->>User: Application declined\\n        end\\n    else Invalid Application\\n        ApplicationIntakeAgent->>User: Validation failed\\n    end",
    "legend": ["Phase 1: ApplicationIntakeAgent validates submission", "Phase 2: RiskComplianceAgent screens for risk", "Phase 3: UnderwritingDecisionAgent evaluates and decides", "Phase 4: OfferFulfillmentAgent delivers offer"]
  },
  "agent_message": "This sequential pipeline orchestrates intake validation, risk screening, underwriting decision, and offer fulfillment. Review the sequence diagram and confirm to proceed with building your automation."
}""",
            7: """{
  "MermaidSequenceDiagram": {
    "workflow_name": "Demand Forecast Comparison",
    "mermaid_diagram": "sequenceDiagram\\n    participant User\\n    participant PlanningCoordinator\\n    participant StatisticalForecastAgent\\n    participant CausalForecastAgent\\n    participant HeuristicForecastAgent\\n    participant ForecastEvaluator\\n    participant RecommendationPublisher\\n\\n    Note over User,RecommendationPublisher: Phase 1: Scenario Brief\\n    User->>PlanningCoordinator: Request forecast\\n    PlanningCoordinator->>PlanningCoordinator: compile_scenario_brief (Notion)\\n    PlanningCoordinator->>PlanningCoordinator: lock_evaluation_metrics (Notion)\\n\\n    Note over PlanningCoordinator,RecommendationPublisher: Phase 2: Parallel Forecast Generation\\n    PlanningCoordinator->>StatisticalForecastAgent: Commission statistical model\\n    PlanningCoordinator->>CausalForecastAgent: Commission causal model\\n    PlanningCoordinator->>HeuristicForecastAgent: Commission heuristic model\\n    Note over StatisticalForecastAgent,HeuristicForecastAgent: Independent parallel execution\\n    StatisticalForecastAgent->>StatisticalForecastAgent: train_statistical_model\\n    StatisticalForecastAgent->>StatisticalForecastAgent: generate_statistical_projection\\n    StatisticalForecastAgent->>StatisticalForecastAgent: publish_forecast_payload (Notion)\\n    CausalForecastAgent->>CausalForecastAgent: ingest_exogenous_signals\\n    CausalForecastAgent->>CausalForecastAgent: generate_causal_projection\\n    HeuristicForecastAgent->>HeuristicForecastAgent: apply_heuristic_rules\\n    HeuristicForecastAgent->>HeuristicForecastAgent: stress_test_edge_cases\\n\\n    Note over HeuristicForecastAgent,RecommendationPublisher: Phase 3: Comparative Evaluation\\n    StatisticalForecastAgent->>ForecastEvaluator: Statistical forecast\\n    CausalForecastAgent->>ForecastEvaluator: Causal forecast\\n    HeuristicForecastAgent->>ForecastEvaluator: Heuristic forecast\\n    Note over ForecastEvaluator: Human approval required\\n    ForecastEvaluator->>ForecastEvaluator: score_forecast_accuracy\\n    ForecastEvaluator->>ForecastEvaluator: analyze_volatility\\n    ForecastEvaluator->>ForecastEvaluator: recommend_preferred_model (Notion)\\n\\n    Note over ForecastEvaluator,RecommendationPublisher: Phase 4: Recommendation Delivery\\n    ForecastEvaluator->>RecommendationPublisher: Selected forecast\\n    Note over RecommendationPublisher: Human context gathering\\n    RecommendationPublisher->>RecommendationPublisher: publish_selected_forecast (Notion)\\n    RecommendationPublisher->>RecommendationPublisher: document_selection_rationale (Notion)\\n    RecommendationPublisher->>User: Final forecast + rationale",
    "legend": ["Phase 1: PlanningCoordinator defines scenario", "Phase 2: Three agents generate independent forecasts in parallel", "Phase 3: ForecastEvaluator scores and recommends", "Phase 4: RecommendationPublisher delivers decision"]
  },
  "agent_message": "Action Plan complete: This redundant forecasting system generates parallel models, evaluates comparatively, and delivers recommendations. Approve to move forward with agent implementation."
}""",
            8: """{
  "MermaidSequenceDiagram": {
    "workflow_name": "Vendor Onboarding Hub",
    "mermaid_diagram": "sequenceDiagram\\n    participant User\\n    participant VendorIntakeCoordinator\\n    participant FinanceReviewAgent\\n    participant SecurityReviewAgent\\n    participant LegalReviewAgent\\n    participant RiskAlignmentMediator\\n    participant OnboardingFinalizer\\n\\n    Note over User,OnboardingFinalizer: Phase 1: Hub Intake\\n    User->>VendorIntakeCoordinator: Submit vendor onboarding\\n    VendorIntakeCoordinator->>VendorIntakeCoordinator: validate_vendor_submission (Salesforce)\\n    VendorIntakeCoordinator->>VendorIntakeCoordinator: determine_required_spokes\\n    VendorIntakeCoordinator->>VendorIntakeCoordinator: assemble_briefing_packet (Salesforce)\\n\\n    Note over VendorIntakeCoordinator,OnboardingFinalizer: Phase 2: Spoke Reviews (Parallel)\\n    VendorIntakeCoordinator->>FinanceReviewAgent: Dispatch finance review\\n    VendorIntakeCoordinator->>SecurityReviewAgent: Dispatch security review\\n    VendorIntakeCoordinator->>LegalReviewAgent: Dispatch legal review\\n    Note over FinanceReviewAgent,LegalReviewAgent: Independent parallel reviews\\n    FinanceReviewAgent->>FinanceReviewAgent: run_financial_due_diligence\\n    FinanceReviewAgent->>FinanceReviewAgent: verify_banking_details (Stripe)\\n    FinanceReviewAgent->>FinanceReviewAgent: post_finance_status (Salesforce)\\n    SecurityReviewAgent->>SecurityReviewAgent: analyze_security_questionnaire (Salesforce)\\n    SecurityReviewAgent->>SecurityReviewAgent: post_security_status (Salesforce)\\n    LegalReviewAgent->>LegalReviewAgent: review_contract_terms (DocuSign)\\n    LegalReviewAgent->>LegalReviewAgent: post_legal_status (Salesforce)\\n\\n    Note over LegalReviewAgent,OnboardingFinalizer: Phase 3: Risk Alignment\\n    FinanceReviewAgent->>RiskAlignmentMediator: Finance status\\n    SecurityReviewAgent->>RiskAlignmentMediator: Security status\\n    LegalReviewAgent->>RiskAlignmentMediator: Legal status\\n    RiskAlignmentMediator->>RiskAlignmentMediator: monitor_spoke_progress (Salesforce)\\n    RiskAlignmentMediator->>RiskAlignmentMediator: resolve_risk_conflicts\\n\\n    Note over RiskAlignmentMediator,OnboardingFinalizer: Phase 4: Hub Approval & Handoff\\n    RiskAlignmentMediator->>OnboardingFinalizer: All reviews complete\\n    Note over OnboardingFinalizer: Human approval required\\n    OnboardingFinalizer->>OnboardingFinalizer: compile_final_approvals (Salesforce)\\n    OnboardingFinalizer->>OnboardingFinalizer: trigger_account_provisioning (Salesforce)\\n    OnboardingFinalizer->>User: Vendor onboarding complete",
    "legend": ["Phase 1: VendorIntakeCoordinator validates and dispatches", "Phase 2: Finance, Security, Legal spokes review in parallel", "Phase 3: RiskAlignmentMediator monitors and mediates", "Phase 4: OnboardingFinalizer compiles and provisions"]
  },
  "agent_message": "Ready to build this hub-and-spoke vendor onboarding system? The workflow coordinates parallel reviews, risk mediation, and finalization. Review and approve the Action Plan to proceed."
}""",
            9: """{
  "MermaidSequenceDiagram": {
    "workflow_name": "Rapid App Foundry",
    "mermaid_diagram": "sequenceDiagram\\n    participant User\\n    participant AppTriageAgent\\n    participant DependencyPlanner\\n    participant ResearchScout\\n    participant UXWireframeAgent\\n    participant AppScaffoldBuilder\\n    participant IntegrationAutomationAgent\\n    participant FoundryLeadReviewer\\n\\n    Note over User,FoundryLeadReviewer: Phase 1: Requirement Breakdown\\n    User->>AppTriageAgent: Request app build\\n    AppTriageAgent->>AppTriageAgent: capture_app_requirements (Jira)\\n    AppTriageAgent->>AppTriageAgent: emit_typed_task_queues (Jira)\\n    AppTriageAgent->>AppTriageAgent: prioritize_foundry_backlog (Jira)\\n    Note over AppTriageAgent: Create Research, Design, Build tasks\\n\\n    Note over AppTriageAgent,FoundryLeadReviewer: Phase 2: Dependency Planning\\n    AppTriageAgent->>DependencyPlanner: Task queues ready\\n    DependencyPlanner->>DependencyPlanner: link_task_dependencies (Jira)\\n    DependencyPlanner->>DependencyPlanner: sequence_execution_order (Jira)\\n    Note over DependencyPlanner: Enforce research→design→build order\\n\\n    Note over DependencyPlanner,FoundryLeadReviewer: Phase 3: Research & Design Execution\\n    DependencyPlanner->>ResearchScout: Research tasks\\n    DependencyPlanner->>UXWireframeAgent: Design tasks\\n    ResearchScout->>ResearchScout: conduct_domain_research (Perplexity)\\n    ResearchScout->>ResearchScout: summarize_competitor_benchmarks (Perplexity)\\n    UXWireframeAgent->>UXWireframeAgent: draft_wireframes (Figma)\\n    UXWireframeAgent->>UXWireframeAgent: export_design_assets (Figma)\\n\\n    Note over UXWireframeAgent,FoundryLeadReviewer: Phase 4: App Scaffolding & Integration\\n    ResearchScout->>AppScaffoldBuilder: Research complete\\n    UXWireframeAgent->>AppScaffoldBuilder: Design complete\\n    AppScaffoldBuilder->>AppScaffoldBuilder: generate_app_skeleton (GitHub)\\n    AppScaffoldBuilder->>AppScaffoldBuilder: apply_integration_stubs (GitHub)\\n    AppScaffoldBuilder->>AppScaffoldBuilder: run_scaffold_tests (GitHubActions)\\n    AppScaffoldBuilder->>IntegrationAutomationAgent: Scaffold ready\\n    IntegrationAutomationAgent->>IntegrationAutomationAgent: configure_integrations\\n    IntegrationAutomationAgent->>IntegrationAutomationAgent: provision_environment_secrets (GitHub)\\n\\n    Note over IntegrationAutomationAgent,FoundryLeadReviewer: Phase 5: Review & Handoff\\n    IntegrationAutomationAgent->>FoundryLeadReviewer: Build complete\\n    Note over FoundryLeadReviewer: Human approval required\\n    FoundryLeadReviewer->>FoundryLeadReviewer: compile_release_bundle (GitHubActions)\\n    FoundryLeadReviewer->>FoundryLeadReviewer: author_demo_script (Notion)\\n    FoundryLeadReviewer->>User: App delivered with demo",
    "legend": ["Phase 1: AppTriageAgent decomposes into task queues", "Phase 2: DependencyPlanner sequences dependencies", "Phase 3: ResearchScout & UXWireframeAgent execute", "Phase 4: AppScaffoldBuilder & IntegrationAutomationAgent build", "Phase 5: FoundryLeadReviewer delivers"]
  },
  "agent_message": "This task-based app foundry orchestrates triage, dependency planning, research/design, scaffolding, and review handoff across 5 coordinated phases. Review the Action Plan and approve to begin building."
}"""
        }
        
        example_json = mermaid_examples.get(pattern_id)
        topology = topology_guidance.get(pattern_id)

        if not example_json or not topology:
            logger.warning(f"No mermaid guidance found for pattern_id {pattern_id}")
            return

        guidance = (
            f"[INJECTED PATTERN GUIDANCE - {pattern_display_name}]\n\n"
            f"{topology}\n\n"
            f"**Mermaid Syntax Essentials**:\n"
            f"- Start with: `sequenceDiagram`\n"
            f"- Participants: `participant AgentName as Display Name`\n"
            f"- Interactions: `Agent1->>Agent2: Message text`\n"
            f"- Self-calls: `Agent->>Agent: Internal processing`\n"
            f"- Conditionals: `alt Condition` / `else Alternate` / `end`\n"
            f"- Loops: `loop Description` / `end`\n"
            f"- Notes: `Note over Agent: Text` or `Note over Agent1,Agent2: Spanning text`\n"
            f"- Phase annotations: Use Note blocks to mark phase boundaries and UI interactions\n\n"
            f"**Complete Example for {pattern_display_name}**:\n"
            f"```json\n{example_json}\n```\n\n"
            f"**CRITICAL INSTRUCTIONS**:\n"
            f"- Follow the topology structure shown above EXACTLY\n"
            f"- Use ActionPlan phases to populate the canonical structure\n"
            f"- Map TechnicalBlueprint.ui_components to Note blocks at correct phases\n"
            f"- Preserve the pattern's characteristic flow (sequences, alt blocks, loops, etc.)\n"
            f"- Do NOT deviate from the topology unless ActionPlan structure requires it\n"
            f"- If ActionPlan conflicts with pattern structure, document mismatch in agent_message"
        )

        if _apply_pattern_guidance(agent, guidance):
            logger.info(f"✓ Injected comprehensive Mermaid guidance for {pattern_display_name} into {agent.name}")
        else:
            logger.warning(f"Pattern guidance injection failed for {agent.name}")

    except Exception as e:
        logger.error(f"Error in inject_project_overview_guidance: {e}", exc_info=True)



def inject_context_variables_guidance(agent, messages: List[Dict[str, Any]]) -> None:
    """
    AG2 update_agent_state hook for ContextVariablesAgent.
    Injects pattern-specific context variable requirements.

    ContextVariablesAgent OUTPUT FORMAT (ContextVariablesAgentOutput JSON):
    {
      "ContextVariablesPlan": {
        "definitions": {
          "<variable_name>": {
            "type": "string|boolean|integer|object",
            "description": "<purpose of the variable>",
            "source": {
              "type": "database|environment|static|derived",
              "database_name": "<db_name>",
              "collection": "<collection_name>",
              "search_by": "<query_field>",
              "field": "<target_field>",
              "env_var": "<ENV_VAR_NAME>",
              "default": "<fallback_value>",
              "value": "<static_value>",
              "triggers": [
                {
                  "type": "agent_text|ui_response",
                  "agent": "<AgentName>",
                  "match": {"equals": "<text>", "contains": "<substring>", "regex": "<pattern>"},
                  "tool": "<tool_name>",
                  "response_key": "<json_key>"
                }
              ]
            }
          }
        },
        "agents": {
          "<PascalCaseAgentName>": {
            "variables": ["<variable_name1>", "<variable_name2>"]
          }
        }
      }
    }
    
    Schema notes:
    - definitions: Object/dict keyed by variable name (not array)
    - agents: Object/dict keyed by agent name (not array)
    - Source fields vary by type: database uses database_name/collection/field, environment uses env_var, static uses value, derived uses triggers
    """
    try:
        pattern = _get_pattern_from_context(agent)
        if not pattern:
            logger.debug(f"No pattern available for {agent.name}, skipping guidance injection")
            return

        pattern_id = pattern.get('id')
        pattern_name = pattern.get('name')
        pattern_display_name = pattern.get('display_name', pattern_name)
        
        # Pattern-specific context variable guidance examples
        context_variable_examples = {
            1: """{
  "ContextVariablesPlan": {
    "definitions": {
      "routing_started": {
        "type": "boolean",
        "description": "Workflow initialization flag",
        "source": {
          "type": "static",
          "value": true
        }
      },
      "current_domain": {
        "type": "string",
        "description": "Currently active domain (tech, finance, healthcare, general)",
        "source": {
          "type": "derived",
          "default": "general",
          "triggers": [
            {
              "type": "agent_text",
              "agent": "RouterAgent",
              "match": {
                "contains": "DOMAIN:"
              }
            }
          ]
        }
      },
      "domain_confidence": {
        "type": "integer",
        "description": "Confidence score for current domain classification (1-10)",
        "source": {
          "type": "derived",
          "default": 5,
          "triggers": [
            {
              "type": "ui_response",
              "tool": "classify_domain",
              "response_key": "confidence"
            }
          ]
        }
      },
      "question_answered": {
        "type": "boolean",
        "description": "Completion flag for workflow termination",
        "source": {
          "type": "derived",
          "default": false,
          "triggers": [
            {
              "type": "agent_text",
              "agent": "TechSpecialist",
              "match": {
                "contains": "ANSWER_COMPLETE"
              }
            }
          ]
        }
      }
    },
    "agents": {
      "RouterAgent": {
        "variables": ["routing_started", "domain_confidence"]
      },
      "TechSpecialist": {
        "variables": ["current_domain", "question_answered"]
      },
      "FinanceSpecialist": {
        "variables": ["current_domain", "question_answered"]
      },
      "HealthcareSpecialist": {
        "variables": ["current_domain", "question_answered"]
      }
    }
  }
}""",
            
            2: """{
  "ContextVariablesPlan": {
    "definitions": {
      "current_question": {
        "type": "string",
        "description": "The question being answered",
        "source": {
          "type": "database",
          "database_name": "workflows",
          "collection": "chat_sessions",
          "search_by": "chat_id",
          "field": "user_question",
          "default": ""
        }
      },
      "max_escalation_tiers": {
        "type": "integer",
        "description": "Maximum number of escalation tiers allowed (configured via environment)",
        "source": {
          "type": "environment",
          "env_var": "MAX_ESCALATION_TIERS",
          "default": 3
        }
      },
      "current_tier": {
        "type": "string",
        "description": "Active tier (basic, intermediate, advanced)",
        "source": {
          "type": "derived",
          "default": "basic",
          "triggers": [
            {
              "type": "agent_text",
              "agent": "TriageAgent",
              "match": {
                "contains": "TIER:"
              }
            }
          ]
        }
      },
      "tier_confidence": {
        "type": "integer",
        "description": "Current tier confidence score (1-10)",
        "source": {
          "type": "derived",
          "default": 5,
          "triggers": [
            {
              "type": "ui_response",
              "tool": "assess_confidence",
              "response_key": "confidence_score"
            }
          ]
        }
      },
      "escalation_count": {
        "type": "integer",
        "description": "Number of tier escalations performed",
        "source": {
          "type": "static",
          "value": 0
        }
      }
    },
    "agents": {
      "TriageAgent": {
        "variables": ["current_tier", "escalation_count", "max_escalation_tiers"]
      },
      "BasicAgent": {
        "variables": ["current_question", "tier_confidence"]
      },
      "IntermediateAgent": {
        "variables": ["current_question", "tier_confidence"]
      },
      "AdvancedAgent": {
        "variables": ["current_question", "tier_confidence"]
      }
    }
  }
}""",
            
            3: """{
  "ContextVariablesPlan": {
    "definitions": {
      "campaign_brief_snapshot": {
        "type": "string",
        "description": "Normalized brief containing personas, tone, and acceptance criteria",
        "source": {
          "type": "derived",
          "default": "",
          "triggers": [
            {
              "type": "agent_text",
              "agent": "FacilitatorAgent",
              "match": {
                "contains": "BRIEF_FINALIZED"
              }
            }
          ]
        }
      },
      "current_iteration": {
        "type": "integer",
        "description": "Current iteration number (starts at 1)",
        "source": {
          "type": "static",
          "value": 1
        }
      },
      "max_iterations": {
        "type": "integer",
        "description": "Maximum allowed iterations",
        "source": {
          "type": "static",
          "value": 3
        }
      },
      "iteration_needed": {
        "type": "boolean",
        "description": "Whether another review-revision cycle required",
        "source": {
          "type": "derived",
          "default": true,
          "triggers": [
            {
              "type": "ui_response",
              "tool": "review_content",
              "response_key": "needs_revision"
            }
          ]
        }
      },
      "approval_gate_status": {
        "type": "string",
        "description": "Tracks stakeholder approval state for the launch copy",
        "source": {
          "type": "derived",
          "default": "pending",
          "triggers": [
            {
              "type": "ui_response",
              "tool": "approve_campaign",
              "response_key": "status"
            }
          ]
        }
      }
    },
    "agents": {
      "FacilitatorAgent": {
        "variables": ["campaign_brief_snapshot", "current_iteration", "max_iterations"]
      },
      "DrafterAgent": {
        "variables": ["campaign_brief_snapshot", "current_iteration"]
      },
      "ReviewAgent": {
        "variables": ["iteration_needed", "current_iteration", "max_iterations"]
      },
      "RevisionAgent": {
        "variables": ["iteration_needed", "current_iteration"]
      },
      "ApprovalAgent": {
        "variables": ["approval_gate_status"]
      }
    }
  }
}""",
            
            4: """{
  "ContextVariablesPlan": {
    "definitions": {
      "workstream_assignments": {
        "type": "string",
        "description": "Mapping of demand, competitor, and regulatory owners",
        "source": {
          "type": "derived",
          "default": "",
          "triggers": [
            {
              "type": "agent_text",
              "agent": "ExecutiveStrategyLead",
              "match": {
                "contains": "WORKSTREAM_PLAN"
              }
            }
          ]
        }
      },
      "demand_research_completed": {
        "type": "boolean",
        "description": "Demand research workstream done",
        "source": {
          "type": "derived",
          "default": false,
          "triggers": [
            {
              "type": "agent_text",
              "agent": "DemandResearchManager",
              "match": {
                "contains": "RESEARCH_COMPLETE"
              }
            }
          ]
        }
      },
      "regulatory_research_completed": {
        "type": "boolean",
        "description": "Regulatory research workstream done",
        "source": {
          "type": "derived",
          "default": false,
          "triggers": [
            {
              "type": "agent_text",
              "agent": "RegulatoryResearchManager",
              "match": {
                "contains": "RESEARCH_COMPLETE"
              }
            }
          ]
        }
      },
      "competitive_research_completed": {
        "type": "boolean",
        "description": "Competitive research workstream done",
        "source": {
          "type": "derived",
          "default": false,
          "triggers": [
            {
              "type": "agent_text",
              "agent": "CompetitiveLandscapeManager",
              "match": {
                "contains": "RESEARCH_COMPLETE"
              }
            }
          ]
        }
      },
      "executive_review_ready": {
        "type": "boolean",
        "description": "All manager sections aggregated",
        "source": {
          "type": "derived",
          "default": false,
          "triggers": [
            {
              "type": "agent_text",
              "agent": "CompetitiveLandscapeManager",
              "match": {
                "contains": "ALL_WORKSTREAMS_COMPLETE"
              }
            }
          ]
        }
      }
    },
    "agents": {
      "ExecutiveStrategyLead": {
        "variables": ["workstream_assignments", "demand_research_completed", "regulatory_research_completed", "competitive_research_completed", "executive_review_ready"]
      },
      "DemandResearchManager": {
        "variables": ["workstream_assignments", "demand_research_completed"]
      },
      "RegulatoryResearchManager": {
        "variables": ["workstream_assignments", "regulatory_research_completed"]
      },
      "CompetitiveLandscapeManager": {
        "variables": ["workstream_assignments", "competitive_research_completed"]
      },
      "DemandSpecialist": {
        "variables": []
      },
      "RegulatorySpecialist": {
        "variables": []
      },
      "CompetitiveSpecialist": {
        "variables": []
      }
    }
  }
}""",
            
            5: """{
  "ContextVariablesPlan": {
    "definitions": {
      "workflow_started": {
        "type": "boolean",
        "description": "Workflow initialization flag",
        "source": {
          "type": "static",
          "value": true
        }
      },
      "conversation_context": {
        "type": "string",
        "description": "Ongoing conversation summary",
        "source": {
          "type": "derived",
          "default": "",
          "triggers": [
            {
              "type": "agent_text",
              "agent": "GroupChatManager",
              "match": {
                "contains": "CONTEXT_UPDATE"
              }
            }
          ]
        }
      },
      "workflow_completed": {
        "type": "boolean",
        "description": "Workflow completion flag",
        "source": {
          "type": "derived",
          "default": false,
          "triggers": [
            {
              "type": "agent_text",
              "agent": "SummarizerAgent",
              "match": {
                "contains": "SESSION_COMPLETE"
              }
            }
          ]
        }
      }
    },
    "agents": {
      "GroupChatManager": {
        "variables": ["conversation_context", "workflow_completed"]
      },
      "BrainstormAgent": {
        "variables": ["conversation_context"]
      },
      "CriticAgent": {
        "variables": ["conversation_context"]
      },
      "SummarizerAgent": {
        "variables": ["conversation_context", "workflow_completed"]
      }
    }
  }
}""",
            
            6: """{
  "ContextVariablesPlan": {
    "definitions": {
      "pipeline_started": {
        "type": "boolean",
        "description": "Workflow initialization flag",
        "source": {
          "type": "static",
          "value": true
        }
      },
      "intake_completed": {
        "type": "boolean",
        "description": "ApplicationIntakeAgent stage completed",
        "source": {
          "type": "derived",
          "default": false,
          "triggers": [
            {
              "type": "agent_text",
              "agent": "ApplicationIntakeAgent",
              "match": {
                "contains": "INTAKE_COMPLETE"
              }
            }
          ]
        }
      },
      "risk_screening_completed": {
        "type": "boolean",
        "description": "RiskComplianceAgent stage completed",
        "source": {
          "type": "derived",
          "default": false,
          "triggers": [
            {
              "type": "agent_text",
              "agent": "RiskComplianceAgent",
              "match": {
                "contains": "RISK_COMPLETE"
              }
            }
          ]
        }
      },
      "underwriting_completed": {
        "type": "boolean",
        "description": "UnderwritingDecisionAgent stage completed",
        "source": {
          "type": "derived",
          "default": false,
          "triggers": [
            {
              "type": "agent_text",
              "agent": "UnderwritingDecisionAgent",
              "match": {
                "contains": "UNDERWRITING_COMPLETE"
              }
            }
          ]
        }
      },
      "has_error": {
        "type": "boolean",
        "description": "Error state flag for early termination",
        "source": {
          "type": "derived",
          "default": false,
          "triggers": [
            {
              "type": "agent_text",
              "agent": "ApplicationIntakeAgent",
              "match": {
                "contains": "ERROR"
              }
            }
          ]
        }
      }
    },
    "agents": {
      "ApplicationIntakeAgent": {
        "variables": ["pipeline_started", "has_error"]
      },
      "RiskComplianceAgent": {
        "variables": ["intake_completed", "has_error"]
      },
      "UnderwritingDecisionAgent": {
        "variables": ["risk_screening_completed", "has_error"]
      },
      "OfferFulfillmentAgent": {
        "variables": ["underwriting_completed", "has_error"]
      }
    }
  }
}""",
            
            7: """{
  "ContextVariablesPlan": {
    "definitions": {
      "forecast_scenario": {
        "type": "string",
        "description": "Planning window description",
        "source": {
          "type": "database",
          "database_name": "workflows",
          "collection": "forecast_requests",
          "search_by": "request_id",
          "field": "scenario_description",
          "default": ""
        }
      },
      "statistical_forecast_ready": {
        "type": "boolean",
        "description": "Statistical model completed",
        "source": {
          "type": "derived",
          "default": false,
          "triggers": [
            {
              "type": "agent_text",
              "agent": "StatisticalForecastAgent",
              "match": {
                "contains": "FORECAST_READY"
              }
            }
          ]
        }
      },
      "causal_forecast_ready": {
        "type": "boolean",
        "description": "Causal model completed",
        "source": {
          "type": "derived",
          "default": false,
          "triggers": [
            {
              "type": "agent_text",
              "agent": "CausalForecastAgent",
              "match": {
                "contains": "FORECAST_READY"
              }
            }
          ]
        }
      },
      "heuristic_forecast_ready": {
        "type": "boolean",
        "description": "Heuristic model completed",
        "source": {
          "type": "derived",
          "default": false,
          "triggers": [
            {
              "type": "agent_text",
              "agent": "HeuristicForecastAgent",
              "match": {
                "contains": "FORECAST_READY"
              }
            }
          ]
        }
      },
      "selected_model_type": {
        "type": "string",
        "description": "Which approach was selected (statistical, causal, or heuristic)",
        "source": {
          "type": "derived",
          "default": "",
          "triggers": [
            {
              "type": "ui_response",
              "tool": "select_forecast",
              "response_key": "model_type"
            }
          ]
        }
      }
    },
    "agents": {
      "PlanningCoordinator": {
        "variables": ["forecast_scenario"]
      },
      "StatisticalForecastAgent": {
        "variables": ["forecast_scenario", "statistical_forecast_ready"]
      },
      "CausalForecastAgent": {
        "variables": ["forecast_scenario", "causal_forecast_ready"]
      },
      "HeuristicForecastAgent": {
        "variables": ["forecast_scenario", "heuristic_forecast_ready"]
      },
      "ForecastEvaluator": {
        "variables": ["statistical_forecast_ready", "causal_forecast_ready", "heuristic_forecast_ready", "selected_model_type"]
      }
    }
  }
}""",
            
            8: """{
  "ContextVariablesPlan": {
    "definitions": {
      "vendor_intake_complete": {
        "type": "boolean",
        "description": "Hub intake completed",
        "source": {
          "type": "derived",
          "default": false,
          "triggers": [
            {
              "type": "agent_text",
              "agent": "VendorIntakeCoordinator",
              "match": {
                "contains": "INTAKE_COMPLETE"
              }
            }
          ]
        }
      },
      "finance_review_complete": {
        "type": "boolean",
        "description": "Finance review finished",
        "source": {
          "type": "derived",
          "default": false,
          "triggers": [
            {
              "type": "agent_text",
              "agent": "FinanceReviewAgent",
              "match": {
                "contains": "REVIEW_COMPLETE"
              }
            }
          ]
        }
      },
      "security_review_complete": {
        "type": "boolean",
        "description": "Security review finished",
        "source": {
          "type": "derived",
          "default": false,
          "triggers": [
            {
              "type": "agent_text",
              "agent": "SecurityReviewAgent",
              "match": {
                "contains": "REVIEW_COMPLETE"
              }
            }
          ]
        }
      },
      "legal_review_complete": {
        "type": "boolean",
        "description": "Legal review finished",
        "source": {
          "type": "derived",
          "default": false,
          "triggers": [
            {
              "type": "agent_text",
              "agent": "LegalReviewAgent",
              "match": {
                "contains": "REVIEW_COMPLETE"
              }
            }
          ]
        }
      },
      "all_reviews_complete": {
        "type": "boolean",
        "description": "All spokes reported back",
        "source": {
          "type": "derived",
          "default": false,
          "triggers": [
            {
              "type": "agent_text",
              "agent": "RiskAlignmentMediator",
              "match": {
                "contains": "ALL_REVIEWS_COMPLETE"
              }
            }
          ]
        }
      }
    },
    "agents": {
      "VendorIntakeCoordinator": {
        "variables": ["vendor_intake_complete", "finance_review_complete", "security_review_complete", "legal_review_complete"]
      },
      "FinanceReviewAgent": {
        "variables": ["vendor_intake_complete", "finance_review_complete"]
      },
      "SecurityReviewAgent": {
        "variables": ["vendor_intake_complete", "security_review_complete"]
      },
      "LegalReviewAgent": {
        "variables": ["vendor_intake_complete", "legal_review_complete"]
      },
      "RiskAlignmentMediator": {
        "variables": ["finance_review_complete", "security_review_complete", "legal_review_complete", "all_reviews_complete"]
      }
    }
  }
}""",
            
            9: """{
  "ContextVariablesPlan": {
    "definitions": {
      "CurrentResearchTaskIndex": {
        "type": "integer",
        "description": "Active research task index",
        "source": {
          "type": "static",
          "value": 0
        }
      },
      "CurrentDesignTaskIndex": {
        "type": "integer",
        "description": "Active design task index",
        "source": {
          "type": "static",
          "value": 0
        }
      },
      "CurrentBuildTaskIndex": {
        "type": "integer",
        "description": "Active build task index",
        "source": {
          "type": "static",
          "value": 0
        }
      },
      "ResearchTasksDone": {
        "type": "boolean",
        "description": "ALL research tasks completed",
        "source": {
          "type": "derived",
          "default": false,
          "triggers": [
            {
              "type": "agent_text",
              "agent": "ResearchScout",
              "match": {
                "contains": "ALL_RESEARCH_COMPLETE"
              }
            }
          ]
        }
      },
      "DesignTasksDone": {
        "type": "boolean",
        "description": "ALL design tasks completed",
        "source": {
          "type": "derived",
          "default": false,
          "triggers": [
            {
              "type": "agent_text",
              "agent": "UXWireframeAgent",
              "match": {
                "contains": "ALL_DESIGN_COMPLETE"
              }
            }
          ]
        }
      },
      "BuildTasksDone": {
        "type": "boolean",
        "description": "ALL build tasks completed",
        "source": {
          "type": "derived",
          "default": false,
          "triggers": [
            {
              "type": "agent_text",
              "agent": "AppScaffoldBuilder",
              "match": {
                "contains": "ALL_BUILD_COMPLETE"
              }
            }
          ]
        }
      }
    },
    "agents": {
      "AppTriageAgent": {
        "variables": ["CurrentResearchTaskIndex", "CurrentDesignTaskIndex", "CurrentBuildTaskIndex"]
      },
      "DependencyPlanner": {
        "variables": ["ResearchTasksDone", "DesignTasksDone", "BuildTasksDone"]
      },
      "ResearchScout": {
        "variables": ["CurrentResearchTaskIndex", "ResearchTasksDone"]
      },
      "UXWireframeAgent": {
        "variables": ["CurrentDesignTaskIndex", "ResearchTasksDone", "DesignTasksDone"]
      },
      "AppScaffoldBuilder": {
        "variables": ["CurrentBuildTaskIndex", "DesignTasksDone", "BuildTasksDone"]
      },
      "IntegrationAutomationAgent": {
        "variables": ["CurrentBuildTaskIndex", "DesignTasksDone", "BuildTasksDone"]
      },
      "FoundryLeadReviewer": {
        "variables": ["ResearchTasksDone", "DesignTasksDone", "BuildTasksDone"]
      }
    }
  }
}"""
        }

        example_json = context_variable_examples.get(pattern_id)

        if not example_json:
            logger.warning(f"No context variable example found for pattern_id {pattern_id}")
            return

        guidance = (
            f"[PATTERN EXAMPLE - {pattern_display_name}]\n"
            f"Here is a complete ContextVariablesPlan JSON example aligned with the {pattern_display_name} pattern.\n\n"
            f"```json\n{example_json}\n```\n"
        )

        if _apply_pattern_guidance(agent, guidance):
            logger.info(f"✓ Injected context variable guidance for {pattern_display_name} into {agent.name}")
        else:
            logger.warning(f"Pattern guidance injection failed for {agent.name}")

    except Exception as e:
        logger.error(f"Error in inject_context_variables_guidance: {e}", exc_info=True)



def inject_tools_manager_guidance(agent, messages: List[Dict[str, Any]]) -> None:
    """
    AG2 update_agent_state hook for ToolsManagerAgent.
    Injects pattern-specific tool requirements and organization guidance.

    ToolsManagerAgent OUTPUT FORMAT (ToolsManagerAgentOutput JSON):
    {
      "tools": [
        {
          "agent": "<PascalCaseAgentName>",
          "file": "<snake_case_file_name>.py",
          "function": "<snake_case_function_name>",
          "description": "<tool purpose, <=140 chars>",
          "tool_type": "UI_Tool|Agent_Tool",
          "auto_invoke": true|false|null,
          "ui": {
            "label": "<Button/Action Label>",
            "description": "<User-facing description>",
            "component": "<ComponentName>|null",
            "mode": "inline|artifact|null"
          }
        }
      ],
      "lifecycle_tools": [
        {
          "agent": "<AgentName>|null",
          "file": "<hook_file>.py",
          "function": "<hook_function_name>",
          "description": "<hook purpose>",
          "tool_type": "Agent_Tool",
          "auto_invoke": null,
          "ui": {
            "label": null,
            "description": null,
            "component": null,
            "mode": null
          }
        }
      ]
    }
    
  Interaction mode mapping:
  - Read `interaction_mode` from PhaseAgents.agent_tools[].
  - `interaction_mode = "inline"` 
  - `interaction_mode = "artifact"` 
  - Missing field or value `"none"` → Treat as Agent_Tool and leave ui metadata null.

  Auto-invoke defaults:
    - UI_Tool: Defaults to true (omit auto_invoke or set null). Override to false only when explicit user timing is required.
    - Agent_Tool: Defaults to false (omit auto_invoke or set null). Set true when downstream agents need this tool's structured output from context.
    - Lifecycle tools: Never have auto_invoke field (not applicable to lifecycle hooks).
    """
    try:
        pattern = _get_pattern_from_context(agent)
        if not pattern:
            logger.debug(f"No pattern available for {agent.name}, skipping guidance injection")
            return

        pattern_id = pattern.get('id')
        pattern_name = pattern.get('name')
        pattern_display_name = pattern.get('display_name', pattern_name)
        
        # Pattern-specific tool examples from PhaseAgents (WorkflowImplementationAgent)
        tools_examples = {
            1: """{
  "tools": [
    {
      "agent": "ContentClassifier",
      "file": "classify_domain.py",
      "function": "classify_domain",
      "description": "Analyzes query content and classifies into domain categories with confidence scores",
      "tool_type": "Agent_Tool",
      "auto_invoke": null,
      "ui": {"label": null, "description": null, "component": null, "mode": null}
    },
    {
      "agent": "TechSpecialist",
      "file": "provide_tech_response.py",
      "function": "provide_tech_response",
      "description": "Generates technical domain-specific responses with supporting documentation",
      "tool_type": "Agent_Tool",
      "auto_invoke": null,
      "ui": {"label": null, "description": null, "component": null, "mode": null}
    },
    {
      "agent": "FinanceSpecialist",
      "file": "provide_finance_response.py",
      "function": "provide_finance_response",
      "description": "Generates finance domain-specific responses with market data references",
      "tool_type": "Agent_Tool",
      "auto_invoke": null,
      "ui": {"label": null, "description": null, "component": null, "mode": null}
    },
    {
      "agent": "HealthcareSpecialist",
      "file": "provide_healthcare_response.py",
      "function": "provide_healthcare_response",
      "description": "Generates healthcare domain-specific responses with compliance validation",
      "tool_type": "Agent_Tool",
      "auto_invoke": null,
      "ui": {"label": null, "description": null, "component": null, "mode": null}
    }
  ],
  "lifecycle_tools": []
}""",
            
            2: """{
  "tools": [
    {
      "agent": "TriageAgent",
      "file": "evaluate_complexity.py",
      "function": "evaluate_complexity",
      "description": "Assesses question complexity and determines appropriate response tier",
      "tool_type": "Agent_Tool",
      "auto_invoke": null,
      "ui": {"label": null, "description": null, "component": null, "mode": null}
    },
    {
      "agent": "BasicAgent",
      "file": "answer_basic.py",
      "function": "answer_basic",
      "description": "Provides tier-1 responses with confidence scoring for escalation decisions",
      "tool_type": "Agent_Tool",
      "auto_invoke": null,
      "ui": {"label": null, "description": null, "component": null, "mode": null}
    },
    {
      "agent": "IntermediateAgent",
      "file": "answer_intermediate.py",
      "function": "answer_intermediate",
      "description": "Provides tier-2 responses with advanced analysis and confidence metrics",
      "tool_type": "Agent_Tool",
      "auto_invoke": null,
      "ui": {"label": null, "description": null, "component": null, "mode": null}
    },
    {
      "agent": "AdvancedAgent",
      "file": "answer_advanced.py",
      "function": "answer_advanced",
      "description": "Provides tier-3 expert responses with comprehensive research and citations",
      "tool_type": "Agent_Tool",
      "auto_invoke": null,
      "ui": {"label": null, "description": null, "component": null, "mode": null}
    }
  ],
  "lifecycle_tools": [
    {
      "trigger": "before_agent",
      "agent": "SRELeadAgent",
      "file": "allocate_incident_db_connection.py",
      "function": "allocate_incident_db_connection",
      "description": "Establishes connection to incident database before SRE lead processes the alert",
      "tool_type": "Agent_Tool",
      "ui": {"label": null, "description": null, "component": null, "mode": null}
    },
    {
      "trigger": "after_agent",
      "agent": "SRELeadAgent",
      "file": "release_incident_db_connection.py",
      "function": "release_incident_db_connection",
      "description": "Releases database connection and commits incident resolution data after SRE lead completes work",
      "tool_type": "Agent_Tool",
      "ui": {"label": null, "description": null, "component": null, "mode": null}
    }
  ]
}""",
            
            3: """{
  "tools": [
    {
      "agent": "CampaignBriefFacilitator",
      "file": "capture_campaign_brief.py",
      "function": "capture_campaign_brief",
      "description": "Captures campaign goals, personas, and acceptance criteria",
      "tool_type": "Agent_Tool",
      "auto_invoke": null,
      "ui": {"label": null, "description": null, "component": null, "mode": null}
    },
    {
      "agent": "LaunchCopyGenerator",
      "file": "generate_launch_copy.py",
      "function": "generate_launch_copy",
      "description": "Generates messaging variants aligned to the campaign brief",
      "tool_type": "Agent_Tool",
      "auto_invoke": null,
      "ui": {"label": null, "description": null, "component": null, "mode": null}
    },
    {
      "agent": "StakeholderReviewAgent",
      "file": "collect_structured_feedback.py",
      "function": "collect_structured_feedback",
      "description": "Collects structured reviewer feedback with scoring",
      "tool_type": "UI_Tool",
      "auto_invoke": true,
      "ui": {"label": "Submit Feedback", "description": "Provide structured review comments", "component": "FeedbackForm", "display": "inline", "mode": "inline", "interaction_pattern": "multi_step"}
    },
    {
      "agent": "StakeholderReviewAgent",
      "file": "approve_campaign.py",
      "function": "approve_campaign",
      "description": "Records stakeholder approval decision and updates gate status",
      "tool_type": "UI_Tool",
      "auto_invoke": true,
      "ui": {"label": "Approve Campaign", "description": "Approve or request revisions", "component": "ApprovalGate", "display": "inline", "mode": "inline", "interaction_pattern": "two_step_confirmation"}
    },
    {
      "agent": "LaunchRevisionAgent",
      "file": "apply_feedback_actions.py",
      "function": "apply_feedback_actions",
      "description": "Applies accepted feedback and updates content",
      "tool_type": "Agent_Tool",
      "auto_invoke": null,
      "ui": {"label": null, "description": null, "component": null, "mode": null}
    }
  ],
  "lifecycle_tools": []
}""",
            
            4: """{
  "tools": [
    {
      "agent": "ExecutiveStrategyLead",
      "file": "initiate_research.py",
      "function": "initiate_research",
      "description": "Decomposes strategic goals into domain-specific research workstreams",
      "tool_type": "Agent_Tool",
      "auto_invoke": null,
      "ui": {"label": null, "description": null, "component": null, "mode": null}
    },
    {
      "agent": "DemandResearchManager",
      "file": "compile_demand_section.py",
      "function": "compile_demand_section",
      "description": "Aggregates demand specialist findings into unified research section",
      "tool_type": "Agent_Tool",
      "auto_invoke": null,
      "ui": {"label": null, "description": null, "component": null, "mode": null}
    },
    {
      "agent": "RegulatoryResearchManager",
      "file": "compile_regulatory_section.py",
      "function": "compile_regulatory_section",
      "description": "Aggregates regulatory specialist findings with compliance markers",
      "tool_type": "Agent_Tool",
      "auto_invoke": null,
      "ui": {"label": null, "description": null, "component": null, "mode": null}
    },
    {
      "agent": "CompetitiveLandscapeManager",
      "file": "compile_competitive_section.py",
      "function": "compile_competitive_section",
      "description": "Aggregates competitive intelligence with strategic positioning insights",
      "tool_type": "Agent_Tool",
      "auto_invoke": null,
      "ui": {"label": null, "description": null, "component": null, "mode": null}
    },
    {
      "agent": "DemandSpecialist",
      "file": "complete_demand_research.py",
      "function": "complete_demand_research",
      "description": "Executes demand-focused market analysis with quantitative findings",
      "tool_type": "Agent_Tool",
      "auto_invoke": null,
      "ui": {"label": null, "description": null, "component": null, "mode": null}
    },
    {
      "agent": "ExecutiveStrategyLead",
      "file": "compile_final_report.py",
      "function": "compile_final_report",
      "description": "Synthesizes all manager sections into executive decision brief",
      "tool_type": "Agent_Tool",
      "auto_invoke": null,
      "ui": {"label": null, "description": null, "component": null, "mode": null}
    }
  ],
  "lifecycle_tools": []
}""",
            
            5: """{
  "tools": [
    {
      "agent": "BrainstormAgent",
      "file": "generate_ideas.py",
      "function": "generate_ideas",
      "description": "Generates creative ideas and perspectives for the discussion",
      "tool_type": "Agent_Tool",
      "auto_invoke": null,
      "ui": {"label": null, "description": null, "component": null, "mode": null}
    },
    {
      "agent": "CriticAgent",
      "file": "evaluate_ideas.py",
      "function": "evaluate_ideas",
      "description": "Provides critical analysis and identifies potential issues",
      "tool_type": "Agent_Tool",
      "auto_invoke": null,
      "ui": {"label": null, "description": null, "component": null, "mode": null}
    },
    {
      "agent": "SummarizerAgent",
      "file": "synthesize_discussion.py",
      "function": "synthesize_discussion",
      "description": "Synthesizes conversation into actionable insights and next steps",
      "tool_type": "Agent_Tool",
      "auto_invoke": null,
      "ui": {"label": null, "description": null, "component": null, "mode": null}
    }
  ],
  "lifecycle_tools": []
}""",
            
            6: """{
  "tools": [
    {
      "agent": "ApplicationIntakeAgent",
      "file": "validate_application.py",
      "function": "validate_application",
      "description": "Validates application completeness and data quality",
      "tool_type": "Agent_Tool",
      "auto_invoke": null,
      "ui": {"label": null, "description": null, "component": null, "mode": null}
    },
    {
      "agent": "ApplicationIntakeAgent",
      "file": "submit_application.py",
      "function": "submit_application",
      "description": "Captures and normalizes application data for pipeline processing",
      "tool_type": "UI_Tool",
      "auto_invoke": true,
      "ui": {"label": "Submit Application", "description": "Submit your loan application", "component": "ApplicationForm", "display": "artifact", "mode": "artifact", "interaction_pattern": "multi_step"}
    },
    {
      "agent": "RiskComplianceAgent",
      "file": "run_risk_screening.py",
      "function": "run_risk_screening",
      "description": "Executes fraud detection and compliance checks",
      "tool_type": "Agent_Tool",
      "auto_invoke": null,
      "ui": {"label": null, "description": null, "component": null, "mode": null}
    },
    {
      "agent": "UnderwritingDecisionAgent",
      "file": "run_underwriting_decision.py",
      "function": "run_underwriting_decision",
      "description": "Executes credit analysis and generates approval decision with terms",
      "tool_type": "Agent_Tool",
      "auto_invoke": null,
      "ui": {"label": null, "description": null, "component": null, "mode": null}
    },
    {
      "agent": "OfferFulfillmentAgent",
      "file": "deliver_offer.py",
      "function": "deliver_offer",
      "description": "Packages and presents loan offer with acceptance workflow",
      "tool_type": "UI_Tool",
      "auto_invoke": true,
      "ui": {"label": "Review Offer", "description": "Review and accept your loan offer", "component": "OfferDisplay", "display": "artifact", "mode": "artifact", "interaction_pattern": "two_step_confirmation"}
    }
  ],
  "lifecycle_tools": [
    {
      "trigger": "before_agent",
      "agent": "ApplicationIntakeAgent",
      "file": "validate_intake_prerequisites.py",
      "function": "validate_intake_prerequisites",
      "description": "Validates required document uploads and applicant identity before processing begins",
      "tool_type": "Agent_Tool",
      "ui": {"label": null, "description": null, "component": null, "mode": null}
    },
    {
      "trigger": "after_agent",
      "agent": "ApplicationIntakeAgent",
      "file": "log_intake_metrics.py",
      "function": "log_intake_metrics",
      "description": "Records intake completion metrics and processing time after intake phase completes",
      "tool_type": "Agent_Tool",
      "ui": {"label": null, "description": null, "component": null, "mode": null}
    }
  ]
}""",
            
            7: """{
  "tools": [
    {
      "agent": "PlanningCoordinator",
      "file": "define_forecast_scenario.py",
      "function": "define_forecast_scenario",
      "description": "Captures planning window parameters and distributes to forecast agents",
      "tool_type": "Agent_Tool",
      "auto_invoke": null,
      "ui": {"label": null, "description": null, "component": null, "mode": null}
    },
    {
      "agent": "StatisticalForecastAgent",
      "file": "generate_statistical_forecast.py",
      "function": "generate_statistical_forecast",
      "description": "Generates time-series statistical forecast with confidence intervals",
      "tool_type": "Agent_Tool",
      "auto_invoke": null,
      "ui": {"label": null, "description": null, "component": null, "mode": null}
    },
    {
      "agent": "CausalForecastAgent",
      "file": "generate_causal_forecast.py",
      "function": "generate_causal_forecast",
      "description": "Generates causal inference forecast with driver attribution",
      "tool_type": "Agent_Tool",
      "auto_invoke": null,
      "ui": {"label": null, "description": null, "component": null, "mode": null}
    },
    {
      "agent": "HeuristicForecastAgent",
      "file": "generate_heuristic_forecast.py",
      "function": "generate_heuristic_forecast",
      "description": "Generates expert heuristic forecast with scenario planning",
      "tool_type": "Agent_Tool",
      "auto_invoke": null,
      "ui": {"label": null, "description": null, "component": null, "mode": null}
    },
    {
      "agent": "ForecastEvaluator",
      "file": "evaluate_forecasts.py",
      "function": "evaluate_forecasts",
      "description": "Scores all forecast approaches and selects optimal model with rationale",
      "tool_type": "Agent_Tool",
      "auto_invoke": null,
      "ui": {"label": null, "description": null, "component": null, "mode": null}
    }
  ],
  "lifecycle_tools": []
}""",
            
            8: """{
  "tools": [
    {
      "agent": "VendorIntakeCoordinator",
      "file": "analyze_vendor_requirements.py",
      "function": "analyze_vendor_requirements",
      "description": "Analyzes vendor submission and determines required review spokes",
      "tool_type": "Agent_Tool",
      "auto_invoke": null,
      "ui": {"label": null, "description": null, "component": null, "mode": null}
    },
    {
      "agent": "FinanceReviewAgent",
      "file": "review_financial_standing.py",
      "function": "review_financial_standing",
      "description": "Reviews vendor financial health and pricing structure",
      "tool_type": "Agent_Tool",
      "auto_invoke": null,
      "ui": {"label": null, "description": null, "component": null, "mode": null}
    },
    {
      "agent": "SecurityReviewAgent",
      "file": "review_security_posture.py",
      "function": "review_security_posture",
      "description": "Assesses vendor security controls and data protection measures",
      "tool_type": "Agent_Tool",
      "auto_invoke": null,
      "ui": {"label": null, "description": null, "component": null, "mode": null}
    },
    {
      "agent": "LegalReviewAgent",
      "file": "review_legal_compliance.py",
      "function": "review_legal_compliance",
      "description": "Reviews vendor contracts and regulatory compliance status",
      "tool_type": "Agent_Tool",
      "auto_invoke": null,
      "ui": {"label": null, "description": null, "component": null, "mode": null}
    },
    {
      "agent": "RiskAlignmentMediator",
      "file": "synthesize_review_findings.py",
      "function": "synthesize_review_findings",
      "description": "Aggregates all spoke findings and identifies cross-functional risks",
      "tool_type": "Agent_Tool",
      "auto_invoke": null,
      "ui": {"label": null, "description": null, "component": null, "mode": null}
    }
  ],
  "lifecycle_tools": []
}""",
            
            9: """{
  "tools": [
    {
      "agent": "AppTriageAgent",
      "file": "decompose_app_requirements.py",
      "function": "decompose_app_requirements",
      "description": "Decomposes app concept into categorized, prioritized task lists",
      "tool_type": "Agent_Tool",
      "auto_invoke": null,
      "ui": {"label": null, "description": null, "component": null, "mode": null}
    },
    {
      "agent": "DependencyPlanner",
      "file": "enforce_task_dependencies.py",
      "function": "enforce_task_dependencies",
      "description": "Validates task dependencies and enforces research→design→build sequence",
      "tool_type": "Agent_Tool",
      "auto_invoke": null,
      "ui": {"label": null, "description": null, "component": null, "mode": null}
    },
    {
      "agent": "ResearchScout",
      "file": "complete_research_task.py",
      "function": "complete_research_task",
      "description": "Executes market/tech research tasks and populates research deliverables",
      "tool_type": "Agent_Tool",
      "auto_invoke": null,
      "ui": {"label": null, "description": null, "component": null, "mode": null}
    },
    {
      "agent": "UXWireframeAgent",
      "file": "complete_design_task.py",
      "function": "complete_design_task",
      "description": "Creates UX wireframes and design specifications from research outputs",
      "tool_type": "Agent_Tool",
      "auto_invoke": null,
      "ui": {"label": null, "description": null, "component": null, "mode": null}
    },
    {
      "agent": "AppScaffoldBuilder",
      "file": "complete_build_task.py",
      "function": "complete_build_task",
      "description": "Generates code scaffolding and infrastructure from design specs",
      "tool_type": "Agent_Tool",
      "auto_invoke": null,
      "ui": {"label": null, "description": null, "component": null, "mode": null}
    },
    {
      "agent": "IntegrationAutomationAgent",
      "file": "complete_integration_task.py",
      "function": "complete_integration_task",
      "description": "Implements API integrations and automation workflows",
      "tool_type": "Agent_Tool",
      "auto_invoke": null,
      "ui": {"label": null, "description": null, "component": null, "mode": null}
    },
    {
      "agent": "FoundryLeadReviewer",
      "file": "validate_app_completion.py",
      "function": "validate_app_completion",
      "description": "Validates all tasks complete and app meets foundry quality standards",
      "tool_type": "Agent_Tool",
      "auto_invoke": null,
      "ui": {"label": null, "description": null, "component": null, "mode": null}
    }
  ],
  "lifecycle_tools": [
    {
      "trigger": "before_agent",
      "agent": "DependencyPlanner",
      "file": "load_task_dependency_graph.py",
      "function": "load_task_dependency_graph",
      "description": "Loads task dependency graph from triage output before dependency planning begins",
      "tool_type": "Agent_Tool",
      "ui": {"label": null, "description": null, "component": null, "mode": null}
    },
    {
      "trigger": "after_agent",
      "agent": "DependencyPlanner",
      "file": "persist_dependency_state.py",
      "function": "persist_dependency_state",
      "description": "Persists updated dependency state and task completion status after planning completes",
      "tool_type": "Agent_Tool",
      "ui": {"label": null, "description": null, "component": null, "mode": null}
    }
  ]
}"""
        }

        example_json = tools_examples.get(pattern_id)

        if not example_json:
            logger.warning(f"No tools example found for pattern_id {pattern_id}")
            return

        guidance = (
            f"[PATTERN EXAMPLE - {pattern_display_name}]\n"
            f"Reconcile every PhaseAgents.agent_tools entry with TechnicalBlueprint.ui_components before emitting the manifest. Mirror component names, display modes, labels, and interaction_pattern values from the blueprint so UI generators receive an authoritative contract.\n"
            f"Here is a complete ToolsManagerAgentOutput JSON example aligned with the {pattern_display_name} pattern.\n\n"
            f"```json\n{example_json}\n```\n"
        )

        if _apply_pattern_guidance(agent, guidance):
            logger.info(f"✓ Injected tools manager guidance for {pattern_display_name} into {agent.name}")
        else:
            logger.warning(f"Pattern guidance injection failed for {agent.name}")

    except Exception as e:
        logger.error(f"Error in inject_tools_manager_guidance: {e}", exc_info=True)

def inject_ui_file_generator_guidance(agent, messages: List[Dict[str, Any]]) -> None:
    """
    AG2 update_agent_state hook for UIFileGenerator.
    Injects pattern-specific UI tool generation guidance.
    
    UIFileGenerator OUTPUT FORMAT (UIFileGeneratorOutput JSON):
    {
      "tools": [
        {
          "tool_name": "<snake_case>",
          "py_content": "<complete_python_async_function>",
          "js_content": "<complete_react_component>"
        }
      ]
    }
    """
    try:
        pattern = _get_pattern_from_context(agent)
        if not pattern:
            logger.debug(f"No pattern available for {agent.name}, skipping guidance injection")
            return

        pattern_id = pattern.get('id')
        pattern_name = pattern.get('name')
        pattern_display_name = pattern.get('display_name', pattern_name)

        # Pattern-specific UIFileGeneratorOutput examples
        ui_examples = {
            1: """{
  "tools": []
}""",
            2: """{
  "tools": []
}""",
            3: """{
  "tools": [
    {
      "tool_name": "collect_structured_feedback",
  "py_content": "import logging\\nfrom typing import Any, Dict\\n\\nfrom core.workflow.ui_tools import UIToolError, use_ui_tool\\n\\nlogger = logging.getLogger(__name__)\\n\\nasync def collect_structured_feedback(StructuredOutput: Dict[str, Any], agent_message: str, **runtime) -> Dict[str, Any]:\\n    data = StructuredOutput or {}\\n    if 'chat_id' not in runtime:\\n        raise ValueError('chat_id missing from runtime context')\\n    workflow_name = runtime.get('workflow_name', 'Product Launch Copy Refinement')\\n    payload = {\\n        'campaignBrief': data.get('campaign_brief_snapshot', ''),\\n        'draftSummary': data.get('draft_summary', {}),\\n        'pillarPrompts': data.get('pillar_prompts', []),\\n        'iteration': data.get('iteration', 1),\\n        'agentMessage': agent_message\\n    }\\n    try:\\n        response = await use_ui_tool('FeedbackForm', payload, chat_id=runtime['chat_id'], workflow_name=workflow_name)\\n    except UIToolError as error:\\n        logger.exception('Feedback form failed to render', exc_info=error)\\n        raise\\n    if not isinstance(response, dict):\\n        raise TypeError('Feedback form must return a dict payload')\\n    missing_fields = {'needs_revision', 'pillar_scores', 'review_notes'} - set(response.keys())\\n    if missing_fields:\\n        raise ValueError(f'Feedback form response missing fields: {missing_fields}')\\n    return response\\n",
      "js_content": "import React, { useMemo, useState } from 'react';\\nimport PropTypes from 'prop-types';\\nimport { components, layouts, spacing, typography } from '../../../styles/artifactDesignSystem';\\n\\nconst FeedbackForm = ({ payload, onResponse }) => {\\n  const [reviewNotes, setReviewNotes] = useState('');\\n  const [needsRevision, setNeedsRevision] = useState(true);\\n  const [scores, setScores] = useState(() => (payload.pillarPrompts || []).map(prompt => ({ ...prompt, score: prompt.score ?? 3 })));\\n\\n  const scoresValid = useMemo(() => scores.every(item => item.score && item.score >= 1 && item.score <= 5), [scores]);\\n\\n  const handleScoreChange = (id, value) => {\\n    setScores(current => current.map(item => (item.id === id ? { ...item, score: Number(value) } : item)));\\n  };\\n\\n  const submitResponse = (event) => {\\n    event.preventDefault();\\n    if (!scoresValid) {\\n      return;\\n    }\\n    onResponse({\\n      needs_revision: needsRevision,\\n      pillar_scores: scores.map(({ id, label, score }) => ({ id, label, score })),\\n      review_notes: reviewNotes.trim()\\n    });\\n  };\\n\\n  return (\\n    <div className={layouts.artifactContainer}>\\n      <div className={components.card.primary}>\\n        <h1 className={typography.display.lg}>Stakeholder Feedback</h1>\\n        <p className={typography.body.md}>{payload.agentMessage}</p>\\n        <section className={spacing.stack.md}>\\n          {(payload.pillarPrompts || []).map(prompt => (\\n            <label key={prompt.id} className={components.form.label}>\\n              <span className={typography.body.lg}>{prompt.label}</span>\\n              <input\\n                type='range'\\n                min='1'\\n                max='5'\\n                value={scores.find(item => item.id === prompt.id)?.score ?? 3}\\n                onChange={(event) => handleScoreChange(prompt.id, event.target.value)}\\n                className={components.form.range}\\n              />\\n            </label>\\n          ))}\\n        </section>\\n        <div className={spacing.stack.md}>\\n          <textarea\\n            className={components.form.textarea}\\n            placeholder='Share actionable notes for the revision agent'\\n            value={reviewNotes}\\n            onChange={(event) => setReviewNotes(event.target.value)}\\n          />\\n          <label className={components.form.checkbox}>\\n            <input\\n              type='checkbox'\\n              checked={needsRevision}\\n              onChange={(event) => setNeedsRevision(event.target.checked)}\\n            />\\n            <span>Another revision cycle required?</span>\\n          </label>\\n        </div>\\n        <button type='submit' onClick={submitResponse} className={components.button.primary}>Submit feedback</button>\\n      </div>\\n    </div>\\n  );\\n};\\n\\nFeedbackForm.propTypes = {\\n  payload: PropTypes.shape({\\n    agentMessage: PropTypes.string,\\n    pillarPrompts: PropTypes.arrayOf(PropTypes.shape({\\n      id: PropTypes.string.isRequired,\\n      label: PropTypes.string.isRequired,\\n      score: PropTypes.number\\n    }))\\n  }).isRequired,\\n  onResponse: PropTypes.func.isRequired\\n};\\n\\nexport default FeedbackForm;\\n"
    },
    {
      "tool_name": "approve_campaign",
      "py_content": "import logging\\nfrom typing import Any, Dict\\n\\nfrom core.workflow.ui_tools import UIToolError, use_ui_tool\\n\\nlogger = logging.getLogger(__name__)\\n\\nasync def approve_campaign(StructuredOutput: Dict[str, Any], agent_message: str, **runtime) -> Dict[str, Any]:\\n    data = StructuredOutput or {}\\n    if 'chat_id' not in runtime:\\n        raise ValueError('chat_id missing from runtime context')\\n    workflow_name = runtime.get('workflow_name', 'Product Launch Copy Refinement')\\n    payload = {\\n        'approvalSummary': data.get('approval_summary', {}),\\n        'decisionOptions': data.get('decision_options', ['approved', 'changes_requested']),\\n        'agentMessage': agent_message\\n    }\\n    try:\\n        response = await use_ui_tool('ApprovalGate', payload, chat_id=runtime['chat_id'], workflow_name=workflow_name)\\n    except UIToolError as error:\\n        logger.exception('Approval gate failed to render', exc_info=error)\\n        raise\\n    if not isinstance(response, dict):\\n        raise TypeError('Approval gate must return a dict payload')\\n    if response.get('status') not in payload['decisionOptions']:\\n        raise ValueError('status must match one of the provided decision options')\\n    return response\\n",
      "js_content": "import React from 'react';\\nimport PropTypes from 'prop-types';\\nimport { components, layouts, typography } from '../../../styles/artifactDesignSystem';\\n\\nconst ApprovalGate = ({ payload, onResponse }) => {\\n  const emitDecision = (status) => {\\n    onResponse({\\n      status,\\n      approver: payload.approvalSummary?.approver || 'stakeholder',\\n      notes: payload.approvalSummary?.notes || ''\\n    });\\n  };\\n\\n  return (\\n    <div className={layouts.inlineCard}>\\n      <div className={components.card.secondary}>\\n        <h1 className={typography.display.md}>Approval Decision</h1>\\n        <p className={typography.body.md}>{payload.agentMessage}</p>\\n        <div className={components.stack.md}>\\n          <h2 className={typography.display.sm}>Current Summary</h2>\\n          <pre className={components.codeBlock}>{JSON.stringify(payload.approvalSummary, null, 2)}</pre>\\n        </div>\\n        <div className={components.inlineActions}>\\n          {payload.decisionOptions.map(option => (\\n            <button key={option} type='button' onClick={() => emitDecision(option)} className={components.button.primary}>\\n              {option === 'approved' ? 'Approve' : 'Request Revisions'}\\n            </button>\\n          ))}\\n        </div>\\n      </div>\\n    </div>\\n  );\\n};\\n\\nApprovalGate.propTypes = {\\n  payload: PropTypes.shape({\\n    agentMessage: PropTypes.string,\\n    approvalSummary: PropTypes.object,\\n    decisionOptions: PropTypes.arrayOf(PropTypes.string)\\n  }).isRequired,\\n  onResponse: PropTypes.func.isRequired\\n};\\n\\nexport default ApprovalGate;\\n"
    }
  ]
}""",
            4: """{
  "tools": []
}""",
            5: """{
  "tools": []
}""",
            6: """{
  "tools": [
    {
      "tool_name": "submit_application",
      "py_content": "import logging\\nfrom typing import Any, Dict\\n\\nfrom core.workflow.ui_tools import UIToolError, use_ui_tool\\n\\nlogger = logging.getLogger(__name__)\\n\\nasync def submit_application(StructuredOutput: Dict[str, Any], agent_message: str, **runtime) -> Dict[str, Any]:\\n    data = StructuredOutput or {}\\n    if 'chat_id' not in runtime:\\n        raise ValueError('chat_id missing from runtime context')\\n    workflow_name = runtime.get('workflow_name', 'Digital Loan Application Pipeline')\\n    payload = {\\n        'applicantProfile': data.get('applicant_profile', {}),\\n        'requestedAmount': data.get('requested_amount'),\\n        'loanProducts': data.get('eligible_products', []),\\n        'requiredDocuments': data.get('required_documents', []),\\n        'agentMessage': agent_message\\n    }\\n    try:\\n        response = await use_ui_tool('ApplicationForm', payload, chat_id=runtime['chat_id'], workflow_name=workflow_name)\\n    except UIToolError as error:\\n        logger.exception('Application form failed to render', exc_info=error)\\n        raise\\n    if not isinstance(response, dict):\\n        raise TypeError('Application form must return a dict payload')\\n    required_fields = {'applicant_profile', 'requested_amount', 'consent'}\\n    missing_fields = required_fields - set(response.keys())\\n    if missing_fields:\\n        raise ValueError(f'Application submission missing fields: {missing_fields}')\\n    return response\\n",
      "js_content": "import React, { useState } from 'react';\\nimport PropTypes from 'prop-types';\\nimport { components, layouts, spacing, typography } from '../../../styles/artifactDesignSystem';\\n\\nconst ApplicationForm = ({ payload, onResponse }) => {\\n  const [formData, setFormData] = useState({ ...payload.applicantProfile, requested_amount: payload.requestedAmount });\\n  const [consent, setConsent] = useState(false);\\n\\n  const updateField = (key, value) => {\\n    setFormData(current => ({ ...current, [key]: value }));\\n  };\\n\\n  const submitForm = (event) => {\\n    event.preventDefault();\\n    if (!consent) {\\n      return;\\n    }\\n    onResponse({\\n      applicant_profile: formData,\\n      requested_amount: Number(formData.requested_amount),\\n      consent: true,\\n      supporting_documents: payload.requiredDocuments\\n    });\\n  };\\n\\n  return (\\n    <div className={layouts.artifactContainer}>\\n      <form className={components.form.base} onSubmit={submitForm}>\\n        <h1 className={typography.display.lg}>Loan Application</h1>\\n        <p className={typography.body.md}>{payload.agentMessage}</p>\\n        <div className={spacing.stack.md}>\\n          <label className={components.form.label}>\\n            <span>Applicant Name</span>\\n            <input type='text' value={formData.full_name || ''} onChange={(event) => updateField('full_name', event.target.value)} className={components.form.input} required />\\n          </label>\\n          <label className={components.form.label}>\\n            <span>Email</span>\\n            <input type='email' value={formData.email || ''} onChange={(event) => updateField('email', event.target.value)} className={components.form.input} required />\\n          </label>\\n          <label className={components.form.label}>\\n            <span>Requested Amount</span>\\n            <input type='number' min='1000' value={formData.requested_amount || ''} onChange={(event) => updateField('requested_amount', event.target.value)} className={components.form.input} required />\\n          </label>\\n        </div>\\n        <section className={spacing.stack.md}>\\n          <h2 className={typography.display.sm}>Required Documents</h2>\\n          <ul className={components.list.bulleted}>\\n            {(payload.requiredDocuments || []).map(doc => (\\n              <li key={doc.id}>{doc.label}</li>\\n            ))}\\n          </ul>\\n        </section>\\n        <label className={components.form.checkbox}>\\n          <input type='checkbox' checked={consent} onChange={(event) => setConsent(event.target.checked)} />\\n          <span>I authorize the credit pull and attest information is accurate.</span>\\n        </label>\\n        <button type='submit' className={components.button.primary}>Submit application</button>\\n      </form>\\n    </div>\\n  );\\n};\\n\\nApplicationForm.propTypes = {\\n  payload: PropTypes.shape({\\n    agentMessage: PropTypes.string,\\n    applicantProfile: PropTypes.object,\\n    requestedAmount: PropTypes.oneOfType([PropTypes.number, PropTypes.string]),\\n    requiredDocuments: PropTypes.arrayOf(PropTypes.shape({ id: PropTypes.string, label: PropTypes.string }))\\n  }).isRequired,\\n  onResponse: PropTypes.func.isRequired\\n};\\n\\nexport default ApplicationForm;\\n"
    },
    {
      "tool_name": "deliver_offer",
      "py_content": "import logging\\nfrom typing import Any, Dict\\n\\nfrom core.workflow.ui_tools import UIToolError, use_ui_tool\\n\\nlogger = logging.getLogger(__name__)\\n\\nasync def deliver_offer(StructuredOutput: Dict[str, Any], agent_message: str, **runtime) -> Dict[str, Any]:\\n    data = StructuredOutput or {}\\n    if 'chat_id' not in runtime:\\n        raise ValueError('chat_id missing from runtime context')\\n    workflow_name = runtime.get('workflow_name', 'Digital Loan Application Pipeline')\\n    payload = {\\n        'offerSummary': data.get('offer_summary', {}),\\n        'rateTable': data.get('rate_table', []),\\n        'nextSteps': data.get('next_steps', []),\\n        'agentMessage': agent_message\\n    }\\n    try:\\n        response = await use_ui_tool('OfferDisplay', payload, chat_id=runtime['chat_id'], workflow_name=workflow_name)\\n    except UIToolError as error:\\n        logger.exception('Offer display failed to render', exc_info=error)\\n        raise\\n    if not isinstance(response, dict):\\n        raise TypeError('Offer display must return a dict payload')\\n    if 'accepted' not in response:\\n        raise ValueError('Offer response must include accepted flag')\\n    return response\\n",
      "js_content": "import React from 'react';\\nimport PropTypes from 'prop-types';\\nimport { components, layouts, typography } from '../../../styles/artifactDesignSystem';\\n\\nconst OfferDisplay = ({ payload, onResponse }) => {\\n  const acceptOffer = (accepted) => {\\n    onResponse({\\n      accepted,\\n      offer_status: accepted ? 'accepted' : 'declined',\\n      accepted_at: accepted ? new Date().toISOString() : null\\n    });\\n  };\\n\\n  return (\\n    <div className={layouts.artifactContainer}>\\n      <div className={components.card.primary}>\\n        <h1 className={typography.display.lg}>Loan Offer</h1>\\n        <p className={typography.body.md}>{payload.agentMessage}</p>\\n        <section className={components.stack.md}>\\n          <h2 className={typography.display.sm}>Summary</h2>\\n          <pre className={components.codeBlock}>{JSON.stringify(payload.offerSummary, null, 2)}</pre>\\n        </section>\\n        <section className={components.stack.md}>\\n          <h2 className={typography.display.sm}>Rate Table</h2>\\n          <pre className={components.codeBlock}>{JSON.stringify(payload.rateTable, null, 2)}</pre>\\n        </section>\\n        <section className={components.stack.md}>\\n          <h2 className={typography.display.sm}>Next Steps</h2>\\n          <ul className={components.list.numbered}>\\n            {(payload.nextSteps || []).map((step, index) => (\\n              <li key={index}>{step}</li>\\n            ))}\\n          </ul>\\n        </section>\\n        <div className={components.inlineActions}>\\n          <button type='button' className={components.button.primary} onClick={() => acceptOffer(true)}>Accept offer</button>\\n          <button type='button' className={components.button.tertiary} onClick={() => acceptOffer(false)}>Decline</button>\\n        </div>\\n      </div>\\n    </div>\\n  );\\n};\\n\\nOfferDisplay.propTypes = {\\n  payload: PropTypes.shape({\\n    agentMessage: PropTypes.string,\\n    offerSummary: PropTypes.object,\\n    rateTable: PropTypes.array,\\n    nextSteps: PropTypes.arrayOf(PropTypes.string)\\n  }).isRequired,\\n  onResponse: PropTypes.func.isRequired\\n};\\n\\nexport default OfferDisplay;\\n"
    }
  ]
}""",
            7: """{
  "tools": []
}""",
            8: """{
  "tools": []
}""",
            9: """{
  "tools": []
}"""
        }

        example_json = ui_examples.get(pattern_id)

        if not example_json:
            logger.warning(f"No UI tool example found for pattern_id {pattern_id}")
            return

        guidance = (
            f"[PATTERN EXAMPLE - {pattern_display_name}]\n"
            f"Here is a complete UIFileGeneratorOutput JSON example aligned with the {pattern_display_name} pattern.\n\n"
            f"```json\n{example_json}\n```\n"
        )
        
        if _apply_pattern_guidance(agent, guidance):
            logger.info(f"✓ Injected UI tool guidance for {pattern_display_name} into {agent.name}")
        else:
            logger.warning(f"Pattern guidance injection failed for {agent.name}")

    except Exception as e:
        logger.error(f"Error in inject_ui_file_generator_guidance: {e}", exc_info=True)


def inject_agent_tools_file_generator_guidance(agent, messages: List[Dict[str, Any]]) -> None:
    """
    AG2 update_agent_state hook for AgentToolsFileGenerator.
    Injects pattern-specific agent tool generation guidance.
    
    AgentToolsFileGenerator OUTPUT FORMAT (AgentToolsFileGeneratorOutput JSON):
    {
      "tools": [
        {
          "tool_name": "<snake_case>",
          "py_content": "<complete_python_function>"
        }
      ]
    }
    """
    try:
        pattern = _get_pattern_from_context(agent)
        if not pattern:
            logger.debug(f"No pattern available for {agent.name}, skipping guidance injection")
            return

        pattern_id = pattern.get('id')
        pattern_name = pattern.get('name')
        pattern_display_name = pattern.get('display_name', pattern_name)
        
        # TODO: Add pattern-specific agent tool examples here
        guidance = f"""
Pattern: {pattern_display_name}

Agent Tool Generation Guidelines:
- Generate complete Python functions for backend (py_content)
- Match tool_name exactly from tools manifest (no path prefixes)
- Include proper error handling and logging
- Return structured data that matches tool specifications
- Use sync or async based on agent auto_tool_mode
"""
        
        if _apply_pattern_guidance(agent, guidance):
            logger.info(f"✓ Injected agent tool guidance for {pattern_display_name} into {agent.name}")
        else:
            logger.warning(f"Pattern guidance injection failed for {agent.name}")

    except Exception as e:
        logger.error(f"Error in inject_agent_tools_file_generator_guidance: {e}", exc_info=True)


def inject_handoffs_guidance(agent, messages: List[Dict[str, Any]]) -> None:
    """
    AG2 update_agent_state hook for HandoffsAgent.
    Injects pattern-specific handoff rules into system message.

        HandoffsAgent OUTPUT FORMAT:
        Emit exactly one JSON object with the following structure:
        - handoff_rules: array of objects, each with
            - source_agent: str (the agent handing off)
            - target_agent: str (the agent receiving the handoff)
            - handoff_type: str ("condition" or "after_work")
            - condition_type: str or null ("expression", "string_llm", or null)
            - condition_scope: str or null ("pre" for ui_response triggers, null otherwise)
            - condition: str or null (expression/text or null)
            - transition_target: str or null (AgentNameTarget | RevertToUserTarget | GroupManagerTarget)
            - metadata: dict or null (additional routing context)
        - agent_message: str (<=140 chars summarizing routing design)
    """
    try:
        pattern = _get_pattern_from_context(agent)
        if not pattern:
            logger.debug(f"No pattern available for {agent.name}, skipping guidance injection")
            return

        agent_patterns = pattern.get('agent_patterns', {})
        coordination = agent_patterns.get('coordination', '')
        communication_flow = agent_patterns.get('communication_flow', '')
        required_roles = agent_patterns.get('required_roles', [])
        pattern_id = pattern.get('id')

        guidance = f"""

[INJECTED PATTERN GUIDANCE - {pattern['name']}]
The workflow requires the **{pattern['name']}** orchestration pattern.
CRITICAL: Your handoff rules MUST align with this pattern's coordination structure.

**Handoff Coordination Pattern:**
{coordination}

**Communication Flow:**
{communication_flow}

**Pattern-Specific Handoff Rules:**
"""

        # Pattern-specific handoff guidance
        if pattern_id == 1:  # Context-Aware Routing
            guidance += """
- Router agent must handoff to specialists based on content analysis
- Use LLM-based conditions for routing decisions (condition_type: "string_llm")
- Specialists should handoff back to router or directly to user/terminate
- No direct specialist-to-specialist handoffs
"""
        elif pattern_id == 2:  # Escalation
            guidance += """
- Progressive handoffs: Basic → Intermediate → Advanced
- Use confidence thresholds for escalation decisions
- After_work handoff type for level completion
- Condition-based handoffs for escalation triggers (low confidence, complexity detected)
"""
        elif pattern_id == 3:  # Feedback Loop
            guidance += """
- Creation phase → Review phase (after_work unconditional)
- Review phase → Revision phase (condition: quality not met)
- Revision phase → Creation phase (loop back)
- Review phase → Terminate (condition: quality threshold met)
- Track iteration count in context variables
"""
        elif pattern_id == 4:  # Hierarchical
            guidance += """
- Executive → Managers (delegation, after_work)
- Managers → Specialists (sequential per branch)
- Specialists → Managers (after_work unconditional)
- Managers → Executive (after_work unconditional)
- No cross-manager or cross-specialist handoffs
"""
        elif pattern_id == 5:  # Organic
            guidance += """
- Flexible handoffs based on agent descriptions
- Minimal explicit handoff rules (let AG2 auto-select)
- Any agent can handoff to any other agent
- Use after_work with null conditions for natural flow
"""
        elif pattern_id == 6:  # Pipeline
            guidance += """
- Strict sequential handoffs: Stage_1 → Stage_2 → Stage_3 → ... → Stage_N
- After_work unconditional handoffs between stages
- No backward handoffs (unidirectional flow)
- Final stage handoffs to user or terminate
"""
        elif pattern_id == 7:  # Redundant
            guidance += """
- Problem definition → Approach 1 → Approach 2 → Approach 3 (sequential after_work)
- Each approach → Evaluator (after_work unconditional from each branch)
- Evaluator → Selector (after_work unconditional)
- No cross-approach handoffs
"""
        elif pattern_id == 8:  # Star
            guidance += """
- Hub → Spoke agents (delegation, condition or after_work)
- Spokes → Hub (after_work unconditional)
- No spoke-to-spoke handoffs (all communication through hub)
- Hub can handoff to multiple spokes in sequence or based on conditions
"""
        elif pattern_id == 9:  # Triage with Tasks
            guidance += """
- Triage → Executor (after_work with task list)
- Executor → Task_1, Task_2, ..., Task_N (sequential after_work)
- Final task → Integrator (after_work unconditional)
- Use context variables to track task completion
"""

        guidance += f"""

**Required Agent Roles:**
"""
        for role in required_roles:
            guidance += f"\n- {role}"

        guidance += """

**Handoff Type Guidelines:**
- **after_work**: Agent completes its work, then handoff evaluates (use for sequential flows)
- **condition**: Evaluate handoff immediately (use for branching logic, escalation triggers)

**Condition Type Guidelines:**
- **expression** (${...}): Context variable evaluation (use for derived variables set by agents/tools)
- **string_llm**: Natural language evaluation by LLM (use for content-based routing, quality checks)

**Condition Scope Guidelines:**
- **null**: Default evaluation (use for agent_text triggers, after_work flows)
- **pre**: Pre-reply evaluation (use for UI interactions, derived variables from UI tools)
- **post**: Post-reply evaluation (use for agent output analysis)
"""

        if _apply_pattern_guidance(agent, guidance):
            logger.info(f"✓ Injected handoff guidance into {agent.name}")
        else:
            logger.warning(f"Handoff guidance injection fell back for {agent.name}")

    except Exception as e:
        logger.error(f"Error in inject_handoffs_guidance: {e}", exc_info=True)




def inject_structured_outputs_guidance(agent, messages: List[Dict[str, Any]]) -> None:
    """
    AG2 update_agent_state hook for StructuredOutputsAgent.
    Injects pattern-specific structured output schema generation guidance.
    
    StructuredOutputsAgent OUTPUT FORMAT (StructuredOutputsAgentOutput JSON):
    {
      "models": [
        {
          "model_name": "<PascalCase>",
          "fields": [
            {
              "name": "<snake_case>",
              "type": "str|int|bool|List[...]|Dict[...]",
              "description": "<field purpose and constraints>"
            }
          ]
        }
      ],
      "registry": [
        {
          "agent": "<PascalCaseAgentName>",
          "agent_definition": "<ModelName>" | null
        }
      ]
    }
    """
    try:
        pattern = _get_pattern_from_context(agent)
        if not pattern:
            logger.debug(f"No pattern available for {agent.name}, skipping guidance injection")
            return

        pattern_id = pattern.get('id')
        pattern_name = pattern.get('name')
        pattern_display_name = pattern.get('display_name', pattern_name)
        
        # TODO: Add pattern-specific structured output examples here
        guidance = f"""
Pattern: {pattern_display_name}

Structured Output Schema Guidelines:
- Define Pydantic models for ALL agents with structured_outputs_required=true
- Use PascalCase for model names, snake_case for field names
- Include comprehensive field descriptions with constraints
- Map EVERY agent in registry to either a model or null
- Use proper type hints (str, int, bool, List[...], Dict[...])
"""
        
        if _apply_pattern_guidance(agent, guidance):
            logger.info(f"✓ Injected structured outputs guidance for {pattern_display_name} into {agent.name}")
        else:
            logger.warning(f"Pattern guidance injection failed for {agent.name}")

    except Exception as e:
        logger.error(f"Error in inject_structured_outputs_guidance: {e}", exc_info=True)


def inject_agents_agent_guidance(agent, messages: List[Dict[str, Any]]) -> None:
    """
    AG2 update_agent_state hook for AgentsAgent.
    Injects pattern-specific runtime agent configuration guidance.
    
    AgentsAgent OUTPUT FORMAT (RuntimeAgentsCall JSON):
    {
      "agents": [
        {
          "name": "<PascalCaseAgentName>",
          "display_name": "<Display Name>",
          "prompt_sections": [
            {"id": "<section_id>", "heading": "[SECTION HEADING]", "content": "<section content>"}
          ],
          "max_consecutive_auto_reply": <int>,
          "auto_tool_mode": true|false,
          "structured_outputs_required": true|false
        }
      ],
      "agent_message": "<Summary>"
    }
    """
    try:
        pattern = _get_pattern_from_context(agent)
        if not pattern:
            logger.debug(f"No pattern available for {agent.name}, skipping guidance injection")
            return

        pattern_id = pattern.get('id')
        pattern_name = pattern.get('name')
        pattern_display_name = pattern.get('display_name', pattern_name)
        
        # TODO: Add pattern-specific agent configuration examples here
        guidance = f"""
Pattern: {pattern_display_name}

Runtime Agent Configuration Guidelines:
- Generate complete prompt_sections for each agent (9 standard sections)
- Set appropriate max_consecutive_auto_reply based on complexity (5-20)
- Enable auto_tool_mode for agents with UI tools
- Set structured_outputs_required for agents that emit JSON
- Include clear role, objective, context, and guidelines sections
"""
        
        if _apply_pattern_guidance(agent, guidance):
            logger.info(f"✓ Injected agents configuration guidance for {pattern_display_name} into {agent.name}")
        else:
            logger.warning(f"Pattern guidance injection failed for {agent.name}")

    except Exception as e:
        logger.error(f"Error in inject_agents_agent_guidance: {e}", exc_info=True)


def inject_hook_agent_guidance(agent, messages: List[Dict[str, Any]]) -> None:
    """
    AG2 update_agent_state hook for HookAgent.
    Injects pattern-specific system hook generation guidance.
    
    HookAgent OUTPUT FORMAT (HookImplementationCall JSON):
    {
      "hook_files": [
        {
          "filename": "<hook_name>.py",
          "hook_type": "before_chat|after_chat|update_agent_state",
          "py_content": "<Python hook function code>"
        }
      ],
      "agent_message": "<Summary of hook generation>"
    }
    """
    try:
        pattern = _get_pattern_from_context(agent)
        if not pattern:
            logger.debug(f"No pattern available for {agent.name}, skipping guidance injection")
            return

        pattern_id = pattern.get('id')
        pattern_name = pattern.get('name')
        pattern_display_name = pattern.get('display_name', pattern_name)
        
        # TODO: Add pattern-specific hook examples here
        guidance = f"""
Pattern: {pattern_display_name}

System Hook Generation Guidelines:
- Generate complete Python hook functions (py_content)
- Use appropriate hook_type (before_chat, after_chat, update_agent_state)
- Include proper parameter handling (agent, messages)
- Add error handling and logging
- Return empty hook_files[] array if no custom hooks needed
"""
        
        if _apply_pattern_guidance(agent, guidance):
            logger.info(f"✓ Injected hook generation guidance for {pattern_display_name} into {agent.name}")
        else:
            logger.warning(f"Pattern guidance injection failed for {agent.name}")

    except Exception as e:
        logger.error(f"Error in inject_hook_agent_guidance: {e}", exc_info=True)


def inject_orchestrator_guidance(agent, messages: List[Dict[str, Any]]) -> None:
    """
    AG2 update_agent_state hook for OrchestratorAgent.
    Injects pattern-specific orchestration configuration guidance.
    
    OrchestratorAgent OUTPUT FORMAT (OrchestratorAgentOutput JSON):
    {
      "workflow_name": "<WorkflowName>",
      "max_turns": <int>,
      "human_in_the_loop": true,
      "startup_mode": "AgentDriven|UserDriven",
      "orchestration_pattern": "<PatternName>",
      "initial_message_to_user": null,
      "initial_message": "<greeting string>|null",
      "recipient": "<FirstAgentName>",
      "visual_agents": ["<AgentName1>", "<AgentName2>"],
      "agent_message": "<Summary of orchestration config>"
    }
    """
    try:
        pattern = _get_pattern_from_context(agent)
        if not pattern:
            logger.debug(f"No pattern available for {agent.name}, skipping guidance injection")
            return

        pattern_id = pattern.get('id')
        pattern_name = pattern.get('name')
        pattern_display_name = pattern.get('display_name', pattern_name)
        
        # TODO: Add pattern-specific orchestration examples here
        guidance = f"""
Pattern: {pattern_display_name}

Orchestration Configuration Guidelines:
- Set max_turns appropriately (20-30 typical)
- Choose startup_mode: AgentDriven (agent starts) or UserDriven (user starts)
- Set initial_message for AgentDriven mode, null for UserDriven
- Set recipient to first agent from phases[0].agents[0]
- Include all agents with UI tools in visual_agents array
- Set human_in_the_loop based on workflow requirements
"""
        
        if _apply_pattern_guidance(agent, guidance):
            logger.info(f"✓ Injected orchestration guidance for {pattern_display_name} into {agent.name}")
        else:
            logger.warning(f"Pattern guidance injection failed for {agent.name}")

    except Exception as e:
        logger.error(f"Error in inject_orchestrator_guidance: {e}", exc_info=True)


def inject_download_agent_guidance(agent, messages: List[Dict[str, Any]]) -> None:
    """
    AG2 update_agent_state hook for DownloadAgent.
    Injects pattern-specific download message generation guidance.
    
    DownloadAgent OUTPUT FORMAT (DownloadRequestCall JSON):
    {
      "agent_message": "<Brief context message for UI>"
    }
    """
    try:
        pattern = _get_pattern_from_context(agent)
        if not pattern:
            logger.debug(f"No pattern available for {agent.name}, skipping guidance injection")
            return

        pattern_id = pattern.get('id')
        pattern_name = pattern.get('name')
        pattern_display_name = pattern.get('display_name', pattern_name)
        
        # TODO: Add pattern-specific download message examples here
        guidance = f"""
Pattern: {pattern_display_name}

Download Message Guidelines:
- Keep agent_message brief (<=140 chars)
- Message should provide context for download UI
- Examples: "Your workflow is ready for download", "Download complete workflow package"
- Message triggers download tool automatically
"""
        
        if _apply_pattern_guidance(agent, guidance):
            logger.info(f"✓ Injected download message guidance for {pattern_display_name} into {agent.name}")
        else:
            logger.warning(f"Pattern guidance injection failed for {agent.name}")

    except Exception as e:
        logger.error(f"Error in inject_download_agent_guidance: {e}", exc_info=True)
