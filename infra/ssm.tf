resource "aws_ssm_parameter" "postgres_password" {
  name  = "/etelemetry/POSTGRES_PASSWORD"
  type  = "SecureString"
  value = "CHANGE_ME"

  lifecycle {
    ignore_changes = [value]
  }

  tags = {
    Project = var.project_name
  }
}

resource "aws_ssm_parameter" "maxmind_account_id" {
  name  = "/etelemetry/MAXMIND_ACCOUNT_ID"
  type  = "SecureString"
  value = "CHANGE_ME"

  lifecycle {
    ignore_changes = [value]
  }

  tags = {
    Project = var.project_name
  }
}

resource "aws_ssm_parameter" "maxmind_license_key" {
  name  = "/etelemetry/MAXMIND_LICENSE_KEY"
  type  = "SecureString"
  value = "CHANGE_ME"

  lifecycle {
    ignore_changes = [value]
  }

  tags = {
    Project = var.project_name
  }
}

resource "aws_ssm_parameter" "github_token" {
  name  = "/etelemetry/GITHUB_TOKEN"
  type  = "SecureString"
  value = ""

  lifecycle {
    ignore_changes = [value]
  }

  tags = {
    Project = var.project_name
  }
}
