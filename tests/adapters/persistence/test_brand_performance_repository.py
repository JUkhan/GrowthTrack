import uuid
from decimal import Decimal

from sqlalchemy import select

from adapters.persistence.brand_performance import (
    BrandPerformanceModel,
    SqlAlchemyBrandPerformanceRepository,
)
from adapters.persistence.database import create_session_factory
from domain.models import BrandPerformance


async def _upsert(rows: list[BrandPerformance]) -> None:
    session_factory = create_session_factory()
    async with session_factory() as session:
        await SqlAlchemyBrandPerformanceRepository(session).upsert_many(rows)
        await session.commit()


async def _get_by_external_id(external_brand_id: str) -> BrandPerformanceModel | None:
    session_factory = create_session_factory()
    async with session_factory() as session:
        stmt = select(BrandPerformanceModel).where(
            BrandPerformanceModel.external_brand_id == external_brand_id
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()


async def test_upsert_many_inserts_a_new_row():
    row = BrandPerformance(
        id=uuid.uuid4(),
        external_brand_id="B1",
        brand_name="Acme",
        sales=Decimal("5000"),
        rank=1,
        growth_pct=Decimal("2.0"),
    )

    await _upsert([row])

    found = await _get_by_external_id("B1")
    assert found is not None
    assert found.brand_name == "Acme"


async def test_upsert_many_updates_an_existing_snapshot_row_on_conflict_not_ignoring_it():
    await _upsert(
        [
            BrandPerformance(
                id=uuid.uuid4(),
                external_brand_id="B1",
                brand_name="Acme",
                sales=Decimal("5000"),
                rank=1,
                growth_pct=Decimal("2.0"),
            )
        ]
    )

    await _upsert(
        [
            BrandPerformance(
                id=uuid.uuid4(),
                external_brand_id="B1",
                brand_name="Acme Corp",
                sales=Decimal("6000"),
                rank=2,
                growth_pct=Decimal("-1.5"),
            )
        ]
    )

    found = await _get_by_external_id("B1")
    assert found is not None
    assert found.brand_name == "Acme Corp"
    assert found.sales == Decimal("6000")
    assert found.rank == 2
    assert found.growth_pct == Decimal("-1.5")


async def test_upsert_many_dedupes_a_batch_with_two_rows_sharing_the_same_conflict_key():
    """A single multi-row ON CONFLICT DO UPDATE statement raises if two input
    rows share a conflict key — this must not crash the whole run."""
    stale = BrandPerformance(
        id=uuid.uuid4(),
        external_brand_id="B1",
        brand_name="Acme",
        sales=Decimal("5000"),
        rank=1,
        growth_pct=Decimal("2.0"),
    )
    corrected = BrandPerformance(
        id=uuid.uuid4(),
        external_brand_id="B1",
        brand_name="Acme Corp",
        sales=Decimal("6000"),
        rank=2,
        growth_pct=Decimal("-1.5"),
    )

    await _upsert([stale, corrected])

    found = await _get_by_external_id("B1")
    assert found is not None
    assert found.brand_name == "Acme Corp"
