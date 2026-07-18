import os

import requests

from db import DbClient

RESEND_API_URL = "https://api.resend.com/emails"


def matches(listing, search):
    """
    Does `listing` satisfy every filter set on `search`? A filter that
    isn't set on the search is ignored. A filter that IS set but whose
    corresponding listing field is missing (e.g. mileage, which many
    Craigslist listings lack) does not disqualify the listing -- we'd
    rather over-notify on incomplete data than silently hide a possible
    deal because a field wasn't scraped.
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


def send_email(to_email, listing):
    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        raise ValueError("Missing RESEND_API_KEY")

    price = listing.get("price")
    price_str = f"${float(price):,.0f}" if price is not None else "N/A"
    mileage = listing.get("mileage")
    mileage_str = f"{mileage:,} mi" if mileage is not None else "mileage unknown"
    title = f"{listing.get('model_year')} {listing.get('make')} {listing.get('model')}"

    res = requests.post(
        RESEND_API_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "from": "Used Car Finder <onboarding@resend.dev>",
            "to": [to_email],
            "subject": f"New match: {title} - {price_str}",
            "html": (
                f"<p>A new listing matches one of your saved searches:</p>"
                f"<p><strong>{title}</strong> — {price_str} ({mileage_str})</p>"
                f"<p>Source: {listing.get('marketplace_source')}</p>"
                f"<p><a href=\"{listing.get('original_url')}\">View listing</a></p>"
            ),
        },
    )
    res.raise_for_status()
    return res.json()


def notify_matches(supabase, send_email_fn=None):
    """
    Check every active listing against every active saved search and
    email the search's owner for any match that hasn't already been
    notified (tracked in notification_history). Returns the number of
    notifications sent.
    """
    send_email_fn = send_email_fn or send_email

    listings_db = DbClient(supabase, table="listings")
    searches_db = DbClient(supabase, table="saved_searches")
    history_db = DbClient(supabase, table="notification_history")

    searches = [s for s in searches_db.read(is_active=True) if s.get("email")]
    listings = listings_db.read(status="active")
    already_notified = {
        (row["saved_search_id"], row["listing_id"]) for row in history_db.read()
    }

    sent = 0
    for search in searches:
        for listing in listings:
            key = (search["id"], listing["id"])
            if key in already_notified:
                continue
            if not matches(listing, search):
                continue

            send_email_fn(search["email"], listing)
            history_db.create({"saved_search_id": search["id"], "listing_id": listing["id"]})
            already_notified.add(key)
            sent += 1

    return sent
