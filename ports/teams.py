"""Repository interface for ``Team`` persistence.

Primitive-typed per ``ports/sessions.py``'s style — a team is just a name,
no domain entity import needed here.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from typing import Any


class TeamRepository(ABC):
    @abstractmethod
    async def get_or_create_by_name(self, name: str) -> uuid.UUID: ...

    @abstractmethod
    async def list_all(self) -> list[tuple[uuid.UUID, str]]:
        """(id, name) pairs only — Story 2.2's Dashboard team-performance
        section (``domain/metrics.py#DashboardMetricsService``) depends on
        this exact shape. Do not change its signature or filter it to
        active-only teams; use ``list_all_full`` for the Recipients
        directory's own needs instead (Story 3.1)."""
        ...

    @abstractmethod
    async def add(self, team_id: uuid.UUID, name: str) -> None: ...

    @abstractmethod
    async def get_by_id(self, team_id: uuid.UUID) -> Any: ...

    @abstractmethod
    async def get_by_name(self, name: str) -> Any: ...

    @abstractmethod
    async def list_all_full(self) -> list[Any]:
        """Full ``Team`` rows (id, name, status, version), all statuses —
        the Recipients Teams grid's own read, separate from ``list_all``."""
        ...

    @abstractmethod
    async def update_name(self, team_id: uuid.UUID, name: str) -> None: ...

    @abstractmethod
    async def deactivate(self, team_id: uuid.UUID) -> None: ...
