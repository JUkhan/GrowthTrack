"""SQLAlchemy ``AuditLogEntry`` model + repository implementation (AD-7).

Generic by design: Epic 3's directory CRUD and Epic 4's schedule changes
reuse this exact table with different ``action``/``entity_type`` values.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from adapters.persistence.database import Base
from domain.models import AuditLogEntry
from ports.audit import AuditLogRepository


class AuditLogEntryModel(Base):
    __tablename__ = "audit_log_entries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    action: Mapped[str] = mapped_column(String, nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String, nullable=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SqlAlchemyAuditLogRepository(AuditLogRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, entry: AuditLogEntry) -> None:
        self._session.add(
            AuditLogEntryModel(
                id=entry.id,
                actor_user_id=entry.actor_user_id,
                action=entry.action,
                entity_type=entry.entity_type,
                entity_id=entry.entity_id,
                details=entry.details,
                created_at=entry.created_at,
            )
        )
