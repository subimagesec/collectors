variable "project_id" {
  type        = string
  description = "Existing Google Cloud project in which to create the collector resources."
}

variable "region" {
  type        = string
  description = "Region for the Cloud Run job, scheduler, and snapshot bucket."
  default     = "us-central1"
}

variable "name" {
  type        = string
  description = "Resource name prefix; limited to fit service account ID limits."
  default     = "onepassword-collector"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,22}[a-z0-9]$", var.name))
    error_message = "Use 3 to 24 lowercase letters, digits, or hyphens, starting with a letter and ending with a letter or digit."
  }
}

variable "collector_image" {
  type        = string
  description = "Collector image available to Cloud Run, pinned to an immutable sha256 digest."

  validation {
    condition     = can(regex("^.+@sha256:[0-9a-f]{64}$", var.collector_image))
    error_message = "Provide a full image reference ending in @sha256:<64 lowercase hex characters>."
  }
}

variable "account_id" {
  type        = string
  description = "Expected 26-character 1Password account UUID, verified at collection time."

  validation {
    condition     = can(regex("^[a-zA-Z0-9]{26}$", var.account_id))
    error_message = "Provide a 26-character alphanumeric 1Password account UUID."
  }
}

variable "vault_ids" {
  type        = list(string)
  description = "Explicit vault UUIDs to collect; this defines snapshot coverage."

  validation {
    condition = (
      length(var.vault_ids) > 0 &&
      length(distinct(var.vault_ids)) == length(var.vault_ids) &&
      alltrue([for id in var.vault_ids : can(regex("^[a-zA-Z0-9]{26}$", id))])
    )
    error_message = "Provide at least one distinct 26-character alphanumeric vault UUID."
  }
}

variable "op_secret_id" {
  type        = string
  description = "ID of an existing Secret Manager secret in this project; payload is never read by Terraform."
}

variable "op_secret_version" {
  type        = string
  description = "Existing numeric secret version containing the validated unattended 1Password token."

  validation {
    condition     = can(regex("^[1-9][0-9]*$", var.op_secret_version))
    error_message = "Pin a numeric secret version; do not use latest."
  }
}

variable "bucket_name" {
  type        = string
  description = "Globally unique name for a new private snapshot bucket."

  validation {
    condition = (
      length(var.bucket_name) >= 3 &&
      length(var.bucket_name) <= 222 &&
      can(regex("^[a-z0-9][a-z0-9._-]*[a-z0-9]$", var.bucket_name)) &&
      alltrue([for component in split(".", var.bucket_name) : length(component) <= 63])
    )
    error_message = "Use 3 to 63 lowercase letters, digits, hyphens, underscores, or dots, starting and ending with a letter or digit. Dotted names may have up to 222 characters, with each component at most 63 characters."
  }
}

variable "output_object" {
  type        = string
  description = "Object key replaced after each successful collection."
  default     = "onepassword/snapshot.json"

  validation {
    condition     = can(regex("^[A-Za-z0-9][A-Za-z0-9/_.-]*$", var.output_object))
    error_message = "Use a relative object key containing letters, digits, slashes, underscores, dots, or hyphens."
  }
}

variable "schedule" {
  type        = string
  description = "Cloud Scheduler unix-cron or groc schedule, evaluated in UTC."
  default     = "0 2 * * *"
}

variable "include_titles" {
  type        = bool
  description = "Include vault names and item titles, which can contain sensitive text."
  default     = false
}
