
import os
import sys
import sqlite3
from datetime import datetime
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

DB_PATH = "database/market_terminal.db"

# ── CANDIDATS PAR CLASSE ──
CANDIDATES = {
    "crypto": [
        {"ticker": "BTC", "nom": "Bitcoin",  "vehicule": "Spot / ETF IBIT"},
        {"ticker": "ETH", "nom": "Ethereum", "vehicule": "Spot"},
        {"ticker": "SOL", "nom": "Solana",   "vehicule": "Spot"},
    ],
    "indice": [
        {"ticker": "^IXIC",    "nom": "Nasdaq 100",  "vehicule": "ETF / CFD"},
        {"ticker": "^GSPC",    "nom": "S&P 500",     "vehicule": "ETF / CFD"},
        {"ticker": "^FCHI",    "nom": "CAC 40",      "vehicule": "ETF / CFD"},
        {"ticker": "^STOXX50E","nom": "EuroStoxx 50","vehicule": "ETF / CFD"},
    ],
    "matiere": [
        {"ticker": "GC=F", "nom": "Or XAU/USD",     "vehicule": "ETF / CFD"},
        {"ticker": "SI=F", "nom": "Argent XAG/USD",  "vehicule": "ETF / CFD"},
    ],
}

STOCKS = {
    "AAPL":"Apple","NVDA":"NVIDIA","MSFT":"Microsoft","META":"Meta",
    "GOOGL":"Alphabet","AMZN":"Amazon","TSLA":"Tesla","AMD":"AMD",
    "IONQ":"IonQ","RGTI":"Rigetti","QUBT":"Quantum Computing","ARQQ":"Arqit Quantum",
    "PLTR":"Palantir","ARM":"ARM Holdings","SMCI":"Super Micro",
    "TTE.PA":"TotalEnergies","AIR.PA":"Airbus","HO.PA":"Thales",
    "LDO.MI":"Leonardo","RTX":"RTX","LMT":"Lockheed Martin",
    "MC.PA":"LVMH","RMS.PA":"Hermès","KER.PA":"Kering",
    "OR.PA":"L'Oréal","ASML.AS":"ASML","CFR.SW":"Richemont",
    "SAP.DE":"SAP","SIE.DE":"Siemens","VOW3.DE":"Volkswagen",
    "NESN.SW":"Nestlé","NOVO-B.CO":"Novo Nordisk",
    "7203.T":"Toyota","005930.KS":"Samsung","TSM":"TSMC",
}

def get_latest(ticker):
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("""
        SELECT price, change_24h FROM market_data
        WHERE asset = ? ORDER BY timestamp DESC LIMIT 1
    """, (ticker,)).fetchone()
    if not row:
        row = conn.execute("""
            SELECT price, change_24h FROM market_data
            WHERE asset LIKE ? ORDER BY timestamp DESC LIMIT 1
        """, (f"{ticker}|%",)).fetchone()
    conn.close()
    if row:
        return {"price": row[0], "change": row[1]}
    return None

def get_recent_news_text():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT title, importance FROM articles
        WHERE importance IN ('CRITIQUE','IMPORTANT')
        ORDER BY collected_at DESC LIMIT 15
    """).fetchall()
    conn.close()
    return [(r[0], r[1]) for r in rows]

def score_factors(ticker, classe):
    factors_pos = []
    factors_neg = []

    dxy   = get_latest("DX-Y.NYB")
    vix   = get_latest("^VIX")
    us10y = get_latest("^TNX")
    gold  = get_latest("GC=F")
    ndx   = get_latest("^IXIC")
    ibit  = get_latest("IBIT")
    asset = get_latest(ticker)

    # ── DXY ──
    if dxy:
        if dxy["change"] < -0.3:
            factors_pos.append(("DXY ↓", f"Dollar en repli ({dxy['change']:+.2f}%) — favorable aux actifs risqués"))
        elif dxy["change"] > 0.3:
            factors_neg.append(("DXY ↑", f"Dollar en hausse ({dxy['change']:+.2f}%) — pression sur les actifs"))

    # ── VIX ──
    if vix:
        if vix["change"] < -5:
            factors_pos.append(("VIX ↓", f"Peur en forte baisse ({vix['change']:+.1f}%) — appétit au risque"))
        elif vix["change"] < -2:
            factors_pos.append(("VIX ↓", f"Peur en baisse ({vix['change']:+.1f}%)"))
        elif vix["change"] > 10:
            factors_neg.append(("VIX ↑", f"Peur en forte hausse ({vix['change']:+.1f}%) — risque élevé"))

    # ── US10Y ──
    if us10y:
        if us10y["change"] < -1:
            factors_pos.append(("US10Y ↓", f"Taux longs en baisse ({us10y['change']:+.2f}%) — favorable aux actifs"))
        elif us10y["change"] > 1:
            factors_neg.append(("US10Y ↑", f"Taux longs en hausse ({us10y['change']:+.2f}%) — pression valorisations"))

    # ── LOGIQUE PAR CLASSE ──
    if classe == "crypto":
        if ibit:
            if ibit["change"] > 2:
                factors_pos.append(("ETF ↑", f"IBIT +{ibit['change']:.1f}% — demande institutionnelle BTC"))
            elif ibit["change"] < -2:
                factors_neg.append(("ETF ↓", f"IBIT {ibit['change']:+.1f}% — sortie institutionnelle"))
        if ndx:
            if ndx["change"] > 0.5:
                factors_pos.append(("Nasdaq ↑", f"+{ndx['change']:.1f}% — corrélation tech favorable"))
            elif ndx["change"] < -1:
                factors_neg.append(("Nasdaq ↓", f"{ndx['change']:+.1f}% — risk-off tech"))
        if gold:
            if gold["change"] > 2:
                factors_neg.append(("Or ↑↑", f"+{gold['change']:.1f}% — fuite vers valeurs refuge"))
            elif gold["change"] > 0.5:
                factors_pos.append(("Or ↑", f"+{gold['change']:.1f}% — inflation hedge actif"))

    elif classe == "indice":
        if ndx and ticker != "^IXIC":
            if ndx["change"] > 0.5:
                factors_pos.append(("Nasdaq ↑", f"+{ndx['change']:.1f}% — leadership tech haussier"))
            elif ndx["change"] < -1:
                factors_neg.append(("Nasdaq ↓", f"{ndx['change']:+.1f}% — tech en repli"))
        if gold and gold["change"] > 1.5:
            factors_neg.append(("Or ↑", f"+{gold['change']:.1f}% — rotation défensive"))

    elif classe == "matiere":
        if ticker in ("GC=F", "SI=F"):
            # Or/Argent : DXY baisse = favorable, taux baisse = favorable
            if dxy and dxy["change"] < -0.3:
                # déjà capturé dessus, on renforce
                pass
            if vix and vix["change"] > 5:
                factors_pos.append(("VIX ↑", f"Peur en hausse ({vix['change']:+.1f}%) — demande refuge Or/Argent"))
            if gold and ticker == "SI=F":
                if gold["change"] > 1:
                    factors_pos.append(("Or ↑", f"+{gold['change']:.1f}% — argent suit l'or"))

    # ── MOMENTUM PROPRE DE L'ACTIF ──
    if asset:
        if asset["change"] > 2:
            factors_pos.append((f"{ticker} ↑", f"Momentum haussier +{asset['change']:.1f}%"))
        elif asset["change"] < -3:
            factors_neg.append((f"{ticker} ↓", f"Momentum baissier {asset['change']:+.1f}%"))

    score_net = len(factors_pos) - len(factors_neg)
    return factors_pos, factors_neg, score_net

def generate_opportunity(ticker, nom, vehicule, classe, factors_pos, factors_neg, asset_data):
    from groq import Groq
    import json
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    factors_text = "\n".join([f"  ✅ {f[0]}: {f[1]}" for f in factors_pos])
    risks_text   = "\n".join([f"  ⚠️ {f[0]}: {f[1]}" for f in factors_neg])
    news = get_recent_news_text()
    news_text = "\n".join([f"  {'🔴' if n[1]=='CRITIQUE' else '🟡'} {n[0]}" for n in news[:8]])

    prompt = f"""Tu es un analyste financier senior. Génère une opportunité de trading structurée.

ACTIF : {nom} ({ticker}) — Classe : {classe}
PRIX ACTUEL : {asset_data['price']:,.2f} ({asset_data['change']:+.2f}%)
VÉHICULE SUGGÉRÉ : {vehicule}

FACTEURS FAVORABLES :
{factors_text}

FACTEURS DÉFAVORABLES :
{risks_text}

ACTUALITÉS RÉCENTES :
{news_text}

Génère une opportunité JSON avec exactement ces champs :
{{
  "thèse": "2-3 phrases expliquant pourquoi maintenant, en croisant les facteurs",
  "entrée": prix_entrée_numérique,
  "stop": prix_stop_numérique,
  "objectif": prix_objectif_numérique,
  "horizon": "X-Y jours",
  "invalidation": "condition précise qui invalide la thèse",
  "véhicule": "Spot / ETF / CFD"
}}

Règles strictes :
- Stop maximum 5% sous l'entrée
- Objectif minimum R/R 1:2.5
- Thèse basée UNIQUEMENT sur les facteurs fournis
- Si les facteurs ne justifient pas une opportunité claire, réponds: {{"skip": true}}
Réponds UNIQUEMENT avec le JSON, sans texte autour."""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=500,
        temperature=0.2
    )
    raw = response.choices[0].message.content.strip()
    raw = raw.replace("```json","").replace("```","").strip()
    return json.loads(raw)

def check_news_for_stock(ticker, nom):
    """Vérifie si des actualités récentes mentionnent cette action."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT title, importance FROM articles
        WHERE importance IN ('CRITIQUE','IMPORTANT')
        ORDER BY collected_at DESC LIMIT 30
    """).fetchall()
    conn.close()
    ticker_clean = ticker.split(".")[0].lower()
    nom_clean    = nom.lower().split()[0]
    matches = []
    for title, importance in rows:
        t = title.lower()
        if ticker_clean in t or nom_clean in t:
            matches.append((title, importance))
    return matches

def score_stock(ticker, nom, asset_data):
    """Score facteurs pour une action individuelle."""
    factors_pos = []
    factors_neg = []
    direction   = "LONG" if asset_data["change"] > 0 else "SHORT"

    dxy   = get_latest("DX-Y.NYB")
    vix   = get_latest("^VIX")
    us10y = get_latest("^TNX")
    ndx   = get_latest("^IXIC")

    # Mouvement propre de l'action — facteur principal
    chg = asset_data["change"]
    if chg >= 5:
        factors_pos.append((f"{ticker} ↑↑", f"Hausse forte +{chg:.1f}% — momentum majeur"))
    elif chg >= 3:
        factors_pos.append((f"{ticker} ↑", f"Hausse significative +{chg:.1f}%"))
    elif chg <= -6:
        factors_neg.append((f"{ticker} ↓↓", f"Baisse forte {chg:.1f}% — signal short"))
    elif chg <= -4:
        factors_neg.append((f"{ticker} ↓", f"Baisse significative {chg:.1f}%"))

    # Actualités spécifiques — facteur clé stockpicking
    news_matches = check_news_for_stock(ticker, nom)
    if news_matches:
        importance_top = "CRITIQUE" if any(n[1]=="CRITIQUE" for n in news_matches) else "IMPORTANT"
        icon = "🔴" if importance_top == "CRITIQUE" else "🟡"
        factors_pos.append(("News ↑", f"{icon} {len(news_matches)} actualité(s) récente(s) sur {nom}"))

    # Contexte macro
    if vix:
        if vix["change"] < -3:
            factors_pos.append(("VIX ↓", f"Sentiment positif ({vix['change']:+.1f}%)"))
        elif vix["change"] > 8:
            factors_neg.append(("VIX ↑", f"Stress marché ({vix['change']:+.1f}%)"))

    if dxy:
        if dxy["change"] < -0.3:
            factors_pos.append(("DXY ↓", f"Dollar faible — favorable actions"))
        elif dxy["change"] > 0.3:
            factors_neg.append(("DXY ↑", f"Dollar fort — pression actions"))

    if ndx:
        if ndx["change"] > 0.5:
            factors_pos.append(("Nasdaq ↑", f"+{ndx['change']:.1f}% — marché actions haussier"))
        elif ndx["change"] < -1:
            factors_neg.append(("Nasdaq ↓", f"{ndx['change']:+.1f}% — marché actions baissier"))

    if us10y:
        if us10y["change"] < -1:
            factors_pos.append(("US10Y ↓", "Taux en baisse — favorable valorisations"))
        elif us10y["change"] > 1:
            factors_neg.append(("US10Y ↑", "Taux en hausse — pression valorisations"))

    score_net = len(factors_pos) - len(factors_neg)
    return factors_pos, factors_neg, score_net, direction

def scan_stocks():
    """Scanne les 35 actions et retourne la meilleure opportunité si signal suffisant."""
    print(f"  → Scan stockpicking ({len(STOCKS)} actions)...")
    best = None
    best_score = 0

    for ticker, nom in STOCKS.items():
        asset_data = get_latest(f"{ticker}|{nom}")
        if not asset_data:
            asset_data = get_latest(ticker)
        if not asset_data:
            continue

        chg = asset_data["change"]
        # Filtre d'entrée : mouvement significatif requis
        if abs(chg) < 3 and chg > -4:
            continue

        factors_pos, factors_neg, score, direction = score_stock(ticker, nom, asset_data)

        if len(factors_pos) < 2 or score <= 0:
            continue

        # Garde le meilleur signal
        total = len(factors_pos)
        if total > best_score:
            best_score = total
            best = {
                "ticker": ticker, "nom": nom,
                "asset_data": asset_data,
                "factors_pos": factors_pos,
                "factors_neg": factors_neg,
                "score": total,
                "direction": direction
            }

    if best:
        print(f"    ✓ Meilleur signal : {best['nom']} ({best['ticker']}) — {best['score']} facteurs")
    else:
        print(f"    → Aucun signal stockpicking suffisant")

    return best

def run(max_opportunities=3):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Moteur opportunités — analyse en cours...")
    opportunities = []

    for classe, candidats in CANDIDATES.items():
        if len(opportunities) >= max_opportunities:
            break
        for c in candidats:
            if len(opportunities) >= max_opportunities:
                break

            ticker  = c["ticker"]
            nom     = c["nom"]
            vehicule = c["vehicule"]

            print(f"  → Analyse {nom} ({ticker})...")
            asset_data = get_latest(ticker)
            if not asset_data:
                print(f"  ⚠ Pas de données pour {ticker}")
                continue

            factors_pos, factors_neg, score = score_factors(ticker, classe)
            print(f"    Score net : {score:+d} ({len(factors_pos)} pos / {len(factors_neg)} neg)")

            if len(factors_pos) < 3 or score <= 0:
                print(f"    ✗ Signal insuffisant")
                continue

            if len(factors_pos) >= 5:
                concordance = "MAJEURE"
            elif len(factors_pos) >= 4:
                concordance = "FORTE"
            else:
                concordance = "MODÉRÉE"

            print(f"    ✓ Signal {concordance} — génération via Groq...")

            try:
                opp = generate_opportunity(ticker, nom, vehicule, classe, factors_pos, factors_neg, asset_data)
                if opp.get("skip"):
                    print(f"    ✗ Groq juge le signal insuffisant")
                    continue

                entry  = opp.get("entrée",   asset_data["price"])
                stop   = opp.get("stop",     entry * 0.96)
                target = opp.get("objectif", entry * 1.08)
                risk   = abs(entry - stop)
                reward = abs(target - entry)
                rr     = round(reward / risk, 1) if risk > 0 else 0

                opportunities.append({
                    "asset":       nom,
                    "ticker":      ticker,
                    "classe":      classe,
                    "price":       asset_data["price"],
                    "change":      asset_data["change"],
                    "concordance": concordance,
                    "factors_pos": factors_pos,
                    "factors_neg": factors_neg,
                    "score":       len(factors_pos),
                    "these":       opp.get("thèse",""),
                    "entree":      entry,
                    "stop":        stop,
                    "objectif":    target,
                    "rr":          rr,
                    "horizon":     opp.get("horizon","7-14 jours"),
                    "invalidation":opp.get("invalidation",""),
                    "vehicule":    opp.get("véhicule", vehicule),
                    "created_at":  datetime.now().isoformat()
                })
                print(f"    ✓ Opportunité {nom} générée — R/R 1:{rr}")

            except Exception as e:
                print(f"    ✗ Erreur : {e}")

    # ── STOCKPICKING ──
    if len(opportunities) < max_opportunities:
        best_stock = scan_stocks()
        if best_stock:
            try:
                opp = generate_opportunity(
                    best_stock["ticker"], best_stock["nom"],
                    "Actions / CFD", "stock",
                    best_stock["factors_pos"], best_stock["factors_neg"],
                    best_stock["asset_data"]
                )
                if not opp.get("skip"):
                    entry  = opp.get("entrée",   best_stock["asset_data"]["price"])
                    stop   = opp.get("stop",     entry * 0.96)
                    target = opp.get("objectif", entry * 1.06)
                    risk   = abs(entry - stop)
                    reward = abs(target - entry)
                    rr     = round(reward / risk, 1) if risk > 0 else 0
                    opportunities.append({
                        "asset":       best_stock["nom"],
                        "ticker":      best_stock["ticker"],
                        "classe":      "stock",
                        "price":       best_stock["asset_data"]["price"],
                        "change":      best_stock["asset_data"]["change"],
                        "concordance": "FORTE" if best_stock["score"] >= 4 else "MODÉRÉE",
                        "factors_pos": best_stock["factors_pos"],
                        "factors_neg": best_stock["factors_neg"],
                        "score":       best_stock["score"],
                        "these":       opp.get("thèse",""),
                        "entree":      entry,
                        "stop":        stop,
                        "objectif":    target,
                        "rr":          rr,
                        "horizon":     opp.get("horizon","5-10 jours"),
                        "invalidation":opp.get("invalidation",""),
                        "vehicule":    opp.get("véhicule","Actions / CFD"),
                        "created_at":  datetime.now().isoformat()
                    })
                    print(f"    ✓ Opportunité stock {best_stock['nom']} générée — R/R 1:{rr}")
            except Exception as e:
                print(f"    ✗ Erreur stock : {e}")

    if not opportunities:
        print(f"  → Aucune opportunité détectée — marchés sans signal clair")
    else:
        print(f"  ✓ {len(opportunities)} opportunité(s) générée(s)")

    return opportunities

if __name__ == "__main__":
    opps = run()
    for o in opps:
        print(f"\n{'='*50}")
        print(f"ACTIF    : {o['asset']} @ {o['price']:,.2f}")
        print(f"SIGNAL   : {o['concordance']} ({o['score']} facteurs)")
        print(f"THÈSE    : {o['these']}")
        print(f"R/R      : 1:{o['rr']}")
