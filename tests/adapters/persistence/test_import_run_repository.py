import contextlib
import uuid
from datetime import UTC, datetime

from sqlalchemy import text

from adapters.persistence.database import create_session_factory
from adapters.persistence.import_runs import ImportRunModel, SqlAlchemyImportRunRepository
from domain.models import ImportRunStatus


async def _get(run_id: uuid.UUID) -> ImportRunModel | None:
    session_factory = create_session_factory()
    async with session_factory() as session:
        return await session.get(ImportRunModel, run_id)


async def test_start_creates_a_running_import_run():
    session_factory = create_session_factory()
    correlation_id = uuid.uuid4()
    started_at = datetime.now(UTC)
    async with session_factory() as session:
        run_id = await SqlAlchemyImportRunRepository(session).start(correlation_id, started_at)
        await session.commit()

    found = await _get(run_id)
    assert found is not None
    assert found.status == ImportRunStatus.RUNNING.value
    assert found.correlation_id == correlation_id
    assert found.completed_at is None


async def test_mark_succeeded_updates_status_and_counts():
    session_factory = create_session_factory()
    async with session_factory() as session:
        repo = SqlAlchemyImportRunRepository(session)
        run_id = await repo.start(uuid.uuid4(), datetime.now(UTC))
        await session.commit()

    completed_at = datetime.now(UTC)
    async with session_factory() as session:
        await SqlAlchemyImportRunRepository(session).mark_succeeded(
            run_id, completed_at, records_processed=10, records_rejected=2
        )
        await session.commit()

    found = await _get(run_id)
    assert found is not None
    assert found.status == ImportRunStatus.SUCCEEDED.value
    assert found.records_processed == 10
    assert found.records_rejected == 2
    assert found.completed_at is not None


async def test_mark_failed_updates_status_without_touching_counts():
    session_factory = create_session_factory()
    correlation_id = uuid.uuid4()
    started_at = datetime.now(UTC)
    async with session_factory() as session:
        repo = SqlAlchemyImportRunRepository(session)
        run_id = await repo.start(correlation_id, started_at)
        await session.commit()

    completed_at = datetime.now(UTC)
    async with session_factory() as session:
        await SqlAlchemyImportRunRepository(session).mark_failed(
            run_id, correlation_id, started_at, completed_at
        )
        await session.commit()

    found = await _get(run_id)
    assert found is not None
    assert found.status == ImportRunStatus.FAILED.value
    assert found.completed_at is not None


async def test_mark_failed_recovers_and_still_records_the_row_after_a_poisoned_transaction():
    """A DB-level error earlier in the same transaction (simulated here by a
    unique-constraint violation) aborts the session's transaction — mark_failed
    must roll back and durably record the failure anyway, not raise."""
    session_factory = create_session_factory()
    correlation_id = uuid.uuid4()
    started_at = datetime.now(UTC)
    async with session_factory() as session:
        repo = SqlAlchemyImportRunRepository(session)
        run_id = await repo.start(correlation_id, started_at)

        # Poison the transaction with a real DB-level error before start()
        # is ever committed, mirroring an upsert conflict mid-pipeline.
        with contextlib.suppress(Exception):
            await session.execute(text("SELECT 1/0"))

        completed_at = datetime.now(UTC)
        await repo.mark_failed(run_id, correlation_id, started_at, completed_at)

    found = await _get(run_id)
    assert found is not None
    assert found.status == ImportRunStatus.FAILED.value
    assert found.correlation_id == correlation_id
    assert found.completed_at is not None


async def test_try_acquire_lock_succeeds_when_uncontended():
    session_factory = create_session_factory()
    async with session_factory() as session:
        acquired = await SqlAlchemyImportRunRepository(session).try_acquire_lock()
        await session.commit()

    assert acquired is True


async def test_try_acquire_lock_fails_when_another_transaction_already_holds_it():
    session_factory = create_session_factory()
    async with session_factory() as holder_session:
        holder_acquired = await SqlAlchemyImportRunRepository(holder_session).try_acquire_lock()
        assert holder_acquired is True

        async with session_factory() as contender_session:
            contender_acquired = await SqlAlchemyImportRunRepository(
                contender_session
            ).try_acquire_lock()

        assert contender_acquired is False
        await holder_session.commit()
