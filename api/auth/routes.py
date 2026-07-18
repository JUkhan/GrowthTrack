"""Login (AC #1, #2, #4), the first protected route (AC #3), first-run
Administrator bootstrap (Story 1.2), and login lockout / forgot-reset
password (Story 1.5, AC #1-#5)."""

from __future__ import annotations

import logging
import uuid
from dataclasses import replace
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from adapters.persistence.audit_log import SqlAlchemyAuditLogRepository
from adapters.persistence.password_reset import SqlAlchemyPasswordResetTokenRepository
from adapters.persistence.sessions import SqlAlchemyRevokedTokenRepository
from adapters.persistence.users import SqlAlchemyUserRepository
from api.auth.dependencies import (
    ACCESS_TOKEN_COOKIE,
    CurrentSession,
    get_current_session,
    get_current_user,
    get_db,
)
from api.auth.tokens import create_access_token
from config import Settings, get_settings
from domain.auth import AccountLocked, AuthenticationService, InvalidCredentials
from domain.bootstrap import BootstrapAlreadyComplete, BootstrapService
from domain.models import ThemePreference, User
from domain.password_reset import InvalidResetToken, PasswordResetService
from domain.preferences import UserPreferenceService
from domain.sessions import SessionService
from ports.auth import PwdlibPasswordHasher

logger = logging.getLogger(__name__)

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
    theme_preference: str


class BootstrapStatusResponse(BaseModel):
    bootstrap_required: bool


class MessageResponse(BaseModel):
    message: str


class ForgotPasswordRequest(BaseModel):
    username: str = Field(min_length=1, max_length=255)


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=1, max_length=512)
    new_password: str = Field(min_length=1, max_length=72)


class UpdateThemePreferenceRequest(BaseModel):
    theme_preference: Literal["light", "dark", "system"]


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


def _account_locked(retry_after_seconds: int) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "code": "account_locked",
            "message": "Too many failed login attempts. Try again later.",
            "details": {"retry_after_seconds": retry_after_seconds},
        },
    )


def _invalid_reset_token() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={
            "code": "invalid_reset_token",
            "message": "This reset link is invalid or has expired.",
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
    settings = get_settings()
    # login() (domain/auth.py) owns both the credential check and the
    # co-transactional audit write (AD-1, AD-7) — this route only orchestrates.
    auth_service = AuthenticationService(
        users,
        PwdlibPasswordHasher(),
        audit_log,
        lockout_threshold=settings.login_lockout_threshold,
        lockout_duration=timedelta(minutes=settings.login_lockout_duration_minutes),
    )

    try:
        user = await auth_service.login(body.username, body.password)
    except AccountLocked as exc:
        # Persists the lockout-state write and its audit entry even though
        # the request itself fails, same pattern as the InvalidCredentials
        # branch below.
        await session.commit()
        raise _account_locked(exc.retry_after_seconds) from None
    except InvalidCredentials:
        # Same code path for "no such username" and "wrong password" (Task 3) —
        # the response shape below is identical either way (AC #2).
        await session.commit()
        raise _invalid_credentials() from None

    # Built before the commit: if token creation ever fails, nothing about
    # this login (including its audit row) is persisted — no false-positive
    # "login.success" entry for a request that never actually issued a session.
    token = create_access_token(user.id)
    await session.commit()
    _set_session_cookie(response, token, settings)

    return UserResponse(
        id=user.id,
        username=user.username,
        role=user.role.value,
        theme_preference=user.theme_preference.value,
    )


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        role=current_user.role.value,
        theme_preference=current_user.theme_preference.value,
    )


@router.patch("/me", response_model=UserResponse)
async def update_theme_preference(
    body: UpdateThemePreferenceRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> UserResponse:
    users = SqlAlchemyUserRepository(session)
    service = UserPreferenceService(users)
    theme_preference = ThemePreference(body.theme_preference)
    await service.update_theme_preference(current_user.id, theme_preference)
    await session.commit()
    updated = replace(current_user, theme_preference=theme_preference)
    return UserResponse(
        id=updated.id,
        username=updated.username,
        role=updated.role.value,
        theme_preference=updated.theme_preference.value,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    current: CurrentSession = Depends(get_current_session),
    session: AsyncSession = Depends(get_db),
) -> None:
    session_service = SessionService(
        SqlAlchemyRevokedTokenRepository(session), SqlAlchemyAuditLogRepository(session)
    )
    await session_service.logout(current.user.id, current.jti)
    await session.commit()
    settings = get_settings()
    response.delete_cookie(
        ACCESS_TOKEN_COOKIE,
        httponly=True,
        samesite="lax",
        secure=settings.environment != "development",
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

    return UserResponse(
        id=user.id,
        username=user.username,
        role=user.role.value,
        theme_preference=user.theme_preference.value,
    )


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(
    body: ForgotPasswordRequest, session: AsyncSession = Depends(get_db)
) -> MessageResponse:
    """Public/unauthenticated, same reasoning as ``bootstrap-status``. The
    response is unconditional (AC #3) regardless of whether a token was
    actually issued — no username-enumeration oracle."""
    users = SqlAlchemyUserRepository(session)
    reset_tokens = SqlAlchemyPasswordResetTokenRepository(session)
    audit_log = SqlAlchemyAuditLogRepository(session)
    settings = get_settings()
    service = PasswordResetService(
        users,
        reset_tokens,
        PwdlibPasswordHasher(),
        audit_log,
        timedelta(minutes=settings.password_reset_token_ttl_minutes),
    )
    raw_token = await service.request_reset(body.username)
    await session.commit()
    if raw_token is not None:
        # `basicConfig`'s default formatter doesn't render `extra` fields —
        # the reset path must be in the message itself or it never appears
        # in the emitted log line at all.
        logger.info("password_reset_link_issued path=/reset-password?token=%s", raw_token)
    return MessageResponse(
        message=(
            "If an account with that username exists, "
            "password reset instructions have been generated."
        )
    )


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(
    body: ResetPasswordRequest, session: AsyncSession = Depends(get_db)
) -> None:
    users = SqlAlchemyUserRepository(session)
    reset_tokens = SqlAlchemyPasswordResetTokenRepository(session)
    audit_log = SqlAlchemyAuditLogRepository(session)
    service = PasswordResetService(
        users, reset_tokens, PwdlibPasswordHasher(), audit_log, timedelta(0)
    )
    try:
        await service.complete_reset(body.token, body.new_password)
    except InvalidResetToken:
        await session.commit()
        raise _invalid_reset_token() from None
    await session.commit()
