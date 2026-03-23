# Latest Amazon Linux 2023 AMI
data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["amzn2023-ami-kernel-*"]
  }

  filter {
    name   = "architecture"
    values = ["x86_64"]
  }

  filter {
    name   = "root-device-type"
    values = ["ebs"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# Security group
resource "aws_security_group" "etelemetry" {
  name        = var.project_name
  description = "Security group for etelemetry server"

  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "All outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name    = var.project_name
    Project = var.project_name
  }
}

# EC2 instance
resource "aws_instance" "etelemetry" {
  ami                  = data.aws_ami.al2023.id
  instance_type        = var.instance_type
  iam_instance_profile = aws_iam_instance_profile.etelemetry.name
  user_data            = file("scripts/user-data.sh")

  vpc_security_group_ids = [aws_security_group.etelemetry.id]

  root_block_device {
    volume_size = var.ebs_volume_size
    volume_type = "gp3"
  }

  tags = {
    Name    = var.project_name
    Project = var.project_name
  }
}

# Elastic IP
resource "aws_eip" "etelemetry" {
  domain = "vpc"

  tags = {
    Name    = var.project_name
    Project = var.project_name
  }
}

resource "aws_eip_association" "etelemetry" {
  instance_id   = aws_instance.etelemetry.id
  allocation_id = aws_eip.etelemetry.id
}
