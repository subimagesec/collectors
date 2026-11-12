output "cluster_arn" {
  description = "ECS cluster for task execution and monitoring."
  value       = aws_ecs_cluster.collector.arn
}

output "task_definition_arn" {
  description = "Pinned task definition revision launched by the schedule."
  value       = aws_ecs_task_definition.collector.arn
}

output "output_uri" {
  description = "Destination of successful snapshots; no consumer access is provisioned."
  value       = "s3://${aws_s3_bucket.snapshots.id}/${var.output_object}"
}

output "log_group" {
  description = "CloudWatch log group for collector exit and failure diagnostics."
  value       = aws_cloudwatch_log_group.collector.name
}
