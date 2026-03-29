"""
Step 1: Navigate to the IMDb exports page and trigger generation
of both the ratings and watchlist exports.

Run this first, then wait ~20 minutes before running download_exports.py.
"""

import asyncio
import base64
import json
import os
from pathlib import Path

from playwright.async_api import async_playwright
from playwright_stealth import stealth_async


EXPORTS_URL = "https://www.imdb.com/exports/?ref_=wl"


async def _run(cookies_b64: str) -> None:
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
        await stealth_async(page)

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
        await page.goto(EXPORTS_URL, wait_until="networkidle")
        print(f"Page title: {await page.title()}")

        # ── Click all Create/Generate buttons ─────────────────────────────────
        # These are the buttons that REQUEST a new export (not download buttons)
        triggered = await page.evaluate("""() => {
            const keywords = ['create', 'generate', 'export', 'request'];
            const results = [];
            const buttons = Array.from(document.querySelectorAll('button, input[type=button], input[type=submit]'));
            for (const btn of buttons) {
                const text = btn.textContent.trim().toLowerCase();
                if (keywords.some(k => text.includes(k)) && !text.includes('download')) {
                    btn.click();
                    results.push(btn.textContent.trim());
                }
            }
            return results;
        }""")

        if triggered:
            print(f"Triggered export buttons: {triggered}")
        else:
            # Dump page for debugging
            content = await page.content()
            print(f"WARNING: No trigger buttons found.")
            print(f"Page HTML (first 2000 chars):\n{content[:2000]}")

        await page.wait_for_timeout(3000)
        await browser.close()


def trigger_exports() -> None:
    cookies = os.environ.get("IMDB_COOKIES", "")
    if not cookies:
        raise RuntimeError("IMDB_COOKIES env var not set. Run save_cookies.py first.")
    asyncio.run(_run(cookies))


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    trigger_exports()
    print("\nDone. Wait ~20 minutes then run download_exports.py.")
