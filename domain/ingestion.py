"""Nightly Source System import (AC #1, #2, #3; AD-6 pipeline: staged,
validated, transformed, then upserted).

``SourceSystemImportService`` is constructed with every port, never a
concrete adapter (AD-1) — the same "no route handler/job callback touches
a repository directly, only a domain service does" pattern already used
by every prior story's route handlers, applied here to a scheduler job
callback instead of an HTTP route.

Not audit-logged: FR-12/AD-7 enumerate the audited-action set as
administrator-initiated actions with a human actor. A nightly import has
no ``actor`` (it's a system-triggered background job), so it doesn't fit
the Audit Log's shape or purpose — structured JSON logging (per-run
``correlation_id``, completion/failure/rejected-row lines) is used
instead, mirroring Story 1.6's "no audit entry for theme-preference
changes" precedent.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum

from domain.models import BrandPerformance, Doctor, SalesData
from ports.brand_performance import BrandPerformanceRepository
from ports.doctors import DoctorRepository
from ports.import_runs import ImportRunRepository
from ports.sales_data import SalesDataRepository
from ports.source_system import SourceSystemImporter
from ports.staging import StagingRepository
from ports.teams import TeamRepository

logger = logging.getLogger(__name__)

_ENTITY_TYPES = ("sales_data", "brand_performance", "doctors")

# Postgres `Integer` range — a value parsing beyond this raises a DB error
# during upsert instead of being rejected per-row like other malformed input.
_MAX_POSTGRES_INTEGER = 2_147_483_647

# NFR-5/AC #2 of Story 2.4: doctors carry no patient health data. An
# unexpected extra CSV column is rejected outright rather than silently
# dropped — this is the full set of columns this story's Doctor entity
# accepts, matching `entities.md` exactly.
_DOCTORS_KNOWN_COLUMNS = frozenset({"external_doctor_id", "name", "territory", "priority"})


def _require(row: dict[str, str | None], key: str) -> str:
    """Returns ``row[key]``, narrowed to ``str`` — safe only after the
    row's own validator has already confirmed the field is non-empty."""
    value = row[key]
    assert value is not None, f"validated row is missing required field {key!r}"
    return value


class ImportOutcome(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"  # another run already holds the advisory lock — not an error


@dataclass
class ImportRunResult:
    outcome: ImportOutcome
    # None only when outcome is SKIPPED — no ImportRun row is ever created for a skip.
    run_id: uuid.UUID | None = None
    records_processed: int = 0
    records_rejected: int = 0


@dataclass
class _TransformedBatch:
    sales_data: list[SalesData] = field(default_factory=list)
    brand_performance: list[BrandPerformance] = field(default_factory=list)
    doctors: list[Doctor] = field(default_factory=list)


def _validate_sales_data_row(row: dict[str, str | None]) -> str | None:
    """Returns a rejection reason, or None if the row is valid."""
    raw_date = row.get("date")
    if not raw_date:
        return "date is required"
    try:
        date.fromisoformat(raw_date)
    except ValueError:
        return f"date {raw_date!r} is not a valid ISO 8601 date"

    if not (row.get("team") or "").strip():
        return "team is required"

    try:
        sales_amount = Decimal(row.get("sales_amount") or "")
    except (InvalidOperation, TypeError):
        return f"sales_amount {row.get('sales_amount')!r} is not a valid decimal"
    if not sales_amount.is_finite():
        return f"sales_amount {row.get('sales_amount')!r} must be a finite number"
    if sales_amount < 0:
        return "sales_amount must be >= 0"

    # achievement_pct/growth_pct may be negative — growth can decline.
    try:
        achievement_pct = Decimal(row.get("achievement_pct") or "")
    except (InvalidOperation, TypeError):
        return f"achievement_pct {row.get('achievement_pct')!r} is not a valid decimal"
    if not achievement_pct.is_finite():
        return f"achievement_pct {row.get('achievement_pct')!r} must be a finite number"
    try:
        growth_pct = Decimal(row.get("growth_pct") or "")
    except (InvalidOperation, TypeError):
        return f"growth_pct {row.get('growth_pct')!r} is not a valid decimal"
    if not growth_pct.is_finite():
        return f"growth_pct {row.get('growth_pct')!r} must be a finite number"

    return None


def _validate_brand_performance_row(row: dict[str, str | None]) -> str | None:
    if not row.get("external_brand_id"):
        return "external_brand_id is required"
    if not row.get("brand_name"):
        return "brand_name is required"

    try:
        sales = Decimal(row.get("sales") or "")
    except (InvalidOperation, TypeError):
        return f"sales {row.get('sales')!r} is not a valid decimal"
    if not sales.is_finite():
        return f"sales {row.get('sales')!r} must be a finite number"
    if sales < 0:
        return "sales must be >= 0"

    try:
        rank = int(row.get("rank") or "")
    except (TypeError, ValueError):
        return f"rank {row.get('rank')!r} is not a valid integer"
    if rank <= 0:
        return "rank must be a positive integer"
    if rank > _MAX_POSTGRES_INTEGER:
        return f"rank {rank} exceeds the maximum allowed value"

    try:
        growth_pct = Decimal(row.get("growth_pct") or "")
    except (InvalidOperation, TypeError):
        return f"growth_pct {row.get('growth_pct')!r} is not a valid decimal"
    if not growth_pct.is_finite():
        return f"growth_pct {row.get('growth_pct')!r} must be a finite number"

    return None


def _validate_doctors_row(row: dict[str, str | None]) -> str | None:
    if not row.get("external_doctor_id"):
        return "external_doctor_id is required"
    if not row.get("name"):
        return "name is required"
    if not row.get("territory"):
        return "territory is required"

    try:
        priority = int(row.get("priority") or "")
    except (TypeError, ValueError):
        return f"priority {row.get('priority')!r} is not a valid integer"
    if priority <= 0:
        return "priority must be a positive integer"
    if priority > _MAX_POSTGRES_INTEGER:
        return f"priority {priority} exceeds the maximum allowed value"

    return None


_VALIDATORS = {
    "sales_data": _validate_sales_data_row,
    "brand_performance": _validate_brand_performance_row,
    "doctors": _validate_doctors_row,
}


class SourceSystemImportService:
    def __init__(
        self,
        importer: SourceSystemImporter,
        staging: StagingRepository,
        teams: TeamRepository,
        sales_data: SalesDataRepository,
        brand_performance: BrandPerformanceRepository,
        doctors: DoctorRepository,
        import_runs: ImportRunRepository,
    ) -> None:
        self._importer = importer
        self._staging = staging
        self._teams = teams
        self._sales_data = sales_data
        self._brand_performance = brand_performance
        self._doctors = doctors
        self._import_runs = import_runs

    async def run(self) -> ImportRunResult:
        # Concurrency guard first, before any ImportRun row exists — if the
        # lock can't be acquired, nothing has been written yet, so there is
        # nothing to clean up and no row left dangling in a RUNNING state.
        if not await self._import_runs.try_acquire_lock():
            logger.info("nightly import skipped: another run already in progress")
            return ImportRunResult(outcome=ImportOutcome.SKIPPED)

        correlation_id = uuid.uuid4()
        started_at = datetime.now(UTC)
        run_id = await self._import_runs.start(correlation_id, started_at)

        try:
            records_processed, records_rejected = await self._run_pipeline(run_id, correlation_id)
        except Exception:
            completed_at = datetime.now(UTC)
            logger.exception(
                "nightly import failed",
                extra={"correlation_id": str(correlation_id), "run_id": str(run_id)},
            )
            await self._import_runs.mark_failed(run_id, correlation_id, started_at, completed_at)
            return ImportRunResult(outcome=ImportOutcome.FAILED, run_id=run_id)

        completed_at = datetime.now(UTC)
        await self._import_runs.mark_succeeded(
            run_id, completed_at, records_processed, records_rejected
        )
        logger.info(
            "nightly import succeeded",
            extra={
                "correlation_id": str(correlation_id),
                "run_id": str(run_id),
                "records_processed": records_processed,
                "records_rejected": records_rejected,
            },
        )
        return ImportRunResult(
            outcome=ImportOutcome.SUCCEEDED,
            run_id=run_id,
            records_processed=records_processed,
            records_rejected=records_rejected,
        )

    async def _run_pipeline(self, run_id: uuid.UUID, correlation_id: uuid.UUID) -> tuple[int, int]:
        # Stage: raw, unconditional land of exactly what the importer
        # returned. Nothing is validated or parsed yet.
        batch = await self._importer.fetch_batch()
        for entity_type in _ENTITY_TYPES:
            raw_rows = batch.get(entity_type, [])
            if not raw_rows:
                logger.warning(
                    "zero records for entity type in nightly import batch",
                    extra={"correlation_id": str(correlation_id), "entity_type": entity_type},
                )
            await self._staging.stage(run_id, entity_type, raw_rows)

        # Validate: per-field checks, written back via mark_validated. Every
        # rejected row is logged individually with its specific reason.
        valid_rows: dict[str, list[dict[str, str | None]]] = {}
        records_rejected = 0
        for entity_type in _ENTITY_TYPES:
            staged = await self._staging.fetch_staged(run_id, entity_type)
            validator = _VALIDATORS[entity_type]
            original_rows = batch.get(entity_type, [])
            results: list[tuple[int, bool, str | None]] = []
            valid_rows[entity_type] = []
            for sequence, raw_row in staged:
                rejection_reason = validator(raw_row)
                if rejection_reason is None and entity_type == "doctors":
                    # No patient health data (NFR-5/AC #2 of Story 2.4) — an
                    # unexpected column is rejected, not silently dropped.
                    # Staging only ever captures the known columns, so the
                    # extra-column check must run against the row as
                    # originally returned by the importer, before staging.
                    original_row = original_rows[sequence]
                    extra_columns = sorted(set(original_row) - _DOCTORS_KNOWN_COLUMNS)
                    if extra_columns:
                        rejection_reason = f"unexpected column(s): {', '.join(extra_columns)}"
                is_valid = rejection_reason is None
                results.append((sequence, is_valid, rejection_reason))
                if is_valid:
                    valid_rows[entity_type].append(raw_row)
                else:
                    records_rejected += 1
                    logger.warning(
                        "nightly import row rejected",
                        extra={
                            "correlation_id": str(correlation_id),
                            "entity_type": entity_type,
                            "sequence": sequence,
                            "rejection_reason": rejection_reason,
                            "raw_row": raw_row,
                        },
                    )
            await self._staging.mark_validated(run_id, entity_type, results)

        # Transform: parse raw strings into typed domain values.
        transformed = await self._transform(valid_rows)

        # Upsert: one call per entity type with all valid, transformed rows.
        await self._sales_data.upsert_many(transformed.sales_data)
        await self._brand_performance.upsert_many(transformed.brand_performance)
        await self._doctors.upsert_many(transformed.doctors)

        records_processed = (
            len(transformed.sales_data)
            + len(transformed.brand_performance)
            + len(transformed.doctors)
        )
        return records_processed, records_rejected

    async def _transform(
        self, valid_rows: dict[str, list[dict[str, str | None]]]
    ) -> _TransformedBatch:
        transformed = _TransformedBatch()

        # Dedupe team names within the batch before resolving each row's
        # team_id — get_or_create_by_name is called once per unique name,
        # not once per row.
        team_cache: dict[str, uuid.UUID] = {}
        for raw_row in valid_rows.get("sales_data", []):
            team_name = _require(raw_row, "team").strip()
            if team_name not in team_cache:
                team_cache[team_name] = await self._teams.get_or_create_by_name(team_name)
            transformed.sales_data.append(
                SalesData(
                    id=uuid.uuid4(),
                    date=date.fromisoformat(_require(raw_row, "date")),
                    team_id=team_cache[team_name],
                    sales_amount=Decimal(_require(raw_row, "sales_amount")),
                    achievement_pct=Decimal(_require(raw_row, "achievement_pct")),
                    growth_pct=Decimal(_require(raw_row, "growth_pct")),
                )
            )

        for raw_row in valid_rows.get("brand_performance", []):
            transformed.brand_performance.append(
                BrandPerformance(
                    id=uuid.uuid4(),
                    external_brand_id=_require(raw_row, "external_brand_id"),
                    brand_name=_require(raw_row, "brand_name"),
                    sales=Decimal(_require(raw_row, "sales")),
                    rank=int(_require(raw_row, "rank")),
                    growth_pct=Decimal(_require(raw_row, "growth_pct")),
                )
            )

        for raw_row in valid_rows.get("doctors", []):
            transformed.doctors.append(
                Doctor(
                    id=uuid.uuid4(),
                    external_doctor_id=_require(raw_row, "external_doctor_id"),
                    name=_require(raw_row, "name"),
                    territory=_require(raw_row, "territory"),
                    priority=int(_require(raw_row, "priority")),
                )
            )

        return transformed
