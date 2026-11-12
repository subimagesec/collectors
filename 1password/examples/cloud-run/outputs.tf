output "job_name" {
  description = "Cloud Run job name for execution and monitoring."
  value       = google_cloud_run_v2_job.collector.name
}

output "output_uri" {
  description = "Destination of successful snapshots; no consumer access is provisioned."
  value       = "gs://${google_storage_bucket.snapshots.name}/${var.output_object}"
}

output "runtime_service_account" {
  description = "Identity used to retrieve the token and write the snapshot."
  value       = google_service_account.runtime.email
}
