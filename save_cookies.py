"""
Run this ONCE locally to save your IMDb session cookies.
Opens a real browser — log in however you normally do (including Sign in with Amazon).

Usage:
    python save_cookies.py

Then copy the printed base64 string into a GitHub Secret named IMDB_COOKIES.
"""

import asyncio
import base64
import json

from playwright.async_api import async_playwright


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
        )

        page = await context.new_page()
        await page.goto("https://www.imdb.com/")

        print("\nA browser window has opened on IMDb.")
        print("1. Click 'Sign In' at the top")
        print("2. Choose 'Sign in with Amazon' and complete login normally")
        print("3. Once you are back on the IMDb homepage, come back here")
        input("\nPress Enter once you are fully logged in...\n")

        # Collect cookies from all pages/tabs in the context
        cookies = await context.cookies(["https://www.imdb.com", "https://www.amazon.com"])
        await browser.close()

    if not cookies:
        print("ERROR: No cookies found. Make sure you logged in successfully.")
        return

    cookies_b64 = base64.b64encode(json.dumps(cookies).encode()).decode()

    print(f"Captured {len(cookies)} cookies.\n")
    print("=" * 60)
    print("Save this as a GitHub Secret named:  IMDB_COOKIES")
    print("=" * 60)
    print(cookies_b64)
    print("=" * 60)
    print("\nGo to: github.com/zlatansolo/imdb-recommender/settings/secrets/actions")


asyncio.run(main())
