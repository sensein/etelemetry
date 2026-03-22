# Phase Log

## 2026-03-22 — Specification & Planning

**Objectives**: Define requirements, choose tech stack, design data model,
create task breakdown for the etelemetry stack migration and monorepo refactor.

**Actions**:
- Created feature specification (spec.md) with 5 user stories, 20 FRs, 9 SCs
- Ratified project constitution v2026.03.22.1 with 8 principles
- Clarified: data retention (indefinite, IPs discarded), dashboard geo
  visualization (interactive map + table), content-addressed dedup (hourly
  buckets), allowlist via config file, scale (~1M pings/week)
- Researched and selected tech stack: FastAPI, PostgreSQL 16, MaxMind
  GeoLite2, htmx + Leaflet.js, httpx, SQLAlchemy 2.0
- Designed data model (3 tables: projects, version_checks, usage_aggregates)
- Defined API contracts (HTTP + Python client)
- Generated 59-task breakdown across 8 phases
- Ran cross-artifact analysis; remediated all HIGH/MEDIUM findings

**Decisions**:
- PostgreSQL over SQLite/DuckDB (concurrent writes via MVCC)
- Server-rendered dashboard over SPA (simplicity, accessibility, no build step)
- Content-addressed dedup with hourly time-buckets (reduces row count by ~100x)
- CalVer for constitution versioning

**Outcomes**: All artifacts ready for implementation. Analysis clean (0
CRITICAL, 0 HIGH, 0 MEDIUM issues).

## 2026-03-22 — Implementation (Phases 1-8)

**Objectives**: Implement all 59 tasks across 8 phases.

**Actions**:
- Phase 1 (Setup): Monorepo structure, pyproject.toml (client + server),
  .gitignore, docs skeleton, package directories
- Phase 2 (Foundational): Pydantic settings, async DB engine, SQLAlchemy
  models (3 tables), Alembic migrations, FastAPI app factory with
  compression, allowlist loader with SIGHUP. 33 unit tests.
- Phase 3 (US1): Geolocation service (MaxMind), version checker (GitHub
  API + in-memory LRU fallback cache), usage recorder (content-addressed
  upsert), health + projects routes, client library (errors, config,
  client, public API). Backward compat: old CI params detected, /et/
  legacy path via nginx rewrite. 15 client tests + contract/integration.
- Phase 4 (US2): Configurable server URL with 4-level precedence chain
  (param → env → default_url → hardcoded). 8 config tests.
- Phase 5 (US3): MongoDB→PostgreSQL migration tool with IP stripping,
  batch processing, --verify flag. Migration tests with fixture data.
- Phase 6 (US4): Aggregation service (tiered daily/weekly/monthly),
  dashboard routes (stats API, GeoJSON, project list), Jinja2 templates
  (base, project list, detail with Leaflet map), JS for map drill-down,
  CSS for accessibility. Contract + integration tests.
- Phase 7 (US5): Dockerfile, Docker Compose (postgres + server + nginx +
  geoipupdate), nginx.conf with IP-stripped logs and legacy /et/ rewrite,
  allowlist.yml, GitHub Actions CI + deploy workflows.
- Phase 8 (Polish): IP audit (PASS — no IP in DB/logs, debug log sanitized),
  code abstraction review (identified 6 extraction opportunities, highest
  priority: project lookup helper and date range parser).

**Decisions**:
- Backward compat: server detects old CI params (name, isPR, isCI) for
  existing clients; nginx rewrites /et/ prefix
- IP audit finding: replaced IP in debug log with exception type name
- Code review: dashboard.py is the largest file (494 lines) with most
  duplication — extraction of project lookup and date range parsing
  recommended for future iteration

**Outcomes**: 51 of 59 tasks complete. Remaining: T050-T051 (Docker/CI
runtime validation), T055-T059 (docs finalization, quickstart validation,
full test suite, performance testing).
