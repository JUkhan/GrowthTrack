"""Repository interface for ``BrandPerformance`` persistence.

``Any``-typed per ``ports/users.py``'s pattern — the row payload is
domain-shaped, so ``ports`` can't import ``domain.models`` directly (the
import-linter contract forbids ``ports`` -> ``domain``).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BrandPerformanceRepository(ABC):
    @abstractmethod
    async def upsert_many(self, rows: list[Any]) -> None: ...

    @abstractmethod
    async def list_all(self) -> list[Any]:
        """All current BrandPerformance rows (the table is a current-snapshot,
        not a time series — Story 2.1's Dev Notes). Ordered by rank ascending.
        Empty list when the table has never been populated, never None."""
        ...
