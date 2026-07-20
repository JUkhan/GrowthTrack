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

        # Serializes concurrent removals (code review of Story 3.1, closing
        # the race flagged in Story 1.3's review): without this, two
        # concurrent deactivate requests against two different
        # Administrators, with exactly 2 active, could both read count == 2
        # and both pass, leaving zero active Administrators. Transaction-
        # scoped — releases automatically on commit/rollback, so the second
        # caller blocks here until the first's deactivate() has committed
        # and sees the decremented count.
        await self._users.acquire_administrator_removal_lock()

        count = await self._users.count_active_administrators()
        if count <= 1:
            raise LastAdministratorError()
