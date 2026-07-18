import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from sqlalchemy import text

from adapters.persistence.audit_log import SqlAlchemyAuditLogRepository
from adapters.persistence.database import create_engine, create_session_factory
from adapters.persistence.password_reset import SqlAlchemyPasswordResetTokenRepository
from adapters.persistence.users import SqlAlchemyUserRepository, UserModel
from api.auth.dependencies import ACCESS_TOKEN_COOKIE
from api.auth.tokens import ALGORITHM, create_access_token
from config import get_settings
from domain.models import PasswordResetToken, Role, UserStatus
from domain.password_reset import PasswordResetService
from ports.auth import PwdlibPasswordHasher


async def _audit_rows() -> list[dict]:
    engine = create_engine()
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT actor_user_id, action, details FROM audit_log_entries ORDER BY created_at")
        )
        return [dict(row._mapping) for row in result]


async def _issue_reset_token(username: str) -> str:
    """Hand-crafts a reset token via the domain service directly — same
    precedent as this file's JWT-crafting helpers below (test_me_with_*) —
    since the HTTP layer deliberately never returns the raw token."""
    session_factory = create_session_factory()
    async with session_factory() as session:
        users = SqlAlchemyUserRepository(session)
        reset_tokens = SqlAlchemyPasswordResetTokenRepository(session)
        audit_log = SqlAlchemyAuditLogRepository(session)
        service = PasswordResetService(
            users, reset_tokens, PwdlibPasswordHasher(), audit_log, timedelta(minutes=60)
        )
        raw_token = await service.request_reset(username)
        await session.commit()
    assert raw_token is not None
    return raw_token


async def _issue_expired_reset_token(username: str) -> str:
    session_factory = create_session_factory()
    raw_token = "an-already-expired-raw-token"
    async with session_factory() as session:
        user = await SqlAlchemyUserRepository(session).get_by_username(username)
        await SqlAlchemyPasswordResetTokenRepository(session).add(
            PasswordResetToken(
                id=uuid.uuid4(),
                user_id=user.id,
                token_hash=hashlib.sha256(raw_token.encode("utf-8")).hexdigest(),
                expires_at=datetime.now(UTC) - timedelta(minutes=1),
                used_at=None,
                created_at=datetime.now(UTC) - timedelta(hours=2),
            )
        )
        await session.commit()
    return raw_token


async def test_valid_login_returns_200_sets_cookie_and_audits_success(client, seed_user):
    user, password = await seed_user(username="admin")

    response = await client.post("/auth/login", json={"username": "admin", "password": password})

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "id": str(user.id),
        "username": "admin",
        "role": "administrator",
        "theme_preference": "system",
    }
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


async def test_non_administrator_role_returns_the_same_generic_401_shape(client, seed_user):
    await seed_user(username="sales", password="correct-horse-battery-staple", role=Role.SALES_USER)

    response = await client.post(
        "/auth/login", json={"username": "sales", "password": "correct-horse-battery-staple"}
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
    assert response.json() == {
        "id": str(user.id),
        "username": "admin",
        "role": "administrator",
        "theme_preference": "system",
    }


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


async def test_me_with_a_valid_token_for_a_non_administrator_returns_401(client, seed_user):
    user, _ = await seed_user(username="sales", role=Role.SALES_USER)
    token = create_access_token(user.id)
    client.cookies.set(ACCESS_TOKEN_COOKIE, token)

    response = await client.get("/auth/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_patch_me_without_cookie_returns_401(client):
    response = await client.patch("/auth/me", json={"theme_preference": "dark"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_patch_me_updates_and_returns_the_new_theme_preference(client, seed_user):
    user, password = await seed_user(username="admin")
    await client.post("/auth/login", json={"username": "admin", "password": password})

    response = await client.patch("/auth/me", json={"theme_preference": "dark"})

    assert response.status_code == 200
    assert response.json() == {
        "id": str(user.id),
        "username": "admin",
        "role": "administrator",
        "theme_preference": "dark",
    }

    follow_up = await client.get("/auth/me")
    assert follow_up.json()["theme_preference"] == "dark"


async def test_patch_me_rejects_an_invalid_theme_preference_with_422(client, seed_user):
    _, password = await seed_user(username="admin")
    await client.post("/auth/login", json={"username": "admin", "password": password})

    response = await client.patch("/auth/me", json={"theme_preference": "purple"})

    assert response.status_code == 422


async def test_logout_returns_204_and_clears_the_cookie(client, seed_user):
    _, password = await seed_user(username="admin")
    await client.post("/auth/login", json={"username": "admin", "password": password})

    response = await client.post("/auth/logout")

    assert response.status_code == 204
    set_cookie_header = response.headers.get("set-cookie", "")
    assert f'{ACCESS_TOKEN_COOKIE}=""' in set_cookie_header
    assert "max-age=0" in set_cookie_header.lower()


async def test_logout_revokes_the_session_and_subsequent_requests_are_rejected(client, seed_user):
    _, password = await seed_user(username="admin")
    await client.post("/auth/login", json={"username": "admin", "password": password})

    logout_response = await client.post("/auth/logout")
    assert logout_response.status_code == 204

    response = await client.get("/auth/me")

    assert response.status_code == 401


async def test_logout_is_scoped_to_its_own_jti_not_the_whole_user(client, seed_user):
    user, password = await seed_user(username="admin")
    login_response = await client.post(
        "/auth/login", json={"username": "admin", "password": password}
    )
    assert login_response.status_code == 200
    token_b = create_access_token(user.id)

    logout_response = await client.post("/auth/logout")
    assert logout_response.status_code == 204

    client.cookies.set(ACCESS_TOKEN_COOKIE, token_b)
    response = await client.get("/auth/me")

    assert response.status_code == 200


async def test_logout_writes_an_audit_entry(client, seed_user):
    user, password = await seed_user(username="admin")
    await client.post("/auth/login", json={"username": "admin", "password": password})

    response = await client.post("/auth/logout")

    assert response.status_code == 204
    rows = await _audit_rows()
    assert rows[-1]["action"] == "logout"
    assert rows[-1]["actor_user_id"] == user.id


async def test_logout_without_a_session_returns_401(client):
    response = await client.post("/auth/logout")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_deactivated_administrator_with_a_still_valid_token_is_rejected_with_an_explanation(
    client, seed_user
):
    user, password = await seed_user(username="admin")
    login_response = await client.post(
        "/auth/login", json={"username": "admin", "password": password}
    )
    assert login_response.status_code == 200

    session_factory = create_session_factory()
    async with session_factory() as session:
        db_user = await session.get(UserModel, user.id)
        db_user.status = UserStatus.INACTIVE.value
        await session.commit()

    response = await client.get("/auth/me")

    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "account_deactivated"
    assert (
        body["error"]["message"]
        == "Your account has been deactivated. Contact an administrator."
    )


async def test_login_locks_after_five_failed_attempts(client, seed_user):
    _, password = await seed_user(username="admin")

    for _ in range(5):
        response = await client.post(
            "/auth/login", json={"username": "admin", "password": "wrong-password"}
        )
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "invalid_credentials"

    # The 6th attempt is rejected as locked even with the correct password.
    response = await client.post("/auth/login", json={"username": "admin", "password": password})

    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "account_locked"
    settings = get_settings()
    retry_after = body["error"]["details"]["retry_after_seconds"]
    assert 0 < retry_after <= settings.login_lockout_duration_minutes * 60


async def test_locked_account_audit_trail(client, seed_user):
    user, password = await seed_user(username="admin")

    for _ in range(5):
        await client.post("/auth/login", json={"username": "admin", "password": "wrong-password"})
    await client.post("/auth/login", json={"username": "admin", "password": password})

    rows = await _audit_rows()
    locked_rows = [r for r in rows if r["action"] == "account.locked"]
    assert len(locked_rows) == 1
    assert locked_rows[0]["actor_user_id"] == user.id

    failure_rows = [r for r in rows if r["action"] == "login.failure"]
    assert failure_rows[-1]["details"]["reason"] == "locked"


async def test_successful_login_clears_a_prior_lockout(client, seed_user):
    user, password = await seed_user(username="admin")

    for _ in range(4):
        response = await client.post(
            "/auth/login", json={"username": "admin", "password": "wrong-password"}
        )
        assert response.status_code == 401

    response = await client.post("/auth/login", json={"username": "admin", "password": password})
    assert response.status_code == 200

    session_factory = create_session_factory()
    async with session_factory() as session:
        db_user = await session.get(UserModel, user.id)
    assert db_user.failed_login_count == 0
    assert db_user.locked_until is None


async def test_forgot_password_returns_the_same_response_regardless_of_account_state(
    client, seed_user
):
    await seed_user(username="admin")
    await seed_user(username="sales", role=Role.SALES_USER)
    await seed_user(username="inactive-admin", status=UserStatus.INACTIVE)

    responses = []
    for username in ("admin", "a-username-that-does-not-exist", "sales", "inactive-admin"):
        response = await client.post("/auth/forgot-password", json={"username": username})
        responses.append((response.status_code, response.json()))

    first = responses[0]
    assert first[0] == 200
    for response in responses[1:]:
        assert response == first


async def test_reset_password_happy_path(client, seed_user):
    _, old_password = await seed_user(username="admin")
    raw_token = await _issue_reset_token("admin")

    response = await client.post(
        "/auth/reset-password",
        json={"token": raw_token, "new_password": "brand-new-password-1"},
    )
    assert response.status_code == 204

    new_password_login = await client.post(
        "/auth/login", json={"username": "admin", "password": "brand-new-password-1"}
    )
    assert new_password_login.status_code == 200

    old_password_login = await client.post(
        "/auth/login", json={"username": "admin", "password": old_password}
    )
    assert old_password_login.status_code == 401


async def test_reset_password_rejects_expired_used_or_unknown_token_identically(
    client, seed_user
):
    await seed_user(username="admin")

    unknown_response = await client.post(
        "/auth/reset-password", json={"token": "never-issued", "new_password": "whatever-1"}
    )

    used_raw_token = await _issue_reset_token("admin")
    await client.post(
        "/auth/reset-password", json={"token": used_raw_token, "new_password": "whatever-2"}
    )
    used_response = await client.post(
        "/auth/reset-password", json={"token": used_raw_token, "new_password": "whatever-3"}
    )

    expired_raw_token = await _issue_expired_reset_token("admin")
    expired_response = await client.post(
        "/auth/reset-password", json={"token": expired_raw_token, "new_password": "whatever-4"}
    )

    for response in (unknown_response, used_response, expired_response):
        assert response.status_code == 400
        assert response.json() == {
            "error": {
                "code": "invalid_reset_token",
                "message": "This reset link is invalid or has expired.",
                "details": None,
            }
        }


async def test_reset_password_clears_a_lockout(client, seed_user):
    await seed_user(username="admin")

    for _ in range(5):
        await client.post("/auth/login", json={"username": "admin", "password": "wrong-password"})

    raw_token = await _issue_reset_token("admin")
    reset_response = await client.post(
        "/auth/reset-password",
        json={"token": raw_token, "new_password": "brand-new-password-2"},
    )
    assert reset_response.status_code == 204

    login_response = await client.post(
        "/auth/login", json={"username": "admin", "password": "brand-new-password-2"}
    )
    assert login_response.status_code == 200
