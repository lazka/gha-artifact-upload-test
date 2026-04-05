from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest
from github import Auth, Github

from gha_artifact_client.client import ArtifactClientApi


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        pytest.skip(f"{name} is required for the live integration test")

    return value


@pytest.mark.integration
def test_live_upload_visible_via_pygithub(tmp_path: Path) -> None:
    token = _require_env("GITHUB_TOKEN")
    repository_name = _require_env("GITHUB_REPOSITORY")
    run_id = int(_require_env("GITHUB_RUN_ID"))

    artifact_name = f"gha-artifact-upload-integration-{run_id}.txt"
    artifact_file = tmp_path / artifact_name
    artifact_file.write_text("integration artifact payload\n", encoding="utf-8")
    expected_digest = hashlib.sha256(artifact_file.read_bytes()).hexdigest()

    result = ArtifactClientApi().upload_artifact(artifact_file, name=artifact_name)

    assert result.id
    assert result.digest == f"sha256:{expected_digest}"

    client = Github(auth=Auth.Token(token))
    requester = client.get_repo(repository_name).requester

    _, artifact_data = requester.requestJsonAndCheck(
        "GET",
        f"/repos/{repository_name}/actions/artifacts/{result.id}",
    )
    _, run_response = requester.requestJsonAndCheck(
        "GET",
        f"/repos/{repository_name}/actions/runs/{run_id}/artifacts",
    )
    run_artifacts = run_response.get("artifacts", [])

    assert artifact_data is not None
    assert artifact_data["name"] == artifact_name
    assert any(str(artifact.get("id")) == result.id for artifact in run_artifacts)

    assert artifact_data.get("digest") == f"sha256:{expected_digest}"
