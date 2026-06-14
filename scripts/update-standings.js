// Aggiorna automaticamente la sezione "standings" di races-data.json
// usando l'API gratuita Jolpica F1 (successore di Ergast).
//
// Non tocca "races" e "season": aggiorna solo "standings" e "lastUpdated".

const fs = require('fs');
const path = require('path');

const BASE = 'https://api.jolpi.ca/ergast/f1/current';
const DATA_FILE = path.join(__dirname, '..', 'races-data.json');

async function fetchJson(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status} su ${url}`);
  return res.json();
}

async function main() {
  const [driverData, constructorData] = await Promise.all([
    fetchJson(`${BASE}/driverstandings.json`),
    fetchJson(`${BASE}/constructorstandings.json`)
  ]);

  const driverList =
    driverData.MRData.StandingsTable.StandingsLists[0]?.DriverStandings || [];
  const constructorList =
    constructorData.MRData.StandingsTable.StandingsLists[0]?.ConstructorStandings || [];

  if (driverList.length === 0 || constructorList.length === 0) {
    throw new Error('Risposta API senza classifiche: niente da aggiornare.');
  }

  const drivers = driverList.map(d => ({
    pos: Number(d.position),
    name: `${d.Driver.givenName} ${d.Driver.familyName}`,
    team: d.Constructors?.[0]?.name || '',
    pts: Number(d.points)
  }));

  const constructors = constructorList.map(c => {
    const teamDrivers = driverList
      .filter(d =>
        d.Constructors?.some(con => con.constructorId === c.Constructor.constructorId)
      )
      .sort((a, b) => Number(b.points) - Number(a.points))
      .map(d => d.Driver.familyName);

    return {
      pos: Number(c.position),
      name: c.Constructor.name,
      team: teamDrivers.join(' / '),
      pts: Number(c.points)
    };
  });

  let data = {};
  if (fs.existsSync(DATA_FILE)) {
    data = JSON.parse(fs.readFileSync(DATA_FILE, 'utf8'));
  }

  data.standings = { drivers, constructors };
  data.lastUpdated = new Date().toISOString().slice(0, 16).replace('T', ' ') + ' UTC';

  fs.writeFileSync(DATA_FILE, JSON.stringify(data, null, 2) + '\n');
  console.log('Classifiche aggiornate:', data.lastUpdated);
  console.log('Piloti:', drivers.map(d => `${d.pos}. ${d.name} (${d.pts})`).join(', '));
  console.log(
    'Costruttori:',
    constructors.map(c => `${c.pos}. ${c.name} (${c.pts})`).join(', ')
  );
}

main().catch(err => {
  console.error('Errore aggiornamento classifiche:', err.message);
  process.exit(1);
});
