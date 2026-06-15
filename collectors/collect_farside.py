import requests
import sqlite3
from datetime import datetime
from html.parser import HTMLParser

DB_PATH = "database/market_terminal.db"

class TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_table = False
        self.in_td = False
        self.rows = []
        self.current_row = []
        self.current_cell = ""

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.current_row = []
        if tag == "td":
            self.in_td = True
            self.current_cell = ""

    def handle_endtag(self, tag):
        if tag == "td":
            self.in_td = False
            self.current_row.append(self.current_cell.strip())
        if tag == "tr" and self.current_row:
            self.rows.append(self.current_row)

    def handle_data(self, data):
        if self.in_td:
            self.current_cell += data

def save_article(title, summary, url):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    existing = c.execute("SELECT id FROM articles WHERE url = ?", (url,)).fetchone()
    if not existing:
        c.execute("""
            INSERT INTO articles (title, summary, source, url, published_at, collected_at, category, importance)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (title, summary, "Farside", url, datetime.now().isoformat(),
              datetime.now().isoformat(), "ETF", "IMPORTANT"))
        conn.commit()
        print(f"  ✓ Sauvegardé : {title[:60]}")
    else:
        print(f"  — Déjà en base : {title[:60]}")
    conn.close()

def collect():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Farside — collecte ETF en cours...")
    url = "https://farside.co.uk/bitcoin-etf-flow-all-data/"
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

    try:
        response = requests.get(url, headers=headers, timeout=15)
        parser = TableParser()
        parser.feed(response.text)

        # Cherche les dernières lignes avec des données de flux
        flux_rows = []
        for row in parser.rows:
            if len(row) >= 3 and row[0] and row[0][0].isdigit():
                flux_rows.append(row)

        if flux_rows:
            # Prend les 3 derniers jours
            recent = flux_rows[-3:]
            lines = []
            for row in recent:
                date = row[0] if row else "?"
                # Calcule le total de la ligne (dernière colonne non vide)
                total = next((row[i] for i in range(len(row)-1, 0, -1) if row[i] and row[i] not in ["-", ""]), "?")
                lines.append(f"{date} : {total}M$")

            summary = "Flux ETF BTC spot (3 derniers jours) : " + " | ".join(lines)
            title = f"ETF BTC Spot — Flux Farside au {datetime.now().strftime('%d/%m/%Y')}"
            save_article(title, summary, url)
            print(f"  ✓ Flux détectés : {' | '.join(lines)}")
        else:
            print("  ⚠ Aucune ligne de flux détectée — structure page peut-être modifiée")

        return True

    except Exception as e:
        print(f"  ✗ Erreur Farside: {e}")
        return False

if __name__ == "__main__":
    collect()
