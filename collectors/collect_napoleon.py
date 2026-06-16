import requests
import sqlite3
import re
import json
from datetime import datetime

DB_PATH = "database/market_terminal.db"

SOURCES = [
    {
        "name": "bdor.fr",
        "url": "https://www.bdor.fr/produits-d-investissement-or/cours-prix-pieces-d-or/20-francs-napoleon-or",
        "method": "json_schema"
    }
]

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

def parse_bdor(html):
    """Extrait le prix depuis le JSON schema de bdor.fr"""
    # Méthode 1 : JSON structuré
    match = re.search(r'"price":\s*"([\d.]+)"', html)
    if match:
        return float(match.group(1))
    # Méthode 2 : cotation affichée
    match = re.search(r'Cotation du jour.*?([\d\s]+[,.][\d]{2})\s*€', html)
    if match:
        return float(match.group(1).replace('\xa0','').replace(' ','').replace(',','.'))
    return None

def parse_orfr(html):
    """Extrait le prix depuis or.fr"""
    patterns = [
        r'"price":\s*"?([\d.]+)"?',
        r'([\d]{3}[,.][\d]{2})\s*€',
        r'prix.*?([\d]{3}[,.][\d]{2})',
    ]
    for pattern in patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            try:
                price = float(match.group(1).replace(',','.'))
                if 400 < price < 1000:  # Fourchette réaliste Napoléon
                    return price
            except:
                continue
    return None

def save(price, source, variation=None):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO market_data (asset, price, change_24h, volume, timestamp, source)
        VALUES (?, ?, ?, ?, ?, ?)
    """, ("Napoleon20F|Napoléon 20F", price, variation or 0.0, 0,
          datetime.now().isoformat(), source))
    conn.commit()
    conn.close()

def collect():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Napoléon 20F — collecte en cours...")

    prices = []

    for source in SOURCES:
        try:
            r = requests.get(source["url"], headers=HEADERS, timeout=15)
            if r.status_code != 200:
                print(f"  ✗ {source['name']}: status {r.status_code}")
                continue

            price = None
            if source["method"] == "json_schema":
                price = parse_bdor(r.text)
                # Récupère aussi la variation
                var_match = re.search(r'variationCOS[^>]*>([-+\d,.]+)%', r.text)
                variation = float(var_match.group(1).replace(',','.')) if var_match else 0.0
            else:
                price = parse_orfr(r.text)
                variation = 0.0

            if price:
                save(price, source["name"], variation)
                prices.append(price)
                print(f"  ✓ {source['name']}: {price:.2f}€ ({variation:+.2f}%)")
            else:
                print(f"  ⚠ {source['name']}: prix non trouvé")

        except Exception as e:
            print(f"  ✗ {source['name']}: {e}")

    # Calcule le prix moyen si deux sources disponibles
    if len(prices) == 2:
        avg = sum(prices) / len(prices)
        diff = abs(prices[0] - prices[1])
        print(f"  ✓ Prix moyen : {avg:.2f}€ (écart entre sources : {diff:.2f}€)")
        if diff > 10:
            print(f"  ⚠ Écart important entre sources — vérification recommandée")
    elif len(prices) == 1:
        print(f"  ⚠ Une seule source disponible")
    else:
        print(f"  ✗ Aucun prix collecté")

    return prices

if __name__ == "__main__":
    collect()
