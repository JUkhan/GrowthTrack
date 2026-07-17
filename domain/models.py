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


@dataclass
class User:
    id: uuid.UUID
    username: str
    hashed_password: str
    role: Role
    status: UserStatus
    version: int
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
