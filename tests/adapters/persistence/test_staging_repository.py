import uuid
from datetime import UTC, datetime

from adapters.persistence.database import create_session_factory
from adapters.persistence.import_runs import SqlAlchemyImportRunRepository
from adapters.persistence.staging import SqlAlchemyStagingRepository


async def _make_import_run() -> uuid.UUID:
    session_factory = create_session_factory()
    async with session_factory() as session:
        run_id = await SqlAlchemyImportRunRepository(session).start(uuid.uuid4(), datetime.now(UTC))
        await session.commit()
        return run_id


async def test_stage_then_fetch_staged_returns_rows_ordered_by_sequence():
    run_id = await _make_import_run()
    raw_rows = [
        {
            "date": "2026-07-18",
            "team": "North",
            "sales_amount": "1000",
            "achievement_pct": "1",
            "growth_pct": "1",
        },
        {
            "date": "2026-07-19",
            "team": "South",
            "sales_amount": "2000",
            "achievement_pct": "2",
            "growth_pct": "2",
        },
    ]
    session_factory = create_session_factory()
    async with session_factory() as session:
        await SqlAlchemyStagingRepository(session).stage(run_id, "sales_data", raw_rows)
        await session.commit()

    async with session_factory() as session:
        staged = await SqlAlchemyStagingRepository(session).fetch_staged(run_id, "sales_data")

    assert [sequence for sequence, _ in staged] == [0, 1]
    assert staged[0][1]["team"] == "North"
    assert staged[1][1]["team"] == "South"


async def test_mark_validated_matches_rows_by_sequence_not_list_position():
    run_id = await _make_import_run()
    raw_rows = [
        {
            "external_brand_id": "B1",
            "brand_name": "Acme",
            "sales": "5000",
            "rank": "1",
            "growth_pct": "1",
        },
        {
            "external_brand_id": "B2",
            "brand_name": "",
            "sales": "bad",
            "rank": "x",
            "growth_pct": "1",
        },
    ]
    session_factory = create_session_factory()
    async with session_factory() as session:
        await SqlAlchemyStagingRepository(session).stage(run_id, "brand_performance", raw_rows)
        await session.commit()

    async with session_factory() as session:
        await SqlAlchemyStagingRepository(session).mark_validated(
            run_id,
            "brand_performance",
            [(1, False, "sales is not a valid decimal"), (0, True, None)],
        )
        await session.commit()

    async with session_factory() as session:
        from sqlalchemy import select

        from adapters.persistence.staging import StagingBrandPerformanceModel

        stmt = (
            select(StagingBrandPerformanceModel)
            .where(StagingBrandPerformanceModel.import_run_id == run_id)
            .order_by(StagingBrandPerformanceModel.sequence)
        )
        result = await session.execute(stmt)
        rows = result.scalars().all()

    assert rows[0].is_valid is True
    assert rows[0].rejection_reason is None
    assert rows[1].is_valid is False
    assert rows[1].rejection_reason == "sales is not a valid decimal"


async def test_stage_with_an_empty_list_leaves_fetch_staged_empty():
    run_id = await _make_import_run()
    session_factory = create_session_factory()
    async with session_factory() as session:
        await SqlAlchemyStagingRepository(session).stage(run_id, "doctors", [])
        await session.commit()

    async with session_factory() as session:
        staged = await SqlAlchemyStagingRepository(session).fetch_staged(run_id, "doctors")

    assert staged == []
