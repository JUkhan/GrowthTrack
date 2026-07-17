"""Repository interface for ``AuditLogEntry`` persistence (AD-7: co-transactional audit writes).

Generic on purpose — Epic 3/4 mutations reuse this exact interface with
different ``action``/``entity_type`` values, not a login-specific one.

Uses ``Any`` for the entity type rather than importing ``domain.models``
directly — see ``ports/users.py``'s docstring for why.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class AuditLogRepository(ABC):
    @abstractmethod
    async def add(self, entry: Any) -> None: ...
