# Quickstart: AWS Deployment

## Prerequisites

- AWS account with an IAM user that can create resources (one-time bootstrap)
- OpenTofu installed (`brew install opentofu` or via package manager)
- AWS CLI configured (`aws configure`)
- Domain DNS access for `et.dandiproject.org`

## Bootstrap (one-time)

```bash
cd infra/

# Initialize OpenTofu with S3 backend
tofu init

# Review what will be created
tofu plan

# Apply — creates EC2, security groups, IAM roles, ECR, SSM params
tofu apply

# Note the outputs:
# - EC2 instance ID
# - ECR repository URL
# - Deploy role ARN (for GitHub Actions)
# - Elastic IP (for DNS A record)
```

## Configure DNS

Point `et.dandiproject.org` A record to the Elastic IP output from bootstrap.

## Store Secrets in SSM

```bash
aws ssm put-parameter --name /etelemetry/POSTGRES_PASSWORD \
  --value "YOUR_STRONG_PASSWORD" --type SecureString

aws ssm put-parameter --name /etelemetry/MAXMIND_ACCOUNT_ID \
  --value "YOUR_ACCOUNT_ID" --type SecureString

aws ssm put-parameter --name /etelemetry/MAXMIND_LICENSE_KEY \
  --value "YOUR_LICENSE_KEY" --type SecureString

# Optional: higher GitHub API rate limit
aws ssm put-parameter --name /etelemetry/GITHUB_TOKEN \
  --value "ghp_YOUR_TOKEN" --type SecureString
```

## Configure GitHub Repository

1. Go to Settings → Secrets and variables → Actions
2. Add variable: `AWS_DEPLOY_ROLE_ARN` = the role ARN from bootstrap output
3. Add variable: `AWS_REGION` = your chosen region (e.g., `us-east-1`)

No AWS access keys needed — the workflow uses OIDC.

## First Deployment

Push to `main` or manually trigger the deploy workflow. The workflow will:
1. Authenticate to AWS via OIDC
2. Build and push the Docker image to ECR
3. Run deploy script on EC2 via SSM (pulls image, updates .env, docker-rollout)
4. Health-check the new deployment
5. Roll back if health check fails

## Verify

```bash
curl https://et.dandiproject.org/
# → {"name": "etelemetry", "version": "2.0.0"}

curl https://et.dandiproject.org/projects/nipy/nipype
# → {"version": "...", "bad_versions": [...]}
```

## Subsequent Deployments

Merge to `main` → automatic deploy. No manual steps.
