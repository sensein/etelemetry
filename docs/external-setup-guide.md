# External Setup Guide

This guide covers all external services that need to be configured for
etelemetry deployment. Follow each section in order.

## 1. GitHub Repository Settings

### 1.1 Branch Protection

1. Go to **Settings → Branches → Add branch ruleset**
2. Apply to `main` branch:
   - Require pull request reviews (1 reviewer)
   - Require status checks: `lint`, `test-client`, `test-server`
   - Require branches to be up to date
   - Do not allow force pushes

### 1.2 Environments for PyPI Publishing

etelemetry uses PyPI trusted publishing (OIDC) — no API tokens needed.
Both stable and pre-release versions publish to PyPI (pip only installs
pre-releases when `--pre` is passed or an exact version is pinned).

**Create one environment:**

1. Go to **Settings → Environments → New environment**
2. Create `pypi`:
   - Optionally add deployment protection (require reviewer approval)
   - No secrets needed (OIDC handles auth)

### 1.3 Repository Secrets for AWS Deployment

Go to **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Value | Description |
|--------|-------|-------------|
| `AWS_SSH_PRIVATE_KEY` | Contents of the EC2 SSH private key file | Used by deploy workflow to SSH into the server |
| `AWS_SERVER_HOST` | `et.dandiproject.org` or EC2 public IP | SSH target for deployment |
| `AWS_SERVER_USER` | `ubuntu` (or your EC2 user) | SSH username |

### 1.4 Repository Variables (optional)

Go to **Settings → Secrets and variables → Actions → Variables**:

| Variable | Value | Description |
|----------|-------|-------------|
| `DEPLOY_ENABLED` | `true` | Set to `false` to disable auto-deploy |

---

## 2. PyPI Setup (Trusted Publishing)

### 2.1 Configure Trusted Publisher

1. Go to https://pypi.org/manage/account/publishing/
2. Click **Add a new pending publisher**
3. Fill in:
   - PyPI project name: `etelemetry`
   - Owner: `sensein`
   - Repository: `etelemetry`
   - Workflow name: `publish.yml`
   - Environment name: `pypi`
4. Click **Add**

### 2.2 First Release Workflow

```bash
# Pre-release (goes to PyPI, but pip won't install without --pre)
git tag v2.0.0a1
git push origin v2.0.0a1
# → Creates GitHub pre-release → publishes to PyPI as pre-release

# Test install of pre-release from PyPI
pip install --pre etelemetry

# Once verified, create the stable release (goes to PyPI)
git tag v2.0.0
git push origin v2.0.0
# → Creates GitHub release → publishes to PyPI
```

---

## 3. MaxMind GeoLite2 Setup

### 3.1 Create Account

1. Register at https://www.maxmind.com/en/geolite2/signup
2. Confirm email and log in
3. Go to **Account → Manage License Keys**
4. Click **Generate New License Key**
   - Description: "etelemetry production"
   - Select "No" for GeoIP Update compatibility (we use env vars)
5. Save the Account ID and License Key

### 3.2 Values Needed

| Value | Where to put it |
|-------|----------------|
| Account ID | `MAXMIND_ACCOUNT_ID` in `deploy/.env` |
| License Key | `MAXMIND_LICENSE_KEY` in `deploy/.env` |

The `geoipupdate` Docker container automatically downloads and updates
the GeoLite2-City database weekly.

---

## 4. AWS EC2 Setup

### 4.1 Launch EC2 Instance

1. **AMI**: Ubuntu 24.04 LTS (arm64 for cost efficiency, or amd64)
2. **Instance type**: `t4g.small` (2 vCPU, 2 GB RAM) — sufficient for
   ~1M pings/week
3. **Storage**: 30 GB gp3 (enough for PostgreSQL data + GeoIP DB)
4. **Security group**:
   - Inbound: SSH (22) from your IP, HTTP (80), HTTPS (443)
   - Outbound: All traffic
5. **Key pair**: Create or select; download the `.pem` file

### 4.2 Install Docker on EC2

```bash
ssh -i your-key.pem ubuntu@<EC2-IP>

# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# Log out and back in

# Install Docker Compose plugin
sudo apt-get install -y docker-compose-plugin

# Verify
docker compose version
```

### 4.3 Deploy etelemetry

```bash
# Clone the repo
git clone https://github.com/sensein/etelemetry.git /opt/etelemetry
cd /opt/etelemetry/deploy

# Create .env from template
cp .env.example .env

# Edit .env with real values:
#   POSTGRES_PASSWORD=<strong-random-password>
#   MAXMIND_ACCOUNT_ID=<from-step-3>
#   MAXMIND_LICENSE_KEY=<from-step-3>
#   GITHUB_TOKEN=<optional-for-higher-rate-limits>
nano .env

# Start services
docker compose up -d

# Verify
docker compose ps
curl http://localhost/projects/nipy/nipype
```

### 4.4 PostgreSQL Backup (recommended)

Set up a daily cron job for database backups:

```bash
# Create backup script
cat > /opt/etelemetry/backup.sh << 'SCRIPT'
#!/bin/bash
BACKUP_DIR=/opt/etelemetry/backups
mkdir -p "$BACKUP_DIR"
docker compose -f /opt/etelemetry/deploy/docker-compose.yml exec -T postgres \
  pg_dump -U etelemetry etelemetry | gzip > "$BACKUP_DIR/etelemetry-$(date +%Y%m%d).sql.gz"
# Keep last 30 days
find "$BACKUP_DIR" -name "*.sql.gz" -mtime +30 -delete
SCRIPT
chmod +x /opt/etelemetry/backup.sh

# Add cron job (daily at 2 AM)
(crontab -l 2>/dev/null; echo "0 2 * * * /opt/etelemetry/backup.sh") | crontab -
```

---

## 5. DNS Setup (et.dandiproject.org)

### 5.1 Create DNS Record

In your DNS provider for `dandiproject.org`:

| Type | Name | Value | TTL |
|------|------|-------|-----|
| A | `et` | `<EC2-Elastic-IP>` | 300 |

### 5.2 Allocate Elastic IP

1. In AWS Console → EC2 → Elastic IPs → **Allocate**
2. Associate the Elastic IP with your EC2 instance
3. Use this IP for the DNS A record

### 5.3 TLS/HTTPS Setup

Use Let's Encrypt with certbot via Docker:

```bash
# On EC2, install certbot
sudo apt-get install -y certbot python3-certbot-nginx

# Stop nginx temporarily (certbot needs port 80)
docker compose -f /opt/etelemetry/deploy/docker-compose.yml stop nginx

# Get certificate
sudo certbot certonly --standalone -d et.dandiproject.org

# Update nginx.conf for HTTPS
# See deploy/nginx.conf — add SSL block pointing to:
#   /etc/letsencrypt/live/et.dandiproject.org/fullchain.pem
#   /etc/letsencrypt/live/et.dandiproject.org/privkey.pem

# Restart nginx
docker compose -f /opt/etelemetry/deploy/docker-compose.yml up -d nginx

# Auto-renew (certbot adds this automatically, but verify)
sudo certbot renew --dry-run
```

### 5.4 Legacy Domain Redirect (rig.mit.edu)

On the existing `rig.mit.edu` server, add an nginx redirect:

```nginx
server {
    listen 80;
    server_name rig.mit.edu;

    location /et/ {
        return 301 https://et.dandiproject.org$request_uri;
    }
}
```

This ensures old clients pointing at `rig.mit.edu/et/projects/...` are
redirected to the new domain. The etelemetry client follows redirects
automatically via `requests`.

---

## 6. MongoDB Data Migration

### 6.1 Prerequisites

- New etelemetry server running and healthy on EC2
- Access to the existing MongoDB on the old EC2 instance
- Network connectivity between old and new instances (or use mongodump)

### 6.2 Run Migration

```bash
# Option A: Direct connection (if network allows)
cd /opt/etelemetry
docker compose exec server python -m tools.migrate \
  --mongo-uri mongodb://<old-ec2-host>:27017/et \
  --pg-uri postgresql://etelemetry:<password>@postgres:5432/etelemetry

# Option B: Via mongodump (if no direct network access)
# On old server:
mongodump -d et --gzip --archive=et-backup.gz
# Transfer to new server, then:
mongorestore --gzip --archive=et-backup.gz --host localhost:27017
# Then run migration against local MongoDB

# Verify
docker compose exec server python -m tools.migrate \
  --mongo-uri mongodb://<mongo-host>:27017/et \
  --pg-uri postgresql://etelemetry:<password>@postgres:5432/etelemetry \
  --verify
```

### 6.3 Post-Migration Verification

```bash
# Check dashboard shows historical data
curl https://et.dandiproject.org/dashboard/

# Check a known project
curl https://et.dandiproject.org/projects/nipy/nipype

# Check that no IPs are in the database
docker compose exec postgres psql -U etelemetry -c \
  "SELECT column_name FROM information_schema.columns WHERE table_name='version_checks';"
# Should NOT contain any IP-related column
```

---

## 7. Transition Checklist

- [ ] EC2 instance launched and Docker installed
- [ ] MaxMind account created and license key obtained
- [ ] `deploy/.env` configured with all secrets
- [ ] `docker compose up -d` succeeds, all services healthy
- [ ] DNS A record for `et.dandiproject.org` points to Elastic IP
- [ ] TLS certificate obtained via Let's Encrypt
- [ ] GitHub repo secrets configured (AWS SSH key, host, user)
- [ ] PyPI trusted publishing configured (pypi + testpypi environments)
- [ ] GitHub branch protection rules enabled
- [ ] Pre-release tag pushed (`v2.0.0a1`), TestPyPI publish succeeds
- [ ] `pip install --index-url https://test.pypi.org/simple/ etelemetry==2.0.0a1` works
- [ ] MongoDB migration completed and verified
- [ ] Dashboard shows historical data at https://et.dandiproject.org/dashboard/
- [ ] Legacy `rig.mit.edu/et/` redirects to new domain
- [ ] Stable release tag pushed (`v2.0.0`), PyPI publish succeeds
- [ ] Downstream projects test with new `etelemetry>=2.0.0`
