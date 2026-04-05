# gha-artifact-client

Python wrapper/CLI around `@actions/artifact` for creating, listing, deleting,
and getting signed download URLs for workflow artifacts from inside a GitHub
Actions job.

Allows you to upload, list, delete, and get signed download URLs for workflow
artifacts dynamically from Python code without needing to invoke the
`actions/upload-artifact` action or the GitHub REST API in your workflow yaml.

## Notes

- Uploading, listing, and deleting artifacts only works during the lifetime of a
  GitHub Actions job.
- Unlike other GitHub API interactions requires a `ACTIONS_RUNTIME_TOKEN` and
  and not a `GITHUB_TOKEN`.
- Since the artifact API is not publicly documented, this package vendors a
  custom-built node wrapper around the official
  [@actions/artifact](https://www.npmjs.com/package/@actions/artifact) package,
  which is invoked with node. node needs to be provided by the user.
- Only depends on the Python standard library.
- Only direct single-file uploads are supported. If you need zip files, you need
  to create them yourself before uploading.

## Usage

### Python API

```python
import io

from gha_artifact_client import ArtifactClientApi

# Credentials from environment variables (default)
api = ArtifactClientApi()

# Or supply credentials explicitly — useful when you don't want them
# sitting in os.environ where other subprocesses could inherit them
api = ArtifactClientApi(
    runtime_token="...",
    results_url="...",
)

# Upload a file from disk
result = api.upload_artifact("dist/package.tar.gz")

# Upload with a custom artifact name and expiry time
result = api.upload_artifact(
    "dist/package.tar.gz",
    name="build-output.tar.gz",
    expires_in=7 * 24 * 3600,  # 7 days from now, in seconds
)

# Or set an exact expiry datetime (must be timezone-aware)
import datetime as dt
result = api.upload_artifact(
    "dist/package.tar.gz",
    expires_at=dt.datetime(2026, 12, 31, 23, 59, 59, tzinfo=dt.timezone.utc),
)

print(result.id)
print(result.digest)

# Upload from in-memory bytes
result = api.upload_artifact_bytes(
    b"hello from memory\n",
    name="build-output.txt",
)

print(result.id)

# Upload using a file-like object
with open("dist/package.tar.gz", "rb") as f:
    result = api.upload_artifact_fileobj(f, name="package.tar.gz")

print(result.id)

# Delete an artifact by name
result = api.delete_artifact("package.tar.gz")

print(result.id)

# Get a pre-signed download URL for an artifact
result = api.get_signed_artifact_url("package.tar.gz")

print(result.url)

# List all artifacts for the current workflow job run
result = api.list_artifacts()

for artifact in result.artifacts:
    print(artifact.id, artifact.name, artifact.size)
```

### CLI

```bash
# Upload
gha-artifact-client upload dist/package.tar.gz --name package.tar.gz --expires-in 604800

# Delete
gha-artifact-client delete package.tar.gz

# Get a pre-signed download URL
gha-artifact-client get-signed-url package.tar.gz

# List all artifacts
gha-artifact-client list
```

`--expires-in` takes seconds (int or float). Use `--expires-at` for an exact
point in time as a timezone-aware ISO 8601 datetime. The two flags are mutually
exclusive.

All subcommands accept `--json` to emit machine-readable output:

```bash
gha-artifact-client upload dist/package.tar.gz --json
# {"id": 42, "size": 1234, "digest": "sha256:..."}

gha-artifact-client delete package.tar.gz --json
# {"id": 42}

gha-artifact-client get-signed-url package.tar.gz --json
# {"url": "https://..."}

gha-artifact-client list --json
# {"artifacts": [{"id": 42, "name": "package.tar.gz", "size": 1234, "created_at": "2025-06-01T12:00:00+00:00", "digest": "sha256:..."}]}
```

Credentials default to `ACTIONS_RUNTIME_TOKEN` and `ACTIONS_RESULTS_URL` from
the environment, but can be supplied explicitly:

```bash
gha-artifact-client --runtime-token "$MY_TOKEN" --results-url "$MY_RESULTS_URL" \
  upload dist/package.tar.gz
```

## Credentials & Security Considerations

Uploading and deleting artifacts requires a URL and a credential that is only
available inside a live GitHub Actions job:

- `ACTIONS_RUNTIME_TOKEN` — a token created for the current job.
- `ACTIONS_RESULTS_URL` — the endpoint for the artifact storage backend.

These are **not** the same as `GITHUB_TOKEN` and are not exposed as regular
environment variables. They are only exposed to `action` steps and not `run`
steps. To make them available in `run` steps you can extract them via
[`actions/github-script`](https://github.com/actions/github-script):

```yaml
permissions: {}

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: Get artifact credentials
        id: vars
        uses: actions/github-script@v8
        with:
          script: |
            core.setOutput('ACTIONS_RUNTIME_TOKEN', process.env['ACTIONS_RUNTIME_TOKEN'])
            core.setOutput('ACTIONS_RESULTS_URL', process.env['ACTIONS_RESULTS_URL'])

      - name: Upload artifact
        env:
          ACTIONS_RUNTIME_TOKEN: ${{ steps.vars.outputs.ACTIONS_RUNTIME_TOKEN }}
          ACTIONS_RESULTS_URL: ${{ steps.vars.outputs.ACTIONS_RESULTS_URL }}
        run: python your_script.py
```

### Notes on the Token and Security

* The token is valid for `timeout-minutes` of the current job, which defaults to
  360 minutes (6 hours). After that, it expires and cannot be used to upload
  artifacts.

* Even if the token hasn't expired, it appears to be invalidated after the job
  completes. Using it after the current job completes results in:

    > Failed to CreateArtifact: Received non-retryable error: Failed request: (403) Forbidden: job is complete

* From what I understand, the token can also be used to upload cache entries and
  job logs, but I haven't tested that. If you are passing them to third party
  code, consider the security implications of that. I'd recommend to remove the
  token from the environment when calling third-party code that doesn't need it,
  to avoid accidental leaks.

* `ACTIONS_RESULTS_URL` for github.com on hosted runners, at the time of
  writing, is `https://results-receiver.actions.githubusercontent.com/`.

## Development

- Install Python dependencies with `uv sync`.
- Install node wrapper dependencies with `npm ci` in `node-wrapper/`.
- Lint the node wrapper with `npm run lint` in `node-wrapper/`.
- Type-check the node wrapper with `npm run tsc` in `node-wrapper/`.
- Rebuild the vendored node wrapper with `npm run build` in `node-wrapper/`.
