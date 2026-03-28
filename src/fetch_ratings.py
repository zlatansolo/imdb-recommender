"""
Logs into IMDb via Playwright and downloads the ratings CSV.
IMDb login is handled by Amazon's auth system.
"""

import asyncio
import os
import time
from pathlib import Path

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError


IMDB_USER_ID = "ur4016761"
RATINGS_EXPORT_URL = (
    f"https://www.imdb.com/list/export?list_id=ratings&author_id={IMDB_USER_ID}"
)
OUTPUT_PATH = Path("ratings.csv")


async def login_and_export(email: str, password: str) -> Path:
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
            ],
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

        # ── Step 1: Go to IMDb sign-in page ──────────────────────────────────
        print("Navigating to IMDb sign-in…")
        await page.goto(
            "https://www.imdb.com/ap/signin?"
            "openid.pape.max_auth_age=0"
            "&openid.return_to=https%3A%2F%2Fwww.imdb.com%2F"
            "&openid.identity=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select"
            "&openid.assoc_handle=imdb_us"
            "&openid.mode=checkid_setup"
            "&siteState=eyJvcGVuaWQuYXNzb2NfaGFuZGxlIjoiaW1kYl91cyJ9"
            "&openid.claimed_id=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select"
            "&openid.ns=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0",
            wait_until="networkidle",
        )

        # ── Step 2: Enter email ───────────────────────────────────────────────
        print("Entering email…")
        email_field = page.locator("input[name='email'], input[type='email'], #ap_email")
        await email_field.wait_for(state="visible", timeout=15000)
        await email_field.fill(email)

        # Some flows show a "Continue" button before the password field
        continue_btn = page.locator("input#continue, input[type='submit']")
        if await continue_btn.count() > 0:
            await continue_btn.first.click()
            await page.wait_for_load_state("networkidle")

        # ── Step 3: Enter password ────────────────────────────────────────────
        print("Entering password…")
        password_field = page.locator("input[name='password'], input[type='password'], #ap_password")
        await password_field.wait_for(state="visible", timeout=15000)
        await password_field.fill(password)

        signin_btn = page.locator("input#signInSubmit, input[type='submit'][name='signIn']")
        await signin_btn.wait_for(state="visible", timeout=10000)
        await signin_btn.click()
        await page.wait_for_load_state("networkidle", timeout=30000)

        # Check for CAPTCHA or 2FA
        if "ap/cvf" in page.url or "captcha" in page.url.lower():
            raise RuntimeError(
                "IMDb login triggered a CAPTCHA challenge. "
                "Try logging in manually once to clear it, then retry."
            )
        if "ap/mfa" in page.url or "verification" in page.url.lower():
            raise RuntimeError(
                "IMDb login triggered a 2FA/MFA challenge. "
                "Disable 2FA on your Amazon account or handle it manually."
            )

        print(f"Logged in. Current URL: {page.url}")

        # ── Step 4: Download ratings CSV ──────────────────────────────────────
        print(f"Downloading ratings CSV for {IMDB_USER_ID}…")
        async with context.expect_download(timeout=60000) as download_info:
            await page.goto(RATINGS_EXPORT_URL)

        download = await download_info.value
        await download.save_as(OUTPUT_PATH)
        print(f"Ratings saved to {OUTPUT_PATH} ({OUTPUT_PATH.stat().st_size:,} bytes)")

        await browser.close()
        return OUTPUT_PATH


def fetch_ratings() -> Path:
    email = os.environ["IMDB_EMAIL"]
    password = os.environ["IMDB_PASSWORD"]
    return asyncio.run(login_and_export(email, password))


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    path = fetch_ratings()
    print(f"Done: {path}")
