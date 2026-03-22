# etelemetry Vision

**Last updated**: 2026-03-22 (post-implementation)

## Purpose

etelemetry provides a lightweight telemetry service that allows software
packages to check for available version updates and known bad versions at
runtime. It informs users when they are running outdated or faulty software
while collecting privacy-preserving usage statistics (city/state-level
geolocation, no IP addresses stored).

## Scope

- **Client library**: Installable Python package (`etelemetry`) that
  downstream projects integrate to check versions at runtime.
- **Server**: FastAPI-based service that resolves versions from GitHub,
  records usage with content-addressed deduplication, and serves a web
  dashboard.
- **Dashboard**: Server-rendered (Jinja2 + htmx + Leaflet.js) web UI
  showing per-project usage statistics with interactive geographic maps.
- **Deployment**: Docker Compose for self-hosting; GitHub Actions for
  automated AWS deployment.

## Architectural Direction

- Monorepo combining client and server (previously separate repos).
- PostgreSQL replaces MongoDB for efficient storage and aggregation.
- MaxMind GeoLite2 for local, fast (<10ms) geolocation — no external API.
- Content-addressed deduplication reduces ~1M pings/week to thousands of
  unique rows.
- Repository allowlist controls which projects are tracked.
- Configurable server URL enables multi-instance deployments.

## Non-Goals (this iteration)

- Support for non-GitHub source forges (GitLab, etc.).
- Authentication for dashboard read access.
- Real-time streaming or WebSocket updates.
