from datetime import datetime, timedelta, timezone

from utils.timestamps import format_relative_time, parse_timestamp


def test_parses_a_z_suffixed_timestamp():
    parsed = parse_timestamp("2026-07-20T12:00:00Z")
    assert parsed is not None
    assert parsed.year == 2026
    assert parsed.tzinfo is not None


def test_parses_an_offset_timestamp():
    parsed = parse_timestamp("2026-07-20T12:00:00+00:00")
    assert parsed is not None
    assert parsed == parsed.replace(tzinfo=timezone.utc)


def test_returns_none_for_missing_value():
    assert parse_timestamp(None) is None
    assert parse_timestamp("") is None


def test_returns_none_for_unparseable_value():
    assert parse_timestamp("not-a-timestamp") is None


def test_passes_through_an_already_parsed_datetime():
    # models.Listing types last_seen_at/created_at as datetime, so
    # Pydantic parses them automatically -- callers that already have a
    # datetime (rather than a raw Supabase string) shouldn't need to
    # re-stringify it just to call this function.
    already_parsed = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)
    assert parse_timestamp(already_parsed) is already_parsed


# --- format_relative_time() ---

NOW = datetime(2026, 7, 20, 12, 0, 0, tzinfo=timezone.utc)


def test_format_relative_time_just_now():
    value = (NOW - timedelta(seconds=30)).isoformat()
    assert format_relative_time(value, now=NOW) == "Updated just now"


def test_format_relative_time_minutes_ago():
    value = (NOW - timedelta(minutes=5)).isoformat()
    assert format_relative_time(value, now=NOW) == "Updated 5 minutes ago"


def test_format_relative_time_singular_minute():
    value = (NOW - timedelta(minutes=1)).isoformat()
    assert format_relative_time(value, now=NOW) == "Updated 1 minute ago"


def test_format_relative_time_hours_ago():
    value = (NOW - timedelta(hours=2)).isoformat()
    assert format_relative_time(value, now=NOW) == "Updated 2 hours ago"


def test_format_relative_time_singular_hour():
    value = (NOW - timedelta(hours=1)).isoformat()
    assert format_relative_time(value, now=NOW) == "Updated 1 hour ago"


def test_format_relative_time_days_ago():
    value = (NOW - timedelta(days=3)).isoformat()
    assert format_relative_time(value, now=NOW) == "Updated 3 days ago"


def test_format_relative_time_returns_none_for_missing_value():
    assert format_relative_time(None, now=NOW) is None
    assert format_relative_time("not-a-timestamp", now=NOW) is None
