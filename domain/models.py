"""Plain domain entities.

No SQLAlchemy/framework types here (AD-1) — ``adapters/persistence`` maps
these to ORM models, it never the other way around.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class Role(StrEnum):
    ADMINISTRATOR = "administrator"
    SALES_USER = "sales_user"
    MANAGER = "manager"


class UserStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class ThemePreference(StrEnum):
    LIGHT = "light"
    DARK = "dark"
    SYSTEM = "system"


@dataclass
class User:
    id: uuid.UUID
    username: str
    hashed_password: str
    role: Role
    status: UserStatus
    version: int
    created_at: datetime
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
