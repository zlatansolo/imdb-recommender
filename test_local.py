"""
Local test runner.
Usage:
  python test_local.py recommendations   # Call Claude API and save recommendations.json
  python test_local.py email             # Build HTML from saved recommendations.json (no send)
  python test_local.py send              # Actually send the email
  python test_local.py all               # recommendations + send

Requires: .env file with ANTHROPIC_API_KEY (and GMAIL_* for send)
Requires: ratings.csv in the project root (export from IMDb manually first)
"""

import json
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, "src")


def test_recommendations(csv_path: Path) -> dict:
    from get_recommendations import get_recommendations
    print(f"Using ratings CSV: {csv_path}")
    recs = get_recommendations(csv_path)
    out = Path("recommendations.json")
    out.write_text(json.dumps(recs, indent=2))
    print(f"\nSaved to {out}")
    for category, items in recs.items():
        print(f"  {category}: {len(items)} recommendations")
    return recs


def test_email_render(recs: dict) -> None:
    from send_email import build_html
    html = build_html(recs, "March 2026")
    out = Path("test_email.html")
    out.write_text(html, encoding="utf-8")
    print(f"HTML email rendered → {out.resolve()} ({len(html):,} chars)")
    print("Open test_email.html in your browser to preview.")


def test_send(recs: dict) -> None:
    from send_email import send_email
    send_email(recs)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "help"
    csv_path = Path("ratings.csv")

    if mode == "help":
        print(__doc__)
        return

    if mode in ("recommendations", "all"):
        if not csv_path.exists():
            print(f"ERROR: {csv_path} not found.")
            print("Export your IMDb ratings manually:")
            print("  1. Go to https://www.imdb.com/user/ur4016761/ratings/")
            print("  2. Click the three-dot menu → Export")
            print("  3. Save as ratings.csv in the project root")
            sys.exit(1)
        recs = test_recommendations(csv_path)
        test_email_render(recs)
        if mode == "all":
            test_send(recs)

    elif mode == "email":
        recs_file = Path("recommendations.json")
        if not recs_file.exists():
            print("ERROR: recommendations.json not found. Run 'python test_local.py recommendations' first.")
            sys.exit(1)
        recs = json.loads(recs_file.read_text())
        test_email_render(recs)

    elif mode == "send":
        recs_file = Path("recommendations.json")
        if not recs_file.exists():
            print("ERROR: recommendations.json not found.")
            sys.exit(1)
        recs = json.loads(recs_file.read_text())
        test_send(recs)

    else:
        print(f"Unknown mode: {mode}")
        print(__doc__)


if __name__ == "__main__":
    main()
