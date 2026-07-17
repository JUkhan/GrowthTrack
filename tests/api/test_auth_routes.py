from datetime import UTC, datetime, timedelta

import jwt
from sqlalchemy import text

from adapters.persistence.database import create_engine
from api.auth.dependencies import ACCESS_TOKEN_COOKIE
from api.auth.tokens import ALGORITHM, create_access_token
from config import get_settings
from domain.models import UserStatus


async def _audit_rows() -> list[dict]:
    engine = create_engine()
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT actor_user_id, action, details FROM audit_log_entries ORDER BY created_at")
        )
        return [dict(row._mapping) for row in result]


async def test_valid_login_returns_200_sets_cookie_and_audits_success(client, seed_user):
    user, password = await seed_user(username="admin")

    response = await client.post("/auth/login", json={"username": "admin", "password": password})

    assert response.status_code == 200
    body = response.json()
    assert body == {"id": str(user.id), "username": "admin", "role": "administrator"}
    assert ACCESS_TOKEN_COOKIE in response.cookies

    rows = await _audit_rows()
    assert len(rows) == 1
    assert rows[0]["action"] == "login.success"
    assert rows[0]["actor_user_id"] == user.id


async def test_login_cookie_is_httponly_and_lax(client, seed_user):
    _, password = await seed_user(username="admin")

    response = await client.post("/auth/login", json={"username": "admin", "password": password})

    set_cookie_header = response.headers.get("set-cookie", "")
    assert "httponly" in set_cookie_header.lower()
    assert "samesite=lax" in set_cookie_header.lower()


async def test_unknown_username_returns_generic_401_and_audits_failure(client):
    response = await client.post(
        "/auth/login", json={"username": "nobody", "password": "whatever"}
    )

    assert response.status_code == 401
    assert response.json() == {
        "error": {
            "code": "invalid_credentials",
            "message": "Invalid username or password",
            "details": None,
        }
    }
    assert ACCESS_TOKEN_COOKIE not in response.cookies

    rows = await _audit_rows()
    assert len(rows) == 1
    assert rows[0]["action"] == "login.failure"
    assert rows[0]["actor_user_id"] is None
    assert rows[0]["details"] == {"username": "nobody"}


async def test_wrong_password_returns_the_same_generic_401_shape(client, seed_user):
    await seed_user(username="admin", password="correct-horse-battery-staple")

    response = await client.post(
        "/auth/login", json={"username": "admin", "password": "wrong-password"}
    )

    assert response.status_code == 401
    assert response.json() == {
        "error": {
            "code": "invalid_credentials",
            "message": "Invalid username or password",
            "details": None,
        }
    }
    assert ACCESS_TOKEN_COOKIE not in response.cookies

    rows = await _audit_rows()
    assert rows[-1]["action"] == "login.failure"


async def test_inactive_user_cannot_log_in_even_with_correct_password(client, seed_user):
    await seed_user(
        username="admin",
        password="correct-horse-battery-staple",
        status=UserStatus.INACTIVE,
    )

    response = await client.post(
        "/auth/login", json={"username": "admin", "password": "correct-horse-battery-staple"}
    )

    assert response.status_code == 401
    assert ACCESS_TOKEN_COOKIE not in response.cookies


async def test_malformed_login_body_returns_422_in_the_error_envelope(client):
    response = await client.post("/auth/login", json={"username": "admin"})

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert isinstance(body["error"]["details"], list)


async def test_oversized_password_is_rejected_with_422(client):
    response = await client.post(
        "/auth/login", json={"username": "admin", "password": "x" * 73}
    )

    assert response.status_code == 422


async def test_login_cookie_is_secure_outside_development(client, seed_user, monkeypatch):
    _, password = await seed_user(username="admin")
    monkeypatch.setenv("ENVIRONMENT", "production")
    get_settings.cache_clear()

    try:
        response = await client.post(
            "/auth/login", json={"username": "admin", "password": password}
        )
    finally:
        get_settings.cache_clear()

    set_cookie_header = response.headers.get("set-cookie", "")
    assert "secure" in set_cookie_header.lower()


async def test_stored_password_is_a_bcrypt_hash_never_plaintext(seed_user):
    user, password = await seed_user(username="admin", password="correct-horse-battery-staple")

    assert user.hashed_password != password
    assert user.hashed_password.startswith("$2b$")


async def test_me_without_cookie_returns_401(client):
    response = await client.get("/auth/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_me_with_valid_cookie_returns_200(client, seed_user):
    user, password = await seed_user(username="admin")
    login_response = await client.post(
        "/auth/login", json={"username": "admin", "password": password}
    )
    assert login_response.status_code == 200

    response = await client.get("/auth/me")

    assert response.status_code == 200
    assert response.json() == {"id": str(user.id), "username": "admin", "role": "administrator"}


async def test_me_with_expired_token_returns_401(client, seed_user):
    user, _ = await seed_user(username="admin")
    settings = get_settings()
    now = datetime.now(UTC)
    expired_token = jwt.encode(
        {"sub": str(user.id), "iat": now - timedelta(hours=1), "exp": now - timedelta(minutes=1)},
        settings.jwt_signing_key,
        algorithm=ALGORITHM,
    )
    client.cookies.set(ACCESS_TOKEN_COOKIE, expired_token)

    response = await client.get("/auth/me")

    assert response.status_code == 401


async def test_me_with_tampered_token_returns_401(client, seed_user):
    user, _ = await seed_user(username="admin")
    token = create_access_token(user.id)
    client.cookies.set(ACCESS_TOKEN_COOKIE, token[:-1] + ("A" if token[-1] != "A" else "B"))

    response = await client.get("/auth/me")

    assert response.status_code == 401
