"""Last-Administrator protection (AC #3; FR-2).

Deliberately no caller yet — Epic 3's Story 3.1 builds the deactivate/delete
endpoint that will invoke ``ensure_can_deactivate`` before mutating a User.
"""

from __future__ import annotations

from domain.models import Role, User, UserStatus
from ports.users import UserRepository


class LastAdministratorError(Exception):
    """Raised when a mutation would leave zero active Administrators."""

    def __init__(self) -> None:
        super().__init__(
            "The last remaining Administrator account cannot be deleted or deactivated"
        )


class LastAdministratorGuard:
    def __init__(self, users: UserRepository) -> None:
        self._users = users

    async def ensure_can_deactivate(self, target: User) -> None:
        if target.role != Role.ADMINISTRATOR or target.status != UserStatus.ACTIVE:
            return

        count = await self._users.count_active_administrators()
        if count <= 1:
            raise LastAdministratorError()
