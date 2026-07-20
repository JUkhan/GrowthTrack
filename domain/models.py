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
