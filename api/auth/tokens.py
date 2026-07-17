"""JWT issuance/validation (AD-8, CAP-1). HS256, signed with ``jwt_signing_key``.

No refresh-token mechanism in Phase 1 (Architecture spine's Deferred scope) —
a single access-token JWT with a configurable TTL; re-login is required after
expiry.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import NamedTuple

import jwt

from config import get_settings

ALGORITHM = "HS256"


class AccessTokenClaims(NamedTuple):
    user_id: uuid.UUID
    jti: uuid.UUID


def create_access_token(user_id: uuid.UUID) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expiry_minutes),
    }
    return jwt.encode(payload, settings.jwt_signing_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> AccessTokenClaims:
    """Returns the subject user id and the token's jti. Raises
    ``jwt.PyJWTError`` (or a subclass) on a missing/invalid/expired/tampered
    token, or one whose ``sub``/``jti`` claim isn't a valid UUID."""
    settings = get_settings()
    payload = jwt.decode(token, settings.jwt_signing_key, algorithms=[ALGORITHM])
    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise jwt.InvalidTokenError("Token 'sub' claim is missing or not a valid UUID") from exc
    try:
        jti = uuid.UUID(payload["jti"])
    except (KeyError, ValueError) as exc:
        raise jwt.InvalidTokenError("Token 'jti' claim is missing or not a valid UUID") from exc
    return AccessTokenClaims(user_id=user_id, jti=jti)
