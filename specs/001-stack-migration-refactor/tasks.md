# Tasks: etelemetry Stack Migration & Monorepo Refactor

**Input**: Design documents from `/specs/001-stack-migration-refactor/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/api.md, quickstart.md

**Tests**: Included — constitution mandates test-driven with real use cases (Principle IV).

**Organization**: Tasks grouped by user story for independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story (US1–US5)
- Exact file paths from plan.md project structure

## Phase 1: Setup

**Purpose**: Monorepo initialization, tooling, and project skeleton

- [ ] T001 Create root `pyproject.toml` for client package `etelemetry` with dependencies: `requests`, `packaging`, `ci-info`; dev extras: `pytest`, `pytest-asyncio`, `httpx`, `ruff`; configure `uv` as build backend
- [ ] T002 Create `server/pyproject.toml` for server package `etelemetry-server` with dependencies: `fastapi`, `uvicorn[standard]`, `sqlalchemy[asyncio]`, `asyncpg`, `alembic`, `httpx`, `geoip2`, `jinja2`, `starlette-compress`, `pydantic-settings`, `pyyaml`; dev extras: `pytest`, `testcontainers`
- [ ] T003 [P] Create `.gitignore` (Python, .env, __pycache__, *.mmdb, node_modules) and `deploy/.env.example` with placeholder keys (POSTGRES_PASSWORD, MAXMIND_LICENSE_KEY, SECRET_KEY)
- [ ] T004 [P] Create skeleton `docs/vision.md`, `docs/phase-log.md`, `docs/rebuild-spec.md` with initial content per constitution (Principles VI, VII)
- [ ] T005 [P] Create empty package directories: `src/etelemetry/`, `server/src/etelemetry_server/`, `server/src/etelemetry_server/routes/`, `server/src/etelemetry_server/services/`, `server/src/etelemetry_server/dashboard/templates/`, `server/src/etelemetry_server/dashboard/static/`, `tools/`, `tests/unit/`, `tests/integration/`, `tests/contract/`, `server/tests/unit/`, `server/tests/integration/`, `server/tests/contract/`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Database, ORM, app factory, and allowlist — MUST complete before ANY user story

**CRITICAL**: No user story work can begin until this phase is complete

- [ ] T006 Implement Pydantic settings in `server/src/etelemetry_server/settings.py` — load from env: DATABASE_URL, MAXMIND_DB_PATH, GITHUB_TOKEN (optional), CACHE_TTL_SECONDS (default 21600), ALLOWLIST_PATH, TIME_BUCKET_HOURS (default 1)
- [ ] T007 Implement database engine and async session factory in `server/src/etelemetry_server/db.py` — `create_async_engine` with asyncpg, session dependency for FastAPI
- [ ] T008 Implement SQLAlchemy ORM models in `server/src/etelemetry_server/models.py` — `Project`, `VersionCheck`, `UsageAggregate` tables per data-model.md with all indexes and unique constraints
- [ ] T009 Initialize Alembic in `server/alembic/` with `alembic.ini` and generate initial migration from models (auto-generate revision)
- [ ] T010 [P] Implement FastAPI application factory in `server/src/etelemetry_server/app.py` — lifespan handler (init DB, load GeoIP reader, load allowlist), mount starlette-compress middleware, include route routers
- [ ] T011 [P] Implement allowlist loader in `server/src/etelemetry_server/allowlist.py` — load YAML file, SIGHUP handler to reload, sync allowlist entries to `projects` table (insert missing, deactivate removed)
- [ ] T012 [P] Write unit tests for settings, models, and allowlist in `server/tests/unit/test_settings.py`, `server/tests/unit/test_models.py`, `server/tests/unit/test_allowlist.py`

**Checkpoint**: Database schema, app factory, and allowlist ready — user story implementation can begin

---

## Phase 3: User Story 1 — Version Check at Runtime (Priority: P1)

**Goal**: Core version-check loop: client sends request, server resolves version from GitHub, records usage with geolocation (no IP), returns version + bad_versions

**Independent Test**: Start local server, configure test project in allowlist, make version check from client, verify response and DB record with geolocation but no IP

### Tests for User Story 1

- [ ] T013 [P] [US1] Write contract test for `GET /projects/{owner}/{repo}` in `server/tests/contract/test_projects_api.py` — verify response shape matches contracts/api.md for 200, 404, 400 cases
- [ ] T014 [P] [US1] Write integration test for end-to-end version check in `server/tests/integration/test_version_check.py` — start server with testcontainers PostgreSQL, make request, verify DB record has geolocation but no IP column

### Implementation for User Story 1

- [ ] T015 [P] [US1] Implement geolocation service in `server/src/etelemetry_server/services/geolocation.py` — load MaxMind GeoLite2 Reader at startup, `resolve(ip: str) -> GeoResult` returning city/region/country/coords, handle lookup failures (return "unknown")
- [ ] T016 [P] [US1] Implement version checker service in `server/src/etelemetry_server/services/version_checker.py` — async GitHub API via httpx (releases then tags fallback), cache in `projects` table with TTL, fetch `.et` file for bad_versions, handle rate limiting gracefully
- [ ] T017 [P] [US1] Implement usage recorder service in `server/src/etelemetry_server/services/usage_recorder.py` — content-addressed upsert: `INSERT INTO version_checks ... ON CONFLICT (composite_key) DO UPDATE SET count = count + 1`, compute time_bucket by truncating to hour
- [ ] T018 [US1] Implement in-memory LRU cache in `server/src/etelemetry_server/services/version_checker.py` — cache recent version lookups in memory so the server can respond to version-check requests even when PostgreSQL is unreachable; populate on successful DB reads, serve from memory on DB failure
- [ ] T019 [US1] Implement health route in `server/src/etelemetry_server/routes/health.py` — `GET /` returning `{"name": "etelemetry", "version": ...}`
- [ ] T020 [US1] Implement projects route in `server/src/etelemetry_server/routes/projects.py` — `GET /projects/{owner}/{repo}` orchestrating: allowlist check → geolocation → usage record → version lookup → response; accept `?ci=` and `?v=` query params; disable uvicorn access log IP logging
- [ ] T021 [P] [US1] Implement client `src/etelemetry/errors.py` — `BadVersionError(RuntimeError)`
- [ ] T022 [P] [US1] Implement client `src/etelemetry/config.py` — `resolve_url(server_url=None)` with basic precedence: `ETELEMETRY_URL` env → hardcoded default; `NO_ET` check
- [ ] T023 [US1] Implement client `src/etelemetry/client.py` — `get_project(repo, **kwargs)` and `check_available_version(project, version, lgr, raise_exception)` per contracts/api.md; use `requests` with 5s timeout; send `?ci=` and `?v=` params
- [ ] T024 [US1] Implement client `src/etelemetry/__init__.py` — export `get_project`, `check_available_version`, `BadVersionError`, `__version__`
- [ ] T025 [US1] Write client unit tests in `tests/unit/test_client.py` — mock server responses, verify outdated warning, bad version critical warning, `BadVersionError` raise, `NO_ET` disables requests
- [ ] T026 [US1] Run contract and integration tests, verify all pass

**Checkpoint**: Core version-check loop fully functional. Client and server independently testable.

---

## Phase 4: User Story 2 — Configurable Server URL (Priority: P2)

**Goal**: Client supports custom server URL via function param, env var, or package-level default

**Independent Test**: Configure client with custom URL, verify it contacts that URL instead of default

### Implementation for User Story 2

- [ ] T027 [US2] Update `src/etelemetry/config.py` — add `default_url` module-level attribute, add `server_url` param support to `resolve_url()`, document full precedence chain (param → env → default_url → hardcoded)
- [ ] T028 [US2] Update `src/etelemetry/client.py` — add `server_url` optional parameter to `get_project()` and `check_available_version()`, pass through to `resolve_url()`
- [ ] T029 [US2] Write tests in `tests/unit/test_config.py` — verify precedence: param > env var > `config.default_url` > hardcoded default; verify `NO_ET` short-circuits
- [ ] T030 [US2] Write integration test in `tests/integration/test_custom_url.py` — start two mock servers, verify client routes to correct one based on config

**Checkpoint**: Client configurable URL working. Backward compatible — no existing code breaks.

---

## Phase 5: User Story 3 — Data Migration from MongoDB (Priority: P3)

**Goal**: One-time migration tool imports all historical MongoDB data into PostgreSQL, stripping IPs

**Independent Test**: Export sample MongoDB data, run migration, verify records in PostgreSQL with no IPs, aggregated stats match

### Tests for User Story 3

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T031 [US3] Write migration test in `server/tests/integration/test_migration.py` — use sample MongoDB fixture data (JSON), run migration against testcontainers PostgreSQL, verify: all valid records imported, no IP fields in DB, duplicate handling, malformed record skipping with warning log, storage size comparison (SC-003)

### Implementation for User Story 3

- [ ] T032 [US3] Implement migration tool in `tools/migrate.py` — CLI with `--mongo-uri` and `--pg-uri` args; connect to MongoDB `et` database; iterate `requests` + `geo` collections; join on `remote_addr`; map fields per data-model.md migration mapping; insert into PostgreSQL using content-addressed dedup; strip all IP fields; log progress, warnings for malformed records; `--verify` flag to compare counts; add `pymongo` to server dev dependencies
- [ ] T033 [US3] Run migration test, verify pass

**Checkpoint**: Migration tool ready for production use against EC2 MongoDB.

---

## Phase 6: User Story 4 — Web Dashboard (Priority: P4)

**Goal**: Server-rendered dashboard with interactive map (drill-down), summary table, version distribution, time-period filtering, WCAG 2.1 AA accessible

**Independent Test**: Seed DB with sample data, open dashboard, verify per-project stats, map drill-down, time filtering, accessibility audit

### Tests for User Story 4

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T034 [P] [US4] Write dashboard contract tests in `server/tests/contract/test_dashboard_api.py` — verify response shapes for stats, geo, and projects endpoints per contracts/api.md
- [ ] T035 [P] [US4] Write dashboard integration test in `server/tests/integration/test_dashboard.py` — seed DB with 12+ months of sample data, verify HTML pages render, API returns correct aggregated data, page loads within 3 seconds (SC-005)

### Implementation for User Story 4

- [ ] T036 [US4] Implement aggregation service in `server/src/etelemetry_server/services/aggregation.py` — tiered rollup job: compute daily/weekly/monthly aggregates from version_checks; configurable age thresholds; callable as background task or CLI command
- [ ] T037 [US4] Implement dashboard API routes in `server/src/etelemetry_server/routes/dashboard.py` — `GET /dashboard/api/projects` (project list with counts), `GET /dashboard/api/stats/{owner}/{repo}` (stats with time range + granularity params), `GET /dashboard/api/geo/{owner}/{repo}` (GeoJSON for Leaflet)
- [ ] T038 [P] [US4] Create dashboard base template in `server/src/etelemetry_server/dashboard/templates/base.html` — HTML skeleton with htmx (CDN), Leaflet.js (CDN), CSS for accessibility (skip links, focus indicators, sufficient contrast, responsive layout)
- [ ] T039 [US4] Create project list page template in `server/src/etelemetry_server/dashboard/templates/projects.html` — list all tracked projects with total check counts, link to detail; `GET /dashboard/` route serves this
- [ ] T040 [US4] Create project detail page template in `server/src/etelemetry_server/dashboard/templates/project_detail.html` — interactive Leaflet map (drill-down country→region→city via GeoJSON endpoint), summary table, version distribution chart, timeline; time-range filter via htmx partial updates
- [ ] T041 [US4] Add static JS in `server/src/etelemetry_server/dashboard/static/dashboard.js` — Leaflet map initialization, GeoJSON layer with click drill-down, htmx event handlers for filter updates
- [ ] T042 [US4] Run accessibility audit — verify WCAG 2.1 AA compliance: keyboard navigation, screen reader landmarks, color contrast, focus management; document results

**Checkpoint**: Dashboard fully functional with map, table, filtering, and accessibility.

---

## Phase 7: User Story 5 — Self-Hosted & AWS Deployment (Priority: P5)

**Goal**: Docker Compose deployment for self-hosting; GitHub Actions CI/CD for AWS

**Independent Test**: Docker Compose up on fresh machine, make version check, verify dashboard shows data. GitHub Actions workflow deploys to AWS.

### Implementation for User Story 5

- [ ] T043 [US5] Create `deploy/Dockerfile` — multi-stage build: uv install server package, copy GeoIP config, expose port 8000, entrypoint: alembic upgrade + uvicorn
- [ ] T044 [P] [US5] Create `deploy/docker-compose.yml` — services: postgres (16-alpine, volume for data), server (build from Dockerfile, depends_on postgres, env from .env), nginx (reverse proxy, port 80/443), geoipupdate (MaxMind DB updates, shared volume with server)
- [ ] T045 [P] [US5] Create `deploy/nginx.conf` — reverse proxy to server:8000, strip IP from access logs (custom log format replacing $remote_addr with "-"), HTTPS config placeholder
- [ ] T046 [US5] Create `deploy/allowlist.yml` — sample allowlist with a few sensein projects, documented format
- [ ] T047 [P] [US5] Create `deploy/geoipupdate.conf` — MaxMind GeoIP update config template with license key placeholder
- [ ] T048 [US5] Create `.github/workflows/ci.yml` — on PR: checkout, uv setup, install deps, run ruff lint, run pytest (client tests + server tests with testcontainers), upload coverage; generate and commit `uv.lock`
- [ ] T049 [US5] Create `.github/workflows/deploy.yml` — on push to main: build Docker image, push to registry, SSH deploy to AWS EC2 (or use docker context), run alembic migrations, restart services; secrets: AWS credentials, server host, MaxMind key
- [ ] T050 [US5] Test Docker Compose deployment locally — `docker compose up`, verify all services healthy, make version check request, verify dashboard accessible
- [ ] T051 [US5] Test GitHub Actions CI workflow — push branch, verify checks pass

**Checkpoint**: Deployment fully automated. Self-hosted and AWS paths both working.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Code review, documentation, IP audit, end-to-end validation

- [ ] T052 Code abstraction review — identify duplicated logic across server services and extract to shared utilities per constitution Principle V
- [ ] T053 [P] IP audit — grep entire codebase and database schema for any IP storage or logging; verify nginx logs strip IPs; verify uvicorn logs strip IPs; verify no IP in version_checks table; document audit results
- [ ] T054 [P] Update `docs/vision.md` with final architectural direction and scope
- [ ] T055 Update `docs/phase-log.md` with entries for all completed phases
- [ ] T056 Update `docs/rebuild-spec.md` — comprehensive specification sufficient to rebuild from scratch per constitution Principle VI
- [ ] T057 Run `quickstart.md` validation — follow every step in quickstart.md on a clean checkout, verify all commands succeed
- [ ] T058 [P] Run full test suite (`uv run pytest`) and verify all tests pass
- [ ] T059 Performance validation — load test with ~1,650 req/min sustained, verify <2s response, verify content-addressed dedup reduces row count as expected, verify storage is at least 50% smaller than MongoDB equivalent (SC-003)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 completion — BLOCKS all user stories
- **US1 (Phase 3)**: Depends on Phase 2 — core functionality
- **US2 (Phase 4)**: Depends on Phase 3 (client library exists)
- **US3 (Phase 5)**: Depends on Phase 2 (database schema exists)
- **US4 (Phase 6)**: Depends on Phase 3 (version_checks data exists to aggregate)
- **US5 (Phase 7)**: Depends on Phase 3 (server functional to deploy)
- **Polish (Phase 8)**: Depends on all desired user stories complete

### User Story Dependencies

- **US1 (P1)**: After Phase 2 — no story dependencies
- **US2 (P2)**: After US1 (extends client.py created in US1)
- **US3 (P3)**: After Phase 2 — independent of US1 (only needs schema)
- **US4 (P4)**: After US1 (needs version_checks data to display)
- **US5 (P5)**: After US1 (needs functional server to containerize)

### Parallel Opportunities

After Phase 2 completes:
- US1 can start immediately (critical path)
- US3 can start in parallel with US1 (only needs DB schema, not server routes)

After US1 completes:
- US2, US4, US5 can all start in parallel

### Within Each User Story

- Tests written first and MUST fail before implementation
- Models/services before routes
- Core implementation before integration/polish

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: Test end-to-end version check
5. Deploy/demo if ready

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. US1 → Core version check working → Deploy (MVP!)
3. US2 → Configurable URLs → Deploy
4. US3 → Historical data migrated
5. US4 → Dashboard live → Deploy
6. US5 → Automated deployment
7. Polish → Production-ready

### Parallel Execution Example

```bash
# After Phase 2 completes, launch in parallel:
Agent A: US1 (version check — critical path)
Agent B: US3 (migration tool — only needs DB schema)

# After US1 completes, launch in parallel:
Agent A: US2 (configurable URL — extends client)
Agent B: US4 (dashboard — needs version_checks data)
Agent C: US5 (deployment — needs functional server)
```

---

## Notes

- [P] tasks = different files, no dependencies on incomplete tasks
- [Story] label maps task to specific user story for traceability
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Constitution compliance: uv for all Python work, secrets via .env, conventional commits
