from __future__ import annotations

import os
from pathlib import Path

import pytest

from gha_artifact_client.client import ArtifactClientApi, ArtifactSignedURLResult


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        pytest.skip(f"{name} is required for the live integration test")

    return value


@pytest.mark.integration
def test_live_get_signed_artifact_url_returns_https_url(tmp_path: Path) -> None:
    run_id = int(_require_env("GITHUB_RUN_ID"))

    artifact_name = f"gha-artifact-signed-url-integration-{run_id}.txt"
    artifact_file = tmp_path / artifact_name
    artifact_file.write_text("integration artifact for signed url\n", encoding="utf-8")

    api = ArtifactClientApi()

    upload_result = api.upload_artifact(artifact_file, name=artifact_name)
    assert upload_result.id > 0

    result = api.get_signed_artifact_url(artifact_name)

    assert isinstance(result, ArtifactSignedURLResult)
    assert result.url.startswith("https://")
