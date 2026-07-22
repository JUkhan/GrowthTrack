"""Recipient directory: Users & Sales Teams CRUD (Story 3.1, CAP-5).

Every route depends on ``get_current_user`` (AD-8's shared choke-point —
never an inline per-route check). See ``domain/recipients.py`` for the
Role-Handling Matrix governing what Administrators can/can't do here.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from adapters.persistence.audit_log import SqlAlchemyAuditLogRepository
from adapters.persistence.consent import SqlAlchemyOptInConsentRepository
from adapters.persistence.doctors import SqlAlchemyDoctorRepository
from adapters.persistence.recipient_lists import SqlAlchemyRecipientListRepository
from adapters.persistence.teams import SqlAlchemyTeamRepository
from adapters.persistence.users import SqlAlchemyUserRepository
from api.auth.dependencies import get_current_user, get_db
from domain.administrators import LastAdministratorError, LastAdministratorGuard
from domain.models import OptInConsent, RecipientList, RecipientListKind, Role, Team, User
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
    TeamRenameBreaksTerritoryMapping,
    UserDirectoryService,
    UserNotFound,
    VersionConflict,
)

users_router = APIRouter(prefix="/users", tags=["recipients"])
teams_router = APIRouter(prefix="/teams", tags=["recipients"])
recipient_lists_router = APIRouter(prefix="/recipient-lists", tags=["recipients"])


class CreateUserRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    mobile: str = Field(min_length=1, max_length=32)
    role: Literal["sales_user", "manager"]
    team_id: uuid.UUID


class UpdateUserRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    mobile: str = Field(min_length=1, max_length=32)
    team_id: uuid.UUID
    version: int = Field(ge=1)


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
    consent_status: Literal["opted_in", "not_opted_in"]
    consent_recorded_at: datetime | None


class OptInConsentResponse(BaseModel):
    user_id: uuid.UUID
    granted_at: datetime


class MobileAvailabilityResponse(BaseModel):
    available: bool


class CreateTeamRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class UpdateTeamRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    version: int = Field(ge=1)


class TeamResponse(BaseModel):
    id: uuid.UUID
    name: str
    status: str
    version: int


class CreateRecipientListRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    kind: Literal["group", "channel"]
    member_user_ids: list[uuid.UUID] = Field(default_factory=list)


class UpdateRecipientListRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    kind: Literal["group", "channel"]
    member_user_ids: list[uuid.UUID] = Field(default_factory=list)
    version: int = Field(ge=1)


class RecipientListResponse(BaseModel):
    id: uuid.UUID
    name: str
    kind: str
    status: str
    version: int
    member_user_ids: list[uuid.UUID]


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


def _team_rename_breaks_territory_mapping() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "team_rename_breaks_territory_mapping",
            "message": (
                "This Sales Team's current name is used as a Territory by one or more "
                "Doctors. Renaming it would disconnect this Team's Recipients from their "
                "Daily Report doctor list."
            ),
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


def _recipient_list_name_taken() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "recipient_list_name_taken",
            "message": "A Recipient Group/Channel with this name already exists",
            "details": None,
        },
    )


def _member_inactive() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={
            "code": "member_inactive",
            "message": "This User has been removed and can't be added as a member",
            "details": None,
        },
    )


def _member_not_addressable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={
            "code": "member_not_addressable",
            "message": "This User has no mobile number on file and can't receive WhatsApp sends",
            "details": None,
        },
    )


def _consent_already_active() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "consent_already_active",
            "message": "This User already has active WhatsApp consent recorded",
            "details": None,
        },
    )


def _consent_not_active() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "consent_not_active",
            "message": "This User has no active WhatsApp consent to revoke",
            "details": None,
        },
    )


def _consent_not_addressable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={
            "code": "consent_not_addressable",
            "message": "This User has no mobile number on file and can't receive WhatsApp sends",
            "details": None,
        },
    )


def _version_conflict(current: BaseModel) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "version_conflict",
            "message": (
                "This record was changed by someone else since you loaded it. "
                "Review the current version before saving."
            ),
            "details": {"current": current.model_dump(mode="json")},
        },
    )


async def _team_name_map(teams: SqlAlchemyTeamRepository) -> dict[uuid.UUID, str]:
    return {team.id: team.name for team in await teams.list_all_full()}


def _to_directory_user_response(
    user: User, team_names: dict[uuid.UUID, str], active_consent: OptInConsent | None
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
        consent_status="opted_in" if active_consent else "not_opted_in",
        consent_recorded_at=active_consent.granted_at if active_consent else None,
    )


def _to_team_response(team: Team) -> TeamResponse:
    return TeamResponse(id=team.id, name=team.name, status=team.status.value, version=team.version)


def _to_recipient_list_response(recipient_list: RecipientList) -> RecipientListResponse:
    return RecipientListResponse(
        id=recipient_list.id,
        name=recipient_list.name,
        kind=recipient_list.kind.value,
        status=recipient_list.status.value,
        version=recipient_list.version,
        member_user_ids=recipient_list.member_user_ids,
    )


@users_router.post("", response_model=DirectoryUserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: CreateUserRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> DirectoryUserResponse:
    users = SqlAlchemyUserRepository(session)
    teams = SqlAlchemyTeamRepository(session)
    audit_log = SqlAlchemyAuditLogRepository(session)
    consents = SqlAlchemyOptInConsentRepository(session)
    service = UserDirectoryService(
        users, teams, audit_log, LastAdministratorGuard(users), consents
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
    # A freshly created User can never have consent yet — no repository call.
    return _to_directory_user_response(user, team_names, active_consent=None)


@users_router.get("", response_model=list[DirectoryUserResponse])
async def list_users(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[DirectoryUserResponse]:
    users = SqlAlchemyUserRepository(session)
    teams = SqlAlchemyTeamRepository(session)
    consents = SqlAlchemyOptInConsentRepository(session)
    team_names = await _team_name_map(teams)
    all_users = await users.list_all()
    consent_by_user = await consents.get_active_by_user_ids([u.id for u in all_users])
    return [
        _to_directory_user_response(user, team_names, consent_by_user.get(user.id))
        for user in all_users
    ]


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
    consents = SqlAlchemyOptInConsentRepository(session)
    service = UserDirectoryService(
        users, teams, audit_log, LastAdministratorGuard(users), consents
    )

    try:
        user = await service.update_user(
            user_id=user_id,
            name=body.name,
            mobile=body.mobile,
            team_id=body.team_id,
            expected_version=body.version,
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
    except VersionConflict:
        await session.commit()
        current = await users.get_by_id(user_id)
        if current is None:
            raise _not_found("User") from None
        team_names = await _team_name_map(teams)
        active_consent = await consents.get_active(user_id)
        raise _version_conflict(
            _to_directory_user_response(current, team_names, active_consent)
        ) from None

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise _mobile_taken() from None

    team_names = await _team_name_map(teams)
    # Re-read post-commit so a mobile change's auto-revoke (if any) is
    # reflected — not the pre-update state.
    active_consent = await consents.get_active(user_id)
    return _to_directory_user_response(user, team_names, active_consent)


@users_router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_user(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    users = SqlAlchemyUserRepository(session)
    teams = SqlAlchemyTeamRepository(session)
    audit_log = SqlAlchemyAuditLogRepository(session)
    consents = SqlAlchemyOptInConsentRepository(session)
    service = UserDirectoryService(
        users, teams, audit_log, LastAdministratorGuard(users), consents
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


@users_router.post(
    "/{user_id}/opt-in-consent",
    response_model=OptInConsentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def grant_opt_in_consent(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> OptInConsentResponse:
    users = SqlAlchemyUserRepository(session)
    consents = SqlAlchemyOptInConsentRepository(session)
    audit_log = SqlAlchemyAuditLogRepository(session)
    service = OptInConsentService(users, consents, audit_log)

    try:
        consent = await service.grant_consent(user_id=user_id, actor_user_id=current_user.id)
        await session.commit()
    except UserNotFound:
        await session.commit()
        raise _not_found("User") from None
    except ConsentTargetNotAddressable:
        await session.commit()
        raise _consent_not_addressable() from None
    except ConsentAlreadyActive:
        await session.commit()
        raise _consent_already_active() from None
    except IntegrityError:
        # The get_active() pre-check is advisory (same NFR-8 proportionality
        # reasoning as MobileTaken/RecipientListNameTaken) — the partial
        # unique index (ix_opt_in_consents_user_id_active_uq) is the real
        # backstop for a genuine concurrent double-grant. grant()'s explicit
        # flush() means this can surface from grant_consent() itself, not
        # just from the commit below — caught here, not in a separate block.
        await session.rollback()
        raise _consent_already_active() from None

    return OptInConsentResponse(user_id=user_id, granted_at=consent.granted_at)


@users_router.delete("/{user_id}/opt-in-consent", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_opt_in_consent(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    users = SqlAlchemyUserRepository(session)
    consents = SqlAlchemyOptInConsentRepository(session)
    audit_log = SqlAlchemyAuditLogRepository(session)
    service = OptInConsentService(users, consents, audit_log)

    try:
        await service.revoke_consent(user_id=user_id, actor_user_id=current_user.id)
    except UserNotFound:
        await session.commit()
        raise _not_found("User") from None
    except ConsentTargetNotAddressable:
        await session.commit()
        raise _consent_not_addressable() from None
    except ConsentNotActive:
        await session.commit()
        raise _consent_not_active() from None

    await session.commit()


@teams_router.post("", response_model=TeamResponse, status_code=status.HTTP_201_CREATED)
async def create_team(
    body: CreateTeamRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> TeamResponse:
    teams = SqlAlchemyTeamRepository(session)
    audit_log = SqlAlchemyAuditLogRepository(session)
    doctors = SqlAlchemyDoctorRepository(session)
    service = TeamDirectoryService(teams, audit_log, doctors)

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
    doctors = SqlAlchemyDoctorRepository(session)
    service = TeamDirectoryService(teams, audit_log, doctors)

    try:
        team = await service.update_team(
            team_id=team_id,
            name=body.name,
            expected_version=body.version,
            actor_user_id=current_user.id,
        )
    except TeamNotFound:
        await session.commit()
        raise _not_found("Team") from None
    except TeamNameTaken:
        await session.commit()
        raise _team_name_taken() from None
    except TeamRenameBreaksTerritoryMapping:
        await session.commit()
        raise _team_rename_breaks_territory_mapping() from None
    except VersionConflict:
        await session.commit()
        current = await teams.get_by_id(team_id)
        if current is None:
            raise _not_found("Team") from None
        raise _version_conflict(_to_team_response(current)) from None

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
    doctors = SqlAlchemyDoctorRepository(session)
    service = TeamDirectoryService(teams, audit_log, doctors)

    try:
        await service.remove_team(team_id=team_id, actor_user_id=current_user.id)
    except TeamNotFound:
        await session.commit()
        raise _not_found("Team") from None

    await session.commit()


@recipient_lists_router.post(
    "", response_model=RecipientListResponse, status_code=status.HTTP_201_CREATED
)
async def create_recipient_list(
    body: CreateRecipientListRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> RecipientListResponse:
    recipient_lists = SqlAlchemyRecipientListRepository(session)
    users = SqlAlchemyUserRepository(session)
    audit_log = SqlAlchemyAuditLogRepository(session)
    service = RecipientListDirectoryService(recipient_lists, users, audit_log)

    try:
        recipient_list = await service.create_recipient_list(
            name=body.name,
            kind=RecipientListKind(body.kind),
            member_user_ids=body.member_user_ids,
            actor_user_id=current_user.id,
        )
    except RecipientListNameTaken:
        await session.commit()
        raise _recipient_list_name_taken() from None
    except MemberNotFound:
        await session.commit()
        raise _not_found("User") from None
    except MemberInactive:
        await session.commit()
        raise _member_inactive() from None
    except MemberNotAddressable:
        await session.commit()
        raise _member_not_addressable() from None
    except IntegrityError:
        # add() flushes immediately (unlike TeamRepository.add()), so a
        # genuine concurrent-name race can raise here rather than at the
        # commit below — same backstop, earlier catch point.
        await session.rollback()
        raise _recipient_list_name_taken() from None

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise _recipient_list_name_taken() from None

    return _to_recipient_list_response(recipient_list)


@recipient_lists_router.get("", response_model=list[RecipientListResponse])
async def list_recipient_lists(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[RecipientListResponse]:
    recipient_lists = SqlAlchemyRecipientListRepository(session)
    return [
        _to_recipient_list_response(recipient_list)
        for recipient_list in await recipient_lists.list_all_full()
    ]


@recipient_lists_router.patch("/{recipient_list_id}", response_model=RecipientListResponse)
async def update_recipient_list(
    recipient_list_id: uuid.UUID,
    body: UpdateRecipientListRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> RecipientListResponse:
    recipient_lists = SqlAlchemyRecipientListRepository(session)
    users = SqlAlchemyUserRepository(session)
    audit_log = SqlAlchemyAuditLogRepository(session)
    service = RecipientListDirectoryService(recipient_lists, users, audit_log)

    try:
        recipient_list = await service.update_recipient_list(
            recipient_list_id=recipient_list_id,
            name=body.name,
            kind=RecipientListKind(body.kind),
            member_user_ids=body.member_user_ids,
            expected_version=body.version,
            actor_user_id=current_user.id,
        )
    except RecipientListNotFound:
        await session.commit()
        raise _not_found("RecipientList") from None
    except RecipientListNameTaken:
        await session.commit()
        raise _recipient_list_name_taken() from None
    except MemberNotFound:
        await session.commit()
        raise _not_found("User") from None
    except MemberInactive:
        await session.commit()
        raise _member_inactive() from None
    except MemberNotAddressable:
        await session.commit()
        raise _member_not_addressable() from None
    except VersionConflict:
        await session.commit()
        current = await recipient_lists.get_by_id(recipient_list_id)
        if current is None:
            raise _not_found("RecipientList") from None
        raise _version_conflict(_to_recipient_list_response(current)) from None
    except IntegrityError:
        # update_details() executes its UPDATE immediately, so a genuine
        # concurrent-rename race can raise here rather than at the commit
        # below — same backstop, earlier catch point.
        await session.rollback()
        raise _recipient_list_name_taken() from None

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise _recipient_list_name_taken() from None

    return _to_recipient_list_response(recipient_list)


@recipient_lists_router.delete("/{recipient_list_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_recipient_list(
    recipient_list_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    recipient_lists = SqlAlchemyRecipientListRepository(session)
    users = SqlAlchemyUserRepository(session)
    audit_log = SqlAlchemyAuditLogRepository(session)
    service = RecipientListDirectoryService(recipient_lists, users, audit_log)

    try:
        await service.remove_recipient_list(
            recipient_list_id=recipient_list_id, actor_user_id=current_user.id
        )
    except RecipientListNotFound:
        await session.commit()
        raise _not_found("RecipientList") from None

    await session.commit()
