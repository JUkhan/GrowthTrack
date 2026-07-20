import uuid
from collections.abc import AsyncIterator, Callable, Coroutine
from datetime import UTC, datetime

import pytest
from httpx2 import ASGITransport, AsyncClient
from sqlalchemy import text

from adapters.persistence.database import create_engine, create_session_factory
from adapters.persistence.users import SqlAlchemyUserRepository
from api.main import app
from domain.models import Role, User, UserStatus
from ports.auth import PwdlibPasswordHasher


@pytest.fixture(autouse=True)
async def _clean_tables() -> AsyncIterator[None]:
    """Every test that touches the DB starts from an empty users/audit_log_entries table."""
    engine = create_engine()
    async with engine.begin() as conn:
        # DELETE, not TRUNCATE: the runtime app role (AD-5's least-privilege
        # split) has DML grants only, no TRUNCATE/DDL rights.
        # password_reset_tokens.user_id carries a ForeignKey("users.id"), so
        # it must be deleted before users or the FK constraint rejects the delete.
        await conn.execute(text("DELETE FROM audit_log_entries"))
        await conn.execute(text("DELETE FROM password_reset_tokens"))
        # recipient_list_members has an FK to users.id, same reasoning
        # password_reset_tokens is deleted before users.
        await conn.execute(text("DELETE FROM recipient_list_members"))
        await conn.execute(text("DELETE FROM users"))
        await conn.execute(text("DELETE FROM revoked_tokens"))
        # Staging tables and sales_data reference import_runs/teams, so
        # those must be deleted first (FK-dependency order).
        await conn.execute(text("DELETE FROM staging_sales_data"))
        await conn.execute(text("DELETE FROM staging_brand_performance"))
        await conn.execute(text("DELETE FROM staging_doctors"))
        await conn.execute(text("DELETE FROM sales_data"))
        await conn.execute(text("DELETE FROM import_runs"))
        await conn.execute(text("DELETE FROM teams"))
        await conn.execute(text("DELETE FROM recipient_lists"))
        await conn.execute(text("DELETE FROM doctors"))
        await conn.execute(text("DELETE FROM brand_performance"))
    yield


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest.fixture
def seed_user() -> Callable[..., Coroutine[None, None, tuple[User, str]]]:
    """Seeds a User row directly through the repository (Dev Notes: no signup
    endpoint exists yet — Story 1.2 builds that). Returns (user, plaintext_password)."""

    async def _seed(
        username: str = "admin",
        password: str = "correct-horse-battery-staple",
        role: Role = Role.ADMINISTRATOR,
        status: UserStatus = UserStatus.ACTIVE,
    ) -> tuple[User, str]:
        session_factory = create_session_factory()
        hasher = PwdlibPasswordHasher()
        user = User(
            id=uuid.uuid4(),
            username=username,
            hashed_password=hasher.hash(password),
            role=role,
            status=status,
            version=1,
            created_at=datetime.now(UTC),
        )
        async with session_factory() as session:
            await SqlAlchemyUserRepository(session).add(user)
            await session.commit()
        return user, password

    return _seed
