"""Twilio status-callback signature verification + status mapping (Story
4.3, AD-3).

``twilio.request_validator.RequestValidator`` is used rather than a
hand-rolled HMAC implementation — Twilio's own guidance is explicit that
the SDK-provided validator must be used, not a custom reimplementation
(see the story's Dev Notes/Sources).
"""

from __future__ import annotations

from twilio.request_validator import RequestValidator

from domain.models import WebhookOutcome

# MessageStatus values for an outbound WhatsApp message: queued, sent,
# delivered, undelivered, failed, plus read (WhatsApp/RCS read receipts).
# undelivered carries a carrier-level ErrorCode after Twilio accepted the
# send; failed means Twilio itself rejected the send before it reached the
# carrier. This story treats both identically — no AC asks for the
# distinction. queued/sent are intentionally not forwarded to domain at
# all (our own SENDING status already represents "in flight").
_DELIVERED_STATUSES = frozenset({"delivered", "read"})
_FAILURE_STATUSES = frozenset({"failed", "undelivered"})


def verify_signature(url: str, params: dict[str, str], signature: str, auth_token: str) -> bool:
    return RequestValidator(auth_token).validate(url, params, signature)


def categorize_message_status(twilio_status: str) -> WebhookOutcome | None:
    if twilio_status in _DELIVERED_STATUSES:
        return WebhookOutcome.DELIVERED
    if twilio_status in _FAILURE_STATUSES:
        return WebhookOutcome.FAILURE
    return None
