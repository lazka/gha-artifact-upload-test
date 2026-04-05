from __future__ import annotations

import os
from pathlib import Path

import pytest

from gha_artifact_client.client import (
    ArtifactClientApi,
    ArtifactInfo,
    ArtifactListResult,
)


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        pytest.skip(f"{name} is required for the live integration test")

    return value


@pytest.mark.integration
def test_live_list_returns_uploaded_artifact(tmp_path: Path) -> None:
    run_id = int(_require_env("GITHUB_RUN_ID"))

    artifact_name = f"gha-artifact-list-integration-{run_id}.txt"
    artifact_file = tmp_path / artifact_name
    artifact_file.write_text("integration artifact for list\n", encoding="utf-8")

    api = ArtifactClientApi()

    upload_result = api.upload_artifact(artifact_file, name=artifact_name)
    assert upload_result.id > 0

    list_result = api.list_artifacts()

    assert isinstance(list_result, ArtifactListResult)
    assert len(list_result.artifacts) > 0

    matching = [a for a in list_result.artifacts if a.name == artifact_name]
    assert len(matching) == 1

    a = matching[0]
    assert isinstance(a, ArtifactInfo)
    assert a.id == upload_result.id
    assert a.size > 0
    assert a.created_at is not None
    assert a.digest is not None
