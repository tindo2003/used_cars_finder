import argparse

from db import get_supabase
from notifications import DEFAULT_TOP_N, notify_matches

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Check saved searches against current listings and email any new matches."
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=DEFAULT_TOP_N,
        help=f"Max listings included per notification digest email (default: {DEFAULT_TOP_N})",
    )
    args = parser.parse_args()

    supabase = get_supabase()
    print("Connected to Supabase.")

    sent = notify_matches(supabase, top_n=args.top_n)
    print(f"Sent {sent} notification email(s).")
