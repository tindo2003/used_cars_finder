from datetime import datetime, timedelta, timezone

from staleness import DEFAULT_STALE_THRESHOLD_DAYS, expire_stale_listings
from tests.fakes import FakeSupabase

NOW = datetime(2026, 7, 20, tzinfo=timezone.utc)


def iso(dt):
    return dt.isoformat()


def make_listing(**overrides):
    listing = {
        "id": "listing-1",
        "status": "active",
        "last_seen_at": iso(NOW),
    }
    listing.update(overrides)
    return listing


def test_expires_a_listing_not_seen_within_the_threshold():
    stale = make_listing(id="stale", last_seen_at=iso(NOW - timedelta(days=DEFAULT_STALE_THRESHOLD_DAYS + 1)))
    supabase = FakeSupabase(initial_data={"listings": [stale]})

    count = expire_stale_listings(supabase, now=NOW)

    assert count == 1
    assert supabase.table("listings").data[0]["status"] == "expired"


def test_leaves_a_recently_seen_listing_active():
    fresh = make_listing(id="fresh", last_seen_at=iso(NOW - timedelta(days=1)))
    supabase = FakeSupabase(initial_data={"listings": [fresh]})

    count = expire_stale_listings(supabase, now=NOW)

    assert count == 0
    assert supabase.table("listings").data[0]["status"] == "active"


def test_leaves_a_listing_with_no_last_seen_at_untouched():
    # Unknown isn't the same as stale -- don't expire listings we can't
    # actually judge (e.g. rows written before this column existed).
    unknown = make_listing(id="unknown", last_seen_at=None)
    supabase = FakeSupabase(initial_data={"listings": [unknown]})

    count = expire_stale_listings(supabase, now=NOW)

    assert count == 0
    assert supabase.table("listings").data[0]["status"] == "active"


def test_threshold_is_configurable():
    thirty_days_stale = make_listing(id="thirty", last_seen_at=iso(NOW - timedelta(days=31)))
    supabase = FakeSupabase(initial_data={"listings": [thirty_days_stale]})

    count = expire_stale_listings(supabase, stale_threshold_days=30, now=NOW)

    assert count == 1
    assert supabase.table("listings").data[0]["status"] == "expired"


def test_only_considers_currently_active_listings():
    supabase = FakeSupabase(
        initial_data={
            "listings": [
                make_listing(
                    id="already-expired",
                    status="expired",
                    last_seen_at=iso(NOW - timedelta(days=DEFAULT_STALE_THRESHOLD_DAYS + 100)),
                )
            ]
        }
    )

    count = expire_stale_listings(supabase, now=NOW)

    assert count == 0
    call = supabase.table("listings").calls[0]
    assert call["op"] == "select"
    assert call["filters"] == {"status": "active"}
