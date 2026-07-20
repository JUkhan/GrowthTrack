import uuid
from datetime import UTC, datetime

import pytest

from domain.administrators import LastAdministratorError, LastAdministratorGuard
from domain.models import Role, User, UserStatus
from ports.auth import PwdlibPasswordHasher


def _make_user(role: Role, status: UserStatus) -> User:
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


class FakeUserRepository:
    def __init__(self, count: int) -> None:
        self._count = count
        self.count_active_administrators_calls = 0
        self.acquire_administrator_removal_lock_calls = 0

    async def count_active_administrators(self) -> int:
        self.count_active_administrators_calls += 1
        return self._count

    async def acquire_administrator_removal_lock(self) -> None:
        self.acquire_administrator_removal_lock_calls += 1


async def test_ensure_can_deactivate_raises_when_only_one_active_administrator_remains():
    target = _make_user(Role.ADMINISTRATOR, UserStatus.ACTIVE)
    users = FakeUserRepository(count=1)
    guard = LastAdministratorGuard(users)

    with pytest.raises(LastAdministratorError):
        await guard.ensure_can_deactivate(target)


async def test_ensure_can_deactivate_raises_when_no_active_administrators_remain():
    target = _make_user(Role.ADMINISTRATOR, UserStatus.ACTIVE)
    users = FakeUserRepository(count=0)
    guard = LastAdministratorGuard(users)

    with pytest.raises(LastAdministratorError):
        await guard.ensure_can_deactivate(target)


async def test_ensure_can_deactivate_does_not_raise_when_two_active_administrators_remain():
    target = _make_user(Role.ADMINISTRATOR, UserStatus.ACTIVE)
    users = FakeUserRepository(count=2)
    guard = LastAdministratorGuard(users)

    await guard.ensure_can_deactivate(target)

    assert users.acquire_administrator_removal_lock_calls == 1


async def test_ensure_can_deactivate_does_not_raise_for_a_sales_user_regardless_of_count():
    target = _make_user(Role.SALES_USER, UserStatus.ACTIVE)
    users = FakeUserRepository(count=1)
    guard = LastAdministratorGuard(users)

    await guard.ensure_can_deactivate(target)

    assert users.count_active_administrators_calls == 0
    # Non-Administrator targets short-circuit before the lock too — no need
    # to serialize a check that will always be skipped.
    assert users.acquire_administrator_removal_lock_calls == 0


async def test_ensure_can_deactivate_does_not_raise_for_an_already_inactive_administrator():
    target = _make_user(Role.ADMINISTRATOR, UserStatus.INACTIVE)
    users = FakeUserRepository(count=1)
    guard = LastAdministratorGuard(users)

    await guard.ensure_can_deactivate(target)

    assert users.count_active_administrators_calls == 0
    assert users.acquire_administrator_removal_lock_calls == 0
