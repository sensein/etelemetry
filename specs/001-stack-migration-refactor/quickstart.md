# Quickstart: etelemetry

## Prerequisites

- Python 3.11+
- uv (Python package manager)
- Docker and Docker Compose (for server)
- MaxMind GeoLite2 license key (free, from maxmind.com)

## Client Library (for downstream package authors)

```bash
# Install the client
uv pip install etelemetry

# Or add to your pyproject.toml
# dependencies = ["etelemetry>=2.0"]
```

```python
import etelemetry

# Check version (uses default server)
result = etelemetry.get_project("nipy/nipype")
print(result)
# {"version": "1.8.6", "bad_versions": ["1.1.0"]}

# Full check with warnings
etelemetry.check_available_version("nipy/nipype", "1.5.0")
# WARNING: A newer version (1.8.6) is available...

# Custom server URL
etelemetry.get_project("org/tool", server_url="https://my-et.example.com/")

# Or via environment variable
# export ETELEMETRY_URL=https://my-et.example.com/
```

## Server (local development)

```bash
# Clone and set up
git clone https://github.com/sensein/etelemetry.git
cd etelemetry

# Create environment
uv venv
uv pip install -e ".[dev]"
uv pip install -e "./server[dev]"

# Copy environment template
cp deploy/.env.example deploy/.env
# Edit deploy/.env — set MAXMIND_LICENSE_KEY and POSTGRES_PASSWORD

# Start services (PostgreSQL + GeoIP updater)
docker compose -f deploy/docker-compose.yml up -d postgres geoipupdate

# Run database migrations
uv run alembic upgrade head

# Start the server
uv run uvicorn etelemetry_server.app:app --reload --port 8000

# Visit dashboard at http://localhost:8000/dashboard/
# API at http://localhost:8000/projects/nipy/nipype
```

## Server (production Docker Compose)

```bash
# On your server
git clone https://github.com/sensein/etelemetry.git
cd etelemetry/deploy

# Configure
cp .env.example .env
# Edit .env — set domain, secrets, MaxMind key

# Edit allowlist.yml — add your tracked projects
# projects:
#   - owner: nipy
#     repo: nipype
#   - owner: nipy
#     repo: nibabel

# Start everything
docker compose up -d

# Verify
curl https://your-domain.com/projects/nipy/nipype
```

## Data Migration (one-time)

```bash
# Export from existing MongoDB on EC2
mongodump -d et --gzip --archive=et-backup.gz

# Copy to new server, then run migration
uv run python -m tools.migrate \
  --mongo-uri mongodb://old-host:27017/et \
  --pg-uri postgresql://user:pass@localhost:5432/etelemetry

# Verify migration
uv run python -m tools.migrate --verify
```

## Running Tests

```bash
# Unit tests (no services needed)
uv run pytest tests/unit/

# Integration tests (requires PostgreSQL)
docker compose -f deploy/docker-compose.yml up -d postgres
uv run pytest tests/integration/

# Contract tests (API shape verification)
uv run pytest tests/contract/

# All tests
uv run pytest
```
