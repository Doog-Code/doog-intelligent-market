import os
import sys
import sqlite3
from datetime import datetime
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

DB_PATH = "database/market_terminal.db"

def get_latest(ticker):
    """Récupère le dernier prix et variation d'un actif."""
    conn = sqlite3.connect(DB_PATH)
    # Recherche exacte d'abord
    row = conn.execute("""
        SELECT price, change_24h FROM market_data
        WHERE asset = ?
        ORDER BY timestamp DESC LIMIT 1
    """, (ticker,)).fetchone()
    # Si pas trouvé, recherche avec pipe (format "ticker|nom")
    if not row:
        row = conn.execute("""
            SELECT price, change_24h FROM market_data
            WHERE asset LIKE ?
            ORDER BY timestamp DESC LIMIT 1
        """, (f"{ticker}|%",)).fetchone()
    conn.close()
    if row:
        return {"price": row[0], "change": row[1]}
    return None

def get_recent_news_text():
    """Récupère les titres des news récentes pour contexte."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT title, importance FROM articles
        WHERE importance IN ('CRITIQUE','IMPORTANT')
        ORDER BY collected_at DESC LIMIT 15
    """).fetchall()
    conn.close()
    return [(r[0], r[1]) for r in rows]

def score_factors(asset):
    """
    Évalue les facteurs de marché pour un actif donné.
    Retourne liste de facteurs positifs, négatifs et le score net.
    """
    factors_pos = []
    factors_neg = []

    # ── FACTEUR 1 : DXY ──
    dxy = get_latest("DX-Y.NYB")
    if dxy:
        if dxy["change"] < -0.3:
            factors_pos.append(("DXY ↓", "Dollar en repli — favorable aux actifs risqués"))
        elif dxy["change"] > 0.3:
            factors_neg.append(("DXY ↑", "Dollar en hausse — pression sur les actifs"))

    # ── FACTEUR 2 : VIX ──
    vix = get_latest("^VIX")
    if vix:
        if vix["change"] < -5:
            factors_pos.append(("VIX ↓", f"Peur en forte baisse ({vix['change']:+.1f}%) — appétit au risque"))
        elif vix["change"] < -2:
            factors_pos.append(("VIX ↓", f"Peur en baisse ({vix['change']:+.1f}%)"))
        elif vix["change"] > 10:
            factors_neg.append(("VIX ↑", f"Peur en forte hausse ({vix['change']:+.1f}%) — risque élevé"))

    # ── FACTEUR 3 : ETF BTC (IBIT comme proxy institutionnel) ──
    ibit = get_latest("IBIT")
    if ibit:
        if ibit["change"] > 2:
            factors_pos.append(("ETF ↑", f"IBIT +{ibit['change']:.1f}% — demande institutionnelle"))
        elif ibit["change"] < -2:
            factors_neg.append(("ETF ↓", f"IBIT {ibit['change']:+.1f}% — sortie institutionnelle"))

    # ── FACTEUR 4 : Nasdaq (corrélation crypto/tech) ──
    ndx = get_latest("^IXIC")
    if ndx:
        if ndx["change"] > 0.5:
            factors_pos.append(("Nasdaq ↑", f"+{ndx['change']:.1f}% — contexte actions favorable"))
        elif ndx["change"] < -1:
            factors_neg.append(("Nasdaq ↓", f"{ndx['change']:+.1f}% — risk-off actions"))

    # ── FACTEUR 5 : Or (signal refuge vs risque) ──
    gold = get_latest("GC=F")
    if gold:
        if asset in ["BTC","ETH","SOL"]:
            # Or en forte hausse = fuite vers refuge = négatif pour crypto
            if gold["change"] > 2:
                factors_neg.append(("Or ↑↑", f"+{gold['change']:.1f}% — fuite vers valeurs refuge"))
            elif gold["change"] > 0.5:
                factors_pos.append(("Or ↑", f"+{gold['change']:.1f}% — inflation hedge actif"))

    # ── FACTEUR 6 : US10Y ──
    us10y = get_latest("^TNX")
    if us10y:
        if us10y["change"] < -1:
            factors_pos.append(("US10Y ↓", "Taux longs en baisse — favorable aux actifs risqués"))
        elif us10y["change"] > 1:
            factors_neg.append(("US10Y ↑", "Taux longs en hausse — pression sur valorisations"))

    # ── FACTEUR 7 : Performance de l'actif lui-même ──
    asset_data = get_latest(asset)
    if asset_data:
        if asset_data["change"] > 2:
            factors_pos.append((f"{asset} ↑", f"Momentum haussier +{asset_data['change']:.1f}%"))
        elif asset_data["change"] < -3:
            factors_neg.append((f"{asset} ↓", f"Momentum baissier {asset_data['change']:+.1f}%"))

    score_net = len(factors_pos) - len(factors_neg)
    return factors_pos, factors_neg, score_net

def generate_opportunity(asset, factors_pos, factors_neg, asset_data):
    """Demande à Groq de structurer une opportunité complète."""
    from groq import Groq
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    factors_text = "\n".join([f"  ✅ {f[0]}: {f[1]}" for f in factors_pos])
    risks_text   = "\n".join([f"  ⚠️ {f[0]}: {f[1]}" for f in factors_neg])

    news = get_recent_news_text()
    news_text = "\n".join([f"  {'🔴' if n[1]=='CRITIQUE' else '🟡'} {n[0]}" for n in news[:8]])

    prompt = f"""Tu es un analyste financier senior. Génère une opportunité de trading structurée.

ACTIF : {asset}
PRIX ACTUEL : ${asset_data['price']:,.2f} ({asset_data['change']:+.2f}%)

FACTEURS FAVORABLES DÉTECTÉS :
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
        messages=[{"role":"user","content":prompt}],
        max_tokens=500,
        temperature=0.2
    )

    import json
    raw = response.choices[0].message.content.strip()
    raw = raw.replace("```json","").replace("```","").strip()
    return json.loads(raw)

def run(max_opportunities=3):
    """Point d'entrée principal du moteur d'opportunités."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Moteur opportunités — analyse en cours...")

    CANDIDATES = ["BTC","ETH","SOL"]
    opportunities = []

    for asset in CANDIDATES:
        if len(opportunities) >= max_opportunities:
            break

        print(f"  → Analyse {asset}...")
        asset_data = get_latest(asset)
        if not asset_data:
            print(f"  ⚠ Pas de données pour {asset}")
            continue

        factors_pos, factors_neg, score = score_factors(asset)
        total_factors = len(factors_pos) + len(factors_neg)

        print(f"    Score net : {score:+d} ({len(factors_pos)} pos / {len(factors_neg)} neg)")

        # Seuil minimum : 3 facteurs positifs ET score net positif
        if len(factors_pos) < 3 or score <= 0:
            print(f"    ✗ Signal insuffisant — pas d'opportunité générée")
            continue

        # Niveau de concordance
        if len(factors_pos) >= 5:
            concordance = "MAJEURE"
        elif len(factors_pos) >= 4:
            concordance = "FORTE"
        else:
            concordance = "MODÉRÉE"

        print(f"    ✓ Signal {concordance} — génération opportunité via Groq...")

        try:
            opp = generate_opportunity(asset, factors_pos, factors_neg, asset_data)

            if opp.get("skip"):
                print(f"    ✗ Groq juge le signal insuffisant — skip")
                continue

            # Calcule R/R
            entry  = opp.get("entrée", asset_data["price"])
            stop   = opp.get("stop",   entry * 0.96)
            target = opp.get("objectif", entry * 1.08)
            risk   = abs(entry - stop)
            reward = abs(target - entry)
            rr     = round(reward / risk, 1) if risk > 0 else 0

            opportunities.append({
                "asset":        asset,
                "price":        asset_data["price"],
                "change":       asset_data["change"],
                "concordance":  concordance,
                "factors_pos":  factors_pos,
                "factors_neg":  factors_neg,
                "score":        len(factors_pos),
                "these":        opp.get("thèse",""),
                "entree":       entry,
                "stop":         stop,
                "objectif":     target,
                "rr":           rr,
                "horizon":      opp.get("horizon","7-14 jours"),
                "invalidation": opp.get("invalidation",""),
                "vehicule":     opp.get("véhicule","Spot"),
                "created_at":   datetime.now().isoformat()
            })

            print(f"    ✓ Opportunité {asset} générée — R/R 1:{rr}")

        except Exception as e:
            print(f"    ✗ Erreur génération : {e}")

    if not opportunities:
        print(f"  → Aucune opportunité détectée aujourd'hui — marchés sans signal clair")
    else:
        print(f"  ✓ {len(opportunities)} opportunité(s) générée(s)")

    return opportunities

if __name__ == "__main__":
    opps = run()
    if opps:
        for o in opps:
            print(f"\n{'='*50}")
            print(f"ACTIF    : {o['asset']} @ ${o['price']:,.2f}")
            print(f"SIGNAL   : {o['concordance']} ({o['score']} facteurs)")
            print(f"THÈSE    : {o['these']}")
            print(f"ENTRÉE   : ${o['entree']:,.2f}")
            print(f"STOP     : ${o['stop']:,.2f}")
            print(f"OBJECTIF : ${o['objectif']:,.2f}")
            print(f"R/R      : 1:{o['rr']}")
            print(f"HORIZON  : {o['horizon']}")
            print(f"INVALID. : {o['invalidation']}")
