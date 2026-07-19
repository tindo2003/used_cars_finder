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

            # Every car scraped gets upserted (deduped on vin/original_url,
            # see get_conflict_key), so this counts records processed this
            # run, not distinct rows in the table -- most of them are
            # re-confirming a listing that's already there, not inserting a
            # new one.
            progress["saved"] += 1
            now = time.monotonic()
            if now - progress["last_log"] >= log_interval_seconds:
                print(f"✅ Processed {progress['saved']} listings so far (deduped on save)...")
                progress["last_log"] = now
