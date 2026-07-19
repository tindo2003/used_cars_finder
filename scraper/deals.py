"""
A minimal "good deal" signal: how a listing's price compares to other
active listings for the same make/model in a similar year/mileage range.
Parameters chosen 2026-07-19 (see research/mvp-checklist.md and prd.md
section 2.5 for the product context this responds to).
"""

from db import DbClient

DEAL_YEAR_WINDOW = 2
DEAL_MILEAGE_WINDOW = 20000
DEAL_MIN_COMPARABLES = 3
DEAL_THRESHOLD = 0.12


def _is_comparable(listing, other):
    if other.get("id") == listing.get("id"):
        return False
    if (other.get("make") or "").lower() != (listing.get("make") or "").lower():
        return False
    if (other.get("model") or "").lower() != (listing.get("model") or "").lower():
        return False

    year = listing.get("model_year")
    other_year = other.get("model_year")
    if year is not None and other_year is not None and abs(other_year - year) > DEAL_YEAR_WINDOW:
        return False

    mileage = listing.get("mileage")
    other_mileage = other.get("mileage")
    if mileage is not None and other_mileage is not None and abs(other_mileage - mileage) > DEAL_MILEAGE_WINDOW:
        return False

    # A $0 price is a known scraper artifact (defaults to 0 when a price
    # attribute is missing/unparseable on the source site), not a real
    # asking price -- treating it as a comparable would produce a bogus
    # "100% below median" false positive.
    other_price = other.get("price")
    return other_price is not None and other_price > 0


def _median(values):
    values = sorted(values)
    n = len(values)
    mid = n // 2
    if n % 2 == 1:
        return values[mid]
    return (values[mid - 1] + values[mid]) / 2


def compute_deal_score(listing, all_listings):
    """
    How far below the comparable market median `listing`'s price is
    (0.15 means 15% below median; negative means above median). Returns
    None if the listing has no price, or if there are fewer than
    DEAL_MIN_COMPARABLES other active listings with the same make/model
    within DEAL_YEAR_WINDOW years and DEAL_MILEAGE_WINDOW miles to judge
    against -- not enough data to trust a median.
    """
    price = listing.get("price")
    if price is None or price <= 0:
        return None

    comparable_prices = [float(other["price"]) for other in all_listings if _is_comparable(listing, other)]
    if len(comparable_prices) < DEAL_MIN_COMPARABLES:
        return None

    median = _median(comparable_prices)
    if median == 0:
        return None

    return (median - float(price)) / median


def is_good_deal(listing, all_listings):
    score = compute_deal_score(listing, all_listings)
    return score is not None and score >= DEAL_THRESHOLD


def ranking_key(listing, all_listings):
    """
    Sort key that ranks listings with a computable deal score by that
    score (best deals first), falling back to plain lowest-price for
    listings without enough comparables to judge -- "we can't tell if
    it's a deal" isn't the same as "it's not one", so those listings are
    included after the scored ones rather than excluded.
    """
    score = compute_deal_score(listing, all_listings)
    if score is not None:
        return (0, -score)
    price = listing.get("price")
    return (1, float(price) if price is not None else float("inf"))


def update_deal_scores(supabase):
    """
    Recompute deal_score/is_good_deal for every active listing and write
    the results back to the `listings` table, so the frontend can
    sort/badge on stored columns instead of reimplementing this heuristic
    in TypeScript. Returns the number of listings flagged as good deals.
    """
    listings_db = DbClient(supabase, table="listings")
    listings = listings_db.read(status="active")

    good_deal_count = 0
    for listing in listings:
        score = compute_deal_score(listing, listings)
        flagged = score is not None and score >= DEAL_THRESHOLD
        listings_db.update(
            {"id": listing["id"]},
            {"deal_score": score, "is_good_deal": flagged},
        )
        if flagged:
            good_deal_count += 1

    return good_deal_count
