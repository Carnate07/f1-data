"""
update_races_data.py
Scarica classifiche piloti/costruttori e sessioni dall'API OpenF1 (gratuita,
senza chiavi) e aggiorna races-data.json mantenendo gli orari TV hardcoded.

OpenF1 API: https://openf1.org — nessun copyright, dati open source.

REGOLA D'ORO: ogni GP ha un id FISSO e UNIVOCO definito qui sotto in
RACE_CALENDAR_2026. Lo script non genera MAI un id nuovo al volo: se non
trova corrispondenza in RACE_CALENDAR_2026, scarta il meeting (lo ignora)
invece di crearne uno improvvisato. Questo evita per costruzione i
duplicati/id-incoerenti che si erano accumulati nelle versioni precedenti
(es. "usa" riusato 3 volte, "gran-bretagna" vs "gran_bretagna", ecc).
"""

import json
import requests
from datetime import datetime, timezone
from pathlib import Path

BASE = "https://api.openf1.org/v1"
YEAR = 2026
JSON_PATH = Path("races-data.json")

# ── Calendario fisso 2026 — 22 GP, id univoci, MAI generati dinamicamente ──
# country_name: come restituito da OpenF1 (campo "country_name" del meeting)
# circuit_keys: sottostringhe (lowercase) di circuit_short_name/location utili
#               a distinguere GP con lo stesso country_name (vedi USA)
RACE_CALENDAR_2026 = [
    {"id": "australia",      "name": "GP Australia",      "country": "Australia"},
    {"id": "cina",            "name": "GP Cina",           "country": "China"},
    {"id": "giappone",        "name": "GP Giappone",       "country": "Japan"},
    {"id": "miami",           "name": "GP Miami",          "country": "United States", "circuit_keys": ["miami"]},
    {"id": "canada",          "name": "GP Canada",         "country": "Canada"},
    {"id": "monaco",          "name": "GP Monaco",         "country": "Monaco"},
    {"id": "catalunya",       "name": "GP Catalunya",      "country": "Spain", "circuit_keys": ["catalunya", "barcelona"]},
    {"id": "austria",         "name": "GP Austria",        "country": "Austria"},
    {"id": "gran-bretagna",   "name": "GP Gran Bretagna",  "country": "United Kingdom"},
    {"id": "belgio",          "name": "GP Belgio",         "country": "Belgium"},
    {"id": "ungheria",        "name": "GP Ungheria",       "country": "Hungary"},
    {"id": "olanda",          "name": "GP Olanda",         "country": "Netherlands"},
    {"id": "italia",          "name": "GP Italia",         "country": "Italy"},
    {"id": "spagna",          "name": "GP Spagna",         "country": "Spain", "circuit_keys": ["madrid"]},
    {"id": "azerbaijan",      "name": "GP Azerbaijan",     "country": "Azerbaijan"},
    {"id": "singapore",       "name": "GP Singapore",      "country": "Singapore"},
    {"id": "usa",             "name": "GP Austin",         "country": "United States", "circuit_keys": ["americas", "austin"]},
    {"id": "messico",         "name": "GP Messico",        "country": "Mexico"},
    {"id": "brasile",         "name": "GP Brasile",        "country": "Brazil"},
    {"id": "las-vegas",       "name": "GP Las Vegas",      "country": "United States", "circuit_keys": ["vegas", "las vegas"]},
    {"id": "qatar",           "name": "GP Qatar",          "country": "Qatar"},
    {"id": "abu-dhabi",       "name": "GP Abu Dhabi",      "country": "United Arab Emirates"},
]

# Id validi: qualsiasi altro id trovato nel JSON esistente viene scartato
# (rimuove i duplicati storici come gran_bretagna, las_vegas, madrid, abu_dhabi)
VALID_IDS = {gp["id"] for gp in RACE_CALENDAR_2026}

# Indice rapido nome→record calendario
ITALIAN_NAMES = {gp["id"]: gp["name"] for gp in RACE_CALENDAR_2026}


def resolve_gp_id(country, circuit_short_name, location=""):
    """
    Determina l'id fisso del GP confrontando country_name (e, per i paesi
    con piu' GP nello stesso anno: USA e Spagna, anche circuit_keys) con
    RACE_CALENDAR_2026. Ritorna None se non trova nessuna corrispondenza
    sicura — il meeting viene scartato invece di generare un id nuovo.
    """
    haystack = f"{circuit_short_name} {location}".lower()
    candidates = [gp for gp in RACE_CALENDAR_2026 if gp["country"] == country]

    if not candidates:
        return None
    if len(candidates) == 1 and "circuit_keys" not in candidates[0]:
        return candidates[0]["id"]

    # Paese con più GP (USA, Spagna): serve circuit_keys per disambiguare
    for gp in candidates:
        keys = gp.get("circuit_keys", [])
        if any(k in haystack for k in keys):
            return gp["id"]

    return None  # nessuna corrispondenza sicura -> scarta, non improvvisare


def get(endpoint, params=None):
    r = requests.get(f"{BASE}/{endpoint}", params=params, timeout=20)
    r.raise_for_status()
    return r.json()


# ── 1. Classifiche piloti ──────────────────────────────────────────────────
def fetch_driver_standings():
    sessions = get("sessions", {"year": YEAR, "session_name": "Race"})
    if not sessions:
        print("  Nessuna sessione Race trovata per il 2026")
        return None

    latest = sorted(sessions, key=lambda s: s.get("date_start", ""))[-1]
    sk = latest["session_key"]
    country = latest.get("country_name", "")
    print(f"  Ultima gara: {country} (session_key={sk})")

    data = get("championship_drivers", {"session_key": sk})
    if not data:
        return None

    standings = []
    for i, d in enumerate(sorted(data, key=lambda x: x.get("points", 0), reverse=True), 1):
        standings.append({
            "pos": i,
            "name": f"{d.get('first_name','')} {d.get('last_name','')}".strip(),
            "team": d.get("team_name", ""),
            "pts": int(d.get("points", 0)),
        })
    return standings


# ── 2. Classifiche costruttori ─────────────────────────────────────────────
def fetch_constructor_standings():
    sessions = get("sessions", {"year": YEAR, "session_name": "Race"})
    if not sessions:
        return None

    latest = sorted(sessions, key=lambda s: s.get("date_start", ""))[-1]
    sk = latest["session_key"]

    data = get("championship_teams", {"session_key": sk})
    if not data:
        return None

    standings = []
    for i, t in enumerate(sorted(data, key=lambda x: x.get("points", 0), reverse=True), 1):
        standings.append({
            "pos": i,
            "name": t.get("team_name", ""),
            "team": "",
            "pts": int(t.get("points", 0)),
        })
    return standings


# ── 3. Aggiorna sessioni e date dei GP ─────────────────────────────────────
SESSION_NAME_MAP = {
    "Practice 1":        "Prove Libere 1",
    "Practice 2":        "Prove Libere 2",
    "Practice 3":        "Prove Libere 3",
    "Qualifying":        "Qualifiche",
    "Sprint":            "Sprint Race",
    "Sprint Qualifying": "Qualifiche Sprint",
    "Race":              "Gara",
}
DAY_IT = {0: "LUN", 1: "MAR", 2: "MER", 3: "GIO", 4: "VEN", 5: "SAB", 6: "DOM"}
MONTHS_IT = ["", "Gen", "Feb", "Mar", "Apr", "Mag", "Giu", "Lug", "Ago", "Set", "Ott", "Nov", "Dic"]

# GP con TV8 in DIRETTA (non differita)
TV8_DIRETTA = {"italia", "abu-dhabi"}

TV8_DIFFERITA_OFFSET = {
    "Qualifying":        3,
    "Sprint Qualifying": 2,
    "Sprint":            2,
    "Race":              3,
}


def default_channels(session_type, gp_id="", session_time=""):
    is_diretta_gp = gp_id in TV8_DIRETTA

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
                {"name": "TV8 DIRETTA",          "type": "free"},
            ]
        return [
            {"name": "Sky Sport F1 / Uno",                 "type": "pay"},
            {"name": f"TV8 ({differita_time('Race')})",     "type": "free"},
        ]

    if session_type == "Qualifying":
        return [
            {"name": "Sky Sport F1 / Uno",                       "type": "pay"},
            {"name": f"TV8 ({differita_time('Qualifying')})",     "type": "free"},
        ]

    if session_type == "Sprint":
        return [
            {"name": "Sky Sport F1 / Uno",                 "type": "pay"},
            {"name": f"TV8 ({differita_time('Sprint')})",   "type": "free"},
        ]

    if session_type == "Sprint Qualifying":
        return [
            {"name": "Sky Sport F1 / Uno",                          "type": "pay"},
            {"name": f"TV8 ({differita_time('Sprint Qualifying')})", "type": "free"},
        ]

    return [{"name": "Sky Sport F1", "type": "pay"}]


def fetch_races(existing_races):
    """
    Scarica meeting e sessioni 2026 da OpenF1 e fa un UPSERT per id fisso:
    - se il GP esiste già in existing_races, viene sovrascritto in place
      (stessa posizione, stesso id) — mai duplicato in append.
    - i GP con id non più valido (residui di bug passati) vengono scartati.
    - i GP del calendario fisso non ancora trovati su OpenF1 restano come
      erano (di solito perché troppo lontani nel tempo per essere già
      pubblicati dall'API).
    """
    meetings = get("meetings", {"year": YEAR})
    if not meetings:
        print("  Nessun meeting trovato su OpenF1")
        return [r for r in existing_races if r.get("id") in VALID_IDS]

    # Mappa id -> GP esistente, scartando id non più validi (pulizia bug storici)
    invalid_ids = [r.get("id") for r in existing_races if r.get("id") not in VALID_IDS]
    if invalid_ids:
        print(f"  🧹 Rimossi id non validi/duplicati storici: {invalid_ids}")

    valid_races = [r for r in existing_races if r.get("id") in VALID_IDS]

    # Se più record condividono lo stesso id valido (bug storico: "usa" usato
    # per Miami/Austin/Las Vegas), tiene solo quello con più sessioni note
    # (più probabile sia il dato corretto/completo) e scarta gli altri.
    existing_map = {}
    id_duplicate_scartati = []
    for r in valid_races:
        rid = r["id"]
        if rid not in existing_map:
            existing_map[rid] = r
        else:
            # mantiene il record con più sessioni; se pari, mantiene il primo
            if len(r.get("sessions", [])) > len(existing_map[rid].get("sessions", [])):
                id_duplicate_scartati.append(existing_map[rid].get("name"))
                existing_map[rid] = r
            else:
                id_duplicate_scartati.append(r.get("name"))
    if id_duplicate_scartati:
        print(f"  🧹 Rimossi doppioni con id riusato (stesso id, record diversi): {id_duplicate_scartati}")

    updated_map = {}  # id -> gp aggiornato, popolato in ordine di RACE_CALENDAR_2026

    for m in meetings:
        country = m.get("country_name", "")
        circuit = m.get("circuit_short_name", "")
        location = m.get("location", "")
        gp_id = resolve_gp_id(country, circuit, location)
        if not gp_id:
            continue  # meeting non riconosciuto nel calendario fisso -> scartato

        sessions_raw = get("sessions", {"meeting_key": m["meeting_key"], "year": YEAR})
        sessions_raw = sorted(sessions_raw, key=lambda s: s.get("date_start", ""))

        race_session = next((s for s in sessions_raw if s.get("session_name") == "Race"), None)
        race_iso = race_session["date_start"] if race_session else m.get("date_start", "")

        if sessions_raw:
            d0 = datetime.fromisoformat(sessions_raw[0]["date_start"])
            d1 = datetime.fromisoformat(sessions_raw[-1]["date_start"])
            if d0.month == d1.month:
                dates_str = f"{d0.day}–{d1.day} {MONTHS_IT[d0.month]}"
            else:
                dates_str = f"{d0.day} {MONTHS_IT[d0.month]}–{d1.day} {MONTHS_IT[d1.month]}"
        else:
            dates_str = existing_map.get(gp_id, {}).get("dates", "")

        existing_sessions_map = {
            s["name"]: s for s in existing_map.get(gp_id, {}).get("sessions", [])
        }

        new_sessions = []
        for s in sessions_raw:
            stype = s.get("session_name", "")
            sname = SESSION_NAME_MAP.get(stype, stype)
            dt = datetime.fromisoformat(s["date_start"])
            sess = {
                "day":      DAY_IT[dt.weekday()],
                "date":     str(dt.day),
                "name":     sname,
                "time":     dt.strftime("%H:%M"),
                "channels": existing_sessions_map.get(sname, {}).get("channels")
                            or default_channels(stype, gp_id, dt.strftime("%H:%M")),
            }
            if stype == "Race":
                sess["isRace"] = True
            new_sessions.append(sess)

        gp = existing_map.get(gp_id, {}).copy()
        gp.update({
            "id":              gp_id,
            "name":            ITALIAN_NAMES.get(gp_id, gp.get("name", "")),
            "track":           m.get("circuit_short_name", gp.get("track", "")),
            "dates":           dates_str,
            "raceDateTimeISO": race_iso,
            "sessions":        new_sessions if new_sessions else gp.get("sessions", []),
        })
        # Upsert: sovrascrive sempre per id, non aggiunge mai un secondo
        # elemento con lo stesso id (a differenza dell'append usato prima)
        updated_map[gp_id] = gp
        print(f"  ✅ {gp['name']} — {len(new_sessions)} sessioni")

    # GP del calendario fisso non aggiornati in questo run: restano com'erano
    for gp_id, gp_existing in existing_map.items():
        if gp_id not in updated_map:
            updated_map[gp_id] = gp_existing

    # Ordina secondo l'ordine ufficiale di RACE_CALENDAR_2026 (non per data,
    # per evitare scivoloni se raceDateTimeISO è ancora mancante/sbagliato)
    order = {gp["id"]: i for i, gp in enumerate(RACE_CALENDAR_2026)}
    result = sorted(updated_map.values(), key=lambda r: order.get(r["id"], 999))
    return result


# ── Main ─────────────────────────────────────────────────────────────────
def main():
    if JSON_PATH.exists():
        with open(JSON_PATH, encoding="utf-8") as f:
            data = json.load(f)
        print("✅ JSON esistente caricato")
    else:
        print("⚠️  races-data.json non trovato, verrà creato da zero")
        data = {"races": [], "season": [], "standings": {"drivers": [], "constructors": []}}

    print("📡 Scarico sessioni GP...")
    try:
        races = fetch_races(data.get("races", []))
        if races:
            data["races"] = races
            print(f"  ✅ {len(races)} GP nel calendario (su {len(RACE_CALENDAR_2026)} totali)")
        else:
            print("  ⚠️  Nessun dato GP, races invariate")
    except Exception as e:
        print(f"  ❌ Errore races: {e}")

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

    data["lastUpdated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n✅ races-data.json aggiornato — {data['lastUpdated']}")


if __name__ == "__main__":
    main()
