import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import feedparser
import re
import sqlite3
import time
from datetime import datetime, timezone

DB_PATH = "database/market_terminal.db"

FEEDS = [
    {
        "url":        "https://www.federalreserve.gov/feeds/press_all.xml",
        "source":     "Federal Reserve",
        "category":   "banque_centrale",
        "importance": "CRITIQUE"
    },
    {
        "url":        "https://www.ecb.europa.eu/rss/press.html",
        "source":     "BCE",
        "category":   "banque_centrale",
        "importance": "CRITIQUE"
    },
    {
        "url":        "https://www.theblock.co/rss.xml",
        "source":     "TheBlock",
        "category":   "crypto",
        "importance": "IMPORTANT"
    },
    {
        "url":        "https://cointelegraph.com/rss",
        "source":     "CoinTelegraph",
        "category":   "crypto",
        "importance": "IMPORTANT"
    },   
    {
        "url":        "https://www.lemonde.fr/economie/rss_full.xml",
        "source":     "Le Monde Économie",
        "category":   "macro",
        "importance": "IMPORTANT"
    },
    {
        "url":        "https://www.esma.europa.eu/rss.xml",
        "source":     "ESMA",
        "category":   "regulation",
        "importance": "CRITIQUE"
    },
]

CRITICAL_KEYWORDS = [
    "fed","federal reserve","fomc","powell","bce","lagarde","ecb",
    "cpi","inflation","interest rate","taux","bitcoin etf","btc etf",
    "sec","recession","crash","crisis","war","sanction","default",
    "emergency","halt","suspension","rate decision","rate cut","rate hike"
]

CRYPTO_KEYWORDS = [
    "bitcoin","btc","ethereum","eth","solana","sol","crypto","defi",
    "stablecoin","etf","blockchain","binance","coinbase","blackrock"
]

def classify(title, summary, category, feed_importance="IMPORTANT"):
    text = (title + " " + summary).lower()
    # Keywords vraiment critiques — priorité absolue
    hard_critical = [
        "fed","federal reserve","fomc","powell","bce","lagarde","ecb",
        "rate decision","rate cut","rate hike","emergency","crash","crisis",
        "recession","default","war","sanction","bitcoin etf","btc etf","sec"
    ]
    for kw in hard_critical:
        if kw in text:
            return "CRITIQUE"
    # Sources réglementaires : on respecte leur importance par défaut
    if category in ("banque_centrale","regulation"):
        return feed_importance
    # Crypto : filtre par keywords
    if category == "crypto":
        for kw in CRYPTO_KEYWORDS:
            if kw in text:
                return "IMPORTANT"
        return "BRUIT"
    return "IMPORTANT"

def already_exists(url):
    conn = sqlite3.connect(DB_PATH)
    row  = conn.execute("SELECT id FROM articles WHERE url=?", (url,)).fetchone()
    conn.close()
    return row is not None

def save_article(title, summary, source, url, published_at, category, importance):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO articles
        (title, summary, source, url, published_at, collected_at, category, importance)
        VALUES (?,?,?,?,?,?,?,?)
    """, (title, summary[:800], source, url,
          published_at, datetime.now().isoformat(), category, importance))
    conn.commit()
    conn.close()

def collect():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] News — collecte RSS en cours...")

    # Buffer : collecte tout sans sauvegarder
    buffer = []
    stats  = {"CRITIQUE": 0, "IMPORTANT": 0, "BRUIT": 0}

    for feed_config in FEEDS:
        source   = feed_config["source"]
        category = feed_config["category"]
        new_count = 0

        try:
            feed   = feedparser.parse(feed_config["url"])
            status = getattr(feed, "status", "?")

            for entry in feed.entries[:15]:
                title   = entry.get("title","").strip()
                summary = entry.get("summary", entry.get("description","")).strip()
                url     = entry.get("link","")

                published = entry.get("published_parsed") or entry.get("updated_parsed")
                pub_str   = datetime(*published[:6],
                            tzinfo=timezone.utc).isoformat() if published else datetime.now().isoformat()

                if not title or not url:
                    continue

                # Supprime les balises HTML des titres et résumés
                title   = re.sub(r'<[^>]+>', '', title).strip()
                summary = re.sub(r'<[^>]+>', '', summary).strip()

                importance = classify(title, summary, category, feed_config.get("importance","IMPORTANT"))

                if importance == "BRUIT":
                    stats["BRUIT"] += 1
                    continue

                if already_exists(url):
                    continue

                buffer.append({
                    "title":       title,
                    "summary":     summary,
                    "source":      source,
                    "url":         url,
                    "published_at": pub_str,
                    "category":    category,
                    "importance":  importance
                })
                stats[importance] += 1
                new_count += 1

            print(f"  → {source}: {new_count} nouveau(x) | status {status}")

        except Exception as e:
            print(f"  ✗ {source}: {e}")

        time.sleep(0.5)

    # Traduction en français via Groq
    if buffer:
        print(f"  → Traduction de {len(buffer)} articles en français...")
        try:
            from analyzers.translate import translate_batch
            buffer = translate_batch(buffer)
            print(f"  ✓ Traduction terminée")
        except Exception as e:
            print(f"  ⚠ Traduction échouée ({e}) — conservation en anglais")

    # Sauvegarde
    for art in buffer:
        save_article(art["title"], art["summary"], art["source"],
                     art["url"], art["published_at"],
                     art["category"], art["importance"])

    total = stats["CRITIQUE"] + stats["IMPORTANT"]
    print(f"\n  ✓ Collecte terminée")
    print(f"    🔴 CRITIQUE  : {stats['CRITIQUE']}")
    print(f"    🟡 IMPORTANT : {stats['IMPORTANT']}")
    print(f"    ⬜ BRUIT filtré : {stats['BRUIT']}")
    print(f"    Total sauvegardé : {total}")
    return True

if __name__ == "__main__":
    collect()
