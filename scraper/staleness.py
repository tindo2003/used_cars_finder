"""
Expires listings we haven't reconfirmed in a while: the working
assumption is that a listing the scraper keeps re-seeing is more likely
still available than one it hasn't re-seen in a long time (see
research/mvp-checklist.md, 2026-07-20).

Caveat: this is a much stronger signal for dealer-sourced listings than
for Craigslist. Dealer scrapers (providers/dealeron.py,
providers/dealerinspire.py) re-crawl a dealer's *entire* inventory every
run, so a dealer listing that stops advancing really did stop showing up
on the site. Craigslist is only searched for make/model combos that
currently have an active saved search (see runner.py's
run_marketplace_searches) -- a Craigslist listing can go stale simply
because nobody has a matching saved search anymore, not because the car
sold. Treat Craigslist staleness as a noisier signal than dealer
staleness; not otherwise corrected for here.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from db import DbClient, read_listings

DEFAULT_STALE_THRESHOLD_DAYS = 90
EXPIRED_STATUS = "expired"


def expire_stale_listings(
    supabase: Any,
    stale_threshold_days: int = DEFAULT_STALE_THRESHOLD_DAYS,
    now: Optional[datetime] = None,
) -> int:
    """
    Marks status="expired" on every active listing whose last_seen_at is
    older than stale_threshold_days. Expired listings are excluded
    everywhere else in the app for free, since every other read already
    filters on status="active" (frontend, deals.py, duplicates.py,
    notifications.py). Listings with no last_seen_at are left alone --
    treated as "unknown", not "stale".

    Returns the number of listings newly expired.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=stale_threshold_days)

    listings_db = DbClient(supabase, table="listings")
    listings = read_listings(supabase, status="active")

    expired_count = 0
    for listing in listings:
        if listing.last_seen_at is not None and listing.last_seen_at < cutoff:
            listings_db.update({"id": listing.id}, {"status": EXPIRED_STATUS})
            expired_count += 1

    return expired_count
