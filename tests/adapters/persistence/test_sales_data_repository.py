import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select

from adapters.persistence.database import create_session_factory
from adapters.persistence.sales_data import SalesDataModel, SqlAlchemySalesDataRepository
from adapters.persistence.teams import SqlAlchemyTeamRepository
from domain.models import SalesData


async def _make_team(name: str = "North") -> uuid.UUID:
    session_factory = create_session_factory()
    async with session_factory() as session:
        team_id = await SqlAlchemyTeamRepository(session).get_or_create_by_name(name)
        await session.commit()
        return team_id


async def _upsert(rows: list[SalesData]) -> None:
    session_factory = create_session_factory()
    async with session_factory() as session:
        await SqlAlchemySalesDataRepository(session).upsert_many(rows)
        await session.commit()


async def _get_by_date_and_team(day: date, team_id: uuid.UUID) -> SalesDataModel | None:
    session_factory = create_session_factory()
    async with session_factory() as session:
        stmt = select(SalesDataModel).where(
            SalesDataModel.date == day, SalesDataModel.team_id == team_id
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()


async def test_upsert_many_inserts_a_new_row():
    team_id = await _make_team()
    row = SalesData(
        id=uuid.uuid4(),
        date=date(2026, 7, 18),
        team_id=team_id,
        sales_amount=Decimal("1000"),
        achievement_pct=Decimal("95.5"),
        growth_pct=Decimal("3.2"),
    )

    await _upsert([row])

    found = await _get_by_date_and_team(date(2026, 7, 18), team_id)
    assert found is not None
    assert found.sales_amount == Decimal("1000")


async def test_upsert_many_updates_an_existing_row_on_conflict_not_ignoring_it():
    team_id = await _make_team()
    first = SalesData(
        id=uuid.uuid4(),
        date=date(2026, 7, 18),
        team_id=team_id,
        sales_amount=Decimal("1000"),
        achievement_pct=Decimal("95.5"),
        growth_pct=Decimal("3.2"),
    )
    await _upsert([first])

    corrected = SalesData(
        id=uuid.uuid4(),
        date=date(2026, 7, 18),
        team_id=team_id,
        sales_amount=Decimal("2000"),
        achievement_pct=Decimal("99.0"),
        growth_pct=Decimal("5.0"),
    )
    await _upsert([corrected])

    found = await _get_by_date_and_team(date(2026, 7, 18), team_id)
    assert found is not None
    assert found.sales_amount == Decimal("2000")
    assert found.achievement_pct == Decimal("99.0")
    assert found.growth_pct == Decimal("5.0")


async def test_upsert_many_with_an_empty_list_does_nothing():
    await _upsert([])


async def test_upsert_many_dedupes_a_batch_with_two_rows_sharing_the_same_conflict_key():
    """A single multi-row ON CONFLICT DO UPDATE statement raises if two input
    rows share a conflict key — this must not crash the whole run."""
    team_id = await _make_team()
    stale = SalesData(
        id=uuid.uuid4(),
        date=date(2026, 7, 18),
        team_id=team_id,
        sales_amount=Decimal("1000"),
        achievement_pct=Decimal("50.0"),
        growth_pct=Decimal("1.0"),
    )
    corrected = SalesData(
        id=uuid.uuid4(),
        date=date(2026, 7, 18),
        team_id=team_id,
        sales_amount=Decimal("2000"),
        achievement_pct=Decimal("99.0"),
        growth_pct=Decimal("5.0"),
    )

    await _upsert([stale, corrected])

    found = await _get_by_date_and_team(date(2026, 7, 18), team_id)
    assert found is not None
    assert found.sales_amount == Decimal("2000")


async def _sum_amount_in_range(start_date: date, end_date: date) -> Decimal:
    session_factory = create_session_factory()
    async with session_factory() as session:
        return await SqlAlchemySalesDataRepository(session).sum_amount_in_range(
            start_date, end_date
        )


async def _latest_per_team() -> list:
    session_factory = create_session_factory()
    async with session_factory() as session:
        return await SqlAlchemySalesDataRepository(session).latest_per_team()


async def test_sum_amount_in_range_includes_inclusive_boundaries():
    team_id = await _make_team()
    await _upsert(
        [
            SalesData(
                id=uuid.uuid4(),
                date=date(2026, 7, 1),
                team_id=team_id,
                sales_amount=Decimal("100"),
                achievement_pct=Decimal("50"),
                growth_pct=Decimal("1"),
            ),
            SalesData(
                id=uuid.uuid4(),
                date=date(2026, 7, 31),
                team_id=team_id,
                sales_amount=Decimal("200"),
                achievement_pct=Decimal("50"),
                growth_pct=Decimal("1"),
            ),
        ]
    )

    total = await _sum_amount_in_range(date(2026, 7, 1), date(2026, 7, 31))

    assert total == Decimal("300")


async def test_sum_amount_in_range_excludes_a_date_just_outside_the_range():
    team_id = await _make_team()
    await _upsert(
        [
            SalesData(
                id=uuid.uuid4(),
                date=date(2026, 8, 1),
                team_id=team_id,
                sales_amount=Decimal("100"),
                achievement_pct=Decimal("50"),
                growth_pct=Decimal("1"),
            )
        ]
    )

    total = await _sum_amount_in_range(date(2026, 7, 1), date(2026, 7, 31))

    assert total == Decimal("0")


async def test_sum_amount_in_range_returns_zero_not_none_for_an_empty_range():
    total = await _sum_amount_in_range(date(2026, 7, 1), date(2026, 7, 31))

    assert total == Decimal("0")


async def test_latest_per_team_returns_only_the_most_recent_dated_row_per_team():
    team_id = await _make_team()
    await _upsert(
        [
            SalesData(
                id=uuid.uuid4(),
                date=date(2026, 7, 17),
                team_id=team_id,
                sales_amount=Decimal("100"),
                achievement_pct=Decimal("40"),
                growth_pct=Decimal("1"),
            ),
            SalesData(
                id=uuid.uuid4(),
                date=date(2026, 7, 18),
                team_id=team_id,
                sales_amount=Decimal("200"),
                achievement_pct=Decimal("50"),
                growth_pct=Decimal("2"),
            ),
            SalesData(
                id=uuid.uuid4(),
                date=date(2026, 7, 19),
                team_id=team_id,
                sales_amount=Decimal("300"),
                achievement_pct=Decimal("60"),
                growth_pct=Decimal("3"),
            ),
        ]
    )

    latest = await _latest_per_team()

    assert len(latest) == 1
    assert latest[0].team_id == team_id
    assert latest[0].date == date(2026, 7, 19)
    assert latest[0].sales_amount == Decimal("300")


async def test_latest_per_team_omits_teams_with_zero_sales_data_rows():
    await _make_team("North")
    await _make_team("South")

    latest = await _latest_per_team()

    assert latest == []
