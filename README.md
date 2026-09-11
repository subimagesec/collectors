# SubImage Collectors

Customer-run collectors that export metadata for security graphs. The first collector produces a JSON snapshot of selected 1Password vaults, their access grants, group memberships, and item metadata.

The collector runs where you control the 1Password credential. It publishes only to the local file, S3 object, or Google Cloud Storage object you explicitly select. A Cartography module to ingest this format is a separate, future integration; this repository does not currently install or configure one.

## 1Password authentication comes first

The credential must support account identification, user and group enumeration, group membership, vault user/group grants, and item listing for every configured vault. A token that can read items is not necessarily able to read this access information. **Generic 1Password service-account-token compatibility has not been established.** The collector exits with an error if a required command is unavailable or unauthorized.

Start with an authenticated [1Password CLI](https://developer.1password.com/docs/cli/) user session whose permissions cover these operations. Validate an unattended credential locally before trying the scheduled deployment examples. This collector does not grant permissions or bypass 1Password's credential restrictions. See the [authentication and deployment guide](docs/deployment.md).

## Run locally

Requirements: Python 3.12+, [uv](https://docs.astral.sh/uv/), and the official 1Password CLI on `PATH`.

```sh
git clone https://github.com/subimagesec/collectors.git
cd collectors
uv sync --frozen
mkdir -p output

uv run subimage-collector onepassword \
  --account-id aaaaaaaaaaaaaaaaaaaaaaaaaa \
  --vault-id bbbbbbbbbbbbbbbbbbbbbbbbbb \
  --output output/onepassword.json
```

Replace the example UUIDs with your account UUID and the vault UUIDs to collect. `op whoami --format=json` identifies the signed-in account; `op vault list --format=json` lists vaults accessible to that session. Repeat `--vault-id` for each vault. Use `--account <account-selector>` when selecting a particular CLI account; `--account-id` independently checks that the selected account is the expected one.

`--output` is required. To upload with the cloud SDK's normal credential chain:

```sh
uv sync --frozen --extra aws
uv run subimage-collector onepassword \
  --account-id aaaaaaaaaaaaaaaaaaaaaaaaaa \
  --vault-id bbbbbbbbbbbbbbbbbbbbbbbbbb \
  --output s3://example-collector-snapshots/onepassword/snapshot.json
```

For Google Cloud Storage, install `--extra gcp` and use `gs://example-collector-snapshots/onepassword/snapshot.json`. Use workload identity for scheduled jobs, or your approved local cloud authentication. No cloud access key is required by the collector's interface.

## What the snapshot means

- Coverage is limited to the explicitly configured vaults. It is not a claim of account-wide vault coverage.
- Archived items are included. The snapshot records its vault scope, collection time, and schema version; see the [format and ingestion contract](docs/format.md) and [JSON schema](schemas/onepassword/v1.json).
- User names, email addresses, group names, and group memberships are included. Vault names and item titles are omitted unless you pass `--include-titles`. Titles can contain sensitive free text. Keep the output private; the local `output/` directory is gitignored.
- The collector uses metadata listing commands and an explicit output schema. It does not fetch item contents, export secret values, modify access, or infer secret-read permission from vault ownership/management alone.
- A collection failure does not publish a partial snapshot or replace an existing output. A successful run replaces the selected file or object with one complete snapshot. A publication failure returns a nonzero exit status.

## Run in a container or on a schedule

The Docker image bundles the collector, the official 1Password CLI, and both cloud upload dependencies. Build it from this checkout:

```sh
docker build -t subimage-collectors:local .
```

For deployment, publish your build to a registry you control and pass its immutable image digest. The initial implementation does not assume that an official image release already exists. Containerized CLI authentication is separate from your desktop session; a successful local desktop run does not prove that an unattended token will work.

After validating authentication, choose a deployment example:

| Runtime | Output | Example |
| --- | --- | --- |
| Cloud Run Job + Cloud Scheduler | GCS | [Terraform](examples/cloud-run/README.md) |
| ECS Fargate + EventBridge Scheduler | S3 | [Terraform](examples/ecs/README.md) |
| Kubernetes CronJob | S3 | [Manifest](examples/kubernetes/README.md) |

## Development

```sh
uv sync --frozen --all-extras
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

Tests use synthetic provider responses. Passing tests do not establish live support for a particular 1Password account or credential.

Collector code is licensed under [Apache 2.0](LICENSE). The image also bundles the official 1Password CLI, which is distributed under [1Password's terms](https://1password.com/legal/terms-of-service/); see its [CLI documentation](https://developer.1password.com/docs/cli/).
