# State backend resources (self-bootstrapping).
# On first run, use: tofu init -backend-config="path=terraform.tfstate"
# After these resources are created, migrate to S3 backend with: tofu init -migrate-state

resource "aws_s3_bucket" "tfstate" {
  bucket = "etelemetry-tfstate"

  tags = {
    Name    = "etelemetry-tfstate"
    Project = var.project_name
  }
}

resource "aws_s3_bucket_versioning" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_dynamodb_table" "tflock" {
  name         = "etelemetry-tflock"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }

  tags = {
    Name    = "etelemetry-tflock"
    Project = var.project_name
  }
}
