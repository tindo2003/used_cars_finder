import os

import requests

from db import DbClient
from deals import ranking_key

RESEND_API_URL = "https://api.resend.com/emails"

DEFAULT_TOP_N = 10


def matches(listing, search):
    """
    Does `listing` satisfy every filter set on `search`? A filter that
    isn't set on the search is ignored. A filter that IS set but whose
    corresponding listing field is missing (e.g. mileage, which many
    Craigslist listings lack) does not disqualify the listing -- we'd
    rather over-notify on incomplete data than silently hide a possible
    deal because a field wasn't scraped. A search with every filter
    unset matches every listing -- notify_matches' top_n cap is what
    keeps that from emailing the entire table.
    """
    if search.get("make") and search["make"].lower() != (listing.get("make") or "").lower():
        return False
    if search.get("model") and search["model"].lower() not in (listing.get("model") or "").lower():
        return False
    if (
        search.get("max_price") is not None
        and listing.get("price") is not None
        and float(listing["price"]) > float(search["max_price"])
    ):
        return False
    if (
        search.get("min_year") is not None
        and listing.get("model_year") is not None
        and listing["model_year"] < search["min_year"]
    ):
        return False
    if (
        search.get("max_mileage") is not None
        and listing.get("mileage") is not None
        and listing["mileage"] > search["max_mileage"]
    ):
        return False
    if (
        search.get("transmission")
        and listing.get("transmission")
        and search["transmission"].lower() != listing["transmission"].lower()
    ):
        return False
    if (
        search.get("seller_type")
        and listing.get("seller_type")
        and search["seller_type"].lower() != listing["seller_type"].lower()
    ):
        return False
    return True


def _format_listing_html(listing):
    price = listing.get("price")
    price_str = f"${float(price):,.0f}" if price is not None else "N/A"
    mileage = listing.get("mileage")
    mileage_str = f"{mileage:,} mi" if mileage is not None else "mileage unknown"
    title = f"{listing.get('model_year')} {listing.get('make')} {listing.get('model')}"
    return (
        f"<li><strong>{title}</strong> — {price_str} ({mileage_str}) "
        f"— {listing.get('marketplace_source')} — "
        f'<a href="{listing.get("original_url")}">View listing</a></li>'
    )


def send_digest_email(to_email, listings):
    """Send one email listing every car in `listings` (already capped to top_n by the caller)."""
    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        raise ValueError("Missing RESEND_API_KEY")

    count = len(listings)
    subject = f"{count} new match{'es' if count != 1 else ''} for your saved search"
    items_html = "".join(_format_listing_html(listing) for listing in listings)

    res = requests.post(
        RESEND_API_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "from": "Used Car Finder <onboarding@resend.dev>",
            "to": [to_email],
            "subject": subject,
            "html": f"<p>New listings matching your saved search:</p><ul>{items_html}</ul>",
        },
    )
    res.raise_for_status()
    return res.json()


def notify_matches(supabase, send_email_fn=None, top_n=DEFAULT_TOP_N):
    """
    For every active saved search, find listings that match it and
    haven't already been notified (tracked in notification_history),
    keep the top_n ranked by deal score (see deals.ranking_key -- best
    relative deal first, falling back to lowest price for listings
    without enough comparables to score), and send a single digest email
    covering all of them. A search with no filters set matches every
    listing, so top_n is what keeps it from emailing the whole table --
    and since only listings actually included in an email get recorded
    in notification_history, the next run naturally surfaces the
    next-best deals once the current top_n have been seen.

    Returns the number of emails sent (not the number of listings).
    """
    send_email_fn = send_email_fn or send_digest_email

    listings_db = DbClient(supabase, table="listings")
    searches_db = DbClient(supabase, table="saved_searches")
    history_db = DbClient(supabase, table="notification_history")

    searches = [s for s in searches_db.read(is_active=True) if s.get("email")]
    listings = listings_db.read(status="active")
    already_notified = {
        (row["saved_search_id"], row["listing_id"]) for row in history_db.read()
    }

    emails_sent = 0
    for search in searches:
        new_matches = [
            listing
            for listing in listings
            if (search["id"], listing["id"]) not in already_notified and matches(listing, search)
        ]
        if not new_matches:
            continue

        top_matches = sorted(new_matches, key=lambda listing: ranking_key(listing, listings))[:top_n]

        send_email_fn(search["email"], top_matches)
        for listing in top_matches:
            history_db.create({"saved_search_id": search["id"], "listing_id": listing["id"]})
            already_notified.add((search["id"], listing["id"]))
        emails_sent += 1

    return emails_sent
