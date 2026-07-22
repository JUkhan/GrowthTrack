import uuid
from datetime import UTC, datetime

from twilio.request_validator import RequestValidator

from adapters.persistence.database import create_session_factory
from adapters.persistence.notifications import (
    SqlAlchemyMessageTemplateRepository,
    SqlAlchemyNotificationDeliveryRepository,
    SqlAlchemyNotificationRepository,
)
from adapters.persistence.users import SqlAlchemyUserRepository
from config import get_settings
from domain.models import (
    DeliveryStatus,
    MessageTemplate,
    Notification,
    NotificationDelivery,
    NotificationType,
    Role,
    User,
    UserStatus,
)

_WEBHOOK_URL = "/webhooks/twilio/status"


def _signed_headers(params: dict[str, str]) -> dict[str, str]:
    settings = get_settings()
    url = f"{settings.webhook_public_base_url.rstrip('/')}{_WEBHOOK_URL}"
    signature = RequestValidator(settings.twilio_auth_token).compute_signature(url, params)
    return {"X-Twilio-Signature": signature}


async def _seed_recipient_user(mobile: str) -> User:
    user = User(
        id=uuid.uuid4(),
        username=None,
        hashed_password=None,
        role=Role.SALES_USER,
        status=UserStatus.ACTIVE,
        version=1,
        created_at=datetime.now(UTC),
        name="Karim",
        mobile=mobile,
    )
    session_factory = create_session_factory()
    async with session_factory() as session:
        await SqlAlchemyUserRepository(session).add(user)
        await session.commit()
    return user


async def _seed_template(name: str) -> MessageTemplate:
    template = MessageTemplate(
        id=uuid.uuid4(),
        name=name,
        twilio_content_sid="HXabc123",
        variable_slots=[],
        body_preview_template="Static body",
        created_at=datetime.now(UTC),
    )
    session_factory = create_session_factory()
    async with session_factory() as session:
        await SqlAlchemyMessageTemplateRepository(session).add(template)
        await session.commit()
    return template


async def _seed_delivery(
    provider_message_sid: str,
    status: DeliveryStatus = DeliveryStatus.SENDING,
    attempt_count: int = 1,
) -> NotificationDelivery:
    user = await _seed_recipient_user(f"+88017{uuid.uuid4().int % 10**8:08d}")
    template = await _seed_template(f"Webhook Notice {uuid.uuid4()}")
    notification = Notification(
        id=uuid.uuid4(),
        notification_type=NotificationType.MANUAL,
        template_id=template.id,
        created_by_user_id=user.id,
        created_at=datetime.now(UTC),
    )
    now = datetime.now(UTC)
    delivery = NotificationDelivery(
        id=uuid.uuid4(),
        notification_id=notification.id,
        notification_type=NotificationType.MANUAL,
        recipient_user_id=user.id,
        operational_day=None,
        status=status,
        attempt_count=attempt_count,
        provider_message_sid=provider_message_sid,
        failure_reason=None,
        created_at=now,
        updated_at=now,
    )
    session_factory = create_session_factory()
    async with session_factory() as session:
        await SqlAlchemyNotificationRepository(session).add(notification, [])
        await SqlAlchemyNotificationDeliveryRepository(session).bulk_create([delivery])
        await session.commit()
    return delivery


async def _read_status(provider_message_sid: str) -> str:
    session_factory = create_session_factory()
    async with session_factory() as session:
        row = await SqlAlchemyNotificationDeliveryRepository(
            session
        ).get_by_provider_message_sid(provider_message_sid)
        return row.status.value if row else "not_found"


# --- Valid signature ------------------------------------------------------------


async def test_valid_signature_with_delivered_status_advances_status(client):
    await _seed_delivery("SM-webhook-delivered", status=DeliveryStatus.SENDING)
    params = {"MessageSid": "SM-webhook-delivered", "MessageStatus": "delivered"}

    response = await client.post(_WEBHOOK_URL, data=params, headers=_signed_headers(params))

    assert response.status_code == 204
    status = await _read_status("SM-webhook-delivered")
    assert status == "delivered"


async def test_valid_signature_with_failed_status_advances_to_failed_retryable(client):
    await _seed_delivery("SM-webhook-failed", status=DeliveryStatus.SENDING, attempt_count=1)
    params = {
        "MessageSid": "SM-webhook-failed",
        "MessageStatus": "failed",
        "ErrorCode": "30008",
    }

    response = await client.post(_WEBHOOK_URL, data=params, headers=_signed_headers(params))

    assert response.status_code == 204
    status = await _read_status("SM-webhook-failed")
    assert status == "failed_retryable"


# --- Invalid signature ------------------------------------------------------------


async def test_invalid_signature_returns_403_and_does_not_touch_the_row(client):
    await _seed_delivery("SM-webhook-invalid-sig", status=DeliveryStatus.SENDING)
    params = {"MessageSid": "SM-webhook-invalid-sig", "MessageStatus": "delivered"}

    response = await client.post(
        _WEBHOOK_URL, data=params, headers={"X-Twilio-Signature": "not-a-real-signature"}
    )

    assert response.status_code == 403
    status = await _read_status("SM-webhook-invalid-sig")
    assert status == "sending"


# --- Unknown SID (superseded) ------------------------------------------------------


async def test_unknown_sid_returns_204_and_does_not_raise(client):
    params = {"MessageSid": "SM-never-seen", "MessageStatus": "delivered"}

    response = await client.post(_WEBHOOK_URL, data=params, headers=_signed_headers(params))

    assert response.status_code == 204


# --- Backward transition (rejected, non-monotonic) ---------------------------------


async def test_backward_transition_returns_204_but_status_is_unchanged(client):
    await _seed_delivery("SM-webhook-backward", status=DeliveryStatus.DELIVERED, attempt_count=1)
    params = {
        "MessageSid": "SM-webhook-backward",
        "MessageStatus": "failed",
        "ErrorCode": "30008",
    }

    response = await client.post(_WEBHOOK_URL, data=params, headers=_signed_headers(params))

    assert response.status_code == 204
    status = await _read_status("SM-webhook-backward")
    assert status == "delivered"


# --- Intermediate status (queued/sent) ---------------------------------------------


async def test_intermediate_status_returns_204_without_error(client):
    await _seed_delivery("SM-webhook-queued", status=DeliveryStatus.SENDING)
    params = {"MessageSid": "SM-webhook-queued", "MessageStatus": "sent"}

    response = await client.post(_WEBHOOK_URL, data=params, headers=_signed_headers(params))

    assert response.status_code == 204
    status = await _read_status("SM-webhook-queued")
    assert status == "sending"
