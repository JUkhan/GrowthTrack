import uuid
from datetime import UTC, datetime

import pytest

from domain.bootstrap import BootstrapAlreadyComplete, BootstrapService
from domain.models import AuditLogEntry, Role, User, UserStatus
from ports.auth import PwdlibPasswordHasher


class FakeUserRepository:
    def __init__(self, users: list[User] | None = None) -> None:
        self.users: list[User] = list(users or [])
        self.lock_acquisitions = 0

    async def get_by_username(self, username: str) -> User | None:
        raise NotImplementedError

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        raise NotImplementedError

    async def add(self, user: User) -> None:
        self.users.append(user)

    async def has_any_administrator(self) -> bool:
        return any(u.role == Role.ADMINISTRATOR for u in self.users)

    async def acquire_bootstrap_lock(self) -> None:
        self.lock_acquisitions += 1


class FakeAuditLogRepository:
    def __init__(self) -> None:
        self.entries: list[AuditLogEntry] = []

    async def add(self, entry: AuditLogEntry) -> None:
        self.entries.append(entry)


def _existing_user(role: Role, status: UserStatus) -> User:
    hasher = PwdlibPasswordHasher()
    return User(
        id=uuid.uuid4(),
        username="admin",
        hashed_password=hasher.hash("correct-horse-battery-staple"),
        role=role,
        status=status,
        version=1,
        created_at=datetime.now(UTC),
    )


def _service(users: FakeUserRepository, audit_log: FakeAuditLogRepository) -> BootstrapService:
    return BootstrapService(users, PwdlibPasswordHasher(), audit_log)


async def test_is_required_is_true_on_an_empty_users_table():
    service = _service(FakeUserRepository(), FakeAuditLogRepository())

    assert await service.is_required() is True


async def test_is_required_is_false_once_an_active_administrator_exists():
    users = FakeUserRepository([_existing_user(Role.ADMINISTRATOR, UserStatus.ACTIVE)])
    service = _service(users, FakeAuditLogRepository())

    assert await service.is_required() is False


async def test_is_required_is_false_even_if_the_administrator_is_inactive():
    users = FakeUserRepository([_existing_user(Role.ADMINISTRATOR, UserStatus.INACTIVE)])
    service = _service(users, FakeAuditLogRepository())

    assert await service.is_required() is False


async def test_bootstrap_creates_an_active_administrator_with_a_bcrypt_hashed_password():
    users = FakeUserRepository()
    audit_log = FakeAuditLogRepository()
    service = _service(users, audit_log)

    user = await service.bootstrap("admin", "correct-horse-battery-staple")

    assert user.role == Role.ADMINISTRATOR
    assert user.status == UserStatus.ACTIVE
    assert user.hashed_password != "correct-horse-battery-staple"
    assert user.hashed_password.startswith("$2b$")
    assert users.users == [user]


async def test_bootstrap_acquires_the_lock_before_the_existence_check():
    users = FakeUserRepository()
    service = _service(users, FakeAuditLogRepository())

    await service.bootstrap("admin", "correct-horse-battery-staple")

    assert users.lock_acquisitions == 1


async def test_bootstrap_writes_a_bootstrap_success_audit_entry():
    users = FakeUserRepository()
    audit_log = FakeAuditLogRepository()
    service = _service(users, audit_log)

    user = await service.bootstrap("admin", "correct-horse-battery-staple")

    assert len(audit_log.entries) == 1
    assert audit_log.entries[0].action == "bootstrap.success"
    assert audit_log.entries[0].actor_user_id == user.id


async def test_bootstrap_raises_bootstrap_already_complete_if_an_administrator_already_exists():
    users = FakeUserRepository([_existing_user(Role.ADMINISTRATOR, UserStatus.ACTIVE)])
    audit_log = FakeAuditLogRepository()
    service = _service(users, audit_log)

    with pytest.raises(BootstrapAlreadyComplete):
        await service.bootstrap("someone-else", "correct-horse-battery-staple")

    assert len(audit_log.entries) == 1
    assert audit_log.entries[0].action == "bootstrap.failure"
    assert audit_log.entries[0].actor_user_id is None
    assert audit_log.entries[0].details == {"username": "someone-else"}


async def test_a_second_bootstrap_call_after_one_already_succeeded_raises():
    users = FakeUserRepository()
    service = _service(users, FakeAuditLogRepository())

    await service.bootstrap("admin", "correct-horse-battery-staple")

    with pytest.raises(BootstrapAlreadyComplete):
        await service.bootstrap("second-admin", "another-password")
