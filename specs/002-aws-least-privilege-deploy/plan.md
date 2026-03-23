# Implementation Plan: AWS Least-Privilege Idempotent Deployment

**Branch**: `002-aws-least-privilege-deploy` | **Date**: 2026-03-22 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/002-aws-least-privilege-deploy/spec.md`

## Summary

Create an idempotent AWS deployment using OpenTofu for infrastructure,
GitHub OIDC for authentication (no long-lived keys), SSM for remote
execution (no SSH), ECR for container images, SSM Parameter Store for
secrets, Caddy for automatic TLS, and docker-rollout for zero-downtime
updates. All infrastructure is version-controlled and least-privilege.

## Technical Context

**IaC Tool**: OpenTofu (Terraform-compatible, open-source)
**Compute**: EC2 t3.small + Docker Compose, managed via SSM
**Auth**: GitHub OIDC → AWS IAM (no access keys)
**Container Registry**: ECR (private)
**Secrets**: SSM Parameter Store (SecureString, KMS-encrypted)
**TLS**: Caddy reverse proxy (automatic Let's Encrypt)
**Zero-downtime**: docker-rollout plugin
**State Backend**: S3 + DynamoDB for OpenTofu state locking
**Target Platform**: AWS (us-east-1), single EC2 instance
**Cost**: ~$18-20/month

## Constitution Check

| Principle | Status | Evidence |
|-----------|--------|----------|
| I. Isolated Environments | PASS | Docker Compose on EC2; uv for any local tooling |
| II. Secret Safety | PASS | SSM Parameter Store (encrypted); no secrets in VCS, images, or logs |
| III. Git Discipline | PASS | Infra code version-controlled; OIDC scoped to main branch |
| IV. Test-Driven | PASS | `tofu plan` validates before apply; health checks verify deployment |
| V. Code Abstraction | PASS | Reusable OpenTofu modules where applicable |
| VI. Provenance | PASS | OpenTofu state tracks all resources; deploy commits recorded |
| VII. Living Documentation | PASS | Quickstart and external setup guide updated |
| VIII. Simplicity | PASS | Single EC2 + Docker Compose; Caddy replaces nginx+certbot |

## Project Structure

### Infrastructure (new)

```text
infra/
├── main.tf                  # Provider, backend, data sources
├── ec2.tf                   # EC2 instance, security group, EIP, user data
├── iam.tf                   # OIDC provider, deploy role, instance role
├── ecr.tf                   # ECR repository
├── ssm.tf                   # SSM parameter definitions (placeholder values)
├── state.tf                 # S3 bucket + DynamoDB for state backend
├── variables.tf             # Input variables (region, instance type, domain)
├── outputs.tf               # Deploy role ARN, instance ID, ECR URL, EIP
├── versions.tf              # Required providers and versions
└── scripts/
    └── deploy.sh            # SSM document: pull image, update .env, rollout
```

### Modified Files

```text
deploy/
├── docker-compose.yml       # Replace nginx with caddy; add healthchecks
├── Caddyfile                # Replaces nginx.conf
└── docker-compose.dev.yml   # No changes

.github/workflows/
├── deploy.yml               # Rewrite: OIDC auth, ECR push, SSM deploy
└── ci.yml                   # No changes
```

**Structure Decision**: Infrastructure code lives in `infra/` at repo root,
alongside application code. OpenTofu state is stored remotely in S3 with
DynamoDB locking. The deploy workflow is rewritten to use OIDC + ECR + SSM
instead of SSH + SCP.
