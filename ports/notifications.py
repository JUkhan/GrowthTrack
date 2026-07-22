"""Repository interfaces for ``MessageTemplate``/``Notification``/
``NotificationDelivery`` persistence (Story 4.1, CAP-4).

``Any``-typed convention (``ports/recipient_lists.py``'s style) — ports
cannot import ``domain`` (AD-1: dependency direction is inward only).
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any


class MessageTemplateRepository(ABC):
    @abstractmethod
    async def list_active(self) -> list[Any]: ...

    @abstractmethod
    async def get_by_id(self, template_id: uuid.UUID) -> Any | None: ...

    @abstractmethod
    async def get_by_name(self, name: str) -> Any | None:
        """Used by ``scripts/seed_demo_data.py``'s idempotent-by-name seeding
        (same shape ``TeamRepository``/``RecipientListRepository`` use) and
        by the Template-management create/edit flow's name-uniqueness check
        (Story 4.5) — approval of the underlying WhatsApp template itself
        still happens entirely in Twilio/Meta's console, never here."""
        ...

    @abstractmethod
    async def add(self, template: Any) -> None: ...

    @abstractmethod
    async def update(
        self,
        template_id: uuid.UUID,
        name: str,
        twilio_content_sid: str,
        variable_slots: list[str],
        body_preview_template: str,
    ) -> bool:
        """Unconditional field update — returns ``False`` if no row matched
        ``template_id`` (not found), ``True`` otherwise. No version/
        conditional-update semantics: unlike ``TeamRepository``/
        ``UserRepository``, ``MessageTemplate`` has no optimistic-concurrency
        column (Story 4.5's deliberate scope decision)."""
        ...


class NotificationRepository(ABC):
    @abstractmethod
    async def add(self, notification: Any, targets: list[Any]) -> None:
        """Bundles both writes into one call — deliberate, small deviation
        from the split-call convention RecipientListRepository.add()/
        .replace_members() uses: both rows are always written together
        atomically, with no independent-update case, unlike list
        membership."""
        ...

    @abstractmethod
    async def try_acquire_daily_report_lock(self) -> bool:
        """Non-blocking advisory lock scoped to the Daily Report scheduled
        send (Story 4.2) — same shape as ``ImportRunRepository.
        try_acquire_lock()``: transaction-scoped, returns ``False`` —
        without mutating anything — when another run already holds it.
        Defense-in-depth against two overlapping scheduler runs; the
        partial unique index on (recipient_user_id, operational_day) is
        the authoritative zero-duplicate-send guarantee (AD-2)."""
        ...

    @abstractmethod
    async def get_by_id(self, notification_id: uuid.UUID) -> Any | None:
        """Used by the retry job (Story 4.3) to find a delivery row's
        parent Notification, and from there its ``template_id``."""
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

    @abstractmethod
    async def get_by_provider_message_sid(self, sid: str) -> Any | None:
        """The webhook's correlation lookup (Story 4.3, AC #2). Doubles as
        the stale/superseded check for free: ``provider_message_sid`` is
        overwritten on every retry attempt (``update_after_send`` always
        sets it), so a payload naming a SID no row currently carries *is*
        the superseded case — returning ``None`` here is that signal."""
        ...

    @abstractmethod
    async def update_status_from_webhook(
        self, delivery_id: uuid.UUID, status: Any, failure_reason: str | None
    ) -> None:
        """Does not touch ``attempt_count`` — unlike ``update_after_send``,
        a webhook status update is not a new send attempt; the attempt was
        already counted when the row was dispatched. Reusing
        ``update_after_send`` here would double-count attempts."""
        ...

    @abstractmethod
    async def list_retry_eligible(self, now: datetime) -> list[Any]:
        """Rows with ``status == 'failed_retryable'`` whose backoff window
        (keyed by ``attempt_count``) has elapsed as of ``now`` (Story 4.3,
        AC #4/#5)."""
        ...
