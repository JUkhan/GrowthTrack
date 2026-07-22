import uuid
from datetime import UTC, datetime

import pytest

from adapters.persistence.database import create_session_factory
from adapters.persistence.notifications import SqlAlchemyMessageTemplateRepository
from api.main import app
from api.notifications.routes import get_whatsapp_sender
from domain.models import MessageTemplate
from ports.whatsapp import SendResult, WhatsAppSendError


class _FakeWhatsAppSender:
    def __init__(self, fail_for: set[str] | None = None) -> None:
        self._fail_for = fail_for or set()
        self.sent: list[tuple[str, str, dict]] = []

    async def send_template_message(self, to_number, content_sid, content_variables):
        self.sent.append((to_number, content_sid, content_variables))
        if to_number in self._fail_for:
            raise WhatsAppSendError(code="21610", message="21610: recipient opted out")
        return SendResult(provider_message_sid=f"SM-{to_number}")


@pytest.fixture
def fake_whatsapp_sender():
    sender = _FakeWhatsAppSender()
    app.dependency_overrides[get_whatsapp_sender] = lambda: sender
    yield sender
    del app.dependency_overrides[get_whatsapp_sender]


async def _seed_template(
    name: str = "Target Revision Notice", variable_slots: list[str] | None = None
) -> MessageTemplate:
    template = MessageTemplate(
        id=uuid.uuid4(),
        name=name,
        twilio_content_sid="HXabc123",
        variable_slots=variable_slots if variable_slots is not None else ["team_name"],
        body_preview_template="{team_name}",
        created_at=datetime.now(UTC),
    )
    session_factory = create_session_factory()
    async with session_factory() as session:
        await SqlAlchemyMessageTemplateRepository(session).add(template)
        await session.commit()
    return template


async def _login_as_admin(client, seed_user, username: str = "admin") -> None:
    _, password = await seed_user(username=username)
    response = await client.post("/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200


async def _create_team(client, name: str = "North Zone") -> str:
    response = await client.post("/teams", json={"name": name})
    assert response.status_code == 201
    return response.json()["id"]


async def _create_opted_in_user(client, mobile: str, team_id: str, name: str = "Karim") -> str:
    response = await client.post(
        "/users", json={"name": name, "mobile": mobile, "role": "sales_user", "team_id": team_id}
    )
    assert response.status_code == 201
    user_id = response.json()["id"]
    consent = await client.post(f"/users/{user_id}/opt-in-consent")
    assert consent.status_code == 201
    return user_id


# --- Auth enforcement (AD-8) --------------------------------------------------


async def test_list_message_templates_without_cookie_returns_401(client):
    response = await client.get("/message-templates")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_resolve_recipients_without_cookie_returns_401(client):
    response = await client.post("/notifications/resolve-recipients", json={})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_compose_and_send_without_cookie_returns_401(client):
    response = await client.post(
        "/notifications",
        json={"template_id": str(uuid.uuid4()), "variable_values": {}},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_create_message_template_without_cookie_returns_401(client):
    response = await client.post(
        "/message-templates",
        json={
            "name": "No Auth Notice",
            "twilio_content_sid": "HXabc",
            "variable_slots": [],
            "body_preview_template": "Static body",
        },
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_update_message_template_without_cookie_returns_401(client):
    response = await client.patch(
        f"/message-templates/{uuid.uuid4()}",
        json={
            "name": "No Auth Notice",
            "twilio_content_sid": "HXabc",
            "variable_slots": [],
            "body_preview_template": "Static body",
        },
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


# --- GET /message-templates ------------------------------------------------------


async def test_list_message_templates_returns_seeded_templates(client, seed_user):
    await _login_as_admin(client, seed_user)
    template = await _seed_template("Listed Notice")

    response = await client.get("/message-templates")

    assert response.status_code == 200
    body = response.json()
    matching = next(row for row in body if row["id"] == str(template.id))
    assert matching["name"] == "Listed Notice"
    assert matching["variable_slots"] == ["team_name"]
    assert matching["twilio_content_sid"] == "HXabc123"


# --- POST /message-templates -------------------------------------------------------


async def test_create_message_template_succeeds_and_appears_in_a_subsequent_list(
    client, seed_user
):
    await _login_as_admin(client, seed_user)

    response = await client.post(
        "/message-templates",
        json={
            "name": "Created Notice",
            "twilio_content_sid": "HXcreated",
            "variable_slots": ["team_name", "new_target"],
            "body_preview_template": "{team_name}: {new_target}",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Created Notice"
    assert body["twilio_content_sid"] == "HXcreated"
    assert body["variable_slots"] == ["team_name", "new_target"]

    list_response = await client.get("/message-templates")
    assert any(row["id"] == body["id"] for row in list_response.json())


async def test_create_message_template_with_a_duplicate_name_returns_409(client, seed_user):
    await _login_as_admin(client, seed_user)
    await _seed_template("Duplicate Route Notice")

    response = await client.post(
        "/message-templates",
        json={
            "name": "Duplicate Route Notice",
            "twilio_content_sid": "HXother",
            "variable_slots": [],
            "body_preview_template": "Static body",
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "template_name_taken"


async def test_create_message_template_with_a_blank_variable_slot_returns_422(client, seed_user):
    await _login_as_admin(client, seed_user)

    response = await client.post(
        "/message-templates",
        json={
            "name": "Blank Slot Notice",
            "twilio_content_sid": "HXblank",
            "variable_slots": ["team_name", "   "],
            "body_preview_template": "{team_name}",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_template_fields"


# --- PATCH /message-templates/{id} -------------------------------------------------


async def test_update_message_template_succeeds_and_change_is_reflected(client, seed_user):
    await _login_as_admin(client, seed_user)
    template = await _seed_template("Pre Update Notice", ["team_name"])

    response = await client.patch(
        f"/message-templates/{template.id}",
        json={
            "name": "Post Update Notice",
            "twilio_content_sid": "HXupdated",
            "variable_slots": ["new_target"],
            "body_preview_template": "{new_target}",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Post Update Notice"
    assert body["twilio_content_sid"] == "HXupdated"
    assert body["variable_slots"] == ["new_target"]

    list_response = await client.get("/message-templates")
    matching = next(row for row in list_response.json() if row["id"] == str(template.id))
    assert matching["name"] == "Post Update Notice"


async def test_update_message_template_on_a_nonexistent_id_returns_404(client, seed_user):
    await _login_as_admin(client, seed_user)

    response = await client.patch(
        f"/message-templates/{uuid.uuid4()}",
        json={
            "name": "Ghost Notice",
            "twilio_content_sid": "HXghost",
            "variable_slots": [],
            "body_preview_template": "Static body",
        },
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


# --- POST /notifications/resolve-recipients --------------------------------------


async def test_resolve_recipients_reports_dedupe_and_ineligible_counts_separately(
    client, seed_user
):
    await _login_as_admin(client, seed_user)
    team_id = await _create_team(client)
    opted_in = await _create_opted_in_user(client, "+8801700001001", team_id, "Opted In")
    # Not opted in — created but consent never granted.
    not_opted_in = (
        await client.post(
            "/users",
            json={
                "name": "Not Opted",
                "mobile": "+8801700001002",
                "role": "sales_user",
                "team_id": team_id,
            },
        )
    ).json()["id"]

    response = await client.post(
        "/notifications/resolve-recipients",
        json={"user_ids": [opted_in, not_opted_in], "team_ids": [], "recipient_list_ids": []},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["selected_count"] == 2
    assert body["overlap_count"] == 0
    assert body["ineligible_count"] == 1
    assert body["unique_count"] == 1


async def test_resolve_recipients_with_no_selections_returns_all_zero(client, seed_user):
    await _login_as_admin(client, seed_user)

    response = await client.post(
        "/notifications/resolve-recipients",
        json={"user_ids": [], "team_ids": [], "recipient_list_ids": []},
    )

    assert response.status_code == 200
    assert response.json() == {
        "selected_count": 0,
        "unique_count": 0,
        "overlap_count": 0,
        "ineligible_count": 0,
    }


# --- POST /notifications ----------------------------------------------------------


async def test_compose_and_send_succeeds_and_is_reflected_on_the_dashboard_tile(
    client, seed_user, fake_whatsapp_sender
):
    await _login_as_admin(client, seed_user)
    team_id = await _create_team(client)
    user_id = await _create_opted_in_user(client, "+8801700001003", team_id)
    template = await _seed_template("Send Notice", ["team_name"])

    response = await client.post(
        "/notifications",
        json={
            "template_id": str(template.id),
            "variable_values": {"team_name": "Team B"},
            "user_ids": [user_id],
            "team_ids": [],
            "recipient_list_ids": [],
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert len(body["outcomes"]) == 1
    assert body["outcomes"][0]["status"] == "sending"
    assert body["outcomes"][0]["recipient_user_id"] == user_id
    assert len(fake_whatsapp_sender.sent) == 1

    status_response = await client.get("/dashboard/notification-status")
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "sending"


async def test_compose_and_send_records_a_whatsapp_rejection_as_failed_not_a_500(
    client, seed_user
):
    await _login_as_admin(client, seed_user)
    team_id = await _create_team(client)
    mobile = "+8801700001004"
    user_id = await _create_opted_in_user(client, mobile, team_id)
    template = await _seed_template("Reject Notice", [])
    fake_sender = _FakeWhatsAppSender(fail_for={mobile})
    app.dependency_overrides[get_whatsapp_sender] = lambda: fake_sender

    try:
        response = await client.post(
            "/notifications",
            json={
                "template_id": str(template.id),
                "variable_values": {},
                "user_ids": [user_id],
                "team_ids": [],
                "recipient_list_ids": [],
            },
        )
    finally:
        del app.dependency_overrides[get_whatsapp_sender]

    assert response.status_code == 201
    body = response.json()
    assert body["outcomes"][0]["status"] == "failed"
    assert body["outcomes"][0]["failure_reason"] == "21610: recipient opted out"


async def test_compose_and_send_with_zero_recipients_returns_422(
    client, seed_user, fake_whatsapp_sender
):
    await _login_as_admin(client, seed_user)
    template = await _seed_template("Empty Notice", [])

    response = await client.post(
        "/notifications",
        json={
            "template_id": str(template.id),
            "variable_values": {},
            "user_ids": [],
            "team_ids": [],
            "recipient_list_ids": [],
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "no_recipients_selected"


async def test_compose_and_send_with_an_unknown_template_returns_404(
    client, seed_user, fake_whatsapp_sender
):
    await _login_as_admin(client, seed_user)
    team_id = await _create_team(client)
    user_id = await _create_opted_in_user(client, "+8801700001005", team_id)

    response = await client.post(
        "/notifications",
        json={
            "template_id": str(uuid.uuid4()),
            "variable_values": {},
            "user_ids": [user_id],
            "team_ids": [],
            "recipient_list_ids": [],
        },
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_compose_and_send_with_mismatched_variable_values_returns_422(
    client, seed_user, fake_whatsapp_sender
):
    await _login_as_admin(client, seed_user)
    team_id = await _create_team(client)
    user_id = await _create_opted_in_user(client, "+8801700001006", team_id)
    template = await _seed_template("Mismatch Notice", ["team_name"])

    response = await client.post(
        "/notifications",
        json={
            "template_id": str(template.id),
            "variable_values": {},  # missing required "team_name"
            "user_ids": [user_id],
            "team_ids": [],
            "recipient_list_ids": [],
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_variable_values"


# --- GET /dashboard/notification-status -------------------------------------------


async def test_notification_status_without_cookie_returns_401(client):
    response = await client.get("/dashboard/notification-status")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_notification_status_before_any_send_returns_null_status(client, seed_user):
    await _login_as_admin(client, seed_user)

    response = await client.get("/dashboard/notification-status")

    assert response.status_code == 200
    assert response.json() == {"status": None, "updated_at": None}
