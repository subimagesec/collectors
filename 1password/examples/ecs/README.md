# Scheduled collector on ECS Fargate

This Terraform root creates a one-shot Fargate task, a daily EventBridge Scheduler trigger, a private S3 bucket, runtime/execution/scheduler IAM roles, and a CloudWatch log group. It uses your existing VPC/subnets and references an existing Secrets Manager secret version.

Use a 1Password service account with **Read Items** access to the intended vaults. Validate a complete local snapshot with the exact token and image before scheduling this example. Read the [authentication requirements](../../docs/authentication.md) before provisioning.

## Prerequisites

- Terraform 1.5+ and approved AWS CLI credentials for resource/IAM creation. No stored cloud key is passed to the job.
- Existing subnets in one VPC with IPv4 HTTPS egress to 1Password, the image registry, Secrets Manager, S3, and CloudWatch Logs. Private subnets need NAT for public endpoints; alternatively use public subnets and set `assign_public_ip = true`. This example provisions no routes or NAT gateway and exposes no inbound port.
- An existing Secrets Manager secret in the deployment account/region. Its selected version must contain the raw token string, not a JSON wrapper. For example:

  ```sh
  op service-account create "Subimage collector" \
    --vault <vault-id>:read_items --vault <another-vault-id>:read_items --raw \
    | tr -d '\n' \
    | aws secretsmanager create-secret --name onepassword-collector-token \
        --secret-string file:///dev/stdin
  ```

- The collector image, pinned by digest. ECS pulls the public `ghcr.io/subimagesec/collectors/1password` release directly over the task's HTTPS egress, or you can mirror it to a same-account ECR repository.
- Your expected account UUID, explicit vault UUIDs, and a globally unique bucket name.

## Deploy

Run from `1password/examples/ecs/` in the checkout:

```sh
cp terraform.tfvars.example terraform.tfvars
# Replace all synthetic IDs, network settings, image digest, and secret references.
terraform init
terraform validate
terraform plan -out=collector.tfplan
terraform apply collector.tfplan
```

`op_secret_arn` and `op_secret_version_id` are references only. The ECS execution role retrieves that version and injects it as `OP_SERVICE_ACCOUNT_TOKEN`. Terraform never reads the payload. For a customer-managed KMS key, supply `op_secret_kms_key_arn` and ensure its key policy permits the execution role. Update the version ID and apply after rotating the token externally.

The task role can only `s3:PutObject` at the configured snapshot key. The execution role pulls the image, delivers logs, and retrieves the one configured secret. The scheduler can launch only this task definition in this cluster and pass only its two roles. The bucket blocks public access, disables ACLs, uses SSE-S3 encryption, and rejects non-TLS requests. No reader is granted access by this example.

The scheduler execution role's `aws:SourceArn` condition uses the schedule-group ARN, as required by [AWS's confused-deputy guidance](https://docs.aws.amazon.com/scheduler/latest/UserGuide/cross-service-confused-deputy-prevention.html).

## Run and verify

Use the ECS console's **Run task** action with the generated cluster/task definition and the same subnet/security-group settings as the schedule. A scheduled launch can also be observed in the ECS console. Confirm the container exits with code zero, inspect its CloudWatch log stream, and verify the object with a separately authorized S3 reader.

Check the snapshot's `collected_at` and configured vault scope. A successful EventBridge delivery means that ECS accepted the task, not that 1Password collection succeeded. Monitor stopped task exit codes and snapshot freshness separately.

The default schedule is daily at 02:00 UTC. Automatic scheduler retries are disabled, and tasks exit after a collection. There is no cross-execution lock or ECS execution timeout in this example; use a schedule longer than the maximum observed runtime and avoid overlapping manual launches.

## Use with Subimage

Set `subimage_tenant_role_arn` and `subimage_external_id` to the values on Subimage's 1Password setup page. The example then creates `SubImageOnePasswordRole`, which trusts only that role with that external ID and can only list and read the snapshot prefix. After you apply, enter these outputs in Subimage's 1Password module:

| Output | Subimage field |
| --- | --- |
| `subimage_onepassword_source` | `onepassword_source` |
| `subimage_onepassword_aws_account_id` | `onepassword_aws_account_id` |

For another consumer, give its IAM role `s3:ListBucket` on the bucket and `s3:GetObject` on the snapshot key. A role in this account needs only its own IAM policy; a role in another account also needs a bucket policy grant.

## Configuration validation

```sh
terraform fmt -check
terraform init -backend=false -input=false
terraform validate
```

References: [EventBridge Scheduler with ECS](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/tasks-scheduled-eventbridge-scheduler.html), [Secrets Manager injection](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/secrets-envvar-secrets-manager.html), [task IAM roles](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-iam-roles.html).
