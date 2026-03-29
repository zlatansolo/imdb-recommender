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

        await page.goto("https://www.imdb.com/", wait_until="domcontentloaded")
        if "ap/signin" in page.url:
            raise RuntimeError(
                "Cookies are expired. Re-run save_cookies.py and update IMDB_COOKIES."
            )
        print(f"Authenticated. URL: {page.url}")

        # ── Navigate to exports page ──────────────────────────────────────────
        print(f"Navigating to {EXPORTS_URL} …")
        await page.goto(EXPORTS_URL, wait_until="load")

        # AWS WAF challenge fires on this page: it runs JS, sets a cookie,
        # then auto-reloads to the real page. Wait until real content appears.
        print("Waiting for WAF challenge to resolve…")
        try:
            await page.wait_for_function(
                "document.title !== '' && document.body.innerText.trim().length > 50",
                timeout=30000,
            )
        except Exception:
            content = await page.content()
            raise RuntimeError(
                f"WAF challenge did not resolve within 30s.\n"
                f"Page HTML:\n{content[:1000]}"
            )
        print(f"Page title: {await page.title()}")

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
    Find the section whose heading contains `label`, click the first
    download link in that section (the most recent export), save the file.
    """
    btn = await page.evaluate_handle("""(label) => {
        const lower = label.toLowerCase();
        // Find the heading element for this section
        const all = Array.from(document.querySelectorAll('h1,h2,h3,h4,h5,span,li,p'));
        const heading = all.find(el =>
            el.children.length === 0 &&
            el.textContent.toLowerCase().includes(lower)
        );
        if (!heading) return null;
        // Walk up to find a container that has a download link
        let container = heading.parentElement;
        for (let i = 0; i < 8; i++) {
            const link = container.querySelector(
                'a[href*="export"], a[href*="download"], a[download], button:not([disabled])'
            );
            if (link) return link;
            if (!container.parentElement) break;
            container = container.parentElement;
        }
        return null;
    }""", label)

    is_null = await page.evaluate("el => el === null", btn)
    if is_null:
        content = await page.content()
        raise RuntimeError(
            f"Could not find download link for '{label}'.\n"
            f"Page title: {await page.title()}\n"
            f"Page HTML (first 2000 chars):\n{content[:2000]}"
        )

    print(f"  Found download element for '{label}'")

    # Get the href directly — if it's an anchor, navigate to it to trigger the download
    href = await page.evaluate("el => el.href || null", btn)
    if href:
        print(f"  Navigating to download URL: {href}")
        async with page.expect_download(timeout=60000) as dl:
            await page.goto(href, wait_until="commit")
    else:
        # Fall back to force-click for buttons
        async with page.expect_download(timeout=60000) as dl:
            await btn.as_element().click(force=True)

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
