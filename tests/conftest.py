from __future__ import annotations

import json
import subprocess
from typing import Any

import pytest

from gha_artifact_client.client import ArtifactClientApi

_TOKEN = "test-token"
_URL = "https://results.example.test"


def make_api(**kwargs: Any) -> ArtifactClientApi:
    defaults = {"runtime_token": _TOKEN, "results_url": _URL}
    defaults.update(kwargs)
    return ArtifactClientApi(**defaults)  # type: ignore[arg-type]


def make_fake_run(stdout: str) -> Any:
    """Return a fake subprocess.run that always succeeds with the given stdout."""

    def fake_run(
        args: list[str],
        *,
        input: str,
        env: dict[str, str],
        text: bool,
        capture_output: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        del input, text, capture_output, check, env
        return subprocess.CompletedProcess(
            args=args, returncode=0, stdout=stdout, stderr=""
        )

    return fake_run


@pytest.fixture
def fake_delete_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(subprocess, "run", make_fake_run(json.dumps({"id": 1})))
