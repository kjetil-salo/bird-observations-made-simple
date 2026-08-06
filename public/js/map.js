/**
 * Kart-modul for visning av brukerposisjon og AO-lokaliteter
 */

import { createAoSite, ensureAoTokens } from './api.js';
import { haversine } from './utils.js';

// Hent data fra localStorage
const mapData = localStorage.getItem('mapData');
if (!mapData) {
  document.body.innerHTML = '<div style="padding: 20px; color: white;">Ingen kartdata tilgjengelig. <a href="/" style="color: #3b82f6;">Gå tilbake</a></div>';
  throw new Error('Ingen kartdata i localStorage');
}

const data = JSON.parse(mapData);
const { userPosition, sites } = data;
console.log('mapData sites-array:', sites);

if (!userPosition || !userPosition.lat || !userPosition.lon) {
  document.body.innerHTML = '<div style="padding: 20px; color: white;">Ugyldig posisjon. <a href="/" style="color: #3b82f6;">Gå tilbake</a></div>';
  throw new Error('Ugyldig brukerposisjon');
}

// Initialiser kart sentrert på brukerens posisjon
const map = L.map('map').setView([userPosition.lat, userPosition.lon], 13);

// Kartlag å velge mellom
const osmLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  maxZoom: 19
});

const kartverketTopoLayer = L.tileLayer('https://cache.kartverket.no/v1/wmts/1.0.0/topo/default/webmercator/{z}/{y}/{x}.png', {
  attribution: '© <a href="https://www.kartverket.no/">Kartverket</a>',
  maxZoom: 18
});

const kartverketGrayscaleLayer = L.tileLayer('https://cache.kartverket.no/v1/wmts/1.0.0/topograatone/default/webmercator/{z}/{y}/{x}.png', {
  attribution: '© <a href="https://www.kartverket.no/">Kartverket</a>',
  maxZoom: 18
});

osmLayer.addTo(map);

L.control.layers({
  'OpenStreetMap': osmLayer,
  'Kartverket Topo': kartverketTopoLayer,
  'Kartverket Gråtone': kartverketGrayscaleLayer
}, null, { position: 'bottomleft', collapsed: true }).addTo(map);

// Marker for brukerens posisjon
const userMarker = L.circleMarker([userPosition.lat, userPosition.lon], {
  color: '#3b82f6',
  fillColor: '#3b82f6',
  fillOpacity: 0.8,
  radius: 10,
  weight: 3
}).addTo(map);

let popupContent = '<strong>📍 Din posisjon</strong>';
if (userPosition.accuracy) {
  popupContent += `<br>Nøyaktighet: ±${Math.round(userPosition.accuracy)} m`;
}
userMarker.bindPopup(popupContent);

// Legg til alle markers i en bounds for auto-zoom
const bounds = L.latLngBounds([[userPosition.lat, userPosition.lon]]);

// Filtrer og legg til AO-lokaliteter
let siteCount = 0;
if (sites && Array.isArray(sites)) {
  // Logging: vis alle sites med isMine=true
  const mineSites = sites.filter(s => s.isMine);
  if (mineSites.length > 0) {
    console.log('Mine lokasjoner (isMine=true):', mineSites.map(s => ({ name: s.name, id: s.id, lat: s.lat, lon: s.lon })));
  } else {
    console.log('Ingen egne lokasjoner (isMine=true) funnet i sites-array.');
  }

  sites.forEach(site => {
    // Sjekk om site er privat
    const isPrivate = isPrivateSite(site);
    const showPrivateSites = localStorage.getItem('showPrivateSitesOnMap') === '1'; // av som standard
    // Private lokasjoner vises på kartet hvis de er mine, eller hvis innstillingen er på
    if (isPrivate && !site.isMine && !showPrivateSites) {
      return; // Hopp over private som ikke er mine (med mindre innstillingen er på)
    }

    const lat = parseFloat(site.lat);
    const lon = parseFloat(site.lon);
    if (isNaN(lat) || isNaN(lon)) {
      return;
    }

    // Bestem farger basert på type
    let markerColor, polygonColor;
    if (site.isMine) {
      markerColor = 'yellow';
      polygonColor = '#eab308';  // Gul
    } else if (isPrivate) {
      markerColor = 'grey';
      polygonColor = '#9ca3af';  // Grå — andres private, dempet
    } else if (site.isSuper) {
      markerColor = 'orange';
      polygonColor = '#f97316';  // Oransje
    } else {
      markerColor = 'green';
      polygonColor = '#22c55e';  // Grønn
    }

    // Tegn polygon hvis det er en polygon-lokalitet
    if (site.raw && site.raw.isPolygon && site.raw.polygonCoordinates) {
      const coords = site.raw.polygonCoordinates;
      if (coords && coords.length > 0) {
        // ByBoundingBox returnerer [lon, lat], Leaflet trenger [lat, lon] - må bytte om
        const leafletCoords = coords.map(coord => [coord[1], coord[0]]);

        L.polygon(leafletCoords, {
          color: polygonColor,
          weight: 2,
          opacity: 0.8,
          fillColor: polygonColor,
          fillOpacity: 0.15
        }).addTo(map);
      }
    }

    // Marker i senter (alltid, uavhengig av om det er polygon)
    const markerIconUrl = `https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-${markerColor}.png`;
    const marker = L.marker([lat, lon], {
      icon: L.icon({
        iconUrl: markerIconUrl,
        shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png',
        iconSize: [25, 41],
        iconAnchor: [12, 41],
        popupAnchor: [1, -34],
        shadowSize: [41, 41]
      })
    }).addTo(map);

    // Navn for visning
    const siteName = site.name || 'Ukjent lokalitet';
    let displayName = site.isSuper ? `🏷️ ${siteName}` : siteName;
    if (site.isMine) displayName = `★ ${siteName}`;

    // Beregn avstand
    const distance = haversine(userPosition.lat, userPosition.lon, lat, lon);
    let distStr = '';
    if (distance !== null) {
      distStr = distance < 1000
        ? `${Math.round(distance)} m`
        : `${(distance / 1000).toFixed(1)} km`;
    }

    // Popup med detaljert info (vises ved klikk)
    let popupHtml = `<strong>${displayName}</strong>`;
    if (distStr) {
      popupHtml += `<br>Avstand: ${distStr}`;
    }
    const siteIdStr = site.id != null ? String(site.id) : '';
    popupHtml += `<br><br><button onclick="selectLocation('${siteName.replace(/'/g, "\\'")}', '${siteIdStr}')">Velg denne lokaliteten</button>`;
    marker.bindPopup(popupHtml);

    // Tooltip med navn (vises permanent)
    const tooltipText = distStr ? `${siteName} (${distStr})` : siteName;
    marker.bindTooltip(tooltipText, {
      permanent: true,
      direction: 'top',
      className: site.isMine ? 'site-label mine-label' : 'site-label',
      offset: [0, -35]
    });

    // Klikk på markør velger lokalitet
    marker.on('click', () => {
      selectLocation(siteName, site.id ?? null);
    });

    // Legg til i bounds
    bounds.extend([lat, lon]);
    siteCount++;
  });
}

// Zoom kartet til å vise alle markers
if (siteCount > 0) {
  map.fitBounds(bounds, { padding: [50, 50] });

  // Vis info-boks
  const infoBox = document.getElementById('info-box');
  const siteCountEl = document.getElementById('site-count');
  if (infoBox && siteCountEl) {
    siteCountEl.textContent = siteCount;
    infoBox.style.display = 'block';
  }
}

/**
 * Sjekk om et site er privat (samme logikk som location.js)
 * @param {Object} site - Site-objekt
 * @returns {boolean} - true hvis privat
 */
function isPrivateSite(site) {
  if (!site || typeof site !== 'object') return false;

  const raw = site.raw && typeof site.raw === 'object' ? site.raw : site;
  if (!raw || typeof raw !== 'object') return false;

  // Bruk isPrivate-flagget fra AO
  if (Object.prototype.hasOwnProperty.call(raw, 'isPrivate')) {
    const v = raw.isPrivate;
    if (v === true || v === 'true') return true;
    if (v === false || v === 'false') return false;
  }

  if (Object.prototype.hasOwnProperty.call(raw, 'IsPrivate')) {
    const v = raw.IsPrivate;
    if (v === true || v === 'true') return true;
    if (v === false || v === 'false') return false;
  }

  return false;
}

/**
 * Velg lokalitet og gå tilbake til hovedsiden
 * @param {string} locationName - Navn på valgt lokalitet
 * @param {string|number|null} locationId - AO-lokalitets-ID
 */
function selectLocation(locationName, locationId) {
  localStorage.setItem('selectedLocation', locationName);
  if (locationId != null) {
    localStorage.setItem('selectedLocationId', String(locationId));
  } else {
    localStorage.removeItem('selectedLocationId');
  }
  window.location.href = '/';
}

// Gjør selectLocation tilgjengelig globalt for onclick i popup
window.selectLocation = selectLocation;

// --- Opprett ny lokasjon (pin-drop) ---

const fab = document.getElementById('add-site-fab');
const hint = document.getElementById('pin-drop-hint');
const cancelPinBtn = document.getElementById('cancel-pin-btn');
const panel = document.getElementById('create-site-panel');
const nameInput = document.getElementById('new-site-name');
const accuracySelect = document.getElementById('new-site-accuracy');
const createBtn = document.getElementById('panel-create-btn');
const panelCancelBtn = document.getElementById('panel-cancel-btn');
const panelStatus = document.getElementById('panel-status');

// Vis FAB kun hvis bruker har AO-credentials
function hasAoCredentials() {
  return !!(localStorage.getItem('ao_username') && localStorage.getItem('ao_password'));
}
if (hasAoCredentials() && fab) {
  fab.style.display = '';
}

let pinDropMode = false;
let dropMarker = null;
let mapClickHandler = null;

function enterPinDropMode() {
  pinDropMode = true;
  fab.style.display = 'none';
  hint.style.display = 'block';
  cancelPinBtn.style.display = 'block';
  map.getContainer().style.cursor = 'crosshair';

  mapClickHandler = (e) => {
    // Plasser draggbar marker
    if (dropMarker) {
      map.removeLayer(dropMarker);
    }
    const redIcon = L.icon({
      iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-red.png',
      shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png',
      iconSize: [25, 41],
      iconAnchor: [12, 41],
      popupAnchor: [1, -34],
      shadowSize: [41, 41]
    });
    dropMarker = L.marker(e.latlng, { icon: redIcon, draggable: true }).addTo(map);
    hint.style.display = 'none';
    cancelPinBtn.style.display = 'none';

    // Fjern klikk-handler (kun én pin)
    map.off('click', mapClickHandler);

    // Vis opprett-panel
    openCreatePanel();
  };

  map.on('click', mapClickHandler);
}

function exitPinDropMode() {
  pinDropMode = false;
  hint.style.display = 'none';
  cancelPinBtn.style.display = 'none';
  panel.style.display = 'none';
  map.getContainer().style.cursor = '';

  if (mapClickHandler) {
    map.off('click', mapClickHandler);
    mapClickHandler = null;
  }
  if (dropMarker) {
    map.removeLayer(dropMarker);
    dropMarker = null;
  }

  // Vis FAB igjen
  if (hasAoCredentials() && fab) {
    fab.style.display = '';
  }
}

function openCreatePanel() {
  nameInput.value = '';
  panelStatus.style.display = 'none';
  createBtn.disabled = false;
  panel.style.display = 'block';
}

function showPanelStatus(msg, isError) {
  panelStatus.textContent = msg;
  panelStatus.style.display = 'block';
  panelStatus.style.background = isError ? 'rgba(239,68,68,0.15)' : 'rgba(34,197,94,0.15)';
  panelStatus.style.color = isError ? '#ef4444' : '#22c55e';
}

function addNewSiteMarker(name, lat, lon) {
  const yellowIcon = L.icon({
    iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-yellow.png',
    shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png',
    iconSize: [25, 41],
    iconAnchor: [12, 41],
    popupAnchor: [1, -34],
    shadowSize: [41, 41]
  });
  const marker = L.marker([lat, lon], { icon: yellowIcon }).addTo(map);
  marker.bindTooltip(`★ ${name}`, {
    permanent: true,
    direction: 'top',
    className: 'site-label mine-label',
    offset: [0, -35]
  });
  marker.bindPopup(`<strong>★ ${name}</strong><br><em>Nettopp opprettet</em>`);
}

// Event listeners
if (fab) {
  fab.addEventListener('click', enterPinDropMode);
}
if (cancelPinBtn) {
  cancelPinBtn.addEventListener('click', exitPinDropMode);
}
if (panelCancelBtn) {
  panelCancelBtn.addEventListener('click', exitPinDropMode);
}
if (createBtn) {
  createBtn.addEventListener('click', async () => {
    const name = nameInput.value.trim();
    if (!name) {
      showPanelStatus('Skriv inn et lokalitetsnavn', true);
      return;
    }
    if (!dropMarker) {
      showPanelStatus('Ingen posisjon valgt', true);
      return;
    }

    const latlng = dropMarker.getLatLng();
    createBtn.disabled = true;
    showPanelStatus('Logger inn på AO...', false);

    try {
      const loggedIn = await ensureAoTokens();
      if (!loggedIn) {
        showPanelStatus('Innlogging feilet. Sjekk brukernavn/passord i innstillinger.', true);
        createBtn.disabled = false;
        return;
      }

      showPanelStatus('Oppretter lokasjon...', false);
      const result = await createAoSite(name, latlng.lat, latlng.lng, parseInt(accuracySelect.value));

      if (result.success) {
        showPanelStatus(result.message || 'Lokasjon opprettet!', false);
        // Fjern rød marker, legg til gul
        if (dropMarker) {
          map.removeLayer(dropMarker);
          dropMarker = null;
        }
        addNewSiteMarker(name, latlng.lat, latlng.lng);

        setTimeout(() => {
          panel.style.display = 'none';
          pinDropMode = false;
          map.getContainer().style.cursor = '';
          if (fab) fab.style.display = '';
        }, 1500);
      } else {
        showPanelStatus(result.message || result.error || 'Ukjent feil', true);
        createBtn.disabled = false;
      }
    } catch (e) {
      showPanelStatus('Nettverksfeil: ' + e.message, true);
      createBtn.disabled = false;
    }
  });
}

