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

from domain.models import BrandPerformance, Doctor, SalesData
from ports.brand_performance import BrandPerformanceRepository
from ports.doctors import DoctorRepository
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

    [Review][Patch, 2026-07-20]: excludes any row whose `date` is older than
    the most recent date represented in `rows` — a team's nightly row can be
    missing or rejected on a given night (Story 2.1's per-row validation),
    and blending that team's stale figures into an otherwise-current
    headline would silently mix two different operational days into one
    number. The excluded team still appears in `team_performance` (Task 2
    Step 7) with its own last-known `achievement_pct` — only the
    company-wide headline weight is affected.
    """
    if not rows:
        return None, None
    latest_date = max(row.date for row in rows)
    current_rows = [row for row in rows if row.date == latest_date]
    total_sales = sum((row.sales_amount for row in current_rows), Decimal(0))
    if total_sales == 0:
        return None, None
    weighted_achievement = sum(
        (row.achievement_pct * row.sales_amount for row in current_rows), Decimal(0)
    )
    weighted_growth = sum(
        (row.growth_pct * row.sales_amount for row in current_rows), Decimal(0)
    )
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


@dataclass
class BrandEntry:
    external_brand_id: str
    brand_name: str
    sales: Decimal
    rank: int
    growth_pct: Decimal


@dataclass
class BrandPerformanceSummary:
    top_brands: list[BrandEntry]
    low_performing_brands: list[BrandEntry]
    focus_brands: list[BrandEntry]


def _classify_brands(
    rows: list[BrandPerformance], top_n: int, low_performing_n: int, focus_n: int
) -> BrandPerformanceSummary:
    """[ASSUMPTION — CONFIRM, epics.md Story 2.3 AC #4 / PRD §4.3 footnote]
    Neither source SRS defines what makes a brand "top," "low-performing,"
    or "focus" — this is a business decision, not an engineering guess,
    and epics.md explicitly says so. This function implements the most
    defensible engineering default so Epic 2 isn't fully blocked and
    Epic 4 has a working BrandPerformanceService to build on, but it MUST
    be confirmed by a business/product stakeholder before this story is
    marked done (AC #4) — do not describe this as "resolved" anywhere.

    Two genuinely open sub-questions this default resolves, both flagged:
    1. Threshold counts (top_n/low_performing_n/focus_n) — arbitrary
       until confirmed; this story's default is 5/5/5 (config.py).
    2. Whether the three lists are mutually exclusive. The PRD glossary
       reads "classified as Top Brand, Low-Performing Brand, or Focus
       Brand" (singular "or"), suggesting one classification per brand,
       not three independently-computed lists that could overlap. This
       function treats them as mutually exclusive for exactly that
       reason: Top N (best `rank`) is selected first; Low-Performing N
       is the worst-`rank` brands among what's LEFT after removing Top;
       Focus N is the most-negative-`growth_pct` brands among what's
       left after removing Top and Low-Performing. A brand already
       ranked "Top" can never also show up as "Focus" — which would be
       a confusing, self-contradicting Dashboard state.

    "Focus Brand" specifically (the vaguest of the three, no PRD
    definition at all) is read as "meaningfully declining but not
    already the worst performer" (growth_pct < 0, among the
    not-already-classified remainder) — distinct from Low-Performing
    (already at the bottom of `rank`, possibly beyond an easy save) and
    distinct from Top (already winning). This reading treats "Focus" as
    an early-intervention signal, which is the only version of "needs a
    push right now" that adds information beyond the other two lists.

    `rank` here is the Source-System-ingested overall performance rank
    (Story 2.1), not sales-recomputed — ascending rank = better.
    """
    if top_n < 0 or low_performing_n < 0 or focus_n < 0:
        raise ValueError("top_n, low_performing_n, and focus_n must be >= 0")

    by_rank = sorted(rows, key=lambda r: (r.rank, r.brand_name))
    top = by_rank[:top_n]
    top_ids = {r.external_brand_id for r in top}
    remaining_after_top = [r for r in by_rank if r.external_brand_id not in top_ids]
    low = sorted(remaining_after_top, key=lambda r: (-r.rank, r.brand_name))[:low_performing_n]
    low_ids = {r.external_brand_id for r in low}
    remaining_after_low = [r for r in remaining_after_top if r.external_brand_id not in low_ids]
    focus = sorted(
        (r for r in remaining_after_low if r.growth_pct < 0),
        key=lambda r: (r.growth_pct, r.brand_name),
    )[:focus_n]

    def _to_entry(r: BrandPerformance) -> BrandEntry:
        return BrandEntry(
            external_brand_id=r.external_brand_id,
            brand_name=r.brand_name,
            sales=r.sales,
            rank=r.rank,
            growth_pct=r.growth_pct,
        )

    return BrandPerformanceSummary(
        top_brands=[_to_entry(r) for r in top],
        low_performing_brands=[_to_entry(r) for r in low],
        focus_brands=[_to_entry(r) for r in focus],
    )


class BrandPerformanceService:
    def __init__(
        self,
        brand_performance: BrandPerformanceRepository,
        top_n: int,
        low_performing_n: int,
        focus_n: int,
    ) -> None:
        self._brand_performance = brand_performance
        self._top_n = top_n
        self._low_performing_n = low_performing_n
        self._focus_n = focus_n

    async def get_summary(self) -> BrandPerformanceSummary:
        rows = await self._brand_performance.list_all()
        return _classify_brands(rows, self._top_n, self._low_performing_n, self._focus_n)


@dataclass
class DoctorEntry:
    doctor_name: str
    territory: str
    target_priority: int


def _rank_doctors_for_territory(rows: list[Doctor], territory: str) -> list[DoctorEntry]:
    """[ASSUMPTION — ranking direction, not flagged as a blocking business
    decision in epics.md Story 2.4 (unlike Story 2.3 AC #4's thresholds or
    Story 2.2 AC #6's formula, which explicitly withhold `done` pending
    stakeholder sign-off) — but genuinely undefined by any planning doc.
    Neither prd.md's Glossary ("Target Priority — the ranking used to
    order the Doctor visit list") nor entities.md's field list say
    whether a LOWER Doctor.priority number means "visit first" or
    "visit last". This function treats lower priority = higher
    urgency = visit first (ascending sort), mirroring this exact
    codebase's already-established `BrandPerformance.rank` convention
    (Story 2.3: "ascending rank = better") for the same kind of
    Source-System-ingested ordinal field. If a business stakeholder
    later confirms the opposite direction, this is a one-function,
    one-line change (flip to descending) — nothing else in this
    story's design depends on the direction chosen.
    """
    normalized_territory = territory.strip().lower()
    matching = [r for r in rows if r.territory.strip().lower() == normalized_territory]
    ranked = sorted(matching, key=lambda r: (r.priority, r.name, r.external_doctor_id))
    return [
        DoctorEntry(doctor_name=r.name, territory=r.territory, target_priority=r.priority)
        for r in ranked
    ]


class DoctorVisitListService:
    def __init__(self, doctors: DoctorRepository) -> None:
        self._doctors = doctors

    async def get_visit_list(self, territory: str) -> list[DoctorEntry]:
        rows = await self._doctors.list_all()
        return _rank_doctors_for_territory(rows, territory)
