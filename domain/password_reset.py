"""Forgot/reset password flow (AC #2, #3, #4, #5; AD-7 audit write).

A separate module/class from ``domain/auth.py`` — password reset is a
genuinely distinct concern that never touches the login control flow,
following the same one-class-one-job precedent as ``SessionService``/
``LastAdministratorGuard``.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from domain.models import AuditLogEntry, PasswordResetToken, Role, UserStatus
from ports.audit import AuditLogRepository
from ports.auth import PasswordHasher
from ports.password_reset import PasswordResetTokenRepository
from ports.users import UserRepository


class InvalidResetToken(Exception):
    """Raised for an unknown, expired, or already-used reset token — one
    generic exception so the three cases aren't distinguishable (AC #4),
    same no-oracle rationale as ``InvalidCredentials``."""


def _hash_token(raw_token: str) -> str:
    # Not PwdlibPasswordHasher/bcrypt: bcrypt is designed for low-entropy
    # human passwords and its per-hash salting makes an equality lookup
    # (WHERE token_hash = :hash) impossible. A secrets.token_urlsafe(32)
    # reset token already has >=128 bits of entropy (OWASP's own minimum),
    # so a fast, unsalted SHA-256 digest is the correct, lookupable hash
    # here. "Hashed per Story 1.1's rule" applies to the new password
    # itself at reset-completion time, not to the token.
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


class PasswordResetService:
    def __init__(
        self,
        users: UserRepository,
        reset_tokens: PasswordResetTokenRepository,
        password_hasher: PasswordHasher,
        audit_log: AuditLogRepository,
        token_ttl: timedelta,
    ) -> None:
        self._users = users
        self._reset_tokens = reset_tokens
        self._password_hasher = password_hasher
        self._audit_log = audit_log
        self._token_ttl = token_ttl

    async def request_reset(self, username: str) -> str | None:
        """Returns the raw token for a valid Administrator, or ``None``
        otherwise. AC #3's enumeration-safety requirement (identical HTTP
        response either way) is enforced by the route, not here."""
        user = await self._users.get_by_username(username)
        if user is None or user.status != UserStatus.ACTIVE or user.role != Role.ADMINISTRATOR:
            return None

        raw_token = secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        await self._reset_tokens.add(
            PasswordResetToken(
                id=uuid.uuid4(),
                user_id=user.id,
                token_hash=_hash_token(raw_token),
                expires_at=now + self._token_ttl,
                used_at=None,
                created_at=now,
            )
        )
        await self._audit_log.add(
            AuditLogEntry(
                id=uuid.uuid4(),
                actor_user_id=user.id,
                action="password_reset.requested",
                entity_type=None,
                entity_id=None,
                details=None,
                created_at=now,
            )
        )
        return raw_token

    async def complete_reset(self, raw_token: str, new_password: str) -> None:
        token = await self._reset_tokens.get_by_hash(_hash_token(raw_token))
        now = datetime.now(UTC)
        if token is None or token.used_at is not None or token.expires_at <= now:
            raise InvalidResetToken()

        user = await self._users.get_by_id(token.user_id)
        if user is None or user.status != UserStatus.ACTIVE or user.role != Role.ADMINISTRATOR:
            # Same generic error as an unknown/expired/used token (AC #4) —
            # an account that's no longer eligible (deactivated or demoted
            # since the token was issued) shouldn't be resettable via an
            # otherwise-still-valid token either.
            raise InvalidResetToken()

        await self._reset_tokens.mark_used(token.id, now)
        await self._users.update_password(token.user_id, self._password_hasher.hash(new_password))
        # A reset also un-sticks any active lockout — an Administrator who
        # successfully proves account ownership via the reset token
        # shouldn't still have to wait out the lockout timer (AC #5).
        await self._users.clear_lockout(token.user_id)
        await self._audit_log.add(
            AuditLogEntry(
                id=uuid.uuid4(),
                actor_user_id=token.user_id,
                action="password_reset.completed",
                entity_type=None,
                entity_id=None,
                details=None,
                created_at=now,
            )
        )
