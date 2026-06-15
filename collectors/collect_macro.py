import requests
import sqlite3
from datetime import datetime

DB_PATH = "database/market_terminal.db"

# Tous les grands baromètres mondiaux
# Format : "ticker Yahoo Finance" : ("nom affiché", "catégorie")
ASSETS = {
    # Dollar et taux
    "DX-Y.NYB":  ("DXY — Dollar Index",        "forex"),
    "^TNX":      ("US 10Y Yield",               "taux"),
    "^IRX":      ("US 3M Yield",                "taux"),

    # Peur et volatilité
    "^VIX":      ("VIX — Indice de peur",       "volatilite"),

    # Indices actions mondiaux
    "^IXIC":     ("Nasdaq Composite",           "actions"),
    "^GSPC":     ("S&P 500",                    "actions"),
    "^FCHI":     ("CAC 40",                     "actions"),
    "^N225":     ("Nikkei 225",                 "actions"),
    "^STOXX50E": ("EuroStoxx 50",               "actions"),

    # Forex majeurs
    "EURUSD=X":  ("EUR/USD",                    "forex"),
    "JPY=X":     ("USD/JPY",                    "forex"),
    "GBPUSD=X":  ("GBP/USD",                    "forex"),

    # Matières premières
    "GC=F":      ("Or XAU/USD",                 "matieres"),
    "SI=F":      ("Argent XAG/USD",             "matieres"),
    "CL=F":      ("Pétrole WTI",                "matieres"),
    "BZ=F":      ("Pétrole Brent",              "matieres"),
}

def save(ticker, name, price, change, volume, category):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO market_data (asset, price, change_24h, volume, timestamp, source)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (f"{ticker}|{name}", price, change, volume,
          datetime.now().isoformat(), f"yahoo_{category}"))
    conn.commit()
    conn.close()

def collect():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Macro mondiale — collecte en cours...")
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

    categories = {}
    errors = []

    for ticker, (name, category) in ASSETS.items():
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=2d"
            r = requests.get(url, headers=headers, timeout=10)

            if r.status_code == 200:
                data = r.json()
                result = data["chart"]["result"]
                if not result:
                    raise ValueError("Pas de données")
                meta = result[0]["meta"]
                price  = meta.get("regularMarketPrice", 0)
                volume = meta.get("regularMarketVolume", 0)
                prev   = meta.get("chartPreviousClose", price)
                change = ((price - prev) / prev * 100) if prev else 0

                save(ticker, name, price, change, volume, category)

                arrow = "▲" if change >= 0 else "▼"
                color_hint = "+" if change >= 0 else ""
                print(f"  ✓ {name:<30} {price:>10.2f}  {arrow} {color_hint}{change:.2f}%")

                if category not in categories:
                    categories[category] = 0
                categories[category] += 1

            else:
                errors.append(f"{ticker} (status {r.status_code})")

        except Exception as e:
            errors.append(f"{ticker} ({str(e)[:40]})")

    print(f"\n  ✓ {sum(categories.values())} actifs collectés")
    for cat, count in categories.items():
        print(f"    — {cat}: {count}")

    if errors:
        print(f"\n  ⚠ {len(errors)} erreur(s): {', '.join(errors)}")

    return True

if __name__ == "__main__":
    collect()
