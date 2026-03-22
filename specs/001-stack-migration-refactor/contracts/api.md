# API Contracts: etelemetry

**Date**: 2026-03-22
**Branch**: `001-stack-migration-refactor`

## Server API (HTTP)

Base URL: `https://{host}/`

All responses use `Content-Type: application/json` unless noted.
Compression: gzip/brotli negotiated via `Accept-Encoding`.

### GET /

Health check and server info.

**Response** `200 OK`:
```json
{
  "name": "etelemetry",
  "version": "2.0.0"
}
```

### GET /projects/{owner}/{repo}

Version check endpoint. Records usage (content-addressed dedup).

**Path parameters**:
- `owner` (string): GitHub org or user
- `repo` (string): Repository name

**Query parameters** (optional, sent by client automatically):
- `ci` (boolean): Whether client is in CI environment
- `v` (string): Client's current version

**Response** `200 OK` (project on allowlist, version resolved):
```json
{
  "version": "1.4.2",
  "bad_versions": ["1.1.0", "1.2.3"]
}
```

**Response** `200 OK` (project on allowlist, version unknown/cached stale):
```json
{
  "version": null,
  "bad_versions": []
}
```

**Response** `404 Not Found` (project not on allowlist):
```json
{
  "error": "project not tracked"
}
```

**Response** `400 Bad Request` (malformed identifier):
```json
{
  "error": "invalid project identifier"
}
```

### GET /dashboard/

Web dashboard (HTML). Serves the main dashboard page.

**Response** `200 OK`: HTML page with embedded htmx + Leaflet.js.

### GET /dashboard/api/stats/{owner}/{repo}

Dashboard data endpoint for a specific project.

**Query parameters**:
- `from` (date, ISO 8601): Start of time range
- `to` (date, ISO 8601): End of time range
- `granularity` (string): `daily`, `weekly`, `monthly` (default: auto)

**Response** `200 OK`:
```json
{
  "project": "nipy/nipype",
  "period": {"from": "2026-01-01", "to": "2026-03-22"},
  "total_checks": 142857,
  "by_version": [
    {"version": "1.8.6", "count": 80000},
    {"version": "1.9.0", "count": 62857}
  ],
  "by_location": [
    {
      "country": "United States",
      "country_code": "US",
      "region": "Massachusetts",
      "city": "Cambridge",
      "lat": 42.36,
      "lon": -71.06,
      "count": 15000
    }
  ],
  "timeline": [
    {"period": "2026-W01", "count": 10204}
  ]
}
```

### GET /dashboard/api/geo/{owner}/{repo}

GeoJSON endpoint for map visualization.

**Query parameters**: Same as stats endpoint.

**Response** `200 OK`: GeoJSON FeatureCollection with point features
per location, `count` in properties. Used by Leaflet.js for map rendering.

### GET /dashboard/api/projects

List all tracked projects with summary counts.

**Response** `200 OK`:
```json
{
  "projects": [
    {"owner": "nipy", "repo": "nipype", "total_checks": 500000},
    {"owner": "nipy", "repo": "nibabel", "total_checks": 300000}
  ]
}
```

## Client Library API (Python)

Package: `etelemetry` (pip installable)

### Backward-compatible public API

```python
# Unchanged from current client
etelemetry.get_project(repo: str, **kwargs) -> dict
etelemetry.check_available_version(
    project: str,
    version: str,
    lgr: logging.Logger | None = None,
    raise_exception: bool = False,
) -> dict | None

class etelemetry.BadVersionError(RuntimeError): ...
```

### New: configurable server URL

Precedence (highest to lowest):
1. `server_url` parameter in `get_project()` / `check_available_version()`
2. `ETELEMETRY_URL` environment variable
3. Default URL (configurable at package level)

```python
# Via function parameter
etelemetry.get_project("nipy/nipype", server_url="https://my-instance.org/")

# Via environment variable
# export ETELEMETRY_URL=https://my-instance.org/

# Via package-level default (for library authors)
etelemetry.config.default_url = "https://my-instance.org/"
```

### Disable telemetry

```python
# Environment variable (unchanged)
# export NO_ET=1
```
