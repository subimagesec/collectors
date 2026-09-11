# Authentication and deployment

## Establish that the credential can collect access metadata

**Do not assume that a 1Password service account token supports this collector.** Reading vault items alone is insufficient. The same credential must be able to run all of these read operations for the configured account and vault scope:

| CLI command family | Required information |
| --- | --- |
| `op whoami` | Account UUID, checked against `--account-id` |
| `op user list` | Users and their status |
| `op group list` | Groups |
| `op group user list` | Group memberships |
| `op vault list` | Accessible vault identities |
| `op vault user list` | Direct user grants on each configured vault |
| `op vault group list` | Group grants on each configured vault |
| `op item list` | Item metadata, including archived items |

The collector fails when a required command is unsupported, denied, or returns an unexpected shape. It does not silently fall back to an item-only inventory. A local authenticated CLI user session is a starting point for validation, but this repository has not established that a generic service account token can run the complete workflow unattended.

Read the official [CLI authentication guide](https://developer.1password.com/docs/cli/sign-in/), [service account documentation](https://developer.1password.com/docs/service-accounts/), and [CLI command reference](https://developer.1password.com/docs/cli/reference/). Determine the minimum permissions that actually satisfy the read operations in your account. The collector never creates a credential or grants access.

The cloud examples inject `OP_SERVICE_ACCOUNT_TOKEN` from an existing secret store. **That wiring is not a claim of token compatibility.** Before applying an example, run the same image with that exact credential in your own environment and verify that it produces a complete local snapshot. If it cannot enumerate users, groups, memberships, or vault grants, unattended deployment is not ready. An interactive session should not be copied into a scheduled job as a presumed long-lived credential.

## Define the collection boundary

Set the expected 26-character account UUID with `--account-id`, and explicitly list each vault UUID with `--vault-id`. `--account` is an optional CLI account selector, not a substitute for the expected UUID. Account identity is checked before collection.

The snapshot's scope is the configured vault set, not every vault in the account. Membership and grants preserve the permissions returned by 1Password. A management or ownership grant does not by itself establish the `read_items` permission. Archived items are included. Vault names and item titles require the explicit `--include-titles` option.

Treat the JSON as private security data even without secret values or titles. It describes who can access which resources. Keep bucket access limited to the collector's writer identity and the consumers you explicitly authorize.

## Supply secrets without putting them in Terraform state

Create and populate the 1Password credential secret using your existing secret-management process, outside these examples. Terraform takes only its identifier and a pinned version identifier:

- Cloud Run references an existing Secret Manager secret and numeric version. The runtime service account receives access to that secret.
- ECS references an existing Secrets Manager secret ARN and version ID. The task execution role retrieves it for environment injection. If that secret uses a customer-managed KMS key, supply the key ARN so the example can grant decryption.
- Kubernetes references an existing Secret. Create it through your approved secret delivery mechanism; no token value appears in the checked-in manifest.

No example reads a secret payload through a Terraform data source or accepts a token as a Terraform variable. Runtime environment injection still makes the credential available to the collector process and to sufficiently privileged runtime administrators. Keep that runtime inside your trust boundary.

## Select the image and destination

Build the image from the reviewed source, publish it to a registry available to your runtime, and use a full `@sha256:` digest. The examples require an explicit image input; no official published release is assumed. The Cloud Run and ECS examples expect an image that supports Linux AMD64. If building on another architecture, use your build system's Linux AMD64 target.

The collector uploads only when `--output` names an `s3://` or `gs://` destination. A local filename writes a local file. There is no default SubImage endpoint or hidden upload. The image includes both AWS and Google Cloud dependencies; local Python installs can select the `aws` or `gcp` extra.

Cloud jobs use their runtime identity to write the configured object. The Terraform examples provision private, encrypted buckets and scope the writer to the snapshot object. They do not grant a downstream reader, configure a SubImage integration, or deploy a Cartography importer. Configure your chosen consumer separately when a compatible importer is available.

## Scheduling and failure behavior

Each invocation collects one complete snapshot and then exits. Collection failures return a nonzero exit status and leave the previous output untouched. Successful publication replaces the fixed output key atomically. The output records collection time, so consumers can distinguish an old successful snapshot from a recent run.

The examples run daily in UTC and avoid automatic job retries. Kubernetes also forbids concurrent runs of its CronJob. Cloud Scheduler and EventBridge Scheduler acknowledge job launch rather than the collector's eventual success; monitor Cloud Run executions or ECS task exits and output freshness separately. Those cloud examples do not lock across invocations. Keep their interval longer than the expected collection time and avoid overlapping manual runs.

Terraform validation checks configuration and provider schemas. It does not prove live 1Password permissions, image availability, network routing, or successful cloud deployment. The examples use no stored AWS/GCP keys; apply them using your approved CLI authentication and grant runtime workload identity as described in each example.

## Examples

- [Cloud Run Job, Cloud Scheduler, and GCS](../examples/cloud-run/README.md)
- [ECS Fargate, EventBridge Scheduler, and S3](../examples/ecs/README.md)
- [Kubernetes CronJob and S3](../examples/kubernetes/README.md)
