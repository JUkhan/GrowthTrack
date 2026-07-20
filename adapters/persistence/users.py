"""SQLAlchemy ``User`` model + repository implementation."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, select, text, update
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from adapters.persistence.advisory_locks import (
    ADMINISTRATOR_REMOVAL_LOCK_KEY,
    BOOTSTRAP_LOCK_KEY,
)
from adapters.persistence.database import Base
from domain.models import Role, ThemePreference, User, UserStatus
from ports.users import UserRepository


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    # Nullable (Story 3.1): a Sales User/Manager roster entry has neither —
    # they never authenticate to the portal (Addendum A5).
    username: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    hashed_password: Mapped[str | None] = mapped_column(String, nullable=True)
    role: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    # Uniqueness enforced by a partial index (ix_users_mobile_active_uq,
    # WHERE status = 'active') rather than a column-level constraint — a
    # soft-deleted User's mobile is reusable by a new User (code review of
    # Story 3.1, migration 17eb25555c26).
    mobile: Mapped[str | None] = mapped_column(String, nullable=True)
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teams.id"), nullable=True
    )
    failed_login_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    theme_preference: Mapped[str] = mapped_column(String, nullable=False, default="system")


def _to_domain(row: UserModel) -> User:
    return User(
        id=row.id,
        username=row.username,
        hashed_password=row.hashed_password,
        role=Role(row.role),
        status=UserStatus(row.status),
        version=row.version,
        created_at=row.created_at,
        name=row.name,
        mobile=row.mobile,
        team_id=row.team_id,
        failed_login_count=row.failed_login_count,
        locked_until=row.locked_until,
        theme_preference=ThemePreference(row.theme_preference),
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
                name=user.name,
                mobile=user.mobile,
                team_id=user.team_id,
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
        # Transaction-scoped: releases automatically on commit/rollback.
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(:key)"), {"key": BOOTSTRAP_LOCK_KEY}
        )

    async def acquire_administrator_removal_lock(self) -> None:
        # Transaction-scoped: releases automatically on commit/rollback.
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(:key)"), {"key": ADMINISTRATOR_REMOVAL_LOCK_KEY}
        )

    async def increment_failed_login_count(self, user_id: uuid.UUID) -> int:
        # Atomic UPDATE ... RETURNING, not read-then-write — two concurrent
        # failed attempts must both land, or the count under-reports and
        # delays lockout.
        stmt = (
            update(UserModel)
            .where(UserModel.id == user_id)
            .values(failed_login_count=UserModel.failed_login_count + 1)
            .returning(UserModel.failed_login_count)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def lock_until(self, user_id: uuid.UUID, until: datetime) -> None:
        stmt = update(UserModel).where(UserModel.id == user_id).values(locked_until=until)
        await self._session.execute(stmt)

    async def clear_lockout(self, user_id: uuid.UUID) -> None:
        stmt = (
            update(UserModel)
            .where(UserModel.id == user_id)
            .values(failed_login_count=0, locked_until=None)
        )
        await self._session.execute(stmt)

    async def update_password(self, user_id: uuid.UUID, hashed_password: str) -> None:
        stmt = (
            update(UserModel)
            .where(UserModel.id == user_id)
            .values(hashed_password=hashed_password, version=UserModel.version + 1)
        )
        await self._session.execute(stmt)

    async def update_theme_preference(self, user_id: uuid.UUID, theme_preference: str) -> None:
        stmt = (
            update(UserModel)
            .where(UserModel.id == user_id)
            .values(theme_preference=theme_preference)
        )
        await self._session.execute(stmt)

    async def get_by_mobile(self, mobile: str) -> User | None:
        # Active-only (code review of Story 3.1): a soft-deleted User's
        # mobile is reusable, matching ix_users_mobile_active_uq.
        stmt = select(UserModel).where(
            UserModel.mobile == mobile, UserModel.status == UserStatus.ACTIVE.value
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return _to_domain(row) if row is not None else None

    async def list_all(self) -> list[User]:
        stmt = select(UserModel).order_by(UserModel.created_at)
        result = await self._session.execute(stmt)
        return [_to_domain(row) for row in result.scalars().all()]

    async def update_directory_fields(
        self, user_id: uuid.UUID, name: str, mobile: str, team_id: uuid.UUID
    ) -> None:
        stmt = (
            update(UserModel)
            .where(UserModel.id == user_id)
            .values(name=name, mobile=mobile, team_id=team_id, version=UserModel.version + 1)
        )
        await self._session.execute(stmt)

    async def deactivate(self, user_id: uuid.UUID) -> None:
        stmt = (
            update(UserModel)
            .where(UserModel.id == user_id)
            .values(status=UserStatus.INACTIVE.value, version=UserModel.version + 1)
        )
        await self._session.execute(stmt)
