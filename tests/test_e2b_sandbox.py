import os
from typing import Any, Dict, Optional

import pytest

from workflows.AppGenerator.tools import e2b_sandbox


@pytest.mark.asyncio
async def test_validate_app_in_sandbox_missing_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("E2B_API_KEY", raising=False)
    result = await e2b_sandbox.validate_app_in_sandbox(files={"package.json": "{}"}, start_dev_server=False)
    assert result["success"] is False
    assert "E2B_API_KEY" in (result.get("errors") or [""])[0]


@pytest.mark.asyncio
async def test_validate_app_in_sandbox_build_success_returns_preview_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("E2B_API_KEY", "e2b_test_key")

    class DummyProc:
        def __init__(self, exit_code: int = 0, stdout: str = "", stderr: str = "") -> None:
            self.exit_code = exit_code
            self.stdout = stdout
            self.stderr = stderr

        def wait(self) -> None:
            return None

    class DummyProcess:
        def __init__(self) -> None:
            self.calls = []

        def start(self, cmd: str, background: bool = False) -> DummyProc:
            self.calls.append({"cmd": cmd, "background": background})
            if cmd == "npm install":
                return DummyProc(exit_code=0, stdout="installed", stderr="")
            if cmd == "npm run build":
                return DummyProc(exit_code=0, stdout="built", stderr="")
            if cmd.startswith("npm test"):
                return DummyProc(exit_code=0, stdout="tests ok", stderr="")
            if cmd.startswith("npm run dev") or cmd.startswith("HOST=") or cmd.startswith("PORT="):
                return DummyProc(exit_code=0, stdout="dev started", stderr="")
            return DummyProc(exit_code=0)

    class DummyFS:
        def __init__(self) -> None:
            self.writes: Dict[str, str] = {}

        def make_dir(self, _path: str) -> None:
            return None

        def write(self, path: str, content: str) -> None:
            self.writes[path] = content

        def read(self, path: str) -> Optional[str]:
            if path == "package.json":
                return '{"scripts": {"build": "vite build", "test": "vitest run"}}'
            return None

    class DummySandbox:
        def __init__(self, api_key: str, timeout: int) -> None:
            self.api_key = api_key
            self.timeout = timeout
            self.filesystem = DummyFS()
            self.process = DummyProcess()

        def get_hostname(self, port: int) -> str:
            return f"https://example.e2b.dev:{port}"

        def close(self) -> None:
            return None

    monkeypatch.setattr(e2b_sandbox, "Sandbox", DummySandbox)
    async def _noop_sleep(_s: float) -> None:
        return None

    monkeypatch.setattr(e2b_sandbox.asyncio, "sleep", _noop_sleep)

    files = {"package.json": '{"name":"x"}', "src/App.jsx": "export default function App(){return null;}"}
    result = await e2b_sandbox.validate_app_in_sandbox(files=files, start_dev_server=True)
    assert result["success"] is True
    assert result.get("preview_url")
    assert result.get("errors") == []


@pytest.mark.asyncio
async def test_validate_app_in_sandbox_build_failure_returns_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("E2B_API_KEY", "e2b_test_key")

    class DummyProc:
        def __init__(self, exit_code: int = 0, stdout: str = "", stderr: str = "") -> None:
            self.exit_code = exit_code
            self.stdout = stdout
            self.stderr = stderr

        def wait(self) -> None:
            return None

    class DummyProcess:
        def start(self, cmd: str, background: bool = False) -> DummyProc:  # noqa: ARG002
            if cmd == "npm install":
                return DummyProc(exit_code=0, stdout="installed", stderr="")
            if cmd == "npm run build":
                return DummyProc(exit_code=1, stdout="", stderr="src/App.js:10:5 - error TS2304: Cannot find name 'x'.")
            return DummyProc(exit_code=0)

    class DummyFS:
        def make_dir(self, _path: str) -> None:
            return None

        def write(self, _path: str, _content: str) -> None:
            return None

    class DummySandbox:
        def __init__(self, api_key: str, timeout: int) -> None:  # noqa: ARG002
            self.filesystem = DummyFS()
            self.process = DummyProcess()

        def close(self) -> None:
            return None

    monkeypatch.setattr(e2b_sandbox, "Sandbox", DummySandbox)

    result = await e2b_sandbox.validate_app_in_sandbox(files={"src/App.js": "const y = x;"}, start_dev_server=False)
    assert result["success"] is False
    assert result.get("errors")


def test_parse_build_errors() -> None:
    output = """
    src/components/Button.tsx:42:10 - error TS2304: Cannot find name 'foo'.
    src/App.tsx:15:3 - error TS1005: ')' expected.
    """
    errors = e2b_sandbox.parse_build_errors(output)
    assert len(errors) == 2
    assert errors[0]["file"] == "src/components/Button.tsx"
    assert errors[0]["line"] == 42
    assert "foo" in errors[0]["message"]
