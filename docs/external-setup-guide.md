# External Setup Guide

This guide provides an ordered pathway for deploying etelemetry from
scratch. Follow each section in sequence.

## Overview: What Gets Set Up

```
1. GitHub repo settings (branch protection, environments, variables)
2. PyPI trusted publishing (for client library releases)
3. MaxMind GeoLite2 account (for IP geolocation)
4. AWS infrastructure via OpenTofu (EC2, IAM, ECR, SSM — no manual setup)
5. DNS record (et.dandiproject.org → Elastic IP)
6. First deployment (automated via GitHub Actions)
7. MongoDB data migration (one-time, from old server)
8. Legacy domain redirect (rig.mit.edu → et.dandiproject.org)
9. First client release (pre-release, then stable)
```

---

## 1. GitHub Repository Settings

### 1.1 Branch Protection

1. Go to **Settings → Branches → Add branch ruleset**
2. Apply to `main` branch:
   - Require pull request reviews (1 reviewer)
   - Require status checks: `lint`, `test-client`, `test-server`,
     `validate-infra`
   - Require branches to be up to date
   - Do not allow force pushes

### 1.2 Environments

Create two environments in **Settings → Environments**:

| Environment | Purpose | Protection |
|-------------|---------|------------|
| `pypi` | Client library publishing | Optional: require reviewer |
| `production` | AWS deployment | Optional: require reviewer |

### 1.3 Repository Variables

Go to **Settings → Secrets and variables → Actions → Variables**:

| Variable | Value | Description |
|----------|-------|-------------|
| `AWS_DEPLOY_ROLE_ARN` | (from `tofu output` in step 4) | IAM role for OIDC deploy |
| `AWS_REGION` | `us-east-1` | AWS region |

No AWS secrets needed — authentication uses OIDC (no access keys).

---

## 2. PyPI Trusted Publishing

### 2.1 Configure Publisher

1. Go to https://pypi.org/manage/account/publishing/
2. Click **Add a new pending publisher**
3. Fill in:
   - PyPI project name: `etelemetry`
   - Owner: `sensein`
   - Repository: `etelemetry`
   - Workflow name: `publish.yml`
   - Environment name: `pypi`
4. Click **Add**

---

## 3. MaxMind GeoLite2 Account

1. Register at https://www.maxmind.com/en/geolite2/signup
2. Confirm email and log in
3. Go to **Account → Manage License Keys**
4. Click **Generate New License Key**
   - Description: "etelemetry production"
5. Save the **Account ID** and **License Key** — you'll need them in step 4

---

## 4. AWS Infrastructure Bootstrap (OpenTofu)

All AWS resources are created automatically via OpenTofu. No manual EC2
setup, no SSH keys, no security group configuration by hand.

See `docs/bootstrap.md` for the full step-by-step, summarized here:

```bash
# 4.1 Create state backend (one-time, see bootstrap.md for commands)
aws s3api create-bucket --bucket etelemetry-tfstate --region us-east-1
aws dynamodb create-table --table-name etelemetry-tflock ...

# 4.2 Apply infrastructure
cd infra/
make init
make plan    # Review what will be created
make apply   # Creates: EC2, IAM roles (OIDC + instance), ECR, SSM, EIP

# 4.3 Note the outputs
tofu output
# deploy_role_arn    → set as GitHub variable AWS_DEPLOY_ROLE_ARN
# elastic_ip         → use for DNS in step 5
# ecr_repository_url → used automatically by deploy workflow
# instance_id        → used automatically by deploy workflow
```

### 4.4 Store Secrets in SSM

```bash
aws ssm put-parameter --name /etelemetry/POSTGRES_PASSWORD \
  --value "$(openssl rand -base64 32)" --type SecureString --overwrite

aws ssm put-parameter --name /etelemetry/MAXMIND_ACCOUNT_ID \
  --value "YOUR_ACCOUNT_ID" --type SecureString --overwrite

aws ssm put-parameter --name /etelemetry/MAXMIND_LICENSE_KEY \
  --value "YOUR_LICENSE_KEY" --type SecureString --overwrite

# Optional: for higher GitHub API rate limits
aws ssm put-parameter --name /etelemetry/GITHUB_TOKEN \
  --value "ghp_YOUR_TOKEN" --type SecureString --overwrite
```

### 4.5 Set GitHub Variable

Go back to GitHub repo → Settings → Variables → Actions and set
`AWS_DEPLOY_ROLE_ARN` to the value from `tofu output deploy_role_arn`.

---

## 5. DNS Setup

**IMPORTANT**: DNS MUST be configured BEFORE the first deployment.
Caddy needs the domain to resolve for automatic TLS certificate issuance.

### 5.1 Create A Record

In your DNS provider for `dandiproject.org`:

| Type | Name | Value | TTL |
|------|------|-------|-----|
| A | `et` | `<elastic_ip from step 4>` | 300 |

### 5.2 Verify Resolution

```bash
dig et.dandiproject.org +short
# Should return the Elastic IP
```

TLS is handled automatically by Caddy — no certbot, no manual
certificate management, no renewal cron jobs.

---

## 6. First Deployment

Merge the infrastructure PR to `main`. The deploy workflow will:

1. Authenticate to AWS via OIDC (no access keys)
2. Build Docker image and push to ECR
3. Run deploy script on EC2 via SSM (no SSH)
4. Pull image, write secrets from SSM to .env, docker-rollout
5. Health-check the deployment
6. Caddy auto-provisions TLS certificate on first HTTPS request

### Verify

```bash
curl https://et.dandiproject.org/
# {"name": "etelemetry", "version": "..."}

curl https://et.dandiproject.org/dashboard/
# HTML dashboard page
```

---

## 7. MongoDB Data Migration (one-time)

After the new server is running and verified:

```bash
# From EC2 (via SSM Session Manager):
cd /opt/etelemetry
python -m tools.migrate \
  --mongo-uri mongodb://<old-ec2-host>:27017/et \
  --pg-uri postgresql://etelemetry:<password>@localhost:5432/etelemetry

# Verify
python -m tools.migrate \
  --mongo-uri mongodb://<old-ec2-host>:27017/et \
  --pg-uri postgresql://etelemetry:<password>@localhost:5432/etelemetry \
  --verify
```

Confirm dashboard shows historical data at
https://et.dandiproject.org/dashboard/

---

## 8. Legacy Domain Redirect

On the existing `rig.mit.edu` server, add a redirect so old clients
transition seamlessly:

```nginx
server {
    listen 80;
    server_name rig.mit.edu;

    location /et/ {
        return 301 https://et.dandiproject.org$request_uri;
    }
}
```

The etelemetry client follows redirects automatically via `requests`.

---

## 9. First Client Release

```bash
# Pre-release (pip won't install without --pre)
git tag v2.0.0a1
git push origin v2.0.0a1
# → GitHub pre-release → PyPI publish

# Test
pip install --pre etelemetry
python -c "import etelemetry; print(etelemetry.get_project('nipy/nipype'))"

# Stable release (once verified)
git tag v2.0.0
git push origin v2.0.0
# → GitHub release → PyPI publish
# → pip install etelemetry picks this up
```

---

## Transition Checklist

Follow in order:

- [ ] GitHub branch protection enabled with CI status checks
- [ ] GitHub `pypi` and `production` environments created
- [ ] PyPI trusted publisher configured for `sensein/etelemetry`
- [ ] MaxMind account created, license key saved
- [ ] OpenTofu bootstrap complete (`make apply` succeeds)
- [ ] Secrets stored in SSM Parameter Store
- [ ] `AWS_DEPLOY_ROLE_ARN` set as GitHub variable
- [ ] DNS A record for `et.dandiproject.org` → Elastic IP
- [ ] DNS resolves correctly (`dig et.dandiproject.org`)
- [ ] First deploy to `main` succeeds
- [ ] `curl https://et.dandiproject.org/` returns health response
- [ ] TLS certificate valid (Caddy auto-provisioned)
- [ ] MongoDB migration completed and verified
- [ ] Dashboard shows historical data
- [ ] Legacy `rig.mit.edu/et/` redirects to new domain
- [ ] Pre-release `v2.0.0a1` published to PyPI
- [ ] `pip install --pre etelemetry` works
- [ ] Stable `v2.0.0` published to PyPI
- [ ] Downstream projects tested with `etelemetry>=2.0.0`
