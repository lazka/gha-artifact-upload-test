from __future__ import annotations

import datetime as dt
import json

import pytest

from gha_artifact_client.cli import main
from gha_artifact_client.client import (
    ArtifactClientApi,
    ArtifactDeleteResult,
    ArtifactInfo,
    ArtifactListResult,
    ArtifactSignedURLResult,
    ArtifactUploadResult,
)
from gha_artifact_client.exceptions import (
    ArtifactClientError,
)


def test_cli_prints_human_readable_result(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fake_upload_artifact(
        self: ArtifactClientApi,
        path: str,
        *,
        name: str | None,
        mime_type: str | None,
        expires_at: object,
        expires_in: object,
    ) -> ArtifactUploadResult:
        return ArtifactUploadResult(id=7, size=11, digest="abc")

    monkeypatch.setattr(ArtifactClientApi, "upload_artifact", fake_upload_artifact)

    exit_code = main(
        [
            "--runtime-token",
            "my-token",
            "--results-url",
            "https://results.example.test",
            "upload",
            "dist/out.tgz",
        ]
    )

    assert exit_code == 0
    output = capsys.readouterr()
    assert "7" in output.out
    assert "11" in output.out
    assert "abc" in output.out
    assert output.err == ""


def test_cli_prints_json_result(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    captured: dict[str, object] = {}

    def fake_upload_artifact(
        self: ArtifactClientApi,
        path: str,
        *,
        name: str | None,
        mime_type: str | None,
        expires_at: object,
        expires_in: object,
    ) -> ArtifactUploadResult:
        captured["call"] = {
            "path": path,
            "name": name,
            "mime_type": mime_type,
            "expires_at": expires_at,
            "expires_in": expires_in,
            "runtime_token": self._runtime_token,
            "results_url": self._results_url,
            "node_executable": self._node_executable,
        }
        return ArtifactUploadResult(id=7, size=11, digest="abc")

    monkeypatch.setattr(ArtifactClientApi, "upload_artifact", fake_upload_artifact)

    exit_code = main(
        [
            "--runtime-token",
            "my-token",
            "--results-url",
            "https://results.example.test",
            "--node",
            "node24",
            "upload",
            "dist/out.tgz",
            "--name",
            "build-output.zip",
            "--mime-type",
            "application/x-custom",
            "--json",
        ]
    )

    assert exit_code == 0
    assert captured["call"] == {
        "path": "dist/out.tgz",
        "name": "build-output.zip",
        "mime_type": "application/x-custom",
        "expires_at": None,
        "expires_in": None,
        "runtime_token": "my-token",
        "results_url": "https://results.example.test",
        "node_executable": "node24",
    }
    output = capsys.readouterr()
    assert json.loads(output.out) == {"id": 7, "size": 11, "digest": "abc"}
    assert output.err == ""


def test_cli_expires_at_is_parsed_as_datetime(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    captured: dict[str, object] = {}

    def fake_upload_artifact(
        self: ArtifactClientApi,
        path: str,
        *,
        name: str | None,
        mime_type: str | None,
        expires_at: object,
        expires_in: object,
    ) -> ArtifactUploadResult:
        captured["expires_at"] = expires_at
        return ArtifactUploadResult(id=1, size=2, digest="x")

    monkeypatch.setattr(ArtifactClientApi, "upload_artifact", fake_upload_artifact)
    monkeypatch.setenv("ACTIONS_RUNTIME_TOKEN", "token")
    monkeypatch.setenv("ACTIONS_RESULTS_URL", "https://results.example.test")

    exit_code = main(
        ["upload", "some-file.txt", "--expires-at", "2030-06-01T12:00:00Z"]
    )

    assert exit_code == 0
    assert captured["expires_at"] == dt.datetime(2030, 6, 1, 12, 0, 0, tzinfo=dt.UTC)


def test_cli_expires_at_rejects_naive_datetime(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("ACTIONS_RUNTIME_TOKEN", "token")
    monkeypatch.setenv("ACTIONS_RESULTS_URL", "https://results.example.test")

    with pytest.raises(SystemExit) as exc_info:
        main(["upload", "some-file.txt", "--expires-at", "2030-06-01T12:00:00"])

    assert exc_info.value.code != 0
    output = capsys.readouterr()
    assert "timezone" in output.err.lower() or "missing" in output.err.lower()


def test_cli_expires_in_is_parsed_as_float(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    captured: dict[str, object] = {}

    def fake_upload_artifact(
        self: ArtifactClientApi,
        path: str,
        *,
        name: str | None,
        mime_type: str | None,
        expires_at: object,
        expires_in: object,
    ) -> ArtifactUploadResult:
        captured["expires_in"] = expires_in
        return ArtifactUploadResult(id=1, size=2, digest="x")

    monkeypatch.setattr(ArtifactClientApi, "upload_artifact", fake_upload_artifact)
    monkeypatch.setenv("ACTIONS_RUNTIME_TOKEN", "token")
    monkeypatch.setenv("ACTIONS_RESULTS_URL", "https://results.example.test")

    exit_code = main(["upload", "some-file.txt", "--expires-in", "86400.5"])

    assert exit_code == 0
    assert captured["expires_in"] == pytest.approx(86400.5)


def test_cli_expires_in_rejects_negative(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("ACTIONS_RUNTIME_TOKEN", "token")
    monkeypatch.setenv("ACTIONS_RESULTS_URL", "https://results.example.test")

    with pytest.raises(SystemExit) as exc_info:
        main(["upload", "some-file.txt", "--expires-in", "-1"])

    assert exc_info.value.code != 0


def test_cli_expires_at_and_expires_in_are_mutually_exclusive(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("ACTIONS_RUNTIME_TOKEN", "token")
    monkeypatch.setenv("ACTIONS_RESULTS_URL", "https://results.example.test")

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "upload",
                "some-file.txt",
                "--expires-at",
                "2030-06-01T12:00:00Z",
                "--expires-in",
                "3600",
            ]
        )

    assert exc_info.value.code != 0


def test_cli_reads_credentials_from_env(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("ACTIONS_RUNTIME_TOKEN", "env-token")
    monkeypatch.setenv("ACTIONS_RESULTS_URL", "https://env.example.test")

    captured: dict[str, object] = {}

    def fake_upload_artifact(
        self: ArtifactClientApi,
        path: str,
        *,
        name: str | None,
        mime_type: str | None,
        expires_at: object,
        expires_in: object,
    ) -> ArtifactUploadResult:
        captured["runtime_token"] = self._runtime_token
        captured["results_url"] = self._results_url
        return ArtifactUploadResult(id=1, size=2, digest="xyz")

    monkeypatch.setattr(ArtifactClientApi, "upload_artifact", fake_upload_artifact)

    exit_code = main(["upload", "some-file.txt"])

    assert exit_code == 0
    assert captured["runtime_token"] == "env-token"
    assert captured["results_url"] == "https://env.example.test"


def test_cli_writes_artifact_errors_to_stderr(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fake_upload_artifact(
        self: ArtifactClientApi,
        path: str,
        *,
        name: str | None,
        mime_type: str | None,
        expires_at: object,
        expires_in: object,
    ) -> ArtifactUploadResult:
        raise ArtifactClientError("nope")

    monkeypatch.setattr(ArtifactClientApi, "upload_artifact", fake_upload_artifact)
    monkeypatch.setenv("ACTIONS_RUNTIME_TOKEN", "token")
    monkeypatch.setenv("ACTIONS_RESULTS_URL", "https://results.example.test")

    exit_code = main(["upload", "missing.txt"])

    assert exit_code == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == "nope\n"


def test_cli_missing_credentials_exits_with_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("ACTIONS_RUNTIME_TOKEN", raising=False)
    monkeypatch.delenv("ACTIONS_RESULTS_URL", raising=False)

    exit_code = main(["upload", "some-file.txt"])

    assert exit_code == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "live GitHub Actions" in output.err


# ---------------------------------------------------------------------------
# delete subcommand
# ---------------------------------------------------------------------------


def test_cli_delete_prints_human_readable_result(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fake_delete_artifact(
        self: ArtifactClientApi,
        name: str,
    ) -> ArtifactDeleteResult:
        return ArtifactDeleteResult(id=42)

    monkeypatch.setattr(ArtifactClientApi, "delete_artifact", fake_delete_artifact)
    monkeypatch.setenv("ACTIONS_RUNTIME_TOKEN", "token")
    monkeypatch.setenv("ACTIONS_RESULTS_URL", "https://results.example.test")

    exit_code = main(["delete", "my-artifact"])

    assert exit_code == 0
    output = capsys.readouterr()
    assert "my-artifact" in output.out
    assert "42" in output.out
    assert output.err == ""


def test_cli_delete_prints_json_result(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    captured: dict[str, object] = {}

    def fake_delete_artifact(
        self: ArtifactClientApi,
        name: str,
    ) -> ArtifactDeleteResult:
        captured["name"] = name
        captured["runtime_token"] = self._runtime_token
        captured["results_url"] = self._results_url
        captured["node_executable"] = self._node_executable
        return ArtifactDeleteResult(id=42)

    monkeypatch.setattr(ArtifactClientApi, "delete_artifact", fake_delete_artifact)

    exit_code = main(
        [
            "--runtime-token",
            "my-token",
            "--results-url",
            "https://results.example.test",
            "--node",
            "node24",
            "delete",
            "my-artifact",
            "--json",
        ]
    )

    assert exit_code == 0
    assert captured == {
        "name": "my-artifact",
        "runtime_token": "my-token",
        "results_url": "https://results.example.test",
        "node_executable": "node24",
    }
    output = capsys.readouterr()
    assert json.loads(output.out) == {"id": 42}
    assert output.err == ""


def test_cli_delete_reads_credentials_from_env(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("ACTIONS_RUNTIME_TOKEN", "env-token")
    monkeypatch.setenv("ACTIONS_RESULTS_URL", "https://env.example.test")

    captured: dict[str, object] = {}

    def fake_delete_artifact(
        self: ArtifactClientApi,
        name: str,
    ) -> ArtifactDeleteResult:
        captured["runtime_token"] = self._runtime_token
        captured["results_url"] = self._results_url
        return ArtifactDeleteResult(id=1)

    monkeypatch.setattr(ArtifactClientApi, "delete_artifact", fake_delete_artifact)

    exit_code = main(["delete", "some-artifact"])

    assert exit_code == 0
    assert captured["runtime_token"] == "env-token"
    assert captured["results_url"] == "https://env.example.test"


def test_cli_delete_writes_artifact_errors_to_stderr(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fake_delete_artifact(
        self: ArtifactClientApi,
        name: str,
    ) -> ArtifactDeleteResult:
        raise ArtifactClientError("delete failed")

    monkeypatch.setattr(ArtifactClientApi, "delete_artifact", fake_delete_artifact)
    monkeypatch.setenv("ACTIONS_RUNTIME_TOKEN", "token")
    monkeypatch.setenv("ACTIONS_RESULTS_URL", "https://results.example.test")

    exit_code = main(["delete", "my-artifact"])

    assert exit_code == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == "delete failed\n"


def test_cli_delete_missing_credentials_exits_with_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("ACTIONS_RUNTIME_TOKEN", raising=False)
    monkeypatch.delenv("ACTIONS_RESULTS_URL", raising=False)

    exit_code = main(["delete", "some-artifact"])

    assert exit_code == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "live GitHub Actions" in output.err


# ---------------------------------------------------------------------------
# get-signed-url subcommand
# ---------------------------------------------------------------------------

_SIGNED_URL = "https://storage.example.test/artifact?sig=abc123"


def test_cli_get_signed_url_prints_human_readable_result(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fake_get_signed_artifact_url(
        self: ArtifactClientApi,
        name: str,
    ) -> ArtifactSignedURLResult:
        return ArtifactSignedURLResult(url=_SIGNED_URL)

    monkeypatch.setattr(
        ArtifactClientApi, "get_signed_artifact_url", fake_get_signed_artifact_url
    )
    monkeypatch.setenv("ACTIONS_RUNTIME_TOKEN", "token")
    monkeypatch.setenv("ACTIONS_RESULTS_URL", "https://results.example.test")

    exit_code = main(["get-signed-url", "my-artifact"])

    assert exit_code == 0
    output = capsys.readouterr()
    assert _SIGNED_URL in output.out
    assert output.err == ""


def test_cli_get_signed_url_prints_json_result(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    captured: dict[str, object] = {}

    def fake_get_signed_artifact_url(
        self: ArtifactClientApi,
        name: str,
    ) -> ArtifactSignedURLResult:
        captured["name"] = name
        captured["runtime_token"] = self._runtime_token
        captured["results_url"] = self._results_url
        captured["node_executable"] = self._node_executable
        return ArtifactSignedURLResult(url=_SIGNED_URL)

    monkeypatch.setattr(
        ArtifactClientApi, "get_signed_artifact_url", fake_get_signed_artifact_url
    )

    exit_code = main(
        [
            "--runtime-token",
            "my-token",
            "--results-url",
            "https://results.example.test",
            "--node",
            "node24",
            "get-signed-url",
            "my-artifact",
            "--json",
        ]
    )

    assert exit_code == 0
    assert captured == {
        "name": "my-artifact",
        "runtime_token": "my-token",
        "results_url": "https://results.example.test",
        "node_executable": "node24",
    }
    output = capsys.readouterr()
    assert json.loads(output.out) == {"url": _SIGNED_URL}
    assert output.err == ""


def test_cli_get_signed_url_reads_credentials_from_env(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("ACTIONS_RUNTIME_TOKEN", "env-token")
    monkeypatch.setenv("ACTIONS_RESULTS_URL", "https://env.example.test")

    captured: dict[str, object] = {}

    def fake_get_signed_artifact_url(
        self: ArtifactClientApi,
        name: str,
    ) -> ArtifactSignedURLResult:
        captured["runtime_token"] = self._runtime_token
        captured["results_url"] = self._results_url
        return ArtifactSignedURLResult(url=_SIGNED_URL)

    monkeypatch.setattr(
        ArtifactClientApi, "get_signed_artifact_url", fake_get_signed_artifact_url
    )

    exit_code = main(["get-signed-url", "some-artifact"])

    assert exit_code == 0
    assert captured["runtime_token"] == "env-token"
    assert captured["results_url"] == "https://env.example.test"


def test_cli_get_signed_url_writes_artifact_errors_to_stderr(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fake_get_signed_artifact_url(
        self: ArtifactClientApi,
        name: str,
    ) -> ArtifactSignedURLResult:
        raise ArtifactClientError("signed url failed")

    monkeypatch.setattr(
        ArtifactClientApi, "get_signed_artifact_url", fake_get_signed_artifact_url
    )
    monkeypatch.setenv("ACTIONS_RUNTIME_TOKEN", "token")
    monkeypatch.setenv("ACTIONS_RESULTS_URL", "https://results.example.test")

    exit_code = main(["get-signed-url", "my-artifact"])

    assert exit_code == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == "signed url failed\n"


def test_cli_get_signed_url_missing_credentials_exits_with_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("ACTIONS_RUNTIME_TOKEN", raising=False)
    monkeypatch.delenv("ACTIONS_RESULTS_URL", raising=False)

    exit_code = main(["get-signed-url", "some-artifact"])

    assert exit_code == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "live GitHub Actions" in output.err


# ---------------------------------------------------------------------------
# list subcommand
# ---------------------------------------------------------------------------

_LIST_RESULT = ArtifactListResult(
    artifacts=(
        ArtifactInfo(
            id=10,
            name="build-output",
            size=2048,
            created_at=dt.datetime(2025, 6, 1, 12, 0, 0, tzinfo=dt.UTC),
            digest="sha256:aabbcc",
        ),
        ArtifactInfo(
            id=11,
            name="test-logs",
            size=512,
            created_at=dt.datetime(2025, 6, 2, 8, 30, 0, tzinfo=dt.UTC),
            digest="sha256:ddeeff",
        ),
    )
)


def test_cli_list_prints_human_readable_result(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fake_list_artifacts(self: ArtifactClientApi) -> ArtifactListResult:
        return _LIST_RESULT

    monkeypatch.setattr(ArtifactClientApi, "list_artifacts", fake_list_artifacts)
    monkeypatch.setenv("ACTIONS_RUNTIME_TOKEN", "token")
    monkeypatch.setenv("ACTIONS_RESULTS_URL", "https://results.example.test")

    exit_code = main(["list"])

    assert exit_code == 0
    output = capsys.readouterr()
    assert "2 artifact(s)" in output.out
    assert "build-output" in output.out
    assert "10" in output.out
    assert "2048" in output.out
    assert "sha256:aabbcc" in output.out
    assert "2025-06-01" in output.out
    assert "test-logs" in output.out
    assert "11" in output.out
    assert "sha256:ddeeff" in output.out
    assert "2025-06-02" in output.out
    assert output.err == ""


def test_cli_list_prints_json_result(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    captured: dict[str, object] = {}

    def fake_list_artifacts(self: ArtifactClientApi) -> ArtifactListResult:
        captured["runtime_token"] = self._runtime_token
        captured["results_url"] = self._results_url
        captured["node_executable"] = self._node_executable
        return _LIST_RESULT

    monkeypatch.setattr(ArtifactClientApi, "list_artifacts", fake_list_artifacts)

    exit_code = main(
        [
            "--runtime-token",
            "my-token",
            "--results-url",
            "https://results.example.test",
            "--node",
            "node24",
            "list",
            "--json",
        ]
    )

    assert exit_code == 0
    assert captured == {
        "runtime_token": "my-token",
        "results_url": "https://results.example.test",
        "node_executable": "node24",
    }
    output = capsys.readouterr()
    data = json.loads(output.out)
    assert "artifacts" in data
    assert len(data["artifacts"]) == 2
    assert data["artifacts"][0] == {
        "id": 10,
        "name": "build-output",
        "size": 2048,
        "created_at": "2025-06-01T12:00:00+00:00",
        "digest": "sha256:aabbcc",
    }
    assert data["artifacts"][1] == {
        "id": 11,
        "name": "test-logs",
        "size": 512,
        "created_at": "2025-06-02T08:30:00+00:00",
        "digest": "sha256:ddeeff",
    }
    assert output.err == ""


def test_cli_list_reads_credentials_from_env(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("ACTIONS_RUNTIME_TOKEN", "env-token")
    monkeypatch.setenv("ACTIONS_RESULTS_URL", "https://env.example.test")

    captured: dict[str, object] = {}

    def fake_list_artifacts(self: ArtifactClientApi) -> ArtifactListResult:
        captured["runtime_token"] = self._runtime_token
        captured["results_url"] = self._results_url
        return ArtifactListResult(artifacts=())

    monkeypatch.setattr(ArtifactClientApi, "list_artifacts", fake_list_artifacts)

    exit_code = main(["list"])

    assert exit_code == 0
    assert captured["runtime_token"] == "env-token"
    assert captured["results_url"] == "https://env.example.test"


def test_cli_list_writes_artifact_errors_to_stderr(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fake_list_artifacts(self: ArtifactClientApi) -> ArtifactListResult:
        raise ArtifactClientError("list failed")

    monkeypatch.setattr(ArtifactClientApi, "list_artifacts", fake_list_artifacts)
    monkeypatch.setenv("ACTIONS_RUNTIME_TOKEN", "token")
    monkeypatch.setenv("ACTIONS_RESULTS_URL", "https://results.example.test")

    exit_code = main(["list"])

    assert exit_code == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == "list failed\n"


def test_cli_list_missing_credentials_exits_with_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("ACTIONS_RUNTIME_TOKEN", raising=False)
    monkeypatch.delenv("ACTIONS_RESULTS_URL", raising=False)

    exit_code = main(["list"])

    assert exit_code == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "live GitHub Actions" in output.err
