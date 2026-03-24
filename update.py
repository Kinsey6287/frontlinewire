#!/usr/bin/env python3
"""
FrontlineWire — update.py
=========================
Fetches conflict news from 50+ global RSS feeds, summarises with Claude AI,
and writes data.json which the static website reads.

Auto-run: GitHub Actions triggers this every 6 hours (see .github/workflows/update.yml)
"""

import os
import re
import json
import time
import logging
import feedparser
import anthropic
import requests
from datetime import datetime, timezone
from dateutil import parser as dateparser

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger(__name__)

# ── CONFIG ───────────────────────────────────────────────────────────────────

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

MAX_STORIES_PER_FEED = 20
MAX_STORIES_TOTAL    = 200
BATCH_SIZE           = 15   # articles per Claude summarise call

# Browser-like headers so news sites don't block us
FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0"
    ),
    "Accept": "application/rss+xml, application/xml, application/atom+xml, text/xml, */*",
    "Accept-Language": "en-US,en;q=0.9",
}

# ── CONFLICT KEYWORDS ────────────────────────────────────────────────────────

CONFLICT_KEYWORDS = [
    # Actions
    "war", "conflict", "attack", "strike", "missile", "drone", "bomb",
    "shelling", "airstrike", "artillery", "offensive", "ceasefire",
    "invasion", "siege", "battle", "fighting", "combat", "ambush",
    "raid", "operation", "incursion", "assault", "hostilities",
    # Actors
    "troops", "military", "forces", "army", "navy", "air force",
    "insurgent", "rebel", "militia", "coalition", "NATO", "mercenary",
    "paramilitary", "jihadist", "extremist", "terrorist",
    # Outcomes
    "casualties", "killed", "wounded", "dead", "death toll",
    "displaced", "refugee", "humanitarian crisis", "war crime",
    # Geopolitical
    "sanctions", "nuclear", "weapons", "arms", "defense", "deterrence",
    # Active conflict zones & actors
    "ukraine", "russia", "gaza", "israel", "west bank", "idf",
    "hamas", "hezbollah", "iran", "syria", "iraq", "isis", "isil",
    "yemen", "houthi", "saudi", "sudan", "rsl", "rsf", "darfur",
    "myanmar", "junta", "tatmadaw", "arakan", "ethiopia", "tigray",
    "amhara", "fano", "somalia", "al-shabaab", "amisom", "atmis",
    "congo", "DRC", "m23", "rwanda", "mozambique", "cabo delgado",
    "mali", "sahel", "wagner", "burkina faso", "niger", "chad",
    "haiti", "gang", "colombia", "ELN", "FARC", "cartel",
    "pakistan", "india", "kashmir", "LOC", "balochistan",
    "nagorno-karabakh", "azerbaijan", "armenia",
    "taiwan", "china", "south china sea", "philippines",
    "north korea", "kim jong", "nuclear test",
    "afghanistan", "taliban", "isis-k",
]

# ── RSS FEED CATALOGUE (50 + sources) ───────────────────────────────────────
# region_key must match the filter IDs used in app.js

RSS_FEEDS = [

    # ── MIDDLE EAST ──────────────────────────────────────────────────────────
    {  "url": "https://feeds.bbci.co.uk/news/world/middle_east/rss.xml",
       "source": "BBC",              "region": "Middle East", "region_key": "middle-east" },
    {  "url": "https://www.aljazeera.com/xml/rss/all.xml",
       "source": "Al Jazeera",       "region": "Middle East", "region_key": "middle-east" },
    {  "url": "https://www.middleeasteye.net/rss",
       "source": "Middle East Eye",  "region": "Middle East", "region_key": "middle-east" },
    {  "url": "https://www.timesofisrael.com/feed/",
       "source": "Times of Israel",  "region": "Middle East", "region_key": "middle-east" },
    {  "url": "https://english.alaraby.co.uk/rss.xml",
       "source": "The New Arab",     "region": "Middle East", "region_key": "middle-east" },
    {  "url": "https://www.middleeastmonitor.com/feed/",
       "source": "ME Monitor",       "region": "Middle East", "region_key": "middle-east" },
    {  "url": "https://www.rudaw.net/english/feed",
       "source": "Rudaw",            "region": "Middle East", "region_key": "middle-east" },
    {  "url": "https://www.arabnews.com/rss.xml",
       "source": "Arab News",        "region": "Middle East", "region_key": "middle-east" },
    {  "url": "https://www.jpost.com/rss/rssfeedsfrontpage.aspx",
       "source": "Jerusalem Post",   "region": "Middle East", "region_key": "middle-east" },

    # ── EUROPE / UKRAINE ─────────────────────────────────────────────────────
    {  "url": "https://feeds.bbci.co.uk/news/world/europe/rss.xml",
       "source": "BBC",              "region": "Europe",      "region_key": "europe" },
    {  "url": "https://kyivindependent.com/feed/",
       "source": "Kyiv Independent", "region": "Europe",      "region_key": "europe" },
    {  "url": "https://www.kyivpost.com/rss",
       "source": "Kyiv Post",        "region": "Europe",      "region_key": "europe" },
    {  "url": "https://euromaidanpress.com/feed/",
       "source": "Euromaidan Press", "region": "Europe",      "region_key": "europe" },
    {  "url": "https://www.ukrinform.net/rss/block-lastnews",
       "source": "Ukrinform",        "region": "Europe",      "region_key": "europe" },
    {  "url": "https://www.rferl.org/api/zydynrrqomvp",
       "source": "Radio Free Europe","region": "Europe",      "region_key": "europe" },
    {  "url": "https://meduza.io/rss/en/all",
       "source": "Meduza",           "region": "Europe",      "region_key": "europe" },
    {  "url": "https://www.themoscowtimes.com/rss/news",
       "source": "Moscow Times",     "region": "Europe",      "region_key": "europe" },
    {  "url": "https://rss.dw.com/rdf/rss-en-world",
       "source": "DW",               "region": "Europe",      "region_key": "europe" },

    # ── AFRICA ───────────────────────────────────────────────────────────────
    {  "url": "https://feeds.bbci.co.uk/news/world/africa/rss.xml",
       "source": "BBC",              "region": "Africa",      "region_key": "africa" },
    {  "url": "https://www.garoweonline.com/en/rss",
       "source": "Garowe Online",    "region": "Africa",      "region_key": "africa" },
    {  "url": "https://www.theafricareport.com/feed/",
       "source": "The Africa Report","region": "Africa",      "region_key": "africa" },
    {  "url": "https://www.africanews.com/feed/",
       "source": "Africanews",       "region": "Africa",      "region_key": "africa" },
    {  "url": "https://allafrica.com/tools/headlines/rdf/latest/headlines.rdf",
       "source": "AllAfrica",        "region": "Africa",      "region_key": "africa" },
    {  "url": "https://www.theeastafrican.co.ke/rss",
       "source": "The East African", "region": "Africa",      "region_key": "africa" },
    {  "url": "https://www.dailymaverick.co.za/feed/",
       "source": "Daily Maverick",   "region": "Africa",      "region_key": "africa" },
    {  "url": "https://www.thenewhumanitarian.org/rss.xml",
       "source": "New Humanitarian", "region": "Africa",      "region_key": "africa" },

    # ── ASIA / PACIFIC ───────────────────────────────────────────────────────
    {  "url": "https://feeds.bbci.co.uk/news/world/asia/rss.xml",
       "source": "BBC",              "region": "Asia",        "region_key": "asia" },
    {  "url": "https://www.irrawaddy.com/feed",
       "source": "Irrawaddy",        "region": "Asia",        "region_key": "asia" },
    {  "url": "https://www.rfa.org/english/news/rss2.xml",
       "source": "Radio Free Asia",  "region": "Asia",        "region_key": "asia" },
    {  "url": "https://www.dawn.com/feeds/home",
       "source": "Dawn",             "region": "Asia",        "region_key": "asia" },
    {  "url": "https://www.benarnews.org/english/rss.xml",
       "source": "BenarNews",        "region": "Asia",        "region_key": "asia" },
    {  "url": "https://www.thehindu.com/news/international/?service=rss",
       "source": "The Hindu",        "region": "Asia",        "region_key": "asia" },
    {  "url": "https://www3.nhk.or.jp/rss/news/cat6.xml",
       "source": "NHK World",        "region": "Asia",        "region_key": "asia" },
    {  "url": "https://eurasianet.org/feed",
       "source": "Eurasianet",       "region": "Asia",        "region_key": "asia" },
    {  "url": "https://www.scmp.com/rss/91/feed",
       "source": "South China Morning Post", "region": "Asia", "region_key": "asia" },
    {  "url": "https://www.straitstimes.com/news/world/rss.xml",
       "source": "Straits Times",    "region": "Asia",        "region_key": "asia" },

    # ── AMERICAS ─────────────────────────────────────────────────────────────
    {  "url": "https://feeds.bbci.co.uk/news/world/latin_america/rss.xml",
       "source": "BBC",              "region": "Americas",    "region_key": "americas" },
    {  "url": "https://insightcrime.org/feed/",
       "source": "InSight Crime",    "region": "Americas",    "region_key": "americas" },
    {  "url": "https://www.dialogo-americas.com/rss.xml",
       "source": "Dialogo Americas", "region": "Americas",    "region_key": "americas" },
    {  "url": "https://en.mercopress.com/rss",
       "source": "MercoPress",       "region": "Americas",    "region_key": "americas" },

    # ── GLOBAL WIRE ──────────────────────────────────────────────────────────
    {  "url": "https://feeds.reuters.com/Reuters/worldNews",
       "source": "Reuters",          "region": "Global",      "region_key": "all" },
    {  "url": "https://www.theguardian.com/world/rss",
       "source": "The Guardian",     "region": "Global",      "region_key": "all" },
    {  "url": "https://www.france24.com/en/rss",
       "source": "France 24",        "region": "Global",      "region_key": "all" },
    {  "url": "https://feeds.voanews.com/voaspecialenglish/n46c",
       "source": "Voice of America", "region": "Global",      "region_key": "all" },
    {  "url": "https://foreignpolicy.com/feed/",
       "source": "Foreign Policy",   "region": "Global",      "region_key": "all" },
    {  "url": "https://warontherocks.com/feed/",
       "source": "War on the Rocks", "region": "Global",      "region_key": "all" },
    {  "url": "https://www.defensenews.com/arc/outboundfeeds/rss/",
       "source": "Defense News",     "region": "Global",      "region_key": "all" },
    {  "url": "https://www.defenseone.com/rss/all/",
       "source": "Defense One",      "region": "Global",      "region_key": "all" },
    {  "url": "https://breakingdefense.com/feed/",
       "source": "Breaking Defense", "region": "Global",      "region_key": "all" },
    {  "url": "https://www.stripes.com/arc/outboundfeeds/rss/",
       "source": "Stars & Stripes",  "region": "Global",      "region_key": "all" },
    {  "url": "https://www.bellingcat.com/feed/",
       "source": "Bellingcat",       "region": "Global",      "region_key": "all" },
    {  "url": "https://www.crisisgroup.org/rss.xml",
       "source": "Crisis Group",     "region": "Global",      "region_key": "all" },
    {  "url": "https://understandingwar.org/rss.xml",
       "source": "ISW",              "region": "Global",      "region_key": "all" },
]

# ── FETCH RSS ─────────────────────────────────────────────────────────────────

def fetch_feed(feed_cfg: dict) -> list[dict]:
    """
    Fetch one RSS feed using requests (browser headers + timeout),
    then parse with feedparser. Returns a list of raw article dicts.
    """
    articles = []
    url = feed_cfg["url"]
    try:
        # Use requests so we control User-Agent and timeout
        resp = requests.get(url, headers=FETCH_HEADERS, timeout=15, allow_redirects=True)
        if resp.status_code != 200:
            log.warning(f"  SKIP {feed_cfg['source']} — HTTP {resp.status_code}")
            return []
        parsed = feedparser.parse(resp.content)
        entries = parsed.entries[:MAX_STORIES_PER_FEED]
        if not entries:
            log.warning(f"  SKIP {feed_cfg['source']} — 0 entries returned")
            return []

        for entry in entries:
            title   = entry.get("title", "").strip()
            summary = (entry.get("summary") or entry.get("description") or "").strip()
            link    = entry.get("link", "")
            pub     = entry.get("published") or entry.get("updated") or ""

            if not title or not link:
                continue

            try:
                pub_dt = dateparser.parse(pub).isoformat() if pub else datetime.now(timezone.utc).isoformat()
            except Exception:
                pub_dt = datetime.now(timezone.utc).isoformat()

            # Strip HTML tags from summary
            summary = re.sub(r"<[^>]+>", "", summary).strip()

            articles.append({
                "title":       title,
                "raw_summary": summary[:600],
                "url":         link,
                "published":   pub_dt,
                "source":      feed_cfg["source"],
                "region":      feed_cfg["region"],
                "region_key":  feed_cfg["region_key"],
            })

    except requests.exceptions.Timeout:
        log.warning(f"  TIMEOUT {feed_cfg['source']} ({url})")
    except Exception as e:
        log.warning(f"  ERROR {feed_cfg['source']} ({url}): {e}")

    return articles


def is_conflict_related(article: dict) -> bool:
    """Return True if the title or summary contains at least one conflict keyword."""
    text = (article["title"] + " " + article["raw_summary"]).lower()
    return any(kw.lower() in text for kw in CONFLICT_KEYWORDS)


# ── SUMMARISE WITH CLAUDE ─────────────────────────────────────────────────────

def summarise_batch(articles: list[dict], client) -> list[str]:
    """
    Send a batch of articles to Claude for summarisation.
    Returns a list of summary strings in the same order as input.
    Falls back to raw_summary[:200] on any failure.
    """
    if not articles:
        return []

    items = "\n\n".join(
        f"[{i+1}] TITLE: {a['title']}\nRAW: {a['raw_summary']}"
        for i, a in enumerate(articles)
    )

    prompt = f"""You are an editor for FrontlineWire, a global conflict-and-security news aggregator.

For each numbered article below write 2-3 neutral, factual sentences that:
- Name specific locations, actors, and the key action or development.
- Do NOT editorialize or copy the title verbatim.
- Stay under 60 words per summary.

Return ONLY a JSON array of strings, one per article, in the same order.
Example: ["Summary one.", "Summary two."]

ARTICLES:
{items}

Respond with ONLY the JSON array. No other text."""

    try:
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        text = re.sub(r"^```[a-z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        summaries = json.loads(text.strip())
        if len(summaries) == len(articles):
            return summaries
        log.warning(f"Summary count mismatch ({len(summaries)} vs {len(articles)}); using raw.")
    except Exception as e:
        log.warning(f"Claude summarise error: {e}")

    return [a["raw_summary"][:200] for a in articles]


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    if not ANTHROPIC_API_KEY:
        log.error("ANTHROPIC_API_KEY is not set.")
        raise SystemExit(1)

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # ── 1. Fetch all feeds ────────────────────────────────────────────────────
    log.info(f"Fetching {len(RSS_FEEDS)} RSS feeds...")
    all_articles: list[dict] = []
    feed_stats: list[str] = []

    for feed in RSS_FEEDS:
        arts = fetch_feed(feed)
        status = f"  ✓ {feed['source']:25s} ({feed['region']:12s}): {len(arts)} articles"
        log.info(status)
        feed_stats.append(status)
        all_articles.extend(arts)
        time.sleep(0.3)

    log.info(f"Total raw articles fetched: {len(all_articles)}")

    # ── 2. Filter to conflict-related ────────────────────────────────────────
    conflict_articles = [a for a in all_articles if is_conflict_related(a)]
    log.info(f"Conflict-related: {len(conflict_articles)} / {len(all_articles)}")

    # ── 3. Deduplicate by title (first 60 chars, lowercased) ─────────────────
    seen_titles: set[str] = set()
    unique_articles: list[dict] = []
    for a in conflict_articles:
        key = a["title"][:60].lower().strip()
        if key and key not in seen_titles:
            seen_titles.add(key)
            unique_articles.append(a)

    # ── 4. Sort newest-first, cap total ──────────────────────────────────────
    unique_articles.sort(key=lambda x: x["published"], reverse=True)
    unique_articles = unique_articles[:MAX_STORIES_TOTAL]
    log.info(f"Unique conflict articles to publish: {len(unique_articles)}")

    # ── 5. Summarise in batches ───────────────────────────────────────────────
    log.info("Summarising with Claude AI...")
    summaries: list[str] = []
    for i in range(0, len(unique_articles), BATCH_SIZE):
        batch = unique_articles[i : i + BATCH_SIZE]
        log.info(f"  Batch {i // BATCH_SIZE + 1}: {len(batch)} articles")
        summaries.extend(summarise_batch(batch, client))
        time.sleep(1)

    # ── 6. Assemble output ───────────────────────────────────────────────────
    stories = []
    for i, article in enumerate(unique_articles):
        stories.append({
            "title":      article["title"],
            "summary":    summaries[i] if i < len(summaries) else article["raw_summary"][:200],
            "url":        article["url"],
            "published":  article["published"],
            "source":     article["source"],
            "region":     article["region"],
            "region_key": article["region_key"],
        })

    # ── 7. Write data.json ───────────────────────────────────────────────────
    output = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "story_count":  len(stories),
        "feed_count":   len(RSS_FEEDS),
        "stories":      stories,
    }
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    log.info(f"Done. Wrote {len(stories)} stories from {len(RSS_FEEDS)} feeds to data.json.")


if __name__ == "__main__":
    main()
