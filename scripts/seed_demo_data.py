"""Seed demonstration data for GrowthTrack.

Populates Teams, a Sales User/Manager roster, RecipientLists (with
membership), opt-in consents, a full year-to-date SalesData time series,
a BrandPerformance snapshot, a Doctor snapshot, and one succeeded ImportRun
— everything the Dashboard, Recipients, and Doctor Visit List
services read from, so a fresh environment has something to look at.

Does not touch the ``users`` table's Administrator row(s) — those only ever
come from Epic 1's bootstrap flow (domain/bootstrap.py).

Safe to re-run: Teams/RecipientLists are looked up by name, roster Users by
mobile, and consents by "already active" before creating anything new;
SalesData/BrandPerformance/Doctors upsert in place by their natural key. A
fresh ImportRun row is added on every run, same as the real nightly job
would.

Run with: uv run python -m scripts.seed_demo_data
"""

from __future__ import annotations

import asyncio
import random
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from adapters.persistence.brand_performance import SqlAlchemyBrandPerformanceRepository
from adapters.persistence.consent import SqlAlchemyOptInConsentRepository
from adapters.persistence.database import create_session_factory
from adapters.persistence.doctors import SqlAlchemyDoctorRepository
from adapters.persistence.import_runs import SqlAlchemyImportRunRepository
from adapters.persistence.recipient_lists import SqlAlchemyRecipientListRepository
from adapters.persistence.sales_data import SqlAlchemySalesDataRepository
from adapters.persistence.teams import SqlAlchemyTeamRepository
from adapters.persistence.users import SqlAlchemyUserRepository
from domain.models import BrandPerformance, Doctor, RecipientListKind, Role, SalesData, User, UserStatus

random.seed(20260720)  # deterministic across re-runs

TEAM_NAMES = ["North Region", "South Region", "East Region", "West Region"]

_FIRST_NAMES = [
    "Rakibul", "Nusrat", "Tanvir", "Sadia", "Mahmudul", "Farzana", "Shakil",
    "Israt", "Habibur", "Marzia", "Rezaul", "Kamrun", "Ashraful", "Nasrin",
    "Golam", "Sharmin", "Jahid", "Rummana", "Emran", "Tahmina",
]
_LAST_NAMES = [
    "Islam", "Rahman", "Ahmed", "Hossain", "Chowdhury", "Akter", "Uddin",
    "Karim", "Hasan", "Begum",
]

BRAND_NAMES = [
    "Cardiozen", "Pulmocare", "Glucoshield", "Renalex", "Hepatone",
    "Neurofit", "Vitanova", "Immunax", "Dermacure", "Osteoplus",
    "Gastrolief", "Thermanix", "Cephalor", "Hematovix", "Rheumatrol",
]


def _person_name(seq: int) -> str:
    return f"{_FIRST_NAMES[seq % len(_FIRST_NAMES)]} {_LAST_NAMES[seq % len(_LAST_NAMES)]}"


def _mobile(seq: int) -> str:
    return f"+8801{300000000 + seq:09d}"


async def _seed_teams(teams_repo: SqlAlchemyTeamRepository) -> dict[str, uuid.UUID]:
    return {name: await teams_repo.get_or_create_by_name(name) for name in TEAM_NAMES}


async def _seed_roster(
    users_repo: SqlAlchemyUserRepository, team_ids: dict[str, uuid.UUID]
) -> tuple[dict[str, list[User]], list[User], list[User]]:
    roster_by_team: dict[str, list[User]] = {name: [] for name in TEAM_NAMES}
    managers: list[User] = []
    reps: list[User] = []
    seq = 0
    for name in TEAM_NAMES:
        team_id = team_ids[name]
        for role, count in ((Role.MANAGER, 1), (Role.SALES_USER, 3)):
            for _ in range(count):
                mobile = _mobile(seq)
                user = await users_repo.get_by_mobile(mobile)
                if user is None:
                    user = User(
                        id=uuid.uuid4(),
                        username=None,
                        hashed_password=None,
                        role=role,
                        status=UserStatus.ACTIVE,
                        version=1,
                        created_at=datetime.now(UTC),
                        name=_person_name(seq),
                        mobile=mobile,
                        team_id=team_id,
                    )
                    await users_repo.add(user)
                roster_by_team[name].append(user)
                (managers if role == Role.MANAGER else reps).append(user)
                seq += 1
    return roster_by_team, managers, reps


async def _seed_recipient_lists(
    recipient_lists_repo: SqlAlchemyRecipientListRepository,
    roster_by_team: dict[str, list[User]],
    managers: list[User],
) -> None:
    for name, members in roster_by_team.items():
        list_name = f"{name} WhatsApp Group"
        if await recipient_lists_repo.get_by_name(list_name) is None:
            list_id = uuid.uuid4()
            await recipient_lists_repo.add(list_id, list_name, RecipientListKind.GROUP)
            await recipient_lists_repo.replace_members(list_id, [u.id for u in members])

    channel_name = "Regional Managers Channel"
    if await recipient_lists_repo.get_by_name(channel_name) is None:
        list_id = uuid.uuid4()
        await recipient_lists_repo.add(list_id, channel_name, RecipientListKind.CHANNEL)
        await recipient_lists_repo.replace_members(list_id, [u.id for u in managers])


async def _seed_consents(
    consents_repo: SqlAlchemyOptInConsentRepository, users: list[User]
) -> None:
    for i, user in enumerate(users):
        if i % 5 == 4:
            continue  # leave ~20% without consent, for demo variety
        if await consents_repo.get_active(user.id) is None:
            await consents_repo.grant(user.id, user.mobile)


async def _seed_sales_data(
    sales_repo: SqlAlchemySalesDataRepository, team_ids: dict[str, uuid.UUID], today: date
) -> int:
    year_start = today.replace(month=1, day=1)
    total = 0
    for team_id in team_ids.values():
        base_amount = Decimal(random.uniform(120_000, 320_000))
        base_achievement = Decimal(random.uniform(75, 115))
        rows: list[SalesData] = []
        d = year_start
        while d <= today:
            noise = Decimal(random.uniform(0.85, 1.15))
            # Bangladesh weekend (Fri/Sat) runs lighter.
            weekend_factor = Decimal("0.6") if d.weekday() in (4, 5) else Decimal("1.0")
            amount = (base_amount * noise * weekend_factor).quantize(Decimal("0.01"))
            achievement = (base_achievement + Decimal(random.uniform(-8, 8))).quantize(Decimal("0.1"))
            growth = Decimal(random.uniform(-12, 22)).quantize(Decimal("0.1"))
            rows.append(
                SalesData(
                    id=uuid.uuid4(),
                    date=d,
                    team_id=team_id,
                    sales_amount=amount,
                    achievement_pct=achievement,
                    growth_pct=growth,
                )
            )
            d += timedelta(days=1)
        await sales_repo.upsert_many(rows)
        total += len(rows)
    return total


async def _seed_brand_performance(brand_repo: SqlAlchemyBrandPerformanceRepository) -> int:
    rows: list[BrandPerformance] = []
    sales = sorted((Decimal(random.uniform(200_000, 900_000)) for _ in BRAND_NAMES), reverse=True)
    for rank, (brand_name, brand_sales) in enumerate(zip(BRAND_NAMES, sales, strict=True), start=1):
        if rank <= 5:
            growth = Decimal(random.uniform(2, 20))
        elif rank <= 10:
            growth = Decimal(random.uniform(-15, -3))  # middle-ranked but declining: Focus brands
        else:
            growth = Decimal(random.uniform(-20, -4))
        rows.append(
            BrandPerformance(
                id=uuid.uuid4(),
                external_brand_id=f"BR-{rank:03d}",
                brand_name=brand_name,
                sales=brand_sales.quantize(Decimal("0.01")),
                rank=rank,
                growth_pct=growth.quantize(Decimal("0.1")),
            )
        )
    await brand_repo.upsert_many(rows)
    return len(rows)


async def _seed_doctors(
    doctor_repo: SqlAlchemyDoctorRepository, team_ids: dict[str, uuid.UUID]
) -> int:
    rows: list[Doctor] = []
    seq = 0
    for territory in team_ids:
        for priority in range(1, 8):
            seq += 1
            slug = territory.split()[0].upper()
            rows.append(
                Doctor(
                    id=uuid.uuid4(),
                    external_doctor_id=f"DOC-{slug}-{priority:02d}",
                    name=f"Dr. {_person_name(seq + 100)}",
                    territory=territory,
                    priority=priority,
                )
            )
    await doctor_repo.upsert_many(rows)
    return len(rows)


async def _seed_import_run(
    import_run_repo: SqlAlchemyImportRunRepository, records_processed: int
) -> None:
    now = datetime.now(UTC)
    correlation_id = uuid.uuid4()
    run_id = await import_run_repo.start(correlation_id, now - timedelta(minutes=2))
    await import_run_repo.mark_succeeded(run_id, now, records_processed, records_rejected=0)


async def main() -> None:
    session_factory = create_session_factory()
    async with session_factory() as session:
        teams_repo = SqlAlchemyTeamRepository(session)
        users_repo = SqlAlchemyUserRepository(session)
        recipient_lists_repo = SqlAlchemyRecipientListRepository(session)
        consents_repo = SqlAlchemyOptInConsentRepository(session)
        sales_repo = SqlAlchemySalesDataRepository(session)
        brand_repo = SqlAlchemyBrandPerformanceRepository(session)
        doctor_repo = SqlAlchemyDoctorRepository(session)
        import_run_repo = SqlAlchemyImportRunRepository(session)

        today = datetime.now(UTC).astimezone(ZoneInfo("Asia/Dhaka")).date()

        team_ids = await _seed_teams(teams_repo)
        roster_by_team, managers, reps = await _seed_roster(users_repo, team_ids)
        await _seed_recipient_lists(recipient_lists_repo, roster_by_team, managers)
        await _seed_consents(consents_repo, managers + reps)

        records_processed = await _seed_sales_data(sales_repo, team_ids, today)
        records_processed += await _seed_brand_performance(brand_repo)
        records_processed += await _seed_doctors(doctor_repo, team_ids)
        await _seed_import_run(import_run_repo, records_processed)

        await session.commit()

    print(f"Seeded {len(team_ids)} teams, {len(managers) + len(reps)} roster users, "
          f"{records_processed} sales/brand/doctor records.")


if __name__ == "__main__":
    asyncio.run(main())
