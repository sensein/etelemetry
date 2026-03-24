#!/bin/bash
set -euo pipefail

IMAGE_TAG="${1:-latest}"
ECR_REPO="${2}"
REGION="${3:-us-east-1}"

# Authenticate to ECR
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$ECR_REPO"

# Pull new image
docker pull "${ECR_REPO}:${IMAGE_TAG}"
docker tag "${ECR_REPO}:${IMAGE_TAG}" etelemetry-server:latest

# Fetch secrets from SSM and write .env
cd /opt/etelemetry/deploy

# Get all parameters under /etelemetry/
aws ssm get-parameters-by-path \
  --path /etelemetry/ \
  --with-decryption \
  --query 'Parameters[*].[Name,Value]' \
  --output text \
  --region "$REGION" | while IFS=$'\t' read -r name value; do
    key=$(basename "$name")
    echo "${key}=${value}"
done > .env.tmp

# Add non-secret config
echo "DATABASE_URL=postgresql+asyncpg://etelemetry:$(grep POSTGRES_PASSWORD .env.tmp | cut -d= -f2)@postgres:5432/etelemetry" >> .env.tmp
echo "MAXMIND_DB_PATH=/data/GeoLite2-City.mmdb" >> .env.tmp
echo "ALLOWLIST_PATH=/config/allowlist.yml" >> .env.tmp

mv .env.tmp .env
chmod 600 .env

# Zero-downtime rollout
cd /opt/etelemetry
docker rollout server -f deploy/docker-compose.yml || {
  echo "ERROR: Rollout failed, previous version still running"
  exit 1
}

# Health check
for i in $(seq 1 30); do
  if curl -sf http://localhost:8000/ > /dev/null 2>&1; then
    echo "Health check passed"
    exit 0
  fi
  sleep 2
done

echo "ERROR: Health check failed after 60 seconds"
exit 1
