import uuid
from datetime import UTC, datetime

from sqlalchemy import text

from adapters.persistence.database import create_session_factory
from adapters.persistence.settings import SqlAlchemyReportScheduleRepository
from adapters.persistence.users import SqlAlchemyUserRepository
from domain.models import REPORT_SCHEDULE_ID, Role, User, UserStatus


async def _seed_user() -> User:
    session_factory = create_session_factory()
    user = User(
        id=uuid.uuid4(),
        username=None,
        hashed_password=None,
        role=Role.ADMINISTRATOR,
        status=UserStatus.ACTIVE,
        version=1,
        created_at=datetime.now(UTC),
        name="Karim",
    )
    async with session_factory() as session:
        await SqlAlchemyUserRepository(session).add(user)
        await session.commit()
    return user


async def test_get_returns_the_migration_seeded_singleton_row_with_its_default_values():
    session_factory = create_session_factory()
    async with session_factory() as session:
        schedule = await SqlAlchemyReportScheduleRepository(session).get()

    assert schedule.id == REPORT_SCHEDULE_ID
    assert schedule.send_hour_utc == 1
    assert schedule.send_minute_utc == 0
    assert schedule.updated_by_user_id is None


async def test_update_changes_every_field_and_a_follow_up_get_reflects_it():
    actor = await _seed_user()
    updated_at = datetime(2026, 7, 23, 12, 30, tzinfo=UTC)
    session_factory = create_session_factory()

    async with session_factory() as session:
        repo = SqlAlchemyReportScheduleRepository(session)
        updated = await repo.update(9, 45, actor.id, updated_at)
        await session.commit()

    assert updated.send_hour_utc == 9
    assert updated.send_minute_utc == 45
    assert updated.updated_by_user_id == actor.id
    assert updated.updated_at == updated_at

    async with session_factory() as session:
        found = await SqlAlchemyReportScheduleRepository(session).get()

    assert found.send_hour_utc == 9
    assert found.send_minute_utc == 45
    assert found.updated_by_user_id == actor.id


async def test_update_never_creates_a_second_row():
    actor = await _seed_user()
    session_factory = create_session_factory()

    async with session_factory() as session:
        await SqlAlchemyReportScheduleRepository(session).update(
            5, 15, actor.id, datetime.now(UTC)
        )
        await session.commit()

    async with session_factory() as session:
        count = await session.execute(text("SELECT COUNT(*) FROM report_schedules"))
        assert count.scalar_one() == 1
