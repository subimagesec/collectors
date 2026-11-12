output "job_name" {
  description = "Cloud Run job name for execution and monitoring."
  value       = google_cloud_run_v2_job.collector.name
}

output "output_uri" {
  description = "Destination of successful snapshots."
  value       = "gs://${google_storage_bucket.snapshots.name}/${var.output_object}"
}

output "runtime_service_account" {
  description = "Identity used to retrieve the token and write the snapshot."
  value       = google_service_account.runtime.email
}

output "subimage_onepassword_source" {
  description = "Value for onepassword_source in Subimage. Grant Subimage's GCP principal read access with snapshot_readers."
  value       = "gs://${google_storage_bucket.snapshots.name}/${dirname(var.output_object) == "." ? "" : "${dirname(var.output_object)}/"}"
}
