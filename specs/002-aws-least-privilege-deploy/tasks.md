# Tasks: AWS Least-Privilege Idempotent Deployment

**Input**: Design documents from `/specs/002-aws-least-privilege-deploy/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, contracts/iam-policy.md, quickstart.md

**Tests**: Included — constitution mandates test-driven (Principle IV). OpenTofu `plan` validates before `apply`; health checks verify deployments.

**Organization**: Tasks grouped by user story for independent implementation.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story (US1–US3)
- Exact file paths from plan.md project structure

## Phase 1: Setup

**Purpose**: Create `infra/` directory structure and OpenTofu project skeleton

- [ ] T001 Create `infra/versions.tf` — required providers (aws ~> 5.0, opentofu backend config)
- [ ] T002 Create `infra/variables.tf` — input variables: aws_region (default us-east-1), instance_type (default t3.small), domain (default et.dandiproject.org), github_repo (default sensein/etelemetry), project_name (default etelemetry)
- [ ] T003 [P] Create `infra/outputs.tf` — output deploy_role_arn, instance_id, ecr_repository_url, elastic_ip, ssm_parameter_prefix
- [ ] T004 [P] Create `infra/state.tf` — S3 backend configuration for OpenTofu state with DynamoDB locking table

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: IAM OIDC provider + core IAM roles — MUST complete before any deployment works

**CRITICAL**: No deployment tasks can proceed without IAM roles

- [ ] T005 Create `infra/iam.tf` — GitHub OIDC identity provider (`aws_iam_openid_connect_provider`), deploy role (`etelemetry-deploy`) with trust policy scoped to `repo:sensein/etelemetry:ref:refs/heads/main`, permission policy with 14 actions per contracts/iam-policy.md (SSM, EC2 describe, ECR push/pull), all resource-scoped
- [ ] T006 [P] Create `infra/iam.tf` (instance role section) — EC2 instance role (`etelemetry-instance`) with instance profile, SSM managed instance core policy, SSM parameter read (`/etelemetry/*`), ECR pull permissions
- [ ] T007 [P] Create `infra/ecr.tf` — ECR private repository `etelemetry`, lifecycle policy (keep last 10 images), image scanning on push enabled
- [ ] T008 Write IAM policy validation test in `infra/tests/test_iam_policy.py` — parse the OpenTofu plan output JSON and verify: deploy role has exactly 14 actions, no `*` resource wildcards on sensitive actions, no `iam:*` permissions, trust policy scoped to correct repo/branch

**Checkpoint**: IAM roles and ECR ready — deployment infrastructure can be built

---

## Phase 3: User Story 1 — Automated Deployment on Push (Priority: P1)

**Goal**: Merge to main → GitHub Actions builds image, pushes to ECR, deploys via SSM, health-checks, rolls back on failure

**Independent Test**: Push to main, verify deploy workflow runs, service is live at et.dandiproject.org, second run is idempotent

### Tests for User Story 1

> **NOTE: Write tests FIRST, verify they would fail without implementation**

- [ ] T009 [US1] Write deploy smoke test in `infra/tests/test_deploy.sh` — after deployment: curl health endpoint, verify 200 + correct JSON shape, verify TLS certificate valid for et.dandiproject.org, verify no SSH port open (port 22 closed)

### Implementation for User Story 1

- [ ] T010 [US1] Create `infra/ec2.tf` — EC2 instance (var.instance_type), Amazon Linux 2023 AMI, instance profile from T006, user data script that installs Docker + Docker Compose + docker-rollout + SSM agent, security group (inbound: 80, 443 only; outbound: all), EBS root volume 20GB gp3, Elastic IP association, tags for identification
- [ ] T011 [US1] Create `infra/ec2.tf` (security group section) — security group `etelemetry-sg` with ingress rules: 80 (HTTP), 443 (HTTPS) from 0.0.0.0/0; NO port 22. Egress: all traffic.
- [ ] T012 [P] [US1] Create `infra/scripts/deploy.sh` — SSM-executed deploy script: authenticate to ECR, pull image by tag, write .env from SSM parameters, run `docker rollout server` for zero-downtime update, run health check (curl localhost:8000/), report success/failure exit code
- [ ] T013 [P] [US1] Create `infra/scripts/user-data.sh` — EC2 user data bootstrap: install Docker, Docker Compose plugin, docker-rollout, clone repo to /opt/etelemetry, pull initial images, start services
- [ ] T014 [US1] Create `deploy/Caddyfile` — Caddy reverse proxy config for et.dandiproject.org: automatic TLS, handle /et/* (strip prefix, reverse_proxy server:8000), handle /* (reverse_proxy server:8000), IP-stripped log format
- [ ] T015 [US1] Update `deploy/docker-compose.yml` — replace nginx service with caddy service (caddy:alpine image, ports 80:80 + 443:443, volume for caddy data + Caddyfile), add healthcheck to server service (curl localhost:8000/), remove nginx-related configs
- [ ] T016 [US1] Rewrite `.github/workflows/deploy.yml` — replace SSH-based deploy with: (1) `aws-actions/configure-aws-credentials@v4` with OIDC role-to-assume, (2) build Docker image, (3) authenticate to ECR + push image tagged with git SHA, (4) `aws ssm send-command` to run deploy.sh on target instance, (5) poll command status, (6) report success/failure, (7) concurrency group to serialize deploys
- [ ] T017 [US1] Run `tofu plan` and verify: all resources declared, no errors, deploy role has correct permissions, security group has no port 22
- [ ] T018 [US1] Run `tofu apply` on test/staging environment (or `tofu plan` in CI) and verify idempotency — second apply shows 0 changes

**Checkpoint**: Automated deployment working. Push to main → build → ECR → SSM deploy → health check → live.

---

## Phase 4: User Story 2 — Infrastructure Bootstrap (Priority: P2)

**Goal**: One-time bootstrap creates all AWS resources idempotently; subsequent runs detect no changes

**Independent Test**: Run bootstrap from scratch, verify all resources created. Run again, verify 0 changes.

### Implementation for User Story 2

- [ ] T019 [US2] Create `infra/main.tf` — AWS provider configuration (region from var), data sources for latest Amazon Linux 2023 AMI, account ID
- [ ] T020 [US2] Create bootstrap documentation in `docs/bootstrap.md` — step-by-step guide: prerequisites (AWS account, tofu installed, AWS CLI configured), S3 bucket + DynamoDB table creation for state backend, `tofu init`, `tofu plan`, `tofu apply`, DNS configuration, secret storage, verify outputs
- [ ] T021 [US2] Create `infra/Makefile` — targets: `init` (tofu init), `plan` (tofu plan), `apply` (tofu apply), `destroy` (tofu destroy with confirmation), `fmt` (tofu fmt), `validate` (tofu validate)
- [ ] T022 [US2] Add OpenTofu validation to `.github/workflows/ci.yml` — on PR: run `tofu init -backend=false`, `tofu validate`, `tofu fmt -check` for the infra/ directory
- [ ] T023 [US2] Test idempotency — run `tofu apply` twice, verify second run shows "No changes. Your infrastructure matches the configuration."

**Checkpoint**: Full infrastructure bootstrappable from scratch. Idempotent.

---

## Phase 5: User Story 3 — Secret Management (Priority: P3)

**Goal**: Secrets stored in SSM Parameter Store, injected at runtime, never in images/logs/VCS

**Independent Test**: Deploy, then verify secrets absent from image layers, workflow logs, and Caddyfile/compose files in VCS

### Tests for User Story 3

> **NOTE: Write tests FIRST**

- [ ] T024 [US3] Write secret audit test in `infra/tests/test_secrets.sh` — verify: no SecureString values in `tofu plan` output, no secrets in `docker inspect` of running containers, no secrets in workflow log artifacts, .env file on EC2 has correct permissions (600, root-owned)

### Implementation for User Story 3

- [ ] T025 [US3] Create `infra/ssm.tf` — SSM parameter definitions for /etelemetry/POSTGRES_PASSWORD, /etelemetry/MAXMIND_ACCOUNT_ID, /etelemetry/MAXMIND_LICENSE_KEY, /etelemetry/GITHUB_TOKEN (all SecureString type, placeholder values that operator replaces via CLI)
- [ ] T026 [US3] Update `infra/scripts/deploy.sh` — add step to fetch all parameters from SSM `/etelemetry/*` path, write to `/opt/etelemetry/deploy/.env` with permissions 600, mask values in script output
- [ ] T027 [US3] Add secret rotation documentation to `docs/bootstrap.md` — how to update a secret via `aws ssm put-parameter --overwrite`, then re-run deploy workflow to pick up new value

**Checkpoint**: Secrets managed securely. Rotatable without image rebuild.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, cleanup, security hardening

- [ ] T028 Update `docs/external-setup-guide.md` — replace SSH-based instructions with OIDC + SSM approach, add OpenTofu bootstrap steps, update GitHub repo settings section (remove SSH key secrets, add OIDC role ARN variable)
- [ ] T029 [P] Update `docs/phase-log.md` — add entry for feature 002 implementation
- [ ] T030 [P] Security review — verify: no port 22 in security group, OIDC trust scoped to repo+branch, deploy role has no IAM write, SSM parameters encrypted, .env not in version control
- [ ] T031 Remove SSH-related secrets documentation from `docs/external-setup-guide.md` — remove references to AWS_SSH_PRIVATE_KEY, SSH key setup, SCP commands
- [ ] T032 Run full CI pipeline — verify OpenTofu validation, application tests, and deploy workflow all pass

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 (needs variables.tf, versions.tf)
- **US1 (Phase 3)**: Depends on Phase 2 (needs IAM roles, ECR)
- **US2 (Phase 4)**: Depends on Phase 2 (needs all infra files to exist)
- **US3 (Phase 5)**: Depends on Phase 2 (needs IAM, SSM)
- **Polish (Phase 6)**: Depends on all user stories

### User Story Dependencies

- **US1 (P1)**: After Phase 2 — core deployment
- **US2 (P2)**: After Phase 2 — can run in parallel with US1 (docs + main.tf)
- **US3 (P3)**: After Phase 2 — can run in parallel with US1 (SSM params)

### Parallel Opportunities

After Phase 2:
- US1 (EC2, deploy workflow), US2 (bootstrap docs, main.tf), US3 (SSM params) can all start in parallel since they touch different files

### Within Each User Story

- Tests first (TDD for deploy smoke test and secret audit)
- Infrastructure files before workflow files
- Workflow before validation

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (4 tasks)
2. Complete Phase 2: Foundational (4 tasks)
3. Complete Phase 3: US1 — Automated Deploy (10 tasks)
4. **STOP and VALIDATE**: Push to main, verify deploy works
5. Iterate

### Incremental Delivery

1. Setup + Foundational → IAM roles ready
2. US1 → Automated deploy working → Verify
3. US2 → Bootstrap documented, CI validates infra
4. US3 → Secrets in SSM, rotation documented
5. Polish → Security review, docs updated

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story
- Commit after each task or logical group
- `tofu plan` acts as the "test" for infrastructure changes
- All IAM permissions scoped to specific resource ARNs — no wildcards
- Constitution: secrets via SSM (Principle II), conventional commits (Principle III), infra as code (Principle VIII)
