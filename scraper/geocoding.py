"""
Populates listings.location (a geometry(Point,4326) column, already live
in the DB but unpopulated -- see migrations/015) from listings.city.

Deliberately a separate enrichment pass over already-saved rows (mirrors
staleness.py/duplicates.py), not threaded into the scrape/upsert hot path
in main.py/runner.py/providers/*.py -- consistent with this codebase's
existing rule that only the DB boundary (db.py, and now this module)
touches validated Listing objects.

Uses Nominatim/OpenStreetMap (free, no API key) since call volume here is
tiny: only ~50 distinct city strings exist across all listings (5 fixed
dealer cities from main.py's DEALERS list, plus Craigslist's messier
free-text location field -- which also includes real garbage scraped as
"location", e.g. dealer phone numbers/CTAs, not just real place names).
Every failure mode collapses to "leave location NULL", never a crash.
"""

import time
from typing import Any, Callable, Dict, Optional, Tuple

import requests

from db import DbClient, read_listings

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
# Nominatim's usage policy requires a descriptive User-Agent identifying
# the application (generic/missing ones risk being blocked).
NOMINATIM_USER_AGENT = "used-cars-finder-scraper/1.0"
MIN_REQUEST_INTERVAL_SECONDS = 1.0
# Every known city string here is Bay Area -- this suffix disambiguates
# bare city names that also exist elsewhere (e.g. "Fremont" isn't unique
# to California) rather than trusting Nominatim to guess the right one.
REGION_SUFFIX = ", CA, USA"


def geocode(query: str, http_get: Callable[..., Any] = requests.get) -> Optional[Tuple[float, float]]:
    """
    One Nominatim /search call. Returns (lat, lng) -- NOTE: lat/lng order,
    NOT PostGIS's (lng, lat); the caller building a POINT(...) EWKT string
    must flip these. Every failure mode (non-2xx, request exception, empty
    results, unparseable body) collapses to None, so a single garbage
    location string (e.g. a Craigslist ad's location field scraped as
    "+ Call (408) 831-3270") can never raise out of this function.
    """
    try:
        response = http_get(
            NOMINATIM_URL,
            params={"q": query, "format": "json", "limit": 1},
            headers={"User-Agent": NOMINATIM_USER_AGENT},
            timeout=10,
        )
        response.raise_for_status()
        results = response.json()
    except (requests.RequestException, ValueError):
        return None

    if not results:
        return None

    try:
        return float(results[0]["lat"]), float(results[0]["lon"])
    except (KeyError, TypeError, ValueError):
        return None


def geocode_listings(
    supabase: Any,
    geocode_fn: Callable[[str], Optional[Tuple[float, float]]] = geocode,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> int:
    """
    Enrichment pass mirroring staleness.expire_stale_listings: reads every
    active listing, filters in Python to those with a city but no location
    yet (DbClient has no IS NULL filter, so this is the same "read broad,
    filter in Python" pattern staleness.py already uses -- not a shortcut),
    geocodes each *distinct* city string once (in-run dict cache -- notify.py
    only runs once a day, so even re-geocoding all ~50 distinct strings from
    scratch every run is trivial Nominatim traffic; a persisted cross-run
    cache would add real complexity for no real benefit at this volume), and
    writes the result back as an EWKT geometry literal via DbClient.update.

    A geocode miss logs a warning and leaves that listing's location NULL.
    A write failure for one listing is caught and logged, not allowed to
    stop the rest of the batch (same reasoning as run_dealer_scrapes' per-
    dealer try/except in runner.py). Returns the count of listings whose
    location was newly written.
    """
    listings_db = DbClient(supabase, table="listings")
    listings = read_listings(supabase, status="active")
    to_geocode = [listing for listing in listings if listing.city and listing.location is None]

    cache: Dict[str, Optional[Tuple[float, float]]] = {}
    updated = 0
    for listing in to_geocode:
        assert listing.city is not None  # narrowed by the filter above
        key = listing.city.strip().lower()

        if key not in cache:
            cache[key] = geocode_fn(f"{listing.city.strip()}{REGION_SUFFIX}")
            sleep_fn(MIN_REQUEST_INTERVAL_SECONDS)  # only on an actual outbound call, never on a cache hit

        coords = cache[key]
        if coords is None:
            print(f"⚠️  Could not geocode city '{listing.city}' for listing {listing.id}; leaving location NULL.")
            continue

        lat, lng = coords
        try:
            listings_db.update({"id": listing.id}, {"location": f"SRID=4326;POINT({lng} {lat})"})
            updated += 1
        except Exception as error:
            print(f"⚠️  Failed to write location for listing {listing.id}: {error}")

    return updated
