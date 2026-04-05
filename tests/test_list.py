from __future__ import annotations

import json
import subprocess
from typing import Any

import pytest

from gha_artifact_client.client import (
    ArtifactInfo,
    ArtifactListResult,
)
from gha_artifact_client.exceptions import (
    NodeWrapperExecutionError,
)

from .conftest import make_api as _make_api

_ARTIFACT_1 = {
    "id": "42",
    "name": "my-artifact",
    "size": "1234",
    "createdAt": "1748779200000",  # 2025-06-01T12:00:00Z
    "digest": "sha256:abc123",
}

_ARTIFACT_2 = {
    "id": "99",
    "name": "other-artifact",
    "size": "5678",
    "createdAt": "1748854200000",  # 2025-06-02T08:30:00Z
    "digest": "sha256:def456",
}


def _list_success_run(
    stdout_payload: dict[str, Any],
) -> Any:
    """Return a fake subprocess.run that succeeds with the given payload."""

    def fake_run(
        args: list[str],
        *,
        input: str,
        env: dict[str, str],
        text: bool,
        capture_output: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        del text, capture_output, check, env
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=json.dumps(stdout_payload),
            stderr="",
        )

    return fake_run


# ---------------------------------------------------------------------------
# list_artifacts: payload
# ---------------------------------------------------------------------------


def test_list_sends_correct_action(
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
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=json.dumps({"artifacts": []}),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    api = _make_api()
    api.list_artifacts()

    assert captured["payload"] == {"action": "list"}


# ---------------------------------------------------------------------------
# list_artifacts: result parsing
# ---------------------------------------------------------------------------


def test_list_returns_artifact_list_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        _list_success_run({"artifacts": [_ARTIFACT_1, _ARTIFACT_2]}),
    )

    api = _make_api()
    result = api.list_artifacts()

    assert isinstance(result, ArtifactListResult)
    assert len(result.artifacts) == 2

    a1 = result.artifacts[0]
    assert isinstance(a1, ArtifactInfo)
    assert a1.id == 42
    assert a1.name == "my-artifact"
    assert a1.size == 1234
    assert a1.digest == "sha256:abc123"
    assert a1.created_at is not None
    assert a1.created_at.year == 2025
    assert a1.created_at.month == 6
    assert a1.created_at.day == 1
    assert a1.created_at.tzinfo is not None

    a2 = result.artifacts[1]
    assert a2.id == 99
    assert a2.name == "other-artifact"
    assert a2.size == 5678
    assert a2.digest == "sha256:def456"


def test_list_handles_empty_artifacts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        _list_success_run({"artifacts": []}),
    )

    api = _make_api()
    result = api.list_artifacts()

    assert result == ArtifactListResult(artifacts=())


# ---------------------------------------------------------------------------
# list_artifacts: node wrapper error handling
# ---------------------------------------------------------------------------


def test_list_node_wrapper_failure_surfaces_structured_error(
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
                '{"error":"Error","message":"list failed"}\n'
            ),
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    api = _make_api()
    with pytest.raises(NodeWrapperExecutionError, match="list failed") as exc_info:
        api.list_artifacts()

    assert exc_info.value.returncode == 1
    assert "some log line" in exc_info.value.stderr
