import uuid
from datetime import UTC, datetime

import pytest

from domain.administrators import LastAdministratorError, LastAdministratorGuard
from domain.models import (
    AuditLogEntry,
    OptInConsent,
    RecipientList,
    RecipientListKind,
    RecipientListStatus,
    Role,
    Team,
    TeamStatus,
    User,
    UserStatus,
)
from domain.recipients import (
    CannotEditAdministrator,
    ConsentAlreadyActive,
    ConsentNotActive,
    ConsentTargetNotAddressable,
    MemberInactive,
    MemberNotAddressable,
    MemberNotFound,
    MobileTaken,
    OptInConsentService,
    RecipientListDirectoryService,
    RecipientListNameTaken,
    RecipientListNotFound,
    RoleNotAllowed,
    TeamDirectoryService,
    TeamInactive,
    TeamNameTaken,
    TeamNotFound,
    UserDirectoryService,
    UserNotFound,
    VersionConflict,
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
        self,
        users: list[User] | None = None,
        active_administrator_count: int = 2,
        simulate_update_race: bool = False,
    ) -> None:
        self._by_id = {u.id: u for u in (users or [])}
        self._active_administrator_count = active_administrator_count
        self._simulate_update_race = simulate_update_race
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
        self, user_id: uuid.UUID, name: str, mobile: str, team_id: uuid.UUID, expected_version: int
    ) -> bool:
        if self._simulate_update_race:
            return False
        user = self._by_id[user_id]
        if user.version != expected_version:
            return False
        self.updated.append((user_id, name, mobile, team_id))
        user.name = name
        user.mobile = mobile
        user.team_id = team_id
        user.version += 1
        return True

    async def deactivate(self, user_id: uuid.UUID) -> None:
        self.deactivated.append(user_id)
        self._by_id[user_id].status = UserStatus.INACTIVE

    async def count_active_administrators(self) -> int:
        return self._active_administrator_count

    async def acquire_administrator_removal_lock(self) -> None:
        pass

    async def get_many_by_ids(self, user_ids: list[uuid.UUID]) -> list[User]:
        if not user_ids:
            return []
        return [self._by_id[user_id] for user_id in user_ids if user_id in self._by_id]


class FakeTeamRepository:
    def __init__(
        self, teams: list[Team] | None = None, simulate_update_race: bool = False
    ) -> None:
        self._by_id = {t.id: t for t in (teams or [])}
        self._simulate_update_race = simulate_update_race
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

    async def update_name(self, team_id: uuid.UUID, name: str, expected_version: int) -> bool:
        if self._simulate_update_race:
            return False
        team = self._by_id[team_id]
        if team.version != expected_version:
            return False
        self.updated.append((team_id, name))
        team.name = name
        team.version += 1
        return True

    async def deactivate(self, team_id: uuid.UUID) -> None:
        self.deactivated.append(team_id)
        self._by_id[team_id].status = TeamStatus.INACTIVE


class FakeAuditLogRepository:
    def __init__(self) -> None:
        self.entries: list[AuditLogEntry] = []

    async def add(self, entry: AuditLogEntry) -> None:
        self.entries.append(entry)


class FakeRecipientListRepository:
    def __init__(
        self,
        recipient_lists: list[RecipientList] | None = None,
        simulate_update_race: bool = False,
    ) -> None:
        self._by_id = {rl.id: rl for rl in (recipient_lists or [])}
        self._simulate_update_race = simulate_update_race
        self.added: list[tuple[uuid.UUID, str, RecipientListKind]] = []
        self.updated: list[tuple[uuid.UUID, str, RecipientListKind]] = []
        self.deactivated: list[uuid.UUID] = []
        self.members_by_list: dict[uuid.UUID, list[uuid.UUID]] = {
            rl.id: list(rl.member_user_ids) for rl in (recipient_lists or [])
        }

    async def get_by_id(self, recipient_list_id: uuid.UUID) -> RecipientList | None:
        rl = self._by_id.get(recipient_list_id)
        if rl is None:
            return None
        rl.member_user_ids = self.members_by_list.get(recipient_list_id, [])
        return rl

    async def get_by_name(self, name: str) -> RecipientList | None:
        return next((rl for rl in self._by_id.values() if rl.name == name), None)

    async def add(self, recipient_list_id: uuid.UUID, name: str, kind: RecipientListKind) -> None:
        rl = RecipientList(id=recipient_list_id, name=name, kind=kind)
        self._by_id[recipient_list_id] = rl
        self.members_by_list[recipient_list_id] = []
        self.added.append((recipient_list_id, name, kind))

    async def update_details(
        self,
        recipient_list_id: uuid.UUID,
        name: str,
        kind: RecipientListKind,
        expected_version: int,
    ) -> bool:
        if self._simulate_update_race:
            return False
        rl = self._by_id[recipient_list_id]
        if rl.version != expected_version:
            return False
        self.updated.append((recipient_list_id, name, kind))
        rl.name = name
        rl.kind = kind
        rl.version += 1
        return True

    async def deactivate(self, recipient_list_id: uuid.UUID) -> None:
        self.deactivated.append(recipient_list_id)
        self._by_id[recipient_list_id].status = RecipientListStatus.INACTIVE

    async def replace_members(
        self, recipient_list_id: uuid.UUID, user_ids: list[uuid.UUID]
    ) -> None:
        self.members_by_list[recipient_list_id] = list(user_ids)

    async def get_member_user_ids(self, recipient_list_id: uuid.UUID) -> list[uuid.UUID]:
        return self.members_by_list.get(recipient_list_id, [])


class FakeOptInConsentRepository:
    def __init__(self, consents: list[OptInConsent] | None = None) -> None:
        self._active_by_user: dict[uuid.UUID, OptInConsent] = {
            c.user_id: c for c in (consents or []) if c.revoked_at is None
        }
        self.granted: list[tuple[uuid.UUID, str]] = []
        self.revoke_calls: list[uuid.UUID] = []

    async def get_active(self, user_id: uuid.UUID) -> OptInConsent | None:
        return self._active_by_user.get(user_id)

    async def get_active_by_user_ids(
        self, user_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, OptInConsent]:
        if not user_ids:
            return {}
        return {uid: c for uid, c in self._active_by_user.items() if uid in user_ids}

    async def grant(self, user_id: uuid.UUID, mobile: str) -> OptInConsent:
        self.granted.append((user_id, mobile))
        consent = OptInConsent(
            id=uuid.uuid4(), user_id=user_id, mobile=mobile, granted_at=datetime.now(UTC)
        )
        self._active_by_user[user_id] = consent
        return consent

    async def revoke_active(self, user_id: uuid.UUID) -> bool:
        self.revoke_calls.append(user_id)
        if user_id in self._active_by_user:
            del self._active_by_user[user_id]
            return True
        return False


def _user_service(
    users: FakeUserRepository,
    audit_log: FakeAuditLogRepository,
    teams: FakeTeamRepository | None = None,
    consents: FakeOptInConsentRepository | None = None,
) -> UserDirectoryService:
    return UserDirectoryService(
        users,
        teams or FakeTeamRepository(),
        audit_log,
        LastAdministratorGuard(users),
        consents or FakeOptInConsentRepository(),
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
        expected_version=1,
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
            expected_version=1,
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
            expected_version=1,
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
        expected_version=1,
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
            expected_version=1,
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
            expected_version=1,
            actor_user_id=uuid.uuid4(),
        )


async def test_update_user_changing_mobile_on_an_opted_in_user_revokes_consent_and_double_audits():
    team = _make_team()
    target = _make_sales_user(mobile="+8801700000020", team_id=team.id)
    active_consent = OptInConsent(
        id=uuid.uuid4(),
        user_id=target.id,
        mobile="+8801700000020",
        granted_at=datetime.now(UTC),
    )
    users = FakeUserRepository([target])
    teams = FakeTeamRepository([team])
    audit_log = FakeAuditLogRepository()
    consents = FakeOptInConsentRepository([active_consent])
    service = _user_service(users, audit_log, teams, consents)

    await service.update_user(
        user_id=target.id,
        name="Renamed",
        mobile="+8801700000021",
        team_id=team.id,
        expected_version=1,
        actor_user_id=uuid.uuid4(),
    )

    assert consents.revoke_calls == [target.id]
    actions = [entry.action for entry in audit_log.entries]
    assert actions == ["user.consent_auto_revoked", "user.updated"]
    assert audit_log.entries[0].details == {"reason": "mobile_number_changed"}


async def test_update_user_changing_mobile_with_no_active_consent_writes_only_user_updated():
    team = _make_team()
    target = _make_sales_user(mobile="+8801700000022", team_id=team.id)
    users = FakeUserRepository([target])
    teams = FakeTeamRepository([team])
    audit_log = FakeAuditLogRepository()
    consents = FakeOptInConsentRepository()
    service = _user_service(users, audit_log, teams, consents)

    await service.update_user(
        user_id=target.id,
        name="Renamed",
        mobile="+8801700000023",
        team_id=team.id,
        expected_version=1,
        actor_user_id=uuid.uuid4(),
    )

    assert consents.revoke_calls == [target.id]
    actions = [entry.action for entry in audit_log.entries]
    assert actions == ["user.updated"]


async def test_update_user_leaving_mobile_unchanged_never_calls_revoke_active():
    team = _make_team()
    target = _make_sales_user(mobile="+8801700000024", team_id=team.id)
    users = FakeUserRepository([target])
    teams = FakeTeamRepository([team])
    audit_log = FakeAuditLogRepository()
    consents = FakeOptInConsentRepository()
    service = _user_service(users, audit_log, teams, consents)

    await service.update_user(
        user_id=target.id,
        name="Renamed",
        mobile="+8801700000024",
        team_id=team.id,
        expected_version=1,
        actor_user_id=uuid.uuid4(),
    )

    assert consents.revoke_calls == []
    actions = [entry.action for entry in audit_log.entries]
    assert actions == ["user.updated"]


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


async def test_update_user_with_a_stale_version_raises_version_conflict():
    team = _make_team()
    target = _make_sales_user(mobile="+8801700000012", team_id=team.id)
    users = FakeUserRepository([target])
    teams = FakeTeamRepository([team])
    audit_log = FakeAuditLogRepository()
    service = _user_service(users, audit_log, teams)

    with pytest.raises(VersionConflict):
        await service.update_user(
            user_id=target.id,
            name="Name",
            mobile="+8801700000012",
            team_id=team.id,
            expected_version=target.version - 1,
            actor_user_id=uuid.uuid4(),
        )

    assert users.updated == []
    assert audit_log.entries == []


async def test_update_user_racing_atomic_backstop_raises_version_conflict():
    team = _make_team()
    target = _make_sales_user(mobile="+8801700000013", team_id=team.id)
    users = FakeUserRepository([target], simulate_update_race=True)
    teams = FakeTeamRepository([team])
    audit_log = FakeAuditLogRepository()
    service = _user_service(users, audit_log, teams)

    with pytest.raises(VersionConflict):
        await service.update_user(
            user_id=target.id,
            name="Name",
            mobile="+8801700000013",
            team_id=team.id,
            expected_version=target.version,
            actor_user_id=uuid.uuid4(),
        )

    assert users.updated == []
    assert audit_log.entries == []


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
            expected_version=1,
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
        team_id=team.id, name="Northern Zone", expected_version=1, actor_user_id=uuid.uuid4()
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
        await service.update_team(
            team_id=target.id, name="South Zone", expected_version=1, actor_user_id=uuid.uuid4()
        )


async def test_update_team_with_an_unknown_id_raises_team_not_found():
    teams = FakeTeamRepository()
    audit_log = FakeAuditLogRepository()
    service = TeamDirectoryService(teams, audit_log)

    with pytest.raises(TeamNotFound):
        await service.update_team(
            team_id=uuid.uuid4(), name="Name", expected_version=1, actor_user_id=uuid.uuid4()
        )


async def test_update_team_with_a_stale_version_raises_version_conflict():
    team = Team(id=uuid.uuid4(), name="North Zone")
    teams = FakeTeamRepository([team])
    audit_log = FakeAuditLogRepository()
    service = TeamDirectoryService(teams, audit_log)

    with pytest.raises(VersionConflict):
        await service.update_team(
            team_id=team.id,
            name="Northern Zone",
            expected_version=team.version - 1,
            actor_user_id=uuid.uuid4(),
        )

    assert teams.updated == []
    assert audit_log.entries == []


async def test_update_team_racing_atomic_backstop_raises_version_conflict():
    team = Team(id=uuid.uuid4(), name="North Zone")
    teams = FakeTeamRepository([team], simulate_update_race=True)
    audit_log = FakeAuditLogRepository()
    service = TeamDirectoryService(teams, audit_log)

    with pytest.raises(VersionConflict):
        await service.update_team(
            team_id=team.id,
            name="Northern Zone",
            expected_version=team.version,
            actor_user_id=uuid.uuid4(),
        )

    assert teams.updated == []
    assert audit_log.entries == []


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


# --- RecipientListDirectoryService.create_recipient_list ----------------------


async def test_create_recipient_list_succeeds_and_writes_an_audit_entry():
    member = _make_sales_user(mobile="+8801700000301")
    recipient_lists = FakeRecipientListRepository()
    users = FakeUserRepository([member])
    audit_log = FakeAuditLogRepository()
    service = RecipientListDirectoryService(recipient_lists, users, audit_log)
    actor_id = uuid.uuid4()

    recipient_list = await service.create_recipient_list(
        name="Dhaka Zone",
        kind=RecipientListKind.GROUP,
        member_user_ids=[member.id],
        actor_user_id=actor_id,
    )

    assert recipient_list.name == "Dhaka Zone"
    assert recipient_list.kind == RecipientListKind.GROUP
    assert recipient_list.member_user_ids == [member.id]
    assert len(audit_log.entries) == 1
    assert audit_log.entries[0].action == "recipient_list.created"
    assert audit_log.entries[0].actor_user_id == actor_id
    assert audit_log.entries[0].details == {
        "name": "Dhaka Zone",
        "kind": "group",
        "member_count": 1,
    }


async def test_create_recipient_list_with_a_taken_name_raises_recipient_list_name_taken():
    existing = RecipientList(id=uuid.uuid4(), name="Dhaka Zone", kind=RecipientListKind.CHANNEL)
    recipient_lists = FakeRecipientListRepository([existing])
    users = FakeUserRepository()
    audit_log = FakeAuditLogRepository()
    service = RecipientListDirectoryService(recipient_lists, users, audit_log)

    with pytest.raises(RecipientListNameTaken):
        await service.create_recipient_list(
            name="Dhaka Zone",
            kind=RecipientListKind.GROUP,
            member_user_ids=[],
            actor_user_id=uuid.uuid4(),
        )

    assert audit_log.entries == []


async def test_create_recipient_list_with_a_nonexistent_member_raises_member_not_found():
    recipient_lists = FakeRecipientListRepository()
    users = FakeUserRepository()
    audit_log = FakeAuditLogRepository()
    service = RecipientListDirectoryService(recipient_lists, users, audit_log)

    with pytest.raises(MemberNotFound):
        await service.create_recipient_list(
            name="Dhaka Zone",
            kind=RecipientListKind.GROUP,
            member_user_ids=[uuid.uuid4()],
            actor_user_id=uuid.uuid4(),
        )

    assert recipient_lists.added == []


async def test_create_recipient_list_with_an_inactive_member_raises_member_inactive():
    member = _make_sales_user(mobile="+8801700000302")
    member.status = UserStatus.INACTIVE
    recipient_lists = FakeRecipientListRepository()
    users = FakeUserRepository([member])
    audit_log = FakeAuditLogRepository()
    service = RecipientListDirectoryService(recipient_lists, users, audit_log)

    with pytest.raises(MemberInactive):
        await service.create_recipient_list(
            name="Dhaka Zone",
            kind=RecipientListKind.GROUP,
            member_user_ids=[member.id],
            actor_user_id=uuid.uuid4(),
        )


async def test_create_recipient_list_with_an_administrator_member_raises_member_not_addressable():
    admin = _make_administrator()
    recipient_lists = FakeRecipientListRepository()
    users = FakeUserRepository([admin])
    audit_log = FakeAuditLogRepository()
    service = RecipientListDirectoryService(recipient_lists, users, audit_log)

    with pytest.raises(MemberNotAddressable):
        await service.create_recipient_list(
            name="Dhaka Zone",
            kind=RecipientListKind.GROUP,
            member_user_ids=[admin.id],
            actor_user_id=uuid.uuid4(),
        )


async def test_create_recipient_list_with_zero_members_succeeds():
    recipient_lists = FakeRecipientListRepository()
    users = FakeUserRepository()
    audit_log = FakeAuditLogRepository()
    service = RecipientListDirectoryService(recipient_lists, users, audit_log)

    recipient_list = await service.create_recipient_list(
        name="Empty Channel",
        kind=RecipientListKind.CHANNEL,
        member_user_ids=[],
        actor_user_id=uuid.uuid4(),
    )

    assert recipient_list.member_user_ids == []


async def test_create_recipient_list_dedupes_repeated_member_ids():
    member = _make_sales_user(mobile="+8801700000305")
    recipient_lists = FakeRecipientListRepository()
    users = FakeUserRepository([member])
    audit_log = FakeAuditLogRepository()
    service = RecipientListDirectoryService(recipient_lists, users, audit_log)

    recipient_list = await service.create_recipient_list(
        name="Dhaka Zone",
        kind=RecipientListKind.GROUP,
        member_user_ids=[member.id, member.id],
        actor_user_id=uuid.uuid4(),
    )

    assert recipient_list.member_user_ids == [member.id]
    assert audit_log.entries[0].details["member_count"] == 1


# --- RecipientListDirectoryService.update_recipient_list ----------------------


async def test_update_recipient_list_renames_changes_kind_and_replaces_membership():
    old_member = _make_sales_user(mobile="+8801700000303")
    new_member = _make_sales_user(mobile="+8801700000304")
    target = RecipientList(
        id=uuid.uuid4(),
        name="Dhaka Zone",
        kind=RecipientListKind.GROUP,
        member_user_ids=[old_member.id],
    )
    recipient_lists = FakeRecipientListRepository([target])
    users = FakeUserRepository([old_member, new_member])
    audit_log = FakeAuditLogRepository()
    service = RecipientListDirectoryService(recipient_lists, users, audit_log)

    updated = await service.update_recipient_list(
        recipient_list_id=target.id,
        name="Dhaka Channel",
        kind=RecipientListKind.CHANNEL,
        member_user_ids=[new_member.id],
        expected_version=1,
        actor_user_id=uuid.uuid4(),
    )

    assert updated.name == "Dhaka Channel"
    assert updated.kind == RecipientListKind.CHANNEL
    assert updated.member_user_ids == [new_member.id]
    assert audit_log.entries[0].action == "recipient_list.updated"


async def test_update_recipient_list_on_an_unknown_id_raises_recipient_list_not_found():
    recipient_lists = FakeRecipientListRepository()
    users = FakeUserRepository()
    audit_log = FakeAuditLogRepository()
    service = RecipientListDirectoryService(recipient_lists, users, audit_log)

    with pytest.raises(RecipientListNotFound):
        await service.update_recipient_list(
            recipient_list_id=uuid.uuid4(),
            name="Name",
            kind=RecipientListKind.GROUP,
            member_user_ids=[],
            expected_version=1,
            actor_user_id=uuid.uuid4(),
        )


async def test_update_recipient_list_to_a_name_taken_by_a_different_list_raises_name_taken():
    other = RecipientList(id=uuid.uuid4(), name="South Zone", kind=RecipientListKind.GROUP)
    target = RecipientList(id=uuid.uuid4(), name="North Zone", kind=RecipientListKind.GROUP)
    recipient_lists = FakeRecipientListRepository([other, target])
    users = FakeUserRepository()
    audit_log = FakeAuditLogRepository()
    service = RecipientListDirectoryService(recipient_lists, users, audit_log)

    with pytest.raises(RecipientListNameTaken):
        await service.update_recipient_list(
            recipient_list_id=target.id,
            name="South Zone",
            kind=RecipientListKind.GROUP,
            member_user_ids=[],
            expected_version=1,
            actor_user_id=uuid.uuid4(),
        )


async def test_update_recipient_list_removing_a_member_actually_drops_it():
    member_one = _make_sales_user(mobile="+8801700000305")
    member_two = _make_sales_user(mobile="+8801700000306")
    target = RecipientList(
        id=uuid.uuid4(),
        name="Dhaka Zone",
        kind=RecipientListKind.GROUP,
        member_user_ids=[member_one.id, member_two.id],
    )
    recipient_lists = FakeRecipientListRepository([target])
    users = FakeUserRepository([member_one, member_two])
    audit_log = FakeAuditLogRepository()
    service = RecipientListDirectoryService(recipient_lists, users, audit_log)

    updated = await service.update_recipient_list(
        recipient_list_id=target.id,
        name="Dhaka Zone",
        kind=RecipientListKind.GROUP,
        member_user_ids=[member_one.id],
        expected_version=1,
        actor_user_id=uuid.uuid4(),
    )

    assert updated.member_user_ids == [member_one.id]


async def test_update_recipient_list_dedupes_repeated_member_ids():
    member = _make_sales_user(mobile="+8801700000307")
    target = RecipientList(id=uuid.uuid4(), name="Dhaka Zone", kind=RecipientListKind.GROUP)
    recipient_lists = FakeRecipientListRepository([target])
    users = FakeUserRepository([member])
    audit_log = FakeAuditLogRepository()
    service = RecipientListDirectoryService(recipient_lists, users, audit_log)

    updated = await service.update_recipient_list(
        recipient_list_id=target.id,
        name="Dhaka Zone",
        kind=RecipientListKind.GROUP,
        member_user_ids=[member.id, member.id],
        expected_version=1,
        actor_user_id=uuid.uuid4(),
    )

    assert updated.member_user_ids == [member.id]
    assert audit_log.entries[0].details["member_count"] == 1


async def test_update_recipient_list_with_a_stale_version_raises_version_conflict():
    target = RecipientList(id=uuid.uuid4(), name="Dhaka Zone", kind=RecipientListKind.GROUP)
    recipient_lists = FakeRecipientListRepository([target])
    users = FakeUserRepository()
    audit_log = FakeAuditLogRepository()
    service = RecipientListDirectoryService(recipient_lists, users, audit_log)

    with pytest.raises(VersionConflict):
        await service.update_recipient_list(
            recipient_list_id=target.id,
            name="Dhaka Channel",
            kind=RecipientListKind.CHANNEL,
            member_user_ids=[],
            expected_version=target.version - 1,
            actor_user_id=uuid.uuid4(),
        )

    assert recipient_lists.updated == []
    assert audit_log.entries == []


async def test_update_recipient_list_racing_atomic_backstop_raises_version_conflict():
    target = RecipientList(id=uuid.uuid4(), name="Dhaka Zone", kind=RecipientListKind.GROUP)
    recipient_lists = FakeRecipientListRepository([target], simulate_update_race=True)
    users = FakeUserRepository()
    audit_log = FakeAuditLogRepository()
    service = RecipientListDirectoryService(recipient_lists, users, audit_log)

    with pytest.raises(VersionConflict):
        await service.update_recipient_list(
            recipient_list_id=target.id,
            name="Dhaka Channel",
            kind=RecipientListKind.CHANNEL,
            member_user_ids=[],
            expected_version=target.version,
            actor_user_id=uuid.uuid4(),
        )

    assert recipient_lists.updated == []
    assert audit_log.entries == []


# --- RecipientListDirectoryService.remove_recipient_list -----------------------


async def test_remove_recipient_list_soft_deletes_and_writes_an_audit_entry():
    target = RecipientList(id=uuid.uuid4(), name="Dhaka Zone", kind=RecipientListKind.GROUP)
    recipient_lists = FakeRecipientListRepository([target])
    users = FakeUserRepository()
    audit_log = FakeAuditLogRepository()
    service = RecipientListDirectoryService(recipient_lists, users, audit_log)

    await service.remove_recipient_list(recipient_list_id=target.id, actor_user_id=uuid.uuid4())

    assert recipient_lists.deactivated == [target.id]
    assert audit_log.entries[0].action == "recipient_list.deactivated"


async def test_remove_recipient_list_with_an_unknown_id_raises_recipient_list_not_found():
    recipient_lists = FakeRecipientListRepository()
    users = FakeUserRepository()
    audit_log = FakeAuditLogRepository()
    service = RecipientListDirectoryService(recipient_lists, users, audit_log)

    with pytest.raises(RecipientListNotFound):
        await service.remove_recipient_list(
            recipient_list_id=uuid.uuid4(), actor_user_id=uuid.uuid4()
        )


# --- OptInConsentService.grant_consent -----------------------------------------


async def test_grant_consent_succeeds_and_writes_an_audit_entry():
    target = _make_sales_user(mobile="+8801700000701")
    users = FakeUserRepository([target])
    consents = FakeOptInConsentRepository()
    audit_log = FakeAuditLogRepository()
    service = OptInConsentService(users, consents, audit_log)
    actor_id = uuid.uuid4()

    consent = await service.grant_consent(user_id=target.id, actor_user_id=actor_id)

    assert consent.user_id == target.id
    assert consent.mobile == "+8801700000701"
    assert consents.granted == [(target.id, "+8801700000701")]
    assert len(audit_log.entries) == 1
    assert audit_log.entries[0].action == "consent.granted"
    assert audit_log.entries[0].entity_id == target.id
    assert audit_log.entries[0].actor_user_id == actor_id
    assert audit_log.entries[0].details == {"mobile": "+8801700000701"}


async def test_grant_consent_when_already_active_raises_consent_already_active():
    target = _make_sales_user(mobile="+8801700000702")
    active_consent = OptInConsent(
        id=uuid.uuid4(), user_id=target.id, mobile="+8801700000702", granted_at=datetime.now(UTC)
    )
    users = FakeUserRepository([target])
    consents = FakeOptInConsentRepository([active_consent])
    audit_log = FakeAuditLogRepository()
    service = OptInConsentService(users, consents, audit_log)

    with pytest.raises(ConsentAlreadyActive):
        await service.grant_consent(user_id=target.id, actor_user_id=uuid.uuid4())

    assert audit_log.entries == []


async def test_grant_consent_for_a_user_with_no_mobile_raises_consent_target_not_addressable():
    admin = _make_administrator()
    users = FakeUserRepository([admin])
    consents = FakeOptInConsentRepository()
    audit_log = FakeAuditLogRepository()
    service = OptInConsentService(users, consents, audit_log)

    with pytest.raises(ConsentTargetNotAddressable):
        await service.grant_consent(user_id=admin.id, actor_user_id=uuid.uuid4())

    assert audit_log.entries == []


async def test_grant_consent_for_a_nonexistent_user_raises_user_not_found():
    users = FakeUserRepository()
    consents = FakeOptInConsentRepository()
    audit_log = FakeAuditLogRepository()
    service = OptInConsentService(users, consents, audit_log)

    with pytest.raises(UserNotFound):
        await service.grant_consent(user_id=uuid.uuid4(), actor_user_id=uuid.uuid4())


# --- OptInConsentService.revoke_consent -----------------------------------------


async def test_revoke_consent_succeeds_and_writes_an_audit_entry():
    target = _make_sales_user(mobile="+8801700000703")
    active_consent = OptInConsent(
        id=uuid.uuid4(), user_id=target.id, mobile="+8801700000703", granted_at=datetime.now(UTC)
    )
    users = FakeUserRepository([target])
    consents = FakeOptInConsentRepository([active_consent])
    audit_log = FakeAuditLogRepository()
    service = OptInConsentService(users, consents, audit_log)
    actor_id = uuid.uuid4()

    await service.revoke_consent(user_id=target.id, actor_user_id=actor_id)

    assert consents.revoke_calls == [target.id]
    assert len(audit_log.entries) == 1
    assert audit_log.entries[0].action == "consent.revoked"
    assert audit_log.entries[0].entity_id == target.id
    assert audit_log.entries[0].actor_user_id == actor_id
    assert audit_log.entries[0].details is None


async def test_revoke_consent_when_nothing_active_raises_consent_not_active():
    target = _make_sales_user(mobile="+8801700000704")
    users = FakeUserRepository([target])
    consents = FakeOptInConsentRepository()
    audit_log = FakeAuditLogRepository()
    service = OptInConsentService(users, consents, audit_log)

    with pytest.raises(ConsentNotActive):
        await service.revoke_consent(user_id=target.id, actor_user_id=uuid.uuid4())

    assert audit_log.entries == []


async def test_revoke_consent_for_a_user_with_no_mobile_raises_consent_target_not_addressable():
    admin = _make_administrator()
    users = FakeUserRepository([admin])
    consents = FakeOptInConsentRepository()
    audit_log = FakeAuditLogRepository()
    service = OptInConsentService(users, consents, audit_log)

    with pytest.raises(ConsentTargetNotAddressable):
        await service.revoke_consent(user_id=admin.id, actor_user_id=uuid.uuid4())

    assert audit_log.entries == []


async def test_revoke_consent_for_a_nonexistent_user_raises_user_not_found():
    users = FakeUserRepository()
    consents = FakeOptInConsentRepository()
    audit_log = FakeAuditLogRepository()
    service = OptInConsentService(users, consents, audit_log)

    with pytest.raises(UserNotFound):
        await service.revoke_consent(user_id=uuid.uuid4(), actor_user_id=uuid.uuid4())
