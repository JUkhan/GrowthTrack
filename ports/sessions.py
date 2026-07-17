"""Repository interface for JWT revocation records (AD-8: revocation keyed
by the JWT's ``jti``).

Unlike ``ports/users.py``/``ports/audit.py``, this uses ``uuid.UUID``/
``datetime`` directly in the signatures rather than ``Any`` — a revocation
record is just a ``(jti, revoked_at)`` pair, with no domain entity to avoid
importing.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import datetime


class RevokedTokenRepository(ABC):
    @abstractmethod
    async def revoke(self, jti: uuid.UUID, revoked_at: datetime) -> None: ...

    @abstractmethod
    async def is_revoked(self, jti: uuid.UUID) -> bool: ...
