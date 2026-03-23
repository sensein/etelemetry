# Research: AWS Least-Privilege Idempotent Deployment

**Date**: 2026-03-22
**Branch**: `002-aws-least-privilege-deploy`

## 1. Infrastructure-as-Code Tool

**Decision**: OpenTofu (Terraform-compatible, open-source)
**Rationale**: Idempotent by design (`tofu apply` converges to declared
state). S3 + DynamoDB state backend with locking. HCL is concise for this
scale (~150 lines). Good GitHub Actions integration
(`opentofu/setup-opentofu`). Open-source (MPL 2.0) vs Terraform's BSL.
**Alternatives considered**:
- Terraform: Functionally identical but BSL-licensed.
- CloudFormation: No state file but more verbose, slower iteration.
- AWS CDK: Overkill for single EC2 + supporting resources.
- Plain AWS CLI: Not idempotent without significant manual effort.

## 2. Compute Approach

**Decision**: EC2 (t3.small) + Docker Compose, managed via SSM (no SSH)
**Rationale**: Docker Compose works as-is. Persistent PostgreSQL via EBS
volume. Cost: ~$15-20/month vs $100-170/month for Fargate + RDS. SSM
Session Manager replaces SSH entirely — no keys, no port 22. Deploy
commands run via `aws ssm send-command`.
**Alternatives considered**:
- ECS Fargate: 6-8x cost, requires RDS for PostgreSQL, Docker Compose
  must be translated to task definitions.
- App Runner: Cannot run PostgreSQL or multi-container compositions.
- Lightsail: No volume persistence for PostgreSQL.

## 3. GitHub OIDC → AWS IAM

**Decision**: OIDC federation with branch-scoped trust policy
**Rationale**: No long-lived access keys. Trust policy scoped to
`repo:sensein/etelemetry:ref:refs/heads/main`. Uses
`aws-actions/configure-aws-credentials@v4` action.

**IAM permissions for deploy role (14 permissions)**:
- `ssm:SendCommand`, `ssm:GetCommandInvocation` — deploy via SSM
- `ssm:GetParameter`, `ssm:PutParameter` — read/write deploy state
- `ec2:DescribeInstances`, `ec2:DescribeInstanceStatus` — find target
- `ecr:GetAuthorizationToken` — authenticate to ECR
- `ecr:BatchCheckLayerAvailability`, `ecr:PutImage`,
  `ecr:InitiateLayerUpload`, `ecr:UploadLayerPart`,
  `ecr:CompleteLayerUpload` — push images
- `ecr:BatchGetImage`, `ecr:GetDownloadUrlForLayer` — pull images

All permissions scoped to specific resource ARNs.

## 4. Secret Management

**Decision**: AWS SSM Parameter Store (SecureString)
**Rationale**: Free for standard parameters. KMS-encrypted. Sufficient
for ~5 static secrets. Secrets stay in AWS (never transit through GitHub
runners). Audit trail via CloudTrail.
**Alternatives considered**:
- Secrets Manager: Better for auto-rotation; unnecessary here ($2/month).
- GitHub Secrets → .env: Secrets transit through runners; no audit trail.

## 5. TLS/Certificate Management

**Decision**: Caddy as reverse proxy (replaces nginx)
**Rationale**: Automatic HTTPS with zero config — obtains and renews
Let's Encrypt certificates given a domain name. No certbot, no cron, no
certificate file management. Drop-in replacement for the existing nginx
proxy. ~10 lines of Caddyfile vs 37 lines of nginx.conf.
**Alternatives considered**:
- ACM + ALB: Adds $16-22/month for the ALB. Unnecessary for single EC2.
- nginx + certbot: Works but adds operational complexity (sidecar
  container, shared volumes, renewal coordination).

## 6. Zero-Downtime Deployment

**Decision**: docker-rollout with health checks
**Rationale**: Docker CLI plugin for zero-downtime Docker Compose deploys.
Starts new container alongside old, waits for health check, routes traffic,
stops old container. Automatic rollback if health check fails.
**Alternatives considered**:
- Simple `docker compose up -d`: 5-30s downtime per deploy.
- Blue-green with profiles: More complex for no benefit at this scale.

## Cost Summary

| Component | Monthly Cost |
|-----------|-------------|
| EC2 t3.small (on-demand) | ~$15 |
| EBS 20GB gp3 | ~$1.60 |
| Elastic IP | $0 (while running) |
| SSM Parameter Store | $0 |
| ECR storage (~2GB) | ~$0.20 |
| Data transfer | ~$1-3 |
| **Total** | **~$18-20/month** |
