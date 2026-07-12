"""
Step 1: create fresh IMDb ratings + watchlist CSV exports.

IMDb (2024+) creates exports from the individual LIST pages, not the /exports/
hub (which now only lists finished exports). This script therefore visits the
ratings and watchlist list pages and clicks their "Export" control.

RECON MODE: set RECON=1 to only dump the export-control markup of each list page
(no clicking), so selectors can be confirmed against the live site.
"""

import asyncio
import base64
import json
import os
from pathlib import Path

from playwright.async_api import async_playwright

EXPORTS_URL = "https://www.imdb.com/exports/?ref_=wl"
RECON = os.environ.get("RECON", "1").lower() not in ("0", "false", "no")

# JS: from a page, collect candidate list-page URLs (ratings / watchlist).
_LIST_LINKS_JS = r"""() => {
    const hrefs = Array.from(document.querySelectorAll('a')).map(a => a.href);
    const pick = re => Array.from(new Set(hrefs.filter(h => re.test(h))));
    return {
        ratings: pick(/\/user\/ur\d+\/ratings|\/ratings(\/|\?|$)/i),
        watchlist: pick(/\/user\/ur\d+\/watchlist|\/watchlist(\/|\?|$)/i),
        allUserLinks: Array.from(new Set(hrefs.filter(h => /\/user\/ur\d+/i.test(h)))).slice(0, 10),
    };
}"""

# JS: dump anything on the current page that looks like an Export control.
_EXPORT_CONTROLS_JS = r"""() => {
    const info = el => ({
        tag: el.tagName,
        testid: el.getAttribute('data-testid'),
        aria: el.getAttribute('aria-label'),
        role: el.getAttribute('role'),
        href: el.getAttribute('href'),
        text: (el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 50),
    });
    const uniq = a => Array.from(new Set(a));
    const nodes = Array.from(document.querySelectorAll('button, a, [role="menuitem"], [role="button"], span, li'));
    const exportish = nodes
        .filter(e => /\bexport\b/i.test((e.textContent || '') + ' ' + (e.getAttribute('aria-label') || '')))
        .map(info)
        // keep the tightest matches (short text) first
        .filter(x => x.text.length <= 40)
        .slice(0, 25);
    const menuish = nodes
        .filter(e => /more|option|menu|\.\.\.|⋯|kebab/i.test((e.getAttribute('aria-label') || '') + ' ' + (e.getAttribute('data-testid') || '')))
        .map(info).slice(0, 15);
    return {
        title: document.title,
        testids: uniq(Array.from(document.querySelectorAll('[data-testid]')).map(e => e.getAttribute('data-testid'))).slice(0, 90),
        exportish, menuish,
    };
}"""


async def _goto_list(page, url, name):
    print(f"\n=== {name} list: {url}")
    await page.goto(url, wait_until="domcontentloaded")
    await page.wait_for_timeout(4000)
    dump = await page.evaluate(_EXPORT_CONTROLS_JS)
    print(f"  title: {dump['title']}")
    print(f"  export-ish controls ({len(dump['exportish'])}):")
    for c in dump["exportish"]:
        print("    ", c)
    print(f"  menu-ish controls ({len(dump['menuish'])}):")
    for c in dump["menuish"]:
        print("    ", c)
    print(f"  testids: {dump['testids']}")


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

        print("Loading session cookies…")
        cookies = json.loads(base64.b64decode(cookies_b64.strip()).decode())
        await context.add_cookies(cookies)

        await page.goto("https://www.imdb.com/", wait_until="domcontentloaded")
        if "ap/signin" in page.url:
            raise RuntimeError("Cookies are expired. Re-run save_cookies.py and update IMDB_COOKIES.")
        print(f"Authenticated. URL: {page.url}")

        # Discover the ratings / watchlist list URLs from the exports hub.
        await page.goto(EXPORTS_URL, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)
        links = await page.evaluate(_LIST_LINKS_JS)
        print("Discovered list links:", json.dumps(links, indent=2))

        ratings_url = links["ratings"][0] if links["ratings"] else None
        watchlist_url = links["watchlist"][0] if links["watchlist"] else None

        if RECON:
            if ratings_url:
                await _goto_list(page, ratings_url, "RATINGS")
            if watchlist_url:
                await _goto_list(page, watchlist_url, "WATCHLIST")
            print("\nRECON complete (no exports triggered).")
        else:
            print("Non-recon trigger flow not implemented yet — set RECON=1.")

        await page.wait_for_timeout(1500)
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
