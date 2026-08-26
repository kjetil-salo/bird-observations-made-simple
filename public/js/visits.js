/**
 * Besøk er feltkonteksten på en lokalitet.
 * Samme lokalitet kan besøkes flere ganger samme dag.
 */

function normalizePlaceName(name) {
  return String(name || '').trim().toLowerCase().replace(/\s+/g, ' ');
}

export function getPlaceKey(placeName, placeId = null) {
  if (placeId !== null && placeId !== undefined && String(placeId).trim() !== '') {
    return `id:${String(placeId).trim()}`;
  }
  const name = normalizePlaceName(placeName);
  return name ? `name:${name}` : 'name:uten-stedsnavn';
}

export function createVisitId(placeName, placeId = null, now = new Date()) {
  const safeTime = now instanceof Date && !isNaN(now.getTime()) ? now.getTime() : Date.now();
  const randomPart = Math.random().toString(36).slice(2, 8);
  return `visit:${getPlaceKey(placeName, placeId)}:${safeTime}:${randomPart}`;
}

export function getObservationPlaceKey(obs) {
  return getPlaceKey(obs?.placeName, obs?.placeId);
}

export function getObservationVisitKey(obs) {
  if (obs?.visitId) return obs.visitId;
  return `legacy:${getObservationPlaceKey(obs)}`;
}

export function findOpenVisitId(observations, placeName, placeId = null) {
  const placeKey = getPlaceKey(placeName, placeId);
  const newestByVisit = new Map();

  for (const obs of observations || []) {
    if (getObservationPlaceKey(obs) !== placeKey) continue;
    const visitKey = getObservationVisitKey(obs);
    if (!newestByVisit.has(visitKey)) {
      newestByVisit.set(visitKey, obs);
    }
  }

  for (const [visitKey, obs] of newestByVisit.entries()) {
    if (!obs.visitLocked) return visitKey;
  }

  return null;
}

export function resolveVisitIdForNewObservation(observations, placeName, placeId = null, now = new Date()) {
  return findOpenVisitId(observations, placeName, placeId) || createVisitId(placeName, placeId, now);
}

export function setVisitLocked(observations, visitKey, locked = true) {
  let count = 0;
  for (const obs of observations || []) {
    if (getObservationVisitKey(obs) !== visitKey) continue;
    obs.visitId = visitKey;
    obs.visitLocked = locked;
    count++;
  }
  return count;
}

/**
 * Tidsspennet til et besøk: tidligste fra-tid og seneste til-tid blant
 * observasjonene i besøket. Samme regnestykke som gruppeoverskrifta i ③
 * viser, men returnert som lokale ISO-strenger klare til å settes på en ny obs.
 *
 * Brukes når man hopper tilbake til et besøk med blyanten: da er den nye
 * observasjonen en etterregistrering *inni* besøket, ikke noe man så nå.
 *
 * @returns {{fra: string, til: string|null}|null} null hvis besøket er tomt
 *   eller ingen av observasjonene har brukbart tidspunkt.
 */
export function getVisitTimeSpan(observations, visitKey) {
  // Sammenlign på parset tid, ikke på streng: lista kan inneholde både
  // «2026-08-26T17:09:00» (toLocalISOString) og eldre UTC-strenger med Z,
  // og de sorterer ikke likt leksikografisk.
  let fra = null, fraMs = Infinity;
  let til = null, tilMs = -Infinity;

  // kanVaereFra: bare fra-tidspunkter kan flytte starten på besøket — samme
  // regnestykke som gruppeoverskrifta i ③ gjør.
  const vurder = (verdi, kanVaereFra) => {
    if (!verdi) return;
    const ms = new Date(verdi).getTime();
    if (isNaN(ms)) return;
    if (kanVaereFra && ms < fraMs) { fraMs = ms; fra = verdi; }
    if (ms > tilMs) { tilMs = ms; til = verdi; }
  };

  for (const obs of observations || []) {
    if (getObservationVisitKey(obs) !== visitKey) continue;
    vurder(obs.timestamp, true);
    vurder(obs.tilKlokkeslett, false);
  }

  if (fra === null) return null;
  return { fra, til: tilMs > fraMs ? til : null };
}

/**
 * Er besøket avsluttet (🔒)? Et besøk er låst når alle observasjonene i det er
 * det — samme regnestykke som gruppeoverskrifta i ③ bruker.
 */
export function isVisitLocked(observations, visitKey) {
  const iBesoket = (observations || []).filter(
    (o) => getObservationVisitKey(o) === visitKey);
  return iBesoket.length > 0 && iBesoket.every((o) => o.visitLocked);
}

/** Finnes besøket fortsatt i lista? */
export function visitExists(observations, visitKey) {
  return (observations || []).some((o) => getObservationVisitKey(o) === visitKey);
}
