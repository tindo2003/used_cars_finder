from datetime import timezone

from utils.timestamps import parse_timestamp


def test_parses_a_z_suffixed_timestamp():
    parsed = parse_timestamp("2026-07-20T12:00:00Z")
    assert parsed.year == 2026
    assert parsed.tzinfo is not None


def test_parses_an_offset_timestamp():
    parsed = parse_timestamp("2026-07-20T12:00:00+00:00")
    assert parsed == parsed.replace(tzinfo=timezone.utc)


def test_returns_none_for_missing_value():
    assert parse_timestamp(None) is None
    assert parse_timestamp("") is None


def test_returns_none_for_unparseable_value():
    assert parse_timestamp("not-a-timestamp") is None
