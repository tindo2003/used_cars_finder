from utils.pagination import page_did_not_advance


def test_first_page_never_counts_as_a_stall():
    # previous_vins is None before any page has been scraped yet.
    assert page_did_not_advance(current_vins={"VIN1", "VIN2"}, previous_vins=None) is False


def test_identical_vins_across_pages_is_a_stall():
    # The exact bug found live: "Next" click succeeds, but the page's
    # content is unchanged.
    vins = frozenset({"VIN1", "VIN2", "VIN3"})
    assert page_did_not_advance(current_vins=vins, previous_vins=vins) is True


def test_completely_different_vins_advances_normally():
    # The case the fix must NOT break: pagination genuinely working,
    # each page showing different vehicles.
    page_1 = frozenset({"VIN1", "VIN2", "VIN3"})
    page_2 = frozenset({"VIN4", "VIN5", "VIN6"})
    assert page_did_not_advance(current_vins=page_2, previous_vins=page_1) is False


def test_partial_overlap_between_pages_still_advances():
    # Real inventory can shift between page loads (a vehicle sells, a new
    # one appears) -- as long as the sets aren't an exact match, this is
    # real pagination, not a stall.
    page_1 = frozenset({"VIN1", "VIN2", "VIN3"})
    page_2 = frozenset({"VIN2", "VIN3", "VIN4"})
    assert page_did_not_advance(current_vins=page_2, previous_vins=page_1) is False


def test_empty_current_page_never_counts_as_a_stall():
    # Couldn't read any VINs off this page (e.g. a markup change) -- not
    # enough information to call it a stall; let the caller's normal
    # "next button" check decide instead.
    assert page_did_not_advance(current_vins=frozenset(), previous_vins=frozenset({"VIN1"})) is False


def test_many_pages_of_real_pagination_never_falsely_stall():
    # Simulates walking through several genuinely distinct pages in a
    # row, confirming the guard doesn't fire at any point.
    pages = [
        frozenset({"VIN1", "VIN2"}),
        frozenset({"VIN3", "VIN4"}),
        frozenset({"VIN5", "VIN6"}),
        frozenset({"VIN7", "VIN8"}),
    ]
    previous = None
    for page in pages:
        assert page_did_not_advance(current_vins=page, previous_vins=previous) is False
        previous = page
