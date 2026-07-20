---
baseline_commit: 9ea7cf0
---

# Story 3.1: Manage Users & Sales Teams

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an Administrator,
I want to add, edit, and remove individual Users and Sales Teams,
so that the directory reflects who's actually on the ground and how they're organized.

## Acceptance Criteria

1. **Given** a new User (Name, Mobile, Role, Team), **when** I submit the Directory form, **then** the User is created, phone-number uniqueness is validated inline on blur, and the change is audit-logged in the same transaction as the write. [Source: epics.md#Story 3.1, prd.md#FR-9, ARCHITECTURE-SPINE.md#AD-7]
2. **Given** an existing User or Team, **when** I edit or remove it, **then** the change takes effect for future notifications and reporting, and is audit-logged co-transactionally. [Source: epics.md#Story 3.1, prd.md#FR-9, ARCHITECTURE-SPINE.md#AD-7]
3. **Given** a User or Team is removed, **when** the removal is processed, **then** it is soft-deleted, never hard-deleted, so notification/audit history referencing it is never orphaned. [Source: epics.md#Story 3.1, ARCHITECTURE-SPINE.md#AD-4]
4. **Given** a Sales Team, **when** created, edited, or removed, **then** the same CRUD-and-audit guarantees apply as for a User. [Source: epics.md#Story 3.1]
5. **[Derived — not stated verbatim in epics.md, required to prevent an ungoverned-Administrator-creation security gap]** **Given** the Directory form, **when** a User is created through it, **then** Role is restricted to Sales User or Manager only — Administrator accounts can be created only through Epic 1's bootstrap flow (Story 1.2), never through this form, because this form has no username/password capture and an Administrator row without portal credentials could never log in. [Source: _bmad-output/planning-artifacts/prds/prd-GrowthTrack-2026-07-14/addendum.md#A5, ARCHITECTURE-SPINE.md#AD-8, prd.md#FR-2]
6. **[Derived — closes the loop `domain/administrators.py`'s docstring explicitly left open for this story]** **Given** exactly one active Administrator remains, **when** an attempt is made to remove/deactivate that account through this story's User-removal endpoint, **then** it is blocked with `LastAdministratorGuard` — Administrators are listed and removable through this same directory (just not creatable or editable through it; see Dev Notes' Role-Handling Matrix). [Source: domain/administrators.py, epics.md#Story 1.3 AC #3, prd.md#FR-2]

## Tasks / Subtasks

- [x] Task 1: Alembic migration — extend `users` and `teams` for directory CRUD (AC: #1, #3, #4, #5, #6)
  - [x] **`users` table.** The existing `username`/`hashed_password` columns are `NOT NULL` because Story 1.1/1.2 built them exclusively for Administrator portal login. Per AC #5, Sales User/Manager rows created by this story never authenticate to the portal (Addendum A5), so they must NOT be forced to have a username/password. Do the opposite instead — relax those two columns:
    ```python
    op.alter_column("users", "username", nullable=True)
    op.alter_column("users", "hashed_password", nullable=True)
    op.add_column("users", sa.Column("name", sa.String(), nullable=True))
    op.add_column("users", sa.Column("mobile", sa.String(), nullable=True))
    op.add_column("users", sa.Column("team_id", sa.UUID(), nullable=True))
    op.create_unique_constraint("uq_users_mobile", "users", ["mobile"])
    op.create_foreign_key("fk_users_team_id_teams", "users", "teams", ["team_id"], ["id"])
    ```
    `name`/`mobile`/`team_id` stay DB-nullable (existing Administrator rows keep them `NULL` forever) — required-ness for Sales User/Manager is enforced at the domain-service layer (Task 4), not the schema. This sidesteps a risky backfill migration entirely (there is no sensible default `name`/`mobile` value for existing bootstrap-created Administrator rows). Postgres treats `NULL` as distinct-from-`NULL` in a plain `UNIQUE` constraint, so multiple Administrators with `mobile IS NULL` do **not** collide — no partial/filtered index needed, a plain `UniqueConstraint` is correct as-is (same reasoning already applies to `username`, unchanged).
  - [x] **`teams` table.** `adapters/persistence/teams.py`'s own docstring flagged this exact debt: *"full CRUD (soft-delete status, optimistic-concurrency version column, management UI) is Epic 3 Story 3.1's job."* Add both columns with `server_default` (the table already has rows from Story 2.1's ingestion in any real deployment — same reasoning `8ae7e5d0d8c9`'s `failed_login_count` migration already documents):
    ```python
    op.add_column("teams", sa.Column("status", sa.String(), nullable=False, server_default="active"))
    op.add_column("teams", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    ```
    `server_default` (not just a Python-side dataclass default) is required so `adapters/persistence/teams.py#get_or_create_by_name`'s existing raw `insert(TeamModel).values(id=..., name=...)` — used by Story 2.1's nightly ingestion, untouched by this story — keeps working without modification; Postgres fills `status`/`version` from the column default when the `INSERT` omits them.
  - [x] Downgrade: reverse each `op.*` call in the opposite order (drop FK/unique constraint before dropping columns; `alter_column` back to `nullable=False` only if you also accept it will fail against any row this story created with `username IS NULL` — note that in the downgrade docstring rather than silently writing a downgrade that can't actually run against post-migration data).

- [x] Task 2: `domain/models.py` — extend `User`/`Team` (AC: #1, #3, #4)
  - [x] `User` dataclass: change `username: str` → `username: str | None`, `hashed_password: str` → `hashed_password: str | None`; add `name: str | None = None`, `mobile: str | None = None`, `team_id: uuid.UUID | None = None`. Every existing caller (`domain/bootstrap.py`, `domain/auth.py`, `tests/conftest.py#seed_user`) constructs `User` with keyword args and never reads `username`/`hashed_password` as non-optional in a way that breaks — confirm this with `uv run mypy .` after the change, but do not add new validation to those files; this story is additive to `User`, not a rewrite of Epic 1's auth path.
  - [x] New `TeamStatus` `StrEnum` (`ACTIVE`/`INACTIVE`) — a **separate** enum from `UserStatus`, not a rename/reuse of it. `UserStatus` is referenced by `domain/auth.py`, `domain/administrators.py`, `adapters/persistence/users.py`, and multiple test files; renaming it to a shared generic `Status` for AD-4's "generalizing" language would be a repo-wide rename this story doesn't need (AD-4 generalizes the *concept*, not literally one Python type — `RecipientList`, the only other entity slated for the same treatment, doesn't exist until Story 3.2). Two small enums with identical values is the lower-blast-radius choice.
  - [x] `Team` dataclass: add `status: TeamStatus = TeamStatus.ACTIVE`, `version: int = 1`.

- [x] Task 3: Repository ports + adapters (AC: #1, #2, #3, #4)
  - [x] `ports/users.py` — add (`Any`-typed per this file's existing docstring convention, `ports` cannot import `domain`):
    ```python
    @abstractmethod
    async def get_by_mobile(self, mobile: str) -> Any: ...

    @abstractmethod
    async def list_all(self) -> list[Any]: ...  # ALL roles, ALL statuses — see Dev Notes' Role-Handling Matrix

    @abstractmethod
    async def update_directory_fields(
        self, user_id: uuid.UUID, name: str, mobile: str, team_id: uuid.UUID
    ) -> None: ...

    @abstractmethod
    async def deactivate(self, user_id: uuid.UUID) -> None: ...
    ```
    `deactivate` sets `status='inactive'`, bumps `version = version + 1` — no optimistic-concurrency precondition on the `UPDATE` (no `WHERE version = :expected`). Story 3.4 (Concurrent-Edit Conflict Detection) is the story that adds stale-version rejection across `User`/`Team`/`RecipientList` — do not implement that check here; this story only keeps `version` incrementing correctly so 3.4 has real data to work against.
  - [x] `adapters/persistence/users.py` — implement all four against `UserModel`. `SqlAlchemyUserRepository.add` (already exists) needs to also persist `name`, `mobile`, `team_id` — currently its `UserModel(...)` construction only sets `username`/`hashed_password`/`role`/`status`/`version`/`created_at`; extend it to pass through `name=user.name, mobile=user.mobile, team_id=user.team_id` too (all `None`-safe already since the columns are nullable). Also add the four new columns to `UserModel` itself (`name`, `mobile`, `team_id`) and to `_to_domain`.
  - [x] `ports/teams.py` — **do not modify the existing `list_all() -> list[tuple[uuid.UUID, str]]` method's signature or behavior.** `domain/metrics.py#DashboardMetricsService.get_summary` (Story 2.2, already shipped) calls it directly to resolve team names for the Dashboard's team-performance section; changing what it returns or filtering it to active-only teams is an unrequested regression risk to already-working code. Add new methods instead:
    ```python
    @abstractmethod
    async def add(self, team_id: uuid.UUID, name: str) -> None: ...

    @abstractmethod
    async def get_by_id(self, team_id: uuid.UUID) -> Any: ...

    @abstractmethod
    async def get_by_name(self, name: str) -> Any: ...

    @abstractmethod
    async def list_all_full(self) -> list[Any]: ...  # full Team rows (id, name, status, version), all statuses

    @abstractmethod
    async def update_name(self, team_id: uuid.UUID, name: str) -> None: ...

    @abstractmethod
    async def deactivate(self, team_id: uuid.UUID) -> None: ...
    ```
  - [x] `adapters/persistence/teams.py` — implement all six. `get_or_create_by_name` stays completely untouched (Story 2.1's ingestion path). Add a module-level `_to_domain(row: TeamModel) -> Team` free function (Story 2.3's Review Findings precedent: implement this as a free function from the start, not a `@staticmethod`) for `get_by_id`/`get_by_name`/`list_all_full` to share.

- [x] Task 4: `domain/recipients.py` (new file) — directory services (AC: #1, #2, #3, #4, #5, #6)
  - [x] Capability map fixes this file's location: `ARCHITECTURE-SPINE.md`'s Capability → Architecture Map lists CAP-5 as `api/recipients`, `domain/recipients`, governed by AD-4/AD-7/AD-9.
  - [x] `UserDirectoryService(users: UserRepository, audit_log: AuditLogRepository, last_admin_guard: LastAdministratorGuard)`:
    - `create_user(name: str, mobile: str, role: Role, team_id: uuid.UUID, actor_user_id: uuid.UUID) -> User` — raises `RoleNotAllowed` if `role == Role.ADMINISTRATOR` (defense-in-depth; the API layer's Pydantic `Literal["sales_user","manager"]` should already reject this before it reaches here — keep both, the domain layer must never trust the API layer alone). Raises `MobileTaken` if `await self._users.get_by_mobile(mobile)` returns non-`None`. Writes the `User` row (`status=UserStatus.ACTIVE`, `version=1`) and one `AuditLogEntry` (`action="user.created"`, `entity_type="User"`) in the same call — this method does not commit; the route commits (AD-7 pattern, mirrors `domain/auth.py#login`/`domain/bootstrap.py#bootstrap`).
    - `update_user(user_id: uuid.UUID, name: str, mobile: str, team_id: uuid.UUID, actor_user_id: uuid.UUID) -> User` — loads the target; raises `CannotEditAdministrator` if `target.role == Role.ADMINISTRATOR` (Administrators have no `name`/`mobile`/`team_id` semantics in this story — see Dev Notes' Role-Handling Matrix). Raises `MobileTaken` if the new mobile belongs to a **different** user (`existing.id != user_id`). Writes the update + audit entry (`action="user.updated"`).
    - `remove_user(user_id: uuid.UUID, actor_user_id: uuid.UUID) -> None` — loads the target, calls `await self._last_admin_guard.ensure_can_deactivate(target)` (raises `LastAdministratorError` — already defined in `domain/administrators.py`, propagate it as-is, do not wrap it in a new exception type) **before** calling `self._users.deactivate(...)`. This is the literal call site `domain/administrators.py`'s docstring says this story owns. Writes the deactivation + audit entry (`action="user.deactivated"`) — for a Sales User/Manager target the guard call is a no-op (its own existing `if target.role != Role.ADMINISTRATOR: return` short-circuit).
  - [x] `TeamDirectoryService(teams: TeamRepository, audit_log: AuditLogRepository)`:
    - `create_team(name: str, actor_user_id: uuid.UUID) -> Team` — raises `TeamNameTaken` if `await self._teams.get_by_name(name)` is non-`None` (pre-check; Phase 1 admin-portal concurrency is "much smaller and unspecified" per NFR-8, so this lightweight pre-check — no advisory lock — is proportionate, same trust level `get_or_create_by_name`'s own on-conflict-do-nothing already assumes for the ingestion path). Audit action `"team.created"`.
    - `update_team(team_id: uuid.UUID, name: str, actor_user_id: uuid.UUID) -> Team` — same `TeamNameTaken` check excluding the team's own current row. Audit action `"team.updated"`.
    - `remove_team(team_id: uuid.UUID, actor_user_id: uuid.UUID) -> None` — no last-something guard analog exists for Teams (that concept is User-specific/AD-11). Audit action `"team.deactivated"`.
  - [x] Exceptions (module-level, mirror `domain/auth.py`'s `InvalidCredentials`/`AccountLocked` style): `RoleNotAllowed`, `MobileTaken`, `CannotEditAdministrator`, `TeamNameTaken`.
  - [x] Opt-in consent: **do not** add any consent-related logic when `mobile` changes. Epics.md's Story 3.3 AC explicitly owns "changing a phone number revokes existing consent" — and no `OptInConsent`/consent column exists in the schema yet (Story 3.3 introduces it). This story only updates `User.mobile`; treat Story 3.3 as a backward extension that will add consent-revocation on top of this story's `update_user`, not a forward dependency this story must stub out (same "backward extension, not forward dependency" posture Story 2.2's Dev Notes used for its notification-status field).

- [x] Task 5: `api/recipients/routes.py` (new package) — REST endpoints (AC: #1, #2, #3, #4, #5, #6)
  - [x] New package `api/recipients/__init__.py` (empty, mirrors `api/dashboard/__init__.py`) + `api/recipients/routes.py`. Two `APIRouter`s in one file (mirrors `api/auth/routes.py` housing login/bootstrap/reset/theme together): `users_router = APIRouter(prefix="/users", tags=["recipients"])`, `teams_router = APIRouter(prefix="/teams", tags=["recipients"])`. Every route depends on `current_user: User = Depends(get_current_user)` (AD-8's shared choke-point — never an inline per-route check) and takes `actor_user_id=current_user.id` into the domain service call.
  - [x] `POST /users` — body `{name, mobile, role: Literal["sales_user","manager"], team_id}` (the `Literal` itself is the first line of defense for AC #5 — submitting `"administrator"` fails Pydantic validation with the standard `validation_error` envelope before the route body even runs). Catches `MobileTaken` → 409 `{code: "mobile_taken"}`; `RoleNotAllowed` → 422 `{code: "role_not_allowed"}` (defense-in-depth path, should be unreachable given the `Literal`).
  - [x] `GET /users` — returns all Users, **all roles included** (AC #6 depends on Administrators being visible/removable here), all statuses included (inactive rows stay visible with `status: "inactive"`, never hidden — matches this codebase's data-table convention of showing history rather than silently dropping rows). Resolve `team_name` per row via one `teams.list_all_full()` call built into a `{id: name}` dict (same shape `DashboardMetricsService.get_summary` already uses for `team_names`) — do not N+1 query per row.
  - [x] `GET /users/mobile-availability?mobile=...&exclude_user_id=...` — the on-blur inline-validation endpoint AC #1 requires. Returns `{"available": bool}`. `exclude_user_id` (optional) lets the edit form check "is this mobile available, ignoring the record I'm currently editing."
  - [x] `PATCH /users/{user_id}` — body `{name, mobile, team_id}` (no `role`; role is immutable after creation in this story — see Dev Notes). Catches `MobileTaken` → 409, `CannotEditAdministrator` → 400 `{code: "administrator_not_editable", message: "Administrator accounts are managed through login, not the Directory form"}`.
  - [x] `DELETE /users/{user_id}` → 204. Catches `LastAdministratorError` → 409 (reuse its existing message, same shape `domain/administrators.py` already defines).
  - [x] `POST /teams` — body `{name}`. Catches `TeamNameTaken` → 409.
  - [x] `GET /teams` — all statuses included, same "never silently hide" rule as `GET /users`.
  - [x] `PATCH /teams/{team_id}` — body `{name}`. Catches `TeamNameTaken` → 409.
  - [x] `DELETE /teams/{team_id}` → 204.
  - [x] Register both routers in `api/main.py`: `app.include_router(recipients_users_router)`, `app.include_router(recipients_teams_router)` (or import both from `api/recipients/routes.py` under aliases — match `api/main.py`'s existing single-import-per-router style).

- [x] Task 6: Dev-loop and deployment wiring (AC: #1, #2) — **easy to miss, breaks the feature in dev/staging silently if skipped**
  - [x] `web/vite.config.ts` — the `server.proxy` map is an explicit allowlist (`/auth`, `/dashboard/summary`, `/dashboard/brand-performance`), not a wildcard. Add `'/users': 'http://localhost:8000'` and `'/teams': 'http://localhost:8000'` or the new requests 404 against the Vite dev server instead of reaching the API.
  - [x] `docker/nginx/nginx.conf` — same reasoning for staging/production, explicit `location` blocks only. Add, mirroring the existing `/dashboard/` block exactly:
    ```nginx
    location /users/ {
        proxy_pass http://api:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /teams/ {
        proxy_pass http://api:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
    ```

- [x] Task 7: Frontend — `RecipientsPage` (AC: #1, #2, #3, #4, #5)
  - [x] `web/src/pages/RecipientsPage.tsx` — reuses the exact session-check-and-redirect `useEffect` pattern already established in `DashboardPage.tsx` (`GET /auth/me`, redirect to `/` on failure). **Duplicate it, do not extract a shared layout/hook** — `DashboardPage.tsx`'s own comment says the nav shell is "still provisional placements... a nav shell no story owns yet"; building one now is unrequested scope creep this story shouldn't take on.
  - [x] Two sections/tabs (MUI `Tabs`): "Users" and "Sales Teams" — leaves room for Story 3.2 to add "Groups"/"Channels" tabs later without restructuring this page (EXPERIENCE.md's IA groups all four under one "Recipients" nav entry). No mockup exists for this screen (`mockups/` only has `dashboard.html`, `notification-history.html`, `notifications-compose.html`) — build directly from EXPERIENCE.md's Directory form / data-table / Confirmation dialog component descriptions (cited in Dev Notes), there is nothing else to cross-check pixel layout against.
  - [x] Users tab: `ResponsiveDataTable` (existing component, `web/src/components/ResponsiveDataTable.tsx`) with columns Name, Mobile, Role, Team, Status (`StatusBadge`, existing component), row actions (Edit — hidden for `role === 'administrator'` per the Role-Handling Matrix; Remove — always shown, opens `ConfirmationDialog` naming the real consequence, e.g. *"This removes {name} from the directory. Future notifications will no longer reach them."*). Zero-Users state uses `EmptyState` (existing component) — *"No Users yet. Add your first Sales User or Manager to start building the notification directory."* + primary action opening the create form.
  - [x] Teams tab: same `ResponsiveDataTable`/`ConfirmationDialog`/`EmptyState` pattern, columns Name, Status.
  - [x] `web/src/pages/UserFormDialog.tsx` — MUI `Dialog` form (create + edit modes, one component). Fields: Name, Mobile (`onBlur` fires `GET /users/mobile-availability?mobile=...` — debounce not required at this scale, a plain on-blur fetch is sufficient; show inline `TextField` error state, not a separate alert, per EXPERIENCE.md's "Directory form validates phone-number uniqueness inline (not just on submit)"), Role (`Select`, options restricted to Sales User / Manager only — Administrator is never an option, per AC #5), Team (`Select`, populated from `GET /teams`, active teams only in the picker). Edit mode omits the Role field entirely (role is immutable post-creation).
  - [x] `web/src/pages/TeamFormDialog.tsx` — same shape, one field: Name.
  - [x] `web/src/router.tsx` — add `{ path: '/recipients', element: <RecipientsPage /> }`.
  - [x] `web/src/pages/DashboardPage.tsx` — add a `Link`/`Button` to `/recipients` next to the existing Logout button in the header `Stack` (the only nav entry point that exists pre-nav-shell; do not build a sidebar/drawer — UX-DR11/UX-DR24's full sidebar IA is out of this story's scope, same "no story owns the nav shell yet" reasoning as Task 7's first bullet).

- [x] Task 8: Tests (AC: all)
  - [x] `tests/domain/test_recipients_service.py` (new) — hand-written `FakeUserRepository`/`FakeTeamRepository`/`FakeAuditLogRepository` (no mocking library, established convention). Cover: create user success + audit entry written; create user with `role=administrator` raises `RoleNotAllowed`; create user with a taken mobile raises `MobileTaken`; update user success; update on an Administrator target raises `CannotEditAdministrator`; remove a Sales User succeeds (guard no-ops); remove the sole active Administrator raises `LastAdministratorError` (construct `LastAdministratorGuard` with a fake `UserRepository.count_active_administrators` returning `1`); remove a non-sole Administrator succeeds. Same coverage shape mirrored for `TeamDirectoryService` (create/update/remove, `TeamNameTaken`).
  - [x] `tests/adapters/persistence/test_user_repository.py` — extend with `get_by_mobile` (found/not-found), `list_all` (mixed roles/statuses all returned), `update_directory_fields`, `deactivate` (status flips, version increments).
  - [x] `tests/adapters/persistence/test_team_repository.py` — extend with `add`, `get_by_id`, `get_by_name`, `list_all_full`, `update_name`, `deactivate`. Confirm `get_or_create_by_name`'s existing tests still pass unmodified (regression check on the untouched method).
  - [x] `tests/api/test_recipients_routes.py` (new) — full route coverage via the `client`/`seed_user` fixtures (`tests/conftest.py`): 201/200/204 happy paths, 409 `mobile_taken`/`team_name_taken`, 422 on `role: "administrator"`, 409 `last_administrator` on removing the sole seeded Administrator, 400 `administrator_not_editable` on `PATCH /users/{admin_id}`, 401 on every route when unauthenticated (AD-8).
  - [x] `tests/conftest.py` — **no change needed.** `_clean_tables` already `DELETE FROM users` (line 27) before `DELETE FROM teams` (line 36) — correct FK-dependency order for the new `users.team_id → teams.id` foreign key this story adds. Verify this order still holds after Task 1's migration; do not reorder it.
  - [x] Frontend: `RecipientsPage.test.tsx`, `UserFormDialog.test.tsx`, `TeamFormDialog.test.tsx` — mirror `BootstrapForm.test.tsx`'s `vi.stubGlobal('fetch', ...)` + `Response` mocking convention (no MSW, no other mocking library in this repo). Cover: table renders rows from a mocked `GET /users`/`GET /teams`; create flow posts and refreshes the table; mobile-availability on-blur check disables submit + shows inline error on `{available: false}`; remove flow shows `ConfirmationDialog` with the real consequence text and calls `DELETE` on confirm; 409 `last_administrator` on removing an Administrator row surfaces as an inline error, not a silent failure.
  - [x] `uv run pytest -q`, `uv run ruff check .`, `uv run mypy .`, `uv run lint-imports` after backend changes (same gate every prior story ran clean against — see `2-4-...md`'s Debug Log References for the exact commands).

### Review Findings

- [x] [Review][Patch] Users can be assigned/kept on an inactive (soft-deleted) Sales Team with no server-side check — Only `UserFormDialog`'s picklist filters to active teams; `create_user`/`update_user` (`domain/recipients.py:58-100,102-133`) never check `team.status`. Decision: reject server-side. Fix: load the target Team in both methods and raise a 422/409 if `team.status != TeamStatus.ACTIVE`.
- [x] [Review][Patch] Mobile numbers and Team names are never recyclable once used, even after the owning User/Team is soft-deleted — `get_by_mobile`/`get_by_name` (`adapters/persistence/users.py:150-154`, `adapters/persistence/teams.py:72-76`) aren't status-filtered. Decision: filter by active status so a soft-deleted record's number/name becomes reusable. Fix: add a `status = 'active'` filter to both queries (or an explicit `get_active_by_mobile`/`get_active_by_name`).
- [x] [Review][Patch] Nginx has no exact-match blocks for the bare `/users`/`/teams` paths, so `POST/GET /users` and `POST/GET /teams` fall through to the SPA catch-all behind Nginx in staging/production — since the frontend only checks `response.ok`, Create silently appears to succeed (HTTP 200 HTML) while nothing is persisted. Invisible to every test in this diff (tests hit the ASGI app directly; Vite's dev proxy matches bare prefixes fine). Fix: add `location = /users { ... }` / `location = /teams { ... }` exact-match blocks mirroring the file's own `/health` pattern. [docker/nginx/nginx.conf:63-73]
- [x] [Review][Patch] No domain-layer check that `team_id` refers to an existing Team on create/update — an invalid `team_id` isn't caught until the DB FK fires, raising an unhandled `IntegrityError` → uncaught 500 (no `IntegrityError` handler anywhere in `api/main.py` or `api/recipients/routes.py`). Fix: `if await self._teams.get_by_id(team_id) is None: raise TeamNotFound()`, mapped to 404. [domain/recipients.py:58-100,102-133]
- [x] [Review][Patch] Mobile-uniqueness and Team-name-uniqueness checks are check-then-act; the pre-check itself is spec-sanctioned (NFR-8: no advisory lock needed at this scale), but neither route catches the resulting `IntegrityError` when two concurrent requests race past it, so the loser gets a raw 500 instead of the intended 409. Fix: wrap `session.commit()` in `try/except IntegrityError` in the four affected routes, mapping to the existing `_mobile_taken()`/`_team_name_taken()` responses. [api/recipients/routes.py:179-196,224-258,285-302,314-337]
- [x] [Review][Patch] `LastAdministratorGuard.ensure_can_deactivate`'s count-then-act check has the same race: two concurrent `DELETE /users/{id}` requests targeting two different Administrators, with exactly 2 active, can both read count=2 and both pass, leaving zero active Administrators. This was already flagged in Story 1.3's code review as "revisit when Story 3.1 wires up the deactivate/delete endpoint" — that endpoint now exists, so this is due. Fix: make the count-and-deactivate atomic (conditional `UPDATE ... WHERE` or `SELECT ... FOR UPDATE`). [domain/administrators.py:26-32, called from domain/recipients.py:144]
- [x] [Review][Patch] No index on `users.team_id` — Postgres doesn't auto-index FK columns, and this backs the team lookup on every `GET /users`. Fix: add an index in the migration. [alembic/versions/dba27c6b09b6_recipient_directory_users_and_teams.py]
- [x] [Review][Patch] Team names aren't trimmed before the uniqueness check/insert in `TeamDirectoryService.create_team`/`update_team` (only the untouched `get_or_create_by_name` ingestion path strips) — "North" and "North " pass as distinct names. Fix: `.strip()` the name in both methods. [domain/recipients.py:165-167,184-191]
- [x] [Review][Patch] `RecipientsPage`'s `loadUsers`/`loadTeams` effect has no unmount-cancellation guard, unlike the session-check effect two lines above it in the same file. Fix: add the same `cancelled` flag pattern. [web/src/pages/RecipientsPage.tsx:129-134]
- [x] [Review][Patch] Mobile-availability check race: `handleMobileBlur` isn't awaited by `handleSubmit`, and Save's `disabled` doesn't factor in `checkingMobile`, so Save is clickable mid-check (server-side 409 is the real backstop, but the inline UX can show a false "not blocked" state momentarily). Fix: disable Save while `checkingMobile` is true. [web/src/pages/UserFormDialog.tsx:66-86,179]
- [x] [Review][Patch] `ConfirmationDialog`'s confirm button isn't disabled while the DELETE is in flight — a double-click can fire duplicate `DELETE` requests. Fix: pass a submitting/loading prop into `ConfirmationDialog` and disable confirm while true. [web/src/pages/RecipientsPage.tsx:209-243,358-384]
- [x] [Review][Patch] Editing a User whose currently-assigned Team was deactivated after assignment: the Team `Select` only lists active teams, so the stored `team_id` has no matching option and renders blank (confusing, though the underlying value is preserved unless the user interacts with the field). Fix: include the current team in the options even if inactive, labeled accordingly. [web/src/pages/RecipientsPage.tsx:144-146, web/src/pages/UserFormDialog.tsx:162-174]
- [x] [Review][Patch] "Add User" with zero active Teams: the Team `Select` renders with no options and required-field validation silently blocks submission with no guidance. Fix: disable "Add User" (or show inline guidance) when there are no active teams. [web/src/pages/RecipientsPage.tsx:144-146, web/src/pages/UserFormDialog.tsx:162-174]
- [x] [Review][Patch] Cancel button in `UserFormDialog`/`TeamFormDialog` isn't disabled while submitting — clicking it hides the dialog without cancelling the in-flight request; a late response on the same (still-mounted) instance can flicker error state or fire a stray `onSaved()` after the dialog is reopened for a different record. Fix: `disabled={submitting}` on Cancel. [web/src/pages/UserFormDialog.tsx:178]
- [x] [Review][Patch] `actionError` is one shared Alert state for both Users and Teams tabs and isn't cleared on tab switch — an error from acting on one tab can linger and appear to apply to the other. Fix: clear `actionError` in the tab `onChange` handler. [web/src/pages/RecipientsPage.tsx:71,256-260,262-265]
- [x] [Review][Patch] `domain/recipients.py` raises bare `LookupError` for "not found," breaking the codebase's established convention of a named exception per domain module (`InvalidCredentials`, `BootstrapAlreadyComplete`, etc.). Cosmetic/consistency only — routes already map it correctly. Fix: add `UserNotFound`/`TeamNotFound`. [domain/recipients.py:112,138,187,210]
- [x] [Review][Defer] Optimistic-concurrency `version` column has no stale-write rejection on any update path [domain/models.py, adapters/persistence/users.py:161-169, adapters/persistence/teams.py:83-89] — deferred, explicitly out of scope per this story's own Dev Notes and Completion Notes: Story 3.4 (Concurrent-Edit Conflict Detection) owns stale-write rejection; `version` is kept incrementing correctly so that story has real data to work against.
- [x] [Review][Defer] Alembic `downgrade()` requires manually deleting Sales User/Manager rows before it can succeed [alembic/versions/dba27c6b09b6_recipient_directory_users_and_teams.py] — deferred, explicitly documented as an intentional, accepted consequence in the migration's own downgrade docstring per this story's Task 1 instructions.
- [x] [Review][Defer] No pagination on `GET /users`/`GET /teams` [api/recipients/routes.py:199-208,305-311] — deferred, consistent with this story's explicit "never hide rows" requirement; a real future scaling concern but not this story's scope.
- [x] [Review][Defer] No test for a non-sole Administrator deactivating their own account [tests/api/test_recipients_routes.py] — deferred, coverage gap only; the guard behavior itself is correct and tested for the sole-admin case.
- [x] [Review][Defer] No client-side (or server-side) format validation on the `mobile` field [api/recipients/routes.py:36-46] — deferred, needs a design decision (E.164? country-specific?) rather than guessing a format now.

## Dev Notes

**Role-Handling Matrix — read this before writing `domain/recipients.py` or the frontend forms.** This is the one genuinely non-obvious design resolution in this story; epics.md's AC list doesn't spell it out, but `domain/administrators.py`'s docstring ("Epic 3's Story 3.1 builds the deactivate/delete endpoint that will invoke `ensure_can_deactivate`") only makes sense if Administrators are reachable through this same directory, while AC #1's field list (Name/Mobile/Role/Team, no Username/Password) only makes sense if Administrators are *not* creatable through it:

| Operation | Administrator | Sales User / Manager |
| --- | --- | --- |
| Create (`POST /users`) | **Not allowed** — 422, `Literal` type rejects `role: "administrator"` at the schema level | Allowed — Name+Mobile+Team required |
| List (`GET /users`) | **Included** (so the last-admin guard has something to protect) | Included |
| Edit (`PATCH /users/{id}`) | **Not allowed** — 400 `administrator_not_editable` (no Name/Mobile/Team semantics) | Editable |
| Role reassignment | Not supported by this story at all — Role is immutable after creation for every row | Not supported by this story at all |
| Remove (`DELETE /users/{id}`) | Allowed, gated by `LastAdministratorGuard` | Allowed, guard is a no-op (existing `if target.role != Role.ADMINISTRATOR: return`) |

- **This is the schema-level tension the migration resolves.** `users` was built in Epic 1 exclusively for Administrator login (`username`/`hashed_password` both `NOT NULL`). Sales User/Manager rows this story creates have neither. Task 1 relaxes both columns to nullable rather than splitting into two tables — a single `User`/`users` table serving both "portal-authenticated Administrator" and "WhatsApp-only roster entry" is the existing shape (`Role` already exists on `User` precisely so downstream WhatsApp content can route/format per role, per Addendum A5), this story extends it rather than replacing it.
- **`TeamRepository.list_all()` must not change.** It's Story 2.2's load-bearing dependency for the Dashboard's team-performance section (`domain/metrics.py#DashboardMetricsService.get_summary`). This story adds `list_all_full()` as a new, separate method for the Recipients Teams grid — touching the existing method's signature or filtering behavior is an avoidable regression against already-shipped, already-tested code.
- **Version-conflict rejection is explicitly out of scope.** `User` already has a `version` column (Epic 1); this story adds one to `Team`. Both get bumped on every update/deactivate, but neither `UPDATE` carries a `WHERE version = :expected` precondition here — Story 3.4 (Concurrent-Edit Conflict Detection) is the story epics.md assigns that check and its conflict-dialog UX to. Writing the check now would be building ahead of a story that owns its own AC list and UX pattern (the conflict dialog showing both versions).
- **Opt-in consent is untouched.** No `OptInConsent` entity/column exists yet — Story 3.3 introduces it, including "changing mobile revokes consent." Don't stub anything consent-related in `update_user`.
- **No mockup exists for this screen.** Unlike Stories 2.2/2.3 (`mockups/dashboard.html`) or the Compose/History stories, `mockups/` has nothing for Recipients — build from EXPERIENCE.md's component descriptions (Directory form, Data table, Confirmation dialog — all cited below) and the already-built shared components (`ResponsiveDataTable`, `ConfirmationDialog`, `EmptyState`, `StatusBadge`), not from a pixel reference.
- **No nav shell exists yet.** `DashboardPage.tsx`'s own comment flags this. Add a plain link to `/recipients`, don't build a sidebar/drawer (UX-DR11/UX-DR24 in full) — that's unrequested scope for this story.

### Project Structure Notes

- New backend files: `domain/recipients.py`, `api/recipients/__init__.py`, `api/recipients/routes.py`, `alembic/versions/<new>_recipient_directory_users_teams.py`, `tests/domain/test_recipients_service.py`, `tests/api/test_recipients_routes.py`.
- Modified backend files: `domain/models.py` (`User` fields, new `TeamStatus`, `Team` fields), `ports/users.py`, `ports/teams.py`, `adapters/persistence/users.py`, `adapters/persistence/teams.py`, `api/main.py` (router registration), `tests/adapters/persistence/test_user_repository.py`, `tests/adapters/persistence/test_team_repository.py`.
- New frontend files: `web/src/pages/RecipientsPage.tsx` (+ `.test.tsx`), `web/src/pages/UserFormDialog.tsx` (+ `.test.tsx`), `web/src/pages/TeamFormDialog.tsx` (+ `.test.tsx`).
- Modified frontend/deploy files: `web/src/router.tsx`, `web/src/pages/DashboardPage.tsx` (nav link only), `web/vite.config.ts`, `docker/nginx/nginx.conf`.
- No changes to `config.py`, `scheduler/`, `adapters/whatsapp_twilio/`, `adapters/source_system/`, or `domain/ingestion.py` — this story is entirely within CAP-5's boundary per the Capability map.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 3.1: Manage Users & Sales Teams] (all 4 literal ACs)
- [Source: _bmad-output/planning-artifacts/epics.md#Story 3.4: Concurrent-Edit Conflict Detection] (confirms version-conflict rejection + the conflict dialog UX are explicitly that story's scope, not this one's)
- [Source: _bmad-output/planning-artifacts/epics.md#Story 3.3: Recipient Opt-In Consent Capture] ("a User's phone number is changed... existing consent is revoked automatically" — confirms this story must NOT implement that; no consent entity exists yet)
- [Source: _bmad-output/planning-artifacts/prds/prd-GrowthTrack-2026-07-14/prd.md#FR-9] ("Administrator can add, edit, or remove individual Users... Sales Teams; ... all directory changes are audit-logged")
- [Source: _bmad-output/planning-artifacts/prds/prd-GrowthTrack-2026-07-14/addendum.md#A5 RBAC Reconciliation Rationale] ("the user resolved this by choosing WhatsApp-only delivery for Sales User and Manager roles — they never authenticate to the portal in Phase 1... the `Role` field on `User` exists and is used to route/format WhatsApp content appropriately per role" — basis for AC #5 and the nullable-credentials migration)
- [Source: ARCHITECTURE-SPINE.md#AD-4] (`RecipientList`/`Team` ownership rules; `User`/`Team`/`RecipientList` soft-deleted via `Status`/active flag, never hard-deleted)
- [Source: ARCHITECTURE-SPINE.md#AD-7] (co-transactional audit write — every mutating service method writes data + `AuditLogEntry` in one transaction; login precedent already established by `domain/auth.py`)
- [Source: ARCHITECTURE-SPINE.md#AD-8] (one shared auth choke-point; every route depends on `get_current_user`)
- [Source: ARCHITECTURE-SPINE.md#AD-11] (`User` already carries `version`/optimistic-concurrency per Epic 1; this story extends the same convention to `Team`)
- [Source: ARCHITECTURE-SPINE.md#Consistency Conventions] (REST plural-noun resources; `{error:{code,message,details}}` envelope already implemented in `api/main.py`; `User`/`Team`/`RecipientList` carry a version column, stale write rejected — Story 3.4's job, not this one's, per above)
- [Source: ARCHITECTURE-SPINE.md#Capability → Architecture Map] (CAP-5 fixes `api/recipients`, `domain/recipients` as this story's file locations, governed by AD-4/AD-7/AD-9)
- [Source: domain/administrators.py] ("Deliberately no caller yet — Epic 3's Story 3.1 builds the deactivate/delete endpoint that will invoke `ensure_can_deactivate`" — the explicit basis for AC #6 and the Role-Handling Matrix's "Administrators are listed/removable, not creatable/editable" resolution)
- [Source: adapters/persistence/teams.py] ("`Team` is intentionally minimal here — full CRUD (soft-delete status, optimistic-concurrency version column, management UI) is Epic 3 Story 3.1's job" — the explicit basis for Task 1's `teams` migration and Task 3's new `TeamRepository` methods)
- [Source: _bmad-output/specs/spec-growthtrack/entities.md#User] (field list: `UserID`, `Name`, `Mobile`, `Role`, `Status` — no `Username`/`Password`, consistent with AC #5's role restriction; those two fields are Epic 1's own portal-login addition, not in the original spec)
- [Source: domain/models.py#User, #Team] (existing dataclasses this story extends, not replaces)
- [Source: domain/auth.py, domain/bootstrap.py] (the co-transactional-audit-write-inside-a-domain-service, route-commits pattern this story's `domain/recipients.py` follows exactly)
- [Source: api/auth/routes.py] (the one-router-per-concern-file, `Depends(get_current_user)`, typed exception → HTTPException-with-envelope pattern this story's `api/recipients/routes.py` mirrors)
- [Source: api/auth/dependencies.py#get_current_user] (the shared AD-8 dependency every new route uses)
- [Source: domain/metrics.py#DashboardMetricsService.get_summary] (existing consumer of `TeamRepository.list_all()` — the exact reason that method's signature/behavior must not change; also the `team_names` dict-building pattern this story's `GET /users` route reuses for `team_name` resolution)
- [Source: web/src/components/ResponsiveDataTable.tsx, ConfirmationDialog.tsx, EmptyState.tsx, StatusBadge.tsx] (existing shared components this story composes, does not rebuild — `ResponsiveDataTable`'s own comment explicitly names "Recipients" as one of its three intended consumers, alongside Notification History and Audit Log)
- [Source: web/src/pages/DashboardPage.tsx] (the inline session-check `useEffect` pattern this story's `RecipientsPage` duplicates; its own comment flags the nav shell as "provisional... no story owns yet")
- [Source: web/src/pages/BootstrapForm.tsx, BootstrapForm.test.tsx] (the form-component shape and `vi.stubGlobal('fetch', ...)` test convention this story's `UserFormDialog`/`TeamFormDialog` and their tests follow)
- [Source: web/src/api/authClient.ts#apiFetch] (existing fetch wrapper — relative paths only, `credentials: 'include'` — reused as-is for every new request this story adds)
- [Source: web/vite.config.ts, docker/nginx/nginx.conf] (explicit per-path proxy/location allowlists — both need new entries for `/users`, `/teams`, per Task 6)
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-GrowthTrack-2026-07-14/EXPERIENCE.md#Information Architecture] ("Recipients | Nav | Manage Users, Recipient Groups, Recipient Channels, Sales Teams; opt-in/out state; directory CRUD (FR-9, FR-10)")
- [Source: EXPERIENCE.md#Shared component vocabulary] ("Directory form — Recipient add/edit validates phone-number uniqueness inline (not just on submit) and surfaces opt-in/consent state..."; "Data table — shared pattern across Notification History, Recipients, and Audit Log"; "Confirmation dialog — ...names the real consequence, requires explicit confirm, uses `button-danger` for the confirming action only")
- [Source: EXPERIENCE.md#State Patterns] ("Empty — zero Sales Teams, zero recipients... each gets its own direct copy + primary action, never a shared generic 'no data' placeholder")
- [Source: _bmad-output/implementation-artifacts/2-3-brand-performance-analytics.md#Review Findings] (`_to_domain`-as-module-level-free-function precedent, reused here for `adapters/persistence/teams.py`)
- [Source: _bmad-output/implementation-artifacts/1-3-role-scoped-portal-access-last-admin-guard.md] (built `LastAdministratorGuard` with no caller, explicitly deferring the caller to this story)
- [Source: alembic/versions/8ae7e5d0d8c9_login_lockout_and_password_reset.py] (the `server_default` pattern this story's `teams` migration follows for adding `NOT NULL` columns to a non-empty table)

### Git Intelligence

- `HEAD` is `9ea7cf0` ("Story 2.4: prioritized doctor visit list"), working tree clean. Migration chain currently ends at `e054c35b938f` (Story 2.1's ingestion tables) — this story's new migration must set `down_revision = "e054c35b938f"`.
- Commit style across this repo: one commit per logical unit of work, imperative summary line (e.g. "Story 2.4: prioritized doctor visit list", "Story 1.3 + 1.4: role-scoped access, last-admin guard, session revocation"), ending with the `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>` trailer.
- Every prior story's Debug Log ran `uv run pytest -q`, `uv run ruff check .`, `uv run mypy .`, `uv run lint-imports` clean before being marked `done` — run the same four before considering this story complete. `lint-imports` matters more than usual here: `domain/recipients.py` is new and must only import from `ports/`, never `adapters/`/`api/` (AD-1).

## Dev Agent Record

### Agent Model Used

Claude Sonnet 5 (claude-sonnet-5)

### Debug Log References

- `uv run alembic upgrade head` / `downgrade base` / `upgrade head` — full migration chain round-trip, clean (matches the CI gate exactly).
- `uv run pytest tests/domain/test_recipients_service.py tests/adapters/persistence/test_user_repository.py tests/adapters/persistence/test_team_repository.py tests/api/test_recipients_routes.py -q` — 82 passed (this story's new/extended backend tests, run in isolation).
- `uv run pytest -q` (full suite, real Postgres test container) — 244 passed on the clean run (196 baseline + 48 new). One later full run showed 2 intermittent failures (`test_me_with_tampered_token_returns_401`, `test_tampered_token_is_rejected`); isolated and repeated 5x standalone, confirmed pre-existing flakiness (~20% failure rate) caused by the test tampering a JWT signature byte derived from a random UUID — the tamper sometimes produces the same decoded byte and fails to actually invalidate the signature. Unrelated to this story's changes (touches neither file); not fixed here as out of scope.
- `uv run ruff check .` — all checks passed, no findings (after wrapping a few lines this story's tests introduced past the 100-char limit).
- `uv run mypy .` (`api domain ports adapters scheduler config.py alembic/env.py`) — no issues in 57 source files. One pre-existing-pattern fix required: `api/auth/routes.py#UserResponse.username` widened from `str` to `str | None` to match `User.username` becoming optional — a direct, anticipated consequence of Task 2, not a rewrite of Epic 1's auth path.
- `uv run lint-imports` — 2 contracts kept, 0 broken (AD-1: `domain` depends only on `ports`; `ports` stays framework/adapter-free) — confirms `domain/recipients.py` is clean.
- `npm run typecheck`, `npm run lint`, `npm run test -- --run` (96 passed), `npm run build` — all clean except 2 pre-existing `react-hooks/set-state-in-effect` lint violations in `DashboardPage.tsx` (an untouched effect) and `LoginPage.tsx` (a file this story never modifies) — confirmed pre-existing by diffing against `git stash`; caused by an `eslint-plugin-react-hooks` version pickup unrelated to this story. This story's 3 new files use the same one-line `eslint-disable-next-line` convention `LoginPage.tsx` already established elsewhere in the repo for the identical rule.
- One frontend test (`DashboardPage.test.tsx`'s skeleton-count assertion) failed once when run as part of the full suite but passed in isolation and on suite re-run — confirmed test-order-dependent flakiness unrelated to this story's isolated diff to that file (header nav-link addition only).

### Completion Notes List

- Implemented all 8 tasks. Resolved the story's flagged schema tension (Epic 1's `users` table built exclusively for Administrator login vs. this story's need for passwordless Sales User/Manager roster rows) by relaxing `username`/`hashed_password` to nullable and adding `name`/`mobile`/`team_id`, all DB-nullable with domain-layer-enforced required-ness (Task 1/2).
- `TeamRepository.list_all()` (Story 2.2's Dashboard dependency) left completely untouched; `list_all_full()` added as a separate method for the Recipients Teams grid, per the story's explicit instruction.
- `LastAdministratorGuard.ensure_can_deactivate` now has its first caller (`UserDirectoryService.remove_user`) — closes the loop `domain/administrators.py`'s docstring left open since Story 1.3.
- Role-Handling Matrix implemented exactly as specified: Administrators are listed and removable through `/users` (guard-protected) but never creatable (`Literal["sales_user","manager"]` on the request body) or editable (`CannotEditAdministrator` → 400) through it.
- Version-conflict rejection and opt-in-consent-on-mobile-change were deliberately NOT implemented — both are explicitly Story 3.4's and Story 3.3's scope respectively, per the story's Dev Notes; `version` still increments correctly on every `User`/`Team` mutation so those later stories have real data to work against.
- All 6 acceptance criteria (4 literal from epics.md + 2 derived and clearly flagged as such) are satisfied and covered by tests at the domain, repository, and API layers, plus frontend component tests for the Directory form's inline mobile-uniqueness validation and the Confirmation-dialog removal flow.
- Two pre-existing, unrelated issues were discovered and worked around without being "fixed" (out of this story's scope): a flaky JWT-tampering test pair (backend) and a `react-hooks/set-state-in-effect` lint-rule regression from a dependency version bump affecting two files this story doesn't own (`DashboardPage.tsx`'s pre-existing third effect, `LoginPage.tsx`).

### File List

**New:**
- `alembic/versions/dba27c6b09b6_recipient_directory_users_and_teams.py`
- `domain/recipients.py`
- `api/recipients/__init__.py`
- `api/recipients/routes.py`
- `tests/domain/test_recipients_service.py`
- `tests/api/test_recipients_routes.py`
- `web/src/pages/RecipientsPage.tsx`
- `web/src/pages/RecipientsPage.test.tsx`
- `web/src/pages/UserFormDialog.tsx`
- `web/src/pages/UserFormDialog.test.tsx`
- `web/src/pages/TeamFormDialog.tsx`
- `web/src/pages/TeamFormDialog.test.tsx`
- `alembic/versions/17eb25555c26_recipients_directory_active_only_.py` (code review: partial unique indexes for active-only mobile/name recycling, `users.team_id` index)

**Modified:**
- `domain/models.py`
- `ports/users.py` (code review: `acquire_administrator_removal_lock` abstract method)
- `ports/teams.py`
- `adapters/persistence/users.py` (code review: active-only `get_by_mobile`, `acquire_administrator_removal_lock`)
- `adapters/persistence/teams.py` (code review: active-only `get_by_name`, `get_or_create_by_name`'s conflict target and final lookup repointed at the partial index)
- `adapters/persistence/advisory_locks.py` (code review: `ADMINISTRATOR_REMOVAL_LOCK_KEY`)
- `domain/administrators.py` (code review: `ensure_can_deactivate` acquires the removal lock before counting)
- `domain/recipients.py` (code review: `UserNotFound`/`TeamNotFound`/`TeamInactive` exceptions replacing bare `LookupError`; `UserDirectoryService` takes a `teams` repository and validates `team_id` exists/is active; `TeamDirectoryService` trims names)
- `api/recipients/routes.py` (code review: catches the new exceptions, wraps commits in `try/except IntegrityError` for the mobile/team-name races)
- `api/main.py`
- `api/auth/routes.py` (`UserResponse.username` widened to `str | None`)
- `tests/adapters/persistence/test_user_repository.py`
- `tests/adapters/persistence/test_team_repository.py`
- `tests/domain/test_ingestion_service.py` (`FakeTeamRepository` stub methods for the port's new abstract methods)
- `tests/domain/test_dashboard_metrics_service.py` (`FakeTeamRepository` stub methods, same reason)
- `tests/domain/test_recipients_service.py` (code review: `_user_service`/fakes updated for the `teams` dependency and new lock stub; new team-existence/active/not-found/trim coverage)
- `tests/domain/test_last_administrator_guard.py` (code review: lock-acquisition assertions)
- `tests/api/test_recipients_routes.py` (code review: team-not-found/inactive, mobile/name recycling coverage)
- `web/src/router.tsx`
- `web/src/pages/DashboardPage.tsx` (nav link only)
- `web/src/pages/RecipientsPage.tsx` (code review: unmount-safe loads, `actionError` cleared per tab, submitting-aware removal dialogs, inactive-team-aware edit options, zero-active-team guard)
- `web/src/pages/UserFormDialog.tsx` (code review: Save disabled while checking mobile, Cancel disabled while submitting)
- `web/src/pages/TeamFormDialog.tsx` (code review: Cancel disabled while submitting)
- `web/src/components/ConfirmationDialog.tsx` (code review: `submitting` prop disables both actions)
- `web/src/components/ConfirmationDialog.test.tsx` (code review: submitting-state coverage)
- `web/vite.config.ts`
- `docker/nginx/nginx.conf` (code review: exact-match `/users`/`/teams` blocks)

## Change Log

- 2026-07-20: Implemented Story 3.1 end-to-end — migration relaxing `users.username`/`hashed_password` to nullable and adding `name`/`mobile`/`team_id`, plus `teams.status`/`version` (Task 1); `TeamStatus` enum and extended `User`/`Team` dataclasses (Task 2); `UserRepository`/`TeamRepository` new methods, `TeamRepository.list_all()` left untouched (Task 3); `domain/recipients.py` with `UserDirectoryService`/`TeamDirectoryService`, wiring `LastAdministratorGuard`'s first caller (Task 4); `api/recipients` REST routes for `/users` and `/teams`, registered in `api/main.py` (Task 5); Vite dev proxy and Nginx location blocks for both new paths (Task 6); `RecipientsPage`/`UserFormDialog`/`TeamFormDialog` frontend with inline mobile-availability validation and Confirmation-dialog removal flow, plus a Dashboard nav link (Task 7); full backend and frontend test coverage across all 6 ACs (Task 8). Full backend suite (244 tests), ruff, mypy, import-linter, and the full migration round-trip all pass clean; full frontend suite (96 tests), typecheck, lint, and build all pass clean except 2 pre-existing lint violations in files this story doesn't own. Two pre-existing test-flakiness issues (a JWT-tampering test pair; a DashboardPage skeleton-count assertion) were investigated and confirmed unrelated to this story's changes, not fixed as out of scope.
- 2026-07-20: Code review round — applied all 16 patch findings (2 promoted from decision-needed: server-side rejection of inactive-Team assignment, active-only mobile/name uniqueness enabling reuse after soft-delete). Notably: added exact-match Nginx `location` blocks for `/users`/`/teams` (the bare-path routes were silently falling through to the SPA behind Nginx, a false-success production bug caught independently by two review layers); closed the `LastAdministratorGuard` TOCTOU race flagged back in Story 1.3's review via a new `pg_advisory_xact_lock` (mirroring the bootstrap-lock pattern); added a new migration (`17eb25555c26`) swapping the plain unique constraints on `users.mobile`/`teams.name` for partial unique indexes scoped to active rows, which in turn required repointing `get_or_create_by_name`'s `ON CONFLICT` target and final lookup at the same partial index (caught by a new regression test — the original unfiltered lookup raised `MultipleResultsFound` once a name was reused post-soft-delete). Full backend suite (260 tests) and frontend suite (97 tests) pass clean; ruff, mypy, import-linter, and the extended migration round-trip (including the new revision) all clean. 3 decision-needed findings resolved as dismiss (Team-removal-with-active-Users check, non-idempotent update/delete on inactive targets), 6 deferred (version-conflict rejection — explicitly Story 3.4's scope; Alembic downgrade's documented manual-cleanup requirement; no pagination; missing non-sole-admin self-deactivation test; mobile format validation — needs a design decision).
