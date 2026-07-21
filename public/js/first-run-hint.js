/**
 * Éngangs førstegangs-hint for helt nye brukere.
 * Peker på ① Lokasjon og forklarer at man alltid starter der.
 *
 * Vises KUN når:
 *  - brukeren aldri har registrert en observasjon, og
 *  - hinten ikke er lukket tidligere.
 * Sekvenseres etter news-splashen slik at det aldri er to overlays samtidig.
 */

import { loadObservations } from './storage.js';

const HINT_ID = 'start-with-location-v1';
const COOKIE_NAME = 'enkelAoHintRead';
const STORAGE_KEY = 'enkelAoHintRead';

function getCookieValue(name) {
  const prefix = `${encodeURIComponent(name)}=`;
  return document.cookie
    .split(';')
    .map((part) => part.trim())
    .find((part) => part.startsWith(prefix))
    ?.slice(prefix.length) || '';
}

function hasSeenHint() {
  if (decodeURIComponent(getCookieValue(COOKIE_NAME)) === HINT_ID) return true;
  try {
    return window.localStorage?.getItem(STORAGE_KEY) === HINT_ID;
  } catch (e) {
    return false;
  }
}

function markHintSeen() {
  const maxAge = 60 * 60 * 24 * 365;
  document.cookie = `${encodeURIComponent(COOKIE_NAME)}=${encodeURIComponent(HINT_ID)}; Max-Age=${maxAge}; Path=/; SameSite=Lax`;
  try {
    window.localStorage?.setItem(STORAGE_KEY, HINT_ID);
  } catch (e) {
    // Cookie er hovedkilden. localStorage er bare fallback.
  }
}

function isFirstTimer() {
  try {
    return loadObservations().length === 0;
  } catch (e) {
    return false;
  }
}

function showHint() {
  const section = document.querySelector('.section-lokasjon');
  const card = section?.closest('.card');
  if (!section || !card || card.querySelector('.coachmark-dim')) return;

  // Sørg for at ① Lokasjon er synlig før vi løfter den frem.
  window.scrollTo({ top: 0, behavior: 'auto' });

  // Kortet blir positioneringskontekst for dim-overlay og boble.
  card.classList.add('coachmark-open');

  // Dim-overlay dekker hele kortet; ① Lokasjon løftes over den.
  const dim = document.createElement('div');
  dim.className = 'coachmark-dim';
  section.classList.add('coachmark-spot');

  // Forklaringsboble som peker opp mot ① Lokasjon.
  const bubble = document.createElement('div');
  bubble.className = 'coachmark-bubble';
  bubble.setAttribute('role', 'dialog');
  bubble.setAttribute('aria-modal', 'true');
  bubble.setAttribute('aria-label', 'Slik kommer du i gang');

  const title = document.createElement('strong');
  title.className = 'coachmark-title';
  title.textContent = '👋 Start her';

  const body = document.createElement('p');
  body.className = 'coachmark-body';
  body.textContent = 'Enkel-AO hjelper deg å registrere fugleobservasjoner i felt og sende dem til Artsobservasjoner. Velg lokasjon først — trykk «Bruk GPS». Deretter kan du søke etter art.';

  const more = document.createElement('p');
  more.className = 'coachmark-body';
  more.style.marginTop = '6px';
  const moreLink = document.createElement('a');
  moreLink.href = 'help.html';
  moreLink.textContent = '📖 Les mer om hvordan appen fungerer';
  moreLink.style.color = '#3b82f6';
  more.appendChild(moreLink);

  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'coachmark-button';
  button.textContent = 'Skjønner';

  bubble.appendChild(title);
  bubble.appendChild(body);
  bubble.appendChild(more);
  bubble.appendChild(button);

  function position() {
    const sr = section.getBoundingClientRect();
    const cr = card.getBoundingClientRect();
    const width = Math.min(360, sr.width);
    bubble.style.width = `${width}px`;
    bubble.style.left = `${sr.left - cr.left}px`;
    bubble.style.top = `${sr.bottom - cr.top + 12}px`;
  }

  function dismiss() {
    markHintSeen();
    section.classList.remove('coachmark-spot');
    card.classList.remove('coachmark-open');
    dim.remove();
    bubble.remove();
    window.removeEventListener('resize', position);
  }

  button.addEventListener('click', dismiss);
  dim.addEventListener('click', dismiss);
  // Naturlig fullføring: når brukeren faktisk oppdaterer lokasjon, er jobben gjort.
  document.getElementById('loc-btn')?.addEventListener('click', dismiss, { once: true });
  window.addEventListener('resize', position);

  card.appendChild(dim);
  card.appendChild(bubble);
  position();
  button.focus({ preventScroll: true });
}

export function initFirstRunHint() {
  if (hasSeenHint() || !isFirstTimer()) return;

  // Vent til news-splashen er lukket før hinten vises (unngå dobbel overlay).
  const splash = document.querySelector('.news-splash');
  if (!splash) {
    showHint();
    return;
  }

  const observer = new MutationObserver(() => {
    if (!document.querySelector('.news-splash')) {
      observer.disconnect();
      showHint();
    }
  });
  observer.observe(document.body, { childList: true });
}
