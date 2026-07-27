/**
 * Storage-modul for localStorage-håndtering
 */

const STORAGE_KEY = 'fugleobservasjoner_v1';
const MEDOBS_KEY = 'medobs_list_v1';
const AO_SIZE_KEY = 'ao_search_radius_v1';
const ACTIVITY_PILLS_KEY = 'activityPills_v1';
const SENT_KEY = 'sent_observations_v1';

// Sendt-loggen husker hva som faktisk ble sendt, slik at arbeidslista trygt kan
// tømmes etterpå. Holdes bevisst kort — den er en kvittering, ikke et arkiv.
export const SENT_MAX_DAYS = 7;
export const SENT_MAX_OBS = 200;

function todayStr() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

/**
 * Last medobservatører fra localStorage.
 * Aktive medobservatører nullstilles automatisk neste dag.
 * @returns {Array} - Liste med medobservatører
 */
export function loadMedobs() {
  try {
    const raw = JSON.parse(window.localStorage.getItem(MEDOBS_KEY) || 'null');
    if (!raw) return [];

    // Gammelt format: array av strings
    if (Array.isArray(raw) && raw.length && typeof raw[0] === 'string') {
      return raw.slice(0, 10).map((n) => ({ name: n, active: false }));
    }

    // Nytt format: { date: 'YYYY-MM-DD', list: [...] }
    if (raw && typeof raw === 'object' && !Array.isArray(raw) && raw.list) {
      const list = Array.isArray(raw.list) ? raw.list : [];
      if (raw.date !== todayStr()) {
        // Ny dag — deaktiver alle
        return list.map((it) => ({ ...it, active: false }));
      }
      return list;
    }

    // Gammelt format: direkte array av objekter
    if (Array.isArray(raw)) {
      return raw.map((it) => ({ ...it, active: false }));
    }

    return [];
  } catch (e) {
    console.warn('Kunne ikke laste medobservatører', e);
    return [];
  }
}

/**
 * Lagre medobservatører til localStorage med dagens dato.
 * @param {Array} list - Liste med medobservatører
 */
export function saveMedobs(list) {
  try {
    window.localStorage.setItem(MEDOBS_KEY, JSON.stringify({ date: todayStr(), list }));
  } catch (e) {
    console.warn('Kunne ikke lagre medobservatører', e);
  }
}

/**
 * Hent standard medobservatører for nye observasjoner
 * @returns {Array<string>} - Array med 10 medobservatør-navn (tomme strenger hvis ingen)
 */
export function defaultCoObservers() {
  const l = loadMedobs();
  const active = (l || []).filter((it) => it && it.name && it.active).map((it) => it.name);
  const res = Array(10).fill('');
  for (let i = 0; i < Math.min(10, active.length); i++) {
    res[i] = active[i];
  }
  return res;
}

/**
 * Lagre observasjoner til localStorage
 * @param {Array} observations - Liste med observasjoner
 */
export function saveObservations(observations) {
  if (!window.localStorage) return;
  
  try {
    const payload = {
      version: 1,
      observations,
    };
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
  } catch (e) {
    console.warn('Kunne ikke lagre til localStorage', e);
  }
}

/**
 * Last observasjoner fra localStorage
 * @returns {Array} - Liste med observasjoner
 */
export function loadObservations() {
  if (!window.localStorage) return [];

  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];

    const payload = JSON.parse(raw);
    if (!payload || !Array.isArray(payload.observations)) return [];

    return payload.observations;
  } catch (e) {
    console.warn('Kunne ikke lese fra localStorage', e);
    return [];
  }
}

/**
 * Fjern for gamle og for mange poster fra sendt-loggen.
 * Nyeste sending først i lista.
 * @param {Array} batches - Sendinger, nyeste først
 * @returns {Array} - Beskåret liste
 */
function pruneSentBatches(batches) {
  const grense = Date.now() - SENT_MAX_DAYS * 86400000;
  const ferske = batches.filter((b) => {
    const t = Date.parse(b && b.ts);
    return !isNaN(t) && t >= grense;
  });

  // Behold nyeste sendinger til vi når obs-taket
  const beholdt = [];
  let antall = 0;
  for (const b of ferske) {
    const n = Array.isArray(b.obs) ? b.obs.length : 0;
    if (beholdt.length && antall + n > SENT_MAX_OBS) break;
    beholdt.push(b);
    antall += n;
  }
  return beholdt;
}

/**
 * Legg en fullført sending til i sendt-loggen.
 * Kalles ved vellykket publisering — før arbeidslista eventuelt tømmes.
 * @param {Array} observations - Observasjonene som ble sendt
 */
export function appendSentBatch(observations) {
  if (!window.localStorage || !Array.isArray(observations) || !observations.length) return;

  try {
    const batches = loadSentBatches();
    batches.unshift({
      ts: new Date().toISOString(),
      obs: JSON.parse(JSON.stringify(observations)),
    });
    window.localStorage.setItem(SENT_KEY, JSON.stringify({
      version: 1,
      batches: pruneSentBatches(batches),
    }));
  } catch (e) {
    // Full localStorage skal aldri velte appen — sendingen er allerede fullført
    console.warn('Kunne ikke lagre sendt-logg', e);
  }
}

/**
 * Hent sendt-loggen, nyeste sending først. Gamle poster filtreres bort.
 * @returns {Array<{ts: string, obs: Array}>}
 */
export function loadSentBatches() {
  if (!window.localStorage) return [];

  try {
    const raw = window.localStorage.getItem(SENT_KEY);
    if (!raw) return [];

    const payload = JSON.parse(raw);
    if (!payload || !Array.isArray(payload.batches)) return [];

    return pruneSentBatches(payload.batches.filter((b) => b && Array.isArray(b.obs)));
  } catch (e) {
    console.warn('Kunne ikke lese sendt-logg', e);
    return [];
  }
}

/**
 * Lagre søkeradius til localStorage
 * @param {number} radius - Radius i meter
 */
export function saveAoSearchRadius(radius) {
  if (!window.localStorage) return;

  try {
    window.localStorage.setItem(AO_SIZE_KEY, String(radius));
  } catch (e) {
    console.warn('Kunne ikke lagre søkeradius', e);
  }
}

/**
 * Last søkeradius fra localStorage
 * @returns {number} - Radius i meter (default 1000)
 */
export function loadAoSearchRadius() {
  if (!window.localStorage) return 1000;

  try {
    const raw = window.localStorage.getItem(AO_SIZE_KEY);
    if (!raw) return 1000;

    const radius = parseFloat(raw);
    if (isNaN(radius) || radius < 500 || radius > 3000) return 1000;

    return radius;
  } catch (e) {
    console.warn('Kunne ikke lese søkeradius', e);
    return 1000;
  }
}

/**
 * Kuraterte forkortelses-forslag for standard-aktivitetene, nøklet på value.
 * Brukes av «Foreslå forkortelser»-knappen i innstillinger. Maks 5 tegn.
 */
export const ACTIVITY_SHORT_SUGGESTIONS = {
  '23': 'Stasj', // Stasjonær
  '22': 'Rast',  // Rastende
  '24': 'Overf', // Overflygende
  '25': 'Nær',   // Næringssøkende
  '32': 'Trekk', // Trekkende
  '52': 'Sang'   // Sang/spill
};

/**
 * Lagre konfigurasjon av aktivitetspills
 * @param {Array<{label: string, value: string, short?: string}>} pills - Array av pill-objekter.
 *   `short` er valgfritt kortnavn (maks 5 tegn) som vises på hurtigknappen i stedet for fullt navn.
 */
export function saveActivityPills(pills) {
  try {
    const config = {
      version: 1,
      pills: pills.slice(0, 6).map(p => {
        const pill = { label: p.label, value: p.value };
        const short = (p.short || '').trim().slice(0, 5);
        if (short) pill.short = short; // tomt kortnavn utelates → vis fullt navn
        return pill;
      })
    };
    localStorage.setItem(ACTIVITY_PILLS_KEY, JSON.stringify(config));
  } catch (e) {
    console.warn('Kunne ikke lagre aktivitetspills', e);
  }
}

/**
 * Last konfigurasjon av aktivitetspills
 * @returns {Array<{label: string, value: string, short?: string}>}
 */
export function loadActivityPills() {
  try {
    const raw = localStorage.getItem(ACTIVITY_PILLS_KEY);
    if (raw) {
      const config = JSON.parse(raw);
      if (config.version === 1 && Array.isArray(config.pills)) {
        return config.pills;
      }
    }
  } catch (e) {
    console.warn('Kunne ikke laste aktivitetspills', e);
  }

  // Migrer fra gammelt system
  return migrateFromOldPillCount();
}

/**
 * Migrer fra gammelt activityPillCount til nytt system
 * @returns {Array<{label: string, value: string}>}
 */
function migrateFromOldPillCount() {
  const oldCount = localStorage.getItem('activityPillCount');

  // Standard pills (matching observation-commit.js hardkoded array)
  const defaultPills = [
    { label: 'Stasjonær', value: '23' },
    { label: 'Rastende', value: '22' },
    { label: 'Overflygende', value: '24' },
    { label: 'Næringssøkende', value: '25' },
    { label: 'Trekkende', value: '32' },
    { label: 'Sang/spill', value: '52' }
  ];

  if (oldCount) {
    const count = parseInt(oldCount, 10);
    if (count >= 1 && count <= 6) {
      return defaultPills.slice(0, count);
    }
  }

  // Default for helt nye brukere: 4 første
  return defaultPills.slice(0, 4);
}
