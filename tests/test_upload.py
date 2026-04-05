from __future__ import annotations

import datetime as dt
import io
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from gha_artifact_client.client import (
    ArtifactClientApi,
    ArtifactUploadResult,
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


def _success_run(
    args: list[str],
    *,
    input: str,
    env: dict[str, str],
    text: bool,
    capture_output: bool,
    check: bool,
    stdout: str = json.dumps({"id": 7, "size": 5, "digest": "sha256:abc"}),
) -> subprocess.CompletedProcess[str]:
    del text, capture_output, check
    return subprocess.CompletedProcess(
        args=args, returncode=0, stdout=stdout, stderr=""
    )


# ---------------------------------------------------------------------------
# upload_artifact
# ---------------------------------------------------------------------------


def test_upload_file_sends_name_and_file_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact_file = tmp_path / "artifact.txt"
    artifact_file.write_text("hello", encoding="utf-8")

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
        del text, capture_output, check
        captured["args"] = args
        captured["payload"] = json.loads(input)
        captured["env"] = env
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=json.dumps({"id": 7, "size": 5, "digest": "sha256:abc"}),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    api = _make_api()
    result = api.upload_artifact(artifact_file)

    assert result == ArtifactUploadResult(id=7, size=5, digest="sha256:abc")
    payload = captured["payload"]
    assert payload == {
        "action": "upload",
        "name": "artifact.txt",
        "filePath": str(artifact_file.resolve()),
    }


def test_upload_symlink_uses_symlink_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact_file = tmp_path / "artifact.txt"
    artifact_file.write_text("hello", encoding="utf-8")
    symlink = tmp_path / "my-release"
    symlink.symlink_to(artifact_file)

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
        del args, text, capture_output, check, env
        captured["payload"] = json.loads(input)
        return subprocess.CompletedProcess(
            args=["node"],
            returncode=0,
            stdout=json.dumps({"id": 7, "size": 5, "digest": "sha256:abc"}),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    api = _make_api()
    api.upload_artifact(symlink)

    payload = captured["payload"]
    assert payload["name"] == "my-release"
    assert payload["filePath"] == str(artifact_file.resolve())


def test_upload_file_passes_custom_name_in_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact_file = tmp_path / "artifact.txt"
    artifact_file.write_text("hello", encoding="utf-8")

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
        del args, text, capture_output, check, env
        captured["payload"] = json.loads(input)
        return subprocess.CompletedProcess(
            args=["node"],
            returncode=0,
            stdout=json.dumps({"id": 9, "size": 5, "digest": "sha256:xyz"}),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    api = _make_api()
    result = api.upload_artifact(artifact_file, name="renamed.zip")

    assert result == ArtifactUploadResult(id=9, size=5, digest="sha256:xyz")
    payload = captured["payload"]
    assert payload["name"] == "renamed.zip"
    assert payload["filePath"] == str(artifact_file.resolve())


def test_upload_accepts_pathlike_node_executable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact_file = tmp_path / "artifact.txt"
    artifact_file.write_text("hello", encoding="utf-8")

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
        del input, text, capture_output, check, env
        captured["args"] = args
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=json.dumps({"id": 5, "size": 5, "digest": "sha256:abc"}),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    api = _make_api(node_executable=Path("/usr/bin/node"))
    api.upload_artifact(artifact_file)

    assert captured["args"] == [
        "/usr/bin/node",
        str(
            Path(__file__).resolve().parents[1]
            / "gha_artifact_client/_vendor/artifact_node_wrapper.mjs"
        ),
    ]


def test_upload_file_includes_expires_at_when_requested(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact_file = tmp_path / "artifact.txt"
    artifact_file.write_text("hello", encoding="utf-8")

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
        del args, text, capture_output, check, env
        captured["payload"] = json.loads(input)
        return subprocess.CompletedProcess(
            args=["node"],
            returncode=0,
            stdout=json.dumps({"id": 1, "size": 2, "digest": "sha256:aaa"}),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    api = _make_api()
    expiry = dt.datetime(2030, 6, 1, 12, 0, 0, tzinfo=dt.UTC)
    api.upload_artifact(artifact_file, expires_at=expiry)

    payload = captured["payload"]
    assert payload["expiresAt"] == pytest.approx(expiry.timestamp())
    assert "retentionDays" not in payload


def test_upload_file_includes_expires_in_when_requested(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact_file = tmp_path / "artifact.txt"
    artifact_file.write_text("hello", encoding="utf-8")

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
        del args, text, capture_output, check, env
        captured["payload"] = json.loads(input)
        return subprocess.CompletedProcess(
            args=["node"],
            returncode=0,
            stdout=json.dumps({"id": 1, "size": 2, "digest": "sha256:aaa"}),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    before = dt.datetime.now(tz=dt.UTC).timestamp()
    api = _make_api()
    api.upload_artifact(artifact_file, expires_in=3600)
    after = dt.datetime.now(tz=dt.UTC).timestamp()

    payload = captured["payload"]
    assert payload["expiresAt"] == pytest.approx(before + 3600, abs=5)
    assert payload["expiresAt"] <= after + 3600
    assert "retentionDays" not in payload


def test_upload_file_expires_at_and_expires_in_conflict(
    tmp_path: Path,
) -> None:
    artifact_file = tmp_path / "artifact.txt"
    artifact_file.write_text("hello", encoding="utf-8")

    api = _make_api()
    expiry = dt.datetime(2030, 6, 1, 12, 0, 0, tzinfo=dt.UTC)

    with pytest.raises(ValueError, match="at most one"):
        api.upload_artifact(artifact_file, expires_at=expiry, expires_in=3600)


def test_upload_file_rejects_naive_expires_at(
    tmp_path: Path,
) -> None:
    artifact_file = tmp_path / "artifact.txt"
    artifact_file.write_text("hello", encoding="utf-8")

    api = _make_api()
    naive_dt = dt.datetime(2030, 6, 1, 12, 0, 0)  # no tzinfo

    with pytest.raises(ValueError, match="timezone-aware"):
        api.upload_artifact(artifact_file, expires_at=naive_dt)


def test_upload_file_includes_mime_type_when_requested(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact_file = tmp_path / "artifact.txt"
    artifact_file.write_text("hello", encoding="utf-8")

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
        del args, text, capture_output, check, env
        captured["payload"] = json.loads(input)
        return subprocess.CompletedProcess(
            args=["node"],
            returncode=0,
            stdout=json.dumps({"id": 1, "size": 2, "digest": "sha256:aaa"}),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    api = _make_api()
    api.upload_artifact(artifact_file, mime_type="application/x-custom")

    payload = captured["payload"]
    assert payload["mimeType"] == "application/x-custom"


def test_upload_file_omits_mime_type_when_not_specified(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact_file = tmp_path / "artifact.txt"
    artifact_file.write_text("hello", encoding="utf-8")

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
        del args, text, capture_output, check, env
        captured["payload"] = json.loads(input)
        return subprocess.CompletedProcess(
            args=["node"],
            returncode=0,
            stdout=json.dumps({"id": 1, "size": 2, "digest": "sha256:aaa"}),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    api = _make_api()
    api.upload_artifact(artifact_file)

    payload = captured["payload"]
    assert "mimeType" not in payload


def test_directory_upload_is_not_supported(tmp_path: Path) -> None:
    directory = tmp_path / "artifact-dir"
    directory.mkdir()

    api = _make_api()
    with pytest.raises(ValueError, match="Only single-file uploads"):
        api.upload_artifact(directory)


# ---------------------------------------------------------------------------
# upload_artifact_fileobj
# ---------------------------------------------------------------------------


def test_upload_fileobj_spools_to_temp_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
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
        del text, capture_output, check, env
        payload = json.loads(input)
        captured["payload"] = payload
        captured["data"] = Path(payload["filePath"]).read_bytes()
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=json.dumps({"id": 3, "size": 4, "digest": "def"}),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    api = _make_api(node_executable=Path("/usr/bin/node"))
    source = io.BytesIO(b"payload")
    result = api.upload_artifact_fileobj(source, name="payload.bin")

    assert result == ArtifactUploadResult(id=3, size=4, digest="def")
    assert captured["data"] == b"payload"
    payload = captured["payload"]
    assert payload["name"] == "payload.bin"
    assert "retentionDays" not in payload


def test_staged_uploads_use_runner_temp_when_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))

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
        del text, capture_output, check, env
        payload = json.loads(input)
        captured["file_path"] = payload["filePath"]
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=json.dumps({"id": "1", "size": 1, "digest": "sha256:aaa"}),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    api = _make_api()
    api.upload_artifact_fileobj(io.BytesIO(b"data"), name="data.bin")

    assert captured["file_path"].startswith(str(tmp_path))


# ---------------------------------------------------------------------------
# upload_artifact_bytes
# ---------------------------------------------------------------------------


def test_upload_bytes_delegates_to_fileobj(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
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
        del text, capture_output, check, env
        payload = json.loads(input)
        captured["data"] = Path(payload["filePath"]).read_bytes()
        captured["name"] = payload["name"]
        captured["expires_in"] = payload.get("expiresAt")
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=json.dumps({"id": 6, "size": 7, "digest": "ghi"}),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    api = _make_api(node_executable=Path("/usr/bin/node"))
    result = api.upload_artifact_bytes(
        memoryview(b"payload"),
        name="payload.bin",
    )

    assert result == ArtifactUploadResult(id=6, size=7, digest="ghi")
    assert captured["data"] == b"payload"
    assert captured["name"] == "payload.bin"
    assert captured["expires_in"] is None


# ---------------------------------------------------------------------------
# Node wrapper error handling
# ---------------------------------------------------------------------------


def test_node_wrapper_failure_surfaces_structured_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact_file = tmp_path / "artifact.txt"
    artifact_file.write_text("hello", encoding="utf-8")

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
                'GHA_ARTIFACT_CLIENT_ERROR:{"error":"Error","message":"boom"}\n'
            ),
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    api = _make_api()
    with pytest.raises(NodeWrapperExecutionError, match="boom") as exc_info:
        api.upload_artifact(artifact_file)

    assert exc_info.value.returncode == 1
    assert "some log line" in exc_info.value.stderr
