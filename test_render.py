import sys
sys.path.insert(0, "src")
from send_email import build_html

full_recs = {
    "movies_not_seen": [
        {"title": "No Country for Old Men", "year": 2007, "imdb_rating": "8.2",
         "imdb_url": "https://www.imdb.com/title/tt0477348/",
         "reason": "The Coens at their most relentlessly bleak — a hitman whose coin-flip philosophy echoes the moral nihilism you loved in Fargo. Anton Chigurh ranks alongside Hans Landa as cinema's greatest villain."},
        {"title": "Prisoners", "year": 2013, "imdb_rating": "8.1",
         "imdb_url": "https://www.imdb.com/title/tt1392214/",
         "reason": "Villeneuve at his most morally complex before Dune — a father descends into vigilante brutality while Deakins crafts every frame like a painting. The slow-burn tension and ambiguous ending will resonate with your love of The Wire."},
    ],
    "tv_not_seen": [
        {"title": "Barry", "year": 2018, "imdb_rating": "8.4",
         "imdb_url": "https://www.imdb.com/title/tt5348176/",
         "reason": "A hitman pivots to acting in LA — dark crime comedy with the wit of Snatch and the moral weight of Breaking Bad. Bill Hader is extraordinary across all four seasons."},
    ],
    "hidden_gems": [
        {"title": "In Bruges", "year": 2008, "imdb_rating": "7.9",
         "imdb_url": "https://www.imdb.com/title/tt0780536/",
         "reason": "Two hitmen hiding in a medieval Belgian city — the dialogue crackles with the same wit you love in Guy Ritchie and the Coens. Criminally underseen despite being one of the finest crime comedies of its era."},
    ],
    "recent_releases": [
        {"title": "Ripley", "year": 2024, "imdb_rating": "8.2",
         "imdb_url": "https://www.imdb.com/title/tt13032730/",
         "reason": "Fincher-esque precision in stunning black-and-white — a con man in 1960s Italy in a slow-burn thriller that rewards patience. The cinematography alone earns its prestige TV status alongside The Bureau."},
    ],
    "french_titles": [
        {"title": "A Prophet", "year": 2009, "imdb_rating": "7.9",
         "imdb_url": "https://www.imdb.com/title/tt1235166/",
         "reason": "The French answer to The Godfather — a young Arab man rises through the prison underworld in a brutally realistic crime epic. As tightly plotted as City of God with the moral depth of The Sopranos."},
    ],
}

html = build_html(full_recs, "March 2026")
with open("test_email.html", "w", encoding="utf-8") as f:
    f.write(html)
print(f"Full email rendered: {len(html):,} chars — open test_email.html in your browser to preview.")
