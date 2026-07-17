"""The shared auth enforcement choke-point (AD-8).

Structured as a pipeline of checks — token present, token valid, user
exists, Administrator role (Story 1.3), active status and ``jti``-based
revocation (Story 1.4) — each added as an additive step here, not a rewrite.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import NamedTuple

import jwt
from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from adapters.persistence.database import create_session_factory
from adapters.persistence.sessions import SqlAlchemyRevokedTokenRepository
from adapters.persistence.users import SqlAlchemyUserRepository
from api.auth.tokens import decode_access_token
from domain.models import Role, User, UserStatus

ACCESS_TOKEN_COOKIE = "access_token"


class CurrentSession(NamedTuple):
    user: User
    jti: uuid.UUID


async def get_db() -> AsyncGenerator[AsyncSession]:
    session_factory = create_session_factory()
    async with session_factory() as session:
        yield session


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": "unauthorized", "message": "Not authenticated", "details": None},
    )


def _deactivated() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "code": "account_deactivated",
            "message": "Your account has been deactivated. Contact an administrator.",
            "details": None,
        },
    )


async def get_current_session(
    access_token: str | None = Cookie(default=None, alias=ACCESS_TOKEN_COOKIE),
    session: AsyncSession = Depends(get_db),
) -> CurrentSession:
    if access_token is None:
        raise _unauthorized()

    try:
        claims = decode_access_token(access_token)
    except jwt.PyJWTError:
        raise _unauthorized() from None

    user = await SqlAlchemyUserRepository(session).get_by_id(claims.user_id)
    if user is None:
        raise _unauthorized()

    if user.role != Role.ADMINISTRATOR:
        raise _unauthorized()

    if user.status != UserStatus.ACTIVE:
        raise _deactivated()

    if await SqlAlchemyRevokedTokenRepository(session).is_revoked(claims.jti):
        raise _unauthorized()

    return CurrentSession(user=user, jti=claims.jti)


async def get_current_user(current: CurrentSession = Depends(get_current_session)) -> User:
    return current.user
