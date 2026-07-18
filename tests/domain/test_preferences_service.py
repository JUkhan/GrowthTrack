import uuid

from domain.models import ThemePreference
from domain.preferences import UserPreferenceService


class FakeUserRepository:
    def __init__(self) -> None:
        self.update_theme_preference_calls: list[tuple[uuid.UUID, str]] = []

    async def update_theme_preference(self, user_id: uuid.UUID, theme_preference: str) -> None:
        self.update_theme_preference_calls.append((user_id, theme_preference))


async def test_update_theme_preference_delegates_to_the_repository_with_the_raw_value():
    users = FakeUserRepository()
    service = UserPreferenceService(users)
    user_id = uuid.uuid4()

    await service.update_theme_preference(user_id, ThemePreference.DARK)

    assert users.update_theme_preference_calls == [(user_id, "dark")]
