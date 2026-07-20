import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from adapters.persistence.consent import SqlAlchemyOptInConsentRepository
from adapters.persistence.database import create_session_factory
from adapters.persistence.users import SqlAlchemyUserRepository
from domain.models import Role, User, UserStatus


async def _seed_user(mobile: str) -> User:
    session_factory = create_session_factory()
    user = User(
        id=uuid.uuid4(),
        username=None,
        hashed_password=None,
        role=Role.SALES_USER,
        status=UserStatus.ACTIVE,
        version=1,
        created_at=datetime.now(UTC),
        name="Karim",
        mobile=mobile,
    )
    async with session_factory() as session:
        await SqlAlchemyUserRepository(session).add(user)
        await session.commit()
    return user


async def test_grant_creates_a_row_with_no_revoked_at():
    user = await _seed_user("+8801700000801")
    session_factory = create_session_factory()

    async with session_factory() as session:
        repo = SqlAlchemyOptInConsentRepository(session)
        consent = await repo.grant(user.id, user.mobile)
        await session.commit()

    assert consent.user_id == user.id
    assert consent.mobile == "+8801700000801"
    assert consent.revoked_at is None


async def test_get_active_returns_the_active_consent():
    user = await _seed_user("+8801700000802")
    session_factory = create_session_factory()

    async with session_factory() as session:
        repo = SqlAlchemyOptInConsentRepository(session)
        await repo.grant(user.id, user.mobile)
        await session.commit()

    async with session_factory() as session:
        found = await SqlAlchemyOptInConsentRepository(session).get_active(user.id)

    assert found is not None
    assert found.user_id == user.id


async def test_get_active_returns_none_when_the_only_row_is_revoked():
    user = await _seed_user("+8801700000803")
    session_factory = create_session_factory()

    async with session_factory() as session:
        repo = SqlAlchemyOptInConsentRepository(session)
        await repo.grant(user.id, user.mobile)
        await session.commit()

    async with session_factory() as session:
        repo = SqlAlchemyOptInConsentRepository(session)
        await repo.revoke_active(user.id)
        await session.commit()

    async with session_factory() as session:
        found = await SqlAlchemyOptInConsentRepository(session).get_active(user.id)

    assert found is None


async def test_get_active_returns_none_when_no_row_exists():
    session_factory = create_session_factory()
    async with session_factory() as session:
        found = await SqlAlchemyOptInConsentRepository(session).get_active(uuid.uuid4())

    assert found is None


async def test_get_active_by_user_ids_groups_correctly_across_mixed_states():
    active_user = await _seed_user("+8801700000804")
    revoked_user = await _seed_user("+8801700000805")
    untouched_user = await _seed_user("+8801700000806")
    session_factory = create_session_factory()

    async with session_factory() as session:
        repo = SqlAlchemyOptInConsentRepository(session)
        await repo.grant(active_user.id, active_user.mobile)
        await repo.grant(revoked_user.id, revoked_user.mobile)
        await session.commit()

    async with session_factory() as session:
        repo = SqlAlchemyOptInConsentRepository(session)
        await repo.revoke_active(revoked_user.id)
        await session.commit()

    async with session_factory() as session:
        by_user = await SqlAlchemyOptInConsentRepository(session).get_active_by_user_ids(
            [active_user.id, revoked_user.id, untouched_user.id]
        )

    assert set(by_user.keys()) == {active_user.id}
    assert by_user[active_user.id].user_id == active_user.id


async def test_get_active_by_user_ids_with_empty_input_returns_empty_dict_without_querying():
    session_factory = create_session_factory()
    async with session_factory() as session:
        by_user = await SqlAlchemyOptInConsentRepository(session).get_active_by_user_ids([])

    assert by_user == {}


async def test_revoke_active_sets_revoked_at_and_returns_true():
    user = await _seed_user("+8801700000807")
    session_factory = create_session_factory()

    async with session_factory() as session:
        repo = SqlAlchemyOptInConsentRepository(session)
        await repo.grant(user.id, user.mobile)
        await session.commit()

    async with session_factory() as session:
        revoked = await SqlAlchemyOptInConsentRepository(session).revoke_active(user.id)
        await session.commit()

    assert revoked is True
    async with session_factory() as session:
        found = await SqlAlchemyOptInConsentRepository(session).get_active(user.id)
    assert found is None


async def test_revoke_active_is_a_no_op_and_returns_false_when_none_exists():
    user = await _seed_user("+8801700000808")
    session_factory = create_session_factory()

    async with session_factory() as session:
        revoked = await SqlAlchemyOptInConsentRepository(session).revoke_active(user.id)

    assert revoked is False


async def test_revoke_active_called_twice_is_safe_and_second_call_returns_false():
    user = await _seed_user("+8801700000809")
    session_factory = create_session_factory()

    async with session_factory() as session:
        repo = SqlAlchemyOptInConsentRepository(session)
        await repo.grant(user.id, user.mobile)
        await session.commit()

    async with session_factory() as session:
        first = await SqlAlchemyOptInConsentRepository(session).revoke_active(user.id)
        await session.commit()

    async with session_factory() as session:
        second = await SqlAlchemyOptInConsentRepository(session).revoke_active(user.id)
        await session.commit()

    assert first is True
    assert second is False


async def test_the_partial_unique_index_rejects_a_second_concurrent_active_row():
    user = await _seed_user("+8801700000810")
    session_factory = create_session_factory()

    async with session_factory() as session:
        repo = SqlAlchemyOptInConsentRepository(session)
        await repo.grant(user.id, user.mobile)
        await session.commit()

    with pytest.raises(IntegrityError):
        async with session_factory() as session:
            await session.execute(
                text(
                    "INSERT INTO opt_in_consents (id, user_id, mobile, granted_at, revoked_at) "
                    "VALUES (:id, :user_id, :mobile, now(), NULL)"
                ),
                {"id": uuid.uuid4(), "user_id": user.id, "mobile": user.mobile},
            )
            await session.commit()
