variable "region" {
  type        = string
  description = "AWS region for the collector resources and existing credential secret."
  default     = "us-east-1"
}

variable "name" {
  type        = string
  description = "Prefix for collector resource names."
  default     = "onepassword-collector"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,39}$", var.name))
    error_message = "Use 3 to 40 lowercase letters, digits, or hyphens, starting with a letter."
  }
}

variable "collector_image" {
  type        = string
  description = "Collector image available to ECS, pinned to an immutable sha256 digest."

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

variable "op_secret_arn" {
  type        = string
  description = "ARN of an existing Secrets Manager secret in this account and region; Terraform does not read its payload."

  validation {
    condition     = can(regex("^arn:[^:]+:secretsmanager:[^:]+:[0-9]{12}:secret:.+$", var.op_secret_arn))
    error_message = "Provide the full ARN of an existing Secrets Manager secret."
  }
}

variable "op_secret_version_id" {
  type        = string
  description = "Pinned Secrets Manager version ID containing the validated unattended 1Password token."

  validation {
    condition     = can(regex("^[A-Za-z0-9-]{32,64}$", var.op_secret_version_id))
    error_message = "Provide an existing 32 to 64 character secret version ID."
  }
}

variable "op_secret_kms_key_arn" {
  type        = string
  description = "Customer-managed KMS key ARN encrypting the existing secret; null for the AWS-managed Secrets Manager key."
  default     = null

  validation {
    condition     = var.op_secret_kms_key_arn == null ? true : can(regex("^arn:[^:]+:kms:[^:]+:[0-9]{12}:key/.+$", var.op_secret_kms_key_arn))
    error_message = "Provide a KMS key ARN or leave this null for the AWS-managed key."
  }
}

variable "vpc_id" {
  type        = string
  description = "Existing VPC containing the task subnets."
}

variable "subnet_ids" {
  type        = list(string)
  description = "Existing subnets with outbound access to 1Password, the image registry, and required AWS services."

  validation {
    condition     = length(var.subnet_ids) > 0
    error_message = "Provide at least one subnet."
  }
}

variable "assign_public_ip" {
  type        = bool
  description = "Enable only for public subnets with an internet gateway; private subnets normally use NAT."
  default     = false
}

variable "bucket_name" {
  type        = string
  description = "Globally unique name for a new private snapshot bucket."
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

variable "schedule_expression" {
  type        = string
  description = "EventBridge Scheduler expression, evaluated in UTC."
  default     = "cron(0 2 * * ? *)"
}

variable "include_titles" {
  type        = bool
  description = "Include vault names and item titles, which can contain sensitive text."
  default     = false
}
