<!--
  Sync Impact Report
  ==================
  Version change: 0.0.0 (template) → 2026.03.22
  Modified principles: N/A (initial population from template)
  Added sections:
    - Principle I: Isolated Environments
    - Principle II: Secret Safety
    - Principle III: Git Discipline & Concurrency
    - Principle IV: Test-Driven with Real Use Cases
    - Principle V: Code Abstraction & Reuse
    - Principle VI: Provenance & Traceability
    - Principle VII: Living Documentation
    - Principle VIII: Simplicity
  Added sections (non-principle):
    - Development Workflow
    - Documentation & Provenance
  Removed sections: None
  Templates requiring updates:
    - .specify/templates/plan-template.md ✅ (Constitution Check already generic)
    - .specify/templates/spec-template.md ✅ (no constitution-specific refs)
    - .specify/templates/tasks-template.md ✅ (no constitution-specific refs)
    - .specify/templates/checklist-template.md ✅ (no constitution-specific refs)
  Follow-up TODOs: None
-->

# etelemetry Constitution

## Core Principles

### I. Isolated Environments

All development, testing, and CI execution MUST use `uv` or Docker to
create isolated Python environments. System Python MUST NOT be used
for any project task. Every spec, plan, and task MUST specify the
isolation method (e.g., `uv venv`, `uv run`, or a Dockerfile).

- Use `uv` as the default tool for local development and CI.
- Use Docker when reproducibility across platforms is required or
  when non-Python system dependencies are involved.
- `pyproject.toml` MUST be the single source of truth for
  dependencies; lock files MUST be committed.

### II. Secret Safety

No tokens, API keys, passwords, or credentials MUST be exposed in
terminal output, logs, CI artifacts, or committed to version control.

- All secrets MUST be loaded via `.env` files (using `python-dotenv`
  or equivalent) or environment variables injected at runtime.
- `.env` files MUST be listed in `.gitignore`.
- CI pipelines MUST use secret stores (e.g., GitHub Actions secrets),
  never inline values.
- Code review MUST verify that no secret is printed, logged, or
  hardcoded before merge.

### III. Git Discipline & Concurrency

Commits MUST be made frequently at meaningful checkpoints (after each
task, phase completion, or logical unit of work). Subagents and
parallel workers MUST coordinate to avoid file conflicts.

- Each subagent MUST operate on distinct files or use a file-locking
  protocol to prevent concurrent writes to the same file.
- Commit messages MUST follow conventional commits format
  (e.g., `feat:`, `fix:`, `docs:`, `refactor:`, `test:`).
- Branches MUST be used for features; `main` is protected.
- Before committing, subagents MUST pull latest changes and resolve
  conflicts rather than force-pushing.

### IV. Test-Driven with Real Use Cases

Every specification MUST conclude with real-use-case validation.
Tests MUST exercise actual user workflows, not just unit-level mocks.

- At the end of each specification phase, at least one real use case
  MUST be executed end-to-end and its result recorded.
- Integration and acceptance tests MUST use real data or realistic
  fixtures, not synthetic stubs, wherever feasible.
- Test results MUST be logged with timestamps and environment details
  for reproducibility.
- Red-Green-Refactor: tests MUST fail before implementation passes
  them.

### V. Code Abstraction & Reuse

Code MUST be reviewed after each phase to identify shareable functions
and patterns. Duplication across modules MUST be extracted into shared
utilities.

- After completing each user story or phase, a review pass MUST
  identify repeated logic and extract it into a shared module.
- Shared utilities MUST have their own tests.
- Abstraction MUST be justified by actual duplication (two or more
  call sites), not hypothetical future use.

### VI. Provenance & Traceability

The project MUST track the provenance of its own development process.
Every phase, decision, and significant change MUST be logged so that
the project can be reconstructed from its records.

- A phase log (`docs/phase-log.md`) MUST be maintained with dated
  summaries of each phase: what was done, key decisions, outcomes.
- Git history MUST serve as the authoritative record of code changes;
  commit messages MUST be descriptive enough to reconstruct intent.
- The final deliverable MUST include a comprehensive specification
  (`docs/rebuild-spec.md`) sufficient to rebuild the project from
  scratch without retracing exploratory paths.
- All AI-assisted decisions MUST be attributed in commit messages or
  phase logs.

### VII. Living Documentation

A vision document (`docs/vision.md`) MUST be created at project
inception and updated as the project unfolds. The constitution itself
MUST evolve: suggest amendments when best practices emerge from new
scenarios.

- `docs/vision.md` MUST capture project goals, scope, and
  architectural direction; it MUST be updated at each major phase
  boundary.
- Constitution amendments MUST be proposed when a new scenario
  reveals a gap or when an existing principle proves too rigid or
  too vague.
- All documentation MUST be kept in sync with the current state of
  the code; stale docs MUST be flagged during review.

### VIII. Simplicity

Start with the simplest solution that satisfies requirements. Avoid
premature abstraction, over-engineering, and speculative features.

- YAGNI: do not build features or infrastructure until a concrete
  need exists.
- Prefer flat project structures over deep nesting.
- Prefer standard library and well-maintained dependencies over
  custom implementations.

## Development Workflow

- **Environment setup**: Run `uv venv && uv pip install -e ".[dev]"`
  (or equivalent) as the first step of any development session.
  Docker Compose MAY be used for services with external dependencies.
- **Branch strategy**: Feature branches off `main`; PRs require
  passing CI and at least one review.
- **Commit cadence**: Commit after each completed task. Subagents
  MUST NOT batch unrelated changes into a single commit.
- **Locking protocol for subagents**: When multiple agents operate
  concurrently, each MUST claim a file manifest before writing.
  If two agents need the same file, they MUST serialize via a
  coordination mechanism (e.g., sequential task ordering or
  explicit handoff).
- **Code review**: Every PR MUST include a check for secret leaks,
  duplicated logic eligible for abstraction, and conformance to
  this constitution.

## Documentation & Provenance

- **Phase log** (`docs/phase-log.md`): Append a dated entry after
  each phase summarizing: objectives, actions taken, decisions made,
  outcomes, and any deviations from plan.
- **Vision document** (`docs/vision.md`): Initialize at project
  start; update at each major milestone or when scope changes.
- **Rebuild specification** (`docs/rebuild-spec.md`): Maintained
  continuously; by project completion it MUST be a standalone
  document sufficient to rebuild the system without access to
  conversation logs or exploratory history.
- **Constitution changelog**: Amendments to this constitution MUST
  be recorded in the phase log with rationale.

## Governance

This constitution is the supreme authority for project development
practices. All specifications, plans, tasks, and code reviews MUST
verify compliance with these principles.

- **Amendments**: Any team member or agent MAY propose an amendment.
  Amendments MUST include rationale and be recorded in the phase log.
  Breaking changes to principles require explicit user approval.
- **Versioning**: This constitution follows calendar versioning
  (CalVer) in `YYYY.MM.DD` format. If multiple amendments occur on
  the same day, append a dot-increment (e.g., `2026.03.22.1`).
- **Compliance review**: At each phase checkpoint, verify that all
  deliverables conform to the active constitution version. Non-
  compliance MUST be resolved before proceeding.
- **Evolution**: When a new scenario reveals a gap in this
  constitution, an amendment MUST be proposed rather than working
  around the gap silently.

**Version**: 2026.03.22 | **Ratified**: 2026-03-22 | **Last Amended**: 2026-03-22
