# Implementation Plan: etelemetry Stack Migration & Monorepo Refactor

**Branch**: `001-stack-migration-refactor` | **Date**: 2026-03-22 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/001-stack-migration-refactor/spec.md`

## Summary

Combine etelemetry-server and etelemetry-client into a single monorepo.
Replace MongoDB/Sanic with PostgreSQL/FastAPI. Add privacy-preserving
geolocation (MaxMind GeoLite2), content-addressed deduplication for ~1M
pings/week, a server-rendered web dashboard (htmx + Leaflet.js), configurable
server URLs, a repository allowlist, and a one-time MongoDB data migration
tool. Deploy via Docker Compose with GitHub Actions CI/CD for AWS.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: FastAPI, SQLAlchemy 2.0, asyncpg, httpx, geoip2,
Jinja2, htmx, Leaflet.js, starlette-compress, Alembic, Pydantic v2
**Storage**: PostgreSQL 16 (via `postgres:16-alpine` Docker image)
**Testing**: pytest, pytest-asyncio, httpx (test client), testcontainers
**Target Platform**: Linux server (AWS EC2 / Docker), client on any OS
**Project Type**: Monorepo — Python client library + web service + dashboard
**Performance Goals**: ~1,650 req/min sustained, <2s version check, <10ms
geolocation, <3s dashboard load
**Constraints**: No IP persistence, WCAG 2.1 AA dashboard, backward-
compatible client API
**Scale/Scope**: ~1M pings/week, content-addressed dedup reduces storage
to ~thousands of unique rows/week

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Evidence |
|-----------|--------|----------|
| I. Isolated Environments | PASS | uv for local dev; Docker for server/DB/geoupdate |
| II. Secret Safety | PASS | .env for secrets; MaxMind key, DB password via env vars; .env in .gitignore; GitHub Actions secrets for CI/CD |
| III. Git Discipline | PASS | Conventional commits; feature branch; CI required; subagent file locking |
| IV. Test-Driven | PASS | pytest with real PostgreSQL (testcontainers); end-to-end quickstart validation |
| V. Code Abstraction | PASS | Review after each phase; shared utilities extracted when duplicated |
| VI. Provenance | PASS | phase-log.md, rebuild-spec.md, descriptive commits |
| VII. Living Documentation | PASS | vision.md, constitution evolves, docs sync |
| VIII. Simplicity | PASS | FastAPI (not SPA), htmx (not React), PostgreSQL (not microservices), single Docker Compose |

No violations. No complexity tracking needed.

## Project Structure

### Documentation (this feature)

```text
specs/001-stack-migration-refactor/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Technology decisions
├── data-model.md        # PostgreSQL schema
├── quickstart.md        # Developer getting-started guide
├── contracts/
│   └── api.md           # HTTP API + Python client API contracts
├── checklists/
│   └── requirements.md  # Spec quality checklist
└── tasks.md             # Task breakdown (created by /speckit.tasks)
```

### Source Code (repository root)

```text
etelemetry/
├── pyproject.toml                 # Client package: "etelemetry"
├── src/etelemetry/                # Client library
│   ├── __init__.py                # Public API exports
│   ├── client.py                  # get_project, check_available_version
│   ├── config.py                  # URL resolution (env, param, default)
│   └── errors.py                  # BadVersionError
│
├── server/
│   ├── pyproject.toml             # Server package: "etelemetry-server"
│   ├── src/etelemetry_server/
│   │   ├── __init__.py
│   │   ├── app.py                 # FastAPI application factory
│   │   ├── settings.py            # Pydantic settings (env-based config)
│   │   ├── models.py              # SQLAlchemy ORM models
│   │   ├── db.py                  # Database engine, session management
│   │   ├── routes/
│   │   │   ├── projects.py        # GET /projects/{owner}/{repo}
│   │   │   ├── health.py          # GET /
│   │   │   └── dashboard.py       # Dashboard HTML + API routes
│   │   ├── services/
│   │   │   ├── version_checker.py # GitHub API + cache logic
│   │   │   ├── geolocation.py     # MaxMind GeoLite2 lookup
│   │   │   ├── usage_recorder.py  # Content-addressed upsert
│   │   │   └── aggregation.py     # Tiered aggregation job
│   │   ├── allowlist.py           # YAML allowlist loader + SIGHUP
│   │   └── dashboard/
│   │       ├── templates/         # Jinja2 templates
│   │       └── static/            # CSS, JS (htmx, Leaflet)
│   ├── alembic/                   # Database migrations
│   │   ├── alembic.ini
│   │   └── versions/
│   └── tests/
│       ├── unit/
│       ├── integration/
│       └── contract/
│
├── tools/
│   ├── __init__.py
│   └── migrate.py                 # MongoDB → PostgreSQL migration
│
├── deploy/
│   ├── docker-compose.yml         # PostgreSQL, server, nginx, geoipupdate
│   ├── Dockerfile                 # Server image
│   ├── nginx.conf                 # Reverse proxy (IP stripping in logs)
│   ├── allowlist.yml              # Tracked repositories
│   ├── .env.example               # Template for secrets
│   └── geoipupdate.conf           # MaxMind update config
│
├── .github/workflows/
│   ├── ci.yml                     # Test + lint on PR
│   └── deploy.yml                 # Deploy to AWS on push
│
├── docs/
│   ├── vision.md
│   ├── phase-log.md
│   └── rebuild-spec.md
│
└── tests/                         # Client library tests
    ├── unit/
    ├── integration/
    └── contract/
```

**Structure Decision**: Monorepo with two installable packages. The root
`pyproject.toml` defines the client library (`etelemetry`), which downstream
users install via pip. The `server/pyproject.toml` defines the server
package (`etelemetry-server`), installed only for deployment. This keeps
the client lightweight (no server dependencies) while sharing the repository.
The `tools/` directory contains one-time scripts (migration). The `deploy/`
directory is self-contained for Docker Compose deployment.
