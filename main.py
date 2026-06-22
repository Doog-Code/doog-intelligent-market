import os
import sqlite3
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
DB_PATH = "database/market_terminal.db"

from analyzers.opportunity_engine import run as run_opportunities
from analyzers.opportunity_tracker import save_opportunity, run_tracker, get_closed_opportunities, get_stats

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

# ══════════════════════════════════════════
# COLLECTE
# ══════════════════════════════════════════
def run_collectors():
    log("DOOG INTELLIGENT MARKET — Collecte démarrée")
    from collectors.collect_coingecko import collect as coingecko
    from collectors.collect_etf       import collect as etf
    from collectors.collect_macro     import collect as macro
    from collectors.collect_news      import collect as news
    from collectors.collect_stocks    import collect as stocks
    coingecko()
    etf()
    macro()
    news()
    stocks()
    log("Collecte terminée")

# ══════════════════════════════════════════
# DONNÉES
# ══════════════════════════════════════════
def get_market_data():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT asset, price, change_24h, source
        FROM market_data
        WHERE timestamp = (
            SELECT MAX(timestamp) FROM market_data m2
            WHERE m2.asset = market_data.asset
        )
        ORDER BY source, asset
    """).fetchall()
    conn.close()
    data = {}
    for asset, price, change, source in rows:
        ticker = asset.split("|")[0]
        name   = asset.split("|")[1] if "|" in asset else asset
        data[ticker] = {"name": name, "price": price,
                        "change": change, "source": source}
    return data

def get_news(limit=30):
    conn = sqlite3.connect(DB_PATH)
    # Quota fixe : 10 CRITIQUE + 20 IMPORTANT
    critiques = conn.execute("""
        SELECT title, summary, source, url, published_at, category, importance
        FROM articles WHERE importance = 'CRITIQUE'
        ORDER BY collected_at DESC LIMIT 10
    """).fetchall()
    importants = conn.execute("""
        SELECT title, summary, source, url, published_at, category, importance
        FROM articles WHERE importance = 'IMPORTANT'
        ORDER BY collected_at DESC LIMIT 20
    """).fetchall()
    conn.close()
    rows = critiques + importants
    return [{"title":r[0], "summary":r[1], "source":r[2],
             "url":r[3], "published":r[4], "category":r[5],
             "importance":r[6]} for r in rows]

# ══════════════════════════════════════════
# INTERPRÉTATION GROQ
# ══════════════════════════════════════════
def generate_interpretations(market_data, news_items):
    log("Interprétation Groq en cours...")
    try:
        from groq import Groq
        client = Groq(api_key=os.getenv("GROQ_API_KEY"))

        # Construit le contexte factuel
        lines = ["=== DONNÉES MARCHÉ EN DIRECT ==="]

        ETF_LIST = ["IBIT","FBTC","BITB","ARKB","HODL"]
        MACRO_KEYS = ["DX-Y.NYB","^TNX","^VIX","^IXIC","^GSPC",
                      "^FCHI","^N225","GC=F","SI=F","CL=F","EURUSD=X"]
        MACRO_NAMES = {
            "DX-Y.NYB":"DXY","^TNX":"US10Y","^VIX":"VIX",
            "^IXIC":"Nasdaq","^GSPC":"SP500","^FCHI":"CAC40",
            "^N225":"Nikkei","GC=F":"Or","SI=F":"Argent",
            "CL=F":"WTI","EURUSD=X":"EURUSD"
        }

        crypto = {k:v for k,v in market_data.items() if v["source"]=="coingecko"}
        etfs   = {k:v for k,v in market_data.items() if k in ETF_LIST}
        macro  = {k:v for k,v in market_data.items() if k in MACRO_KEYS}

        if crypto:
            lines.append("\nCRYPTO:")
            for t,d in crypto.items():
                lines.append(f"  {t}: ${d['price']:,.2f} ({d['change']:+.2f}%)")

        if etfs:
            lines.append("\nETF BTC SPOT:")
            for t,d in etfs.items():
                lines.append(f"  {t}: ${d['price']:,.2f} ({d['change']:+.2f}%)")

        if macro:
            lines.append("\nMACRO:")
            for t,d in macro.items():
                n = MACRO_NAMES.get(t,t)
                lines.append(f"  {n}: {d['price']:.2f} ({d['change']:+.2f}%)")

        if news_items:
            lines.append("\nACTUALITÉS RÉCENTES:")
            for n in news_items[:12]:
                m = "🔴" if n["importance"]=="CRITIQUE" else "🟡"
                lines.append(f"  {m} [{n['source']}] {n['title']}")

        context = "\n".join(lines)

        system = """Tu es un analyste financier senior spécialisé macro et crypto.
Tu travailles UNIQUEMENT avec les données factuelles fournies — jamais d'invention.
Tu croises TOUJOURS au minimum 2-3 sources avant de conclure.
Ne jamais inventer de causalité sans signal direct dans les données.
Tes réponses sont en français, concises, directes, sans introduction."""

        def ask(question, tokens=350):
            r = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role":"system","content":system},
                    {"role":"user","content":f"{context}\n\n{question}"}
                ],
                max_tokens=tokens,
                temperature=0.3
            )
            return r.choices[0].message.content.strip()

        results = {}

        log("  → Résumé exécutif...")
        results["resume"] = ask("""En croisant prix crypto, flux ETF, DXY, VIX et actualités,
rédige un résumé exécutif de 4-5 phrases sur l'état des marchés ce matin.
Identifie les 2-3 signaux les plus importants et leurs corrélations.
Commence directement par l'analyse.""")

        log("  → Analyse BTC...")
        results["btc"] = ask("""En croisant le prix BTC, les ETF (IBIT/FBTC), le DXY, le VIX
et les news récentes, explique en 2-3 phrases pourquoi BTC évolue ainsi.
Cite les facteurs concordants et les risques identifiés.""")

        log("  → Analyse macro...")
        results["macro"] = ask("""En croisant DXY, US10Y, VIX, Or, Pétrole et indices actions,
donne en 2-3 phrases le contexte macro global ce matin.
Que signalent ces indicateurs combinés sur l'appétit au risque ?""")

        log("  → Signal ETF...")
        results["etf"] = ask("""En croisant les ETF BTC (IBIT, FBTC, BITB, ARKB, HODL)
avec le prix BTC et le contexte macro, que révèlent les ETF aujourd'hui ?
2 phrases maximum.""")

        log(f"  ✓ {len(results)} interprétations générées")
        return results

    except Exception as e:
        log(f"  ⚠ Groq indisponible : {e}")
        return {}

# ══════════════════════════════════════════
# HELPERS HTML
# ══════════════════════════════════════════
def age_label(pub):
    try:
        delta = datetime.now() - datetime.fromisoformat(pub.replace("Z",""))
        h = int(delta.total_seconds() // 3600)
        return f"Il y a {h}h" if h < 24 else f"Il y a {delta.days}j"
    except:
        return ""

def fmt(ticker, d):
    p, c  = d["price"], d["change"]
    arrow = "▲" if c >= 0 else "▼"
    cls   = "up" if c >= 0 else "dn"
    if p > 1000:   ps = f"${p:,.0f}"
    elif p > 1:    ps = f"${p:,.2f}"
    else:          ps = f"{p:.4f}"
    return arrow, cls, ps, f"{c:+.2f}%"

def market_card(ticker, d, link):
    arrow, cls, ps, chg = fmt(ticker, d)
    pct = min(abs(d["change"]) * 8, 100)
    bar = "var(--green)" if d["change"] >= 0 else "var(--red)"
    return f"""<div class="mc">
      <div class="mc-name">{ticker}</div>
      <div class="mc-label">{d['name'][:26]}</div>
      <div class="mc-price">{ps}</div>
      <div class="mc-row">
        <span class="mc-chg {cls}">{arrow} {chg}</span>
        <a class="src-link" href="{link}" target="_blank">↗</a>
      </div>
      <div class="mbar"><div class="mbar-f" style="width:{pct:.0f}%;background:{bar}"></div></div>
    </div>"""

def news_card(n):
    bc  = "b-crit" if n["importance"]=="CRITIQUE" else "b-imp"
    bt  = "Critique" if n["importance"]=="CRITIQUE" else "Important"
    age = age_label(n["published"])
    pub = n["published"][:16].replace("T"," ") if n["published"] else ""
    sm  = n["summary"][:300]+"..." if len(n["summary"])>300 else n["summary"]
    return f"""<div class="news-card">
      <div class="nc-top">
        <span class="badge {bc}">{bt}</span>
        <div class="nc-meta">
          <span class="nc-source">{n['source']}</span>
          <a class="src-link" href="{n['url']}" target="_blank">→ Source originale</a>
        </div>
      </div>
      <div class="nc-title">{n['title']}</div>
      <div class="nc-body">{sm}</div>
      <div class="nc-foot">
        <span class="nc-time">{pub}</span>
        <span class="nc-age">{age}</span>
      </div>
    </div>"""

def interp_block(text, color="var(--neon)"):
    if not text:
        return ""
    return f"""<div class="interp-block" style="border-left-color:{color}">
      <div class="interp-label">⚡ Analyse Doog · Groq / Llama 3.3</div>
      <div class="interp-text">{text}</div>
    </div>"""

def sum_line(tick, d, note=""):
    if not d:
        return ""
    arrow, cls, ps, chg = fmt(tick, d)
    note_html = f'<span class="sum-note">— {note}</span>' if note else ""
    return f"""<div class="summary-line">
      <span class="sum-tick">{tick}</span>
      <span class="sum-text">
        <span class="sum-val {cls}">{ps} ({chg})</span> {note_html}
      </span>
    </div>"""

# ══════════════════════════════════════════
# GÉNÉRATION RAPPORT
# ══════════════════════════════════════════


def history_block(tracking, stats, closed):
    """Génère le HTML du bloc historique des performances."""

    # Stats globales
    if stats.get("closed", 0) == 0:
        stats_html = """<div style="color:var(--text3);font-size:12px;
            font-style:italic;padding:10px 0">
            Historique vide — les premières opportunités sont en cours de suivi.</div>"""
    else:
        stats_html = f"""<div style="display:grid;grid-template-columns:1fr 1fr 1fr;
            gap:8px;margin-bottom:16px">
          <div class="hs"><div class="hs-val" style="color:var(--green)">{stats.get("avg_score","—")}</div>
            <div class="hs-lbl">Score moyen</div></div>
          <div class="hs"><div class="hs-val" style="color:var(--neon)">{stats.get("win_rate","—")}%</div>
            <div class="hs-lbl">Taux succès</div></div>
          <div class="hs"><div class="hs-val" style="color:var(--text2)">{stats.get("closed","—")}</div>
            <div class="hs-lbl">Clôturées</div></div>
        </div>"""

    # Opportunités en cours
    open_html = ""
    open_items = [t for t in tracking if t["status"] == "OUVERTE"]
    for t in open_items:
        pnl_cls = "up" if t["pnl_pct"] >= 0 else "dn"
        pnl_arrow = "▲" if t["pnl_pct"] >= 0 else "▼"
        bar_pct = min(abs(t["pnl_pct"]) * 5, 100)
        bar_col = "var(--green)" if t["pnl_pct"] >= 0 else "var(--red)"
        open_html += f"""
        <div class="hist-card">
          <div class="hist-top">
            <div>
              <div class="hist-asset">{t["asset"]} · En cours</div>
              <div class="hist-horizon">Jour {t["days_open"]}/{t["max_days"]} · Entrée ${t["entry"]:,.2f}</div>
            </div>
            <div class="hist-score-wrap">
              <span class="hist-score {pnl_cls}">{pnl_arrow} {t["pnl_pct"]:+.1f}%</span>
            </div>
          </div>
          <div class="hist-thesis">{t.get("thesis","")[:120]}...</div>
          <div class="hist-result" style="color:var(--text3)">
            📍 Prix actuel : ${t["current"]:,.2f}
            · Stop : ${t["stop"]:,.2f}
            · Objectif : ${t["target"]:,.2f}
          </div>
          <div class="score-bar">
            <div class="score-fill" style="width:{bar_pct:.0f}%;background:{bar_col}"></div>
          </div>
        </div>"""

    # Opportunités clôturées
    closed_html = ""
    for row in closed:
        asset, entry, target, stop, rr, thesis, horizon, created, score, result, comment, evaluated = row
        if result == "OBJECTIF":
            result_icon, result_color = "✓", "var(--green)"
        elif result == "STOP":
            result_icon, result_color = "✗", "var(--red)"
        elif result in ("EXPIRE_POSITIF",):
            result_icon, result_color = "~", "var(--green)"
        else:
            result_icon, result_color = "~", "var(--amber)"

        score_pct = min(score * 10, 100)
        stars = "★" * int(score/2.5) + "☆" * (4 - int(score/2.5))
        created_short = created[:10] if created else ""
        eval_short    = evaluated[:10] if evaluated else ""

        closed_html += f"""
        <div class="hist-card">
          <div class="hist-top">
            <div>
              <div class="hist-asset">{asset} · {horizon}</div>
              <div class="hist-horizon">Ouvert : {created_short} · Fermé : {eval_short}</div>
            </div>
            <div class="hist-score-wrap">
              <span class="hist-score" style="color:{result_color}">{score}</span>
              <span class="hist-stars">{stars}</span>
            </div>
          </div>
          <div class="hist-thesis">{thesis[:120]}...</div>
          <div class="hist-result" style="color:{result_color}">
            {result_icon} {comment}
          </div>
          <div class="score-bar">
            <div class="score-fill" style="width:{score_pct:.0f}%;background:{result_color}"></div>
          </div>
        </div>"""

    if not open_items and not closed:
        body = """<div style="color:var(--text3);font-size:12px;font-style:italic;
            padding:10px 0">Les premières opportunités générées aujourd'hui
            seront suivies ici dès demain.</div>"""
    else:
        body = open_html + closed_html

    return stats_html + body

def opportunity_cards(opportunities):
    """Génère le HTML pour le bloc opportunités."""
    if not opportunities:
        return """<div style="
            background:var(--bg3);border:1px solid var(--border);
            border-radius:10px;padding:20px;text-align:center;
            color:var(--text3);font-size:13px;font-style:italic;">
            Aucune opportunité détectée aujourd'hui.<br>
            <span style="font-size:11px">Le marché ne présente pas de signal suffisamment clair — patience.</span>
        </div>"""

    cards = []
    for o in opportunities:
        # Couleur selon concordance
        if o["concordance"] == "MAJEURE":
            conc_color = "var(--neon)"
        elif o["concordance"] == "FORTE":
            conc_color = "var(--green)"
        else:
            conc_color = "var(--amber)"

        # Facteurs positifs et négatifs
        fpos = "".join([
            f'<span class="fc fc-pos">▲ {f[0]}</span>'
            for f in o["factors_pos"]
        ])
        fneg = "".join([
            f'<span class="fc fc-neg">▼ {f[0]}</span>'
            for f in o["factors_neg"]
        ])

        # R/R bar visuelle
        rr_pct = min(o["rr"] * 20, 100)

        cards.append(f"""
        <div class="opp-card">
          <div class="opp-head">
            <div>
              <div class="opp-asset">{o["asset"]}</div>
              <div class="opp-mkt">{o["vehicule"]} · Long</div>
            </div>
            <div style="text-align:right">
              <div class="conc-num" style="color:{conc_color}">{o["score"]}</div>
              <div class="conc-lbl">Facteurs</div>
              <div class="conc-pill" style="background:rgba(0,229,255,.1);
                color:{conc_color};border:1px solid {conc_color};
                font-size:9px;padding:2px 7px;border-radius:3px;
                margin-top:3px;display:inline-block">
                {o["concordance"]}
              </div>
            </div>
          </div>
          <div class="opp-body">
            <div class="opp-thesis">{o["these"]}</div>
            <div class="opp-levels">
              <div class="ol">
                <div class="ol-lbl">Entrée</div>
                <div class="ol-val" style="color:var(--green)">${o["entree"]:,.2f}</div>
              </div>
              <div class="ol">
                <div class="ol-lbl">Objectif</div>
                <div class="ol-val" style="color:var(--neon)">${o["objectif"]:,.2f}</div>
              </div>
              <div class="ol">
                <div class="ol-lbl">Stop</div>
                <div class="ol-val" style="color:var(--red)">${o["stop"]:,.2f}</div>
              </div>
            </div>
            <div class="rr-block">
              <div>
                <div class="rr-title">Ratio Rendement / Risque</div>
                <div class="rr-val">1 : {o["rr"]}</div>
                <div class="rr-desc">Pour 1$ risqué → {o["rr"]}$ visé</div>
              </div>
              <div style="text-align:right">
                <div class="horizon-lbl">Horizon</div>
                <div class="horizon-val">{o["horizon"]}</div>
              </div>
            </div>
            <div class="factors">{fpos}{fneg}</div>
            <div class="inval-row">
              <span class="inval-lbl">Invalidation :</span>
              <span>{o["invalidation"]}</span>
            </div>
          </div>
        </div>""")

    return "\n".join(cards)

def generate_report(market_data, news_items, interpretations, opportunities=[], tracking=[], stats={}, closed=[]):
    log("Génération du rapport HTML...")
    now      = datetime.now()
    date_str = now.strftime("%A %d %B %Y · %H:%M").capitalize()

    ETF_LIST   = ["IBIT","FBTC","BITB","ARKB","HODL"]
    CG_IDS     = {"BTC":"bitcoin","ETH":"ethereum","SOL":"solana"}
    MACRO_DISP = {
        "DX-Y.NYB":"DXY","^TNX":"US10Y","^IRX":"US3M","^VIX":"VIX",
        "^IXIC":"Nasdaq","^GSPC":"SP500","^FCHI":"CAC40",
        "^N225":"Nikkei","^STOXX50E":"EuroStoxx",
        "EURUSD=X":"EUR/USD","JPY=X":"USD/JPY","GBPUSD=X":"GBP/USD",
        "GC=F":"Or","SI=F":"Argent","CL=F":"WTI","BZ=F":"Brent"
    }
    yf = "https://finance.yahoo.com/quote/"
    cg = "https://www.coingecko.com/en/coins/"

    # Cartes marché
    crypto_cards = "".join([
        market_card(t, d, cg+CG_IDS.get(t,t.lower()))
        for t,d in market_data.items() if d["source"]=="coingecko"
    ])
    etf_cards = "".join([
        market_card(t, d, yf+t)
        for t,d in market_data.items() if t in ETF_LIST
    ])
    macro_cards = "".join([
        market_card(MACRO_DISP.get(t,t), d, yf+t)
        for t,d in market_data.items()
        if d["source"].startswith("yahoo_") and t not in ETF_LIST
    ])
    # Napoléon 20F — récupération directe depuis la base
    import sqlite3 as _sq
    _conn = _sq.connect(DB_PATH)
    _row = _conn.execute("""
        SELECT price, change_24h FROM market_data
        WHERE asset LIKE '%Napoleon%' AND source = 'bdor.fr'
        ORDER BY timestamp DESC LIMIT 1
    """).fetchone()
    _conn.close()
    if _row:
        macro_cards += market_card(
            "Napoléon 20F",
            {"name": "Napoléon 20F · bdor.fr", "price": _row[0], "change": _row[1]},
            "https://www.bdor.fr/produits-d-investissement-or/cours-prix-pieces-d-or/20-francs-napoleon-or"
        )

    # News
    critiques  = [n for n in news_items if n["importance"]=="CRITIQUE"][:5]
    importants = [n for n in news_items if n["importance"]=="IMPORTANT"][:8]
    crit_html  = "".join([news_card(n) for n in critiques]) or "<p class='empty'>Aucune actualité critique.</p>"
    imp_html   = "".join([news_card(n) for n in importants]) or "<p class='empty'>Aucune actualité importante.</p>"

    # Résumé
    dxy  = market_data.get("DX-Y.NYB",{})
    vix  = market_data.get("^VIX",{})
    dxy_n = "Dollar en repli — favorable aux actifs" if dxy.get("change",0)<0 else "Dollar en hausse — pression sur les actifs"
    vix_n = "Peur en baisse — marchés sereins" if vix.get("change",0)<0 else "Tension visible"
    gold_n = "Valeur refuge recherchée" if market_data.get("GC=F",{}).get("change",0)>1 else ""

    summary_html = "".join([
        sum_line("BTC",    market_data.get("BTC",{})),
        sum_line("ETH",    market_data.get("ETH",{})),
        sum_line("SOL",    market_data.get("SOL",{})),
        sum_line("DXY",    dxy,  dxy_n),
        sum_line("Or",     market_data.get("GC=F",{}), gold_n),
        sum_line("VIX",    vix,  vix_n),
        sum_line("S&P500", market_data.get("^GSPC",{})),
        sum_line("IBIT",   market_data.get("IBIT",{}), "ETF BlackRock · baromètre institutionnel"),
    ])

    # Blocs Groq
    ib_resume = interp_block(interpretations.get("resume",""), "var(--neon)")
    ib_btc    = interp_block(interpretations.get("btc",""),    "var(--green)")
    ib_macro  = interp_block(interpretations.get("macro",""),  "var(--amber)")
    ib_etf    = interp_block(interpretations.get("etf",""),    "var(--purple)")
    hist_html = history_block(tracking, stats, closed)
    opp_html  = opportunity_cards(opportunities)

    nb_crit = len(critiques)
    nb_imp  = len(importants)

    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Doog Intelligent Market — {now.strftime('%d/%m/%Y')}</title>
<style>
:root{{--bg:#0a0c0f;--bg2:#111418;--bg3:#161b22;--bg4:#1c2230;
--border:rgba(255,255,255,0.08);--border2:rgba(255,255,255,0.15);
--text:#e8edf2;--text2:#8b95a3;--text3:#5a6475;
--neon:#00e5ff;--neon2:#7c4dff;--green:#00c896;--red:#ff4d6a;
--amber:#ffb020;--purple:#a78bfa;
--font:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
--mono:'JetBrains Mono','Fira Code','Courier New',monospace;--max:860px}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--text);font-family:var(--font);font-size:18px;line-height:1.55}}
.wrap{{max-width:var(--max);margin:0 auto}}
.header{{background:var(--bg2);border-bottom:1px solid var(--border2);position:sticky;top:0;z-index:100}}
.header-inner{{max-width:var(--max);margin:0 auto;padding:12px 20px 10px}}
.header-top{{display:flex;align-items:center;justify-content:space-between;margin-bottom:10px}}
.logo{{display:flex;align-items:center;gap:10px}}
.logo-mark{{width:34px;height:34px;border-radius:8px;background:linear-gradient(135deg,var(--neon),var(--neon2));display:flex;align-items:center;justify-content:center;font-size:15px;font-weight:800;color:#000}}
.logo-name{{font-size:16px;font-weight:700}}
.logo-tag{{font-size:10px;color:var(--text3);letter-spacing:1.5px;text-transform:uppercase;margin-top:1px}}
.live-pill{{display:inline-flex;align-items:center;gap:5px;background:rgba(0,200,150,0.1);border:1px solid rgba(0,200,150,0.25);border-radius:20px;padding:2px 8px;margin-bottom:4px}}
.live-dot{{width:6px;height:6px;border-radius:50%;background:var(--green);animation:blink 2s infinite}}
@keyframes blink{{0%,100%{{opacity:1}}50%{{opacity:.3}}}}
.live-text{{font-size:10px;color:var(--green)}}
.header-date{{font-size:11px;color:var(--text3);font-family:var(--mono)}}
.nav{{display:flex;gap:4px;overflow-x:auto;scrollbar-width:none;padding-bottom:2px}}
.nav::-webkit-scrollbar{{display:none}}
.nb{{background:none;border:1px solid var(--border);color:var(--text3);font-size:11px;padding:4px 12px;border-radius:20px;cursor:pointer;white-space:nowrap;transition:all .15s;flex-shrink:0;font-family:var(--font)}}
.nb.on{{background:rgba(0,229,255,0.1);border-color:rgba(0,229,255,0.35);color:var(--neon)}}
.neon-rule{{height:1px;background:linear-gradient(90deg,transparent,rgba(0,229,255,.25),transparent)}}
.section{{padding:20px;border-bottom:1px solid var(--border)}}
.slabel{{font-size:9px;letter-spacing:2.5px;text-transform:uppercase;color:var(--text3);margin-bottom:14px;display:flex;align-items:center;gap:10px}}
.slabel::after{{content:'';flex:1;height:1px;background:var(--border)}}
.summary-block{{border-left:2px solid var(--neon);padding-left:14px}}
.summary-line{{font-size:18px;display:flex;gap:8px;align-items:baseline;padding:5px 0;border-bottom:1px solid var(--border)}}
.summary-line:last-child{{border-bottom:none}}
.sum-tick{{font-size:11px;font-weight:700;font-family:var(--mono);color:var(--neon);min-width:52px;flex-shrink:0}}
.sum-val{{font-weight:600}}.sum-note{{color:var(--text3);font-size:12px}}
.up{{color:var(--green)}}.dn{{color:var(--red)}}
.interp-block{{background:var(--bg4);border-left:3px solid var(--neon);border-radius:0 8px 8px 0;padding:13px 15px;margin-bottom:14px}}
.interp-label{{font-size:9px;color:var(--text3);text-transform:uppercase;letter-spacing:1.5px;margin-bottom:7px}}
.interp-text{{font-size:18px;color:var(--text2);line-height:1.75}}
.news-card{{background:var(--bg3);border:1px solid var(--border);border-radius:10px;padding:13px 14px;margin-bottom:10px}}
.nc-top{{display:flex;align-items:flex-start;justify-content:space-between;gap:8px;margin-bottom:7px}}
.badge{{font-size:9px;font-weight:700;letter-spacing:1px;text-transform:uppercase;padding:2px 7px;border-radius:3px;white-space:nowrap}}
.b-crit{{background:rgba(255,77,106,.18);color:var(--red)}}
.b-imp{{background:rgba(255,176,32,.14);color:var(--amber)}}
.nc-meta{{display:flex;align-items:center;gap:8px;flex-wrap:wrap}}
.nc-source{{font-size:10px;color:var(--text3);font-family:var(--mono)}}
.src-link{{font-size:10px;color:var(--neon);text-decoration:none;border-bottom:1px solid rgba(0,229,255,0.3)}}
.nc-title{{font-size:18px;font-weight:600;color:var(--text);margin-bottom:5px;line-height:1.4}}
.nc-body{{font-size:18px;color:var(--text2);line-height:1.6}}
.nc-foot{{display:flex;align-items:center;justify-content:space-between;margin-top:8px}}
.nc-time{{font-size:10px;color:var(--text3);font-family:var(--mono)}}
.nc-age{{font-size:9px;padding:1px 6px;border-radius:3px;background:var(--bg4);color:var(--text3)}}
.mcat{{font-size:10px;color:var(--text3);text-transform:uppercase;letter-spacing:1.5px;margin:16px 0 10px}}
.mcat:first-child{{margin-top:0}}
.mgrid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(155px,1fr));gap:8px}}
.mc{{background:var(--bg3);border:1px solid var(--border);border-radius:8px;padding:11px 13px}}
.mc-name{{font-size:12px;font-weight:700;color:var(--neon);font-family:var(--mono)}}
.mc-label{{font-size:10px;color:var(--text3);margin-bottom:4px}}
.mc-price{{font-size:16px;font-weight:700;font-family:var(--mono);line-height:1.2}}
.mc-row{{display:flex;align-items:center;justify-content:space-between;margin-top:4px}}
.mc-chg{{font-size:12px;font-family:var(--mono);font-weight:600}}
.mbar{{height:2px;background:var(--bg4);border-radius:1px;overflow:hidden;margin-top:7px}}
.mbar-f{{height:100%;border-radius:1px}}
.empty{{color:var(--text3);font-size:12px;font-style:italic}}
.footer{{padding:24px 20px;text-align:center;max-width:var(--max);margin:0 auto}}
.footer-name{{font-size:13px;font-weight:600;color:var(--text2);margin-bottom:4px}}
.footer-src{{font-size:10px;color:var(--text3);margin-bottom:6px}}
.footer-disc{{font-size:10px;color:var(--text3);font-style:italic}}
.stb{{position:fixed;bottom:20px;right:20px;width:38px;height:38px;border-radius:50%;background:var(--bg3);border:1px solid var(--border2);color:var(--text2);font-size:16px;display:flex;align-items:center;justify-content:center;cursor:pointer;opacity:0;transition:opacity .2s;z-index:50}}
.stb.on{{opacity:1}}
@media(max-width:600px){{
:root{{--max:100%}}
body{{font-size:20px;-webkit-text-size-adjust:100%}}
.nc-title{{font-size:20px}}
.nc-body{{font-size:19px}}
.interp-text{{font-size:19px}}
.summary-line{{font-size:19px}}
.mc-price{{font-size:19px}}
.nb{{font-size:14px;padding:6px 16px}}
.section{{padding:14px}}
.mgrid{{grid-template-columns:repeat(auto-fill,minmax(140px,1fr))}}
}}
</style>
</head>
<body>
<div class="header"><div class="header-inner">
  <div class="header-top">
    <div class="logo">
      <div class="logo-mark">D</div>
      <div><div class="logo-name">Doog Intelligent Market</div>
      <div class="logo-tag">Intelligence Financière · v1</div></div>
    </div>
    <div style="text-align:right">
      <div class="live-pill"><span class="live-dot"></span>
      <span class="live-text">Données réelles</span></div>
      <div class="header-date">{date_str}</div>
    </div>
  </div>
  <div class="nav">
    <button class="nb on" onclick="go('s1',this)">Résumé</button>
    <button class="nb" onclick="go('s2',this)">Critique ({nb_crit})</button>
    <button class="nb" onclick="go('s3',this)">Important ({nb_imp})</button>
    <button class="nb" onclick="go('s4',this)">Marchés</button>
  </div>
</div></div>
<div class="neon-rule"></div>
<div class="wrap">

  <div class="section" id="s1">
    <div class="slabel">01 · Résumé exécutif</div>
    {ib_resume}
    <div class="summary-block">{summary_html}</div>
  </div>

  <div class="section" id="s2">
    <div class="slabel">02 · Actualités critiques</div>
    {crit_html}
  </div>

  <div class="section" id="s3">
    <div class="slabel">03 · Actualités importantes</div>
    {imp_html}
  </div>

  <div class="section" id="s4">
    <div class="slabel">04 · Cartographie des marchés</div>
    <div class="mcat">Crypto</div>
    {ib_btc}
    <div class="mgrid">{crypto_cards}</div>
    <div class="mcat">ETF Bitcoin Spot</div>
    {ib_etf}
    <div class="mgrid">{etf_cards}</div>
    <div class="mcat">Macro mondiale</div>
    {ib_macro}
    <div class="mgrid">{macro_cards}</div>
  </div>

  <div class="section" id="s5">
    <div class="slabel">05 · Opportunités du jour</div>
    <div style="font-size:11px;color:var(--text3);margin-bottom:14px;
      line-height:1.6;border-left:2px solid var(--border);padding-left:10px">
      Chaque opportunité nécessite minimum 3 facteurs concordants.
      Le <strong style="color:var(--text2)">R/R</strong> indique le ratio
      Rendement/Risque : "1:3" = pour 1$ risqué, 3$ visés.
      Zéro opportunité = marchés sans signal clair ce jour.
    </div>
    {opp_html}
  </div>

  <div class="section" id="s6">
    <div class="slabel">06 · Suivi des performances</div>
    {hist_html}
  </div>

</div>
<div class="footer">
  <div class="footer-name">Doog Intelligent Market · v1</div>
  <div class="footer-src">Sources : CoinGecko · Yahoo Finance · TheBlock · CoinTelegraph · Federal Reserve · BCE</div>
  <div class="footer-disc">Rapport généré le {date_str} · Usage personnel · Pas un conseil en investissement</div>
</div>
<div class="stb" id="stb" onclick="window.scrollTo({{top:0,behavior:'smooth'}})">↑</div>
<script>
function go(id,btn){{
  const el=document.getElementById(id);if(!el)return;
  const hh=document.querySelector('.header').offsetHeight+10;
  window.scrollTo({{top:el.getBoundingClientRect().top+scrollY-hh,behavior:'smooth'}});
  document.querySelectorAll('.nb').forEach(b=>b.classList.remove('on'));
  btn.classList.add('on');
}}
window.addEventListener('scroll',()=>{{
  document.getElementById('stb').classList.toggle('on',scrollY>300);
  const hh=document.querySelector('.header').offsetHeight+30;
  const ids=['s1','s2','s3','s5','s4','s6'];
  const btns=document.querySelectorAll('.nb');
  let cur=0;
  ids.forEach((id,i)=>{{
    const el=document.getElementById(id);
    if(el&&el.getBoundingClientRect().top<=hh)cur=i;
  }});
  btns.forEach((b,i)=>b.classList.toggle('on',i===cur));
}});
</script>
</body></html>"""

    filename = f"rapport_{now.strftime('%Y-%m-%d')}.html"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(html)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO reports (report_date, html, created_at) VALUES (?,?,?)",
                 (now.strftime("%Y-%m-%d"), html, now.isoformat()))
    conn.commit()
    conn.close()
    log(f"✓ Rapport sauvegardé : {filename}")
    return filename

# ══════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════
def main():
    run_collectors()
    market_data     = get_market_data()
    news_items      = get_news()
    interpretations = generate_interpretations(market_data, news_items)
    filename        = generate_report(market_data, news_items, interpretations)
    log(f"✓ Ouvre dans le navigateur : {filename}")
    os.system(f"open {filename}")

if __name__ == "__main__":
    main()
