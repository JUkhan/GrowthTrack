import uuid

from sqlalchemy import select

from adapters.persistence.database import create_session_factory
from adapters.persistence.doctors import DoctorModel, SqlAlchemyDoctorRepository
from domain.models import Doctor


async def _upsert(rows: list[Doctor]) -> None:
    session_factory = create_session_factory()
    async with session_factory() as session:
        await SqlAlchemyDoctorRepository(session).upsert_many(rows)
        await session.commit()


async def _get_by_external_id(external_doctor_id: str) -> DoctorModel | None:
    session_factory = create_session_factory()
    async with session_factory() as session:
        stmt = select(DoctorModel).where(DoctorModel.external_doctor_id == external_doctor_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()


async def test_upsert_many_inserts_a_new_row():
    row = Doctor(
        id=uuid.uuid4(),
        external_doctor_id="D1",
        name="Dr. Smith",
        territory="East",
        priority=1,
    )

    await _upsert([row])

    found = await _get_by_external_id("D1")
    assert found is not None
    assert found.name == "Dr. Smith"


async def test_upsert_many_updates_an_existing_snapshot_row_on_conflict_not_ignoring_it():
    await _upsert(
        [
            Doctor(
                id=uuid.uuid4(),
                external_doctor_id="D1",
                name="Dr. Smith",
                territory="East",
                priority=1,
            )
        ]
    )

    await _upsert(
        [
            Doctor(
                id=uuid.uuid4(),
                external_doctor_id="D1",
                name="Dr. Smith Jr.",
                territory="West",
                priority=2,
            )
        ]
    )

    found = await _get_by_external_id("D1")
    assert found is not None
    assert found.name == "Dr. Smith Jr."
    assert found.territory == "West"
    assert found.priority == 2


async def test_upsert_many_dedupes_a_batch_with_two_rows_sharing_the_same_conflict_key():
    """A single multi-row ON CONFLICT DO UPDATE statement raises if two input
    rows share a conflict key — this must not crash the whole run."""
    stale = Doctor(
        id=uuid.uuid4(), external_doctor_id="D1", name="Dr. Smith", territory="East", priority=1
    )
    corrected = Doctor(
        id=uuid.uuid4(), external_doctor_id="D1", name="Dr. Smith Jr.", territory="West", priority=2
    )

    await _upsert([stale, corrected])

    found = await _get_by_external_id("D1")
    assert found is not None
    assert found.name == "Dr. Smith Jr."
