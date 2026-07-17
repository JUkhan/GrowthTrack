import uuid

from sqlalchemy import text

from adapters.persistence.database import create_engine
from api.auth.dependencies import ACCESS_TOKEN_COOKIE


async def _audit_rows() -> list[dict]:
    engine = create_engine()
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT actor_user_id, action, details FROM audit_log_entries ORDER BY created_at")
        )
        return [dict(row._mapping) for row in result]


async def _user_count() -> int:
    engine = create_engine()
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT COUNT(*) FROM users"))
        return result.scalar_one()


async def test_bootstrap_status_is_required_true_on_an_empty_db(client):
    response = await client.get("/auth/bootstrap-status")

    assert response.status_code == 200
    assert response.json() == {"bootstrap_required": True}


async def test_bootstrap_status_is_required_false_once_a_user_is_seeded(client, seed_user):
    await seed_user()

    response = await client.get("/auth/bootstrap-status")

    assert response.status_code == 200
    assert response.json() == {"bootstrap_required": False}


async def test_bootstrap_on_an_empty_db_creates_the_administrator_and_logs_in(client):
    response = await client.post(
        "/auth/bootstrap", json={"username": "admin", "password": "correct-horse-battery-staple"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "admin"
    assert body["role"] == "administrator"
    assert ACCESS_TOKEN_COOKIE in response.cookies

    set_cookie_header = response.headers.get("set-cookie", "")
    assert "httponly" in set_cookie_header.lower()
    assert "samesite=lax" in set_cookie_header.lower()

    me_response = await client.get("/auth/me")
    assert me_response.status_code == 200

    rows = await _audit_rows()
    assert len(rows) == 1
    assert rows[0]["action"] == "bootstrap.success"
    assert rows[0]["actor_user_id"] == uuid.UUID(body["id"])


async def test_bootstrap_when_an_administrator_already_exists_returns_409(client, seed_user):
    await seed_user(username="admin")

    response = await client.post(
        "/auth/bootstrap", json={"username": "second-admin", "password": "another-password"}
    )

    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "administrator_exists",
            "message": "An Administrator account already exists",
            "details": None,
        }
    }
    assert ACCESS_TOKEN_COOKIE not in response.cookies
    assert await _user_count() == 1


async def test_bootstrap_malformed_body_returns_422(client):
    response = await client.post("/auth/bootstrap", json={"username": "admin"})

    assert response.status_code == 422
