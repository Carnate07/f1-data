// Aggiorna automaticamente la sezione "season" di races-data.json
// usando l'API gratuita Jolpica F1 (successore di Ergast).
//
// Genera: round, bandiera, nome GP, date del weekend, flag "sprint",
// e i flag "done"/"next" calcolati confrontando le date con oggi.
//
// Non tocca "races" (programma TV dettagliato) e "standings".

const fs = require('fs');
const path = require('path');

const RACES_URL = 'https://api.jolpi.ca/ergast/f1/current/races.json?limit=40';
const DATA_FILE = path.join(__dirname, '..', 'races-data.json');

const MONTHS_IT = ['Gen','Feb','Mar','Apr','Mag','Giu','Lug','Ago','Set','Ott','Nov','Dic'];

// Bandiera in base al paese (come restituito da Jolpica/Ergast)
const COUNTRY_FLAGS = {
  'Australia': '🇦🇺',
  'China': '🇨🇳',
  'Japan': '🇯🇵',
  'Bahrain': '🇧🇭',
  'Saudi Arabia': '🇸🇦',
  'USA': '🇺🇸',
  'Italy': '🇮🇹',
  'Monaco': '🇲🇨',
  'Canada': '🇨🇦',
  'Spain': '🇪🇸',
  'Austria': '🇦🇹',
  'UK': '🇬🇧',
  'Belgium': '🇧🇪',
  'Hungary': '🇭🇺',
  'Netherlands': '🇳🇱',
  'Azerbaijan': '🇦🇿',
  'Singapore': '🇸🇬',
  'Mexico': '🇲🇽',
  'Brazil': '🇧🇷',
  'Qatar': '🇶🇦',
  'UAE': '🇦🇪',
  'France': '🇫🇷',
  'Germany': '🇩🇪',
  'Portugal': '🇵🇹',
  'Russia': '🇷🇺',
  'Turkey': '🇹🇷',
  'South Korea': '🇰🇷',
  'India': '🇮🇳',
  'Malaysia': '🇲🇾'
};

// Nome del GP in italiano in base al circuito (come lo vuole l'app).
// Se un circuito non è in questa lista, viene usato un nome generico
// derivato da raceName (es. "Madrid Grand Prix" -> "GP Madrid").
const CIRCUIT_NAMES_IT = {
  'albert_park': 'GP Australia',
  'shanghai': 'GP Cina',
  'suzuka': 'GP Giappone',
  'bahrain': 'GP Bahrain',
  'jeddah': 'GP Arabia Saudita',
  'miami': 'GP Miami',
  'imola': 'GP Emilia Romagna',
  'monaco': 'GP Monaco',
  'villeneuve': 'GP Canada',
  'catalunya': 'GP Spagna',
  'red_bull_ring': 'GP Austria',
  'silverstone': 'GP Gran Bretagna',
  'spa': 'GP Belgio',
  'hungaroring': 'GP Ungheria',
  'zandvoort': 'GP Olanda',
  'monza': 'GP Italia (Monza)',
  'baku': 'GP Azerbaijan',
  'marina_bay': 'GP Singapore',
  'americas': 'GP USA (Austin)',
  'rodriguez': 'GP Messico',
  'interlagos': 'GP Brasile',
  'vegas': 'GP Las Vegas',
  'losail': 'GP Qatar',
  'yas_marina': 'GP Abu Dhabi',
  'madring': 'GP Madrid'
};

async function fetchJson(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status} su ${url}`);
  return res.json();
}

// Calcola l'intervallo di date del weekend (venerdì-domenica) a partire
// dalla data della gara (domenica), in formato italiano "DD-DD Mmm"
// oppure "DD Mmm-DD Mmm" se il weekend attraversa due mesi.
function formatWeekendDates(raceDateStr) {
  const raceDate = new Date(`${raceDateStr}T00:00:00Z`);
  const start = new Date(raceDate);
  start.setUTCDate(start.getUTCDate() - 2);

  const d1 = start.getUTCDate();
  const m1 = MONTHS_IT[start.getUTCMonth()];
  const d2 = raceDate.getUTCDate();
  const m2 = MONTHS_IT[raceDate.getUTCMonth()];

  if (m1 === m2) return `${d1}-${d2} ${m1}`;
  return `${d1} ${m1}-${d2} ${m2}`;
}

function italianName(race) {
  const circuitId = race.Circuit.circuitId;
  if (CIRCUIT_NAMES_IT[circuitId]) return CIRCUIT_NAMES_IT[circuitId];
  return `GP ${race.raceName.replace(/ Grand Prix$/i, '')}`;
}

async function main() {
  const data = await fetchJson(RACES_URL);
  const races = data.MRData?.RaceTable?.Races || [];

  if (races.length < 15) {
    throw new Error('Calendario non disponibile o incompleto: niente da aggiornare.');
  }

  const now = new Date();
  // Margine dopo l'orario di partenza della gara: prima di questo
  // istante la gara è considerata "in corso/da disputare", non "passata"
  const RACE_DURATION_BUFFER_MS = 3 * 60 * 60 * 1000; // 3 ore

  let nextAssigned = false;
  const season = races.map(race => {
    const country = race.Circuit.Location.country;
    const entry = {
      round: Number(race.round),
      flag: COUNTRY_FLAGS[country] || '🏁',
      name: italianName(race),
      date: formatWeekendDates(race.date)
    };

    if (race.Sprint) entry.sprint = true;

    // Orario di partenza della gara (UTC). Se manca, usiamo fine giornata
    // come stima prudente.
    const raceStart = race.time
      ? new Date(`${race.date}T${race.time}`)
      : new Date(`${race.date}T23:59:59Z`);
    const raceConsideredOver = new Date(raceStart.getTime() + RACE_DURATION_BUFFER_MS);

    if (raceConsideredOver <= now) {
      entry.done = true;
    } else if (!nextAssigned) {
      entry.next = true;
      nextAssigned = true;
    }

    return entry;
  });

  let json = {};
  if (fs.existsSync(DATA_FILE)) {
    json = JSON.parse(fs.readFileSync(DATA_FILE, 'utf8'));
  }

  json.season = season;
  json.lastUpdated = new Date().toISOString().slice(0, 16).replace('T', ' ') + ' UTC';

  fs.writeFileSync(DATA_FILE, JSON.stringify(json, null, 2) + '\n');

  const next = season.find(s => s.next);
  console.log(`Calendario aggiornato: ${season.length} gare.`);
  console.log(`Prossima gara: ${next ? `${next.flag} ${next.name} (${next.date})` : 'nessuna (stagione finita)'}`);
}

main().catch(err => {
  console.error('Errore aggiornamento calendario:', err.message);
  process.exit(1);
});
