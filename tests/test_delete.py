from __future__ import annotations

import json
import subprocess
from typing import Any

import pytest

from gha_artifact_client.client import (
    ArtifactClientApi,
    ArtifactDeleteResult,
)
from gha_artifact_client.exceptions import (
    NodeWrapperExecutionError,
)

_TOKEN = "test-token"
_URL = "https://results.example.test"


def _make_api(**kwargs: Any) -> ArtifactClientApi:
    defaults = {"runtime_token": _TOKEN, "results_url": _URL}
    defaults.update(kwargs)
    return ArtifactClientApi(**defaults)  # type: ignore[arg-type]


def _delete_success_run(
    args: list[str],
    *,
    input: str,
    env: dict[str, str],
    text: bool,
    capture_output: bool,
    check: bool,
    artifact_id: int = 42,
) -> subprocess.CompletedProcess[str]:
    del text, capture_output, check
    return subprocess.CompletedProcess(
        args=args,
        returncode=0,
        stdout=json.dumps({"id": artifact_id}),
        stderr="",
    )


# ---------------------------------------------------------------------------
# delete_artifact: payload
# ---------------------------------------------------------------------------


def test_delete_sends_correct_action_and_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_run(
        args: list[str],
        *,
        input: str,
        env: dict[str, str],
        text: bool,
        capture_output: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        captured["payload"] = json.loads(input)
        return _delete_success_run(
            args,
            input=input,
            env=env,
            text=text,
            capture_output=capture_output,
            check=check,
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    api = _make_api()
    result = api.delete_artifact("my-artifact")

    assert result == ArtifactDeleteResult(id=42)
    assert captured["payload"] == {"action": "delete", "name": "my-artifact"}


def test_delete_returns_artifact_delete_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(
        args: list[str],
        *,
        input: str,
        env: dict[str, str],
        text: bool,
        capture_output: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=json.dumps({"id": 99}),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    api = _make_api()
    result = api.delete_artifact("my-artifact")

    assert isinstance(result, ArtifactDeleteResult)
    assert result.id == 99


# ---------------------------------------------------------------------------
# delete_artifact: node wrapper error handling
# ---------------------------------------------------------------------------


def test_delete_node_wrapper_failure_surfaces_structured_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(
        args: list[str],
        *,
        input: str,
        env: dict[str, str],
        text: bool,
        capture_output: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        del args, input, text, capture_output, check, env
        return subprocess.CompletedProcess(
            args=["node"],
            returncode=1,
            stdout="",
            stderr=(
                "some log line\n"
                "GHA_ARTIFACT_CLIENT_ERROR:"
                '{"error":"Error","message":"artifact not found"}\n'
            ),
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    api = _make_api()
    with pytest.raises(
        NodeWrapperExecutionError, match="artifact not found"
    ) as exc_info:
        api.delete_artifact("missing-artifact")

    assert exc_info.value.returncode == 1
    assert "some log line" in exc_info.value.stderr
