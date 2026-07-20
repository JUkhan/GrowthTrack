---
baseline_commit: c1d411c
---

# Story 3.4: Concurrent-Edit Conflict Detection

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an Administrator,
I want to be warned if I try to save a record someone else already changed,
so that I never silently overwrite a teammate's edit.

## Acceptance Criteria

1. **Given** a User, Team, or `RecipientList` with a version column, **when** two Administrators load the same record and one saves first, **then** the second save is rejected as a conflict, not silently applied. [Source: epics.md#Story 3.4, ARCHITECTURE-SPINE.md#Consistency Conventions]
2. **Given** a save conflict, **when** surfaced, **then** a conflict dialog shows both versions and requires an explicit choice — never a silent overwrite. [Source: epics.md#Story 3.4, ux-designs/EXPERIENCE.md#State Patterns]
3. **[Derived — AC #1 says "rejected as a conflict," but a pre-check alone (compare loaded version to current version, then write) is a read-then-write TOCTOU race: two requests can both read the same version before either commits, both pass the pre-check, and the second silently wins — exactly the bug this story exists to close. Closing it requires the same advisory-pre-check-plus-atomic-DB-backstop shape this codebase already uses for `RecipientListNameTaken`/`MobileTaken`/`ConsentAlreadyActive`]** **Given** two concurrent save requests that both read the same version before either commits, **when** they run their `UPDATE ... WHERE id = ? AND version = ?` statements, **then** at most one succeeds — the losing request's update affects zero rows and is rejected as a conflict, even though its own pre-check passed. [Source: domain/recipients.py precedent (`OptInConsentRepository.revoke_active`'s `rowcount > 0` pattern, Story 3.3), ARCHITECTURE-SPINE.md#Consistency Conventions]
4. **[Derived — the epics AC only says "a save," but this codebase's three directory entities (User, Team, RecipientList) share one PATCH-based edit shape; leaving one entity unguarded would silently defeat AC #1's own "a User, Team, or RecipientList" scope]** **Given** the `PATCH /users/{id}`, `PATCH /teams/{id}`, and `PATCH /recipient-lists/{id}` routes, **when** the request body's `version` does not match the record's current version, **then** all three return `409 {error: {code: "version_conflict"}}` with the current server-side record embedded in `details.current` — the same guarantee, applied uniformly across all three entities, not just one. [Source: ARCHITECTURE-SPINE.md#Consistency Conventions ("`User`/`Team`/`RecipientList` carry an optimistic-concurrency version column")]

## Tasks / Subtasks

- [x] Task 1: `domain/recipients.py` — `VersionConflict` exception + wire into all three `update_*` methods (AC: #1, #2, #3)
  - [x] Add `class VersionConflict(Exception):` near the other bare marker exceptions in this file (same style as `TeamNameTaken`/`RecipientListNotFound` — no payload; the API layer re-fetches the current record for the 409 body, it doesn't need the exception to carry data).
  - [x] `UserDirectoryService.update_user` gains a new required parameter `expected_version: int`. Insert the pre-check **immediately after** the existing `CannotEditAdministrator` check, **before** `mobile_changed = target.mobile != mobile` and the team/mobile validation below it:
    ```python
    target = await self._users.get_by_id(user_id)
    if target is None:
        raise UserNotFound()
    if target.role == Role.ADMINISTRATOR:
        raise CannotEditAdministrator()
    if target.version != expected_version:
        raise VersionConflict()
    mobile_changed = target.mobile != mobile
    ...
    ```
    This ordering is deliberate: a stale version means the Administrator is editing against data that's already moved, so it's rejected before spending a query on team-active/mobile-uniqueness checks that are about to be redone against fresh data anyway — and before the mobile-change consent-auto-revoke side effect could fire based on stale assumptions.
  - [x] Change the repository call site from `await self._users.update_directory_fields(user_id, name, mobile, team_id)` to pass `expected_version` and check its (now-boolean) return value **before** the mobile-changed consent-revoke block and the `user.updated` audit write:
    ```python
    updated = await self._users.update_directory_fields(
        user_id, name, mobile, team_id, expected_version
    )
    if not updated:
        raise VersionConflict()
    if mobile_changed:
        ...  # unchanged
    ```
    This is AC #3's real backstop — the pre-check above catches the common case cheaply, this catches the genuine race the pre-check structurally cannot (both requests can read `target.version == expected_version` before either commits).
  - [x] `TeamDirectoryService.update_team` gains `expected_version: int`. Same shape: pre-check right after the not-found check (before the name-taken check), then `updated = await self._teams.update_name(team_id, name, expected_version)`, `if not updated: raise VersionConflict()`, before the audit write.
  - [x] `RecipientListDirectoryService.update_recipient_list` gains `expected_version: int`. Same pre-check placement (after not-found, before name-taken). Gate `update_details` the same way: `updated = await self._recipient_lists.update_details(recipient_list_id, name, kind, expected_version)`, `if not updated: raise VersionConflict()` — **before** the `replace_members(...)` call, not after. Membership must never be replaced on a lost race; gating `update_details` first and only calling `replace_members` once it succeeds keeps both writes inside the version guard.

- [x] Task 2: `ports/users.py`, `ports/teams.py`, `ports/recipient_lists.py` — extend the three update signatures (AC: #1, #3)
  - [x] `UserRepository.update_directory_fields(self, user_id, name, mobile, team_id, expected_version: int) -> bool` — docstring explains the atomic-conditional-update contract: `False` means the version moved since the caller last read it (or the id vanished, but the caller already confirmed existence), same shape as `OptInConsentRepository.revoke_active`'s existing docstring (Story 3.3).
  - [x] `TeamRepository.update_name(self, team_id, name, expected_version: int) -> bool` — same contract.
  - [x] `RecipientListRepository.update_details(self, recipient_list_id, name, kind, expected_version: int) -> bool` — same contract.

- [x] Task 3: SQLAlchemy adapters — atomic `WHERE id = ? AND version = ?` updates (AC: #1, #3)
  - [x] `adapters/persistence/users.py#SqlAlchemyUserRepository.update_directory_fields` — add `expected_version: int` param; add `UserModel.version == expected_version` to the `.where(...)` clause (alongside the existing `UserModel.id == user_id`); cast the result and return `rowcount > 0`, exactly `OptInConsentRepository.revoke_active`'s pattern (`adapters/persistence/consent.py:87-94`):
    ```python
    async def update_directory_fields(
        self, user_id: uuid.UUID, name: str, mobile: str, team_id: uuid.UUID, expected_version: int
    ) -> bool:
        stmt = (
            update(UserModel)
            .where(UserModel.id == user_id, UserModel.version == expected_version)
            .values(name=name, mobile=mobile, team_id=team_id, version=UserModel.version + 1)
        )
        result = cast(CursorResult, await self._session.execute(stmt))
        return result.rowcount > 0
    ```
    Needs `from typing import cast` and `from sqlalchemy.engine import CursorResult` added to this file's imports (not currently present).
  - [x] `adapters/persistence/teams.py#SqlAlchemyTeamRepository.update_name` — identical shape: add `expected_version: int`, `.where(TeamModel.id == team_id, TeamModel.version == expected_version)`, `cast(CursorResult, ...)`, `return result.rowcount > 0`. Same new imports needed in this file.
  - [x] `adapters/persistence/recipient_lists.py#SqlAlchemyRecipientListRepository.update_details` — identical shape: add `expected_version: int`, `.where(RecipientListModel.id == recipient_list_id, RecipientListModel.version == expected_version)`, `cast(CursorResult, ...)`, `return result.rowcount > 0`. Same new imports needed.
  - [x] No migration needed — `version` already exists as a non-nullable `Integer` column on all three tables (Story 3.1/3.2's migrations); this story only changes how it's read, never the schema.

- [x] Task 4: `api/recipients/routes.py` — `version` on update requests, `_version_conflict` 409 helper, wire `VersionConflict` (AC: #1, #2, #4)
  - [x] `UpdateUserRequest`, `UpdateTeamRequest`, `UpdateRecipientListRequest` each gain a required `version: int` field (no default — a client that omits it gets a `422` from Pydantic, not a silently-skipped check; this is the point of AC #1, not an oversight to soften later).
  - [x] Import `VersionConflict` from `domain.recipients` alongside the other exception imports.
  - [x] New helper, same style as `_mobile_taken`/`_team_name_taken` but taking the current record to embed:
    ```python
    def _version_conflict(current: BaseModel) -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "version_conflict",
                "message": "This record was changed by someone else since you loaded it. Review the current version before saving.",
                "details": {"current": current.model_dump(mode="json")},
            },
        )
    ```
    `mode="json"` is load-bearing, not decorative: FastAPI's `HTTPException` handler wraps `detail` in a plain Starlette `JSONResponse`, which calls raw `json.dumps` — it does **not** run `jsonable_encoder` the way a normal `response_model` return value does. A `UUID`/`datetime` left un-converted here throws inside the error handler itself. `.model_dump(mode="json")` pre-converts everything to JSON-safe primitives (every other error `detail=` in this file already avoids the problem by only ever passing plain strs — this is the first one embedding a whole record, so it's the first one that needs this).
  - [x] `update_user` route: pass `expected_version=body.version` into `service.update_user(...)`; add `except VersionConflict:` (order among the except clauses doesn't matter — each is a distinct exception type):
    ```python
    except VersionConflict:
        await session.commit()
        current = await users.get_by_id(user_id)
        team_names = await _team_name_map(teams)
        active_consent = await consents.get_active(user_id)
        raise _version_conflict(
            _to_directory_user_response(current, team_names, active_consent)
        ) from None
    ```
    No `current is None` guard — `User` is soft-deleted, never hard-deleted (AD-4), so the row this route just found by `user_id` is guaranteed to still exist.
  - [x] `update_team` route: pass `expected_version=body.version`; add:
    ```python
    except VersionConflict:
        await session.commit()
        current = await teams.get_by_id(team_id)
        raise _version_conflict(_to_team_response(current)) from None
    ```
  - [x] `update_recipient_list` route: pass `expected_version=body.version`; add:
    ```python
    except VersionConflict:
        await session.commit()
        current = await recipient_lists.get_by_id(recipient_list_id)
        raise _version_conflict(_to_recipient_list_response(current)) from None
    ```
  - [x] `remove_user`/`remove_team`/`remove_recipient_list` and every `create_*` route are **not** touched — see Dev Notes for why removal is deliberately out of this story's scope.

- [x] Task 5: `web/src/components/ConflictDialog.tsx` (new) — shared conflict UI (AC: #2)
  - [x] New component, same "one shared component, parameterized" precedent as `ConfirmationDialog` (used identically by all three edit dialogs below):
    ```typescript
    export interface ConflictField {
      label: string
      mine: string
      theirs: string
    }

    interface ConflictDialogProps {
      open: boolean
      entityLabel: string
      fields: ConflictField[]
      submitting?: boolean
      onKeepMine: () => void
      onDiscardMine: () => void
    }
    ```
  - [x] Title: "Conflicting Changes". Body copy: `` `This ${entityLabel} was changed by someone else since you opened it. Review both versions, then choose whether to keep your changes or discard them.` `` — names the real situation, no generic "Are you sure?" (mirrors `ConfirmationDialog`'s existing copy discipline, UX-DR25-style even though this isn't literally the Confirmation dialog pattern).
  - [x] Render each `fields` entry as a labeled two-line comparison: `Yours: {mine}` / `Current: {theirs}` (muted color on the second line) — `Stack`/`Typography`, matching this codebase's existing dialog layout style (no MUI `Table` used anywhere else in these dialogs).
  - [x] Two actions, no third "Cancel": `Button onClick={onDiscardMine}` (plain) and `Button onClick={onKeepMine} variant="contained"` (primary — this isn't a `button-danger` case per DESIGN.md, which reserves that token for delete/deactivate/opt-out actions specifically; overwriting a stale value with an explicit, informed choice isn't in that category).
  - [x] **Deliberately no `onClose` prop wired to the MUI `Dialog`** — omitting it means backdrop-click/Escape do nothing while this dialog is open, forcing one of the two explicit buttons. This is the concrete mechanism behind AC #2's "requires an explicit choice — never a silent overwrite": a silent dismiss would otherwise leave the conflict state ambiguous (did they mean discard? keep editing?).
  - [x] New test file `web/src/components/ConflictDialog.test.tsx`, same harness shape as `ConfirmationDialog.test.tsx` (a `Harness` wrapper with a trigger button, `renderWithTheme`): renders both `mine`/`theirs` values for every field; clicking "Discard My Changes" calls `onDiscardMine`; clicking "Keep My Changes" calls `onKeepMine`; both buttons disabled when `submitting`.

- [x] Task 6: Wire `ConflictDialog` into `UserFormDialog.tsx`, `TeamFormDialog.tsx`, `RecipientListFormDialog.tsx` (AC: #1, #2)
  - [x] All three `*FormValues` interfaces (`UserFormValues`, `TeamFormValues`, `RecipientListFormValues`) gain a required `version: number` field.
  - [x] All three dialogs gain local `const [version, setVersion] = useState(1)`, reset in the existing open-effect the same way `name`/`mobile`/etc. already are (`setVersion(x?.version ?? 1)`).
  - [x] All three dialogs gain `const [conflict, setConflict] = useState<ConflictCurrent | null>(null)` where `ConflictCurrent` is a small local type matching what that entity's `details.current` actually contains (User: `{name, mobile, team_id, team_name, version}`; Team: `{name, version}`; RecipientList: `{name, kind, member_user_ids, version}` — a subset of the full response, only the fields the dialog displays/needs).
  - [x] Refactor each dialog's `handleSubmit` body into a `performSave(versionToSend: number)` async function so both the form's normal Save button and the conflict dialog's "Keep My Changes" action can call it. `performSave` sends `version: versionToSend` in the PATCH body (create/`POST` bodies are unaffected — no version to send yet). On a `409` with `body.error.code === 'version_conflict'`, set `conflict` from `body.error.details.current` and `return` (don't fall through to the generic `error` Alert path — the conflict gets its own dialog, not an inline message).
  - [x] `handleSubmit` (the form's `onSubmit`) becomes `await performSave(version)`.
  - [x] "Keep My Changes" handler: `performSave(conflict.version)` (retries with the now-current version — an explicit, informed overwrite, not automatic) then clears `conflict` on success (handled naturally: a successful `performSave` calls `onSaved()`, which the parent uses to close the dialog and reload — no separate cleanup needed since the whole dialog unmounts/resets on next open).
  - [x] "Discard My Changes" handler: copies every field from `conflict` back into the form's local state (`setName(conflict.name)`, etc.) **and** `setVersion(conflict.version)`, then `setConflict(null)` — the edit dialog itself stays open so the Administrator can review the now-current values (and re-edit/re-save if they still want to) instead of being kicked back to the table.
  - [x] `UserFormDialog` computes its `fields` for `ConflictDialog` as `[{label: 'Name', mine: name, theirs: conflict.name}, {label: 'Mobile', mine: mobile, theirs: conflict.mobile}, {label: 'Team', mine: <lookup teamId in the `teams` prop>, theirs: conflict.team_name ?? '—'}]`.
  - [x] `TeamFormDialog` computes `[{label: 'Name', mine: name, theirs: conflict.name}]`.
  - [x] `RecipientListFormDialog` computes `[{label: 'Name', mine: name, theirs: conflict.name}, {label: 'Kind', mine: <Title Case of local kind>, theirs: <Title Case of conflict.kind>}, {label: 'Members', mine: String(memberUserIds.length), theirs: String(conflict.member_user_ids.length)}]` — member lists are compared by count, matching how `RecipientListsPanel`'s own table column already summarizes membership (`row.member_user_ids.length`), not by rendering raw UUIDs.
  - [x] Render `<ConflictDialog open={conflict !== null} .../>` as a third stacked element alongside the existing edit `<Dialog>` (and, in `UserFormDialog`'s case, the existing revoke-consent `<ConfirmationDialog>`) — this codebase already stacks a second `Dialog` on top of the edit form for consent revocation (Story 3.3), so this isn't a new pattern being introduced.

- [x] Task 7: Thread `version` from the table row into each edit dialog's initial values (AC: #1)
  - [x] `web/src/pages/RecipientsPage.tsx` — the `Edit` button's `setEditingUser({...})` call and `setEditingTeam({...})` call both gain `version: row.version` (the `DirectoryUser`/`DirectoryTeam` interfaces already carry `version: number` from Story 3.1 — nothing to add there).
  - [x] `web/src/pages/RecipientListsPanel.tsx` — the `Edit` button's `setEditing({...})` call gains `version: row.version` (`RecipientListRow` already carries `version: number`).

- [x] Task 8: Tests (AC: all)
  - [x] `tests/domain/test_recipients_service.py`:
    - Every existing call to `service.update_user(...)`, `service.update_team(...)`, `service.update_recipient_list(...)` must add `expected_version=<the fixture's current version>` (every fixture in this file is freshly constructed with `version=1` by default, so `expected_version=1` for every existing test that isn't specifically testing the conflict path) — this is a required-parameter addition, every existing update-path test in this file breaks without it.
    - `FakeUserRepository.update_directory_fields`, `FakeTeamRepository.update_name`, `FakeRecipientListRepository.update_details` each gain `expected_version: int` and now return `bool`: compare against the stored entity's `.version`; on match, apply the field mutation **and increment `.version`**, return `True`; on mismatch, leave the stored entity untouched, return `False` — mirrors the real repositories' atomic-conditional-update contract closely enough for the domain-layer tests to exercise the real branching.
    - Also add an optional `simulate_update_race: bool = False` constructor flag to each Fake repository: when `True`, the corresponding `update_*` method always returns `False` without mutating state, regardless of whether the passed version matches. This is the only way to unit-test AC #3's atomic-backstop path in isolation from the pre-check — a test that constructs `FakeUserRepository([target], simulate_update_race=True)` and calls `update_user(..., expected_version=target.version, ...)` (the *correct* current version, so the pre-check passes) must still observe `VersionConflict` raised and `audit_log.entries == []`.
    - New tests: `test_update_user_with_a_stale_version_raises_version_conflict` (pre-check path: `expected_version` one less than `target.version`, assert `VersionConflict`, `users.updated == []`, `audit_log.entries == []`); the `simulate_update_race`-backed backstop-path test described above; identical pairs for `TeamDirectoryService.update_team` and `RecipientListDirectoryService.update_recipient_list` (six new tests total, two per entity).
  - [x] `tests/adapters/persistence/test_user_repository.py`, `test_team_repository.py`, `test_recipient_list_repository.py` — extend each with: `update_directory_fields`/`update_name`/`update_details` returns `True` and increments `version` in the DB when `expected_version` matches; returns `False` and leaves every column (including `version`) unchanged when `expected_version` is stale; calling it twice in a row with the *same* (now-stale after the first call) `expected_version` — the second call returns `False` — direct proof of the atomic backstop, exercised against the real database, mirroring `test_opt_in_consent_repository.py`'s existing `revoke_active`-called-twice test (Story 3.3).
  - [x] `tests/api/test_recipients_routes.py`:
    - Every existing `client.patch("/users/{id}", ...)`, `client.patch("/teams/{id}", ...)`, `client.patch("/recipient-lists/{id}", ...)` call in this file must add `"version": 1` to its JSON body (every one of these PATCHes a freshly-`POST`ed resource, which is always at `version == 1`) — nine existing call sites break without this.
    - New tests, one per entity: create → update once (version becomes 2) → update again reusing the original stale `"version": 1` → `409`, `error.code == "version_conflict"`, `error.details.current.version == 2`, and `error.details.current`'s other fields reflect the *first* update's values (not the original pre-update or the second, rejected attempt's values).
    - New test per entity: PATCH with `version` omitted from the JSON body → `422`, proving it's a required field, not a quietly-optional one (Pydantic's own validation, same as the existing `test_create_user_with_administrator_role_is_rejected_by_request_validation` precedent for asserting on request-shape rejection).
  - [x] `web/src/pages/UserFormDialog.test.tsx`, `TeamFormDialog.test.tsx`, `RecipientListFormDialog.test.tsx`:
    - Every existing test's `user`/`team`/`recipientList` prop fixture gains `version: 1`, and every existing assertion on the PATCH request body (`expect.objectContaining({..., body: JSON.stringify({...})})`) gains `version: 1` in the expected JSON — every existing edit-path test in these three files breaks without this.
    - New tests per dialog: a `409 version_conflict` response (mock `fetch` returning `{error: {code: 'version_conflict', message: '...', details: {current: {...}}}}`) opens `ConflictDialog` showing the mocked `current` values instead of the plain inline `Alert`; clicking "Discard My Changes" repopulates the form fields from `current` and closes `ConflictDialog` (edit dialog stays open — assert the edit `Dialog`'s title/fields are still present); clicking "Keep My Changes" re-`PATCH`es with `version` equal to the conflict's `current.version` and, on a subsequent `200`, calls `onSaved`.
  - [x] `web/src/pages/RecipientsPage.test.tsx`, `RecipientListsPanel.test.tsx` — extend the existing "editing a row seeds the dialog" test(s) to assert the seeded `version` matches the mocked row's `version` field (fixture rows in these test files need a `version` value if they don't already carry one).
  - [x] `uv run pytest -q`, `uv run ruff check .`, `uv run mypy .`, `uv run lint-imports` after backend changes; `npx tsc -b`, `npx eslint .`, `npx vitest run` after frontend changes — same gate every prior story ran clean against.

### Review Findings

- [x] [Review][Patch] Members conflict field compares list length only, not actual membership — The `Members` row in `ConflictDialog` shows `Yours: <count>` vs `Current: <count>`. If someone else swapped a list's members to a different, same-size set, this reads as "no conflict" and "Keep My Changes" silently discards the other party's entire membership change with zero warning. Resolved: show a named added/removed list — resolve ids to names via the existing `options` prop (e.g. "Added: Jane Doe · Removed: John Smith") alongside the counts. [web/src/pages/RecipientListFormDialog.tsx:170-174] — Fixed.

- [x] [Review][Patch] Errors during a "Keep My Changes"/"Discard" retry are invisible to the user [web/src/pages/RecipientListFormDialog.tsx:92-100, web/src/pages/TeamFormDialog.tsx:61-69, web/src/pages/UserFormDialog.tsx:189-200] — When `performSave`'s retry (triggered from `handleKeepMine`) fails with anything other than `version_conflict`, `setError(...)` runs but `conflict` state is never cleared, so `ConflictDialog` (which has no `onClose`) stays open on top of the underlying edit `Dialog`'s hidden `error` Alert. In `UserFormDialog` this can compound: a `mobile_taken` retry response also sets `mobileAvailable=false` while `conflict` stays set: if the user then clicks "Discard My Changes" not realizing an error occurred, the Save button remains disabled afterward with no visible explanation. — Fixed: `conflict` is now cleared before falling through to `setError(...)` in all three dialogs.
- [x] [Review][Patch] `version` request field has no numeric bound [api/recipients/routes.py:66,98,118] — `UpdateUserRequest`/`UpdateTeamRequest`/`UpdateRecipientListRequest`'s `version: int` accepts values outside the `Integer` DB column's int4 range, crashing the update with an unhandled 500 instead of a clean 422. — Fixed: `version: int = Field(ge=1)`.
- [x] [Review][Patch] `assert current is not None` after the post-commit re-fetch is stripped under `-O`/`PYTHONOPTIMIZE` [api/recipients/routes.py:443,616,746] — Currently harmless since these entities are only ever soft-deleted (never hard-deleted), but relying on `assert` for a guarded invariant in production request-handling code is fragile; replace with an explicit `None` check. — Fixed: replaced with `if current is None: raise _not_found(...)`.
- [x] [Review][Patch] User-repository "called twice" test doesn't assert `final.version` [tests/adapters/persistence/test_user_repository.py:289-313] — Unlike its Team/RecipientList siblings, `test_update_directory_fields_called_twice_with_the_same_version_second_call_returns_false` never asserts the resulting `version`, leaving it unable to catch a bug where the failed second call still increments the version counter. — Fixed.
- [x] [Review][Patch] `RecipientListFormDialog.tsx` JSX not re-indented after the Fragment wrap [web/src/pages/RecipientListFormDialog.tsx:130-183] — Unlike `UserFormDialog.tsx`/`TeamFormDialog.tsx`, which both re-indent one level deeper after wrapping in `<>...</>`, this file's `<Dialog>`/`<ConflictDialog>` stayed at the outer indentation. Cosmetic only. — Fixed.

- [x] [Review][Defer] Client-side "Keep My Changes" never updates local `version` state after a successful retry [web/src/pages/RecipientListFormDialog.tsx, web/src/pages/TeamFormDialog.tsx, web/src/pages/UserFormDialog.tsx `handleKeepMine`] — deferred, pre-existing pattern; currently masked because every caller closes the dialog on `onSaved` — Quick reason: latent trap only if a future caller keeps the dialog open after save; no current caller does.
- [x] [Review][Defer] Deactivate races the edit-version-check with no active-status guard, and `ConflictDialog` never surfaces `status` [domain/recipients.py `update_user`/`update_team`/`update_recipient_list`] — deferred, pre-existing — Quick reason: same root cause as the "edit-while-inactive" gap already tracked in deferred-work.md#Deferred from: code review of 3-2-manage-recipient-groups-channels; this story's own Dev Notes explicitly scope removal as unguarded by design.
- [x] [Review][Defer] `RecipientListFormDialog`'s `handleDiscardMine` doesn't reset `kind` on discard [web/src/pages/RecipientListFormDialog.tsx:120-126] — deferred, pre-existing — Quick reason: currently unreachable since no UI exposes kind-editing on an existing list; would only matter if a future feature adds one.

### Dev Notes

- **This story closes a gap Story 3.1's own code review explicitly deferred to it.** [deferred-work.md#Deferred from: code review of 3-1-manage-users-sales-teams] — *"Optimistic-concurrency `version` column has no stale-write rejection on any update path ... Story 3.4 (Concurrent-Edit Conflict Detection) owns stale-write rejection; `version` is kept incrementing correctly so that story has real data to work against."* The `version` column, its increment-on-every-write behavior, and its presence in every response body (`DirectoryUserResponse.version`, `TeamResponse.version`, `RecipientListResponse.version`) already exist and are already correct — Stories 3.1/3.2/3.3 built the plumbing on purpose. This story's job is exclusively the *rejection* half: reading `version` back from the client and enforcing it, nowhere else.
- **Two-layer enforcement, not one.** A domain-layer pre-check (`target.version != expected_version`) alone is a read-then-write race — see AC #3. The atomic `UPDATE ... WHERE id = ? AND version = ?` in the repository is the real backstop; the pre-check exists only so the common (non-racing) case gets a cheap, early rejection before other validation runs. This is the same "advisory pre-check, DB-level real backstop" shape already used three times in this codebase (`MobileTaken`, `RecipientListNameTaken`/`TeamNameTaken`, `ConsentAlreadyActive`) — the difference here is the backstop is a conditional `UPDATE`'s `rowcount`, not a unique-index `IntegrityError`, because there's no natural unique constraint to violate for "wrong version" the way there is for "duplicate name."
- **Removal (`DELETE /users/{id}`, `/teams/{id}`, `/recipient-lists/{id}`) is deliberately NOT version-checked.** The epics ACs say "save," and `EXPERIENCE.md`'s Conflict state names "editing a Recipient record that someone else just changed" specifically — both frame this as an edit-form problem. A remove/deactivate call doesn't overwrite any field a concurrent edit might have touched (it only flips `status` and bumps `version`), so the harm this story exists to prevent — silently clobbering someone else's field-level edit — doesn't apply to it. A stale-version *edit* immediately following a concurrent *remove* is still caught: the remove already bumped `version`, so the edit's own version check (AC #1) rejects it as a conflict, same as any other concurrent edit. Do not add a `version` param to any of the three `DELETE` routes or `remove_*` domain methods — out of scope, not requested by any AC.
- **This story does not touch the separate, pre-existing "edit-while-inactive" gap.** [deferred-work.md#Deferred from: code review of 3-2-manage-recipient-groups-channels] flags that `PATCH` on an already-soft-deleted `User`/`Team`/`RecipientList` silently succeeds without reactivating it — a *status* gap, unrelated to *version* conflict detection, and explicitly deferred as its own future item ("Revisit across all three directory entities together"). Don't conflate the two in this diff.
- **Response-body serialization inside `HTTPException.detail` is the one real trap here.** Every other error `detail=` in `api/recipients/routes.py` today only ever contains plain `str`/`None` values, because FastAPI's `HTTPException` handler bypasses `jsonable_encoder` and hands `detail` straight to Starlette's `JSONResponse` (`json.dumps`). This story is the first one to embed a whole record in an error body — `current.model_dump(mode="json")` is what makes that safe (converts `UUID`/`datetime` to strings up front); passing the raw Pydantic model or a hand-built dict containing raw `UUID`/`datetime` objects would 500 inside the exception handler itself, a failure mode that's easy to miss in dev (SQLite/Postgres round-trips can mask it) but explodes immediately in a real `TestClient` request.
- **Frontend `version` threading is only one-way except after a conflict.** The number a form sends back is whatever it read when the dialog opened (or, after "Discard My Changes," whatever the conflict response's `current.version` was) — never silently re-fetched or auto-incremented client-side. If that were auto-incremented, a client could "self-heal" past a real conflict without the Administrator ever seeing the other Administrator's change, defeating AC #2.
- **`ConflictDialog` intentionally has no `onClose`.** MUI's `Dialog` treats a missing `onClose` as "backdrop click / Escape do nothing" — the dialog only closes via one of its own two action buttons. This is what makes AC #2's "requires an explicit choice" literal rather than aspirational.

### Project Structure Notes

- New files: `web/src/components/ConflictDialog.tsx`, `web/src/components/ConflictDialog.test.tsx`.
- Modified backend files: `domain/recipients.py` (`VersionConflict`, `expected_version` param + gating on all three `update_*` methods), `ports/users.py`/`ports/teams.py`/`ports/recipient_lists.py` (signature changes only, no new methods), `adapters/persistence/users.py`/`teams.py`/`recipient_lists.py` (atomic conditional updates), `api/recipients/routes.py` (`version` on the three `Update*Request` models, `_version_conflict` helper, `VersionConflict` wiring in the three `PATCH` routes), `tests/domain/test_recipients_service.py`, `tests/adapters/persistence/test_user_repository.py`/`test_team_repository.py`/`test_recipient_list_repository.py`, `tests/api/test_recipients_routes.py`.
- Modified frontend files: `web/src/pages/UserFormDialog.tsx`, `TeamFormDialog.tsx`, `RecipientListFormDialog.tsx` (all three: `version` field, `performSave` refactor, `ConflictDialog` wiring), `web/src/pages/RecipientsPage.tsx` (`version` threaded into `setEditingUser`/`setEditingTeam`), `web/src/pages/RecipientListsPanel.tsx` (`version` threaded into `setEditing`), and the corresponding `*.test.tsx` files for all of the above.
- No new Alembic migration — `version` columns and their increment-on-write behavior already exist (Story 3.1/3.2). No changes to `docker/nginx/nginx.conf`, `web/vite.config.ts`, `api/main.py`, `domain/administrators.py`, `adapters/persistence/consent.py`, or any `remove_*`/`DELETE` code path.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 3.4: Concurrent-Edit Conflict Detection] (both literal ACs)
- [Source: ARCHITECTURE-SPINE.md#Consistency Conventions] ("`User`/`Team`/`RecipientList` carry an optimistic-concurrency version column; a stale-version write is rejected as a conflict, not silently overwritten — the backing rule for EXPERIENCE.md's Conflict dialog.") — the authoritative source of this story's entire scope; there is no dedicated Architecture Decision (AD-#) for it, only this Consistency Conventions row.
- [Source: ux-designs/ux-GrowthTrack-2026-07-14/EXPERIENCE.md#State Patterns] ("Conflict — editing a Recipient record that someone else just changed surfaces a conflict dialog showing both versions; it never silently overwrites.")
- [Source: _bmad-output/implementation-artifacts/deferred-work.md#Deferred from: code review of 3-1-manage-users-sales-teams] (explicit hand-off: "`version` is kept incrementing correctly so that story has real data to work against" — confirms this story is purely additive on top of already-correct plumbing)
- [Source: _bmad-output/implementation-artifacts/deferred-work.md#Deferred from: code review of 3-2-manage-recipient-groups-channels] (the separate, NOT-this-story's-scope "edit-while-inactive" gap)
- [Source: adapters/persistence/consent.py#SqlAlchemyOptInConsentRepository.revoke_active] (the exact `cast(CursorResult, ...) / rowcount > 0` pattern this story's three repository methods copy)
- [Source: domain/recipients.py, api/recipients/routes.py] (existing `update_user`/`update_team`/`update_recipient_list` methods and their `PATCH` routes — this story's sole modification target, no new methods/routes added)
- [Source: web/src/components/ConfirmationDialog.tsx, ConfirmationDialog.test.tsx] (the shared-dialog-component precedent `ConflictDialog` follows; the `renderWithTheme` test-harness convention)
- [Source: web/src/pages/UserFormDialog.tsx] (the existing stacked-`Dialog`-for-a-secondary-action precedent — revoke-consent's `ConfirmationDialog` already renders alongside the edit `Dialog`, Story 3.3)
- [Source: _bmad-output/implementation-artifacts/3-3-recipient-opt-in-consent-capture.md] (the most recent precedent for: `Fake*Repository` boolean-return conventions, the "advisory pre-check + atomic backstop" shape, and the `IntegrityError`-adjacent "the real backstop is at the DB layer" reasoning this story reuses for `rowcount` instead of a unique index)

### Git Intelligence

- `HEAD` is `c1d411c` ("Story 3.3: recipient opt-in consent capture"), working tree clean. No migration chain change needed for this story — no new Alembic revision.
- Commit style: one commit per logical unit of work, imperative summary line, ending with the `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>` trailer.
- Every prior story's Debug Log ran `uv run pytest -q`, `uv run ruff check .`, `uv run mypy .`, `uv run lint-imports` clean (backend) plus `npx tsc -b`, `npx eslint .`, `npx vitest run` clean (frontend) before being marked `done` — run the same seven before considering this story complete.
- This story is unusual among Epic 3's stories in that its primary risk is **breaking existing call sites**, not writing new ones: `expected_version`/`version` becoming required parameters on three domain methods, three repository methods, three Pydantic request models, and three frontend PATCH payloads means every existing test in `tests/domain/test_recipients_service.py`, `tests/api/test_recipients_routes.py`, `UserFormDialog.test.tsx`, `TeamFormDialog.test.tsx`, and `RecipientListFormDialog.test.tsx` that exercises an update path needs a mechanical but non-optional update alongside the new conflict-specific tests. Do the mechanical updates first and get the full suite green before adding new test cases — easier to tell a real regression apart from a fixture that just needs `version: 1` added.

## Dev Agent Record

### Implementation Plan

Implemented exactly per the story's prescribed shape, in task order:

1. `domain/recipients.py` — added `VersionConflict`, a pre-check (`target.version != expected_version`) immediately after each entity's existing not-found/role checks, and gated the repository call's boolean return (`if not updated: raise VersionConflict()`) as the atomic backstop. `RecipientListDirectoryService.update_recipient_list` gates `update_details` before `replace_members`, so a lost race never touches membership.
2. `ports/users.py`/`teams.py`/`recipient_lists.py` — extended the three update-method signatures with `expected_version: int`, changed return type to `bool`, documented the atomic-conditional-update contract.
3. `adapters/persistence/users.py`/`teams.py`/`recipient_lists.py` — atomic `UPDATE ... WHERE id = ? AND version = ?` statements via `cast(CursorResult, ...) / rowcount > 0`, copying `OptInConsentRepository.revoke_active`'s exact pattern (Story 3.3).
4. `api/recipients/routes.py` — `version: int` (required, no default) added to the three `Update*Request` models; `_version_conflict()` helper builds the 409 body with `current.model_dump(mode="json")` (load-bearing for `HTTPException.detail` JSON-safety); `VersionConflict` wired into all three `PATCH` routes, each re-fetching the current record post-rollback for the response body.
5. `web/src/components/ConflictDialog.tsx` (new) — shared conflict UI, no `onClose` wired to MUI `Dialog` (forces an explicit Keep/Discard choice per AC #2), same test-harness convention as `ConfirmationDialog.test.tsx`.
6. `UserFormDialog.tsx`/`TeamFormDialog.tsx`/`RecipientListFormDialog.tsx` — `version` state seeded from the record, `handleSubmit` refactored into `performSave(versionToSend)`, a 409 `version_conflict` response opens `ConflictDialog` instead of the inline `Alert`; "Keep My Changes" retries with the conflict's `current.version`; "Discard My Changes" repopulates local form state from `current` and stays open. `version` is only sent on `PATCH` bodies, never `POST` (no version to send yet on create).
7. `RecipientsPage.tsx`/`RecipientListsPanel.tsx` — `version: row.version` threaded into each Edit button's seed call.
8. Tests — every existing update-path test across `tests/domain/test_recipients_service.py`, `tests/adapters/persistence/test_*_repository.py`, `tests/api/test_recipients_routes.py`, and the three `*FormDialog.test.tsx` files updated with the new required `expected_version`/`version` parameter (mechanical pass, done first, full suite kept green throughout); new conflict-specific tests added per entity (stale-version pre-check, atomic-backstop-under-simulated-race, 409 API round-trip, 422-on-omitted-version, and the ConflictDialog Keep/Discard frontend flows).

### Debug Log

- Backend: `uv run pytest -q` → 354 passed (one transient failure on `test_me_with_tampered_token_returns_401` on a single run under heavy background load, unrelated file, reproduced green in isolation and on a clean re-run of the full suite — confirmed pre-existing flakiness, not a regression).
- `uv run ruff check .` → clean.
- `uv run mypy .` → 13 pre-existing errors remain (verified identical on `git stash` baseline before this story's changes — none introduced by this story). Two `TeamRepository` `Fake` subclasses in `tests/domain/test_dashboard_metrics_service.py` and `tests/domain/test_ingestion_service.py` needed their `update_name` stub signature bumped to match the new port interface (mechanical, `NotImplementedError` bodies unchanged). Added `assert current is not None` narrowing in the three new `VersionConflict` except-blocks in `api/recipients/routes.py` (the row is known to exist — same reasoning as the story's `update_user` "no `current is None` guard" note — but mypy needs the explicit narrowing since the concrete repositories return `T | None`).
- `uv run lint-imports` → 2 contracts kept, 0 broken.
- Frontend: `npx tsc -b` → clean. `npx eslint .` → 2 pre-existing errors in `DashboardPage.tsx`/`LoginPage.tsx` (verified identical on `git stash` baseline, unrelated files). `npx vitest run` → 138 passed (one flaky run under heavy background load with 5s default timeouts on unrelated pre-existing tests, reproduced green in isolation and on a clean full-suite re-run).

### Completion Notes

All 4 ACs satisfied: optimistic-concurrency rejection on `User`/`Team`/`RecipientList` updates (AC #1), a `ConflictDialog` requiring an explicit Keep/Discard choice with no silent-dismiss path (AC #2), a genuine two-layer defense — advisory pre-check plus an atomic `UPDATE ... WHERE version = ?` backstop proven under a simulated race (AC #3), and uniform `409 version_conflict` enforcement across all three directory entities' `PATCH` routes (AC #4). Removal/`DELETE` routes and the separate edit-while-inactive gap were deliberately left untouched, per the story's Dev Notes.

## File List

### New

- `web/src/components/ConflictDialog.tsx`
- `web/src/components/ConflictDialog.test.tsx`

### Modified — Backend

- `domain/recipients.py`
- `ports/users.py`
- `ports/teams.py`
- `ports/recipient_lists.py`
- `adapters/persistence/users.py`
- `adapters/persistence/teams.py`
- `adapters/persistence/recipient_lists.py`
- `api/recipients/routes.py`
- `tests/domain/test_recipients_service.py`
- `tests/domain/test_dashboard_metrics_service.py` (mechanical: `FakeTeamRepository.update_name` stub signature)
- `tests/domain/test_ingestion_service.py` (mechanical: `FakeTeamRepository.update_name` stub signature)
- `tests/adapters/persistence/test_user_repository.py`
- `tests/adapters/persistence/test_team_repository.py`
- `tests/adapters/persistence/test_recipient_list_repository.py`
- `tests/api/test_recipients_routes.py`

### Modified — Frontend

- `web/src/pages/UserFormDialog.tsx`
- `web/src/pages/UserFormDialog.test.tsx`
- `web/src/pages/TeamFormDialog.tsx`
- `web/src/pages/TeamFormDialog.test.tsx`
- `web/src/pages/RecipientListFormDialog.tsx`
- `web/src/pages/RecipientListFormDialog.test.tsx`
- `web/src/pages/RecipientsPage.tsx`
- `web/src/pages/RecipientsPage.test.tsx`
- `web/src/pages/RecipientListsPanel.tsx`
- `web/src/pages/RecipientListsPanel.test.tsx`

## Change Log

| Date | Change |
| --- | --- |
| 2026-07-20 | Implemented Story 3.4: optimistic-concurrency version-conflict detection on `User`/`Team`/`RecipientList` updates, two-layer (pre-check + atomic backstop) enforcement, `ConflictDialog` frontend flow, uniform 409 across all three directory PATCH routes. |
