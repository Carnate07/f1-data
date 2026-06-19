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
# NB: gli Stati Uniti hanno 3 GP (Miami, Austin, Las Vegas) quindi il country
# da solo non basta: serve anche il nome del circuito per distinguerli.
COUNTRY_TO_ID = {
    "Austria":        "austria",
    "United Kingdom": "gran-bretagna",
    "Belgium":        "belgio",
    "Hungary":        "ungheria",
    "Netherlands":    "olanda",
    "Italy":          "italia",
    "Azerbaijan":     "azerbaijan",
    "Singapore":      "singapore",
    "Mexico":         "messico",
    "Brazil":         "brasile",
    "Qatar":          "qatar",
    "Abu Dhabi":      "abu-dhabi",
}

# Per i meeting USA (3 GP diversi) si usa il nome del circuito
US_CIRCUIT_TO_ID = {
    "Miami International Autodrome": "miami",
    "Circuit of the Americas":       "usa",
    "Las Vegas Strip Circuit":       "las-vegas",
}

# Nomi italiani ufficiali per ogni GP, usati al posto del meeting_name inglese
# restituito da OpenF1 (es. "Dutch Grand Prix" → "GP Olanda")
ITALIAN_NAMES = {
    "austria":       "GP Austria",
    "gran-bretagna": "GP Gran Bretagna",
    "belgio":        "GP Belgio",
    "ungheria":      "GP Ungheria",
    "olanda":        "GP Olanda",
    "italia":        "GP Italia",
    "azerbaijan":    "GP Azerbaijan",
    "singapore":     "GP Singapore",
    "miami":         "GP Miami",
    "usa":           "GP USA",
    "messico":       "GP Messico",
    "brasile":       "GP Brasile",
    "las-vegas":     "GP Las Vegas",
    "qatar":         "GP Qatar",
    "abu-dhabi":     "GP Abu Dhabi",
}

def resolve_gp_id(country, circuit_short_name):
    """Determina l'id del GP, gestendo il caso speciale degli USA."""
    if country == "United States":
        return US_CIRCUIT_TO_ID.get(circuit_short_name)
    return COUNTRY_TO_ID.get(country)

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
    sessions = get("sessions", {"year": YEAR, "session_name": "Race"})
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
    sessions = get("sessions", {"year": YEAR, "session_name": "Race"})
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

# ── 3. Aggiorna sessioni e date dei GP ──────────────────────────────────────
SESSION_NAME_MAP = {
    "Practice 1":        "Prove Libere 1",
    "Practice 2":        "Prove Libere 2",
    "Practice 3":        "Prove Libere 3",
    "Qualifying":        "Qualifiche",
    "Sprint":            "Sprint Race",
    "Sprint Qualifying": "Qualifiche Sprint",
    "Race":              "Gara",
}
DAY_IT = {0:"LUN",1:"MAR",2:"MER",3:"GIO",4:"VEN",5:"SAB",6:"DOM"}
MONTHS_IT = ["","Gen","Feb","Mar","Apr","Mag","Giu","Lug","Ago","Set","Ott","Nov","Dic"]

# GP con TV8 in DIRETTA (non differita)
TV8_DIRETTA = {"italia", "abu-dhabi"}

# Orari approssimativi differita TV8 per tipo sessione
# (offset in ore rispetto all'orario della sessione)
TV8_DIFFERITA_OFFSET = {
    "Qualifying":        3,   # qualifiche → differita ~3h dopo
    "Sprint Qualifying": 2,
    "Sprint":            2,
    "Race":              3,
}

def default_channels(session_type, gp_id="", session_time=""):
    """
    Canali TV italiani intelligenti per tipo sessione.
    - Monza e Abu Dhabi: TV8 in diretta per la gara
    - Sprint weekend: TV8 anche per Sprint e Qualifiche Sprint
    - Differita: orario approssimativo calcolato
    """
    is_diretta_gp = gp_id in TV8_DIRETTA

    # Calcola orario differita TV8
    def differita_time(stype):
        if not session_time:
            return "differita"
        try:
            h, m = map(int, session_time.split(":"))
            offset = TV8_DIFFERITA_OFFSET.get(stype, 3)
            total = (h + offset) % 24
            return f"differita {total:02d}:00"
        except Exception:
            return "differita"

    if session_type == "Race":
        if is_diretta_gp:
            return [
                {"name": "Sky Sport F1 / Uno", "type": "pay"},
                {"name": "TV8 DIRETTA",         "type": "free"}
            ]
        return [
            {"name": "Sky Sport F1 / Uno",                       "type": "pay"},
            {"name": f"TV8 ({differita_time('Race')})",           "type": "free"}
        ]

    if session_type == "Qualifying":
        return [
            {"name": "Sky Sport F1 / Uno",                            "type": "pay"},
            {"name": f"TV8 ({differita_time('Qualifying')})",          "type": "free"}
        ]

    if session_type == "Sprint":
        return [
            {"name": "Sky Sport F1 / Uno",                       "type": "pay"},
            {"name": f"TV8 ({differita_time('Sprint')})",         "type": "free"}
        ]

    if session_type == "Sprint Qualifying":
        return [
            {"name": "Sky Sport F1 / Uno",                                "type": "pay"},
            {"name": f"TV8 ({differita_time('Sprint Qualifying')})",       "type": "free"}
        ]

    # Prove libere → solo Sky
    return [{"name": "Sky Sport F1", "type": "pay"}]

def fetch_races(existing_races):
    """
    Scarica meeting e sessioni 2026 da OpenF1.
    Mantiene i canali TV già presenti nel JSON esistente.
    """
    meetings = get("meetings", {"year": YEAR})
    if not meetings:
        print("  Nessun meeting trovato su OpenF1")
        return existing_races

    # Indice rapido per id
    existing_map = {r["id"]: r for r in existing_races}
    updated = []

    for m in sorted(meetings, key=lambda x: x.get("date_start", "")):
        country = m.get("country_name", "")
        circuit = m.get("circuit_short_name", "")
        gp_id   = resolve_gp_id(country, circuit)
        if not gp_id:
            continue  # GP non riconosciuto o già corso — salta

        # Sessioni del meeting ordinate per data
        sessions_raw = get("sessions", {"meeting_key": m["meeting_key"], "year": YEAR})
        sessions_raw = sorted(sessions_raw, key=lambda s: s.get("date_start", ""))

        # Data ISO della gara
        race_session = next((s for s in sessions_raw if s.get("session_name") == "Race"), None)
        race_iso     = race_session["date_start"] if race_session else m.get("date_start", "")

        # Stringa date weekend (es. "27–29 Giu")
        if sessions_raw:
            d0 = datetime.fromisoformat(sessions_raw[0]["date_start"])
            d1 = datetime.fromisoformat(sessions_raw[-1]["date_start"])
            if d0.month == d1.month:
                dates_str = f"{d0.day}–{d1.day} {MONTHS_IT[d0.month]}"
            else:
                dates_str = f"{d0.day} {MONTHS_IT[d0.month]}–{d1.day} {MONTHS_IT[d1.month]}"
        else:
            dates_str = existing_map.get(gp_id, {}).get("dates", "")

        # Indice sessioni esistenti per nome → per preservare i canali TV
        existing_sessions_map = {
            s["name"]: s
            for s in existing_map.get(gp_id, {}).get("sessions", [])
        }

        new_sessions = []
        for s in sessions_raw:
            stype = s.get("session_name", "")
            sname = SESSION_NAME_MAP.get(stype, stype)
            dt    = datetime.fromisoformat(s["date_start"])
            sess  = {
                "day":      DAY_IT[dt.weekday()],
                "date":     str(dt.day),
                "name":     sname,
                "time":     dt.strftime("%H:%M"),
                # Usa canali TV già configurati, altrimenti default
                "channels": existing_sessions_map.get(sname, {}).get("channels")
                            or default_channels(stype, gp_id, dt.strftime("%H:%M")),
            }
            if stype == "Race":
                sess["isRace"] = True
            new_sessions.append(sess)

        gp = existing_map.get(gp_id, {}).copy()
        gp.update({
            "id":              gp_id,
            "name":            ITALIAN_NAMES.get(gp_id, gp.get("name", m.get("meeting_name",""))),
            "track":           m.get("circuit_short_name", gp.get("track", "")),
            "dates":           dates_str,
            "raceDateTimeISO": race_iso,
            "sessions":        new_sessions if new_sessions else gp.get("sessions", []),
        })
        updated.append(gp)
        print(f"  ✅ {gp['name']} — {len(new_sessions)} sessioni")

    # Mantieni GP non ancora su OpenF1 (senza meeting_key)
    ids_updated = {r["id"] for r in updated}
    for r in existing_races:
        if r["id"] not in ids_updated:
            updated.append(r)

    updated.sort(key=lambda r: r.get("raceDateTimeISO", ""))
    return updated

# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    if JSON_PATH.exists():
        with open(JSON_PATH, encoding="utf-8") as f:
            data = json.load(f)
        print("✅ JSON esistente caricato")
    else:
        print("⚠️  races-data.json non trovato, verrà creato da zero")
        data = {"races": [], "season": [], "standings": {"drivers": [], "constructors": []}}

    # Sessioni e date GP
    print("📡 Scarico sessioni GP...")
    try:
        races = fetch_races(data.get("races", []))
        if races:
            data["races"] = races
            print(f"  ✅ {len(races)} GP aggiornati")
        else:
            print("  ⚠️  Nessun dato GP, races invariate")
    except Exception as e:
        print(f"  ❌ Errore races: {e}")

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

    # Timestamp
    data["lastUpdated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n✅ races-data.json aggiornato — {data['lastUpdated']}")

if __name__ == "__main__":
    main()
