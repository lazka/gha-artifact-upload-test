from __future__ import annotations

import json
import subprocess
from typing import Any

import pytest

from gha_artifact_client.client import (
    ArtifactSignedURLResult,
)
from gha_artifact_client.exceptions import (
    NodeWrapperExecutionError,
)

from .conftest import make_api as _make_api

_SIGNED_URL = "https://storage.example.test/artifact?sig=abc123"


def _signed_url_success_run(
    args: list[str],
    *,
    input: str,
    env: dict[str, str],
    text: bool,
    capture_output: bool,
    check: bool,
    signed_url: str = _SIGNED_URL,
) -> subprocess.CompletedProcess[str]:
    del text, capture_output, check
    return subprocess.CompletedProcess(
        args=args,
        returncode=0,
        stdout=json.dumps({"url": signed_url}),
        stderr="",
    )


# ---------------------------------------------------------------------------
# get_signed_artifact_url: payload
# ---------------------------------------------------------------------------


def test_get_signed_url_sends_correct_action_and_name(
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
        return _signed_url_success_run(
            args,
            input=input,
            env=env,
            text=text,
            capture_output=capture_output,
            check=check,
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    api = _make_api()
    result = api.get_signed_artifact_url("my-artifact")

    assert result == ArtifactSignedURLResult(url=_SIGNED_URL)
    assert captured["payload"] == {"action": "get-signed-url", "name": "my-artifact"}


# ---------------------------------------------------------------------------
# get_signed_artifact_url: missing field
# ---------------------------------------------------------------------------


def test_get_signed_url_missing_url_field_raises(
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
            returncode=0,
            stdout=json.dumps({}),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    api = _make_api()
    with pytest.raises(NodeWrapperExecutionError, match="url"):
        api.get_signed_artifact_url("my-artifact")


# ---------------------------------------------------------------------------
# get_signed_artifact_url: node wrapper error handling
# ---------------------------------------------------------------------------


def test_get_signed_url_node_wrapper_failure_surfaces_structured_error(
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
        api.get_signed_artifact_url("missing-artifact")

    assert exc_info.value.returncode == 1
    assert "some log line" in exc_info.value.stderr
