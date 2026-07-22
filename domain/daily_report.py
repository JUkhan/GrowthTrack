"""Daily Report content assembly (Story 4.2, CAP-3).

Composes the three already-existing Epic 2 read services
(``DashboardMetricsService``, ``BrandPerformanceService``,
``DoctorVisitListService``) into the WhatsApp content-variable values for
the Daily Report template — zero changes to any of those services. The
company-wide figures (YTD/MTD/Achievement/Growth/team-performance/top
brand/focus brand) are identical for every Recipient in a run; only the
doctor-list section varies, by Territory.

``[ASSUMPTION — territory-to-Recipient mapping]``: neither ``entities.md``,
the PRD, nor the Architecture spine defines how a Recipient's Territory is
determined from a ``User`` row — ``Team`` has no ``territory`` field, and
``User`` has only ``team_id``. ``resolve_territories`` treats
``Team.name`` as the Territory (case-insensitive match against
``Doctor.territory``, mirroring ``domain/metrics.py``'s
``_rank_doctors_for_territory`` normalization) — this mirrors
``scripts/seed_demo_data.py``'s own seeding convention
(``Doctor.territory`` is seeded as exactly the Team name string), not an
invented rule. A future Source System integration where Team names and
territory strings diverge would silently break this mapping (empty
doctor sections, not an error).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime

from domain.metrics import BrandPerformanceService, DashboardMetricsService, DoctorVisitListService
from domain.models import User
from domain.report_formatting import format_cr_bdt, format_percent
from ports.teams import TeamRepository

# "no data" fallback (Dev Notes: never let an empty top_brands/
# focus_brands/team_performance/doctor-list produce an IndexError or a
# silent blank content-variable value).
_NO_DATA = "No data available"

# A Recipient with team_id is None (shouldn't occur for an active Sales
# User/Manager per scripts/seed_demo_data.py's roster shape, but not
# schema-enforced) gets this explicit fallback territory, not a silent
# blank — DoctorVisitListService.get_visit_list() naturally returns []
# for a territory with no matching Doctor rows, routing this recipient to
# the same "no data" doctor section as a genuinely unmatched territory.
UNASSIGNED_TERRITORY = "Unassigned"

# WhatsApp template parameter values cannot contain newlines (Dev Notes) —
# entries within a single content-variable value are joined with this
# separator instead of a literal line break.
_JOIN_SEPARATOR = "; "


@dataclass
class CompanyWideReportContent:
    ytd_sales: str
    mtd_sales: str
    achievement_pct: str
    growth_pct: str
    team_performance: str
    top_brand: str
    focus_brand: str


class DailyReportContentService:
    def __init__(
        self,
        dashboard_metrics: DashboardMetricsService,
        brand_performance: BrandPerformanceService,
        doctor_visit_list: DoctorVisitListService,
        teams: TeamRepository,
        top_doctors_n: int,
    ) -> None:
        self._dashboard_metrics = dashboard_metrics
        self._brand_performance = brand_performance
        self._doctor_visit_list = doctor_visit_list
        self._teams = teams
        self._top_doctors_n = top_doctors_n

    async def build_company_wide_content(
        self, today: date, now: datetime
    ) -> CompanyWideReportContent:
        """Calls the underlying Epic 2 services exactly once per scheduled
        run, never once per recipient — these figures are identical for
        every Recipient."""
        summary = await self._dashboard_metrics.get_summary(today, now)
        brands = await self._brand_performance.get_summary()

        team_performance = (
            _JOIN_SEPARATOR.join(
                f"{tp.team_name} : {format_percent(tp.achievement_pct)}"
                for tp in summary.team_performance
            )
            or _NO_DATA
        )
        top_brand = brands.top_brands[0].brand_name if brands.top_brands else _NO_DATA
        focus_brand = brands.focus_brands[0].brand_name if brands.focus_brands else _NO_DATA

        return CompanyWideReportContent(
            ytd_sales=format_cr_bdt(summary.ytd_sales),
            mtd_sales=format_cr_bdt(summary.mtd_sales),
            achievement_pct=(
                format_percent(summary.achievement_pct)
                if summary.achievement_pct is not None
                else _NO_DATA
            ),
            growth_pct=(
                format_percent(summary.growth_pct) if summary.growth_pct is not None else _NO_DATA
            ),
            team_performance=team_performance,
            top_brand=top_brand,
            focus_brand=focus_brand,
        )

    async def resolve_territories(self, recipients: list[User]) -> dict[uuid.UUID, str]:
        """Recipient User.id -> Territory string, for every recipient in
        ``recipients`` — see the module docstring's ``[ASSUMPTION]`` for
        the Team.name-as-Territory reasoning. Fetches the Team (id, name)
        map once, not once per recipient."""
        team_names_by_id = dict(await self._teams.list_all())
        return {
            recipient.id: (
                team_names_by_id.get(recipient.team_id, UNASSIGNED_TERRITORY)
                if recipient.team_id is not None
                else UNASSIGNED_TERRITORY
            )
            for recipient in recipients
        }

    async def build_doctor_section(self, territory: str) -> str:
        """Calls this once per **distinct** Territory represented in a
        run's resolved recipients, not once per recipient — callers should
        cache by territory string."""
        rows = await self._doctor_visit_list.get_visit_list(territory)
        if not rows:
            return _NO_DATA
        top = rows[: self._top_doctors_n]
        return _JOIN_SEPARATOR.join(row.doctor_name for row in top)
