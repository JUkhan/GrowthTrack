import pathlib

from adapters.source_system.csv_importer import CsvFileSourceSystemImporter

_FIXTURES_DIR = pathlib.Path(__file__).parent.parent.parent / "fixtures" / "source_system"


async def test_fetch_batch_returns_raw_string_dicts_for_all_three_entity_types():
    importer = CsvFileSourceSystemImporter(str(_FIXTURES_DIR))

    batch = await importer.fetch_batch()

    assert set(batch.keys()) == {"sales_data", "brand_performance", "doctors"}
    assert batch["sales_data"][0] == {
        "date": "2026-07-18",
        "team": "North",
        "sales_amount": "1000",
        "achievement_pct": "95.5",
        "growth_pct": "3.2",
    }
    assert batch["brand_performance"][0]["external_brand_id"] == "B1"
    assert batch["doctors"][0]["external_doctor_id"] == "D1"


async def test_fetch_batch_does_not_filter_or_raise_on_a_malformed_row():
    """Validation is the domain service's job, not the adapter's — the
    adapter must not pre-filter or fail on a bad row."""
    importer = CsvFileSourceSystemImporter(str(_FIXTURES_DIR))

    batch = await importer.fetch_batch()

    assert len(batch["sales_data"]) == 2
    assert batch["sales_data"][1]["sales_amount"] == "not-a-number"


async def test_fetch_batch_returns_an_empty_list_for_a_missing_file(tmp_path):
    importer = CsvFileSourceSystemImporter(str(tmp_path))

    batch = await importer.fetch_batch()

    assert batch == {"sales_data": [], "brand_performance": [], "doctors": []}


async def test_fetch_batch_strips_a_utf8_bom_from_the_header_row(tmp_path):
    """A BOM (common from Excel/Windows exports) prefixed onto the first
    header name would otherwise make every row fail validation with a
    misleading "field is required" reason."""
    (tmp_path / "doctors.csv").write_bytes(
        b"\xef\xbb\xbfexternal_doctor_id,name,territory,priority\r\nD1,Dr. Smith,East,1\r\n"
    )
    importer = CsvFileSourceSystemImporter(str(tmp_path))

    batch = await importer.fetch_batch()

    assert batch["doctors"] == [
        {"external_doctor_id": "D1", "name": "Dr. Smith", "territory": "East", "priority": "1"}
    ]


async def test_fetch_batch_logs_a_warning_for_duplicate_header_columns(tmp_path, caplog):
    (tmp_path / "doctors.csv").write_text(
        "external_doctor_id,name,name,territory,priority\nD1,Dr. Smith,Dr. S.,East,1\n"
    )
    importer = CsvFileSourceSystemImporter(str(tmp_path))

    with caplog.at_level("WARNING"):
        batch = await importer.fetch_batch()

    assert len(batch["doctors"]) == 1
    assert any("duplicate header column" in message for message in caplog.messages)
