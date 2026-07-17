"""First-run Administrator creation (AC #1, #2, #3; AD-7 audit write).

A separate service from ``AuthenticationService`` (single-responsibility) —
see the story's Dev Notes for why bootstrap concurrency needs its own
advisory-lock-backed flow rather than a plain check-then-insert.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from domain.models import AuditLogEntry, Role, User, UserStatus
from ports.audit import AuditLogRepository
from ports.auth import PasswordHasher
from ports.users import UserRepository


class BootstrapAlreadyComplete(Exception):
    """Raised when a bootstrap attempt loses the race — an Administrator
    already exists by the time the advisory lock is acquired."""


class BootstrapService:
    def __init__(
        self,
        users: UserRepository,
        password_hasher: PasswordHasher,
        audit_log: AuditLogRepository,
    ) -> None:
        self._users = users
        self._password_hasher = password_hasher
        self._audit_log = audit_log

    async def is_required(self) -> bool:
        return not await self._users.has_any_administrator()

    async def bootstrap(self, username: str, password: str) -> User:
        # First, before the existence check: serializes concurrent bootstrap
        # attempts. The second caller blocks here until the first's
        # transaction commits or rolls back.
        await self._users.acquire_bootstrap_lock()

        # Re-checked *after* the lock is held — this is what actually closes
        # the race: whichever caller wins the lock and finds zero
        # Administrators is the only one that proceeds to create one.
        if not await self.is_required():
            await self._audit_log.add(
                AuditLogEntry(
                    id=uuid.uuid4(),
                    actor_user_id=None,
                    action="bootstrap.failure",
                    entity_type=None,
                    entity_id=None,
                    details={"username": username},
                    created_at=datetime.now(UTC),
                )
            )
            raise BootstrapAlreadyComplete()

        user = User(
            id=uuid.uuid4(),
            username=username,
            hashed_password=self._password_hasher.hash(password),
            role=Role.ADMINISTRATOR,
            status=UserStatus.ACTIVE,
            version=1,
            created_at=datetime.now(UTC),
        )
        await self._users.add(user)

        await self._audit_log.add(
            AuditLogEntry(
                id=uuid.uuid4(),
                actor_user_id=user.id,
                action="bootstrap.success",
                entity_type=None,
                entity_id=None,
                details=None,
                created_at=datetime.now(UTC),
            )
        )

        return user
