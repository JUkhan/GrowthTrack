---
baseline_commit: 766b98b41bc0fd67ce51e15ae5492a3085aa3ecf
---

# Story 1.1: Administrator Login & Session

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an Administrator,
I want to log in with my username and password and receive a session,
so that I can access the GrowthTrack portal securely.

## Acceptance Criteria

1. **Given** valid Administrator credentials, **when** I submit the login form, **then** I receive a JWT access token, **and** the exchange occurs over HTTPS only. [Source: epics.md#Story 1.1]
2. **Given** invalid credentials, **when** I submit the login form, **then** the request is rejected, **and** no session token is issued, **and** no information leaks about whether the username exists. [Source: epics.md#Story 1.1]
3. **Given** no valid session, **when** I request any portal route, **then** the request is rejected, **and** no portal content is returned. [Source: epics.md#Story 1.1]
4. **Given** a stored Administrator password, **when** it is persisted, **then** it is hashed with pwdlib (bcrypt backend), never stored in plaintext. [Source: epics.md#Story 1.1]

## Tasks / Subtasks

- [x] Task 1: Add the `User` entity end-to-end — domain, port, persistence, migration (AC: #1, #4)
  - [x] `domain/`: a plain `User` model (id, username, hashed_password, role, status, version, created_at) — no SQLAlchemy/framework types in its definition (AD-1)
  - [x] `ports/`: a `UserRepository` interface (`get_by_username`, `add`, `get_by_id`) that `domain/` depends on
  - [x] `adapters/persistence/`: SQLAlchemy `User` ORM model (table `users`, `snake_case` columns) implementing `UserRepository`
  - [x] Alembic revision on top of `3066ace65d15` adding only the `users` table: `id UUID PK`, `username` (unique, not null), `hashed_password` (not null), `role` (not null — values mirror `entities.md`'s `Role`; **not enforced at login yet**, see Dev Notes), `status` (active/inactive, soft-delete per AD-4), `version` (int, default 1, optimistic concurrency per AD-4 — unused until Story 3.4, added now to avoid a second migration later, same reasoning Story 1.0 applied to the two DB roles), `created_at`
  - [x] Do **not** add `failed_login_count`, `locked_until`, or `theme_preference` — those are Story 1.5's and Story 1.6's columns respectively (AD-11); adding them now is scope creep this story doesn't need
  - [x] Cache `create_engine()`/`create_session_factory()` (`adapters/persistence/database.py`) as singletons — this is the first story to actually wire up a repository; Story 1.0's review flagged the missing caching as unreachable-until-now (see Previous Story Intelligence)
- [x] Task 2: Add the `AuditLogEntry` entity + migration (AC: — cross-cutting, required by AD-7)
  - [x] `ports/`: an `AuditLogRepository` (or equivalent) interface
  - [x] `adapters/persistence/`: SQLAlchemy `AuditLogEntry` model — generic enough that Epic 3's directory CRUD, Epic 3's opt-in/out, and Epic 4's schedule changes all reuse this same table later (do not build a login-specific audit table)
  - [x] Migration adding `audit_log_entries`: `id UUID PK`, `actor_user_id UUID` (nullable — a failed login before identity is confirmed has no actor), `action` (str, e.g. `"login.success"` / `"login.failure"`), `entity_type`/`entity_id` (nullable — unused by login, populated by later stories' directory mutations), `details` (text/JSON, nullable), `created_at`
  - [x] No admin-facing view of this table yet — Story 5.2 builds the Audit Log screen; this story only writes to it
- [x] Task 3: Password hashing + credential-verification domain service (AC: #4, #2)
  - [x] `ports/`: a `PasswordHasher` interface (`hash`, `verify`)
  - [x] An implementation backed by `pwdlib` (bcrypt backend, already pinned in `pyproject.toml`) — `pwdlib` is not in the `domain`/`ports` import-linter forbidden list, so it may be imported directly by `domain/` or `ports/` if you choose to implement it there instead of behind an adapter; either placement is fine as long as `domain/` never imports `sqlalchemy`/`twilio`/`adapters`
  - [x] `domain/`: an `AuthenticationService.authenticate(username, password) -> User | None` — on a non-existent username, still run a dummy bcrypt verification before returning `None`, so response timing doesn't leak whether the username exists (AC #2's "no information leaks" is a timing requirement, not just a response-shape requirement)
- [x] Task 4: JWT issuance + the shared AD-8 auth dependency (AC: #1, #3)
  - [x] `api/auth/`: encode/decode a JWT via PyJWT, algorithm **HS256**, signed with `config.get_settings().jwt_signing_key`. Add a new configurable `jwt_expiry_minutes` setting (pick a reasonable default, e.g. 480 — 8 hours; PRD §13 Q11 leaves the exact TTL an open question, and the Architecture spine's Deferred section explicitly leaves it "configurable, enforced by AD-8's mechanisms regardless of the numbers chosen" — this is not a pre-implementation blocker like the Achievement %/brand-threshold items elsewhere in this epic)
  - [x] `api/auth/`: one shared FastAPI dependency (e.g. `get_current_user`) that every future protected route will depend on — decodes and validates the JWT (signature + expiry) and rejects with 401 if missing/invalid/expired. **This story does not add revocation-record storage or a `jti` check** — Story 1.4 extends this exact dependency to add that; **it does not add an Administrator-role check either** — Story 1.3 extends it to reject non-Administrator roles. Build it so both are additive changes to one function, not a rewrite.
  - [x] No Phase 1 refresh-token mechanism — a single access-token JWT with a configurable TTL; re-login is required after expiry (matches the Architecture spine's Deferred scope; do not build token refresh/rotation, it isn't asked for)
- [x] Task 5: Login endpoint + a protected test route + audit logging (AC: #1, #2, #3)
  - [x] `POST /auth/login` — JSON body `{username, password}`. On success: call `AuthenticationService.authenticate`, issue the JWT, set it as an **httpOnly, SameSite=Lax cookie** (`Secure` when `environment != "development"`) — the frontend never touches the raw token, closing the client-side-storage/XSS gap the architecture's own security review left open (Finding 2.4). Also write an `AuditLogEntry` (`action="login.success"`, `actor_user_id=<user.id>`) in the same transaction (AD-7 — login events are audited even though login isn't a directory mutation)
  - [x] On failure (bad username or bad password — same code path, see Task 3): return 401 with the standard `{error:{code,message,details}}` envelope, a single generic message (e.g. `"Invalid username or password"`) regardless of which credential was wrong, and no cookie set. Also write an `AuditLogEntry` (`action="login.failure"`, `actor_user_id=null`, `details` capturing the attempted username) — not literally mandated by AD-7's text (which names login events generically), but the PRD's own edge-case review flagged failed-login auditing as unresolved, and Story 1.5's lockout counter will want this trail; log both, it costs nothing extra here
  - [x] `GET /auth/me` — depends on Task 4's shared dependency, returns the current user's `{id, username, role}`. This is the first protected route and is how AC #3 ("no valid session → any portal route rejected") is actually exercised — no other business route exists yet for this to hook into
  - [x] This story has **no account-creation endpoint or UI** — Story 1.2 (First-Run Bootstrap) is what creates the first Administrator. Seed `User` rows directly via the repository in test fixtures; don't build a signup flow here.
- [x] Task 6: Frontend login page + routing (AC: #1, #2, #3)
  - [x] Add `react-router-dom` to `web/` (not yet a dependency)
  - [x] A `LoginPage` component: username/password fields, submit button, inline error text on 401 (using the API's generic message) — plain MUI defaults, **no Story 1.6 design tokens** (that story hasn't applied brand overrides to the theme yet; follow Story 1.0's precedent of app-shell-before-design-tokens)
  - [x] `fetch('/auth/login', {method: 'POST', credentials: 'include', ...})` — relative path, not an absolute `http://localhost:8000` URL, so the same code works unmodified once Story 1.6/later stories add more routes
  - [x] On success, navigate to a minimal authenticated placeholder route (e.g. a bare "Logged in" page) — **Epic 2 hasn't built the Dashboard yet**, so there is nowhere real to land; don't build a Dashboard placeholder that pretends to be the real thing, just gate a route behind "did `/auth/me` succeed"
  - [x] Add a Vite dev-server proxy (`web/vite.config.ts`) forwarding `/auth` to `http://localhost:8000`, so the browser only ever talks to origin `5173` and the `httpOnly` cookie stays same-origin in dev too (avoids `SameSite`/cross-origin cookie issues that a direct cross-port fetch would hit) — this also means the existing CORS middleware in `api/main.py` stops being load-bearing for the web app itself (it can stay for direct API testing tools)
- [x] Task 7: Fix the Nginx routing gap for the new `/auth/` routes (AC: #1 — the feature does not work in staging/production without this)
  - [x] Add a `location /auth/` block to `docker/nginx/nginx.conf` proxying to `api:8000`, matching the existing `/webhooks/` block's pattern — **Story 1.0's own review flagged this exact gap**: "Any future backend route (e.g. Story 1.1's login endpoint) needs a new location block added by hand, or it silently falls through to the SPA's index.html." Without this, login works in dev (Task 6's Vite proxy) but 404s/falls through to the SPA in staging and production.
- [x] Task 8: Tests (AC: all)
  - [x] Backend (`pytest`): valid login → 200 + cookie set + `AuditLogEntry` written; invalid username → 401 generic message, no leak; invalid password → 401 generic message (same shape as invalid username); password persisted as a bcrypt hash, never plaintext; `GET /auth/me` → 401 with no cookie / expired / tampered token, 200 with a valid one
  - [x] Frontend (`vitest` + RTL): `LoginPage` happy path (submit → redirect), error path (401 → inline message shown, no redirect)
  - [x] No CI changes needed — the existing `backend`/`frontend` CI jobs (Story 1.0) already run `pytest`/`vitest` against whatever exists in `tests/`/`web/src`

### Review Findings

- [x] [Review][Patch] Login route calls `AuditLogRepository.add()` directly instead of going through `domain/` — violates AD-1 ("the only layer permitted to call a repository port") and AD-7's "login-handling service method" framing [api/auth/routes.py:61,75] — fixed: added `AuthenticationService.login()` (domain/auth.py), which owns the audit write; the route now only calls `login()`
- [x] [Review][Patch] `AuthenticationService.authenticate` never checks `user.status` — a deactivated (`UserStatus.INACTIVE`) Administrator can still log in and receive a valid session [domain/auth.py:25-35] — fixed: `authenticate()` now rejects any non-`ACTIVE` status, verifying the password first so timing stays uniform
- [x] [Review][Patch] `decode_access_token`'s `uuid.UUID(payload["sub"])` is unguarded — a validly-signed token with a missing/malformed `sub` claim raises `KeyError`/`ValueError`, which `get_current_user` doesn't catch (only `jwt.PyJWTError`), surfacing as a 500 instead of a 401 [api/auth/tokens.py:36, api/auth/dependencies.py:46] — fixed: both exceptions are now re-raised as `jwt.InvalidTokenError`
- [x] [Review][Patch] `RequestValidationError` (422, malformed/missing JSON body) bypasses the `{error:{code,message,details}}` envelope — only `HTTPException` has a handler registered [api/main.py:16] — fixed: added a `RequestValidationError` exception handler
- [x] [Review][Patch] `LoginPage.tsx`'s `handleSubmit` has no `catch` — a network failure (offline, unreachable backend) is an unhandled promise rejection with no error shown to the user [web/src/pages/LoginPage.tsx:24-39] — fixed: added a `catch` showing a generic error message
- [x] [Review][Patch] `HomePage.tsx`'s `/auth/me` fetch has no `catch` — a network failure leaves `status` at `'loading'` forever instead of redirecting to login [web/src/pages/HomePage.tsx:16-20] — fixed: added a `.catch()` treating a failed request as unauthenticated
- [x] [Review][Patch] Login-success audit entry is committed before the JWT is created/cookie is set — a failure in between would leave a `login.success` audit row for a request that never actually issued a session [api/auth/routes.py:75-97] — fixed: token is now created before the session commit
- [x] [Review][Patch] `jwt_expiry_minutes` has no validation against zero/negative values — a misconfigured `.env` would issue already-expired tokens and immediately-deleted cookies, breaking login silently [config.py:40] — fixed: `Field(gt=0)`
- [x] [Review][Patch] `LoginRequest` has no length constraints on `username`/`password` — combined with bcrypt's silent 72-byte truncation (never addressed), a password differing only after byte 72 still authenticates [api/auth/routes.py:24-26] — fixed: `Field(min_length=1, max_length=…)`, capping password at bcrypt's own 72-byte limit
- [x] [Review][Patch] `test_authenticate_timing_does_not_leak_username_existence` asserts on wall-clock duration — flaky under CI scheduler jitter [tests/domain/test_auth_service.py:63-79] — fixed: replaced with a deterministic spy asserting the dummy verification actually ran
- [x] [Review][Patch] `router.tsx` has no catch-all/404 route — any unmatched path renders React Router's default error boundary [web/src/router.tsx] — fixed: added a `path: '*'` route redirecting to `/`
- [x] [Review][Patch] No test exercises the login cookie's `secure` flag in a non-development environment [api/auth/routes.py:95, tests/api/test_auth_routes.py] — fixed: added a test overriding `ENVIRONMENT=production`
- [x] [Review][Patch] `react-router-dom` was added with a caret range (`^7.18.1`) while the other consequential dependencies (`react`, `react-dom`, `@mui/*`) are exact-pinned [web/package.json:21] — fixed: pinned to `7.18.1`
- [x] [Review][Defer] `create_engine()`/`create_session_factory()`'s `lru_cache` singleton has no dispose/cache-clear path — inherent to this story's own Task 1 requirement to cache them; only matters if a future story needs per-test loop isolation beyond the session-scoped test loop this story introduced [adapters/persistence/database.py:19-25] — deferred, pre-existing tradeoff of the singleton pattern this story was asked to build
- [x] [Review][Defer] `audit_log_entries` has no index beyond its primary key and no FK on `actor_user_id` [alembic/versions/98ddc369b175_user_and_audit_log_entities.py] — deferred, pre-existing (not required by any AC; revisit at scale or when Story 5.2 builds the Audit Log screen)
- [x] [Review][Defer] `adapters/persistence/users.py` constructs `Role(row.role)`/`UserStatus(row.status)` unguarded against a value outside the enum [adapters/persistence/users.py:31-37] — deferred, pre-existing (only reachable via external DB corruption; no code path in this diff can write an invalid value)
- [x] [Review][Defer] `docker/nginx/nginx.conf`'s `/auth/` block doesn't match a bare `/auth` (no trailing slash), which falls through to the SPA [docker/nginx/nginx.conf:51-56] — deferred, pre-existing (mirrors the existing `/webhooks/` convention from Story 1.0; no app code path ever requests the bare path)

## Dev Notes

- **Role enforcement is explicitly out of scope here.** `User.role` exists and is stored (per `entities.md`), but Story 1.1's login does not check it — a Sales User or Manager account could technically obtain a token from this story's endpoint alone. That gap is closed by Story 1.3 ("Sales User or Manager attempts to obtain a portal session token → rejected"), which is the story that actually enforces role at the auth boundary. This isn't a bug to fix here; it's a deliberate sequencing the epics file draws — don't pull Story 1.3's AC forward into this one, and don't skip it thinking 1.1 already covers it. In practice this is low-risk today because no story before Epic 3 creates non-Administrator `User` rows.
- **Revocation is explicitly out of scope here.** AD-8's full rule ("validates the JWT, the Administrator role, and a revocation check keyed by `jti`") is delivered across three stories: this one builds JWT issuance + validation, Story 1.3 adds the role check, Story 1.4 adds `jti`-based revocation (logout, mid-session deactivation). Build the shared dependency so those are two clean additions, not a rewrite — e.g. structure it as a small pipeline of checks rather than one monolithic `if`.
- **Token transport decision (this story owns it): httpOnly cookie, not a client-readable token.** The architecture's own security review left this explicitly unstated (Finding 2.4, "Token algorithm and client-side storage are unstated — LOW"). An httpOnly, `SameSite=Lax`, conditionally-`Secure` cookie means the JWT is never reachable from JS (no XSS exfiltration path) and the frontend never manages token storage/refresh logic. Pair this with Task 6's Vite proxy and Task 7's Nginx block so requests are always same-origin from the browser's point of view in every environment — never introduce a separate API origin/CORS-with-credentials setup to work around this.
- **JWT algorithm: HS256.** One shared `jwt_signing_key` already exists in `config.py`/`.env.example` — HS256 (symmetric) matches that; there's no need for RS256/asymmetric keys since nothing outside this service verifies the token.
- **AuditLogEntry is new in this story, not deferred to Epic 5.** AD-7 states plainly: "Login events are also written to `AuditLogEntry`... even though it isn't a directory mutation" — this is a hard architecture rule, not an Epic-5-only concern. Story 5.2's AC list ("any login (Epic 1)") is describing data this story must already be producing, not a table Story 5.2 creates. Design the schema generically (Task 2) since Epic 3/4 mutations reuse the exact same table with different `action`/`entity_type` values — don't scope it to logins only.
- **No account-creation flow exists yet.** Story 1.2 (First-Run Administrator Bootstrap) is the very next story and is what lets a real user create the first Administrator. Until then, the only way a `User` row exists is a test fixture seeding one directly through the repository. Do not build any create-account UI/endpoint in this story — that duplicates Story 1.2's job and this story's own AC list has no such requirement.
- **No Dashboard exists to redirect to post-login.** Epic 2 (Story 2.2) builds it. Land the frontend on a bare authenticated placeholder after login — something that proves the session/route-guard works, not a stand-in Dashboard.
- **No Story 1.6 design tokens yet.** `web/src/App.tsx`'s theme is still `createTheme()` with no overrides (Story 1.0 deliberately deferred this). Build the login form against MUI's stock theme; Story 1.6 re-themes every existing screen afterward, this story doesn't need to anticipate it.

### Previous Story Intelligence (from 1-0-project-scaffolding-deployment-foundation)

- **`docker/nginx/nginx.conf` only proxies `/health` and `/webhooks/`.** Explicitly called out in that story's own deferred-work log as "the next story" needing a hand-added `location` block — this story is that story (Task 7).
- **`create_engine()`/`create_session_factory()` have no singleton caching**, flagged as "currently unreachable, nothing calls it yet" — this story is the first to call it (Task 1); cache it now.
- **`GET /health` reports liveness only, not DB readiness** — flagged as "matters once a real DB-backed route exists (Story 1.1+)." Optional, not an AC of this story: extending `/health` to check DB connectivity is a reasonable opportunistic improvement now that `adapters/persistence` has real repositories wired up, but is not required to satisfy any AC here — don't let it block the story if time-constrained.
- **Two-role DB split is already in place** (`postgres_migrator_*` for Alembic, `postgres_app_*` for runtime) — new repositories/migrations use the existing `config.get_settings()` / `get_migration_settings()` split as-is, no changes needed there.
- **CORS middleware in `api/main.py`** currently allows `http://localhost:5173` unconditionally for local dev convenience. With Task 6's Vite proxy in place, the web app itself no longer depends on this — leave the middleware as-is (harmless, useful for direct API testing) rather than removing it; removing it isn't in scope and isn't necessary.
- **Stack versions already pinned and verified current** (`pyproject.toml`): `pwdlib[bcrypt]>=0.3.0` and `pyjwt==2.13.0` are already dependencies — no new backend packages needed for Tasks 1–5 beyond what's already installed.

### Git Intelligence

- Commit `766b98b` ("review") is the current `HEAD` and closes out Story 1.0's full adversarial-review remediation cycle — the source tree, Docker Compose topology, CI, and DB role split are all stable and were verified against real infrastructure (not mocks). Build directly on top of it; nothing there is still in flux.

### Project Structure Notes

- New backend files land in the existing `domain/`, `ports/`, `adapters/persistence/`, `api/` packages — no new top-level directories. Likely new files: `domain/auth.py` (or `domain/auth/`), `domain/models.py` (or wherever `User` lives — follow whatever convention feels most consistent with the empty scaffolding; there is no prior precedent to match since this is the first domain entity), `ports/users.py`, `ports/audit.py`, `ports/auth.py` (or combine ports sensibly — small interfaces, no need to over-split into many files), `adapters/persistence/users.py`, `adapters/persistence/audit_log.py`, `api/auth/routes.py`, `api/auth/dependencies.py`, `api/auth/tokens.py` (or combine — `api/routes/health.py`'s single-file-per-concern style is the closest existing precedent), new Alembic revision(s) chained on `3066ace65d15`.
- Frontend: new files likely `web/src/pages/LoginPage.tsx` (or similar), a router setup in `App.tsx` or a new `web/src/router.tsx`, an API client helper (a thin `fetch` wrapper is sufficient — no new HTTP library needed).
- No conflicts detected — this is the first story adding real backend logic on top of Story 1.0's scaffold; no existing behavior to preserve or avoid breaking.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.1: Administrator Login & Session]
- [Source: _bmad-output/planning-artifacts/prds/prd-GrowthTrack-2026-07-14/prd.md#4.1, #FR-1] (auth requirements, "no information leaks" clause, HTTPS-only)
- [Source: _bmad-output/planning-artifacts/architecture/architecture-GrowthTrack-2026-07-14/ARCHITECTURE-SPINE.md#AD-1] (dependency direction — domain/ports only)
- [Source: _bmad-output/planning-artifacts/architecture/architecture-GrowthTrack-2026-07-14/ARCHITECTURE-SPINE.md#AD-4] (User soft-delete + optimistic-concurrency version column)
- [Source: _bmad-output/planning-artifacts/architecture/architecture-GrowthTrack-2026-07-14/ARCHITECTURE-SPINE.md#AD-7] (Audit Log co-transactional, login events explicitly included)
- [Source: _bmad-output/planning-artifacts/architecture/architecture-GrowthTrack-2026-07-14/ARCHITECTURE-SPINE.md#AD-8] (shared auth dependency, JWT + role + revocation — this story covers JWT validation only)
- [Source: _bmad-output/planning-artifacts/architecture/architecture-GrowthTrack-2026-07-14/ARCHITECTURE-SPINE.md#AD-11] (auth security state entities — failed_login_count/locked_until/theme_preference NOT this story's scope)
- [Source: _bmad-output/planning-artifacts/architecture/architecture-GrowthTrack-2026-07-14/ARCHITECTURE-SPINE.md#Capability → Architecture Map] (CAP-1 lives in api/auth, ports/auth)
- [Source: _bmad-output/planning-artifacts/architecture/architecture-GrowthTrack-2026-07-14/ARCHITECTURE-SPINE.md#Deferred] (JWT TTL and retry-policy values are configurable, not pre-implementation blockers)
- [Source: _bmad-output/planning-artifacts/architecture/architecture-GrowthTrack-2026-07-14/reviews/review-security-compliance.md §2, §5] (JWT algorithm/storage unstated — Finding 2.4; AD-7 vs. FR-12 login-audit gap — Finding 5.1, both resolved by this story's design choices)
- [Source: _bmad-output/planning-artifacts/prds/prd-GrowthTrack-2026-07-14/review-edge-case-hunter.md] (failed-login audit logging flagged as unresolved — this story logs both outcomes)
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-GrowthTrack-2026-07-14/EXPERIENCE.md#Information Architecture, #Key Flows] (Login surface, auth edge states — lockout/bootstrap/deactivation belong to later stories, not this one)
- [Source: _bmad-output/implementation-artifacts/1-0-project-scaffolding-deployment-foundation.md#Deferred Work / Review Findings] (Nginx routing gap, repository singleton caching, health DB-readiness)
- [Source: _bmad-output/implementation-artifacts/deferred-work.md] (same findings, standalone log)
- [Source: docker/nginx/nginx.conf], [Source: web/vite.config.ts], [Source: config.py], [Source: api/main.py], [Source: adapters/persistence/database.py], [Source: pyproject.toml]

## Dev Agent Record

### Agent Model Used

Claude Sonnet 5 (claude-sonnet-5), via bmad-dev-story.

### Debug Log References

- Verified against real infrastructure per project convention (not mocked): a standalone `postgres:18.4-alpine` container (host port 15432 — the host's default 5432 was already bound by an unrelated container on this machine, so `POSTGRES_PORT=15432` in the local `.env`; purely a local dev-environment detail, not a code or compose-file change), full Alembic upgrade/downgrade/upgrade round-trip, `docker build` of `docker/backend.Dockerfile`, and a real `nginx -t` syntax check of the updated `nginx.conf`.
- **Architecture contract conflict found and resolved:** `pyproject.toml`'s import-linter contract forbids `ports` from importing `domain` ("Ports stay framework- and adapter-free"), but this story's own Dev Notes describe `ports/users.py`/`ports/audit.py` as interfaces returning `User`/`AuditLogEntry` domain types. Resolved by typing the port interfaces' entity parameters/returns as `typing.Any` instead of importing `domain.models` — concrete return types are enforced at the `adapters/persistence` implementation level instead, which the contract does allow to import `domain`. Both import-linter contracts pass. Future stories adding repository ports should follow the same pattern.
- `pytest-asyncio` was switched from its default per-test event loop to a session-scoped loop (`asyncio_default_fixture_loop_scope`/`asyncio_default_test_loop_scope = "session"` in `pyproject.toml`) — required because `adapters/persistence/database.py`'s `create_engine()`/`create_session_factory()` are now actually exercised (Task 1's singleton caching) and an asyncpg connection pool is bound to the event loop it was created on; a fresh per-test loop broke on the second test with `InterfaceError`.
- `web/src/setupTests.ts` was missing `@testing-library/react`'s automatic per-test DOM cleanup (a no-op under `vite.config.ts`'s `globals: false`, since testing-library's auto-registration relies on a global `afterEach`) — invisible with only one test file (`App.test.tsx`) in the repo, but it made `LoginPage.test.tsx`'s second test see the first test's still-mounted DOM tree. Added an explicit `afterEach(() => cleanup())`.
- `TRUNCATE` in the test-cleanup fixture failed with `InsufficientPrivilegeError` — the runtime `growthtrack_app` role only holds DML grants (AD-5's least-privilege split), not `TRUNCATE`. Switched to `DELETE FROM`.

### Completion Notes List

- All 4 ACs covered: JWT-over-HTTPS issuance (AC1, cookie-based per Dev Notes' Finding-2.4 resolution), generic no-username-leak 401 with a timing-safe dummy bcrypt verify (AC2), the shared `get_current_user` dependency rejecting every unauthenticated `/auth/me` request (AC3), and bcrypt-hashed password storage (AC4).
- Role enforcement (Story 1.3) and `jti` revocation (Story 1.4) were deliberately left out, per Dev Notes — `get_current_user` is structured as a linear pipeline of checks (token present → decode → user exists) so both are additive.
- Backend: 32/32 `pytest` passing after the review round (up from 21 — added inactive-user, 422-envelope, oversized-password, secure-cookie, malformed-JWT-`sub`, and `login()`-audit-write tests). `ruff check .`, `mypy`, and `lint-imports` all clean.
- Frontend: 7/7 `vitest` passing after the review round (up from 3 — added a `LoginPage` network-failure test and a new `HomePage.test.tsx`). `eslint`, `tsc -b`, and `vite build` all clean.
- Left for a later story, not this one: `POSTGRES_BACKUP_USER`/role creation wasn't exercised in local manual testing (an artifact of building a standalone test container by hand rather than via `docker compose`) — CI's own `init-roles.sh` step and the real `docker-compose.yml` stack are unaffected and untouched.

### File List

**New:**
- `domain/models.py` — `User`, `Role`, `UserStatus`, `AuditLogEntry`
- `domain/auth.py` — `AuthenticationService`
- `ports/users.py` — `UserRepository`
- `ports/audit.py` — `AuditLogRepository`
- `ports/auth.py` — `PasswordHasher`, `PwdlibPasswordHasher`
- `adapters/persistence/users.py` — `UserModel`, `SqlAlchemyUserRepository`
- `adapters/persistence/audit_log.py` — `AuditLogEntryModel`, `SqlAlchemyAuditLogRepository`
- `alembic/versions/98ddc369b175_user_and_audit_log_entities.py`
- `api/auth/__init__.py`
- `api/auth/tokens.py` — JWT encode/decode
- `api/auth/dependencies.py` — `get_db`, `get_current_user`
- `api/auth/routes.py` — `POST /auth/login`, `GET /auth/me`
- `tests/conftest.py` — `_clean_tables`, `client`, `seed_user` fixtures
- `tests/domain/test_auth_service.py`
- `tests/ports/test_password_hasher.py`
- `tests/api/test_tokens.py`
- `tests/api/test_auth_routes.py`
- `web/src/api/authClient.ts`
- `web/src/pages/LoginPage.tsx`
- `web/src/pages/LoginPage.test.tsx`
- `web/src/pages/HomePage.tsx`
- `web/src/pages/HomePage.test.tsx`
- `web/src/router.tsx`

**Modified:**
- `.env.example` — documented `JWT_EXPIRY_MINUTES`
- `config.py` — added `Settings.jwt_expiry_minutes`
- `adapters/persistence/database.py` — `create_engine()`/`create_session_factory()` cached as singletons (`lru_cache`)
- `adapters/persistence/__init__.py` — imports model modules so Alembic autogenerate sees the full schema
- `api/main.py` — registered the auth router; added the `{error:{code,message,details}}` `HTTPException` handler
- `docker/nginx/nginx.conf` — added the `/auth/` location block
- `pyproject.toml` — `ruff` bugbear FastAPI `Depends`/`Cookie` exemption; `pytest-asyncio` session-scoped event loop
- `web/package.json`, `web/package-lock.json` — added `react-router-dom`
- `web/src/App.tsx` — wired `RouterProvider`
- `web/src/setupTests.ts` — explicit RTL `afterEach(cleanup)`
- `web/vite.config.ts` — dev-server proxy for `/auth`

### Change Log

- 2026-07-17: Implemented Story 1.1 in full — `User`/`AuditLogEntry` domain entities and repositories, bcrypt password hashing with a timing-safe `AuthenticationService`, HS256 JWT issuance behind a shared `get_current_user` auth dependency, `POST /auth/login`/`GET /auth/me`, the `LoginPage`/routing/Vite-proxy frontend, and the Nginx `/auth/` routing fix Story 1.0's review flagged. All 8 tasks complete; all 4 ACs satisfied and verified against real (not mocked) infrastructure — a live Postgres instance, a full Alembic upgrade/downgrade/upgrade round-trip, a real `docker build` of the backend image, and an actual `nginx -t` syntax check. 21/21 backend and 3/3 frontend tests passing; `ruff`, `mypy`, `lint-imports`, `eslint`, and `tsc` all clean. Found and resolved one pre-existing architecture-contract/tooling gap along the way (see Debug Log References): the `ports`-may-not-import-`domain` import-linter contract, `pytest-asyncio`'s per-test event loop vs. the newly-exercised singleton DB engine, and missing RTL auto-cleanup in `web/src/setupTests.ts`.
- 2026-07-17: Code review (Blind Hunter + Edge Case Hunter + Acceptance Auditor) raised 13 patch and 4 defer findings (6 dismissed as noise, incl. a false-positive `httpx2`-doesn't-exist claim); user approved applying all 13 patches. Fixed: the login route was calling `AuditLogRepository.add()` directly instead of through `domain/` (a real AD-1 violation — added `AuthenticationService.login()` to own the audit write); `AuthenticationService.authenticate` didn't check `user.status`, so a deactivated Administrator could still log in; `decode_access_token`'s unguarded `uuid.UUID(payload["sub"])` could 500 instead of 401 on a malformed `sub` claim; `RequestValidationError` (422) responses bypassed the `{error:{code,message,details}}` envelope; the login-success audit write was committed before token creation (reordered so a token-creation failure leaves nothing committed); `jwt_expiry_minutes` and `LoginRequest.username`/`password` had no bounds validation; a wall-clock timing assertion in the auth-service tests was flaky under CI jitter (replaced with a deterministic call-count spy); `LoginPage`/`HomePage` had unhandled fetch rejections on network failure; `router.tsx` had no catch-all route; `react-router-dom` was added with a caret range while other core deps are exact-pinned; no test covered the cookie's `secure` flag outside development. All fixes verified: 32/32 backend and 7/7 frontend tests passing, `ruff`/`mypy`/`lint-imports`/`eslint`/`tsc`/`vite build` all clean. Status set to `done`.
