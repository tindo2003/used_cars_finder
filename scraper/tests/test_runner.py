from options import ScrapeOptions
from runner import ScrapeRunner


class FakeDbClient:
    def __init__(self):
        self.calls = []

    def bulk_save(self, cars, dry_run, progress, log_interval_seconds):
        self.calls.append({"cars": cars, "dry_run": dry_run})


def make_runner(dealers=None, dealer_scrapers=None, active_marketplaces=None, sleep_fn=None):
    db_client = FakeDbClient()
    runner = ScrapeRunner(
        db_client,
        dealers if dealers is not None else [],
        dealer_scrapers if dealer_scrapers is not None else {},
        active_marketplaces if active_marketplaces is not None else [],
        sleep_fn=sleep_fn if sleep_fn is not None else (lambda seconds: None),
    )
    return runner, db_client


def make_progress():
    return {"saved": 0, "last_log": 0}


# --- run_marketplace_searches ---


def test_run_marketplace_searches_calls_provider_with_search_filters():
    captured_options = []

    def fake_provider(options):
        captured_options.append(options)
        return [{"make": "Toyota", "model": "Camry"}]

    runner, db_client = make_runner(active_marketplaces=[fake_provider])
    searches = [{"make": ["Toyota"], "model": ["Camry"], "max_price": 20000}]

    runner.run_marketplace_searches(searches, dry_run=False, progress=make_progress(), log_interval_seconds=60)

    assert captured_options == [ScrapeOptions(make="Toyota", model="Camry", max_price=20000)]
    assert len(db_client.calls) == 1
    assert db_client.calls[0]["cars"] == [{"make": "Toyota", "model": "Camry"}]


def test_run_marketplace_searches_skips_searches_with_no_make_or_model():
    calls = []

    def fake_provider(options):
        calls.append(options)
        return []

    runner, db_client = make_runner(active_marketplaces=[fake_provider])
    searches = [{"make": None, "model": None, "max_price": 20000}]

    runner.run_marketplace_searches(searches, dry_run=False, progress=make_progress(), log_interval_seconds=60)

    assert calls == []
    assert db_client.calls == []


def test_run_marketplace_searches_calls_every_active_marketplace():
    calls = []

    def provider_a(options):
        calls.append("provider-a")
        return []

    def provider_b(options):
        calls.append("provider-b")
        return []

    runner, db_client = make_runner(active_marketplaces=[provider_a, provider_b])
    searches = [{"make": ["Honda"], "model": ["Civic"]}]

    runner.run_marketplace_searches(searches, dry_run=False, progress=make_progress(), log_interval_seconds=60)

    assert calls == ["provider-a", "provider-b"]
    assert len(db_client.calls) == 2


def test_run_marketplace_searches_covers_every_make_and_model_combination():
    # migration 014: make/model are lists now -- a search watching 2
    # makes and 2 models should search all 4 combinations, not just one.
    captured_options = []

    def fake_provider(options):
        captured_options.append(options)
        return []

    runner, _ = make_runner(active_marketplaces=[fake_provider])
    searches = [{"make": ["Toyota", "Lexus"], "model": ["Camry", "ES"]}]

    runner.run_marketplace_searches(searches, dry_run=False, progress=make_progress(), log_interval_seconds=60)

    assert {(o.make, o.model) for o in captured_options} == {
        ("Toyota", "Camry"),
        ("Toyota", "ES"),
        ("Lexus", "Camry"),
        ("Lexus", "ES"),
    }


def test_run_marketplace_searches_handles_multiple_makes_with_no_model_filter():
    captured_options = []

    def fake_provider(options):
        captured_options.append(options)
        return []

    runner, _ = make_runner(active_marketplaces=[fake_provider])
    searches = [{"make": ["Toyota", "Lexus"], "model": None}]

    runner.run_marketplace_searches(searches, dry_run=False, progress=make_progress(), log_interval_seconds=60)

    assert {(o.make, o.model) for o in captured_options} == {("Toyota", None), ("Lexus", None)}


# --- run_dealer_scrapes ---


def test_run_dealer_scrapes_calls_the_scraper_matching_the_dealer_platform():
    captured = []

    def fake_dealeron_scrape(url, options):
        captured.append((url, options))
        return [{"make": "Toyota"}]

    dealers = [{"url": "https://example.com", "platform": "dealeron", "city": "San Jose", "name": "Example Toyota"}]
    runner, db_client = make_runner(dealers=dealers, dealer_scrapers={"dealeron": fake_dealeron_scrape})

    runner.run_dealer_scrapes(dry_run=False, progress=make_progress(), log_interval_seconds=60, max_pages=1)

    assert len(captured) == 1
    url, options = captured[0]
    assert url == "https://example.com"
    assert options == ScrapeOptions(max_pages=1, city="San Jose", dealer_name="Example Toyota")
    assert len(db_client.calls) == 1


def test_run_dealer_scrapes_skips_dealers_with_an_unknown_platform(capsys):
    dealers = [{"url": "https://example.com", "platform": "unknown-platform"}]
    runner, db_client = make_runner(dealers=dealers, dealer_scrapers={"dealeron": lambda url, options: []})

    runner.run_dealer_scrapes(dry_run=False, progress=make_progress(), log_interval_seconds=60)

    assert db_client.calls == []
    assert "Unknown platform" in capsys.readouterr().out


def test_run_dealer_scrapes_uses_the_injected_sleep_fn_instead_of_real_sleep():
    sleep_calls = []
    dealers = [{"url": "https://example.com", "platform": "dealeron"}]
    runner, _ = make_runner(
        dealers=dealers,
        dealer_scrapers={"dealeron": lambda url, options: []},
        sleep_fn=lambda seconds: sleep_calls.append(seconds),
    )

    runner.run_dealer_scrapes(dry_run=False, progress=make_progress(), log_interval_seconds=60)

    assert len(sleep_calls) == 1
    assert 5 <= sleep_calls[0] <= 10


# --- run() ---


def test_run_executes_marketplace_searches_then_dealer_scrapes():
    call_order = []

    def fake_provider(options):
        call_order.append("marketplace")
        return []

    def fake_dealer_scrape(url, options):
        call_order.append("dealer")
        return []

    runner, db_client = make_runner(
        dealers=[{"url": "https://example.com", "platform": "dealeron"}],
        dealer_scrapers={"dealeron": fake_dealer_scrape},
        active_marketplaces=[fake_provider],
    )
    searches = [{"make": ["Honda"], "model": ["Civic"]}]

    runner.run(searches, dry_run=False, progress=make_progress(), log_interval_seconds=60)

    assert call_order == ["marketplace", "dealer"]
