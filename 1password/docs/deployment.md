# Deployment

**Validate the exact unattended credential before deployment.** Generic 1Password service-account-token compatibility has not been established. Follow the [authentication guide](authentication.md), including its required access-metadata operations and explicit account/vault scope.

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
