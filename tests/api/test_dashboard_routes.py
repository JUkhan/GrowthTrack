import uuid
from datetime import UTC, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from adapters.persistence.brand_performance import SqlAlchemyBrandPerformanceRepository
from adapters.persistence.database import create_session_factory
from adapters.persistence.import_runs import SqlAlchemyImportRunRepository
from adapters.persistence.sales_data import SqlAlchemySalesDataRepository
from adapters.persistence.teams import SqlAlchemyTeamRepository
from domain.models import BrandPerformance, SalesData


async def _seed_dashboard_data() -> None:
    session_factory = create_session_factory()
    today = datetime.now(UTC).astimezone(ZoneInfo("Asia/Dhaka")).date()
    async with session_factory() as session:
        team_id = await SqlAlchemyTeamRepository(session).get_or_create_by_name("North")
        await SqlAlchemySalesDataRepository(session).upsert_many(
            [
                SalesData(
                    id=uuid.uuid4(),
                    date=today,
                    team_id=team_id,
                    sales_amount=Decimal("1000.00"),
                    achievement_pct=Decimal("95.50"),
                    growth_pct=Decimal("3.20"),
                )
            ]
        )
        run_id = await SqlAlchemyImportRunRepository(session).start(
            uuid.uuid4(), datetime.now(UTC)
        )
        await session.commit()

    async with session_factory() as session:
        await SqlAlchemyImportRunRepository(session).mark_succeeded(
            run_id, datetime.now(UTC), records_processed=1, records_rejected=0
        )
        await session.commit()


async def test_summary_without_cookie_returns_401(client):
    response = await client.get("/dashboard/summary")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_summary_with_valid_session_returns_200_with_expected_shape(client, seed_user):
    _, password = await seed_user(username="admin")
    await client.post("/auth/login", json={"username": "admin", "password": password})
    await _seed_dashboard_data()

    response = await client.get("/dashboard/summary")

    assert response.status_code == 200
    body = response.json()

    # Decimal fields must serialize as JSON strings, not numbers.
    assert isinstance(body["today_sales"], str)
    assert isinstance(body["ytd_sales"], str)
    assert isinstance(body["mtd_sales"], str)
    assert isinstance(body["achievement_pct"], str)
    assert isinstance(body["growth_pct"], str)
    assert isinstance(body["team_performance"][0]["achievement_pct"], str)

    assert Decimal(body["today_sales"]) == Decimal("1000.00")
    assert Decimal(body["ytd_sales"]) == Decimal("1000.00")
    assert Decimal(body["mtd_sales"]) == Decimal("1000.00")
    assert Decimal(body["achievement_pct"]) == Decimal("95.50")
    assert Decimal(body["growth_pct"]) == Decimal("3.20")
    assert body["team_performance"] == [
        {"team_name": "North", "achievement_pct": body["team_performance"][0]["achievement_pct"]}
    ]
    assert Decimal(body["team_performance"][0]["achievement_pct"]) == Decimal("95.50")
    assert body["is_stale"] is False
    assert body["data_as_of"] is not None


async def _seed_brand_performance() -> None:
    session_factory = create_session_factory()
    async with session_factory() as session:
        await SqlAlchemyBrandPerformanceRepository(session).upsert_many(
            [
                BrandPerformance(
                    id=uuid.uuid4(),
                    external_brand_id="B1",
                    brand_name="Acme",
                    sales=Decimal("5000.00"),
                    rank=1,
                    growth_pct=Decimal("2.50"),
                ),
                BrandPerformance(
                    id=uuid.uuid4(),
                    external_brand_id="B2",
                    brand_name="Beta Corp",
                    sales=Decimal("1000.00"),
                    rank=2,
                    growth_pct=Decimal("-3.75"),
                ),
            ]
        )
        await session.commit()


async def test_brand_performance_without_cookie_returns_401(client):
    response = await client.get("/dashboard/brand-performance")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_brand_performance_with_valid_session_returns_200_with_expected_shape(
    client, seed_user
):
    _, password = await seed_user(username="admin")
    await client.post("/auth/login", json={"username": "admin", "password": password})
    await _seed_brand_performance()

    response = await client.get("/dashboard/brand-performance")

    assert response.status_code == 200
    body = response.json()

    # Only 2 brands seeded, well under the default top_n=5 threshold, so
    # both land in top_brands (ascending rank) — low_performing/focus stay
    # empty. This mirrors _classify_brands' documented "fewer brands than
    # top_n" behavior; the three-bucket split itself is unit-tested in
    # tests/domain/test_brand_performance_service.py.
    assert body["top_brands"] == [
        {
            "external_brand_id": "B1",
            "brand_name": "Acme",
            "sales": "5000.00",
            "rank": 1,
            "growth_pct": "2.50",
        },
        {
            "external_brand_id": "B2",
            "brand_name": "Beta Corp",
            "sales": "1000.00",
            "rank": 2,
            "growth_pct": "-3.75",
        },
    ]
    assert body["low_performing_brands"] == []
    assert body["focus_brands"] == []
    # Decimal fields must serialize as JSON strings, not numbers.
    assert isinstance(body["top_brands"][0]["sales"], str)
    assert isinstance(body["top_brands"][0]["growth_pct"], str)
