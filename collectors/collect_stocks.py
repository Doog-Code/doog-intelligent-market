import requests
import sqlite3
from datetime import datetime

DB_PATH = "database/market_terminal.db"

STOCKS = {
    # Big Tech US
    "AAPL":     "Apple",
    "NVDA":     "NVIDIA",
    "MSFT":     "Microsoft",
    "META":     "Meta Platforms",
    "GOOGL":    "Alphabet",
    "AMZN":     "Amazon",
    "TSLA":     "Tesla",
    "AMD":      "AMD",
    # Deeptech / IA / Quantique
    "IONQ":     "IonQ",
    "RGTI":     "Rigetti Computing",
    "QUBT":     "Quantum Computing Inc",
    "ARQQ":     "Arqit Quantum",
    "PLTR":     "Palantir",
    "ARM":      "ARM Holdings",
    "SMCI":     "Super Micro Computer",
    # Énergie / Défense
    "TTE.PA":   "TotalEnergies",
    "AIR.PA":   "Airbus",
    "HO.PA":    "Thales",
    "LDO.MI":   "Leonardo",
    "RTX":      "RTX Corporation",
    "LMT":      "Lockheed Martin",
    # Luxe / Consommation
    "MC.PA":    "LVMH",
    "RMS.PA":   "Hermès",
    "KER.PA":   "Kering",
    "OR.PA":    "L'Oréal",
    "ASML.AS":  "ASML",
    "CFR.SW":   "Richemont",
    # Europe hors France
    "SAP.DE":   "SAP",
    "SIE.DE":   "Siemens",
    "VOW3.DE":  "Volkswagen",
    "NESN.SW":  "Nestlé",
    "NOVO-B.CO":"Novo Nordisk",
    # Asie
    "7203.T":   "Toyota",
    "005930.KS":"Samsung",
    "TSM":      "TSMC",
}

def save_market(asset, price, change, volume, source):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO market_data (asset, price, change_24h, volume, timestamp, source)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (asset, price, change, volume, datetime.now().isoformat(), source))
    conn.commit()
    conn.close()

def collect():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Stocks — collecte Yahoo Finance...")
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
    ok, fail = 0, 0

    for ticker, name in STOCKS.items():
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=2d"
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code == 200:
                data = r.json()
                meta = data["chart"]["result"][0]["meta"]
                price  = meta.get("regularMarketPrice", 0)
                volume = meta.get("regularMarketVolume", 0)
                prev   = meta.get("chartPreviousClose", price)
                change = ((price - prev) / prev * 100) if prev else 0
                asset_key = f"{ticker}|{name}"
                save_market(asset_key, price, change, volume, "yahoo_stocks")
                print(f"  ✓ {ticker:<12} {name[:25]:<25} {price:>10.2f} ({change:+.2f}%)")
                ok += 1
            else:
                print(f"  ✗ {ticker}: HTTP {r.status_code}")
                fail += 1
        except Exception as e:
            print(f"  ✗ {ticker}: {e}")
            fail += 1

    print(f"\n  ✓ Stocks terminé — {ok} OK / {fail} erreurs")
    return True

if __name__ == "__main__":
    collect()
