"""
Step 2: Navigate to the IMDb exports page and download the latest
ready files for both ratings and watchlist, saving them to data/.

Run this ~20 minutes after trigger_exports.py.
"""

import asyncio
import base64
import json
import os
from pathlib import Path

from playwright.async_api import async_playwright


EXPORTS_URL = "https://www.imdb.com/exports/?ref_=wl"
DATA_DIR = Path(__file__).parent.parent / "data"


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

        # Verify auth by checking the exports page directly
        await page.goto(EXPORTS_URL, wait_until="load")
        await page.wait_for_function(
            "document.title && document.title.toLowerCase().includes('export')",
            timeout=30000,
        )
        # Check we're actually logged in (page will show sign-in links if not)
        sign_in_visible = await page.locator("a[href*='registration/signin']").count()
        page_text = await page.evaluate("document.body ? document.body.innerText : ''")
        if sign_in_visible and "sign in for more" in page_text.lower():
            raise RuntimeError(
                "Exports page requires sign-in — cookies are expired or incomplete.\n"
                "Re-run save_cookies.py locally and update the IMDB_COOKIES secret."
            )
        print(f"Authenticated. Page title: {await page.title()}")
        await page.wait_for_timeout(3000)

        # (already on exports page after auth check above)

        # ── Download ratings (top entry in "your ratings" section) ────────────
        ratings_path = DATA_DIR / "ratings.csv"
        print("Downloading ratings…")
        ratings_path = await _download_top(page, "your ratings", ratings_path)

        # ── Download watchlist (top entry in watchlist section) ───────────────
        watchlist_path = DATA_DIR / "watchlist.csv"
        print("Downloading watchlist…")
        watchlist_path = await _download_top(page, "jeremy-taieb", watchlist_path)

        await browser.close()
        return ratings_path, watchlist_path


async def _download_top(page, label: str, dest: Path) -> Path:
    """
    Find the first real download link for the given section label and save it.
    """
    # Dump all links to find the download URL pattern
    all_links = await page.evaluate("""() => {
        return Array.from(document.querySelectorAll('a[href]')).map(a => ({
            text: a.textContent.trim().slice(0, 80),
            href: a.href
        }));
    }""")
    print(f"  All links on page ({len(all_links)} total):")
    for link in all_links:
        print(f"    [{link['text']}] -> {link['href']}")

    # Filter to real download links — exclude nav/auth URLs
    excluded = ['logout', 'signin', 'register', 'ap/signin', 'javascript', '#']
    download_links = [
        l for l in all_links
        if not any(ex in l['href'].lower() for ex in excluded)
        and ('export' in l['href'].lower()
             or 'download' in l['href'].lower()
             or 'amazonaws' in l['href'].lower()
             or '.csv' in l['href'].lower())
    ]
    print(f"  Candidate download links: {download_links}")

    if not download_links:
        raise RuntimeError(
            f"No download links found for '{label}'.\n"
            f"All links: {all_links}"
        )

    # Pick the link whose surrounding text matches the label (or just first)
    href = download_links[0]['href']
    for link in download_links:
        if label.lower() in link['text'].lower():
            href = link['href']
            break

    print(f"  Downloading from: {href}")
    async with page.expect_download(timeout=60000) as dl:
        await page.goto(href, wait_until="commit")

    download = await dl.value
    await download.save_as(dest)
    print(f"  Saved: {dest} ({dest.stat().st_size:,} bytes)")
    return dest


def download_exports() -> tuple[Path, Path]:
    cookies = os.environ.get("IMDB_COOKIES", "")
    if not cookies:
        raise RuntimeError("IMDB_COOKIES env var not set. Run save_cookies.py first.")
    return asyncio.run(_run(cookies))


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    ratings, watchlist = download_exports()
    print(f"\nDone:\n  {ratings}\n  {watchlist}")
