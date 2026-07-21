"""Twilio-backed ``WhatsAppSender`` (Story 4.1).

Twilio's ``messages.create`` is a blocking/synchronous call (``requests``
under the hood) — every port method elsewhere in this codebase is
``async def``, and calling a blocking network call directly inside one
would stall FastAPI's event loop for the full round-trip of every send.
Wrapped in ``asyncio.to_thread`` rather than treated as a sub-100ms
CPU-bound sync-in-async case (the precedent ``PwdlibPasswordHasher` sets).
"""

from __future__ import annotations

import asyncio
import json

from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

from config import get_settings
from ports.whatsapp import SendResult, WhatsAppSender, WhatsAppSendError


class TwilioWhatsAppSender(WhatsAppSender):
    def __init__(self) -> None:
        settings = get_settings()
        self._client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
        self._from_number = settings.twilio_whatsapp_number

    async def send_template_message(
        self, to_number: str, content_sid: str, content_variables: dict[str, str]
    ) -> SendResult:
        try:
            # Content API only — body/media_url are excluded when
            # content_sid is set (AC #4's "pre-approved template only").
            message = await asyncio.to_thread(
                self._client.messages.create,
                content_sid=content_sid,
                content_variables=json.dumps(content_variables),
                to=f"whatsapp:{to_number}",
                from_=f"whatsapp:{self._from_number}",
            )
        except TwilioRestException as exc:
            raise WhatsAppSendError(code=str(exc.code), message=f"{exc.code}: {exc.msg}") from exc

        return SendResult(provider_message_sid=message.sid)
