import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from domain.daily_report import UNASSIGNED_TERRITORY, DailyReportContentService
from domain.metrics import (
    BrandEntry,
    BrandPerformanceSummary,
    DashboardSummary,
    DoctorVisitListService,
    TeamPerformance,
)
from domain.models import Doctor, Role, User, UserStatus
from domain.report_formatting import format_cr_bdt, format_percent


def _make_user(team_id: uuid.UUID | None) -> User:
    return User(
        id=uuid.uuid4(),
        username=None,
        hashed_password=None,
        role=Role.SALES_USER,
        status=UserStatus.ACTIVE,
        version=1,
        created_at=datetime.now(UTC),
        name="Rahim",
        mobile="+8801700000000",
        team_id=team_id,
    )


def _make_doctor(name: str, territory: str, priority: int) -> Doctor:
    return Doctor(
        id=uuid.uuid4(),
        external_doctor_id=f"DOC-{name}",
        name=name,
        territory=territory,
        priority=priority,
    )


class FakeDashboardMetricsService:
    def __init__(self, summary: DashboardSummary) -> None:
        self._summary = summary
        self.call_count = 0

    async def get_summary(self, today: date, now: datetime) -> DashboardSummary:
        self.call_count += 1
        return self._summary


class FakeBrandPerformanceService:
    def __init__(self, summary: BrandPerformanceSummary) -> None:
        self._summary = summary
        self.call_count = 0

    async def get_summary(self) -> BrandPerformanceSummary:
        self.call_count += 1
        return self._summary


class FakeDoctorRepository:
    def __init__(self, rows: list[Doctor]) -> None:
        self._rows = rows

    async def list_all(self) -> list[Doctor]:
        return self._rows


class FakeTeamRepository:
    def __init__(self, teams: list[tuple[uuid.UUID, str]]) -> None:
        self._teams = teams

    async def list_all(self) -> list[tuple[uuid.UUID, str]]:
        return self._teams


def _empty_dashboard_summary() -> DashboardSummary:
    return DashboardSummary(
        today_sales=Decimal("0"),
        ytd_sales=Decimal("0"),
        mtd_sales=Decimal("0"),
        achievement_pct=None,
        growth_pct=None,
        team_performance=[],
        data_as_of=None,
        is_stale=True,
    )


def _empty_brand_summary() -> BrandPerformanceSummary:
    return BrandPerformanceSummary(top_brands=[], low_performing_brands=[], focus_brands=[])


def _service(
    dashboard_summary: DashboardSummary | None = None,
    brand_summary: BrandPerformanceSummary | None = None,
    doctors: list[Doctor] | None = None,
    teams: list[tuple[uuid.UUID, str]] | None = None,
    top_doctors_n: int = 5,
) -> tuple[DailyReportContentService, FakeDashboardMetricsService, FakeBrandPerformanceService]:
    dashboard_metrics = FakeDashboardMetricsService(dashboard_summary or _empty_dashboard_summary())
    brand_performance = FakeBrandPerformanceService(brand_summary or _empty_brand_summary())
    doctor_visit_list = DoctorVisitListService(FakeDoctorRepository(doctors or []))
    team_repo = FakeTeamRepository(teams or [])
    service = DailyReportContentService(
        dashboard_metrics=dashboard_metrics,
        brand_performance=brand_performance,
        doctor_visit_list=doctor_visit_list,
        teams=team_repo,
        top_doctors_n=top_doctors_n,
    )
    return service, dashboard_metrics, brand_performance


# --- build_company_wide_content --------------------------------------------------


async def test_build_company_wide_content_calls_underlying_services_exactly_once():
    team_id = uuid.uuid4()
    summary = DashboardSummary(
        today_sales=Decimal("100"),
        ytd_sales=Decimal("1000000000"),
        mtd_sales=Decimal("120000000"),
        achievement_pct=Decimal("40"),
        growth_pct=Decimal("10"),
        team_performance=[
            TeamPerformance(team_id=team_id, team_name="Team A", achievement_pct=Decimal("45"))
        ],
        data_as_of=datetime.now(UTC),
        is_stale=False,
    )
    brands = BrandPerformanceSummary(
        top_brands=[
            BrandEntry(
                external_brand_id="B1",
                brand_name="ABC Pharma",
                sales=Decimal("100"),
                rank=1,
                growth_pct=Decimal("5"),
            )
        ],
        low_performing_brands=[],
        focus_brands=[
            BrandEntry(
                external_brand_id="B2",
                brand_name="XYZ Pharma",
                sales=Decimal("50"),
                rank=10,
                growth_pct=Decimal("-5"),
            )
        ],
    )
    service, dashboard_metrics, brand_performance = _service(summary, brands)

    content = await service.build_company_wide_content(date(2026, 7, 22), datetime.now(UTC))

    assert dashboard_metrics.call_count == 1
    assert brand_performance.call_count == 1
    assert content.ytd_sales == "100.0 Cr BDT"
    assert content.mtd_sales == "12.0 Cr BDT"
    assert content.achievement_pct == "40%"
    assert content.growth_pct == "10%"
    assert content.team_performance == "Team A : 45%"
    assert content.top_brand == "ABC Pharma"
    assert content.focus_brand == "XYZ Pharma"


async def test_build_company_wide_content_handles_empty_brand_and_team_lists_without_indexerror():
    service, *_ = _service()

    content = await service.build_company_wide_content(date(2026, 7, 22), datetime.now(UTC))

    assert content.top_brand == "No data available"
    assert content.focus_brand == "No data available"
    assert content.team_performance == "No data available"
    assert content.achievement_pct == "No data available"
    assert content.growth_pct == "No data available"


# --- resolve_territories -----------------------------------------------------------


async def test_resolve_territories_maps_team_id_to_team_name():
    team_id = uuid.uuid4()
    recipient = _make_user(team_id=team_id)
    service, *_ = _service(teams=[(team_id, "North Region")])

    territories = await service.resolve_territories([recipient])

    assert territories[recipient.id] == "North Region"


async def test_resolve_territories_falls_back_to_unassigned_for_a_recipient_with_no_team():
    recipient = _make_user(team_id=None)
    service, *_ = _service()

    territories = await service.resolve_territories([recipient])

    assert territories[recipient.id] == UNASSIGNED_TERRITORY


# --- build_doctor_section -----------------------------------------------------------


async def test_build_doctor_section_matches_territory_case_insensitively_and_truncates():
    doctors = [
        _make_doctor("Dr. Rahman", "North Region", priority=1),
        _make_doctor("Dr. Hasan", "North Region", priority=2),
        _make_doctor("Dr. Ahmed", "North Region", priority=3),
        _make_doctor("Dr. Other", "South Region", priority=1),
    ]
    service, *_ = _service(doctors=doctors, top_doctors_n=2)

    # Different casing/whitespace than the stored Doctor.territory.
    section = await service.build_doctor_section("  north region  ")

    assert section == "Dr. Rahman; Dr. Hasan"


async def test_build_doctor_section_returns_no_data_fallback_for_an_unmatched_territory():
    service, *_ = _service(doctors=[_make_doctor("Dr. Rahman", "North Region", priority=1)])

    section = await service.build_doctor_section("Unmapped Territory")

    assert section == "No data available"


# --- report_formatting.py ----------------------------------------------------------


def test_format_cr_bdt_matches_known_values_from_format_ts_formula():
    # (value / 1e7), one decimal, " Cr BDT" suffix (not bare " Cr").
    assert format_cr_bdt(Decimal("1000000000")) == "100.0 Cr BDT"
    assert format_cr_bdt(Decimal("120000000")) == "12.0 Cr BDT"
    assert format_cr_bdt(Decimal("0")) == "0.0 Cr BDT"
    assert format_cr_bdt(Decimal("-50000000")) == "-5.0 Cr BDT"


def test_format_percent_matches_known_values_from_format_ts_formula():
    assert format_percent(Decimal("40")) == "40%"
    assert format_percent(Decimal("40.4")) == "40%"
    assert format_percent(Decimal("40.6")) == "41%"
    assert format_percent(Decimal("-5")) == "-5%"


def test_format_percent_matches_javascripts_math_round_on_exact_tie_values():
    # Regression test (code review): Python's round() defaults to
    # round-half-to-even ("banker's rounding") and would give 40 here, but
    # web/src/utils/format.ts's Math.round rounds an exact tie toward
    # positive infinity (41 for +40.5, -40 for -40.5) — these two must
    # never disagree per this module's own stated purpose.
    assert format_percent(Decimal("40.5")) == "41%"
    assert format_percent(Decimal("-40.5")) == "-40%"
    assert format_percent(Decimal("0.5")) == "1%"


def test_format_cr_bdt_matches_javascripts_tofixed_on_exact_tie_values():
    # Regression test (code review): round(Decimal("9.25"), 1) == 9.2
    # (banker's rounding), but format.ts's (9.25).toFixed(1) == "9.3".
    assert format_cr_bdt(Decimal("92500000")) == "9.3 Cr BDT"
    assert format_cr_bdt(Decimal("12500000")) == "1.3 Cr BDT"
