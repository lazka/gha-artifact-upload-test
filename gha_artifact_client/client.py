from __future__ import annotations

import datetime as dt
import io
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import BinaryIO

from .exceptions import (
    NodeNotFoundError,
    NodeWrapperExecutionError,
    UnsupportedEnvironmentError,
)

_NODE_WRAPPER_ERROR_PREFIX = "GHA_ARTIFACT_CLIENT_ERROR:"
_PathLike = str | bytes | os.PathLike[str] | os.PathLike[bytes]
_ExpiresAt = dt.datetime | float | int


def _expires_at_to_unix(expires_at: _ExpiresAt) -> float:
    if isinstance(expires_at, dt.datetime):
        if expires_at.tzinfo is None:
            raise ValueError(
                "expires_at must be a timezone-aware datetime; "
                "got a naive datetime which has ambiguous timezone semantics. "
                "Add tzinfo, e.g. dt.datetime(..., tzinfo=dt.timezone.utc)."
            )
        return expires_at.timestamp()
    return float(expires_at)


def _expires_in_to_unix(expires_in: float | int) -> float:
    return (
        dt.datetime.now(tz=dt.UTC) + dt.timedelta(seconds=float(expires_in))
    ).timestamp()


@dataclass(frozen=True, slots=True)
class ArtifactUploadResult:
    """Result of a successful artifact upload."""

    id: int
    """The numeric artifact ID assigned by GitHub Actions, e.g. ``42``."""

    size: int
    """The size of the uploaded artifact in bytes, e.g. ``1048576``."""

    digest: str
    """The SHA-256 content digest of the uploaded file in the form
    ``"sha256:<hex>"``, e.g.
    ``"sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"``."""


@dataclass(frozen=True, slots=True)
class ArtifactDeleteResult:
    """Result of a successful artifact deletion."""

    id: int
    """The numeric artifact ID of the deleted artifact, e.g. ``42``."""


class ArtifactClientApi:
    """Client for GitHub Actions artifacts.

    Credentials (``runtime_token`` and ``results_url``) are resolved at
    construction time. If not provided explicitly, they are read from the
    ``ACTIONS_RUNTIME_TOKEN`` and ``ACTIONS_RESULTS_URL`` environment
    variables. A :exc:`UnsupportedEnvironmentError` is raised immediately if
    either value cannot be resolved.

    Supplying credentials explicitly avoids placing them in ``os.environ``,
    which would otherwise expose them to any subprocess spawned by the calling
    process.
    """

    def __init__(
        self,
        *,
        runtime_token: str | None = None,
        results_url: str | None = None,
        node_executable: _PathLike = "node",
    ) -> None:
        resolved_token = (
            runtime_token
            if runtime_token is not None
            else os.environ.get("ACTIONS_RUNTIME_TOKEN")
        )
        resolved_url = (
            results_url
            if results_url is not None
            else os.environ.get("ACTIONS_RESULTS_URL")
        )

        missing = [
            name
            for name, value in (
                ("ACTIONS_RUNTIME_TOKEN", resolved_token),
                ("ACTIONS_RESULTS_URL", resolved_url),
            )
            if not value
        ]
        if missing:
            raise UnsupportedEnvironmentError(
                "Artifact upload requires a live GitHub Actions job runtime. "
                f"Missing environment variables: {', '.join(missing)}."
            )

        # At this point both values are non-empty strings.
        assert resolved_token is not None and resolved_url is not None
        self._runtime_token: str = resolved_token
        self._results_url: str = resolved_url
        self._node_executable = node_executable

    def _run_node_wrapper(
        self, payload: dict[str, object]
    ) -> dict[str, str | int | float | bool]:
        node_command = os.fsdecode(self._node_executable)
        node_wrapper = resources.files("gha_artifact_client").joinpath(
            "_vendor/artifact_node_wrapper.mjs"
        )
        with resources.as_file(node_wrapper) as node_wrapper_path:
            node_wrapper_env = {
                **os.environ,
                "ACTIONS_RUNTIME_TOKEN": self._runtime_token,
                "ACTIONS_RESULTS_URL": self._results_url,
            }
            try:
                process = subprocess.run(
                    [node_command, str(node_wrapper_path)],
                    input=json.dumps(payload),
                    env=node_wrapper_env,
                    text=True,
                    capture_output=True,
                    check=False,
                )
            except FileNotFoundError as exc:
                raise NodeNotFoundError(
                    f"Unable to execute Node.js binary '{node_command}'."
                ) from exc

        if process.returncode != 0:
            message = "Artifact node wrapper failed"
            for line in reversed(process.stderr.splitlines()):
                if line.startswith(_NODE_WRAPPER_ERROR_PREFIX):
                    try:
                        details = json.loads(
                            line.removeprefix(_NODE_WRAPPER_ERROR_PREFIX)
                        )
                    except json.JSONDecodeError:
                        break

                    message = details.get("message", message)
                    break

            raise NodeWrapperExecutionError(
                message,
                returncode=process.returncode,
                stderr=process.stderr,
                stdout=process.stdout,
            )

        try:
            response: dict[str, str | int | float | bool] = json.loads(process.stdout)
        except json.JSONDecodeError as exc:
            raise NodeWrapperExecutionError(
                "Artifact node wrapper returned invalid JSON",
                returncode=process.returncode,
                stderr=process.stderr,
                stdout=process.stdout,
            ) from exc

        return response

    def upload_artifact(
        self,
        path: _PathLike,
        *,
        name: str | None = None,
        mime_type: str | None = None,
        expires_at: _ExpiresAt | None = None,
        expires_in: float | int | None = None,
    ) -> ArtifactUploadResult:
        """Upload a single file as a GitHub Actions artifact.

        By default, the created artifact name matches the uploaded file name.
        For example, uploading ``dist/package.tar.gz`` creates an artifact
        named ``package.tar.gz``. If ``name`` is provided, it will be used as
        an artifact name instead.

        The MIME type is inferred from the file extension by default. Pass
        ``mime_type`` to override it explicitly.

        ``expires_at`` sets an exact expiry time. It may be a
        :class:`~datetime.datetime` object (must be timezone-aware) or a Unix
        timestamp (int or float, seconds since epoch).

        ``expires_in`` sets an expiry time relative to now, in seconds. It may
        be an int or float. Providing both ``expires_at`` and ``expires_in`` is
        an error.

        If neither is given, GitHub uses the repository or organization default
        retention policy.

        Only direct single-file uploads are supported. If you want to upload a
        directory or multiple files, create a zip archive in Python first and
        upload that archive file.
        """

        requested_path = Path(os.fsdecode(path))
        if not requested_path.exists():
            raise ValueError(f"Upload path does not exist: {requested_path}")

        resolved_path = requested_path.resolve()

        if not resolved_path.is_file():
            raise ValueError(
                "Only single-file uploads are supported. "
                f"Expected a regular file path, got: {resolved_path}"
            )

        artifact_name = name if name is not None else requested_path.name

        if expires_at is not None and expires_in is not None:
            raise ValueError(
                "Specify at most one of expires_at and expires_in, not both."
            )

        payload: dict[str, object] = {
            "action": "upload",
            "name": artifact_name,
            "filePath": str(resolved_path),
        }
        if mime_type is not None:
            payload["mimeType"] = mime_type
        if expires_at is not None:
            payload["expiresAt"] = _expires_at_to_unix(expires_at)
        elif expires_in is not None:
            payload["expiresAt"] = _expires_in_to_unix(expires_in)

        response = self._run_node_wrapper(payload)

        raw_id = response.get("id")
        raw_size = response.get("size")
        raw_digest = response.get("digest")

        missing = [
            field_name
            for field_name, value in (
                ("id", raw_id),
                ("size", raw_size),
                ("digest", raw_digest),
            )
            if value is None
        ]
        if missing:
            raise NodeWrapperExecutionError(
                "Artifact upload node wrapper response missing fields: "
                + ", ".join(missing),
                returncode=0,
                stderr="",
                stdout="",
            )

        assert raw_id is not None and raw_size is not None and raw_digest is not None
        return ArtifactUploadResult(
            id=int(raw_id),
            size=int(raw_size),
            digest=str(raw_digest),
        )

    def upload_artifact_fileobj(
        self,
        fileobj: BinaryIO,
        *,
        name: str,
        mime_type: str | None = None,
        expires_at: _ExpiresAt | None = None,
        expires_in: float | int | None = None,
    ) -> ArtifactUploadResult:
        """Upload a single artifact from a binary file-like object.
        The file object is read from its current position.
        """

        with tempfile.TemporaryDirectory(
            prefix="gha-artifact-client-",
            dir=os.environ.get("RUNNER_TEMP") or None,
        ) as temp_dir:
            temp_path = Path(temp_dir) / "upload"
            with temp_path.open("wb") as temp_file:
                shutil.copyfileobj(fileobj, temp_file)

            return self.upload_artifact(
                temp_path,
                name=name,
                mime_type=mime_type,
                expires_at=expires_at,
                expires_in=expires_in,
            )

    def upload_artifact_bytes(
        self,
        data: bytes | bytearray | memoryview,
        *,
        name: str,
        mime_type: str | None = None,
        expires_at: _ExpiresAt | None = None,
        expires_in: float | int | None = None,
    ) -> ArtifactUploadResult:
        """Upload a single artifact from in-memory bytes."""

        return self.upload_artifact_fileobj(
            io.BytesIO(bytes(data)),
            name=name,
            mime_type=mime_type,
            expires_at=expires_at,
            expires_in=expires_in,
        )

    def delete_artifact(self, name: str) -> ArtifactDeleteResult:
        """Delete a GitHub Actions artifact by name.

        Deletes the artifact with the given name from the current workflow job
        run. If multiple artifacts share the same name, the backend deletes the
        most recently created one.

        Returns an :class:`ArtifactDeleteResult` containing the numeric ID of
        the deleted artifact.
        """

        payload: dict[str, object] = {
            "action": "delete",
            "name": name,
        }

        response = self._run_node_wrapper(payload)

        raw_id = response.get("id")
        if raw_id is None:
            raise NodeWrapperExecutionError(
                "Artifact delete node wrapper response missing field: id",
                returncode=0,
                stderr="",
                stdout="",
            )

        assert raw_id is not None
        return ArtifactDeleteResult(id=int(raw_id))
