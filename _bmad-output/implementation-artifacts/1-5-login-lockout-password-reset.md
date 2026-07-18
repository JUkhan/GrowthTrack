---
baseline_commit: 5da4e5b252ef61127d7428245c913af7e6f6cc61
---

# Story 1.5: Login Lockout & Password Reset

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an Administrator,
I want repeated failed login attempts to trigger a temporary lockout, and a way to reset a forgotten password,
so that I'm not permanently locked out while brute-force attempts are slowed.

## Acceptance Criteria

1. **Given** 5 failed login attempts for the same account (`Settings.login_lockout_threshold`, default 5 — `[ASSUMPTION, carried from epics.md, OWASP-validated: see Dev Notes]`), **when** the next attempt is made, **then** further attempts for that account are rejected — with a distinct `account_locked` response carrying the remaining lockout seconds — for 15 minutes (`Settings.login_lockout_duration_minutes`, default 15), **and** the check happens before password verification runs (AD-11), **and** the frontend shows a counting-down cooldown timer, not a bare "try again" loop (EXPERIENCE.md). [Source: epics.md#Story 1.5]
2. **Given** a forgotten password, **when** I use the reset flow, **then** I can request a reset via my username and set a new password through a secure, single-use, time-limited (`Settings.password_reset_token_ttl_minutes`, default 60) reset path backed by a standalone `PasswordResetToken` entity whose token is hashed at rest — the raw token is never stored, and never returned in the forgot-password HTTP response (see Dev Notes "Open Question — reset-link delivery"). [Source: epics.md#Story 1.5, AD-11]
3. **Given** a request to `/auth/forgot-password` for a username that doesn't exist, isn't an Administrator, or isn't active, **when** the request is made, **then** the response is identical to a valid request (generic 200, no existence signal) — no username-enumeration oracle. [Source: OWASP Forgot Password Cheat Sheet; PRD NFR-3]
4. **Given** a reset token that is unknown, expired, or already used, **when** `/auth/reset-password` is called with it, **then** the request is rejected with one generic `invalid_reset_token` error — the three cases are not distinguished in the response. [Source: OWASP Forgot Password Cheat Sheet]
5. **Given** a successful password reset, **when** it completes, **then** the account's lockout state (if any) is cleared and the new password is hashed the same way as every other stored password (`PwdlibPasswordHasher`, Story 1.1's rule). [Source: epics.md#Story 1.5; Story 1.1]

## Tasks / Subtasks

- [x] Task 1: `Settings` — three new configurable policy values (AC: #1, #2)
  - [x] `config.py`: add to `Settings`, immediately after `jwt_expiry_minutes` (same `Field(default=..., gt=0)` style/comment convention as that field — architecture's own Deferred section calls "retry policy magnitude" a policy value, "left configurable"):
    - `login_lockout_threshold: int = Field(default=5, gt=0)`
    - `login_lockout_duration_minutes: int = Field(default=15, gt=0)`
    - `password_reset_token_ttl_minutes: int = Field(default=60, gt=0)`
  - [x] `.env.example` already lists `JWT_EXPIRY_MINUTES` (with a comment noting it's optional/defaulted) even though `Settings` doesn't require it — that's this repo's established convention for documenting every `Settings` field, not just required ones. Add `LOGIN_LOCKOUT_THRESHOLD`, `LOGIN_LOCKOUT_DURATION_MINUTES`, and `PASSWORD_RESET_TOKEN_TTL_MINUTES` there too, under the existing `# --- Auth ---` section, each with a one-line comment matching `JWT_EXPIRY_MINUTES`'s style ("Optional; defaults to N if unset").

- [x] Task 2: Domain model + ports — `failed_login_count`/`locked_until` on `User`, new `PasswordResetToken` entity (AC: #1, #2)
  - [x] `domain/models.py`: add `failed_login_count: int = 0` and `locked_until: datetime | None = None` to the end of the `User` dataclass (defaults required — they must come after the existing non-default fields). Add a new dataclass:
    ```python
    @dataclass
    class PasswordResetToken:
        id: uuid.UUID
        user_id: uuid.UUID
        token_hash: str
        expires_at: datetime
        used_at: datetime | None
        created_at: datetime
    ```
  - [x] `ports/users.py`: add `datetime` to the imports, then four new abstract methods on `UserRepository` (mirrors this file's existing `Any`-typed style, and Task 3's atomic-update rationale):
    - `async def increment_failed_login_count(self, user_id: uuid.UUID) -> int: ...` (returns the new count — must be an atomic `UPDATE ... RETURNING`, not read-then-write, or two concurrent failed attempts can under-count and delay lockout)
    - `async def lock_until(self, user_id: uuid.UUID, until: datetime) -> None: ...`
    - `async def clear_lockout(self, user_id: uuid.UUID) -> None: ...` (sets `failed_login_count=0`, `locked_until=NULL` — used on both successful login and successful password reset)
    - `async def update_password(self, user_id: uuid.UUID, hashed_password: str) -> None: ...` (also bumps `version += 1` per the Consistency Conventions' optimistic-concurrency column — this is the first story to `UPDATE` an existing `users` row at all; no conflict-detection read is needed here, that's Story 3.4's scope, but the column must still increment for consistency)
  - [x] New `ports/password_reset.py`, same shape as `ports/sessions.py` (Story 1.4's precedent for a brand-new persistence-only port — AD-11 explicitly allows this: "reachable through existing repository patterns... none require a new port or adapter" means no new *kind* of port like an email sender, not that no new port at all is allowed):
    ```python
    class PasswordResetTokenRepository(ABC):
        @abstractmethod
        async def add(self, token: Any) -> None: ...
        @abstractmethod
        async def get_by_hash(self, token_hash: str) -> Any: ...
        @abstractmethod
        async def mark_used(self, token_id: uuid.UUID, used_at: datetime) -> None: ...
    ```

- [x] Task 3: Persistence — columns, new table, migration (AC: #1, #2)
  - [x] `adapters/persistence/users.py`: `UserModel` gains `failed_login_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)` and `locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)`. Update `_to_domain` to pass both through. Add the four new repository methods from Task 2 using SQLAlchemy Core `update()` (import `update` from `sqlalchemy`), e.g.:
    ```python
    async def increment_failed_login_count(self, user_id: uuid.UUID) -> int:
        stmt = (
            update(UserModel)
            .where(UserModel.id == user_id)
            .values(failed_login_count=UserModel.failed_login_count + 1)
            .returning(UserModel.failed_login_count)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()
    ```
    `lock_until`/`clear_lockout`/`update_password` follow the same `update().where(id == user_id).values(...)` shape (no `.returning()` needed).
  - [x] New `adapters/persistence/password_reset.py`, mirroring `adapters/persistence/sessions.py`'s one-file model+repository structure. `user_id` **must** carry a real `ForeignKey("users.id")` — this is what AD-11's ERD (`USER ||--o{ PASSWORD_RESET_TOKEN : "requests"`) requires, and it's also the DB-enforced reason `tests/conftest.py`'s cleanup order matters (below):
    ```python
    class PasswordResetTokenModel(Base):
        __tablename__ = "password_reset_tokens"
        id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
        user_id: Mapped[uuid.UUID] = mapped_column(
            UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
        )
        token_hash: Mapped[str] = mapped_column(String, nullable=False, unique=True)
        expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
        used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
        created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ```
    `get_by_hash` uses `select(...).where(token_hash == ...)`, `scalar_one_or_none()`; `mark_used` is an `update()` setting `used_at`. Include a `_to_domain` mapper like `users.py`'s. The migration (below) must also declare this FK (`sa.ForeignKeyConstraint(["user_id"], ["users.id"])`), and `test_password_reset_token_repository.py` (Task 8) must insert rows via a real seeded user (`seed_user()`, matching every other real-Postgres test's convention) — a row with a random, non-existent `user_id` will fail the FK constraint.
  - [x] `adapters/persistence/__init__.py`: add `from adapters.persistence import password_reset as password_reset  # noqa: F401` (alphabetical alongside the existing three imports).
  - [x] New Alembic revision on top of current head `a2fafc72668b` (`uv run alembic revision --autogenerate -m "login lockout and password reset"`). **Critical gotchas, verify by hand — autogenerate will not get both of these right on its own:**
    - The new `users.failed_login_count` column is `NOT NULL` on a table that (in any real deployment) already has rows from Story 1.2's bootstrap — the `ALTER TABLE` needs `server_default="0"` (a DB-side default), not just the SQLAlchemy model's Python-side `default=0`, or `upgrade()` fails against existing data. Add `server_default="0"` to that one `op.add_column` call by hand if autogenerate omits it (it does, by default, for a plain `Integer` column). `locked_until` is nullable, needs no default.
    - `op.create_table("password_reset_tokens", ...)` must include `sa.ForeignKeyConstraint(["user_id"], ["users.id"])` alongside the primary-key/unique constraints, matching the `ForeignKey("users.id")` on the model (previous bullet) — autogenerate should emit this on its own from the model, but confirm it's actually present in the generated `upgrade()`, not silently dropped.
    - Reformat autogenerate's output to this repo's established double-quote/one-arg-per-line style (`98ddc369b175`'s convention, not autogenerate's raw single-quote/compact output).
  - [x] `tests/conftest.py`: add `await conn.execute(text("DELETE FROM password_reset_tokens"))` to `_clean_tables`, alongside the existing three deletes, **placed before** `DELETE FROM users` in that same block — `password_reset_tokens.user_id`'s new `ForeignKey("users.id")` (previous bullets) means deleting `users` first would raise a foreign-key violation on any row left in `password_reset_tokens`. Reorder to `audit_log_entries` → `password_reset_tokens` → `users` → `revoked_tokens` (`revoked_tokens` has no FK to `users`, so its position relative to `users` doesn't matter, but keep it last to minimize the diff against the existing order).

- [x] Task 4: `domain/auth.py` — lockout logic, extending `AuthenticationService` (not a new class) (AC: #1)
  - [x] Keep this inline in `AuthenticationService`, not a separate service: the lockout check must run *before* `authenticate()`'s existing password-verify line and the failure-counting must happen in the *same* branch that already decides pass/fail — splitting it into a second class would mean passing intermediate authentication state back and forth for no structural benefit (unlike `SessionService`/`LastAdministratorGuard`, which are genuinely separate concerns from login itself).
  - [x] Add `lockout_threshold: int` and `lockout_duration: timedelta` constructor params (no class-level constants — these are `Settings`-sourced per Task 1, passed in by the route). Add:
    ```python
    class AccountLocked(Exception):
        def __init__(self, retry_after_seconds: int) -> None:
            self.retry_after_seconds = retry_after_seconds
            super().__init__("Account is temporarily locked due to repeated failed login attempts")
    ```
  - [x] `authenticate()` new control flow, in order:
    1. `user is None` branch unchanged (dummy-hash timing-safe verify, return `None` — a nonexistent username has no row to lock, and must never raise `AccountLocked`, which would itself be an existence oracle).
    2. **New, before password verification (AD-11's explicit ordering requirement):** `now = datetime.now(UTC)`; if `user.locked_until is not None and user.locked_until > now`, `raise AccountLocked(retry_after_seconds=int((user.locked_until - now).total_seconds()))` — the password hasher is never called on a locked account (assert this in tests via a call-count spy, not just the return value).
    3. Existing `password_ok = ...verify(...)` line, unchanged.
    4. **New:** if the login fails *specifically* because of a wrong password on an otherwise-valid (active Administrator) account — i.e., `not password_ok and user.status == UserStatus.ACTIVE and user.role == Role.ADMINISTRATOR` — call `new_count = await self._users.increment_failed_login_count(user.id)`; if `new_count >= self._lockout_threshold`, call `await self._users.lock_until(user.id, now + self._lockout_duration)` and write a `account.locked` audit entry (`actor_user_id=user.id`, `details={"failed_login_count": new_count}`) — this is a security-relevant state change distinct from `login.failure`, and AD-7's own rationale ("an administrative action — or a login — taking effect without a corresponding audit record") applies here too. Do **not** increment the counter for a wrong-role or inactive-account failure — those already return `None` for reasons unrelated to a guessed password and would let an attacker rack up billable "confirmations" the lockout mechanism isn't meant to gate.
    5. Existing `if not password_ok or ...: return None` line unchanged in shape, but only reached after step 4's counting.
    6. **New**, on success (end of the method, before `return user`): if `user.failed_login_count or user.locked_until is not None`, call `await self._users.clear_lockout(user.id)` — a clean login always clears stale lockout state, so a legitimate user isn't left "one more wrong password from instant re-lock" after they finally get it right.
  - [x] `login()`: `authenticate()` can now raise `AccountLocked` (new) in addition to returning `None`. Wrap the call: `except AccountLocked:` → write a `login.failure` audit entry with `details={"username": username, "reason": "locked"}` (distinguishing it from a plain wrong-password failure in the audit trail, without changing the *user-facing* response's oracle properties — audit log is operator-only), then `raise` (propagate `AccountLocked` itself, don't swallow it — the route needs `retry_after_seconds`). The existing `user is None` → `InvalidCredentials` branch is unchanged.
  - [x] **No time-decay of `failed_login_count` for old, sporadic failures.** AD-11's schema has only `failed_login_count`/`locked_until` — no `last_failed_attempt_at` — so there is no column to determine "was that 5th failure within the last 15 minutes." The counter is cumulative until either a successful login or a completed password reset clears it (Task 2/6). This is a deliberate reading of epics.md's "within a 15-minute window" phrasing as *the lockout duration*, not a rolling attempt-counting window — flagged as `[ASSUMPTION — CONFIRM WITH PM/ARCHITECT]`, see Dev Notes.

- [x] Task 5: `domain/password_reset.py` — new `PasswordResetService` (AC: #2, #3, #4, #5)
  - [x] A separate module/class from `AuthenticationService` — password reset is a genuinely distinct concern (it never touches the login control flow), following the same one-class-one-job precedent as `SessionService`/`LastAdministratorGuard`. Constructor: `users: UserRepository`, `reset_tokens: PasswordResetTokenRepository`, `password_hasher: PasswordHasher`, `audit_log: AuditLogRepository`, `token_ttl: timedelta`.
  - [x] `InvalidResetToken(Exception)` — one generic exception for unknown/expired/used tokens (AC #4), same no-oracle rationale as `InvalidCredentials`.
  - [x] Token hashing: use `hashlib.sha256(raw_token.encode("utf-8")).hexdigest()`, **not** `PwdlibPasswordHasher`/bcrypt. Document this as a deliberate deviation from a literal reading of "hashed per Story 1.1's rule": bcrypt is designed to be slow and salted for low-entropy human passwords, and its per-hash salt makes an equality lookup (`WHERE token_hash = :hash`) impossible — you'd have to fetch every unexpired token and bcrypt-verify each one. A `secrets.token_urlsafe(32)` reset token already has ≥128 bits of entropy (OWASP Forgot Password Cheat Sheet's own minimum), so a fast, unsalted SHA-256 digest is the appropriate, lookupable hash for this specific case — "hashed per Story 1.1's rule" applies to the **new password itself** at reset-completion time (Task 5's `complete_reset`, which does use `PwdlibPasswordHasher`), not to the token.
  - [x] `async def request_reset(self, username: str) -> str | None:` — looks up the user; returns `None` immediately (no token created, no audit entry) if the user doesn't exist, isn't `UserStatus.ACTIVE`, or isn't `Role.ADMINISTRATOR` (AC #3's enumeration-safety requirement is enforced by the **route**, Task 6, returning the same response either way — this method's `None`/`str` return only tells the route whether to log the link, never changes the HTTP response shape). On a valid user: generate `raw_token = secrets.token_urlsafe(32)`, `now = datetime.now(UTC)`, persist a `PasswordResetToken` (`expires_at=now + self._token_ttl`, `used_at=None`), write a `password_reset.requested` audit entry (`actor_user_id=user.id`), return `raw_token`.
  - [x] `async def complete_reset(self, raw_token: str, new_password: str) -> None:` — hash the incoming token, `get_by_hash`; if `token is None or token.used_at is not None or token.expires_at <= now`, `raise InvalidResetToken()` (all three cases collapsed into one exception/one response, AC #4). Otherwise: `mark_used(token.id, now)`, `update_password(token.user_id, self._password_hasher.hash(new_password))` (Story 1.1's hashing rule, AC #5), `clear_lockout(token.user_id)` (AC #5 — a reset also un-sticks any active lockout; a locked-out Administrator who successfully proves account ownership via the reset token shouldn't still have to wait out the timer), then a `password_reset.completed` audit entry.
  - [x] **Known, deliberately out-of-scope gap — flag in Dev Notes, don't silently build a fix:** completing a reset does not revoke any already-issued, still-valid session `jti`s for that user (unlike Story 1.4's logout/deactivation paths). There's no "list every outstanding session for a user" mechanism in this codebase — JWTs are stateless and `revoked_tokens` is keyed by individual `jti`, not by user. A session created before a compromise-driven reset would keep working until it naturally expires. Building a per-user bulk-revocation mechanism is out of scope for AD-11's token-entity-only schema and this story's ACs.

- [x] Task 6: API routes (AC: #1, #2, #3, #4)
  - [x] `api/auth/routes.py` — `POST /login`: move `settings = get_settings()` earlier (before constructing `AuthenticationService`, not after `.login()` as today) so the lockout policy values can be passed in: `AuthenticationService(users, PwdlibPasswordHasher(), audit_log, lockout_threshold=settings.login_lockout_threshold, lockout_duration=timedelta(minutes=settings.login_lockout_duration_minutes))`. Wrap the existing `try/except InvalidCredentials` with an additional `except AccountLocked as exc:` branch **before** the `InvalidCredentials` one — `await session.commit()` (persists the lockout-state write and its audit entry even though the request itself fails, same pattern as the existing `InvalidCredentials` branch), then `raise _account_locked(exc.retry_after_seconds) from None`.
  - [x] New helper next to `_invalid_credentials`/`_administrator_exists`:
    ```python
    def _account_locked(retry_after_seconds: int) -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "account_locked",
                "message": "Too many failed login attempts. Try again later.",
                "details": {"retry_after_seconds": retry_after_seconds},
            },
        )
    ```
    Stays `401` (not a new `423 Locked`) — every auth failure in this app is `401`, distinguished only by the envelope's `code`, matching the established `invalid_credentials`/`account_deactivated` precedent (Story 1.4). This is a deliberate, accepted enumeration tradeoff, different in kind from Story 1.3's "always identical 401" rule for role/existence checks: an attacker who *causes* the lockout via their own 5 wrong-password guesses learns "this username is real" on their 6th attempt — but OWASP's own guidance treats this as an inherent, acceptable cost of any lockout mechanism (the alternative — never signaling lockout at all — defeats EXPERIENCE.md's explicit cooldown-timer requirement). Don't try to further hide this.
  - [x] New response model: `class MessageResponse(BaseModel): message: str` (generic, next to `UserResponse`/`BootstrapStatusResponse`).
  - [x] New request models:
    ```python
    class ForgotPasswordRequest(BaseModel):
        username: str = Field(min_length=1, max_length=255)

    class ResetPasswordRequest(BaseModel):
        token: str = Field(min_length=1)
        new_password: str = Field(min_length=1, max_length=72)
    ```
  - [x] New endpoint:
    ```python
    @router.post("/forgot-password", response_model=MessageResponse)
    async def forgot_password(
        body: ForgotPasswordRequest, session: AsyncSession = Depends(get_db)
    ) -> MessageResponse:
        users = SqlAlchemyUserRepository(session)
        reset_tokens = SqlAlchemyPasswordResetTokenRepository(session)
        audit_log = SqlAlchemyAuditLogRepository(session)
        settings = get_settings()
        service = PasswordResetService(
            users, reset_tokens, PwdlibPasswordHasher(), audit_log,
            timedelta(minutes=settings.password_reset_token_ttl_minutes),
        )
        raw_token = await service.request_reset(body.username)
        await session.commit()
        if raw_token is not None:
            logger.info(
                "password_reset_link_issued",
                extra={"reset_path": f"/reset-password?token={raw_token}"},
            )
        return MessageResponse(
            message="If an account with that username exists, password reset instructions have been generated."
        )
    ```
    **Public/unauthenticated, same reasoning as `bootstrap-status`.** The response is unconditional — same `200`/same body — regardless of whether `request_reset` returned a token or `None` (AC #3). `logger` is `logging.getLogger(__name__)` (stdlib, matching `scheduler/main.py`'s existing precedent — no structured-JSON/correlation-id logging infrastructure exists in `api/` yet despite the architecture's aspiration for it; don't build that infrastructure in this story, it's out of scope).
  - [x] **`api/main.py` currently has no `logging.basicConfig()`/handler setup at all** (confirmed: `scheduler/main.py` calls it, `api/main.py` doesn't, and Uvicorn's own logging config only touches its own `uvicorn.*` loggers, not application loggers) — the `logger.info(...)` call above would otherwise silently go nowhere, no console/file output anywhere, and this would only surface once someone actually tries to use the feature, not in any test (Task 8's tests fetch the token via direct repository access, not via the log). Add `import logging` and `logging.basicConfig(level=logging.INFO)` near the top of `api/main.py` (module level, before `app = FastAPI(...)`), mirroring `scheduler/main.py`'s existing call.
  - [x] New endpoint:
    ```python
    @router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
    async def reset_password(
        body: ResetPasswordRequest, session: AsyncSession = Depends(get_db)
    ) -> None:
        users = SqlAlchemyUserRepository(session)
        reset_tokens = SqlAlchemyPasswordResetTokenRepository(session)
        audit_log = SqlAlchemyAuditLogRepository(session)
        service = PasswordResetService(
            users, reset_tokens, PwdlibPasswordHasher(), audit_log, timedelta(0)
        )
        try:
            await service.complete_reset(body.token, body.new_password)
        except InvalidResetToken:
            await session.commit()
            raise _invalid_reset_token() from None
        await session.commit()
    ```
    (`token_ttl` is unused by `complete_reset`, only by `request_reset` — passing `timedelta(0)` here is harmless but slightly awkward; consider splitting `PasswordResetService`'s constructor so `token_ttl` is a `request_reset`-only parameter instead of a constructor field, if that reads cleaner once written.) Add `_invalid_reset_token()` alongside the other `_*` helpers: `400 Bad Request` (not `401` — the caller isn't "unauthenticated," they're submitting a malformed/expired one-time credential; `400` matches typical REST semantics for that and doesn't collide with the `401`-means-"your session/login failed" convention established elsewhere in this file), body `{"code": "invalid_reset_token", "message": "This reset link is invalid or has expired.", "details": None}` — one message for unknown/expired/used (AC #4).
  - [x] Imports to add: `timedelta` from `datetime`, `logging`, `SqlAlchemyPasswordResetTokenRepository` from `adapters.persistence.password_reset`, `PasswordResetService`/`InvalidResetToken` from `domain.password_reset`, `AccountLocked` from `domain.auth` (alongside the existing `InvalidCredentials` import).

- [x] Task 7: Frontend — shared form shell (addresses the Story 1.2-review-deferred duplication), lockout cooldown UI, forgot/reset pages (AC: #1, #2)
  - [x] **Resolve the Story 1.2 code-review deferral now, not again:** `deferred-work.md`'s entry for `BootstrapForm.tsx`/`LoginPage.tsx` duplication explicitly said "revisit if a third similar form appears (e.g. Story 1.5's password reset)." This story adds *two* more near-identical forms (forgot-password, reset-password) — that's the fourth and fifth occurrence, not just the third. Extract a small shared component before adding more copies, don't defer a third time.
  - [x] New `web/src/components/AuthFormShell.tsx`:
    ```tsx
    import type { FormEvent, ReactNode } from 'react'
    import Box from '@mui/material/Box'
    import Container from '@mui/material/Container'
    import Typography from '@mui/material/Typography'

    interface AuthFormShellProps {
      heading: string
      onSubmit: (event: FormEvent<HTMLFormElement>) => void
      children: ReactNode
    }

    function AuthFormShell({ heading, onSubmit, children }: AuthFormShellProps) {
      return (
        <Container maxWidth="xs" sx={{ py: 8 }}>
          <Typography variant="h4" component="h1" gutterBottom>
            {heading}
          </Typography>
          <Box
            component="form"
            onSubmit={onSubmit}
            noValidate
            sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}
          >
            {children}
          </Box>
        </Container>
      )
    }

    export default AuthFormShell
    ```
    Extracts exactly the `Container`/`Typography`/`Box` scaffold both `LoginPage.tsx` and `BootstrapForm.tsx` already duplicate verbatim — nothing more (no field abstraction, no submit-state management: those still differ per-form and aren't worth genericizing yet).
  - [x] Refactor `LoginPage.tsx` and `BootstrapForm.tsx` to render through `<AuthFormShell heading="..." onSubmit={handleSubmit}>...`, moving their `Alert`/`TextField`/`Button` children inside unchanged. This is a pure structural extraction — no behavior change, so `LoginPage.test.tsx`/`BootstrapForm.test.tsx` should keep passing as-is; only touch them if a query breaks on the new DOM nesting (unlikely — RTL queries by role/label, not container structure).
  - [x] `LoginPage.tsx` — lockout cooldown (EXPERIENCE.md: "shows a cooldown timer, not a bare 'try again' loop"): add `lockoutSeconds: number | null` state. In `handleSubmit`'s `!response.ok` branch, additionally check `body?.error?.code === 'account_locked'` and read `body.error.details?.retry_after_seconds`, setting `lockoutSeconds` to that integer (falls through to the existing generic `error` Alert for every other failure code, unchanged). Add a `useEffect` that, while `lockoutSeconds` is a positive number, runs a 1-second `setInterval` decrementing it, clearing the interval and setting it back to `null` when it reaches 0. Render, in place of (not in addition to) the generic error `Alert` when `lockoutSeconds` is set: `<Alert severity="warning">Too many failed attempts. Try again in {lockoutSeconds}s.</Alert>`, and disable the submit `Button` while `lockoutSeconds` is truthy (`disabled={submitting || Boolean(lockoutSeconds)}`) so the form visibly can't be resubmitted mid-cooldown — this is the literal "cooldown timer, not a bare try-again loop" requirement.
  - [x] `LoginPage.tsx` — extend the router-state message type from `{ message?: string }` to `{ message?: string; severity?: 'warning' | 'success' }`, and render `<Alert severity={locationSeverity ?? 'warning'}>{deactivationMessage}</Alert>` (defaulting to `'warning'` preserves Story 1.4's existing deactivation-notice behavior unchanged) so `ResetPasswordPage.tsx` (below) can pass `severity: 'success'` for its own message instead of every router-state notice rendering as a warning regardless of content.
  - [x] `LoginPage.tsx` — add a "Forgot password?" link below the submit button: `<Link component={RouterLink} to="/forgot-password">Forgot password?</Link>` (`import { Link as RouterLink } from 'react-router-dom'` alongside the existing `useLocation`/`useNavigate` import; `import Link from '@mui/material/Link'`, same import `BootstrapForm.tsx` already uses for its "Back to login" link).
  - [x] New `web/src/pages/ForgotPasswordPage.tsx`: `AuthFormShell` with a single username `TextField`, submit → `apiFetch('/auth/forgot-password', { method: 'POST', body: JSON.stringify({ username }) })`. Always show the same success `Alert severity="info"` after any `2xx` response (the generic message from the response body) — never render different UI for "user exists" vs. not (AC #3 extends to the frontend, not just the API response body). A network/non-2xx failure shows a generic `Alert severity="error"` ("Something went wrong. Please try again.", matching the existing catch-block copy convention). Include a "Back to login" `Link` (same pattern as `BootstrapForm.tsx`).
  - [x] New `web/src/pages/ResetPasswordPage.tsx`: reads `token` from `useSearchParams()` (`?token=...`). `AuthFormShell` with a new-password `TextField` (`type="password"`) — a confirm-password field is a reasonable addition for basic UX safety (not in the AC, low-risk/high-value, keep it simple: client-side-only equality check before submitting, no new API surface). Submit → `apiFetch('/auth/reset-password', { method: 'POST', body: JSON.stringify({ token, new_password }) })`. On success (`204`), `navigate('/', { replace: true, state: { message: 'Password reset. Please log in with your new password.', severity: 'success' } })` — **reuses `LoginPage.tsx`'s existing router-state Alert mechanism** (the same one Story 1.4 built for the deactivation notice), extended with an optional `severity` field (`'warning' | 'success'`, defaulting to `'warning'` so Story 1.4's existing deactivation notice needs no call-site change) rather than hardcoding `severity="warning"` for a message that's actually good news; do not build a second, parallel "flash message" mechanism. On failure, generic `Alert severity="error"` reading `body?.error?.message` (the `invalid_reset_token` message from Task 6), matching `LoginPage.tsx`'s existing error-Alert pattern.
  - [x] `web/src/router.tsx`: add `{ path: '/forgot-password', element: <ForgotPasswordPage /> }` and `{ path: '/reset-password', element: <ResetPasswordPage /> }`.

- [x] Task 8: Tests (AC: all)
  - [x] `tests/domain/test_auth_service.py` additions (local fakes extended with the new `UserRepository` methods, per this codebase's per-file-fakes convention): failing 4 times then succeeding does not lock (fake tracks the count); the 5th consecutive wrong-password failure calls `lock_until` and writes an `account.locked` audit entry; a 6th attempt while locked raises `AccountLocked` with the correct `retry_after_seconds` **and the fake password hasher's `verify` is never called for that attempt** (assert a call-count spy, not just the exception — this is what actually proves AD-11's "before password verification runs" ordering); a successful login after `locked_until` has passed clears `failed_login_count`/`locked_until` via `clear_lockout`; a nonexistent username never touches any of the new lockout methods.
  - [x] `tests/domain/test_password_reset_service.py` (new, local fakes): `request_reset` for an unknown/inactive/non-Administrator username returns `None` and creates no token/audit row; for a valid user, returns a raw token, and the fake repo's stored `token_hash` is **not** equal to the raw token (proves it's actually hashed, not stored verbatim); `complete_reset` with the right raw token succeeds, updates the password via the fake hasher, clears lockout, marks the token used; a second `complete_reset` with the same raw token raises `InvalidResetToken` (single-use); an expired token (fake clock or a token constructed with a past `expires_at`) raises `InvalidResetToken`; an unknown token raises `InvalidResetToken` — assert all three failure modes raise the *same* exception type/message, not distinguishable ones.
  - [x] `tests/adapters/persistence/test_user_repository.py` additions (real Postgres, `seed_user`/`create_session_factory` convention): `increment_failed_login_count` returns the correct running total across repeated calls and is safe under two concurrent increments (both land, final count is +2, not +1 — proves the `UPDATE ... RETURNING` is atomic, not read-then-write); `lock_until`/`clear_lockout` round-trip correctly; `update_password` persists the new hash and increments `version`.
  - [x] `tests/adapters/persistence/test_password_reset_token_repository.py` (new, real-Postgres style, mirrors `test_revoked_token_repository.py`): `add` + `get_by_hash` round-trip; `get_by_hash` for an unknown hash returns `None`; `mark_used` sets `used_at` and is reflected on a subsequent `get_by_hash`.
  - [x] `tests/api/test_auth_routes.py` additions:
    - `test_login_locks_after_five_failed_attempts`: `seed_user` → 5x `POST /auth/login` with wrong password (each a plain 401 `invalid_credentials`) → 6th attempt (even with the *correct* password) returns 401 `account_locked` with `details.retry_after_seconds` a positive int close to `settings.login_lockout_duration_minutes * 60`.
    - `test_locked_account_audit_trail`: after the above, `_audit_rows()` includes one `account.locked` entry and the 6th attempt's rejection is logged as `login.failure` with `details.reason == "locked"`.
    - `test_successful_login_clears_a_prior_lockout`: seed → 4 wrong attempts (below threshold) → 1 correct login → succeeds and `GET /auth/me` style follow-up (or a direct repository check) shows `failed_login_count == 0`.
    - `test_forgot_password_returns_the_same_response_regardless_of_account_state`: four calls with the identical status code and response body shape (AC #3's three literal exclusion cases, plus the real-user control case) — (1) `seed_user`'s real active Administrator username, (2) a random nonexistent username, (3) `seed_user(role=Role.SALES_USER)` (existing but non-Administrator), (4) `seed_user(status=UserStatus.INACTIVE)` (existing but inactive). Don't collapse this to just "real vs. fake" — AC #3 names all three exclusion cases explicitly and the route, not just `PasswordResetService.request_reset`, is what must be proven not to leak which case applies.
    - `test_reset_password_happy_path`: `seed_user` → hit `/auth/forgot-password` → since the route only logs the token (not returned in the response), call `PasswordResetService`/the repository directly in the test to fetch the still-unused token's raw value the same way Story 1.4's tests hand-craft tokens ahead of a mechanism the HTTP layer doesn't expose (`test_auth_routes.py`'s established precedent) → `POST /auth/reset-password` with that raw token + a new password → 204 → subsequent `POST /auth/login` with the new password succeeds; with the old password fails.
    - `test_reset_password_rejects_expired_used_or_unknown_token_identically`: three sub-cases, each asserting the same `400` + `invalid_reset_token` shape.
    - `test_reset_password_clears_a_lockout`: lock an account (5 failures) → complete a reset → immediately log in with the new password succeeds (not rejected as still-locked).
  - [x] Frontend (`vitest` + RTL): `LoginPage.test.tsx` additions — a `account_locked` response renders the cooldown Alert and disables the submit button; the displayed countdown decrements after advancing fake timers by 1000ms (`vi.useFakeTimers()`, matching this repo's existing test tooling — confirm `vitest.config`/`setupTests` already enables fake timers or add the import locally). New `ForgotPasswordPage.test.tsx` — submitting always shows the generic confirmation Alert regardless of the mocked response's implied "existence" (test both a 200-with-token-issued-server-side and 200-without, same rendered text). New `ResetPasswordPage.test.tsx` — reads `token` from the URL, successful submit navigates to `/` with the expected router `state.message`; a `400 invalid_reset_token` response renders the generic error Alert and does not navigate. `AuthFormShell.test.tsx` is optional (thin presentational wrapper, already exercised indirectly through every page that renders through it: `LoginPage.test.tsx`, `BootstrapForm.test.tsx`, `ForgotPasswordPage.test.tsx`, `ResetPasswordPage.test.tsx`) — skip a dedicated test file for it.
  - [x] No CI changes needed — same reasoning as Story 1.4 (existing glob-style test discovery already covers new files under `tests/domain`, `tests/adapters/persistence`, `tests/api`, `web/src/**/*.test.tsx`).

### Review Findings

- [x] [Review][Defer] `/auth/forgot-password` reopens the login-flow's timing side-channel — a valid username triggers extra DB work (INSERT token + INSERT audit row) before returning; an invalid one returns immediately after one SELECT. `domain/auth.py`'s dummy-hash verify exists specifically to close this exact class of oracle for login, but the same treatment wasn't applied here. [`domain/password_reset.py:55-86`, `api/auth/routes.py:246-276`] — deferred, low exploitability for Phase-1 (admin-only, single-tenant, self-hosted deployment; precise timing measurement requires network access an external attacker is unlikely to have; revisit if multi-tenant or public-facing)
- [x] [Review][Patch] Lockout counter never resets `failed_login_count` when `locked_until` expires — only a successful login or completed reset clears it via `clear_lockout`, so the very next wrong password after a lockout expires immediately re-locks the account with a fresh window. Resolved by decision: reset the counter on lockout expiry (call `clear_lockout` before the `locked_until` check when it has passed) rather than adding a full rolling-window column — this story's own Dev Notes had flagged the cumulative-counter assumption as `[CONFIRM WITH PM/ARCHITECT]`; confirmed during this review as "reset on expiry." [`domain/auth.py:57-73`] — fixed; regression test added (`test_a_wrong_password_right_after_lockout_expiry_does_not_instantly_relock`)
- [x] [Review][Patch] Reset link never actually appears in the emitted log line — `logger.info("password_reset_link_issued", extra={"reset_path": ...})` combined with `logging.basicConfig(level=logging.INFO)` (no custom `format=`) silently drops `extra` fields; verified with a live repro (`INFO:test:password_reset_link_issued` — no `reset_path`). Since this is the feature's only documented reset-link delivery path (see Dev Notes "Open Question"), password reset is non-functional for a real operator today, and no test catches it because every test fetches the token directly via the repository. [`api/auth/routes.py:266-270`, `api/main.py:17`] — fixed by interpolating the path into the log message itself instead of relying on `extra`
- [x] [Review][Patch] A previously-locked account that is later deactivated or demoted still returns `account_locked` (revealing lockout state) instead of the generic response — the `locked_until` check runs before the status/role check, so the oracle-closing order used at the function's final `return None` isn't applied here too. [`domain/auth.py:57-59` vs `domain/auth.py:86`] — fixed; regression test added (`test_a_locked_but_deactivated_account_does_not_raise_account_locked`)
- [x] [Review][Patch] `complete_reset` never re-verifies the token's owner is still an active Administrator — a token issued while eligible remains redeemable (and clears lockout) even if the account is deactivated or demoted before the token is used, unlike `request_reset`, which does check eligibility. [`domain/password_reset.py:88-99`] — fixed; regression test added (`test_complete_reset_for_a_deactivated_account_raises_the_same_generic_error`)
- [x] [Review][Patch] `ResetPasswordRequest.token` has no `max_length`, unlike every other string field in this router (`username` caps at 255). [`api/auth/routes.py:70-72`] — fixed, `max_length=512`
- [x] [Review][Patch] `ForgotPasswordPage` hardcodes the confirmation copy instead of rendering the response body's `message`, as Task 7 literally specifies — currently harmless only because the two strings happen to match. [`web/src/pages/ForgotPasswordPage.tsx:28-35`] — fixed, now renders `response.json().message`
- [x] [Review][Patch] `retry_after_seconds` truncates via bare `int(...)` and the frontend gates on truthiness (`lockoutSeconds ? ... : ...`, `Boolean(lockoutSeconds)`), so a sub-1-second remaining lockout can report/render as unlocked. [`domain/auth.py:59`, `web/src/pages/LoginPage.tsx:124,145`] — fixed, `max(1, math.ceil(...))` server-side and `!== null` checks client-side
- [x] [Review][Patch] `ResetPasswordPage` renders the form and allows submitting even with no `?token=` present in the URL, relying on the generic `invalid_reset_token` error instead of an upfront "missing/invalid link" message. [`web/src/pages/ResetPasswordPage.tsx:11-12`] — fixed, shows an inline error and skips the form when no token is present
- [x] [Review][Defer] Password reset does not invalidate other already-issued JWT sessions for the account [`domain/password_reset.py:88-99`] — deferred, pre-existing (deliberately out-of-scope per this story's own Dev Notes)
- [x] [Review][Defer] No rate limiting on `/auth/forgot-password` or `/auth/reset-password` [`api/auth/routes.py:246-295`] — deferred, pre-existing (consistent with app-wide absence of throttling infrastructure)
- [x] [Review][Defer] `increment_failed_login_count`'s `scalar_one()` would raise unhandled if the user row vanished mid-request [`adapters/persistence/users.py`] — deferred, pre-existing (unreachable today; no user-deletion feature exists anywhere in the codebase)
- [x] [Review][Defer] `password_reset_tokens.user_id` FK has no `ON DELETE` behavior [`alembic/versions/8ae7e5d0d8c9_login_lockout_and_password_reset.py`] — deferred, pre-existing (only matters once user deletion exists)
- [x] [Review][Defer] Concurrent simultaneous lockout-triggering requests can each independently call `lock_until` and write a duplicate `account.locked` audit row [`domain/auth.py:66-84`] — deferred, pre-existing (narrow race, duplicate audit row only, no functional/security harm)
- [x] [Review][Defer] Requesting a new reset link does not invalidate prior outstanding tokens for the same user [`domain/password_reset.py:55-86`] — deferred, pre-existing (not required by any AC; defense-in-depth nicety beyond spec scope)
- [x] [Review][Defer] `new_password`'s 72-character cap (not byte length) lets bcrypt's 72-byte truncation bite on multi-byte-character passwords [`api/auth/routes.py:70-72`] — deferred, pre-existing (copied verbatim from `LoginRequest`/`BootstrapRequest`, Story 1.1)
- [x] [Review][Defer] `new_password` has no complexity/strength requirement [`api/auth/routes.py:70-72`] — deferred, pre-existing (same convention as every other password field in this app)
- [x] [Review][Defer] Frontend lockout countdown is seeded once and counts down client-side with no re-sync to the server [`web/src/pages/LoginPage.tsx:43-56`] — deferred, pre-existing (cosmetic; server still enforces the real lockout)
- [x] [Review][Defer] `retry_after_seconds` is only in the JSON body, no standard `Retry-After` HTTP header [`api/auth/routes.py:97-105`] — deferred, pre-existing (beyond what AC #1 requires)
- [x] [Review][Defer] `PasswordResetService.token_ttl` is unused by `complete_reset` (`reset_password` route passes a meaningless `timedelta(0)`) [`domain/password_reset.py:41-53`, `api/auth/routes.py:286-288`] — deferred, pre-existing (already flagged and accepted as "slightly awkward" in this story's own Dev Notes)

## Dev Notes

- **Open Question — reset-link delivery mechanism (flag for PM/Architect confirmation before or during dev-story):** no email/SMS adapter exists anywhere in this codebase, and AD-11 explicitly scopes all four of its new entities as `adapters/persistence`-only ("none require a new port or adapter"); `_bmad-output/planning-artifacts/prds/prd-GrowthTrack-2026-07-14/reconcile-spec.md`-adjacent `SPEC.md` places email notifications out of Phase 1 scope entirely. AC #2's "secure, time-limited reset path" therefore has **no PRD/architecture-specified delivery channel**. This story's chosen interim design (Task 6) logs the raw reset link server-side via stdlib `logging` (INFO level) for an operator to relay out-of-band, and deliberately never returns it in the `/auth/forgot-password` HTTP response — returning it there would let *any* anonymous caller take over *any* Administrator account just by knowing/guessing a username, which is a full authentication bypass, not an acceptable Phase-1 shortcut. Logging a secret token to application logs is itself a real, known tradeoff (logs are often longer-retained and more widely readable than the token's own 1-hour lifetime would suggest) — flagged here as `[ASSUMPTION — CONFIRM WITH PM/ARCHITECT]` rather than silently treated as final. Alternatives considered and rejected for this pass: (a) returning the token directly in the response — rejected, account-takeover oracle; (b) building an SMTP/Twilio-WhatsApp adapter now — rejected, explicitly out of architecture/PRD scope for Phase 1, and a materially bigger change than this story's ACs ask for; (c) requiring a currently-authenticated Administrator to reset a *different* Administrator's password — rejected, Epic 3 (Manage Users) doesn't exist yet, and doesn't help a single-Administrator deployment where the locked-out Administrator *is* the only Administrator.
- **`failed_login_count`/`locked_until` reset semantics — a second `[ASSUMPTION — CONFIRM]`:** epics.md's AC phrasing ("5 failed attempts... within a 15-minute window") implies a rolling/decaying counting window, but AD-11's schema has exactly two columns and no `last_failed_attempt_at` to measure elapsed time between failures. This story reads "15-minute window" as *the lockout duration itself*, not a decay window: the counter is purely cumulative until a success or a completed reset clears it (Task 4/5). A developer picking this up should not add a third column to implement true time-decay without confirming that's actually wanted — it's a real, if narrow, gap between the epics.md wording and the architecture's fixed schema.
- **Why lockout lives inside `AuthenticationService`, not a new `LockoutService`.** Unlike `SessionService`/`LastAdministratorGuard` (genuinely separate concerns bolted onto login/deactivation from the outside), the lockout check must interleave with `authenticate()`'s own pass/fail decision at two specific points (before verify, after a specific kind of failure) — extracting it would mean threading authentication state through a second class for no structural gain.
- **Why the reset token is SHA-256, not bcrypt, despite AC #2/#5's "hashed" language.** Bcrypt is for low-entropy secrets (human passwords) and its per-hash salting makes an equality-based DB lookup impossible. A 256-bit `secrets.token_urlsafe(32)` reset token is already far above OWASP's 128-bit minimum, so a fast, unsalted SHA-256 digest is the correct, lookupable choice — "hashed per Story 1.1's rule" is satisfied literally for the **new password itself** at reset-completion (which does go through `PwdlibPasswordHasher`), not for the token.
- **Why `account_locked` stays a 401, not a new 423.** Every authentication failure in this app is `401`, distinguished only by envelope `code` (Story 1.1's `invalid_credentials`, Story 1.4's `account_deactivated`, now `account_locked`). Introducing a different status code here would be an unexplained inconsistency with no benefit — the frontend already branches on `error.code`, not the HTTP status, for anything beyond "is this a 2xx."
- **The account-locked response is a deliberate, narrow exception to Story 1.3's "always identical 401" rule, for a different reason than Story 1.4's `account_deactivated` exception.** Story 1.4's exception applies only to a caller who *already holds a valid token for their own account* — no other-account information can leak. This story's `account_locked` response is shown to an *unauthenticated* caller and does reveal that a guessed username is real once they've caused 5 failures against it — but that's an inherent, OWASP-accepted property of any lockout mechanism with user-visible feedback (the alternative is no cooldown signal at all, which EXPERIENCE.md explicitly rules out). Don't try to further disguise this; don't generalize it into "unauthenticated responses can now vary" either — this is one specific, bounded exception.
- **Extending the shared form shell now, not deferring a third time.** `deferred-work.md`'s Story 1.2 entry named this story by number as the trigger for revisiting `LoginPage.tsx`/`BootstrapForm.tsx`'s duplication. This story adds two more near-identical forms, making it the fourth/fifth occurrence — `AuthFormShell` (Task 7) is a minimal, mechanical extraction (just the `Container`/`Typography`/`Box` scaffold), not a bigger design-system component; Story 1.6 (Design System Foundation) is where any deeper shared-component work belongs.
- **Completing a reset does not revoke other active sessions for that user.** No per-user session registry exists (Story 1.4's `revoked_tokens` is keyed by individual `jti`, not by user) — a session issued before a compromise-driven reset keeps working until it naturally expires. Building bulk per-user revocation is out of scope for AD-11's schema and this story's ACs; flagged here rather than silently left unstated.
- **No new Nginx/CI changes needed.** `/auth/` is already a proxied prefix (Story 1.1); `/auth/forgot-password` and `/auth/reset-password` fall under it with no config change.

### Project Structure Notes

- New backend files: `ports/password_reset.py`, `adapters/persistence/password_reset.py`, `domain/password_reset.py`, a new Alembic revision on top of `a2fafc72668b`, `tests/domain/test_password_reset_service.py`, `tests/adapters/persistence/test_password_reset_token_repository.py`.
- Modified backend files: `config.py` (3 new `Settings` fields), `domain/models.py` (`User` fields + `PasswordResetToken`), `ports/users.py` (4 new abstract methods), `adapters/persistence/users.py` (columns + methods), `adapters/persistence/__init__.py` (register new model module), `domain/auth.py` (`AccountLocked`, lockout logic), `api/auth/routes.py` (new endpoints + `_account_locked`/`_invalid_reset_token` helpers), `tests/conftest.py`, `tests/domain/test_auth_service.py`, `tests/adapters/persistence/test_user_repository.py`, `tests/api/test_auth_routes.py`.
- New frontend files: `web/src/components/AuthFormShell.tsx`, `web/src/pages/ForgotPasswordPage.tsx`, `web/src/pages/ResetPasswordPage.tsx`, and their `*.test.tsx` files.
- Modified frontend files: `web/src/pages/LoginPage.tsx` (shell refactor, cooldown UI, forgot-password link), `web/src/pages/LoginPage.test.tsx`, `web/src/pages/BootstrapForm.tsx` (shell refactor only), `web/src/router.tsx` (2 new routes).
- Fully additive to the existing `domain/`, `ports/`, `adapters/persistence/`, `api/auth/` packages and the existing two-page-plus-bootstrap frontend — no new top-level directories.

### Previous Story Intelligence (from 1-4-session-invalidation-logout-revocation)

- One-class-one-job domain services, constructor-injected with only the collaborators actually used — `PasswordResetService` (Task 5) follows this; lockout logic deliberately does *not* get its own class (see Dev Notes) because it fails this test differently than `SessionService` did.
- Fakes are defined locally per test file, not shared/imported — continue that for `test_password_reset_service.py` and the `test_auth_service.py` additions.
- A co-transactional audit write accompanies every security-relevant mutation (AD-7) — this story adds `account.locked`, `password_reset.requested`, `password_reset.completed` to the existing `login.success`/`login.failure`/`bootstrap.success`/`bootstrap.failure`/`logout` vocabulary. `login`/`bootstrap` each disambiguate success/failure with a suffix because both outcomes are reachable and worth telling apart in the audit trail; this story's three new actions don't get a `.success`/`.failure` pair each because every one of them has exactly one meaning (locked, requested, completed) — `password_reset`'s *failure* path (invalid/expired/used token) is deliberately not audited at all, since an unauthenticated caller triggers it and it's the same no-oracle reasoning as `InvalidCredentials`/`InvalidResetToken` not being logged per-attempt elsewhere.
- Story 1.4 established the "distinct 401 message is fine when no other-account info leaks" precedent (`account_deactivated`) — this story both reuses it (`account_locked`, for a different, narrower reason) and is careful to explain *why* the reasoning differs (see Dev Notes) rather than treating the precedent as a blanket license.
- Story 1.4's own review left two items unaddressed by design, both still open: no audit entry for authorization-rejection paths at `get_current_user`/`get_current_session` (untouched by this story — lockout is a *pre-authentication* concern, not a rejection at the session-dependency layer), and `revoked_tokens` has no cleanup/expiry job (also untouched — this story's own new `password_reset_tokens` table has the same unbounded-growth characteristic and is called out above as a known, accepted gap at Phase-1 scale).
- Verify against real infrastructure, not mocks, for anything DB-backed — the new `test_password_reset_token_repository.py` and the `test_user_repository.py` additions continue the `seed_user`/`create_session_factory`-against-live-Postgres convention.

### Git Intelligence

- `HEAD` is `5da4e5b` ("Story 1.3 + 1.4: role-scoped access, last-admin guard, session revocation"), working tree clean. This story is written directly against that committed state — no uncommitted work to account for (unlike Story 1.4, which was written against Story 1.3's then-uncommitted tree).
- Migration chain so far: `3066ace65d15` (baseline) → `98ddc369b175` (`users`/`audit_log_entries`) → `a2fafc72668b` (`revoked_tokens`). This story's migration is the fourth revision, built on `a2fafc72668b`.
- Established migration convention (from `98ddc369b175`/`a2fafc72668b`): autogenerate first, then hand-reformat to double-quote/one-arg-per-line style; this story additionally requires hand-adding `server_default="0"` to the new `failed_login_count` column, which autogenerate will not infer on its own (see Task 3).
- Commit style: one commit per logical unit of work (sometimes bundling stories, as `5da4e5b` did for 1.3+1.4), imperative summary line, body listing code-review fixes folded in, ending with the `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>` trailer.

### Latest Technical Notes (from web research, 2026-07-18)

- OWASP's Blocking Brute Force Attacks / Authentication Cheat Sheet guidance: lockout thresholds in the 3–10 range and lockout durations around 15–20 minutes are both squarely typical — this story's defaults (5 attempts / 15 minutes) sit comfortably inside that range; no change recommended, only noted as validated rather than arbitrary. [Source: OWASP Blocking Brute Force Attacks; OWASP Authentication Cheat Sheet]
- OWASP's Forgot Password Cheat Sheet: reset tokens should carry ≥128 bits of entropy, be single-use, expire within roughly 15–60 minutes, and be stored hashed (never plaintext) so a DB compromise doesn't hand out live reset capability. This story's `secrets.token_urlsafe(32)` (256 bits) and 60-minute default TTL both meet or exceed these; storing only a SHA-256 digest (not the raw token) follows the same guidance. [Source: OWASP Forgot Password Cheat Sheet]

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.5: Login Lockout & Password Reset]
- [Source: _bmad-output/planning-artifacts/prds/prd-GrowthTrack-2026-07-14/prd.md#FR-1] (Administrator Login & Session — the parent requirement; lockout/reset themselves are not separately numbered FRs, per PRD §13/§14's explicit "deliberately left to downstream... work" note)
- [Source: _bmad-output/planning-artifacts/prds/prd-GrowthTrack-2026-07-14/review-edge-case-hunter.md] (original source of the lockout/reset requirement, prior to epics.md's story breakdown)
- [Source: _bmad-output/planning-artifacts/architecture/architecture-GrowthTrack-2026-07-14/ARCHITECTURE-SPINE.md#AD-11] ("`User` gains `failed_login_count` and `locked_until` columns... `PasswordResetToken` is a standalone entity... single-use, invalidated on first use or on expiry... All four are `adapters/persistence` additions... none require a new port or adapter")
- [Source: _bmad-output/planning-artifacts/architecture/architecture-GrowthTrack-2026-07-14/ARCHITECTURE-SPINE.md#AD-7] (co-transactional audit write — extended here to `account.locked`/`password_reset.requested`/`password_reset.completed`)
- [Source: _bmad-output/planning-artifacts/architecture/architecture-GrowthTrack-2026-07-14/ARCHITECTURE-SPINE.md#Deferred] ("Exact retry policy magnitude (attempt count, backoff)... Policy values, not structural decisions — left configurable" — the basis for Task 1's `Settings` fields)
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-GrowthTrack-2026-07-14/EXPERIENCE.md#State Patterns] ("login lockout after repeated failed attempts shows a cooldown timer, not a bare 'try again' loop" — verbatim source of Task 7's countdown requirement) and `#Voice and Tone` (no vague copy, state the real cause/consequence — governs the new lockout/reset UI copy)
- [Source: _bmad-output/implementation-artifacts/1-4-session-invalidation-logout-revocation.md#Dev Notes] (audit-write precedent, distinct-401-message precedent and its stated limits)
- [Source: _bmad-output/implementation-artifacts/deferred-work.md] ("Revisit if a third similar form appears (e.g. Story 1.5's password reset)" — direct trigger for Task 7's `AuthFormShell` extraction)
- [Source: domain/auth.py], [Source: domain/models.py], [Source: domain/administrators.py] (one-class-one-job precedent), [Source: ports/users.py], [Source: ports/audit.py], [Source: ports/auth.py], [Source: ports/sessions.py] (new-port precedent), [Source: adapters/persistence/users.py], [Source: adapters/persistence/sessions.py] (new-adapter-module precedent), [Source: adapters/persistence/audit_log.py], [Source: adapters/persistence/__init__.py], [Source: api/auth/routes.py], [Source: api/auth/dependencies.py], [Source: config.py] (`jwt_expiry_minutes`'s `Field(default=..., gt=0)` precedent), [Source: tests/conftest.py], [Source: tests/api/test_auth_routes.py], [Source: web/src/pages/LoginPage.tsx], [Source: web/src/pages/BootstrapForm.tsx], [Source: web/src/router.tsx], [Source: web/src/api/authClient.ts]
- OWASP Blocking Brute Force Attacks — https://owasp.org/www-community/controls/Blocking_Brute_Force_Attacks
- OWASP Authentication Cheat Sheet — https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- OWASP Forgot Password Cheat Sheet — https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html

## Dev Agent Record

### Agent Model Used

Claude Sonnet 5 (claude-sonnet-5)

### Debug Log References

- `uv run alembic revision --autogenerate -m "login lockout and password reset"` generated `8ae7e5d0d8c9`; hand-added `server_default="0"` to the `failed_login_count` `add_column` (autogenerate omitted it, as expected) and reformatted to the repo's double-quote/one-arg-per-line style.
- Migration round-trip (`alembic upgrade head` → `downgrade base` → `upgrade head`) verified clean against the local `gt-test-postgres` container.
- `uv run pytest` (103 passed), `uv run ruff check .`, `uv run mypy api domain ports adapters scheduler config.py alembic/env.py`, and `uv run lint-imports` all clean.
- `npx vitest run` (27 passed), `npx tsc -b`, and `npx eslint .` all clean on the frontend — the one `eslint` finding (`react-hooks/set-state-in-effect` in `LoginPage.tsx`) is pre-existing on `HEAD` (verified by lint-checking the unmodified file), not introduced by this story.

### Completion Notes List

- Implemented login lockout (AC #1): `Settings`-sourced threshold/duration, atomic `UPDATE ... RETURNING` failed-count increment, lockout check ordered before password verification (proven via a call-count spy on the password hasher), `account.locked` audit entry, and a frontend cooldown timer that disables the submit button.
- Implemented forgot/reset password (AC #2-#5): `PasswordResetToken` entity with a SHA-256 (not bcrypt) token hash — documented in `domain/password_reset.py` why bcrypt's per-hash salt would make the required equality lookup impossible; single-use/expiring tokens; one generic `invalid_reset_token` response for unknown/expired/used tokens; `/auth/forgot-password` returns an identical response regardless of account state (no username-enumeration oracle); the raw reset link is logged server-side only (never returned in the HTTP response) since no email/SMS delivery adapter exists in this codebase — flagged in the story's Dev Notes as an open, PM/Architect-confirmable assumption, not silently resolved.
- Extracted `AuthFormShell` (Task 7) per the Story 1.2 code-review deferral, resolving the `LoginPage`/`BootstrapForm` duplication now that `ForgotPasswordPage`/`ResetPasswordPage` would otherwise have made it a fourth/fifth copy.
- Two `[ASSUMPTION — CONFIRM WITH PM/ARCHITECT]` items remain flagged, not resolved, per the story's own Dev Notes: (1) the reset-link delivery mechanism (log-only, no email/SMS adapter), and (2) `failed_login_count` is cumulative until a success/reset clears it — there is no `last_failed_attempt_at` column to implement a true rolling 15-minute window, since AD-11's schema doesn't include one.
- Frontend lockout-countdown test uses a real (not faked) 1-second wait via `waitFor` rather than `vi.useFakeTimers()` — fake timers proved unreliable in combination with `@testing-library/user-event` in this environment (hung indefinitely and leaked into subsequent tests); the real-timer approach is slower but deterministic and this repo has no existing fake-timer precedent to follow instead.

### File List

**New:**
- `ports/password_reset.py`
- `adapters/persistence/password_reset.py`
- `domain/password_reset.py`
- `alembic/versions/8ae7e5d0d8c9_login_lockout_and_password_reset.py`
- `tests/domain/test_password_reset_service.py`
- `tests/adapters/persistence/test_password_reset_token_repository.py`
- `web/src/components/AuthFormShell.tsx`
- `web/src/pages/ForgotPasswordPage.tsx`
- `web/src/pages/ForgotPasswordPage.test.tsx`
- `web/src/pages/ResetPasswordPage.tsx`
- `web/src/pages/ResetPasswordPage.test.tsx`

**Modified:**
- `config.py`
- `.env.example`
- `domain/models.py`
- `ports/users.py`
- `adapters/persistence/users.py`
- `adapters/persistence/__init__.py`
- `domain/auth.py`
- `api/auth/routes.py`
- `api/main.py`
- `tests/conftest.py`
- `tests/domain/test_auth_service.py`
- `tests/adapters/persistence/test_user_repository.py`
- `tests/api/test_auth_routes.py`
- `web/src/pages/LoginPage.tsx`
- `web/src/pages/LoginPage.test.tsx`
- `web/src/pages/BootstrapForm.tsx`
- `web/src/router.tsx`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`

### Change Log

- 2026-07-18: Implemented Story 1.5 (Login Lockout & Password Reset) — `Settings`-configurable lockout threshold/duration and reset-token TTL; atomic failed-login counting, `AccountLocked` (pre-verification lockout check, `account.locked` audit entry); `PasswordResetToken` entity/table/migration (`8ae7e5d0d8c9`), `PasswordResetService` (SHA-256 token hash, single-use/expiring, enumeration-safe `/auth/forgot-password`, generic `invalid_reset_token` on `/auth/reset-password`); shared `AuthFormShell`, lockout cooldown UI, and new `ForgotPasswordPage`/`ResetPasswordPage`. Full backend (103) and frontend (27) test suites pass, along with ruff/mypy/lint-imports and eslint/tsc. Status moved to review.
