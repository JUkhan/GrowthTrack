"""Repository interface for ``RecipientList`` persistence.

``Any``-typed convention (``ports/teams.py``'s style) — ports cannot import
``domain`` (AD-1: dependency direction is inward only).
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from typing import Any


class RecipientListRepository(ABC):
    @abstractmethod
    async def get_by_id(self, recipient_list_id: uuid.UUID) -> Any: ...

    @abstractmethod
    async def get_by_name(self, name: str) -> Any: ...

    @abstractmethod
    async def add(self, recipient_list_id: uuid.UUID, name: str, kind: Any) -> None: ...

    @abstractmethod
    async def list_all_full(self) -> list[Any]:
        """Full RecipientList rows (id, name, kind, status, version,
        member_user_ids), all statuses, all kinds — the Recipients
        Groups/Channels tabs filter by kind client-side, same "never
        hide rows" convention as GET /users, /teams."""
        ...

    @abstractmethod
    async def update_details(self, recipient_list_id: uuid.UUID, name: str, kind: Any) -> None: ...

    @abstractmethod
    async def deactivate(self, recipient_list_id: uuid.UUID) -> None: ...

    @abstractmethod
    async def replace_members(
        self, recipient_list_id: uuid.UUID, user_ids: list[uuid.UUID]
    ) -> None:
        """Full-replace semantics: delete every existing membership row
        for this list, then insert the given set — matches the form's
        save-the-whole-picker-selection UX; there is no incremental
        add-one/remove-one endpoint in this story."""
        ...

    @abstractmethod
    async def get_member_user_ids(self, recipient_list_id: uuid.UUID) -> list[uuid.UUID]: ...
