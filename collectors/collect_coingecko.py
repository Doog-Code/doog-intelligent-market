import requests
import sqlite3
from datetime import datetime

DB_PATH = "database/market_terminal.db"

ASSETS = {
    "bitcoin": "BTC",
    "ethereum": "ETH",
    "solana": "SOL"
}

def save(results):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    for r in results:
        c.execute("""
            INSERT INTO market_data (asset, price, change_24h, volume, timestamp, source)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (r["asset"], r["price"], r["change_24h"], r["volume"], r["timestamp"], r["source"]))
    conn.commit()
    conn.close()
    print(f"  ✓ {len(results)} actifs sauvegardés dans la base")

def collect():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] CoinGecko — collecte en cours...")
    ids = ",".join(ASSETS.keys())
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={ids}&vs_currencies=usd&include_24hr_change=true&include_24hr_vol=true"
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        results = []
        for cg_id, ticker in ASSETS.items():
            if cg_id in data:
                asset = data[cg_id]
                results.append({
                    "asset": ticker,
                    "price": asset.get("usd"),
                    "change_24h": asset.get("usd_24h_change"),
                    "volume": asset.get("usd_24h_vol"),
                    "timestamp": datetime.now().isoformat(),
                    "source": "coingecko"
                })
                print(f"  ✓ {ticker}: ${asset.get('usd'):,.2f} ({asset.get('usd_24h_change'):+.2f}%)")
        save(results)
        return results
    except Exception as e:
        print(f"  ✗ Erreur CoinGecko: {e}")
        return []

if __name__ == "__main__":
    collect()
