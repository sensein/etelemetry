output "deploy_role_arn" {
  description = "ARN of the GitHub Actions deploy role"
  value       = aws_iam_role.deploy.arn
}

output "instance_id" {
  description = "EC2 instance ID"
  value       = aws_instance.etelemetry.id
}

output "ecr_repository_url" {
  description = "ECR repository URL"
  value       = aws_ecr_repository.etelemetry.repository_url
}

output "elastic_ip" {
  description = "Elastic IP address"
  value       = aws_eip.etelemetry.public_ip
}

output "ssm_parameter_prefix" {
  description = "SSM Parameter Store prefix"
  value       = "/etelemetry"
}
