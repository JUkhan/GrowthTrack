"""Plain domain entities.

No SQLAlchemy/framework types here (AD-1) — ``adapters/persistence`` maps
these to ORM models, it never the other way around.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum


class Role(StrEnum):
    ADMINISTRATOR = "administrator"
    SALES_USER = "sales_user"
    MANAGER = "manager"


class UserStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class TeamStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class RecipientListKind(StrEnum):
    GROUP = "group"
    CHANNEL = "channel"


class RecipientListStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class ThemePreference(StrEnum):
    LIGHT = "light"
    DARK = "dark"
    SYSTEM = "system"


class ImportRunStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class NotificationType(StrEnum):
    MANUAL = "manual"
    SCHEDULED = "scheduled"


class DeliveryStatus(StrEnum):
    QUEUED = "queued"
    SENDING = "sending"
    DELIVERED = "delivered"
    RETRYING = "retrying"
    FAILED = "failed"
    # Story 4.3-only outcome — included now so AD-2's claim SQL can name it
    # in its WHERE clause without a later schema migration.
    FAILED_RETRYABLE = "failed_retryable"


class TargetType(StrEnum):
    USER = "user"
    TEAM = "team"
    RECIPIENT_LIST = "recipient_list"


class WebhookOutcome(StrEnum):
    """The two-value vocabulary a Twilio status-callback's five-value
    ``MessageStatus`` gets mapped down to (Story 4.3, AD-1) — keeps
    Twilio-specific strings out of domain/ signatures.
    ``queued``/``sent`` intermediate statuses map to neither (our own
    SENDING already represents "in flight") and are log-and-ignored at the
    route layer instead."""

    DELIVERED = "delivered"
    FAILURE = "failure"


@dataclass
class User:
    id: uuid.UUID
    # Optional: an Administrator (Epic 1) has both; a Sales User/Manager
    # roster entry (Story 3.1) has neither — they never authenticate to the
    # portal (Addendum A5). See domain/recipients.py's Role-Handling Matrix.
    username: str | None
    hashed_password: str | None
    role: Role
    status: UserStatus
    version: int
    created_at: datetime
    name: str | None = None
    mobile: str | None = None
    team_id: uuid.UUID | None = None
    failed_login_count: int = 0
    locked_until: datetime | None = None
    theme_preference: ThemePreference = ThemePreference.SYSTEM


@dataclass
class PasswordResetToken:
    id: uuid.UUID
    user_id: uuid.UUID
    token_hash: str
    expires_at: datetime
    used_at: datetime | None
    created_at: datetime


@dataclass
class AuditLogEntry:
    id: uuid.UUID
    actor_user_id: uuid.UUID | None
    action: str
    entity_type: str | None
    entity_id: uuid.UUID | None
    details: dict | None
    created_at: datetime


@dataclass
class Team:
    id: uuid.UUID
    name: str
    status: TeamStatus = TeamStatus.ACTIVE
    version: int = 1


@dataclass
class RecipientList:
    id: uuid.UUID
    name: str
    kind: RecipientListKind
    status: RecipientListStatus = RecipientListStatus.ACTIVE
    version: int = 1
    member_user_ids: list[uuid.UUID] = field(default_factory=list)


@dataclass
class OptInConsent:
    id: uuid.UUID
    user_id: uuid.UUID
    mobile: str
    granted_at: datetime
    revoked_at: datetime | None = None


@dataclass
class SalesData:
    id: uuid.UUID
    date: date  # business date, not datetime — see Dev Notes on timezone handling
    team_id: uuid.UUID
    sales_amount: Decimal
    achievement_pct: Decimal
    growth_pct: Decimal


@dataclass
class BrandPerformance:
    id: uuid.UUID
    external_brand_id: str
    brand_name: str
    sales: Decimal
    rank: int
    growth_pct: Decimal


@dataclass
class Doctor:
    id: uuid.UUID
    external_doctor_id: str
    name: str
    territory: str
    priority: int


@dataclass
class ImportRun:
    id: uuid.UUID
    correlation_id: uuid.UUID
    started_at: datetime
    status: ImportRunStatus
    completed_at: datetime | None = None
    records_processed: int = 0
    records_rejected: int = 0


@dataclass
class MessageTemplate:
    id: uuid.UUID
    name: str
    twilio_content_sid: str
    # Order is the positional mapping to Twilio's content_variables keys
    # ("1", "2", ...) — see adapters/whatsapp_twilio/sender.py.
    variable_slots: list[str]
    # Human-readable text with {slot_name} placeholders (Python str.format),
    # used purely for the composer's local live-preview render — Twilio's
    # Content API has no "render me the text" call.
    body_preview_template: str
    created_at: datetime


@dataclass
class Notification:
    id: uuid.UUID
    notification_type: NotificationType
    template_id: uuid.UUID
    created_at: datetime
    # None for a Scheduled Notification (Story 4.2) — a system-triggered
    # background job has no human actor to attribute the send to.
    created_by_user_id: uuid.UUID | None = None


@dataclass
class NotificationTarget:
    id: uuid.UUID
    notification_id: uuid.UUID
    target_type: TargetType
    target_id: uuid.UUID


@dataclass
class NotificationDelivery:
    id: uuid.UUID
    notification_id: uuid.UUID
    # Denormalized onto the delivery row (not just joined from Notification)
    # because Postgres partial-unique-index predicates can't reference a
    # joined table (AD-2).
    notification_type: NotificationType
    recipient_user_id: uuid.UUID
    # Stays None for Manual sends — only Scheduled/Story 4.2 populates it.
    operational_day: date | None
    status: DeliveryStatus
    attempt_count: int
    provider_message_sid: str | None
    failure_reason: str | None
    created_at: datetime
    updated_at: datetime
    # The exact Twilio content_variables this row was (or will be) sent
    # with — persisted so a retry can resend the identical values, since
    # the live dispatch call itself never stores them anywhere else.
    content_variables: dict[str, str] = field(default_factory=dict)


@dataclass
class NotificationStatusSummary:
    # Aggregate view of the most recent Notification's overall outcome —
    # worst-status-wins across all of its NotificationDelivery rows (AC #8),
    # so one late per-recipient failure/success can't hide the others.
    status: DeliveryStatus
    updated_at: datetime
