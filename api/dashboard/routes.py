"""Dashboard summary read (Story 2.2, CAP-2)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from adapters.persistence.import_runs import SqlAlchemyImportRunRepository
from adapters.persistence.sales_data import SqlAlchemySalesDataRepository
from adapters.persistence.teams import SqlAlchemyTeamRepository
from api.auth.dependencies import get_current_user, get_db
from config import get_settings
from domain.metrics import DashboardMetricsService
from domain.models import User

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


class TeamPerformanceResponse(BaseModel):
    team_name: str
    achievement_pct: Decimal


class DashboardSummaryResponse(BaseModel):
    today_sales: Decimal
    ytd_sales: Decimal
    mtd_sales: Decimal
    achievement_pct: Decimal | None
    growth_pct: Decimal | None
    team_performance: list[TeamPerformanceResponse]
    data_as_of: datetime | None
    is_stale: bool


@router.get("/summary", response_model=DashboardSummaryResponse)
async def summary(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> DashboardSummaryResponse:
    settings = get_settings()
    now = datetime.now(UTC)
    today = now.astimezone(ZoneInfo("Asia/Dhaka")).date()

    service = DashboardMetricsService(
        sales_data=SqlAlchemySalesDataRepository(session),
        teams=SqlAlchemyTeamRepository(session),
        import_runs=SqlAlchemyImportRunRepository(session),
        stale_after=timedelta(hours=settings.dashboard_stale_after_hours),
    )
    result = await service.get_summary(today, now)

    return DashboardSummaryResponse(
        today_sales=result.today_sales,
        ytd_sales=result.ytd_sales,
        mtd_sales=result.mtd_sales,
        achievement_pct=result.achievement_pct,
        growth_pct=result.growth_pct,
        team_performance=[
            TeamPerformanceResponse(team_name=tp.team_name, achievement_pct=tp.achievement_pct)
            for tp in result.team_performance
        ],
        data_as_of=result.data_as_of,
        is_stale=result.is_stale,
    )
