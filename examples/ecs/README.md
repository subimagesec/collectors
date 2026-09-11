# Scheduled collector on ECS Fargate

This Terraform root creates a one-shot Fargate task, a daily EventBridge Scheduler trigger, a private S3 bucket, runtime/execution/scheduler IAM roles, and a CloudWatch log group. It uses your existing VPC/subnets and references an existing Secrets Manager secret version.

**First validate the exact unattended credential.** Generic 1Password service-account-token support has not been established, and item-read permission alone is insufficient. User/group enumeration, memberships, and vault grants must work too. Read [authentication requirements](../../docs/deployment.md) before provisioning.

## Prerequisites

- Terraform 1.5+ and approved AWS CLI credentials for resource/IAM creation. No stored cloud key is passed to the job.
- Existing subnets in one VPC with IPv4 HTTPS egress to 1Password, the image registry, Secrets Manager, S3, and CloudWatch Logs. Private subnets need NAT for public endpoints; alternatively use public subnets and set `assign_public_ip = true`. This example provisions no routes or NAT gateway and exposes no inbound port.
- An existing Secrets Manager secret in the deployment account/region. Its selected version must contain the raw token string, not a JSON wrapper. Populate it through your existing secret-management workflow.
- A Linux AMD64 collector image accessible to ECS. A same-account ECR repository works with the provided task execution policy. Cross-account/private registries need their own pull authorization. Use an immutable image digest; placeholders are not released images.
- Your expected account UUID, explicit vault UUIDs, and a globally unique bucket name.

## Deploy

```sh
cp terraform.tfvars.example terraform.tfvars
# Replace all synthetic IDs, network settings, image digest, and secret references.
terraform init
terraform validate
terraform plan -out=collector.tfplan
terraform apply collector.tfplan
```

`op_secret_arn` and `op_secret_version_id` are references only. The ECS execution role retrieves that version and injects it as `OP_SERVICE_ACCOUNT_TOKEN`. Terraform never reads the payload. For a customer-managed KMS key, supply `op_secret_kms_key_arn` and ensure its key policy permits the execution role. Update the version ID and apply after rotating the token externally.

The task role can only `s3:PutObject` at the configured snapshot key. The execution role pulls the image, delivers logs, and retrieves the one configured secret. The scheduler can launch only this task definition in this cluster and pass only its two roles. The bucket blocks public access, disables ACLs, uses SSE-S3 encryption, and rejects non-TLS requests. No downstream reader is granted access.

## Run and verify

Use the ECS console's **Run task** action with the generated cluster/task definition and the same subnet/security-group settings as the schedule. A scheduled launch can also be observed in the ECS console. Confirm the container exits with code zero, inspect its CloudWatch log stream, and verify the object with a separately authorized S3 reader.

Check the snapshot's `collected_at` and configured vault scope. A successful EventBridge delivery means that ECS accepted the task, not that 1Password collection succeeded. Monitor stopped task exit codes and snapshot freshness separately.

The default schedule is daily at 02:00 UTC. Automatic scheduler retries are disabled, and tasks exit after a collection. There is no cross-execution lock or ECS execution timeout in this example; use a schedule longer than the maximum observed runtime and avoid overlapping manual launches. No downstream Cartography importer is configured.

## Configuration validation

```sh
terraform fmt -check
terraform init -backend=false -input=false
terraform validate
```

References: [EventBridge Scheduler with ECS](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/tasks-scheduled-eventbridge-scheduler.html), [Secrets Manager injection](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/secrets-envvar-secrets-manager.html), [task IAM roles](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-iam-roles.html).
