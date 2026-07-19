"""Repository interface for ``Team`` persistence.

Primitive-typed per ``ports/sessions.py``'s style — a team is just a name,
no domain entity import needed here.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod


class TeamRepository(ABC):
    @abstractmethod
    async def get_or_create_by_name(self, name: str) -> uuid.UUID: ...
