# Feature Specification: AWS Least-Privilege Idempotent Deployment

**Feature Branch**: `002-aws-least-privilege-deploy`
**Created**: 2026-03-22
**Status**: Draft
**Input**: Create an idempotent AWS deployment setup for the etelemetry
server usable from GitHub Actions, with least-privilege IAM roles instead
of full administrator access.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Automated Deployment on Push (Priority: P1)

A maintainer merges a PR to the `main` branch. The GitHub Actions deploy
workflow automatically provisions or updates the etelemetry server on AWS
without manual SSH access. The deployment is idempotent — running it twice
with no code changes produces no infrastructure changes. The workflow uses
a scoped IAM role with only the permissions required to deploy, not full
administrator access.

**Why this priority**: This is the core value — automated, secure, repeatable
deployment is the entire purpose of this feature.

**Independent Test**: Run the deploy workflow twice in succession on the
same commit. Verify that the first run provisions/updates the infrastructure
and the second run reports no changes. Verify the IAM role cannot perform
actions outside its deployment scope (e.g., cannot create new IAM users,
cannot access unrelated S3 buckets, cannot modify billing).

**Acceptance Scenarios**:

1. **Given** a merged PR to `main`, **When** the deploy workflow runs,
   **Then** the etelemetry server is running on AWS at `et.dandiproject.org`
   with all services healthy (server, database, geolocation).

2. **Given** a successful deployment, **When** the deploy workflow runs
   again with no code changes, **Then** it completes successfully and
   reports no infrastructure changes (idempotent).

3. **Given** the deploy workflow IAM role, **When** an attacker obtains
   the temporary credentials, **Then** they can only perform deployment-
   related actions (push images, update services) and cannot escalate
   privileges, access other AWS accounts, or modify IAM policies.

4. **Given** a deployment failure (e.g., health check fails), **When** the
   workflow detects the failure, **Then** it rolls back to the previous
   working state and reports the failure clearly in the workflow log.

---

### User Story 2 - Initial Infrastructure Bootstrap (Priority: P2)

A new operator runs a one-time bootstrap process to create the AWS
infrastructure (compute, networking, storage, IAM roles) for the first
time. After bootstrap, all subsequent updates are handled by the automated
deploy workflow. The bootstrap is also idempotent — running it again updates
existing resources rather than creating duplicates.

**Why this priority**: The initial setup must happen before automated
deploys can work, but it only runs once (or when infrastructure changes
are needed).

**Independent Test**: Run the bootstrap on a clean AWS account. Verify all
resources are created. Run it again and verify no duplicates. Tear down and
re-bootstrap to verify it works from scratch.

**Acceptance Scenarios**:

1. **Given** a clean AWS account with appropriate credentials, **When** the
   bootstrap process runs, **Then** all required infrastructure is created:
   compute instance, security groups, persistent storage, IAM roles, and
   container registry.

2. **Given** existing infrastructure from a prior bootstrap, **When** the
   bootstrap runs again, **Then** it updates existing resources without
   creating duplicates.

3. **Given** a bootstrapped environment, **When** the automated deploy
   workflow (US1) runs for the first time, **Then** it successfully
   deploys the application using the infrastructure created by bootstrap.

---

### User Story 3 - Secret Management (Priority: P3)

Deployment secrets (database password, MaxMind license key, GitHub token)
are stored securely and injected at deploy time without being exposed in
workflow logs, container images, or version control. The secrets are
managed through a single secure channel.

**Why this priority**: Secrets management is critical for security but
builds on top of the deployment infrastructure.

**Independent Test**: Deploy the service, then inspect workflow logs,
container environment, and image layers. Verify no secrets are visible
in any of these locations.

**Acceptance Scenarios**:

1. **Given** secrets stored in the secure secret store, **When** the deploy
   workflow runs, **Then** secrets are injected into the running containers
   at runtime without appearing in build logs, image layers, or workflow
   output.

2. **Given** a deployed service, **When** an operator rotates a secret
   (e.g., database password), **Then** the change can be applied by
   re-running the deploy workflow without rebuilding the container image.

---

### Edge Cases

- What happens when the AWS region is unavailable? The deploy workflow
  MUST fail clearly and not leave infrastructure in a partial state.
- What happens when the container health check fails after deploy? The
  deployment MUST roll back to the previous working version automatically.
- What happens when the IAM role's temporary credentials expire mid-deploy?
  The workflow MUST use credentials with sufficient duration for the full
  deployment process.
- What happens when two deploy workflows run concurrently (e.g., rapid
  merges)? The system MUST serialize deployments or fail the second
  gracefully with a clear message.
- What happens when the bootstrap resources are manually modified outside
  the infrastructure-as-code tool? The next bootstrap run MUST detect
  drift and reconcile to the declared state.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The deployment MUST be idempotent — running the same
  deployment with the same code and configuration MUST produce no
  infrastructure changes on subsequent runs.
- **FR-002**: The deployment MUST use a dedicated IAM role with only the
  minimum permissions required to deploy the etelemetry application. The
  role MUST NOT have administrator access, IAM write access, or access
  to unrelated AWS services.
- **FR-003**: The GitHub Actions workflow MUST authenticate to AWS using
  OpenID Connect (OIDC) federation — no long-lived AWS access keys stored
  as GitHub secrets. The OIDC trust policy MUST be scoped to the specific
  repository and branch.
- **FR-004**: The deployment MUST include a health check that verifies the
  etelemetry server is responding correctly after deployment. If the health
  check fails, the deployment MUST roll back automatically.
- **FR-005**: The bootstrap process MUST create all required AWS resources
  in a single idempotent operation: compute, networking, persistent storage
  for database and GeoIP data, IAM roles, and container image storage.
- **FR-006**: Secrets (database password, MaxMind key, GitHub token) MUST
  be stored in a secure secret store and injected at container runtime.
  Secrets MUST NOT appear in container images, build logs, or workflow
  output.
- **FR-007**: The deployment MUST support zero-downtime updates — the new
  version MUST be running and healthy before the old version is stopped.
- **FR-008**: The infrastructure definition MUST be version-controlled
  alongside the application code so that infrastructure changes go through
  the same review process as code changes.
- **FR-009**: The IAM role MUST use a trust policy that restricts
  assumption to the specific GitHub repository (`sensein/etelemetry`) and
  optionally a specific branch (`main`).
- **FR-010**: The deployment MUST configure the domain `et.dandiproject.org`
  to point to the deployed service with TLS termination.
- **FR-011**: The deployment MUST provision persistent storage for
  PostgreSQL data that survives container restarts and redeployments.
- **FR-012**: The deployment MUST include automated TLS certificate
  provisioning and renewal for `et.dandiproject.org`.
- **FR-013**: Concurrent deployment attempts MUST be serialized or the
  second attempt MUST fail gracefully without corrupting state.

### Key Entities

- **DeployRole**: The IAM role assumed by GitHub Actions during deployment.
  Has a trust policy limiting who can assume it and a permission policy
  limiting what actions it can perform.
- **Infrastructure State**: The declared state of all AWS resources
  (compute, networking, storage, IAM). Stored as code, applied
  idempotently.
- **Deployment Artifact**: The container image built from the etelemetry
  source code, tagged with the git commit SHA, stored in a container
  registry.
- **Secret**: A sensitive configuration value (database password, API key)
  stored in a secure secret store and injected at runtime.

### Assumptions

- The AWS account is already created and an initial user with sufficient
  privileges exists to run the bootstrap (one-time).
- The domain `et.dandiproject.org` DNS is managed externally (the
  deployment creates the necessary records or provides the values to
  configure manually).
- The etelemetry application is already containerized (Dockerfile exists
  from feature 001).
- GitHub Actions OIDC provider is available in the target AWS account
  (or will be created during bootstrap).
- A single EC2 instance (or equivalent compute) is sufficient for the
  current load (~1M pings/week). Horizontal scaling is out of scope.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A code change merged to `main` is live on
  `et.dandiproject.org` within 15 minutes of merge without manual
  intervention.
- **SC-002**: Running the deployment workflow twice on the same commit
  produces no infrastructure changes on the second run.
- **SC-003**: The IAM deployment role has fewer than 20 distinct IAM
  permissions (not `*` actions), covering only the services required
  for deployment.
- **SC-004**: No long-lived AWS credentials (access key ID / secret key)
  are stored in GitHub secrets — authentication uses only OIDC federation.
- **SC-005**: A failed deployment automatically rolls back and the
  previous version continues serving traffic with zero downtime.
- **SC-006**: An operator can bootstrap the full infrastructure from
  scratch in under 30 minutes by following the documentation.
- **SC-007**: All secrets are verifiably absent from container images,
  workflow logs, and the version-controlled infrastructure definition.
