# Data Model: etelemetry

**Date**: 2026-03-22
**Branch**: `001-stack-migration-refactor`
**Storage**: PostgreSQL 16

## Entity Relationship

```text
AllowlistEntry 1──* Project 1──* VersionCheck
                                      │
                                      └── GeoLocation (embedded fields)

VersionCheck ──(aggregated into)──> UsageAggregate
```

## Tables

### projects

Allowlisted software projects tracked by etelemetry.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | SERIAL | PK | Internal ID |
| owner | VARCHAR(255) | NOT NULL | GitHub org/user |
| repo | VARCHAR(255) | NOT NULL | Repository name |
| latest_version | VARCHAR(100) | | Cached latest release |
| bad_versions | JSONB | DEFAULT '[]' | From .et file |
| cache_expires_at | TIMESTAMPTZ | | When to re-fetch |
| active | BOOLEAN | DEFAULT true | Allowlist flag |
| created_at | TIMESTAMPTZ | DEFAULT now() | |
| updated_at | TIMESTAMPTZ | DEFAULT now() | |

**Unique**: `(owner, repo)`
**Index**: `(owner, repo)` — primary lookup path

### version_checks

Content-addressed deduplicated usage records. Composite key ensures
one row per unique combination per time-bucket.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | BIGSERIAL | PK | Internal ID |
| project_id | INTEGER | FK → projects.id, NOT NULL | |
| version | VARCHAR(100) | NOT NULL | Client's reported version |
| city | VARCHAR(255) | | Resolved from IP at request time |
| region | VARCHAR(255) | | State/province |
| country | VARCHAR(100) | | Country name |
| country_code | CHAR(2) | | ISO 3166-1 alpha-2 |
| latitude | FLOAT | | Approximate |
| longitude | FLOAT | | Approximate |
| is_ci | BOOLEAN | DEFAULT false | CI environment flag |
| time_bucket | TIMESTAMPTZ | NOT NULL | Truncated to hour |
| count | INTEGER | DEFAULT 1 | Ping count in bucket |
| created_at | TIMESTAMPTZ | DEFAULT now() | |

**Unique**: `(project_id, version, city, region, country_code, is_ci, time_bucket)`
**Index**: `(project_id, time_bucket)` — dashboard queries
**Index**: `(time_bucket)` — aggregation job

**Content-address key**: The unique constraint is the content address.
On conflict: `SET count = count + 1`.

**No IP column**: IP addresses are never stored. Geolocation fields are
resolved transiently at request time and written directly.

### usage_aggregates

Pre-computed summaries for dashboard performance. Tiered granularity.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | BIGSERIAL | PK | |
| project_id | INTEGER | FK → projects.id, NOT NULL | |
| version | VARCHAR(100) | | NULL = all versions |
| country_code | CHAR(2) | | NULL = all countries |
| region | VARCHAR(255) | | NULL = all regions |
| granularity | VARCHAR(10) | NOT NULL | 'daily', 'weekly', 'monthly' |
| period_start | DATE | NOT NULL | Start of period |
| total_count | BIGINT | DEFAULT 0 | Sum of counts |
| unique_locations | INTEGER | DEFAULT 0 | Distinct city+region combos |
| ci_count | BIGINT | DEFAULT 0 | Subset from CI |
| created_at | TIMESTAMPTZ | DEFAULT now() | |

**Unique**: `(project_id, version, country_code, region, granularity, period_start)`
**Index**: `(project_id, granularity, period_start)` — dashboard range queries

### Aggregation Tiers (configurable defaults)

| Data age | Granularity | Source |
|----------|-------------|--------|
| < 30 days | daily | Computed from version_checks |
| 30 days – 1 year | weekly | Rolled up from daily |
| > 1 year | monthly | Rolled up from weekly |

A scheduled job (cron or background task) computes aggregates and
optionally compacts old version_checks rows into aggregates.

## State Transitions

### Project cache lifecycle

```text
STALE → FETCHING → CACHED (expires in 6h) → STALE
                 ↘ FETCH_FAILED (serve stale, retry later)
```

### Version check request flow

```text
Request arrives
  → Check allowlist (reject if not listed)
  → Resolve geolocation from IP (transient, not stored)
  → Discard IP
  → Upsert version_check (content-addressed)
  → Return cached project version + bad_versions
```

## Migration Mapping (MongoDB → PostgreSQL)

| MongoDB collection | MongoDB field | PostgreSQL table | PostgreSQL column |
|-------------------|---------------|-----------------|-------------------|
| requests | owner | projects | owner |
| requests | repository | projects | repo |
| requests | version | version_checks | version |
| requests | is_ci | version_checks | is_ci |
| requests | access_time | version_checks | time_bucket (truncated) |
| requests | remote_addr | — | DROPPED |
| geo | city | version_checks | city |
| geo | region_name | version_checks | region |
| geo | country_name | version_checks | country |
| geo | latitude | version_checks | latitude |
| geo | longitude | version_checks | longitude |
| geo | remote_addr | — | DROPPED |
