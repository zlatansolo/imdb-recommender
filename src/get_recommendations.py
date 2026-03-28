"""
Reads the IMDb ratings CSV, sends it to Claude, and returns structured
recommendations across 5 categories — guaranteed to exclude already-seen titles.
"""

import json
import os
import re
from pathlib import Path

import anthropic
import pandas as pd


# ── Constants ─────────────────────────────────────────────────────────────────

CATEGORIES = [
    "movies_not_seen",
    "tv_not_seen",
    "hidden_gems",
    "recent_releases",
    "french_titles",
]

CATEGORY_LABELS = {
    "movies_not_seen":  "Movies You Haven't Seen",
    "tv_not_seen":      "TV Series You Haven't Seen",
    "hidden_gems":      "Hidden Gems & Underrated Picks",
    "recent_releases":  "Recent Releases (Last 2 Years)",
    "french_films":     "French Films & Series",
}

TASTE_PROFILE = """
TASTE PROFILE (from 1,031 personal ratings):
- Loves: witty crime comedies (Snatch, Lock Stock & Two Smoking Barrels, The Big Lebowski),
  prestige crime TV (The Sopranos, The Wire, Breaking Bad, The Bureau/Le Bureau des Légendes),
  directors: Nolan, the Coens, Tarantino, Fincher, Villeneuve, Guy Ritchie.
- Rated 10/10: Reservoir Dogs, City of God, Amélie, Django Unchained, Inception,
  The Revenant, Flight of the Conchords, South Park, Seinfeld.
- Recent 9/10s: The Penguin (2024), Shōgun (2024), Dune: Part Two (2024),
  Project Hail Mary (upcoming — book lover).
- Dislikes: superhero bloat (rated most MCU/DCEU 5-6), fantasy epics
  (rated all LOTR films 3-4), overly slow arthouse cinema. Horror movies.
- Appreciates: sharp dialogue, strong character arcs, stylish cinematography,
  dark humour, morally complex protagonists.
"""


# ── CSV Parsing ───────────────────────────────────────────────────────────────

def load_ratings(csv_path: Path) -> tuple[pd.DataFrame, set[str]]:
    """Return (full DataFrame, set of lower-cased 'Title (Year)' strings)."""
    df = pd.read_csv(csv_path)
    # Normalise column names (IMDb export varies slightly over time)
    df.columns = [c.strip() for c in df.columns]
    rename = {
        "Const": "imdb_id",
        "Your Rating": "your_rating",
        "Date Rated": "date_rated",
        "Title": "title",
        "URL": "url",
        "Title Type": "title_type",
        "IMDb Rating": "imdb_rating",
        "Runtime (mins)": "runtime",
        "Year": "year",
        "Genres": "genres",
        "Num Votes": "num_votes",
        "Release Date": "release_date",
        "Directors": "directors",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
    seen = set()
    for _, row in df.iterrows():
        title = str(row.get("title", "")).strip()
        year = str(row.get("year", "")).strip()
        if title:
            seen.add(f"{title.lower()} ({year})")
            seen.add(title.lower())
    return df, seen


def build_rated_titles_block(df: pd.DataFrame) -> str:
    """Compact list of all rated titles for the 'do not recommend' constraint."""
    lines = []
    for _, row in df.iterrows():
        title = str(row.get("title", "")).strip()
        year = str(row.get("year", "")).strip()
        rating = str(row.get("your_rating", "")).strip()
        if title:
            lines.append(f"{title} ({year}) — rated {rating}/10")
    return "\n".join(lines)


def build_taste_sample(df: pd.DataFrame) -> str:
    """Top-rated and recently-rated titles for richer taste analysis."""
    df_sorted = df.copy()
    df_sorted["your_rating"] = pd.to_numeric(df_sorted.get("your_rating", pd.Series()), errors="coerce")
    df_sorted["date_rated"] = pd.to_datetime(df_sorted.get("date_rated", pd.Series()), errors="coerce")

    top = df_sorted.nlargest(100, "your_rating")
    recent = df_sorted.nlargest(50, "date_rated")
    combined = pd.concat([top, recent]).drop_duplicates(subset=["title"])

    lines = []
    for _, row in combined.iterrows():
        title = str(row.get("title", "")).strip()
        year = str(row.get("year", "")).strip()
        your_rating = row.get("your_rating", "?")
        imdb_rating = row.get("imdb_rating", "?")
        genres = str(row.get("genres", "")).strip()
        lines.append(
            f"{title} ({year}) | your: {your_rating}/10 | IMDb: {imdb_rating} | {genres}"
        )
    return "\n".join(lines)


# ── Prompt ────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a world-class film and TV critic with encyclopaedic knowledge of IMDb.
Your job is to generate deeply personalised recommendations.

RULES — follow these exactly:
1. NEVER recommend any title that appears in the user's rated titles list.
2. Every recommendation MUST include a real, valid IMDb URL in the format:
   https://www.imdb.com/title/ttXXXXXXX/
   Use the correct tt-number you know from your training data.
3. IMDb ratings must be accurate to your training data (format: X.X/10).
4. Each reason must be exactly 2 sentences, personalised to the user's taste.
5. Provide exactly 8 recommendations per category.
6. Output ONLY valid JSON — no markdown fences, no commentary.

OUTPUT FORMAT (strict JSON):
{
  "movies_not_seen": [
    {
      "title": "...",
      "year": 2022,
      "imdb_rating": "8.2",
      "imdb_url": "https://www.imdb.com/title/tt1234567/",
      "reason": "Sentence one. Sentence two."
    }
  ],
  "tv_not_seen": [...],
  "hidden_gems": [...],
  "recent_releases": [...],
  "french_titles": [...]
}"""


def build_user_prompt(df: pd.DataFrame) -> str:
    rated_block = build_rated_titles_block(df)
    taste_sample = build_taste_sample(df)
    total = len(df)

    return f"""The user has rated {total} titles on IMDb. Here is their taste profile:

{TASTE_PROFILE}

── REPRESENTATIVE RATED TITLES (top-rated + recent, for taste analysis) ──
{taste_sample}

── COMPLETE LIST OF ALL RATED TITLES (DO NOT recommend ANY of these) ──
{rated_block}

Generate personalised recommendations across all 5 categories.
For "recent_releases", only include titles from 2024 or 2025.
For "french_titles", include French-language films AND series (can be from any era).
For "hidden_gems", prioritise titles with IMDb rating 7.0–8.2 and under 100,000 votes.
Ensure variety — don't cluster recommendations around the same director or franchise."""


# ── API Call ──────────────────────────────────────────────────────────────────

def get_recommendations(csv_path: Path) -> dict:
    df, seen_titles = load_ratings(csv_path)
    print(f"Loaded {len(df)} rated titles.")

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    print("Calling Claude for recommendations…")
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8192,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": build_user_prompt(df)}],
    )

    raw = message.content[0].text.strip()

    # Strip any accidental markdown fences
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print("Raw response (first 500 chars):", raw[:500])
        raise ValueError(f"Claude returned invalid JSON: {e}") from e

    # ── Validate: remove any already-seen titles that slipped through ──────
    for category in CATEGORIES:
        key = category
        if key not in data:
            # Try alternate key naming
            continue
        filtered = []
        for rec in data[key]:
            title_year = f"{rec['title'].lower()} ({rec['year']})"
            title_only = rec["title"].lower()
            if title_year in seen_titles or title_only in seen_titles:
                print(f"  [FILTERED] '{rec['title']}' already rated — removing.")
            else:
                filtered.append(rec)
        data[key] = filtered

    # Count total
    total_recs = sum(len(data.get(k, [])) for k in CATEGORIES)
    print(f"Recommendations generated: {total_recs} across {len(CATEGORIES)} categories.")
    return data


if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv
    load_dotenv()
    csv_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("ratings.csv")
    recs = get_recommendations(csv_path)
    print(json.dumps(recs, indent=2))
