import sys
from types import SimpleNamespace

import pytest

from core.workflow.execution.hooks import register_hooks_for_workflow


class _MockAgent:
    def __init__(self) -> None:
        self.hooks = {}

    def register_hook(self, hook_type, fn):
        self.hooks.setdefault(hook_type, []).append(fn)


@pytest.fixture()
def temp_hooks_workflow(tmp_path, monkeypatch):
    workflows_dir = tmp_path / "workflows"
    tools_dir = workflows_dir / "TestHooks" / "tools"
    tools_dir.mkdir(parents=True)

    # Package initializers
    (workflows_dir / "__init__.py").write_text("", encoding="utf-8")
    (workflows_dir / "TestHooks" / "__init__.py").write_text("", encoding="utf-8")
    (tools_dir / "__init__.py").write_text("", encoding="utf-8")

    # Hook modules
    (tools_dir / "hook_one.py").write_text(
        """
from typing import Any, Dict, Union

CALL_LOG = []

def hook_one(sender, message: Union[str, Dict[str, Any]], recipient, silent):
    CALL_LOG.append(("one", message))
    return message
""",
        encoding="utf-8",
    )

    (tools_dir / "hook_two.py").write_text(
        """
CALL_LOG = []

def hook_two(content, sender=None):
    CALL_LOG.append(("two", content))
    return content
""",
        encoding="utf-8",
    )

    # hooks.json definition
    hooks_json = workflows_dir / "TestHooks" / "hooks.json"
    hooks_json.write_text(
        """
{
  "hooks": [
    {
      "hook_type": "process_message_before_send",
      "hook_agent": "AgentOne",
      "filename": "hook_one.py",
      "function": "hook_one"
    },
    {
      "hook_type": "process_last_received_message",
      "hook_agent": "AgentTwo",
      "filename": "hook_two.py",
      "function": "hook_two"
    }
  ]
}
""",
        encoding="utf-8",
    )

    monkeypatch.syspath_prepend(str(tmp_path))
    return workflows_dir


def test_wrapped_hooks_preserve_original_function(temp_hooks_workflow):
    agents = {"AgentOne": _MockAgent(), "AgentTwo": _MockAgent()}

    registered = register_hooks_for_workflow(
        "TestHooks", agents, base_path=str(temp_hooks_workflow)
    )

    # Ensure both hooks registered
    assert len(registered) == 2

    # Invoke the registered hooks and check that each one uses the correct original function
    agent_one_hook = agents["AgentOne"].hooks["process_message_before_send"][0]
    agent_two_hook = agents["AgentTwo"].hooks["process_last_received_message"][0]

    agent_one_hook(SimpleNamespace(), "payload-one", SimpleNamespace(), False)
    agent_two_hook("payload-two")

    hook_one_module = sys.modules["workflows.TestHooks.tools.hook_one"]
    hook_two_module = sys.modules["workflows.TestHooks.tools.hook_two"]

    assert hook_one_module.CALL_LOG == [("one", "payload-one")]
    assert hook_two_module.CALL_LOG == [("two", "payload-two")]
