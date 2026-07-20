"""Repository interface for ``User`` persistence.

Signatures use ``Any`` for the entity type rather than importing
``domain.models.User`` directly — the import-linter contract forbids
``ports`` from depending on ``domain`` (dependency direction is inward
only, AD-1: ``domain`` depends on ``ports``, never the reverse). Concrete
implementations (``adapters/persistence``) import the real ``User`` type.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any


class UserRepository(ABC):
    @abstractmethod
    async def get_by_username(self, username: str) -> Any: ...

    @abstractmethod
    async def get_by_id(self, user_id: uuid.UUID) -> Any: ...

    @abstractmethod
    async def add(self, user: Any) -> None: ...

    @abstractmethod
    async def has_any_administrator(self) -> bool: ...

    @abstractmethod
    async def count_active_administrators(self) -> int: ...

    @abstractmethod
    async def acquire_bootstrap_lock(self) -> None: ...

    @abstractmethod
    async def acquire_administrator_removal_lock(self) -> None:
        """Transaction-scoped advisory lock serializing concurrent
        Administrator deactivate/delete requests — closes the TOCTOU race
        flagged in Story 1.3's code review (two concurrent removals of two
        different Administrators, both reading the same active-count before
        either commits, could otherwise leave zero active Administrators)."""
        ...

    @abstractmethod
    async def increment_failed_login_count(self, user_id: uuid.UUID) -> int: ...

    @abstractmethod
    async def lock_until(self, user_id: uuid.UUID, until: datetime) -> None: ...

    @abstractmethod
    async def clear_lockout(self, user_id: uuid.UUID) -> None: ...

    @abstractmethod
    async def update_password(self, user_id: uuid.UUID, hashed_password: str) -> None: ...

    @abstractmethod
    async def update_theme_preference(self, user_id: uuid.UUID, theme_preference: str) -> None: ...

    @abstractmethod
    async def get_by_mobile(self, mobile: str) -> Any: ...

    @abstractmethod
    async def list_all(self) -> list[Any]:
        """ALL roles, ALL statuses — the Recipients directory (Story 3.1)
        lists Administrators alongside Sales User/Manager rows so the
        last-Administrator guard has something to protect on removal, and
        never hides inactive rows (data-table convention: show, don't
        silently drop)."""
        ...

    @abstractmethod
    async def update_directory_fields(
        self, user_id: uuid.UUID, name: str, mobile: str, team_id: uuid.UUID
    ) -> None: ...

    @abstractmethod
    async def deactivate(self, user_id: uuid.UUID) -> None: ...
