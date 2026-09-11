# Scheduled collector on Cloud Run

This Terraform root creates a Cloud Run v2 Job, a daily Cloud Scheduler trigger, a private GCS bucket, and separate runtime/scheduler service accounts. It references an existing Secret Manager secret version. It does not create or read the token payload.

**First validate the exact unattended credential.** Generic 1Password service-account-token support has not been established, and the collector requires user/group enumeration and vault grants in addition to item access. Read [authentication requirements](../../docs/deployment.md) before provisioning this example.

## Prerequisites

- Terraform 1.5+ and approved Google Cloud application-default credentials for deployment.
- An existing project and permission to enable the listed APIs, create resources/service accounts, and grant their IAM access.
- An existing Secret Manager secret in that project, with a numeric version containing a token already validated against the collector.
- A published Linux AMD64 collector image available to Cloud Run, preferably in Artifact Registry in the same project. Cloud Run must have permission to pull it. Use the full immutable image digest; the placeholder is not a released image.
- Your expected account UUID, explicit vault UUIDs, and a globally unique bucket name.

## Deploy

```sh
cp terraform.tfvars.example terraform.tfvars
# Replace the synthetic IDs, image digest, secret reference, and bucket name.
terraform init
terraform validate
terraform plan -out=collector.tfplan
terraform apply collector.tfplan
```

Do not put a token value in `terraform.tfvars`. `op_secret_id` and `op_secret_version` identify the secret that Cloud Run injects into `OP_SERVICE_ACCOUNT_TOKEN` at runtime. After rotating the secret externally, update the pinned version and apply the configuration again.

The runtime identity has Secret Manager accessor access to the configured secret and object-user access restricted to the exact snapshot object. GCS encrypts objects at rest by default; public access prevention and uniform bucket access are enabled. The scheduler identity can invoke only this job. Image-pull permissions are separate from runtime permissions, especially for images in another project.

## Run and verify

Execute the job from the Cloud Run console or with your authenticated `gcloud` CLI:

```sh
gcloud run jobs execute onepassword-collector \
  --project example-security-project \
  --region us-central1 \
  --wait
```

Use your configured name/project/region if changed. Confirm the execution succeeded and inspect the configured GCS object using a separately authorized reader identity. Its `collected_at` should reflect the completed run. Monitor job failures and snapshot freshness: a successful scheduler request proves launch, not collection success.

The default schedule is daily at 02:00 UTC, with a 30-minute execution timeout and no retries. Choose a schedule longer than collection time and avoid overlapping manual invocations. No downstream reader or Cartography importer is configured.

## Configuration validation

```sh
terraform fmt -check
terraform init -backend=false -input=false
terraform validate
```

References: [Cloud Run scheduled jobs](https://cloud.google.com/run/docs/execute/jobs-on-schedule), [Cloud Run secrets](https://cloud.google.com/run/docs/configuring/jobs/secrets), [Cloud Storage encryption](https://cloud.google.com/storage/docs/encryption/default-keys).
