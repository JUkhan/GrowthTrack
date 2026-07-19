"""Inbound port ``adapters/source_system/`` implements (AD-6: "Source System
ingestion is a contract, not a system").

Returns raw string-keyed dicts (not domain types — same import-linter
constraint as the other ``ports`` modules), grouped by entity type, so the
domain layer stays the one place that parses/validates.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class SourceSystemImporter(ABC):
    @abstractmethod
    async def fetch_batch(self) -> dict[str, list[dict[str, str | None]]]:
        """Returns {"sales_data": [...], "brand_performance": [...],
        "doctors": [...]}, each a list of raw string-valued rows."""
        ...
