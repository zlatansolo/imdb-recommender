"""
Push the freshly-downloaded IMDb exports into the Notion "IMDb Data Snapshots"
database as a new row: Date, row counts, and both CSVs attached as files.

Run after fetch_ratings.py has written data/ratings.csv + data/watchlist.csv.

Auth: needs a Notion internal-integration token in NOTION_TOKEN, and the
integration must be shared with the snapshot database (see repo docs).

Usage:
    python src/push_to_notion.py            # upload + create the snapshot row
    python src/push_to_notion.py --dry-run  # count rows only, hit no API
"""

import csv
import datetime
import os
import sys
from pathlib import Path

import requests

DATA_DIR = Path(__file__).parent.parent / "data"
NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"

# Default to the database created for this project; override via env if it moves.
DEFAULT_DB_ID = "d65b451c89194db78c1e9184d4744b6d"


def _count_rows(csv_path: Path) -> int:
    """Number of data rows (excludes the header)."""
    with csv_path.open(encoding="utf-8", newline="") as f:
        return max(sum(1 for _ in csv.reader(f)) - 1, 0)


def _headers(token: str, *, json: bool = True) -> dict:
    h = {"Authorization": f"Bearer {token}", "Notion-Version": NOTION_VERSION}
    if json:
        h["Content-Type"] = "application/json"
    return h


def _check(resp, what: str):
    """Raise on error, but surface Notion's response body first (it explains 400s)."""
    if not resp.ok:
        print(f"  Notion API error [{what}]: {resp.status_code} :: {resp.text[:800]}")
    resp.raise_for_status()
    return resp


def _upload_file(token: str, path: Path) -> str:
    """Upload a file to Notion and return its file_upload id."""
    # 1. Create the file upload object (single-part is the default mode).
    create = requests.post(
        f"{NOTION_API}/file_uploads",
        headers=_headers(token),
        json={"filename": path.name, "content_type": "text/csv"},
        timeout=30,
    )
    create.raise_for_status()
    upload = create.json()
    upload_id, upload_url = upload["id"], upload["upload_url"]

    # 2. Send the bytes to the returned upload URL (multipart/form-data).
    with path.open("rb") as f:
        send = requests.post(
            upload_url,
            headers=_headers(token, json=False),  # let requests set the multipart boundary
            files={"file": (path.name, f, "text/csv")},
            timeout=120,
        )
    send.raise_for_status()
    print(f"  uploaded {path.name} ({path.stat().st_size:,} bytes) -> {upload_id}")
    return upload_id


def _create_row(token: str, db_id: str, date_str: str,
                ratings_n: int, watchlist_n: int,
                ratings_upload: str, watchlist_upload: str) -> str:
    props = {
        "Snapshot":  {"title": [{"text": {"content": date_str}}]},
        "Date":      {"date": {"start": date_str}},
        "Ratings":   {"number": ratings_n},
        "Watchlist": {"number": watchlist_n},
        "Ratings CSV": {"files": [
            {"name": "ratings.csv", "type": "file_upload", "file_upload": {"id": ratings_upload}}
        ]},
        "Watchlist CSV": {"files": [
            {"name": "watchlist.csv", "type": "file_upload", "file_upload": {"id": watchlist_upload}}
        ]},
    }
    resp = requests.post(
        f"{NOTION_API}/pages",
        headers=_headers(token),
        json={"parent": {"database_id": db_id}, "properties": props},
        timeout=30,
    )
    _check(resp, "create page")
    return resp.json()["url"]


def push_to_notion(dry_run: bool = False) -> None:
    ratings_csv = DATA_DIR / "ratings.csv"
    watchlist_csv = DATA_DIR / "watchlist.csv"
    for p in (ratings_csv, watchlist_csv):
        if not p.exists():
            raise FileNotFoundError(f"{p} not found — run the download step first.")

    ratings_n = _count_rows(ratings_csv)
    watchlist_n = _count_rows(watchlist_csv)
    date_str = datetime.date.today().isoformat()
    print(f"Snapshot {date_str}: {ratings_n} ratings, {watchlist_n} watchlist.")

    if dry_run:
        print("[dry-run] Skipping all Notion API calls.")
        return

    token = os.environ.get("NOTION_TOKEN")
    if not token:
        print("NOTION_TOKEN not set — skipping Notion push "
              "(add the secret to enable it). Data was still committed to the repo.")
        return
    # `or` (not get's default) so an empty env value from an unset repo var falls back.
    db_id = os.environ.get("NOTION_SNAPSHOTS_DB_ID") or DEFAULT_DB_ID

    print("Uploading CSVs to Notion…")
    ratings_upload = _upload_file(token, ratings_csv)
    watchlist_upload = _upload_file(token, watchlist_csv)

    print("Creating snapshot row…")
    url = _create_row(token, db_id, date_str, ratings_n, watchlist_n,
                      ratings_upload, watchlist_upload)
    print(f"Done. Snapshot row: {url}")


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    push_to_notion(dry_run="--dry-run" in sys.argv)
