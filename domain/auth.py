"""Credential verification + login orchestration (AC #2, #4; AD-7 audit write).

Revocation (Story 1.4) is deliberately out of scope here — see that story's
Dev Notes.
"""

from __future__ import annotations

import math
import uuid
from datetime import UTC, datetime, timedelta

from domain.models import AuditLogEntry, Role, User, UserStatus
from ports.audit import AuditLogRepository
from ports.auth import PasswordHasher
from ports.users import UserRepository

# A precomputed hash with no matching plaintext. Verified against on a
# non-existent username so a failed lookup and a failed password check cost
# the same bcrypt work — timing alone can't reveal whether the username
# exists (AC #2).
_DUMMY_HASH = "$2b$12$C6UzMDM.H6dfI/f/IKcEeO0rQiXQ/Q0kMe.Y6cJv7c1XxK/y6c6Da"


class InvalidCredentials(Exception):
    """Raised by ``AuthenticationService.login`` on any authentication failure —
    unknown username, wrong password, or an inactive account."""


class AccountLocked(Exception):
    def __init__(self, retry_after_seconds: int) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__("Account is temporarily locked due to repeated failed login attempts")


class AuthenticationService:
    def __init__(
        self,
        users: UserRepository,
        password_hasher: PasswordHasher,
        audit_log: AuditLogRepository,
        lockout_threshold: int,
        lockout_duration: timedelta,
    ) -> None:
        self._users = users
        self._password_hasher = password_hasher
        self._audit_log = audit_log
        self._lockout_threshold = lockout_threshold
        self._lockout_duration = lockout_duration

    async def authenticate(self, username: str, password: str) -> User | None:
        user = await self._users.get_by_username(username)

        if user is None:
            self._password_hasher.verify(password, _DUMMY_HASH)
            return None

        now = datetime.now(UTC)
        is_eligible = user.status == UserStatus.ACTIVE and user.role == Role.ADMINISTRATOR
        if user.locked_until is not None:
            if user.locked_until > now:
                if is_eligible:
                    raise AccountLocked(
                        retry_after_seconds=max(
                            1, math.ceil((user.locked_until - now).total_seconds())
                        )
                    )
                # A wrong-role/inactive account's stale lockout state isn't
                # revealed as `account_locked` — falls through to the same
                # generic response any other ineligible account gets below,
                # instead of leaking that this account was ever locked.
            else:
                # Lockout window has expired — reset the counter so the next
                # attempt isn't judged against a stale count and instantly
                # re-locked (no time-decay otherwise; review-confirmed:
                # reset on expiry rather than a rolling window).
                await self._users.clear_lockout(user.id)
                user.failed_login_count = 0
                user.locked_until = None

        # Always run the real verification (even for an inactive account) so
        # timing doesn't distinguish "wrong password" from "correct password,
        # inactive account" — both must cost one bcrypt verify.
        password_ok = self._password_hasher.verify(password, user.hashed_password)

        if not password_ok and user.status == UserStatus.ACTIVE and user.role == Role.ADMINISTRATOR:
            # Only count a wrong password on an otherwise-valid account — a
            # wrong-role or inactive-account failure already returns None for
            # reasons unrelated to a guessed password, and shouldn't let an
            # attacker rack up billable "confirmations" toward lockout.
            new_count = await self._users.increment_failed_login_count(user.id)
            if new_count >= self._lockout_threshold:
                await self._users.lock_until(user.id, now + self._lockout_duration)
                await self._audit_log.add(
                    AuditLogEntry(
                        id=uuid.uuid4(),
                        actor_user_id=user.id,
                        action="account.locked",
                        entity_type=None,
                        entity_id=None,
                        details={"failed_login_count": new_count},
                        created_at=now,
                    )
                )

        if not password_ok or user.status != UserStatus.ACTIVE or user.role != Role.ADMINISTRATOR:
            return None

        if user.failed_login_count or user.locked_until is not None:
            # A clean login always clears stale lockout state, so a
            # legitimate user isn't left "one more wrong password from
            # instant re-lock" after they finally get it right.
            await self._users.clear_lockout(user.id)

        return user

    async def login(self, username: str, password: str) -> User:
        """Authenticates and writes the co-transactional audit entry (AD-7) —
        the only path a route handler should use, since AD-1 reserves
        repository-port calls for ``domain/``."""
        try:
            user = await self.authenticate(username, password)
        except AccountLocked:
            await self._audit_log.add(
                AuditLogEntry(
                    id=uuid.uuid4(),
                    actor_user_id=None,
                    action="login.failure",
                    entity_type=None,
                    entity_id=None,
                    details={"username": username, "reason": "locked"},
                    created_at=datetime.now(UTC),
                )
            )
            raise

        if user is None:
            await self._audit_log.add(
                AuditLogEntry(
                    id=uuid.uuid4(),
                    actor_user_id=None,
                    action="login.failure",
                    entity_type=None,
                    entity_id=None,
                    details={"username": username},
                    created_at=datetime.now(UTC),
                )
            )
            raise InvalidCredentials()

        await self._audit_log.add(
            AuditLogEntry(
                id=uuid.uuid4(),
                actor_user_id=user.id,
                action="login.success",
                entity_type=None,
                entity_id=None,
                details=None,
                created_at=datetime.now(UTC),
            )
        )
        return user
