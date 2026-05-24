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
    Find and click the READY download button for the export section matching label.
    IMDb renders READY exports as <button data-testid="export-status-button" class="... READY">
    and in-progress ones as a non-interactive <span> with class PROCESSING.
    """
    # Check status first (plain evaluate so we can inspect without holding a handle)
    status = await page.evaluate("""(label) => {
        const lower = label.toLowerCase();
        const titles = Array.from(document.querySelectorAll('.ipc-metadata-list-summary-item__t'));
        for (const title of titles) {
            if (!title.textContent.toLowerCase().includes(lower)) continue;
            let el = title.parentElement;
            for (let i = 0; i < 12; i++) {
                if (!el) break;
                const node = el.querySelector('[data-testid="export-status-button"]');
                if (node) {
                    return {
                        found: true,
                        ready: node.tagName === 'BUTTON' && node.classList.contains('READY'),
                        statusText: node.textContent.trim()
                    };
                }
                el = el.parentElement;
            }
        }
        return { found: false };
    }""", label)

    if not status["found"]:
        raise RuntimeError(
            f"Could not find export section for '{label}'. "
            "The page may not have loaded fully or the section label changed."
        )
    if not status["ready"]:
        raise RuntimeError(
            f"Export for '{label}' is not ready (status: {status['statusText']}). "
            "Trigger a new export and wait a few minutes, then retry."
        )

    # Fetch the actual button element handle and click it
    btn = await page.evaluate_handle("""(label) => {
        const lower = label.toLowerCase();
        const titles = Array.from(document.querySelectorAll('.ipc-metadata-list-summary-item__t'));
        for (const title of titles) {
            if (!title.textContent.toLowerCase().includes(lower)) continue;
            let el = title.parentElement;
            for (let i = 0; i < 12; i++) {
                if (!el) break;
                const btn = el.querySelector('button[data-testid="export-status-button"]');
                if (btn) return btn;
                el = el.parentElement;
            }
        }
        return null;
    }""", label)

    print(f"  Found 'Ready' button for '{label}'")
    async with page.expect_download(timeout=60000) as dl:
        await btn.as_element().click()

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
