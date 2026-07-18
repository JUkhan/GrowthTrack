import uuid
from datetime import UTC, datetime, timedelta

import pytest

from domain.auth import AccountLocked, AuthenticationService, InvalidCredentials
from domain.models import AuditLogEntry, Role, User, UserStatus
from ports.auth import PwdlibPasswordHasher

_DEFAULT_LOCKOUT_THRESHOLD = 5
_DEFAULT_LOCKOUT_DURATION = timedelta(minutes=15)


def _make_user(
    username: str,
    password: str,
    status: UserStatus = UserStatus.ACTIVE,
    role: Role = Role.ADMINISTRATOR,
) -> User:
    hasher = PwdlibPasswordHasher()
    return User(
        id=uuid.uuid4(),
        username=username,
        hashed_password=hasher.hash(password),
        role=role,
        status=status,
        version=1,
        created_at=datetime.now(UTC),
    )


class FakeUserRepository:
    def __init__(self, users: list[User]) -> None:
        self._by_username = {u.username: u for u in users}
        self._by_id = {u.id: u for u in users}
        self.increment_calls: list[uuid.UUID] = []
        self.lock_calls: list[tuple[uuid.UUID, datetime]] = []
        self.clear_calls: list[uuid.UUID] = []

    async def get_by_username(self, username: str) -> User | None:
        return self._by_username.get(username)

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return self._by_id.get(user_id)

    async def add(self, user: User) -> None:
        raise NotImplementedError

    async def increment_failed_login_count(self, user_id: uuid.UUID) -> int:
        self.increment_calls.append(user_id)
        user = self._by_id[user_id]
        user.failed_login_count += 1
        return user.failed_login_count

    async def lock_until(self, user_id: uuid.UUID, until: datetime) -> None:
        self.lock_calls.append((user_id, until))
        self._by_id[user_id].locked_until = until

    async def clear_lockout(self, user_id: uuid.UUID) -> None:
        self.clear_calls.append(user_id)
        user = self._by_id[user_id]
        user.failed_login_count = 0
        user.locked_until = None

    async def update_password(self, user_id: uuid.UUID, hashed_password: str) -> None:
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


def _service(
    users: list[User],
    lockout_threshold: int = _DEFAULT_LOCKOUT_THRESHOLD,
    lockout_duration: timedelta = _DEFAULT_LOCKOUT_DURATION,
) -> AuthenticationService:
    return AuthenticationService(
        FakeUserRepository(users),
        PwdlibPasswordHasher(),
        FakeAuditLogRepository(),
        lockout_threshold=lockout_threshold,
        lockout_duration=lockout_duration,
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


async def test_authenticate_returns_none_for_a_sales_user_even_with_correct_password():
    user = _make_user("sales", "correct-horse-battery-staple", role=Role.SALES_USER)
    service = _service([user])

    result = await service.authenticate("sales", "correct-horse-battery-staple")

    assert result is None


async def test_authenticate_returns_none_for_a_manager_even_with_correct_password():
    user = _make_user("manager", "correct-horse-battery-staple", role=Role.MANAGER)
    service = _service([user])

    result = await service.authenticate("manager", "correct-horse-battery-staple")

    assert result is None


async def test_authenticate_runs_a_real_verification_for_a_nonexistent_username():
    """AC #2: a nonexistent-username attempt still runs a bcrypt verification
    (against a fixed dummy hash) rather than short-circuiting, so response
    timing can't reveal whether the username exists."""
    spy = SpyPasswordHasher()
    service = AuthenticationService(
        FakeUserRepository([]),
        spy,
        FakeAuditLogRepository(),
        lockout_threshold=_DEFAULT_LOCKOUT_THRESHOLD,
        lockout_duration=_DEFAULT_LOCKOUT_DURATION,
    )

    await service.authenticate("nobody", "anything")

    assert spy.verify_call_count == 1


async def test_authenticate_runs_exactly_one_verification_for_a_real_user_too():
    user = _make_user("admin", "correct-horse-battery-staple")
    spy = SpyPasswordHasher()
    # SpyPasswordHasher wraps PwdlibPasswordHasher but _make_user hashed with
    # a separate instance — verify() still works since both use the same
    # bcrypt scheme, only the call-counting wrapper differs.
    service = AuthenticationService(
        FakeUserRepository([user]),
        spy,
        FakeAuditLogRepository(),
        lockout_threshold=_DEFAULT_LOCKOUT_THRESHOLD,
        lockout_duration=_DEFAULT_LOCKOUT_DURATION,
    )

    await service.authenticate("admin", "wrong-password")

    assert spy.verify_call_count == 1


async def test_login_returns_the_user_and_writes_a_success_audit_entry():
    user = _make_user("admin", "correct-horse-battery-staple")
    audit_log = FakeAuditLogRepository()
    service = AuthenticationService(
        FakeUserRepository([user]),
        PwdlibPasswordHasher(),
        audit_log,
        lockout_threshold=_DEFAULT_LOCKOUT_THRESHOLD,
        lockout_duration=_DEFAULT_LOCKOUT_DURATION,
    )

    result = await service.login("admin", "correct-horse-battery-staple")

    assert result.id == user.id
    assert len(audit_log.entries) == 1
    assert audit_log.entries[0].action == "login.success"
    assert audit_log.entries[0].actor_user_id == user.id


async def test_login_raises_and_writes_a_failure_audit_entry_on_bad_credentials():
    audit_log = FakeAuditLogRepository()
    service = AuthenticationService(
        FakeUserRepository([]),
        PwdlibPasswordHasher(),
        audit_log,
        lockout_threshold=_DEFAULT_LOCKOUT_THRESHOLD,
        lockout_duration=_DEFAULT_LOCKOUT_DURATION,
    )

    with pytest.raises(InvalidCredentials):
        await service.login("nobody", "anything")

    assert len(audit_log.entries) == 1
    assert audit_log.entries[0].action == "login.failure"
    assert audit_log.entries[0].actor_user_id is None
    assert audit_log.entries[0].details == {"username": "nobody"}


async def test_login_raises_for_an_inactive_user_and_still_audits_the_failure():
    user = _make_user("admin", "correct-horse-battery-staple", status=UserStatus.INACTIVE)
    audit_log = FakeAuditLogRepository()
    service = AuthenticationService(
        FakeUserRepository([user]),
        PwdlibPasswordHasher(),
        audit_log,
        lockout_threshold=_DEFAULT_LOCKOUT_THRESHOLD,
        lockout_duration=_DEFAULT_LOCKOUT_DURATION,
    )

    with pytest.raises(InvalidCredentials):
        await service.login("admin", "correct-horse-battery-staple")

    assert audit_log.entries[0].action == "login.failure"


async def test_login_raises_for_a_non_administrator_role_and_still_audits_the_failure():
    user = _make_user("sales", "correct-horse-battery-staple", role=Role.SALES_USER)
    audit_log = FakeAuditLogRepository()
    service = AuthenticationService(
        FakeUserRepository([user]),
        PwdlibPasswordHasher(),
        audit_log,
        lockout_threshold=_DEFAULT_LOCKOUT_THRESHOLD,
        lockout_duration=_DEFAULT_LOCKOUT_DURATION,
    )

    with pytest.raises(InvalidCredentials):
        await service.login("sales", "correct-horse-battery-staple")

    assert audit_log.entries[0].action == "login.failure"


async def test_four_failures_then_a_correct_password_does_not_lock_the_account():
    user = _make_user("admin", "correct-horse-battery-staple")
    users_repo = FakeUserRepository([user])
    service = AuthenticationService(
        users_repo,
        PwdlibPasswordHasher(),
        FakeAuditLogRepository(),
        lockout_threshold=5,
        lockout_duration=timedelta(minutes=15),
    )

    for _ in range(4):
        result = await service.authenticate("admin", "wrong-password")
        assert result is None

    result = await service.authenticate("admin", "correct-horse-battery-staple")

    assert result is not None
    assert users_repo.lock_calls == []


async def test_fifth_consecutive_wrong_password_failure_locks_the_account():
    user = _make_user("admin", "correct-horse-battery-staple")
    users_repo = FakeUserRepository([user])
    audit_log = FakeAuditLogRepository()
    service = AuthenticationService(
        users_repo,
        PwdlibPasswordHasher(),
        audit_log,
        lockout_threshold=5,
        lockout_duration=timedelta(minutes=15),
    )

    for _ in range(4):
        await service.authenticate("admin", "wrong-password")
    assert users_repo.lock_calls == []

    result = await service.authenticate("admin", "wrong-password")

    assert result is None
    assert len(users_repo.lock_calls) == 1
    assert users_repo.lock_calls[0][0] == user.id
    locked_entries = [e for e in audit_log.entries if e.action == "account.locked"]
    assert len(locked_entries) == 1
    assert locked_entries[0].actor_user_id == user.id
    assert locked_entries[0].details == {"failed_login_count": 5}


async def test_sixth_attempt_while_locked_raises_account_locked_without_verifying_password():
    user = _make_user("admin", "correct-horse-battery-staple")
    user.locked_until = datetime.now(UTC) + timedelta(minutes=10)
    users_repo = FakeUserRepository([user])
    spy = SpyPasswordHasher()
    service = AuthenticationService(
        users_repo,
        spy,
        FakeAuditLogRepository(),
        lockout_threshold=5,
        lockout_duration=timedelta(minutes=15),
    )

    with pytest.raises(AccountLocked) as exc_info:
        # Even the correct password is rejected while locked.
        await service.authenticate("admin", "correct-horse-battery-staple")

    assert 0 < exc_info.value.retry_after_seconds <= 600
    assert spy.verify_call_count == 0


async def test_successful_login_after_lockout_expires_clears_lockout_state():
    user = _make_user("admin", "correct-horse-battery-staple")
    user.failed_login_count = 3
    user.locked_until = datetime.now(UTC) - timedelta(seconds=1)
    users_repo = FakeUserRepository([user])
    service = AuthenticationService(
        users_repo,
        PwdlibPasswordHasher(),
        FakeAuditLogRepository(),
        lockout_threshold=5,
        lockout_duration=timedelta(minutes=15),
    )

    result = await service.authenticate("admin", "correct-horse-battery-staple")

    assert result is not None
    assert users_repo.clear_calls == [user.id]


async def test_a_locked_but_deactivated_account_does_not_raise_account_locked():
    """Review fix: a stale locked_until must not leak lockout state for an
    account that's no longer eligible (deactivated/demoted) — it should fall
    through to the same generic None every other ineligible account gets."""
    user = _make_user("admin", "correct-horse-battery-staple", status=UserStatus.INACTIVE)
    user.locked_until = datetime.now(UTC) + timedelta(minutes=10)
    service = AuthenticationService(
        FakeUserRepository([user]),
        PwdlibPasswordHasher(),
        FakeAuditLogRepository(),
        lockout_threshold=5,
        lockout_duration=timedelta(minutes=15),
    )

    result = await service.authenticate("admin", "correct-horse-battery-staple")

    assert result is None


async def test_a_wrong_password_right_after_lockout_expiry_does_not_instantly_relock():
    """Review fix: the lockout counter resets when locked_until has passed,
    so a single post-expiry mistake starts a fresh count instead of
    immediately re-triggering another lockout."""
    user = _make_user("admin", "correct-horse-battery-staple")
    user.failed_login_count = 5
    user.locked_until = datetime.now(UTC) - timedelta(seconds=1)
    users_repo = FakeUserRepository([user])
    service = AuthenticationService(
        users_repo,
        PwdlibPasswordHasher(),
        FakeAuditLogRepository(),
        lockout_threshold=5,
        lockout_duration=timedelta(minutes=15),
    )

    result = await service.authenticate("admin", "wrong-password")

    assert result is None
    assert users_repo.clear_calls == [user.id]
    assert users_repo.lock_calls == []
    assert user.failed_login_count == 1


async def test_nonexistent_username_never_touches_lockout_methods():
    users_repo = FakeUserRepository([])
    service = AuthenticationService(
        users_repo,
        PwdlibPasswordHasher(),
        FakeAuditLogRepository(),
        lockout_threshold=5,
        lockout_duration=timedelta(minutes=15),
    )

    result = await service.authenticate("nobody", "anything")

    assert result is None
    assert users_repo.increment_calls == []
    assert users_repo.lock_calls == []
    assert users_repo.clear_calls == []


async def test_login_raises_account_locked_and_audits_a_login_failure_with_locked_reason():
    user = _make_user("admin", "correct-horse-battery-staple")
    user.locked_until = datetime.now(UTC) + timedelta(minutes=10)
    users_repo = FakeUserRepository([user])
    audit_log = FakeAuditLogRepository()
    service = AuthenticationService(
        users_repo,
        PwdlibPasswordHasher(),
        audit_log,
        lockout_threshold=5,
        lockout_duration=timedelta(minutes=15),
    )

    with pytest.raises(AccountLocked):
        await service.login("admin", "correct-horse-battery-staple")

    assert audit_log.entries[-1].action == "login.failure"
    assert audit_log.entries[-1].details == {"username": "admin", "reason": "locked"}
