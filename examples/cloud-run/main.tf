locals {
  collector_args = concat(
    ["onepassword", "--account-id", var.account_id],
    flatten([for id in var.vault_ids : ["--vault-id", id]]),
    ["--output", "gs://${var.bucket_name}/${var.output_object}"],
    var.include_titles ? ["--include-titles"] : [],
  )
}

resource "google_project_service" "required" {
  for_each = toset([
    "cloudscheduler.googleapis.com",
    "iam.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "storage.googleapis.com",
  ])

  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

resource "google_service_account" "runtime" {
  project      = var.project_id
  account_id   = "${var.name}-run"
  display_name = "1Password collector runtime"
  depends_on   = [google_project_service.required]
}

resource "google_service_account" "scheduler" {
  project      = var.project_id
  account_id   = "${var.name}-cron"
  display_name = "1Password collector scheduler"
  depends_on   = [google_project_service.required]
}

resource "google_storage_bucket" "snapshots" {
  project                     = var.project_id
  name                        = var.bucket_name
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  depends_on                  = [google_project_service.required]
}

resource "google_storage_bucket_iam_member" "snapshot_writer" {
  bucket = google_storage_bucket.snapshots.name
  role   = "roles/storage.objectUser"
  member = "serviceAccount:${google_service_account.runtime.email}"

  condition {
    title       = "collector-snapshot-only"
    description = "The collector may replace only its configured snapshot object."
    expression  = "resource.name == 'projects/_/buckets/${google_storage_bucket.snapshots.name}/objects/${var.output_object}'"
  }
}

resource "google_secret_manager_secret_iam_member" "token_reader" {
  project   = var.project_id
  secret_id = var.op_secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.runtime.email}"
}

resource "google_cloud_run_v2_job" "collector" {
  project             = var.project_id
  name                = var.name
  location            = var.region
  deletion_protection = false

  template {
    task_count  = 1
    parallelism = 1

    template {
      service_account = google_service_account.runtime.email
      timeout         = "1800s"
      max_retries     = 0

      containers {
        image = var.collector_image
        args  = local.collector_args

        resources {
          limits = {
            cpu    = "1"
            memory = "512Mi"
          }
        }

        env {
          name = "OP_SERVICE_ACCOUNT_TOKEN"

          value_source {
            secret_key_ref {
              secret  = var.op_secret_id
              version = var.op_secret_version
            }
          }
        }
      }
    }
  }

  depends_on = [
    google_secret_manager_secret_iam_member.token_reader,
    google_storage_bucket_iam_member.snapshot_writer,
  ]
}

resource "google_cloud_run_v2_job_iam_member" "scheduler_invoker" {
  project  = var.project_id
  location = google_cloud_run_v2_job.collector.location
  name     = google_cloud_run_v2_job.collector.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.scheduler.email}"
}

resource "google_cloud_scheduler_job" "collector" {
  project          = var.project_id
  name             = var.name
  region           = var.region
  schedule         = var.schedule
  time_zone        = "Etc/UTC"
  attempt_deadline = "180s"

  retry_config {
    retry_count = 0
  }

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.project_id}/locations/${var.region}/jobs/${google_cloud_run_v2_job.collector.name}:run"

    oauth_token {
      service_account_email = google_service_account.scheduler.email
      scope                 = "https://www.googleapis.com/auth/cloud-platform"
    }
  }

  depends_on = [google_cloud_run_v2_job_iam_member.scheduler_invoker]
}
