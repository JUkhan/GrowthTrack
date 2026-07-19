"""SQLAlchemy staging-table models + repository implementation (AD-6).

Three staging tables, one per entity type, each keyed on
`(import_run_id, sequence)` — `sequence` is the 0-based row-identity
ordinal `stage()` assigns in list order, not the row's UUID PK (unordered)
and not `created_at` (can collide within one bulk-insert transaction).
Raw columns are nullable text (pre-validation); `is_valid`/`rejection_reason`
are null until `mark_validated` runs.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import cast

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    UniqueConstraint,
    bindparam,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from adapters.persistence.database import Base
from ports.staging import StagingRepository


class StagingSalesDataModel(Base):
    __tablename__ = "staging_sales_data"
    __table_args__ = (UniqueConstraint("import_run_id", "sequence"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    import_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("import_runs.id"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_date: Mapped[str | None] = mapped_column(String, nullable=True)
    raw_team: Mapped[str | None] = mapped_column(String, nullable=True)
    raw_sales_amount: Mapped[str | None] = mapped_column(String, nullable=True)
    raw_achievement_pct: Mapped[str | None] = mapped_column(String, nullable=True)
    raw_growth_pct: Mapped[str | None] = mapped_column(String, nullable=True)
    is_valid: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class StagingBrandPerformanceModel(Base):
    __tablename__ = "staging_brand_performance"
    __table_args__ = (UniqueConstraint("import_run_id", "sequence"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    import_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("import_runs.id"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_external_brand_id: Mapped[str | None] = mapped_column(String, nullable=True)
    raw_brand_name: Mapped[str | None] = mapped_column(String, nullable=True)
    raw_sales: Mapped[str | None] = mapped_column(String, nullable=True)
    raw_rank: Mapped[str | None] = mapped_column(String, nullable=True)
    raw_growth_pct: Mapped[str | None] = mapped_column(String, nullable=True)
    is_valid: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class StagingDoctorsModel(Base):
    __tablename__ = "staging_doctors"
    __table_args__ = (UniqueConstraint("import_run_id", "sequence"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    import_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("import_runs.id"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_external_doctor_id: Mapped[str | None] = mapped_column(String, nullable=True)
    raw_name: Mapped[str | None] = mapped_column(String, nullable=True)
    raw_territory: Mapped[str | None] = mapped_column(String, nullable=True)
    raw_priority: Mapped[str | None] = mapped_column(String, nullable=True)
    is_valid: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


# entity_type -> raw-field-name -> csv-column-name map
_FIELD_MAPS: dict[str, dict[str, str]] = {
    "sales_data": {
        "raw_date": "date",
        "raw_team": "team",
        "raw_sales_amount": "sales_amount",
        "raw_achievement_pct": "achievement_pct",
        "raw_growth_pct": "growth_pct",
    },
    "brand_performance": {
        "raw_external_brand_id": "external_brand_id",
        "raw_brand_name": "brand_name",
        "raw_sales": "sales",
        "raw_rank": "rank",
        "raw_growth_pct": "growth_pct",
    },
    "doctors": {
        "raw_external_doctor_id": "external_doctor_id",
        "raw_name": "name",
        "raw_territory": "territory",
        "raw_priority": "priority",
    },
}

_StagingModel = StagingSalesDataModel | StagingBrandPerformanceModel | StagingDoctorsModel


def _model_for(entity_type: str) -> type[_StagingModel]:
    # A union of the three concrete model classes (rather than a bare
    # `type`) so attribute access below (`.import_run_id`, `.sequence`,
    # `.__table__`) is still statically checked — all three declare the
    # same columns, so mypy can resolve them across the union.
    if entity_type == "sales_data":
        return StagingSalesDataModel
    if entity_type == "brand_performance":
        return StagingBrandPerformanceModel
    if entity_type == "doctors":
        return StagingDoctorsModel
    raise ValueError(f"unknown entity_type: {entity_type!r}")


class SqlAlchemyStagingRepository(StagingRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def stage(
        self, import_run_id: uuid.UUID, entity_type: str, raw_rows: list[dict[str, str | None]]
    ) -> None:
        model = _model_for(entity_type)
        field_map = _FIELD_MAPS[entity_type]
        now = datetime.now(UTC)
        for sequence, raw_row in enumerate(raw_rows):
            kwargs = {
                raw_field: raw_row.get(csv_column) for raw_field, csv_column in field_map.items()
            }
            self._session.add(
                model(
                    id=uuid.uuid4(),
                    import_run_id=import_run_id,
                    sequence=sequence,
                    created_at=now,
                    **kwargs,
                )
            )

    async def fetch_staged(
        self, import_run_id: uuid.UUID, entity_type: str
    ) -> list[tuple[int, dict[str, str | None]]]:
        model = _model_for(entity_type)
        field_map = _FIELD_MAPS[entity_type]
        stmt = (
            select(model)
            .where(model.import_run_id == import_run_id)
            .order_by(model.sequence)
        )
        result = await self._session.execute(stmt)
        rows = result.scalars().all()
        return [
            (
                getattr(row, "sequence"),  # noqa: B009 — see model union typing note in _model_for
                {
                    csv_column: getattr(row, raw_field)
                    for raw_field, csv_column in field_map.items()
                },
            )
            for row in rows
        ]

    async def mark_validated(
        self,
        import_run_id: uuid.UUID,
        entity_type: str,
        results: list[tuple[int, bool, str | None]],
    ) -> None:
        if not results:
            return
        model = _model_for(entity_type)
        # Core Table-level update (not the ORM-enabled `update(model)`,
        # which — given a list of parameter dicts — triggers SQLAlchemy's
        # "ORM Bulk UPDATE by Primary Key" convention and then demands each
        # dict carry the row's PK instead of matching by our own WHERE
        # criteria). A single bulk UPDATE (executemany-style, one round
        # trip) rather than one UPDATE per row in a Python loop — a batch of
        # a few thousand rows would otherwise mean a few thousand sequential
        # round trips purely for this write-back step.
        stmt = (
            # `__table__` is declared as the wider `FromClause` in
            # SQLAlchemy's stubs, but every mapped class's `__table__` is
            # concretely a `Table` — the `update(MappedClass)` form is
            # deliberately avoided instead of cast away here, since it
            # triggers SQLAlchemy's ORM "Bulk UPDATE by Primary Key"
            # convention when executed with a list of parameter dicts,
            # which demands the PK in every dict instead of matching by our
            # own WHERE criteria.
            update(cast(Table, model.__table__))
            .where(model.import_run_id == bindparam("b_import_run_id"))
            .where(model.sequence == bindparam("b_sequence"))
            .values(
                is_valid=bindparam("b_is_valid"),
                rejection_reason=bindparam("b_rejection_reason"),
            )
        )
        params = [
            {
                "b_import_run_id": import_run_id,
                "b_sequence": sequence,
                "b_is_valid": is_valid,
                "b_rejection_reason": rejection_reason,
            }
            for sequence, is_valid, rejection_reason in results
        ]
        await self._session.execute(stmt, params)
