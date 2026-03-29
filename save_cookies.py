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
from pathlib import Path

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

    # Save to file — easier than copying from terminal
    out = Path("imdb_cookies.txt")
    out.write_text(cookies_b64)

    print(f"Captured {len(cookies)} cookies.")
    print(f"\nSaved to: {out.resolve()}")
    print("\nNext steps:")
    print("  1. Open imdb_cookies.txt and copy the entire contents")
    print("  2. Go to: github.com/zlatansolo/imdb-recommender/settings/secrets/actions")
    print("  3. Create a secret named IMDB_COOKIES and paste the value")


asyncio.run(main())
