# 1Password collector: agent guide

The collector exports who can reach which 1Password vaults: users, service
accounts, groups, memberships, vault grants with their permissions, and item
metadata. It never reads item fields or secret values. It runs once, writes one
JSON snapshot to a local file, S3, or Google Cloud Storage, and exits.

Two consumers read the snapshot:

- **Cartography**: `cartography --selected-modules onepassword,ontology --onepassword-source <file, directory, or bucket prefix>`.
  See the [Cartography 1Password module](https://docs.cartography.dev/modules/onepassword/index.html).
- **Subimage**: the 1Password module in Subimage, a managed Cartography that is
  faster to run and operate. See the
  [Subimage setup guide](https://docs.subimage.io/docs/modules/onepassword/setup)
  or [subimage.io](https://subimage.io).

## Set up the collector for a user

Ask the user which consumer they use (Cartography or Subimage) and which cloud
holds the bucket. Then follow these steps in order.

1. **Check the 1Password CLI.** `op --version` must be current: 1Password
   rejects outdated CLI releases. The published image bundles a current CLI.

2. **Find the account and vault IDs.** Signed in as a 1Password admin:

   ```sh
   op account get --format json   # "id" is the account ID
   op vault list
   ```

   Service accounts can't be granted the built-in Private, Employee, or Shared
   vaults, and new vaults are not added to a service account automatically.

3. **Create a read-only service account and store its token.** Never print the
   token or write it to a file. Pipe it straight into the secret store of the
   cloud that runs the collector, and strip the trailing newline that `--raw`
   prints. On AWS:

   ```sh
   op service-account create "Subimage collector" \
     --vault <vault-id>:read_items --vault <another-vault-id>:read_items \
     --raw | tr -d '\n' \
     | aws secretsmanager create-secret --name onepassword-collector-token \
         --secret-string file:///dev/stdin
   ```

   On Google Cloud, end the pipeline with
   `gcloud secrets create onepassword-collector-token --data-file=-` in the
   deployment project, and pass the secret and its version (`1`) to the Cloud
   Run example as `op_secret_id` and `op_secret_version`.

   Ask the user to confirm the vault list first: a Read Items token can read the
   secrets in those vaults.

4. **Deploy a scheduled example.** The ECS and Cloud Run examples create a
   private bucket, the schedule, and least-privilege roles. The Kubernetes
   manifest needs an existing bucket and a workload identity that can write to
   it. None of them accepts inbound traffic.

   | Cloud | Example | Subimage access |
   | --- | --- | --- |
   | AWS | [ECS Fargate + EventBridge](examples/ecs/README.md) | Set `subimage_tenant_role_arn` and `subimage_external_id` from Subimage's 1Password setup page. |
   | Google Cloud | [Cloud Run + Cloud Scheduler](examples/cloud-run/README.md) | Add the Subimage GCP integration's principal to `snapshot_readers`. |
   | Kubernetes | [CronJob](examples/kubernetes/README.md) | Grant read access to the bucket yourself. |

   Pin `ghcr.io/subimagesec/collectors/1password` by digest:

   ```sh
   docker buildx imagetools inspect ghcr.io/subimagesec/collectors/1password:<version>
   ```

5. **Run it once by hand** and confirm a snapshot appears at the output key.
   Do not wait for the schedule.

6. **Connect the consumer.**
   - Subimage: enter the example's `subimage_onepassword_source` output (and
     `subimage_onepassword_aws_account_id` for S3) in **Modules** → **1Password**,
     then run a sync. The Kubernetes manifest has no outputs: enter the
     `s3://<bucket>/<prefix>/` that the CronJob writes to and the bucket's AWS
     account ID, and create the reader role from the Subimage setup guide.
   - Cartography: pass the bucket prefix to `--onepassword-source`, with
     credentials that can list and read it.

## Gotchas

- **Use one collector per 1Password account and one fixed output key.**
  Consumers read every `.json` object under the prefix. Two snapshots of one
  account with different vault scopes stop the sync, and old timestamped copies
  are re-read on every sync.
- **On ECS Fargate, do not set a read-only root filesystem.** The CLI writes its
  config to `/tmp/op` as the image's non-root user (UID 10001), and Fargate
  creates task volumes owned by root.
- **The image must run as UID 10001.** The CLI needs a matching Unix user, so an
  arbitrary numeric UID breaks authentication.
- **Errors are deliberately generic** so they never echo provider data. To debug
  authentication, run `op whoami` in the same image and environment.
- Snapshots include vault names and item titles, so answers name the vaults and
  items. Titles are free text and can be sensitive. Pass `--omit-titles` (or set
  `include_titles = false` in an example) if the user wants them left out.

## Code map

| Path | Purpose |
| --- | --- |
| `src/onepassword_collector/onepassword.py` | CLI reads (`op` subprocess), validation, and snapshot assembly. |
| `src/onepassword_collector/vault_access.py` | Vault grants from the 1Password SDK, including the raw permission bitmask. |
| `src/onepassword_collector/output.py` | Atomic publication to a file, S3, or GCS. |
| `schemas/v1.json`, `docs/format.md` | The snapshot contract that Cartography and Subimage depend on. |
| `examples/` | Terraform and Kubernetes deployments. CI validates them. |

## Change the collector

- Run `make test`. Tests use synthetic responses and a canary token. A new read
  needs a test proving the canary never reaches the snapshot, arguments, or
  errors.
- A snapshot format change updates `schemas/v1.json` and `docs/format.md`, and
  needs a matching change in Cartography's `cartography/intel/onepassword`.
- Bump `version` in `pyproject.toml` for a release, then a maintainer tags
  `1password/v<version>` on `main`.
