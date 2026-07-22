"""Manual Notification compose/send (Story 4.1, CAP-4).

``RecipientResolutionService.resolve`` is the one function AD-2 requires be
shared by both the send path (``ManualNotificationService.compose_and_send``)
and the composer's live-preview endpoint — both call sites must see
identical resolution output, so the live preview never promises a bigger
number than what actually gets sent.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from domain.models import (
    AuditLogEntry,
    DeliveryStatus,
    MessageTemplate,
    Notification,
    NotificationDelivery,
    NotificationStatusSummary,
    NotificationTarget,
    NotificationType,
    RecipientListStatus,
    TargetType,
    TeamStatus,
    UserStatus,
    WebhookOutcome,
)
from ports.audit import AuditLogRepository
from ports.consent import OptInConsentRepository
from ports.notifications import (
    MessageTemplateRepository,
    NotificationDeliveryRepository,
    NotificationRepository,
)
from ports.recipient_lists import RecipientListRepository
from ports.teams import TeamRepository
from ports.users import UserRepository
from ports.whatsapp import WhatsAppSender, WhatsAppSendError

logger = logging.getLogger(__name__)


class TemplateNotFound(Exception):
    """Raised when no MessageTemplate exists for a given id."""


class TemplateNameTaken(Exception):
    """Raised when a MessageTemplate name is already in use by a different
    MessageTemplate (Story 4.5) — mirrors TeamNameTaken's shape
    (domain/recipients.py)."""


class InvalidTemplateFields(Exception):
    """Raised when a MessageTemplate's name/Content SID/preview text is
    blank (after stripping) or a variable slot is blank — distinct from
    InvalidVariableValues, which is about a composed *message*'s values
    not matching a template's slots, not the template record itself."""


class InvalidVariableValues(Exception):
    """Raised when the composed message's variable values don't exactly
    match the template's variable_slots (missing or extra keys) — enforces
    AC #4's "variable slots only, no free-form body text"."""


class NoRecipientsSelected(Exception):
    """Raised when recipient resolution yields zero sendable recipients
    (AC #2) — mapped to a 422 by the route."""


@dataclass
class ResolvedRecipients:
    # Raw picker selections/expansions before any filtering.
    selected_count: int
    # Cross-mechanism duplicates only (e.g. individually listed AND a member
    # of a selected Team) — never conflated with ineligible_count.
    overlap_count: int
    # Resolved-but-excluded for being inactive or not opt-in-consented.
    ineligible_count: int
    # Final sendable count: selected_count - overlap_count - ineligible_count.
    unique_count: int
    recipient_user_ids: list[uuid.UUID]


class RecipientResolutionService:
    def __init__(
        self,
        users: UserRepository,
        recipient_lists: RecipientListRepository,
        consents: OptInConsentRepository,
        teams: TeamRepository,
    ) -> None:
        self._users = users
        self._recipient_lists = recipient_lists
        self._consents = consents
        self._teams = teams

    async def resolve(
        self,
        user_ids: list[uuid.UUID],
        team_ids: list[uuid.UUID],
        recipient_list_ids: list[uuid.UUID],
    ) -> ResolvedRecipients:
        expanded_ids: list[uuid.UUID] = list(user_ids)
        for team_id in team_ids:
            # A Team the frontend picker would never offer (it filters to
            # active-only) can still reach here via stale client state or a
            # direct API call — never expand a since-archived Team's
            # members as sendable.
            team = await self._teams.get_by_id(team_id)
            if team is None or team.status != TeamStatus.ACTIVE:
                continue
            members = await self._users.list_by_team_id(team_id)
            expanded_ids.extend(member.id for member in members)
        for recipient_list_id in recipient_list_ids:
            recipient_list = await self._recipient_lists.get_by_id(recipient_list_id)
            if recipient_list is None or recipient_list.status != RecipientListStatus.ACTIVE:
                continue
            expanded_ids.extend(recipient_list.member_user_ids)

        selected_count = len(expanded_ids)
        deduped_ids = list(dict.fromkeys(expanded_ids))
        overlap_count = selected_count - len(deduped_ids)

        resolved_users = await self._users.get_many_by_ids(deduped_ids)
        users_by_id = {user.id: user for user in resolved_users}
        active_consent_by_user = await self._consents.get_active_by_user_ids(deduped_ids)

        sendable_ids: list[uuid.UUID] = []
        ineligible_count = 0
        for user_id in deduped_ids:
            user = users_by_id.get(user_id)
            if (
                user is None
                or user.status != UserStatus.ACTIVE
                or user.mobile is None
                or user_id not in active_consent_by_user
            ):
                ineligible_count += 1
                continue
            sendable_ids.append(user_id)

        return ResolvedRecipients(
            selected_count=selected_count,
            overlap_count=overlap_count,
            ineligible_count=ineligible_count,
            unique_count=len(sendable_ids),
            recipient_user_ids=sendable_ids,
        )


def _status_after_failed_attempt(
    attempt_count_after_increment: int, max_retry_attempts: int
) -> DeliveryStatus:
    """Shared decision function for both of this story's failure sources —
    a synchronous send-time rejection and an asynchronous webhook-reported
    failure — so the retry budget is counted consistently regardless of
    which path discovered the failure (Story 4.3). ``FAILED_RETRYABLE``
    while attempts remain, terminal ``FAILED`` once the budget is
    exhausted (AC #5 — left Failed, not re-claimed by this Send Event)."""
    if attempt_count_after_increment < 1 + max_retry_attempts:
        return DeliveryStatus.FAILED_RETRYABLE
    return DeliveryStatus.FAILED


@dataclass
class DeliveryOutcome:
    recipient_user_id: uuid.UUID
    # "sending" (accepted by Twilio), "failed_retryable" (rejected, retry
    # budget remains), or "failed" (rejected, terminal) are produced here
    # — delivered is Story 4.3's webhook-driven transition only.
    status: DeliveryStatus
    failure_reason: str | None


@dataclass
class ComposeResult:
    notification_id: uuid.UUID
    outcomes: list[DeliveryOutcome]


async def dispatch_deliveries(
    deliveries: NotificationDeliveryRepository,
    whatsapp: WhatsAppSender,
    delivery_rows: list[NotificationDelivery],
    content_variables_by_recipient: dict[uuid.UUID, dict[str, str]],
    template_content_sid: str,
    recipients_by_id: dict[uuid.UUID, Any],
    max_retry_attempts: int,
) -> list[DeliveryOutcome]:
    """Per-recipient claim/send/fail loop shared by
    ``ManualNotificationService.compose_and_send`` and
    ``ScheduledReportService.run_daily_report`` — extracted rather than
    duplicated (Story 4.2 Task 4 Step 8) since the claim-for-dispatch /
    broad-exception-guard / outcome-recording shape is non-trivial and any
    divergence between two independent copies would be a latent bug.
    """
    outcomes: list[DeliveryOutcome] = []

    async def _fail(row: NotificationDelivery, reason: str) -> None:
        # Every per-recipient failure mode — Twilio rejection, a
        # transport/timeout error, or a missing recipient record — must
        # land here rather than propagate: an uncaught exception here
        # would abort the loop, and since this whole call is one
        # uncommitted transaction, that would roll back the
        # already-recorded outcomes (and Notification/audit rows) for
        # every recipient processed so far, even though Twilio may have
        # already sent them a real message.
        status = _status_after_failed_attempt(row.attempt_count + 1, max_retry_attempts)
        await deliveries.update_after_send(row.id, status, None, reason)
        logger.warning(
            "notification delivery attempt failed",
            extra={
                "delivery_id": str(row.id),
                "recipient_user_id": str(row.recipient_user_id),
                "attempt_count": row.attempt_count + 1,
                "status": status.value,
                "reason": reason,
            },
        )
        outcomes.append(
            DeliveryOutcome(
                recipient_user_id=row.recipient_user_id,
                status=status,
                failure_reason=reason,
            )
        )

    for row in delivery_rows:
        claimed = await deliveries.claim_for_dispatch(row.id)
        if not claimed:
            continue  # pragma: no cover - unreachable for a freshly-created row

        recipient = recipients_by_id.get(row.recipient_user_id)
        if recipient is None:
            await _fail(row, "recipient no longer exists")
            continue

        try:
            result = await whatsapp.send_template_message(
                to_number=recipient.mobile,
                content_sid=template_content_sid,
                content_variables=content_variables_by_recipient[row.recipient_user_id],
            )
        except WhatsAppSendError as exc:
            await _fail(row, exc.message)
            continue
        except Exception as exc:
            # Deliberately broad: see _fail's docstring above.
            await _fail(row, str(exc))
            continue

        await deliveries.update_after_send(
            row.id, DeliveryStatus.SENDING, result.provider_message_sid, None
        )
        logger.info(
            "notification delivery attempt sent",
            extra={
                "delivery_id": str(row.id),
                "recipient_user_id": str(row.recipient_user_id),
                "attempt_count": row.attempt_count + 1,
                "provider_message_sid": result.provider_message_sid,
            },
        )
        outcomes.append(
            DeliveryOutcome(
                recipient_user_id=row.recipient_user_id,
                status=DeliveryStatus.SENDING,
                failure_reason=None,
            )
        )

    return outcomes


class MessageTemplateDirectoryService:
    """MessageTemplate CRUD (Story 4.5, FR-13) — mirrors
    ``TeamDirectoryService``'s shape (domain/recipients.py), minus
    version/conflict handling: this entity has no optimistic-concurrency
    column, deliberately (see the story's Dev Notes). Records an
    already-approved template's identifiers only — never submits or
    approves anything with Twilio/Meta on the Administrator's behalf."""

    def __init__(self, templates: MessageTemplateRepository, audit_log: AuditLogRepository) -> None:
        self._templates = templates
        self._audit_log = audit_log

    async def create_template(
        self,
        name: str,
        twilio_content_sid: str,
        variable_slots: list[str],
        body_preview_template: str,
        actor_user_id: uuid.UUID,
    ) -> MessageTemplate:
        name = name.strip()
        twilio_content_sid = twilio_content_sid.strip()
        body_preview_template = body_preview_template.strip()
        if not name or not twilio_content_sid or not body_preview_template:
            raise InvalidTemplateFields()
        if any(not slot.strip() for slot in variable_slots):
            raise InvalidTemplateFields()
        if len(set(variable_slots)) != len(variable_slots):
            raise InvalidTemplateFields()

        if await self._templates.get_by_name(name) is not None:
            raise TemplateNameTaken()

        template = MessageTemplate(
            id=uuid.uuid4(),
            name=name,
            twilio_content_sid=twilio_content_sid,
            variable_slots=variable_slots,
            body_preview_template=body_preview_template,
            created_at=datetime.now(UTC),
        )
        await self._templates.add(template)
        await self._audit_log.add(
            AuditLogEntry(
                id=uuid.uuid4(),
                actor_user_id=actor_user_id,
                action="message_template.created",
                entity_type="MessageTemplate",
                entity_id=template.id,
                details={"name": name, "twilio_content_sid": twilio_content_sid},
                created_at=template.created_at,
            )
        )
        return template

    async def update_template(
        self,
        template_id: uuid.UUID,
        name: str,
        twilio_content_sid: str,
        variable_slots: list[str],
        body_preview_template: str,
        actor_user_id: uuid.UUID,
    ) -> MessageTemplate:
        target = await self._templates.get_by_id(template_id)
        if target is None:
            raise TemplateNotFound()

        name = name.strip()
        twilio_content_sid = twilio_content_sid.strip()
        body_preview_template = body_preview_template.strip()
        if not name or not twilio_content_sid or not body_preview_template:
            raise InvalidTemplateFields()
        if any(not slot.strip() for slot in variable_slots):
            raise InvalidTemplateFields()
        if len(set(variable_slots)) != len(variable_slots):
            raise InvalidTemplateFields()

        existing = await self._templates.get_by_name(name)
        if existing is not None and existing.id != template_id:
            raise TemplateNameTaken()

        updated = await self._templates.update(
            template_id, name, twilio_content_sid, variable_slots, body_preview_template
        )
        if not updated:
            raise TemplateNotFound()
        await self._audit_log.add(
            AuditLogEntry(
                id=uuid.uuid4(),
                actor_user_id=actor_user_id,
                action="message_template.updated",
                entity_type="MessageTemplate",
                entity_id=template_id,
                details={
                    "name": name,
                    "twilio_content_sid": twilio_content_sid,
                    "variable_slots": variable_slots,
                    "body_preview_template": body_preview_template,
                },
                created_at=datetime.now(UTC),
            )
        )
        refreshed = await self._templates.get_by_id(template_id)
        if refreshed is None:
            raise TemplateNotFound()
        return refreshed


class ManualNotificationService:
    def __init__(
        self,
        templates: MessageTemplateRepository,
        notifications: NotificationRepository,
        deliveries: NotificationDeliveryRepository,
        users: UserRepository,
        whatsapp: WhatsAppSender,
        resolution: RecipientResolutionService,
        audit_log: AuditLogRepository,
        max_retry_attempts: int,
    ) -> None:
        self._templates = templates
        self._notifications = notifications
        self._deliveries = deliveries
        self._users = users
        self._whatsapp = whatsapp
        self._resolution = resolution
        self._audit_log = audit_log
        self._max_retry_attempts = max_retry_attempts

    async def compose_and_send(
        self,
        template_id: uuid.UUID,
        variable_values: dict[str, str],
        user_ids: list[uuid.UUID],
        team_ids: list[uuid.UUID],
        recipient_list_ids: list[uuid.UUID],
        actor_user_id: uuid.UUID,
    ) -> ComposeResult:
        template = await self._templates.get_by_id(template_id)
        if template is None:
            raise TemplateNotFound()

        if set(variable_values.keys()) != set(template.variable_slots):
            raise InvalidVariableValues()
        if any(not value.strip() for value in variable_values.values()):
            raise InvalidVariableValues()

        resolved = await self._resolution.resolve(user_ids, team_ids, recipient_list_ids)
        if resolved.unique_count == 0:
            raise NoRecipientsSelected()

        now = datetime.now(UTC)
        notification = Notification(
            id=uuid.uuid4(),
            notification_type=NotificationType.MANUAL,
            template_id=template_id,
            created_by_user_id=actor_user_id,
            created_at=now,
        )
        # The raw picker selections, not the expanded members (AD-4).
        targets = [
            NotificationTarget(
                id=uuid.uuid4(),
                notification_id=notification.id,
                target_type=TargetType.USER,
                target_id=user_id,
            )
            for user_id in user_ids
        ] + [
            NotificationTarget(
                id=uuid.uuid4(),
                notification_id=notification.id,
                target_type=TargetType.TEAM,
                target_id=team_id,
            )
            for team_id in team_ids
        ] + [
            NotificationTarget(
                id=uuid.uuid4(),
                notification_id=notification.id,
                target_type=TargetType.RECIPIENT_LIST,
                target_id=recipient_list_id,
            )
            for recipient_list_id in recipient_list_ids
        ]

        await self._notifications.add(notification, targets)
        await self._audit_log.add(
            AuditLogEntry(
                id=uuid.uuid4(),
                actor_user_id=actor_user_id,
                action="notification.sent",
                entity_type="Notification",
                entity_id=notification.id,
                details={
                    "template_id": str(template_id),
                    "recipient_count": resolved.unique_count,
                },
                created_at=now,
            )
        )

        # Positional string keys ("1", "2", ...), not named — variable_slots'
        # order is what maps a named slot to Twilio's positional key.
        content_variables = {
            str(index): variable_values[slot]
            for index, slot in enumerate(template.variable_slots, start=1)
        }

        delivery_rows = [
            NotificationDelivery(
                id=uuid.uuid4(),
                notification_id=notification.id,
                notification_type=NotificationType.MANUAL,
                recipient_user_id=recipient_user_id,
                operational_day=None,
                status=DeliveryStatus.QUEUED,
                attempt_count=0,
                provider_message_sid=None,
                failure_reason=None,
                created_at=now,
                updated_at=now,
                # Persisted so a retry can resend the exact values this row
                # was originally composed with (Story 4.3).
                content_variables=content_variables,
            )
            for recipient_user_id in resolved.recipient_user_ids
        ]
        await self._deliveries.bulk_create(delivery_rows)

        recipients_by_id = {
            user.id: user for user in await self._users.get_many_by_ids(resolved.recipient_user_ids)
        }

        # Small manual-send batch sizes — looped synchronously (Twilio
        # allows 80 msg/sec per sender, far above this path's volume;
        # NFR-1's 500+ concurrent dispatch figure is Story 4.2's scope).
        # Same content_variables dict for every recipient (Manual has no
        # per-recipient variation, unlike ScheduledReportService's
        # per-territory doctor section).
        content_variables_by_recipient = {
            recipient_user_id: content_variables
            for recipient_user_id in resolved.recipient_user_ids
        }
        outcomes = await dispatch_deliveries(
            deliveries=self._deliveries,
            whatsapp=self._whatsapp,
            delivery_rows=delivery_rows,
            content_variables_by_recipient=content_variables_by_recipient,
            template_content_sid=template.twilio_content_sid,
            recipients_by_id=recipients_by_id,
            max_retry_attempts=self._max_retry_attempts,
        )

        return ComposeResult(notification_id=notification.id, outcomes=outcomes)


class WebhookApplyResult(StrEnum):
    """For the webhook route to log — not to branch business logic on
    (Story 4.3)."""

    APPLIED = "applied"
    SUPERSEDED = "superseded"
    REJECTED_NON_MONOTONIC = "rejected_non_monotonic"


# Rank table for AC #3's monotonic-transition check. DELIVERED/RETRYING/
# FAILED/FAILED_RETRYABLE share the same top tier — a webhook can move a
# delivery *into* any one of them from QUEUED/SENDING, but never between
# them (e.g. DELIVERED -> FAILURE is rejected, and a repeated same-status
# callback is correctly a no-op rather than wasted work).
_STATUS_RANK: dict[DeliveryStatus, int] = {
    DeliveryStatus.QUEUED: 0,
    DeliveryStatus.SENDING: 1,
    DeliveryStatus.DELIVERED: 2,
    DeliveryStatus.RETRYING: 2,
    DeliveryStatus.FAILED: 2,
    DeliveryStatus.FAILED_RETRYABLE: 2,
}


class DeliveryStatusWebhookService:
    """Applies a Twilio delivery-status callback to the matching
    ``NotificationDelivery`` row (Story 4.3, AC #1-#3). No audit-log entry
    is written — mirrors ``domain/ingestion.py``'s precedent: an inbound
    provider callback has no human actor (AD-7 governs administrative
    actions only). Plain structured logging is used instead, at the route
    layer."""

    def __init__(self, deliveries: NotificationDeliveryRepository, max_retry_attempts: int) -> None:
        self._deliveries = deliveries
        self._max_retry_attempts = max_retry_attempts

    async def apply_status_update(
        self, provider_message_sid: str, outcome: WebhookOutcome, failure_reason: str | None
    ) -> WebhookApplyResult:
        row = await self._deliveries.get_by_provider_message_sid(provider_message_sid)
        if row is None:
            # The SID doesn't match any row's *current* SID (AC #2) —
            # provider_message_sid is overwritten on every retry attempt,
            # so this means the payload belongs to an attempt that has
            # since been superseded by a retry.
            return WebhookApplyResult.SUPERSEDED

        if outcome == WebhookOutcome.DELIVERED:
            candidate = DeliveryStatus.DELIVERED
        else:
            # row.attempt_count is already the post-increment value from
            # the original dispatch (update_after_send incremented it at
            # send time) — this webhook call must not increment it again.
            candidate = _status_after_failed_attempt(row.attempt_count, self._max_retry_attempts)

        if _STATUS_RANK[candidate] <= _STATUS_RANK[row.status]:
            return WebhookApplyResult.REJECTED_NON_MONOTONIC

        await self._deliveries.update_status_from_webhook(row.id, candidate, failure_reason)
        return WebhookApplyResult.APPLIED


class NotificationStatusService:
    """Read-only — the Dashboard tile's own dependency footprint, separate
    from ManualNotificationService's write-path dependencies (Twilio, audit
    log) that a read has no business requiring."""

    def __init__(self, deliveries: NotificationDeliveryRepository) -> None:
        self._deliveries = deliveries

    async def latest_notification_status(self) -> NotificationStatusSummary | None:
        # "Most recent send system-wide" (AC #8) — Scheduled doesn't exist
        # yet, so today this is always the latest Manual send. Aggregated
        # worst-status-wins across all of that Notification's deliveries so
        # one late failure/success can't misrepresent the rest.
        return await self._deliveries.most_recent_status_summary()
