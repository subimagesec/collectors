data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

locals {
  collector_args = concat(
    ["onepassword", "--account-id", var.account_id],
    flatten([for id in var.vault_ids : ["--vault-id", id]]),
    ["--output", "s3://${var.bucket_name}/${var.output_object}"],
    var.include_titles ? ["--include-titles"] : [],
  )
  task_assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
      Condition = {
        StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.current.account_id }
        ArnLike = {
          "aws:SourceArn" = "arn:${data.aws_partition.current.partition}:ecs:${var.region}:${data.aws_caller_identity.current.account_id}:*"
        }
      }
    }]
  })
}

resource "aws_s3_bucket" "snapshots" {
  bucket = var.bucket_name
}

resource "aws_s3_bucket_public_access_block" "snapshots" {
  bucket                  = aws_s3_bucket.snapshots.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "snapshots" {
  bucket = aws_s3_bucket.snapshots.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "snapshots" {
  bucket = aws_s3_bucket.snapshots.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_policy" "require_tls" {
  bucket = aws_s3_bucket.snapshots.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "RequireTLS"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource  = [aws_s3_bucket.snapshots.arn, "${aws_s3_bucket.snapshots.arn}/*"]
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }]
  })
}

resource "aws_ecs_cluster" "collector" {
  name = var.name
}

resource "aws_cloudwatch_log_group" "collector" {
  name              = "/ecs/${var.name}"
  retention_in_days = 14
}

resource "aws_security_group" "collector" {
  name        = var.name
  description = "Collector outbound HTTPS; no inbound rules"
  vpc_id      = var.vpc_id
}

resource "aws_vpc_security_group_egress_rule" "https" {
  security_group_id = aws_security_group.collector.id
  description       = "1Password, image registry, and AWS APIs"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  cidr_ipv4         = "0.0.0.0/0"
}

resource "aws_iam_role" "runtime" {
  name               = "${var.name}-runtime"
  assume_role_policy = local.task_assume_role_policy
}

resource "aws_iam_role_policy" "snapshot_writer" {
  name = "snapshot-writer"
  role = aws_iam_role.runtime.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "s3:PutObject"
      Resource = "${aws_s3_bucket.snapshots.arn}/${var.output_object}"
    }]
  })
}

resource "aws_iam_role" "execution" {
  name               = "${var.name}-execution"
  assume_role_policy = local.task_assume_role_policy
}

resource "aws_iam_role_policy_attachment" "execution" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "token_reader" {
  name = "token-reader"
  role = aws_iam_role.execution.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat(
      [{
        Effect   = "Allow"
        Action   = "secretsmanager:GetSecretValue"
        Resource = var.op_secret_arn
      }],
      var.op_secret_kms_key_arn == null ? [] : [{
        Effect   = "Allow"
        Action   = "kms:Decrypt"
        Resource = var.op_secret_kms_key_arn
        Condition = {
          StringEquals = {
            "kms:ViaService" = "secretsmanager.${var.region}.${data.aws_partition.current.dns_suffix}"
          }
        }
      }],
    )
  })
}

resource "aws_ecs_task_definition" "collector" {
  family                   = var.name
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.runtime.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([{
    name      = "collector"
    image     = var.collector_image
    essential = true
    command   = local.collector_args
    user      = "10001:10001"
    environment = [
      { name = "AWS_REGION", value = var.region },
      { name = "AWS_DEFAULT_REGION", value = var.region },
      { name = "OP_CONFIG_DIR", value = "/tmp/op" },
    ]
    secrets = [{
      name      = "OP_SERVICE_ACCOUNT_TOKEN"
      valueFrom = "${var.op_secret_arn}:::${var.op_secret_version_id}"
    }]
    linuxParameters = { capabilities = { drop = ["ALL"] } }
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.collector.name
        awslogs-region        = var.region
        awslogs-stream-prefix = "collector"
      }
    }
  }])
}

resource "aws_scheduler_schedule_group" "collector" {
  name = var.name
}

resource "aws_iam_role" "scheduler" {
  name = "${var.name}-scheduler"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "scheduler.amazonaws.com" }
      Action    = "sts:AssumeRole"
      Condition = {
        StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.current.account_id }
        ArnEquals    = { "aws:SourceArn" = aws_scheduler_schedule_group.collector.arn }
      }
    }]
  })
}

resource "aws_iam_role_policy" "scheduler" {
  name = "run-collector"
  role = aws_iam_role.scheduler.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "ecs:RunTask"
        Resource = aws_ecs_task_definition.collector.arn
        Condition = {
          ArnEquals = { "ecs:cluster" = aws_ecs_cluster.collector.arn }
        }
      },
      {
        Effect   = "Allow"
        Action   = "iam:PassRole"
        Resource = [aws_iam_role.execution.arn, aws_iam_role.runtime.arn]
        Condition = {
          StringEquals = { "iam:PassedToService" = "ecs-tasks.amazonaws.com" }
        }
      },
    ]
  })
}

resource "aws_scheduler_schedule" "collector" {
  name                         = var.name
  group_name                   = aws_scheduler_schedule_group.collector.name
  schedule_expression          = var.schedule_expression
  schedule_expression_timezone = "UTC"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_ecs_cluster.collector.arn
    role_arn = aws_iam_role.scheduler.arn

    retry_policy {
      maximum_event_age_in_seconds = 3600
      maximum_retry_attempts       = 0
    }

    ecs_parameters {
      task_definition_arn = aws_ecs_task_definition.collector.arn
      task_count          = 1
      launch_type         = "FARGATE"
      platform_version    = "1.4.0"

      network_configuration {
        subnets          = var.subnet_ids
        security_groups  = [aws_security_group.collector.id]
        assign_public_ip = var.assign_public_ip
      }
    }
  }

  depends_on = [
    aws_iam_role_policy.scheduler,
    aws_iam_role_policy.token_reader,
    aws_iam_role_policy.snapshot_writer,
    aws_iam_role_policy_attachment.execution,
    aws_vpc_security_group_egress_rule.https,
  ]
}
