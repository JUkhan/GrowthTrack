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
