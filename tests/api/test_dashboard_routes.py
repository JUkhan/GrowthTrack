import uuid
from datetime import UTC, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from adapters.persistence.database import create_session_factory
from adapters.persistence.import_runs import SqlAlchemyImportRunRepository
from adapters.persistence.sales_data import SqlAlchemySalesDataRepository
from adapters.persistence.teams import SqlAlchemyTeamRepository
from domain.models import SalesData


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
