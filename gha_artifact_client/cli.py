from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections.abc import Sequence
from dataclasses import asdict

from .client import (
    ArtifactClientApi,
    ArtifactDeleteResult,
    ArtifactListResult,
    ArtifactSignedURLResult,
)
from .exceptions import ArtifactClientError


def _parse_expires_at(value: str) -> dt.datetime:
    try:
        parsed = dt.datetime.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Invalid ISO 8601 datetime: {value!r}. "
            "Expected a timezone-aware format like "
            "'2026-12-31T23:59:59Z' or '2026-12-31T23:59:59+05:30'."
        ) from exc
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError(
            f"Missing timezone in {value!r}. "
            "Expected a timezone-aware format like "
            "'2026-12-31T23:59:59Z' or '2026-12-31T23:59:59+05:30'."
        )
    return parsed


def _parse_expires_in(value: str) -> float:
    try:
        seconds = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Invalid number of seconds: {value!r}. Expected an integer or float."
        ) from exc
    if seconds < 0:
        raise argparse.ArgumentTypeError(
            f"expires-in must be non-negative, got {value!r}."
        )
    return seconds


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gha-artifact-client",
        description="GitHub Actions artifact client.",
    )
    parser.add_argument(
        "--runtime-token",
        default=None,
        dest="runtime_token",
        help=(
            "GitHub Actions runtime token "
            "(default: read from ACTIONS_RUNTIME_TOKEN environment variable)"
        ),
    )
    parser.add_argument(
        "--results-url",
        default=None,
        help=(
            "GitHub Actions results URL "
            "(default: read from ACTIONS_RESULTS_URL environment variable)"
        ),
    )
    parser.add_argument(
        "--node",
        default="node",
        dest="node_executable",
        help=(
            "Node.js executable to run the vendored node wrapper (default: %(default)s)"
        ),
    )

    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    upload_parser = subparsers.add_parser(
        "upload",
        help="Upload a file as a GitHub Actions artifact.",
        description="Upload a single file as a GitHub Actions artifact.",
    )
    upload_parser.add_argument("path", help="File to upload")
    upload_parser.add_argument(
        "--name",
        help="Artifact name (default: the uploaded file's basename)",
    )
    upload_parser.add_argument(
        "--mime-type",
        help="MIME type for the artifact (default: inferred from the file extension)",
    )
    expiry_group = upload_parser.add_mutually_exclusive_group()
    expiry_group.add_argument(
        "--expires-at",
        type=_parse_expires_at,
        help=(
            "Exact expiry time as a timezone-aware ISO 8601 datetime "
            "(e.g. '2026-12-31T23:59:59Z'). Mutually exclusive with --expires-in."
        ),
    )
    expiry_group.add_argument(
        "--expires-in",
        type=_parse_expires_in,
        help=(
            "Expiry time as seconds from now (int or float, e.g. 86400 for one day). "
            "Mutually exclusive with --expires-at."
        ),
    )
    upload_parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Output result as JSON instead of human-readable text",
    )

    delete_parser = subparsers.add_parser(
        "delete",
        help="Delete a GitHub Actions artifact by name.",
        description=(
            "Delete a GitHub Actions artifact by name from the current workflow"
            " job run."
        ),
    )
    delete_parser.add_argument("name", help="Name of the artifact to delete")
    delete_parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Output result as JSON instead of human-readable text",
    )

    get_signed_url_parser = subparsers.add_parser(
        "get-signed-url",
        help="Get a pre-signed download URL for a GitHub Actions artifact.",
        description=(
            "Return a pre-signed HTTPS URL for direct download of a GitHub Actions"
            " artifact from storage."
        ),
    )
    get_signed_url_parser.add_argument("name", help="Name of the artifact")
    get_signed_url_parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Output result as JSON instead of human-readable text",
    )

    list_parser = subparsers.add_parser(
        "list",
        help="List all GitHub Actions artifacts for the current workflow job run.",
        description=("List all artifacts for the current workflow job run."),
    )
    list_parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Output result as JSON instead of human-readable text",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.subcommand == "upload":
        try:
            api = ArtifactClientApi(
                runtime_token=args.runtime_token,
                results_url=args.results_url,
                node_executable=args.node_executable,
            )
            result = api.upload_artifact(
                args.path,
                name=args.name,
                mime_type=args.mime_type,
                expires_at=args.expires_at,
                expires_in=args.expires_in,
            )
        except ArtifactClientError as exc:
            print(str(exc), file=sys.stderr)
            return 1

        if args.json:
            print(json.dumps(asdict(result)))
        else:
            print("Artifact uploaded successfully.")
            if result.id is not None:
                print(f"  ID:     {result.id}")
            if result.size is not None:
                print(f"  Size:   {result.size} bytes")
            if result.digest is not None:
                print(f"  Digest: {result.digest}")

    elif args.subcommand == "delete":
        try:
            api = ArtifactClientApi(
                runtime_token=args.runtime_token,
                results_url=args.results_url,
                node_executable=args.node_executable,
            )
            result_d: ArtifactDeleteResult = api.delete_artifact(args.name)
        except ArtifactClientError as exc:
            print(str(exc), file=sys.stderr)
            return 1

        if args.json:
            print(json.dumps({"id": result_d.id}))
        else:
            print(f"Deleted artifact '{args.name}' (id: {result_d.id}).")

    elif args.subcommand == "get-signed-url":
        try:
            api = ArtifactClientApi(
                runtime_token=args.runtime_token,
                results_url=args.results_url,
                node_executable=args.node_executable,
            )
            result_s: ArtifactSignedURLResult = api.get_signed_artifact_url(args.name)
        except ArtifactClientError as exc:
            print(str(exc), file=sys.stderr)
            return 1

        if args.json:
            print(json.dumps({"url": result_s.url}))
        else:
            print(f"Signed URL for '{args.name}': {result_s.url}")

    elif args.subcommand == "list":
        try:
            api = ArtifactClientApi(
                runtime_token=args.runtime_token,
                results_url=args.results_url,
                node_executable=args.node_executable,
            )
            result_l: ArtifactListResult = api.list_artifacts()
        except ArtifactClientError as exc:
            print(str(exc), file=sys.stderr)
            return 1

        if args.json:
            artifacts_json = [
                {
                    "id": a.id,
                    "name": a.name,
                    "size": a.size,
                    "created_at": a.created_at.isoformat(),
                    "digest": a.digest,
                }
                for a in result_l.artifacts
            ]
            print(json.dumps({"artifacts": artifacts_json}))
        else:
            n = len(result_l.artifacts)
            print(f"{n} artifact(s):")
            for artifact in result_l.artifacts:
                print(f"  {artifact.name}")
                print(f"    ID:         {artifact.id}")
                print(f"    Size:       {artifact.size} bytes")
                print(f"    Created at: {artifact.created_at.isoformat()}")
                print(f"    Digest:     {artifact.digest}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
