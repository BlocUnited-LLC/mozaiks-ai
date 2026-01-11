import pytest

from workflows.AppGenerator.tools.platform.build_events_client import BuildEventsClient
from workflows.AppGenerator.tools.platform.build_events_outbox import build_outbox_id
from workflows.AppGenerator.tools.platform.build_events_processor import BuildEventsProcessor
from workflows.AppGenerator.tools.platform.build_lifecycle import build_export_download_url, is_build_workflow


def test_is_build_workflow_defaults_to_appgenerator(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MOZAIKS_BUILD_WORKFLOW_NAMES", raising=False)
    assert is_build_workflow("AppGenerator") is True
    assert is_build_workflow("appgenerator") is True
    assert is_build_workflow("ValueEngine") is False


def test_is_build_workflow_respects_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOZAIKS_BUILD_WORKFLOW_NAMES", "ValueEngine,AgentGenerator")
    assert is_build_workflow("ValueEngine") is True
    assert is_build_workflow("AgentGenerator") is True
    assert is_build_workflow("AppGenerator") is False


def test_build_export_url_relative_when_no_public_base(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MOZAIKS_RUNTIME_PUBLIC_BASE_URL", raising=False)
    monkeypatch.delenv("RUNTIME_PUBLIC_BASE_URL", raising=False)
    monkeypatch.delenv("PUBLIC_RUNTIME_BASE_URL", raising=False)
    assert build_export_download_url(app_id="app_1", build_id="bld_1") == "/api/apps/app_1/builds/bld_1/export"


def test_build_export_url_absolute_when_public_base_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOZAIKS_RUNTIME_PUBLIC_BASE_URL", "https://runtime.example.com/")
    assert (
        build_export_download_url(app_id="app_1", build_id="bld_1")
        == "https://runtime.example.com/api/apps/app_1/builds/bld_1/export"
    )


def test_build_outbox_id_is_deterministic_and_sanitized() -> None:
    a = build_outbox_id(app_id="app/..", build_id="b\\..", event_type="build_started")
    b = build_outbox_id(app_id="app/..", build_id="b\\..", event_type="build_started")
    assert a == b
    assert "build_evt:" in a
    assert "/" not in a
    assert "\\" not in a


@pytest.mark.asyncio
async def test_build_events_client_returns_not_configured_when_missing_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MOZAIKS_PLATFORM_BASE_URL", raising=False)
    monkeypatch.delenv("MOZAIKS_BACKEND_URL", raising=False)
    monkeypatch.delenv("MOZAIKS_PLATFORM_INTERNAL_API_KEY", raising=False)
    monkeypatch.delenv("INTERNAL_API_KEY", raising=False)

    client = BuildEventsClient(enabled=True)
    res = await client.post_build_event(
        app_id="app_1",
        payload={
            "event_type": "build_started",
            "appId": "app_1",
            "buildId": "bld_1",
            "status": "building",
        },
    )
    assert res.ok is False
    assert res.error == "not_configured"


def test_build_events_processor_does_not_start_without_client_config() -> None:
    client = BuildEventsClient(enabled=True, base_url="", api_key="")
    proc = BuildEventsProcessor(client=client, enabled=True)
    assert proc.start() is None

