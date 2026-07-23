"""Repository interface for ``ReportSchedule`` persistence (Story 4.4, AD-11).

``Any``-typed convention (``ports/notifications.py``'s style) — ports cannot
import ``domain`` (AD-1: dependency direction is inward only).
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any


class ReportScheduleRepository(ABC):
    @abstractmethod
    async def get(self) -> Any:
        """The singleton row — always present after the seed migration runs,
        so the return type is not ``Any | None``."""
        ...

    @abstractmethod
    async def update(
        self,
        send_hour_utc: int,
        send_minute_utc: int,
        updated_by_user_id: uuid.UUID,
        updated_at: datetime,
    ) -> Any:
        """Updates the singleton row and returns the updated ``ReportSchedule``
        entity directly (unlike ``MessageTemplateRepository.update()``, which
        returns a bare ``bool`` and leaves the re-fetch to the domain
        service) — there is no meaningful "not found" case for a singleton
        to distinguish via a ``bool``."""
        ...
