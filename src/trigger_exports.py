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

        # ── Trigger any exports that are not already READY or PROCESSING ─────
        # IMDb uses data-testid="export-status-button" for the status indicator.
        # READY → <button class="... READY"> (clickable download)
        # PROCESSING → <span class="... PROCESSING"> (non-interactive)
        # Expired/never created → a different "Create export" button nearby
        triggered = await page.evaluate("""() => {
            const results = [];

            // Click any visible non-status buttons near export sections that look
            // like "create" / "request" triggers (text won't say "Ready"/"In progress")
            const allBtns = Array.from(document.querySelectorAll('button'));
            const statusTexts = new Set(['ready', 'in progress', 'processing', 'back to top']);
            for (const btn of allBtns) {
                const text = btn.textContent.trim().toLowerCase();
                if (!text || statusTexts.has(text)) continue;
                // Only click if it's in an export-related section
                const inExportSection = !!btn.closest('[data-testid*="export"], .ipc-metadata-list-summary-item');
                if (inExportSection) {
                    btn.click();
                    results.push(btn.textContent.trim());
                }
            }

            // Report current status of all export-status-button elements
            const statusNodes = Array.from(document.querySelectorAll('[data-testid="export-status-button"]'));
            const statuses = statusNodes.map(n => ({
                tag: n.tagName,
                status: n.classList.contains('READY') ? 'READY' : n.classList.contains('PROCESSING') ? 'PROCESSING' : 'UNKNOWN',
                text: n.textContent.trim()
            }));

            return { triggered: results, statuses };
        }""")

        if triggered["triggered"]:
            print(f"Triggered export buttons: {triggered['triggered']}")
        else:
            print("No new exports to trigger (all sections are already READY or PROCESSING).")

        print("Export statuses:")
        for s in triggered.get("statuses", []):
            print(f"  [{s['status']}] {s['text']}")

        await page.wait_for_timeout(3000)
        await browser.close()


def _load_cookies() -> str:
    cookies = os.environ.get("IMDB_COOKIES", "")
    if not cookies:
        local = Path(__file__).parent.parent / "imdb_cookies.txt"
        if local.exists():
            cookies = local.read_text().strip()
    if not cookies:
        raise RuntimeError("IMDB_COOKIES not set and imdb_cookies.txt not found. Run save_cookies.py first.")
    return cookies


def trigger_exports() -> None:
    asyncio.run(_run(_load_cookies()))


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    trigger_exports()
    print("\nDone. Wait ~20 minutes then run download_exports.py.")
