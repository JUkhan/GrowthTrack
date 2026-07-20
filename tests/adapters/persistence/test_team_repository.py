import uuid

from adapters.persistence.database import create_session_factory
from adapters.persistence.teams import SqlAlchemyTeamRepository
from domain.models import TeamStatus


async def _get_or_create(name: str):
    session_factory = create_session_factory()
    async with session_factory() as session:
        team_id = await SqlAlchemyTeamRepository(session).get_or_create_by_name(name)
        await session.commit()
        return team_id


async def test_get_or_create_by_name_creates_a_new_team():
    team_id = await _get_or_create("North")

    assert team_id is not None


async def test_get_or_create_by_name_returns_the_same_id_for_an_existing_name():
    first_id = await _get_or_create("North")
    second_id = await _get_or_create("North")

    assert first_id == second_id


async def test_get_or_create_by_name_returns_different_ids_for_different_names():
    north_id = await _get_or_create("North")
    south_id = await _get_or_create("South")

    assert north_id != south_id


async def _list_all():
    session_factory = create_session_factory()
    async with session_factory() as session:
        return await SqlAlchemyTeamRepository(session).list_all()


async def test_list_all_returns_every_team_ordered_by_name():
    south_id = await _get_or_create("South")
    north_id = await _get_or_create("North")

    teams = await _list_all()

    assert teams == [(north_id, "North"), (south_id, "South")]


async def test_add_creates_a_team_with_active_status_and_version_one():
    team_id = uuid.uuid4()
    session_factory = create_session_factory()
    async with session_factory() as session:
        repo = SqlAlchemyTeamRepository(session)
        await repo.add(team_id, "East")
        await session.commit()

    async with session_factory() as session:
        team = await SqlAlchemyTeamRepository(session).get_by_id(team_id)

    assert team.name == "East"
    assert team.status == TeamStatus.ACTIVE
    assert team.version == 1


async def test_get_by_id_returns_none_for_an_unknown_id():
    session_factory = create_session_factory()
    async with session_factory() as session:
        team = await SqlAlchemyTeamRepository(session).get_by_id(uuid.uuid4())

    assert team is None


async def test_get_by_name_returns_the_matching_team():
    team_id = await _get_or_create("West")
    session_factory = create_session_factory()

    async with session_factory() as session:
        team = await SqlAlchemyTeamRepository(session).get_by_name("West")

    assert team.id == team_id


async def test_get_by_name_returns_none_when_no_team_has_that_name():
    session_factory = create_session_factory()
    async with session_factory() as session:
        team = await SqlAlchemyTeamRepository(session).get_by_name("Nonexistent")

    assert team is None


async def test_get_by_name_returns_none_for_a_deactivated_teams_name(seed_user):
    # Active-only (code review of Story 3.1): a soft-deleted Team's name is
    # reusable, matching ix_teams_name_active_uq.
    team_id = await _get_or_create("Deactivated Zone")
    session_factory = create_session_factory()

    async with session_factory() as session:
        await SqlAlchemyTeamRepository(session).deactivate(team_id)
        await session.commit()

    async with session_factory() as session:
        team = await SqlAlchemyTeamRepository(session).get_by_name("Deactivated Zone")

    assert team is None


async def test_get_or_create_by_name_creates_a_fresh_active_row_after_the_old_one_deactivates():
    # Regression check for ix_teams_name_active_uq: get_or_create_by_name's
    # ON CONFLICT DO NOTHING must target the partial index (index_where
    # status='active'), not a plain unique constraint on name, or this
    # ingestion path (Story 2.1, untouched by Story 3.1) breaks once a
    # Team's name has been reused after a soft-delete.
    first_id = await _get_or_create("Ingestion Zone")
    session_factory = create_session_factory()
    async with session_factory() as session:
        await SqlAlchemyTeamRepository(session).deactivate(first_id)
        await session.commit()

    second_id = await _get_or_create("Ingestion Zone")

    assert second_id != first_id
    async with session_factory() as session:
        second = await SqlAlchemyTeamRepository(session).get_by_id(second_id)
    assert second.status == TeamStatus.ACTIVE


async def test_list_all_full_returns_full_team_rows_including_status_and_version():
    await _get_or_create("North")

    session_factory = create_session_factory()
    async with session_factory() as session:
        teams = await SqlAlchemyTeamRepository(session).list_all_full()

    assert len(teams) == 1
    assert teams[0].name == "North"
    assert teams[0].status == TeamStatus.ACTIVE
    assert teams[0].version == 1


async def test_update_name_persists_the_new_name_and_increments_version():
    team_id = await _get_or_create("North")
    session_factory = create_session_factory()

    async with session_factory() as session:
        await SqlAlchemyTeamRepository(session).update_name(team_id, "Northern")
        await session.commit()

    async with session_factory() as session:
        updated = await SqlAlchemyTeamRepository(session).get_by_id(team_id)

    assert updated.name == "Northern"
    assert updated.version == 2


async def test_deactivate_flips_status_and_increments_version():
    team_id = await _get_or_create("North")
    session_factory = create_session_factory()

    async with session_factory() as session:
        await SqlAlchemyTeamRepository(session).deactivate(team_id)
        await session.commit()

    async with session_factory() as session:
        deactivated = await SqlAlchemyTeamRepository(session).get_by_id(team_id)

    assert deactivated.status == TeamStatus.INACTIVE
    assert deactivated.version == 2
