import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from adapters.persistence.database import create_session_factory
from adapters.persistence.teams import SqlAlchemyTeamRepository
from adapters.persistence.users import SqlAlchemyUserRepository
from domain.models import Role, ThemePreference, User, UserStatus


async def _seed_directory_user(
    name: str, mobile: str, team_id: uuid.UUID, role: Role = Role.SALES_USER
) -> User:
    """Seeds a Sales User/Manager row directly through the repository — no
    username/hashed_password, unlike the `seed_user` fixture, which only
    ever builds Administrator-shaped rows."""
    session_factory = create_session_factory()
    user = User(
        id=uuid.uuid4(),
        username=None,
        hashed_password=None,
        role=role,
        status=UserStatus.ACTIVE,
        version=1,
        created_at=datetime.now(UTC),
        name=name,
        mobile=mobile,
        team_id=team_id,
    )
    async with session_factory() as session:
        await SqlAlchemyUserRepository(session).add(user)
        await session.commit()
    return user


async def _seed_team(name: str) -> uuid.UUID:
    session_factory = create_session_factory()
    async with session_factory() as session:
        team_id = await SqlAlchemyTeamRepository(session).get_or_create_by_name(name)
        await session.commit()
    return team_id


async def _count_active_administrators() -> int:
    session_factory = create_session_factory()
    async with session_factory() as session:
        return await SqlAlchemyUserRepository(session).count_active_administrators()


async def test_count_active_administrators_is_zero_on_an_empty_table():
    assert await _count_active_administrators() == 0


async def test_count_active_administrators_is_one_after_seeding_one_active_administrator(
    seed_user,
):
    await seed_user(username="admin")

    assert await _count_active_administrators() == 1


async def test_count_active_administrators_is_two_after_seeding_a_second(seed_user):
    await seed_user(username="admin")
    await seed_user(username="admin2")

    assert await _count_active_administrators() == 2


async def test_count_active_administrators_excludes_non_administrators_and_inactive_administrators(
    seed_user,
):
    await seed_user(username="admin")
    await seed_user(username="sales", role=Role.SALES_USER)
    await seed_user(username="inactive-admin", status=UserStatus.INACTIVE)

    assert await _count_active_administrators() == 1


async def test_increment_failed_login_count_returns_the_running_total(seed_user):
    user, _ = await seed_user(username="admin")
    session_factory = create_session_factory()

    async with session_factory() as session:
        repo = SqlAlchemyUserRepository(session)
        first = await repo.increment_failed_login_count(user.id)
        second = await repo.increment_failed_login_count(user.id)
        third = await repo.increment_failed_login_count(user.id)
        await session.commit()

    assert (first, second, third) == (1, 2, 3)


async def test_increment_failed_login_count_is_atomic_under_concurrent_increments(seed_user):
    user, _ = await seed_user(username="admin")
    session_factory = create_session_factory()

    async def _increment() -> None:
        async with session_factory() as session:
            await SqlAlchemyUserRepository(session).increment_failed_login_count(user.id)
            await session.commit()

    await asyncio.gather(_increment(), _increment())

    async with session_factory() as session:
        final = await SqlAlchemyUserRepository(session).get_by_id(user.id)

    assert final.failed_login_count == 2


async def test_lock_until_and_clear_lockout_round_trip(seed_user):
    user, _ = await seed_user(username="admin")
    session_factory = create_session_factory()
    until = datetime.now(UTC) + timedelta(minutes=15)

    async with session_factory() as session:
        repo = SqlAlchemyUserRepository(session)
        await repo.increment_failed_login_count(user.id)
        await repo.lock_until(user.id, until)
        await session.commit()

    async with session_factory() as session:
        locked = await SqlAlchemyUserRepository(session).get_by_id(user.id)
    assert locked.locked_until is not None
    assert locked.failed_login_count == 1

    async with session_factory() as session:
        await SqlAlchemyUserRepository(session).clear_lockout(user.id)
        await session.commit()

    async with session_factory() as session:
        cleared = await SqlAlchemyUserRepository(session).get_by_id(user.id)
    assert cleared.locked_until is None
    assert cleared.failed_login_count == 0


async def test_update_password_persists_the_new_hash_and_increments_version(seed_user):
    user, _ = await seed_user(username="admin")
    session_factory = create_session_factory()

    async with session_factory() as session:
        await SqlAlchemyUserRepository(session).update_password(user.id, "a-new-hash")
        await session.commit()

    async with session_factory() as session:
        updated = await SqlAlchemyUserRepository(session).get_by_id(user.id)

    assert updated.hashed_password == "a-new-hash"
    assert updated.version == user.version + 1


async def test_new_user_defaults_to_system_theme_preference(seed_user):
    user, _ = await seed_user(username="admin")

    assert user.theme_preference == ThemePreference.SYSTEM


async def test_update_theme_preference_persists_the_new_value(seed_user):
    user, _ = await seed_user(username="admin")
    session_factory = create_session_factory()

    async with session_factory() as session:
        await SqlAlchemyUserRepository(session).update_theme_preference(
            user.id, ThemePreference.DARK.value
        )
        await session.commit()

    async with session_factory() as session:
        updated = await SqlAlchemyUserRepository(session).get_by_id(user.id)

    assert updated.theme_preference == ThemePreference.DARK


async def test_get_by_mobile_returns_the_matching_user(seed_user):
    team_id = await _seed_team("North Zone")
    seeded = await _seed_directory_user("Karim", "+8801700000101", team_id)
    session_factory = create_session_factory()

    async with session_factory() as session:
        found = await SqlAlchemyUserRepository(session).get_by_mobile("+8801700000101")

    assert found is not None
    assert found.id == seeded.id
    assert found.name == "Karim"


async def test_get_by_mobile_returns_none_for_a_deactivated_users_mobile(seed_user):
    # Active-only (code review of Story 3.1): a soft-deleted User's mobile
    # is reusable, matching ix_users_mobile_active_uq.
    team_id = await _seed_team("North Zone")
    seeded = await _seed_directory_user("Karim", "+8801700000103", team_id)
    session_factory = create_session_factory()

    async with session_factory() as session:
        await SqlAlchemyUserRepository(session).deactivate(seeded.id)
        await session.commit()

    async with session_factory() as session:
        found = await SqlAlchemyUserRepository(session).get_by_mobile("+8801700000103")

    assert found is None


async def test_get_by_mobile_returns_none_when_no_user_has_that_mobile(seed_user):
    session_factory = create_session_factory()

    async with session_factory() as session:
        found = await SqlAlchemyUserRepository(session).get_by_mobile("+8801700000999")

    assert found is None


async def test_list_all_includes_administrators_and_sales_users_of_every_status(seed_user):
    team_id = await _seed_team("North Zone")
    await seed_user(username="admin")
    await _seed_directory_user("Karim", "+8801700000102", team_id)
    session_factory = create_session_factory()

    async with session_factory() as session:
        repo = SqlAlchemyUserRepository(session)
        directory_user = await repo.get_by_mobile("+8801700000102")
        await repo.deactivate(directory_user.id)
        await session.commit()

    async with session_factory() as session:
        all_users = await SqlAlchemyUserRepository(session).list_all()

    roles = {u.role for u in all_users}
    statuses = {u.status for u in all_users}
    assert Role.ADMINISTRATOR in roles
    assert Role.SALES_USER in roles
    assert UserStatus.INACTIVE in statuses


async def test_list_all_returns_empty_list_when_table_is_empty():
    session_factory = create_session_factory()

    async with session_factory() as session:
        all_users = await SqlAlchemyUserRepository(session).list_all()

    assert all_users == []


async def test_update_directory_fields_persists_changes_and_increments_version(seed_user):
    team_id = await _seed_team("North Zone")
    other_team_id = await _seed_team("South Zone")
    seeded = await _seed_directory_user("Karim", "+8801700000103", team_id)
    session_factory = create_session_factory()

    async with session_factory() as session:
        result = await SqlAlchemyUserRepository(session).update_directory_fields(
            seeded.id, "Karim Updated", "+8801700000104", other_team_id, seeded.version
        )
        await session.commit()

    assert result is True

    async with session_factory() as session:
        updated = await SqlAlchemyUserRepository(session).get_by_id(seeded.id)

    assert updated.name == "Karim Updated"
    assert updated.mobile == "+8801700000104"
    assert updated.team_id == other_team_id
    assert updated.version == seeded.version + 1


async def test_update_directory_fields_with_a_stale_version_returns_false_and_leaves_row_unchanged(
    seed_user,
):
    team_id = await _seed_team("North Zone")
    seeded = await _seed_directory_user("Karim", "+8801700000110", team_id)
    session_factory = create_session_factory()

    async with session_factory() as session:
        result = await SqlAlchemyUserRepository(session).update_directory_fields(
            seeded.id, "Karim Updated", "+8801700000111", team_id, seeded.version - 1
        )
        await session.commit()

    assert result is False

    async with session_factory() as session:
        unchanged = await SqlAlchemyUserRepository(session).get_by_id(seeded.id)

    assert unchanged.name == "Karim"
    assert unchanged.mobile == "+8801700000110"
    assert unchanged.version == seeded.version


async def test_update_directory_fields_called_twice_with_the_same_version_second_call_returns_false(
    seed_user,
):
    team_id = await _seed_team("North Zone")
    seeded = await _seed_directory_user("Karim", "+8801700000112", team_id)
    session_factory = create_session_factory()

    async with session_factory() as session:
        repo = SqlAlchemyUserRepository(session)
        first_result = await repo.update_directory_fields(
            seeded.id, "First Update", "+8801700000113", team_id, seeded.version
        )
        second_result = await repo.update_directory_fields(
            seeded.id, "Second Update", "+8801700000114", team_id, seeded.version
        )
        await session.commit()

    assert first_result is True
    assert second_result is False

    async with session_factory() as session:
        final = await SqlAlchemyUserRepository(session).get_by_id(seeded.id)

    assert final.name == "First Update"
    assert final.mobile == "+8801700000113"
    assert final.version == seeded.version + 1


async def test_deactivate_flips_status_and_increments_version(seed_user):
    team_id = await _seed_team("North Zone")
    seeded = await _seed_directory_user("Karim", "+8801700000105", team_id)
    session_factory = create_session_factory()

    async with session_factory() as session:
        await SqlAlchemyUserRepository(session).deactivate(seeded.id)
        await session.commit()

    async with session_factory() as session:
        deactivated = await SqlAlchemyUserRepository(session).get_by_id(seeded.id)

    assert deactivated.status == UserStatus.INACTIVE
    assert deactivated.version == seeded.version + 1


async def test_get_many_by_ids_returns_the_matching_subset():
    team_id = await _seed_team("North Zone")
    first = await _seed_directory_user("Karim", "+8801700000106", team_id)
    second = await _seed_directory_user("Rahim", "+8801700000107", team_id)
    await _seed_directory_user("Not Included", "+8801700000108", team_id)
    session_factory = create_session_factory()

    async with session_factory() as session:
        found = await SqlAlchemyUserRepository(session).get_many_by_ids([first.id, second.id])

    assert {u.id for u in found} == {first.id, second.id}


async def test_get_many_by_ids_with_empty_input_returns_empty_list_without_querying():
    session_factory = create_session_factory()

    async with session_factory() as session:
        found = await SqlAlchemyUserRepository(session).get_many_by_ids([])

    assert found == []


async def test_get_many_by_ids_with_a_mix_of_found_and_unknown_ids_returns_only_found():
    team_id = await _seed_team("North Zone")
    seeded = await _seed_directory_user("Karim", "+8801700000109", team_id)
    session_factory = create_session_factory()

    async with session_factory() as session:
        found = await SqlAlchemyUserRepository(session).get_many_by_ids([seeded.id, uuid.uuid4()])

    assert [u.id for u in found] == [seeded.id]
