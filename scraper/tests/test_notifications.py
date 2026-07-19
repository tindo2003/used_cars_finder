from datetime import datetime, timedelta, timezone

from models import Listing, SavedSearch
from notifications import DEFAULT_TOP_N, _format_listing_html, _seller_label, matches, notify_matches
from tests.fakes import FakeSupabase


def make_search(**overrides):
    search = {
        "id": "search-1",
        "email": "buyer@example.com",
        "is_active": True,
        "make": None,
        "model": None,
        "max_price": None,
        "min_year": None,
        "max_mileage": None,
        "transmission": None,
        "seller_type": None,
    }
    search.update(overrides)
    return SavedSearch.model_validate(search)


def make_search_row(**overrides):
    """Same defaults as make_search(), but as a plain dict -- for
    seeding FakeSupabase's saved_searches table."""
    return make_search(**overrides).model_dump(exclude_none=True)


def make_listing(**overrides):
    listing = {
        "id": "listing-1",
        "status": "active",
        "make": "Toyota",
        "model": "Camry",
        "model_year": 2020,
        "price": 15000,
        "mileage": 40000,
        "transmission": "Automatic",
        "seller_type": "dealer",
    }
    listing.update(overrides)
    return Listing.model_validate(listing)


def make_listing_row(**overrides):
    """Same defaults as make_listing(), but as a plain dict -- for
    seeding FakeSupabase, which stores/returns rows exactly as Supabase
    would (see read_listings(), the boundary that validates them back
    into a Listing)."""
    return make_listing(**overrides).model_dump(exclude_none=True)


# --- matches() ---


def test_matches_with_no_filters_set_always_passes():
    assert matches(make_listing(), make_search()) is True


def test_matches_rejects_wrong_make():
    assert matches(make_listing(make="Honda"), make_search(make="Toyota")) is False


def test_matches_accepts_case_insensitive_make():
    assert matches(make_listing(make="toyota"), make_search(make="TOYOTA")) is True


def test_matches_model_is_a_substring_match():
    assert matches(make_listing(model="Corolla Hatchback"), make_search(model="corolla")) is True


def test_matches_rejects_price_above_max():
    assert matches(make_listing(price=25000), make_search(max_price=20000)) is False


def test_matches_accepts_price_at_or_below_max():
    assert matches(make_listing(price=20000), make_search(max_price=20000)) is True


def test_matches_rejects_year_below_min():
    assert matches(make_listing(model_year=2015), make_search(min_year=2018)) is False


def test_matches_rejects_mileage_above_max():
    assert matches(make_listing(mileage=80000), make_search(max_mileage=50000)) is False


def test_matches_does_not_exclude_when_listing_mileage_is_missing():
    # Craigslist listings often lack mileage -- unknown data shouldn't
    # hide a possible match.
    assert matches(make_listing(mileage=None), make_search(max_mileage=50000)) is True


def test_matches_rejects_wrong_transmission():
    assert matches(make_listing(transmission="Manual"), make_search(transmission="Automatic")) is False


def test_matches_rejects_wrong_seller_type():
    assert matches(make_listing(seller_type="private"), make_search(seller_type="dealer")) is False


# --- _seller_label() ---


def test_seller_label_prefers_dealer_name_and_city():
    listing = make_listing(dealer_name="Capitol Ford", city="San Jose", marketplace_source="dealeron")
    assert _seller_label(listing) == "Capitol Ford · San Jose"


def test_seller_label_falls_back_to_dealer_name_alone_without_a_city():
    listing = make_listing(dealer_name="Capitol Ford", city=None, marketplace_source="dealeron")
    assert _seller_label(listing) == "Capitol Ford"


def test_seller_label_uses_a_friendly_marketplace_label_without_a_dealer_name():
    listing = make_listing(dealer_name=None, marketplace_source="craigslist")
    assert _seller_label(listing) == "Craigslist"


def test_seller_label_falls_back_to_the_raw_marketplace_source_if_unrecognized():
    listing = make_listing(dealer_name=None, marketplace_source="some_new_platform")
    assert _seller_label(listing) == "some_new_platform"


# --- _format_listing_html() ---


def test_format_listing_html_includes_the_seller_label_and_last_updated():
    two_hours_ago = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    listing = make_listing(
        dealer_name="Capitol Ford",
        city="San Jose",
        marketplace_source="dealeron",
        last_seen_at=two_hours_ago,
        original_url="https://example.com/listing-1",
    )

    html = _format_listing_html(listing)

    assert "Capitol Ford · San Jose" in html
    assert "Updated 2 hours ago" in html
    assert "dealeron" not in html


def test_format_listing_html_omits_last_updated_when_last_seen_at_is_missing():
    listing = make_listing(last_seen_at=None)

    html = _format_listing_html(listing)

    assert "Updated" not in html


# --- notify_matches(): basic single-match behavior ---


def test_notify_matches_sends_one_digest_email_and_records_history():
    supabase = FakeSupabase(
        initial_data={
            "saved_searches": [make_search_row(max_price=20000)],
            "listings": [make_listing_row(price=15000)],
        }
    )
    digests = []

    count = notify_matches(supabase, send_email_fn=lambda email, listings: digests.append((email, listings)))

    assert count == 1  # one email sent
    assert digests == [("buyer@example.com", [make_listing(price=15000)])]
    history = supabase.table("notification_history").data
    assert len(history) == 1
    assert history[0]["saved_search_id"] == "search-1"
    assert history[0]["listing_id"] == "listing-1"


def test_notify_matches_sends_nothing_when_no_new_matches():
    supabase = FakeSupabase(
        initial_data={
            "saved_searches": [make_search_row()],
            "listings": [make_listing_row()],
            "notification_history": [{"saved_search_id": "search-1", "listing_id": "listing-1"}],
        }
    )
    digests = []

    count = notify_matches(supabase, send_email_fn=lambda email, listings: digests.append(listings))

    assert count == 0
    assert digests == []


def test_notify_matches_skips_non_matching_listings():
    supabase = FakeSupabase(
        initial_data={
            "saved_searches": [make_search_row(make="Honda")],
            "listings": [make_listing_row(make="Toyota")],
        }
    )
    digests = []

    count = notify_matches(supabase, send_email_fn=lambda email, listings: digests.append(listings))

    assert count == 0
    assert digests == []


def test_notify_matches_ignores_inactive_saved_searches():
    supabase = FakeSupabase(
        initial_data={
            "saved_searches": [make_search_row(is_active=False)],
            "listings": [make_listing_row()],
        }
    )
    digests = []

    count = notify_matches(supabase, send_email_fn=lambda email, listings: digests.append(listings))

    assert count == 0
    assert digests == []


def test_notify_matches_ignores_searches_without_an_email():
    supabase = FakeSupabase(
        initial_data={
            "saved_searches": [make_search_row(email=None)],
            "listings": [make_listing_row()],
        }
    )
    digests = []

    count = notify_matches(supabase, send_email_fn=lambda email, listings: digests.append(listings))

    assert count == 0
    assert digests == []


def test_notify_matches_sends_separate_digests_for_separate_searches():
    supabase = FakeSupabase(
        initial_data={
            "saved_searches": [
                make_search_row(id="search-1", email="a@example.com"),
                make_search_row(id="search-2", email="b@example.com"),
            ],
            "listings": [make_listing_row()],
        }
    )
    digests = []

    count = notify_matches(supabase, send_email_fn=lambda email, listings: digests.append(email))

    assert count == 2
    assert set(digests) == {"a@example.com", "b@example.com"}


# --- notify_matches(): batching into one digest, configurable top_n ---


def test_notify_matches_batches_all_new_matches_into_one_email():
    listings = [make_listing_row(id=f"listing-{i}", price=10000 + i * 1000) for i in range(4)]
    supabase = FakeSupabase(
        initial_data={
            "saved_searches": [make_search_row(max_price=100000)],
            "listings": listings,
        }
    )
    digests = []

    count = notify_matches(supabase, send_email_fn=lambda email, listings: digests.append(listings))

    assert count == 1  # one email, not four
    assert len(digests) == 1
    assert len(digests[0]) == 4


def test_notify_matches_caps_digest_at_default_top_n():
    listings = [make_listing_row(id=f"listing-{i}", price=10000 + i * 1000) for i in range(DEFAULT_TOP_N + 5)]
    supabase = FakeSupabase(
        initial_data={
            "saved_searches": [make_search_row()],  # no filters -- matches everything
            "listings": listings,
        }
    )
    digests = []

    count = notify_matches(supabase, send_email_fn=lambda email, listings: digests.append(listings))

    assert count == 1
    assert len(digests[0]) == DEFAULT_TOP_N


def test_notify_matches_digest_contains_the_cheapest_listings_first():
    listings = [make_listing_row(id=f"listing-{i}", price=10000 + i * 1000) for i in range(DEFAULT_TOP_N + 5)]
    supabase = FakeSupabase(
        initial_data={
            "saved_searches": [make_search_row()],
            "listings": listings,
        }
    )
    digests = []

    notify_matches(supabase, send_email_fn=lambda email, listings: digests.append(listings))

    prices = [listing.price for listing in digests[0] if listing.price is not None]
    assert prices == sorted(prices)
    assert prices[0] == 10000


def test_notify_matches_respects_a_custom_top_n():
    listings = [make_listing_row(id=f"listing-{i}", price=10000 + i * 1000) for i in range(10)]
    supabase = FakeSupabase(
        initial_data={
            "saved_searches": [make_search_row()],
            "listings": listings,
        }
    )
    digests = []

    notify_matches(supabase, send_email_fn=lambda email, listings: digests.append(listings), top_n=3)

    assert len(digests[0]) == 3


def test_notify_matches_records_history_for_every_listing_in_the_digest():
    listings = [make_listing_row(id=f"listing-{i}", price=10000 + i * 1000) for i in range(3)]
    supabase = FakeSupabase(
        initial_data={
            "saved_searches": [make_search_row()],
            "listings": listings,
        }
    )

    notify_matches(supabase, send_email_fn=lambda email, listings: None)

    history = supabase.table("notification_history").data
    assert {row["listing_id"] for row in history} == {"listing-0", "listing-1", "listing-2"}


def test_notify_matches_next_run_surfaces_the_next_cheapest_once_top_n_already_notified():
    listings = [make_listing_row(id=f"listing-{i}", price=10000 + i * 1000) for i in range(5)]
    supabase = FakeSupabase(
        initial_data={
            "saved_searches": [make_search_row()],
            "listings": listings,
        }
    )

    notify_matches(supabase, send_email_fn=lambda email, listings: None, top_n=3)
    digests = []
    notify_matches(supabase, send_email_fn=lambda email, listings: digests.append(listings), top_n=3)

    # listing-0/1/2 already notified in the first run; the second run
    # should surface listing-3 and listing-4, the next cheapest.
    assert len(digests) == 1
    assert {listing.id for listing in digests[0]} == {"listing-3", "listing-4"}
