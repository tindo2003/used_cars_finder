from deals import DEAL_MIN_COMPARABLES, DEAL_THRESHOLD, compute_deal_score, is_good_deal, ranking_key, update_deal_scores
from tests.fakes import FakeSupabase


def make_listing(**overrides):
    listing = {
        "id": "listing-1",
        "make": "Toyota",
        "model": "Camry",
        "model_year": 2020,
        "mileage": 40000,
        "price": 15000,
    }
    listing.update(overrides)
    return listing


def make_comparables(prices, **shared_overrides):
    base = {"make": "Toyota", "model": "Camry", "model_year": 2020, "mileage": 40000}
    base.update(shared_overrides)
    return [make_listing(id=f"comp-{i}", price=price, **base) for i, price in enumerate(prices)]


# --- compute_deal_score ---


def test_returns_none_with_fewer_than_min_comparables():
    listing = make_listing(price=10000)
    comparables = make_comparables([20000, 20000])  # one short of DEAL_MIN_COMPARABLES
    assert len(comparables) == DEAL_MIN_COMPARABLES - 1

    assert compute_deal_score(listing, [listing] + comparables) is None


def test_computes_percentage_below_median_with_enough_comparables():
    listing = make_listing(price=8000)
    comparables = make_comparables([10000, 10000, 10000])  # median 10000

    score = compute_deal_score(listing, [listing] + comparables)

    assert score == 0.2  # (10000 - 8000) / 10000


def test_negative_score_when_priced_above_median():
    listing = make_listing(price=12000)
    comparables = make_comparables([10000, 10000, 10000])

    score = compute_deal_score(listing, [listing] + comparables)

    assert score == -0.2


def test_ignores_listings_of_a_different_make_or_model():
    listing = make_listing(price=8000)
    comparables = make_comparables([10000, 10000, 10000])
    unrelated = [
        make_listing(id="other-make", make="Honda", price=1000),
        make_listing(id="other-model", model="Corolla", price=1000),
    ]

    score = compute_deal_score(listing, [listing] + comparables + unrelated)

    assert score == 0.2  # unaffected by the unrelated listings


def test_excludes_listings_outside_the_year_window():
    listing = make_listing(price=8000, model_year=2020)
    # DEAL_YEAR_WINDOW is 2, so 2023 (3 years away) shouldn't count
    comparables = make_comparables([10000, 10000, 10000])
    too_old = [make_listing(id="too-old", model_year=2023, price=1000)]

    score = compute_deal_score(listing, [listing] + comparables + too_old)

    assert score == 0.2


def test_excludes_listings_outside_the_mileage_window():
    listing = make_listing(price=8000, mileage=40000)
    # DEAL_MILEAGE_WINDOW is 20000, so 100000 (60k away) shouldn't count
    comparables = make_comparables([10000, 10000, 10000])
    too_high_mileage = [make_listing(id="high-mileage", mileage=100000, price=1000)]

    score = compute_deal_score(listing, [listing] + comparables + too_high_mileage)

    assert score == 0.2


def test_missing_mileage_does_not_exclude_comparables():
    listing = make_listing(price=8000, mileage=None)
    comparables = make_comparables([10000, 10000, 10000], mileage=None)

    score = compute_deal_score(listing, [listing] + comparables)

    assert score == 0.2


def test_returns_none_when_listing_has_no_price():
    listing = make_listing(price=None)
    comparables = make_comparables([10000, 10000, 10000])

    assert compute_deal_score(listing, [listing] + comparables) is None


def test_returns_none_when_listing_price_is_zero():
    # $0 is a known scraper artifact (price attribute missing/unparseable
    # on the source site), not a real asking price.
    listing = make_listing(price=0)
    comparables = make_comparables([10000, 10000, 10000])

    assert compute_deal_score(listing, [listing] + comparables) is None


def test_zero_priced_listings_are_excluded_from_the_comparable_pool():
    listing = make_listing(price=8000)
    real_comparables = make_comparables([10000, 10000, 10000])
    zero_priced = [make_listing(id="zero", price=0)]

    score = compute_deal_score(listing, [listing] + real_comparables + zero_priced)

    assert score == 0.2  # unaffected -- the $0 listing shouldn't pull the median down


# --- is_good_deal ---


def test_is_good_deal_true_at_or_above_threshold():
    listing = make_listing(price=8800)  # 12% below 10000
    comparables = make_comparables([10000, 10000, 10000])

    score = compute_deal_score(listing, [listing] + comparables)
    assert score >= DEAL_THRESHOLD
    assert is_good_deal(listing, [listing] + comparables) is True


def test_is_good_deal_false_below_threshold():
    listing = make_listing(price=9500)  # only 5% below median
    comparables = make_comparables([10000, 10000, 10000])

    assert is_good_deal(listing, [listing] + comparables) is False


def test_is_good_deal_false_without_enough_comparables():
    listing = make_listing(price=1000)
    comparables = make_comparables([10000, 10000])

    assert is_good_deal(listing, [listing] + comparables) is False


# --- ranking_key ---


def test_ranking_key_orders_scored_listings_by_best_deal_first():
    great_deal = make_listing(id="great", price=7000)
    ok_deal = make_listing(id="ok", price=9000)
    comparables = make_comparables([10000, 10000, 10000])
    pool = [great_deal, ok_deal] + comparables

    ordered = sorted([great_deal, ok_deal], key=lambda listing: ranking_key(listing, pool))

    assert [listing["id"] for listing in ordered] == ["great", "ok"]


def test_ranking_key_falls_back_to_price_when_score_unavailable():
    cheap_unscored = make_listing(id="cheap", make="Rare", price=5000)
    pricier_unscored = make_listing(id="pricier", make="Rare", price=6000)
    # no comparables for "Rare" make at all -- neither can be scored

    ordered = sorted(
        [pricier_unscored, cheap_unscored],
        key=lambda listing: ranking_key(listing, [cheap_unscored, pricier_unscored]),
    )

    assert [listing["id"] for listing in ordered] == ["cheap", "pricier"]


def test_ranking_key_prefers_scored_deals_over_unscored_cheaper_listings():
    scored_deal = make_listing(id="scored", price=8000)  # 20% below comparable median
    comparables = make_comparables([10000, 10000, 10000])
    unscored_cheaper = make_listing(id="unscored", make="Rare", price=100)  # cheaper but no comparables

    pool = [scored_deal, unscored_cheaper] + comparables
    ordered = sorted([unscored_cheaper, scored_deal], key=lambda listing: ranking_key(listing, pool))

    assert [listing["id"] for listing in ordered] == ["scored", "unscored"]


def test_ranking_key_breaks_a_score_tie_by_more_recently_seen_first():
    seen_recently = make_listing(id="recent", price=8000, last_seen_at="2026-07-20T00:00:00Z")
    seen_a_while_ago = make_listing(id="stale", price=8000, last_seen_at="2026-01-01T00:00:00Z")
    comparables = make_comparables([10000, 10000, 10000])  # both score identically at 20% off

    pool = [seen_recently, seen_a_while_ago] + comparables
    ordered = sorted([seen_a_while_ago, seen_recently], key=lambda listing: ranking_key(listing, pool))

    assert [listing["id"] for listing in ordered] == ["recent", "stale"]


def test_ranking_key_breaks_a_price_tie_by_more_recently_seen_first():
    seen_recently = make_listing(id="recent", make="Rare", price=5000, last_seen_at="2026-07-20T00:00:00Z")
    seen_a_while_ago = make_listing(id="stale", make="Rare", price=5000, last_seen_at="2026-01-01T00:00:00Z")
    # no comparables for "Rare" -- both fall back to the price tier, which ties

    ordered = sorted(
        [seen_a_while_ago, seen_recently],
        key=lambda listing: ranking_key(listing, [seen_recently, seen_a_while_ago]),
    )

    assert [listing["id"] for listing in ordered] == ["recent", "stale"]


def test_ranking_key_treats_missing_last_seen_at_as_least_recent():
    seen_recently = make_listing(id="recent", price=8000, last_seen_at="2026-07-20T00:00:00Z")
    never_recorded = make_listing(id="unknown", price=8000, last_seen_at=None)
    comparables = make_comparables([10000, 10000, 10000])

    pool = [seen_recently, never_recorded] + comparables
    ordered = sorted([never_recorded, seen_recently], key=lambda listing: ranking_key(listing, pool))

    assert [listing["id"] for listing in ordered] == ["recent", "unknown"]


# --- update_deal_scores() ---


def test_update_deal_scores_writes_score_and_flag_for_a_good_deal():
    deal = make_listing(id="deal", price=8000, status="active")
    comparables = [
        make_listing(id=f"comp-{i}", price=10000, status="active") for i in range(3)
    ]
    supabase = FakeSupabase(initial_data={"listings": [deal] + comparables})

    good_count = update_deal_scores(supabase)

    assert good_count == 1
    updated = {row["id"]: row for row in supabase.table("listings").data}
    assert updated["deal"]["is_good_deal"] is True
    assert updated["deal"]["deal_score"] == 0.2


def test_update_deal_scores_flags_false_for_non_deals():
    fair_price = make_listing(id="fair", price=9700, status="active")
    comparables = [
        make_listing(id=f"comp-{i}", price=10000, status="active") for i in range(3)
    ]
    supabase = FakeSupabase(initial_data={"listings": [fair_price] + comparables})

    good_count = update_deal_scores(supabase)

    assert good_count == 0
    updated = {row["id"]: row for row in supabase.table("listings").data}
    assert updated["fair"]["is_good_deal"] is False


def test_update_deal_scores_only_considers_active_listings():
    supabase = FakeSupabase(
        initial_data={
            "listings": [
                make_listing(id="active-1", price=8000, status="active"),
                make_listing(id="active-2", price=10000, status="active"),
                make_listing(id="active-3", price=10000, status="active"),
                make_listing(id="active-4", price=10000, status="active"),
                make_listing(id="sold", price=1000, status="sold"),
            ]
        }
    )

    update_deal_scores(supabase)

    call = supabase.table("listings").calls[0]
    assert call["op"] == "select"
    assert call["filters"] == {"status": "active"}
