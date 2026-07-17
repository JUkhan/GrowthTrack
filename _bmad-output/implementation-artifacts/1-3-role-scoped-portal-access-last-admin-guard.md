---
baseline_commit: ea9f335e33f20fa960a292793496a5d6e1c111d3
---

# Story 1.3: Role-Scoped Portal Access & Last-Admin Guard

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As the system,
I want every portal route to enforce an Administrator-role check server-side and protect the last remaining Administrator account,
so that Phase 1's single-role RBAC story holds without exception.

## Acceptance Criteria

1. **Given** a Sales User or Manager account, **when** it attempts to obtain a portal session token, **then** the request is rejected. [Source: epics.md#Story 1.3]
2. **Given** any portal route, **when** it is implemented, **then** it depends on one shared Administrator-role-checking dependency, never an inline per-route check. [Source: epics.md#Story 1.3]
3. **Given** exactly one active Administrator remains, **when** an attempt is made to delete or deactivate that account, **then** it is blocked with an explanatory message. [Source: epics.md#Story 1.3]

## Tasks / Subtasks

- [x] Task 1: Reject non-Administrator roles at login (AC: #1)
  - [x] `domain/auth.py`: `AuthenticationService.authenticate()` — extend the existing `if not password_ok or user.status != UserStatus.ACTIVE: return None` guard to also reject `user.role != Role.ADMINISTRATOR`, in the same `if`. Add `Role` to the existing `from domain.models import AuditLogEntry, User, UserStatus` import line.
  - [x] **Keep this in the same boolean condition and the same generic `None` return** — do not add a distinct exception/response for "wrong role" vs. "wrong password"/"inactive." A distinct response would tell a caller a Sales User/Manager account exists under that username — exactly the leak Story 1.1's AC #2 ("no information leaks about whether the username exists") already closed for password/status; role must follow the identical rule. Password verification still runs unconditionally first (`password_ok = ...verify(...)`), so timing is unaffected — role is checked in the same `if`, alongside `status`, not before it.
  - [x] No change needed in `AuthenticationService.login()` — it already treats any `authenticate() is None` result as `InvalidCredentials` and writes the same `login.failure` audit entry regardless of cause. This one existing code path now covers role rejection for free.
- [x] Task 2: Extend the shared `get_current_user` dependency with the Administrator-role check (AC: #2)
  - [x] `api/auth/dependencies.py`: replace the `# Story 1.3 adds: reject if user.role != Role.ADMINISTRATOR.` comment with the actual check — `if user.role != Role.ADMINISTRATOR: raise _unauthorized()` — placed after the `user is None` check, before the `# Story 1.4 adds:` comment (leave that comment as-is; revocation stays out of scope here). Change the import to `from domain.models import Role, User`.
  - [x] Reuse the existing `_unauthorized()` helper (same 401 `{code: "unauthorized", message: "Not authenticated"}` shape as a missing/invalid token) — do not add a distinct "forbidden"/403 response or a different message. `get_current_user` is, per AD-8 and this story's own AC #2, the single choke-point every future portal route depends on, and every route in Phase 1 requires the Administrator role — there is no "authenticated but wrong role" case worth disambiguating to the caller, and a distinct response would leak role/account-existence information to whoever holds a non-Administrator token.
  - [x] No other route needs its own role check — that is the entire point of AC #2. `GET /auth/me` (the only current consumer of `get_current_user`) and every portal route any future story adds inherit this automatically by depending on the same dependency. If a future addition is tempted to add an inline `if current_user.role != ...` check, the shared dependency is where that check belongs instead — do not do it here or set a precedent for it.
- [x] Task 3: `UserRepository.count_active_administrators()` — the query the last-admin guard needs (AC: #3)
  - [x] `ports/users.py`: add `async def count_active_administrators(self) -> int: ...` as a new abstract method, placed after `has_any_administrator`, following that method's existing docstring/placement convention.
  - [x] `adapters/persistence/users.py`: implement as `SELECT COUNT(*) FROM users WHERE role = :role AND status = :status`, parameterized with `Role.ADMINISTRATOR.value` / `UserStatus.ACTIVE.value` (import `UserStatus` alongside the existing `Role, User` import). Mirror `has_any_administrator`'s existing `text()`-query style exactly — same file, same pattern, `COUNT` instead of `EXISTS`, with an added status filter.
- [x] Task 4: `domain/administrators.py` — new `LastAdministratorGuard` (AC: #3)
  - [x] A new domain module, separate from `domain/auth.py` and `domain/bootstrap.py` — this codebase's established one-class-one-job pattern (Story 1.2's `BootstrapService` precedent: a dedicated service per concern, not bolted onto an existing one).
  - [x] `class LastAdministratorError(Exception)` — raised when a mutation would leave zero active Administrators. Message: `"The last remaining Administrator account cannot be deleted or deactivated"` — FR-2's own wording verbatim, per UX-DR25's names-the-real-consequence convention. This exact message is what a future Epic 3 story surfaces to the Administrator, so get the wording right now rather than leaving it for Story 3.1 to invent.
  - [x] `class LastAdministratorGuard`: `def __init__(self, users: UserRepository) -> None`. Single collaborator, no `AuditLogRepository` — this guard performs no mutation and writes nothing; it only raises (see Dev Notes for why).
  - [x] `async def ensure_can_deactivate(self, target: User) -> None`: if `target.role != Role.ADMINISTRATOR or target.status != UserStatus.ACTIVE`, return immediately without querying the repository — a non-Administrator, or an Administrator who is already inactive, can never be "the last active Administrator" being newly removed. Otherwise call `count = await self._users.count_active_administrators()`; if `count <= 1`, raise `LastAdministratorError()`.
  - [x] **This guard has no caller yet in this story.** Epic 3's Story 3.1 ("Manage Users & Sales Teams") builds the actual deactivate/delete endpoint and will call `ensure_can_deactivate()` before soft-deleting or deactivating a `User` — that endpoint doesn't exist yet, so there is nothing to wire this into today. Do not build a deactivate/delete endpoint in this story to give the guard something to attach to; that endpoint's real shape (soft-delete semantics, audit co-transactionality, request/response contract) is Story 3.1's job to design. Verify this task via domain-level unit tests against a fake repository (Task 5) — see Dev Notes for why this is the correct scope, not a shortcut.
- [x] Task 5: Tests (AC: all)
  - [x] `tests/domain/test_auth_service.py`: extend `_make_user` with an optional `role: Role = Role.ADMINISTRATOR` parameter (keeps every existing call site unchanged). Add: `authenticate()` returns `None` for a correct password on a `Role.SALES_USER` account and again for `Role.MANAGER` (two cases); `login()` raises `InvalidCredentials` and writes a `login.failure` audit entry for a non-Administrator role (mirror the existing `test_login_raises_for_an_inactive_user_and_still_audits_the_failure` structure).
  - [x] `tests/api/test_auth_routes.py`: `seed_user(username="sales", role=Role.SALES_USER)` (the fixture in `tests/conftest.py` already accepts `role` — no fixture change needed) → `POST /auth/login` with the correct password → 401, identical `invalid_credentials` envelope to `test_wrong_password_returns_the_same_generic_401_shape`, no cookie set. Import `Role` from `domain.models` in this file (not currently imported there).
  - [x] `tests/api/test_auth_routes.py`: seed a `Role.SALES_USER` user, craft a **valid** token directly via `create_access_token(user.id)` and set it as the cookie (exactly like `test_me_with_expired_token_returns_401`/`test_me_with_tampered_token_returns_401` already bypass login to hand-craft a token), then `GET /auth/me` → 401. This is what actually exercises AC #2's shared-dependency role check independent of AC #1's login-time gate — the two ACs are two separate code paths (Task 1 vs. Task 2) and need two separate tests, even though in Phase 1 a non-Administrator token can currently only be minted this artificial way.
  - [x] New `tests/domain/test_last_administrator_guard.py` — a local `FakeUserRepository` defined in this file (matching `test_bootstrap_service.py`'s per-file-local-fake convention; do not import/share a fake across test files) implementing `count_active_administrators` (return a configured int, plus a call-count counter for the short-circuit assertions below):
    - `ensure_can_deactivate` raises `LastAdministratorError` for an active-Administrator target when `count_active_administrators()` returns `1`.
    - does not raise when `count_active_administrators()` returns `2`.
    - does not raise for a `Role.SALES_USER` target regardless of the configured count — assert the fake's `count_active_administrators` was never called (proves the short-circuit, not just a lucky count value).
    - does not raise for an already-`UserStatus.INACTIVE` Administrator target — same short-circuit assertion.
  - [x] New `tests/adapters/persistence/test_user_repository.py` (new `tests/adapters/` and `tests/adapters/persistence/` directories — first files in either; add `__init__.py` files only if the existing `tests/api`/`tests/domain`/`tests/ports` directories have them — check before assuming). Real-DB style, using the `seed_user` fixture and a directly-instantiated `SqlAlchemyUserRepository` (mirror `tests/api/test_auth_routes.py`'s `_audit_rows()` direct-query convention — this method has no HTTP endpoint of its own to exercise it through): `count_active_administrators()` returns `0` on an empty table; `1` after seeding one active Administrator; `2` after seeding a second; unchanged (still `1`) after additionally seeding a `Role.SALES_USER` and a separate `UserStatus.INACTIVE` Administrator (both must be excluded from the count).

### Review Findings

- [x] [Review][Defer] No audit entry for role-based authorization rejection at `get_current_user` [api/auth/dependencies.py:53-54] — deferred, belongs to Story 1.4 (revocation). Login-time role rejection (Task 1, `domain/auth.py`) writes a `login.failure` audit entry via `AuthenticationService.login`. Per-request role rejection at the shared `get_current_user` dependency writes nothing — a previously-issued, still-valid token for a user whose role no longer qualifies (e.g. downgraded) is silently 401'd with no forensic record, unlike every other enforcement point in this story.
- [x] [Review][Patch] No test for `LastAdministratorGuard`'s `count == 0` boundary [tests/domain/test_last_administrator_guard.py]
- [x] [Review][Patch] Unrelated blank-line insertion in sprint-status.yaml diff [_bmad-output/implementation-artifacts/sprint-status.yaml:2-3]
- [x] [Review][Defer] `LastAdministratorGuard.ensure_can_deactivate` has a check-then-act race, no locking [domain/administrators.py:260-266] — deferred, pre-existing design gap; not fixable in isolation since locking strategy depends on Story 3.1's transaction/mutation design (per this story's own Dev Notes)
- [x] [Review][Defer] `get_current_user` never checks `user.status` — an inactive Administrator's still-valid token retains full portal access [api/auth/dependencies.py:37-58] — deferred, pre-existing (confirmed identical in HEAD before this diff, not introduced by this change)
- [x] [Review][Defer] `count_active_administrators` query has no index on `role`/`status` columns [adapters/persistence/users.py] — deferred, pre-existing schema (columns from Story 1.1's migration `98ddc369b175`); low risk at current table size

## Dev Notes

- **This is a backend-only, no-UI story.** Like Story 1.2, this story's "As the system" framing (not "As an Administrator") signals no Administrator-facing screen is being built. `web/` is untouched — do not add frontend routes or components.
- **AC #1 and AC #2 are two separate enforcement points, not one — implement and test both.** AC #1 (Task 1) stops a non-Administrator from ever obtaining a token in the first place, closing the exact gap Story 1.1's own Dev Notes flagged and deferred: *"That gap is closed by Story 1.3 ('Sales User or Manager attempts to obtain a portal session token → rejected'), which is the story that actually enforces role at the auth boundary."* AC #2 (Task 2) is AD-8's separate requirement that every portal route *also* re-checks role via the shared dependency, independent of how the token was obtained — defense in depth, and the exact mechanism `get_current_user`'s own placeholder comment already anticipated. Neither makes the other redundant; a token minted before this story shipped (there are none in practice, but the principle holds for any future path that might someday mint one) would only be caught by Task 2, not Task 1.
- **AC #3's guard is deliberately unwired in this story — that is correct, not incomplete.** No deactivate/delete endpoint exists yet (Epic 3/Story 3.1 is still `backlog` per sprint-status.yaml) for `LastAdministratorGuard.ensure_can_deactivate()` to be called from. The Architecture spine's own reconciliation review flagged this precise gap: *"'Last Administrator cannot be deleted/deactivated' (FR-2) has no stated enforcement point... Not mentioned anywhere"* [review-reconcile-inputs.md]. This story is what closes that gap, as reusable domain infrastructure Story 3.1 will call. This follows epics.md's own Story 2.4 precedent — a domain computation built and verified by tests directly, ahead of the UI/endpoint that will eventually consume it (2.4: *"verification happens via automated tests against the domain computation and repository layer directly... this story's acceptance does not wait on Epic 4"*). Do not skip Task 4 thinking it's premature, and do not build a deactivate/delete endpoint here just to give the guard a caller — that endpoint's real shape is Story 3.1's to design.
- **Why the guard takes no `AuditLogRepository` collaborator.** Unlike `AuthenticationService`/`BootstrapService`, `LastAdministratorGuard` performs no mutation and writes nothing — it only raises before a mutation would proceed. AD-7's co-transactional audit rule binds the *mutation itself* (the `deactivate`/`delete` call Story 3.1 will build), not a guard check that runs ahead of it and may block it entirely. Story 3.1's own service method is what writes the `AuditLogEntry` for the directory action (successful or blocked) — do not add an audit write inside this guard.
- **Why role is checked in the same `if` as `status`/`password_ok` in `authenticate()`, not a separate check.** Identical reasoning to Story 1.1's inactive-user check: a non-Administrator role and an inactive account must produce byte-identical 401 responses and cost the same bcrypt work, or response timing/shape becomes an oracle for "does this username exist, and in what state." Do not special-case role into its own `if`/`return` — that reintroduces the exact leak Story 1.1's AC #2 and this story's AC #1 both guard against.
- **No new Alembic migration needed.** `UserModel.role`/`.status` (the `users` table) already exist from Story 1.1's migration (`98ddc369b175`) — `count_active_administrators` is a new query against existing columns, not new schema.
- **No Nginx/Vite/CI changes needed.** This story adds no new routes (Task 2 extends an existing dependency; Task 1 extends an existing service method) and no new frontend surface.

### Project Structure Notes

- New backend files: `domain/administrators.py`, `tests/domain/test_last_administrator_guard.py`, `tests/adapters/persistence/test_user_repository.py` (new `tests/adapters/` and `tests/adapters/persistence/` directories).
- Modified backend files: `domain/auth.py` (role check in `authenticate()`), `api/auth/dependencies.py` (role check in `get_current_user()`), `ports/users.py` (`count_active_administrators` abstract method), `adapters/persistence/users.py` (`count_active_administrators` implementation), `tests/domain/test_auth_service.py`, `tests/api/test_auth_routes.py`.
- No frontend files touched, no router changes, no migration, no Nginx/Vite/CI changes. Fully additive to the existing `domain/`, `ports/`, `adapters/persistence/`, `api/auth/` packages.

### Previous Story Intelligence (from 1-2-first-run-administrator-bootstrap)

- **One-class-one-job domain services, constructor-injected with only the collaborators actually used** — `BootstrapService` took exactly the collaborators it needed (not `AuthenticationService`'s full set). `LastAdministratorGuard` follows the same minimalism: `users` only, no `password_hasher`/`audit_log`.
- **`FakeUserRepository`/`FakeAuditLogRepository` are defined locally per test file, not shared/imported across files** — `test_auth_service.py` and `test_bootstrap_service.py` each define their own, implementing only the methods that file's tests need. Follow this for `test_last_administrator_guard.py`'s new fake too.
- **A new abstract method on an ABC port (`UserRepository`) does not break existing duck-typed `FakeUserRepository` test doubles at runtime** — they aren't subclasses of `UserRepository`, just structurally similar classes, so Python's ABC machinery never enforces completeness on them. The pre-existing `mypy` `arg-type` false-positives on these fakes (confirmed pre-existing via `git stash` during Story 1.2's review) will gain one more instance of the same category on `count_active_administrators` — expected, not a new regression to chase down.
- **`seed_user`'s `role`/`status` parameters already exist** (`tests/conftest.py`) — no fixture changes needed for this story's API-level tests.
- **Verify against real infrastructure, not mocks, for anything DB-backed** — Stories 1.1/1.2 both ran their full test suites against a live Postgres instance, not an in-memory substitute; `tests/adapters/persistence/test_user_repository.py` (Task 5) continues that convention via the existing `seed_user`/`create_session_factory` fixtures.

### Git Intelligence

- Commit `ea9f335` ("bootstrap") is the current `HEAD` and is Story 1.2 fully reviewed and merged — its `[Review][Patch]` findings are already applied in `api/auth/routes.py`/`domain/bootstrap.py` as read during this story's creation (verified directly, not assumed from Story 1.2's own Tasks section, which describes pre-review state). `domain/bootstrap.py`, the `_set_session_cookie` helper, and the `BootstrapForm` frontend flow are all stable. Build directly on top of it.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.3: Role-Scoped Portal Access & Last-Admin Guard]
- [Source: _bmad-output/planning-artifacts/prds/prd-GrowthTrack-2026-07-14/prd.md#FR-2] ("last remaining Administrator account cannot be deleted or deactivated" — verbatim source of the guard's error message)
- [Source: _bmad-output/planning-artifacts/architecture/architecture-GrowthTrack-2026-07-14/ARCHITECTURE-SPINE.md#AD-8] (shared auth dependency: JWT + Administrator role + revocation — this story delivers the role-check third of that pipeline)
- [Source: _bmad-output/planning-artifacts/architecture/architecture-GrowthTrack-2026-07-14/reviews/review-reconcile-inputs.md] ("'Last Administrator cannot be deleted/deactivated' (FR-2) has no stated enforcement point... Not mentioned anywhere" — this story's Task 3/4 close that gap)
- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.4] (precedent for domain logic built/verified ahead of its consuming UI)
- [Source: _bmad-output/implementation-artifacts/1-1-administrator-login-session.md#Dev Notes] ("Role enforcement is explicitly out of scope here... closed by Story 1.3" — the gap this story closes)
- [Source: _bmad-output/implementation-artifacts/1-2-first-run-administrator-bootstrap.md] (one-class-one-job domain service pattern, local-per-file Fake repository convention, real-infrastructure testing convention)
- [Source: domain/auth.py], [Source: domain/models.py], [Source: api/auth/dependencies.py], [Source: api/auth/routes.py], [Source: ports/users.py], [Source: adapters/persistence/users.py], [Source: tests/conftest.py], [Source: tests/domain/test_auth_service.py], [Source: tests/domain/test_bootstrap_service.py], [Source: tests/api/test_auth_routes.py], [Source: pyproject.toml] (import-linter contracts)

## Dev Agent Record

### Agent Model Used

claude-sonnet-5

### Debug Log References

- `uv run pytest -q` — 58 passed (0 failed)
- `uv run ruff check .` — All checks passed!
- `uv run mypy .` — 4 pre-existing `arg-type` false-positives on `FakeUserRepository`/`FakeAuditLogRepository` in `test_bootstrap_service.py`/`test_auth_service.py` (confirmed pre-existing via `git stash`); no new errors
- `uv run lint-imports` — 2 kept, 0 broken

### Completion Notes List

- Task 1: `AuthenticationService.authenticate()` now rejects `user.role != Role.ADMINISTRATOR` in the same boolean condition as the existing `password_ok`/`status` check, preserving the single generic `None` return and unconditional bcrypt verify (no new timing/response oracle). `login()` needed no change — it already treats any `None` as `InvalidCredentials` and audits `login.failure`. Updated the module docstring (stale "Story 1.3 deliberately out of scope" note).
- Task 2: `get_current_user` now raises the existing `_unauthorized()` 401 after the `user is None` check, before the Story 1.4 revocation placeholder comment — no new response shape, no other route needs its own check.
- Task 3: Added `UserRepository.count_active_administrators()` (abstract) and `SqlAlchemyUserRepository.count_active_administrators()` (`SELECT COUNT(*) ... WHERE role = :role AND status = :status`), mirroring `has_any_administrator`'s `text()`-query style. Used `result.scalar_one()` rather than `.scalar()` to keep mypy satisfied (`COUNT(*)` always returns exactly one non-null row, so `scalar_one()` is both correct and typed as non-Optional, unlike `.scalar()`'s `Any | None`).
- Task 4: New `domain/administrators.py` with `LastAdministratorError` (FR-2's exact wording) and `LastAdministratorGuard.ensure_can_deactivate()`, short-circuiting on non-Administrator/already-inactive targets before querying the repository. No caller wired in this story per Dev Notes — Story 3.1 will call it. No audit write (guard performs no mutation).
- Task 5: Extended `_make_user` in `test_auth_service.py` with an optional `role` param; added Sales User/Manager `authenticate()`-returns-`None` tests and a `login()` non-Administrator-role audit test. Added `test_non_administrator_role_returns_the_same_generic_401_shape` and `test_me_with_a_valid_token_for_a_non_administrator_returns_401` to `test_auth_routes.py` (AC #1 and AC #2 are separately exercised, per Dev Notes). New `tests/domain/test_last_administrator_guard.py` (local `FakeUserRepository` with a call-count counter proving the short-circuit) and new `tests/adapters/persistence/test_user_repository.py` (real-DB style via `seed_user`/`create_session_factory`, no `__init__.py` added — matches sibling test dirs). Full suite: 58 passed.

### File List

- `domain/auth.py` (modified — role check in `authenticate()`, docstring update)
- `api/auth/dependencies.py` (modified — role check in `get_current_user()`)
- `ports/users.py` (modified — `count_active_administrators` abstract method)
- `adapters/persistence/users.py` (modified — `count_active_administrators` implementation)
- `domain/administrators.py` (new — `LastAdministratorError`, `LastAdministratorGuard`)
- `tests/domain/test_auth_service.py` (modified — role tests)
- `tests/api/test_auth_routes.py` (modified — role tests)
- `tests/domain/test_last_administrator_guard.py` (new)
- `tests/adapters/persistence/test_user_repository.py` (new)

### Change Log

- 2026-07-17: Implemented Story 1.3 (Role-Scoped Portal Access & Last-Admin Guard) — Administrator-role rejection at login (`AuthenticationService.authenticate()`), shared-dependency role check (`get_current_user`), `UserRepository.count_active_administrators()` + `LastAdministratorGuard` domain infrastructure for the last-admin protection (unwired pending Story 3.1), and full backend test coverage. Status moved to review.
