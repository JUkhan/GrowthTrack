import uuid
from datetime import UTC, datetime

from adapters.persistence.database import create_session_factory
from adapters.persistence.recipient_lists import SqlAlchemyRecipientListRepository
from adapters.persistence.users import SqlAlchemyUserRepository
from domain.models import RecipientListKind, RecipientListStatus, Role, User, UserStatus


async def _seed_user(mobile: str) -> User:
    session_factory = create_session_factory()
    user = User(
        id=uuid.uuid4(),
        username=None,
        hashed_password=None,
        role=Role.SALES_USER,
        status=UserStatus.ACTIVE,
        version=1,
        created_at=datetime.now(UTC),
        name="Karim",
        mobile=mobile,
    )
    async with session_factory() as session:
        await SqlAlchemyUserRepository(session).add(user)
        await session.commit()
    return user


async def _add(name: str, kind: RecipientListKind = RecipientListKind.GROUP) -> uuid.UUID:
    recipient_list_id = uuid.uuid4()
    session_factory = create_session_factory()
    async with session_factory() as session:
        await SqlAlchemyRecipientListRepository(session).add(recipient_list_id, name, kind)
        await session.commit()
    return recipient_list_id


async def test_add_creates_a_recipient_list_with_active_status_and_version_one():
    recipient_list_id = await _add("North Group")

    session_factory = create_session_factory()
    async with session_factory() as session:
        repo = SqlAlchemyRecipientListRepository(session)
        recipient_list = await repo.get_by_id(recipient_list_id)

    assert recipient_list.name == "North Group"
    assert recipient_list.kind == RecipientListKind.GROUP
    assert recipient_list.status == RecipientListStatus.ACTIVE
    assert recipient_list.version == 1
    assert recipient_list.member_user_ids == []


async def test_get_by_id_returns_none_for_an_unknown_id():
    session_factory = create_session_factory()
    async with session_factory() as session:
        recipient_list = await SqlAlchemyRecipientListRepository(session).get_by_id(uuid.uuid4())

    assert recipient_list is None


async def test_get_by_name_returns_the_matching_active_recipient_list():
    recipient_list_id = await _add("West Channel", RecipientListKind.CHANNEL)

    session_factory = create_session_factory()
    async with session_factory() as session:
        found = await SqlAlchemyRecipientListRepository(session).get_by_name("West Channel")

    assert found.id == recipient_list_id


async def test_get_by_name_returns_none_when_no_list_has_that_name():
    session_factory = create_session_factory()
    async with session_factory() as session:
        found = await SqlAlchemyRecipientListRepository(session).get_by_name("Nonexistent")

    assert found is None


async def test_get_by_name_returns_none_for_a_deactivated_lists_name():
    recipient_list_id = await _add("Deactivated Group")
    session_factory = create_session_factory()

    async with session_factory() as session:
        await SqlAlchemyRecipientListRepository(session).deactivate(recipient_list_id)
        await session.commit()

    async with session_factory() as session:
        found = await SqlAlchemyRecipientListRepository(session).get_by_name("Deactivated Group")

    assert found is None


async def test_replace_members_sets_the_membership_and_get_member_user_ids_reflects_it():
    recipient_list_id = await _add("North Group")
    member_one = await _seed_user("+8801700000401")
    member_two = await _seed_user("+8801700000402")
    session_factory = create_session_factory()

    async with session_factory() as session:
        repo = SqlAlchemyRecipientListRepository(session)
        await repo.replace_members(recipient_list_id, [member_one.id, member_two.id])
        await session.commit()

    async with session_factory() as session:
        repo = SqlAlchemyRecipientListRepository(session)
        member_ids = await repo.get_member_user_ids(recipient_list_id)

    assert set(member_ids) == {member_one.id, member_two.id}


async def test_replace_members_with_an_empty_set_clears_all_rows():
    recipient_list_id = await _add("North Group")
    member = await _seed_user("+8801700000403")
    session_factory = create_session_factory()

    async with session_factory() as session:
        repo = SqlAlchemyRecipientListRepository(session)
        await repo.replace_members(recipient_list_id, [member.id])
        await session.commit()

    async with session_factory() as session:
        repo = SqlAlchemyRecipientListRepository(session)
        await repo.replace_members(recipient_list_id, [])
        await session.commit()

    async with session_factory() as session:
        repo = SqlAlchemyRecipientListRepository(session)
        member_ids = await repo.get_member_user_ids(recipient_list_id)

    assert member_ids == []


async def test_replace_members_fully_replaces_not_merges():
    recipient_list_id = await _add("North Group")
    member_one = await _seed_user("+8801700000404")
    member_two = await _seed_user("+8801700000405")
    session_factory = create_session_factory()

    async with session_factory() as session:
        repo = SqlAlchemyRecipientListRepository(session)
        await repo.replace_members(recipient_list_id, [member_one.id])
        await session.commit()

    async with session_factory() as session:
        repo = SqlAlchemyRecipientListRepository(session)
        await repo.replace_members(recipient_list_id, [member_two.id])
        await session.commit()

    async with session_factory() as session:
        repo = SqlAlchemyRecipientListRepository(session)
        member_ids = await repo.get_member_user_ids(recipient_list_id)

    assert member_ids == [member_two.id]


async def test_update_details_persists_name_and_kind_and_increments_version():
    recipient_list_id = await _add("North Group", RecipientListKind.GROUP)
    session_factory = create_session_factory()

    async with session_factory() as session:
        await SqlAlchemyRecipientListRepository(session).update_details(
            recipient_list_id, "North Channel", RecipientListKind.CHANNEL
        )
        await session.commit()

    async with session_factory() as session:
        updated = await SqlAlchemyRecipientListRepository(session).get_by_id(recipient_list_id)

    assert updated.name == "North Channel"
    assert updated.kind == RecipientListKind.CHANNEL
    assert updated.version == 2


async def test_deactivate_flips_status_and_increments_version():
    recipient_list_id = await _add("North Group")
    session_factory = create_session_factory()

    async with session_factory() as session:
        await SqlAlchemyRecipientListRepository(session).deactivate(recipient_list_id)
        await session.commit()

    async with session_factory() as session:
        deactivated = await SqlAlchemyRecipientListRepository(session).get_by_id(recipient_list_id)

    assert deactivated.status == RecipientListStatus.INACTIVE
    assert deactivated.version == 2


async def test_list_all_full_returns_every_list_with_correct_per_list_membership_grouping():
    # This is the test that would catch an N+1-avoidance bug if the
    # grouping logic in list_all_full were wrong — two lists, each with a
    # distinct, non-overlapping membership set.
    north_id = await _add("North Group", RecipientListKind.GROUP)
    south_id = await _add("South Channel", RecipientListKind.CHANNEL)
    north_member = await _seed_user("+8801700000406")
    south_member = await _seed_user("+8801700000407")
    session_factory = create_session_factory()

    async with session_factory() as session:
        repo = SqlAlchemyRecipientListRepository(session)
        await repo.replace_members(north_id, [north_member.id])
        await repo.replace_members(south_id, [south_member.id])
        await session.commit()

    async with session_factory() as session:
        all_lists = await SqlAlchemyRecipientListRepository(session).list_all_full()

    by_id = {rl.id: rl for rl in all_lists}
    assert by_id[north_id].member_user_ids == [north_member.id]
    assert by_id[south_id].member_user_ids == [south_member.id]


async def test_list_all_full_returns_empty_list_when_table_is_empty():
    session_factory = create_session_factory()
    async with session_factory() as session:
        all_lists = await SqlAlchemyRecipientListRepository(session).list_all_full()

    assert all_lists == []
