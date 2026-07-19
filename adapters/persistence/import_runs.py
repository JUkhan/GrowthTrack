"""SQLAlchemy ``ImportRun`` model + repository implementation.

Backs the Dashboard's "Data as of HH:MM" badge (Story 2.2) — records each
nightly import's completion timestamp. `status`/`records_processed`/
`records_rejected` are plain INSERT/UPDATE ... WHERE id, no upsert
semantics needed (each run is its own new row).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, select, text, update
from sqlalchemy.dialects.postgresql import UUID, insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from adapters.persistence.advisory_locks import NIGHTLY_IMPORT_LOCK_KEY
from adapters.persistence.database import Base
from domain.models import ImportRunStatus
from ports.import_runs import ImportRunRepository


class ImportRunModel(Base):
    __tablename__ = "import_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    correlation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    records_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_rejected: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class SqlAlchemyImportRunRepository(ImportRunRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def try_acquire_lock(self) -> bool:
        # pg_try_advisory_xact_lock is non-blocking (unlike
        # pg_advisory_xact_lock): it returns immediately with the outcome
        # rather than queueing, which is what lets a second overlapping run
        # skip instead of hang. Transaction-scoped: releases automatically
        # on commit/rollback — this is why the lock is held for exactly as
        # long as the pipeline's single uncommitted transaction is open,
        # with no separate release call needed.
        result = await self._session.execute(
            text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": NIGHTLY_IMPORT_LOCK_KEY}
        )
        return bool(result.scalar())

    async def start(self, correlation_id: uuid.UUID, started_at: datetime) -> uuid.UUID:
        run_id = uuid.uuid4()
        self._session.add(
            ImportRunModel(
                id=run_id,
                correlation_id=correlation_id,
                started_at=started_at,
                status=ImportRunStatus.RUNNING.value,
            )
        )
        return run_id

    async def mark_succeeded(
        self,
        run_id: uuid.UUID,
        completed_at: datetime,
        records_processed: int,
        records_rejected: int,
    ) -> None:
        stmt = (
            update(ImportRunModel)
            .where(ImportRunModel.id == run_id)
            .values(
                status=ImportRunStatus.SUCCEEDED.value,
                completed_at=completed_at,
                records_processed=records_processed,
                records_rejected=records_rejected,
            )
        )
        await self._session.execute(stmt)

    async def mark_failed(
        self,
        run_id: uuid.UUID,
        correlation_id: uuid.UUID,
        started_at: datetime,
        completed_at: datetime,
    ) -> None:
        # A DB-level error earlier in the pipeline (e.g. an upsert conflict)
        # can leave this session's transaction aborted — any further
        # statement on it raises until it's rolled back. Roll back first so
        # this write can run at all. That discards start()'s still-uncommitted
        # RUNNING row (and every other write from this run's pipeline, which
        # is the right outcome: a failed run should never leave partial data
        # committed). Upsert (not a plain INSERT) so this is safe whether the
        # row was just discarded by the rollback above (most runs) or, in
        # some other caller's flow, already durably committed. Committed
        # immediately and independently of the scheduler's own final commit,
        # so a failure is durably recorded even if nothing else about this
        # run ever gets committed.
        await self._session.rollback()
        stmt = insert(ImportRunModel).values(
            id=run_id,
            correlation_id=correlation_id,
            started_at=started_at,
            status=ImportRunStatus.FAILED.value,
            completed_at=completed_at,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={"status": stmt.excluded.status, "completed_at": stmt.excluded.completed_at},
        )
        await self._session.execute(stmt)
        await self._session.commit()

    async def get_last_successful_completed_at(self) -> datetime | None:
        stmt = (
            select(ImportRunModel.completed_at)
            .where(ImportRunModel.status == ImportRunStatus.SUCCEEDED.value)
            .order_by(ImportRunModel.completed_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
