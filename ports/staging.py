"""Repository interface for the ingestion staging layer (AD-6).

Row identity across ``stage``/``fetch_staged``/``mark_validated`` is a
0-based ``sequence`` int assigned by ``stage()`` in list order — not the
row's UUID PK (unordered per the Consistency Conventions' UUIDv4-ids rule)
and not ``created_at`` (can collide within one bulk-insert transaction).
This is the stable key the three methods key on.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod


class StagingRepository(ABC):
    @abstractmethod
    async def stage(
        self, import_run_id: uuid.UUID, entity_type: str, raw_rows: list[dict[str, str | None]]
    ) -> None:
        """Assigns each row a 0-based `sequence` in list order — the stable
        identity fetch_staged/mark_validated key on."""
        ...

    @abstractmethod
    async def fetch_staged(
        self, import_run_id: uuid.UUID, entity_type: str
    ) -> list[tuple[int, dict[str, str | None]]]:
        """Returns (sequence, raw_row) pairs ordered by sequence."""
        ...

    @abstractmethod
    async def mark_validated(
        self,
        import_run_id: uuid.UUID,
        entity_type: str,
        results: list[tuple[int, bool, str | None]],
    ) -> None:
        """results: (sequence, is_valid, rejection_reason) — sequence matches
        the value `stage` assigned, not a list position."""
        ...
