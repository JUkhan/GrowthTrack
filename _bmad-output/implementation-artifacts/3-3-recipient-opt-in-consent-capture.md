---
baseline_commit: b7a17de
---

# Story 3.3: Recipient Opt-In Consent Capture

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an Administrator,
I want to capture, view, and revoke a Recipient's WhatsApp opt-in consent,
so that no one receives a message from GrowthTrack without recorded consent.

## Acceptance Criteria

1. **Given** a User with no recorded consent, **when** I record opt-in consent (with a timestamp), **then** that User becomes eligible to receive Scheduled or Manual notifications. [Source: epics.md#Story 3.3, ARCHITECTURE-SPINE.md#AD-9]
2. **Given** a User's consent is revoked, **when** the change is saved, **then** future sends to that User stop immediately, audit-logged co-transactionally. [Source: epics.md#Story 3.3, ARCHITECTURE-SPINE.md#AD-7, AD-9]
3. **Given** a User's phone number is changed, **when** saved, **then** existing consent is revoked automatically, and delivery is blocked until fresh consent is recorded for the new number. [Source: epics.md#Story 3.3, ARCHITECTURE-SPINE.md#AD-9]
4. **Given** a User's record, **when** viewed, **then** consent state and its timestamp are shown directly in the form, not a separate tab. [Source: epics.md#Story 3.3, ux-designs/EXPERIENCE.md#Directory form, UX-DR14]
5. **[Derived — the literal AC only covers "no recorded consent"; without an explicit guard, a duplicate grant either silently no-ops or, worse, violates the one-active-consent-per-User invariant with an unhandled 500]** **Given** a User who already has active consent, **when** an attempt is made to record consent again without first revoking it, **then** it is rejected as a conflict (`ConsentAlreadyActive`), backed by a DB-level partial unique index, not app logic alone — mirrors the exact `RecipientListNameTaken`-style guard-plus-index-backstop shape Story 3.2 established for "can't create a second active thing with the same identity." [Source: domain/recipients.py precedent (Story 3.2), ARCHITECTURE-SPINE.md#Core-entity relationships ERD (`OPT_IN_CONSENT` as a history entity — see Dev Notes)]
6. **[Derived — closes the symmetric gap: nothing in the literal ACs says what happens when there's nothing to revoke]** **Given** a User with no active consent, **when** an attempt is made to revoke consent, **then** it is rejected (`ConsentNotActive`) rather than silently no-op'd or crashing — guards a double-click/double-submit revoke.
7. **[Derived — an Administrator row always has `mobile: None` per Story 3.1's schema; consent exists to gate WhatsApp delivery, and an Administrator is never a WhatsApp recipient]** **Given** a User with no mobile number on file (in practice, an Administrator), **when** an attempt is made to grant or revoke their consent, **then** it is rejected (`ConsentTargetNotAddressable`) — the identical reasoning Story 3.2's AC #6 already applied to `RecipientList` membership, applied here to consent. In practice this is unreachable through the UI (Administrators are never editable via the Directory form — `RecipientsPage.tsx` already hides Edit for `role === 'administrator'`), so this is backend defense-in-depth, not a new frontend gate. [Source: domain/models.py#User.mobile, addendum.md#A5/A6]
8. **[Derived — EXPERIENCE.md's Component Patterns explicitly names the shared `status-badge` component as driving "Recipient opt-in state," which needs a glanceable home beyond one row's edit dialog]** **Given** the Users table, **when** displayed, **then** each row shows a Consent status badge (Opted In / Not Opted In) alongside the existing Status (Active/Inactive) column, so an Administrator can see who's opted in without opening every row's edit dialog. [Source: ux-designs/EXPERIENCE.md#Component Patterns, UX-DR3]
9. **[Derived — UX-DR25 requires copy to name the real cause/consequence, and AC #3's automatic revoke-on-phone-change is otherwise a silent surprise to the Administrator saving the form]** **Given** an Administrator edits a User's Mobile field in the Directory form, **and** that User currently has active consent, **when** the new value differs from the original, **then** an inline notice explains that saving will revoke existing consent and require a fresh opt-in before delivery resumes — no such notice is shown if the User was never opted in (nothing would actually be revoked). [Source: UX-DR25, ARCHITECTURE-SPINE.md#AD-9]

## Tasks / Subtasks

- [x] Task 1: Alembic migration — `opt_in_consents` (AC: #1, #2, #3, #5, #6)
  - [x] Run `uv run alembic heads` first to confirm the current head is `976cabf50f32` (Story 3.2's migration) — do not hand-guess; then `uv run alembic revision -m "opt in consents"` with `down_revision = "976cabf50f32"`.
  - [x] `opt_in_consents` is a **history** table — one User can have many rows over time (one per grant), but at most one *active* (non-revoked) row at any moment. Get the partial unique index right in this migration, first time, same discipline Story 3.2 already applied for `recipient_lists.name` (Story 3.1 only got there after a follow-up migration):
    ```python
    op.create_table(
        "opt_in_consents",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("mobile", sa.String(), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_opt_in_consents_user_id_active_uq",
        "opt_in_consents",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    ```
    `mobile` is a snapshot of the User's mobile number *at the moment consent was granted* (PRD assumption: "consent is tied to the number, not the person") — this is why phone-number changes must revoke it: the old row's `mobile` no longer matches the User's current number.
  - [x] No `ON DELETE CASCADE` on the `user_id` FK — `User` is soft-deleted, never hard-deleted (AD-4), so the default `NO ACTION` never actually fires (same reasoning `recipient_list_members`' FK already uses).
  - [x] Downgrade: `op.drop_index("ix_opt_in_consents_user_id_active_uq", table_name="opt_in_consents")` then `op.drop_table("opt_in_consents")`.

- [x] Task 2: `domain/models.py` — new `OptInConsent` entity (AC: #1, #2, #3)
  - [x] **Do not add consent fields directly onto `User`.** `entities.md`/`reconcile-entities.md` (PRD-side, pre-architecture) sketch consent as a plain field on `User`, but `ARCHITECTURE-SPINE.md`'s ERD explicitly supersedes that: `USER ||--o{ OPT_IN_CONSENT : "consent history"` — a separate, historized entity. The architecture spine is the later, authoritative reconciliation; follow the ERD, not the PRD's provisional sketch. This is the single most important structural decision in this story — flag it in code review if anyone suggests collapsing it back onto `User`.
  - [x] Add near `AuditLogEntry`/`Team`:
    ```python
    @dataclass
    class OptInConsent:
        id: uuid.UUID
        user_id: uuid.UUID
        mobile: str
        granted_at: datetime
        revoked_at: datetime | None = None
    ```

- [x] Task 3: `ports/consent.py` (new file) (AC: #1, #2, #3, #5, #6)
  - [x] Same `Any`-typed convention as `ports/recipient_lists.py` (ports cannot import `domain`):
    ```python
    class OptInConsentRepository(ABC):
        @abstractmethod
        async def get_active(self, user_id: uuid.UUID) -> Any | None: ...

        @abstractmethod
        async def get_active_by_user_ids(self, user_ids: list[uuid.UUID]) -> dict[uuid.UUID, Any]:
            """Batched active-consent lookup keyed by user_id — avoids the
            N+1 shape Story 3.2's RecipientList.list_all_full() was written
            to avoid for membership. Used by GET /users."""
            ...

        @abstractmethod
        async def grant(self, user_id: uuid.UUID, mobile: str) -> Any: ...

        @abstractmethod
        async def revoke_active(self, user_id: uuid.UUID) -> bool:
            """Revokes the current active row, if any (sets revoked_at).
            Returns whether a row was actually revoked, so callers (the
            phone-number-change path in UserDirectoryService.update_user)
            know whether an audit entry is warranted — don't audit a
            no-op."""
            ...
    ```

- [x] Task 4: `adapters/persistence/consent.py` (new file) (AC: #1, #2, #3, #5, #6)
  - [x] `OptInConsentModel` (`opt_in_consents` table) + a module-level `_to_domain` free function (Story 2.3/3.1/3.2 precedent — not a `@staticmethod`).
  - [x] `get_active(user_id)`: `select(...).where(user_id == :id, revoked_at.is_(None))`, `scalar_one_or_none()`.
  - [x] `get_active_by_user_ids(user_ids)`: short-circuit to `{}` on empty input (an empty `IN ()` is either invalid or always-false depending on dialect — don't rely on it, same discipline as `get_many_by_ids`); otherwise one bulk `select(...).where(user_id.in_(user_ids), revoked_at.is_(None))`, build `{row.user_id: _to_domain(row) for row in ...}`.
  - [x] `grant(user_id, mobile)`: builds a new `OptInConsentModel(id=uuid4(), user_id=..., mobile=..., granted_at=now, revoked_at=None)`, `session.add(...)`, then an explicit `await self._session.flush()` — Story 3.2's real code-review-caught bug was exactly a missing flush before a later plain `INSERT`/`UPDATE` that doesn't trigger ORM autoflush; be explicit here too rather than relying on autoflush timing.
  - [x] `revoke_active(user_id) -> bool`: a single `UPDATE opt_in_consents SET revoked_at = :now WHERE user_id = :id AND revoked_at IS NULL` (atomic conditional update, not read-then-write — same shape as `increment_failed_login_count`'s `RETURNING` pattern, but here the signal is `result.rowcount > 0`, no `RETURNING` needed since the caller only needs to know *whether* it fired).

- [x] Task 5: `domain/recipients.py` — extend with `OptInConsentService` + `UserDirectoryService` phone-change hook (AC: all)
  - [x] **Extend this existing file** — CAP-5 fixes `domain/recipients` for the whole Recipient-directory-management capability; `OptInConsentService` joins `UserDirectoryService`/`TeamDirectoryService`/`RecipientListDirectoryService` as a fourth class in the same module, same as Story 3.2's addition pattern.
  - [x] New exceptions (module-level, same style as the existing ones): `ConsentAlreadyActive`, `ConsentNotActive`, `ConsentTargetNotAddressable`.
  - [x] `UserDirectoryService.__init__` gains a new constructor parameter: `consents: OptInConsentRepository` (stored as `self._consents`). This means all three existing call sites in `api/recipients/routes.py` (`create_user`, `update_user`, `remove_user` routes) must pass a `SqlAlchemyOptInConsentRepository(session)` into the constructor, even though `create_user`/`remove_user` don't otherwise touch it — one shared constructor across the class's methods, matching the existing pattern (`last_admin_guard` is already passed in for the same reason, used only by `remove_user`).
  - [x] `UserDirectoryService.update_user` — insert the phone-change hook using the `target` object it already fetches at the top of the method (AC #3):
    ```python
    mobile_changed = target.mobile != mobile
    await self._ensure_team_active(team_id)
    existing = await self._users.get_by_mobile(mobile)
    if existing is not None and existing.id != user_id:
        raise MobileTaken()
    await self._users.update_directory_fields(user_id, name, mobile, team_id)
    if mobile_changed:
        revoked = await self._consents.revoke_active(user_id)
        if revoked:
            await self._audit_log.add(
                AuditLogEntry(
                    id=uuid.uuid4(),
                    actor_user_id=actor_user_id,
                    action="user.consent_auto_revoked",
                    entity_type="User",
                    entity_id=user_id,
                    details={"reason": "mobile_number_changed"},
                    created_at=datetime.now(UTC),
                )
            )
    await self._audit_log.add(  # existing "user.updated" entry, unchanged
        ...
    )
    ```
    Compute `mobile_changed` from `target.mobile` (the pre-update snapshot already loaded) vs. the incoming `mobile` param — do not re-fetch. Only write the `user.consent_auto_revoked` audit entry when `revoke_active` actually revoked something (`revoked is True`) — a mobile "change" to the exact same value, or a User with no prior consent, must not produce a spurious audit entry. This yields **two** audit entries in one request when mobile genuinely changes on a previously-opted-in User (`user.consent_auto_revoked` + `user.updated`), both inside the same transaction (AD-7).
  - [x] `remove_user` (soft-delete) deliberately does **not** touch consent — a removed User's lingering active-consent row is harmless (Epic 4's recipient resolution will gate on `User.status` independently of consent), mirroring Story 3.2's identical reasoning for leaving `RecipientList` membership rows in place on soft-delete. Don't add logic here.
  - [x] `OptInConsentService(users: UserRepository, consents: OptInConsentRepository, audit_log: AuditLogRepository)`:
    - `async def grant_consent(self, user_id: uuid.UUID, actor_user_id: uuid.UUID) -> OptInConsent` — load `target = await self._users.get_by_id(user_id)`, raise `UserNotFound()` if absent; raise `ConsentTargetNotAddressable()` if `target.mobile is None` (AC #7); raise `ConsentAlreadyActive()` if `await self._consents.get_active(user_id) is not None` (AC #5); otherwise `consent = await self._consents.grant(user_id, target.mobile)`; audit `action="consent.granted"`, `entity_type="User"`, `entity_id=user_id`, `details={"mobile": target.mobile}`; return `consent`.
    - `async def revoke_consent(self, user_id: uuid.UUID, actor_user_id: uuid.UUID) -> None` — load `target`, raise `UserNotFound()` if absent; raise `ConsentTargetNotAddressable()` if `target.mobile is None` (symmetric with grant, AC #7); `active = await self._consents.get_active(user_id)`, raise `ConsentNotActive()` if `active is None` (AC #6); `await self._consents.revoke_active(user_id)`; audit `action="consent.revoked"`, `entity_type="User"`, `entity_id=user_id`, `details=None` (AC #2).
    - Deliberately does **not** check `target.status` (active/inactive) — consent is a User-level attribute independent of directory status; an inactive User is excluded from any send at Epic 4's recipient-resolution step regardless of consent state, so gating consent actions on status here would be a redundant, premature check.

- [x] Task 6: `api/recipients/routes.py` — embed consent in `DirectoryUserResponse` + new `/users/{user_id}/opt-in-consent` routes (AC: all)
  - [x] New imports needed in this file (none of these are currently present — check before assuming a bare `datetime`/`OptInConsentService` reference will resolve): `from datetime import datetime` (for `consent_recorded_at`/`granted_at` field types); `from adapters.persistence.consent import SqlAlchemyOptInConsentRepository`; add `ConsentAlreadyActive, ConsentNotActive, ConsentTargetNotAddressable, OptInConsentService` to the existing `from domain.recipients import (...)` block.
  - [x] Extend `DirectoryUserResponse`:
    ```python
    class DirectoryUserResponse(BaseModel):
        ...  # existing fields unchanged
        consent_status: Literal["opted_in", "not_opted_in"]
        consent_recorded_at: datetime | None
    ```
  - [x] New response model: `class OptInConsentResponse(BaseModel): user_id: uuid.UUID; granted_at: datetime`.
  - [x] `_to_directory_user_response(user, team_names, active_consent)` gains a third parameter (`active_consent: OptInConsent | None`); sets `consent_status="opted_in" if active_consent else "not_opted_in"`, `consent_recorded_at=active_consent.granted_at if active_consent else None`.
  - [x] `create_user` route: pass `active_consent=None` directly (a freshly created User can never have one — no repository call needed).
  - [x] `list_users` route: instantiate `consents = SqlAlchemyOptInConsentRepository(session)`; batch-fetch `consent_by_user = await consents.get_active_by_user_ids([u.id for u in all_users])` **once**, then `active_consent=consent_by_user.get(user.id)` per row — do not call `get_active` once per row in a loop (the exact N+1 shape Story 3.2's `list_all_full()` was written to avoid).
  - [x] `update_user` route: after `service.update_user(...)` returns (reflecting any auto-revoke that just happened), `active_consent = await consents.get_active(user_id)` (single-row read, acceptable) so the response reflects the just-applied state.
  - [x] `UserDirectoryService(...)` construction in `create_user`/`update_user`/`remove_user` routes: add `SqlAlchemyOptInConsentRepository(session)` as the new `consents` argument at all three call sites (Task 5's constructor change).
  - [x] New error helpers, same style as `_member_inactive`/`_recipient_list_name_taken`:
    ```python
    def _consent_already_active() -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "consent_already_active", "message": "This User already has active WhatsApp consent recorded", "details": None},
        )

    def _consent_not_active() -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "consent_not_active", "message": "This User has no active WhatsApp consent to revoke", "details": None},
        )

    def _consent_not_addressable() -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "consent_not_addressable", "message": "This User has no mobile number on file and can't receive WhatsApp sends", "details": None},
        )
    ```
  - [x] New routes on the **existing** `users_router` (a consent grant/revoke is a User sub-resource, not a new top-level resource — no new router, no new prefix):
    ```python
    @users_router.post(
        "/{user_id}/opt-in-consent", response_model=OptInConsentResponse, status_code=status.HTTP_201_CREATED,
    )
    async def grant_opt_in_consent(
        user_id: uuid.UUID,
        current_user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_db),
    ) -> OptInConsentResponse:
        users = SqlAlchemyUserRepository(session)
        consents = SqlAlchemyOptInConsentRepository(session)
        audit_log = SqlAlchemyAuditLogRepository(session)
        service = OptInConsentService(users, consents, audit_log)

        try:
            consent = await service.grant_consent(user_id=user_id, actor_user_id=current_user.id)
        except UserNotFound:
            await session.commit()
            raise _not_found("User") from None
        except ConsentTargetNotAddressable:
            await session.commit()
            raise _consent_not_addressable() from None
        except ConsentAlreadyActive:
            await session.commit()
            raise _consent_already_active() from None

        try:
            await session.commit()
        except IntegrityError:
            # The get_active() pre-check is advisory (same NFR-8 proportionality
            # reasoning as MobileTaken/RecipientListNameTaken) — the partial
            # unique index (ix_opt_in_consents_user_id_active_uq) is the real
            # backstop for a genuine concurrent double-grant.
            await session.rollback()
            raise _consent_already_active() from None

        return OptInConsentResponse(user_id=user_id, granted_at=consent.granted_at)

    @users_router.delete("/{user_id}/opt-in-consent", status_code=status.HTTP_204_NO_CONTENT)
    async def revoke_opt_in_consent(
        user_id: uuid.UUID,
        current_user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_db),
    ) -> None:
        users = SqlAlchemyUserRepository(session)
        consents = SqlAlchemyOptInConsentRepository(session)
        audit_log = SqlAlchemyAuditLogRepository(session)
        service = OptInConsentService(users, consents, audit_log)

        try:
            await service.revoke_consent(user_id=user_id, actor_user_id=current_user.id)
        except UserNotFound:
            await session.commit()
            raise _not_found("User") from None
        except ConsentTargetNotAddressable:
            await session.commit()
            raise _consent_not_addressable() from None
        except ConsentNotActive:
            await session.commit()
            raise _consent_not_active() from None

        await session.commit()
    ```
  - [x] **No `api/main.py`, `docker/nginx/nginx.conf`, or `web/vite.config.ts` changes needed.** Unlike Story 3.1/3.2 (new top-level resources), these routes extend the already-registered `users_router` under the already-proxied `/users/` prefix (`location /users/ { ... }` in nginx.conf, `'/users': 'http://localhost:8000'` in vite.config.ts both already match `/users/{id}/opt-in-consent` as a sub-path) — verify this by testing the route through the full stack, don't skip verification just because no config diff is expected.

- [x] Task 7: Frontend — consent in the Directory form + Users table (AC: #4, #8, #9)
  - [x] `web/src/pages/UserFormDialog.tsx` — extend `UserFormValues`:
    ```typescript
    export interface UserFormValues {
      id: string
      name: string
      mobile: string
      role: 'sales_user' | 'manager'
      teamId: string
      consentStatus: 'opted_in' | 'not_opted_in'
      consentRecordedAt: string | null
    }
    ```
    Add local state seeded from `user` on open (same `useEffect` that resets `name`/`mobile`/etc.): `consentStatus`/`consentRecordedAt`. This local copy is what the consent section renders and what grant/revoke actions update directly from their own response — it is **not** re-derived from the `user` prop after a grant/revoke, since the parent's `editingUser` object isn't automatically refreshed while the dialog stays open (only a fresh `Edit` click reseeds it).
  - [x] Render a "Consent" section only when `user !== null` (editing an existing User — mirrors the existing `{!user && <Role select>}` pattern, inverted): a `StatusBadge` (`status="success"` + check icon + "Opted In" + a formatted `consentRecordedAt`, or `status="warning"` + an appropriate icon + "Not Opted In"), plus one action button:
    - Not opted in → "Record Consent" button. On click: `POST /users/{id}/opt-in-consent`; on success, set local `consentStatus='opted_in'`, `consentRecordedAt=<response.granted_at>` directly from the JSON body (no need to refetch); call `onConsentChanged?.()` (new prop, see below) so the underlying table row updates in the background; on failure (409 `consent_already_active`, 422 `consent_not_addressable`), surface `body.error.message` in the existing `error` `Alert`.
    - Opted in → "Revoke Consent" button, `color="error"`. Opens a `ConfirmationDialog` (reuse the shared component) with a real consequence: e.g. `` `This immediately stops all future WhatsApp notifications to ${name || 'this User'}.` `` (UX-DR15/UX-DR25 — never "Are you sure?"). On confirm: `DELETE /users/{id}/opt-in-consent`; on success, set local `consentStatus='not_opted_in'`, `consentRecordedAt=null`; call `onConsentChanged?.()`; on failure (409 `consent_not_active`), surface the message.
    - Manage a separate `consentActionSubmitting` boolean, distinct from the main form's `submitting` — granting/revoking consent must not disable or interact with the Name/Mobile/Team Save button, and vice versa.
  - [x] Add prop `onConsentChanged?: () => void` to `UserFormDialogProps` — a lightweight "please reload the Users list" signal, deliberately **not** the same as `onSaved` (`onSaved` closes the dialog; a consent action should not close the dialog, since the Administrator may still be reviewing/editing other fields).
  - [x] Mobile-change notice (AC #9): when `user !== null`, `user.consentStatus === 'opted_in'`, and the current `mobile` input value differs from `user.mobile` (the original, unedited value — not the live `mobile` state compared to itself), show inline helper text under the Mobile field, e.g. *"Saving this number will revoke {name}'s existing WhatsApp consent — they'll need to opt in again before receiving messages."* Do not show this when the User was never opted in (nothing would actually be revoked, so the warning would be inaccurate).
  - [x] `web/src/pages/RecipientsPage.tsx`:
    - Extend `DirectoryUser` interface: `consent_status: 'opted_in' | 'not_opted_in'`, `consent_recorded_at: string | null`.
    - Add a `consentBadge(status)` helper alongside the existing `statusBadge(status)` — pick icons from DESIGN.md's check/clock/alert-triangle vocabulary (e.g. `CheckCircleIcon`/`success` for opted-in, a distinct icon such as `WarningAmberIcon`/`warning` for not-opted-in — deliberately different from the Active/Inactive column's icon pair so the two badge columns aren't visually indistinguishable at a glance).
    - Add a `{ key: 'consent', header: 'Consent', render: (row) => consentBadge(row.consent_status) }` column to `userColumns`, positioned after `status` and before `actions` (AC #8).
    - When opening the edit dialog (`setEditingUser({...})`), include `consentStatus: row.consent_status, consentRecordedAt: row.consent_recorded_at`.
    - Pass `onConsentChanged={loadUsers}` to `<UserFormDialog />`.
  - [x] No mockup exists for the consent section (same gap Story 3.1/3.2 already navigated) — build from `EXPERIENCE.md`'s Directory form / status-badge / Confirmation dialog descriptions, not a pixel reference.

- [x] Task 8: Tests (AC: all)
  - [x] `tests/domain/test_recipients_service.py` — extend:
    - `OptInConsentService`: grant success + `consent.granted` audit entry with correct `mobile`; grant when already active raises `ConsentAlreadyActive`; grant for a User with `mobile=None` raises `ConsentTargetNotAddressable`; grant for a nonexistent user raises `UserNotFound`; revoke success + `consent.revoked` audit entry; revoke when nothing active raises `ConsentNotActive`; revoke for a `mobile=None` User raises `ConsentTargetNotAddressable`; revoke for a nonexistent user raises `UserNotFound`.
    - `UserDirectoryService.update_user`: changing `mobile` on a previously-opted-in User revokes the active consent (assert the fake consent repo's `revoke_active` was called and returned `True`-driven audit entry `user.consent_auto_revoked` was written) *in addition to* the existing `user.updated` entry — two audit entries from one call; changing `mobile` on a User with **no** active consent writes only `user.updated`, no `user.consent_auto_revoked` (assert on the fake `AuditLogRepository`'s recorded entries, not just call count); leaving `mobile` unchanged never calls `revoke_active` at all.
  - [x] `tests/adapters/persistence/test_opt_in_consent_repository.py` (new) — `grant` (creates row, `revoked_at is None`); `get_active` (found active / found-but-revoked returns `None` / no row returns `None`); `get_active_by_user_ids` (multiple users mixed active/revoked/none, correct per-user grouping, empty input returns `{}` without querying); `revoke_active` (returns `True` and sets `revoked_at` when an active row exists; returns `False` and is a no-op when none exists; calling it twice in a row is safe — second call returns `False`); a direct-SQL test confirming `ix_opt_in_consents_user_id_active_uq` rejects a second concurrently-inserted active row for the same `user_id` (raises `IntegrityError`) — this is the DB-level backstop for `ConsentAlreadyActive`, exercise it for real, don't just trust the migration DDL.
  - [x] `tests/api/test_recipients_routes.py` — extend: `POST /users/{id}/opt-in-consent` → 201 + `granted_at` in body; 404 for a nonexistent user; 422 `consent_not_addressable` against a seeded Administrator; 409 `consent_already_active` on a second grant without revoking; `DELETE /users/{id}/opt-in-consent` → 204; 409 `consent_not_active` when nothing to revoke; 404 for a nonexistent user; 401 on both routes when unauthenticated (AD-8). `GET /users` response includes `consent_status`/`consent_recorded_at` correctly per row (opted-in vs never-opted-in, in the same call — proves the batched lookup is per-user, not a shared/leaked value). `PATCH /users/{id}` changing `mobile` on a previously-opted-in seeded User returns `consent_status: "not_opted_in"` in the same response (proves the route re-reads post-auto-revoke state, not a stale pre-update value).
  - [x] `tests/conftest.py` — `_clean_tables` must `DELETE FROM opt_in_consents` before `DELETE FROM users` (FK to `users.id`, same reasoning already documented for `password_reset_tokens`/`recipient_list_members`) — add it alongside those two lines.
  - [x] Frontend: `UserFormDialog.test.tsx` — extend: consent section renders "Opted In" + formatted timestamp for an opted-in `user`, "Not Opted In" (no timestamp) otherwise; consent section is absent entirely when `user === null` (create mode); clicking "Record Consent" POSTs to `/users/{id}/opt-in-consent` and flips the local badge to "Opted In" without closing the dialog; clicking "Revoke Consent" opens the `ConfirmationDialog` with the real consequence text, DELETEs on confirm, flips the badge to "Not Opted In"; the mobile-change notice appears only when editing an opted-in user with an edited (different-from-original) mobile value, and is absent for a not-opted-in user even with an edited mobile value.
  - [x] `web/src/pages/RecipientsPage.test.tsx` — extend: Users table renders a Consent column badge per row from a mocked `GET /users` response; editing a User seeds the dialog's consent fields from the row; a consent action inside the dialog triggers a `GET /users` reload (via `onConsentChanged`) without the dialog closing.
  - [x] `uv run pytest -q`, `uv run ruff check .`, `uv run mypy .`, `uv run lint-imports` after backend changes; `npx tsc -b`, `npx eslint .`, `npx vitest run` after frontend changes — same four-plus-three gate every prior story ran clean against.

### Review Findings

- [x] [Review][Decision] "Opted In" badge visually collides with "Active" status badge — Both `statusBadge('active')` and `consentBadge('opted_in')` in `web/src/pages/RecipientsPage.tsx` rendered `StatusBadge status="success" icon={<CheckCircleIcon />}`, so an Active + Opted In row showed two identical green check-circle chips side by side. Task 7 explicitly requires the Consent column icon pair be "deliberately different from the Active/Inactive column's icon pair." Resolved: user chose to keep the green "success" color and swap the icon. Fixed by using `MarkChatReadIcon` (consent/messaging-specific) for "Opted In" instead of `CheckCircleIcon`, in both `RecipientsPage.tsx`'s `consentBadge()` and `UserFormDialog.tsx`'s inline Consent section badge.
- [x] [Review][Patch] Concurrent double-grant returns 500 instead of 409 [api/recipients/routes.py:476-498, adapters/persistence/consent.py:74-81] — `SqlAlchemyOptInConsentRepository.grant()` calls `await self._session.flush()` immediately, so the partial-unique-index `IntegrityError` on a genuine concurrent double-grant fires inside `service.grant_consent()`, inside the route's first `try/except` (which only caught `UserNotFound`/`ConsentTargetNotAddressable`/`ConsentAlreadyActive`) — not the second `try: await session.commit() except IntegrityError` block below it, which never ran. This contradicted AC #5's explicit requirement that the partial unique index be "the real backstop" for a concurrent double-grant. Fixed: merged into a single `try` that also catches `IntegrityError` around `grant_consent(...)` itself, not just the later commit.
- [x] [Review][Patch] Revoke race can log a spurious `consent.revoked` audit entry [domain/recipients.py:490-512] — `OptInConsentService.revoke_consent` discarded the boolean return value of `self._consents.revoke_active(user_id)` and unconditionally wrote the audit entry. Under two concurrent revoke calls, the second request's `get_active()` pre-check could still see an active row before the first commits, so its `revoke_active()` UPDATE affected zero rows once unblocked — yet the route still returned 204 and logged `consent.revoked` for an action that didn't happen. Fixed: now checks the return value and raises `ConsentNotActive` when `revoke_active` returns `False`, mirroring `UserDirectoryService.update_user`'s auto-revoke hook in the same file.
- [x] [Review][Patch] Mobile-change consent warning uses stale prop instead of live consent state [web/src/pages/UserFormDialog.tsx:218] — The Mobile field's helper text checked `user.consentStatus === 'opted_in'` (the prop frozen at dialog-open time) instead of the local `consentStatus` state that `handleRecordConsent`/`handleRevokeConsent` actually update. If an Administrator granted consent via the in-dialog "Record Consent" button and then edited Mobile in the same session, the warning that saving will revoke the just-granted consent never appeared, even though it would happen. Fixed: ternary now reads `consentStatus` (local state) instead of `user.consentStatus`.

- [x] [Review][Defer] Consent grant/revoke handlers lack an unmount guard [web/src/pages/UserFormDialog.tsx:95-137] — deferred, pre-existing: `handleSubmit` in the same component already lacks an `isMountedRef`-style guard (unlike `RecipientsPage.tsx`'s load functions, which do have one), so this is consistent with an existing gap in this file rather than a regression introduced by this diff.



- **`OptInConsent` is a separate, historized entity — not fields on `User`.** This is the one architectural decision in this story most likely to be gotten wrong: `entities.md`/`reconcile-entities.md` (PRD-side documents, written before the architecture spine) sketch consent as a simple boolean+timestamp on `User`. `ARCHITECTURE-SPINE.md`'s ERD (`USER ||--o{ OPT_IN_CONSENT : "consent history"`) is the later, authoritative reconciliation and explicitly models it as its own table with a one-to-many relationship. Follow the ERD. The "one active row per User" invariant is enforced by a partial unique index (`ix_opt_in_consents_user_id_active_uq` on `user_id WHERE revoked_at IS NULL`), not a `User.opted_in` boolean.
- **Consent is tied to the number, not just the person.** `OptInConsent.mobile` snapshots the number consent was granted for. This is *why* a phone-number change must revoke it (AC #3) — the old consent row's `mobile` no longer describes the User's current number, so it can no longer imply consent for the new one. A fresh grant after a mobile change stamps the new number onto a new row.
- **`UserDirectoryService.update_user` owns the phone-change-revokes-consent side effect**, not the route layer or a separate orchestration step — it already loads the pre-update `target` (giving it `target.mobile` to diff against) and already writes audit entries inside one call (AD-7's co-transactionality). Story 3.1 explicitly deferred this exact hook to this story (see Story 3.1's Dev Notes / this story's own git-intelligence note below) — `update_user` today does nothing consent-related.
- **`OptInConsentService` is a fourth class in `domain/recipients.py`**, joining `UserDirectoryService`/`TeamDirectoryService`/`RecipientListDirectoryService` — CAP-5 fixes this file (and `api/recipients/routes.py`) as the location for the whole Recipient-directory-management capability. Do not create `domain/consent.py`.
- **Consent grant/revoke deliberately does not check `User.status` (active/inactive).** Consent is a User-level attribute orthogonal to directory status; Epic 4's recipient-resolution step (not yet built) will gate delivery on `User.status == ACTIVE` independently of consent, so checking status here too would be a redundant, premature coupling to a capability that doesn't exist yet.
- **Removing/deactivating a User does not auto-revoke consent.** A lingering active-consent row on a soft-deleted User is harmless for the same reason above — mirrors Story 3.2's identical "membership rows are left in place on soft-delete" reasoning for `RecipientList`.
- **No new router, no new Nginx/vite proxy entries.** Unlike Story 3.1 (`/users`, `/teams`) and Story 3.2 (`/recipient-lists`), the two new routes (`POST`/`DELETE /users/{id}/opt-in-consent`) are sub-paths of the already-proxied `/users/` prefix — confirm this holds end-to-end rather than assuming it (Story 3.1's code review caught exactly this class of gap for a *new* prefix; this story's risk is the opposite mistake — assuming an existing prefix already covers a deeper sub-path without checking).
- **Frontend: `onConsentChanged` is intentionally not `onSaved`.** `onSaved` closes the dialog (used by the Name/Mobile/Team form submit). A consent grant/revoke should refresh the underlying table in the background without closing the dialog the Administrator is still using — conflating the two would close the dialog out from under someone who just clicked "Record Consent" while still editing other fields.
- **Consent-section visibility mirrors the existing Role-field pattern, inverted.** Role is hidden when editing (`!user`); consent is hidden when creating (`user === null`) — a User must exist before it can have consent.

### Project Structure Notes

- New backend files: `ports/consent.py`, `adapters/persistence/consent.py`, `alembic/versions/<new>_opt_in_consents.py`, `tests/adapters/persistence/test_opt_in_consent_repository.py`.
- Modified backend files: `domain/models.py` (`OptInConsent`), `domain/recipients.py` (new `OptInConsentService` + 3 new exceptions + `UserDirectoryService.__init__`/`update_user` changes), `api/recipients/routes.py` (2 new routes, `DirectoryUserResponse`/`OptInConsentResponse`, 3 new error helpers, updated `UserDirectoryService(...)` call sites), `tests/domain/test_recipients_service.py`, `tests/api/test_recipients_routes.py`, `tests/conftest.py` (`_clean_tables` addition).
- Modified frontend files: `web/src/pages/UserFormDialog.tsx` (consent section, mobile-change notice, `onConsentChanged` prop), `web/src/pages/RecipientsPage.tsx` (Consent column, dialog wiring), `web/src/pages/UserFormDialog.test.tsx`, `web/src/pages/RecipientsPage.test.tsx`.
- No changes to `docker/nginx/nginx.conf`, `web/vite.config.ts`, `api/main.py`, `ports/recipient_lists.py`/`adapters/persistence/recipient_lists.py` (Story 3.2's files, untouched), `scheduler/`, `adapters/whatsapp_twilio/`, `adapters/source_system/` — this story stays entirely within CAP-5's boundary, touching only the User sub-resource.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 3.3: Recipient Opt-In Consent Capture] (all 4 literal ACs)
- [Source: _bmad-output/planning-artifacts/prds/prd-GrowthTrack-2026-07-14/prd.md#FR-10] ("System captures and records a Recipient's opt-in consent before enabling WhatsApp delivery; opt-out immediately stops future sends; consent state is visible in the Recipient directory")
- [Source: _bmad-output/planning-artifacts/prds/prd-GrowthTrack-2026-07-14/addendum.md#A3] (FR-10's origin: Meta/WhatsApp's business-messaging opt-in policy — a general opt-in suffices, no WhatsApp-specific language required, but the business must be named and an opt-out path provided)
- [Source: ARCHITECTURE-SPINE.md#AD-9] ("Consent state is checked inside the same recipient-resolution step AD-2 uses, before a `NotificationDelivery` row is created — never as an after-the-fact filter at dispatch time... Changing a `User`'s phone number revokes existing consent; delivery to that `User` is blocked until fresh consent is recorded.") — binds FR-9, FR-10, CAP-3, CAP-4.
- [Source: ARCHITECTURE-SPINE.md#AD-7] (co-transactional audit write — "opt-in/out state (AD-9)" is explicitly named as one of the mutation types this rule covers)
- [Source: ARCHITECTURE-SPINE.md#AD-4] (`User` soft-delete via `Status`/active flag; never hard-deleted, so `OptInConsent` history is never orphaned)
- [Source: ARCHITECTURE-SPINE.md#Core-entity relationships ERD] (`USER ||--o{ OPT_IN_CONSENT : "consent history"` — the authoritative structural decision this story implements; supersedes `entities.md`/`reconcile-entities.md`'s simpler single-field sketch)
- [Source: ARCHITECTURE-SPINE.md#Capability → Architecture Map] (CAP-5 fixes `api/recipients`, `domain/recipients` as this story's file locations too — same as Stories 3.1/3.2)
- [Source: ARCHITECTURE-SPINE.md#Consistency Conventions] (timestamps ISO 8601 UTC always; `{error:{code,message,details}}` envelope; all writes go through the domain service layer)
- [Source: domain/recipients.py, domain/models.py, ports/recipient_lists.py, adapters/persistence/recipient_lists.py] (the exact existing patterns this story mirrors: service structure, co-transactional audit writes, partial-unique-index-backed conflict guards, `_to_domain` free functions, explicit post-`add()` flush)
- [Source: alembic/versions/976cabf50f32_recipient_lists_and_membership.py] (current migration head this story's new migration chains from; the partial-unique-index-from-the-start pattern this story's migration adopts)
- [Source: api/recipients/routes.py, api/main.py] (router-per-resource-in-one-file convention — this story adds to the existing `users_router` rather than creating a new one; typed-exception-to-HTTPException mapping; `IntegrityError` race backstop)
- [Source: ux-designs/ux-GrowthTrack-2026-07-14/EXPERIENCE.md#Directory form] ("Recipient add/edit validates phone-number uniqueness inline... and surfaces opt-in/consent state with its timestamp directly in the form, not hidden behind a separate tab")
- [Source: ux-designs/ux-GrowthTrack-2026-07-14/EXPERIENCE.md#Component Patterns] (status-badge component named as driving "Recipient opt-in state" — basis for AC #8's Consent column)
- [Source: UX-DR14, UX-DR15, UX-DR25] (consent-in-form not a tab; shared Confirmation dialog naming the real consequence for opt-out; copy names the actual cause/consequence, never a generic "Are you sure?")
- [Source: web/src/pages/UserFormDialog.tsx, RecipientsPage.tsx, ConfirmationDialog.tsx, StatusBadge.tsx] (existing components this story composes, does not rebuild)
- [Source: _bmad-output/implementation-artifacts/3-1-manage-users-sales-teams.md] (`update_user`'s current shape, which this story extends; the mobile-uniqueness-on-blur pattern this story's mobile-change detection sits alongside)
- [Source: _bmad-output/implementation-artifacts/3-2-manage-recipient-groups-channels.md] (the RecipientList precedent for: a fourth-class-in-one-file addition, partial-unique-index-backed conflict guards, explicit post-add() flush bug class, N+1-avoidance via batched lookups, soft-delete-leaves-related-rows-in-place reasoning)
- [Source: _bmad-output/implementation-artifacts/deferred-work.md] (no open item from Story 3.1/3.2's code review touches consent/opt-in/phone-number directly beyond what's already cited above — this story starts clean)

### Git Intelligence

- `HEAD` is `b7a17de` ("Story 3.2: manage recipient groups & channels"), working tree clean. Migration chain currently ends at `976cabf50f32` — this story's new migration must set `down_revision = "976cabf50f32"` (confirm with `uv run alembic heads` before writing it, don't hand-guess).
- Commit style: one commit per logical unit of work, imperative summary line, ending with the `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>` trailer.
- Every prior story's Debug Log ran `uv run pytest -q`, `uv run ruff check .`, `uv run mypy .`, `uv run lint-imports` clean (backend) plus `npx tsc -b`, `npx eslint .`, `npx vitest run` clean (frontend) before being marked `done` — run the same seven before considering this story complete. `lint-imports` matters here too: `domain/recipients.py`'s new class and `UserDirectoryService`'s new dependency must only import from `ports/`, never `adapters/`/`api/` (AD-1).
- Stories 3.1 and 3.2's own code-review findings are the richest source of "mistakes already made once in this exact directory-CRUD shape" — this story's tasks pre-empt the same classes again: partial index from the start (Task 1), explicit flush after `session.add()` (Task 4), N+1-avoidance via batched lookup (Task 6), and an `IntegrityError` backstop on every guard that has a DB-level index behind it (Task 6) — rather than requiring a second review pass to catch them again.

## Change Log

- 2026-07-20: Implemented Story 3.3 — Recipient Opt-In Consent Capture backend (migration, `OptInConsent` domain entity, repository, `OptInConsentService`, phone-change auto-revoke hook, REST routes) and frontend (Consent section + mobile-change notice in `UserFormDialog`, Consent column in `RecipientsPage`). All 8 tasks complete, all 9 ACs satisfied. Full backend (`pytest`/`ruff`/`mypy`/`lint-imports`) and frontend (`vitest`/`eslint`/`tsc`) gates green.

## Dev Agent Record

### Agent Model Used

Claude Sonnet 5

### Debug Log References

- `uv run alembic heads` confirmed `976cabf50f32` as the head before generating the new migration; `uv run alembic revision -m "opt in consents"` produced `1dfe4d12bdee` with `down_revision` auto-set correctly.
- `uv run alembic upgrade head` applied cleanly against the running Postgres instance; `uv run alembic heads` confirmed `1dfe4d12bdee (head)`.
- `uv run pytest -q`: 336 passed (one `test_tampered_token_is_rejected` flake observed on an earlier run — inherently flaky, ~25% chance the tampered base64 char decodes to the same signature bytes; passed on re-run in isolation and on the final full-suite run).
- `uv run ruff check .`: found one `E501` line-too-long on the new `grant_opt_in_consent` route decorator; fixed by wrapping the decorator arguments onto multiple lines. Clean after.
- `uv run mypy .`: found one real issue — `SqlAlchemyOptInConsentRepository.revoke_active`'s `result.rowcount` access on `Result[Any]` (rowcount lives on `CursorResult`, not the base `Result` type); fixed with an explicit `cast(CursorResult, ...)`. Remaining 13 errors are pre-existing `Fake*Repository` structural-typing mismatches in test files that predate this story (confirmed via `git stash` diff against the baseline commit) — my new `FakeOptInConsentRepository` follows the identical established test convention as the others.
- `uv run lint-imports`: 2 contracts kept, 0 broken.
- `npx tsc -b`: clean.
- `npx eslint .`: 2 pre-existing errors in `DashboardPage.tsx`/`LoginPage.tsx` (unrelated `react-hooks/set-state-in-effect` findings), confirmed present on the baseline commit via `git stash`; no new errors introduced.
- `npx vitest run`: an initial full-suite run showed 44 failures with 5000ms timeouts across many unrelated files (TeamFormDialog, ResetPasswordPage, etc.) — diagnosed as environment slowness (132s setup / 378s import phase that run), not a real regression; re-running in isolation passed. Two real issues found and fixed in the new `RecipientsPage.test.tsx` test: (1) `findByText('Opted In')` was ambiguous once both the Users table's Consent-column badge and the open dialog's Consent-section badge matched — switched the wait condition to the dialog-only "Revoke Consent" button; (2) the post-confirm assertion ran before the MUI `ConfirmationDialog`'s exit transition finished unmounting — switched `getByRole` to `findByRole` so it retries until the transition completes. Final full run: 123 passed, 20 files.

### Completion Notes List

- Implemented `OptInConsent` as a separate historized entity (per `ARCHITECTURE-SPINE.md`'s ERD, not a field on `User`) with a partial unique index (`ix_opt_in_consents_user_id_active_uq` on `user_id WHERE revoked_at IS NULL`) as the DB-level backstop for the one-active-consent invariant.
- `UserDirectoryService.update_user` now revokes any active consent when the User's mobile number changes, writing a co-transactional `user.consent_auto_revoked` audit entry (only when a row was actually revoked) alongside the existing `user.updated` entry.
- Added `OptInConsentService` (grant/revoke) as a fourth class in `domain/recipients.py`, with `ConsentAlreadyActive`, `ConsentNotActive`, and `ConsentTargetNotAddressable` exceptions mapped to 409/409/422 respectively at the API layer, with an `IntegrityError` backstop on grant mapping a genuine concurrent double-grant race to the same 409.
- `GET /users` batches consent lookups via `get_active_by_user_ids` (one query) rather than N+1 per-row lookups, matching Story 3.2's `list_all_full()` precedent.
- Frontend: `UserFormDialog.tsx` gained a Consent section (StatusBadge + Record/Revoke Consent actions, backed by a `ConfirmationDialog` naming the real consequence for revoke) and a mobile-change notice warning that saving will revoke existing consent; a new `onConsentChanged` prop refreshes the underlying table without closing the dialog. `RecipientsPage.tsx` gained a Consent column badge.
- All 8 tasks completed; all 50 subtasks checked off. Full backend gate (`pytest`, `ruff`, `mypy`, `lint-imports`) and frontend gate (`tsc -b`, `eslint`, `vitest`) run clean, with only pre-existing/unrelated issues noted above (none introduced by this story).

### File List

**New:**
- `alembic/versions/1dfe4d12bdee_opt_in_consents.py`
- `ports/consent.py`
- `adapters/persistence/consent.py`
- `tests/adapters/persistence/test_opt_in_consent_repository.py`

**Modified:**
- `domain/models.py`
- `domain/recipients.py`
- `api/recipients/routes.py`
- `tests/domain/test_recipients_service.py`
- `tests/api/test_recipients_routes.py`
- `tests/conftest.py`
- `web/src/pages/UserFormDialog.tsx`
- `web/src/pages/UserFormDialog.test.tsx`
- `web/src/pages/RecipientsPage.tsx`
- `web/src/pages/RecipientsPage.test.tsx`
- `web/src/pages/RecipientListsPanel.test.tsx`
