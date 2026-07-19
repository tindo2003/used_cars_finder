import argparse
from providers import craigslist, dealeron, dealerinspire
from db import get_supabase, DbClient
from runner import ScrapeRunner
import time

DEALERS = [
    # San Jose
    {"url": "https://www.stevenscreektoyota.com", "platform": "dealeron", "city": "San Jose", "name": "Stevens Creek Toyota"},
    {"url": "https://www.lexusstevenscreek.com", "platform": "dealeron", "city": "San Jose", "name": "Lexus Stevens Creek"},
    {"url": "https://www.capitolhonda.com", "platform": "dealerinspire", "city": "San Jose", "name": "Capitol Honda"},
    {"url": "https://www.capitolford.com", "platform": "dealerinspire", "city": "San Jose", "name": "Capitol Ford"},
    {"url": "https://www.capitolchevysj.com", "platform": "dealerinspire", "city": "San Jose", "name": "Capitol Chevrolet"},
    {"url": "https://www.capitolhyundaisj.com", "platform": "dealerinspire", "city": "San Jose", "name": "Capitol Hyundai"},
    # Santa Clara
    {"url": "https://www.stevenscreekhyundai.com", "platform": "dealerinspire", "city": "Santa Clara", "name": "Stevens Creek Hyundai"},
    # Sunnyvale
    {"url": "https://www.sunnyvalehonda.com", "platform": "dealerinspire", "city": "Sunnyvale", "name": "Sunnyvale Honda"},
    # Fremont / Newark
    {"url": "https://www.chevroletoffremont.com", "platform": "dealeron", "city": "Fremont", "name": "Fremont Chevrolet"},
    {"url": "https://www.fremonthyundai.com", "platform": "dealeron", "city": "Fremont", "name": "Fremont Hyundai"},
    {"url": "https://www.fremontcdjr.com", "platform": "dealerinspire", "city": "Newark", "name": "Fremont Chrysler Dodge Jeep Ram"},
]

DEALER_SCRAPERS = {
    "dealeron": dealeron.scrape,
    "dealerinspire": dealerinspire.scrape,
}

# eBay is intentionally excluded: its robots.txt explicitly disallows this
# search pattern and prohibits automated access without permission. See
# research/scraping-etiquette.md.
ACTIVE_MARKETPLACES = [craigslist.scrape]


def run_scraper(dry_run=False, max_pages=None, log_interval_minutes=1):
    supabase = None
    if not dry_run:
        supabase = get_supabase()
        print("Connected to Supabase.")
    else:
        print("--- RUNNING IN DRY RUN MODE (No DB connection) ---")

    db_client = DbClient(supabase)

    # Progress is logged at most once per log_interval_minutes instead of
    # once per saved listing, to keep GitHub Actions logs readable.
    progress = {"saved": 0, "inserted": 0, "updated": 0, "skipped": 0, "last_log": time.monotonic()}
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

    runner = ScrapeRunner(db_client, DEALERS, DEALER_SCRAPERS, ACTIVE_MARKETPLACES)
    runner.run(searches, dry_run, progress, log_interval_seconds, max_pages)

    print(
        f"Done. Processed {progress['saved']} listings this run: "
        f"{progress['inserted']} new, {progress['updated']} already existed (re-confirmed), "
        f"{progress['skipped']} skipped (cross-dealer link collision)."
    )


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
    args = parser.parse_args()

    run_scraper(
        dry_run=args.dry_run,
        max_pages=args.max_pages,
        log_interval_minutes=args.log_interval,
    )
