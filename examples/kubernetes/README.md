# Kubernetes CronJob writing to S3

The manifest runs one collection daily at 02:00 UTC and writes a fixed S3 object. It includes a namespace, service account, and CronJob. Kubernetes 1.27+ is required for the `timeZone` field.

**Validate the exact unattended 1Password credential first.** A generic service account token is not established as compatible. The collector requires account/user/group discovery, membership and vault grants, and item listing; a token that can only read items will fail. See [authentication requirements](../../docs/deployment.md).

## Configure before applying

1. Build and publish the collector image, then replace the placeholder with its full immutable digest. No official release is assumed. Match the image architecture to the cluster nodes.
2. Replace the synthetic account and vault UUIDs. Add repeated `--vault-id` pairs for additional vaults. Replace the S3 bucket/key and set both `AWS_REGION` and `AWS_DEFAULT_REGION` to the bucket's region.
3. Provision a private S3 bucket and a workload IAM role outside this manifest. The role needs `s3:PutObject` on exactly `arn:aws:s3:::<bucket>/onepassword/snapshot.json`. If the bucket uses a customer-managed KMS key, configure the required KMS permissions/key policy separately.
4. Set up workload identity. The example service-account annotation uses [EKS IAM roles for service accounts](https://docs.aws.amazon.com/eks/latest/userguide/iam-roles-for-service-accounts.html). Configure your cluster's OIDC provider and an IAM trust policy for the exact subject (`system:serviceaccount:subimage-collectors:onepassword-collector`) and audience (`sts.amazonaws.com`), and replace the role ARN. Other clusters need an equivalent supported AWS web-identity setup; the annotation alone does not create credentials or trust. Do not add static AWS access keys.
5. Create the namespace and deliver a Secret named `onepassword-collector-token` with a `token` key into it, using your existing external secret-management process. The Secret must contain the already-validated unattended credential. Its payload is deliberately absent from this repository. Limit who can read it or create workloads in this namespace.
6. Ensure the pod can resolve DNS and reach 1Password, AWS STS, and S3 over HTTPS. Ensure nodes can pull the image; configure registry authentication separately if needed.

Review the manifest after replacing placeholders:

```sh
kubectl apply --dry-run=server -f cronjob.yaml
kubectl apply -f cronjob.yaml
```

The manifest uses a nonroot process, a read-only container filesystem, dropped capabilities, and a memory-backed `/tmp` volume for CLI runtime files. It grants no Kubernetes API permissions. The environment token remains accessible to the process and privileged cluster administrators.

## Run and verify

```sh
kubectl create job --from=cronjob/onepassword-collector \
  onepassword-collector-manual -n subimage-collectors
kubectl logs -f job/onepassword-collector-manual -n subimage-collectors
kubectl get job onepassword-collector-manual -n subimage-collectors
```

Choose a new manual job name for later runs and avoid starting it during a scheduled execution. Confirm the Job completed and use a separately authorized S3 reader to inspect snapshot `collected_at` and vault scope. Manual Jobs are not protected by the CronJob's `Forbid` concurrency policy.

The CronJob forbids overlapping scheduled runs, disables retries, and terminates executions after 30 minutes. Collection failures leave the prior snapshot untouched. Monitor failed Jobs and object freshness. No downstream reader or Cartography importer is configured by this example.
