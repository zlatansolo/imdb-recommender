"""
Logs into IMDb via Playwright and downloads both the ratings CSV and watchlist CSV.
Both files are saved to the data/ directory (relative to project root).

Authentication strategy:
  1. If IMDB_COOKIES env var is set (base64 JSON), inject cookies directly — no login needed.
  2. Otherwise fall back to email/password login (may trigger CAPTCHA on CI).

To generate IMDB_COOKIES, run save_cookies.py locally.
"""

import asyncio
import base64
import json
import os
from pathlib import Path

from playwright.async_api import async_playwright


IMDB_USER_ID = "ur4016761"
DATA_DIR = Path(__file__).parent.parent / "data"

RATINGS_EXPORT_URL  = f"https://www.imdb.com/list/export?list_id=ratings&author_id={IMDB_USER_ID}"
WATCHLIST_EXPORT_URL = f"https://www.imdb.com/list/export?list_id=watchlist&author_id={IMDB_USER_ID}"


async def _run(email: str, password: str, cookies_b64: str | None) -> tuple[Path, Path]:
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

        # ── Auth: cookies or login ────────────────────────────────────────────
        if cookies_b64:
            print("Using saved cookies for authentication…")
            cookies = json.loads(base64.b64decode(cookies_b64.strip()).decode())
            await context.add_cookies(cookies)
            # Quick check: hit IMDb to confirm session is valid
            await page.goto("https://www.imdb.com/", wait_until="domcontentloaded")
            if "signIn" in page.url or "ap/signin" in page.url:
                raise RuntimeError(
                    "Saved cookies are expired. Re-run save_cookies.py locally "
                    "and update the IMDB_COOKIES GitHub Secret."
                )
            print(f"Authenticated via cookies. URL: {page.url}")
        else:
            print("No cookies found — falling back to email/password login…")
            await _login(page, email, password)

        # ── Navigate to exports page ──────────────────────────────────────────
        print("Navigating to IMDb exports page…")
        await page.goto("https://www.imdb.com/exports/?ref_=wl", wait_until="networkidle")

        # ── Download ratings ──────────────────────────────────────────────────
        ratings_path = DATA_DIR / "ratings.csv"
        print("Downloading ratings…")
        ratings_path = await _click_export(page, "your ratings", ratings_path)

        # ── Download watchlist ────────────────────────────────────────────────
        watchlist_path = DATA_DIR / "watchlist.csv"
        print("Downloading watchlist…")
        watchlist_path = await _click_export(page, "watchlist", watchlist_path)

        await browser.close()
        return ratings_path, watchlist_path


async def _click_export(page, label: str, dest: Path) -> Path:
    """
    Find the export card whose heading contains `label` (case-insensitive),
    then click its Download button and save the file.
    """
    # Find the section/card that contains the label text, then find a
    # download link or button inside it.
    selectors = [
        # Card contains the label, button/link inside it
        f":has-text('{label}') >> button:has-text('Download')",
        f":has-text('{label}') >> a:has-text('Download')",
        f":has-text('{label}') >> button:has-text('Export')",
        f":has-text('{label}') >> a[href*='export']",
        f":has-text('{label}') >> a[download]",
        # Fallback: any Download button on page
        "button:has-text('Download')",
        "a:has-text('Download')",
    ]

    btn = None
    used_sel = None
    for sel in selectors:
        candidate = page.locator(sel).first
        if await candidate.count() > 0:
            btn = candidate
            used_sel = sel
            break

    if btn is None:
        content = await page.content()
        raise RuntimeError(
            f"Could not find download button for '{label}'.\n"
            f"Page title: {await page.title()}\n"
            f"Page snippet:\n{content[:1000]}"
        )

    print(f"  Found via: {used_sel}")
    async with page.expect_download(timeout=60000) as dl:
        await btn.click()

    download = await dl.value
    await download.save_as(dest)
    print(f"  Saved: {dest} ({dest.stat().st_size:,} bytes)")
    return dest


async def _login(page, email: str, password: str) -> None:
    print("Navigating to IMDb sign-in…")
    await page.goto(
        "https://www.imdb.com/ap/signin?"
        "openid.pape.max_auth_age=0"
        "&openid.return_to=https%3A%2F%2Fwww.imdb.com%2F"
        "&openid.identity=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select"
        "&openid.assoc_handle=imdb_us"
        "&openid.mode=checkid_setup"
        "&openid.claimed_id=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select"
        "&openid.ns=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0",
        wait_until="networkidle",
    )

    email_field = page.locator("input[name='email'], input[type='email'], #ap_email")
    await email_field.wait_for(state="visible", timeout=15000)
    await email_field.fill(email)

    continue_btn = page.locator("input#continue, input[type='submit']")
    if await continue_btn.count() > 0:
        await continue_btn.first.click()
        await page.wait_for_load_state("networkidle")

    password_field = page.locator("input[name='password'], input[type='password'], #ap_password")
    await password_field.wait_for(state="visible", timeout=15000)
    await password_field.fill(password)

    signin_btn = page.locator("input#signInSubmit, input[type='submit'][name='signIn']")
    await signin_btn.wait_for(state="visible", timeout=10000)
    await signin_btn.click()
    await page.wait_for_load_state("networkidle", timeout=30000)

    if "ap/cvf" in page.url or "captcha" in page.url.lower():
        raise RuntimeError(
            "IMDb login triggered a CAPTCHA. Run save_cookies.py locally "
            "and add IMDB_COOKIES as a GitHub Secret."
        )
    if "ap/mfa" in page.url or "verification" in page.url.lower():
        raise RuntimeError("IMDb login triggered 2FA. Disable it or use cookie auth.")

    print(f"Logged in. URL: {page.url}")


def fetch_all() -> tuple[Path, Path]:
    email    = os.environ.get("IMDB_EMAIL", "")
    password = os.environ.get("IMDB_PASSWORD", "")
    cookies  = os.environ.get("IMDB_COOKIES", "")
    return asyncio.run(_run(email, password, cookies or None))


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    ratings, watchlist = fetch_all()
    print(f"\nDone:\n  {ratings}\n  {watchlist}")
