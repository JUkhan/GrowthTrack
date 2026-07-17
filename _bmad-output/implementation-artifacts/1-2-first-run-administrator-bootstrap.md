---
baseline_commit: 61c276e8a0245205c462c63611b8006871f861ac
---

# Story 1.2: First-Run Administrator Bootstrap

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a new GrowthTrack deployment with no Administrator account yet,
I want the Login screen to route to a one-time bootstrap flow,
so that the first Administrator can be created without a dead end.

## Acceptance Criteria

1. **Given** zero Administrator accounts exist, **when** I visit Login, **then** I am routed to a one-time bootstrap flow instead of the standard form. [Source: epics.md#Story 1.2]
2. **Given** the bootstrap flow, **when** I submit a valid new Administrator username/password, **then** the first Administrator account is created, **and** I am logged in via Story 1.1's session mechanism. [Source: epics.md#Story 1.2]
3. **Given** at least one Administrator already exists, **when** I visit Login, **then** the standard login form is shown, not bootstrap. [Source: epics.md#Story 1.2]

## Tasks / Subtasks

- [x] Task 1: Add the bootstrap-gate check to `UserRepository` (AC: #1, #3)
  - [x] `ports/users.py`: add two abstract methods to `UserRepository` — `has_any_administrator(self) -> bool` and `acquire_bootstrap_lock(self) -> None`. Follow the existing file's convention: signatures typed `Any`-free here since these don't take/return entity types, no import-linter conflict.
  - [x] `adapters/persistence/users.py`: implement `has_any_administrator` as `SELECT EXISTS(SELECT 1 FROM users WHERE role = 'administrator')` (`role` stored as the plain string value, matching `UserModel.role`'s existing column — see `_to_domain`'s `Role(row.role)` pattern for the enum value). **Do not filter by `status`** — count administrators regardless of active/inactive (see Dev Notes' "why not just active admins" rationale, an `[ASSUMPTION]` this story makes explicitly).
  - [x] `adapters/persistence/users.py`: implement `acquire_bootstrap_lock` as `await self._session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": 890217364})` — a fixed, arbitrary 32-bit lock key reserved solely for this purpose (comment it as such so nobody else's feature accidentally reuses the same key). This is a **transaction-scoped** advisory lock: it auto-releases on commit/rollback, requiring no explicit unlock call.
- [x] Task 2: `domain/bootstrap.py` — new `BootstrapService` (AC: #1, #2, #3)
  - [x] A new domain service, separate from `AuthenticationService` (single-responsibility, matches this codebase's one-class-one-job pattern) — do not bolt bootstrap logic onto `domain/auth.py`.
  - [x] `class BootstrapAlreadyComplete(Exception)` — raised when a bootstrap attempt loses the race (an Administrator already exists by the time the lock is acquired).
  - [x] `BootstrapService.__init__(self, users: UserRepository, password_hasher: PasswordHasher, audit_log: AuditLogRepository)` — same three collaborators `AuthenticationService` takes; same constructor-injection style.
  - [x] `async def is_required(self) -> bool: return not await self._users.has_any_administrator()` — the **single** function both the routing check (Task 4's `GET /auth/bootstrap-status`) and the create-gate (below) call. Do not re-implement this check a second way anywhere else — this codebase's established pattern (AD-2's resolution function, AD-9's single enforcement point) is one check, multiple callers.
  - [x] `async def bootstrap(self, username: str, password: str) -> User`:
    1. `await self._users.acquire_bootstrap_lock()` — **first**, before the existence check. This serializes concurrent bootstrap attempts (e.g. a double-submit, or two operators racing during initial deployment setup): the second caller blocks here until the first's transaction commits or rolls back.
    2. `if await self._users.has_any_administrator(): raise BootstrapAlreadyComplete()` — re-check *after* the lock is held, not before. This is what actually closes the race: whichever caller wins the lock and finds zero Administrators is the only one that proceeds to create one.
    3. Build a `User` (`id=uuid4()`, `username`, `hashed_password=self._password_hasher.hash(password)`, `role=Role.ADMINISTRATOR`, `status=UserStatus.ACTIVE`, `version=1`, `created_at=datetime.now(UTC)`) and `await self._users.add(user)`.
    4. Write the co-transactional audit entry (AD-7 — this is a `User` mutation, same rule Story 1.1's login-audit followed): `action="bootstrap.success"`, `actor_user_id=user.id`, `entity_type=None`, `entity_id=None`, `details=None`.
    5. Return the created `User`.
- [x] Task 3: `GET /auth/bootstrap-status` endpoint (AC: #1, #3)
  - [x] `api/auth/routes.py`: `GET /auth/bootstrap-status` → `{"bootstrap_required": bool}`, backed by `BootstrapService.is_required()`. Public/unauthenticated — no `get_current_user` dependency, matching `/auth/login`'s existing unauthenticated posture (a session-less visitor must be able to call this before any account exists).
- [x] Task 4: `POST /auth/bootstrap` endpoint (AC: #2, #3)
  - [x] `api/auth/routes.py`: a `BootstrapRequest` Pydantic model — same field constraints as `LoginRequest` (`username: Field(min_length=1, max_length=255)`, `password: Field(min_length=1, max_length=72)` — reuse `LoginRequest`'s constraints verbatim, bcrypt's 72-byte limit applies here too).
  - [x] `POST /auth/bootstrap` — instantiates `BootstrapService` (same wiring pattern as the login route's `AuthenticationService` instantiation: `SqlAlchemyUserRepository(session)`, `PwdlibPasswordHasher()`, `SqlAlchemyAuditLogRepository(session)`), calls `bootstrap(username, password)`.
  - [x] On `BootstrapAlreadyComplete`: `await session.commit()` (releases the advisory lock cleanly) then raise a 409 with the standard envelope — `code="administrator_exists"`, message e.g. `"An Administrator account already exists"`. This is the endpoint's permanent-lockout behavior: once any Administrator exists, this path is closed forever, not just during the race window — do not skip this check thinking the lock alone is sufficient; the lock only prevents a race, this `if` is what prevents the endpoint from being a standing unauthenticated admin-creation backdoor after first-run.
  - [x] On success: issue the session **exactly like `/auth/login` does** — same `create_access_token`, same `response.set_cookie(...)` call (httpOnly, `SameSite=Lax`, conditionally `Secure`, `max_age`). Extract this cookie-issuing block into a small shared private helper (e.g. `_set_session_cookie(response, user, settings)`) that both `login` and `bootstrap` call — do not copy-paste the `set_cookie` call a second time. Commit the transaction before setting the cookie (mirrors login's own reasoning: a token-creation failure must leave nothing committed). Response body: same `UserResponse` shape as login.
- [x] Task 5: `LoginPage.tsx` — conditional bootstrap routing (AC: #1, #3)
  - [x] On mount, `LoginPage` calls `GET /auth/bootstrap-status` via `apiFetch`. While the check is in flight, render `null` (matches `HomePage.tsx`'s existing loading-state convention — do not introduce a different loading pattern).
  - [x] If `bootstrap_required === true`, render the new `BootstrapForm` component (Task 6) instead of the existing login form JSX.
  - [x] If `bootstrap_required === false` (or the status check itself fails/errors — treat a failed check as "not required," i.e. fail toward the existing standard login form, never toward exposing an unauthenticated account-creation form on an ambiguous/error response), render the existing login form unchanged.
  - [x] No router changes needed — `router.tsx`'s `{ path: '/', element: <LoginPage /> }` stays as-is; the branching happens inside `LoginPage`, consistent with UX-DR11/EXPERIENCE.md treating Login (incl. bootstrap, and later Story 1.5's reset) as one IA surface, not separate routes.
- [x] Task 6: `BootstrapForm` component (AC: #2)
  - [x] New file `web/src/pages/BootstrapForm.tsx` — same structural pattern as `LoginPage.tsx`'s form (MUI `Container`/`Box`/`TextField`/`Button`, `useState` for username/password/error/submitting, `useNavigate`), posting to `POST /auth/bootstrap` instead of `/auth/login` via `apiFetch`.
  - [x] Copy that mirrors the actual situation, per this codebase's established voice/tone convention (Dev Notes below) — e.g. a heading like "Create the first Administrator account" rather than reusing the plain "GrowthTrack" login heading unchanged, so a fresh deployment doesn't look like a broken login page.
  - [x] On success, `navigate('/home')` — same landing as login (AC #2's "logged in via Story 1.1's session mechanism" means the same post-auth destination).
  - [x] On a 409 (`administrator_exists`) or any other error response, show the server's `error.message` inline (same `Alert severity="error"` pattern `LoginPage` already uses) — do not silently redirect to the login form on a 409; show the message, since this is an unexpected-but-real state (a race was lost, or someone bootstrapped between page-load and submit).
  - [x] On a network failure (fetch rejects), show the same generic `"Something went wrong. Please try again."` text `LoginPage` already uses — for consistency, not a new message.
- [x] Task 7: Tests (AC: all)
  - [x] Backend (`pytest`, `tests/domain/test_bootstrap_service.py`): `is_required()` is `True` on an empty `users` table, `False` once any Administrator row exists (active or inactive — assert both); `bootstrap()` creates an `ACTIVE` `ADMINISTRATOR` `User` with a bcrypt-hashed password and writes a `bootstrap.success` audit row; a second `bootstrap()` call after one already succeeded raises `BootstrapAlreadyComplete`.
  - [x] Backend (`pytest`, extend or add to `tests/api/test_auth_routes.py` or a new `tests/api/test_bootstrap_routes.py`): `GET /auth/bootstrap-status` → `{"bootstrap_required": true}` on an empty DB, `{"bootstrap_required": false}` once `seed_user` has seeded one; `POST /auth/bootstrap` on an empty DB → 200, cookie set (assert `httponly`/`samesite=lax` like the existing login cookie tests), `GET /auth/me` with that cookie succeeds, one `bootstrap.success` audit row written; `POST /auth/bootstrap` when an Administrator already exists (via `seed_user`) → 409 `administrator_exists`, no cookie set, no second `User` row created.
  - [x] Backend: a concurrency test is optional/nice-to-have (exercising `acquire_bootstrap_lock` under real concurrent requests is awkward in a single-connection test client) — do not skip the sequential "second call after first succeeded → 409" test above, that is the actual required regression guard; a true two-connection race test is not required to satisfy the ACs.
  - [x] Frontend (`vitest` + RTL): **update `web/src/pages/LoginPage.test.tsx`'s existing three tests first** — they currently `vi.stubGlobal('fetch', vi.fn().mockResolvedValue(<single-response>))`, which will break once `LoginPage` fires a `GET /auth/bootstrap-status` call on mount before any login submission. Change each mock to a `mockImplementation` that branches on the request URL: return `{bootstrap_required: false}` for `/auth/bootstrap-status` and the existing canned response for `/auth/login`. This is a required fix, not optional — the three existing tests will fail against the new `LoginPage` otherwise, which is exactly the kind of regression this workflow exists to prevent.
  - [x] Frontend: new `LoginPage.test.tsx` cases — bootstrap-status returns `bootstrap_required: true` → the bootstrap form renders (assert on its distinguishing heading/copy), not the standard login form.
  - [x] Frontend: new `web/src/pages/BootstrapForm.test.tsx` — happy path (submit → navigates to `/home`); 409 error path (inline message shown, no navigation); network-failure path (generic message shown, no navigation) — mirror `LoginPage.test.tsx`'s existing three-case structure exactly.
  - [x] No CI, Nginx, or Vite proxy changes needed — `docker/nginx/nginx.conf`'s existing `location /auth/` block and `vite.config.ts`'s existing `/auth` proxy entry are both prefix matches that already cover `/auth/bootstrap-status` and `/auth/bootstrap` (verified by inspection; Story 1.1's Task 7 already closed this gap for the whole `/auth/` prefix, not just `/auth/login`).

### Review Findings

- [x] [Review][Defer] Bootstrap endpoint has no defense against a hostile first caller — permanent, unauthenticated admin-creation race — deferred, pre-existing. Reason: `POST /auth/bootstrap` is unauthenticated by design and defends against a racing *second* caller (advisory lock) and *later* callers (permanent `has_any_administrator` gate), but any anonymous visitor who reaches a freshly deployed, not-yet-bootstrapped instance before the real operator does becomes the permanent Administrator. Compounding this: `pg_advisory_xact_lock` (`adapters/persistence/users.py:76-80`) blocks indefinitely with no timeout, so a flood of concurrent unauthenticated bootstrap POSTs would each hold a DB connection open indefinitely. Decision: mitigation is expected to come from deployment/network isolation (e.g. firewalling the instance until the first Administrator is created), not app code. Revisit if network-level isolation isn't feasible for a given deployment.
- [ ] [Review][Patch] Losing the bootstrap race leaves the operator stuck on the bootstrap form with no way back to login [web/src/pages/BootstrapForm.tsx, web/src/pages/LoginPage.tsx] — If `POST /auth/bootstrap` returns 409 (another request won the race), `BootstrapForm.tsx` shows the inline error but never resets `LoginPage.tsx`'s `bootstrapRequired` state (no router change per this story's Task 5, so re-navigating won't remount `LoginPage`). Fix: add a "back to login" link/button on the 409 error that resets `LoginPage`'s `bootstrapRequired` state via a callback prop, so the operator can return to the standard login form without a full page reload.
- [ ] [Review][Patch] Session-cookie helper commits before creating the JWT, reintroducing the audit/session race Story 1.1 explicitly fixed [api/auth/routes.py:69-80,103-108,152-154] — `_set_session_cookie()` calls `create_access_token()` internally but is invoked *after* `session.commit()` in both `login` and `bootstrap`. If token creation (or `set_cookie`) fails, the `login.success`/`bootstrap.success` audit row (and, for bootstrap, the new Administrator `User` row) are already durably committed with no session ever issued — exactly what the pre-existing ordering, and this story's own Dev Notes ("build the JWT before the route's `session.commit()`"), required avoiding. Fix: call `create_access_token()` before `session.commit()`; only `response.set_cookie(...)` after.
- [ ] [Review][Patch] `BootstrapService.bootstrap()` re-implements the existence check instead of calling `is_required()` [domain/bootstrap.py] — `if await self._users.has_any_administrator(): raise BootstrapAlreadyComplete()` duplicates `is_required()`'s logic inline instead of `if not await self.is_required(): raise ...`, contradicting this story's own "one check, multiple callers" rule (Task 2). Behaviorally identical today; trivial fix.
- [ ] [Review][Patch] No audit entry written when a bootstrap attempt is rejected [domain/bootstrap.py, api/auth/routes.py:143-150] — `AuthenticationService.login` writes a `login.failure` audit row on every rejected attempt (AD-7's uniform audit-logging convention), but `BootstrapService.bootstrap()` writes nothing when `BootstrapAlreadyComplete` is raised. Repeated post-bootstrap probing leaves zero audit trail. Fix: write a `bootstrap.failure`-style audit entry before raising, mirroring login's convention.
- [x] [Review][Defer] Username collision with a pre-existing non-Administrator user is unhandled (surfaces as a bare 500, not the app's error envelope) [domain/bootstrap.py] — deferred, pre-existing. Reason: currently unreachable — the only way to create any `users` row today is via this same bootstrap endpoint (which locks itself after the first Administrator); Epic 3 ("Manage Users"), the only future path that could seed a colliding non-Administrator username, is still backlog. Revisit when Epic 3 ships.
- [x] [Review][Defer] `BootstrapForm.tsx` duplicates `LoginPage.tsx`'s layout and submit-handling logic near verbatim [web/src/pages/BootstrapForm.tsx, web/src/pages/LoginPage.tsx] — deferred, pre-existing. Reason: this story's own Dev Notes discourage over-abstracting a one-time flow, and no third consumer exists yet to justify extraction. Revisit if a third similar form appears (e.g. Story 1.5's password reset).

## Dev Notes

- **Why "any Administrator, active or inactive" — not just active — gates bootstrap (`[ASSUMPTION]`).** The epics AC says "at least one Administrator already exists" without qualifying active/inactive, and Story 1.3 (not yet built) will add a last-admin guard preventing the *last active* Administrator from being deleted/deactivated — but that guard doesn't exist yet, and even once it does, this codebase has no path before Epic 3 to deactivate anyone. Gating on "any administrator row at all" (not just active ones) is the more conservative, secure choice: it guarantees `POST /auth/bootstrap` can never reopen once a real Administrator has ever existed, regardless of later deactivation. Counting only active admins would risk a scenario (even if currently unreachable) where deactivating the sole admin silently reopens an unauthenticated account-creation endpoint — treat that as a standing risk this story closes off permanently, not something to leave to Story 1.3.
- **The advisory lock is this story's own architectural decision, not something the Architecture spine specifies.** Nothing in `ARCHITECTURE-SPINE.md` addresses first-run bootstrap concurrency (the spine's own rubric review flagged that AD-8's "every portal route" rule doesn't even reconcile with bootstrap being unauthenticated — see References). `pg_advisory_xact_lock` is the standard Postgres idiom for "serialize this rare, one-time operation" without inventing a job-queue or a SERIALIZABLE-isolation-plus-retry scheme, which would be over-engineering for a first-run action a deployment operator triggers once. Follow the Task 1/2 design exactly (lock → re-check → insert, all in one transaction) rather than a simpler "check then insert" — the simpler version has a real, if narrow, race window that would let a double-submit or two racing operators both create an Administrator, and — far more importantly — has no mechanism to definitively close the endpoint after first use.
- **`POST /auth/bootstrap` is unauthenticated by necessity (matches `/auth/login`'s existing posture), not an oversight.** AD-8 requires "every portal route" to depend on the shared auth dependency, but bootstrap — like login — cannot require a session, since it exists precisely for when none is possible. The permanent-lockout `if has_any_administrator(): raise` (Task 4) is what keeps this from being a standing security hole, not the absence of `get_current_user`.
- **No confirm-password field, no separate `role` selector in the bootstrap form.** The AC only requires "a valid new Administrator username/password"; `role` is hardcoded to `ADMINISTRATOR` server-side (the bootstrap endpoint has exactly one purpose). Do not add UI or API surface beyond what Task 4/6 specify — this is a one-time, single-purpose flow.
- **Copy/voice convention (established by `epics.md` UX-DR25, already in force for this codebase):** error/empty-state/confirmation copy names the actual cause or consequence directly, never generic filler. `BootstrapForm`'s heading and the 409 message should read as what's actually happening ("An Administrator account already exists" — not "Something went wrong"), consistent with `LoginPage`'s existing `"Invalid username or password"` precedent.
- **No Story 1.6 design tokens yet** — same note Story 1.1's Dev Notes carried forward: `web/src/App.tsx`'s theme is still `createTheme()` with no brand overrides. Build `BootstrapForm` against MUI's stock theme, matching `LoginPage`'s current styling exactly (same `Container maxWidth="xs"`, same spacing) — don't anticipate Story 1.6.
- **No new Alembic migration needed.** `UserModel`/the `users` table (including the `role` column) already exist from Story 1.1's migration (`98ddc369b175`) — this story only adds a new row-creation path, not new schema.
- **Do not touch `docker/nginx/nginx.conf` or `web/vite.config.ts`.** Both already proxy the full `/auth/` prefix (Story 1.1 Task 7 / Task 6) — re-verified by inspection during this story's creation. Adding either `/auth/bootstrap-status` or `/auth/bootstrap` there is unnecessary scope.

### Project Structure Notes

- New backend files: `domain/bootstrap.py`, `tests/domain/test_bootstrap_service.py`, and either an extension of `tests/api/test_auth_routes.py` or a new `tests/api/test_bootstrap_routes.py` (either is fine — `test_auth_routes.py` already covers the `/auth` router broadly; a dedicated file is only marginally cleaner).
- Modified backend files: `ports/users.py` (two new abstract methods), `adapters/persistence/users.py` (two new implementations), `api/auth/routes.py` (two new routes + the extracted cookie-setting helper).
- New frontend files: `web/src/pages/BootstrapForm.tsx`, `web/src/pages/BootstrapForm.test.tsx`.
- Modified frontend files: `web/src/pages/LoginPage.tsx` (status check + conditional render), `web/src/pages/LoginPage.test.tsx` (fetch-mock fix, required — see Task 7).
- No new top-level directories, no router changes, no migration, no Nginx/Vite changes. Fully additive to the existing `domain/`, `ports/`, `adapters/persistence/`, `api/auth/` packages and `web/src/pages/`.

### Previous Story Intelligence (from 1-1-administrator-login-session)

- **`AuthenticationService`'s constructor-injection + domain-owns-the-audit-write pattern is the template to follow exactly** for `BootstrapService` — same three collaborators, same "route only orchestrates, domain calls the repository and writes the audit entry" split (AD-1). Do not have `api/auth/routes.py` call `AuditLogRepository.add()` or `UserRepository.add()` directly — that was Story 1.1's own first review finding (a real AD-1 violation, since fixed).
- **Commit token creation before `session.commit()`** — Story 1.1's review reordered login so a token-creation failure leaves nothing committed. Apply the same ordering to bootstrap: build the `BootstrapService.bootstrap()` result and the JWT before the route's `session.commit()`.
- **`LoginRequest`'s field constraints exist for a reason** (bcrypt's silent 72-byte truncation) — reuse them verbatim for `BootstrapRequest`, don't redefine looser ones.
- **`get_settings.cache_clear()` pattern** — if a bootstrap test needs to override `ENVIRONMENT` like `test_login_cookie_is_secure_outside_development` does, follow that exact `monkeypatch.setenv` + `get_settings.cache_clear()` (before and after, in a `try`/`finally`) pattern; don't invent a different settings-override mechanism. (Not required by this story's ACs, but available if a bootstrap cookie-security test is added.)
- **`seed_user` fixture already supports everything Task 7's backend tests need** (`role=Role.ADMINISTRATOR`, `status=UserStatus.INACTIVE` for the "inactive admin still gates bootstrap" test) — no new fixture required.
- **The `httpx2` import in `tests/conftest.py` is intentional, not a typo** — Story 1.1's own code review raised and dismissed this as a false positive. Do not "fix" it.

### Git Intelligence

- Commit `61c276e` ("auth") is the current `HEAD` and is Story 1.1 fully reviewed and merged — `domain/auth.py`, `ports/{users,auth,audit}.py`, `adapters/persistence/{users,audit_log}.py`, `api/auth/{routes,dependencies,tokens}.py`, and the full frontend login flow are all stable, verified against real infrastructure, and exactly as read during this story's creation (no drift). Build directly on top of it.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.2: First-Run Administrator Bootstrap]
- [Source: _bmad-output/planning-artifacts/epics.md#UX-DR11, #UX-DR23] (Login hosts bootstrap + reset as one IA surface; zero-Administrators auth edge state)
- [Source: _bmad-output/planning-artifacts/prds/prd-GrowthTrack-2026-07-14/prd.md#FR-1, #FR-2] (Administrator Login & Session; Role-Scoped Portal Access)
- [Source: _bmad-output/planning-artifacts/prds/prd-GrowthTrack-2026-07-14/review-edge-case-hunter.md] (FR-1/FR-9: "No Administrator exists yet" edge case — this story is its guard)
- [Source: _bmad-output/planning-artifacts/architecture/architecture-GrowthTrack-2026-07-14/ARCHITECTURE-SPINE.md#AD-1] (dependency direction — domain owns repository calls, route only orchestrates)
- [Source: _bmad-output/planning-artifacts/architecture/architecture-GrowthTrack-2026-07-14/ARCHITECTURE-SPINE.md#AD-7] (co-transactional audit write — `bootstrap.success` follows the same rule `login.success`/`login.failure` do)
- [Source: _bmad-output/planning-artifacts/architecture/architecture-GrowthTrack-2026-07-14/ARCHITECTURE-SPINE.md#AD-8] (shared auth choke-point — bootstrap is deliberately outside it, like login)
- [Source: _bmad-output/planning-artifacts/architecture/architecture-GrowthTrack-2026-07-14/reviews/review-rubric-walker.md] (Finding 7: AD-8 vs. bootstrap not reconciled in the spine itself — this story's Dev Notes resolve it the same way login already does)
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-GrowthTrack-2026-07-14/EXPERIENCE.md#Information Architecture, #Auth edge states] (Login surface hosts bootstrap; voice/tone/copy conventions)
- [Source: _bmad-output/implementation-artifacts/1-1-administrator-login-session.md] (constructor-injection pattern, commit-ordering, `seed_user` fixture, `httpx2` false-positive note)
- [Source: domain/auth.py], [Source: ports/users.py], [Source: ports/auth.py], [Source: ports/audit.py], [Source: api/auth/routes.py], [Source: api/auth/dependencies.py], [Source: adapters/persistence/users.py], [Source: adapters/persistence/audit_log.py], [Source: web/src/pages/LoginPage.tsx], [Source: web/src/pages/LoginPage.test.tsx], [Source: web/src/router.tsx], [Source: web/src/api/authClient.ts], [Source: docker/nginx/nginx.conf], [Source: web/vite.config.ts], [Source: pyproject.toml] (import-linter contracts, test config)

## Dev Agent Record

### Agent Model Used

Claude Sonnet 5 (claude-sonnet-5)

### Debug Log References

None — implementation proceeded without needing a debug log; all backend and frontend test suites passed on first full run after the fetch-mock fix described in Completion Notes.

### Completion Notes List

- Implemented the bootstrap-gate check on `UserRepository`/`SqlAlchemyUserRepository` (`has_any_administrator`, `acquire_bootstrap_lock` via `pg_advisory_xact_lock(890217364)`, transaction-scoped, no explicit unlock).
- Implemented `domain/bootstrap.py`'s `BootstrapService` following `AuthenticationService`'s constructor-injection/domain-owns-audit-write pattern exactly: `is_required()` is the single check reused by both the status endpoint and the create-gate; `bootstrap()` acquires the advisory lock first, re-checks existence after the lock is held, then creates the `ACTIVE` `ADMINISTRATOR` user and writes the co-transactional `bootstrap.success` audit entry.
- Added `GET /auth/bootstrap-status` and `POST /auth/bootstrap` to `api/auth/routes.py`. Extracted a shared `_set_session_cookie(response, user, settings)` helper used by both `login` and `bootstrap` so the cookie-issuing `set_cookie` call is not duplicated; both routes commit the transaction before calling the helper. `POST /auth/bootstrap` returns 409 `administrator_exists` (with `session.commit()` first, to release the advisory lock cleanly) when `BootstrapAlreadyComplete` is raised.
- `LoginPage.tsx` now checks `GET /auth/bootstrap-status` on mount (rendering `null` while in flight, matching `HomePage.tsx`'s loading convention), rendering the new `BootstrapForm` when `bootstrap_required === true` and falling back to the existing login form on `false` or any check failure.
- Added `web/src/pages/BootstrapForm.tsx`, structurally mirroring `LoginPage.tsx`, posting to `/auth/bootstrap`, with the "Create the first Administrator account" heading, navigating to `/home` on success, and showing inline/generic error messages on 409/network failure respectively.
- Backend tests: new `tests/domain/test_bootstrap_service.py` (8 tests, fake-repository style matching `test_auth_service.py`) and `tests/api/test_bootstrap_routes.py` (5 tests, real-DB style matching `test_auth_routes.py`) — all pass, plus the full existing 45-test backend suite (`pytest`) still passes with no regressions.
- Frontend tests: fixed `LoginPage.test.tsx`'s three pre-existing tests (they now stub `fetch` with a URL-branching `mockImplementation` returning `{bootstrap_required: false}` for the new mount-time status check, required since `LoginPage` now fires that call before any login submission) and added a fourth case asserting the bootstrap form renders when `bootstrap_required: true`. Added `web/src/pages/BootstrapForm.test.tsx` (3 tests) mirroring `LoginPage.test.tsx`'s three-case structure. Also fixed `App.test.tsx`, whose synchronous render+assert broke for the same root cause (the async bootstrap-status check now gates `LoginPage`'s first render) — not in the story's file list but a genuine regression from this story's change, fixed to keep the DoD's "no regressions" requirement.
- Verified: `ruff check .`, `mypy` (pre-existing false-positive `arg-type` errors on `FakeUserRepository`/`FakeAuditLogRepository` in both the new and pre-existing fake-repository test files, confirmed present on the unmodified baseline via `git stash` — not a regression), `lint-imports` (both import-linter contracts kept), full `pytest` (45 passed), `npm run typecheck`, `npm run lint`, and `npm run test` (11 passed) — all green.

### File List

- `ports/users.py` (modified)
- `adapters/persistence/users.py` (modified)
- `domain/bootstrap.py` (new)
- `api/auth/routes.py` (modified)
- `web/src/pages/LoginPage.tsx` (modified)
- `web/src/pages/BootstrapForm.tsx` (new)
- `web/src/pages/LoginPage.test.tsx` (modified)
- `web/src/pages/BootstrapForm.test.tsx` (new)
- `web/src/App.test.tsx` (modified)
- `tests/domain/test_bootstrap_service.py` (new)
- `tests/api/test_bootstrap_routes.py` (new)

### Change Log

- 2026-07-17: Implemented Story 1.2 (First-Run Administrator Bootstrap) — bootstrap-gate repository methods, `BootstrapService`, `GET /auth/bootstrap-status` + `POST /auth/bootstrap` endpoints, `LoginPage` conditional routing, `BootstrapForm` component, and full backend/frontend test coverage. Status moved to review.
