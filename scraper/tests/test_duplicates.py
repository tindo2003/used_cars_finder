from duplicates import compute_duplicate_map, find_duplicate_groups, update_duplicate_flags
from tests.fakes import FakeSupabase


def make_listing(**overrides):
    listing = {
        "id": "listing-1",
        "marketplace_source": "craigslist",
        "make": "Toyota",
        "model": "Camry",
        "model_year": 2020,
        "mileage": 40000,
        "price": 15000,
        "status": "active",
    }
    listing.update(overrides)
    return listing


# --- find_duplicate_groups ---


def test_groups_the_same_vehicle_across_two_marketplaces():
    craigslist_listing = make_listing(id="cl-1", marketplace_source="craigslist")
    dealer_listing = make_listing(id="dealer-1", marketplace_source="dealeron")

    groups = find_duplicate_groups([craigslist_listing, dealer_listing])

    assert len(groups) == 1
    assert {listing["id"] for listing in groups[0]} == {"cl-1", "dealer-1"}


def test_does_not_group_listings_from_the_same_source():
    a = make_listing(id="a", marketplace_source="craigslist")
    b = make_listing(id="b", marketplace_source="craigslist")

    assert find_duplicate_groups([a, b]) == []


def test_does_not_group_different_make_or_model():
    craigslist_listing = make_listing(id="cl-1", marketplace_source="craigslist")
    different_make = make_listing(id="dealer-1", marketplace_source="dealeron", make="Honda")
    different_model = make_listing(id="dealer-2", marketplace_source="dealeron", model="Corolla")

    assert find_duplicate_groups([craigslist_listing, different_make, different_model]) == []


def test_does_not_group_different_model_year():
    craigslist_listing = make_listing(id="cl-1", marketplace_source="craigslist", model_year=2020)
    dealer_listing = make_listing(id="dealer-1", marketplace_source="dealeron", model_year=2021)

    assert find_duplicate_groups([craigslist_listing, dealer_listing]) == []


def test_missing_model_year_does_not_match():
    craigslist_listing = make_listing(id="cl-1", marketplace_source="craigslist", model_year=None)
    dealer_listing = make_listing(id="dealer-1", marketplace_source="dealeron", model_year=None)

    assert find_duplicate_groups([craigslist_listing, dealer_listing]) == []


def test_mileage_within_tolerance_still_matches():
    craigslist_listing = make_listing(id="cl-1", marketplace_source="craigslist", mileage=40000)
    dealer_listing = make_listing(id="dealer-1", marketplace_source="dealeron", mileage=40300)

    groups = find_duplicate_groups([craigslist_listing, dealer_listing])

    assert len(groups) == 1


def test_mileage_outside_tolerance_does_not_match():
    craigslist_listing = make_listing(id="cl-1", marketplace_source="craigslist", mileage=40000)
    dealer_listing = make_listing(id="dealer-1", marketplace_source="dealeron", mileage=45000)

    assert find_duplicate_groups([craigslist_listing, dealer_listing]) == []


def test_price_within_tolerance_still_matches():
    craigslist_listing = make_listing(id="cl-1", marketplace_source="craigslist", price=15000)
    dealer_listing = make_listing(id="dealer-1", marketplace_source="dealeron", price=15200)

    groups = find_duplicate_groups([craigslist_listing, dealer_listing])

    assert len(groups) == 1


def test_price_outside_tolerance_does_not_match():
    craigslist_listing = make_listing(id="cl-1", marketplace_source="craigslist", price=15000)
    dealer_listing = make_listing(id="dealer-1", marketplace_source="dealeron", price=16000)

    assert find_duplicate_groups([craigslist_listing, dealer_listing]) == []


def test_zero_or_missing_price_never_matches():
    craigslist_listing = make_listing(id="cl-1", marketplace_source="craigslist", price=0)
    dealer_listing = make_listing(id="dealer-1", marketplace_source="dealeron", price=0)

    assert find_duplicate_groups([craigslist_listing, dealer_listing]) == []


def test_groups_across_three_marketplaces():
    craigslist_listing = make_listing(id="cl-1", marketplace_source="craigslist")
    dealeron_listing = make_listing(id="dealeron-1", marketplace_source="dealeron")
    dealerinspire_listing = make_listing(id="dealerinspire-1", marketplace_source="dealerinspire")

    groups = find_duplicate_groups([craigslist_listing, dealeron_listing, dealerinspire_listing])

    assert len(groups) == 1
    assert {listing["id"] for listing in groups[0]} == {"cl-1", "dealeron-1", "dealerinspire-1"}


def test_unrelated_listings_are_not_grouped():
    craigslist_listing = make_listing(id="cl-1", marketplace_source="craigslist")
    unrelated = make_listing(id="unrelated", marketplace_source="dealeron", make="Ford", model="F-150")

    assert find_duplicate_groups([craigslist_listing, unrelated]) == []


def test_same_vin_matches_across_the_same_marketplace_source():
    # Dealer groups can syndicate one VIN across multiple storefronts on
    # the same platform (e.g. two DealerInspire sites) -- db.py now keys
    # upserts on (vin, dealer_name) so both survive as separate rows, and
    # this exact-VIN rule is what flags them as duplicates of each other.
    honda_store = make_listing(
        id="honda-1", marketplace_source="dealerinspire", dealer_name="Capitol Honda", vin="1HGCM82633A004352"
    )
    ford_store = make_listing(
        id="ford-1", marketplace_source="dealerinspire", dealer_name="Capitol Ford", vin="1HGCM82633A004352"
    )

    groups = find_duplicate_groups([honda_store, ford_store])

    assert len(groups) == 1
    assert {listing["id"] for listing in groups[0]} == {"honda-1", "ford-1"}


def test_same_vin_matches_even_outside_the_fuzzy_price_and_mileage_windows():
    # VIN equality is a certain match, not a fuzzy one -- price/mileage
    # can legitimately differ between two storefronts' listings of the
    # exact same car (different negotiated price, mileage updated at a
    # different scrape time).
    honda_store = make_listing(
        id="honda-1",
        marketplace_source="dealerinspire",
        dealer_name="Capitol Honda",
        vin="1HGCM82633A004352",
        price=15000,
        mileage=40000,
    )
    ford_store = make_listing(
        id="ford-1",
        marketplace_source="dealerinspire",
        dealer_name="Capitol Ford",
        vin="1HGCM82633A004352",
        price=20000,
        mileage=50000,
    )

    groups = find_duplicate_groups([honda_store, ford_store])

    assert len(groups) == 1


def test_different_vins_are_not_matched_even_with_identical_make_model_year():
    a = make_listing(id="a", marketplace_source="dealerinspire", vin="1HGCM82633A004352")
    b = make_listing(id="b", marketplace_source="dealerinspire", vin="2HGCM82633A004999")

    assert find_duplicate_groups([a, b]) == []


# --- compute_duplicate_map ---


def test_map_prefers_the_listing_with_a_vin_as_canonical():
    craigslist_listing = make_listing(id="cl-1", marketplace_source="craigslist", vin=None)
    dealer_listing = make_listing(id="dealer-1", marketplace_source="dealeron", vin="1HGCM82633A004352")

    duplicate_map = compute_duplicate_map([craigslist_listing, dealer_listing])

    assert duplicate_map == {"cl-1": "dealer-1"}


def test_map_picks_earliest_created_as_canonical_when_both_share_a_vin():
    later = make_listing(
        id="ford-1",
        marketplace_source="dealerinspire",
        dealer_name="Capitol Ford",
        vin="1HGCM82633A004352",
        created_at="2026-07-02T00:00:00Z",
    )
    earlier = make_listing(
        id="honda-1",
        marketplace_source="dealerinspire",
        dealer_name="Capitol Honda",
        vin="1HGCM82633A004352",
        created_at="2026-07-01T00:00:00Z",
    )

    duplicate_map = compute_duplicate_map([later, earlier])

    assert duplicate_map == {"ford-1": "honda-1"}


def test_map_falls_back_to_earliest_created_when_neither_has_a_vin():
    later = make_listing(id="later", marketplace_source="craigslist", created_at="2026-07-02T00:00:00Z")
    earlier = make_listing(id="earlier", marketplace_source="dealeron", created_at="2026-07-01T00:00:00Z")

    duplicate_map = compute_duplicate_map([later, earlier])

    assert duplicate_map == {"later": "earlier"}


def test_map_omits_canonical_and_unmatched_listings():
    craigslist_listing = make_listing(id="cl-1", marketplace_source="craigslist", vin=None)
    dealer_listing = make_listing(id="dealer-1", marketplace_source="dealeron", vin="1HGCM82633A004352")
    unrelated = make_listing(id="unrelated", marketplace_source="dealeron", make="Ford", model="F-150")

    duplicate_map = compute_duplicate_map([craigslist_listing, dealer_listing, unrelated])

    assert "dealer-1" not in duplicate_map
    assert "unrelated" not in duplicate_map


# --- update_duplicate_flags ---


def test_update_duplicate_flags_writes_duplicate_of_for_the_non_canonical_row():
    craigslist_listing = make_listing(id="cl-1", marketplace_source="craigslist", vin=None)
    dealer_listing = make_listing(id="dealer-1", marketplace_source="dealeron", vin="1HGCM82633A004352")
    supabase = FakeSupabase(initial_data={"listings": [craigslist_listing, dealer_listing]})

    count = update_duplicate_flags(supabase)

    assert count == 1
    updated = {row["id"]: row for row in supabase.table("listings").data}
    assert updated["cl-1"]["duplicate_of"] == "dealer-1"
    assert updated["dealer-1"]["duplicate_of"] is None


def test_update_duplicate_flags_clears_a_previously_flagged_listing_no_longer_matching():
    # Simulates a listing that was flagged as a duplicate on a prior run
    # (price has since diverged past the tolerance) -- the flag should
    # be cleared, not left stale.
    stale_duplicate = make_listing(
        id="cl-1", marketplace_source="craigslist", price=15000, duplicate_of="dealer-1"
    )
    dealer_listing = make_listing(id="dealer-1", marketplace_source="dealeron", price=20000)
    supabase = FakeSupabase(initial_data={"listings": [stale_duplicate, dealer_listing]})

    update_duplicate_flags(supabase)

    updated = {row["id"]: row for row in supabase.table("listings").data}
    assert updated["cl-1"]["duplicate_of"] is None


def test_update_duplicate_flags_only_considers_active_listings():
    supabase = FakeSupabase(
        initial_data={
            "listings": [
                make_listing(id="cl-1", marketplace_source="craigslist", status="active"),
                make_listing(id="dealer-1", marketplace_source="dealeron", status="sold"),
            ]
        }
    )

    count = update_duplicate_flags(supabase)

    assert count == 0
    call = supabase.table("listings").calls[0]
    assert call["op"] == "select"
    assert call["filters"] == {"status": "active"}
