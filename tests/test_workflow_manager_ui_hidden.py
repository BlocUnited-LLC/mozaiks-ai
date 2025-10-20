from pathlib import Path
from typing import Dict, Any

from core.workflow.workflow_manager import UnifiedWorkflowManager


def _make_manager(config: Dict[str, Any]) -> UnifiedWorkflowManager:
    manager = object.__new__(UnifiedWorkflowManager)
    manager.workflows_base_path = Path(".")
    manager._workflows = {}
    manager._config_cache = {"test": config}
    return manager


def test_ui_hidden_triggers_handles_legacy_variables_schema():
    config = {
        "context_variables": {
            "context_variables": {
                "variables": [
                    {
                        "name": "interview_complete",
                        "from": "trigger.InterviewAgent.text",
                        "match": "NEXT",
                        "ui_hidden": True,
                    },
                    {
                        "name": "ignored",
                        "from": "trigger.OtherAgent.text",
                        "match": "VISIBLE",
                        "ui_hidden": False,
                    },
                ]
            }
        }
    }
    manager = _make_manager(config)

    hidden = manager.get_ui_hidden_triggers("test")

    assert hidden == {"InterviewAgent": {"NEXT"}}


def test_ui_hidden_triggers_handles_new_definitions_schema():
    config = {
        "context_variables": {
            "context_variables": {
                "definitions": {
                    "action_plan_acceptance": {
                        "source": {
                            "type": "derived",
                            "triggers": [
                                {
                                    "ui_hidden": True,
                                    "agent": "ActionPlanArchitect",
                                    "match": {"equals": ["APPROVED", "NEXT"]},
                                },
                                {
                                    "ui_hidden": False,
                                    "agent": "ActionPlanArchitect",
                                    "match": {"equals": "VISIBLE"},
                                },
                            ],
                        }
                    }
                }
            }
        }
    }
    manager = _make_manager(config)

    hidden = manager.get_ui_hidden_triggers("test")

    assert hidden == {"ActionPlanArchitect": {"APPROVED", "NEXT"}}
