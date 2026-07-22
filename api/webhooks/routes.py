"""Inbound Twilio delivery-status webhook (Story 4.3, AD-3).

Deliberately does not depend on ``get_current_user`` — this is an
unauthenticated, internet-facing provider callback (``docker/nginx/
nginx.conf``'s own comment on the ``/webhooks/`` block already calls this
out), authenticated instead by Twilio's request signature below. This is a
deliberate, documented exception to AD-8's "every route depends on
get_current_user" convention, not an oversight.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from adapters.persistence.notifications import SqlAlchemyNotificationDeliveryRepository
from adapters.whatsapp_twilio.webhook_verifier import categorize_message_status, verify_signature
from api.auth.dependencies import get_db
from config import get_settings
from domain.notifications import DeliveryStatusWebhookService, WebhookApplyResult

logger = logging.getLogger(__name__)

webhooks_router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@webhooks_router.post("/twilio/status", status_code=204)
async def twilio_status_webhook(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> Response:
    settings = get_settings()
    form = await request.form()
    params = {key: str(value) for key, value in form.items()}
    signature = request.headers.get("X-Twilio-Signature", "")

    # Twilio signs the exact public POST URL it called — never
    # str(request.url), which behind Nginx would be the internal
    # http://<container> URL, not what Twilio actually signed (Dev Notes).
    url = f"{settings.webhook_public_base_url.rstrip('/')}/webhooks/twilio/status"

    # AC #1: verification gates everything downstream, including the
    # repository construction below — an invalid signature must not touch
    # the database at all.
    if not verify_signature(url, params, signature, settings.twilio_auth_token):
        logger.warning(
            "twilio webhook: invalid signature, rejected",
            extra={"message_sid": params.get("MessageSid", "")},
        )
        return Response(status_code=403)

    message_sid = params.get("MessageSid", "")
    twilio_status = params.get("MessageStatus", "")
    # Twilio's documented status-callback payload only ever includes
    # ErrorCode, not ErrorMessage — no ErrorMessage fallback to attempt.
    failure_reason = params.get("ErrorCode") or None

    outcome = categorize_message_status(twilio_status)
    if outcome is None:
        # An intermediate queued/sent status, or an unrecognized value —
        # no domain-level transition applies (Task 4/5's Dev Notes).
        logger.info(
            "twilio webhook: no domain transition for status, ignored",
            extra={"message_sid": message_sid, "twilio_status": twilio_status},
        )
        return Response(status_code=204)

    service = DeliveryStatusWebhookService(
        SqlAlchemyNotificationDeliveryRepository(session),
        max_retry_attempts=settings.notification_max_retry_attempts,
    )
    result = await service.apply_status_update(message_sid, outcome, failure_reason)

    # superseded/rejected_non_monotonic are expected outcomes, not errors.
    log = logger.info if result == WebhookApplyResult.APPLIED else logger.warning
    log(
        "twilio webhook processed",
        extra={"message_sid": message_sid, "twilio_status": twilio_status, "result": result.value},
    )

    # All three outcomes are valid terminal states for this request, not
    # error branches needing rollback.
    await session.commit()
    return Response(status_code=204)
