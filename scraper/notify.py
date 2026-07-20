import argparse
import os
import sys

from db import get_supabase
from deals import update_deal_scores
from duplicates import update_duplicate_flags
from notifications import DEFAULT_TOP_N, notify_matches
from staleness import DEFAULT_STALE_THRESHOLD_DAYS, expire_stale_listings

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Check saved searches against current listings and email today's top matches."
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=DEFAULT_TOP_N,
        help=f"Max listings included per notification digest email (default: {DEFAULT_TOP_N})",
    )
    parser.add_argument(
        "--stale-threshold-days",
        type=int,
        default=DEFAULT_STALE_THRESHOLD_DAYS,
        help=(
            "Listings not reconfirmed by the scraper in this many days are "
            f"marked expired and excluded everywhere (default: {DEFAULT_STALE_THRESHOLD_DAYS})"
        ),
    )
    args = parser.parse_args()

    supabase = get_supabase()
    print("Connected to Supabase.")

    # Runs first so every step below (duplicate flags, deal scores,
    # notification matching) only ever sees non-expired listings, since
    # they all already filter on status="active".
    expired = expire_stale_listings(supabase, stale_threshold_days=args.stale_threshold_days)
    print(f"Expired {expired} listings not reconfirmed in over {args.stale_threshold_days} days.")

    duplicates = update_duplicate_flags(supabase)
    print(f"Updated duplicate flags; {duplicates} listings flagged as cross-marketplace duplicates.")

    good_deals = update_deal_scores(supabase)
    print(f"Updated deal scores; {good_deals} listings currently flagged as good deals.")

    sent = notify_matches(supabase, top_n=args.top_n)
    print(f"Sent {sent} notification email(s).")

    # Same fix as main.py: the real Supabase client leaves the process
    # hanging indefinitely after all work is done (confirmed live on ECS
    # Fargate), likely a non-daemon thread from its realtime/websockets
    # dependency that CPython waits on before it will exit on its own.
    # On a schedule that means indefinitely-billed Fargate time, so
    # force the exit rather than trust a clean shutdown.
    sys.stdout.flush()
    os._exit(0)
