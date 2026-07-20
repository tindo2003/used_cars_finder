from typing import Any

import pytest

from options import ScrapeOptions
from providers import craigslist


class FakeResponse:
    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.status_code = status_code


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch: Any) -> None:
    # scrape() ends with a jittered 2-4s delay to stay polite to
    # Craigslist -- fine in production, pointless to actually wait for
    # in tests.
    monkeypatch.setattr(craigslist.time, "sleep", lambda *_: None)


def _search_result_html(*items: str) -> str:
    return f'<ul>{"".join(items)}</ul>'


def _listing_li(title: str, price: str, href: str = "https://www.craigslist.org/view/d/example") -> str:
    price_div = f'<div class="price">{price}</div>' if price is not None else ""
    return f"""
    <li class="cl-static-search-result">
      <a href="{href}">
        <div class="title">{title}</div>
        {price_div}
        <div class="location">san jose</div>
      </a>
    </li>
    """


def test_extract_year_finds_a_plausible_year_in_the_title():
    assert craigslist.extract_year("2022 Toyota Camry Hybrid LE 4dr Sedan") == 2022


def test_extract_year_defaults_when_no_year_present():
    assert craigslist.extract_year("Clean title, low miles!") == 2010


def test_rejects_result_whose_title_does_not_mention_the_searched_make(monkeypatch: Any):
    # Real bug: searching "toyota nx" (a combination that doesn't exist --
    # NX is a Lexus model) returned an unrelated Camry Hybrid ad, which the
    # old code mislabeled as "Toyota Nx" by trusting the query instead of
    # the actual title.
    html = _search_result_html(
        _listing_li("2022 Toyota Camry Hybrid Electric LE 4dr Sedan", "$403"),
        _listing_li("2020 LEXUS NX 300 F SPORT 2WD", "$22,995"),
    )
    monkeypatch.setattr(craigslist.requests, "get", lambda *a, **k: FakeResponse(html))

    results = craigslist.scrape(ScrapeOptions(make="toyota", model="nx"))

    assert results == []


def test_accepts_result_whose_title_mentions_both_make_and_model(monkeypatch: Any):
    html = _search_result_html(
        _listing_li("2022 Toyota Camry Hybrid Electric LE 4dr Sedan", "$22,500"),
    )
    monkeypatch.setattr(craigslist.requests, "get", lambda *a, **k: FakeResponse(html))

    results = craigslist.scrape(ScrapeOptions(make="toyota", model="camry"))

    assert len(results) == 1
    assert results[0]["make"] == "Toyota"
    assert results[0]["model"] == "Camry"
    assert results[0]["price"] == 22500


def test_rejects_implausibly_low_price(monkeypatch: Any):
    # Real bug: dealer-syndicated ads sometimes show a monthly payment
    # ($302-$420 observed) or a "$0" placeholder instead of a real price,
    # which then wins "best deal" ranking via the lowest-price fallback.
    html = _search_result_html(
        _listing_li("2021 Toyota Camry LE 4dr Sedan", "$302"),
        _listing_li("Certified 2025 Lexus Camry", "$0"),
    )
    monkeypatch.setattr(craigslist.requests, "get", lambda *a, **k: FakeResponse(html))

    results = craigslist.scrape(ScrapeOptions(make="toyota", model="camry"))

    assert results == []


def test_no_make_or_model_filter_accepts_any_title(monkeypatch: Any):
    # A saved search with only one dimension set (e.g. any make, a
    # specific model) shouldn't require the other to appear in the title.
    html = _search_result_html(_listing_li("2022 Toyota Camry Hybrid", "$22,500"))
    monkeypatch.setattr(craigslist.requests, "get", lambda *a, **k: FakeResponse(html))

    results = craigslist.scrape(ScrapeOptions(make=None, model="camry"))

    assert len(results) == 1
