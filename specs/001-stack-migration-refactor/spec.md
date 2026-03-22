# Feature Specification: etelemetry Stack Migration & Monorepo Refactor

**Feature Branch**: `001-stack-migration-refactor`
**Created**: 2026-03-22
**Status**: Draft
**Input**: Combine etelemetry-server and etelemetry-client into a single monorepo, migrate from MongoDB/Sanic to a modern efficient stack, add privacy-preserving geolocation, a web dashboard, configurable server URLs, and data migration from the existing MongoDB instance.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Version Check at Runtime (Priority: P1)

A developer integrates etelemetry into their Python package. When a user runs
the package interactively, the client checks the etelemetry server for the
latest available version and any known bad versions. The user sees a warning
if they are outdated or using a faulty release. The server records the
check (project name, version, timestamp, city/state-level location) without
storing the user's IP address.

**Why this priority**: This is the core value proposition of etelemetry — the
fundamental check-and-inform loop. Without it, nothing else matters.

**Independent Test**: Deploy a local server instance, configure a client to
point at it, register a test project with a known latest version and a bad
version, then verify that (a) an outdated client receives an "update available"
warning, (b) a client on a bad version receives a critical warning, (c) the
server records the check with city/state geolocation, and (d) no IP address
is persisted in the database or logs.

**Acceptance Scenarios**:

1. **Given** a deployed etelemetry server with project "org/tool" at version
   2.0.0 and bad_versions ["1.1.0"], **When** a client running version 1.5.0
   checks in, **Then** the client receives a response containing
   `{"version": "2.0.0", "bad_versions": ["1.1.0"]}` and the server persists
   a usage record with city/state geolocation but no IP address.

2. **Given** a deployed etelemetry server, **When** a client running a version
   listed in bad_versions checks in, **Then** the client logs a CRITICAL
   warning and optionally raises `BadVersionError`.

3. **Given** a deployed etelemetry server, **When** a client running the latest
   version checks in, **Then** the client logs a DEBUG message and no warning
   is shown.

4. **Given** a client with `NO_ET=1` set, **When** the application starts,
   **Then** no request is made to the server.

---

### User Story 2 - Configurable Server URL (Priority: P2)

An organization wants to run their own etelemetry instance (e.g., on internal
infrastructure). They deploy the server with their own domain and configure
their packages' clients to point at it. Existing clients using the old
hardcoded domain continue to work during transition.

**Why this priority**: Decoupling from a hardcoded domain is essential for
adoption by other organizations and for migrating away from the current
`rig.mit.edu` endpoint.

**Independent Test**: Start two server instances on different URLs. Configure
one client to use instance A and another to use instance B. Verify each client
talks to its configured server. Verify a client with no explicit configuration
falls back to a sensible default.

**Acceptance Scenarios**:

1. **Given** a client with no custom configuration, **When** a version check
   is made, **Then** the client uses the default server URL.

2. **Given** a client configured with a custom server URL via environment
   variable, **When** a version check is made, **Then** the client contacts
   the custom server.

3. **Given** a project that embeds a server URL in its etelemetry integration
   code, **When** a version check is made, **Then** that URL takes precedence
   over the default.

---

### User Story 3 - Data Migration from Existing MongoDB (Priority: P3)

The etelemetry maintainer migrates historical usage data from the existing
MongoDB instance on EC2 to the new storage backend. After migration, all
previously recorded projects, version checks, and geolocation data are
queryable in the new system. IP addresses present in the old data are
dropped during migration.

**Why this priority**: Preserving historical data is important for continuity
but does not block new functionality. The migration can happen once the new
server is operational.

**Independent Test**: Export a sample of the existing MongoDB data, run the
migration tool, and verify that (a) all projects and their usage records
appear in the new database, (b) no IP addresses exist in the migrated data,
and (c) aggregated statistics match between old and new systems.

**Acceptance Scenarios**:

1. **Given** an existing MongoDB dump with records in the `requests` and `geo`
   collections, **When** the migration tool runs, **Then** all records are
   imported into the new storage with IP addresses stripped.

2. **Given** migrated data, **When** a user queries the dashboard for a
   project's historical usage, **Then** the results include pre-migration
   data.

3. **Given** a migration run, **When** the tool encounters malformed or
   incomplete records, **Then** it logs a warning, skips the record, and
   continues without aborting.

---

### User Story 4 - Web Dashboard for Usage Statistics (Priority: P4)

A project maintainer visits the etelemetry web dashboard to see how many
users are running their software, which versions are in use, and where
(city/state level) users are located. The dashboard shows summary statistics
over selectable time periods.

**Why this priority**: The dashboard is a valuable addition but is not required
for the core check-and-inform functionality to work. It can be built on top
of the data already collected by the server.

**Independent Test**: Seed the database with sample usage records spanning
multiple projects, versions, locations, and dates. Open the dashboard and
verify that (a) per-project usage counts are correct, (b) a geographic
summary shows city/state distribution, (c) time-period filters work, and
(d) the dashboard is accessible (keyboard-navigable, screen-reader friendly,
sufficient color contrast).

**Acceptance Scenarios**:

1. **Given** usage data for project "org/tool", **When** a maintainer visits
   the dashboard and selects "org/tool", **Then** they see total checks,
   version distribution, and an interactive map showing geographic
   distribution with drill-down capability (country → region → city)
   alongside a summary table with precise counts.

2. **Given** a dashboard with data, **When** a user selects a time range
   (e.g., last 7 days, last 30 days, custom range), **Then** all displayed
   statistics reflect only that period.

3. **Given** a dashboard, **When** accessed by a screen reader or navigated
   via keyboard only, **Then** all information is accessible and all controls
   are operable.

---

### User Story 5 - Self-Hosted Deployment (Priority: P5)

An organization deploys their own etelemetry instance using Docker Compose.
They configure their domain, bring up the service, and it is ready to accept
version checks from clients.

**Why this priority**: Self-hosting enables adoption beyond the original
maintainers but depends on the server and client being functional first.

**Independent Test**: Follow the deployment documentation to bring up an
instance using only Docker Compose on a fresh machine. Register a test
project, make a version check from a client, and verify the dashboard
displays the result.

**Acceptance Scenarios**:

1. **Given** a machine with Docker and Docker Compose installed, **When** a
   user follows the deployment guide, **Then** the etelemetry server, database,
   and dashboard are running and reachable.

2. **Given** a self-hosted instance, **When** a client is configured to point
   at it, **Then** version checks succeed and data appears in the dashboard.

---

### Edge Cases

- What happens when the GitHub API is rate-limited or unavailable? The server
  MUST return cached version data if available, or a graceful error indicating
  the version is unknown.
- What happens when the geolocation service is unavailable? The server MUST
  still record the usage check with location marked as "unknown" rather than
  failing the request.
- What happens when a client sends a malformed project identifier (e.g.,
  missing owner)? The server MUST return a clear error message with an
  appropriate status code.
- What happens when the database is unreachable? The server MUST still respond
  to version-check requests using cached data, even if it cannot record the
  usage event.
- What happens when the migration tool encounters duplicate records? It MUST
  deduplicate based on project + timestamp + location and log the duplicates.
- What happens when a project has no `.et` file? The server MUST return an
  empty bad_versions list rather than an error.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide an endpoint that, given a project
  identifier (owner/repo), returns the latest available version and a list
  of known bad versions.
- **FR-002**: The system MUST resolve the latest version by querying the
  project's source repository (GitHub releases, then tags as fallback).
- **FR-003**: The system MUST cache version lookups to avoid excessive
  upstream API calls, with a configurable cache duration (default: 6 hours).
- **FR-004**: The system MUST record each version-check event with: project
  identifier, checked version, timestamp, CI environment flag, and
  city/state-level geolocation.
- **FR-005**: The system MUST NOT persist IP addresses in the database or
  in application logs. IP addresses MUST be used only transiently for
  geolocation resolution and then discarded.
- **FR-006**: The system MUST resolve IP addresses to city/state-level
  geolocation as quickly and accurately as possible (local lookup preferred
  over external API calls).
- **FR-007**: The client library MUST allow the server URL to be configured
  via (in order of precedence): function parameter, environment variable,
  project-level configuration, then a default URL.
- **FR-008**: The client library MUST maintain backward compatibility with
  the existing public API (`get_project`, `check_available_version`,
  `BadVersionError`).
- **FR-009**: The system MUST provide a web dashboard showing per-project
  usage counts, version distribution, and geographic distribution via an
  interactive map with drill-down (country → region → city) and a
  companion summary table, with time-period filtering.
- **FR-010**: The dashboard MUST meet WCAG 2.1 AA accessibility standards.
- **FR-011**: The system MUST provide a migration tool that imports data
  from the existing MongoDB instance, stripping IP addresses during import.
- **FR-012**: The system MUST be deployable via Docker Compose with a single
  configuration file for domain, secrets, and service settings.
- **FR-013**: The system MUST serve both server and client from a single
  repository (monorepo) with the client installable as a standalone package.
- **FR-014**: The system MUST read bad_versions from the project's `.et`
  file in its source repository and include them in the version-check
  response.
- **FR-015**: The system MUST detect whether the client is running in a CI
  environment and include that flag in the usage record.
- **FR-016**: Web server access logs MUST strip or omit IP addresses before
  writing to disk.
- **FR-017**: The system MUST support tiered aggregation granularity that
  coarsens over time (e.g., daily for recent data, weekly as the standard
  granularity, monthly for older data). The age thresholds for each tier
  MUST be configurable.

### Key Entities

- **Project**: A software project tracked by etelemetry. Identified by
  owner/repo (e.g., "nipy/nipype"). Has a latest known version, a list of
  bad versions, and a cache timestamp.
- **VersionCheck**: A single check-in event. Captures project identifier,
  version reported by client, timestamp, CI flag, and resolved geolocation
  (city, state/region, country). No IP address.
- **GeoLocation**: City/state-level location derived from an IP address at
  request time. Stored as city, region, country, and approximate coordinates.
  Never linked to an IP.
- **UsageAggregate**: Pre-computed summary of version checks grouped by
  project, time period, version, and location. Aggregation granularity
  coarsens over time: daily for recent data, weekly as the standard
  granularity, and monthly for older data. The specific age thresholds
  for transitioning between granularities are configurable. Used by the
  dashboard for efficient querying.

### Assumptions

- The existing MongoDB data on EC2 is accessible via a standard `mongodump`
  export or direct connection during migration.
- GitHub remains the primary source for version and bad_versions data; other
  source forges (GitLab, etc.) are out of scope for this iteration.
- A local IP-to-geolocation database (e.g., MaxMind GeoLite2) is acceptable
  and preferred over an external API for speed and privacy.
- The default server URL will be updated from `rig.mit.edu` to a new domain
  to be determined; the old domain will redirect during a transition period.
- The dashboard does not require authentication for read access to aggregated
  statistics (no individual-user data is exposed).
- Individual version-check records are retained indefinitely (IPs are never
  stored). Aggregation granularity coarsens over time (daily → weekly →
  monthly) to balance query performance with storage efficiency. Weekly is
  the standard useful granularity.

## Clarifications

### Session 2026-03-22

- Q: What is the data retention policy for version-check records? → A: Keep
  all records indefinitely (only IPs are discarded). Introduce tiered
  aggregation granularity that coarsens over time; weekly is the useful
  baseline granularity.
- Q: What type of geographic visualization for the dashboard? → A: Interactive
  map with drill-down (country → region → city) plus a summary table with
  precise counts.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A version check from client to server completes in under
  2 seconds under normal conditions (cached version data).
- **SC-002**: Geolocation resolution adds no more than 10 milliseconds to
  request processing time (local database lookup).
- **SC-003**: The new storage backend uses at least 50% less disk space than
  the equivalent MongoDB data for the same record count.
- **SC-004**: The migration tool successfully imports 100% of valid records
  from the existing MongoDB, with zero IP addresses in the new database.
- **SC-005**: The dashboard loads project statistics for any project within
  3 seconds, even with 12+ months of historical data.
- **SC-006**: The dashboard passes automated accessibility audits (e.g.,
  axe-core) with zero critical or serious violations.
- **SC-007**: A new self-hosted instance can be brought up from scratch in
  under 15 minutes following the deployment guide.
- **SC-008**: All existing client integrations (`get_project`,
  `check_available_version`, `BadVersionError`) continue to work without
  code changes in downstream projects (backward compatibility).
- **SC-009**: The system handles at least 100 concurrent version-check
  requests without degradation.
