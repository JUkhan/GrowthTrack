import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from domain.metrics import DashboardMetricsService, _aggregate_company_wide
from domain.models import SalesData
from ports.import_runs import ImportRunRepository
from ports.sales_data import SalesDataRepository
from ports.teams import TeamRepository


def _row(
    team_id: uuid.UUID,
    day: date,
    amount: str,
    achievement: Decimal = Decimal("50"),
    growth: Decimal = Decimal("5"),
) -> SalesData:
    return SalesData(
        id=uuid.uuid4(),
        date=day,
        team_id=team_id,
        sales_amount=Decimal(amount),
        achievement_pct=achievement,
        growth_pct=growth,
    )


class FakeSalesDataRepository(SalesDataRepository):
    def __init__(
        self, rows: list[SalesData] | None = None, latest: list[SalesData] | None = None
    ) -> None:
        self._rows = rows or []
        self._latest = latest if latest is not None else []

    async def upsert_many(self, rows: list) -> None:
        raise NotImplementedError

    async def sum_amount_in_range(self, start_date: date, end_date: date) -> Decimal:
        return sum(
            (row.sales_amount for row in self._rows if start_date <= row.date <= end_date),
            Decimal(0),
        )

    async def latest_per_team(self) -> list:
        return self._latest


class FakeTeamRepository(TeamRepository):
    def __init__(self, teams: list[tuple[uuid.UUID, str]] | None = None) -> None:
        self._teams = teams or []

    async def get_or_create_by_name(self, name: str) -> uuid.UUID:
        raise NotImplementedError

    async def list_all(self) -> list[tuple[uuid.UUID, str]]:
        return self._teams

    async def add(self, team_id: uuid.UUID, name: str) -> None:
        raise NotImplementedError

    async def get_by_id(self, team_id: uuid.UUID) -> None:
        raise NotImplementedError

    async def get_by_name(self, name: str) -> None:
        raise NotImplementedError

    async def list_all_full(self) -> list:
        raise NotImplementedError

    async def update_name(self, team_id: uuid.UUID, name: str, expected_version: int) -> bool:
        raise NotImplementedError

    async def deactivate(self, team_id: uuid.UUID) -> None:
        raise NotImplementedError


class FakeImportRunRepository(ImportRunRepository):
    def __init__(self, last_successful: datetime | None = None) -> None:
        self._last_successful = last_successful

    async def try_acquire_lock(self) -> bool:
        raise NotImplementedError

    async def start(self, correlation_id: uuid.UUID, started_at: datetime) -> uuid.UUID:
        raise NotImplementedError

    async def mark_succeeded(self, *args, **kwargs) -> None:
        raise NotImplementedError

    async def mark_failed(self, *args, **kwargs) -> None:
        raise NotImplementedError

    async def get_last_successful_completed_at(self) -> datetime | None:
        return self._last_successful


def _service(
    *,
    sales_data: FakeSalesDataRepository | None = None,
    teams: FakeTeamRepository | None = None,
    import_runs: FakeImportRunRepository | None = None,
    stale_after: timedelta = timedelta(hours=24),
) -> DashboardMetricsService:
    return DashboardMetricsService(
        sales_data=sales_data or FakeSalesDataRepository(),
        teams=teams or FakeTeamRepository(),
        import_runs=import_runs or FakeImportRunRepository(),
        stale_after=stale_after,
    )


async def test_today_mtd_ytd_sums_at_mid_month():
    team_id = uuid.uuid4()
    rows = [
        _row(team_id, date(2026, 7, 19), "100"),  # today
        _row(team_id, date(2026, 7, 1), "50"),  # earlier this month
        _row(team_id, date(2026, 1, 1), "10"),  # earlier this year
        _row(team_id, date(2025, 12, 31), "999"),  # last year — excluded from YTD
    ]
    service = _service(sales_data=FakeSalesDataRepository(rows=rows))

    summary = await service.get_summary(
        today=date(2026, 7, 19), now=datetime(2026, 7, 19, 12, tzinfo=UTC)
    )

    assert summary.today_sales == Decimal("100")
    assert summary.mtd_sales == Decimal("150")
    assert summary.ytd_sales == Decimal("160")


async def test_today_mtd_ytd_sums_are_all_equal_at_the_year_boundary():
    team_id = uuid.uuid4()
    rows = [_row(team_id, date(2026, 1, 1), "100"), _row(team_id, date(2025, 12, 31), "999")]
    service = _service(sales_data=FakeSalesDataRepository(rows=rows))

    summary = await service.get_summary(
        today=date(2026, 1, 1), now=datetime(2026, 1, 1, 12, tzinfo=UTC)
    )

    assert summary.today_sales == summary.mtd_sales == summary.ytd_sales == Decimal("100")


async def test_team_performance_maps_names_and_sorts_by_name():
    team_a = uuid.uuid4()
    team_b = uuid.uuid4()
    latest = [
        _row(team_b, date(2026, 7, 19), "100", achievement=Decimal("80")),
        _row(team_a, date(2026, 7, 19), "200", achievement=Decimal("60")),
    ]
    service = _service(
        sales_data=FakeSalesDataRepository(latest=latest),
        teams=FakeTeamRepository(teams=[(team_a, "Alpha"), (team_b, "Bravo")]),
    )

    summary = await service.get_summary(
        today=date(2026, 7, 19), now=datetime(2026, 7, 19, tzinfo=UTC)
    )

    assert [tp.team_name for tp in summary.team_performance] == ["Alpha", "Bravo"]
    assert summary.team_performance[0].achievement_pct == Decimal("60")


async def test_team_with_no_sales_data_rows_is_absent_not_fabricated():
    team_with_sales = uuid.uuid4()
    team_without_sales = uuid.uuid4()
    latest = [_row(team_with_sales, date(2026, 7, 19), "100")]
    service = _service(
        sales_data=FakeSalesDataRepository(latest=latest),
        teams=FakeTeamRepository(
            teams=[(team_with_sales, "Alpha"), (team_without_sales, "Bravo")]
        ),
    )

    summary = await service.get_summary(
        today=date(2026, 7, 19), now=datetime(2026, 7, 19, tzinfo=UTC)
    )

    assert [tp.team_name for tp in summary.team_performance] == ["Alpha"]


def test_aggregate_company_wide_weighted_average():
    rows = [
        _row(
            uuid.uuid4(), date(2026, 7, 19), "100", achievement=Decimal("40"), growth=Decimal("10")
        ),
        _row(
            uuid.uuid4(), date(2026, 7, 19), "300", achievement=Decimal("80"), growth=Decimal("20")
        ),
    ]

    achievement, growth = _aggregate_company_wide(rows)

    assert achievement == Decimal("70")
    assert growth == Decimal("17.5")


def test_aggregate_company_wide_empty_list_returns_none_none():
    assert _aggregate_company_wide([]) == (None, None)


def test_aggregate_company_wide_all_zero_sales_amount_returns_none_none_without_zero_division():
    rows = [
        _row(uuid.uuid4(), date(2026, 7, 19), "0", achievement=Decimal("50"), growth=Decimal("5"))
    ]

    assert _aggregate_company_wide(rows) == (None, None)


async def test_is_stale_true_when_older_than_threshold():
    now = datetime(2026, 7, 19, 12, tzinfo=UTC)
    data_as_of = now - timedelta(hours=25)
    service = _service(import_runs=FakeImportRunRepository(last_successful=data_as_of))

    summary = await service.get_summary(today=date(2026, 7, 19), now=now)

    assert summary.is_stale is True


async def test_is_stale_false_exactly_at_the_threshold():
    now = datetime(2026, 7, 19, 12, tzinfo=UTC)
    data_as_of = now - timedelta(hours=24)
    service = _service(import_runs=FakeImportRunRepository(last_successful=data_as_of))

    summary = await service.get_summary(today=date(2026, 7, 19), now=now)

    assert summary.is_stale is False


async def test_is_stale_false_just_under_the_threshold():
    now = datetime(2026, 7, 19, 12, tzinfo=UTC)
    data_as_of = now - timedelta(hours=23, minutes=59)
    service = _service(import_runs=FakeImportRunRepository(last_successful=data_as_of))

    summary = await service.get_summary(today=date(2026, 7, 19), now=now)

    assert summary.is_stale is False


async def test_is_stale_true_when_no_import_has_ever_succeeded():
    now = datetime(2026, 7, 19, 12, tzinfo=UTC)
    service = _service(import_runs=FakeImportRunRepository(last_successful=None))

    summary = await service.get_summary(today=date(2026, 7, 19), now=now)

    assert summary.is_stale is True
    assert summary.data_as_of is None


async def test_fresh_db_with_zero_sales_data_anywhere_returns_zeroes_and_none_without_raising():
    service = _service()

    summary = await service.get_summary(
        today=date(2026, 7, 19), now=datetime(2026, 7, 19, tzinfo=UTC)
    )

    assert summary.today_sales == Decimal(0)
    assert summary.mtd_sales == Decimal(0)
    assert summary.ytd_sales == Decimal(0)
    assert summary.team_performance == []
    assert summary.achievement_pct is None
    assert summary.growth_pct is None
