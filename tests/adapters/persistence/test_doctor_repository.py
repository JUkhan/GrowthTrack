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


async def _list_all() -> list[Doctor]:
    session_factory = create_session_factory()
    async with session_factory() as session:
        return await SqlAlchemyDoctorRepository(session).list_all()


async def test_list_all_returns_empty_list_when_table_is_empty():
    found = await _list_all()

    assert found == []


async def test_list_all_returns_rows_ordered_by_territory_then_priority_ascending():
    await _upsert(
        [
            Doctor(
                id=uuid.uuid4(),
                external_doctor_id="D3",
                name="Dr. West Two",
                territory="West",
                priority=2,
            ),
            Doctor(
                id=uuid.uuid4(),
                external_doctor_id="D1",
                name="Dr. East One",
                territory="East",
                priority=1,
            ),
            Doctor(
                id=uuid.uuid4(),
                external_doctor_id="D2",
                name="Dr. West One",
                territory="West",
                priority=1,
            ),
        ]
    )

    found = await _list_all()

    assert [row.external_doctor_id for row in found] == ["D1", "D2", "D3"]
    assert all(isinstance(row.id, uuid.UUID) for row in found)
    assert [(row.territory, row.priority) for row in found] == [
        ("East", 1),
        ("West", 1),
        ("West", 2),
    ]
