import uuid

from domain.metrics import DoctorVisitListService, _rank_doctors_for_territory
from domain.models import Doctor
from ports.doctors import DoctorRepository


def _doctor(
    external_id: str,
    name: str,
    territory: str,
    priority: int,
) -> Doctor:
    return Doctor(
        id=uuid.uuid4(),
        external_doctor_id=external_id,
        name=name,
        territory=territory,
        priority=priority,
    )


class FakeDoctorRepository(DoctorRepository):
    def __init__(self, rows: list[Doctor] | None = None) -> None:
        self._rows = rows or []

    async def upsert_many(self, rows: list) -> None:
        raise NotImplementedError

    async def list_all(self) -> list:
        return self._rows


def test_rank_doctors_for_territory_orders_by_ascending_priority():
    rows = [
        _doctor("D1", "Dr. Low Urgency", "East", priority=3),
        _doctor("D2", "Dr. High Urgency", "East", priority=1),
        _doctor("D3", "Dr. Mid Urgency", "East", priority=2),
    ]

    entries = _rank_doctors_for_territory(rows, "East")

    assert [e.doctor_name for e in entries] == [
        "Dr. High Urgency",
        "Dr. Mid Urgency",
        "Dr. Low Urgency",
    ]
    assert [e.target_priority for e in entries] == [1, 2, 3]
    assert all(e.territory == "East" for e in entries)


def test_rank_doctors_for_territory_excludes_other_territories():
    rows = [
        _doctor("D1", "Dr. East", "East", priority=1),
        _doctor("D2", "Dr. West", "West", priority=1),
    ]

    entries = _rank_doctors_for_territory(rows, "East")

    assert [e.doctor_name for e in entries] == ["Dr. East"]


def test_rank_doctors_for_territory_no_matching_doctors_returns_empty_list():
    rows = [_doctor("D1", "Dr. West", "West", priority=1)]

    entries = _rank_doctors_for_territory(rows, "East")

    assert entries == []


def test_rank_doctors_for_territory_empty_repository_rows_returns_empty_list():
    entries = _rank_doctors_for_territory([], "East")

    assert entries == []


def test_rank_doctors_for_territory_ties_broken_by_doctor_name_and_both_retained():
    rows = [
        _doctor("D1", "Zebra", "East", priority=1),
        _doctor("D2", "Apple", "East", priority=1),
    ]
    reversed_rows = list(reversed(rows))

    first = _rank_doctors_for_territory(rows, "East")
    second = _rank_doctors_for_territory(reversed_rows, "East")

    assert [e.doctor_name for e in first] == ["Apple", "Zebra"]
    assert first == second


async def test_doctor_visit_list_service_get_visit_list_delegates_to_rank_doctors_for_territory():
    rows = [
        _doctor("D1", "Dr. Low Urgency", "East", priority=3),
        _doctor("D2", "Dr. High Urgency", "East", priority=1),
        _doctor("D3", "Dr. Other Territory", "West", priority=1),
    ]
    repo = FakeDoctorRepository(rows)
    service = DoctorVisitListService(doctors=repo)

    entries = await service.get_visit_list("East")

    assert [e.doctor_name for e in entries] == ["Dr. High Urgency", "Dr. Low Urgency"]


async def test_doctor_visit_list_service_empty_repository_returns_empty_list():
    repo = FakeDoctorRepository([])
    service = DoctorVisitListService(doctors=repo)

    entries = await service.get_visit_list("East")

    assert entries == []
