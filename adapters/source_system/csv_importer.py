"""CSV file-drop implementation of ``SourceSystemImporter`` (AD-6).

Phase-1 default transport — reads three fixed-name CSV files from a
configured directory. When the real Source System is identified, only
this adapter is expected to change (AD-6: "Source System ingestion is a
contract, not a system").

Read-only by construction (PRD §5 Non-Goals: no bidirectional sync, no
writing back to source systems) — this adapter never deletes/moves/
modifies the source files.
"""

from __future__ import annotations

import csv
import logging
import pathlib

from ports.source_system import SourceSystemImporter

logger = logging.getLogger(__name__)

_FILENAMES = {
    "sales_data": "sales_data.csv",
    "brand_performance": "brand_performance.csv",
    "doctors": "doctors.csv",
}


class CsvFileSourceSystemImporter(SourceSystemImporter):
    def __init__(self, import_dir: str) -> None:
        self._import_dir = pathlib.Path(import_dir)

    async def fetch_batch(self) -> dict[str, list[dict[str, str | None]]]:
        return {
            entity_type: self._read_csv(filename)
            for entity_type, filename in _FILENAMES.items()
        }

    def _read_csv(self, filename: str) -> list[dict[str, str | None]]:
        path = self._import_dir / filename
        if not path.is_file():
            # A missing file is not itself a validation failure at this
            # layer — the domain service decides whether zero records for
            # an expected entity type is worth a WARN log line.
            logger.warning("source system file not found: %s", path)
            return []

        # utf-8-sig transparently strips a leading BOM if present (common
        # from Excel/Windows exports) and behaves exactly like utf-8 when
        # there isn't one — without it, a BOM'd file's first header name
        # comes through as "﻿date" and every row fails validation with
        # a misleading "date is required".
        with path.open(newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            fieldnames = list(reader.fieldnames or [])
            duplicates = {name for name in fieldnames if fieldnames.count(name) > 1}
            if duplicates:
                logger.warning(
                    "source system file has duplicate header column(s), "
                    "later columns overwrite earlier ones: %s (%s)",
                    sorted(duplicates),
                    path,
                )
            return [dict(row) for row in reader]
