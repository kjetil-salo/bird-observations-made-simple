/**
 * Main entry point for fugleobservasjoner app
 * Koordinerer alle moduler og setter opp event listeners
 */

// Eksisterende moduler
import { logPageView, loadActivities, fetchAoSites, fetchAndCachePrivateSites, getCachedPrivateSites } from './api.js';
import { loadObservations, saveObservations, loadAoSearchRadius, saveAoSearchRadius } from './storage.js';
import { setStatus, setLocationStatus, showToast } from './ui.js';
import { setAoSiteSuggestions, initLocation, openMap, openMapPage, updateCreateSiteBtnVisibility, initCreateSite } from './location.js';
import { renderObservations } from './observations.js';
import { getVisitTimeSpan, isVisitLocked, visitExists } from './visits.js';

// Nye moduler
import { updateSectionStates, pulseSearchFieldAndFocus } from './form-state.js';
import { fetchResults, renderResults, chooseItem, updateSubtaxaCheckboxState } from './species-search.js';
import { commitObservation, renderActivityPills } from './observation-commit.js';
import { handleExport, handleCopy, handleCopyAndOpen, handleClear, handleDirectSend } from './export-operations.js';
import { openShareDialog } from './share.js';
import { initAutocomplete } from './autocomplete.js';
import { initNewsSplash } from './news-splash.js';
import { initFirstRunHint } from './first-run-hint.js';

// ============================================================
// Applikasjonstilstand
// ============================================================
const appState = {
  currentResults: [],
  activeIndex: -1,
  debounceTimer: null,
  selectedSpecies: null,
  searchPulseTimeout: null,
  observations: [],
  currentPosition: null,
  currentPlaceName: '',
  currentPlaceId: null,
  // Satt når man hopper tilbake til et besøk med blyanten i ③. Da er nye
  // observasjoner etterregistreringer *inni* det besøket, og arver besøkets
  // klokkeslett i stedet for å få «nå». Nullstilles så snart plassen endres
  // på en hvilken som helst annen måte.
  etterregVisitKey: null,
  currentAoSites: [],
  currentAoSizeMeters: 1000,
  _callbacks: null, // settes i init()
};

// Autocomplete cleanup-funksjon
let autocompleteCleanup = null;

// ============================================================
// DOM-elementreferanser
// ============================================================
const dom = {
  input: document.getElementById('search'),
  resultsEl: document.getElementById('results'),
  emptyMsgEl: document.getElementById('empty-msg'),
  statusDot: document.getElementById('status-dot'),
  statusText: document.getElementById('status-text'),
  resultCount: document.getElementById('result-count'),
  countInput: document.getElementById('count'),
  activitySelect: document.getElementById('activity'),
  activitySubmitBtn: document.getElementById('activity-submit'),
  activityPillsEl: document.getElementById('activity-pills'),
  obsListEl: document.getElementById('obs-list'),
  exportBtn: document.getElementById('export-btn'),
  copyBtn: document.getElementById('copy-btn'),
  copyOpenBtn: document.getElementById('copy-open-btn'),
  shareBtn: document.getElementById('share-btn'),
  clearBtn: document.getElementById('clear-btn'),
  aoDirectBtn: document.getElementById('ao-direct-btn'),
  aoDirectRow: document.getElementById('ao-direct-row'),
  aoDirectStatus: document.getElementById('ao-direct-status'),
  locDot: document.getElementById('loc-dot'),
  locText: document.getElementById('loc-text'),
  locMapBtn: document.getElementById('loc-map-btn'),
  locBtn: document.getElementById('loc-btn'),
  placeInput: document.getElementById('place'),
  aoSitesEl: document.getElementById('ao-sites'),
  aoSitesDropdown: document.getElementById('ao-sites-dropdown'),
  aoSizeInput: document.getElementById('ao-size'),
  sectionLokasjon: document.querySelector('.section-main:nth-of-type(1)'),
  sectionObservasjon: document.querySelector('.section-main:nth-of-type(2)'),
  sectionAktivitet: document.querySelector('.row .activity-input-row'),
  ageSelect: document.getElementById('age'),
  genderSelect: document.getElementById('gender'),
};

// ============================================================
// Callbacks-objekt (unngår sirkulære imports)
// ============================================================
const callbacks = {
  updateSectionStates: () => updateSectionStates(appState, dom),
  updateStatus: (mode, text, html) => setStatus(dom.statusDot, dom.statusText, mode, text, html),
  updateLocationStatus: (mode, text) => setLocationStatus(dom.locDot, dom.locText, mode, text),
  doRenderObservations,
  saveState,
  renderResults: () => renderResults(appState, dom),
};
appState._callbacks = callbacks;

// ============================================================
// Korte wrappere
// ============================================================
function saveState() {
  saveObservations(appState.observations);
}

/**
 * Forlat etterregistrerings-modus for et besøk. Kalles fra alle steder som
 * setter aktiv plass på annen måte enn blyanten — GPS-dropdown, autocomplete,
 * kartvalg og manuell skriving. Da er man ikke lenger i det gamle besøket.
 */
function avsluttEtterregistrering() {
  if (!appState.etterregVisitKey) return;
  appState.etterregVisitKey = null;
  oppdaterEtterregMerke();
}

function loadState() {
  const loaded = loadObservations();
  appState.observations.splice(0, appState.observations.length);
  loaded.forEach(o => appState.observations.push(o));

  const last = appState.observations[appState.observations.length - 1];
  if (last && last.placeName) {
    appState.currentPlaceName = last.placeName;
    appState.currentPlaceId = last.placeId || null;
    if (dom.placeInput) {
      dom.placeInput.value = appState.currentPlaceName;
      dom.placeInput.dataset.autofilled = 'false';
    }
  }
}

function doRenderObservations() {
  const buttons = { exportBtn: dom.exportBtn, copyBtn: dom.copyBtn, copyOpenBtn: dom.copyOpenBtn, shareBtn: dom.shareBtn, clearBtn: dom.clearBtn, aoDirectBtn: dom.aoDirectBtn };
  renderObservations(appState.observations, dom.obsListEl, buttons, saveState);
  // Lista kan ha endret besøket vi etterregistrerer i (låst, tømt, nye tider)
  oppdaterEtterregMerke();
}

function updateAoDirectVisibility() {
  if (!dom.aoDirectRow) return;
  const hasCredentials = localStorage.getItem('ao_username') && localStorage.getItem('ao_password');
  dom.aoDirectRow.style.display = hasCredentials ? 'block' : 'none';
  // Uten innlogging: vis CTA så nye brukere ser at direkte publisering finnes
  const loginCta = document.getElementById('ao-login-cta');
  if (loginCta) loginCta.style.display = hasCredentials ? 'none' : 'flex';
}

function commitFromActivity() {
  commitObservation(appState, dom, callbacks);
}

// ============================================================
// Radius-formattering (500 m – 3 km)
// ============================================================
function formatRadius(meters) {
  if (meters < 1000) return `${Math.round(meters)} m`;
  const km = meters / 1000;
  const str = Number.isInteger(km) ? String(km) : km.toFixed(1).replace('.', ',');
  return `${str} km`;
}

// ============================================================
// Kollaps/utvid ① Lokasjon (festet kompakt linje når plass er valgt)
// ============================================================
function collapseLocation() {
  const name = (dom.placeInput && dom.placeInput.value.trim()) || (appState.currentPlaceName || '').trim();
  if (!name) return; // Kollaps aldri uten en valgt plass
  const locPinned = document.getElementById('loc-pinned');
  const locPinnedName = document.getElementById('loc-pinned-name');
  const sectionLokasjon = document.querySelector('.section-lokasjon');
  if (locPinnedName) locPinnedName.textContent = name;
  if (locPinned) locPinned.style.display = 'flex';
  if (sectionLokasjon) sectionLokasjon.style.display = 'none';
}

function klokke(iso) {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '';
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

/**
 * Merket i den festede lokasjonslinja som viser at nye observasjoner går inn
 * i et tidligere besøk, og hvilket klokkeslett de får. Uten dette ville tida
 * bli satt stille i bakgrunnen — brukeren skal se hva som skjer.
 */
function oppdaterEtterregMerke() {
  const merke = document.getElementById('loc-pinned-visit');
  if (!merke) return;

  // Besøket kan ha blitt tømt (slettede obser, «tøm lista») siden ↩ ble
  // trykket. Da finnes det ikke lenger å gå tilbake til. Et *låst* besøk
  // beholdes derimot — ↩ er nettopp et eksplisitt valg om å gå inn i det.
  if (appState.etterregVisitKey
      && !visitExists(appState.observations, appState.etterregVisitKey)) {
    appState.etterregVisitKey = null;
  }

  const span = appState.etterregVisitKey
    ? getVisitTimeSpan(appState.observations, appState.etterregVisitKey)
    : null;

  if (!span) {
    merke.style.display = 'none';
    merke.textContent = '';
    return;
  }

  // Nye arter får besøkets starttidspunkt — ett nøyaktig klokkeslett. Merket
  // viser akkurat det tallet, så tida aldri settes i det skjulte.
  const laast = isVisitLocked(appState.observations, appState.etterregVisitKey);
  merke.textContent = `${laast ? '🔒 ' : ''}↩ ${klokke(span.fra)}`;
  merke.title = laast
    ? 'Avsluttet besøk. Nye arter legges likevel inn her, med besøkets klokkeslett.'
    : 'Nye arter legges inn i dette besøket og får dette klokkeslettet';
  merke.style.display = '';
}

function expandLocation() {
  // Åpner man ① for å bytte plass, er man ute av etterregistreringen — det er
  // den enkle veien tilbake til vanlig «nå»-registrering på samme lokalitet.
  avsluttEtterregistrering();
  const locPinned = document.getElementById('loc-pinned');
  const sectionLokasjon = document.querySelector('.section-lokasjon');
  if (locPinned) locPinned.style.display = 'none';
  if (sectionLokasjon) sectionLokasjon.style.display = '';
  // Scroll den gjenåpnede seksjonen til topp — ellers ser det ut som ingenting
  // skjer når man trykker «Bytt plass» mens man er scrollet ned i obs-lista.
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// ============================================================
// Posisjonshåndtering
// ============================================================
function handlePositionUpdate(position, sites) {
  appState.currentPosition = position;

  function setCurrentPlaceAndUpdate(name, siteId = null) {
    avsluttEtterregistrering();
    appState.currentPlaceName = name;
    appState.currentPlaceId = siteId;
    if (dom.placeInput) {
      dom.placeInput.value = name;
      dom.placeInput.dataset.autofilled = 'true';
    }
    updateSectionStates(appState, dom);
    collapseLocation();
    pulseSearchFieldAndFocus(appState, dom);
  }

  appState.currentAoSites = setAoSiteSuggestions(
    (sites && sites.length) ? sites : [],
    appState.currentPosition,
    dom.aoSitesDropdown,
    dom.aoSitesEl,
    dom.placeInput,
    setCurrentPlaceAndUpdate,
    appState.currentAoSizeMeters
  );
  updateSectionStates(appState, dom);
  updateMapBtnVisibility();
  updateCreateSiteBtnVisibility(appState.currentPosition);
}

// ============================================================
// Event listeners
// ============================================================
function setupEventListeners() {
  // Utvid ① Lokasjon fra festet kompakt linje (ingen auto-GPS)
  const locChangeBtn = document.getElementById('loc-change-btn');
  const locPinnedLabel = document.getElementById('loc-pinned-label');
  if (locChangeBtn) locChangeBtn.addEventListener('click', expandLocation);
  if (locPinnedLabel) locPinnedLabel.addEventListener('click', expandLocation);

  // Blyant i gruppeoverskrifta i ③: bytt aktiv lokalitet tilbake til den
  // gruppens sted, uten å måtte søke det opp på nytt. Observasjons-modulen
  // eier ikke appState, så den varsler hit via CustomEvent.
  document.addEventListener('obs:bruk-lokalitet', (e) => {
    const placeName = (e.detail && e.detail.placeName || '').trim();
    if (!placeName) return;
    appState.currentPlaceName = placeName;
    appState.currentPlaceId = (e.detail && e.detail.placeId) || null;
    if (dom.placeInput) {
      dom.placeInput.value = placeName;
      dom.placeInput.dataset.autofilled = 'true';
    }
    // Å gå tilbake hit er en etterregistrering inn i besøket, ikke noe man ser
    // nå: nye arter får besøkets starttidspunkt (se observation-commit.js).
    // Vil man registrere et *nytt* besøk på samme sted, velger man lokaliteten
    // på vanlig måte i ① i stedet — da blir tida «nå».
    appState.etterregVisitKey = (e.detail && e.detail.visitKey) || null;
    updateSectionStates(appState, dom);
    collapseLocation();
    oppdaterEtterregMerke();
    // Brukeren står nede i obs-lista når hen trykker — ta hen tilbake til
    // toppen der art-feltet står, ellers ser det ut som ingenting skjedde.
    window.scrollTo({ top: 0, behavior: 'smooth' });
    const span = appState.etterregVisitKey
      ? getVisitTimeSpan(appState.observations, appState.etterregVisitKey)
      : null;
    const tid = span ? klokke(span.fra) : '';
    // Lett advarsel ved låst besøk: brukeren har selv sagt at besøket er
    // avsluttet, så det skal ikke være stille at nye arter havner der — og
    // enda mindre at klokka settes tilbake i tid. Ikke-blokkerende med vilje.
    if (e.detail && e.detail.visitLocked) {
      showToast(
        `↩ ${placeName} — avsluttet besøk. Nye arter får kl. ${tid}, tilbake i tid.`,
        { raw: true, borderColor: '#f59e0b', duration: 3500 }
      );
    } else {
      showToast(`↩ ${placeName}${tid ? ` — nye arter får kl. ${tid}` : ''}`, { raw: true });
    }
    pulseSearchFieldAndFocus(appState, dom);
  });

  const includeSubtaxaCheckbox = document.getElementById('include-subtaxa');
  if (includeSubtaxaCheckbox) {
    includeSubtaxaCheckbox.addEventListener('change', () => {
      fetchResults(dom.input.value, appState, dom, callbacks);
    });
  }

  if (dom.placeInput) {
    dom.placeInput.addEventListener('input', () => {
      // Manuell redigering fjerner alltid ID — ID kjem berre frå dropdown-val
      avsluttEtterregistrering();
      appState.currentPlaceId = null;
      dom.placeInput.dataset.autofilled = 'false';
      appState.currentPlaceName = dom.placeInput.value;
      updateSectionStates(appState, dom);
    });
  }
  if (dom.countInput) {
    dom.countInput.addEventListener('input', () => updateSectionStates(appState, dom));
  }
  if (dom.input) {
    dom.input.addEventListener('input', () => updateSectionStates(appState, dom));
  }

  // Søkefelt
  dom.input.addEventListener('input', () => {
    // Ved første tastetrykk etter registrering - nullstill state
    // IKKE tøm feltet - .select() gjør at første tastetrykk automatisk erstatter teksten
    if (dom.input.dataset.pendingClear === 'true') {
      dom.input.dataset.pendingClear = 'false';
      appState.selectedSpecies = null;
      dom.input.classList.remove('species-selected');
    }

    if (appState.searchPulseTimeout) {
      clearTimeout(appState.searchPulseTimeout);
      appState.searchPulseTimeout = null;
    }
    dom.input.classList.remove('field-highlight');

    if (appState.selectedSpecies) {
      appState.selectedSpecies = null;
      dom.input.classList.remove('species-selected');
      dom.countInput.disabled = true;
      dom.countInput.value = '';
      dom.activitySelect.disabled = true;
      dom.activitySubmitBtn.disabled = true;
      dom.ageSelect.disabled = true;
      dom.genderSelect.disabled = true;
    }
    if (appState.debounceTimer) {
      clearTimeout(appState.debounceTimer);
    }
    appState.debounceTimer = setTimeout(() => {
      fetchResults(dom.input.value, appState, dom, callbacks);
    }, 300);
  });

  dom.input.addEventListener('focus', () => {
    // Re-select teksten hvis pendingClear (hvis bruker klikker i stedet for å skrive)
    if (dom.input.dataset.pendingClear === 'true') {
      dom.input.select();
    } else if (appState.selectedSpecies) {
      dom.input.select();
    }
  });

  dom.input.addEventListener('keydown', (e) => {
    if (!appState.currentResults.length) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      appState.activeIndex = (appState.activeIndex + 1) % appState.currentResults.length;
      renderResults(appState, dom);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      appState.activeIndex = (appState.activeIndex - 1 + appState.currentResults.length) % appState.currentResults.length;
      renderResults(appState, dom);
    } else if (e.key === 'Enter') {
      if (appState.activeIndex >= 0) {
        e.preventDefault();
        chooseItem(appState.activeIndex, appState, dom, callbacks);
      }
    }
  });

  dom.countInput.addEventListener('keydown', (e) => {
    // Tillat kun sifre, navigasjon og kontrolltaster
    const allowed = ['Backspace', 'Delete', 'Tab', 'Enter', 'ArrowLeft', 'ArrowRight', 'Home', 'End'];
    if (!allowed.includes(e.key) && !e.ctrlKey && !e.metaKey && !/^[0-9]$/.test(e.key)) {
      e.preventDefault();
      return;
    }
    if (e.key !== 'Enter') return;
    if (!appState.selectedSpecies) return;
    const raw = dom.countInput.value.trim();
    const num = parseInt(raw, 10);
    if (!raw || isNaN(num) || num <= 0) return;
    if (dom.activitySelect && !dom.activitySelect.disabled) {
      dom.activitySelect.focus();
    }
  });

  if (dom.activitySubmitBtn) {
    dom.activitySubmitBtn.addEventListener('click', commitFromActivity);
  }

  if (dom.activitySelect) {
    dom.activitySelect.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') commitFromActivity();
    });
    // Fjernet auto-commit ved dropdown-endring - bruker må klikke grønn knapp
    // Pills (hurtigvalg) lagrer fortsatt umiddelbart
  }

  if (dom.locMapBtn) {
    dom.locMapBtn.style.display = 'none'; // Skjul som default
    dom.locMapBtn.addEventListener('click', () => openMapPage(appState.currentPosition, appState.currentAoSites));
  }




// Oppdater synlighet og stil på kart-ikonet basert på posisjon
function updateMapBtnVisibility() {
  if (!dom.locMapBtn) return;
  if (appState.currentPosition && typeof appState.currentPosition.lat === 'number' && typeof appState.currentPosition.lon === 'number') {
    dom.locMapBtn.style.display = '';
    dom.locMapBtn.style.background = 'var(--accent)';
    dom.locMapBtn.style.color = 'white';
    dom.locMapBtn.style.borderColor = 'var(--accent)';
    dom.locMapBtn.style.boxShadow = '0 0 0 3px #22c55e55, 0 2px 8px rgba(59,130,246,0.18)';
    dom.locMapBtn.style.fontWeight = 'bold';
    dom.locMapBtn.style.fontSize = '1.7em';
    dom.locMapBtn.title = 'Vis posisjon og AO-lokaliteter i kart';
    dom.locMapBtn.classList.add('map-btn-active');
  } else {
    dom.locMapBtn.style.display = 'none';
    dom.locMapBtn.classList.remove('map-btn-active');
  }
}

// Gjør funksjonen globalt tilgjengelig for andre moduler (f.eks. location.js)
window.updateMapBtnVisibility = updateMapBtnVisibility;

  if (dom.aoSizeInput) {
    const aoSizeValueEl = document.getElementById('ao-size-value');
    const renderRadiusValue = (v) => {
      if (aoSizeValueEl) aoSizeValueEl.textContent = formatRadius(v);
    };

    // Last lagret radius fra localStorage
    const savedRadius = loadAoSearchRadius();
    dom.aoSizeInput.value = savedRadius;
    appState.currentAoSizeMeters = savedRadius;
    renderRadiusValue(savedRadius);

    dom.aoSizeInput.addEventListener('input', () => {
      const v = parseFloat(dom.aoSizeInput.value);
      if (isNaN(v) || v <= 0) return;
      appState.currentAoSizeMeters = v;
      saveAoSearchRadius(v);
      renderRadiusValue(v);
    });
  }

  if (dom.exportBtn) dom.exportBtn.addEventListener('click', () => handleExport(appState.observations, dom));
  if (dom.copyBtn) dom.copyBtn.addEventListener('click', () => handleCopy(appState.observations, dom));
  if (dom.copyOpenBtn) dom.copyOpenBtn.addEventListener('click', () => handleCopyAndOpen(appState.observations, dom));
  if (dom.shareBtn) dom.shareBtn.addEventListener('click', () => openShareDialog(appState.observations));
  if (dom.clearBtn) dom.clearBtn.addEventListener('click', () => handleClear(appState.observations, dom, callbacks));
  if (dom.aoDirectBtn) dom.aoDirectBtn.addEventListener('click', () => handleDirectSend(appState.observations, dom, callbacks));
}

// ============================================================
// Initialisering
// ============================================================
async function init() {
  loadState();

  if (dom.placeInput && !dom.placeInput.value) {
    dom.placeInput.value = '';
    appState.currentPlaceName = '';
  }

  // Sjekk om bruker har valgt lokalitet fra kartet
  const selectedLocation = localStorage.getItem('selectedLocation');
  if (selectedLocation) {
    avsluttEtterregistrering();
    appState.currentPlaceName = selectedLocation;
    const selectedLocationId = localStorage.getItem('selectedLocationId');
    appState.currentPlaceId = selectedLocationId ? parseInt(selectedLocationId, 10) || selectedLocationId : null;
    if (dom.placeInput) {
      dom.placeInput.value = selectedLocation;
      dom.placeInput.dataset.autofilled = 'true';
    }
    localStorage.removeItem('selectedLocation');
    localStorage.removeItem('selectedLocationId');
  }

  setupEventListeners();

  if (dom.placeInput && !autocompleteCleanup) {
    autocompleteCleanup = initAutocomplete(
      dom.placeInput,
      (name, id) => {
        avsluttEtterregistrering();
        appState.currentPlaceName = name;
        appState.currentPlaceId = id;
        dom.placeInput.dataset.autofilled = 'true';
        updateSectionStates(appState, dom);
        collapseLocation();
      },
      () => appState.currentPosition
    );
  }

  updateSectionStates(appState, dom);

  // Gjenopprettet/sticky plass ved oppstart → vis festet kompakt linje
  if (dom.placeInput && dom.placeInput.value.trim()) {
    collapseLocation();
  }

  // Hvis lokalitet ble valgt fra kart, sett fokus på art-feltet
  if (selectedLocation) {
    pulseSearchFieldAndFocus(appState, dom);
  }

  initLocation(
    { locBtn: dom.locBtn, locMapBtn: dom.locMapBtn, locDot: dom.locDot, locText: dom.locText },
    handlePositionUpdate,
    appState.currentAoSizeMeters
  );

  // Initialiser opprett-lokasjon-funksjonalitet
  initCreateSite(
    () => appState.currentPosition,
    () => appState.currentPlaceName,
    () => {
      // Re-hent AO-sites etter opprettelse
      if (appState.currentPosition) {
        fetchAoSites(appState.currentPosition.lat, appState.currentPosition.lon, appState.currentAoSizeMeters)
          .then(sites => handlePositionUpdate(appState.currentPosition, sites))
          .catch(() => {});
      }
    }
  );

  doRenderObservations();

  try {
    const activities = await loadActivities();
    activities.forEach(a => {
      const opt = document.createElement('option');
      opt.value = a.value;
      opt.textContent = a.label;
      if (a.selected) opt.selected = true;
      dom.activitySelect.appendChild(opt);
    });
    renderActivityPills(dom, commitFromActivity);
  } catch (e) {
    console.error('Kunne ikke laste aktiviteter:', e);
  }

  logPageView();
  initNewsSplash();
  initFirstRunHint();
}

/**
 * Oppdater UI for modus-pill (Felt vs Etterregistrering)
 */
function updateModeUI() {
  const modePill = document.getElementById('mode-pill');
  const datetimeFields = document.getElementById('datetime-fields');
  const obsDateInput = document.getElementById('obs-date');
  const obsTimeInput = document.getElementById('obs-time');

  // GPS-relaterte rader
  const locStatusRow = document.getElementById('loc-status-row');
  const gpsControlsRow = document.getElementById('gps-controls-row');
  const radiusRow = document.getElementById('radius-row');
  const aoSitesDropdown = document.getElementById('ao-sites-dropdown');

  if (!modePill || !datetimeFields) return;

  const isAfterMode = localStorage.getItem('afterRegistrationMode') === '1';

  if (isAfterMode) {
    modePill.textContent = 'Etterregistrering';
    modePill.className = 'pill mode-pill after-mode';
    datetimeFields.style.display = 'block';

    // Skjul GPS-relaterte rader
    if (locStatusRow) locStatusRow.style.display = 'none';
    if (gpsControlsRow) gpsControlsRow.style.display = 'none';
    if (radiusRow) radiusRow.style.display = 'none';
    if (aoSitesDropdown) aoSitesDropdown.style.display = 'none';

    // Sett dagens dato som default
    const today = new Date();
    const yyyy = today.getFullYear();
    const mm = String(today.getMonth() + 1).padStart(2, '0');
    const dd = String(today.getDate()).padStart(2, '0');
    if (obsDateInput) obsDateInput.value = `${yyyy}-${mm}-${dd}`;
    if (obsTimeInput) obsTimeInput.value = ''; // Ingen tid som default
    const obsTimeToInput = document.getElementById('obs-time-to');
    if (obsTimeToInput) obsTimeToInput.value = ''; // Clear "til"-tid
  } else {
    modePill.textContent = 'Felt';
    modePill.className = 'pill mode-pill field-mode';
    datetimeFields.style.display = 'none';

    // Vis GPS-relaterte rader
    if (locStatusRow) locStatusRow.style.display = 'flex';
    if (gpsControlsRow) gpsControlsRow.style.display = 'flex';
    if (radiusRow) radiusRow.style.display = 'flex';
    // aoSitesDropdown styres av egen logikk
  }
}

/**
 * Setup modus-toggle event listener
 */
function setupModeToggle() {
  const modePill = document.getElementById('mode-pill');
  if (!modePill) return;

  modePill.addEventListener('click', () => {
    const current = localStorage.getItem('afterRegistrationMode') === '1';
    if (current) {
      localStorage.removeItem('afterRegistrationMode');
    } else {
      localStorage.setItem('afterRegistrationMode', '1');
    }
    updateModeUI();
  });
}

window.addEventListener('DOMContentLoaded', () => {
  updateSubtaxaCheckboxState();
  init();
  updateMapBtnVisibility();
  updateModeUI();
  setupModeToggle();
  updateAoDirectVisibility();

  // Hent private lokasjoner i bakgrunnen hvis cache mangler eller er utdatert
  if (getCachedPrivateSites().length === 0) {
    const tokens = JSON.parse(localStorage.getItem('ao_tokens') || '{}');
    if (tokens.authCookie) {
      fetchAndCachePrivateSites();
    }
  }
});
