import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, cast

from pydantic import ValidationError
from supabase import create_client

from models import Listing
from utils.timestamps import parse_timestamp

# How close a returned row's created_at has to be to the last_seen_at we
# just stamped to count as "this upsert inserted the row" rather than
# "updated an existing one". Postgres only re-defaults created_at on
# INSERT; on UPDATE it keeps whatever it already was, since our payload
# never includes created_at. A few seconds of slack covers request
# latency between us stamping last_seen_at and Postgres applying its own
# now() default -- real inserts and updates differ by far more than this.
NEW_ROW_TOLERANCE = timedelta(seconds=5)


def get_supabase() -> Any:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SECRET_KEY")
    if not url or not key:
        raise ValueError("Missing Supabase credentials!")
    return create_client(url, key)


def _row_was_inserted(last_seen_at: str, returned_row: Dict[str, Any]) -> bool:
    """
    True if `returned_row` (the row an upsert call just affected) looks
    freshly inserted rather than updated -- see upsert()'s docstring.
    """
    created_at = parse_timestamp(returned_row.get("created_at"))
    stamped_at = parse_timestamp(last_seen_at)
    if created_at is None or stamped_at is None:
        return False
    return abs(stamped_at - created_at) < NEW_ROW_TOLERANCE


def read_listings(supabase: Any, **filters: Any) -> List[Listing]:
    """
    The typed entry point for reading listings -- validates every row
    into a Listing, so callers (deals.py, duplicates.py, staleness.py,
    notifications.py) get real attribute access instead of an
    unvalidated dict. Every row here was already validated once on the
    way in (see DbClient.bulk_save), so a failure here is a genuine bug
    worth surfacing loudly, not something to skip quietly.
    """
    rows = DbClient(supabase, table="listings").read(**filters)
    return [Listing.model_validate(row) for row in rows]


class DbClient:
    """Generic CRUD access to a Supabase table (defaults to `listings`)."""

    def __init__(self, supabase: Optional[Any] = None, table: str = "listings") -> None:
        self.supabase = supabase
        self.table_name = table

    def _table(self) -> Any:
        if self.supabase is None:
            raise ValueError("DbClient was constructed without a Supabase client")
        return self.supabase.table(self.table_name)

    def create(self, row: Dict[str, Any]) -> Any:
        """Insert a new row."""
        return self._table().insert(row).execute()

    def read(self, **filters: Any) -> List[Dict[str, Any]]:
        """Fetch rows matching equality filters, e.g. read(vin='...')."""
        query = self._table().select("*")
        for key, value in filters.items():
            query = query.eq(key, value)
        return cast(List[Dict[str, Any]], query.execute().data)

    def update(self, match: Dict[str, Any], fields: Dict[str, Any]) -> Any:
        """Update row(s) matching the `match` equality filters with `fields`."""
        query = self._table().update(fields)
        for key, value in match.items():
            query = query.eq(key, value)
        return query.execute()

    def delete(self, **match: Any) -> Any:
        """Delete row(s) matching equality filters."""
        query = self._table().delete()
        for key, value in match.items():
            query = query.eq(key, value)
        return query.execute()

    def upsert(self, car: Listing) -> bool:
        """
        Insert or update a listing. Stamps last_seen_at with the current
        time on every call (insert or update) -- this is what
        staleness.expire_stale_listings and deals.ranking_key's recency
        tiebreak both key off of.

        Returns True if this call inserted a brand-new row, False if it
        updated an existing one.
        """
        last_seen_at = datetime.now(timezone.utc).isoformat()
        payload = car.model_dump(exclude_none=True, mode="json")
        payload["status"] = "active"
        payload["last_seen_at"] = last_seen_at

        if car.vin:
            # (vin, dealer_name), not vin alone: dealer groups often
            # syndicate the same physical vehicle's VIN across multiple
            # storefronts they own (e.g. a trade-in shows up on both
            # "Capitol Honda" and sister store "Capitol Ford"). Upserting
            # on bare vin would make the second store's scrape silently
            # overwrite the first store's dealer_name/city/original_url in
            # place -- one row that flip-flops location with no visible
            # duplicate and no history of the swap. Keying on the pair
            # keeps each storefront's listing as its own row, so the
            # cross-listing case becomes visible and gets flagged by
            # duplicates.py instead of disappearing silently.
            result = self._table().upsert(payload, on_conflict="vin,dealer_name").execute()
            return _row_was_inserted(last_seen_at, result.data[0] if result.data else {})

        # VIN-less sources (e.g. Craigslist) have no database-level unique
        # constraint to upsert against: original_url isn't reliably unique
        # either, since a dealer's own inventory card can legitimately
        # link to a DIFFERENT dealer's page for the same syndicated
        # vehicle (see migrations/012). So this path dedupes manually --
        # look the row up by original_url first, update if found, insert
        # if not -- rather than relying on Postgres's ON CONFLICT
        # inference, which needs a real unique arbiter we don't have here.
        existing = self.read(original_url=car.original_url) if car.original_url else []
        if existing:
            self.update({"id": existing[0]["id"]}, payload)
            return False

        self.create(payload)
        return True

    def _maybe_log_progress(self, progress: Dict[str, Any], log_interval_seconds: float) -> None:
        now = time.monotonic()
        if now - progress["last_log"] >= log_interval_seconds:
            print(f"✅ Processed {progress['saved']} listings so far (deduped on save)...")
            progress["last_log"] = now

    def bulk_save(
        self,
        cars: List[Dict[str, Any]],
        dry_run: bool,
        progress: Dict[str, Any],
        log_interval_seconds: float,
    ) -> None:
        for car in cars:
            if dry_run:
                print(
                    f"🔍 [DRY RUN] Would save: {car.get('make')} {car.get('model')} - ${car.get('price')}"
                )
                continue

            try:
                listing = Listing.model_validate(car)
            except ValidationError as error:
                # Raw scraped data (unlike our own DB rows) is untrusted --
                # a provider's parsing bug shouldn't crash the whole run,
                # just this one listing.
                print(f"⚠️  Skipping invalid listing (failed validation): {error}")
                progress["saved"] += 1
                progress["invalid"] = progress.get("invalid", 0) + 1
                self._maybe_log_progress(progress, log_interval_seconds)
                continue

            inserted = self.upsert(listing)

            # Every car scraped gets upserted (deduped on vin/original_url,
            # see upsert()), so "saved" counts records processed this run,
            # not distinct rows in the table -- "inserted" vs. "updated"
            # vs. "invalid" is the actual breakdown.
            progress["saved"] += 1
            if inserted:
                progress["inserted"] = progress.get("inserted", 0) + 1
            else:
                progress["updated"] = progress.get("updated", 0) + 1
            self._maybe_log_progress(progress, log_interval_seconds)
