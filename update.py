#!/usr/bin/env python3
"""
FrontlineWire — update.py
=========================
Fetches conflict news from RSS feeds, summarizes with Claude AI,
and writes data.json which the website reads.

Run manually:  python3 update.py
Auto-run:      GitHub Actions runs this every 6 hours (see .github/workflows/update.yml)

Requirements:
  pip install requests anthropic feedparser python-dateutil
"""

import os
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

# ── CONFIG ──────────────────────────────────────────────────────────────────

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")  # Set in GitHub Secrets

# Conflict keywords — articles must match at least one to be included
CONFLICT_KEYWORDS = [
    "war", "conflict", "attack", "strike", "missile", "drone", "bomb",
    "troops", "military", "offensive", "ceasefire", "shelling", "airstrike",
    "invasion", "insurgent", "rebel", "armed", "casualties", "killed",
    "fighting", "battle", "siege", "artillery", "forces", "army",
    "militia", "coalition", "NATO", "sanctions", "hostilities",
    "iran", "israel", "ukraine", "russia", "sudan", "myanmar", "haiti",
    "yemen", "houthi", "gaza", "hezbollah", "wagner", "DRC", "congo",
    "somalia", "al-shabaab", "ethiopia", "tigray", "colombia", "ELN",
    "pakistan", "india", "LOC", "kashmir", "iraq", "syria"
]

# RSS feeds — region_key maps to the nav filter in app.js
RSS_FEEDS = [
    # Middle East
    { "url": "https://feeds.bbci.co.uk/news/world/middle_east/rss.xml",    "source": "BBC",       "region": "Middle East", "region_key": "middle-east" },
    { "url": "https://www.aljazeera.com/xml/rss/all.xml",                   "source": "Al Jazeera","region": "Middle East", "region_key": "middle-east" },
    { "url": "https://rss.app/feeds/tlkOlJZmXvIvnkJI.xml",                 "source": "Reuters",   "region": "Middle East", "region_key": "middle-east" },
    # Europe / Ukraine
    { "url": "https://feeds.bbci.co.uk/news/world/europe/rss.xml",          "source": "BBC",       "region": "Europe",      "region_key": "europe" },
    { "url": "https://www.kyivpost.com/rss",                                 "source": "Kyiv Post", "region": "Europe",      "region_key": "europe" },
    # Africa
    { "url": "https://feeds.bbci.co.uk/news/world/africa/rss.xml",          "source": "BBC",       "region": "Africa",      "region_key": "africa" },
    { "url": "https://www.garoweonline.com/en/rss",                          "source": "Garowe Online","region":"Africa",    "region_key": "africa" },
    # Asia
    { "url": "https://feeds.bbci.co.uk/news/world/asia/rss.xml",            "source": "BBC",       "region": "Asia",        "region_key": "asia" },
    { "url": "https://www.irrawaddy.com/feed",                               "source": "Irrawaddy", "region": "Asia",        "region_key": "asia" },
    # Americas
    { "url": "https://feeds.bbci.co.uk/news/world/latin_america/rss.xml",   "source": "BBC",       "region": "Americas",    "region_key": "americas" },
    # Global wire
    { "url": "https://feeds.reuters.com/reuters/worldNews",                  "source": "Reuters",   "region": "Global",      "region_key": "all" },
    { "url": "https://apnews.com/apf-intlnews.rss",                         "source": "AP",        "region": "Global",      "region_key": "all" },
]

MAX_STORIES_PER_FEED = 25    # How many articles to pull per feed
MAX_STORIES_TOTAL    = 120   # Max stories written to data.json
SUMMARY_MAX_TOKENS   = 300  # Words in each AI summary

# ── FETCH RSS ────────────────────────────────────────────────────────────────

def fetch_feed(feed_config):
    """Download and parse one RSS feed, return list of raw article dicts."""
    articles = []
    try:
        parsed = feedparser.parse(feed_config["url"])
        for entry in parsed.entries[:MAX_STORIES_PER_FEED]:
            title   = entry.get("title", "").strip()
            summary = entry.get("summary", entry.get("description", "")).strip()
            url     = entry.get("link", "")
            pub     = entry.get("published", entry.get("updated", ""))

            # Parse date
            try:
                pub_dt = dateparser.parse(pub).isoformat() if pub else datetime.now(timezone.utc).isoformat()
            except Exception:
                pub_dt = datetime.now(timezone.utc).isoformat()

            # Strip HTML tags from summary
            import re
            summary = re.sub(r'<[^>]+>', '', summary).strip()

            articles.append({
                "title":      title,
                "raw_summary": summary[:600],
                "url":        url,
                "published":  pub_dt,
                "source":     feed_config["source"],
                "region":     feed_config["region"],
                "region_key": feed_config["region_key"],
            })
    except Exception as e:
        log.warning(f"Feed error [{feed_config['url']}]: {e}")
    return articles

def is_conflict_related(article):
    """Return True if title or summary contains a conflict keyword."""
    text = (article["title"] + " " + article["raw_summary"]).lower()
    return any(kw.lower() in text for kw in CONFLICT_KEYWORDS)

# ── SUMMARISE WITH CLAUDE ────────────────────────────────────────────────────

def summarise_batch(articles, client):
    """
    Send up to 20 articles to Claude in one call for efficiency.
    Returns list of clean summaries aligned to input order.
    """
    if not articles:
        return []

    items = "\n\n".join(
        f"[{i+1}] TITLE: {a['title']}\nRAW: {a['raw_summary']}"
        for i, a in enumerate(articles)
    )

    prompt = f"""You are an editor for FrontlineWire, a global conflict news site.

For each numbered article below, write a single neutral, factual summary sentence of 2-3 sentences (around {SUMMARY_MAX_TOKENS} words max).
- Be specific: include locations, actors, and key actions.
- Do NOT editorialize, do NOT add opinions.
- Do NOT copy the title.
- Return ONLY a JSON array of strings, one per article, in the same order.
- Example output: ["Summary one.", "Summary two."]

ARTICLES:
{items}

Respond with ONLY the JSON array. No other text."""

    try:
        response = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )
        text = response.content[0].text.strip()
        # Strip markdown code fences if present
        text = text.replace("```json", "").replace("```", "").strip()
        summaries = json.loads(text)
        if len(summaries) == len(articles):
            return summaries
        log.warning("Summary count mismatch, using raw summaries.")
    except Exception as e:
        log.warning(f"Claude summarise error: {e}")

    # Fallback: return raw summaries truncated
    return [a["raw_summary"][:200] for a in articles]

# ── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    if not ANTHROPIC_API_KEY:
        log.error("ANTHROPIC_API_KEY is not set. Export it as an environment variable.")
        raise SystemExit(1)

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # 1. Fetch all feeds
    log.info("Fetching RSS feeds...")
    all_articles = []
    for feed in RSS_FEEDS:
        arts = fetch_feed(feed)
        log.info(f"  {feed['source']} ({feed['region']}): {len(arts)} articles")
        all_articles.extend(arts)
        time.sleep(0.5)  # polite delay

    # 2. Filter to conflict-related only
    conflict_articles = [a for a in all_articles if is_conflict_related(a)]
    log.info(f"Conflict-related articles: {len(conflict_articles)} / {len(all_articles)}")

    # 3. Deduplicate by title similarity (simple)
    seen_titles = set()
    unique_articles = []
    for a in conflict_articles:
        key = a["title"][:60].lower()
        if key not in seen_titles:
            seen_titles.add(key)
            unique_articles.append(a)

    # 4. Sort by publish date (newest first), cap total
    unique_articles.sort(key=lambda x: x["published"], reverse=True)
    unique_articles = unique_articles[:MAX_STORIES_TOTAL]

    # 5. Summarise in batches of 15 to stay within token limits
    log.info("Summarising with Claude AI...")
    BATCH = 15
    summaries = []
    for i in range(0, len(unique_articles), BATCH):
        batch = unique_articles[i:i+BATCH]
        log.info(f"  Summarising batch {i//BATCH + 1} ({len(batch)} articles)...")
        summaries.extend(summarise_batch(batch, client))
        time.sleep(1)

    # 6. Assemble final stories list
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

    # 7. Write data.json
    output = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "story_count":  len(stories),
        "stories":      stories,
    }
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    log.info(f"Done. Wrote {len(stories)} stories to data.json.")

if __name__ == "__main__":
    main()
