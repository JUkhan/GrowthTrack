import uuid
from datetime import datetime

from domain.models import AuditLogEntry
from domain.sessions import SessionService


class FakeRevokedTokenRepository:
    def __init__(self) -> None:
        self.calls: list[tuple[uuid.UUID, datetime]] = []

    async def revoke(self, jti: uuid.UUID, revoked_at: datetime) -> None:
        self.calls.append((jti, revoked_at))

    async def is_revoked(self, jti: uuid.UUID) -> bool:
        return any(jti == recorded_jti for recorded_jti, _ in self.calls)


class FakeAuditLogRepository:
    def __init__(self) -> None:
        self.entries: list[AuditLogEntry] = []

    async def add(self, entry: AuditLogEntry) -> None:
        self.entries.append(entry)


async def test_logout_revokes_the_given_jti():
    revoked_tokens = FakeRevokedTokenRepository()
    audit_log = FakeAuditLogRepository()
    service = SessionService(revoked_tokens, audit_log)
    jti = uuid.uuid4()

    await service.logout(uuid.uuid4(), jti)

    assert len(revoked_tokens.calls) == 1
    assert revoked_tokens.calls[0][0] == jti


async def test_logout_writes_exactly_one_logout_audit_entry():
    revoked_tokens = FakeRevokedTokenRepository()
    audit_log = FakeAuditLogRepository()
    service = SessionService(revoked_tokens, audit_log)
    user_id = uuid.uuid4()

    await service.logout(user_id, uuid.uuid4())

    assert len(audit_log.entries) == 1
    assert audit_log.entries[0].action == "logout"
    assert audit_log.entries[0].actor_user_id == user_id
