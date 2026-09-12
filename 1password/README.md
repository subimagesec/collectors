# 1Password Collector

A customer-run collector that exports a JSON snapshot of selected 1Password vaults, their access grants, group memberships, and item metadata for security graphs.

The collector runs where you control the 1Password credential. It publishes only to the local file, S3 object, or Google Cloud Storage object you explicitly select. A Cartography module to ingest this format is a separate, future integration; this repository does not currently install or configure one.

## 1Password authentication comes first

Set `OP_SERVICE_ACCOUNT_TOKEN` to a 1Password service account token scoped to the intended vaults with **Read Items** access. The collector uses that token with the official CLI for inventory and the official Python SDK for authoritative user/group vault grants. It requires the token even if a desktop CLI user session is available.

Full local collection was validated with **1Password CLI 2.32.1** and **Python SDK 0.4.1** using this permission scope. Follow the [service account setup and validation guide](docs/authentication.md) for your intended deployment before scheduling collection. The collector does not grant permissions, and fails if required reads are unavailable or unauthorized.

## Run locally

Requirements: Python 3.12+, [uv](https://docs.astral.sh/uv/), the official [1Password CLI](https://developer.1password.com/docs/cli/) on `PATH`, and `OP_SERVICE_ACCOUNT_TOKEN` injected through your approved secret-handling method. `uv sync` installs the official Python SDK dependency. Keep the token out of shell history and tracked files.

```sh
git clone https://github.com/subimagesec/collectors.git
cd collectors/1password
uv sync --frozen
mkdir -p output

uv run onepassword-collector \
  --account-id aaaaaaaaaaaaaaaaaaaaaaaaaa \
  --vault-id bbbbbbbbbbbbbbbbbbbbbbbbbb \
  --output output/onepassword.json
```

Replace the example UUIDs with your account UUID and the vault UUIDs to collect. With the same token, `op whoami --format=json` identifies the account and `op vault list --format=json` lists accessible vaults. Repeat `--vault-id` for each vault; `--account-id` independently checks the expected account. Newly created vaults are not automatically added to the token or collection scope.

`--output` is required. To upload with the cloud SDK's normal credential chain:

```sh
uv sync --frozen --extra aws
uv run onepassword-collector \
  --account-id aaaaaaaaaaaaaaaaaaaaaaaaaa \
  --vault-id bbbbbbbbbbbbbbbbbbbbbbbbbb \
  --output s3://example-collector-snapshots/onepassword/snapshot.json
```

For Google Cloud Storage, install `--extra gcp` and use `gs://example-collector-snapshots/onepassword/snapshot.json`. Use workload identity for scheduled jobs, or your approved local cloud authentication. No cloud access key is required by the collector's interface.

## What the snapshot means

- Coverage is limited to the explicitly configured vaults. It is not a claim of account-wide vault coverage.
- Archived items are included. The snapshot records its vault scope, collection time, and schema version; see the [format and ingestion contract](docs/format.md) and [JSON schema](schemas/v1.json).
- User names, email addresses, and states are included when provided, along with group names and memberships. The authenticated service account can have only an ID and type if it is absent from the directory. Vault names and item titles are omitted unless you pass `--include-titles`. Titles can contain sensitive free text. Keep the output private; the local `output/` directory is gitignored.
- The collector uses CLI metadata commands and SDK vault-accessor reads with an explicit output schema. It does not fetch item contents, export secret values, modify access, or infer secret-read permission from vault ownership/management alone. Grants retain known SDK permission names in lowercase and the complete `permissions_bitmask`, including unknown bits.
- A collection failure does not publish a partial snapshot or replace an existing output. A successful run replaces the selected file or object with one complete snapshot. A publication failure returns a nonzero exit status.

## Run in a container

The Docker image bundles the collector, the official 1Password CLI and Python SDK, and both cloud upload dependencies. Build it from the `1password/` directory:

```sh
docker build -t onepassword-collector:local .
docker run --rm onepassword-collector:local --help
```

Run as the image's configured user (UID/GID `10001:10001`) and make any output volume writable by that user. The 1Password CLI requires a matching Unix user entry; overriding the container user with an arbitrary numeric UID can prevent authentication.

Component releases use tags such as `1password/v0.1.0` and publish to `ghcr.io/subimagesec/collectors/1password`. Until a release is available, publish your reviewed build to a registry you control. Use its immutable image digest for deployment. Containerized CLI authentication is separate from your desktop session; a successful local desktop run does not prove that an unattended token will work.

Maintainers create release tags from `main`. The release workflow verifies that the tagged commit is on `main`, its version matches `pyproject.toml`, and Python/container checks pass before publishing. Release tags cannot be moved or deleted.

## Development

```sh
uv sync --frozen --all-extras
make test
```

The Python distribution is `subimage-collector-onepassword`; its module is `onepassword_collector`. `make test` runs lint and the full test suite. Tests use synthetic provider responses. Passing tests do not establish live support for a particular 1Password account or credential.

Collector code is licensed under [Apache 2.0](LICENSE). The image also bundles the official 1Password CLI, which is distributed under [1Password's terms](https://1password.com/legal/terms-of-service/); see its [CLI documentation](https://developer.1password.com/docs/cli/).

The bundled Python SDK is [MIT-licensed](third-party/onepassword-sdk-LICENSE). Use of 1Password APIs and services is governed by the [1Password API Terms of Service](https://1password.com/legal/api-sdk-terms-of-service).
