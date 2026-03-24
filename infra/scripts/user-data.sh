#!/bin/bash
set -euo pipefail

# Install Docker
dnf install -y docker
systemctl enable docker
systemctl start docker
usermod -aG docker ec2-user

# Install Docker Compose plugin
mkdir -p /usr/local/lib/docker/cli-plugins
curl -SL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-$(uname -m)" \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

# Install docker-rollout
curl -SL "https://raw.githubusercontent.com/wowu/docker-rollout/main/docker-rollout" \
  -o /usr/local/lib/docker/cli-plugins/docker-rollout
chmod +x /usr/local/lib/docker/cli-plugins/docker-rollout

# Install AWS CLI (for ECR auth and SSM parameter fetch)
dnf install -y aws-cli

# Clone etelemetry repo
git clone https://github.com/sensein/etelemetry.git /opt/etelemetry
chown -R ec2-user:ec2-user /opt/etelemetry

# Create data directories
mkdir -p /opt/etelemetry/caddy_data
