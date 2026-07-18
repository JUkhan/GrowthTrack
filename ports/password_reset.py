"""Repository interface for ``PasswordResetToken`` persistence (AD-11).

Signatures use ``Any`` for the entity type rather than importing
``domain.models.PasswordResetToken`` directly — matches ``ports/users.py``'s
import-linter-driven convention (``ports`` may not depend on ``domain``).
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any


class PasswordResetTokenRepository(ABC):
    @abstractmethod
    async def add(self, token: Any) -> None: ...

    @abstractmethod
    async def get_by_hash(self, token_hash: str) -> Any: ...

    @abstractmethod
    async def mark_used(self, token_id: uuid.UUID, used_at: datetime) -> None: ...
