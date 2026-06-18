"""
update_races_data.py
Scarica classifiche piloti/costruttori e sessioni dall'API OpenF1 (gratuita,
senza chiavi) e aggiorna races-data.json mantenendo gli orari TV hardcoded.

OpenF1 API: https://openf1.org  — nessun copyright, dati open source.
"""

import json
import requests
from datetime import datetime, timezone
from pathlib import Path

BASE = "https://api.openf1.org/v1"
YEAR = 2026
JSON_PATH = Path("races-data.json")

# ── Mappa nomi paese OpenF1 → id GP usato nel tuo JSON ──────────────────────
COUNTRY_TO_ID = {
    "Austria":        "austria",
    "United Kingdom": "gran-bretagna",
    "Belgium":        "belgio",
    "Hungary":        "ungheria",
    "Netherlands":    "olanda",
    "Italy":          "italia",
    "Azerbaijan":     "azerbaijan",
    "Singapore":      "singapore",
    "United States":  "usa",
    "Mexico":         "messico",
    "Brazil":         "brasile",
    "Qatar":          "qatar",
    "Abu Dhabi":      "abu-dhabi",
}

def get(endpoint, params=None):
    r = requests.get(f"{BASE}/{endpoint}", params=params, timeout=20)
    r.raise_for_status()
    return r.json()

# ── 1. Classifiche piloti ────────────────────────────────────────────────────
def fetch_driver_standings():
    """
    Prende le classifiche dall'ultima sessione Race disponibile per il 2026.
    endpoint: /championship_drivers
    """
    # Trova le sessioni Race del 2026
    sessions = get("sessions", {"year": YEAR, "session_type": "Race"})
    if not sessions:
        print("  Nessuna sessione Race trovata per il 2026")
        return None

    # Prende l'ultima (la più recente)
    latest = sorted(sessions, key=lambda s: s.get("date_start",""))[-1]
    sk = latest["session_key"]
    country = latest.get("country_name","")
    print(f"  Ultima gara: {country} (session_key={sk})")

    data = get("championship_drivers", {"session_key": sk})
    if not data:
        return None

    standings = []
    for i, d in enumerate(sorted(data, key=lambda x: x.get("points",0), reverse=True), 1):
        standings.append({
            "pos":  i,
            "name": f"{d.get('first_name','')} {d.get('last_name','')}".strip(),
            "team": d.get("team_name", ""),
            "pts":  int(d.get("points", 0))
        })
    return standings

# ── 2. Classifiche costruttori ───────────────────────────────────────────────
def fetch_constructor_standings():
    sessions = get("sessions", {"year": YEAR, "session_type": "Race"})
    if not sessions:
        return None

    latest = sorted(sessions, key=lambda s: s.get("date_start",""))[-1]
    sk = latest["session_key"]

    data = get("championship_teams", {"session_key": sk})
    if not data:
        return None

    standings = []
    for i, t in enumerate(sorted(data, key=lambda x: x.get("points",0), reverse=True), 1):
        standings.append({
            "pos":  i,
            "name": t.get("team_name",""),
            "team": "",   # verrà lasciato vuoto (OpenF1 non fornisce i piloti qui)
            "pts":  int(t.get("points", 0))
        })
    return standings

# ── 3. Segna GP come "done" nel calendario ───────────────────────────────────
def mark_done_races(season):
    """
    Confronta la data attuale con le date nel calendario e segna done=True
    per i GP già corsi. Non dipende da OpenF1, basta la data di sistema.
    """
    now = datetime.now(timezone.utc)
    for r in season:
        # Cerca la data ISO nelle races se disponibile
        # (il campo 'done' viene gestito dinamicamente nell'app, ma lo aggiorniamo
        #  anche qui per coerenza)
        r.pop("next", None)  # rimuove il flag 'next' statico, l'app lo calcola
    return season

# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    # Carica il JSON esistente (mantiene gli orari TV hardcoded)
    if JSON_PATH.exists():
        with open(JSON_PATH, encoding="utf-8") as f:
            data = json.load(f)
        print("✅ JSON esistente caricato")
    else:
        print("⚠️  races-data.json non trovato, verrà creato da zero (senza orari TV)")
        data = {"races": [], "season": [], "standings": {"drivers": [], "constructors": []}}

    # Classifiche piloti
    print("📡 Scarico classifiche piloti...")
    try:
        drivers = fetch_driver_standings()
        if drivers:
            data["standings"]["drivers"] = drivers
            print(f"  ✅ {len(drivers)} piloti aggiornati")
        else:
            print("  ⚠️  Nessun dato piloti, classifiche invariate")
    except Exception as e:
        print(f"  ❌ Errore piloti: {e}")

    # Classifiche costruttori
    print("📡 Scarico classifiche costruttori...")
    try:
        constructors = fetch_constructor_standings()
        if constructors:
            data["standings"]["constructors"] = constructors
            print(f"  ✅ {len(constructors)} costruttori aggiornati")
        else:
            print("  ⚠️  Nessun dato costruttori, classifiche invariate")
    except Exception as e:
        print(f"  ❌ Errore costruttori: {e}")

    # Aggiorna timestamp
    data["lastUpdated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Salva
    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n✅ races-data.json aggiornato — {data['lastUpdated']}")

if __name__ == "__main__":
    main()
