import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from domain.ingestion import ImportOutcome, SourceSystemImportService
from ports.brand_performance import BrandPerformanceRepository
from ports.doctors import DoctorRepository
from ports.import_runs import ImportRunRepository
from ports.sales_data import SalesDataRepository
from ports.source_system import SourceSystemImporter
from ports.staging import StagingRepository
from ports.teams import TeamRepository


class FakeSourceSystemImporter(SourceSystemImporter):
    def __init__(self, batch: dict[str, list[dict[str, str | None]]]) -> None:
        self._batch = batch

    async def fetch_batch(self) -> dict[str, list[dict[str, str | None]]]:
        return self._batch


class FakeStagingRepository(StagingRepository):
    def __init__(self) -> None:
        self._rows: dict[tuple[uuid.UUID, str], list[dict]] = {}

    async def stage(
        self, import_run_id: uuid.UUID, entity_type: str, raw_rows: list[dict[str, str | None]]
    ) -> None:
        self._rows[(import_run_id, entity_type)] = [
            {"sequence": i, "raw_row": row, "is_valid": None, "rejection_reason": None}
            for i, row in enumerate(raw_rows)
        ]

    async def fetch_staged(
        self, import_run_id: uuid.UUID, entity_type: str
    ) -> list[tuple[int, dict[str, str | None]]]:
        return [
            (r["sequence"], r["raw_row"]) for r in self._rows.get((import_run_id, entity_type), [])
        ]

    async def mark_validated(
        self,
        import_run_id: uuid.UUID,
        entity_type: str,
        results: list[tuple[int, bool, str | None]],
    ) -> None:
        by_sequence = {r["sequence"]: r for r in self._rows.get((import_run_id, entity_type), [])}
        for sequence, is_valid, rejection_reason in results:
            by_sequence[sequence]["is_valid"] = is_valid
            by_sequence[sequence]["rejection_reason"] = rejection_reason


class FakeTeamRepository(TeamRepository):
    def __init__(self) -> None:
        self._teams: dict[str, uuid.UUID] = {}
        self.call_count_by_name: dict[str, int] = {}

    async def get_or_create_by_name(self, name: str) -> uuid.UUID:
        self.call_count_by_name[name] = self.call_count_by_name.get(name, 0) + 1
        if name not in self._teams:
            self._teams[name] = uuid.uuid4()
        return self._teams[name]

    async def list_all(self) -> list[tuple[uuid.UUID, str]]:
        raise NotImplementedError


class FakeSalesDataRepository(SalesDataRepository):
    def __init__(self, raise_on_upsert: bool = False) -> None:
        self.upserted: list = []
        self._raise_on_upsert = raise_on_upsert

    async def upsert_many(self, rows: list) -> None:
        if self._raise_on_upsert:
            raise RuntimeError("simulated persistence failure")
        self.upserted.extend(rows)

    async def sum_amount_in_range(self, start_date: date, end_date: date) -> Decimal:
        raise NotImplementedError

    async def latest_per_team(self) -> list:
        raise NotImplementedError


class FakeBrandPerformanceRepository(BrandPerformanceRepository):
    def __init__(self) -> None:
        self.upserted: list = []

    async def upsert_many(self, rows: list) -> None:
        self.upserted.extend(rows)


class FakeDoctorRepository(DoctorRepository):
    def __init__(self) -> None:
        self.upserted: list = []

    async def upsert_many(self, rows: list) -> None:
        self.upserted.extend(rows)


class FakeImportRunRepository(ImportRunRepository):
    def __init__(self, lock_available: bool = True) -> None:
        self._lock_available = lock_available
        self.calls: list[str] = []
        self.started: list[tuple[uuid.UUID, datetime]] = []
        self.succeeded: list[tuple] = []
        self.failed: list[tuple] = []
        self._run_id = uuid.uuid4()

    async def try_acquire_lock(self) -> bool:
        self.calls.append("try_acquire_lock")
        return self._lock_available

    async def start(self, correlation_id: uuid.UUID, started_at: datetime) -> uuid.UUID:
        self.calls.append("start")
        self.started.append((correlation_id, started_at))
        return self._run_id

    async def mark_succeeded(
        self,
        run_id: uuid.UUID,
        completed_at: datetime,
        records_processed: int,
        records_rejected: int,
    ) -> None:
        self.calls.append("mark_succeeded")
        self.succeeded.append((run_id, completed_at, records_processed, records_rejected))

    async def mark_failed(
        self,
        run_id: uuid.UUID,
        correlation_id: uuid.UUID,
        started_at: datetime,
        completed_at: datetime,
    ) -> None:
        self.calls.append("mark_failed")
        self.failed.append((run_id, correlation_id, started_at, completed_at))

    async def get_last_successful_completed_at(self) -> datetime | None:
        raise NotImplementedError


@dataclass
class _Fakes:
    staging: FakeStagingRepository = field(default_factory=FakeStagingRepository)
    teams: FakeTeamRepository = field(default_factory=FakeTeamRepository)
    sales_data: FakeSalesDataRepository = field(default_factory=FakeSalesDataRepository)
    brand_performance: FakeBrandPerformanceRepository = field(
        default_factory=FakeBrandPerformanceRepository
    )
    doctors: FakeDoctorRepository = field(default_factory=FakeDoctorRepository)
    import_runs: FakeImportRunRepository = field(default_factory=FakeImportRunRepository)


def _service(
    batch: dict[str, list[dict[str, str | None]]],
    *,
    sales_data: FakeSalesDataRepository | None = None,
    import_runs: FakeImportRunRepository | None = None,
) -> tuple[SourceSystemImportService, _Fakes]:
    fakes = _Fakes(
        sales_data=sales_data or FakeSalesDataRepository(),
        import_runs=import_runs or FakeImportRunRepository(),
    )
    service = SourceSystemImportService(
        importer=FakeSourceSystemImporter(batch),
        staging=fakes.staging,
        teams=fakes.teams,
        sales_data=fakes.sales_data,
        brand_performance=fakes.brand_performance,
        doctors=fakes.doctors,
        import_runs=fakes.import_runs,
    )
    return service, fakes


async def test_happy_path_upserts_all_entity_types_and_marks_run_succeeded():
    batch = {
        "sales_data": [
            {
                "date": "2026-07-18",
                "team": "North",
                "sales_amount": "1000",
                "achievement_pct": "95.5",
                "growth_pct": "3.2",
            }
        ],
        "brand_performance": [
            {
                "external_brand_id": "B1",
                "brand_name": "Acme",
                "sales": "5000",
                "rank": "1",
                "growth_pct": "2.0",
            }
        ],
        "doctors": [
            {"external_doctor_id": "D1", "name": "Dr. Smith", "territory": "East", "priority": "1"}
        ],
    }
    service, fakes = _service(batch)

    result = await service.run()

    assert result.outcome == ImportOutcome.SUCCEEDED
    assert result.records_processed == 3
    assert result.records_rejected == 0
    assert len(fakes.sales_data.upserted) == 1
    assert len(fakes.brand_performance.upserted) == 1
    assert len(fakes.doctors.upserted) == 1
    assert len(fakes.import_runs.succeeded) == 1
    assert fakes.import_runs.succeeded[0][2:] == (3, 0)


async def test_malformed_rows_are_rejected_while_valid_rows_in_the_same_batch_still_upsert():
    batch = {
        "sales_data": [
            {
                "date": "2026-07-18",
                "team": "North",
                "sales_amount": "1000",
                "achievement_pct": "1",
                "growth_pct": "1",
            },
            {
                "date": "2026-07-18",
                "team": "South",
                "sales_amount": "not-a-number",
                "achievement_pct": "1",
                "growth_pct": "1",
            },
        ],
        "brand_performance": [],
        "doctors": [
            {"external_doctor_id": "D1", "name": "Dr. Smith", "territory": "East", "priority": "1"},
            {"external_doctor_id": "D2", "name": "Dr. Jones", "territory": "", "priority": "2"},
        ],
    }
    service, fakes = _service(batch)

    result = await service.run()

    assert result.outcome == ImportOutcome.SUCCEEDED
    assert result.records_processed == 2
    assert result.records_rejected == 2
    assert len(fakes.sales_data.upserted) == 1
    assert len(fakes.doctors.upserted) == 1


async def test_dedupes_team_name_lookups_within_a_batch():
    batch = {
        "sales_data": [
            {
                "date": "2026-07-18",
                "team": "North",
                "sales_amount": "1000",
                "achievement_pct": "1",
                "growth_pct": "1",
            },
            {
                "date": "2026-07-19",
                "team": "North",
                "sales_amount": "2000",
                "achievement_pct": "1",
                "growth_pct": "1",
            },
        ],
        "brand_performance": [],
        "doctors": [],
    }
    service, fakes = _service(batch)

    result = await service.run()

    assert result.records_processed == 2
    assert fakes.teams.call_count_by_name == {"North": 1}


async def test_team_names_are_normalized_before_dedup_and_lookup():
    batch = {
        "sales_data": [
            {
                "date": "2026-07-18",
                "team": "North",
                "sales_amount": "1000",
                "achievement_pct": "1",
                "growth_pct": "1",
            },
            {
                "date": "2026-07-19",
                "team": "  North  ",
                "sales_amount": "2000",
                "achievement_pct": "1",
                "growth_pct": "1",
            },
        ],
        "brand_performance": [],
        "doctors": [],
    }
    service, fakes = _service(batch)

    result = await service.run()

    assert result.records_processed == 2
    assert fakes.teams.call_count_by_name == {"North": 1}


async def test_a_failure_partway_marks_import_run_failed_and_does_not_propagate():
    batch = {
        "sales_data": [
            {
                "date": "2026-07-18",
                "team": "North",
                "sales_amount": "1000",
                "achievement_pct": "1",
                "growth_pct": "1",
            }
        ],
        "brand_performance": [],
        "doctors": [],
    }
    import_runs = FakeImportRunRepository()
    service, fakes = _service(
        batch, sales_data=FakeSalesDataRepository(raise_on_upsert=True), import_runs=import_runs
    )

    result = await service.run()

    assert result.outcome == ImportOutcome.FAILED
    assert result.run_id is not None
    assert len(import_runs.failed) == 1
    assert len(import_runs.succeeded) == 0


async def test_returns_skipped_without_touching_any_repository_when_lock_already_held():
    import_runs = FakeImportRunRepository(lock_available=False)
    batch = {
        "sales_data": [
            {
                "date": "2026-07-18",
                "team": "North",
                "sales_amount": "1000",
                "achievement_pct": "1",
                "growth_pct": "1",
            }
        ],
        "brand_performance": [],
        "doctors": [],
    }
    service, fakes = _service(batch, import_runs=import_runs)

    result = await service.run()

    assert result.outcome == ImportOutcome.SKIPPED
    assert result.run_id is None
    assert import_runs.calls == ["try_acquire_lock"]
    assert fakes.sales_data.upserted == []
    assert fakes.brand_performance.upserted == []
    assert fakes.doctors.upserted == []


async def test_non_finite_decimal_values_are_rejected_not_persisted():
    batch = {
        "sales_data": [
            {
                "date": "2026-07-18",
                "team": "North",
                "sales_amount": "NaN",
                "achievement_pct": "1",
                "growth_pct": "1",
            },
            {
                "date": "2026-07-19",
                "team": "North",
                "sales_amount": "Infinity",
                "achievement_pct": "1",
                "growth_pct": "1",
            },
        ],
        "brand_performance": [
            {
                "external_brand_id": "B1",
                "brand_name": "Acme",
                "sales": "NaN",
                "rank": "1",
                "growth_pct": "1",
            }
        ],
        "doctors": [],
    }
    service, fakes = _service(batch)

    result = await service.run()

    assert result.records_processed == 0
    assert result.records_rejected == 3
    assert fakes.sales_data.upserted == []
    assert fakes.brand_performance.upserted == []


async def test_rank_and_priority_beyond_postgres_integer_range_are_rejected():
    batch = {
        "sales_data": [],
        "brand_performance": [
            {
                "external_brand_id": "B1",
                "brand_name": "Acme",
                "sales": "1000",
                "rank": "99999999999",
                "growth_pct": "1",
            }
        ],
        "doctors": [
            {
                "external_doctor_id": "D1",
                "name": "Dr. Smith",
                "territory": "East",
                "priority": "99999999999",
            }
        ],
    }
    service, fakes = _service(batch)

    result = await service.run()

    assert result.records_processed == 0
    assert result.records_rejected == 2
    assert fakes.brand_performance.upserted == []
    assert fakes.doctors.upserted == []


async def test_doctor_rows_with_an_unexpected_extra_column_are_rejected_not_dropped():
    batch = {
        "sales_data": [],
        "brand_performance": [],
        "doctors": [
            {
                "external_doctor_id": "D1",
                "name": "Dr. Smith",
                "territory": "East",
                "priority": "1",
                "diagnosis": "unexpected patient data",
            },
            {"external_doctor_id": "D2", "name": "Dr. Jones", "territory": "West", "priority": "2"},
        ],
    }
    service, fakes = _service(batch)

    result = await service.run()

    assert result.records_processed == 1
    assert result.records_rejected == 1
    assert [row.external_doctor_id for row in fakes.doctors.upserted] == ["D2"]
