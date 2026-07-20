"""Recipient directory: Users & Sales Teams CRUD (Story 3.1, CAP-5, AC #1-#6).

Every mutating method writes its data change and its ``AuditLogEntry`` in
the same call (AD-7) — the caller (an ``api/recipients`` route) commits the
transaction, same pattern ``domain/auth.py``/``domain/bootstrap.py`` already
established.

Role-Handling Matrix (see the story's Dev Notes for the full table):
Administrators are listed and removable through this directory (so
``LastAdministratorGuard`` has something to protect), but never creatable or
editable through it — Administrator accounts exist only via Epic 1's
bootstrap flow, and have no Name/Mobile/Team semantics.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from domain.administrators import LastAdministratorGuard
from domain.models import AuditLogEntry, Role, Team, TeamStatus, User, UserStatus
from ports.audit import AuditLogRepository
from ports.teams import TeamRepository
from ports.users import UserRepository


class RoleNotAllowed(Exception):
    """Raised when a User is created through this directory with
    ``role=Role.ADMINISTRATOR`` — Administrator accounts are created only
    through Epic 1's bootstrap flow (AC #5)."""


class MobileTaken(Exception):
    """Raised when a mobile number is already assigned to a different User."""


class CannotEditAdministrator(Exception):
    """Raised on an attempt to edit an Administrator's Name/Mobile/Team
    through this directory — Administrators have no such fields (see the
    Role-Handling Matrix)."""


class TeamNameTaken(Exception):
    """Raised when a Team name is already in use by a different Team."""


class UserNotFound(Exception):
    """Raised when no User exists for a given id."""


class TeamNotFound(Exception):
    """Raised when no Team exists for a given id."""


class TeamInactive(Exception):
    """Raised when a User is created/updated against a Team that has been
    soft-deleted (``TeamStatus.INACTIVE``) — code review of Story 3.1."""


class UserDirectoryService:
    def __init__(
        self,
        users: UserRepository,
        teams: TeamRepository,
        audit_log: AuditLogRepository,
        last_admin_guard: LastAdministratorGuard,
    ) -> None:
        self._users = users
        self._teams = teams
        self._audit_log = audit_log
        self._last_admin_guard = last_admin_guard

    async def _ensure_team_active(self, team_id: uuid.UUID) -> None:
        team = await self._teams.get_by_id(team_id)
        if team is None:
            raise TeamNotFound()
        if team.status != TeamStatus.ACTIVE:
            raise TeamInactive()

    async def create_user(
        self,
        name: str,
        mobile: str,
        role: Role,
        team_id: uuid.UUID,
        actor_user_id: uuid.UUID,
    ) -> User:
        # Defense-in-depth: the API layer's Pydantic Literal type should
        # already reject "administrator" before this is ever called, but the
        # domain layer must never trust the API layer alone (AC #5).
        if role == Role.ADMINISTRATOR:
            raise RoleNotAllowed()

        # Code review of Story 3.1: the frontend's Team picker only offers
        # active Teams, but nothing previously stopped a direct API call
        # (or a stale form submitted after the Team was deactivated) from
        # assigning a User to a nonexistent or inactive Team.
        await self._ensure_team_active(team_id)

        if await self._users.get_by_mobile(mobile) is not None:
            raise MobileTaken()

        now = datetime.now(UTC)
        user = User(
            id=uuid.uuid4(),
            username=None,
            hashed_password=None,
            role=role,
            status=UserStatus.ACTIVE,
            version=1,
            created_at=now,
            name=name,
            mobile=mobile,
            team_id=team_id,
        )
        await self._users.add(user)
        await self._audit_log.add(
            AuditLogEntry(
                id=uuid.uuid4(),
                actor_user_id=actor_user_id,
                action="user.created",
                entity_type="User",
                entity_id=user.id,
                details={"name": name, "mobile": mobile, "role": role.value},
                created_at=now,
            )
        )
        return user

    async def update_user(
        self,
        user_id: uuid.UUID,
        name: str,
        mobile: str,
        team_id: uuid.UUID,
        actor_user_id: uuid.UUID,
    ) -> User:
        target = await self._users.get_by_id(user_id)
        if target is None:
            raise UserNotFound()

        if target.role == Role.ADMINISTRATOR:
            raise CannotEditAdministrator()

        await self._ensure_team_active(team_id)

        existing = await self._users.get_by_mobile(mobile)
        if existing is not None and existing.id != user_id:
            raise MobileTaken()

        await self._users.update_directory_fields(user_id, name, mobile, team_id)
        await self._audit_log.add(
            AuditLogEntry(
                id=uuid.uuid4(),
                actor_user_id=actor_user_id,
                action="user.updated",
                entity_type="User",
                entity_id=user_id,
                details={"name": name, "mobile": mobile, "team_id": str(team_id)},
                created_at=datetime.now(UTC),
            )
        )
        return await self._users.get_by_id(user_id)

    async def remove_user(self, user_id: uuid.UUID, actor_user_id: uuid.UUID) -> None:
        target = await self._users.get_by_id(user_id)
        if target is None:
            raise UserNotFound()

        # No-ops for a Sales User/Manager target (existing short-circuit);
        # raises LastAdministratorError if this would leave zero active
        # Administrators (AC #6) — this is the call site
        # domain/administrators.py's docstring deferred to this story.
        await self._last_admin_guard.ensure_can_deactivate(target)

        await self._users.deactivate(user_id)
        await self._audit_log.add(
            AuditLogEntry(
                id=uuid.uuid4(),
                actor_user_id=actor_user_id,
                action="user.deactivated",
                entity_type="User",
                entity_id=user_id,
                details=None,
                created_at=datetime.now(UTC),
            )
        )


class TeamDirectoryService:
    def __init__(self, teams: TeamRepository, audit_log: AuditLogRepository) -> None:
        self._teams = teams
        self._audit_log = audit_log

    async def create_team(self, name: str, actor_user_id: uuid.UUID) -> Team:
        # Trimmed here too (code review of Story 3.1), mirroring
        # get_or_create_by_name's own normalization — "North" and "North "
        # must not pass the uniqueness check as distinct names.
        name = name.strip()
        if await self._teams.get_by_name(name) is not None:
            raise TeamNameTaken()

        team_id = uuid.uuid4()
        await self._teams.add(team_id, name)
        await self._audit_log.add(
            AuditLogEntry(
                id=uuid.uuid4(),
                actor_user_id=actor_user_id,
                action="team.created",
                entity_type="Team",
                entity_id=team_id,
                details={"name": name},
                created_at=datetime.now(UTC),
            )
        )
        return await self._teams.get_by_id(team_id)

    async def update_team(self, team_id: uuid.UUID, name: str, actor_user_id: uuid.UUID) -> Team:
        target = await self._teams.get_by_id(team_id)
        if target is None:
            raise TeamNotFound()

        name = name.strip()
        existing = await self._teams.get_by_name(name)
        if existing is not None and existing.id != team_id:
            raise TeamNameTaken()

        await self._teams.update_name(team_id, name)
        await self._audit_log.add(
            AuditLogEntry(
                id=uuid.uuid4(),
                actor_user_id=actor_user_id,
                action="team.updated",
                entity_type="Team",
                entity_id=team_id,
                details={"name": name},
                created_at=datetime.now(UTC),
            )
        )
        return await self._teams.get_by_id(team_id)

    async def remove_team(self, team_id: uuid.UUID, actor_user_id: uuid.UUID) -> None:
        target = await self._teams.get_by_id(team_id)
        if target is None:
            raise TeamNotFound()

        await self._teams.deactivate(team_id)
        await self._audit_log.add(
            AuditLogEntry(
                id=uuid.uuid4(),
                actor_user_id=actor_user_id,
                action="team.deactivated",
                entity_type="Team",
                entity_id=team_id,
                details=None,
                created_at=datetime.now(UTC),
            )
        )
