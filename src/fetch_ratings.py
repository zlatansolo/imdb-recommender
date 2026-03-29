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
        watchlist_path = await _click_export(page, "jeremy-taieb", watchlist_path)

        await browser.close()
        return ratings_path, watchlist_path


async def _click_export(page, label: str, dest: Path) -> Path:
    """
    On the IMDb exports page, find the section whose heading contains `label`,
    then click the first (top) download link in that section's list.
    """
    # Use JS to locate the heading by text, walk up to its section container,
    # then grab the first anchor/button with a download href inside it.
    btn = await page.evaluate_handle("""(label) => {
        const lower = label.toLowerCase();
        // Find all headings/spans that contain the label text
        const all = Array.from(document.querySelectorAll('h1,h2,h3,h4,h5,span,p,div'));
        const heading = all.find(el =>
            el.children.length === 0 && el.textContent.toLowerCase().includes(lower)
        );
        if (!heading) return null;
        // Walk up until we find a container that holds download links
        let container = heading.parentElement;
        for (let i = 0; i < 6; i++) {
            const link = container.querySelector('a[href*="export"], a[download], button');
            if (link) return link;
            if (container.parentElement) container = container.parentElement;
        }
        return null;
    }""", label)

    # Check if we got a valid element back
    is_null = await page.evaluate("el => el === null", btn)
    if is_null:
        content = await page.content()
        raise RuntimeError(
            f"Could not find section for '{label}' on exports page.\n"
            f"Page title: {await page.title()}\n"
            f"Page HTML (first 1500 chars):\n{content[:1500]}"
        )

    print(f"  Found download element for '{label}'")
    async with page.expect_download(timeout=60000) as dl:
        await btn.as_element().click()

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
