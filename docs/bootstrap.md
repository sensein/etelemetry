# Infrastructure Bootstrap Guide

One-time setup to create all AWS resources for etelemetry. After bootstrap,
all deployments are automated via GitHub Actions.

## Prerequisites

- AWS account with an IAM user that has permissions to create IAM roles,
  EC2 instances, ECR repositories, S3 buckets, DynamoDB tables, and SSM
  parameters
- [OpenTofu](https://opentofu.org/docs/intro/install/) installed (v1.6+)
- AWS CLI configured (`aws configure`)
- Git access to `sensein/etelemetry`

## Step 1: Create State Backend

The S3 bucket and DynamoDB table for OpenTofu state must exist before
`tofu init`. Create them manually (one-time):

```bash
AWS_REGION=us-east-1

# Create S3 bucket for state
aws s3api create-bucket \
  --bucket etelemetry-tfstate \
  --region $AWS_REGION

aws s3api put-bucket-versioning \
  --bucket etelemetry-tfstate \
  --versioning-configuration Status=Enabled

aws s3api put-bucket-encryption \
  --bucket etelemetry-tfstate \
  --server-side-encryption-configuration \
  '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'

aws s3api put-public-access-block \
  --bucket etelemetry-tfstate \
  --public-access-block-configuration \
  'BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true'

# Create DynamoDB table for state locking
aws dynamodb create-table \
  --table-name etelemetry-tflock \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region $AWS_REGION
```

## Step 2: Initialize and Apply

```bash
cd infra/

# Initialize OpenTofu with S3 backend
make init

# Review what will be created
make plan

# Apply — creates: EC2, security groups, IAM roles (OIDC + deploy +
# instance), ECR repository, SSM parameters, Elastic IP
make apply
```

Note the outputs:

```bash
tofu output
# deploy_role_arn     = "arn:aws:iam::123456789012:role/etelemetry-deploy"
# ecr_repository_url  = "123456789012.dkr.ecr.us-east-1.amazonaws.com/etelemetry"
# elastic_ip          = "52.x.x.x"
# instance_id         = "i-0abcdef1234567890"
# ssm_parameter_prefix = "/etelemetry"
```

## Step 3: Configure DNS

**IMPORTANT**: DNS MUST be configured BEFORE the first deployment with TLS.
Caddy needs the domain to resolve to the server IP for the ACME challenge.

Create a DNS A record:

| Type | Name | Value | TTL |
|------|------|-------|-----|
| A | `et` | `<elastic_ip from output>` | 300 |

in the DNS zone for `dandiproject.org`.

## Step 4: Store Secrets

Replace the placeholder values in SSM Parameter Store:

```bash
aws ssm put-parameter \
  --name /etelemetry/POSTGRES_PASSWORD \
  --value "$(openssl rand -base64 32)" \
  --type SecureString \
  --overwrite

aws ssm put-parameter \
  --name /etelemetry/MAXMIND_ACCOUNT_ID \
  --value "YOUR_MAXMIND_ACCOUNT_ID" \
  --type SecureString \
  --overwrite

aws ssm put-parameter \
  --name /etelemetry/MAXMIND_LICENSE_KEY \
  --value "YOUR_MAXMIND_LICENSE_KEY" \
  --type SecureString \
  --overwrite

# Optional: higher GitHub API rate limit
aws ssm put-parameter \
  --name /etelemetry/GITHUB_TOKEN \
  --value "ghp_YOUR_TOKEN" \
  --type SecureString \
  --overwrite
```

### Rotating Secrets

To rotate a secret, update it in SSM and re-run the deploy workflow:

```bash
aws ssm put-parameter \
  --name /etelemetry/POSTGRES_PASSWORD \
  --value "NEW_STRONG_PASSWORD" \
  --type SecureString \
  --overwrite

# Then trigger a deploy (push to main, or manually trigger workflow)
```

The deploy script fetches fresh secrets from SSM on every run.

## Step 5: Configure GitHub Repository

Go to the GitHub repo **Settings → Secrets and variables → Actions**:

**Variables** (not secrets — these are not sensitive):

| Variable | Value |
|----------|-------|
| `AWS_DEPLOY_ROLE_ARN` | `arn:aws:iam::ACCOUNT_ID:role/etelemetry-deploy` (from `tofu output`) |
| `AWS_REGION` | `us-east-1` |

**Environment**: Create a `production` environment (Settings → Environments)
with optional deployment protection rules.

No AWS access keys are needed — the workflow uses OIDC.

## Step 6: First Deployment

Push to `main` or manually trigger the deploy workflow. It will:
1. Authenticate to AWS via OIDC (assume `etelemetry-deploy` role)
2. Build Docker image and push to ECR
3. Run `deploy.sh` on EC2 via SSM (pull image, write .env, docker rollout)
4. Health-check the deployment
5. Report success/failure

## Step 7: Verify

```bash
curl https://et.dandiproject.org/
# {"name": "etelemetry", "version": "..."}

curl https://et.dandiproject.org/projects/nipy/nipype
# {"version": "...", "bad_versions": [...]}
```

## Teardown

To destroy all infrastructure (irreversible):

```bash
cd infra/
make destroy
# Type 'yes' when prompted
```

Then manually delete the state backend:

```bash
aws s3 rb s3://etelemetry-tfstate --force
aws dynamodb delete-table --table-name etelemetry-tflock
```
