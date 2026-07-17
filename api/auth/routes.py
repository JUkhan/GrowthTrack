"""Login (AC #1, #2, #4) and the first protected route (AC #3)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from adapters.persistence.audit_log import SqlAlchemyAuditLogRepository
from adapters.persistence.users import SqlAlchemyUserRepository
from api.auth.dependencies import ACCESS_TOKEN_COOKIE, get_current_user, get_db
from api.auth.tokens import create_access_token
from config import get_settings
from domain.auth import AuthenticationService, InvalidCredentials
from domain.models import User
from ports.auth import PwdlibPasswordHasher

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=255)
    # 72: bcrypt's own input limit — capping here turns a silent truncation
    # into a clean 422 instead of two different passwords hashing the same.
    password: str = Field(min_length=1, max_length=72)


class UserResponse(BaseModel):
    id: uuid.UUID
    username: str
    role: str


def _invalid_credentials() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "code": "invalid_credentials",
            "message": "Invalid username or password",
            "details": None,
        },
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

    response.set_cookie(
        key=ACCESS_TOKEN_COOKIE,
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.environment != "development",
        max_age=settings.jwt_expiry_minutes * 60,
    )

    return UserResponse(id=user.id, username=user.username, role=user.role.value)


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse(
        id=current_user.id, username=current_user.username, role=current_user.role.value
    )
