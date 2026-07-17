import uuid
from datetime import UTC, datetime

from adapters.persistence.database import create_session_factory
from adapters.persistence.sessions import SqlAlchemyRevokedTokenRepository


async def _is_revoked(jti: uuid.UUID) -> bool:
    session_factory = create_session_factory()
    async with session_factory() as session:
        return await SqlAlchemyRevokedTokenRepository(session).is_revoked(jti)


async def _revoke(jti: uuid.UUID) -> None:
    session_factory = create_session_factory()
    async with session_factory() as session:
        await SqlAlchemyRevokedTokenRepository(session).revoke(jti, datetime.now(UTC))
        await session.commit()


async def test_is_revoked_returns_false_for_an_unrevoked_unknown_jti():
    assert await _is_revoked(uuid.uuid4()) is False


async def test_is_revoked_returns_true_after_revoke():
    jti = uuid.uuid4()

    await _revoke(jti)

    assert await _is_revoked(jti) is True


async def test_two_distinct_jtis_revoked_independently_do_not_cross_contaminate():
    revoked_jti = uuid.uuid4()
    other_jti = uuid.uuid4()

    await _revoke(revoked_jti)

    assert await _is_revoked(revoked_jti) is True
    assert await _is_revoked(other_jti) is False
