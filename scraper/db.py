import os
import time
from datetime import datetime, timedelta, timezone

from supabase import create_client

from utils.timestamps import parse_timestamp

# How close a returned row's created_at has to be to the last_seen_at we
# just stamped to count as "this upsert inserted the row" rather than
# "updated an existing one". Postgres only re-defaults created_at on
# INSERT; on UPDATE it keeps whatever it already was, since our payload
# never includes created_at. A few seconds of slack covers request
# latency between us stamping last_seen_at and Postgres applying its own
# now() default -- real inserts and updates differ by far more than this.
NEW_ROW_TOLERANCE = timedelta(seconds=5)


def get_supabase():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SECRET_KEY")
    if not url or not key:
        raise ValueError("Missing Supabase credentials!")
    return create_client(url, key)


def get_conflict_key(car):
    """
    VIN is the real stable identity for dealer-sourced cars (a listing's
    URL can drift over time, e.g. an edited trim name changes the slug);
    fall back to original_url for VIN-less sources like Craigslist.

    Conflict target is (vin, dealer_name), not vin alone: dealer groups
    often syndicate the same physical vehicle's VIN across multiple
    storefronts they own (e.g. a trade-in shows up on both "Nissan San
    Jose" and sister store "Honda Fremont"). Upserting on bare vin would
    make the second store's scrape silently overwrite the first store's
    dealer_name/city/original_url in place -- one row that flip-flops
    location with no visible duplicate and no history of the swap.
    Keying on the pair keeps each storefront's listing as its own row
    (still collapsing repeat scrapes of the *same* dealer's listing, the
    original bug this fixed -- see migration 001), so the cross-listing
    case becomes visible and gets flagged by duplicates.py instead of
    disappearing silently.
    """
    return "vin,dealer_name" if car.get("vin") else "original_url"


def _row_was_inserted(last_seen_at, returned_row):
    """
    True if `returned_row` (the row an upsert call just affected) looks
    freshly inserted rather than updated -- see upsert()'s docstring.
    """
    created_at = parse_timestamp(returned_row.get("created_at"))
    stamped_at = parse_timestamp(last_seen_at)
    if created_at is None or stamped_at is None:
        return False
    return abs(stamped_at - created_at) < NEW_ROW_TOLERANCE


class DbClient:
    """Generic CRUD access to a Supabase table (defaults to `listings`)."""

    def __init__(self, supabase=None, table="listings"):
        self.supabase = supabase
        self.table_name = table

    def _table(self):
        if self.supabase is None:
            raise ValueError("DbClient was constructed without a Supabase client")
        return self.supabase.table(self.table_name)

    def create(self, row):
        """Insert a new row."""
        return self._table().insert(row).execute()

    def read(self, **filters):
        """Fetch rows matching equality filters, e.g. read(vin='...')."""
        query = self._table().select("*")
        for key, value in filters.items():
            query = query.eq(key, value)
        return query.execute().data

    def update(self, match, fields):
        """Update row(s) matching the `match` equality filters with `fields`."""
        query = self._table().update(fields)
        for key, value in match.items():
            query = query.eq(key, value)
        return query.execute()

    def delete(self, **match):
        """Delete row(s) matching equality filters."""
        query = self._table().delete()
        for key, value in match.items():
            query = query.eq(key, value)
        return query.execute()

    def upsert(self, car):
        """
        Insert or update a listing, deduping on (vin, dealer_name)
        (dealer sources) or original_url (VIN-less sources like
        Craigslist) — see get_conflict_key(). Stamps last_seen_at with
        the current time on every call (insert or update) -- this is
        what staleness.expire_stale_listings and deals.ranking_key's
        recency tiebreak both key off of.

        Returns True if this call inserted a brand-new row, False if it
        updated an existing one -- determined from the same response,
        no extra round trip (see _row_was_inserted).
        """
        last_seen_at = datetime.now(timezone.utc).isoformat()
        car = dict(car, status="active", last_seen_at=last_seen_at)
        conflict_key = get_conflict_key(car)
        result = self._table().upsert(car, on_conflict=conflict_key).execute()
        return _row_was_inserted(last_seen_at, result.data[0] if result.data else {})

    def bulk_save(self, cars, dry_run, progress, log_interval_seconds):
        for car in cars:
            if dry_run:
                print(
                    f"🔍 [DRY RUN] Would save: {car.get('make')} {car.get('model')} - ${car.get('price')}"
                )
                continue

            inserted = self.upsert(car)

            # Every car scraped gets upserted (deduped on vin/original_url,
            # see get_conflict_key), so "saved" counts records processed
            # this run, not distinct rows in the table -- "inserted" vs.
            # "updated" is the actual new-vs-already-existed breakdown.
            progress["saved"] += 1
            progress["inserted"] = progress.get("inserted", 0) + (1 if inserted else 0)
            progress["updated"] = progress.get("updated", 0) + (0 if inserted else 1)
            now = time.monotonic()
            if now - progress["last_log"] >= log_interval_seconds:
                print(f"✅ Processed {progress['saved']} listings so far (deduped on save)...")
                progress["last_log"] = now
