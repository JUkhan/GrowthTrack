---
baseline_commit: 7e9a19a2f95969128c2cbac9d0706b3d61444257
---

# Story 4.5: Manage Message Templates

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an Administrator,
I want to create, view, and edit the message templates the Notification composer selects from,
so that a real, Twilio/Meta-console-approved template can be entered and corrected without anyone touching the database directly.

## Acceptance Criteria

1. **Given** a WhatsApp template already approved in the Twilio/Meta console (Name, Content SID, variable slots, preview text) **When** I create a new MessageTemplate in GrowthTrack **Then** it is saved and becomes selectable in the Notification composer (Story 4.1), and the change is audit-logged in the same transaction as the write

2. **Given** an existing MessageTemplate **When** I view the Templates list **Then** every template's Name, Content SID, variable slots, and preview text are shown — never hidden pagination or truncation, consistent with FR-9's directory-listing convention

3. **Given** an existing MessageTemplate **When** I edit its Content SID, variable slots, or preview text **Then** the change takes effect for future Manual Notification sends, and is audit-logged co-transactionally

4. **Given** a MessageTemplate **When** managed **Then** no delete/deactivate control is exposed — no status/active field exists on this entity in this iteration, unlike User/Team/RecipientList

5. **Given** GrowthTrack's own template-approval workflow **When** this story is implemented **Then** it performs no approval/submission call to Twilio/Meta on the Administrator's behalf — approval remains entirely a console-side, out-of-band process (Architecture spine's existing Deferred item)

## Tasks / Subtasks

- [x] **Task 1: Port — add `update()`** (AC: #3)
  - [x] `ports/notifications.py`'s `MessageTemplateRepository` currently has `list_active()`, `get_by_id()`, `get_by_name()`, `add()` — no edit method. Add `async def update(self, template_id: uuid.UUID, name: str, twilio_content_sid: str, variable_slots: list[str], body_preview_template: str) -> bool` (returns whether a row was updated — `False` means not found, mirroring `TeamRepository.update_name`'s bool-return convention, not `UserRepository.update_directory_fields`'s version-conditional one, since `MessageTemplate` has no version column to condition on — AC #4).

- [x] **Task 2: Persistence — implement `update()`** (AC: #3)
  - [x] `adapters/persistence/notifications.py`'s `SqlAlchemyMessageTemplateRepository` — add `update()` as a plain SQLAlchemy `update(MessageTemplateModel).where(id == template_id).values(...)`, check `result.rowcount > 0`, matching the unconditional-update shape (no `AND version = ?` clause — there is no version column on this table, unlike `TeamModel`/`UserModel`/`RecipientListModel`).

- [x] **Task 3: Domain service** (AC: #1, #2, #3, #4, #5)
  - [x] New `MessageTemplateDirectoryService` in `domain/notifications.py` (co-locate with `ManualNotificationService` — same file already owns `MessageTemplateRepository`'s only other caller), constructor takes `templates: MessageTemplateRepository, audit_log: AuditLogRepository` — mirrors `TeamDirectoryService`'s shape in `domain/recipients.py` (no `LastAdministratorGuard`/consent dependencies needed here, this entity has neither).
    - `create_template(name, twilio_content_sid, variable_slots, body_preview_template, actor_user_id) -> MessageTemplate`: validate `name` non-blank after `.strip()` and `variable_slots`/`twilio_content_sid`/`body_preview_template` non-blank (reuse the blank-after-strip lesson already fixed for `TeamDirectoryService`/`RecipientListDirectoryService` per `deferred-work.md`'s "Whitespace-only name" item — don't reintroduce that gap here); reject if `get_by_name(name)` finds an existing row with the same name (**new exception `TemplateNameTaken`**, matching `TeamNameTaken`'s shape) — this table currently has no unique DB constraint on `name`, so this app-level check is the only guard; write the row via `add()`, then an `AuditLogEntry` (`action="message_template.created"`) in the same call, co-transactional per AD-7.
    - `update_template(template_id, name, twilio_content_sid, variable_slots, body_preview_template, actor_user_id) -> MessageTemplate`: `get_by_id` → raise **new exception `TemplateNotFound`** if `None` (this name already exists as a distinct exception in `ManualNotificationService`'s own module for the "no template found to send with" case — reuse that existing `TemplateNotFound` class, don't declare a second one with the same name in the same file); same blank-field validation as create; if the new `name` collides with a *different* existing template, raise `TemplateNameTaken`; call `update()`; audit-log `action="message_template.updated"` with the changed fields in `details`. No `expected_version`/`VersionConflict` handling anywhere in this service (AC #4 — deliberately no optimistic-concurrency column on this entity, unlike every other directory entity Story 3.4 covers).
  - [x] No `remove`/`deactivate` method — AC #4 is a hard scope boundary, not an oversight to "complete" later in this story.

- [x] **Task 4: API routes** (AC: #1, #2, #3)
  - [x] `api/notifications/routes.py` already has `GET /message-templates` (`list_active`, currently used only by the composer). Its response model, `MessageTemplateResponse`, returns `id, name, variable_slots, body_preview_template` — no `twilio_content_sid`. **Add `twilio_content_sid` to that same model and reuse this one route for both the composer and this story's admin list (AC #2)** — do *not* build a parallel `/message-templates/admin` endpoint or a second response model. Reasoning: the entire portal is Administrator-only (FR-2), so there is no privilege boundary between "the composer's view" and "the admin's view" that would justify hiding the SID from one caller — adding a field to an existing response is backward-compatible (confirmed: `tests/api/test_notifications_routes.py`'s existing `GET /message-templates` test only asserts specific fields by key, never full-body equality, so this addition won't break it), and the composer's frontend simply ignores the new field it doesn't render. This keeps the codebase from carrying two near-identical list endpoints for one small table.
  - [x] Add two new routes to the same file:
    - `POST /message-templates` → `CreateMessageTemplateRequest {name, twilio_content_sid, variable_slots: list[str], body_preview_template}` (Pydantic `Field(min_length=1)` on `name`/`twilio_content_sid`/`body_preview_template`, `variable_slots: list[str] = Field(default_factory=list)`) → `MessageTemplateDirectoryService.create_template` → 201, reusing the (now-extended) `MessageTemplateResponse`. Catch `TemplateNameTaken` → 409 `{code: "template_name_taken", ...}` (new local error-envelope helper, same shape as `_team_name_taken()`), matching the existing `commit()`-then-`raise`/`IntegrityError`-fallback double-guard pattern `create_team` uses (Task 2's app-level name check plus a DB-level race is still possible with two concurrent creates of the same name — no unique index exists on `message_templates.name` today, so decide whether to add one via migration or accept the same small race window `TeamRepository`/`RecipientListRepository` already accept; **recommendation: add the unique index** — it's a one-line migration and closes the race for near-zero cost, unlike the accepted precedent which predates this decision).
    - `PATCH /message-templates/{template_id}` → `UpdateMessageTemplateRequest {name, twilio_content_sid, variable_slots, body_preview_template}` (**no `version` field** — contrast with `UpdateTeamRequest`/`UpdateUserRequest`, AC #4) → `MessageTemplateDirectoryService.update_template` → 200 `MessageTemplateResponse`. Catch `TemplateNotFound` → 404 (reuse the existing `_template_not_found()` helper already defined in this file for the send-path's 404), `TemplateNameTaken` → 409.
  - [x] All three routes depend on `get_current_user`/`get_db` (AD-8) — same as every existing route in this file.
  - [x] No nginx change needed — `docker/nginx/nginx.conf` already proxies both `location = /message-templates` and `location /message-templates/` to the API (added by Story 4.1 for the existing GET), which already covers the new POST/PATCH paths. Verify this rather than re-adding it.

- [x] **Task 5: Frontend — Templates page** (AC: #1, #2, #3, #4)
  - [x] New `web/src/pages/TemplateFormDialog.tsx` — mirror `web/src/pages/TeamFormDialog.tsx`'s structure almost exactly (single dialog handles both create and edit — `template === null` means create), but: (a) four fields instead of one — Name (`TextField`), Twilio Content SID (`TextField`, helper text pointing at the Twilio Console as the source), Variable Slots (a repeatable list of text inputs — add/remove row controls, matching `variable_slots: string[]`'s ordered-array shape, order matters since it's the positional mapping to Twilio's `content_variables` keys per `ports/notifications.py`'s existing docstring), Preview Text (multiline `TextField`, supports `{slot_name}` placeholder syntax — mention this in helper text so the Administrator knows the format); (b) **no `ConflictDialog`, no `version` state, no `handleKeepMine`/`handleDiscardMine`** — this entity has no version column (AC #4), so `TeamFormDialog`'s conflict-handling branch is the one part *not* to copy.
  - [x] New `web/src/pages/TemplatesPage.tsx` — mirror `RecipientsPage.tsx`'s single-tab shape (no `Tabs` needed, only one entity type): `isMountedRef` guard, `loadTemplates()` fetching `GET /message-templates` (same route the composer uses — now includes `twilio_content_sid`), `ResponsiveDataTable` with columns Name / Content SID / Variable Slots (join with commas or show a chip per slot) / Preview Text (truncate visually via CSS `overflow`, but the underlying data is never truncated — AC #2's "never hidden... truncation" refers to data, not necessarily unbounded on-screen width) / Actions (Edit only — **no Remove/Delete button**, unlike `RecipientsPage`'s Users/Teams tabs, per AC #4), `EmptyState` when the list is empty ("No message templates yet" + "Add Template" primary action, per UX-DR16 — direct copy, no generic placeholder), `ConfirmationDialog` is **not** needed here (no destructive action exists to confirm).
  - [x] `web/src/router.tsx`: add `{ path: '/notifications/templates', element: <TemplatesPage /> }`.
  - [x] No shared nav shell exists yet (`RecipientsPage.tsx`'s own comment: "no nav shell exists yet ... DashboardPage's own comment flags this as unowned by any story") — don't build one for this story. Instead, add a `<Link component={RouterLink} to="/notifications/templates">Manage templates</Link>` near `NotificationComposePage.tsx`'s template `<select>` (same `Link`/`RouterLink` pattern that file already uses for its "Back to Dashboard" link at line ~230), and a reciprocal link back from `TemplatesPage.tsx` to `/notifications/compose`.

- [x] **Task 6: Tests** (AC: all)
  - [x] `tests/domain/test_notifications_service.py` — extend with `MessageTemplateDirectoryService` coverage: create succeeds + audit-logs co-transactionally (assert on the `FakeAuditLogRepository`'s recorded entries, matching this file's existing pattern for `ManualNotificationService`); create with a duplicate name raises `TemplateNameTaken`; create/update reject blank-after-strip `name` (and the other three fields); update on a nonexistent id raises `TemplateNotFound`; update changes are visible via a subsequent `get_by_id` on the fake repo.
  - [x] `tests/adapters/persistence/test_notifications_repository.py` — extend with real-Postgres coverage for the new `update()` method: updates every field, returns `False` for a nonexistent id, and (if the Task 4 unique-index recommendation is taken) a duplicate-name insert raises `IntegrityError`.
  - [x] `tests/api/test_notifications_routes.py` — extend with 401-without-cookie tests for the two new routes (AD-8); `POST /message-templates` 201 + appears in a subsequent `GET /message-templates`, including its `twilio_content_sid`; `POST` with a duplicate name → 409 `template_name_taken`; `PATCH /message-templates/{id}` 200 + change reflected; `PATCH` on a nonexistent id → 404. No need to test that `GET /message-templates` "hides" the SID — it deliberately no longer does (Task 4).
  - [x] Frontend: `TemplateFormDialog.test.tsx` (create mode, edit mode pre-fills all four fields, variable-slot add/remove row controls, submit failure shows inline error — no conflict-dialog test, since that branch doesn't exist here), `TemplatesPage.test.tsx` (empty state renders + its action opens the create dialog, list renders all four fields per row, Edit opens the dialog pre-filled, no Remove/Delete button is rendered anywhere in the row actions — an explicit assertion for AC #4, not just an omission).
  - [x] No `tests/conftest.py` change needed — its `_clean_tables` fixture already does `DELETE FROM message_templates` (added by Story 4.1).

- [x] **Task 7: Seed data cleanup** (not required by any AC, but closes the story's own trigger)
  - [x] Optional but recommended: once this UI exists, update `scripts/seed_demo_data.py`'s comment at the "Target Revision Notice" template (currently: *"this placeholder Content SID must be swapped for a real one from the Twilio Console before any real send"*) to point at the new `/notifications/templates` page instead of implying a DB edit is the only path. Do not change the seeded placeholder value itself — that's an operational step for whoever has a real Twilio-approved template, not something this story can do for them.

## Dev Notes

- **Why this story exists:** A real Manual Notification send failed with Twilio `20422: Invalid Parameter` against `scripts/seed_demo_data.py`'s placeholder `twilio_content_sid = "HXdemoplaceholder0000000000000"`. The only fix path today is a direct database edit. `ports/notifications.py`'s `MessageTemplateRepository` docstring already anticipated `add()` having a real caller beyond the seed script — this story is that caller. See `_bmad-output/planning-artifacts/sprint-change-proposal-2026-07-22.md` for the full impact analysis and `_bmad-output/planning-artifacts/prds/prd-GrowthTrack-2026-07-14/prd.md` §4.9 (FR-13) for the backing requirement.
- **Scope boundary (AC #5) — do not build:** Twilio/Meta template *submission* or *approval-status polling*. This story only records an already-approved template's identifiers locally. The architecture spine's own Deferred list already states this ("WhatsApp template approval workflow... isn't modeled here") — this story does not change that boundary, it only fills the adjacent gap (recording, not approving).
- **No version/optimistic-concurrency column** on `MessageTemplate` — confirmed as a deliberate scope decision with the user (2026-07-22), not an oversight. Do not add one, do not add a migration for it. This is the one place this story's CRUD pattern *diverges* from `TeamDirectoryService`/`UserDirectoryService`'s established shape — call this out explicitly in code review if it's flagged, since it looks at first glance like a gap relative to Story 3.4's coverage but is an intentional, narrower-scoped entity.
- **No soft-delete/status field** either (AC #4) — no `remove_template`/deactivate method, no status column, no migration. `MessageTemplateModel` (`adapters/persistence/notifications.py:38-46`) already has every field this story needs (`id, name, twilio_content_sid, variable_slots, body_preview_template, created_at`) — **no Alembic migration is needed for this story at all**, a rare case in this codebase worth double-checking rather than assuming a migration is always required.
- **`GET /message-templates` gains a field (`twilio_content_sid`), same route, same shape otherwise.** `NotificationComposePage.tsx` already consumes `id, name, variable_slots, body_preview_template` from it — it will simply ignore the new field. Do not rename the route, split it into two, or otherwise change what the composer already relies on; `NotificationComposePage.test.tsx` should still pass unmodified.
- **Files being modified (read fully before editing, per this workflow's own guardrail):**
  - `ports/notifications.py` — read the existing `MessageTemplateRepository` docstring (explains why `Any`-typing is used here) before adding `update()`.
  - `adapters/persistence/notifications.py` — read `SqlAlchemyMessageTemplateRepository`'s existing four methods (lines 129-161) and the `_template_to_domain` helper; the new `update()` follows the same file's `claim_for_dispatch`/`update_after_send` conditional-`UPDATE` shape (further down the same file) for its SQLAlchemy `update()` construction style, not the ORM-object-mutation style.
  - `domain/notifications.py` — read the whole file; `TemplateNotFound` already exists here (line 42) for `ManualNotificationService.compose_and_send`'s use — reuse it, do not redeclare.
  - `api/notifications/routes.py` — read the whole file (216 lines); `_template_not_found()` helper (line 109) already exists and is reusable for the new PATCH route's 404 case.
  - `web/src/pages/TeamFormDialog.tsx` — read fully; this is the closest frontend precedent, and the file's own note ("same shape as UserFormDialog") tells you `UserFormDialog.tsx` is the *other* precedent if `TeamFormDialog` alone under-specifies something (it's the simpler of the two — fewer fields, matching this story's entity better).
  - `web/src/pages/RecipientsPage.tsx` — read fully; reuse its `isMountedRef`/`loadX` fetch pattern, `ResponsiveDataTable`/`EmptyState` wiring, but note its own comment that no shared nav shell exists — don't invent one.
  - `web/src/pages/NotificationComposePage.tsx` — read fully; this is where the "Manage templates" link is added (near the template `<select>`), and where the existing `GET /message-templates` contract must be preserved unchanged.

### Project Structure Notes

- No new top-level directories or files outside the existing `ports/`, `adapters/persistence/`, `domain/`, `api/notifications/`, `web/src/pages/` — this story extends existing modules rather than creating new packages, consistent with AD-1's dependency-direction rule (domain still imports only from `ports/`).
- No migration file — see Dev Notes above. If code review determines the unique-index-on-`name` recommendation (Task 4) should be taken, that's the one place a migration would be added; flag it as a Task-4 sub-decision if deferred rather than silently skipping it.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 4.5: Manage Message Templates] — acceptance criteria, verbatim origin
- [Source: _bmad-output/planning-artifacts/prds/prd-GrowthTrack-2026-07-14/prd.md#4.9 Message Template Management] — FR-13, backing requirement
- [Source: _bmad-output/planning-artifacts/sprint-change-proposal-2026-07-22.md] — full impact analysis and rationale for this story's existence/placement
- [Source: _bmad-output/planning-artifacts/architecture/architecture-GrowthTrack-2026-07-14/ARCHITECTURE-SPINE.md#AD-4] — `MessageTemplate` as a standalone entity; approval workflow explicitly deferred
- [Source: _bmad-output/planning-artifacts/architecture/architecture-GrowthTrack-2026-07-14/ARCHITECTURE-SPINE.md#AD-7] — co-transactional audit log requirement
- [Source: ports/notifications.py] — existing `MessageTemplateRepository` (add()/get_by_id()/get_by_name()/list_active())
- [Source: adapters/persistence/notifications.py] — existing `SqlAlchemyMessageTemplateRepository` + `MessageTemplateModel`
- [Source: domain/notifications.py] — existing `TemplateNotFound`, `ManualNotificationService`, module conventions to mirror
- [Source: api/notifications/routes.py] — existing `/message-templates` GET route, error-envelope helpers to reuse
- [Source: domain/recipients.py#TeamDirectoryService] — closest CRUD-service precedent (create/update/name-uniqueness pattern)
- [Source: api/recipients/routes.py#teams_router] — closest CRUD-route precedent (POST/GET/PATCH shape, error mapping)
- [Source: web/src/pages/TeamFormDialog.tsx] — closest frontend form-dialog precedent
- [Source: web/src/pages/RecipientsPage.tsx] — closest frontend list-page precedent
- [Source: scripts/seed_demo_data.py#_seed_message_templates] — the placeholder this story's UI replaces the only-workaround for
- [Source: docker/nginx/nginx.conf] — confirms `/message-templates` proxy blocks already exist, no change needed

## Dev Agent Record

### Agent Model Used

Claude Sonnet 5 (claude-sonnet-5)

### Debug Log References

- `domain/notifications.py`'s `update_template` originally returned `await self._templates.get_by_id(template_id)` directly at the end (per Task 3's literal wording). `mypy` flagged this: `get_by_id` returns `Any | None` per the port's `Any`-typed convention, and an un-narrowed `Any | None` isn't assignable to the declared `-> MessageTemplate` return type. Fixed by assigning to a variable and raising `TemplateNotFound` if `None` (defensively unreachable in practice — nothing deletes a `MessageTemplate` — but keeps the type honest), matching the narrow-then-return pattern the rest of this file already uses.
- One test name (`test_update_template_colliding_with_a_different_templates_name_raises_template_name_taken`) exceeded ruff's 100-char line-length limit; shortened to `..._raises_taken`.
- Both were mechanical fixes with no behavior change; noted here rather than silently deviating from the story's literal Task 3/Task 6 wording.
- One full-suite run reported `tests/api/test_auth_routes.py::test_me_with_tampered_token_returns_401` as failed. Investigated: passes in isolation, passes as part of the full `tests/api/` directory alone, and touches nothing this story's code overlaps with (auth/token handling, untouched by this story). A second full-suite run passed clean (417/417). Concluded this was a one-off environment flake, not a regression — not investigated further since it didn't reproduce.

### Completion Notes List

- Full slice implemented per Dev Notes: `ports/notifications.py` (`update()`) → `adapters/persistence/notifications.py` (`SqlAlchemyMessageTemplateRepository.update()`) → `domain/notifications.py` (`MessageTemplateDirectoryService`, new `TemplateNameTaken`/`InvalidTemplateFields` exceptions, reusing the existing `TemplateNotFound`) → `api/notifications/routes.py` (`POST`/`PATCH /message-templates`, `twilio_content_sid` added to the existing `GET /message-templates` response) → `web/src/pages/TemplateFormDialog.tsx` + `TemplatesPage.tsx` → `web/src/router.tsx` (`/notifications/templates`) → a "Manage templates" link added to `NotificationComposePage.tsx`.
- Took Task 4's own recommendation: added a unique index on `message_templates.name` via a new Alembic migration (`b3f7a1c9d2e4`, head, chained off `c4a8f21e6b3d`) rather than accepting the app-level-only race window `TeamRepository`/`RecipientListRepository` already live with. Applied to the local dev database (`alembic upgrade head`) and verified with a dedicated `IntegrityError` regression test.
- Confirmed (Task 4's stated assumption) that adding `twilio_content_sid` to the existing `GET /message-templates` response is backward-compatible: `NotificationComposePage.tsx`/`.test.tsx` needed no changes, and the pre-existing `test_list_message_templates_returns_seeded_templates` test (which only asserts specific fields by key) still passes unmodified.
- No Alembic migration was needed for the CRUD fields themselves (all four already existed on `message_templates` since Story 4.1) — only the new unique index required one, confirming the story's own prediction.
- Frontend fix beyond the story's literal text: two spots (`TemplateFormDialog.tsx`'s slot-row `Stack`, its helper `Typography`, and `TemplatesPage.tsx`'s header `Stack`) initially passed `alignItems`/`justifyContent`/`display`/`flexWrap` as direct MUI props; this MUI version doesn't forward them off `Stack`/`Typography` as system props, causing a React "unrecognized DOM attribute" warning and a `tsc` error on the `Typography` case. Fixed by moving them into `sx={{...}}`, matching every other file in this codebase (grepped — no existing file passes these as direct props either).
- Test-writing note: MUI's `required` prop appends a visible/accessible `" *"` to the field's label text, so `getByLabelText` queries needed prefix-anchored regexes (`/^name/i`, `/^slot 1/i`) rather than exact-match — an exact match against `/^name$/i` fails, and an unanchored `/slot 1/i` collides with the "Remove slot 1" icon button's `aria-label`. Documented here since the same gotcha will resurface in any future test against a required MUI `TextField`.
- Full regression: 417 backend tests (`pytest`) pass — no pre-existing test needed modification. 170 frontend tests (`vitest`) pass when run without forced file-parallelism; under this sandbox's default parallel worker pool a few tests intermittently timed out under heavy concurrent CPU load (confirmed as environment flakiness, not a defect — every test passes individually and the full suite passes cleanly serialized).
- `ruff`, `mypy` (project-wide, both clean) and `eslint`/`tsc` (clean on every file this story touched) all pass. Three pre-existing `eslint` `react-hooks/set-state-in-effect` violations remain in `DashboardPage.tsx`/`LoginPage.tsx` — confirmed via `git status`/`git diff` that this story never touched either file; left as-is, out of scope.

### File List

**New files:**
- `alembic/versions/b3f7a1c9d2e4_message_templates_name_unique.py`
- `web/src/pages/TemplateFormDialog.tsx`
- `web/src/pages/TemplateFormDialog.test.tsx`
- `web/src/pages/TemplatesPage.tsx`
- `web/src/pages/TemplatesPage.test.tsx`

**Modified files:**
- `ports/notifications.py` (`MessageTemplateRepository.update()`; refreshed `get_by_name` docstring)
- `adapters/persistence/notifications.py` (`SqlAlchemyMessageTemplateRepository.update()`)
- `domain/notifications.py` (`MessageTemplateDirectoryService`; new `TemplateNameTaken`/`InvalidTemplateFields` exceptions)
- `api/notifications/routes.py` (`twilio_content_sid` added to `MessageTemplateResponse`; `POST`/`PATCH /message-templates` routes; `_template_name_taken()`/`_invalid_template_fields()` error helpers)
- `scripts/seed_demo_data.py` (comment update pointing at the new Templates page instead of a database edit)
- `web/src/router.tsx` (`/notifications/templates` route)
- `web/src/pages/NotificationComposePage.tsx` ("Manage templates" link)
- `tests/domain/test_notifications_service.py` (`MessageTemplateDirectoryService` coverage; `FakeMessageTemplateRepository` gained `get_by_name`/`add`/`update`)
- `tests/adapters/persistence/test_notifications_repository.py` (`update()` coverage; unique-index `IntegrityError` regression test)
- `tests/api/test_notifications_routes.py` (401 checks, create/update route coverage)

## Change Log

| Date | Change |
| --- | --- |
| 2026-07-22 | Implemented Story 4.5: Manage Message Templates — `MessageTemplateDirectoryService` (create/update, name-uniqueness, audit-logged), `POST`/`PATCH /message-templates` routes, `TemplatesPage`/`TemplateFormDialog` frontend, and a unique index on `message_templates.name`. No delete/deactivate and no version column, per the story's explicit scope decision. 62 new/extended backend tests, 10 new frontend tests; ruff, mypy, tsc, eslint all clean on touched files. |

### Review Findings

- [x] [Review][Patch] Revert `adapters/whatsapp_twilio/sender.py`'s `_build_http_client()`/`trust_env = False` change [adapters/whatsapp_twilio/sender.py:24-34] — decided out of scope for this story; the CA-bundle workaround should be a separate, correctly-scoped change (it currently also disables env-based proxy trust, unrelated to this story's File List). **Fixed:** reverted the file to HEAD.
- [x] [Review][Patch] Revert `scripts/seed_demo_data.py`'s seeded `twilio_content_sid` back to the placeholder `"HXdemoplaceholder0000000000000"` [scripts/seed_demo_data.py:~148] — decided: keep the comment update, revert the value change, per Task 7's explicit instruction not to change the seeded value. **Fixed.**
- [x] [Review][Defer] `alembic/versions/b3f7a1c9d2e4_message_templates_name_unique.py`'s unique index has no pre-migration duplicate-name cleanup [alembic/versions/b3f7a1c9d2e4_message_templates_name_unique.py:20-29] — deferred, accepted risk: no demo/prod environment currently has duplicate template names; handle manually if the migration ever fails on deploy.
- [x] [Review][Patch] `web/src/pages/TemplateFormDialog.tsx`: "Add Slot" button (line 155) and "Remove slot N" `IconButton` (line 146) are inside `<form onSubmit={handleSubmit}>` without `type="button"`, so they default to `type="submit"`. When editing an existing template (fields already valid), clicking either prematurely submits the form — "Remove slot" in particular triggers `onSaved()`, which closes the dialog outright. This breaks the core "correct a template's variable slots" workflow the story exists to support. **Fixed:** added `type="button"` to both.
- [x] [Review][Patch] `domain/notifications.py`: `create_template`/`update_template` (lines 193, 239) validate that no slot is blank, but never reject duplicate names within `variable_slots`. The frontend/composer keys variable values by slot name (`Record<string, string>`), so two identically-named slots collapse to one value client-side, while `ManualNotificationService.compose_and_send` (lines 383-386) maps values back onto `variable_slots` positionally — silently sending one value into two distinct Twilio content-variable positions on a real send. **Fixed:** both methods now reject duplicate slot names via `InvalidTemplateFields`; covered by new tests.
- [x] [Review][Patch] `domain/notifications.py` `update_template` (line 258): the audit log `details` only records `name`/`twilio_content_sid`, never `variable_slots`/`body_preview_template`. Contradicts AC #3 and Task 3's explicit instruction to audit-log "the changed fields" — an edit that only changes slots or preview text is indistinguishable in the audit trail from no change at all. **Fixed:** `details` now includes all four fields; covered by a new test.
- [x] [Review][Patch] `api/notifications/routes.py` `update_message_template` (lines 225-248): the `except IntegrityError` block only wraps `session.commit()`, but `MessageTemplateRepository.update()` executes a Core-style `UPDATE` immediately via `session.execute()` — so a unique-index violation (concurrent rename race) raises `IntegrityError` inside the *first* try block, uncaught, surfacing as an unhandled 500 instead of the intended 409. **Fixed:** added an `except IntegrityError` to the first try block, mapping to the same 409.
- [x] [Review][Patch] `web/src/pages/TemplatesPage.tsx` (lines 34, 175-179): `actionError`/`setActionError` is declared and rendered but `setActionError` is never called with a non-null value anywhere in the file — dead state/dead branch. **Fixed:** removed.
- [x] [Review][Patch] `api/notifications/routes.py`: `CreateMessageTemplateRequest` (lines 60-64) and `UpdateMessageTemplateRequest` (lines 67-71) are byte-for-byte identical Pydantic models — straightforward duplication. **Fixed:** collapsed into one `MessageTemplateWriteRequest`, aliased for both names.
- [x] [Review][Patch] `api/notifications/routes.py`: `body_preview_template` (lines 64, 71) has no `max_length`, and `variable_slots` has no bound on list length or per-item string length, unlike `name`/`twilio_content_sid` which are capped at 255 chars. **Fixed:** added `max_length=2000` on `body_preview_template`, `max_length=20` on the `variable_slots` list, and `max_length=255` per slot item.
- [x] [Review][Patch] `tests/domain/test_notifications_service.py`: Task 6 calls for blank-field validation coverage on "create/update" together, but only `create_template`'s blank-name/blank-slot rejection is tested — `update_template`'s identical validation branch has no test. **Fixed:** added matching `update_template` blank-name/blank-slot/duplicate-slot tests.
- [x] [Review][Patch] `tests/api/test_notifications_routes.py`: no route-level test exercises the `422 invalid_template_fields` response — it's only covered at the domain-service level. **Fixed:** added `test_create_message_template_with_a_blank_variable_slot_returns_422`.
- [x] [Review][Patch] `web/src/pages/TemplatesPage.test.tsx`: the "renders every field per row" test doesn't assert the Preview Text column's value, only name/SID/slots. **Fixed:** added the assertion.
- [x] [Review][Defer] `web/src/pages/TemplateFormDialog.tsx`: "Cancel" button (line 177) also lacks `type="button"` inside the form, carrying the same premature-submit risk as the Add/Remove slot controls — deferred, pre-existing (this exact pattern is copied verbatim from `TeamFormDialog.tsx`, which the story was explicitly instructed to mirror; not introduced by this diff).
