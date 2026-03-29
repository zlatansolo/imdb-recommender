# Monthly IMDb Recommendations — Claude.ai Prompt

Copy and paste everything below the line into Claude.ai, then attach `data/ratings.csv`
and `data/watchlist.csv` (download them from GitHub first).

---

I want personalised movie and TV recommendations based on my IMDb history.

I'm attaching two files:
- **ratings.csv** — every title I've rated on IMDb (1,031+ entries)
- **watchlist.csv** — my current IMDb watchlist

**My taste profile:**
- Loves: witty crime comedies (Snatch, Lock Stock, Big Lebowski), prestige crime TV
  (The Sopranos, The Wire, Breaking Bad, Le Bureau des Légendes), directors
  Nolan / Coens / Tarantino / Fincher / Villeneuve / Guy Ritchie
- Rated 10/10: Reservoir Dogs, City of God, Amélie, Django Unchained, Inception,
  The Revenant, Flight of the Conchords, South Park, Seinfeld
- Recent 9/10s: The Penguin (2024), Shōgun (2024), Dune: Part Two (2024)
- Dislikes: superhero bloat, fantasy epics (rated LOTR 3-4), overly slow arthouse

**Rules:**
1. NEVER recommend any title that appears in my ratings.csv (already seen)
2. NEVER recommend any title that appears in my watchlist.csv (already on my list)
3. Every recommendation needs a real IMDb URL: https://www.imdb.com/title/ttXXXXXXX/
4. Each reason must be 2 sentences personalised to my taste
5. Exactly 8 picks per category

**Categories:**
1. Movies I haven't seen
2. TV series I haven't seen
3. Hidden gems (IMDb 7.0–8.2, under 100k votes)
4. Recent releases (2024–2025 only)
5. French films & series (any era)

Once you have the recommendations, please send me an email using Gmail with:
- Subject: "Your IMDb Picks for [Month Year] 🎬"
- To: [YOUR EMAIL HERE]
- A clean HTML email with one card per recommendation showing title, year, IMDb rating,
  IMDb link button, and the personalised reason. Group by category with colour-coded sections.
