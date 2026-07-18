import random
import time

from options import ScrapeOptions


class ScrapeRunner:
    """
    Owns the actual "call a scraper, then call the DB saver" work that
    main.py used to do inline. Every dependency (db client, dealer list,
    platform->scraper mapping, marketplace scrapers, the sleep function)
    is passed in, so this can be tested with fakes instead of hitting
    real websites or a real database.
    """

    def __init__(self, db_client, dealers, dealer_scrapers, active_marketplaces, sleep_fn=time.sleep):
        self.db_client = db_client
        self.dealers = dealers
        self.dealer_scrapers = dealer_scrapers
        self.active_marketplaces = active_marketplaces
        self.sleep_fn = sleep_fn

    def run_marketplace_searches(self, searches, dry_run, progress, log_interval_seconds):
        for search in searches:
            make = search.get("make") or ""
            model = search.get("model") or ""

            if not make and not model:
                continue

            print(f"\nEvaluating target: {make.capitalize()} {model.capitalize()}")

            options = ScrapeOptions(make=make, model=model, max_price=search.get("max_price"))
            for provider_func in self.active_marketplaces:
                cars_found = provider_func(options)
                self.db_client.bulk_save(cars_found, dry_run, progress, log_interval_seconds)

    def run_dealer_scrapes(self, dry_run, progress, log_interval_seconds, max_pages=None):
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

    def run(self, searches, dry_run, progress, log_interval_seconds, max_pages=None):
        self.run_marketplace_searches(searches, dry_run, progress, log_interval_seconds)
        self.run_dealer_scrapes(dry_run, progress, log_interval_seconds, max_pages)
