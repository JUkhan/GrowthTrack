"""Dashboard summary metrics (Story 2.2, CAP-2).

Read-only aggregation over Story 2.1's ingested ``SalesData``/``Team``/
``ImportRun`` tables — no mutation, so this service is a straightforward
port-composition, same shape as the other ``domain`` services (AD-1).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from domain.models import SalesData
from ports.import_runs import ImportRunRepository
from ports.sales_data import SalesDataRepository
from ports.teams import TeamRepository


@dataclass
class TeamPerformance:
    team_id: uuid.UUID
    team_name: str
    achievement_pct: Decimal


@dataclass
class DashboardSummary:
    today_sales: Decimal
    ytd_sales: Decimal
    mtd_sales: Decimal
    achievement_pct: Decimal | None  # None only when there is no sales data at all yet
    growth_pct: Decimal | None
    team_performance: list[TeamPerformance]
    data_as_of: datetime | None  # UTC — Asia/Dhaka conversion happens at the presentation edge
    is_stale: bool


def _aggregate_company_wide(rows: list[SalesData]) -> tuple[Decimal | None, Decimal | None]:
    """[ASSUMPTION — CONFIRM, epics.md Story 2.2 AC #6 / PRD §13 OQ#3]
    Sales-amount-weighted average of each team's latest achievement_pct/
    growth_pct. These per-team/per-row values are already ingested
    as-given from the Source System per Story 2.1's Dev Notes — but that
    was Story 2.1's own unconfirmed `[ASSUMPTION — CONFIRM]`, never
    ratified by a finance/business stakeholder, and `ARCHITECTURE-SPINE.md`'s
    Deferred section still lists "exact Achievement %/Growth % formulas"
    as entirely open. Do not treat Story 2.1's shipped behavior as
    authoritative confirmation — it is an existing, load-bearing
    implementation this story builds on (rewriting Story 2.1 is out of
    this story's scope), but it still needs sign-off. On top of that,
    this function adds a second, genuinely new open question: how
    per-team figures roll up into ONE company-wide headline number.
    sample-whatsapp-report.md proves this isn't a naive average
    (MTD Achievement 40% != mean of Team A/B/C's 45/50/40, which is 45) —
    some non-trivial weighting is in play upstream that this story cannot
    reverse-engineer from the sample alone. Sales-weighted average is the
    most defensible engineering default (bigger teams influence the
    headline more, directionally right for a company-wide figure) but is
    NOT verified against the sample. Both halves — the per-row ingestion
    treatment AND this aggregation — MUST be confirmed by a
    finance/business stakeholder before this story is marked done (AC #6).
    """
    total_sales = sum((row.sales_amount for row in rows), Decimal(0))
    if not rows or total_sales == 0:
        return None, None
    weighted_achievement = sum((row.achievement_pct * row.sales_amount for row in rows), Decimal(0))
    weighted_growth = sum((row.growth_pct * row.sales_amount for row in rows), Decimal(0))
    return weighted_achievement / total_sales, weighted_growth / total_sales


class DashboardMetricsService:
    def __init__(
        self,
        sales_data: SalesDataRepository,
        teams: TeamRepository,
        import_runs: ImportRunRepository,
        stale_after: timedelta,
    ) -> None:
        self._sales_data = sales_data
        self._teams = teams
        self._import_runs = import_runs
        self._stale_after = stale_after

    async def get_summary(self, today: date, now: datetime) -> DashboardSummary:
        year_start = today.replace(month=1, day=1)
        month_start = today.replace(day=1)

        today_sales = await self._sales_data.sum_amount_in_range(today, today)
        ytd_sales = await self._sales_data.sum_amount_in_range(year_start, today)
        mtd_sales = await self._sales_data.sum_amount_in_range(month_start, today)

        latest_rows = await self._sales_data.latest_per_team()
        team_names = dict(await self._teams.list_all())
        team_performance = sorted(
            (
                TeamPerformance(
                    team_id=row.team_id,
                    team_name=team_names.get(row.team_id, row.team_id.hex),
                    achievement_pct=row.achievement_pct,
                )
                for row in latest_rows
            ),
            key=lambda tp: tp.team_name,
        )

        achievement_pct, growth_pct = _aggregate_company_wide(latest_rows)

        data_as_of = await self._import_runs.get_last_successful_completed_at()
        is_stale = data_as_of is None or (now - data_as_of) > self._stale_after

        return DashboardSummary(
            today_sales=today_sales,
            ytd_sales=ytd_sales,
            mtd_sales=mtd_sales,
            achievement_pct=achievement_pct,
            growth_pct=growth_pct,
            team_performance=team_performance,
            data_as_of=data_as_of,
            is_stale=is_stale,
        )
