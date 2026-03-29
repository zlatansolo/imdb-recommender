"""
Fetches IMDb ratings and watchlist, saves both to data/.
Run by GitHub Actions weekly or on workflow_dispatch.
"""

import sys
import traceback

from dotenv import load_dotenv
load_dotenv()

from fetch_ratings import fetch_all


def main() -> None:
    print("=" * 60)
    print("Fetching IMDb ratings + watchlist")
    print("=" * 60)
    try:
        ratings_path, watchlist_path = fetch_all()
    except Exception as e:
        print(f"ERROR: {e}")
        traceback.print_exc()
        sys.exit(1)

    print("\nAll done.")
    print(f"  Ratings:   {ratings_path}")
    print(f"  Watchlist: {watchlist_path}")


if __name__ == "__main__":
    main()
