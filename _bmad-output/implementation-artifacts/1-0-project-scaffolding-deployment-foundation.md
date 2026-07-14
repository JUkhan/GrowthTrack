---
baseline_commit: 70094c216185a946cd2f876d2e7b3aba19437386
---

# Story 1.0: Project Scaffolding & Deployment Foundation

Status: in-progress

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer setting up GrowthTrack,
I want the source tree, Docker Compose deployment topology, and baseline database migration stood up exactly as the Architecture spine specifies,
so that every other story — in this epic and every epic after it — has a working, deployable foundation to build on, rather than each one improvising its own.

## Acceptance Criteria

1. **Given** a fresh repository checkout, **when** the project is scaffolded, **then** the source tree matches the Architecture spine's structure exactly: `api/`, `domain/`, `ports/`, `adapters/whatsapp_twilio/`, `adapters/source_system/`, `adapters/persistence/`, `scheduler/`, `web/`, `alembic/`, `tests/`, `docker/` — with `domain/` importing only from `ports/`, per AD-1. [Source: ARCHITECTURE-SPINE.md#AD-1, #Source tree]
2. **Given** the Docker Compose topology, **when** it is defined, **then** it includes an API container, a **separate** scheduler container, PostgreSQL, and an Nginx reverse proxy terminating TLS (pinned ≥1.30.1 stable / ≥1.31.0 mainline, per CVE-2026-42945) — staging and production run the identical topology. [Source: ARCHITECTURE-SPINE.md#AD-5]
3. **Given** any container in the compose topology, **when** it is defined, **then** it declares a health check and a `restart: always` policy. [Source: ARCHITECTURE-SPINE.md#AD-10]
4. **Given** the API service, **when** it starts, **then** it exposes a `/health` liveness endpoint suitable for polling by an external uptime monitor. [Source: ARCHITECTURE-SPINE.md#AD-10]
5. **Given** the database layer, **when** it is provisioned, **then** Alembic is initialized with a baseline migration, and PostgreSQL is backed up via an automated daily dump to off-host storage. [Source: ARCHITECTURE-SPINE.md#AD-10]
6. **Given** the repository, **when** code is pushed, **then** a CI pipeline runs linting, type checks, and the automated test suite, blocking merge on failure — the specific CI provider is an implementation choice, not fixed by the Architecture spine. [Source: epics.md#Story 1.0]
7. **Given** this story is complete, **when** any later story in any epic begins implementation, **then** it builds directly on this source tree and deployment topology — no later story re-establishes project structure, container topology, or CI configuration. [Source: epics.md#Story 1.0]

## Tasks / Subtasks

- [x] Task 1: Scaffold the backend source tree per the Architecture spine (AC: #1)
  - [x] Create `api/`, `domain/`, `ports/`, `adapters/whatsapp_twilio/`, `adapters/source_system/`, `adapters/persistence/`, `scheduler/`, `alembic/`, `tests/` as Python packages
  - [x] Set up `pyproject.toml` pinned to: Python 3.13+, FastAPI 0.139.0, Pydantic v2 (bundled), SQLAlchemy 2.0.51, Alembic 1.18.5, PyJWT 2.13.0, pwdlib (bcrypt backend — **not** passlib), APScheduler 3.11.3, Twilio Python SDK 9.10.9
  - [x] Add a `pydantic-settings`-based typed config object reading environment variables — no scattered `os.environ` calls anywhere (Consistency Conventions)
  - [x] Add an import-boundary lint contract (e.g. `import-linter`) enforcing AD-1: `domain/` may import `ports/` only, never any `adapters/*` package or a Twilio/SQLAlchemy type in a `domain/` function signature — wire this into Task 5's CI lint step so an AD-1 violation fails the build, not just a code-review convention
  - [x] Scaffold `web/` as a React 19.2.7 + MUI (`@mui/material`) 9.2.0 app using Vite (current standard for React 19 — Create React App is long deprecated); this story stands up the app shell only, not Story 1.6's design tokens
  - [x] Add Vitest + React Testing Library to `web/` with one smoke test (e.g. the app shell renders) — Task 5's CI test step assumes this exists; without it there is nothing for the frontend CI step to run
- [x] Task 2: Define the Docker Compose deployment topology (AC: #2, #3)
  - [x] Write one `docker-compose.yml` under `docker/` covering API, scheduler, PostgreSQL, and Nginx — reused as-is by local dev, staging, and production; environment variance is env-var injection only (secrets, connection targets), never a second/third compose file (AD-5)
  - [x] Every service declares a `healthcheck` and `restart: always`
  - [x] Nginx: terminate TLS, redirect all HTTP → HTTPS, pin the image to an exact tag ≥1.30.1 (stable) or ≥1.31.0 (mainline) — do **not** use a floating `nginx:stable`/`nginx:latest` tag, since a stale cached pull could still resolve to a pre-CVE-2026-42945 version
  - [x] Document required environment variables in a committed `.env.example` (Twilio credentials, JWT signing key, DB credentials) — actual values are never committed
- [x] Task 3: Add the `/health` liveness endpoint (AC: #4)
  - [x] FastAPI route in `api/` returning a simple liveness signal, no auth required, suitable for an external uptime monitor to poll
- [x] Task 4: Provision the database layer (AC: #5)
  - [x] Wire Alembic's `env.py` to the SQLAlchemy engine/settings
  - [x] Generate one baseline migration that establishes Alembic's version-tracking table — **do not** create `User`, `SalesData`, `Notification`, etc. tables here; each entity's table belongs to the story that first needs it (e.g. Story 1.1 adds `User`, Story 2.1 adds `SalesData`/`BrandPerformance`/`Doctor`), added as new revisions on this same chain, never a second `alembic init`
  - [x] Use two Postgres roles, not one shared credential: a migration-capable (DDL) role for Alembic and a runtime DML-only role for the API/scheduler containers — closes an open Medium-severity architecture-review gap (least-privilege DB credentials) cheaply, while it's still free to do at scaffolding time
  - [x] Add an automated daily `pg_dump` job (compose service or scheduled script) writing to off-host storage — retention period is explicitly deferred, do not invent one
- [x] Task 5: Stand up the CI pipeline (AC: #6)
  - [x] GitHub Actions workflow (repo origin is `github.com/JUkhan/GrowthTrack`) running, on every push/PR: lint (`ruff` for Python, `eslint` for `web/`), type-check (`mypy` or `pyright` for Python, `tsc` for `web/`), test suite (`pytest` for Python, `vitest`/React Testing Library for `web/`)
  - [x] Pipeline blocks merge on any step failing
  - [x] Add a minimal real test (e.g. a `pytest` hitting `/health`) so the pipeline exercises something real on day one, not an empty placeholder
  - [x] Add a secret-scanning step (e.g. `gitleaks`) plus `.gitignore` coverage for `.env`/`.env.*` files — closes an open Low-severity architecture-review gap (no enforcement behind the "secrets never committed" rule)
- [x] Task 6: Guardrail note for future stories (AC: #7)
  - [x] Add a short repo-root note (README or CONTRIBUTING) stating the source tree, Compose topology, and CI configuration are fixed by this story — no later story re-scaffolds them

### Review Findings

- [x] [Review][Defer] Backup writes to a local Docker volume, not off-host storage (AC5) [docker/docker-compose.yml:92-115, docker/backup/pg_dump_daily.sh] — deferred, pre-existing (blocked on hosting provider decision)
- [x] [Review][Patch] Backup pipeline can silently produce empty/corrupt dumps with the healthcheck still reporting healthy [docker/backup/pg_dump_daily.sh:14-19]
- [x] [Review][Patch] Two-role least-privilege DB setup (init-roles.sh) has zero CI coverage [.github/workflows/ci.yml:16-29]
- [x] [Review][Patch] Neither Dockerfile is built in CI — broken builds only surface at deploy time [.github/workflows/ci.yml]
- [x] [Review][Patch] Backup job authenticates as the DDL-capable migrator role instead of a dedicated read-only role [docker/docker-compose.yml:92-99]
- [x] [Review][Patch] AD-1 import-linter contract doesn't forbid domain/ports from importing third-party SDK packages (sqlalchemy, twilio) directly, only this repo's own adapters/api/scheduler packages [pyproject.toml:60-65]
- [x] [Review][Patch] config.py's DSN builder doesn't URL-escape credentials — a password with @, :, /, or % breaks the connection string [config.py:41-54]
- [x] [Review][Patch] docker/backend.Dockerfile runs api/scheduler containers as root — no USER directive [docker/backend.Dockerfile]
- [x] [Review][Patch] scheduler/main.py has no SIGTERM handler — a redeploy kills the process immediately instead of shutting down gracefully [scheduler/main.py:30-33]
- [x] [Review][Patch] No CORS middleware on the FastAPI app — will block the next story's frontend-to-API calls from the Vite dev server [api/main.py]
- [x] [Review][Patch] No security headers (HSTS, X-Content-Type-Options, X-Frame-Options) on nginx.conf, notable since /webhooks/ is unauthenticated and internet-facing [docker/nginx/nginx.conf]
- [x] [Review][Patch] alembic/env.py unconditionally requires JWT/Twilio settings (no defaults) to run any migration [alembic/env.py:23-24]
- [x] [Review][Patch] Nothing in the compose topology runs `alembic upgrade head` automatically — api/scheduler start against whatever schema state already exists [docker/docker-compose.yml:40-71]
- [x] [Review][Patch] CI's mypy invocation omits alembic/env.py, which has real logic (sys.path manipulation, settings access) [.github/workflows/ci.yml:59]
- [x] [Review][Patch] Dependency pinning is inconsistent with the story's "use these exact versions" framing (some `>=`, some `==`; frontend uses caret ranges) [pyproject.toml:5-16, web/package.json]
- [x] [Review][Patch] Nginx's /health location matches by prefix, not exact path [docker/nginx/nginx.conf:30-34]
- [x] [Review][Patch] init-roles.sh interpolates the app password directly into a SQL string — a password containing a single quote breaks CREATE ROLE [docker/postgres/init-roles.sh:9]
- [x] [Review][Defer] GET /health reports liveness only, not DB readiness [api/routes/health.py] — deferred, pre-existing (satisfies AC4's literal wording; matters once a DB-backed route exists)
- [x] [Review][Defer] Nginx only proxies /health and /webhooks/ — future backend routes need a new location block added by hand [docker/nginx/nginx.conf] — deferred, pre-existing
- [x] [Review][Defer] create_engine()/create_session_factory() have no singleton caching [adapters/persistence/database.py:22-24] — deferred, pre-existing (currently unreachable, nothing calls it yet)
- [x] [Review][Defer] Postgres bound to 127.0.0.1:5432 on the host in all three environments via the shared compose file [docker/docker-compose.yml:27-28] — deferred, pre-existing (contingent on undecided hosting/infra layout)
- [x] [Review][Defer] init-roles.sh only runs once via docker-entrypoint-initdb.d — a disaster-recovery restore onto a fresh volume needs it re-run manually [docker/postgres/init-roles.sh] — deferred, pre-existing

## Dev Notes

- **This is the first story in the project — the repository currently contains only planning documents (`_bmad-output/`, `docs/`, SRS files) and no application code.** There is nothing to preserve or avoid breaking; everything under `api/`, `domain/`, `ports/`, `adapters/`, `scheduler/`, `web/`, `alembic/`, `tests/`, `docker/` is net-new.
- **Architecture paradigm:** hexagonal (ports & adapters). `domain/` has zero inbound framework dependency and zero outbound driver/SDK imports — it depends on `ports/` only. `api/` and `scheduler/` are inbound adapters calling into `domain/`; `adapters/whatsapp_twilio/`, `adapters/source_system/`, `adapters/persistence/` are outbound adapters implementing `ports/`. No arrow points from `domain/` to any `adapters/*` package — this absence is AD-1's rule, and it is why Task 1 wires an automated import-boundary check rather than relying on reviewer vigilance. [Source: ARCHITECTURE-SPINE.md#AD-1]
- **This story only stands up structure, not features.** Story 1.1 (Administrator Login) is the first story to add a `User` table/migration and real `api/` routes; Story 1.6 is the first to apply brand design tokens to `web/`. Do not pull either forward into this story.
- **Baseline migration scope is deliberately minimal.** "Baseline migration" means an empty-schema Alembic revision that proves the migration chain works end-to-end (upgrade/downgrade), not a pre-creation of the eventual data model. `entities.md`/AD-4/AD-11 define what tables eventually exist, but each is added by the story that needs it.
- **Docker Compose topology (AD-5):** API container, a **separate** scheduler container/process (a web-tier crash or redeploy must never silently drop a scheduled run — this is *why* it's a separate container, not a thread in the API process), PostgreSQL, Nginx in front of both the API and the webhook endpoint. Nginx terminates TLS and redirects all HTTP to HTTPS — this is the concrete mechanism satisfying the PRD's "all communication over HTTPS" NFR, so it must actually be configured, not left to "Nginx is in the topology somewhere." Staging and production run the **identical** compose topology; local dev reuses the same compose file — differences are env-var-injected secrets/connection targets only. [Source: ARCHITECTURE-SPINE.md#AD-5]
- **Nginx version floor is a real, live security requirement, not a formality.** CVE-2026-42945 ("NGINX Rift") is an unauthenticated heap-buffer-overflow in `ngx_http_rewrite_module`, RCE-capable on hosts with ASLR disabled, affecting nginx through 1.30.0 / NGINX Plus through R36, fixed only at 1.30.1 (stable) / 1.31.0 (mainline) / R36-1. Nginx sits directly in front of the unauthenticated Twilio webhook endpoint in this topology, so pin an exact patched version tag in the Dockerfile/compose — a floating tag risks silently resolving to a pre-fix build. [Source: ARCHITECTURE-SPINE.md#AD-5, reviews/review-version-check.md Finding 2]
- **Operational envelope (AD-10):** every container needs a health check + `restart: always` — this is the concrete definition of "automatic recovery after failures," not a vague ops aspiration. PostgreSQL gets an automated daily dump to off-host storage (retention period is an open question — do not invent a number). The API's `/health` endpoint is polled by an external uptime monitor (vendor not yet chosen — out of scope here). [Source: ARCHITECTURE-SPINE.md#AD-10]
- **Least-privilege DB credentials (Task 4).** The Architecture spine's AD-5 states DB credentials are env-var-injected but doesn't itself distinguish a migration role from a runtime role — an unresolved Medium-severity finding from the architecture's own security review. Splitting into two Postgres roles now costs nothing structurally and is far cheaper than retrofitting later once every story is writing against one shared credential. [Source: reviews/review-security-compliance.md Finding 3.3]
- **Secret-scanning / `.gitignore` (Task 5).** Same review flagged (Low severity) that "secrets are never committed" is stated as a rule with no enforcement backing it. A CI secret-scan step plus `.env*` gitignore coverage is the cheap fix, and this scaffolding story is the only place it can be added before any secret-bearing file could ever be committed. [Source: reviews/review-security-compliance.md Finding 3.4]
- **CI provider and test frameworks are explicitly *not* fixed by the Architecture spine** (epics.md Story 1.0 AC6 says so directly) — GitHub Actions is recommended only because the repo's origin remote is already `github.com/JUkhan/GrowthTrack`; `pytest`/`ruff`/`mypy` and `vitest`/`eslint`/`tsc` are recommended as the current (2026) idiomatic choices for this exact stack, not an architecture mandate. Pick these unless you have a specific reason not to — consistency here matters more than the specific tool, since every later story's CI step builds on whatever this story establishes.
- **Stack versions are independently web-verified as current for 2026-07-14**, not asserted from training-data memory — an adversarial review queried PyPI/npm JSON APIs and vendor pages directly for every pinned version in the table below and found no fabrication or staleness. Use these exact versions. [Source: reviews/review-version-check.md]

  | Layer | Package | Version |
  | --- | --- | --- |
  | Language | Python | 3.13+ (3.12 is security-only maintenance as of 2026) |
  | Backend framework | FastAPI | 0.139.0 |
  | Validation | Pydantic | v2 (bundled with FastAPI 0.139) |
  | ORM | SQLAlchemy | 2.0.51 |
  | Migrations | Alembic | 1.18.5 |
  | Database | PostgreSQL | 18.4 |
  | Auth tokens | PyJWT | 2.13.0 |
  | Password hashing | pwdlib (bcrypt backend) | latest — **not** passlib (unmaintained; FastAPI's own docs now recommend pwdlib) |
  | Scheduling | APScheduler | 3.11.3 (the only production-ready line — 4.0 is alpha-only) |
  | WhatsApp SDK | Twilio Python SDK | 9.10.9 |
  | Frontend | React | 19.2.7 |
  | UI library | MUI (`@mui/material`) | 9.2.0 |
  | Reverse proxy | Nginx | ≥1.30.1 (stable) / ≥1.31.0 (mainline) |
  | Containers | Docker / Docker Compose | current stable (deliberately unpinned — both projects rev too fast to pin usefully) |

- **Explicitly out of scope / deferred — do not add in this story:** Redis/Celery (Postgres + APScheduler is the Phase 1 choice — AD-2), a dedicated secrets manager (env vars suffice at this scale), concrete hosting provider or monitoring/alerting vendor selection, backup/data retention period values, and Bangladesh PDPA hosting-region decisions. [Source: ARCHITECTURE-SPINE.md#Deferred]
- **Naming/logging conventions to establish now** (apply from this story forward): REST paths are plural-noun resources; DB tables `snake_case`, API schemas `PascalCase`; all entity ids UUIDv4; timestamps stored/transmitted as ISO 8601 UTC only (Asia/Dhaka conversion happens at presentation edges only, in later stories); one error envelope `{error:{code,message,details}}`; structured JSON logging with a correlation/request id threaded end-to-end. Scaffold logging/config/error-envelope conventions now so no later story invents its own. [Source: ARCHITECTURE-SPINE.md#Consistency Conventions]

### Project Structure Notes

- Greenfield story — no existing source tree to reconcile against. The target structure is fixed exactly by the Architecture spine's Structural Seed section; do not deviate from the listed top-level directories or rename any of them.
- No conflicts detected: repository currently has zero application code (only `_bmad-output/`, `docs/`, `.claude/`, `_bmad/`, `.git/`, and top-level SRS/PDF reference files).
- The Architecture spine's Structural Seed diagram shows the source tree under a `growthtrack/` label — this is illustrative naming, not a literal wrapper folder to create. Scaffold `api/`, `domain/`, `web/`, etc. directly at the repository root, alongside the existing `_bmad-output/`/`docs/` folders.
- Python packaging tool (Poetry, `uv`, Hatch, or plain `pip` + `pyproject.toml`) is an open implementation choice, same as the CI provider — not fixed by the Architecture spine. Pick one and use it consistently; `uv` is a reasonable 2026-current default if you have no other preference.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.0: Project Scaffolding & Deployment Foundation]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-GrowthTrack-2026-07-14/ARCHITECTURE-SPINE.md#AD-1] (dependency direction)
- [Source: _bmad-output/planning-artifacts/architecture/architecture-GrowthTrack-2026-07-14/ARCHITECTURE-SPINE.md#AD-5] (deployment topology, environments, secrets)
- [Source: _bmad-output/planning-artifacts/architecture/architecture-GrowthTrack-2026-07-14/ARCHITECTURE-SPINE.md#AD-10] (operational envelope: health, recovery, backup)
- [Source: _bmad-output/planning-artifacts/architecture/architecture-GrowthTrack-2026-07-14/ARCHITECTURE-SPINE.md#Stack]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-GrowthTrack-2026-07-14/ARCHITECTURE-SPINE.md#Structural Seed / Source tree]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-GrowthTrack-2026-07-14/ARCHITECTURE-SPINE.md#Consistency Conventions]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-GrowthTrack-2026-07-14/reviews/review-version-check.md] (independent version verification, Nginx CVE floor)
- [Source: _bmad-output/planning-artifacts/architecture/architecture-GrowthTrack-2026-07-14/reviews/review-security-compliance.md Finding 3.3, 3.4] (DB credential separation, secret-scanning gap)
- [Source: _bmad-output/specs/spec-growthtrack/stack.md]

## Dev Agent Record

### Agent Model Used

claude-sonnet-5

### Debug Log References

- `postgres:18.4-alpine` changed its data-directory convention: the official image now expects a single volume mount at `/var/lib/postgresql` (it manages a major-version-specific subdirectory itself), not the pre-18 `/var/lib/postgresql/data` — the container failed to start until `docker/docker-compose.yml`'s volume mount was corrected.
- Nginx's `localhost` health-check target resolves to `::1` first inside the container; the initial `nginx.conf` only had IPv4 `listen` directives, so the container's own healthcheck saw "connection refused" until IPv6 `listen [::]:80`/`listen [::]:443` directives were added.
- The repo-root Docker build context included `.venv/` and `web/node_modules/` (a 297s context transfer) until a `.dockerignore` was added.
- Verified end-to-end against real containers (not just `docker compose config`): built and ran the full stack (postgres, api, scheduler, nginx, backup) via Docker, confirmed all five report `healthy`, exercised `/health` through Nginx over HTTPS and the HTTP→HTTPS redirect, ran the Alembic upgrade/downgrade/upgrade round-trip against the compose-managed Postgres, and confirmed the `docker-entrypoint-initdb.d` two-role script (migrator + least-privilege app role) executes correctly.
- Swapped the `httpx` test dependency for `httpx2` — `starlette.testclient.TestClient` deprecated the former in favor of the latter as of the currently pinned Starlette/FastAPI versions.

### Completion Notes List

- Task 1: Backend source tree (`api/`, `domain/`, `ports/`, `adapters/{whatsapp_twilio,source_system,persistence}/`, `scheduler/`, `tests/`) scaffolded as `uv`-managed Python packages via a `pyproject.toml` pinned to every version in the Dev Notes table; all versions resolved successfully against real PyPI/npm, confirming no staleness. `config.py` provides a single `pydantic-settings` `Settings`/`get_settings()` object (no `os.environ` elsewhere). `import-linter` enforces AD-1 (`domain`/`ports` may not import `adapters`/`api`/`scheduler`) and is wired into CI. `web/` is a Vite + React 19.2.7 + MUI 9.2.0 app-shell (ThemeProvider/CssBaseline only — no design tokens, per Story 1.6 deferral); ESLint (flat config), `tsc`, and Vitest + React Testing Library (one smoke test) are wired up and pass.
- Task 2: `docker/docker-compose.yml` defines postgres, api, scheduler, nginx, and a backup service, reused as-is (env-var-only variance) — verified by actually building and running the stack. Every service has a `healthcheck` and `restart: always`. Nginx is a custom multi-stage image (`docker/nginx.Dockerfile`) built on `nginx:1.30.3-alpine` (exceeds the ≥1.30.1 CVE-2026-42945 floor), terminates TLS, redirects HTTP→HTTPS, and serves the built SPA plus proxies `/health` and `/webhooks/` to `api`. `.env.example` documents every required variable.
- Task 3: `GET /health` (`api/routes/health.py`) returns `{"status": "ok"}`, unauthenticated; covered by `tests/test_health.py` and confirmed reachable through Nginx over HTTPS.
- Task 4: `alembic/env.py` imports `adapters/persistence/database.py`'s `Base.metadata` and the migration role's URL from `config.get_settings()`. The baseline revision (`3066ace65d15`) is an empty-schema migration; its upgrade/downgrade/upgrade round-trip was verified against a real Postgres instance, both standalone and through the actual compose topology. `docker/postgres/init-roles.sh` creates the least-privilege `growthtrack_app` (DML-only, via `ALTER DEFAULT PRIVILEGES` so it automatically covers tables created by future migrations) alongside the migration-capable role — verified the app role has no superuser/DDL rights. `docker/backup/pg_dump_daily.sh` performs a daily `pg_dump | gzip` to a `/backups` volume (no retention policy invented, per Dev Notes).
- Task 5: `.github/workflows/ci.yml` runs three jobs on push/PR — `backend` (ruff, mypy, import-linter, Alembic upgrade/downgrade/upgrade round-trip, pytest, against a Postgres service container), `frontend` (eslint, tsc, vitest, vite build), `secret-scan` (gitleaks). All steps correspond to commands verified locally. `.gitignore`/`.dockerignore` cover `.env`/`.env.*` (excluding `.env.example`) and — caught during review — the locally-generated dev TLS cert/key (`docker/certs/*.pem`), which was briefly untracked-but-not-ignored before the fix.
- Task 6: `README.md` documents the source tree, local/dev-stack quickstart, and the guardrail that this story's source tree, Compose topology, and CI configuration are not re-scaffolded by later stories.

### File List

- `.dockerignore`
- `.env.example`
- `.github/workflows/ci.yml`
- `.gitignore`
- `.python-version`
- `README.md`
- `adapters/__init__.py`
- `adapters/persistence/__init__.py`
- `adapters/persistence/database.py`
- `adapters/source_system/__init__.py`
- `adapters/whatsapp_twilio/__init__.py`
- `alembic.ini`
- `alembic/env.py`
- `alembic/README`
- `alembic/script.py.mako`
- `alembic/versions/3066ace65d15_baseline.py`
- `api/__init__.py`
- `api/main.py`
- `api/routes/__init__.py`
- `api/routes/health.py`
- `config.py`
- `docker/backend.Dockerfile`
- `docker/backup/pg_dump_daily.sh`
- `docker/certs/generate-dev-cert.sh`
- `docker/docker-compose.yml`
- `docker/nginx.Dockerfile`
- `docker/nginx/nginx.conf`
- `docker/postgres/init-roles.sh`
- `domain/__init__.py`
- `ports/__init__.py`
- `pyproject.toml`
- `scheduler/__init__.py`
- `scheduler/main.py`
- `tests/test_health.py`
- `uv.lock`
- `web/.gitignore`
- `web/eslint.config.js`
- `web/index.html`
- `web/package.json`
- `web/package-lock.json`
- `web/public/favicon.svg`
- `web/README.md`
- `web/src/App.test.tsx`
- `web/src/App.tsx`
- `web/src/main.tsx`
- `web/src/setupTests.ts`
- `web/tsconfig.app.json`
- `web/tsconfig.json`
- `web/tsconfig.node.json`
- `web/vite.config.ts`

### Change Log

- 2026-07-14: Implemented Story 1.0 in full — backend/frontend source tree, Docker Compose deployment topology, `/health` endpoint, Alembic baseline migration with two-role DB credentials, GitHub Actions CI pipeline, and the repo-root guardrail note. All six tasks complete; all ACs satisfied and verified against real (not mocked) tooling — Docker containers, a live Postgres instance, and the actual lint/type-check/test commands CI runs.
- 2026-07-14: Adversarial code review (Blind Hunter + Edge Case Hunter + Acceptance Auditor) raised 1 decision-needed and 16 patch findings; user resolved the decision (backup off-host storage deferred, blocked on hosting provider selection) and approved applying all 16 patches. Added a read-only Postgres backup role, non-root Dockerfile user, CORS middleware, Nginx security headers, SIGTERM handling in the scheduler, auto-migration on API startup, a `docker build` CI job, CI coverage for the two-role DB setup, URL-escaped DB credentials, a narrower `MigrationSettings` for Alembic (no longer requires JWT/Twilio env vars), a hardened backup script (explicit failure detection instead of a masked pipe), an exact-match Nginx `/health` location, an import-linter contract closing the SQLAlchemy/Twilio-in-domain gap, exact frontend dependency pins, and quote-safe SQL in `init-roles.sh`. All changes verified against the real toolchain (ruff, mypy, import-linter, pytest, `npm ci`/lint/typecheck/test, and a live 5-container Docker Compose stack: all healthy, HTTPS `/health` reachable with security headers, HTTP→HTTPS redirect, CORS header present, `/healthxyz` now falls through to the SPA instead of the API, both DB roles created with correct least-privilege grants verified by direct INSERT/SELECT probes, non-root container user confirmed, and a real backup file + success marker written). Status set to `in-progress`: the deferred backup off-host-storage gap is high-severity per the review's own triage rule.
