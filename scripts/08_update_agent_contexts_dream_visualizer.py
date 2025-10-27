#!/usr/bin/env python3
"""
Update all Generator agent [EXAMPLE] sections to use StoryCreator as canonical example.

Strategy:
1. Find current [EXAMPLE] sections in each agent's system_message
2. Replace them with StoryCreator-specific examples
3. Preserve all other sections unchanged
"""

import json
import re
from pathlib import Path

def update_agent_examples():
    """
    Replace [EXAMPLE] sections in Generator agent system messages with StoryCreator examples.
    """
    
    agents_json_path = Path("workflows/Generator/agents.json")
    
    # Read current agents.json
    with open(agents_json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Map of agent names to their new StoryCreator examples
    # These replace the existing Generator-specific examples (WeeklyInsightEngine, InvoiceAutomation, CustomQuoteBuilder)
    story_examples = {
        "ActionPlanArchitect": """[EXAMPLE - StoryCreator Workflow]
{
  "ActionPlan": {
    "workflow": {
      "name": "StoryCreator",
      "model": "gpt-4o-mini",
      "description": "When users want to create visual stories, this workflow interviews them via text chat about their story idea, extracts key visual elements and cinematographic variables from their responses, crafts an optimized prompt for Google Veo 3 video generation, generates the cinematic video, posts it to their personal Storyboard for review and organization, and optionally shares to social media platforms via Blotato integration. This transforms simple story ideas into professional video content through specialized prompt engineering.",
      "initiated_by": "user",
      "trigger_type": "chat_start",
      "interaction_mode": "checkpoint_approval",
      "phases": [
        {
          "name": "Phase 1: Story Interview",
          "description": "Ask user targeted questions about their story idea to gather creative details.",
          "agents": [
            {
              "name": "InterviewAgent",
              "description": "Conducts structured text-based interview asking about characters, setting, conflict, and emotional tone.",
              "human_interaction": "context",
              "integrations": [],
              "operations": []
            }
          ]
        },
        {
          "name": "Phase 2: Veo 3 Prompt Engineering",
          "description": "Extract context variables and build optimized Veo 3 prompt.",
          "agents": [
            {
              "name": "ContextExtractionAgent",
              "description": "Analyzes story brief to extract key visual elements, camera angles, lighting, mood, and pacing for Veo 3.",
              "human_interaction": "none",
              "integrations": [],
              "operations": ["extract_video_elements", "update_context_variables"]
            },
            {
              "name": "PromptAgent",
              "description": "Builds detailed Veo 3 prompt using extracted visual elements and cinematographic specifications.",
              "human_interaction": "none",
              "integrations": [],
              "operations": ["build_veo3_prompt"]
            }
          ]
        },
        {
          "name": "Phase 3: Video Generation",
          "description": "Generate cinematic video using Google Veo 3.",
          "agents": [
            {
              "name": "VideoAgent",
              "description": "Executes Veo 3 API call with optimized prompt to generate video.",
              "human_interaction": "none",
              "integrations": ["GoogleVeo"],
              "operations": ["call_veo3_api", "monitor_generation", "download_video"]
            }
          ]
        },
        {
          "name": "Phase 4: Video Approval",
          "description": "Ask user if they agree with the video content.",
          "agents": [
            {
              "name": "VideoApprovalAgent",
              "description": "Shows video preview and asks user to confirm approval.",
              "human_interaction": "approval",
              "integrations": [],
              "operations": ["show_preview", "capture_decision"]
            }
          ]
        },
        {
          "name": "Phase 5: Storyboard Posting",
          "description": "Post completed video to user's personal Storyboard for review.",
          "agents": [
            {
              "name": "ThumbnailAgent",
              "description": "Generates eye-catching thumbnail for the video using Midjourney.",
              "human_interaction": "none",
              "integrations": ["Midjourney"],
              "operations": ["extract_key_frame", "generate_thumbnail_prompt", "create_thumbnail"]
            },
            {
              "name": "StoryboardAgent",
              "description": "Saves video to user's Storyboard with metadata and thumbnail.",
              "human_interaction": "none",
              "integrations": ["MongoDB"],
              "operations": ["save_video", "attach_thumbnail", "tag_story"]
            }
          ]
        },
        {
          "name": "Phase 6: Share Approval",
          "description": "Ask user if they want to share story to social media.",
          "agents": [
            {
              "name": "ShareApprovalAgent",
              "description": "Shows video preview and asks user to confirm social media sharing.",
              "human_interaction": "approval",
              "integrations": [],
              "operations": ["show_preview", "capture_decision"]
            }
          ]
        },
        {
          "name": "Phase 7: Social Distribution",
          "description": "Share approved story to social platforms via Blotato.",
          "agents": [
            {
              "name": "BlotatoAgent",
              "description": "Posts video to selected social platforms using Blotato API.",
              "human_interaction": "none",
              "integrations": ["Blotato"],
              "operations": ["select_platforms", "format_post", "track_engagement"]
            }
              "operations": []
            }
          ]
        }
      ]
    }
  },
  "agent_message": "Review your story creation workflow before launching."
}""",

        "ProjectOverviewAgent": """[EXAMPLE - StoryCreator Sequence Diagram]
{
  "MermaidSequenceDiagram": {
    "workflow_name": "StoryCreator",
    "mermaid_diagram": "sequenceDiagram\\n    participant User\\n    participant P1 as InterviewAgent\\n    participant P2A as ContextExtractionAgent\\n    participant P2B as PromptAgent\\n    participant P3 as VideoAgent\\n    participant P4 as VideoApprovalAgent\\n    participant P5A as ThumbnailAgent\\n    participant P5B as StoryboardAgent\\n    participant P6 as ShareApprovalAgent\\n    participant P7 as BlotatoAgent\\n\\n    User->>P1: Describe story idea\\n    P1->>User: Ask clarifying questions\\n    User->>P1: Provide story details\\n    P1->>P2A: Hand off story brief\\n    P2A->>P2B: Extract visual context\\n    P2B->>P3: Build optimized Veo 3 prompt\\n    P3->>P4: Generate video\\n    P4->>User: Show video preview\\n    User->>P4: Approve video\\n    P4->>P5A: Proceed to storyboard\\n    P5A->>P5B: Generate thumbnail via Midjourney\\n    P5B->>P6: Save to Storyboard\\n    P6->>User: Show sharing options\\n    User->>P6: Approve social sharing\\n    P6->>P7: Proceed with posting\\n    P7->>User: Story shared via Blotato",
    "legend": [
      "P1: Story Interview",
      "P2A & P2B: Veo 3 Prompt Engineering (2 agents)",
      "P3: Video Generation",
      "P4: Video Approval",
      "P5A & P5B: Storyboard Posting (2 agents: thumbnail + save)",
      "P6: Share Approval",
      "P7: Social Distribution"
    ]
  },
  "agent_message": "Review the story creator workflow sequence."
}""",

        "ContextVariablesAgent": """[EXAMPLE - StoryCreator Context Variables]
{
  "ContextVariablesPlan": {
    "context_variables": [
      {
        "name": "story_brief",
        "type": "str",
        "description": "Compiled story brief from interview responses",
        "default_value": null,
        "required": true
      },
      {
        "name": "veo3_context",
        "type": "dict",
        "description": "Extracted visual elements, cinematography specs, and mood palette for Veo 3",
        "default_value": {},
        "required": false
      },
      {
        "name": "veo3_prompt",
        "type": "str",
        "description": "Optimized prompt for Google Veo 3 video generation",
        "default_value": null,
        "required": false
      },
      {
        "name": "video_url",
        "type": "str",
        "description": "Generated video URL from Veo 3",
        "default_value": null,
        "required": false
      },
      {
        "name": "thumbnail_url",
        "type": "str",
        "description": "Midjourney-generated thumbnail URL",
        "default_value": null,
        "required": false
      },
      {
        "name": "storyboard_id",
        "type": "str",
        "description": "ID of saved storyboard entry",
        "default_value": null,
        "required": false
      },
      {
        "name": "share_approved",
        "type": "bool",
        "description": "User approval flag for social media posting",
        "default_value": false,
        "required": true
      }
    ],
    "agent_message": "Configure story workflow runtime variables."
  }
}""",

        "ToolsManagerAgent": """[EXAMPLE - StoryCreator Tools Manifest]
{
  "tools": [
    {
      "agent": "InterviewAgent",
      "file": "story_interview.py",
      "function": "story_interview",
      "description": "Conduct text-based interview about story idea",
      "tool_type": "Agent_Tool",
      "ui": null
    },
    {
      "agent": "ContextExtractionAgent",
      "file": "extract_veo3_context.py",
      "function": "extract_veo3_context",
      "description": "Extract visual elements and cinematographic variables from story brief",
      "tool_type": "Agent_Tool",
      "ui": null
    },
    {
      "agent": "PromptAgent",
      "file": "build_veo3_prompt.py",
      "function": "build_veo3_prompt",
      "description": "Build optimized Veo 3 prompt from extracted context",
      "tool_type": "Agent_Tool",
      "ui": null
    },
    {
      "agent": "VideoAgent",
      "file": "generate_veo_video.py",
      "function": "generate_veo_video",
      "description": "Generate video using Google Veo 3 with optimized prompt",
      "tool_type": "Agent_Tool",
      "ui": null
    },
    {
      "agent": "ThumbnailAgent",
      "file": "generate_thumbnail.py",
      "function": "generate_thumbnail",
      "description": "Generate eye-catching thumbnail using Midjourney API",
      "tool_type": "Agent_Tool",
      "ui": null
    },
    {
      "agent": "StoryboardAgent",
      "file": "save_to_storyboard.py",
      "function": "save_to_storyboard",
      "description": "Save video to user's personal Storyboard",
      "tool_type": "Agent_Tool",
      "ui": null
    },
    {
      "agent": "ShareApprovalAgent",
      "file": "approval_preview.py",
      "function": "approval_preview",
      "description": "Show video preview and capture user approval decision",
      "tool_type": "UI_Tool",
      "ui": {
        "component": "ApprovalPreview",
        "mode": "inline"
      }
    },
    {
      "agent": "BlotatoAgent",
      "file": "blotato_share.py",
      "function": "blotato_share",
      "description": "Share video to social platforms via Blotato API",
      "tool_type": "Agent_Tool",
      "ui": null
    },
    {
      "agent": "System",
      "file": "runtime_context_manager.py",
      "function": "runtime_context_manager",
      "description": "Manages runtime context and state",
      "tool_type": "Agent_Tool",
      "ui": null
    }
  ],
  "agent_modes": [
    { "agent": "InterviewAgent", "auto_tool_mode": false },
    { "agent": "ContextExtractionAgent", "auto_tool_mode": true },
    { "agent": "PromptAgent", "auto_tool_mode": true },
    { "agent": "VideoAgent", "auto_tool_mode": true },
    { "agent": "ThumbnailAgent", "auto_tool_mode": true },
    { "agent": "StoryboardAgent", "auto_tool_mode": true },
    { "agent": "ShareApprovalAgent", "auto_tool_mode": true },
    { "agent": "BlotatoAgent", "auto_tool_mode": false }
  ]
}""",

        "UIFileGenerator": """[EXAMPLE - StoryCreator UI Tool]
{
  "tools": [
    {
      "tool_name": "approval_preview",
      "py_content": \"\"\"async def approval_preview(*, video_url: str, storyboard_id: str, **runtime) -> dict:
    payload = {
        'video_url': video_url,
        'storyboard_id': storyboard_id,
        'agent_message': 'Review your story video before sharing to social media'
    }
    return await use_ui_tool('ApprovalPreview', payload, chat_id=runtime['chat_id'], workflow_name='StoryCreator')
\"\"\",
      "js_content": \"\"\"const ApprovalPreview = ({ payload, onResponse }) => {
  return (
    <div className={layouts.artifactContainer}>
      <video src={payload.video_url} controls />
      <button onClick={() => onResponse({ status: 'approved' })} className={components.button.primary}>
        Share to Social
      </button>
      <button onClick={() => onResponse({ status: 'rejected' })} className={components.button.secondary}>
        Keep Private
      </button>
    </div>
  );
};
\"\"\"
    }
  ]
}""",

        "AgentToolsFileGenerator": """[EXAMPLE - StoryCreator Agent Tool]
{
  "tools": [
    {
      "tool_name": "generate_veo_video",
      "py_content": \"\"\"import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

async def generate_veo_video(*, story_brief: str, **runtime) -> Dict[str, Any]:
    if not story_brief:
        raise ValueError('story_brief is required')
    logger.info('Generating video using Google Veo 3')
    # Integration: Google Veo 3 API
    # Returns: { 'status': 'success', 'video_url': '...' }
    return {
        'status': 'success',
        'video_url': 'https://storage.googleapis.com/veo/story_12345.mp4'
    }
\"\"\"
    }
  ]
}""",

        "AgentsAgent": """[EXAMPLE - StoryCreator Agent Definition]
{
  "agents": [
    {
      "name": "InterviewAgent",
      "display_name": "Story Interview",
      "system_message": "[ROLE] You conduct structured interviews about story ideas...\\n\\n[CONTEXT VARIABLES]\\nYou have access to:\\n- story_brief (str): Compiled interview responses\\n\\n[COORDINATION]\\nAfter interview complete, emit INTERVIEW_COMPLETE token.",
      "max_consecutive_auto_reply": 5,
      "auto_tool_mode": false,
      "structured_outputs_required": false
    },
    {
      "name": "ThumbnailAgent",
      "display_name": "Thumbnail Generator",
      "system_message": "[ROLE] You generate story thumbnails using DALL-E AI image generation...\\n\\n[IMAGE GENERATION CAPABILITY]\\nYou have AG2's ImageGeneration capability enabled. To generate images:\\n1. Describe the image you want in conversational text\\n2. AG2's capability automatically detects image generation intent\\n3. DALL-E renders the image and returns it in the conversation\\n4. Extract the image from conversation history when needed\\n\\n[CONTEXT VARIABLES]\\nYou have access to:\\n- veo3_prompt (str): Optimized video prompt for visual consistency\\n- story_brief (str): Story context for thumbnail design",
      "max_consecutive_auto_reply": 5,
      "auto_tool_mode": true,
      "structured_outputs_required": false,
      "image_generation_enabled": true
    },
    {
      "name": "ShareApprovalAgent",
      "display_name": "Share Approval",
      "system_message": "[ROLE] You present the story video preview and capture user approval...\\n\\n[UI TOOL]\\n- Tool: workflows/StoryCreator/tools/approval_preview.py\\n- Component: ChatUI/src/workflows/StoryCreator/components/ApprovalPreview.js",
      "max_consecutive_auto_reply": 5,
      "auto_tool_mode": true,
      "structured_outputs_required": true
    }
  ]
}""",

        "StructuredOutputsAgent": """[EXAMPLE - StoryCreator Structured Outputs]
{
  "models": [
    {
      "model_name": "StoryBriefOutput",
      "fields": [
        {"name": "characters", "type": "list[Character]", "description": "Main characters in the story"},
        {"name": "setting", "type": "str", "description": "Physical and temporal setting"},
        {"name": "plot", "type": "str", "description": "Core plot summary"},
        {"name": "tone", "type": "str", "description": "Emotional tone (dramatic, comedic, suspenseful, etc.)"},
        {"name": "agent_message", "type": "str", "description": "Message to user (≤140 chars)"}
      ]
    },
    {
      "model_name": "Character",
      "fields": [
        {"name": "name", "type": "str", "description": "Character name"},
        {"name": "role", "type": "str", "description": "Protagonist, antagonist, supporting, etc."},
        {"name": "traits", "type": "list[str]", "description": "Key personality traits"}
      ]
    }
  ],
  "registry": [
    {"agent": "InterviewAgent", "agent_definition": "StoryBriefOutput"},
    {"agent": "VideoAgent", "agent_definition": null}
  ]
}""",

        "HookAgent": """[EXAMPLE - StoryCreator Hooks]
{
  "hooks": []
}""",

        "HandoffsAgent": """[EXAMPLE - StoryCreator Handoffs]
{
  "handoff_rules": [
    {
      "source_agent": "InterviewAgent",
      "target_agent": "ContextExtractionAgent",
      "handoff_type": "after_work",
      "condition_type": null,
      "condition_scope": null,
      "condition": null,
      "transition_target": "AgentTarget"
    },
    {
      "source_agent": "ContextExtractionAgent",
      "target_agent": "PromptAgent",
      "handoff_type": "after_work",
      "condition_type": null,
      "condition_scope": null,
      "condition": null,
      "transition_target": "AgentTarget"
    },
    {
      "source_agent": "PromptAgent",
      "target_agent": "VideoAgent",
      "handoff_type": "after_work",
      "condition_type": null,
      "condition_scope": null,
      "condition": null,
      "transition_target": "AgentTarget"
    },
    {
      "source_agent": "VideoAgent",
      "target_agent": "ThumbnailAgent",
      "handoff_type": "after_work",
      "condition_type": null,
      "condition_scope": null,
      "condition": null,
      "transition_target": "AgentTarget"
    },
    {
      "source_agent": "ThumbnailAgent",
      "target_agent": "StoryboardAgent",
      "handoff_type": "after_work",
      "condition_type": null,
      "condition_scope": null,
      "condition": null,
      "transition_target": "AgentTarget"
    },
    {
      "source_agent": "StoryboardAgent",
      "target_agent": "ShareApprovalAgent",
      "handoff_type": "after_work",
      "condition_type": null,
      "condition_scope": null,
      "condition": null,
      "transition_target": "AgentTarget"
    },
    {
      "source_agent": "user",
      "target_agent": "BlotatoAgent",
      "handoff_type": "condition",
      "condition_type": "expression",
      "condition_scope": "pre",
      "condition": "${share_approved} == true",
      "transition_target": "AgentTarget"
    },
    {
      "source_agent": "user",
      "target_agent": "TERMINATE",
      "handoff_type": "condition",
      "condition_type": "expression",
      "condition_scope": "pre",
      "condition": "${share_approved} == false",
      "transition_target": "AgentTarget"
    }
  ]
}""",

        "OrchestratorAgent": """[EXAMPLE - StoryCreator Orchestrator]
{
  "workflow_name": "StoryCreator",
  "max_turns": 20,
  "human_in_the_loop": true,
  "startup_mode": "AgentDriven",
  "orchestration_pattern": "DefaultPattern",
  "initial_message_to_user": null,
  "initial_message": "Welcome to Story Creator! Tell me your story idea and I'll help you bring it to life as a video.",
  "recipient": "InterviewAgent",
  "visual_agents": ["InterviewAgent", "ShareApprovalAgent"]
}"""
    }
    
    updated_count = 0
    
    for agent_name, new_example in story_examples.items():
        if agent_name not in data['agents']:
            print(f"⚠️  Agent '{agent_name}' not found in agents.json, skipping")
            continue
        
        current_system_message = data['agents'][agent_name]['system_message']
        
        # Pattern to find [EXAMPLE sections - matches from [EXAMPLE to the next section marker
        # This will match patterns like:
        # [EXAMPLE 1 - ...] ... [EXAMPLE 2 - ...] ... [EXAMPLE 3 - ...]
        # and replace ALL of them with the single new example
        
        example_pattern = r'\[EXAMPLE[^\]]*\].*?(?=\n\[(?:OUTPUT FORMAT|ALGORITHM|INSTRUCTIONS|NOTES|FAILURE|QUALITY|CANONICAL)|$)'
        
        # Count how many examples exist
        matches = list(re.finditer(example_pattern, current_system_message, flags=re.DOTALL))
        
        if not matches:
            print(f"⚠️  No [EXAMPLE] section found in {agent_name}, skipping")
            continue
        
        # Replace ALL [EXAMPLE] sections with the new single example
        new_system_message = re.sub(
            example_pattern,
            new_example,
            current_system_message,
            count=1,  # Replace only the first match group (which captures all examples)
            flags=re.DOTALL
        )
        
        # If there are multiple examples, remove the extras
        if len(matches) > 1:
            # Keep replacing until all [EXAMPLE patterns are gone except our new one
            for _ in range(len(matches) - 1):
                new_system_message = re.sub(
                    example_pattern,
                    '',
                    new_system_message,
                    count=1,
                    flags=re.DOTALL
                )
        
        data['agents'][agent_name]['system_message'] = new_system_message
        updated_count += 1
        
        print(f"✅ Updated {agent_name} - replaced {len(matches)} example(s) with StoryCreator")
    
    # Write back to file
    with open(agents_json_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Successfully updated {updated_count} agents with StoryCreator examples")
    print(f"📄 Replaced Generator-specific examples (WeeklyInsightEngine, InvoiceAutomation, CustomQuoteBuilder)")
    print(f"🎯 New canonical: StoryCreator (7-phase checkpoint_approval workflow)")
    print(f"💡 Pattern: interview → prompt engineering (2 agents) → video → approval → thumbnail + storyboard (2 agents) → share approval → social")
    print(f"🎬 Multi-agent phases: Phase 2 (ContextExtraction → Prompt), Phase 5 (Thumbnail → Storyboard)")
    print(f"📝 Empty operations[] arrays show phases can be pure chat sequences (OpenAI LLM assumed)")
    
    return updated_count > 0

if __name__ == "__main__":
    success = update_agent_examples()
    exit(0 if success else 1)
