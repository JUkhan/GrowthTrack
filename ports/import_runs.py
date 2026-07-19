"""Repository interface for ``ImportRun`` persistence.

Primitive-typed per ``ports/sessions.py``'s style — no domain entity import
needed here.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import datetime


class ImportRunRepository(ABC):
    @abstractmethod
    async def try_acquire_lock(self) -> bool:
        """Non-blocking advisory lock scoped to the nightly import job —
        the same transaction-scoped-lock precedent as
        ``UserRepository.acquire_bootstrap_lock``, but non-blocking: a
        second overlapping run (e.g. a scheduler restart re-firing
        mid-import) must skip immediately rather than queue behind the
        first. Returns True if the lock was acquired, False if another run
        already holds it."""
        ...

    @abstractmethod
    async def start(self, correlation_id: uuid.UUID, started_at: datetime) -> uuid.UUID: ...

    @abstractmethod
    async def mark_succeeded(
        self,
        run_id: uuid.UUID,
        completed_at: datetime,
        records_processed: int,
        records_rejected: int,
    ) -> None: ...

    @abstractmethod
    async def mark_failed(
        self,
        run_id: uuid.UUID,
        correlation_id: uuid.UUID,
        started_at: datetime,
        completed_at: datetime,
    ) -> None:
        """``correlation_id``/``started_at`` are the same values passed to
        ``start()`` for this run. A DB-level error earlier in the pipeline
        (e.g. an upsert conflict) can poison the session's transaction, so
        implementations must be able to recover and durably record the
        failure even though the row ``start()`` added was never committed
        and is lost to that recovery — the caller-supplied values let the
        implementation reconstruct a complete row from scratch."""
        ...
