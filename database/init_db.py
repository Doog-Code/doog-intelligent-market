import sqlite3
from datetime import datetime

DB_PATH = "database/market_terminal.db"

def init():
    print("Création de la base de données...")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.executescript("""
        CREATE TABLE IF NOT EXISTS market_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset TEXT,
            price REAL,
            change_24h REAL,
            volume REAL,
            timestamp TEXT,
            source TEXT
        );

        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            summary TEXT,
            source TEXT,
            url TEXT,
            published_at TEXT,
            collected_at TEXT,
            category TEXT,
            importance TEXT
        );

        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_date TEXT,
            html TEXT,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS opportunities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset TEXT,
            thesis TEXT,
            entry REAL,
            stop REAL,
            target REAL,
            rr TEXT,
            horizon TEXT,
            factors TEXT,
            concordance INTEGER,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS evaluations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            opportunity_id INTEGER,
            score REAL,
            result TEXT,
            comment TEXT,
            evaluated_at TEXT
        );
    """)

    conn.commit()
    conn.close()
    print("✓ Base de données créée : database/market_terminal.db")
    print("✓ Tables : market_data, articles, reports, opportunities, evaluations")

if __name__ == "__main__":
    init()
