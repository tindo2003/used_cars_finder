import os
import time

from supabase import create_client


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
    """
    return "vin" if car.get("vin") else "original_url"


class ListingsDB:
    """CRUD access to the `listings` table."""

    TABLE = "listings"

    def __init__(self, supabase=None):
        self.supabase = supabase

    def _table(self):
        if self.supabase is None:
            raise ValueError("ListingsDB was constructed without a Supabase client")
        return self.supabase.table(self.TABLE)

    def create(self, car):
        """Insert a new listing row."""
        return self._table().insert(car).execute()

    def read(self, **filters):
        """Fetch listings matching equality filters, e.g. read(vin='...')."""
        query = self._table().select("*")
        for key, value in filters.items():
            query = query.eq(key, value)
        return query.execute().data

    def update(self, match, fields):
        """Update listing(s) matching the `match` equality filters with `fields`."""
        query = self._table().update(fields)
        for key, value in match.items():
            query = query.eq(key, value)
        return query.execute()

    def delete(self, **match):
        """Delete listing(s) matching equality filters."""
        query = self._table().delete()
        for key, value in match.items():
            query = query.eq(key, value)
        return query.execute()

    def upsert(self, car):
        """
        Insert or update a listing, deduping on vin (dealer sources) or
        original_url (VIN-less sources like Craigslist) — see
        get_conflict_key().
        """
        car = dict(car, status="active")
        conflict_key = get_conflict_key(car)
        return self._table().upsert(car, on_conflict=conflict_key).execute()

    def bulk_save(self, cars, dry_run, progress, log_interval_seconds):
        for car in cars:
            if dry_run:
                print(
                    f"🔍 [DRY RUN] Would save: {car.get('make')} {car.get('model')} - ${car.get('price')}"
                )
                continue

            self.upsert(car)

            progress["saved"] += 1
            now = time.monotonic()
            if now - progress["last_log"] >= log_interval_seconds:
                print(f"✅ Saved {progress['saved']} listings so far...")
                progress["last_log"] = now
