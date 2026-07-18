import argparse
from providers import craigslist, dealeron, dealerinspire
from options import ScrapeOptions
from db import get_supabase, DbClient
from notifications import notify_matches, DEFAULT_TOP_N
import time
import random

DEALERS = [
    # San Jose
    {"url": "https://www.stevenscreektoyota.com", "platform": "dealeron", "city": "San Jose"},
    {"url": "https://www.capitolhonda.com", "platform": "dealerinspire", "city": "San Jose"},
    {"url": "https://www.capitolford.com", "platform": "dealerinspire", "city": "San Jose"},
    {"url": "https://www.capitolchevysj.com", "platform": "dealerinspire", "city": "San Jose"},
    {"url": "https://www.capitolhyundaisj.com", "platform": "dealerinspire", "city": "San Jose"},
    # Santa Clara
    {"url": "https://www.stevenscreekhyundai.com", "platform": "dealerinspire", "city": "Santa Clara"},
    # Sunnyvale
    {"url": "https://www.sunnyvalehonda.com", "platform": "dealerinspire", "city": "Sunnyvale"},
    # Fremont / Newark
    {"url": "https://www.chevroletoffremont.com", "platform": "dealeron", "city": "Fremont"},
    {"url": "https://www.fremonthyundai.com", "platform": "dealeron", "city": "Fremont"},
    {"url": "https://www.fremontcdjr.com", "platform": "dealerinspire", "city": "Newark"},
]

DEALER_SCRAPERS = {
    "dealeron": dealeron.scrape,
    "dealerinspire": dealerinspire.scrape,
}


def run_scraper(dry_run=False, max_pages=None, log_interval_minutes=1, notify_top_n=DEFAULT_TOP_N):
    supabase = None
    if not dry_run:
        supabase = get_supabase()
        print("Connected to Supabase.")
    else:
        print("--- RUNNING IN DRY RUN MODE (No DB connection) ---")

    db_client = DbClient(supabase)

    # Progress is logged at most once per log_interval_minutes instead of
    # once per saved listing, to keep GitHub Actions logs readable.
    progress = {"saved": 0, "last_log": time.monotonic()}
    log_interval_seconds = log_interval_minutes * 60

    print(f"Fetching saved searches... {'(DRY RUN MODE)' if dry_run else ''}")

    # Only fetch from DB if NOT a dry run
    if not dry_run:
        response = (
            supabase.table("saved_searches").select("*").eq("is_active", True).execute()
        )
        searches = response.data
    else:
        # Dummy data for dry run testing
        searches = [{"make": "Toyota", "model": "Camry", "max_price": 20000}]

    # --- 1. Scrape Marketplaces based on Saved Searches ---
    # eBay is intentionally excluded: its robots.txt explicitly disallows
    # this search pattern and prohibits automated access without
    # permission. See research/scraping-etiquette.md.
    active_marketplaces = [craigslist.scrape]

    for search in searches:
        make = search.get("make") or ""
        model = search.get("model") or ""

        if not make and not model:
            continue

        print(f"\nEvaluating target: {make.capitalize()} {model.capitalize()}")

        options = ScrapeOptions(make=make, model=model, max_price=search.get("max_price"))
        for provider_func in active_marketplaces:
            cars_found = provider_func(options)
            db_client.bulk_save(cars_found, dry_run, progress, log_interval_seconds)

    # --- 2. Scrape Dealerships (Independently of user searches) ---
    # Dealerships have their own inventory; we scrape their full used list
    for dealer in DEALERS:
        scraper_func = DEALER_SCRAPERS.get(dealer["platform"])
        if not scraper_func:
            print(f"Unknown platform '{dealer['platform']}' for {dealer['url']}, skipping.")
            continue

        # Sleep before hitting a new dealership website
        wait_time = random.uniform(5, 10)
        print(f"Waiting {wait_time:.2f} seconds before next dealer...")
        time.sleep(wait_time)

        options = ScrapeOptions(max_pages=max_pages, city=dealer.get("city"))
        cars_found = scraper_func(dealer["url"], options)
        db_client.bulk_save(cars_found, dry_run, progress, log_interval_seconds)

    print(f"Done. Saved {progress['saved']} listings total.")

    if not dry_run:
        sent = notify_matches(supabase, top_n=notify_top_n)
        print(f"Sent {sent} notification email(s).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the car scraper.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print results without saving to Supabase",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Limit how many inventory pages each dealer scraper fetches (useful for quick tests)",
    )
    parser.add_argument(
        "--log-interval",
        type=float,
        default=1,
        help="Minutes between progress log lines while saving listings (default: 1)",
    )
    parser.add_argument(
        "--notify-top-n",
        type=int,
        default=DEFAULT_TOP_N,
        help=f"Max listings included per notification digest email (default: {DEFAULT_TOP_N})",
    )
    args = parser.parse_args()

    run_scraper(
        dry_run=args.dry_run,
        max_pages=args.max_pages,
        log_interval_minutes=args.log_interval,
        notify_top_n=args.notify_top_n,
    )
