"""Outbound WhatsApp-send interface (AD-5's Structural Seed).

Named for by the architecture spine but unbuilt until this story —
``adapters/whatsapp_twilio/sender.py`` is its first implementation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class SendResult:
    provider_message_sid: str


class WhatsAppSendError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class WhatsAppSender(ABC):
    @abstractmethod
    async def send_template_message(
        self, to_number: str, content_sid: str, content_variables: dict[str, str]
    ) -> SendResult:
        """Sends a pre-approved Content API template message. Raises
        ``WhatsAppSendError`` on any provider-side rejection."""
        ...
