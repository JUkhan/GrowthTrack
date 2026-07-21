---
baseline_commit: 864927b4e2bc37962dfa658517ead670cbf16700
---

# Story 4.1: Compose & Send Manual Notification

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an Administrator,
I want to select Recipients, pick a pre-approved template, fill in its variables, optionally attach the current report, and send immediately,
so that an urgent update reaches the right people without waiting for the next scheduled run.

## Acceptance Criteria

1. **Given** the Recipient picker **When** I select a mix of individual Users, Teams, and RecipientLists **Then** a live de-duplicated count is shown (e.g. "14 selected → 11 unique recipients (3 overlaps merged)") using the same resolution logic the send path uses

2. **Given** zero recipients selected **When** I attempt to send **Then** Send is disabled with an inline reason, not a silent no-op

3. **Given** a set of resolved recipients **When** I confirm Send **Then** one `Notification` row is created, recipients are resolved fresh (deduped, consent-filtered) into one `NotificationDelivery` row each, keyed uniquely by `(recipient_user_id, notification_id)`

4. **Given** the composer **When** I compose a message **Then** I select from pre-approved WhatsApp templates and fill its variable slots only — no free-form body text — with a live preview of exactly what the recipient will see

5. **Given** I confirm Send **When** dispatch begins **Then** the Send control is disabled and shows "Sending to N recipients…" — no double-submit is possible

6. **Given** each `NotificationDelivery` row is ready to dispatch **When** the WhatsApp adapter is called **Then** the row is atomically claimed first (conditional UPDATE) so a crashed/racing retry can never re-dispatch against the same row

7. **Given** a sent Manual Notification **When** it completes **Then** it appears in Notification History tagged "Manual"

8. **Given** a Manual Notification's send outcome **When** it is the most recent send system-wide **Then** the Dashboard's notification-status field (Story 2.2) reflects it, replacing the "No sends yet" placeholder

## Tasks / Subtasks

- [x] **Task 1: Domain models + migration** (AC: #3, #6, #7)
  - [x] Add enums to `domain/models.py`: `NotificationType` (`manual`/`scheduled`), `DeliveryStatus` (`queued`/`sending`/`delivered`/`retrying`/`failed`/`failed_retryable` — include `failed_retryable` now even though this story never writes it; AD-2's literal claim SQL references it and Story 4.3 needs it without a schema change), `TargetType` (`user`/`team`/`recipient_list`)
  - [x] Add `@dataclass` entities to `domain/models.py`, matching the existing `User`/`Team`/`RecipientList` style (plain dataclasses, no SQLAlchemy/ORM leakage — AD-1):
    - `MessageTemplate(id, name, twilio_content_sid, variable_slots: list[str], body_preview_template: str, created_at)` — `variable_slots` order is the positional mapping to Twilio's `content_variables` keys (`"1"`, `"2"`, …). `body_preview_template` holds human-readable text with `{slot_name}` placeholders (Python `str.format`) purely for the composer's local live-preview render — Twilio's Content API has no "render me the text" call, so this field is the only source for AC #4's preview.
    - `Notification(id, notification_type: NotificationType, template_id, created_by_user_id, created_at)`
    - `NotificationTarget(id, notification_id, target_type: TargetType, target_id)` — relational join rows, never a JSON blob (AD-4)
    - `NotificationDelivery(id, notification_id, notification_type: NotificationType, recipient_user_id, operational_day: date | None, status: DeliveryStatus, attempt_count: int, provider_message_sid: str | None, failure_reason: str | None, created_at, updated_at)` — `notification_type` is **denormalized onto the delivery row** (not just joined from `Notification`) because Postgres partial-unique-index predicates can't reference a joined table; `operational_day` stays `None` for Manual sends (only Scheduled/Story 4.2 populates it)
  - [x] New Alembic migration, `down_revision` = `1dfe4d12bdee` (current head): `message_templates`, `notifications`, `notification_targets`, `notification_deliveries` tables, following `976cabf50f32_recipient_lists_and_membership.py`'s style (UUID PK, `sa.PrimaryKeyConstraint`, plain columns). `notification_targets` gets its own `id` PK plus **exactly the three columns named in the domain model above**: `target_type` (discriminator) + a single generic `target_id` column (AD-4: relational join rows, never a JSON blob, one polymorphic id column — **not** three separate nullable per-type FK columns; this must match Task 3's ORM mapping exactly, unlike the pure two-FK-column join table `recipient_list_members` uses)
  - [x] Two **partial unique indexes** on `notification_deliveries`, one per `notification_type`, via `op.create_index(..., unique=True, postgresql_where=sa.text("notification_type = 'manual'"))` — never a single composite constraint over nullable columns (AD-2 is explicit: NULL-is-distinct-from-NULL defeats that): `(notification_id, recipient_user_id) WHERE notification_type = 'manual'` and `(recipient_user_id, operational_day) WHERE notification_type = 'scheduled'`

- [x] **Task 2: Ports** (AC: #1, #2, #3, #4, #6, #7, #8)
  - [x] `ports/notifications.py` — `ABC`/`@abstractmethod` style matching `ports/recipient_lists.py`/`ports/consent.py`: `MessageTemplateRepository` (`list_active()`, `get_by_id()`), `NotificationRepository` (`add(notification, targets)` — bundling both writes into one port call is a deliberate, small deviation from the split-call convention `RecipientListRepository.add()`/`.replace_members()` uses; keep it bundled here since both rows are always written together atomically with no independent-update case, unlike list membership), `NotificationDeliveryRepository` (`bulk_create(rows)`, `claim_for_dispatch(id) -> bool` implementing AD-2's claim semantics as a plain `UPDATE notification_deliveries SET status='sending' WHERE id=? AND status IN ('queued','failed_retryable')` — **no `RETURNING` clause**, matching every existing atomic-conditional-update method in this codebase (`update_details`, `update_name`, etc.), just `return result.rowcount > 0` — `update_after_send(id, status, provider_message_sid, failure_reason)`, `most_recent_status_summary() -> Any | None` for the Dashboard tile)
  - [x] `ports/whatsapp.py` — `WhatsAppSender` ABC: `send_template_message(to_number: str, content_sid: str, content_variables: dict[str, str]) -> SendResult` (returns provider message SID) raising `WhatsAppSendError(code, message)` on failure. This is the port named in ARCHITECTURE-SPINE.md's Structural Seed that doesn't exist yet.
  - [x] Extend `ports/users.py`: add `list_by_team_id(team_id) -> list[Any]` — **Teams have no member-join-table**, membership is `User.team_id`, and no existing method resolves this (confirmed: `TeamRepository` only manages Team rows themselves). Required for recipient resolution to expand a selected Team into member Users.

- [x] **Task 3: Persistence adapters** (AC: #1, #2, #3, #4, #6, #7, #8)
  - [x] `adapters/persistence/notifications.py` — SQLAlchemy models (`XxxModel`, `snake_case` plural tables) + repo implementations of Task 2's ports, following `adapters/persistence/recipient_lists.py`'s atomic-conditional-update pattern (`result = await session.execute(stmt); return result.rowcount > 0`) for `claim_for_dispatch`. `notification_targets` mapped as its own ORM class (not a Core `Table` like `recipient_list_members`) since it carries an `id` and polymorphic `target_type`/`target_id`, not a pure two-FK join row.
  - [x] Implement `list_by_team_id` in `adapters/persistence/users.py`
  - [x] `adapters/whatsapp_twilio/sender.py` — `TwilioWhatsAppSender(WhatsAppSender)` using `twilio.rest.Client(settings.twilio_account_sid, settings.twilio_auth_token)`. **This package is currently empty — build it from scratch.** Twilio SDK 9.10.9 is already a pinned dependency (`pyproject.toml`) — no dependency change needed. **The Twilio SDK's `messages.create` is a blocking/synchronous call (`requests` under the hood)** — every port method elsewhere in this codebase is `async def`, and calling a blocking network call directly inside one would stall FastAPI's event loop (including `/health` checks and any concurrent request) for the full round-trip of every send in the loop, unlike the sub-100ms CPU-bound sync-in-async precedent `PwdlibPasswordHasher` sets. Wrap the call in `asyncio.to_thread(...)`. Call shape (Content API — templates are Content API only in Twilio's current model, `body`/`media_url` are excluded when `content_sid` is used):
    ```python
    message = await asyncio.to_thread(
        client.messages.create,
        content_sid=template.twilio_content_sid,
        content_variables=json.dumps(content_variables),  # {"1": "...", "2": "...", ...} — positional, from variable_slots order
        to=f"whatsapp:{recipient.mobile}",
        from_=f"whatsapp:{settings.twilio_whatsapp_number}",
    )
    # message.sid -> provider message SID to store; message.status starts "queued" (Twilio-side, distinct from our own DeliveryStatus)
    ```
    Catch `twilio.base.exceptions.TwilioRestException` (exposes `.code`, `.msg`, `.status`) and re-raise as `WhatsAppSendError(code=str(e.code), message=f"{e.code}: {e.msg}")` — this becomes `NotificationDelivery.failure_reason`.
  - [x] Wire `WhatsAppSender` via a FastAPI dependency provider (own function, e.g. in `api/notifications/routes.py` or a shared `api/dependencies.py`) that tests can override — do **not** hardcode `TwilioWhatsAppSender()` inline in the route, or tests will hit real Twilio.

- [x] **Task 4: Domain services** (AC: #1, #2, #3, #4, #5, #6, #7, #8)
  - [x] `domain/notifications.py`, following `domain/recipients.py`'s shape (service class takes repo ports + `AuditLogRepository` in `__init__`; bare marker exceptions; service never calls `session.commit()` — the route does):
    - `RecipientResolutionService.resolve(user_ids, team_ids, recipient_list_ids) -> ResolvedRecipients` — **the one function AD-2 requires be shared by both the send path and the composer's live-preview endpoint.** Expands Teams via `list_by_team_id`, RecipientLists via existing `get_member_user_ids`, unions with directly-selected `user_ids`, dedupes by user id, filters to **active users only**, then filters to **opt-in-consent-granted only** (AD-9: consent gate lives in resolution, not dispatch). **Track the gap between selected and sendable as two distinct counts, not one** — `overlap_count` (recipients reachable via more than one mechanism, e.g. individually listed AND a member of a selected Team — true cross-mechanism duplicates only) and a separate `ineligible_count` (resolved-but-excluded for being inactive or not opt-in-consented). Collapsing both into a single "overlaps merged" figure is factually wrong per UX-DR25 ("names the actual cause... numbers are never rounded away") — a consent-excluded recipient is not an "overlap." Return `selected_count` (raw picker selections/expansions before any filtering), `overlap_count`, `ineligible_count`, and `unique_count` (final sendable count = `selected_count - overlap_count - ineligible_count`, deduped). **Design decision — the live preview (AC #1) must show `unique_count`** (the same post-consent, post-active-filter number that will actually receive the message), not a raw pre-filter count, since AD-2 mandates identical resolution output for both callers; showing a bigger number in preview than actually gets sent would mislead the Administrator. The UI copy should surface `ineligible_count` separately when non-zero (e.g. "11 unique recipients (3 overlaps merged, 1 not opted in)") rather than folding it into "overlaps."
    - `ManualNotificationService.compose_and_send(template_id, variable_values, user_ids, team_ids, recipient_list_ids, actor_user_id) -> ComposeResult`:
      1. Load template, validate `variable_values` keys exactly match `template.variable_slots` (no missing/extra — enforces AC #4's "variable slots only, no free-form")
      2. Call `RecipientResolutionService.resolve(...)`; if `unique_count == 0` raise `NoRecipientsSelected` (→ AC #2, mapped to a 422 by the route)
      3. In one transaction: create `Notification` row + `NotificationTarget` rows (the raw picker selections, not the expanded members — AD-4) + audit log entry (`notification.sent` or similar, AD-7 co-transactional)
      4. Bulk-create one `NotificationDelivery` row per resolved unique recipient, `status=queued`, `notification_type=manual`
      5. For each row, **loop synchronously** (batch sizes here are small manual sends — Twilio allows 80 msg/sec per sender, far above this path's volume; NFR-1's 500+ concurrent dispatch figure is Story 4.2's scheduled-fan-out concern, not this one): `claim_for_dispatch(id)` (AC #6) → on `True`, call `WhatsAppSender.send_template_message(...)` → on success `update_after_send(id, status="sending", provider_message_sid=sid)`; on `WhatsAppSendError`, `update_after_send(id, status="failed", failure_reason=...)`. **This story implements only `queued`→`sending` (accepted) and `queued`→`failed` (rejected, terminal) — automatic retry and the `delivered`/`retrying` transitions are Story 4.3's scope (webhook-driven), not this one's.**
      6. Return per-recipient outcome summary for the API response
    - A read method for the Dashboard tile, e.g. `latest_notification_status()`, reading `NotificationDeliveryRepository.most_recent_status_summary()` — "most recent send system-wide" per AC #8 (system-wide = latest across Manual and Scheduled; Scheduled doesn't exist yet, so today this is always the latest Manual send)

- [x] **Task 5: API routes** (AC: #1, #2, #3, #4, #5, #6, #7, #8)
  - [x] `api/notifications/routes.py`, following `api/recipients/routes.py`'s conventions exactly: `APIRouter(prefix="/notifications", tags=["notifications"])`, every route depends on `get_current_user`/`get_db` from `api.auth.dependencies` (AD-8, never an inline check), errors via the `{error:{code,message,details}}` envelope
    - `GET /message-templates` — list active templates (id, name, variable_slots, body_preview_template) for the composer dropdown
    - `POST /notifications/resolve-recipients` — body `{user_ids, team_ids, recipient_list_ids}`, calls `RecipientResolutionService.resolve` **read-only** (no DB writes — the dedupe-preview caller), returns `{selected_count, unique_count, overlap_count, ineligible_count}` (see Task 4 — `ineligible_count` must stay distinct from `overlap_count`, never folded together)
    - `POST /notifications` — body `{template_id, variable_values, user_ids, team_ids, recipient_list_ids}`, calls `ManualNotificationService.compose_and_send`; 201 with per-recipient summary on success; `NoRecipientsSelected` → 422 with error code `no_recipients_selected`
  - [x] Register the router in `api/main.py` (flat `include_router` list, same as existing routers)
  - [x] Add `GET /dashboard/notification-status` **in `api/dashboard/routes.py`** (that file already exists with the exact router/pattern needed — don't create a new module for one endpoint). Separate endpoint, not bundled into `GET /dashboard/summary`'s response — mirrors this exact file's existing precedent of fetching Brand Performance via its own effect/endpoint rather than extending the summary contract.
  - [x] Add `location /notifications/` + `location = /notifications` blocks to `docker/nginx/nginx.conf`, matching the existing bare+trailing-slash pattern for every other resource (`/users`, `/teams`, `/recipient-lists`) — **omitting this means the route 404s/falls through to the SPA in staging/production while working fine in local dev**, exactly the sharp edge Story 2.2's Dev Notes already flagged once. `GET /dashboard/notification-status` needs no new block — it falls under the existing `location /dashboard/` block.

- [x] **Task 6: Frontend — Compose page** (AC: #1, #2, #3, #4, #5)
  - [x] New `web/src/components/MixedRecipientPicker.tsx` — **the existing `web/src/components/RecipientPicker.tsx` is explicitly documented in its own source as NOT sufficient here** ("a plain multi-select of individual, active, WhatsApp-addressable Users only... Epic 4's Notifications ▸ Compose extends this (or builds its own) once it needs to resolve a mixed User/Team/RecipientList selection with a de-duplicated count — that cross-type dedupe logic is explicitly not this component's job yet"). Build a new component: chip-row of selected User/Team/RecipientList entries (removable via `×`, per the mockup), calls `POST /notifications/resolve-recipients` (debounced) on every selection change, renders the dedupe-note text exactly like the mockup: `"14 selected → 11 unique recipients (3 overlaps merged)"`
  - [x] New `web/src/pages/NotificationComposePage.tsx` — layout per `mockups/notifications-compose.html`: Recipients section (chips + dedupe note) / Message section (template `<select>`, one editable field per `variable_slots` entry, attach-report checkbox — see scope note below) / live WhatsApp-bubble preview panel (client-side `body_preview_template` interpolated with current field values — plain string substitution, re-render on every keystroke) / footer Send + Cancel buttons
  - [x] Send button: disabled with visible inline reason "Select at least one recipient" when `unique_count === 0` (AC #2); on click, `setSubmitting(true)`, label becomes `"Sending to N recipients…"` with a spinner (AC #5), request in flight guards against double-submit
  - [x] Fetch `GET /users`, `GET /teams`, `GET /recipient-lists` (existing endpoints, same pattern `RecipientsPage.tsx` already uses) to populate the picker's option lists; fetch `GET /message-templates` for the template dropdown. **`GET /users` returns ALL roles/statuses, including Administrators (who always have `mobile=None`) and inactive Users** — filter to `status === 'active' && mobile != null` before offering them as picker options, the same contract `RecipientPicker.tsx` already enforces on its own options. Without this filter, an Administrator or inactive User selected in the picker gets silently dropped later by the resolution service's active/consent filters and miscounted as `ineligible_count` instead of never being offered at all.
  - [x] `web/src/router.tsx`: add `/notifications/compose` route; add "Notifications" to the sidebar nav (per the mockup, a single nav item — no Compose/History sub-nav yet since Notification History is Epic 5 Story 5.1, out of this story's scope)
  - [x] **Scope note — "attach current report" checkbox**: appears in the story's narrative and the mockup, but **is not tested by any of the 8 acceptance criteria above**, and Epic 4 Story 4.2 (which generates the Daily Report content this would attach) doesn't exist yet — there is no "current report" artifact to attach today. `[ASSUMPTION: attach-report scope, pending confirmation]` — do not build report-generation logic in this story. Recommended: omit the control entirely for this story's first cut, or render it disabled with a tooltip ("Report attachment available once Daily Reports are generated — Story 4.2"). Do not block this story's completion on it.

- [x] **Task 7: Frontend — Dashboard wiring** (AC: #8)
  - [x] `web/src/pages/DashboardPage.tsx` — replace the static `<StatusBadge status="neutral" ... label="No sends yet" />` notification-status tile with a fetch to `GET /dashboard/notification-status`, following the same separate-`useEffect` pattern already used for Brand Performance in this file. Map delivery-outcome states to `StatusBadge` variants (component already supports all needed states — no changes to `StatusBadge.tsx` itself needed): success→Delivered, warning→Retrying, error→Failed, neutral→Queued/Sending/no-sends-yet.

- [x] **Task 8: Seed data** (AC: #4)
  - [x] Extend `scripts/seed_demo_data.py` to insert at least one demo `MessageTemplate` row (placeholder `twilio_content_sid`, e.g. matching the mockup's "Target Revision Notice" with `variable_slots=["team_name","new_target","effective_date"]`) so a fresh environment's composer has something to select — **no story anywhere in epics.md builds a Template-management UI** (approval happens in Twilio/Meta's console per the architecture spine's Deferred list); document in the seed script that real Content SIDs must be swapped in from the Twilio Console before any real send.

- [x] **Task 9: Tests** (AC: all)
  - [x] `tests/domain/test_notifications_service.py` — hand-written `Fake*Repository` classes (no mocking library, matching `tests/domain/test_recipients_service.py`'s style): cover dedup across overlapping User/Team/RecipientList selections (asserting `overlap_count` specifically), consent-filtering and inactive-user exclusion (asserting they land in `ineligible_count`, not `overlap_count`), zero-recipient rejection, audit-log co-transactional write, atomic-claim race (`simulate_update_race`-style flag returning `False` on second claim attempt), and a data-layer check that a completed manual send's `Notification`/`NotificationDelivery` rows carry `notification_type='manual'` and are queryable (AC #7 — no History UI exists yet to check this against instead)
  - [x] `tests/adapters/persistence/test_notifications_repository.py` — real Postgres (no mocking, matching existing adapter tests): verify both partial unique indexes reject a same-type duplicate but allow the same `recipient_user_id` across different notification types, verify `claim_for_dispatch` rowcount semantics
  - [x] `tests/api/test_notifications_routes.py` — `httpx2` `AsyncClient` + `ASGITransport(app=app)` against the real app (matching `tests/api/` convention): 401-without-cookie tests for every new route (AD-8), end-to-end compose+send using a **fake `WhatsAppSender` injected via FastAPI dependency override** (never hit real Twilio in tests), 422 on zero recipients, `GET /dashboard/notification-status` reflecting a just-completed send
  - [x] Update `tests/conftest.py`'s `_clean_tables` autouse fixture: add `DELETE FROM notification_deliveries`, `notification_targets`, `notifications`, `message_templates` in FK-dependency order (children before the `users`/`teams`/`recipient_lists` deletes that already exist)
  - [x] Frontend: `MixedRecipientPicker.test.tsx`, `NotificationComposePage.test.tsx` (zero-recipient blocked state, sending-state no-double-submit, live preview updates on field change), update `DashboardPage.test.tsx` for the live notification-status fetch

### Review Findings

- [x] [Review][Decision] Dashboard "Notification Status" tile shows one arbitrary delivery row's status, not the notification's overall outcome — `NotificationStatusService.latest_notification_status`/`most_recent_status_summary` (`domain/notifications.py:307-310`, `adapters/persistence/notifications.py:most_recent_status_summary`) picks whichever single `NotificationDelivery` row has the newest `updated_at` system-wide. For a multi-recipient send, whichever recipient happens to be processed last in the synchronous dispatch loop determines what the Admin sees — e.g. 99/100 succeed and the last one fails (bad number) → dashboard shows "Failed" for what was actually a near-total success, and the reverse (early failures, later success) hides real failures. Violates AC #8, which speaks of "a Manual Notification's send outcome" (notification-level), not one arbitrary delivery row. **Resolved:** worst-status-wins — group by `notification_id`, take the latest `Notification`, surface its worst delivery outcome (any failure → Failed). Converted to a Patch item below.

- [x] [Review][Patch] Aggregate the Dashboard notification-status tile by `notification_id` (worst-status-wins) instead of the single most-recently-updated delivery row [domain/notifications.py:307-310, adapters/persistence/notifications.py:most_recent_status_summary] — Fixed: new `NotificationStatusSummary` domain type; `most_recent_status_summary` now finds the latest `Notification` and returns the worst-severity status among its own delivery rows. Regression tests added at both the domain-fake and real-Postgres-adapter level.
- [x] [Review][Patch] Uncaught exceptions during the per-recipient dispatch loop can lose already-sent WhatsApp messages with no DB record [domain/notifications.py:260-296] — Fixed: the per-recipient `try/except` now also catches any non-`WhatsAppSendError` exception (and guards the `recipients_by_id` lookup) so a single transport failure is recorded as a `FAILED` outcome instead of aborting the whole batch and rolling back everyone already processed. Regression test added.
- [x] [Review][Patch] `RecipientResolutionService.resolve()` never checks for a missing mobile number [domain/notifications.py:100-111] — Fixed: added `user.mobile is None` to the eligibility check. Test added.
- [x] [Review][Patch] Blank/whitespace-only template variable values are never rejected, server or client side [domain/notifications.py:170-171] — Fixed on both sides: backend raises `InvalidVariableValues` on any blank/whitespace-only value; frontend's `canSend` now also requires every slot to be non-blank. Tests added on both sides.
- [x] [Review][Patch] Live WhatsApp preview can substitute inside an already-substituted value, misrepresenting the real send [web/src/pages/NotificationComposePage.tsx:49-55] — Fixed: `renderPreview` now does a single regex pass over the original template text instead of sequential split/join, so a typed value can never be re-scanned for further substitution.
- [x] [Review][Patch] Recipient resolution doesn't check that an expanded Team/RecipientList is itself active [domain/notifications.py:84-90] — Fixed: `resolve()` now fetches the Team/RecipientList via the existing `get_by_id` port methods and skips expansion unless `status == ACTIVE`. Required adding a `teams: TeamRepository` dependency to `RecipientResolutionService` (both call sites in `api/notifications/routes.py` updated). Tests added.
- [x] [Review][Patch] Ineligible-count label doesn't name the actual cause, deviating from the spec's own example copy [web/src/components/MixedRecipientPicker.tsx:39-41] — Fixed: wording changed from "N not eligible" to "N inactive or not opted in".
- [x] [Review][Patch] Send button's inline reason can misleadingly read "Select at least one recipient" for ~300ms+ after a recipient IS selected [web/src/pages/NotificationComposePage.tsx:157-158] — Fixed: the hint now distinguishes three states — no recipients selected, still resolving (`resolved === null`), and resolved-to-zero-eligible — instead of collapsing them all into `uniqueCount === 0`.
- [x] [Review][Patch] ~~Redundant `session.commit()` on every pre-write validation error branch~~ [api/notifications/routes.py:187-197] — **Not applied.** On closer check this matches an established, deliberate codebase-wide convention (every handled-error branch commits before returning, e.g. `api/recipients/routes.py`, `api/auth/routes.py`), not an oversight specific to this file. "Fixing" it here would make this file inconsistent with the rest of the codebase, so left as-is.

- [x] [Review][Defer] Manual send batch is dispatched synchronously in one request/DB transaction with no size cap [domain/notifications.py:256-294] — deferred, pre-existing: explicitly, deliberately scoped to Story 4.2 per this story's own code comment/Dev Notes (NFR-1's 500+ concurrent-dispatch figure is 4.2's scope, not this story's).
- [x] [Review][Defer] Silent recipient drop if `claim_for_dispatch` ever loses the race [domain/notifications.py:261-263] — deferred, pre-existing: explicitly out of this story's scope per the spec — retry/claim-race handling belongs to Story 4.3; the code already documents (`# pragma: no cover`) and tests this branch as expected-unreachable within 4.1.
- [x] [Review][Defer] No server-side idempotency/double-send protection beyond the frontend's `submitting` guard [api/notifications/routes.py, domain/notifications.py] — deferred, pre-existing class of gap: not required by any AC in this story (AC #5 only requires the client-side single-flight guard, which is present); worth a design decision in a future story.

## Dev Notes

- **This is a fully greenfield slice within the established hexagonal pattern** — no `Notification`/`NotificationDelivery`/`NotificationTarget`/`MessageTemplate` domain types, ports, adapters, migrations, or routes exist anywhere in the codebase today, and `adapters/whatsapp_twilio/__init__.py` is completely empty. The one genuinely novel piece with *no* existing precedent to copy is the cross-type (User+Team+RecipientList) deduplicated recipient-resolution function AD-2 mandates.
- **Twilio config already exists** — `twilio_account_sid`, `twilio_auth_token`, `twilio_whatsapp_number` are already required fields on the `Settings` object (`config.py`, read via `get_settings()`), already wired into `docker/docker-compose.yml`'s shared `x-backend-env` anchor for both `api` and `scheduler`, and already present (as `change-me` placeholders) in `.env.example`. No config or docker-compose changes needed — just consume `get_settings()` in the new Twilio adapter.
- **Import-linter enforces AD-1**: Twilio SDK types and SQLAlchemy types may only appear inside `adapters/*` — never in a `domain/` function signature.
- **`scheduler/` is out of scope for this story.** It's a separate Compose service (AD-5) that Story 4.2 (Automated) and 4.3 (retry) will touch. Manual sends are entirely API-request-triggered.
- **Status vocabulary**: only `queued → sending` (accepted by Twilio) and `queued → failed` (rejected, terminal) are produced by this story. `delivered`/`retrying` require Story 4.3's webhook; `failed_retryable` is a Story-4.3-only outcome. Include all six values in the `DeliveryStatus` enum now (AD-2's claim SQL literally names `failed_retryable` in its `WHERE` clause) so Story 4.3 doesn't need a schema migration just to add an enum value.
- **`RecipientPicker.tsx` is not reusable as-is** — read its own source comment before touching it; it's explicitly scoped to single-type User-only selection and defers cross-type dedup to this story. Build `MixedRecipientPicker.tsx` new rather than trying to extend it in place.
- **No pagination on the new `GET /message-templates` list** — consistent with the existing directory-listing convention (Story 3.1 deferred pagination the same way); revisit only if template count grows large.
- **Mobile-number format is still unvalidated anywhere in this codebase** (deferred since Story 3.1) — don't add first-time validation here; `TwilioWhatsAppSender` should let a malformed number fail naturally via `TwilioRestException` rather than pre-validating.
- **AC #7 ("appears in Notification History tagged Manual") is only satisfiable at the data layer in this story.** No task here builds a `/notifications/history` endpoint or view — Notification History is Epic 5 Story 5.1, which doesn't exist yet. This story's job for AC #7 is limited to correctly persisting `notification_type='manual'` on every `Notification`/`NotificationDelivery` row so Story 5.1 can query it later. Verify via a repository-level test that a manual send's rows are queryable and correctly tagged — do not build or expect a History screen to visually confirm against, mirroring Story 2.4's identical precedent (its doctor list shipped before Epic 4 existed and was verified the same way, per epics.md's own note on that story).

### Twilio WhatsApp API — current specifics (verified against current docs, not just training data)

- Templates are **Content API only** for WhatsApp — `content_sid`/`content_variables` fully replace `body`/`media_url` for a template send; Twilio's docs say to exclude `Body`/`MediaUrl` when `ContentSid` is set. This lines up exactly with AC #4's "pre-approved template + variable-slot fill-in, no free-form body."
- `content_variables` keys are positional strings (`"1"`, `"2"`, …), not named — hence `MessageTemplate.variable_slots`' *order* is what maps a named slot to Twilio's positional key.
- SDK `twilio==9.10.9` (already pinned/installed) is current — no newer major version found, no breaking changes to account for.
- Auth: Account SID + Auth Token works but Twilio's current guidance favors **API Keys** for production server-side use (revocable, scoped) over the raw Auth Token. Not a blocker — `config.py`'s existing `twilio_auth_token` field satisfies AD-5 either way — but worth a one-line note if credentials are (re)provisioned during this story.
- Rate limit: 80 msg/sec per WhatsApp sender by default (up to 400 MPS on request) — far above a manual send's batch size, so the synchronous per-recipient loop in `ManualNotificationService` needs no async/queue restructuring for this story.
- Error handling: catch `twilio.base.exceptions.TwilioRestException` — exposes `.code` (Twilio numeric error code, e.g. 21610 = recipient opted out/blacklisted Twilio-side), `.msg`, `.status`. Populate `NotificationDelivery.failure_reason` from these — don't try to enumerate Twilio's full error taxonomy in code, just pass it through.
- Nothing product-renamed or materially different from typical training-data assumptions as of this check; the one deployment-relevant flag is that Twilio's WhatsApp *sender* (sandbox vs. production-registered number) is provisioned independently of code — confirm which is configured in each environment, not something this story's code needs to branch on.

### Project Structure Notes

New files (all new — nothing here modifies existing hexagonal layering, only extends it the same way Story 3.x extended the directory-management slice):
`domain/notifications.py`, `ports/notifications.py`, `ports/whatsapp.py`, `adapters/persistence/notifications.py`, `adapters/whatsapp_twilio/sender.py`, `api/notifications/routes.py`, `alembic/versions/<new>_notifications_and_message_templates.py`, `web/src/components/MixedRecipientPicker.tsx`, `web/src/pages/NotificationComposePage.tsx`.

Modified files: `domain/models.py` (new enums/dataclasses), `ports/users.py` + `adapters/persistence/users.py` (`list_by_team_id`), `api/main.py` (router registration), `api/dashboard/routes.py` or a new module (notification-status endpoint), `docker/nginx/nginx.conf` (new location blocks), `web/src/pages/DashboardPage.tsx`, `web/src/router.tsx`, `scripts/seed_demo_data.py`, `tests/conftest.py`.

No conflicts detected with the fixed source tree (Architecture Spine's Structural Seed) — this story fills in previously-named-but-unbuilt pieces (`WhatsAppSender` port, `adapters/whatsapp_twilio/`) rather than deviating from it.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 4.1: Compose & Send Manual Notification] — story statement, all 8 ACs, FR-8
- [Source: _bmad-output/planning-artifacts/architecture/architecture-GrowthTrack-2026-07-14/ARCHITECTURE-SPINE.md#AD-1] — dependency direction, domain/ports/adapters isolation
- [Source: ...ARCHITECTURE-SPINE.md#AD-2] — Send Event identity, partial unique indexes, atomic claim SQL, fresh-at-send-time resolution, one resolution function for two callers
- [Source: ...ARCHITECTURE-SPINE.md#AD-3] — delivery-status webhook is Story 4.3's scope, monotonic status transitions, provider SID overwritten not historized
- [Source: ...ARCHITECTURE-SPINE.md#AD-4] — `RecipientList`/`Team`/`Notification`/`NotificationDelivery`/`NotificationTarget`/`MessageTemplate` data ownership and relational (never JSON) target spec
- [Source: ...ARCHITECTURE-SPINE.md#AD-5] — Twilio credentials as env-injected secrets, deployment topology
- [Source: ...ARCHITECTURE-SPINE.md#AD-7] — co-transactional audit log
- [Source: ...ARCHITECTURE-SPINE.md#AD-8] — shared auth dependency, no inline route checks
- [Source: ...ARCHITECTURE-SPINE.md#AD-9] — opt-in consent enforced at resolution, not dispatch
- [Source: ...ARCHITECTURE-SPINE.md#Stack] — Twilio Python SDK 9.10.9, versions pinned
- [Source: ...ARCHITECTURE-SPINE.md#Capability → Architecture Map] — CAP-4 lives in `api/notifications`, `domain/notifications`, `adapters/whatsapp_twilio`
- [Source: _bmad-output/specs/spec-growthtrack/entities.md] — baseline `Notification` field inventory, `Team`/`NotificationLog` open questions this story's data model resolves
- [Source: _bmad-output/specs/spec-growthtrack/sample-whatsapp-report.md] — reference format for a "current report" attachment, relevant to the Task 6 scope note
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-GrowthTrack-2026-07-14/mockups/notifications-compose.html] — exact composer layout, chip/dedupe-note/preview-bubble visual spec
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-GrowthTrack-2026-07-14/EXPERIENCE.md] — Recipient picker / Notification composer / In-progress / Blocked component-and-state patterns, UX-DR12/13/19/21
- [Source: _bmad-output/planning-artifacts/prds/prd-GrowthTrack-2026-07-14/addendum.md#A2] — Twilio POC-only, template billing/category
- [Source: ...addendum.md#A3] — WhatsApp opt-in compliance backing AD-9
- [Source: ...addendum.md#A6] — Recipient Group/Channel modeled as GrowthTrack-internal User sets, not live WhatsApp platform objects — confirms fan-out-to-individual-numbers is correct
- [Source: _bmad-output/implementation-artifacts/deferred-work.md#Deferred from: code review of 3-1-manage-users-sales-teams] — no-pagination and mobile-format-unvalidated precedents this story continues
- Codebase (read directly, current as of this story's creation): `domain/models.py`, `domain/recipients.py`, `domain/administrators.py`, `ports/{recipient_lists,teams,users,consent,audit}.py`, `adapters/persistence/{recipient_lists,teams,users,consent,database}.py`, `adapters/whatsapp_twilio/__init__.py` (empty), `api/{recipients,dashboard}/routes.py`, `api/auth/dependencies.py`, `api/main.py`, `web/src/components/{RecipientPicker,StatusBadge,ConfirmationDialog}.tsx`, `web/src/pages/{DashboardPage,RecipientsPage}.tsx`, `web/src/router.tsx`, `web/src/api/authClient.ts`, `config.py`, `docker/docker-compose.yml`, `docker/nginx/nginx.conf`, `alembic/versions/{976cabf50f32,1dfe4d12bdee}_*.py`, `pyproject.toml`, `tests/conftest.py`, `scripts/seed_demo_data.py`

## Dev Agent Record

### Agent Model Used

Claude Sonnet 5 (claude-sonnet-5)

### Debug Log References

None — no blocking failures encountered; all validation gates (ruff, mypy, import-linter, eslint, tsc, pytest, vitest) passed on first green run after implementation.

### Completion Notes List

- Full hexagonal slice implemented per Dev Notes: `domain/models.py` enums/dataclasses → `ports/notifications.py` + `ports/whatsapp.py` + `ports/users.list_by_team_id` → `adapters/persistence/notifications.py` + `adapters/whatsapp_twilio/sender.py` → `domain/notifications.py` (`RecipientResolutionService`, `ManualNotificationService`, `NotificationStatusService`) → `api/notifications/routes.py` + `api/dashboard/routes.py` notification-status endpoint.
- `NotificationStatusService` is a separate, minimal class (just `NotificationDeliveryRepository`) rather than a method on `ManualNotificationService` — the Dashboard's read path has no business requiring Twilio/audit-log dependencies just to read the latest delivery status.
- `MessageTemplateRepository` gained `get_by_name`/`add` beyond Task 2's read-only spec (`list_active`/`get_by_id`) — needed so `scripts/seed_demo_data.py` (Task 8) can idempotently seed the demo template through the repository layer, matching `TeamRepository`/`RecipientListRepository`'s existing get-by-name-then-add seeding shape rather than reaching around the port with raw SQL.
- Interpreted `GET /message-templates` as a literal top-level path (separate `message_templates_router`, prefix `/message-templates`) rather than nested under `/notifications`, since the story lists it without the `/notifications` prefix unlike the other two routes. Added matching `location /message-templates`/`= /message-templates` nginx blocks and a vite dev-proxy entry beyond what Task 5's nginx bullet literally named, applying the same "un-proxied route 404s in staging" lesson to the sibling route.
- Also added `/notifications`, `/message-templates`, and `/dashboard/notification-status` entries to `web/vite.config.ts`'s dev proxy — undocumented in the story tasks but required by the same reasoning as the nginx blocks (Vite's proxy allowlist is explicit per-path, not a catch-all).
- No nav shell exists yet in this codebase (flagged by `DashboardPage.tsx`'s own prior comment) — "Notifications" was added as a header `Link` next to the existing "Recipients" link (Dashboard → Compose) and a "Back to Dashboard" link on the Compose page, mirroring `RecipientsPage.tsx`'s established lightweight pattern instead of building a sidebar.
- "Attach current report" checkbox rendered disabled with an explanatory tooltip per the story's recommended option — no report-generation logic built (Story 4.2 scope).
- `NotificationDelivery.status`/`DeliveryStatus` values sent to the frontend are the raw enum strings; `DashboardPage.tsx` maps `delivered`→success, `retrying`→warning, `failed`/`failed_retryable`→error, `queued`/`sending`→neutral, and a fetch failure → warning "Unable to load".
- Left one pre-existing, unrelated lint violation untouched: `DashboardPage.tsx`'s Brand Performance effect (`setBrandPerformanceError(false)` called synchronously in a `useEffect` body) already violated `react-hooks/set-state-in-effect` before this story (confirmed via `git show HEAD`). The new Notification Status effect mirrors that exact, pre-existing sibling pattern for consistency rather than introducing a differently-shaped fix in only the new code.
- All new/changed backend files pass `ruff`, `mypy --strict=false` (project config), and `import-linter` (AD-1 hexagonal boundaries hold). All new/changed frontend files pass `tsc --noEmit` and `eslint` (excepting the one pre-existing violation noted above).
- Full regression: 394 backend tests (`pytest`) and 159 frontend tests (`vitest`) pass, including all newly added notification tests.
- Alembic migration `c4a8f21e6b3d` applied cleanly against the local dev Postgres; `scripts/seed_demo_data.py` re-ran successfully end-to-end and seeded the demo `MessageTemplate` row (verified via direct repository query).

### File List

**New files:**
- `alembic/versions/c4a8f21e6b3d_notifications_and_message_templates.py`
- `domain/notifications.py`
- `ports/notifications.py`
- `ports/whatsapp.py`
- `adapters/persistence/notifications.py`
- `adapters/whatsapp_twilio/sender.py`
- `api/notifications/__init__.py`
- `api/notifications/routes.py`
- `web/src/components/MixedRecipientPicker.tsx`
- `web/src/components/MixedRecipientPicker.test.tsx`
- `web/src/pages/NotificationComposePage.tsx`
- `web/src/pages/NotificationComposePage.test.tsx`
- `tests/domain/test_notifications_service.py`
- `tests/adapters/persistence/test_notifications_repository.py`
- `tests/api/test_notifications_routes.py`

**Modified files:**
- `domain/models.py` (new enums: `NotificationType`, `DeliveryStatus`, `TargetType`; new dataclasses: `MessageTemplate`, `Notification`, `NotificationTarget`, `NotificationDelivery`, `NotificationStatusSummary` (code review))
- `ports/users.py` (`list_by_team_id`)
- `adapters/persistence/users.py` (`list_by_team_id` implementation)
- `api/dashboard/routes.py` (`GET /dashboard/notification-status`)
- `api/main.py` (registered `message_templates_router`, `notifications_router`)
- `docker/nginx/nginx.conf` (`/notifications`, `/message-templates` location blocks)
- `web/vite.config.ts` (dev-proxy entries for `/notifications`, `/message-templates`, `/dashboard/notification-status`)
- `web/src/pages/DashboardPage.tsx` (live notification-status tile + "Notifications" nav link)
- `web/src/pages/DashboardPage.test.tsx` (notification-status stub + new mapping tests)
- `web/src/router.tsx` (`/notifications/compose` route)
- `scripts/seed_demo_data.py` (seeds a demo `MessageTemplate` row)
- `tests/conftest.py` (`_clean_tables` now clears `notification_deliveries`, `notification_targets`, `notifications`, `message_templates`)

## Change Log

| Date | Change |
| --- | --- |
| 2026-07-21 | Implemented Story 4.1: Manual Notification compose/send — greenfield `Notification`/`NotificationDelivery`/`NotificationTarget`/`MessageTemplate` domain slice, cross-type recipient resolution shared by preview and send (AD-2), atomic per-delivery claim before WhatsApp dispatch, Twilio Content API adapter, `MixedRecipientPicker`/`NotificationComposePage` frontend, and the Dashboard's live notification-status tile. |
| 2026-07-21 | Code review pass: Dashboard status tile now aggregates worst-status-wins per Notification (was a single arbitrary delivery row); dispatch loop no longer loses already-sent outcomes on a non-Twilio exception; `resolve()` now excludes mobile-less users and skips expansion of an inactive Team/RecipientList; blank/whitespace template variable values rejected client- and server-side; live preview substitution fixed to a single regex pass; ineligible-count wording and the recipient-picker loading/zero-state hint improved. 7 new backend tests (401 total), 1 new frontend test (160 total); ruff, mypy, import-linter, tsc, eslint all clean. |
