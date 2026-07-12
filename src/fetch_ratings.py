"""
Step 2: Navigate to the IMDb exports page and download the latest
ready files for both ratings and watchlist, saving them to data/.

Run this ~20 minutes after trigger_exports.py.

Robust against IMDb design-system churn: instead of keying off a specific
`ipc-*` title class, it anchors on the stable `data-testid="export-status-button"`
inside each export row and classifies rows by their visible text
(ratings vs watchlist). It prints a full inventory of the exports list on every
run, so any future markup change shows up in the log instead of failing blind.
"""

import asyncio
import base64
import json
import os
from pathlib import Path

from playwright.async_api import async_playwright


EXPORTS_URL = "https://www.imdb.com/exports/?ref_=wl"
DATA_DIR = Path(__file__).parent.parent / "data"
# Watchlist rows may be titled by the account handle rather than "Watchlist".
IMDB_USERNAME = os.environ.get("IMDB_USERNAME", "jeremy-taieb").lower()

# Text matchers per export kind (any match wins, case-insensitive).
MATCHERS = {
    "ratings": ["rating"],
    "watchlist": ["watchlist", "watch list", IMDB_USERNAME],
}

# JS that walks the exports page and returns one record per export row:
# its text, and — if present — the state of its export-status-button
# (BUTTON => ready/clickable, SPAN => processing) plus any csv download link.
_INVENTORY_JS = """() => {
    // Every export row contains a status button with this stable testid.
    const btns = Array.from(document.querySelectorAll('[data-testid="export-status-button"]'));
    const rows = [];
    const seen = new Set();
    for (const node of btns) {
        // Walk up to the enclosing list item (or a reasonable container).
        let item = node.closest('.ipc-metadata-list-summary-item') ||
                   node.closest('li') || node.parentElement;
        for (let i = 0; i < 6 && item && item.parentElement &&
             (item.innerText || '').trim().length < 3; i++) item = item.parentElement;
        if (!item || seen.has(item)) continue;
        seen.add(item);
        const csv = item.querySelector('a[href$=".csv"], a[download], a[href*="download"]');
        rows.push({
            text: (item.innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 160),
            statusTag: node.tagName,                    // BUTTON = ready, SPAN = processing
            statusText: (node.textContent || '').trim(),
            ready: node.tagName === 'BUTTON',
            csvHref: csv ? csv.href : null,
        });
    }
    return rows;
}"""


async def _run(cookies_b64: str) -> tuple[Path, Path]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox",
                  "--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()

        # ── Auth ──────────────────────────────────────────────────────────────
        print("Loading session cookies…")
        cookies = json.loads(base64.b64decode(cookies_b64.strip()).decode())
        await context.add_cookies(cookies)

        await page.goto(EXPORTS_URL, wait_until="load")
        await page.wait_for_function(
            "document.title && document.title.toLowerCase().includes('export')",
            timeout=30000,
        )
        sign_in_visible = await page.locator("a[href*='registration/signin']").count()
        page_text = await page.evaluate("document.body ? document.body.innerText : ''")
        if sign_in_visible and "sign in for more" in page_text.lower():
            raise RuntimeError(
                "Exports page requires sign-in — cookies are expired or incomplete.\n"
                "Re-run save_cookies.py locally and update the IMDB_COOKIES secret."
            )
        print(f"Authenticated. Page title: {await page.title()}")

        # Let the export list render (it is client-rendered) and settle.
        try:
            await page.wait_for_selector('[data-testid="export-status-button"]', timeout=20000)
        except Exception:
            pass
        await page.wait_for_timeout(3000)

        # ── Inventory (always logged, so markup changes are visible) ──────────
        rows = await page.evaluate(_INVENTORY_JS)
        print(f"Exports page inventory ({len(rows)} row(s) with a status button):")
        for i, r in enumerate(rows):
            print(f"  [{i}] {'READY ' if r['ready'] else 'BUSY  '}"
                  f"status={r['statusText']!r} :: {r['text']!r}")
        if not rows:
            raise RuntimeError(
                "No export rows found on the exports page. IMDb markup may have changed, "
                "or no exports exist yet (run trigger_exports.py first). "
                "See the inventory above (empty)."
            )

        ratings_path = await _download_kind(page, rows, "ratings", DATA_DIR / "ratings.csv")
        watchlist_path = await _download_kind(page, rows, "watchlist", DATA_DIR / "watchlist.csv")

        await browser.close()
        return ratings_path, watchlist_path


def _match_row(rows: list[dict], kind: str) -> tuple[int, dict] | tuple[None, None]:
    """First inventory row whose text matches this kind's matchers."""
    matchers = MATCHERS[kind]
    for i, r in enumerate(rows):
        text = r["text"].lower()
        if any(m in text for m in matchers):
            return i, r
    return None, None


async def _download_kind(page, rows: list[dict], kind: str, dest: Path) -> Path:
    print(f"Downloading {kind}…")
    idx, row = _match_row(rows, kind)
    if row is None:
        raise RuntimeError(
            f"Could not find an export row for '{kind}' "
            f"(matchers={MATCHERS[kind]}). See the inventory logged above — "
            "IMDb likely renamed the row; update MATCHERS."
        )
    if not row["ready"]:
        raise RuntimeError(
            f"Export for '{kind}' is not ready (status: {row['statusText']!r}). "
            "Trigger a new export and wait a few minutes, then retry."
        )

    # Resolve the clickable ready-download control for this exact row index.
    btn = await page.evaluate_handle(
        """(idx) => {
            const btns = Array.from(document.querySelectorAll('[data-testid="export-status-button"]'));
            const seen = new Set(); const items = [];
            for (const node of btns) {
                let item = node.closest('.ipc-metadata-list-summary-item') ||
                           node.closest('li') || node.parentElement;
                for (let i = 0; i < 6 && item && item.parentElement &&
                     (item.innerText || '').trim().length < 3; i++) item = item.parentElement;
                if (!item || seen.has(item)) continue;
                seen.add(item); items.push({item, node});
            }
            const rec = items[idx];
            if (!rec) return null;
            // Prefer an explicit csv/download link; else the status button itself.
            return rec.item.querySelector('a[href$=".csv"], a[download], a[href*="download"]')
                   || (rec.node.tagName === 'BUTTON' ? rec.node : null);
        }""",
        idx,
    )
    element = btn.as_element()
    if element is None:
        raise RuntimeError(
            f"Found the '{kind}' row (index {idx}) but no clickable download control. "
            "See the inventory above."
        )

    print(f"  Clicking ready download for '{kind}' (row {idx})")
    async with page.expect_download(timeout=60000) as dl:
        await element.click()
    download = await dl.value
    await download.save_as(dest)
    print(f"  Saved: {dest} ({dest.stat().st_size:,} bytes)")
    return dest


def _load_cookies() -> str:
    cookies = os.environ.get("IMDB_COOKIES", "")
    if not cookies:
        local = Path(__file__).parent.parent / "imdb_cookies.txt"
        if local.exists():
            cookies = local.read_text().strip()
    if not cookies:
        raise RuntimeError("IMDB_COOKIES not set and imdb_cookies.txt not found. Run save_cookies.py first.")
    return cookies


def download_exports() -> tuple[Path, Path]:
    return asyncio.run(_run(_load_cookies()))


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    ratings, watchlist = download_exports()
    print(f"\nDone:\n  {ratings}\n  {watchlist}")
