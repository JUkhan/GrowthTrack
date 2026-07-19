"""Repository interface for ``SalesData`` persistence.

``Any``-typed per ``ports/users.py``'s pattern — the row payload is
domain-shaped, so ``ports`` can't import ``domain.models`` directly (the
import-linter contract forbids ``ports`` -> ``domain``).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class SalesDataRepository(ABC):
    @abstractmethod
    async def upsert_many(self, rows: list[Any]) -> None: ...
