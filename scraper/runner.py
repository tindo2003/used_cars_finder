import random
import time
from typing import Any, Callable, Dict, List, Optional

from models import SavedSearch
from options import ScrapeOptions


class ScrapeRunner:
    """
    Owns the actual "call a scraper, then call the DB saver" work that
    main.py used to do inline. Every dependency (db client, dealer list,
    platform->scraper mapping, marketplace scrapers, the sleep function)
    is passed in, so this can be tested with fakes instead of hitting
    real websites or a real database.
    """

    def __init__(
        self,
        db_client: Any,
        dealers: List[Dict[str, Any]],
        dealer_scrapers: Dict[str, Callable[..., List[Dict[str, Any]]]],
        active_marketplaces: List[Callable[..., List[Dict[str, Any]]]],
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self.db_client = db_client
        self.dealers = dealers
        self.dealer_scrapers = dealer_scrapers
        self.active_marketplaces = active_marketplaces
        self.sleep_fn = sleep_fn

    def run_marketplace_searches(
        self,
        searches: List[SavedSearch],
        dry_run: bool,
        progress: Dict[str, Any],
        log_interval_seconds: float,
    ) -> None:
        for search in searches:
            makes = search.make or []
            models = search.model or []

            if not makes and not models:
                continue

            # A saved search can watch several makes/models at once
            # (migration 014, any-of-list semantics) -- Craigslist's
            # search endpoint only takes one query at a time, so cover
            # every make x model combination (the same AND-of-two-OR-sets
            # semantics the search filter and notification matching use).
            # `[None]` stands in for an unset dimension so e.g. "any
            # Camry" (no make filter) still runs once, not zero times.
            make_options: List[Optional[str]] = list(makes) if makes else [None]
            model_options: List[Optional[str]] = list(models) if models else [None]
            for make in make_options:
                for model in model_options:
                    print(f"\nEvaluating target: {(make or '').capitalize()} {(model or '').capitalize()}")

                    options = ScrapeOptions(make=make, model=model, max_price=search.max_price)
                    for provider_func in self.active_marketplaces:
                        cars_found = provider_func(options)
                        self.db_client.bulk_save(cars_found, dry_run, progress, log_interval_seconds)

    def run_dealer_scrapes(
        self,
        dry_run: bool,
        progress: Dict[str, Any],
        log_interval_seconds: float,
        max_pages: Optional[int] = None,
    ) -> None:
        for dealer in self.dealers:
            scraper_func = self.dealer_scrapers.get(dealer["platform"])
            if not scraper_func:
                print(f"Unknown platform '{dealer['platform']}' for {dealer['url']}, skipping.")
                continue

            # Sleep before hitting a new dealership website
            wait_time = random.uniform(5, 10)
            print(f"Waiting {wait_time:.2f} seconds before next dealer...")
            self.sleep_fn(wait_time)

            options = ScrapeOptions(
                max_pages=max_pages,
                city=dealer.get("city"),
                dealer_name=dealer.get("name"),
            )
            cars_found = scraper_func(dealer["url"], options)
            self.db_client.bulk_save(cars_found, dry_run, progress, log_interval_seconds)

    def run(
        self,
        searches: List[SavedSearch],
        dry_run: bool,
        progress: Dict[str, Any],
        log_interval_seconds: float,
        max_pages: Optional[int] = None,
    ) -> None:
        self.run_marketplace_searches(searches, dry_run, progress, log_interval_seconds)
        self.run_dealer_scrapes(dry_run, progress, log_interval_seconds, max_pages)
