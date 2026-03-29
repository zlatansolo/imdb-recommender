"""
Run this ONCE locally to save your IMDb session cookies.
It opens a real browser window so you can log in normally (and solve any CAPTCHA).

Usage:
    python save_cookies.py

Then copy the printed base64 string and save it as a GitHub Secret named IMDB_COOKIES.
"""

import asyncio
import base64
import json

from playwright.async_api import async_playwright


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  # visible window
        context = await browser.new_context()
        page = await context.new_page()

        print("Opening IMDb login page...")
        print("Please log in normally in the browser window that opens.")
        print("Once you are logged in and see the IMDb homepage, come back here and press Enter.")

        await page.goto("https://www.imdb.com/ap/signin?"
            "openid.pape.max_auth_age=0"
            "&openid.return_to=https%3A%2F%2Fwww.imdb.com%2F"
            "&openid.identity=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select"
            "&openid.assoc_handle=imdb_us"
            "&openid.mode=checkid_setup"
            "&openid.claimed_id=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select"
            "&openid.ns=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0")

        input("\nPress Enter once you are fully logged in to IMDb...")

        cookies = await context.cookies()
        await browser.close()

    if not cookies:
        print("ERROR: No cookies found. Make sure you logged in successfully.")
        return

    cookies_json = json.dumps(cookies)
    cookies_b64 = base64.b64encode(cookies_json.encode()).decode()

    print(f"\nFound {len(cookies)} cookies.")
    print("\n" + "=" * 60)
    print("Copy the text below and save it as a GitHub Secret named:")
    print("  IMDB_COOKIES")
    print("=" * 60)
    print(cookies_b64)
    print("=" * 60)
    print("\nGo to: github.com/zlatansolo/imdb-recommender/settings/secrets/actions")


asyncio.run(main())
