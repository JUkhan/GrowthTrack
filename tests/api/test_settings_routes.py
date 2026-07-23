from sqlalchemy import text

from adapters.persistence.database import create_session_factory


async def _login_as_admin(client, seed_user, username: str = "admin") -> None:
    _, password = await seed_user(username=username)
    response = await client.post("/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200


# --- Auth enforcement (AD-8) ------------------------------------------------


async def test_get_report_schedule_without_cookie_returns_401(client):
    response = await client.get("/settings/report-schedule")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_update_report_schedule_without_cookie_returns_401(client):
    response = await client.patch(
        "/settings/report-schedule", json={"send_hour": 8, "send_minute": 0}
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


# --- GET /settings/report-schedule ------------------------------------------


async def test_get_report_schedule_returns_the_seeded_default_converted_to_dhaka_local_time(
    client, seed_user
):
    await _login_as_admin(client, seed_user)

    response = await client.get("/settings/report-schedule")

    assert response.status_code == 200
    body = response.json()
    # Seeded default is 01:00 UTC = 07:00 Asia/Dhaka (UTC+6).
    assert body["send_hour"] == 7
    assert body["send_minute"] == 0
    assert body["updated_by_user_id"] is None


# --- PATCH /settings/report-schedule -----------------------------------------


async def test_patch_report_schedule_updates_it_and_a_follow_up_get_reflects_the_new_value(
    client, seed_user
):
    await _login_as_admin(client, seed_user)

    response = await client.patch(
        "/settings/report-schedule", json={"send_hour": 8, "send_minute": 30}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["send_hour"] == 8
    assert body["send_minute"] == 30
    assert body["updated_by_user_id"] is not None

    follow_up = await client.get("/settings/report-schedule")
    assert follow_up.json()["send_hour"] == 8
    assert follow_up.json()["send_minute"] == 30


async def test_patch_report_schedule_with_an_out_of_range_value_returns_422_and_is_unchanged(
    client, seed_user
):
    await _login_as_admin(client, seed_user)

    response = await client.patch(
        "/settings/report-schedule", json={"send_hour": 25, "send_minute": 0}
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"

    session_factory = create_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            text("SELECT send_hour_utc, send_minute_utc FROM report_schedules")
        )
        send_hour_utc, send_minute_utc = result.one()
    assert send_hour_utc == 1
    assert send_minute_utc == 0
