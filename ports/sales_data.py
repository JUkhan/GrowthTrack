"""Repository interface for ``SalesData`` persistence.

``Any``-typed per ``ports/users.py``'s pattern — the row payload is
domain-shaped, so ``ports`` can't import ``domain.models`` directly (the
import-linter contract forbids ``ports`` -> ``domain``).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from decimal import Decimal
from typing import Any


class SalesDataRepository(ABC):
    @abstractmethod
    async def upsert_many(self, rows: list[Any]) -> None: ...

    @abstractmethod
    async def sum_amount_in_range(self, start_date: date, end_date: date) -> Decimal:
        """Sum of sales_amount across ALL teams for date in [start_date, end_date]
        inclusive. 0 (never None) when no rows match."""
        ...

    @abstractmethod
    async def latest_per_team(self) -> list[Any]:
        """One SalesData-shaped row per team_id — the row with the most recent
        `date` for that team. Teams with zero sales_data rows are simply
        absent (never a fabricated zero row)."""
        ...
