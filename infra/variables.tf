variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "us-east-1"
}

variable "instance_type" {
  description = "EC2 instance type"
  type        = string
  default     = "t3.small"
}

variable "domain" {
  description = "Domain name for the etelemetry service"
  type        = string
  default     = "et.dandiproject.org"
}

variable "github_repo" {
  description = "GitHub repository for OIDC trust"
  type        = string
  default     = "sensein/etelemetry"
}

variable "project_name" {
  description = "Project name used for resource naming and tagging"
  type        = string
  default     = "etelemetry"
}

variable "ebs_volume_size" {
  description = "Size of the root EBS volume in GB"
  type        = number
  default     = 20
}
