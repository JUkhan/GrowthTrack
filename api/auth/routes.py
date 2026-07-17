"""Login (AC #1, #2, #4), the first protected route (AC #3), and first-run
Administrator bootstrap (Story 1.2)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from adapters.persistence.audit_log import SqlAlchemyAuditLogRepository
from adapters.persistence.users import SqlAlchemyUserRepository
from api.auth.dependencies import ACCESS_TOKEN_COOKIE, get_current_user, get_db
from api.auth.tokens import create_access_token
from config import Settings, get_settings
from domain.auth import AuthenticationService, InvalidCredentials
from domain.bootstrap import BootstrapAlreadyComplete, BootstrapService
from domain.models import User
from ports.auth import PwdlibPasswordHasher

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=255)
    # 72: bcrypt's own input limit — capping here turns a silent truncation
    # into a clean 422 instead of two different passwords hashing the same.
    password: str = Field(min_length=1, max_length=72)


class BootstrapRequest(BaseModel):
    username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=72)


class UserResponse(BaseModel):
    id: uuid.UUID
    username: str
    role: str


class BootstrapStatusResponse(BaseModel):
    bootstrap_required: bool


def _invalid_credentials() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "code": "invalid_credentials",
            "message": "Invalid username or password",
            "details": None,
        },
    )


def _administrator_exists() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "administrator_exists",
            "message": "An Administrator account already exists",
            "details": None,
        },
    )


def _set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    """Issues the session cookie — the one path both ``login`` and
    ``bootstrap`` use to avoid duplicating the ``set_cookie`` call.

    Takes an already-created ``token`` (built before ``session.commit()``,
    not here) so a token-creation failure can never follow an
    already-committed "success" audit row."""
    response.set_cookie(
        key=ACCESS_TOKEN_COOKIE,
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.environment != "development",
        max_age=settings.jwt_expiry_minutes * 60,
    )


@router.post("/login", response_model=UserResponse)
async def login(
    body: LoginRequest,
    response: Response,
    session: AsyncSession = Depends(get_db),
) -> UserResponse:
    users = SqlAlchemyUserRepository(session)
    audit_log = SqlAlchemyAuditLogRepository(session)
    # login() (domain/auth.py) owns both the credential check and the
    # co-transactional audit write (AD-1, AD-7) — this route only orchestrates.
    auth_service = AuthenticationService(users, PwdlibPasswordHasher(), audit_log)

    try:
        user = await auth_service.login(body.username, body.password)
    except InvalidCredentials:
        # Same code path for "no such username" and "wrong password" (Task 3) —
        # the response shape below is identical either way (AC #2).
        await session.commit()
        raise _invalid_credentials() from None

    # Built before the commit: if token creation ever fails, nothing about
    # this login (including its audit row) is persisted — no false-positive
    # "login.success" entry for a request that never actually issued a session.
    settings = get_settings()
    token = create_access_token(user.id)
    await session.commit()
    _set_session_cookie(response, token, settings)

    return UserResponse(id=user.id, username=user.username, role=user.role.value)


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse(
        id=current_user.id, username=current_user.username, role=current_user.role.value
    )


@router.get("/bootstrap-status", response_model=BootstrapStatusResponse)
async def bootstrap_status(session: AsyncSession = Depends(get_db)) -> BootstrapStatusResponse:
    """Public/unauthenticated (AC #1, #3) — a session-less visitor must be
    able to call this before any Administrator account exists."""
    users = SqlAlchemyUserRepository(session)
    audit_log = SqlAlchemyAuditLogRepository(session)
    bootstrap_service = BootstrapService(users, PwdlibPasswordHasher(), audit_log)
    return BootstrapStatusResponse(bootstrap_required=await bootstrap_service.is_required())


@router.post("/bootstrap", response_model=UserResponse)
async def bootstrap(
    body: BootstrapRequest,
    response: Response,
    session: AsyncSession = Depends(get_db),
) -> UserResponse:
    users = SqlAlchemyUserRepository(session)
    audit_log = SqlAlchemyAuditLogRepository(session)
    # bootstrap() (domain/bootstrap.py) owns the lock, the existence
    # re-check, the User creation, and the co-transactional audit write
    # (AD-1) — this route only orchestrates.
    bootstrap_service = BootstrapService(users, PwdlibPasswordHasher(), audit_log)

    try:
        user = await bootstrap_service.bootstrap(body.username, body.password)
    except BootstrapAlreadyComplete:
        # Releases the advisory lock cleanly. This is the endpoint's
        # permanent-lockout behavior: once any Administrator exists, this
        # path is closed forever, not just during the race window.
        await session.commit()
        raise _administrator_exists() from None

    settings = get_settings()
    token = create_access_token(user.id)
    await session.commit()
    _set_session_cookie(response, token, settings)

    return UserResponse(id=user.id, username=user.username, role=user.role.value)
