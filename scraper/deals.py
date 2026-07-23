"""
A minimal "good deal" signal: how a listing's price compares to other
active listings for the same make/model in a similar year/mileage range.
Parameters chosen 2026-07-19 (see research/mvp-checklist.md and prd.md
section 2.5 for the product context this responds to).
"""

from typing import Any, List, Optional, Tuple

from db import DbClient, read_listings
from models import Listing

DEAL_YEAR_WINDOW = 2
DEAL_MILEAGE_WINDOW = 20000
DEAL_MIN_COMPARABLES = 3
DEAL_THRESHOLD = 0.12


def _is_comparable(listing: Listing, other: Listing) -> bool:
    if other.id == listing.id:
        return False
    if (other.make or "").lower() != (listing.make or "").lower():
        return False
    if (other.model or "").lower() != (listing.model or "").lower():
        return False
    # Craigslist listings (seller_type unset, i.e. None) are
    # overwhelmingly private-party and price meaningfully lower than a
    # dealer's listing of a comparable car (no reconditioning cost, no
    # dealer markup, no warranty backed into the price). Mixing the two
    # channels into one median made either channel look artificially
    # like a "deal" relative to the other, most visibly with old, cheap
    # Craigslist listings dominating a make's top-ranked matches purely
    # from being systematically cheaper by channel (user-flagged
    # 2026-07-20, with production evidence). None == None keeps
    # Craigslist-vs-Craigslist comparisons intact -- only cross-channel
    # (dealer vs. private-party) pairs are excluded.
    if (other.seller_type or "").lower() != (listing.seller_type or "").lower():
        return False

    year = listing.model_year
    other_year = other.model_year
    if year is not None and other_year is not None and abs(other_year - year) > DEAL_YEAR_WINDOW:
        return False

    mileage = listing.mileage
    other_mileage = other.mileage
    if mileage is not None and other_mileage is not None and abs(other_mileage - mileage) > DEAL_MILEAGE_WINDOW:
        return False

    # A $0 price is a known scraper artifact (defaults to 0 when a price
    # attribute is missing/unparseable on the source site), not a real
    # asking price -- treating it as a comparable would produce a bogus
    # "100% below median" false positive.
    other_price = other.price
    return other_price is not None and other_price > 0


def _is_comparable_same_trim(listing: Listing, other: Listing) -> bool:
    """
    A stricter tier on top of _is_comparable: also requires matching
    trim (e.g. distinguishes a base F-150 from a Raptor, which
    _is_comparable alone treats as the same "F-150"). Same None-vs-None
    treatment as the seller_type check above -- two listings that both
    lack a trim (overwhelmingly Craigslist, whose ads have no structured
    trim field) still compare against each other; a listing with a real
    trim never matches one with none, since we can't tell if they're
    actually comparable.

    Deliberately NOT used as the only comparable check -- see
    compute_deal_score's tiered fallback and research/deal-scoring-heuristic.md
    for why a hard trim-equality requirement guts coverage in practice
    (trim strings are dealer-specific free text, not a clean taxonomy,
    so exact matches are too rare to reliably clear DEAL_MIN_COMPARABLES).
    """
    if not _is_comparable(listing, other):
        return False
    return (other.trim or "").lower() == (listing.trim or "").lower()


def _median(values: List[float]) -> float:
    values = sorted(values)
    n = len(values)
    mid = n // 2
    if n % 2 == 1:
        return values[mid]
    return (values[mid - 1] + values[mid]) / 2


def compute_deal_score(listing: Listing, all_listings: List[Listing]) -> Optional[float]:
    """
    How far below the comparable market median `listing`'s price is
    (0.15 means 15% below median; negative means above median). Returns
    None if the listing has no price, or if there are fewer than
    DEAL_MIN_COMPARABLES other active listings with the same make/model
    within DEAL_YEAR_WINDOW years and DEAL_MILEAGE_WINDOW miles to judge
    against -- not enough data to trust a median.

    Tries the trim-matched pool first (_is_comparable_same_trim) for a
    more accurate comparison when there's enough same-trim data to trust;
    falls back to the trim-agnostic pool otherwise. This tiering, not a
    hard trim requirement, is a deliberate choice verified against real
    production data -- see research/deal-scoring-heuristic.md.
    """
    price = listing.price
    if price is None or price <= 0:
        return None

    trim_matched_prices = [
        float(other.price)
        for other in all_listings
        if _is_comparable_same_trim(listing, other) and other.price is not None
    ]
    if len(trim_matched_prices) >= DEAL_MIN_COMPARABLES:
        median = _median(trim_matched_prices)
        return (median - float(price)) / median if median else None

    comparable_prices = [
        float(other.price)
        for other in all_listings
        if _is_comparable(listing, other) and other.price is not None
    ]
    if len(comparable_prices) < DEAL_MIN_COMPARABLES:
        return None

    median = _median(comparable_prices)
    if median == 0:
        return None

    return (median - float(price)) / median


def is_good_deal(listing: Listing, all_listings: List[Listing]) -> bool:
    score = compute_deal_score(listing, all_listings)
    return score is not None and score >= DEAL_THRESHOLD


def _recency_tiebreak(listing: Listing) -> float:
    """
    Sorts more-recently-reconfirmed listings first (see
    staleness.expire_stale_listings for why "seen more recently" is a
    proxy for "more likely still available"). Only meant to break ties
    on score/price -- listings with no last_seen_at sort last within
    their tie group rather than winning by default.
    """
    return -listing.last_seen_at.timestamp() if listing.last_seen_at is not None else float("inf")


def ranking_key(listing: Listing, all_listings: List[Listing]) -> Tuple[int, float, float]:
    """
    Sort key that ranks listings with a computable deal score by that
    score (best deals first), falling back to plain lowest-price for
    listings without enough comparables to judge -- "we can't tell if
    it's a deal" isn't the same as "it's not one", so those listings are
    included after the scored ones rather than excluded. Ties are broken
    by _recency_tiebreak, not score/price alone.
    """
    score = compute_deal_score(listing, all_listings)
    recency = _recency_tiebreak(listing)
    if score is not None:
        return (0, -score, recency)
    price = listing.price
    return (1, float(price) if price is not None else float("inf"), recency)


def update_deal_scores(supabase: Any) -> int:
    """
    Recompute deal_score/is_good_deal for every active listing and write
    the results back to the `listings` table, so the frontend can
    sort/badge on stored columns instead of reimplementing this heuristic
    in TypeScript. Returns the number of listings flagged as good deals.
    """
    listings_db = DbClient(supabase, table="listings")
    listings = read_listings(supabase, status="active")

    good_deal_count = 0
    for listing in listings:
        score = compute_deal_score(listing, listings)
        flagged = score is not None and score >= DEAL_THRESHOLD
        listings_db.update(
            {"id": listing.id},
            {"deal_score": score, "is_good_deal": flagged},
        )
        if flagged:
            good_deal_count += 1

    return good_deal_count
