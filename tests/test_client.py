from __future__ import annotations

import json
import subprocess
from typing import Any

import pytest

from gha_artifact_client.client import ArtifactClientApi
from gha_artifact_client.exceptions import UnsupportedEnvironmentError

_TOKEN = "test-token"
_URL = "https://results.example.test"


def _make_api(**kwargs: Any) -> ArtifactClientApi:
    defaults = {"runtime_token": _TOKEN, "results_url": _URL}
    defaults.update(kwargs)
    return ArtifactClientApi(**defaults)  # type: ignore[arg-type]


def _noop_run(
    args: list[str],
    *,
    input: str,
    env: dict[str, str],
    text: bool,
    capture_output: bool,
    check: bool,
) -> subprocess.CompletedProcess[str]:
    """Minimal fake subprocess.run that returns a valid delete response."""
    del input, text, capture_output, check
    return subprocess.CompletedProcess(
        args=args,
        returncode=0,
        stdout=json.dumps({"id": 1}),
        stderr="",
    )


# ---------------------------------------------------------------------------
# Construction / credential resolution
# ---------------------------------------------------------------------------


def test_construction_reads_credentials_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ACTIONS_RUNTIME_TOKEN", "env-token")
    monkeypatch.setenv("ACTIONS_RESULTS_URL", "https://env.example.test")

    api = ArtifactClientApi()

    assert api._runtime_token == "env-token"
    assert api._results_url == "https://env.example.test"


def test_explicit_credentials_override_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ACTIONS_RUNTIME_TOKEN", "env-token")
    monkeypatch.setenv("ACTIONS_RESULTS_URL", "https://env.example.test")

    api = ArtifactClientApi(
        runtime_token="explicit-token", results_url="https://explicit.example.test"
    )

    assert api._runtime_token == "explicit-token"
    assert api._results_url == "https://explicit.example.test"


def test_explicit_credentials_work_without_env_vars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ACTIONS_RUNTIME_TOKEN", raising=False)
    monkeypatch.delenv("ACTIONS_RESULTS_URL", raising=False)

    # Should not raise.
    api = ArtifactClientApi(runtime_token=_TOKEN, results_url=_URL)

    assert api._runtime_token == _TOKEN
    assert api._results_url == _URL


def test_missing_credentials_raise_at_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ACTIONS_RUNTIME_TOKEN", raising=False)
    monkeypatch.delenv("ACTIONS_RESULTS_URL", raising=False)

    with pytest.raises(UnsupportedEnvironmentError, match="live GitHub Actions"):
        ArtifactClientApi()


def test_missing_token_only_raises_at_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ACTIONS_RUNTIME_TOKEN", raising=False)
    monkeypatch.setenv("ACTIONS_RESULTS_URL", _URL)

    with pytest.raises(UnsupportedEnvironmentError, match="ACTIONS_RUNTIME_TOKEN"):
        ArtifactClientApi()


def test_missing_url_only_raises_at_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ACTIONS_RUNTIME_TOKEN", _TOKEN)
    monkeypatch.delenv("ACTIONS_RESULTS_URL", raising=False)

    with pytest.raises(UnsupportedEnvironmentError, match="ACTIONS_RESULTS_URL"):
        ArtifactClientApi()


# ---------------------------------------------------------------------------
# Credential forwarding to the node wrapper subprocess
# ---------------------------------------------------------------------------


def test_node_wrapper_receives_explicit_credentials_in_env(
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
        captured["env"] = env
        return _noop_run(
            args,
            input=input,
            env=env,
            text=text,
            capture_output=capture_output,
            check=check,
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.delenv("ACTIONS_RUNTIME_TOKEN", raising=False)
    monkeypatch.delenv("ACTIONS_RESULTS_URL", raising=False)

    api = ArtifactClientApi(
        runtime_token="explicit-token", results_url="https://explicit.example.test"
    )
    api.delete_artifact("my-artifact")

    env = captured["env"]
    assert isinstance(env, dict)
    assert env["ACTIONS_RUNTIME_TOKEN"] == "explicit-token"
    assert env["ACTIONS_RESULTS_URL"] == "https://explicit.example.test"


def test_explicit_credentials_override_env_in_node_wrapper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Explicit credentials must win over env vars when passed to the node wrapper."""
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
        captured["env"] = env
        return _noop_run(
            args,
            input=input,
            env=env,
            text=text,
            capture_output=capture_output,
            check=check,
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setenv("ACTIONS_RUNTIME_TOKEN", "env-token")
    monkeypatch.setenv("ACTIONS_RESULTS_URL", "https://env.example.test")

    api = ArtifactClientApi(
        runtime_token="explicit-token", results_url="https://explicit.example.test"
    )
    api.delete_artifact("my-artifact")

    env = captured["env"]
    assert env["ACTIONS_RUNTIME_TOKEN"] == "explicit-token"
    assert env["ACTIONS_RESULTS_URL"] == "https://explicit.example.test"
