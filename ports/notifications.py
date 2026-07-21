"""Repository interfaces for ``MessageTemplate``/``Notification``/
``NotificationDelivery`` persistence (Story 4.1, CAP-4).

``Any``-typed convention (``ports/recipient_lists.py``'s style) — ports
cannot import ``domain`` (AD-1: dependency direction is inward only).
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from typing import Any


class MessageTemplateRepository(ABC):
    @abstractmethod
    async def list_active(self) -> list[Any]: ...

    @abstractmethod
    async def get_by_id(self, template_id: uuid.UUID) -> Any | None: ...

    @abstractmethod
    async def get_by_name(self, name: str) -> Any | None:
        """No Template-management UI exists yet (approval happens in
        Twilio/Meta's console) — this and ``add`` exist for
        ``scripts/seed_demo_data.py``'s idempotent-by-name seeding, the same
        shape ``TeamRepository``/``RecipientListRepository`` already use."""
        ...

    @abstractmethod
    async def add(self, template: Any) -> None: ...


class NotificationRepository(ABC):
    @abstractmethod
    async def add(self, notification: Any, targets: list[Any]) -> None:
        """Bundles both writes into one call — deliberate, small deviation
        from the split-call convention RecipientListRepository.add()/
        .replace_members() uses: both rows are always written together
        atomically, with no independent-update case, unlike list
        membership."""
        ...


class NotificationDeliveryRepository(ABC):
    @abstractmethod
    async def bulk_create(self, rows: list[Any]) -> None: ...

    @abstractmethod
    async def claim_for_dispatch(self, delivery_id: uuid.UUID) -> bool:
        """Atomic conditional claim (AD-2): only transitions
        queued/failed_retryable -> sending. Returns ``False`` — without
        mutating anything — when the row wasn't in a claimable state,
        meaning a crashed/racing retry can never re-dispatch against the
        same row."""
        ...

    @abstractmethod
    async def update_after_send(
        self,
        delivery_id: uuid.UUID,
        status: Any,
        provider_message_sid: str | None,
        failure_reason: str | None,
    ) -> None: ...

    @abstractmethod
    async def most_recent_status_summary(self) -> Any | None:
        """Aggregate outcome of the most-recently-created Notification,
        system-wide (across Manual and Scheduled) — worst-status-wins
        across all of that Notification's delivery rows, so a single late
        failure or success can't misrepresent the rest. Feeds the
        Dashboard's notification-status tile (AC #8)."""
        ...
