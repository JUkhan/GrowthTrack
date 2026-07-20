import uuid
from datetime import UTC, datetime

import pytest

from domain.administrators import LastAdministratorError, LastAdministratorGuard
from domain.models import AuditLogEntry, Role, Team, TeamStatus, User, UserStatus
from domain.recipients import (
    CannotEditAdministrator,
    MobileTaken,
    RoleNotAllowed,
    TeamDirectoryService,
    TeamInactive,
    TeamNameTaken,
    TeamNotFound,
    UserDirectoryService,
    UserNotFound,
)


def _make_administrator() -> User:
    return User(
        id=uuid.uuid4(),
        username="admin",
        hashed_password="hashed",
        role=Role.ADMINISTRATOR,
        status=UserStatus.ACTIVE,
        version=1,
        created_at=datetime.now(UTC),
    )


def _make_sales_user(mobile: str = "+8801700000000", team_id: uuid.UUID | None = None) -> User:
    return User(
        id=uuid.uuid4(),
        username=None,
        hashed_password=None,
        role=Role.SALES_USER,
        status=UserStatus.ACTIVE,
        version=1,
        created_at=datetime.now(UTC),
        name="Rahim",
        mobile=mobile,
        team_id=team_id or uuid.uuid4(),
    )


def _make_team(name: str = "North Zone", status: TeamStatus = TeamStatus.ACTIVE) -> Team:
    return Team(id=uuid.uuid4(), name=name, status=status)


class FakeUserRepository:
    def __init__(
        self, users: list[User] | None = None, active_administrator_count: int = 2
    ) -> None:
        self._by_id = {u.id: u for u in (users or [])}
        self._active_administrator_count = active_administrator_count
        self.added: list[User] = []
        self.updated: list[tuple[uuid.UUID, str, str, uuid.UUID]] = []
        self.deactivated: list[uuid.UUID] = []

    async def get_by_mobile(self, mobile: str) -> User | None:
        return next((u for u in self._by_id.values() if u.mobile == mobile), None)

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return self._by_id.get(user_id)

    async def add(self, user: User) -> None:
        self._by_id[user.id] = user
        self.added.append(user)

    async def list_all(self) -> list[User]:
        return list(self._by_id.values())

    async def update_directory_fields(
        self, user_id: uuid.UUID, name: str, mobile: str, team_id: uuid.UUID
    ) -> None:
        self.updated.append((user_id, name, mobile, team_id))
        user = self._by_id[user_id]
        user.name = name
        user.mobile = mobile
        user.team_id = team_id

    async def deactivate(self, user_id: uuid.UUID) -> None:
        self.deactivated.append(user_id)
        self._by_id[user_id].status = UserStatus.INACTIVE

    async def count_active_administrators(self) -> int:
        return self._active_administrator_count

    async def acquire_administrator_removal_lock(self) -> None:
        pass


class FakeTeamRepository:
    def __init__(self, teams: list[Team] | None = None) -> None:
        self._by_id = {t.id: t for t in (teams or [])}
        self.added: list[tuple[uuid.UUID, str]] = []
        self.updated: list[tuple[uuid.UUID, str]] = []
        self.deactivated: list[uuid.UUID] = []

    async def get_by_id(self, team_id: uuid.UUID) -> Team | None:
        return self._by_id.get(team_id)

    async def get_by_name(self, name: str) -> Team | None:
        return next((t for t in self._by_id.values() if t.name == name), None)

    async def add(self, team_id: uuid.UUID, name: str) -> None:
        team = Team(id=team_id, name=name)
        self._by_id[team_id] = team
        self.added.append((team_id, name))

    async def update_name(self, team_id: uuid.UUID, name: str) -> None:
        self.updated.append((team_id, name))
        self._by_id[team_id].name = name

    async def deactivate(self, team_id: uuid.UUID) -> None:
        self.deactivated.append(team_id)
        self._by_id[team_id].status = TeamStatus.INACTIVE


class FakeAuditLogRepository:
    def __init__(self) -> None:
        self.entries: list[AuditLogEntry] = []

    async def add(self, entry: AuditLogEntry) -> None:
        self.entries.append(entry)


def _user_service(
    users: FakeUserRepository,
    audit_log: FakeAuditLogRepository,
    teams: FakeTeamRepository | None = None,
) -> UserDirectoryService:
    return UserDirectoryService(
        users, teams or FakeTeamRepository(), audit_log, LastAdministratorGuard(users)
    )


# --- UserDirectoryService.create_user ---------------------------------------


async def test_create_user_succeeds_and_writes_an_audit_entry():
    team = _make_team()
    users = FakeUserRepository()
    teams = FakeTeamRepository([team])
    audit_log = FakeAuditLogRepository()
    service = _user_service(users, audit_log, teams)
    actor_id = uuid.uuid4()

    user = await service.create_user(
        name="Karim",
        mobile="+8801700000001",
        role=Role.SALES_USER,
        team_id=team.id,
        actor_user_id=actor_id,
    )

    assert user.name == "Karim"
    assert user.mobile == "+8801700000001"
    assert user.role == Role.SALES_USER
    assert user.team_id == team.id
    assert user.status == UserStatus.ACTIVE
    assert user.username is None
    assert user.hashed_password is None
    assert users.added == [user]
    assert len(audit_log.entries) == 1
    assert audit_log.entries[0].action == "user.created"
    assert audit_log.entries[0].entity_id == user.id
    assert audit_log.entries[0].actor_user_id == actor_id


async def test_create_user_with_administrator_role_raises_role_not_allowed():
    users = FakeUserRepository()
    audit_log = FakeAuditLogRepository()
    service = _user_service(users, audit_log)

    with pytest.raises(RoleNotAllowed):
        await service.create_user(
            name="Karim",
            mobile="+8801700000001",
            role=Role.ADMINISTRATOR,
            team_id=uuid.uuid4(),
            actor_user_id=uuid.uuid4(),
        )

    assert users.added == []
    assert audit_log.entries == []


async def test_create_user_with_a_taken_mobile_raises_mobile_taken():
    team = _make_team()
    existing = _make_sales_user(mobile="+8801700000002")
    users = FakeUserRepository([existing])
    teams = FakeTeamRepository([team])
    audit_log = FakeAuditLogRepository()
    service = _user_service(users, audit_log, teams)

    with pytest.raises(MobileTaken):
        await service.create_user(
            name="Karim",
            mobile="+8801700000002",
            role=Role.MANAGER,
            team_id=team.id,
            actor_user_id=uuid.uuid4(),
        )

    assert audit_log.entries == []


async def test_create_user_with_a_nonexistent_team_raises_team_not_found():
    users = FakeUserRepository()
    audit_log = FakeAuditLogRepository()
    service = _user_service(users, audit_log)

    with pytest.raises(TeamNotFound):
        await service.create_user(
            name="Karim",
            mobile="+8801700000001",
            role=Role.SALES_USER,
            team_id=uuid.uuid4(),
            actor_user_id=uuid.uuid4(),
        )

    assert users.added == []


async def test_create_user_with_an_inactive_team_raises_team_inactive():
    team = _make_team(status=TeamStatus.INACTIVE)
    users = FakeUserRepository()
    teams = FakeTeamRepository([team])
    audit_log = FakeAuditLogRepository()
    service = _user_service(users, audit_log, teams)

    with pytest.raises(TeamInactive):
        await service.create_user(
            name="Karim",
            mobile="+8801700000001",
            role=Role.SALES_USER,
            team_id=team.id,
            actor_user_id=uuid.uuid4(),
        )

    assert users.added == []


# --- UserDirectoryService.update_user ----------------------------------------


async def test_update_user_succeeds_and_writes_an_audit_entry():
    new_team = _make_team()
    target = _make_sales_user(mobile="+8801700000003")
    users = FakeUserRepository([target])
    teams = FakeTeamRepository([new_team])
    audit_log = FakeAuditLogRepository()
    service = _user_service(users, audit_log, teams)

    updated = await service.update_user(
        user_id=target.id,
        name="Updated Name",
        mobile="+8801700000004",
        team_id=new_team.id,
        actor_user_id=uuid.uuid4(),
    )

    assert updated.name == "Updated Name"
    assert updated.mobile == "+8801700000004"
    assert updated.team_id == new_team.id
    assert audit_log.entries[0].action == "user.updated"


async def test_update_user_on_an_administrator_target_raises_cannot_edit_administrator():
    admin = _make_administrator()
    users = FakeUserRepository([admin])
    audit_log = FakeAuditLogRepository()
    service = _user_service(users, audit_log)

    with pytest.raises(CannotEditAdministrator):
        await service.update_user(
            user_id=admin.id,
            name="New Name",
            mobile="+8801700000005",
            team_id=uuid.uuid4(),
            actor_user_id=uuid.uuid4(),
        )

    assert audit_log.entries == []


async def test_update_user_with_a_mobile_taken_by_a_different_user_raises_mobile_taken():
    team = _make_team()
    other = _make_sales_user(mobile="+8801700000006")
    target = _make_sales_user(mobile="+8801700000007")
    users = FakeUserRepository([other, target])
    teams = FakeTeamRepository([team])
    audit_log = FakeAuditLogRepository()
    service = _user_service(users, audit_log, teams)

    with pytest.raises(MobileTaken):
        await service.update_user(
            user_id=target.id,
            name="Name",
            mobile="+8801700000006",
            team_id=team.id,
            actor_user_id=uuid.uuid4(),
        )


async def test_update_user_keeping_its_own_mobile_does_not_raise_mobile_taken():
    team = _make_team()
    target = _make_sales_user(mobile="+8801700000008", team_id=team.id)
    users = FakeUserRepository([target])
    teams = FakeTeamRepository([team])
    audit_log = FakeAuditLogRepository()
    service = _user_service(users, audit_log, teams)

    updated = await service.update_user(
        user_id=target.id,
        name="Renamed",
        mobile="+8801700000008",
        team_id=target.team_id,
        actor_user_id=uuid.uuid4(),
    )

    assert updated.name == "Renamed"


async def test_update_user_with_a_nonexistent_team_raises_team_not_found():
    target = _make_sales_user(mobile="+8801700000009")
    users = FakeUserRepository([target])
    audit_log = FakeAuditLogRepository()
    service = _user_service(users, audit_log)

    with pytest.raises(TeamNotFound):
        await service.update_user(
            user_id=target.id,
            name="Name",
            mobile="+8801700000009",
            team_id=uuid.uuid4(),
            actor_user_id=uuid.uuid4(),
        )


async def test_update_user_with_an_inactive_team_raises_team_inactive():
    team = _make_team(status=TeamStatus.INACTIVE)
    target = _make_sales_user(mobile="+8801700000010")
    users = FakeUserRepository([target])
    teams = FakeTeamRepository([team])
    audit_log = FakeAuditLogRepository()
    service = _user_service(users, audit_log, teams)

    with pytest.raises(TeamInactive):
        await service.update_user(
            user_id=target.id,
            name="Name",
            mobile="+8801700000010",
            team_id=team.id,
            actor_user_id=uuid.uuid4(),
        )


# --- UserDirectoryService.remove_user -----------------------------------------


async def test_remove_user_deactivates_a_sales_user_and_the_guard_is_a_no_op():
    target = _make_sales_user()
    users = FakeUserRepository([target], active_administrator_count=1)
    audit_log = FakeAuditLogRepository()
    service = _user_service(users, audit_log)

    await service.remove_user(user_id=target.id, actor_user_id=uuid.uuid4())

    assert users.deactivated == [target.id]
    assert audit_log.entries[0].action == "user.deactivated"


async def test_remove_user_raises_last_administrator_error_for_the_sole_active_administrator():
    admin = _make_administrator()
    users = FakeUserRepository([admin], active_administrator_count=1)
    audit_log = FakeAuditLogRepository()
    service = _user_service(users, audit_log)

    with pytest.raises(LastAdministratorError):
        await service.remove_user(user_id=admin.id, actor_user_id=uuid.uuid4())

    assert users.deactivated == []
    assert audit_log.entries == []


async def test_remove_user_succeeds_for_an_administrator_when_others_remain_active():
    admin = _make_administrator()
    users = FakeUserRepository([admin], active_administrator_count=2)
    audit_log = FakeAuditLogRepository()
    service = _user_service(users, audit_log)

    await service.remove_user(user_id=admin.id, actor_user_id=uuid.uuid4())

    assert users.deactivated == [admin.id]
    assert audit_log.entries[0].action == "user.deactivated"


async def test_remove_user_with_an_unknown_id_raises_user_not_found():
    users = FakeUserRepository()
    audit_log = FakeAuditLogRepository()
    service = _user_service(users, audit_log)

    with pytest.raises(UserNotFound):
        await service.remove_user(user_id=uuid.uuid4(), actor_user_id=uuid.uuid4())


async def test_update_user_with_an_unknown_id_raises_user_not_found():
    users = FakeUserRepository()
    audit_log = FakeAuditLogRepository()
    service = _user_service(users, audit_log)

    with pytest.raises(UserNotFound):
        await service.update_user(
            user_id=uuid.uuid4(),
            name="Name",
            mobile="+8801700000011",
            team_id=uuid.uuid4(),
            actor_user_id=uuid.uuid4(),
        )


# --- TeamDirectoryService -----------------------------------------------------


async def test_create_team_succeeds_and_writes_an_audit_entry():
    teams = FakeTeamRepository()
    audit_log = FakeAuditLogRepository()
    service = TeamDirectoryService(teams, audit_log)
    actor_id = uuid.uuid4()

    team = await service.create_team(name="North Zone", actor_user_id=actor_id)

    assert team.name == "North Zone"
    assert len(audit_log.entries) == 1
    assert audit_log.entries[0].action == "team.created"
    assert audit_log.entries[0].actor_user_id == actor_id


async def test_create_team_with_a_taken_name_raises_team_name_taken():
    existing = Team(id=uuid.uuid4(), name="North Zone")
    teams = FakeTeamRepository([existing])
    audit_log = FakeAuditLogRepository()
    service = TeamDirectoryService(teams, audit_log)

    with pytest.raises(TeamNameTaken):
        await service.create_team(name="North Zone", actor_user_id=uuid.uuid4())

    assert audit_log.entries == []


async def test_create_team_trims_whitespace_before_the_uniqueness_check():
    existing = Team(id=uuid.uuid4(), name="North Zone")
    teams = FakeTeamRepository([existing])
    audit_log = FakeAuditLogRepository()
    service = TeamDirectoryService(teams, audit_log)

    with pytest.raises(TeamNameTaken):
        await service.create_team(name="  North Zone  ", actor_user_id=uuid.uuid4())


async def test_update_team_succeeds_and_writes_an_audit_entry():
    team = Team(id=uuid.uuid4(), name="North Zone")
    teams = FakeTeamRepository([team])
    audit_log = FakeAuditLogRepository()
    service = TeamDirectoryService(teams, audit_log)

    updated = await service.update_team(
        team_id=team.id, name="Northern Zone", actor_user_id=uuid.uuid4()
    )

    assert updated.name == "Northern Zone"
    assert audit_log.entries[0].action == "team.updated"


async def test_update_team_to_a_name_taken_by_a_different_team_raises_team_name_taken():
    other = Team(id=uuid.uuid4(), name="South Zone")
    target = Team(id=uuid.uuid4(), name="North Zone")
    teams = FakeTeamRepository([other, target])
    audit_log = FakeAuditLogRepository()
    service = TeamDirectoryService(teams, audit_log)

    with pytest.raises(TeamNameTaken):
        await service.update_team(team_id=target.id, name="South Zone", actor_user_id=uuid.uuid4())


async def test_update_team_with_an_unknown_id_raises_team_not_found():
    teams = FakeTeamRepository()
    audit_log = FakeAuditLogRepository()
    service = TeamDirectoryService(teams, audit_log)

    with pytest.raises(TeamNotFound):
        await service.update_team(team_id=uuid.uuid4(), name="Name", actor_user_id=uuid.uuid4())


async def test_remove_team_deactivates_it_and_writes_an_audit_entry():
    team = Team(id=uuid.uuid4(), name="North Zone")
    teams = FakeTeamRepository([team])
    audit_log = FakeAuditLogRepository()
    service = TeamDirectoryService(teams, audit_log)

    await service.remove_team(team_id=team.id, actor_user_id=uuid.uuid4())

    assert teams.deactivated == [team.id]
    assert audit_log.entries[0].action == "team.deactivated"


async def test_remove_team_with_an_unknown_id_raises_team_not_found():
    teams = FakeTeamRepository()
    audit_log = FakeAuditLogRepository()
    service = TeamDirectoryService(teams, audit_log)

    with pytest.raises(TeamNotFound):
        await service.remove_team(team_id=uuid.uuid4(), actor_user_id=uuid.uuid4())
