import asyncio
from datetime import UTC, datetime, timedelta

from adapters.persistence.database import create_session_factory
from adapters.persistence.users import SqlAlchemyUserRepository
from domain.models import Role, UserStatus


async def _count_active_administrators() -> int:
    session_factory = create_session_factory()
    async with session_factory() as session:
        return await SqlAlchemyUserRepository(session).count_active_administrators()


async def test_count_active_administrators_is_zero_on_an_empty_table():
    assert await _count_active_administrators() == 0


async def test_count_active_administrators_is_one_after_seeding_one_active_administrator(
    seed_user,
):
    await seed_user(username="admin")

    assert await _count_active_administrators() == 1


async def test_count_active_administrators_is_two_after_seeding_a_second(seed_user):
    await seed_user(username="admin")
    await seed_user(username="admin2")

    assert await _count_active_administrators() == 2


async def test_count_active_administrators_excludes_non_administrators_and_inactive_administrators(
    seed_user,
):
    await seed_user(username="admin")
    await seed_user(username="sales", role=Role.SALES_USER)
    await seed_user(username="inactive-admin", status=UserStatus.INACTIVE)

    assert await _count_active_administrators() == 1


async def test_increment_failed_login_count_returns_the_running_total(seed_user):
    user, _ = await seed_user(username="admin")
    session_factory = create_session_factory()

    async with session_factory() as session:
        repo = SqlAlchemyUserRepository(session)
        first = await repo.increment_failed_login_count(user.id)
        second = await repo.increment_failed_login_count(user.id)
        third = await repo.increment_failed_login_count(user.id)
        await session.commit()

    assert (first, second, third) == (1, 2, 3)


async def test_increment_failed_login_count_is_atomic_under_concurrent_increments(seed_user):
    user, _ = await seed_user(username="admin")
    session_factory = create_session_factory()

    async def _increment() -> None:
        async with session_factory() as session:
            await SqlAlchemyUserRepository(session).increment_failed_login_count(user.id)
            await session.commit()

    await asyncio.gather(_increment(), _increment())

    async with session_factory() as session:
        final = await SqlAlchemyUserRepository(session).get_by_id(user.id)

    assert final.failed_login_count == 2


async def test_lock_until_and_clear_lockout_round_trip(seed_user):
    user, _ = await seed_user(username="admin")
    session_factory = create_session_factory()
    until = datetime.now(UTC) + timedelta(minutes=15)

    async with session_factory() as session:
        repo = SqlAlchemyUserRepository(session)
        await repo.increment_failed_login_count(user.id)
        await repo.lock_until(user.id, until)
        await session.commit()

    async with session_factory() as session:
        locked = await SqlAlchemyUserRepository(session).get_by_id(user.id)
    assert locked.locked_until is not None
    assert locked.failed_login_count == 1

    async with session_factory() as session:
        await SqlAlchemyUserRepository(session).clear_lockout(user.id)
        await session.commit()

    async with session_factory() as session:
        cleared = await SqlAlchemyUserRepository(session).get_by_id(user.id)
    assert cleared.locked_until is None
    assert cleared.failed_login_count == 0


async def test_update_password_persists_the_new_hash_and_increments_version(seed_user):
    user, _ = await seed_user(username="admin")
    session_factory = create_session_factory()

    async with session_factory() as session:
        await SqlAlchemyUserRepository(session).update_password(user.id, "a-new-hash")
        await session.commit()

    async with session_factory() as session:
        updated = await SqlAlchemyUserRepository(session).get_by_id(user.id)

    assert updated.hashed_password == "a-new-hash"
    assert updated.version == user.version + 1
