---
baseline_commit: a352f24
---

# Story 3.2: Manage Recipient Groups & Channels

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an Administrator,
I want to create, edit, and remove Recipient Groups and Recipient Channels as named sets of Users,
so that I can target a group with one selection instead of picking individuals every time.

## Acceptance Criteria

1. **Given** a set of existing Users, **when** I create a Recipient Group or Recipient Channel, **then** it is saved as a `RecipientList` with a `kind` field distinguishing them for display only — both share the same fan-out mechanism. [Source: epics.md#Story 3.2, ARCHITECTURE-SPINE.md#AD-4]
2. **Given** an existing `RecipientList`, **when** I edit its membership or remove it, **then** the change reaches future notifications, and is audit-logged co-transactionally. [Source: epics.md#Story 3.2, ARCHITECTURE-SPINE.md#AD-7]
3. **Given** a `RecipientList` is removed, **when** processed, **then** it is soft-deleted, never hard-deleted. [Source: epics.md#Story 3.2, ARCHITECTURE-SPINE.md#AD-4]
4. **[Derived — not stated verbatim in epics.md, required so two identically-named lists can't make the picker/audit trail ambiguous; mirrors the exact pattern Story 3.1 established for `Team.name`]** **Given** an active `RecipientList` name, **when** a second `RecipientList` (Group or Channel, same namespace — `kind` is display-only per AD-4, not a separate namespace) is created or renamed with that same name, **then** it is rejected as a conflict — scoped to active rows only, so a soft-deleted list's name becomes reusable (same `ix_*_active_uq` pattern Story 3.1's code review added for `users.mobile`/`teams.name`). [Source: domain 3.1 code-review precedent, ARCHITECTURE-SPINE.md#AD-4]
5. **[Derived — closes a gap AC #1 leaves open: "a set of existing Users" implies membership is validated, not merely stored]** **Given** a `RecipientList`'s membership is created or edited, **then** every referenced member must be an existing, active User — a nonexistent or soft-deleted User cannot be added, mirroring the `_ensure_team_active` check Story 3.1 added for `User.team_id`. Per Addendum A6, members are individual Users only; Teams and other `RecipientList`s are never nested inside one. [Source: domain/recipients.py#_ensure_team_active (3.1 precedent), addendum.md#A6]
6. **[Derived — an Administrator row always has `mobile: None` per Story 3.1's schema (Administrators authenticate to the portal, they don't receive WhatsApp sends); silently allowing one into a `RecipientList` would create a permanently-unreachable "member" with no error anywhere]** **Given** a User is selected for `RecipientList` membership, **when** that User has no `mobile` recorded, **then** adding them is rejected — a `RecipientList` exists to fan out WhatsApp sends to individual numbers (Addendum A6), so every member must be WhatsApp-addressable. In practice this excludes Administrator rows (the only rows with `mobile: None`) without needing to hard-code a Role check. [Source: domain/models.py#User.mobile (nullable only for Administrator rows per Story 3.1), addendum.md#A6]

## Tasks / Subtasks

- [x] Task 1: Alembic migration — `recipient_lists` + `recipient_list_members` (AC: #1, #3, #4, #5)
  - [x] Run `uv run alembic revision -m "recipient lists and membership"` with `down_revision = "17eb25555c26"` (the current head — confirm via `uv run alembic heads` first; do not hand-guess the revision id, let Alembic generate it).
  - [x] `recipient_lists` table — get the active-only partial unique index right from day one (Story 3.1 had to retrofit this in a follow-up migration after code review; this story doesn't repeat that mistake):
    ```python
    op.create_table(
        "recipient_lists",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_recipient_lists_name_active_uq",
        "recipient_lists",
        ["name"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    ```
    No column-level unique constraint on `name` at all (unlike `users.mobile`/`teams.name`'s original mistake) — go straight to the partial index.
  - [x] `recipient_list_members` — a pure join table (AD-4: "relational join rows, never a JSON blob"), composite primary key, no surrogate `id`/`created_at` (this table has no independent identity beyond the pair):
    ```python
    op.create_table(
        "recipient_list_members",
        sa.Column("recipient_list_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["recipient_list_id"], ["recipient_lists.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("recipient_list_id", "user_id"),
    )
    op.create_index("ix_recipient_list_members_user_id", "recipient_list_members", ["user_id"])
    ```
    No `ON DELETE CASCADE` — `User`/`RecipientList` are soft-deleted, never hard-deleted (AD-4), so the FK's default `NO ACTION` never actually fires; adding cascade behavior for a delete path that structurally cannot happen would be dead code.
  - [x] Downgrade: `op.drop_table("recipient_list_members")` (drops its own index with it) before `op.drop_index(...)` / `op.drop_table("recipient_lists")` — child before parent, same ordering discipline as `dba27c6b09b6`'s downgrade.

- [x] Task 2: `domain/models.py` — new `RecipientList` entity (AC: #1, #5)
  - [x] Add `from dataclasses import dataclass, field` (currently only `dataclass` is imported — `field` is needed for `member_user_ids`'s mutable default).
  - [x] New `RecipientListKind(StrEnum)`: `GROUP = "group"`, `CHANNEL = "channel"`.
  - [x] New `RecipientListStatus(StrEnum)`: `ACTIVE = "active"`, `INACTIVE = "inactive"` — a **separate** enum from `TeamStatus`/`UserStatus`, not a shared generic `Status` type. This is the exact fork-in-the-road Story 3.1's Dev Notes predicted: *"`RecipientList`, the only other entity slated for the same treatment, doesn't exist until Story 3.2"* — now it does, and gets its own small enum for the same lower-blast-radius reasoning already applied twice.
  - [x] New dataclass:
    ```python
    @dataclass
    class RecipientList:
        id: uuid.UUID
        name: str
        kind: RecipientListKind
        status: RecipientListStatus = RecipientListStatus.ACTIVE
        version: int = 1
        member_user_ids: list[uuid.UUID] = field(default_factory=list)
    ```

- [x] Task 3: `ports/recipient_lists.py` (new file) + `ports/users.py` addition (AC: #1, #2, #3, #5)
  - [x] `ports/recipient_lists.py`, same `Any`-typed convention as `ports/teams.py` (ports cannot import `domain`):
    ```python
    class RecipientListRepository(ABC):
        @abstractmethod
        async def get_by_id(self, recipient_list_id: uuid.UUID) -> Any: ...

        @abstractmethod
        async def get_by_name(self, name: str) -> Any: ...

        @abstractmethod
        async def add(self, recipient_list_id: uuid.UUID, name: str, kind: Any) -> None: ...

        @abstractmethod
        async def list_all_full(self) -> list[Any]:
            """Full RecipientList rows (id, name, kind, status, version,
            member_user_ids), all statuses, all kinds — the Recipients
            Groups/Channels tabs filter by kind client-side, same "never
            hide rows" convention as GET /users, /teams."""
            ...

        @abstractmethod
        async def update_details(self, recipient_list_id: uuid.UUID, name: str, kind: Any) -> None: ...

        @abstractmethod
        async def deactivate(self, recipient_list_id: uuid.UUID) -> None: ...

        @abstractmethod
        async def replace_members(self, recipient_list_id: uuid.UUID, user_ids: list[uuid.UUID]) -> None:
            """Full-replace semantics: delete every existing membership row
            for this list, then insert the given set — matches the form's
            save-the-whole-picker-selection UX; there is no incremental
            add-one/remove-one endpoint in this story."""
            ...

        @abstractmethod
        async def get_member_user_ids(self, recipient_list_id: uuid.UUID) -> list[uuid.UUID]: ...
    ```
  - [x] `ports/users.py` — add one bulk-lookup method (avoids an N+1 membership-validation loop, same discipline Story 3.1 required for `team_name` resolution):
    ```python
    @abstractmethod
    async def get_many_by_ids(self, user_ids: list[uuid.UUID]) -> list[Any]: ...
    ```

- [x] Task 4: `adapters/persistence/recipient_lists.py` (new file) + `adapters/persistence/users.py` addition (AC: #1, #2, #3, #5)
  - [x] `RecipientListModel` (`recipient_lists` table) + a module-level `recipient_list_members` Core `Table` (not a mapped class — it's a pure join table with no independent identity, so plain `sqlalchemy.Table`/`insert`/`delete`/`select` Core statements are the right tool, not the ORM).
  - [x] `_to_domain(row: RecipientListModel, member_user_ids: list[uuid.UUID]) -> RecipientList` — a free function (Story 2.3/3.1 precedent), takes member ids as a parameter rather than querying inside itself, so callers control batching.
  - [x] `get_by_id`/`get_by_name` each call `get_member_user_ids` for that one row (acceptable — single-row reads, not a list scan).
  - [x] `list_all_full()` — **one** bulk query for every list's memberships, grouped in Python into a `dict[uuid.UUID, list[uuid.UUID]]`, then zipped onto each row. Do not call `get_member_user_ids` once per row in a loop (the exact N+1 shape Story 3.1's `GET /users` route was written to avoid for `team_name`).
  - [x] `get_by_name`/uniqueness check: filter `status = RecipientListStatus.ACTIVE.value`, mirroring `adapters/persistence/teams.py#get_by_name`'s active-only filter exactly (code review of Story 3.1 already established this is the right default the *first* time — no need to ship the unfiltered version and fix it later).
  - [x] `replace_members`: `DELETE FROM recipient_list_members WHERE recipient_list_id = :id`, then a single bulk `INSERT` of the new rows (skip the insert entirely if the new set is empty — an empty `VALUES` list is invalid SQL).
  - [x] `adapters/persistence/users.py` — add `get_many_by_ids`: `select(UserModel).where(UserModel.id.in_(user_ids))` (return `[]` immediately if `user_ids` is empty, without issuing a query — an empty `IN ()` is either invalid or always-false depending on dialect handling, don't rely on it).

- [x] Task 5: `domain/recipients.py` — extend with `RecipientListDirectoryService` (AC: #1, #2, #3, #4, #5, #6)
  - [x] This story **extends the existing file**, per CAP-5's fixed location (`domain/recipients`) — do not create a new `domain/recipient_lists.py`; `UserDirectoryService`/`TeamDirectoryService` already live here and `RecipientListDirectoryService` joins them as a third class in the same module.
  - [x] New exceptions (module-level, same style as the existing five): `RecipientListNameTaken`, `RecipientListNotFound`, `MemberNotFound`, `MemberInactive`, `MemberNotAddressable`.
  - [x] `RecipientListDirectoryService(recipient_lists: RecipientListRepository, users: UserRepository, audit_log: AuditLogRepository)`:
    - `async def _ensure_members_valid(self, member_user_ids: list[uuid.UUID]) -> None` — no-ops on an empty list (a `RecipientList` may legitimately start with zero members; nothing in the ACs requires a minimum). Otherwise: one `get_many_by_ids` call, build an `{id: User}` dict, then for each requested id — raise `MemberNotFound()` if absent, `MemberInactive()` if `status != UserStatus.ACTIVE`, `MemberNotAddressable()` if `mobile is None` (AC #6 — catches Administrator rows without hard-coding a Role check; check status before mobile so an inactive-and-mobile-less row reports as inactive, the more actionable error).
    - `create_recipient_list(name, kind, member_user_ids, actor_user_id) -> RecipientList` — `name = name.strip()`; raise `RecipientListNameTaken()` if `get_by_name(name)` is non-`None`; call `_ensure_members_valid`; `add(...)` then `replace_members(...)`; one `AuditLogEntry` (`action="recipient_list.created"`, `entity_type="RecipientList"`, `details={"name": name, "kind": kind.value, "member_count": len(member_user_ids)}`). Return the freshly-read row.
    - `update_recipient_list(recipient_list_id, name, kind, member_user_ids, actor_user_id) -> RecipientList` — load target, raise `RecipientListNotFound()` if absent; `name = name.strip()`; raise `RecipientListNameTaken()` if a *different* list already has that name; `_ensure_members_valid`; `update_details(...)` then `replace_members(...)` (full-replace, not a diff — simplest correct semantics for a form that submits its whole current selection); audit `action="recipient_list.updated"`. `kind` is editable here (unlike `Role` on `User`, which is genuinely immutable because it drives WhatsApp content routing) — `kind` is purely a display label per AD-4, so allowing an Administrator to move a list between "Group" and "Channel" costs nothing and needs no special-casing.
    - `remove_recipient_list(recipient_list_id, actor_user_id) -> None` — load target, raise `RecipientListNotFound()` if absent; `deactivate(...)`; audit `action="recipient_list.deactivated"`. Membership rows are left in place on soft-delete (they're harmless once the list itself is inactive, and deleting them would contradict "never hard-deleted" in spirit even though they're join rows, not the entity itself).

- [x] Task 6: `api/recipients/routes.py` — new `/recipient-lists` resource (AC: #1, #2, #3, #4, #5, #6)
  - [x] Extend the existing file/module — same one-router-per-resource-in-one-file convention `users_router`/`teams_router` already establish here. Add `recipient_lists_router = APIRouter(prefix="/recipient-lists", tags=["recipients"])`.
  - [x] Request/response models:
    ```python
    class CreateRecipientListRequest(BaseModel):
        name: str = Field(min_length=1, max_length=255)
        kind: Literal["group", "channel"]
        member_user_ids: list[uuid.UUID] = Field(default_factory=list)

    class UpdateRecipientListRequest(BaseModel):
        name: str = Field(min_length=1, max_length=255)
        kind: Literal["group", "channel"]
        member_user_ids: list[uuid.UUID] = Field(default_factory=list)

    class RecipientListResponse(BaseModel):
        id: uuid.UUID
        name: str
        kind: str
        status: str
        version: int
        member_user_ids: list[uuid.UUID]
    ```
  - [x] `RecipientListNotFound` reuses the existing generic `_not_found(entity: str)` helper (→ `_not_found("RecipientList")`, code `"not_found"`) — same as `TeamNotFound`/`UserNotFound` already do. Do not invent a `recipient_list_not_found` code for it; the codebase's convention is: state-conflict exceptions (taken/inactive/not-addressable) get entity-specific codes, plain not-found exceptions all share the generic `"not_found"` code with an entity-specific message.
  - [x] `POST /recipient-lists` → 201. Catches `RecipientListNameTaken` → 409 `recipient_list_name_taken`; `MemberNotFound` → 404 (via `_not_found("User")`); `MemberInactive` → 422 `member_inactive`; `MemberNotAddressable` → 422 `member_not_addressable` (message: e.g. "This User has no mobile number on file and can't receive WhatsApp sends"). Wrap `session.commit()` in `try/except IntegrityError` → 409 `recipient_list_name_taken` (same race-backstop pattern as `create_team`).
  - [x] `GET /recipient-lists` → all statuses, all kinds, `member_user_ids` embedded per row (no separate get-by-id detail endpoint — this story's scale doesn't need one; the edit form gets everything it needs from the list response, same non-paginated simplicity as `GET /users`/`GET /teams`).
  - [x] `PATCH /recipient-lists/{id}` → catches `RecipientListNotFound` → 404 (`_not_found("RecipientList")`), `RecipientListNameTaken` → 409, `MemberNotFound` → 404, `MemberInactive` → 422, `MemberNotAddressable` → 422; same `IntegrityError` backstop as `update_team`.
  - [x] `DELETE /recipient-lists/{id}` → 204, catches `RecipientListNotFound` → 404 (`_not_found("RecipientList")`).
  - [x] Register in `api/main.py`: `app.include_router(recipient_lists_router)` (import alongside the existing `teams_router`/`users_router` imports from `api.recipients.routes`).

- [x] Task 7: Dev-loop and deployment wiring (AC: #1, #2) — Story 3.1's code review caught this exact gap for `/users`/`/teams` after the fact; get it right the first time here.
  - [x] `web/vite.config.ts` — add `'/recipient-lists': 'http://localhost:8000'` to `server.proxy`.
  - [x] `docker/nginx/nginx.conf` — add both an exact-match and a prefix block, mirroring the `/users`/`/teams` pair exactly (bare-prefix POST/GET without a trailing slash falls through to the SPA catch-all otherwise — the false-success bug Story 3.1's review found):
    ```nginx
    location = /recipient-lists {
        proxy_pass http://api:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /recipient-lists/ {
        proxy_pass http://api:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
    ```

- [x] Task 8: Frontend — Recipient Groups & Channels (AC: #1, #2, #3, #4, #5, #6)
  - [x] `web/src/components/RecipientPicker.tsx` (new) — the first version of the shared "Recipient picker" component EXPERIENCE.md's component vocabulary names (used by directory group/channel editing now; Epic 4's Notifications ▸ Compose extends/reuses it later for mixed User+Team+RecipientList selection with a live de-duplicated count — that cross-type dedupe logic is explicitly **not** this story's job, same "backward extension, not forward dependency" posture as Story 2.2's notification-status field). This story's version: a plain multi-select of individual, active, WhatsApp-addressable Users only (MUI `Autocomplete multiple` over `{id, name}` options, or an equivalent checklist), showing a simple "N selected" caption — no overlap/dedupe count needed yet, since every option here is the same type (an individual User) and can't overlap with itself. The options list passed in must already exclude Administrator rows (`mobile === null`) — filter them out alongside the active-status filter (AC #6) so the picker never even offers an unaddressable User, rather than relying solely on the server's `MemberNotAddressable` rejection.
  - [x] `web/src/pages/RecipientListFormDialog.tsx` (new) — one component for create + edit (`list === null` means create, same convention as `UserFormDialog`/`TeamFormDialog`). Fields: Name, a hidden/fixed `kind` determined by which tab opened it (Groups tab → `kind: 'group'`, Channels tab → `kind: 'channel'`), and `RecipientPicker` for membership. Options passed to `RecipientPicker` are `users` filtered to `status === 'active'` (same `activeTeamOptions` filtering pattern `RecipientsPage.tsx` already computes for the Team `Select` — that filtering lives in the page, not inside `UserFormDialog.tsx` itself) — pass the current list's own already-selected members through untouched even if one has since gone inactive (same "include the current value even if now inactive" fix Story 3.1's code review applied to the Team select), so editing a list doesn't silently drop a member from view.
  - [x] `web/src/pages/RecipientListsPanel.tsx` (new) — one component parameterized by `kind: 'group' | 'channel'` and a `title`/`emptyMessage`, rendered twice by `RecipientsPage` (once per new tab). Justified as a real, immediate 2-consumer extraction (not the speculative one-consumer abstraction Story 3.1's Dev Notes explicitly avoided for the page shell) — Groups and Channels are the same UI and API shape, differing only by the `kind` value sent/filtered. Uses `ResponsiveDataTable` (columns: Name, Members — `member_user_ids.length`, Status via `StatusBadge`, actions), `EmptyState` (kind-specific copy, e.g. *"No Recipient Groups yet. Add your first Group to target a named set of Users in one selection."* / the Channel equivalent), and `ConfirmationDialog` for removal (consequence text: *"This removes {name} from the directory. Future notifications will no longer reach its {N} member(s)."*) — same submitting-aware, unmount-safe patterns Story 3.1's code review already established for the Users/Teams tabs.
  - [x] `web/src/pages/RecipientsPage.tsx` — extend the existing `Tabs` from two (`'users' | 'teams'`) to four (`'users' | 'teams' | 'groups' | 'channels'`), adding `Tab value="groups" label="Recipient Groups"` / `Tab value="channels" label="Recipient Channels"` — this is the exact extension point Story 3.1's Dev Notes reserved ("leaves room for Story 3.2 to add 'Groups'/'Channels' tabs later without restructuring"). Fetch `GET /recipient-lists` once (alongside the existing `loadUsers`/`loadTeams` calls, same unmount-cancellation-guarded `useCallback` shape), filter client-side by `kind` for each of the two new tabs — do not add a `?kind=` query parameter to the API call, the whole list is small enough to fetch once and split client-side (same reasoning `GET /users`/`GET /teams` never paginate). Clear `actionError` on every tab switch, including into/out of the two new tabs (Story 3.1 code review's fix for the Users/Teams pair applies identically here).
  - [x] No mockup exists for Groups/Channels (same gap as Users/Teams in Story 3.1) — build from `EXPERIENCE.md`'s Recipient picker / Directory form / Data table / Confirmation dialog descriptions (cited in Dev Notes), not a pixel reference.

- [x] Task 9: Tests (AC: all)
  - [x] `tests/domain/test_recipients_service.py` — extend with `RecipientListDirectoryService` coverage using hand-written fakes (no mocking library, established convention): create success + audit entry; create with a taken name raises `RecipientListNameTaken`; create with a nonexistent member raises `MemberNotFound`; create with an inactive member raises `MemberInactive`; create with an Administrator (`mobile=None`) as a member raises `MemberNotAddressable`; create with zero members succeeds; update renames + changes `kind` + replaces membership; update on a nonexistent list raises `RecipientListNotFound`; remove soft-deletes and audits; membership replace is a true full-replace (removing an id from the submitted set actually drops it, not just adds new ones).
  - [x] `tests/adapters/persistence/test_recipient_list_repository.py` (new) — `add`/`get_by_id`/`get_by_name` (active-only filtering, found/not-found), `list_all_full` (multiple lists, correct per-list membership grouping — this is the test that would catch an N+1-avoidance bug if the grouping logic were wrong), `update_details`, `deactivate`, `replace_members` (replacing a non-empty set with an empty one actually clears all rows), `get_member_user_ids`.
  - [x] `tests/adapters/persistence/test_user_repository.py` — extend with `get_many_by_ids` (found subset, empty input, mixed found/not-found ids).
  - [x] `tests/api/test_recipients_routes.py` — extend with full `/recipient-lists` route coverage: 201/200/204 happy paths for both `kind` values, 409 `recipient_list_name_taken`, 404 `not_found` on a nonexistent member, 422 `member_inactive`, 422 `member_not_addressable` (attempt to add a seeded Administrator as a member), 404 `not_found` on update/delete of an unknown `RecipientList` id, 401 on every route when unauthenticated (AD-8).
  - [x] `tests/conftest.py` — `_clean_tables` must delete `recipient_list_members` **before** `users` (it has an FK to `users.id`, same reasoning `password_reset_tokens` is deleted before `users`) and **before** `recipient_lists` (FK to `recipient_lists.id`). Add `DELETE FROM recipient_list_members` immediately before the existing `DELETE FROM users` line, and `DELETE FROM recipient_lists` anywhere after `users` (e.g. alongside `teams`) — verify this ordering against the new migration's FK definitions before relying on it.
  - [x] Frontend: `RecipientListFormDialog.test.tsx`, `RecipientListsPanel.test.tsx`, `RecipientPicker.test.tsx` (new) — mirror `UserFormDialog.test.tsx`'s `vi.stubGlobal('fetch', ...)` convention. Cover: both tabs render rows from a mocked `GET /recipient-lists` filtered by `kind`; create flow posts `member_user_ids` and refreshes; editing a list whose member has since gone inactive still shows that member in the picker (same inactive-team-in-select precedent); remove flow shows the real member-count consequence text and calls `DELETE` on confirm.
  - [x] `uv run pytest -q`, `uv run ruff check .`, `uv run mypy .`, `uv run lint-imports` after backend changes — same gate every prior story ran clean against.

### Review Findings

- [x] [Review][Patch] Concurrent duplicate-name race yields unhandled 500 instead of 409, on both create and update [adapters/persistence/recipient_lists.py:85-96,113-121] — `add()` flushes immediately (unlike `TeamRepository.add()`, which defers to the route's commit) and `update_details()` executes its `UPDATE` immediately; both sit inside the route's `try/except` that only catches the five named domain exceptions, not `IntegrityError` (api/recipients/routes.py:498-522,551-579). Two concurrent requests reusing the same name each pass the `get_by_name()` pre-check, then the loser's flush/execute raises an uncaught `IntegrityError`, producing a bare 500 instead of the intended 409 `recipient_list_name_taken`. No test exercises this race. **Fixed**: added an `except IntegrityError` clause to both routes' first `try` block, mapping to the same `_recipient_list_name_taken()` 409 the final-commit backstop already provides.
- [x] [Review][Patch] Duplicate ids in `member_user_ids` crash with an unhandled 500 instead of a validation error [domain/recipients.py:308-324] — neither the Pydantic request models nor `_ensure_members_valid` dedupe `member_user_ids`; a repeated id passes validation (each id independently resolves fine) then hits `replace_members()`'s bulk insert into the `(recipient_list_id, user_id)` composite-PK table, raising an uncaught `IntegrityError` → 500. Reachable via a double-submitted form or any future API consumer (e.g. Epic 4's Compose reusing this endpoint), not just malicious input. **Fixed**: `create_recipient_list`/`update_recipient_list` now dedupe `member_user_ids` via `list(dict.fromkeys(...))` before validation/replace_members. Added regression tests `test_create_recipient_list_dedupes_repeated_member_ids` and `test_update_recipient_list_dedupes_repeated_member_ids`.
- [x] [Review][Defer] No guard against acting on an already-inactive RecipientList (double-remove / edit-while-inactive) [domain/recipients.py:355-411] — deferred, pre-existing (mirrors the identical gap already present in `TeamDirectoryService`/`UserDirectoryService` from Story 3.1; not introduced by this diff)
- [x] [Review][Defer] Whitespace-only name passes validation and can create a blank-named RecipientList [domain/recipients.py:333-370] — deferred, pre-existing (mirrors the identical latent gap already present in `TeamDirectoryService.create_team`/`update_team`; not introduced by this diff)

## Dev Notes

- **This story extends `domain/recipients.py` and `api/recipients/routes.py`, it does not create new packages for them.** CAP-5 fixes both file locations for the whole "Recipient directory management" capability; `RecipientListDirectoryService` and `recipient_lists_router` join the classes/routers Story 3.1 already put there.
- **`RecipientList` unifies Recipient Group and Recipient Channel — this is a GrowthTrack-internal saved set of individual Users, never a live WhatsApp Group/Channel object.** Per PRD Addendum A6: Twilio's WhatsApp API has no mechanism to broadcast into a real WhatsApp Group, and WhatsApp Channels use an incompatible broadcast model. Sending to a `RecipientList` fans out to each member's individual phone number via the same per-recipient template-message call used for an individual Recipient — `kind` (`group`/`channel`) is a display-only label an Administrator picks for organizational clarity, with zero difference in fan-out mechanism, storage, or validation. Don't build anything that branches behavior on `kind` beyond the tab it's shown under and the value round-tripped to the API.
- **Members are individual Users only — never Teams, never other `RecipientList`s nested inside one.** Epic 4's Notification `NotificationTarget` join rows are what let a single Notification target a mix of User/Team/RecipientList later (AD-4) — that's a Notification-level composition, not a `RecipientList`-level one. Don't build nested-list membership; it isn't in any AC and isn't in the architecture spine's data model.
- **The Recipient picker built here is deliberately the simple, single-type version.** EXPERIENCE.md names it as shared with Notifications ▸ Compose, but Compose (Epic 4, not yet built) needs to resolve a *mixed* selection of individual Users, Teams, and RecipientLists into one de-duplicated count ("14 selected → 11 unique recipients (3 overlaps merged)") using the same resolution logic AD-2 defines for send-time dedup. This story's picker only ever selects among individual Users for one list's membership — there's no overlap to de-duplicate within a single, homogeneous selection. Do not build the cross-type resolver now; Epic 4 extends this component (or builds its own) once that logic exists.
- **Name uniqueness is scoped to active rows, shared across both `kind` values (one namespace, not two).** A `RecipientList` is one entity type per AD-4; `kind` doesn't partition its own uniqueness space. This mirrors `ix_users_mobile_active_uq`/`ix_teams_name_active_uq` exactly — get the partial index right in this story's *first* migration; Story 3.1 only arrived at this after a follow-up migration triggered by code review.
- **Version-conflict rejection is explicitly out of scope**, same as `User`/`Team`: `RecipientList` gets a `version` column that increments on every update/deactivate, but no `WHERE version = :expected` precondition — Story 3.4 (Concurrent-Edit Conflict Detection) owns stale-write rejection across all three entities together.
- **A member must be WhatsApp-addressable (`mobile is not None`), which in practice excludes Administrator rows.** Story 3.1 built `User.mobile` as nullable specifically because Administrator rows never get one (they authenticate to the portal, they don't receive sends — Addendum A5). Checking `mobile is None` directly (rather than `role == Role.ADMINISTRATOR`) is the more direct, structurally-grounded check and doesn't need to special-case a role at all — it also automatically covers any future row shape that ends up mobile-less for a different reason.
- **Opt-in consent (Story 3.3) is untouched by this story.** A `RecipientList`'s membership is just "which Users are in this named set" — whether a given member has recorded WhatsApp consent is checked later, at send-time recipient resolution (AD-9), not here. Adding a User to a Group/Channel they haven't opted into is not an error this story should raise.
- **No mockup exists for this screen** (same gap Story 3.1 already navigated for Users/Teams) — build from `EXPERIENCE.md`'s component descriptions, not a pixel reference.

### Project Structure Notes

- New backend files: `ports/recipient_lists.py`, `adapters/persistence/recipient_lists.py`, `alembic/versions/<new>_recipient_lists_and_membership.py`, `tests/adapters/persistence/test_recipient_list_repository.py`.
- Modified backend files: `domain/models.py` (`RecipientList`, `RecipientListKind`, `RecipientListStatus`), `domain/recipients.py` (new `RecipientListDirectoryService` + 5 new exceptions), `ports/users.py` (`get_many_by_ids`), `adapters/persistence/users.py` (`get_many_by_ids`), `api/recipients/routes.py` (new `recipient_lists_router`), `api/main.py` (router registration), `tests/domain/test_recipients_service.py`, `tests/adapters/persistence/test_user_repository.py`, `tests/api/test_recipients_routes.py`, `tests/conftest.py` (`_clean_tables` ordering).
- New frontend files: `web/src/components/RecipientPicker.tsx` (+ `.test.tsx`), `web/src/pages/RecipientListFormDialog.tsx` (+ `.test.tsx`), `web/src/pages/RecipientListsPanel.tsx` (+ `.test.tsx`).
- Modified frontend/deploy files: `web/src/pages/RecipientsPage.tsx` (two new tabs), `web/vite.config.ts`, `docker/nginx/nginx.conf`.
- No changes to `config.py`, `scheduler/`, `adapters/whatsapp_twilio/`, `adapters/source_system/`, `domain/ingestion.py`, or anything in `api/notifications` (doesn't exist until Epic 4) — this story stays entirely within CAP-5's boundary.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 3.2: Manage Recipient Groups & Channels] (all 3 literal ACs)
- [Source: _bmad-output/planning-artifacts/epics.md#Story 3.4: Concurrent-Edit Conflict Detection] (confirms version-conflict rejection is that story's scope, not this one's)
- [Source: _bmad-output/planning-artifacts/epics.md#Story 3.3: Recipient Opt-In Consent Capture] (confirms consent state is unrelated to list membership, checked later at resolution)
- [Source: _bmad-output/planning-artifacts/prds/prd-GrowthTrack-2026-07-14/prd.md#FR-9] ("Administrator can add, edit, or remove ... Recipient Groups, Recipient Channels ... all directory changes are audit-logged")
- [Source: _bmad-output/planning-artifacts/prds/prd-GrowthTrack-2026-07-14/addendum.md#A6 Recipient Group / Recipient Channel — Technical Feasibility Note] (the entire basis for treating Group/Channel as GrowthTrack-internal saved User sets, not live WhatsApp platform objects — Twilio has no Group-broadcast API)
- [Source: ARCHITECTURE-SPINE.md#AD-4] (`RecipientList` as the single entity backing Group/Channel via `kind`; `Team`/`User`/`RecipientList` soft-delete convention; relational join rows, never a JSON blob, for target/membership modeling)
- [Source: ARCHITECTURE-SPINE.md#AD-7] (co-transactional audit write — every mutating service method)
- [Source: ARCHITECTURE-SPINE.md#AD-2] (recipient resolution happens fresh at send time, never frozen at creation — the reason this story's picker doesn't need to resolve/dedupe anything itself)
- [Source: ARCHITECTURE-SPINE.md#Core-entity relationships ERD] (`USER }o--o{ RECIPIENT_LIST : "member of"` — the many-to-many membership this story's join table implements)
- [Source: ARCHITECTURE-SPINE.md#Capability → Architecture Map] (CAP-5 fixes `api/recipients`, `domain/recipients` as this story's file locations too — same as Story 3.1)
- [Source: ARCHITECTURE-SPINE.md#Consistency Conventions] (`User`/`Team`/`RecipientList` carry a version column; REST plural-noun resources; `{error:{code,message,details}}` envelope)
- [Source: domain/recipients.py, domain/models.py, ports/teams.py, ports/users.py, adapters/persistence/teams.py, adapters/persistence/users.py] (the exact existing patterns this story mirrors: service structure, co-transactional audit writes, active-only uniqueness filtering, `_to_domain` free functions, `_ensure_team_active`-style validation)
- [Source: alembic/versions/17eb25555c26_recipients_directory_active_only_.py] (the partial-unique-index pattern this story's migration adopts from the start, avoiding the follow-up-migration path Story 3.1 needed)
- [Source: api/recipients/routes.py, api/main.py] (the router-per-resource-in-one-file convention, `Depends(get_current_user)`, typed-exception-to-HTTPException mapping, `IntegrityError` race backstop this story's new routes mirror)
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-GrowthTrack-2026-07-14/EXPERIENCE.md#Information Architecture] ("Recipients | Nav | Manage Users, Recipient Groups, Recipient Channels, Sales Teams")
- [Source: EXPERIENCE.md#Shared component vocabulary] ("Recipient picker — used by both Notifications ▸ Compose and directory group/channel/team editing... shows the de-duplicated count live" — basis for building the picker here first, simple-typed, with the cross-type dedupe explicitly deferred to Epic 4)
- [Source: EXPERIENCE.md#State Patterns] (Empty state: direct copy + one primary action, never a generic placeholder; Confirmation dialog: names the real consequence)
- [Source: web/src/pages/RecipientsPage.tsx] ("leaves room for Story 3.2 to add 'Groups'/'Channels' tabs later without restructuring" — the literal extension point this story uses)
- [Source: web/src/components/ResponsiveDataTable.tsx, ConfirmationDialog.tsx, EmptyState.tsx, StatusBadge.tsx] (existing shared components this story composes, does not rebuild)
- [Source: _bmad-output/implementation-artifacts/3-1-manage-users-sales-teams.md#Review Findings] (the exact classes of bugs this story's tasks pre-empt: missing Nginx exact-match blocks, non-active-scoped uniqueness shipped too late, N+1 name/membership resolution, unmount-safety, inactive-option-hidden-in-select)
- [Source: _bmad-output/implementation-artifacts/deferred-work.md] (no open item from any prior story's code review touches `RecipientList`/membership directly; confirms this story starts clean)

### Git Intelligence

- `HEAD` is `a352f24` ("Story 3.1: manage users & sales teams"), working tree clean. Migration chain currently ends at `17eb25555c26` — this story's new migration must set `down_revision = "17eb25555c26"` (confirm with `uv run alembic heads` before writing it, don't hand-guess).
- Commit style: one commit per logical unit of work, imperative summary line, ending with the `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>` trailer.
- Every prior story's Debug Log ran `uv run pytest -q`, `uv run ruff check .`, `uv run mypy .`, `uv run lint-imports` clean before being marked `done` — run the same four before considering this story complete. `lint-imports` matters here too: `domain/recipients.py`'s new class must only import from `ports/`, never `adapters/`/`api/` (AD-1) — same rule Story 3.1's `RecipientListDirectoryService`-adjacent classes already satisfy.
- Story 3.1's own code review is the single richest source of "mistakes already made once in this exact directory-CRUD shape" — Task list above pre-empts each one (partial index from the start, exact-match Nginx blocks from the start, N+1-avoidance from the start, inactive-option-visible-in-edit from the start) rather than requiring a second review pass to catch them again.

## Dev Agent Record

### Agent Model Used

claude-sonnet-5

### Debug Log References

- `uv run alembic upgrade head` — migration `976cabf50f32` applied cleanly on top of `17eb25555c26`.
- `uv run pytest -q` — 302 passed.
- `uv run ruff check .` — all checks passed.
- `uv run mypy .` — 0 new errors introduced; 12 pre-existing errors remain in `tests/domain/test_bootstrap_service.py`, `tests/domain/test_auth_service.py`, `tests/domain/test_password_reset_service.py`, `tests/api/test_auth_routes.py`, and the pre-existing `_user_service`/`TeamDirectoryService` fake-repository calls in `tests/domain/test_recipients_service.py` — confirmed via `git stash` against `main` (commit `a352f24`) that these errors pre-date this story (Fake repositories are plain classes, not registered ABC subclasses, so mypy's nominal typing rejects them structurally; unrelated to this story's scope).
- `uv run lint-imports` — 2 contracts kept, 0 broken.
- `npx tsc -b` (web) — 0 errors.
- `npx eslint .` (web) — 0 errors in new/modified files (2 pre-existing errors in untouched `DashboardPage.tsx`/`LoginPage.tsx`, confirmed via `git status` to be unrelated to this story).
- `npx vitest run` (web) — 113 passed, 20 files. One real bug found and fixed during frontend testing: `RecipientPicker.test.tsx`'s chip-removal test used a bad selector (`getByRole('button', {name: /karim/i})` doesn't match MUI's Chip delete icon); fixed by targeting `getByTestId('CancelIcon')` scoped to the chip. One flaky test fixed: `RecipientsPage.test.tsx`'s new "clears actionError" test needed to wait for the ConfirmationDialog's exit transition to finish (`waitFor` on `queryByRole('dialog')`) before clicking the newly-revealed tab, since MUI's modal aria-hides background content during the close transition.

### Completion Notes List

- Migration `976cabf50f32` adds `recipient_lists` (partial unique index on `name` scoped to `status = 'active'`, from the first migration — no follow-up needed) and `recipient_list_members` (pure Core-table join, composite PK, no cascade since soft-delete means the FK's `NO ACTION` default never fires).
- `domain/models.py` gets `RecipientList`, `RecipientListKind`, `RecipientListStatus` (its own enum, not shared with `TeamStatus`/`UserStatus`, per Story 3.1's Dev Notes prediction).
- `RecipientListDirectoryService` (`domain/recipients.py`) implements create/update/remove with co-transactional audit logging (AD-7), active-only name uniqueness (AD-4), and `_ensure_members_valid` (AC #5/#6: rejects nonexistent, inactive, or mobile-less — i.e. Administrator — members, checking status before mobile so the more actionable error surfaces first).
- Found and fixed one real bug during backend testing: `SqlAlchemyRecipientListRepository.add()` staged the new `RecipientList` row via `session.add()` without flushing; `create_recipient_list`'s immediately-following `replace_members()` call issues a plain Core `INSERT` into `recipient_list_members`, which doesn't trigger SQLAlchemy's ORM autoflush the way a `select()`/ORM query would — so the FK to the not-yet-flushed parent row failed with `ForeignKeyViolationError`. Fixed by adding an explicit `await self._session.flush()` at the end of `add()`. Caught by `test_create_recipient_list_group_succeeds_and_is_audit_logged` in the full `pytest` run, not a hand-written repository test in isolation.
- New `/recipient-lists` REST resource (`api/recipients/routes.py`) mirrors the existing `/users`/`/teams` router conventions exactly: typed-exception-to-HTTPException mapping, `IntegrityError` race backstop, `_not_found("RecipientList")` reusing the shared generic-not-found helper.
- Frontend: `RecipientPicker` (new shared component, simple single-type version per Dev Notes), `RecipientListFormDialog` (create+edit, kind fixed by which tab opened it), `RecipientListsPanel` (parameterized by `kind`, rendered twice), and `RecipientsPage` extended from 2 to 4 tabs. The picker-options augmentation (base active+addressable options, plus the currently-edited list's own members even if since gone inactive, labeled "(inactive)") lives in `RecipientListsPanel` rather than `RecipientsPage`, since the `editing` state that drives it is local to the panel — the same "include the current value even if now inactive" pattern Story 3.1's code review established for the Team select, adapted to where the relevant state actually lives.
- `.env`'s `POSTGRES_PORT` was corrected from a stale `15432` to `5432` (matching `docker-compose.yml`'s actual port mapping and `.env.example`) so local `alembic`/`pytest` runs could reach the dev Postgres container; `.env` is gitignored, so this is a local-only fix, not a tracked change.
- Deferred nothing: all 6 ACs are covered by the domain service, route layer, and both backend/frontend test suites; no open items identified for `deferred-work.md`.

### File List

**New:**
- `alembic/versions/976cabf50f32_recipient_lists_and_membership.py`
- `ports/recipient_lists.py`
- `adapters/persistence/recipient_lists.py`
- `tests/adapters/persistence/test_recipient_list_repository.py`
- `web/src/components/RecipientPicker.tsx`
- `web/src/components/RecipientPicker.test.tsx`
- `web/src/pages/RecipientListFormDialog.tsx`
- `web/src/pages/RecipientListFormDialog.test.tsx`
- `web/src/pages/RecipientListsPanel.tsx`
- `web/src/pages/RecipientListsPanel.test.tsx`

**Modified:**
- `domain/models.py`
- `domain/recipients.py`
- `ports/users.py`
- `adapters/persistence/users.py`
- `api/recipients/routes.py`
- `api/main.py`
- `web/vite.config.ts`
- `docker/nginx/nginx.conf`
- `tests/domain/test_recipients_service.py`
- `tests/adapters/persistence/test_user_repository.py`
- `tests/api/test_recipients_routes.py`
- `tests/conftest.py`
- `web/src/pages/RecipientsPage.tsx`
- `web/src/pages/RecipientsPage.test.tsx`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`

## Change Log

- 2026-07-20: Implemented Story 3.2 — Recipient Groups & Channels backend (migration, domain service, repository, REST routes) and frontend (RecipientPicker, RecipientListFormDialog, RecipientListsPanel, RecipientsPage tabs). All 9 tasks complete, all 6 ACs satisfied. Full backend (`pytest`/`ruff`/`mypy`/`lint-imports`) and frontend (`vitest`/`eslint`/`tsc`) gates green.
