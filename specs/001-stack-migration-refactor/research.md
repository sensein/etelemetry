# Research: etelemetry Stack Migration

**Date**: 2026-03-22
**Branch**: `001-stack-migration-refactor`

## 1. Web Framework

**Decision**: FastAPI
**Rationale**: Largest community (4.5M+ daily downloads), automatic OpenAPI
docs, native async/await, Pydantic validation, first-class Jinja2 support
for the dashboard. Runs on Starlette — throughput is more than sufficient
for ~1,650 req/min sustained (SC-009). Single framework serves both the
API and dashboard.
**Alternatives considered**:
- Litestar: ~2x synthetic benchmarks but irrelevant at this scale; smaller
  community, fewer integrations.
- Starlette: Lower-level; would require manual validation, serialization,
  and OpenAPI generation.
- Sanic (current): Smaller ecosystem, no built-in OpenAPI, less momentum.

## 2. Database

**Decision**: PostgreSQL 16
**Rationale**: Content-addressed dedup (FR-004) maps directly to
`INSERT ... ON CONFLICT DO UPDATE SET count = count + 1`, atomic under
MVCC with row-level locking. Multiple Uvicorn workers write concurrently
without coordination. Aggregation queries (SC-005) benefit from mature
query planner, partial indexes, and materialized views for tiered
aggregation (FR-017). Docker Compose integration is trivial
(`postgres:16-alpine`). Storage efficiency vs MongoDB easily meets SC-003.
**Alternatives considered**:
- SQLite (WAL): Single-writer limitation. Under concurrent Uvicorn workers,
  would require application-level write serialization — added complexity
  violating Principle VIII.
- DuckDB: Excellent analytics but explicitly single-writer. Not designed
  for OLTP upsert workloads.

## 3. Geolocation

**Decision**: MaxMind GeoLite2 with `geoip2` Python library
**Rationale**: Industry standard for local IP geolocation. In-memory MMDB
lookups in microseconds (well under SC-002's 10ms target). Free with
registration; requires attribution and 30-day update cycle (automate via
`geoipupdate` in Docker entrypoint). Already assumed in spec.
**Alternatives considered**:
- IP2Location Lite: Lower accuracy for North American IPs, less mature
  Python library.
- DB-IP Lite: Smaller community, fewer accuracy studies, no advantage.

## 4. Dashboard

**Decision**: Server-rendered — Jinja2 + htmx + Leaflet.js
**Rationale**: No Node.js build step; single Python language stack.
Server-rendered HTML is inherently accessible (FR-010/WCAG). htmx (14KB)
handles partial page updates; Leaflet.js (~40KB) provides interactive map
with drill-down via `L.geoJSON` click handlers. FastAPI serves everything.
**Alternatives considered**:
- React/Vue SPA: Introduces Node.js toolchain, separate frontend project,
  state management. Doubles project complexity for a dashboard showing
  aggregate statistics. Violates Principle VIII.

## 5. HTTP Client (GitHub API)

**Decision**: httpx
**Rationale**: Modern async/sync dual API, HTTP/2 support, connection
pooling, configurable timeouts. API mirrors `requests` for familiarity.
Volume is low (few requests per cache-miss, at most hourly).
**Alternatives considered**:
- aiohttp: ~2x faster but irrelevant for cached GitHub calls. Async-only
  (no sync fallback for migration tool). Less intuitive API.

## 6. Response Compaction

**Decision**: HTTP compression (gzip/brotli) via `starlette-compress`
**Rationale**: Zero client-side changes — standard `Accept-Encoding`
negotiation handled transparently. Combined with minimal JSON (short field
names, `exclude_none=True` in Pydantic). Version-check payloads are small
(~100-200B) so per-request savings are modest, but dashboard pages benefit.
**Alternatives considered**:
- msgpack: Breaks backward compatibility (FR-008), requires client-side
  decoder. Marginal savings over compressed JSON for small payloads.

## 7. ORM / Database Access

**Decision**: SQLAlchemy 2.0 with asyncpg driver
**Rationale**: Async support via `create_async_engine`, mature migration
tooling (Alembic), composable query building for aggregation queries.
asyncpg is the fastest PostgreSQL driver for Python.
**Alternatives considered**:
- Raw asyncpg: Faster but loses migration tooling, requires manual SQL
  string management for complex aggregation queries.
- Tortoise ORM: Smaller community, less mature than SQLAlchemy 2.0.

## Summary

| Area | Decision | Key Reason |
|------|----------|------------|
| Web Framework | FastAPI | Community, OpenAPI, async, Jinja2 |
| Database | PostgreSQL 16 | MVCC upserts, aggregation, Docker |
| Geolocation | MaxMind GeoLite2 | Microsecond lookups, free, standard |
| Dashboard | Jinja2 + htmx + Leaflet.js | No build step, accessible, simple |
| HTTP Client | httpx | Modern async/sync, familiar API |
| Compression | gzip/brotli middleware | Standard HTTP, zero client changes |
| ORM | SQLAlchemy 2.0 + asyncpg | Async, Alembic migrations, mature |
