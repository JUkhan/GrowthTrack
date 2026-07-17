"""Credential verification + login orchestration (AC #2, #4; AD-7 audit write).

Role enforcement (Story 1.3) and revocation (Story 1.4) are deliberately
out of scope here — see the story's Dev Notes.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from domain.models import AuditLogEntry, User, UserStatus
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


class AuthenticationService:
    def __init__(
        self,
        users: UserRepository,
        password_hasher: PasswordHasher,
        audit_log: AuditLogRepository,
    ) -> None:
        self._users = users
        self._password_hasher = password_hasher
        self._audit_log = audit_log

    async def authenticate(self, username: str, password: str) -> User | None:
        user = await self._users.get_by_username(username)

        if user is None:
            self._password_hasher.verify(password, _DUMMY_HASH)
            return None

        # Always run the real verification (even for an inactive account) so
        # timing doesn't distinguish "wrong password" from "correct password,
        # inactive account" — both must cost one bcrypt verify.
        password_ok = self._password_hasher.verify(password, user.hashed_password)
        if not password_ok or user.status != UserStatus.ACTIVE:
            return None

        return user

    async def login(self, username: str, password: str) -> User:
        """Authenticates and writes the co-transactional audit entry (AD-7) —
        the only path a route handler should use, since AD-1 reserves
        repository-port calls for ``domain/``."""
        user = await self.authenticate(username, password)

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
