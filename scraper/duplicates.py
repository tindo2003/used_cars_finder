"""
Cross-marketplace duplicate detection: the same physical vehicle can be
scraped from two different sources with no shared identifier (e.g. a
dealer's own inventory site plus that same dealer's Craigslist repost,
which usually lacks a VIN), or under the same shared VIN from two
different storefronts in the same dealer group (db.get_conflict_key
keys upserts on (vin, dealer_name), not vin alone, precisely so each
storefront's listing survives as its own row instead of one silently
overwriting the other). Distinct from the per-source dedup in db.py,
which only catches the same ad seen twice from the *same* source.

Parameters chosen 2026-07-20 -- see research/mvp-checklist.md.
"""

from db import DbClient

DUPLICATE_MILEAGE_TOLERANCE = 500
DUPLICATE_PRICE_TOLERANCE = 250


def _is_same_vin(a, b):
    vin_a, vin_b = a.get("vin"), b.get("vin")
    return bool(vin_a) and vin_a == vin_b


def _is_same_vehicle(a, b):
    # An exact VIN match is a certain identity match, not a fuzzy one --
    # skip straight to true regardless of marketplace_source/dealer_name.
    # This is what catches dealer groups syndicating the same physical
    # vehicle across sister storefronts (see db.get_conflict_key), which
    # keeps each storefront's listing as its own row precisely so this
    # case is visible instead of one row silently overwriting another.
    if _is_same_vin(a, b):
        return True

    # Below this point neither listing has a shared identifier, so the
    # match is fuzzy and only meaningful across different sources (a
    # same-source repost is already deduped on save via vin/original_url).
    if (a.get("marketplace_source") or "") == (b.get("marketplace_source") or ""):
        return False

    if (a.get("make") or "").lower() != (b.get("make") or "").lower():
        return False
    if (a.get("model") or "").lower() != (b.get("model") or "").lower():
        return False

    a_year, b_year = a.get("model_year"), b.get("model_year")
    if a_year is None or b_year is None or a_year != b_year:
        return False

    a_mileage, b_mileage = a.get("mileage"), b.get("mileage")
    if a_mileage is None or b_mileage is None or abs(a_mileage - b_mileage) > DUPLICATE_MILEAGE_TOLERANCE:
        return False

    a_price, b_price = a.get("price"), b.get("price")
    if a_price is None or b_price is None or a_price <= 0 or b_price <= 0:
        return False
    if abs(a_price - b_price) > DUPLICATE_PRICE_TOLERANCE:
        return False

    return True


def find_duplicate_groups(listings):
    """
    Groups active listings that look like the same vehicle posted under
    more than one marketplace_source (same make/model/model_year, mileage
    within DUPLICATE_MILEAGE_TOLERANCE miles, price within
    DUPLICATE_PRICE_TOLERANCE dollars). Returns only groups of size 2+;
    singletons (no cross-marketplace match found) are omitted.
    """
    parent = {listing["id"]: listing["id"] for listing in listings}

    def find(listing_id):
        while parent[listing_id] != listing_id:
            parent[listing_id] = parent[parent[listing_id]]
            listing_id = parent[listing_id]
        return listing_id

    def union(id_a, id_b):
        root_a, root_b = find(id_a), find(id_b)
        if root_a != root_b:
            parent[root_a] = root_b

    for i, a in enumerate(listings):
        for b in listings[i + 1 :]:
            if _is_same_vehicle(a, b):
                union(a["id"], b["id"])

    groups = {}
    for listing in listings:
        groups.setdefault(find(listing["id"]), []).append(listing)

    return [group for group in groups.values() if len(group) > 1]


def _pick_canonical(group):
    """
    VIN is the more reliable identity (see db.get_conflict_key), so a
    listing with one wins over a VIN-less repost of the same vehicle;
    ties broken by whichever was scraped first, then by id for
    determinism.
    """
    return min(
        group,
        key=lambda listing: (
            0 if listing.get("vin") else 1,
            listing.get("created_at") or "",
            listing["id"],
        ),
    )


def compute_duplicate_map(listings):
    """
    Returns {listing_id: canonical_listing_id} for every listing that is
    a cross-marketplace duplicate of another. Canonical listings and
    listings with no match are omitted (i.e. absence means "not a known
    duplicate").
    """
    duplicate_map = {}
    for group in find_duplicate_groups(listings):
        canonical = _pick_canonical(group)
        for listing in group:
            if listing["id"] != canonical["id"]:
                duplicate_map[listing["id"]] = canonical["id"]
    return duplicate_map


def update_duplicate_flags(supabase):
    """
    Recomputes duplicate_of for every active listing and writes it back,
    clearing it for listings no longer flagged (e.g. price diverged since
    the last run). Returns the number of listings flagged as duplicates.
    """
    listings_db = DbClient(supabase, table="listings")
    listings = listings_db.read(status="active")
    duplicate_map = compute_duplicate_map(listings)

    duplicate_count = 0
    for listing in listings:
        canonical_id = duplicate_map.get(listing["id"])
        listings_db.update({"id": listing["id"]}, {"duplicate_of": canonical_id})
        if canonical_id is not None:
            duplicate_count += 1

    return duplicate_count
