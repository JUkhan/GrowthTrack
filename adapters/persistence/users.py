"""SQLAlchemy ``User`` model + repository implementation."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, select, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from adapters.persistence.database import Base
from domain.models import Role, User, UserStatus
from ports.users import UserRepository


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    username: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


def _to_domain(row: UserModel) -> User:
    return User(
        id=row.id,
        username=row.username,
        hashed_password=row.hashed_password,
        role=Role(row.role),
        status=UserStatus(row.status),
        version=row.version,
        created_at=row.created_at,
    )


class SqlAlchemyUserRepository(UserRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_username(self, username: str) -> User | None:
        stmt = select(UserModel).where(UserModel.username == username)
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return _to_domain(row) if row is not None else None

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        row = await self._session.get(UserModel, user_id)
        return _to_domain(row) if row is not None else None

    async def add(self, user: User) -> None:
        self._session.add(
            UserModel(
                id=user.id,
                username=user.username,
                hashed_password=user.hashed_password,
                role=user.role.value,
                status=user.status.value,
                version=user.version,
                created_at=user.created_at,
            )
        )

    async def has_any_administrator(self) -> bool:
        # Not filtered by status (active/inactive) — see Story 1.2 Dev Notes'
        # rationale for gating bootstrap on any Administrator row at all.
        stmt = text("SELECT EXISTS(SELECT 1 FROM users WHERE role = :role)")
        result = await self._session.execute(stmt, {"role": Role.ADMINISTRATOR.value})
        return bool(result.scalar())

    async def count_active_administrators(self) -> int:
        stmt = text("SELECT COUNT(*) FROM users WHERE role = :role AND status = :status")
        result = await self._session.execute(
            stmt, {"role": Role.ADMINISTRATOR.value, "status": UserStatus.ACTIVE.value}
        )
        return int(result.scalar_one())

    async def acquire_bootstrap_lock(self) -> None:
        # Fixed, arbitrary 32-bit key reserved solely for first-run bootstrap
        # serialization (Story 1.2) — do not reuse this key elsewhere.
        # Transaction-scoped: releases automatically on commit/rollback.
        await self._session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": 890217364})
