from notifications import matches, notify_matches
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
    return search


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
    return listing


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


# --- notify_matches() ---


def test_notify_matches_sends_email_and_records_history():
    supabase = FakeSupabase(
        initial_data={
            "saved_searches": [make_search(max_price=20000)],
            "listings": [make_listing(price=15000)],
        }
    )
    sent_emails = []

    count = notify_matches(supabase, send_email_fn=lambda email, listing: sent_emails.append((email, listing)))

    assert count == 1
    assert sent_emails == [("buyer@example.com", make_listing(price=15000))]
    history = supabase.table("notification_history").data
    assert len(history) == 1
    assert history[0]["saved_search_id"] == "search-1"
    assert history[0]["listing_id"] == "listing-1"


def test_notify_matches_skips_already_notified_pairs():
    supabase = FakeSupabase(
        initial_data={
            "saved_searches": [make_search()],
            "listings": [make_listing()],
            "notification_history": [{"saved_search_id": "search-1", "listing_id": "listing-1"}],
        }
    )
    sent_emails = []

    count = notify_matches(supabase, send_email_fn=lambda email, listing: sent_emails.append(email))

    assert count == 0
    assert sent_emails == []


def test_notify_matches_skips_non_matching_listings():
    supabase = FakeSupabase(
        initial_data={
            "saved_searches": [make_search(make="Honda")],
            "listings": [make_listing(make="Toyota")],
        }
    )
    sent_emails = []

    count = notify_matches(supabase, send_email_fn=lambda email, listing: sent_emails.append(email))

    assert count == 0
    assert sent_emails == []


def test_notify_matches_ignores_inactive_saved_searches():
    supabase = FakeSupabase(
        initial_data={
            "saved_searches": [make_search(is_active=False)],
            "listings": [make_listing()],
        }
    )
    sent_emails = []

    count = notify_matches(supabase, send_email_fn=lambda email, listing: sent_emails.append(email))

    assert count == 0
    assert sent_emails == []


def test_notify_matches_ignores_searches_without_an_email():
    supabase = FakeSupabase(
        initial_data={
            "saved_searches": [make_search(email=None)],
            "listings": [make_listing()],
        }
    )
    sent_emails = []

    count = notify_matches(supabase, send_email_fn=lambda email, listing: sent_emails.append(email))

    assert count == 0
    assert sent_emails == []


def test_notify_matches_notifies_multiple_matching_searches_for_one_listing():
    supabase = FakeSupabase(
        initial_data={
            "saved_searches": [
                make_search(id="search-1", email="a@example.com"),
                make_search(id="search-2", email="b@example.com"),
            ],
            "listings": [make_listing()],
        }
    )
    sent_emails = []

    count = notify_matches(supabase, send_email_fn=lambda email, listing: sent_emails.append(email))

    assert count == 2
    assert set(sent_emails) == {"a@example.com", "b@example.com"}
