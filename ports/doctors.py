"""Repository interface for ``Doctor`` persistence.

``Any``-typed per ``ports/users.py``'s pattern — the row payload is
domain-shaped, so ``ports`` can't import ``domain.models`` directly (the
import-linter contract forbids ``ports`` -> ``domain``).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class DoctorRepository(ABC):
    @abstractmethod
    async def upsert_many(self, rows: list[Any]) -> None: ...

    @abstractmethod
    async def list_all(self) -> list[Any]:
        """All current Doctor rows (current-snapshot table, not a time
        series — same shape as BrandPerformance). Ordered by territory
        ascending, then priority ascending. Empty list when the table
        has never been populated, never None."""
        ...
