/**
 * Location-modul for geolokasjon og AO-sites
 */


import { fetchAoSites, createAoSite, getCachedPrivateSites, ensureAoTokens } from './api.js';
import { setLocationStatus, haversine } from './ui.js';


/**
 * Sjekk om et site er privat
 * @param {Object} site - Site-objekt
 * @returns {boolean} - true hvis privat
 */
export function isPrivateSite(site) {
  if (!site || typeof site !== 'object') return false;
  
  const raw = site.raw && typeof site.raw === 'object' ? site.raw : site;
  if (!raw || typeof raw !== 'object') return false;

  // Bruk isPrivate-flagget fra AO. Kun eksplisitt true / "true" er privat.
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
 * Hent navn på site
 * @param {Object} site - Site-objekt
 * @returns {string} - Site-navn
 */
export function getSiteLabel(site) {
  if (!site || typeof site !== 'object') return '';
  
  // Bruk konsekvent "name" fra AO som lokalitetsnavn
  if (typeof site.name === 'string' && site.name.trim()) {
    return site.name.trim();
  }
  
  const raw = site.raw && typeof site.raw === 'object' ? site.raw : site;
  if (raw && typeof raw.name === 'string' && raw.name.trim()) {
    return raw.name.trim();
  }
  
  return '';
}

/**
 * Hent kommune (evt. fylke) for et site
 * @param {Object} site - Site-objekt
 * @returns {string} - Kommunenavn, eller tom streng
 */
export function getSiteMunicipality(site) {
  if (!site || typeof site !== 'object') return '';

  const raw = site.raw && typeof site.raw === 'object' ? site.raw : {};
  const value = site.municipality || raw.municipalityName
    || site.county || raw.countyName;

  return typeof value === 'string' ? value.trim() : '';
}

/**
 * Sett AO-site forslag i dropdown
 * @param {Array} sites - Liste med sites
 * @param {Object} currentPosition - Nåværende posisjon {lat, lon}
 * @param {HTMLElement} dropdown - Dropdown-element
 * @param {HTMLElement} aoSitesEl - AO-sites info-element
 * @param {HTMLInputElement} placeInput - Stedsnavn input-felt
 * @param {Function} setCurrentPlace - Callback for å sette nåværende sted
 * @returns {Array} - Oppdatert liste med sites
 */
export function setAoSiteSuggestions(sites, currentPosition, dropdown, aoSitesEl, placeInput, setCurrentPlace, searchRadiusMeters) {
  console.log('currentPosition:', currentPosition);
  
  // Slå sammen bbox-sites med cachet liste over mine private lokasjoner
  const bboxSites = Array.isArray(sites) ? sites : [];
  const cachedPrivate = getCachedPrivateSites();
  const cachedIds = new Set(cachedPrivate.map(s => s.id));

  // Marker bbox-sites som isMine hvis de finnes i cachen
  const markedBbox = bboxSites.map(s => {
    if (!s.isMine && s.id != null && cachedIds.has(s.id)) {
      return { ...s, isMine: true };
    }
    return s;
  });

  // Legg til cachet private lokasjoner som ikke er innenfor bbox, men kun de nærmeste
  const bboxIds = new Set(bboxSites.map(s => s.id).filter(id => id != null));
  const userLat0 = currentPosition && typeof currentPosition.lat === 'number' ? currentPosition.lat : null;
  const userLon0 = currentPosition && typeof currentPosition.lon === 'number' ? currentPosition.lon : null;
  const extraPrivate = cachedPrivate
    .filter(s => !bboxIds.has(s.id))
    .map(s => {
      let dist = null;
      if (userLat0 != null && userLon0 != null && s.lat != null && s.lon != null) {
        dist = haversine(userLat0, userLon0, parseFloat(s.lat), parseFloat(s.lon));
      }
      return { ...s, isMine: true, isPrivate: true, _distance: dist };
    })
    .filter(s => s._distance != null && s._distance <= (searchRadiusMeters || 5000))
    .sort((a, b) => (a._distance ?? Infinity) - (b._distance ?? Infinity))
    .slice(0, 5);

  const currentAoSites = [...markedBbox, ...extraPrivate];

  if (!dropdown) return currentAoSites;
  
  dropdown.innerHTML = '';
  dropdown.style.display = 'block';
  aoSitesEl.style.display = 'none';

  if (!currentAoSites.length) {
    dropdown.style.display = 'none';
    aoSitesEl.innerHTML = 'Ingen lokasjoner fra Artsobservasjoner i nærheten.';
    aoSitesEl.style.display = 'block';
    return currentAoSites;
  }

  // Sorter: mine private > superlokasjon > offentlig > privat, deretter på avstand
  const userLat = currentPosition && typeof currentPosition.lat === 'number' ? currentPosition.lat : null;
  const userLon = currentPosition && typeof currentPosition.lon === 'number' ? currentPosition.lon : null;
  
  if (userLat == null || userLon == null) {
    aoSitesEl.innerHTML = 'Kan ikke vise avstand til lokasjoner fordi posisjonen til enheten ikke er tilgjengelig. Godta posisjonsdeling i nettleseren.';
    aoSitesEl.style.display = 'block';
  }
  
  const withDist = currentAoSites.map(site => {
    let dist = null;
    const lat = parseFloat(site.lat);
    const lon = parseFloat(site.lon);
    if (userLat != null && userLon != null && !isNaN(lat) && !isNaN(lon)) {
      dist = haversine(userLat, userLon, lat, lon);
    }
    return { ...site, _distance: dist };
  });
  
  withDist.sort((a, b) => {
    // 1. Mine egne private først
    if ((a.isMine ? 1 : 0) !== (b.isMine ? 1 : 0)) return (b.isMine ? 1 : 0) - (a.isMine ? 1 : 0);
    // 2. Superlokasjon først
    if ((a.isSuper ? 1 : 0) !== (b.isSuper ? 1 : 0)) return (b.isSuper ? 1 : 0) - (a.isSuper ? 1 : 0);
    // 3. Offentlig før privat
    if (isPrivateSite(a) !== isPrivateSite(b)) return isPrivateSite(a) - isPrivateSite(b);
    // 4. Nærmest først
    if (a._distance != null && b._distance != null) return a._distance - b._distance;
    return 0;
  });

  // Maks 20 elementer
  const visibleSites = withDist.filter(s => s && typeof s.name === 'string' && s.name.trim()).slice(0, 20);

  
  if (!visibleSites.length) {
    dropdown.style.display = 'none';
    aoSitesEl.innerHTML = 'Ingen lokasjoner fra Artsobservasjoner i nærheten.';
    aoSitesEl.style.display = 'block';
    return currentAoSites;
  }

  // Legg til en tom "Velg lokasjon"-rad
  const emptyDiv = document.createElement('div');
  emptyDiv.className = 'ao-site-suggestion ao-site-empty';
  emptyDiv.textContent = 'Velg lokasjon...';
  emptyDiv.style.color = 'var(--muted)';
  emptyDiv.style.cursor = 'default';
  dropdown.appendChild(emptyDiv);

  visibleSites.forEach((site) => {
    const item = document.createElement('div');
    item.className = 'ao-site-suggestion';
    item.style.display = 'flex';
    item.style.justifyContent = 'space-between';
    item.style.alignItems = 'center';
    item.style.gap = '8px';

    // Tekstdel
    const textSpan = document.createElement('div');
    textSpan.className = 'ao-site-text';
    textSpan.style.flex = '1';

    let label = getSiteLabel(site) || site.name;
    if (site.isMine) label = '⭐ ' + label;
    if (site.isSuper) label = '🏷️ ' + label;
    if (isPrivateSite(site)) label = '👤 ' + label;

    let distStr = '';
    if (site._distance != null) {
      distStr = site._distance < 1000
        ? ` (${Math.round(site._distance)} m)`
        : ` (${(site._distance / 1000).toFixed(1)} km)`;
    }

    label = label + distStr;
    textSpan.textContent = label;
    textSpan.tabIndex = 0;

    // Kommune som undertekst — skiller lokaliteter med samme navn
    const municipality = getSiteMunicipality(site);
    if (municipality) {
      const subText = document.createElement('div');
      subText.textContent = municipality;
      subText.style.cssText = 'font-size: 0.75em; color: var(--muted);';
      textSpan.appendChild(subText);
    }

    const selectSite = () => {
      const name = getSiteLabel(site) || site.name;
      const siteId = site.id || null;
      setCurrentPlace(name, siteId);
      if (placeInput) {
        placeInput.value = name;
        placeInput.dataset.autofilled = 'true';
      }
      dropdown.style.display = 'none';
    };

    textSpan.addEventListener('click', selectSite);
    textSpan.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        selectSite();
      }
    });

    // Hover-effekt på rad
    item.addEventListener('mouseenter', () => {
      item.style.background = 'rgba(59, 130, 246, 0.1)';
      item.style.borderColor = 'rgba(59, 130, 246, 0.3)';
    });
    item.addEventListener('mouseleave', () => {
      item.style.background = 'transparent';
      item.style.borderColor = 'transparent';
    });

    // Kartknapp
    const mapBtn = document.createElement('button');
    mapBtn.textContent = '🗺️';
    mapBtn.title = 'Vis i kart';
    mapBtn.style.cssText = `
      background: transparent;
      border: 1px solid rgba(148, 163, 184, 0.3);
      border-radius: 6px;
      padding: 4px 8px;
      cursor: pointer;
      font-size: 1rem;
      opacity: 0.7;
      transition: all 0.2s;
      flex-shrink: 0;
    `;

    mapBtn.addEventListener('mouseenter', () => {
      mapBtn.style.opacity = '1';
      mapBtn.style.background = 'rgba(59, 130, 246, 0.15)';
      mapBtn.style.borderColor = 'rgba(59, 130, 246, 0.6)';
    });

    mapBtn.addEventListener('mouseleave', () => {
      mapBtn.style.opacity = '0.7';
      mapBtn.style.background = 'transparent';
      mapBtn.style.borderColor = 'rgba(148, 163, 184, 0.3)';
    });

    mapBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      openMapWithTwoPoints(currentPosition, { lat: site.lat, lon: site.lon }, getSiteLabel(site) || site.name);
    });

    item.appendChild(textSpan);
    item.appendChild(mapBtn);
    dropdown.appendChild(item);
  });
  
  return currentAoSites;
}

/**
 * Initialiser geolokasjon
 * @param {Object} elements - Objekt med DOM-elementer
 * @param {Function} onPositionUpdate - Callback når posisjon er oppdatert
 * @param {number} aoSizeMeters - Radius for AO-sites søk
 */
export function initLocation(elements, onPositionUpdate, aoSizeMeters = 1000) {
  const { locBtn, locMapBtn, locDot, locText } = elements;
  
  console.log('[initLocation] Kalles');
  
  if (!locBtn) {
    console.warn('[initLocation] Fant ikke #loc-btn');
    return;
  }
  
  console.log('[initLocation] Fant #loc-btn, setter event-listener');
  
  if (!navigator.geolocation) {
    setLocationStatus(locDot, locText, 'error', 'Ingen geolokasjon-støtte i denne nettleseren.');
    return;
  }

  // Gjenopprett lagret status fra localStorage hvis tilgjengelig
  try {
    const savedStatus = localStorage.getItem('locationStatus');
    if (savedStatus) {
      const { mode, text } = JSON.parse(savedStatus);
      // Gjenopprett status uten å oppdatere klokkeslett
      if (locText) locText.textContent = text;
      if (locDot) {
        if (mode === 'ok') {
          locDot.style.background = '#22c55e';
        } else if (mode === 'error') {
          locDot.style.background = '#ef4444';
        } else {
          locDot.style.background = '#6b7280';
        }
      }
    } else {
      setLocationStatus(locDot, locText, 'idle', 'Trykk «Bruk GPS» før registrering.');
    }
  } catch (e) {
    // Hvis localStorage feiler, bruk default
    setLocationStatus(locDot, locText, 'idle', 'Trykk «Bruk GPS» før registrering.');
  }

  locBtn.addEventListener('click', () => {
    console.log('[loc-btn] Klikk registrert, starter geolokasjon');
    setLocationStatus(locDot, locText, 'pending', 'Henter lokasjon …');
    locBtn.disabled = true;

    // Les radius direkte fra inputfeltet hvis det finnes
    let effectiveAoSize = aoSizeMeters;
    const aoSizeInput = document.getElementById('ao-size');
    if (aoSizeInput) {
      const v = parseFloat(aoSizeInput.value);
      if (!isNaN(v) && v > 0) {
        effectiveAoSize = v;
      }
    }

    let bestPosition = null;
    let finished = false;
    let watchId = null;

    async function finish() {
      if (finished) return;
      finished = true;
      if (watchId !== null) navigator.geolocation.clearWatch(watchId);
      clearTimeout(timeoutId);

      if (!bestPosition) {
        console.warn('Ingen GPS-fix mottatt innen tidsfrist');
        setLocationStatus(locDot, locText, 'error', 'Kunne ikke hente lokasjon. Sjekk tillatelser og prøv igjen.');
        onPositionUpdate(null, []);
        if (locMapBtn) {
          locMapBtn.style.display = 'none';
        }
        if (typeof updateMapBtnVisibility === 'function') updateMapBtnVisibility();
        locBtn.disabled = false;
        return;
      }

      const { lat, lon, accuracy } = bestPosition;
      const latStr = lat.toFixed(5);
      const lonStr = lon.toFixed(5);
      const accStr = Math.round(accuracy);

      setLocationStatus(locDot, locText, 'ok', `Lokasjon hentet (±${accStr} m)`);

      if (locText) {
        locText.title = `${latStr}, ${lonStr} (±${accStr} m)`;
      }

      try {
        const sites = await fetchAoSites(lat, lon, effectiveAoSize);
        onPositionUpdate(bestPosition, sites);
      } catch (err) {
        console.warn('Feil ved henting av AO-lokaliteter', err);
        onPositionUpdate(bestPosition, []);
      }

      if (locMapBtn) {
        locMapBtn.style.display = 'block';
      }
      if (typeof updateMapBtnVisibility === 'function') updateMapBtnVisibility();
      locBtn.disabled = false;
    }

    function startHighAccuracyWatch() {
      watchId = navigator.geolocation.watchPosition(
        (pos) => {
          const accuracy = pos.coords.accuracy;
          const candidate = {
            lat: pos.coords.latitude,
            lon: pos.coords.longitude,
            accuracy: accuracy,
          };

          if (!bestPosition || accuracy < bestPosition.accuracy) {
            bestPosition = candidate;
            console.log(`[loc] Nytt GPS-fix: ±${Math.round(accuracy)}m`);
          }

          setLocationStatus(locDot, locText, 'pending', `Henter lokasjon … ±${Math.round(accuracy)}m`);

          if (accuracy <= 50) {
            finish();
          }
        },
        (err) => {
          console.warn('Feil ved geolokasjon (watchPosition)', err);
          if (!bestPosition) {
            setLocationStatus(locDot, locText, 'error', 'Kunne ikke hente lokasjon. Sjekk tillatelser og prøv igjen.');
            onPositionUpdate(null, []);
            if (locMapBtn) {
              locMapBtn.style.display = 'none';
            }
            if (typeof updateMapBtnVisibility === 'function') updateMapBtnVisibility();
            locBtn.disabled = false;
            finished = true;
            clearTimeout(timeoutId);
          } else {
            finish();
          }
        },
        {
          enableHighAccuracy: true,
          maximumAge: 0,
          timeout: 30000,
        }
      );
    }

    // Steg 1: Vekk opp GPS-hardware med et raskt nettverksbasert kall (cell/WiFi).
    // Dette fikser et kjent problem på Samsung/Android Chrome der watchPosition
    // med maximumAge: 0 henger fordi GPS ikke er aktiv ennå — brukeren måtte
    // tidligere innom Google Maps for å "varme opp" GPS.
    // maximumAge: 0 sikrer at vi IKKE får gammel cachet posisjon (f.eks. hjemsted).
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        if (finished) return;
        const accuracy = pos.coords.accuracy;
        const candidate = {
          lat: pos.coords.latitude,
          lon: pos.coords.longitude,
          accuracy: accuracy,
        };
        // Kun bruk nettverksposisjonen som midlertidig visning, ikke som endelig svar.
        // GPS-watch nedenfor vil overstyre med ekte GPS-posisjon.
        bestPosition = candidate;
        console.log(`[loc] Nettverksposisjon (oppvarming): ±${Math.round(accuracy)}m — starter GPS-raffinering`);
        setLocationStatus(locDot, locText, 'pending', `Henter lokasjon … ±${Math.round(accuracy)}m`);
        // Steg 2: GPS-hardware er nå aktiv, start høy-nøyaktighets-watch
        startHighAccuracyWatch();
      },
      (err) => {
        if (finished) return;
        console.warn('[loc] Nettverksposisjon feilet, prøver direkte GPS-watch', err);
        // Fallback: prøv watchPosition direkte
        startHighAccuracyWatch();
      },
      {
        enableHighAccuracy: false,
        maximumAge: 0,
        timeout: 5000,
      }
    );

    const timeoutId = setTimeout(() => {
      console.log(`[loc] Timeout etter 10s, bruker beste posisjon (±${bestPosition ? Math.round(bestPosition.accuracy) + 'm' : 'ingen'})`);
      finish();
    }, 10000);
  });
}

/**
 * Åpne kart med nåværende posisjon
 * Bruker native kart-app på mobil (Apple Maps/Google Maps), Google Maps på desktop
 * @param {Object} position - Posisjon {lat, lon}
 */
export function openMap(position) {
  if (!position) return;

  const { lat, lon } = position;

  // Detekter plattform
  const ua = navigator.userAgent || '';
  const isIOS = /iPhone|iPad|iPod/.test(ua);
  const isAndroid = /Android/.test(ua);

  let url;

  if (isIOS) {
    // Apple Maps på iOS
    url = `https://maps.apple.com/?q=${encodeURIComponent(lat)},${encodeURIComponent(lon)}&ll=${encodeURIComponent(lat)},${encodeURIComponent(lon)}&z=16`;
  } else if (isAndroid) {
    // Google Maps på Android
    url = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(lat)},${encodeURIComponent(lon)}`;
  } else {
    // Desktop: Google Maps
    url = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(lat)},${encodeURIComponent(lon)}`;
  }

  window.open(url, '_blank', 'noopener');
}

/**
 * Åpne kartside med brukerposisjon og alle AO-lokaliteter
 * @param {Object} userPosition - Brukerens posisjon {lat, lon, accuracy}
 * @param {Array} sites - Liste med AO-lokaliteter
 */
export function openMapPage(userPosition, sites) {
  if (!userPosition || !userPosition.lat || !userPosition.lon) {
    console.warn('openMapPage: Mangler brukerposisjon');
    return;
  }

  // Lagre data i localStorage
  const mapData = {
    userPosition: {
      lat: userPosition.lat,
      lon: userPosition.lon,
      accuracy: userPosition.accuracy
    },
    sites: sites || []
  };

  localStorage.setItem('mapData', JSON.stringify(mapData));

  // Åpne kartside
  window.open('/map.html', '_blank');
}

/**
 * Åpne kart med to punkter (egen posisjon og lokalitet)
 * Bruker native kart-app på mobil (Apple Maps/Google Maps), Google Maps på desktop
 * @param {Object} fromPos - Fra-posisjon {lat, lon}
 * @param {Object} toPos - Til-posisjon {lat, lon}
 * @param {string} locationName - Navn på destinasjonen
 */
/**
 * Sjekk om bruker er innlogget på AO
 * @returns {boolean}
 */
export function isAoLoggedIn() {
  return !!(localStorage.getItem('ao_username') && localStorage.getItem('ao_password'));
}

/**
 * Oppdater synlighet av opprett-lokasjon-knappen
 * @param {Object} currentPosition - Nåværende posisjon {lat, lon}
 */
export function updateCreateSiteBtnVisibility(currentPosition) {
  const btn = document.getElementById('create-site-btn');
  if (!btn) return;

  const hasPosition = currentPosition && typeof currentPosition.lat === 'number';
  const loggedIn = isAoLoggedIn();

  btn.style.display = (hasPosition && loggedIn) ? '' : 'none';
}

/**
 * Initialiser opprett-lokasjon-funksjonalitet
 * @param {Function} getPosition - Funksjon som returnerer nåværende posisjon
 * @param {Function} getPlaceName - Funksjon som returnerer nåværende stedsnavn
 * @param {Function} onSiteCreated - Callback etter vellykket opprettelse
 */
export function initCreateSite(getPosition, getPlaceName, onSiteCreated) {
  const btn = document.getElementById('create-site-btn');
  const modal = document.getElementById('create-site-modal');
  const nameInput = document.getElementById('create-site-name');
  const accuracySelect = document.getElementById('create-site-accuracy');
  const submitBtn = document.getElementById('create-site-submit');
  const cancelBtn = document.getElementById('create-site-cancel');
  const statusEl = document.getElementById('create-site-status');

  const mapImg = document.getElementById('create-site-map');

  if (!btn || !modal) return;

  function openModal() {
    nameInput.value = getPlaceName() || '';
    statusEl.style.display = 'none';
    submitBtn.disabled = false;

    // Vis kartbilde fra OSM tile
    const pos = getPosition();
    if (pos && mapImg) {
      const z = 15;
      const latRad = pos.lat * Math.PI / 180;
      const tileX = Math.floor((pos.lon + 180) / 360 * Math.pow(2, z));
      const tileY = Math.floor((1 - Math.log(Math.tan(latRad) + 1 / Math.cos(latRad)) / Math.PI) / 2 * Math.pow(2, z));
      mapImg.src = `https://tile.openstreetmap.org/${z}/${tileX}/${tileY}.png`;
    }

    modal.style.display = 'flex';
  }

  function closeModal() {
    modal.style.display = 'none';
  }

  function showStatus(msg, isError) {
    statusEl.textContent = msg;
    statusEl.style.display = 'block';
    statusEl.style.background = isError ? 'rgba(239,68,68,0.15)' : 'rgba(34,197,94,0.15)';
    statusEl.style.color = isError ? '#ef4444' : '#22c55e';
  }

  btn.addEventListener('click', openModal);
  cancelBtn.addEventListener('click', closeModal);

  // Lukk ved klikk på bakgrunn
  modal.addEventListener('click', (e) => {
    if (e.target === modal) closeModal();
  });

  submitBtn.addEventListener('click', async () => {
    const name = nameInput.value.trim();
    if (!name) {
      showStatus('Skriv inn et lokalitetsnavn', true);
      return;
    }

    const pos = getPosition();
    if (!pos || !pos.lat || !pos.lon) {
      showStatus('Ingen GPS-posisjon tilgjengelig', true);
      return;
    }

    submitBtn.disabled = true;
    showStatus('Logger inn på AO...', false);

    try {
      const loggedIn = await ensureAoTokens();
      if (!loggedIn) {
        showStatus('Innlogging feilet. Sjekk brukernavn/passord i innstillinger.', true);
        submitBtn.disabled = false;
        return;
      }

      showStatus('Oppretter lokasjon...', false);
      const result = await createAoSite(name, pos.lat, pos.lon, parseInt(accuracySelect.value));

      if (result.success) {
        showStatus(result.message || 'Lokasjon opprettet!', false);
        setTimeout(() => {
          closeModal();
          if (onSiteCreated) onSiteCreated();
        }, 1500);
      } else {
        showStatus(result.message || result.error || 'Ukjent feil', true);
        submitBtn.disabled = false;
      }
    } catch (e) {
      showStatus('Nettverksfeil: ' + e.message, true);
      submitBtn.disabled = false;
    }
  });
}

export function openMapWithTwoPoints(fromPos, toPos, locationName = 'Lokalitet') {
  if (!fromPos || !toPos) {
    console.warn('openMapWithTwoPoints: Mangler posisjon(er)');
    return;
  }

  const fromLat = fromPos.lat;
  const fromLon = fromPos.lon;
  const toLat = parseFloat(toPos.lat);
  const toLon = parseFloat(toPos.lon);

  if (isNaN(toLat) || isNaN(toLon)) {
    console.warn('openMapWithTwoPoints: Ugyldig til-posisjon', toPos);
    return;
  }

  // Detekter plattform
  const ua = navigator.userAgent || '';
  const isIOS = /iPhone|iPad|iPod/.test(ua);
  const isAndroid = /Android/.test(ua);

  let url;

  if (isIOS) {
    // Apple Maps på iOS - støtter directions med saddr og daddr
    url = `https://maps.apple.com/?saddr=${encodeURIComponent(fromLat)},${encodeURIComponent(fromLon)}&daddr=${encodeURIComponent(toLat)},${encodeURIComponent(toLon)}&dirflg=d`;
  } else if (isAndroid) {
    // Google Maps på Android - bruker saddr og daddr for directions
    url = `https://www.google.com/maps/dir/?api=1&origin=${encodeURIComponent(fromLat)},${encodeURIComponent(fromLon)}&destination=${encodeURIComponent(toLat)},${encodeURIComponent(toLon)}&travelmode=driving`;
  } else {
    // Desktop: Google Maps directions
    url = `https://www.google.com/maps/dir/?api=1&origin=${encodeURIComponent(fromLat)},${encodeURIComponent(fromLon)}&destination=${encodeURIComponent(toLat)},${encodeURIComponent(toLon)}&travelmode=driving`;
  }

  window.open(url, '_blank', 'noopener');
}
