import time

import pytest

from db import ListingsDB, get_conflict_key


class FakeResult:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    """
    Minimal stand-in for supabase-py's fluent query builder: every method
    returns self (or a query already carrying the recorded operation) so
    calls can be chained the same way as the real client, e.g.
    .select("*").eq("vin", "X").execute().
    """

    def __init__(self, table):
        self.table = table
        self.op = None
        self.payload = None
        self.on_conflict = None
        self.filters = {}

    def select(self, *_args):
        self.op = "select"
        return self

    def insert(self, payload):
        self.op = "insert"
        self.payload = payload
        return self

    def update(self, payload):
        self.op = "update"
        self.payload = payload
        return self

    def delete(self):
        self.op = "delete"
        return self

    def upsert(self, payload, on_conflict):
        self.op = "upsert"
        self.payload = payload
        self.on_conflict = on_conflict
        return self

    def eq(self, key, value):
        self.filters[key] = value
        return self

    def execute(self):
        self.table.calls.append(
            {
                "op": self.op,
                "payload": self.payload,
                "on_conflict": self.on_conflict,
                "filters": dict(self.filters),
            }
        )
        return FakeResult(self.table.data)


class FakeTable:
    def __init__(self, name, data=None):
        self.name = name
        self.data = data if data is not None else []
        self.calls = []

    def select(self, *args):
        return FakeQuery(self).select(*args)

    def insert(self, payload):
        return FakeQuery(self).insert(payload)

    def update(self, payload):
        return FakeQuery(self).update(payload)

    def delete(self):
        return FakeQuery(self).delete()

    def upsert(self, payload, on_conflict):
        return FakeQuery(self).upsert(payload, on_conflict=on_conflict)


class FakeSupabase:
    def __init__(self, data=None):
        self.listings = FakeTable("listings", data)

    def table(self, name):
        assert name == "listings"
        return self.listings


def make_progress(last_log=None):
    return {"saved": 0, "last_log": last_log if last_log is not None else time.monotonic()}


# --- get_conflict_key ---


def test_get_conflict_key_prefers_vin_when_present():
    assert get_conflict_key({"vin": "1HGCR2F81DA008735"}) == "vin"


def test_get_conflict_key_falls_back_to_original_url_when_vin_missing():
    assert get_conflict_key({}) == "original_url"


def test_get_conflict_key_falls_back_to_original_url_when_vin_none():
    assert get_conflict_key({"vin": None}) == "original_url"


def test_get_conflict_key_falls_back_to_original_url_when_vin_empty_string():
    assert get_conflict_key({"vin": ""}) == "original_url"


# --- create ---


def test_create_inserts_the_given_car():
    supabase = FakeSupabase()
    db = ListingsDB(supabase)

    db.create({"vin": "A", "make": "Toyota"})

    assert supabase.listings.calls[0]["op"] == "insert"
    assert supabase.listings.calls[0]["payload"] == {"vin": "A", "make": "Toyota"}


# --- read ---


def test_read_returns_rows_matching_filters():
    supabase = FakeSupabase(data=[{"vin": "A", "make": "Toyota"}])
    db = ListingsDB(supabase)

    rows = db.read(vin="A")

    assert rows == [{"vin": "A", "make": "Toyota"}]
    assert supabase.listings.calls[0]["op"] == "select"
    assert supabase.listings.calls[0]["filters"] == {"vin": "A"}


def test_read_with_no_filters_selects_everything():
    supabase = FakeSupabase(data=[{"vin": "A"}, {"vin": "B"}])
    db = ListingsDB(supabase)

    rows = db.read()

    assert len(rows) == 2
    assert supabase.listings.calls[0]["filters"] == {}


# --- update ---


def test_update_applies_fields_to_rows_matching_the_given_filters():
    supabase = FakeSupabase()
    db = ListingsDB(supabase)

    db.update({"vin": "A"}, {"status": "sold"})

    call = supabase.listings.calls[0]
    assert call["op"] == "update"
    assert call["payload"] == {"status": "sold"}
    assert call["filters"] == {"vin": "A"}


# --- delete ---


def test_delete_removes_rows_matching_filters():
    supabase = FakeSupabase()
    db = ListingsDB(supabase)

    db.delete(vin="A")

    call = supabase.listings.calls[0]
    assert call["op"] == "delete"
    assert call["filters"] == {"vin": "A"}


# --- upsert ---


def test_upsert_uses_vin_as_conflict_key_when_present():
    supabase = FakeSupabase()
    db = ListingsDB(supabase)

    db.upsert({"vin": "A", "original_url": "https://example.com/a"})

    call = supabase.listings.calls[0]
    assert call["op"] == "upsert"
    assert call["on_conflict"] == "vin"
    assert call["payload"]["status"] == "active"


def test_upsert_falls_back_to_original_url_when_vin_missing():
    supabase = FakeSupabase()
    db = ListingsDB(supabase)

    db.upsert({"original_url": "https://craigslist.org/view/d/example"})

    assert supabase.listings.calls[0]["on_conflict"] == "original_url"


def test_upsert_does_not_mutate_the_caller_dict():
    supabase = FakeSupabase()
    db = ListingsDB(supabase)
    car = {"vin": "A"}

    db.upsert(car)

    assert "status" not in car


# --- bulk_save ---


def test_bulk_save_dry_run_never_touches_supabase(capsys):
    supabase = FakeSupabase()
    db = ListingsDB(supabase)
    progress = make_progress()

    db.bulk_save(
        [{"make": "Toyota", "model": "Camry", "price": 15000}],
        dry_run=True,
        progress=progress,
        log_interval_seconds=60,
    )

    assert supabase.listings.calls == []
    assert progress["saved"] == 0
    assert "DRY RUN" in capsys.readouterr().out


def test_bulk_save_increments_progress_for_every_car():
    supabase = FakeSupabase()
    db = ListingsDB(supabase)
    progress = make_progress()
    cars = [{"vin": f"VIN{i}"} for i in range(5)]

    db.bulk_save(cars, dry_run=False, progress=progress, log_interval_seconds=9999)

    assert progress["saved"] == 5
    assert len(supabase.listings.calls) == 5


def test_bulk_save_throttles_progress_logging(capsys):
    supabase = FakeSupabase()
    db = ListingsDB(supabase)
    # last_log far enough in the past that the very first save should log.
    progress = make_progress(last_log=0)
    cars = [{"vin": f"VIN{i}"} for i in range(5)]

    db.bulk_save(cars, dry_run=False, progress=progress, log_interval_seconds=9999)

    saved_logs = [line for line in capsys.readouterr().out.splitlines() if "Saved" in line]
    # Only the first car should trigger a log line; the rest fall inside
    # the 9999s interval window and should be suppressed.
    assert len(saved_logs) == 1
    assert progress["saved"] == 5


def test_bulk_save_logs_again_once_interval_elapses():
    supabase = FakeSupabase()
    db = ListingsDB(supabase)
    progress = make_progress(last_log=0)

    db.bulk_save([{"vin": "A"}], dry_run=False, progress=progress, log_interval_seconds=0)
    first_log_time = progress["last_log"]

    db.bulk_save([{"vin": "B"}], dry_run=False, progress=progress, log_interval_seconds=0)

    assert progress["last_log"] >= first_log_time
    assert progress["saved"] == 2


# --- constructed without a client ---


def test_operations_raise_a_clear_error_without_a_supabase_client():
    db = ListingsDB()

    with pytest.raises(ValueError):
        db.read()
