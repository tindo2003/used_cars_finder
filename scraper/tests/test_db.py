import time
from datetime import datetime

import pytest

from db import DbClient, get_conflict_key
from tests.fakes import FakeSupabase


def make_progress(last_log=None):
    return {
        "saved": 0,
        "inserted": 0,
        "updated": 0,
        "skipped": 0,
        "last_log": last_log if last_log is not None else time.monotonic(),
    }


# --- get_conflict_key ---


def test_get_conflict_key_prefers_vin_and_dealer_name_when_present():
    assert get_conflict_key({"vin": "1HGCR2F81DA008735", "dealer_name": "Capitol Honda"}) == "vin,dealer_name"


def test_get_conflict_key_falls_back_to_original_url_when_vin_missing():
    assert get_conflict_key({}) == "original_url"


def test_get_conflict_key_falls_back_to_original_url_when_vin_none():
    assert get_conflict_key({"vin": None}) == "original_url"


def test_get_conflict_key_falls_back_to_original_url_when_vin_empty_string():
    assert get_conflict_key({"vin": ""}) == "original_url"


# --- create ---


def test_create_inserts_the_given_car():
    supabase = FakeSupabase()
    db = DbClient(supabase)

    db.create({"vin": "A", "make": "Toyota"})

    calls = supabase.table("listings").calls
    assert calls[0]["op"] == "insert"
    assert calls[0]["payload"] == {"vin": "A", "make": "Toyota"}


# --- read ---


def test_read_returns_rows_matching_filters():
    supabase = FakeSupabase(initial_data={"listings": [{"vin": "A", "make": "Toyota"}, {"vin": "B", "make": "Honda"}]})
    db = DbClient(supabase)

    rows = db.read(vin="A")

    assert rows == [{"vin": "A", "make": "Toyota"}]


def test_read_with_no_filters_selects_everything():
    supabase = FakeSupabase(initial_data={"listings": [{"vin": "A"}, {"vin": "B"}]})
    db = DbClient(supabase)

    rows = db.read()

    assert len(rows) == 2


# --- update ---


def test_update_applies_fields_to_rows_matching_the_given_filters():
    supabase = FakeSupabase(initial_data={"listings": [{"vin": "A", "status": "active"}]})
    db = DbClient(supabase)

    db.update({"vin": "A"}, {"status": "sold"})

    assert supabase.table("listings").data[0]["status"] == "sold"


# --- delete ---


def test_delete_removes_rows_matching_filters():
    supabase = FakeSupabase(initial_data={"listings": [{"vin": "A"}, {"vin": "B"}]})
    db = DbClient(supabase)

    db.delete(vin="A")

    assert supabase.table("listings").data == [{"vin": "B"}]


# --- upsert ---


def test_upsert_uses_vin_and_dealer_name_as_conflict_key_when_present():
    supabase = FakeSupabase()
    db = DbClient(supabase)

    db.upsert({"vin": "A", "dealer_name": "Capitol Honda", "original_url": "https://example.com/a"})

    call = supabase.table("listings").calls[0]
    assert call["op"] == "upsert"
    assert call["on_conflict"] == "vin,dealer_name"
    assert call["payload"]["status"] == "active"


def test_upsert_stamps_last_seen_at():
    supabase = FakeSupabase()
    db = DbClient(supabase)
    before = time.time()

    db.upsert({"original_url": "https://example.com/a"})

    payload = supabase.table("listings").calls[0]["payload"]
    stamped = datetime.fromisoformat(payload["last_seen_at"])
    assert before <= stamped.timestamp() <= time.time()


def test_upsert_falls_back_to_original_url_when_vin_missing():
    supabase = FakeSupabase()
    db = DbClient(supabase)

    db.upsert({"original_url": "https://craigslist.org/view/d/example"})

    assert supabase.table("listings").calls[0]["on_conflict"] == "original_url"


def test_upsert_does_not_mutate_the_caller_dict():
    supabase = FakeSupabase()
    db = DbClient(supabase)
    car = {"vin": "A"}

    db.upsert(car)

    assert "status" not in car
    assert "last_seen_at" not in car


def test_upsert_updates_in_place_on_conflict():
    supabase = FakeSupabase(
        initial_data={
            "listings": [
                {
                    "id": "1",
                    "vin": "A",
                    "dealer_name": "Capitol Honda",
                    "original_url": "https://example.com/a",
                    "price": 100,
                }
            ]
        }
    )
    db = DbClient(supabase)

    db.upsert({"vin": "A", "dealer_name": "Capitol Honda", "original_url": "https://example.com/b", "price": 200})

    rows = supabase.table("listings").data
    assert len(rows) == 1
    assert rows[0]["original_url"] == "https://example.com/b"
    assert rows[0]["price"] == 200


def test_upsert_returns_true_when_inserting_a_new_row():
    supabase = FakeSupabase()
    db = DbClient(supabase)

    inserted = db.upsert({"vin": "A", "dealer_name": "Capitol Honda", "original_url": "https://example.com/a"})

    assert inserted is True


def test_upsert_returns_false_when_updating_an_existing_row():
    supabase = FakeSupabase(
        initial_data={
            "listings": [
                {
                    "id": "1",
                    "vin": "A",
                    "dealer_name": "Capitol Honda",
                    "original_url": "https://example.com/a",
                    "created_at": "2026-01-01T00:00:00+00:00",
                }
            ]
        }
    )
    db = DbClient(supabase)

    inserted = db.upsert({"vin": "A", "dealer_name": "Capitol Honda", "original_url": "https://example.com/a"})

    assert inserted is False


def test_upsert_keeps_the_same_vin_from_a_different_dealer_as_a_separate_row():
    # Dealer groups can syndicate the same VIN across sister storefronts
    # (e.g. a trade-in shows up on both "Capitol Honda" and "Capitol
    # Ford"). Conflicting on vin alone would silently overwrite the first
    # store's row with the second's; keying on (vin, dealer_name) keeps
    # both visible so duplicates.py can flag them explicitly instead.
    supabase = FakeSupabase(
        initial_data={
            "listings": [
                {"id": "1", "vin": "A", "dealer_name": "Capitol Honda", "original_url": "https://honda.example/a"}
            ]
        }
    )
    db = DbClient(supabase)

    db.upsert({"vin": "A", "dealer_name": "Capitol Ford", "original_url": "https://ford.example/a"})

    rows = supabase.table("listings").data
    assert len(rows) == 2
    assert {row["dealer_name"] for row in rows} == {"Capitol Honda", "Capitol Ford"}


def test_upsert_skips_when_original_url_collides_with_a_different_dealers_row():
    # A dealer's own inventory card can link straight to a DIFFERENT
    # dealer's detail page for the same physical vehicle (observed live:
    # a Capitol Honda card linking to chevroletoffremont.com). The new
    # car's (vin, dealer_name) upsert doesn't match any existing row, so
    # Postgres tries to INSERT -- and that INSERT collides with the
    # existing row's original_url, which has its own separate table-wide
    # uniqueness. Should skip rather than overwrite that row's identity.
    supabase = FakeSupabase(
        initial_data={
            "listings": [
                {
                    "id": "1",
                    "vin": "JF2SKAJC5SH408677",
                    "dealer_name": "Fremont Chevrolet",
                    "original_url": "https://www.chevroletoffremont.com/used-...-JF2SKAJC5SH408677",
                }
            ]
        }
    )
    db = DbClient(supabase)

    result = db.upsert(
        {
            "vin": "JF2SKAJC5SH408677",
            "dealer_name": "Capitol Honda",
            "original_url": "https://www.chevroletoffremont.com/used-...-JF2SKAJC5SH408677",
        }
    )

    assert result is None
    rows = supabase.table("listings").data
    assert len(rows) == 1
    assert rows[0]["dealer_name"] == "Fremont Chevrolet"


def test_is_original_url_conflict_only_matches_the_specific_constraint():
    from db import _is_original_url_conflict

    class FakeError:
        def __init__(self, code, message):
            self.code = code
            self.message = message

    assert _is_original_url_conflict(FakeError("23505", 'violates unique constraint "listings_original_url_key"'))
    assert not _is_original_url_conflict(FakeError("23505", 'violates unique constraint "listings_vin_dealer_name_key"'))
    assert not _is_original_url_conflict(FakeError("23503", 'violates unique constraint "listings_original_url_key"'))


# --- bulk_save ---


def test_bulk_save_dry_run_never_touches_supabase(capsys):
    supabase = FakeSupabase()
    db = DbClient(supabase)
    progress = make_progress()

    db.bulk_save(
        [{"make": "Toyota", "model": "Camry", "price": 15000}],
        dry_run=True,
        progress=progress,
        log_interval_seconds=60,
    )

    assert supabase.table("listings").calls == []
    assert progress["saved"] == 0
    assert "DRY RUN" in capsys.readouterr().out


def test_bulk_save_increments_progress_for_every_car():
    supabase = FakeSupabase()
    db = DbClient(supabase)
    progress = make_progress()
    cars = [{"vin": f"VIN{i}"} for i in range(5)]

    db.bulk_save(cars, dry_run=False, progress=progress, log_interval_seconds=9999)

    assert progress["saved"] == 5
    assert len(supabase.table("listings").data) == 5


def test_bulk_save_tracks_inserted_vs_updated_counts():
    supabase = FakeSupabase(
        initial_data={
            "listings": [
                {
                    "id": "1",
                    "vin": "ALREADY-THERE",
                    "dealer_name": "Capitol Honda",
                    "original_url": "https://example.com/existing",
                    "created_at": "2026-01-01T00:00:00+00:00",
                }
            ]
        }
    )
    db = DbClient(supabase)
    progress = make_progress()
    cars = [
        {"vin": "ALREADY-THERE", "dealer_name": "Capitol Honda", "original_url": "https://example.com/existing"},
        {"vin": "BRAND-NEW-1", "dealer_name": "Capitol Honda", "original_url": "https://example.com/new-1"},
        {"vin": "BRAND-NEW-2", "dealer_name": "Capitol Honda", "original_url": "https://example.com/new-2"},
    ]

    db.bulk_save(cars, dry_run=False, progress=progress, log_interval_seconds=9999)

    assert progress["saved"] == 3
    assert progress["inserted"] == 2
    assert progress["updated"] == 1


def test_bulk_save_tracks_skipped_count_for_cross_dealer_url_collisions():
    supabase = FakeSupabase(
        initial_data={
            "listings": [
                {
                    "id": "1",
                    "vin": "SHARED-VIN",
                    "dealer_name": "Fremont Chevrolet",
                    "original_url": "https://www.chevroletoffremont.com/shared",
                }
            ]
        }
    )
    db = DbClient(supabase)
    progress = make_progress()
    cars = [
        {"vin": "SHARED-VIN", "dealer_name": "Capitol Honda", "original_url": "https://www.chevroletoffremont.com/shared"},
        {"vin": "BRAND-NEW", "dealer_name": "Capitol Honda", "original_url": "https://example.com/new"},
    ]

    db.bulk_save(cars, dry_run=False, progress=progress, log_interval_seconds=9999)

    assert progress["saved"] == 2
    assert progress["skipped"] == 1
    assert progress["inserted"] == 1
    assert progress["updated"] == 0


def test_bulk_save_throttles_progress_logging(capsys):
    supabase = FakeSupabase()
    db = DbClient(supabase)
    # last_log far enough in the past that the very first save should log.
    progress = make_progress(last_log=0)
    cars = [{"vin": f"VIN{i}"} for i in range(5)]

    db.bulk_save(cars, dry_run=False, progress=progress, log_interval_seconds=9999)

    saved_logs = [line for line in capsys.readouterr().out.splitlines() if "Processed" in line]
    # Only the first car should trigger a log line; the rest fall inside
    # the 9999s interval window and should be suppressed.
    assert len(saved_logs) == 1
    assert progress["saved"] == 5


def test_bulk_save_logs_again_once_interval_elapses():
    supabase = FakeSupabase()
    db = DbClient(supabase)
    progress = make_progress(last_log=0)

    db.bulk_save([{"vin": "A"}], dry_run=False, progress=progress, log_interval_seconds=0)
    first_log_time = progress["last_log"]

    db.bulk_save([{"vin": "B"}], dry_run=False, progress=progress, log_interval_seconds=0)

    assert progress["last_log"] >= first_log_time
    assert progress["saved"] == 2


# --- constructed without a client ---


def test_operations_raise_a_clear_error_without_a_supabase_client():
    db = DbClient()

    with pytest.raises(ValueError):
        db.read()
