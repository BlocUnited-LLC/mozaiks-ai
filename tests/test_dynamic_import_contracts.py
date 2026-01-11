import sys
import types

import pytest


def test_general_agent_loader_returns_none_on_missing_module(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOZAIKS_GENERAL_AGENT_MODULE", "this.module.does.not.exist")
    monkeypatch.setenv("MOZAIKS_GENERAL_AGENT_FACTORY", "get_ask_mozaiks_service")

    from core.transport import simple_transport

    assert simple_transport._load_general_agent_service() is None


def test_general_agent_loader_returns_none_on_noncallable_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    module_name = "fake_general_agent_module"
    fake_module = types.ModuleType(module_name)
    setattr(fake_module, "get_ask_mozaiks_service", "not-callable")

    monkeypatch.setitem(sys.modules, module_name, fake_module)
    monkeypatch.setenv("MOZAIKS_GENERAL_AGENT_MODULE", module_name)
    monkeypatch.setenv("MOZAIKS_GENERAL_AGENT_FACTORY", "get_ask_mozaiks_service")

    from core.transport import simple_transport

    assert simple_transport._load_general_agent_service() is None


def test_platform_build_lifecycle_loader_returns_nones_on_missing_module(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOZAIKS_PLATFORM_BUILD_LIFECYCLE_MODULE", "this.module.does.not.exist")

    from core.transport import simple_transport

    lifecycle = simple_transport._load_platform_build_lifecycle()
    assert set(lifecycle.keys()) == {
        "is_build_workflow",
        "emit_build_started",
        "emit_build_completed",
        "emit_build_failed",
    }
    assert all(v is None for v in lifecycle.values())


def test_platform_build_events_processor_loader_returns_none_on_missing_module(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOZAIKS_PLATFORM_BUILD_EVENTS_PROCESSOR_MODULE", "this.module.does.not.exist")
    monkeypatch.setenv("MOZAIKS_PLATFORM_BUILD_EVENTS_PROCESSOR_CLASS", "BuildEventsProcessor")

    import shared_app

    assert shared_app._load_platform_build_events_processor() is None


def test_platform_build_events_processor_loader_instantiates_when_available(monkeypatch: pytest.MonkeyPatch) -> None:
    module_name = "fake_build_events_processor_module"

    fake_module = types.ModuleType(module_name)

    class BuildEventsProcessor:
        def __init__(self) -> None:
            self.started = False

        def start(self) -> None:
            self.started = True

    setattr(fake_module, "BuildEventsProcessor", BuildEventsProcessor)

    monkeypatch.setitem(sys.modules, module_name, fake_module)
    monkeypatch.setenv("MOZAIKS_PLATFORM_BUILD_EVENTS_PROCESSOR_MODULE", module_name)
    monkeypatch.setenv("MOZAIKS_PLATFORM_BUILD_EVENTS_PROCESSOR_CLASS", "BuildEventsProcessor")

    import shared_app

    proc = shared_app._load_platform_build_events_processor()
    assert proc is not None
    assert proc.__class__.__name__ == "BuildEventsProcessor"
