"""
Logs into IMDb via Playwright and downloads both the ratings CSV and watchlist CSV.
Both files are saved to the data/ directory (relative to project root).
"""

import asyncio
import os
from pathlib import Path

from playwright.async_api import async_playwright


IMDB_USER_ID = "ur4016761"
DATA_DIR = Path(__file__).parent.parent / "data"

RATINGS_EXPORT_URL = (
    f"https://www.imdb.com/list/export?list_id=ratings&author_id={IMDB_USER_ID}"
)
WATCHLIST_EXPORT_URL = (
    f"https://www.imdb.com/list/export?list_id=watchlist&author_id={IMDB_USER_ID}"
)


async def _run(email: str, password: str) -> tuple[Path, Path]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

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

        # ── Login ─────────────────────────────────────────────────────────────
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

        print("Entering email…")
        email_field = page.locator("input[name='email'], input[type='email'], #ap_email")
        await email_field.wait_for(state="visible", timeout=15000)
        await email_field.fill(email)

        continue_btn = page.locator("input#continue, input[type='submit']")
        if await continue_btn.count() > 0:
            await continue_btn.first.click()
            await page.wait_for_load_state("networkidle")

        print("Entering password…")
        password_field = page.locator(
            "input[name='password'], input[type='password'], #ap_password"
        )
        await password_field.wait_for(state="visible", timeout=15000)
        await password_field.fill(password)

        signin_btn = page.locator(
            "input#signInSubmit, input[type='submit'][name='signIn']"
        )
        await signin_btn.wait_for(state="visible", timeout=10000)
        await signin_btn.click()
        await page.wait_for_load_state("networkidle", timeout=30000)

        if "ap/cvf" in page.url or "captcha" in page.url.lower():
            raise RuntimeError(
                "IMDb login triggered a CAPTCHA. Log in manually once from the same IP, then retry."
            )
        if "ap/mfa" in page.url or "verification" in page.url.lower():
            raise RuntimeError(
                "IMDb login triggered 2FA. Disable it on your Amazon account or handle manually."
            )

        print(f"Logged in. URL: {page.url}")

        # ── Download ratings ──────────────────────────────────────────────────
        ratings_path = DATA_DIR / "ratings.csv"
        print("Downloading ratings…")
        async with context.expect_download(timeout=60000) as dl:
            await page.goto(RATINGS_EXPORT_URL)
        await (await dl.value).save_as(ratings_path)
        print(f"  Saved: {ratings_path} ({ratings_path.stat().st_size:,} bytes)")

        # ── Download watchlist ────────────────────────────────────────────────
        watchlist_path = DATA_DIR / "watchlist.csv"
        print("Downloading watchlist…")
        async with context.expect_download(timeout=60000) as dl:
            await page.goto(WATCHLIST_EXPORT_URL)
        await (await dl.value).save_as(watchlist_path)
        print(f"  Saved: {watchlist_path} ({watchlist_path.stat().st_size:,} bytes)")

        await browser.close()
        return ratings_path, watchlist_path


def fetch_all() -> tuple[Path, Path]:
    """Fetch both ratings and watchlist in a single browser session."""
    email = os.environ["IMDB_EMAIL"]
    password = os.environ["IMDB_PASSWORD"]
    return asyncio.run(_run(email, password))


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    ratings, watchlist = fetch_all()
    print(f"\nDone:\n  {ratings}\n  {watchlist}")
