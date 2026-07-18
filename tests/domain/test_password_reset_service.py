import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from domain.models import AuditLogEntry, PasswordResetToken, Role, User, UserStatus
from domain.password_reset import InvalidResetToken, PasswordResetService
from ports.auth import PwdlibPasswordHasher


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
        self.update_password_calls: list[tuple[uuid.UUID, str]] = []
        self.clear_calls: list[uuid.UUID] = []

    async def get_by_username(self, username: str) -> User | None:
        return self._by_username.get(username)

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return self._by_id.get(user_id)

    async def update_password(self, user_id: uuid.UUID, hashed_password: str) -> None:
        self.update_password_calls.append((user_id, hashed_password))
        self._by_id[user_id].hashed_password = hashed_password

    async def clear_lockout(self, user_id: uuid.UUID) -> None:
        self.clear_calls.append(user_id)


class FakePasswordResetTokenRepository:
    def __init__(self) -> None:
        self._by_hash: dict[str, PasswordResetToken] = {}
        self._by_id: dict[uuid.UUID, PasswordResetToken] = {}

    async def add(self, token: PasswordResetToken) -> None:
        self._by_hash[token.token_hash] = token
        self._by_id[token.id] = token

    async def get_by_hash(self, token_hash: str) -> PasswordResetToken | None:
        return self._by_hash.get(token_hash)

    async def mark_used(self, token_id: uuid.UUID, used_at: datetime) -> None:
        self._by_id[token_id].used_at = used_at


class FakeAuditLogRepository:
    def __init__(self) -> None:
        self.entries: list[AuditLogEntry] = []

    async def add(self, entry: AuditLogEntry) -> None:
        self.entries.append(entry)


_ServiceFixture = tuple[
    PasswordResetService,
    FakeUserRepository,
    FakePasswordResetTokenRepository,
    FakeAuditLogRepository,
]


def _service(users: list[User], token_ttl: timedelta = timedelta(minutes=60)) -> _ServiceFixture:
    users_repo = FakeUserRepository(users)
    reset_tokens = FakePasswordResetTokenRepository()
    audit_log = FakeAuditLogRepository()
    service = PasswordResetService(
        users_repo, reset_tokens, PwdlibPasswordHasher(), audit_log, token_ttl
    )
    return service, users_repo, reset_tokens, audit_log


async def test_request_reset_for_an_unknown_username_returns_none_and_creates_nothing():
    service, _, reset_tokens, audit_log = _service([])

    result = await service.request_reset("nobody")

    assert result is None
    assert reset_tokens._by_hash == {}
    assert audit_log.entries == []


async def test_request_reset_for_an_inactive_user_returns_none_and_creates_nothing():
    user = _make_user("admin", "correct-horse-battery-staple", status=UserStatus.INACTIVE)
    service, _, reset_tokens, audit_log = _service([user])

    result = await service.request_reset("admin")

    assert result is None
    assert reset_tokens._by_hash == {}
    assert audit_log.entries == []


async def test_request_reset_for_a_non_administrator_returns_none_and_creates_nothing():
    user = _make_user("sales", "correct-horse-battery-staple", role=Role.SALES_USER)
    service, _, reset_tokens, audit_log = _service([user])

    result = await service.request_reset("sales")

    assert result is None
    assert reset_tokens._by_hash == {}
    assert audit_log.entries == []


async def test_request_reset_for_a_valid_administrator_returns_a_raw_token_and_stores_a_hash():
    user = _make_user("admin", "correct-horse-battery-staple")
    service, _, reset_tokens, audit_log = _service([user])

    raw_token = await service.request_reset("admin")

    assert raw_token is not None
    assert len(reset_tokens._by_hash) == 1
    stored_token = next(iter(reset_tokens._by_hash.values()))
    # Proves the stored value is actually hashed, not the raw token verbatim.
    assert stored_token.token_hash != raw_token
    assert stored_token.user_id == user.id
    assert len(audit_log.entries) == 1
    assert audit_log.entries[0].action == "password_reset.requested"
    assert audit_log.entries[0].actor_user_id == user.id


async def test_complete_reset_with_the_right_token_succeeds():
    user = _make_user("admin", "correct-horse-battery-staple")
    service, users_repo, _, audit_log = _service([user])
    raw_token = await service.request_reset("admin")

    await service.complete_reset(raw_token, "new-password-123")

    assert users_repo.update_password_calls[0][0] == user.id
    assert users_repo.clear_calls == [user.id]
    assert audit_log.entries[-1].action == "password_reset.completed"
    assert audit_log.entries[-1].actor_user_id == user.id


async def test_complete_reset_for_a_deactivated_account_raises_the_same_generic_error():
    """A token issued while eligible must not remain redeemable once the
    account is deactivated or demoted before the token is used (review
    finding: complete_reset re-checks eligibility, mirroring request_reset)."""
    user = _make_user("admin", "correct-horse-battery-staple")
    service, users_repo, _, _ = _service([user])
    raw_token = await service.request_reset("admin")
    users_repo._by_id[user.id].status = UserStatus.INACTIVE
    users_repo._by_username[user.username].status = UserStatus.INACTIVE

    with pytest.raises(InvalidResetToken):
        await service.complete_reset(raw_token, "new-password-123")

    assert users_repo.update_password_calls == []
    assert users_repo.clear_calls == []


async def test_complete_reset_with_the_same_token_twice_raises_on_the_second_use():
    user = _make_user("admin", "correct-horse-battery-staple")
    service, _, _, _ = _service([user])
    raw_token = await service.request_reset("admin")

    await service.complete_reset(raw_token, "new-password-123")

    with pytest.raises(InvalidResetToken):
        await service.complete_reset(raw_token, "another-password-456")


async def test_complete_reset_with_an_expired_token_raises():
    user = _make_user("admin", "correct-horse-battery-staple")
    service, _, reset_tokens, _ = _service([user])
    raw_expired_token = "an-expired-raw-token"
    expired_token = PasswordResetToken(
        id=uuid.uuid4(),
        user_id=user.id,
        token_hash=hashlib.sha256(raw_expired_token.encode("utf-8")).hexdigest(),
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
        used_at=None,
        created_at=datetime.now(UTC) - timedelta(hours=2),
    )
    await reset_tokens.add(expired_token)

    with pytest.raises(InvalidResetToken):
        await service.complete_reset(raw_expired_token, "new-password-123")


async def test_complete_reset_with_an_unknown_token_raises():
    service, _, _, _ = _service([])

    with pytest.raises(InvalidResetToken):
        await service.complete_reset("never-issued", "new-password-123")


async def test_all_three_invalid_token_reasons_raise_the_same_exception_type():
    """Unknown, expired, and used tokens must be indistinguishable (AC #4)."""
    user = _make_user("admin", "correct-horse-battery-staple")
    service, _, reset_tokens, _ = _service([user])

    used_token = await service.request_reset("admin")
    await service.complete_reset(used_token, "new-password-123")

    raw_expired_token = "an-expired-raw-token"
    expired_token = PasswordResetToken(
        id=uuid.uuid4(),
        user_id=user.id,
        token_hash=hashlib.sha256(raw_expired_token.encode("utf-8")).hexdigest(),
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
        used_at=None,
        created_at=datetime.now(UTC) - timedelta(hours=2),
    )
    await reset_tokens.add(expired_token)

    exceptions = []
    for coro in (
        service.complete_reset("never-issued", "x"),
        service.complete_reset(used_token, "x"),
        service.complete_reset(raw_expired_token, "x"),
    ):
        try:
            await coro
        except InvalidResetToken as exc:
            exceptions.append(exc)

    assert len(exceptions) == 3
    assert all(type(e) is InvalidResetToken for e in exceptions)
    assert all(str(e) == str(exceptions[0]) for e in exceptions)
