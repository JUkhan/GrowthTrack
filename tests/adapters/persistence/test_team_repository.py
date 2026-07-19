from adapters.persistence.database import create_session_factory
from adapters.persistence.teams import SqlAlchemyTeamRepository


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
