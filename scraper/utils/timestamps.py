from datetime import datetime, timezone
from typing import Optional, Union


def parse_timestamp(value: Optional[Union[str, datetime]]) -> Optional[datetime]:
    """
    Parses a Postgres/Supabase timestamptz string into a timezone-aware
    datetime. Returns None for anything missing or unparseable, rather
    than raising -- callers treat "we don't know" the same as "very
    old"/"very new" depending on context. Passing an already-parsed
    datetime (e.g. models.Listing.last_seen_at, which Pydantic parses
    automatically) is a no-op pass-through.
    """
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def format_relative_time(value: Optional[Union[str, datetime]], now: Optional[datetime] = None) -> Optional[str]:
    """
    Human-readable "time ago" string for a Postgres timestamptz string
    or an already-parsed datetime, e.g. "Updated 2 hours ago". Mirrors
    app/page.tsx's formatLastSeen so the frontend and the notification
    digest describe listing freshness the same way. Returns None when
    `value` is missing/unparseable.
    """
    parsed = parse_timestamp(value)
    if parsed is None:
        return None

    now = now or datetime.now(timezone.utc)
    diff_minutes = round((now - parsed).total_seconds() / 60)
    if diff_minutes < 1:
        return "Updated just now"
    if diff_minutes < 60:
        return f"Updated {diff_minutes} minute{'s' if diff_minutes != 1 else ''} ago"

    diff_hours = round(diff_minutes / 60)
    if diff_hours < 24:
        return f"Updated {diff_hours} hour{'s' if diff_hours != 1 else ''} ago"

    diff_days = round(diff_hours / 24)
    return f"Updated {diff_days} day{'s' if diff_days != 1 else ''} ago"
