"""Session logout (AC #1; AD-7 co-transactional audit write).

A dedicated service, separate from ``domain/auth.py`` — this codebase's
one-class-one-job pattern (Story 1.3's ``LastAdministratorGuard`` precedent).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from domain.models import AuditLogEntry
from ports.audit import AuditLogRepository
from ports.sessions import RevokedTokenRepository


class SessionService:
    def __init__(
        self,
        revoked_tokens: RevokedTokenRepository,
        audit_log: AuditLogRepository,
    ) -> None:
        self._revoked_tokens = revoked_tokens
        self._audit_log = audit_log

    async def logout(self, user_id: uuid.UUID, jti: uuid.UUID) -> None:
        now = datetime.now(UTC)
        await self._revoked_tokens.revoke(jti, now)
        await self._audit_log.add(
            AuditLogEntry(
                id=uuid.uuid4(),
                actor_user_id=user_id,
                action="logout",
                entity_type=None,
                entity_id=None,
                details=None,
                created_at=now,
            )
        )
