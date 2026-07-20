"""SQLAlchemy ``OptInConsent`` model + repository implementation.

``opt_in_consents`` is a history table — one User can have many rows over
time (one per grant), but at most one *active* (non-revoked) row at any
moment, enforced by ``ix_opt_in_consents_user_id_active_uq`` (a partial
unique index on ``user_id WHERE revoked_at IS NULL``).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import cast

from sqlalchemy import DateTime, ForeignKey, String, select, update
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from adapters.persistence.database import Base
from domain.models import OptInConsent
from ports.consent import OptInConsentRepository


class OptInConsentModel(Base):
    __tablename__ = "opt_in_consents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    mobile: Mapped[str] = mapped_column(String, nullable=False)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


def _to_domain(row: OptInConsentModel) -> OptInConsent:
    return OptInConsent(
        id=row.id,
        user_id=row.user_id,
        mobile=row.mobile,
        granted_at=row.granted_at,
        revoked_at=row.revoked_at,
    )


class SqlAlchemyOptInConsentRepository(OptInConsentRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_active(self, user_id: uuid.UUID) -> OptInConsent | None:
        stmt = select(OptInConsentModel).where(
            OptInConsentModel.user_id == user_id, OptInConsentModel.revoked_at.is_(None)
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return _to_domain(row) if row is not None else None

    async def get_active_by_user_ids(
        self, user_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, OptInConsent]:
        if not user_ids:
            return {}
        stmt = select(OptInConsentModel).where(
            OptInConsentModel.user_id.in_(user_ids), OptInConsentModel.revoked_at.is_(None)
        )
        result = await self._session.execute(stmt)
        return {row.user_id: _to_domain(row) for row in result.scalars().all()}

    async def grant(self, user_id: uuid.UUID, mobile: str) -> OptInConsent:
        model = OptInConsentModel(
            id=uuid.uuid4(),
            user_id=user_id,
            mobile=mobile,
            granted_at=datetime.now(UTC),
            revoked_at=None,
        )
        self._session.add(model)
        # Explicit flush: Story 3.2's real code-review-caught bug was exactly
        # a missing flush before a later plain INSERT/UPDATE that doesn't
        # trigger ORM autoflush — be explicit here too rather than relying on
        # autoflush timing.
        await self._session.flush()
        return _to_domain(model)

    async def revoke_active(self, user_id: uuid.UUID) -> bool:
        stmt = (
            update(OptInConsentModel)
            .where(OptInConsentModel.user_id == user_id, OptInConsentModel.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )
        result = cast(CursorResult, await self._session.execute(stmt))
        return result.rowcount > 0
