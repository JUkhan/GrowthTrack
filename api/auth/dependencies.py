"""The shared auth enforcement choke-point (AD-8).

Structured as a pipeline of checks — token present, token valid, user
exists — so Story 1.3 (Administrator-role check) and Story 1.4
(``jti``-based revocation check) are additive steps here, not a rewrite.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import jwt
from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from adapters.persistence.database import create_session_factory
from adapters.persistence.users import SqlAlchemyUserRepository
from api.auth.tokens import decode_access_token
from domain.models import User

ACCESS_TOKEN_COOKIE = "access_token"


async def get_db() -> AsyncGenerator[AsyncSession]:
    session_factory = create_session_factory()
    async with session_factory() as session:
        yield session


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": "unauthorized", "message": "Not authenticated", "details": None},
    )


async def get_current_user(
    access_token: str | None = Cookie(default=None, alias=ACCESS_TOKEN_COOKIE),
    session: AsyncSession = Depends(get_db),
) -> User:
    if access_token is None:
        raise _unauthorized()

    try:
        user_id = decode_access_token(access_token)
    except jwt.PyJWTError:
        raise _unauthorized() from None

    user = await SqlAlchemyUserRepository(session).get_by_id(user_id)
    if user is None:
        raise _unauthorized()

    # Story 1.3 adds: reject if user.role != Role.ADMINISTRATOR.
    # Story 1.4 adds: reject if the token's jti has been revoked.

    return user
