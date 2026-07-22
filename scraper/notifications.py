import os
from typing import Any, Callable, Dict, List, Optional, Tuple, cast

import requests

from db import DbClient, read_listings
from deals import ranking_key
from geocoding import haversine_miles, point_coordinates
from models import Listing, SavedSearch
from utils.timestamps import format_relative_time

RESEND_API_URL = "https://api.resend.com/emails"

DEFAULT_TOP_N = 10

# Mirrors app/page.tsx's MARKETPLACE_LABELS, so the digest email
# describes a listing's source the same way the frontend does.
MARKETPLACE_LABELS = {
    "craigslist": "Craigslist",
    "ebay": "eBay",
}


def _seller_label(listing: Listing) -> Optional[str]:
    """Mirrors app/page.tsx's getSellerLabel for consistency with the UI."""
    if listing.dealer_name:
        return f"{listing.dealer_name} · {listing.city}" if listing.city else listing.dealer_name
    return MARKETPLACE_LABELS.get(listing.marketplace_source or "", listing.marketplace_source)


def matches(listing: Listing, search: SavedSearch) -> bool:
    """
    Does `listing` satisfy every filter set on `search`? A filter that
    isn't set on the search is ignored. A filter that IS set but whose
    corresponding listing field is missing (e.g. mileage, which many
    Craigslist listings lack) does not disqualify the listing -- we'd
    rather over-notify on incomplete data than silently hide a possible
    deal because a field wasn't scraped. A search with every filter
    unset matches every listing -- notify_matches' top_n cap is what
    keeps that from emailing the entire table.

    make/model are lists (a search can watch several at once, e.g.
    "Toyota or Lexus") -- a listing passes if it matches ANY value in
    the list. Both are exact, case-insensitive matches: the frontend's
    multi-select only ever offers distinct values already present in
    listings, so there's no free-typed fragment to substring-match
    against anymore.
    """
    if search.make and not any(m.lower() == (listing.make or "").lower() for m in search.make):
        return False
    if search.model and not any(m.lower() == (listing.model or "").lower() for m in search.model):
        return False
    if search.max_price is not None and listing.price is not None and float(listing.price) > float(search.max_price):
        return False
    if search.min_year is not None and listing.model_year is not None and listing.model_year < search.min_year:
        return False
    if search.max_mileage is not None and listing.mileage is not None and listing.mileage > search.max_mileage:
        return False
    if (
        search.transmission
        and listing.transmission
        and search.transmission.lower() != listing.transmission.lower()
    ):
        return False
    if (
        search.seller_type
        and listing.seller_type
        and search.seller_type.lower() != listing.seller_type.lower()
    ):
        return False
    if search.target_location is not None and search.search_radius_miles is not None:
        search_coords = point_coordinates(search.target_location)
        listing_coords = point_coordinates(listing.location)
        # Same "missing data doesn't disqualify" convention as every filter
        # above -- a listing that couldn't be geocoded (e.g. an
        # ungeocodable Craigslist city, see geocoding.py) isn't excluded
        # just because a radius filter happens to be set.
        if search_coords and listing_coords:
            distance = haversine_miles(*search_coords, *listing_coords)
            if distance > search.search_radius_miles:
                return False
    return True


def _format_listing_html(listing: Listing) -> str:
    price = listing.price
    price_str = f"${float(price):,.0f}" if price is not None else "N/A"
    mileage = listing.mileage
    mileage_str = f"{mileage:,} mi" if mileage is not None else "mileage unknown"
    title = f"{listing.model_year} {listing.make} {listing.model}"
    last_updated = format_relative_time(listing.last_seen_at)
    last_updated_part = f" — {last_updated}" if last_updated else ""
    return (
        f"<li><strong>{title}</strong> — {price_str} ({mileage_str}) "
        f"— {_seller_label(listing)}{last_updated_part} — "
        f'<a href="{listing.original_url}">View listing</a></li>'
    )


def _search_label(search: SavedSearch) -> Optional[str]:
    """
    Identifies a saved search in an email subject/intro -- prefers its
    name (quoted, since a customer chose that text specifically), else
    falls back to describing its make/model filters, else None (fully
    unfiltered search, or no way to describe it). Used so a customer
    with multiple saved searches can tell 2 simultaneous digest emails
    apart instead of both saying the generic "your saved search"
    (a real gap found from live production digests, 2026-07-20).
    """
    if search.name:
        return f"'{search.name}'"
    parts = []
    if search.make:
        parts.append("/".join(search.make))
    if search.model:
        parts.append("/".join(search.model))
    return " ".join(parts) if parts else None


def send_digest_email(
    to_email: str,
    listings: List[Listing],
    group_label: Optional[str] = None,
    search_label: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Send one email listing every car in `listings` (already capped to
    top_n by the caller). `group_label` is set when the saved search
    groups its digest by make/model (e.g. "Toyota") -- it customizes the
    subject/intro so a customer getting several emails for one saved
    search can tell them apart. `search_label` (see _search_label)
    identifies the saved search itself, so 2 different saved searches'
    digests don't read identically either.
    """
    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        raise ValueError("Missing RESEND_API_KEY")

    count = len(listings)
    label_part = f"{group_label} " if group_label else ""
    target = search_label or "your saved search"
    subject = f"Top {count} {label_part}match{'es' if count != 1 else ''} for {target}"
    items_html = "".join(_format_listing_html(listing) for listing in listings)

    res = requests.post(
        RESEND_API_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "from": "Used Car Finder <onboarding@resend.dev>",
            "to": [to_email],
            "subject": subject,
            "html": f"<p>Today's top {label_part}matches for {target}:</p><ul>{items_html}</ul>",
        },
    )
    res.raise_for_status()
    return cast(Dict[str, Any], res.json())


def _group_matches(matching_listings: List[Listing], group_by: str) -> List[Tuple[str, List[Listing]]]:
    """
    Splits matching_listings into groups keyed by the listing's actual
    make/model value (case-insensitively -- "Toyota" and "toyota"
    shouldn't become two groups), preserving the first-seen casing as
    the display label. Listings missing the field entirely land in a
    single "Other" group rather than being dropped.
    """
    order: List[str] = []
    labels: Dict[str, str] = {}
    groups: Dict[str, List[Listing]] = {}
    for listing in matching_listings:
        raw = (listing.make if group_by == "make" else listing.model) or "Other"
        key = raw.strip().lower()
        if key not in groups:
            groups[key] = []
            labels[key] = raw.strip()
            order.append(key)
        groups[key].append(listing)
    return [(labels[key], groups[key]) for key in order]


def notify_matches(
    supabase: Any,
    send_email_fn: Optional[Callable[..., Any]] = None,
    top_n: int = DEFAULT_TOP_N,
) -> int:
    """
    For every active saved search, find listings that match it, rank by
    deal score (see deals.ranking_key -- best relative deal first,
    falling back to lowest price for listings without enough comparables
    to score), and send a digest of the top_n -- regardless of whether
    those listings were included in a previous digest. A deal-hunter
    wants today's best matches, not just novel ones, so a search whose
    top_n hasn't changed gets the same email again the next day.

    A search with notification_grouping="make" or "model" (default
    "combined") gets one digest per distinct make/model among its
    matches instead of a single email -- each group independently
    capped to top_n, so e.g. a search watching both Toyota and Lexus
    with top_n=10 can send up to 10 Toyota listings AND up to 10 Lexus
    listings, as two emails, rather than splitting one shared 10 across
    both.

    notification_history is still written to after every send (one row
    per listing per digest it appears in), but purely as a log for a
    future click-through-rate metric -- it's no longer read back to
    filter what gets sent (see migrations/013, which dropped the
    unique (saved_search_id, listing_id) constraint that used to enforce
    "never send the same listing twice").

    Listings flagged as a cross-marketplace duplicate (duplicate_of set,
    see duplicates.update_duplicate_flags) are excluded so the same
    physical vehicle never gets emailed twice under two different rows.

    Returns the number of emails sent (not the number of listings).
    """
    send_email_fn = send_email_fn or send_digest_email

    searches_db = DbClient(supabase, table="saved_searches")
    history_db = DbClient(supabase, table="notification_history")

    searches = [SavedSearch.model_validate(row) for row in searches_db.read(is_active=True)]
    listings = [listing for listing in read_listings(supabase, status="active") if not listing.duplicate_of]

    emails_sent = 0
    for search in searches:
        if not search.email:
            continue

        matching_listings = [listing for listing in listings if matches(listing, search)]
        if not matching_listings:
            continue

        grouping = search.notification_grouping or "combined"
        groups: List[Tuple[Optional[str], List[Listing]]]
        if grouping in ("make", "model"):
            groups = cast(List[Tuple[Optional[str], List[Listing]]], _group_matches(matching_listings, grouping))
        else:
            groups = [(None, matching_listings)]

        search_label = _search_label(search)

        for label, group_listings in groups:
            top_matches = sorted(group_listings, key=lambda listing: ranking_key(listing, listings))[:top_n]
            if not top_matches:
                continue

            extra_kwargs: Dict[str, str] = {}
            if label is not None:
                extra_kwargs["group_label"] = label
            if search_label is not None:
                extra_kwargs["search_label"] = search_label
            send_email_fn(search.email, top_matches, **extra_kwargs)

            for listing in top_matches:
                history_db.create({"saved_search_id": search.id, "listing_id": listing.id})
            emails_sent += 1

    return emails_sent
