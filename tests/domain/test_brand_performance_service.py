import uuid
from decimal import Decimal

from domain.metrics import BrandPerformanceService, _classify_brands
from domain.models import BrandPerformance
from ports.brand_performance import BrandPerformanceRepository


def _brand(
    external_id: str,
    name: str,
    rank: int,
    growth: str,
    sales: str = "1000",
) -> BrandPerformance:
    return BrandPerformance(
        id=uuid.uuid4(),
        external_brand_id=external_id,
        brand_name=name,
        sales=Decimal(sales),
        rank=rank,
        growth_pct=Decimal(growth),
    )


class FakeBrandPerformanceRepository(BrandPerformanceRepository):
    def __init__(self, rows: list[BrandPerformance] | None = None) -> None:
        self._rows = rows or []

    async def upsert_many(self, rows: list) -> None:
        raise NotImplementedError

    async def list_all(self) -> list:
        return self._rows


def test_classify_brands_top_and_low_performing_never_overlap():
    rows = [_brand(f"B{i}", f"Brand{i}", rank=i, growth="1.0") for i in range(1, 11)]

    summary = _classify_brands(rows, top_n=3, low_performing_n=3, focus_n=3)

    assert [b.rank for b in summary.top_brands] == [1, 2, 3]
    assert [b.rank for b in summary.low_performing_brands] == [10, 9, 8]
    top_ids = {b.brand_name for b in summary.top_brands}
    low_ids = {b.brand_name for b in summary.low_performing_brands}
    assert top_ids.isdisjoint(low_ids)


def test_classify_brands_focus_excludes_already_classified_brands():
    # B1 is Top (rank 1) despite negative growth; B10 is Low-Performing (rank 10, worst)
    # with negative growth too. Neither should also show up in Focus.
    rows = [
        _brand("B1", "TopButDeclining", rank=1, growth="-5.0"),
        _brand("B2", "MiddleDeclining", rank=2, growth="-2.0"),
        _brand("B3", "MiddleGrowing", rank=3, growth="4.0"),
        _brand("B10", "WorstAndDeclining", rank=10, growth="-9.0"),
    ]

    summary = _classify_brands(rows, top_n=1, low_performing_n=1, focus_n=5)

    focus_names = {b.brand_name for b in summary.focus_brands}
    assert focus_names == {"MiddleDeclining"}
    assert "TopButDeclining" not in focus_names
    assert "WorstAndDeclining" not in focus_names


def test_classify_brands_fewer_brands_than_top_n_no_error():
    rows = [_brand("B1", "Only", rank=1, growth="1.0")]

    summary = _classify_brands(rows, top_n=5, low_performing_n=5, focus_n=5)

    assert [b.brand_name for b in summary.top_brands] == ["Only"]
    assert summary.low_performing_brands == []
    assert summary.focus_brands == []


def test_classify_brands_empty_rows_returns_all_empty_lists():
    summary = _classify_brands([], top_n=5, low_performing_n=5, focus_n=5)

    assert summary.top_brands == []
    assert summary.low_performing_brands == []
    assert summary.focus_brands == []


def test_classify_brands_focus_never_includes_non_declining_brand():
    rows = [_brand(f"B{i}", f"Brand{i}", rank=i, growth="0.0") for i in range(1, 6)]

    summary = _classify_brands(rows, top_n=1, low_performing_n=1, focus_n=5)

    assert summary.focus_brands == []


def test_classify_brands_top_ties_broken_by_brand_name_and_both_retained():
    rows = [
        _brand("B2", "Zebra", rank=1, growth="1.0"),
        _brand("B1", "Apple", rank=1, growth="1.0"),
    ]

    first = _classify_brands(rows, top_n=2, low_performing_n=1, focus_n=1)
    second = _classify_brands(rows, top_n=2, low_performing_n=1, focus_n=1)

    assert [b.brand_name for b in first.top_brands] == ["Apple", "Zebra"]
    assert first.top_brands == second.top_brands


def test_classify_brands_low_performing_ties_broken_by_brand_name_and_both_retained():
    rows = [
        _brand("B1", "Leader", rank=1, growth="1.0"),
        _brand("B3", "Zebra", rank=10, growth="1.0"),
        _brand("B2", "Apple", rank=10, growth="1.0"),
    ]

    first = _classify_brands(rows, top_n=1, low_performing_n=2, focus_n=1)
    second = _classify_brands(rows, top_n=1, low_performing_n=2, focus_n=1)

    assert [b.brand_name for b in first.low_performing_brands] == ["Apple", "Zebra"]
    assert first.low_performing_brands == second.low_performing_brands


def test_classify_brands_focus_ties_broken_by_brand_name_and_both_retained():
    rows = [
        _brand("B1", "Leader", rank=1, growth="1.0"),
        _brand("B4", "Worst", rank=10, growth="1.0"),
        _brand("B3", "Zebra", rank=5, growth="-2.0"),
        _brand("B2", "Apple", rank=6, growth="-2.0"),
    ]

    first = _classify_brands(rows, top_n=1, low_performing_n=1, focus_n=2)
    second = _classify_brands(rows, top_n=1, low_performing_n=1, focus_n=2)

    assert [b.brand_name for b in first.focus_brands] == ["Apple", "Zebra"]
    assert first.focus_brands == second.focus_brands


def test_classify_brands_rejects_negative_thresholds():
    rows = [_brand("B1", "Only", rank=1, growth="1.0")]

    for kwargs in (
        {"top_n": -1, "low_performing_n": 1, "focus_n": 1},
        {"top_n": 1, "low_performing_n": -1, "focus_n": 1},
        {"top_n": 1, "low_performing_n": 1, "focus_n": -1},
    ):
        try:
            _classify_brands(rows, **kwargs)
        except ValueError:
            continue
        raise AssertionError(f"expected ValueError for {kwargs}")


async def test_brand_performance_service_get_summary_delegates_to_classify_brands():
    rows = [_brand(f"B{i}", f"Brand{i}", rank=i, growth="1.0") for i in range(1, 4)]
    repo = FakeBrandPerformanceRepository(rows)
    service = BrandPerformanceService(
        brand_performance=repo, top_n=1, low_performing_n=1, focus_n=1
    )

    summary = await service.get_summary()

    assert [b.brand_name for b in summary.top_brands] == ["Brand1"]
    assert [b.brand_name for b in summary.low_performing_brands] == ["Brand3"]
    assert summary.focus_brands == []
