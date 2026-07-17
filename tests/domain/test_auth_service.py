import uuid
from datetime import UTC, datetime

import pytest

from domain.auth import AuthenticationService, InvalidCredentials
from domain.models import AuditLogEntry, Role, User, UserStatus
from ports.auth import PwdlibPasswordHasher


def _make_user(
    username: str, password: str, status: UserStatus = UserStatus.ACTIVE
) -> User:
    hasher = PwdlibPasswordHasher()
    return User(
        id=uuid.uuid4(),
        username=username,
        hashed_password=hasher.hash(password),
        role=Role.ADMINISTRATOR,
        status=status,
        version=1,
        created_at=datetime.now(UTC),
    )


class FakeUserRepository:
    def __init__(self, users: list[User]) -> None:
        self._by_username = {u.username: u for u in users}

    async def get_by_username(self, username: str) -> User | None:
        return self._by_username.get(username)

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        raise NotImplementedError

    async def add(self, user: User) -> None:
        raise NotImplementedError


class FakeAuditLogRepository:
    def __init__(self) -> None:
        self.entries: list[AuditLogEntry] = []

    async def add(self, entry: AuditLogEntry) -> None:
        self.entries.append(entry)


class SpyPasswordHasher(PwdlibPasswordHasher):
    """Counts verify() calls without changing their behavior — lets tests
    prove the dummy bcrypt verification actually ran, without depending on
    wall-clock timing (flaky under CI scheduler jitter)."""

    def __init__(self) -> None:
        super().__init__()
        self.verify_call_count = 0

    def verify(self, plain_password: str, hashed_password: str) -> bool:
        self.verify_call_count += 1
        return super().verify(plain_password, hashed_password)


def _service(users: list[User]) -> AuthenticationService:
    return AuthenticationService(
        FakeUserRepository(users), PwdlibPasswordHasher(), FakeAuditLogRepository()
    )


async def test_authenticate_returns_user_for_correct_credentials():
    user = _make_user("admin", "correct-horse-battery-staple")
    service = _service([user])

    result = await service.authenticate("admin", "correct-horse-battery-staple")

    assert result is not None
    assert result.id == user.id


async def test_authenticate_returns_none_for_wrong_password():
    user = _make_user("admin", "correct-horse-battery-staple")
    service = _service([user])

    result = await service.authenticate("admin", "wrong-password")

    assert result is None


async def test_authenticate_returns_none_for_nonexistent_username():
    service = _service([])

    result = await service.authenticate("nobody", "anything")

    assert result is None


async def test_authenticate_returns_none_for_inactive_user_even_with_correct_password():
    user = _make_user("admin", "correct-horse-battery-staple", status=UserStatus.INACTIVE)
    service = _service([user])

    result = await service.authenticate("admin", "correct-horse-battery-staple")

    assert result is None


async def test_authenticate_runs_a_real_verification_for_a_nonexistent_username():
    """AC #2: a nonexistent-username attempt still runs a bcrypt verification
    (against a fixed dummy hash) rather than short-circuiting, so response
    timing can't reveal whether the username exists."""
    spy = SpyPasswordHasher()
    service = AuthenticationService(FakeUserRepository([]), spy, FakeAuditLogRepository())

    await service.authenticate("nobody", "anything")

    assert spy.verify_call_count == 1


async def test_authenticate_runs_exactly_one_verification_for_a_real_user_too():
    user = _make_user("admin", "correct-horse-battery-staple")
    spy = SpyPasswordHasher()
    # SpyPasswordHasher wraps PwdlibPasswordHasher but _make_user hashed with
    # a separate instance — verify() still works since both use the same
    # bcrypt scheme, only the call-counting wrapper differs.
    service = AuthenticationService(FakeUserRepository([user]), spy, FakeAuditLogRepository())

    await service.authenticate("admin", "wrong-password")

    assert spy.verify_call_count == 1


async def test_login_returns_the_user_and_writes_a_success_audit_entry():
    user = _make_user("admin", "correct-horse-battery-staple")
    audit_log = FakeAuditLogRepository()
    service = AuthenticationService(FakeUserRepository([user]), PwdlibPasswordHasher(), audit_log)

    result = await service.login("admin", "correct-horse-battery-staple")

    assert result.id == user.id
    assert len(audit_log.entries) == 1
    assert audit_log.entries[0].action == "login.success"
    assert audit_log.entries[0].actor_user_id == user.id


async def test_login_raises_and_writes_a_failure_audit_entry_on_bad_credentials():
    audit_log = FakeAuditLogRepository()
    service = AuthenticationService(FakeUserRepository([]), PwdlibPasswordHasher(), audit_log)

    with pytest.raises(InvalidCredentials):
        await service.login("nobody", "anything")

    assert len(audit_log.entries) == 1
    assert audit_log.entries[0].action == "login.failure"
    assert audit_log.entries[0].actor_user_id is None
    assert audit_log.entries[0].details == {"username": "nobody"}


async def test_login_raises_for_an_inactive_user_and_still_audits_the_failure():
    user = _make_user("admin", "correct-horse-battery-staple", status=UserStatus.INACTIVE)
    audit_log = FakeAuditLogRepository()
    service = AuthenticationService(FakeUserRepository([user]), PwdlibPasswordHasher(), audit_log)

    with pytest.raises(InvalidCredentials):
        await service.login("admin", "correct-horse-battery-staple")

    assert audit_log.entries[0].action == "login.failure"
