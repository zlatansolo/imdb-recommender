"""
Step 1: create fresh IMDb ratings + watchlist CSV exports.

IMDb (2024+) creates exports from the individual LIST pages, not the /exports/
hub (which now only lists finished exports). The "Export" action lives inside
each list page's "Actions" dropdown (data-testid="hero-list-subnav-actions-menu-button").
This script opens that menu on the ratings and watchlist pages and clicks Export,
confirming any follow-up dialog.

RECON=1 => only dump each list page's controls (no clicking).
"""

import asyncio
import base64
import json
import os
from pathlib import Path

from playwright.async_api import async_playwright

EXPORTS_URL = "https://www.imdb.com/exports/?ref_=wl"
RATINGS_URL = "https://www.imdb.com/list/ratings/"
WATCHLIST_URL = "https://www.imdb.com/list/watchlist/"
ACTIONS_BTN = 'button[data-testid="hero-list-subnav-actions-menu-button"]'
RECON = os.environ.get("RECON", "0").lower() not in ("0", "false", "no")

_LIST_LINKS_JS = r"""() => {
    const hrefs = Array.from(document.querySelectorAll('a')).map(a => a.href);
    const pick = re => Array.from(new Set(hrefs.filter(h => re.test(h))));
    return { ratings: pick(/\/list\/ratings|\/ratings(\/|\?|$)/i),
             watchlist: pick(/\/list\/watchlist|\/watchlist(\/|\?|$)/i) };
}"""

# Visible menu / dialog items (used both to click Export and to log the menu).
_VISIBLE_ITEMS_JS = r"""() => {
    const vis = el => el && el.offsetParent !== null && (el.getClientRects().length > 0);
    const nodes = Array.from(document.querySelectorAll(
        '[role="menuitem"], [role="menu"] a, [role="menu"] button, [role="dialog"] button, .ipc-list-item__text, li a, li button'));
    const out = [];
    for (const el of nodes) {
        const text = (el.textContent || '').replace(/\s+/g, ' ').trim();
        if (text && vis(el)) out.push({ tag: el.tagName, role: el.getAttribute('role'),
            testid: el.getAttribute('data-testid'), text: text.slice(0, 50) });
    }
    return out.slice(0, 40);
}"""

# Click the VISIBLE clickable whose label matches `word`. Prefers an EXACT
# (case-insensitive) match on a real menu item/button/link — this avoids grabbing
# a container whose text concatenates sibling items (e.g. "ExportCreate a new list").
_CLICK_BY_TEXT_JS = r"""(word) => {
    const w = word.toLowerCase();
    const vis = el => el && el.offsetParent !== null && el.getClientRects().length > 0;
    const clickable = Array.from(document.querySelectorAll(
        '[role="menuitem"], [role="button"], a, button')).filter(vis);
    // 1) exact leaf match
    for (const el of clickable) {
        if ((el.textContent || '').trim().toLowerCase() === w) { el.click(); return el.textContent.trim(); }
    }
    // 2) short startsWith (leaf-ish, so "Export" but not "ExportCreate a new list")
    for (const el of clickable) {
        const t = (el.textContent || '').trim();
        if (t.toLowerCase().startsWith(w) && t.length <= word.length + 4) { el.click(); return t; }
    }
    return null;
}"""


async def _create_export(page, url, name):
    print(f"\n=== {name}: {url}")
    await page.goto(url, wait_until="domcontentloaded")
    await page.wait_for_timeout(3500)

    actions = page.locator(ACTIONS_BTN)
    try:
        await actions.wait_for(timeout=15000)
    except Exception:
        raise RuntimeError(f"{name}: Actions menu button ({ACTIONS_BTN}) not found — list page markup changed.")
    await actions.click()
    await page.wait_for_timeout(1500)

    menu = await page.evaluate(_VISIBLE_ITEMS_JS)
    print(f"  Actions menu items ({len(menu)}):")
    for it in menu:
        print("    ", it)

    clicked = await page.evaluate(_CLICK_BY_TEXT_JS, "export")
    if not clicked:
        raise RuntimeError(f"{name}: no visible 'Export' item in the Actions menu (see menu dump above).")
    print(f"  Clicked menu item: {clicked!r}")
    await page.wait_for_timeout(2000)

    # A confirmation dialog may appear ("Export this list?" → Export/Confirm button).
    dialog = await page.evaluate(_VISIBLE_ITEMS_JS)
    dlg_buttons = [d for d in dialog if d["tag"] == "BUTTON"]
    if dlg_buttons:
        print(f"  Dialog buttons: {dlg_buttons}")
        confirm = await page.evaluate(_CLICK_BY_TEXT_JS, "export")
        if confirm:
            print(f"  Confirmed dialog with: {confirm!r}")
        await page.wait_for_timeout(2000)

    # Snackbar / toast confirmation, if any.
    toast = await page.evaluate(
        "() => { const n = document.querySelector('[data-testid=\"snackbase-live-region\"]');"
        " return n ? (n.textContent||'').trim() : ''; }")
    if toast:
        print(f"  Toast: {toast!r}")
    print(f"  {name}: export request submitted.")


async def _recon(page, url, name):
    print(f"\n=== RECON {name}: {url}")
    await page.goto(url, wait_until="domcontentloaded")
    await page.wait_for_timeout(3000)
    actions = page.locator(ACTIONS_BTN)
    if await actions.count():
        await actions.click(); await page.wait_for_timeout(1500)
    print("  menu:", json.dumps(await page.evaluate(_VISIBLE_ITEMS_JS), indent=2))


async def _run(cookies_b64: str) -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox",
                  "--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"),
        )
        page = await context.new_page()

        print("Loading session cookies…")
        cookies = json.loads(base64.b64decode(cookies_b64.strip()).decode())
        await context.add_cookies(cookies)

        await page.goto("https://www.imdb.com/", wait_until="domcontentloaded")
        if "ap/signin" in page.url:
            raise RuntimeError("Cookies are expired. Re-run save_cookies.py and update IMDB_COOKIES.")
        print(f"Authenticated. URL: {page.url}")

        # Prefer canonical list URLs; fall back to discovery from the exports hub.
        ratings_url, watchlist_url = RATINGS_URL, WATCHLIST_URL
        try:
            await page.goto(EXPORTS_URL, wait_until="domcontentloaded")
            await page.wait_for_timeout(2500)
            links = await page.evaluate(_LIST_LINKS_JS)
            if links["ratings"]:
                ratings_url = next((u for u in links["ratings"] if "/list/ratings" in u), links["ratings"][0])
            if links["watchlist"]:
                watchlist_url = next((u for u in links["watchlist"] if "/list/watchlist" in u), links["watchlist"][0])
        except Exception as e:
            print("link discovery failed, using canonical URLs:", e)

        step = _recon if RECON else _create_export
        await step(page, ratings_url, "RATINGS")
        await step(page, watchlist_url, "WATCHLIST")

        await page.wait_for_timeout(1500)
        await browser.close()
        print("\nDone. Wait ~15-20 minutes, then run the Download workflow.")


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
