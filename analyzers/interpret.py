import os
import sqlite3
from groq import Groq
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()
DB_PATH = "database/market_terminal.db"
client  = Groq(api_key=os.getenv("GROQ_API_KEY"))

def get_latest_prices():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT asset, price, change_24h, source
        FROM market_data
        WHERE timestamp = (
            SELECT MAX(timestamp) FROM market_data m2
            WHERE m2.asset = market_data.asset
        )
    """).fetchall()
    conn.close()
    return rows

def get_recent_news(limit=15):
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT title, source, importance
        FROM articles
        WHERE importance IN ('CRITIQUE','IMPORTANT')
        ORDER BY collected_at DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return rows

def build_context(prices, news):
    """Construit le contexte factuel brut à envoyer au LLM"""
    lines = ["=== DONNÉES MARCHÉ EN DIRECT ==="]

    # Crypto
    crypto = [(a,p,c) for a,p,c,s in prices if s == "coingecko"]
    if crypto:
        lines.append("\nCRYPTO:")
        for asset, price, change in crypto:
            lines.append(f"  {asset}: ${price:,.2f} ({change:+.2f}%)")

    # ETF
    etf_list = ["IBIT","FBTC","BITB","ARKB","HODL"]
    etf = [(a,p,c) for a,p,c,s in prices if a in etf_list]
    if etf:
        lines.append("\nETF BTC SPOT:")
        for asset, price, change in etf:
            lines.append(f"  {asset}: ${price:,.2f} ({change:+.2f}%)")

    # Macro
    macro_map = {
        "DX-Y.NYB":"DXY","^TNX":"US10Y","^VIX":"VIX",
        "^IXIC":"Nasdaq","^GSPC":"SP500","^FCHI":"CAC40",
        "^N225":"Nikkei","GC=F":"Or","SI=F":"Argent",
        "CL=F":"WTI","BZ=F":"Brent","EURUSD=X":"EURUSD"
    }
    macro = [(macro_map.get(a,a),p,c) for a,p,c,s in prices
             if a in macro_map]
    if macro:
        lines.append("\nMACRO MONDIALE:")
        for name, price, change in macro:
            lines.append(f"  {name}: {price:.2f} ({change:+.2f}%)")

    # News
    if news:
        lines.append("\n=== ACTUALITÉS RÉCENTES ===")
        for title, source, importance in news:
            marker = "🔴" if importance == "CRITIQUE" else "🟡"
            lines.append(f"  {marker} [{source}] {title}")

    return "\n".join(lines)

def interpret(context, question, max_tokens=400):
    """Appelle Groq avec le contexte factuel et une question précise"""
    system = """Tu es un analyste financier senior spécialisé macro et crypto.
Tu travailles UNIQUEMENT avec les données factuelles fournies — jamais d'invention.
Tu croises TOUJOURS au minimum 2-3 sources avant de conclure.
Tes réponses sont en français, concises, directes, sans jargon inutile.
Si les données sont insuffisantes pour conclure, tu le dis clairement."""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": f"{context}\n\n{question}"}
        ],
        max_tokens=max_tokens,
        temperature=0.3
    )
    return response.choices[0].message.content.strip()

def generate_interpretations():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Interprétation en cours...")

    prices  = get_latest_prices()
    news    = get_recent_news()
    context = build_context(prices, news)

    results = {}

    # 1. Résumé exécutif global
    print("  → Résumé exécutif...")
    results["resume"] = interpret(context, """
En croisant les données de prix, les flux ETF, le DXY, le VIX et les actualités,
rédige un résumé exécutif de 4-5 phrases sur l'état des marchés ce matin.
Identifie les 2-3 signaux les plus importants et leur corrélation.
Commence directement par l'analyse, sans introduction.""")

    # 2. Brief BTC
    print("  → Analyse BTC...")
    results["btc"] = interpret(context, """
En croisant le prix BTC, les flux ETF (IBIT/FBTC), le DXY, le VIX et les news récentes,
explique en 2-3 phrases pourquoi BTC évolue ainsi aujourd'hui.
Cite les facteurs concordants et les risques.""")

    # 3. Brief macro
    print("  → Analyse macro...")
    results["macro"] = interpret(context, """
En croisant DXY, US10Y, VIX, Or, Pétrole et les indices actions,
donne en 2-3 phrases le contexte macro global ce matin.
Qu'est-ce que ces signaux combinés indiquent sur l'appétit au risque ?""")

    # 4. Signal ETF
    print("  → Signal ETF...")
    results["etf"] = interpret(context, """
En croisant les performances des ETF BTC (IBIT, FBTC, BITB, ARKB, HODL) avec
le prix BTC et le contexte macro, que révèlent les ETF aujourd'hui ?
Réponds en 2 phrases maximum.""")

    print(f"  ✓ {len(results)} interprétations générées")
    return results

if __name__ == "__main__":
    results = generate_interpretations()
    print("\n" + "="*60)
    for key, text in results.items():
        print(f"\n[{key.upper()}]")
        print(text)
        print()
