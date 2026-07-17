import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from api.auth.tokens import ALGORITHM, create_access_token, decode_access_token
from config import get_settings


def test_round_trip_returns_the_same_user_id():
    user_id = uuid.uuid4()

    token = create_access_token(user_id)

    assert decode_access_token(token) == user_id


def test_tampered_token_is_rejected():
    token = create_access_token(uuid.uuid4())
    tampered = token[:-1] + ("A" if token[-1] != "A" else "B")

    with pytest.raises(jwt.PyJWTError):
        decode_access_token(tampered)


def test_expired_token_is_rejected():
    settings = get_settings()
    now = datetime.now(UTC)
    expired_payload = {
        "sub": str(uuid.uuid4()),
        "iat": now - timedelta(minutes=settings.jwt_expiry_minutes + 10),
        "exp": now - timedelta(minutes=1),
    }
    expired_token = jwt.encode(expired_payload, settings.jwt_signing_key, algorithm=ALGORITHM)

    with pytest.raises(jwt.PyJWTError):
        decode_access_token(expired_token)


def test_token_signed_with_a_different_key_is_rejected():
    now = datetime.now(UTC)
    payload = {
        "sub": str(uuid.uuid4()),
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    forged = jwt.encode(payload, "not-the-real-signing-key", algorithm=ALGORITHM)

    with pytest.raises(jwt.PyJWTError):
        decode_access_token(forged)


def test_token_with_missing_sub_claim_is_rejected():
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {"iat": now, "exp": now + timedelta(minutes=5)}
    token = jwt.encode(payload, settings.jwt_signing_key, algorithm=ALGORITHM)

    with pytest.raises(jwt.PyJWTError):
        decode_access_token(token)


def test_token_with_non_uuid_sub_claim_is_rejected():
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {"sub": "not-a-uuid", "iat": now, "exp": now + timedelta(minutes=5)}
    token = jwt.encode(payload, settings.jwt_signing_key, algorithm=ALGORITHM)

    with pytest.raises(jwt.PyJWTError):
        decode_access_token(token)
