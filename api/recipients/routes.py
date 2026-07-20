"""Recipient directory: Users & Sales Teams CRUD (Story 3.1, CAP-5).

Every route depends on ``get_current_user`` (AD-8's shared choke-point —
never an inline per-route check). See ``domain/recipients.py`` for the
Role-Handling Matrix governing what Administrators can/can't do here.
"""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from adapters.persistence.audit_log import SqlAlchemyAuditLogRepository
from adapters.persistence.teams import SqlAlchemyTeamRepository
from adapters.persistence.users import SqlAlchemyUserRepository
from api.auth.dependencies import get_current_user, get_db
from domain.administrators import LastAdministratorError, LastAdministratorGuard
from domain.models import Role, Team, User
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

users_router = APIRouter(prefix="/users", tags=["recipients"])
teams_router = APIRouter(prefix="/teams", tags=["recipients"])


class CreateUserRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    mobile: str = Field(min_length=1, max_length=32)
    role: Literal["sales_user", "manager"]
    team_id: uuid.UUID


class UpdateUserRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    mobile: str = Field(min_length=1, max_length=32)
    team_id: uuid.UUID


class DirectoryUserResponse(BaseModel):
    id: uuid.UUID
    name: str | None
    mobile: str | None
    username: str | None
    role: str
    status: str
    team_id: uuid.UUID | None
    team_name: str | None
    version: int


class MobileAvailabilityResponse(BaseModel):
    available: bool


class CreateTeamRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class UpdateTeamRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class TeamResponse(BaseModel):
    id: uuid.UUID
    name: str
    status: str
    version: int


def _mobile_taken() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "mobile_taken",
            "message": "This mobile number is already assigned to another User",
            "details": None,
        },
    )


def _role_not_allowed() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={
            "code": "role_not_allowed",
            "message": "Administrator accounts can only be created through the bootstrap flow",
            "details": None,
        },
    )


def _administrator_not_editable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={
            "code": "administrator_not_editable",
            "message": "Administrator accounts are managed through login, not the Directory form",
            "details": None,
        },
    )


def _last_administrator(exc: LastAdministratorError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": "last_administrator", "message": str(exc), "details": None},
    )


def _team_name_taken() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "team_name_taken",
            "message": "A Sales Team with this name already exists",
            "details": None,
        },
    )


def _team_inactive() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={
            "code": "team_inactive",
            "message": "This Sales Team has been removed and can't accept new members",
            "details": None,
        },
    )


def _not_found(entity: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "code": "not_found",
            "message": f"No {entity} found for the given id",
            "details": None,
        },
    )


async def _team_name_map(teams: SqlAlchemyTeamRepository) -> dict[uuid.UUID, str]:
    return {team.id: team.name for team in await teams.list_all_full()}


def _to_directory_user_response(
    user: User, team_names: dict[uuid.UUID, str]
) -> DirectoryUserResponse:
    return DirectoryUserResponse(
        id=user.id,
        name=user.name,
        mobile=user.mobile,
        username=user.username,
        role=user.role.value,
        status=user.status.value,
        team_id=user.team_id,
        team_name=team_names.get(user.team_id) if user.team_id is not None else None,
        version=user.version,
    )


def _to_team_response(team: Team) -> TeamResponse:
    return TeamResponse(id=team.id, name=team.name, status=team.status.value, version=team.version)


@users_router.post("", response_model=DirectoryUserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: CreateUserRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> DirectoryUserResponse:
    users = SqlAlchemyUserRepository(session)
    teams = SqlAlchemyTeamRepository(session)
    audit_log = SqlAlchemyAuditLogRepository(session)
    service = UserDirectoryService(
        users, teams, audit_log, LastAdministratorGuard(users)
    )

    try:
        user = await service.create_user(
            name=body.name,
            mobile=body.mobile,
            role=Role(body.role),
            team_id=body.team_id,
            actor_user_id=current_user.id,
        )
    except MobileTaken:
        await session.commit()
        raise _mobile_taken() from None
    except RoleNotAllowed:
        await session.commit()
        raise _role_not_allowed() from None
    except TeamNotFound:
        await session.commit()
        raise _not_found("Team") from None
    except TeamInactive:
        await session.commit()
        raise _team_inactive() from None

    try:
        await session.commit()
    except IntegrityError:
        # The mobile-uniqueness pre-check above is a lightweight,
        # advisory-lock-free check (proportionate to Phase-1 concurrency per
        # NFR-8) — a concurrent request can still race past it. The
        # uq_users_mobile / ix_users_mobile_active_uq constraint is the real
        # backstop; map its violation to the same 409 the pre-check gives.
        await session.rollback()
        raise _mobile_taken() from None

    team_names = await _team_name_map(teams)
    return _to_directory_user_response(user, team_names)


@users_router.get("", response_model=list[DirectoryUserResponse])
async def list_users(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[DirectoryUserResponse]:
    users = SqlAlchemyUserRepository(session)
    teams = SqlAlchemyTeamRepository(session)
    team_names = await _team_name_map(teams)
    all_users = await users.list_all()
    return [_to_directory_user_response(user, team_names) for user in all_users]


@users_router.get("/mobile-availability", response_model=MobileAvailabilityResponse)
async def check_mobile_availability(
    mobile: str = Query(min_length=1, max_length=32),
    exclude_user_id: uuid.UUID | None = None,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> MobileAvailabilityResponse:
    users = SqlAlchemyUserRepository(session)
    existing = await users.get_by_mobile(mobile)
    available = existing is None or existing.id == exclude_user_id
    return MobileAvailabilityResponse(available=available)


@users_router.patch("/{user_id}", response_model=DirectoryUserResponse)
async def update_user(
    user_id: uuid.UUID,
    body: UpdateUserRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> DirectoryUserResponse:
    users = SqlAlchemyUserRepository(session)
    teams = SqlAlchemyTeamRepository(session)
    audit_log = SqlAlchemyAuditLogRepository(session)
    service = UserDirectoryService(
        users, teams, audit_log, LastAdministratorGuard(users)
    )

    try:
        user = await service.update_user(
            user_id=user_id,
            name=body.name,
            mobile=body.mobile,
            team_id=body.team_id,
            actor_user_id=current_user.id,
        )
    except UserNotFound:
        await session.commit()
        raise _not_found("User") from None
    except MobileTaken:
        await session.commit()
        raise _mobile_taken() from None
    except CannotEditAdministrator:
        await session.commit()
        raise _administrator_not_editable() from None
    except TeamNotFound:
        await session.commit()
        raise _not_found("Team") from None
    except TeamInactive:
        await session.commit()
        raise _team_inactive() from None

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise _mobile_taken() from None

    team_names = await _team_name_map(teams)
    return _to_directory_user_response(user, team_names)


@users_router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_user(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    users = SqlAlchemyUserRepository(session)
    teams = SqlAlchemyTeamRepository(session)
    audit_log = SqlAlchemyAuditLogRepository(session)
    service = UserDirectoryService(
        users, teams, audit_log, LastAdministratorGuard(users)
    )

    try:
        await service.remove_user(user_id=user_id, actor_user_id=current_user.id)
    except UserNotFound:
        await session.commit()
        raise _not_found("User") from None
    except LastAdministratorError as exc:
        await session.commit()
        raise _last_administrator(exc) from None

    await session.commit()


@teams_router.post("", response_model=TeamResponse, status_code=status.HTTP_201_CREATED)
async def create_team(
    body: CreateTeamRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> TeamResponse:
    teams = SqlAlchemyTeamRepository(session)
    audit_log = SqlAlchemyAuditLogRepository(session)
    service = TeamDirectoryService(teams, audit_log)

    try:
        team = await service.create_team(name=body.name, actor_user_id=current_user.id)
    except TeamNameTaken:
        await session.commit()
        raise _team_name_taken() from None

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise _team_name_taken() from None

    return _to_team_response(team)


@teams_router.get("", response_model=list[TeamResponse])
async def list_teams(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[TeamResponse]:
    teams = SqlAlchemyTeamRepository(session)
    return [_to_team_response(team) for team in await teams.list_all_full()]


@teams_router.patch("/{team_id}", response_model=TeamResponse)
async def update_team(
    team_id: uuid.UUID,
    body: UpdateTeamRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> TeamResponse:
    teams = SqlAlchemyTeamRepository(session)
    audit_log = SqlAlchemyAuditLogRepository(session)
    service = TeamDirectoryService(teams, audit_log)

    try:
        team = await service.update_team(
            team_id=team_id, name=body.name, actor_user_id=current_user.id
        )
    except TeamNotFound:
        await session.commit()
        raise _not_found("Team") from None
    except TeamNameTaken:
        await session.commit()
        raise _team_name_taken() from None

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise _team_name_taken() from None

    return _to_team_response(team)


@teams_router.delete("/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_team(
    team_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    teams = SqlAlchemyTeamRepository(session)
    audit_log = SqlAlchemyAuditLogRepository(session)
    service = TeamDirectoryService(teams, audit_log)

    try:
        await service.remove_team(team_id=team_id, actor_user_id=current_user.id)
    except TeamNotFound:
        await session.commit()
        raise _not_found("Team") from None

    await session.commit()
