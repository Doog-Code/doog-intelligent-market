import os
import sys
import sqlite3
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DB_PATH = "database/market_terminal.db"

def save_opportunity(opp):
    """Sauvegarde une opportunité générée en base."""
    conn = sqlite3.connect(DB_PATH)

    # Vérifie si une opportunité identique existe déjà aujourd'hui
    today = datetime.now().strftime("%Y-%m-%d")
    existing = conn.execute("""
        SELECT id FROM opportunities
        WHERE asset = ? AND date(created_at) = ?
    """, (opp["asset"], today)).fetchone()

    if existing:
        conn.close()
        print(f"    — Opportunité {opp['asset']} déjà en base pour aujourd'hui")
        return existing[0]

    import json
    conn.execute("""
        INSERT INTO opportunities
        (asset, thesis, entry, stop, target, rr, horizon, score, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        opp["asset"],
        opp["these"],
        opp["entree"],
        opp["stop"],
        opp["objectif"],
        str(opp["rr"]),
        opp["horizon"],
        opp["score"],
        opp["created_at"]
    ))
    conn.commit()
    opp_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    print(f"    ✓ Opportunité {opp['asset']} sauvegardée (id={opp_id})")
    return opp_id

def get_current_price(asset):
    """Récupère le prix actuel depuis la base."""
    conn = sqlite3.connect(DB_PATH)
    row  = conn.execute("""
        SELECT price FROM market_data
        WHERE asset = ?
        ORDER BY timestamp DESC LIMIT 1
    """, (asset,)).fetchone()
    conn.close()
    return row[0] if row else None

def parse_horizon_days(horizon_str):
    """Convertit '7-14 jours' en nombre de jours max."""
    import re
    numbers = re.findall(r'\d+', horizon_str)
    if numbers:
        return int(numbers[-1])  # Prend le max
    return 14  # Défaut

def evaluate_opportunity(opp_id, asset, entry, stop, target, horizon_str, created_at):
    """Évalue une opportunité ouverte — retourne un dict résultat ou None."""
    current_price = get_current_price(asset)
    if not current_price:
        return None

    created   = datetime.fromisoformat(created_at)
    now       = datetime.now()
    days_open = (now - created).days
    max_days  = parse_horizon_days(horizon_str)

    # Calculs
    pnl_pct    = ((current_price - entry) / entry) * 100
    risk       = abs(entry - stop)
    reward     = abs(target - entry)
    rr         = round(reward / risk, 1) if risk > 0 else 0

    result     = None
    score      = None
    comment    = None

    # Stop touché
    if current_price <= stop:
        result  = "STOP"
        score   = 3.0
        comment = f"Stop touché à ${current_price:,.2f} ({pnl_pct:+.1f}%)"

    # Objectif atteint
    elif current_price >= target:
        result  = "OBJECTIF"
        score   = 9.0
        comment = f"Objectif atteint à ${current_price:,.2f} ({pnl_pct:+.1f}%)"

    # Horizon dépassé
    elif days_open >= max_days:
        if pnl_pct > 5:
            score   = 7.0
            result  = "EXPIRE_POSITIF"
            comment = f"Horizon dépassé — position positive ({pnl_pct:+.1f}%)"
        elif pnl_pct > 0:
            score   = 5.5
            result  = "EXPIRE_NEUTRE"
            comment = f"Horizon dépassé — léger gain ({pnl_pct:+.1f}%)"
        else:
            score   = 4.0
            result  = "EXPIRE_NEGATIF"
            comment = f"Horizon dépassé — en perte ({pnl_pct:+.1f}%)"

    # Encore ouverte
    else:
        return {
            "status":        "OUVERTE",
            "asset":         asset,
            "entry":         entry,
            "current":       current_price,
            "pnl_pct":       pnl_pct,
            "days_open":     days_open,
            "max_days":      max_days,
            "stop":          stop,
            "target":        target,
        }

    return {
        "status":    result,
        "asset":     asset,
        "entry":     entry,
        "current":   current_price,
        "pnl_pct":   pnl_pct,
        "days_open": days_open,
        "score":     score,
        "comment":   comment
    }

def save_evaluation(opp_id, score, result, comment):
    """Sauvegarde l'évaluation finale en base."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO evaluations (opportunity_id, score, result, comment, evaluated_at)
        VALUES (?, ?, ?, ?, ?)
    """, (opp_id, score, result, comment, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_open_opportunities():
    """Récupère toutes les opportunités sans évaluation finale."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT o.id, o.asset, o.entry, o.stop, o.target,
               o.horizon, o.created_at, o.thesis, o.rr, o.score
        FROM opportunities o
        LEFT JOIN evaluations e ON e.opportunity_id = o.id
            AND e.result NOT IN ('OUVERTE')
        WHERE e.id IS NULL
        ORDER BY o.created_at DESC
    """).fetchall()
    conn.close()
    return rows

def get_closed_opportunities(limit=10):
    """Récupère les opportunités clôturées avec leur évaluation."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT o.asset, o.entry, o.target, o.stop, o.rr,
               o.thesis, o.horizon, o.created_at,
               e.score, e.result, e.comment, e.evaluated_at
        FROM opportunities o
        JOIN evaluations e ON e.opportunity_id = o.id
        WHERE e.result != 'OUVERTE'
        ORDER BY e.evaluated_at DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return rows

def get_stats():
    """Calcule les statistiques globales du tracker."""
    conn = sqlite3.connect(DB_PATH)

    total = conn.execute("SELECT COUNT(*) FROM opportunities").fetchone()[0]
    closed = conn.execute("""
        SELECT COUNT(*) FROM evaluations WHERE result != 'OUVERTE'
    """).fetchone()[0]
    avg_score = conn.execute("""
        SELECT AVG(score) FROM evaluations WHERE result != 'OUVERTE'
    """).fetchone()[0]
    wins = conn.execute("""
        SELECT COUNT(*) FROM evaluations
        WHERE result IN ('OBJECTIF','EXPIRE_POSITIF')
    """).fetchone()[0]

    conn.close()

    win_rate = round(wins / closed * 100) if closed > 0 else 0
    return {
        "total":     total,
        "closed":    closed,
        "avg_score": round(avg_score, 1) if avg_score else 0,
        "win_rate":  win_rate,
        "wins":      wins
    }

def run_tracker():
    """Lance le tracker — évalue toutes les opportunités ouvertes."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Tracker — vérification opportunités...")

    open_opps = get_open_opportunities()
    print(f"  → {len(open_opps)} opportunité(s) ouverte(s) à vérifier")

    results = []
    for row in open_opps:
        opp_id, asset, entry, stop, target, horizon, created_at, thesis, rr, score = row
        evaluation = evaluate_opportunity(
            opp_id, asset, entry, stop, target, horizon, created_at
        )
        if not evaluation:
            continue

        status = evaluation["status"]
        print(f"  → {asset} : {status} ({evaluation.get('pnl_pct',0):+.1f}%)")

        if status != "OUVERTE":
            save_evaluation(
                opp_id,
                evaluation["score"],
                status,
                evaluation["comment"]
            )

        results.append({**evaluation, "thesis": thesis, "rr": rr,
                        "score_facteurs": score, "horizon": horizon,
                        "created_at": created_at})

    stats = get_stats()
    print(f"  ✓ Stats : {stats['closed']} clôturées · {stats['win_rate']}% succès · score moy. {stats['avg_score']}")
    return results, stats

if __name__ == "__main__":
    results, stats = run_tracker()
    print(f"\nStats globales : {stats}")
