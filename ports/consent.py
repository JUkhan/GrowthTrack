"""Repository interface for ``OptInConsent`` persistence.

``Any``-typed convention (``ports/recipient_lists.py``'s style) — ports
cannot import ``domain`` (AD-1: dependency direction is inward only).
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from typing import Any


class OptInConsentRepository(ABC):
    @abstractmethod
    async def get_active(self, user_id: uuid.UUID) -> Any | None: ...

    @abstractmethod
    async def get_active_by_user_ids(self, user_ids: list[uuid.UUID]) -> dict[uuid.UUID, Any]:
        """Batched active-consent lookup keyed by user_id — avoids the
        N+1 shape Story 3.2's RecipientList.list_all_full() was written
        to avoid for membership. Used by GET /users."""
        ...

    @abstractmethod
    async def grant(self, user_id: uuid.UUID, mobile: str) -> Any: ...

    @abstractmethod
    async def revoke_active(self, user_id: uuid.UUID) -> bool:
        """Revokes the current active row, if any (sets revoked_at).
        Returns whether a row was actually revoked, so callers (the
        phone-number-change path in UserDirectoryService.update_user)
        know whether an audit entry is warranted — don't audit a
        no-op."""
        ...
