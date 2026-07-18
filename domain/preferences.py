"""Per-Administrator UI preferences (AD-11).

No audit write here — AD-7/FR-12 enumerate the audited action set
(directory CRUD, opt-in/out, Daily Report schedule changes, logins) and a
personal display preference isn't in it.
"""

from __future__ import annotations

import uuid

from domain.models import ThemePreference
from ports.users import UserRepository


class UserPreferenceService:
    def __init__(self, users: UserRepository) -> None:
        self._users = users

    async def update_theme_preference(
        self, user_id: uuid.UUID, theme_preference: ThemePreference
    ) -> None:
        await self._users.update_theme_preference(user_id, theme_preference.value)
