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
    # Dump all buttons to find download buttons
    all_buttons = await page.evaluate("""() => {
        return Array.from(document.querySelectorAll('button')).map((b, i) => ({
            index: i,
            text: b.textContent.trim().slice(0, 80),
            type: b.type,
            disabled: b.disabled,
            classes: b.className.slice(0, 80)
        }));
    }""")
    print(f"  Buttons on page ({len(all_buttons)} total):")
    for b in all_buttons:
        print(f"    [{b['index']}] '{b['text']}' class='{b['classes']}'")

    # Find button whose text matches label or contains 'download'
    lower_label = label.lower()
    target_idx = None
    for b in all_buttons:
        text = b['text'].lower()
        if 'download' in text or lower_label in text:
            target_idx = b['index']
            print(f"  Matched button [{target_idx}]: '{b['text']}'")
            break

    if target_idx is None:
        raise RuntimeError(
            f"No download button found for '{label}'.\n"
            f"Buttons: {all_buttons}"
        )

    btn = page.locator("button").nth(target_idx)
    async with page.expect_download(timeout=60000) as dl:
        await btn.click()

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
