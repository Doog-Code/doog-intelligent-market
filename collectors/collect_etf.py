import requests
import feedparser
import sqlite3
from datetime import datetime

DB_PATH = "database/market_terminal.db"

ETF_TICKERS = {
    "IBIT":  "BlackRock iShares Bitcoin ETF",
    "FBTC":  "Fidelity Wise Origin Bitcoin ETF",
    "BITB":  "Bitwise Bitcoin ETF",
    "ARKB":  "ARK 21Shares Bitcoin ETF",
    "HODL":  "VanEck Bitcoin ETF"
}

def save_market(asset, price, change, volume, source):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO market_data (asset, price, change_24h, volume, timestamp, source)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (asset, price, change, volume, datetime.now().isoformat(), source))
    conn.commit()
    conn.close()

def save_article(title, summary, url, source):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    existing = c.execute("SELECT id FROM articles WHERE url = ?", (url,)).fetchone()
    if not existing:
        c.execute("""
            INSERT INTO articles (title, summary, source, url, published_at, collected_at, category, importance)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (title, summary, source, url,
              datetime.now().isoformat(), datetime.now().isoformat(),
              "ETF", "IMPORTANT"))
        conn.commit()
        print(f"  ✓ Article : {title[:70]}")
    conn.close()

def collect_prices():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] ETF — Prix Yahoo Finance...")
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
    results = []
    for ticker, name in ETF_TICKERS.items():
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=2d"
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code == 200:
                data = r.json()
                meta = data["chart"]["result"][0]["meta"]
                price = meta.get("regularMarketPrice", 0)
                volume = meta.get("regularMarketVolume", 0)
                prev = meta.get("chartPreviousClose", price)
                change = ((price - prev) / prev * 100) if prev else 0
                save_market(ticker, price, change, volume, "yahoo_finance")
                print(f"  ✓ {ticker} ({name[:25]}): ${price:.2f} ({change:+.2f}%) vol:{volume:,}")
                results.append(ticker)
        except Exception as e:
            print(f"  ✗ {ticker}: {e}")
    return results

def collect_news():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] ETF — Actualités TheBlock RSS...")
    keywords = ["etf", "ibit", "fbtc", "bitcoin etf", "btc etf", "flow", "inflow", "outflow"]
    found = 0
    try:
        feed = feedparser.parse("https://www.theblock.co/rss.xml")
        for entry in feed.entries:
            title = entry.get("title", "").lower()
            if any(k in title for k in keywords):
                save_article(
                    entry.get("title", ""),
                    entry.get("summary", "")[:500],
                    entry.get("link", ""),
                    "TheBlock"
                )
                found += 1
        print(f"  ✓ {found} article(s) ETF trouvé(s) sur TheBlock")
    except Exception as e:
        print(f"  ✗ TheBlock RSS: {e}")

def collect():
    prices = collect_prices()
    collect_news()
    print(f"  ✓ Collecte ETF terminée — {len(prices)} ETF en base")
    return True

if __name__ == "__main__":
    collect()
