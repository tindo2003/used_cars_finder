from datetime import datetime


def parse_timestamp(value):
    """
    Parses a Postgres/Supabase timestamptz string into a timezone-aware
    datetime. Returns None for anything missing or unparseable, rather
    than raising -- callers treat "we don't know" the same as "very
    old"/"very new" depending on context.
    """
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
