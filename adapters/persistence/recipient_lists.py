"""SQLAlchemy ``RecipientList`` model + repository implementation.

``recipient_list_members`` is a pure join table (AD-4: relational join rows,
never a JSON blob) with no independent identity beyond the
(recipient_list_id, user_id) pair — modeled as a Core ``Table``, not a
mapped class, so plain Core ``insert``/``delete``/``select`` statements are
the tool used to touch it, not the ORM.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Column, ForeignKey, Integer, String, Table, delete, insert, select, update
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from adapters.persistence.database import Base
from domain.models import RecipientList, RecipientListKind, RecipientListStatus
from ports.recipient_lists import RecipientListRepository


class RecipientListModel(Base):
    __tablename__ = "recipient_lists"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    # Uniqueness enforced by a partial index (ix_recipient_lists_name_active_uq,
    # WHERE status = 'active'), not a column-level constraint — a
    # soft-deleted list's name is reusable by a new list (same pattern as
    # users.mobile/teams.name, Story 3.1 code review).
    name: Mapped[str] = mapped_column(String, nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


recipient_list_members = Table(
    "recipient_list_members",
    Base.metadata,
    Column(
        "recipient_list_id",
        UUID(as_uuid=True),
        ForeignKey("recipient_lists.id"),
        primary_key=True,
    ),
    Column("user_id", UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True),
)


def _to_domain(row: RecipientListModel, member_user_ids: list[uuid.UUID]) -> RecipientList:
    return RecipientList(
        id=row.id,
        name=row.name,
        kind=RecipientListKind(row.kind),
        status=RecipientListStatus(row.status),
        version=row.version,
        member_user_ids=member_user_ids,
    )


class SqlAlchemyRecipientListRepository(RecipientListRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, recipient_list_id: uuid.UUID) -> RecipientList | None:
        row = await self._session.get(RecipientListModel, recipient_list_id)
        if row is None:
            return None
        return _to_domain(row, await self.get_member_user_ids(recipient_list_id))

    async def get_by_name(self, name: str) -> RecipientList | None:
        # Active-only, mirroring adapters/persistence/teams.py#get_by_name
        # exactly — matches ix_recipient_lists_name_active_uq.
        stmt = select(RecipientListModel).where(
            RecipientListModel.name == name,
            RecipientListModel.status == RecipientListStatus.ACTIVE.value,
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return _to_domain(row, await self.get_member_user_ids(row.id))

    async def add(self, recipient_list_id: uuid.UUID, name: str, kind: RecipientListKind) -> None:
        self._session.add(
            RecipientListModel(
                id=recipient_list_id, name=name, kind=kind.value, status="active", version=1
            )
        )
        # Flushed immediately: create_recipient_list follows this with a
        # replace_members call that INSERTs into recipient_list_members via
        # a plain Core statement, which doesn't trigger ORM autoflush the
        # way a select()/ORM query would — without this, the FK to this
        # not-yet-flushed row fails.
        await self._session.flush()

    async def list_all_full(self) -> list[RecipientList]:
        stmt = select(RecipientListModel).order_by(RecipientListModel.name)
        result = await self._session.execute(stmt)
        rows = result.scalars().all()

        # One bulk query for every list's memberships, grouped in Python —
        # not one get_member_user_ids call per row (the N+1 shape Story
        # 3.1's GET /users route was written to avoid for team_name).
        members_result = await self._session.execute(select(recipient_list_members))
        members_by_list: dict[uuid.UUID, list[uuid.UUID]] = {}
        for recipient_list_id, user_id in members_result.all():
            members_by_list.setdefault(recipient_list_id, []).append(user_id)

        return [_to_domain(row, members_by_list.get(row.id, [])) for row in rows]

    async def update_details(
        self, recipient_list_id: uuid.UUID, name: str, kind: RecipientListKind
    ) -> None:
        stmt = (
            update(RecipientListModel)
            .where(RecipientListModel.id == recipient_list_id)
            .values(name=name, kind=kind.value, version=RecipientListModel.version + 1)
        )
        await self._session.execute(stmt)

    async def deactivate(self, recipient_list_id: uuid.UUID) -> None:
        stmt = (
            update(RecipientListModel)
            .where(RecipientListModel.id == recipient_list_id)
            .values(
                status=RecipientListStatus.INACTIVE.value,
                version=RecipientListModel.version + 1,
            )
        )
        await self._session.execute(stmt)

    async def replace_members(
        self, recipient_list_id: uuid.UUID, user_ids: list[uuid.UUID]
    ) -> None:
        await self._session.execute(
            delete(recipient_list_members).where(
                recipient_list_members.c.recipient_list_id == recipient_list_id
            )
        )
        if user_ids:
            await self._session.execute(
                insert(recipient_list_members),
                [
                    {"recipient_list_id": recipient_list_id, "user_id": user_id}
                    for user_id in user_ids
                ],
            )

    async def get_member_user_ids(self, recipient_list_id: uuid.UUID) -> list[uuid.UUID]:
        stmt = select(recipient_list_members.c.user_id).where(
            recipient_list_members.c.recipient_list_id == recipient_list_id
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
