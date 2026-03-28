"""
Orchestrator: fetch ratings → get recommendations → send email.
"""

import json
import os
import sys
import traceback
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fetch_ratings import fetch_ratings
from get_recommendations import get_recommendations
from send_email import send_email


def main() -> None:
    skip_fetch = os.environ.get("SKIP_FETCH", "false").lower() == "true"

    # ── 1. Fetch ratings ──────────────────────────────────────────────────────
    print("=" * 60)
    print("STEP 1: Fetching IMDb ratings")
    print("=" * 60)
    csv_path = Path("ratings.csv")
    if skip_fetch and csv_path.exists():
        print(f"SKIP_FETCH=true — using existing {csv_path}")
    else:
        try:
            csv_path = fetch_ratings()
        except Exception as e:
            print(f"ERROR fetching ratings: {e}")
            traceback.print_exc()
            sys.exit(1)

    # ── 2. Get recommendations ────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("STEP 2: Generating recommendations with Claude")
    print("=" * 60)
    try:
        recommendations = get_recommendations(csv_path)
        # Save for debugging
        debug_path = Path("recommendations.json")
        with open(debug_path, "w") as f:
            json.dump(recommendations, f, indent=2)
        print(f"Recommendations saved to {debug_path}")
    except Exception as e:
        print(f"ERROR generating recommendations: {e}")
        traceback.print_exc()
        sys.exit(1)

    # ── 3. Send email ─────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("STEP 3: Sending email")
    print("=" * 60)
    try:
        send_email(recommendations)
    except Exception as e:
        print(f"ERROR sending email: {e}")
        traceback.print_exc()
        sys.exit(1)

    print("\n" + "=" * 60)
    print("All done! Email sent successfully.")
    print("=" * 60)


if __name__ == "__main__":
    main()
