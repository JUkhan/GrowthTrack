import uuid
from datetime import UTC, datetime, timedelta

from adapters.persistence.database import create_session_factory
from adapters.persistence.password_reset import SqlAlchemyPasswordResetTokenRepository
from domain.models import PasswordResetToken


def _make_token(user_id: uuid.UUID, token_hash: str = "some-hash") -> PasswordResetToken:
    now = datetime.now(UTC)
    return PasswordResetToken(
        id=uuid.uuid4(),
        user_id=user_id,
        token_hash=token_hash,
        expires_at=now + timedelta(minutes=60),
        used_at=None,
        created_at=now,
    )


async def test_add_and_get_by_hash_round_trip(seed_user):
    user, _ = await seed_user(username="admin")
    session_factory = create_session_factory()
    token = _make_token(user.id, token_hash="a-real-token-hash")

    async with session_factory() as session:
        await SqlAlchemyPasswordResetTokenRepository(session).add(token)
        await session.commit()

    async with session_factory() as session:
        found = await SqlAlchemyPasswordResetTokenRepository(session).get_by_hash(
            "a-real-token-hash"
        )

    assert found is not None
    assert found.id == token.id
    assert found.user_id == user.id
    assert found.used_at is None


async def test_get_by_hash_for_an_unknown_hash_returns_none():
    session_factory = create_session_factory()

    async with session_factory() as session:
        found = await SqlAlchemyPasswordResetTokenRepository(session).get_by_hash("no-such-hash")

    assert found is None


async def test_mark_used_sets_used_at_and_is_reflected_on_a_subsequent_lookup(seed_user):
    user, _ = await seed_user(username="admin")
    session_factory = create_session_factory()
    token = _make_token(user.id, token_hash="another-token-hash")

    async with session_factory() as session:
        repo = SqlAlchemyPasswordResetTokenRepository(session)
        await repo.add(token)
        await session.commit()

    used_at = datetime.now(UTC)
    async with session_factory() as session:
        await SqlAlchemyPasswordResetTokenRepository(session).mark_used(token.id, used_at)
        await session.commit()

    async with session_factory() as session:
        found = await SqlAlchemyPasswordResetTokenRepository(session).get_by_hash(
            "another-token-hash"
        )

    assert found is not None
    assert found.used_at is not None
