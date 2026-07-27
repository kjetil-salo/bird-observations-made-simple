"""
API handlers for fugleobservasjoner.

Håndterer eksterne API-kall til Artsobservasjoner og Nominatim.
"""

import json
import logging
import math
import re
import os
import threading
import time
from html import unescape
from urllib.parse import urlencode

import httpx

logger = logging.getLogger('fugleobs')

from src.utils import mask_token


# Import for å hente CSRF tokens
from src.ao_import_httpx import fetch_csrf_tokens


def fetch_ao_autocomplete(term: str, login_token: str = None, auth_cookie: str = None, user_id: str = None, location_db=None, lat: float = None, lon: float = None) -> dict:
    """
    Hent autocomplete-forslag for lokaliteter.

    Søker først i lokal DB (hvis tilgjengelig), deretter i AO (hvis innlogget).
    Uten innlogging returneres kun lokale resultater.

    Args:
        term: Søketekst (minimum 2-3 tegn)
        login_token: Optional logintoken cookie (for å inkludere private lokaliteter)
        auth_cookie: Optional .ASPXAUTHNO cookie (for å inkludere private lokaliteter)
        user_id: Optional bruker-ID (for auto-relogin)
        location_db: Optional LocationDB-instans for lokalt søk

    Returns:
        Dict med 'results' (liste) og 'refreshed_auth_cookie' (str eller None)
    """
    if not term or len(term) < 2:
        return {'results': [], 'refreshed_auth_cookie': None}

    # Søk i lokal DB først (alltid tilgjengelig, ingen innlogging nødvendig)
    local_results = []
    if location_db:
        try:
            local_sites = location_db.search_by_name(term, limit=20, lat=lat, lon=lon)
            # Konverter til AO autocomplete-format
            local_results = []
            for site in local_sites:
                parts = [p for p in [site.get('municipality'), site.get('county')] if p]
                entry = {
                    'id': site['id'],
                    'value': site['name'],
                    'presentationvalue': site['name'],
                    'subvalue': ', '.join(parts),
                    '_source': 'local_db',
                    'isSuper': site.get('isSuper', False),
                    'isPrivate': site.get('isPrivate', False),
                }
                if '_distance' in site:
                    entry['_distance'] = site['_distance']
                local_results.append(entry)
            logger.debug(f'[AO-AUTOCOMPLETE] Lokal DB: {len(local_results)} treff for "{term}"')
        except Exception as e:
            logger.warning(f'[AO-AUTOCOMPLETE] Lokal DB-søk feilet: {e}')

    refreshed_auth_cookie = None
    is_logged_in = bool(login_token and (auth_cookie or user_id))

    # Prøv AO bare hvis innlogget
    if not is_logged_in:
        if local_results:
            return {'results': local_results, 'refreshed_auth_cookie': None}
        return {'results': [], 'refreshed_auth_cookie': None, 'not_logged_in': True}

    # Sørg for gyldig auth (sliding expiration → logintoken → credentials)
    if user_id and login_token:
        auth_cookie, refreshed_auth_cookie = _ensure_auth(auth_cookie, user_id, login_token)

    base_url = os.getenv('AO_URL', 'https://www.artsobservasjoner.no')
    params = {
        'speciesGroupId': '8',  # Fugler
        'term': term,
        'searchSitesAlsoByExternalId': 'False'
    }

    url = f'{base_url}/Map/FindSitesByNameForAutocomplete?{urlencode(params)}'

    headers = {
        'User-Agent': 'Mozilla/5.0 (compatible; Fugleobservasjoner-Autocomplete/1.0)',
        'Accept': '*/*',
        'X-Requested-With': 'XMLHttpRequest',
        'Referer': f'{base_url}/SubmitSighting/Report'
    }

    # Legg til cookies hvis tilgjengelig (for private lokaliteter)
    if login_token and auth_cookie:
        headers['Cookie'] = f'logintoken={login_token}; .ASPXAUTHNO={auth_cookie}; AcceptCookies=1'

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(url, headers=headers, follow_redirects=True)
            response.raise_for_status()

            logger.debug(f'[AO-AUTOCOMPLETE] Status: {response.status_code}, Content-Type: {response.headers.get("content-type")}')

            # Sjekk om vi ble redirectet til innloggingssiden
            if '/LogOn' in str(response.url):
                logger.warning(f'[AO-AUTOCOMPLETE] Auth utløpt — redirectet til innloggingsside for term={term}')
                # Returner lokale resultater selv om AO-auth feilet
                if local_results:
                    return {'results': local_results, 'refreshed_auth_cookie': refreshed_auth_cookie, 'auth_expired': True}
                return {'results': [], 'refreshed_auth_cookie': refreshed_auth_cookie, 'auth_expired': True}

            # Sjekk om responsen er JSON
            content_type = response.headers.get('content-type', '')
            if 'application/json' not in content_type:
                logger.warning(f'[AO-AUTOCOMPLETE] Ikke-JSON respons. Første 500 tegn: {response.text[:500]}')
                return {'results': local_results, 'refreshed_auth_cookie': refreshed_auth_cookie}

            ao_results = response.json()

            # Merge: AO-resultater først, deretter lokale som ikke finnes i AO
            ao_ids = {r.get('id') for r in ao_results if r.get('id') is not None}
            merged = ao_results + [r for r in local_results if r['id'] not in ao_ids]

            return {'results': merged, 'refreshed_auth_cookie': refreshed_auth_cookie}
    except Exception as e:
        logger.error(f'[AO-AUTOCOMPLETE] Feil ved henting: {e}')
        # Ved AO-feil, returner lokale resultater
        return {'results': local_results, 'refreshed_auth_cookie': refreshed_auth_cookie}



# Sliding expiration cache for AO auth cookie (bruker-id -> (cookie, last_refresh_ts))
_ao_cookie_refresh_cache = {}
_AO_COOKIE_REFRESH_INTERVAL = 300  # 5 minutter (balanse mellom overhead og token-friskhet)

# Lock for trådsikker tilgang til alle cacher (ThreadingHTTPServer)
_cache_lock = threading.Lock()

# Filbasert credentials-lagring (overlever server-restart)
_CREDENTIALS_PATH = os.environ.get('CREDENTIALS_PATH', '/data/credentials.json')


def _load_credentials(user_id: str) -> tuple:
    """Last credentials fra disk. Returnerer (username, password) eller None."""
    try:
        with open(_CREDENTIALS_PATH, 'r') as f:
            data = json.load(f)
        entry = data.get(str(user_id))
        if entry:
            return (entry['username'], entry['password'])
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        pass
    return None


def _save_credentials(user_id: str, username: str, password: str):
    """Lagre credentials til disk (trådsikkert)."""
    try:
        os.makedirs(os.path.dirname(_CREDENTIALS_PATH), exist_ok=True)
        with _cache_lock:
            try:
                with open(_CREDENTIALS_PATH, 'r') as f:
                    data = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                data = {}
            data[str(user_id)] = {'username': username, 'password': password}
            with open(_CREDENTIALS_PATH, 'w') as f:
                json.dump(data, f)
    except Exception as e:
        logger.warning(f'[CREDENTIALS] Kunne ikke lagre credentials: {e}')

def _sliding_expiration(auth_cookie: str, user_id: str, login_token: str = None) -> str:
    """Forleng AO-session via sliding expiration (rate-limited).

    Treffer /User/MyPages med eksisterende cookie for å trigge fornyelse.
    Rate-limited til maks 1 gang per 5 minutter per bruker.

    Returns:
        Ny auth-cookie hvis AO fornyet, ellers None.
    """
    now = time.time()
    cache_key = f'{user_id}:{auth_cookie[:16]}'
    with _cache_lock:
        last_entry = _ao_cookie_refresh_cache.get(cache_key)
    if last_entry and now - last_entry[1] < _AO_COOKIE_REFRESH_INTERVAL:
        return None

    try:
        cookies = {'.ASPXAUTHNO': auth_cookie, 'AcceptCookies': '1'}
        if login_token:
            cookies['logintoken'] = login_token
            cookies['logintoken_ssl'] = '1'

        with httpx.Client(cookies=cookies) as client:
            response = client.get(
                'https://www.artsobservasjoner.no/User/MyPages',
                headers={'User-Agent': 'Mozilla/5.0 (compatible; Fugleobservasjoner/1.0)'},
                timeout=10,
                follow_redirects=True
            )

            # Finn ny .ASPXAUTHNO fra cookie jar
            new_auth = None
            for cookie in client.cookies.jar:
                if cookie.name == '.ASPXAUTHNO' and cookie.value != auth_cookie:
                    new_auth = cookie.value
                    break

            # Oppdater rate-limit uansett (unngå spam mot AO)
            with _cache_lock:
                _ao_cookie_refresh_cache[cache_key] = (new_auth or auth_cookie, now)

            # VIKTIG: Sjekk /LogOn-redirect FØR new_auth tolkes. Ved utløpt cookie
            # setter AO en logout/anonym .ASPXAUTHNO (forskjellig verdi) som ellers
            # feilaktig ville blitt returnert som en «fornyelse» og hoppet over relogin.
            if '/LogOn' in str(response.url):
                logger.debug('[SLIDING] Cookie utløpt (redirect til /LogOn)')
                return None

            if new_auth:
                logger.info(f'[SLIDING] Fikk ny auth-cookie: {mask_token(new_auth)}')
                return new_auth

            logger.info('[SLIDING] Cookie fortsatt gyldig, ingen fornyelse nødvendig')
            return None
    except Exception as e:
        logger.error(f'[SLIDING] Feil: {e}')
        return None


def login_to_ao(username: str, password: str) -> dict:
    """
    Logger inn på Artsobservasjoner med brukernavn/passord.

    Returnerer dict med:
    - authCookie: .ASPXAUTHNO cookie-verdi
    - loginToken: logintoken for "husk meg" (varer 1 år)
    - userId: bruker-ID

    Raises:
        ValueError: Ved ugyldig brukernavn/passord eller andre feil
    """
    logger.info(f'[AO-LOGIN] Starter innlogging for bruker: {username}')

    # Steg 1: Hent login-siden for CSRF-token
    with httpx.Client() as client:
        response = client.get(
            'https://www.artsobservasjoner.no/LogOn',
            headers={'User-Agent': 'Mozilla/5.0 (compatible; Fugleobservasjoner/1.0)'},
            timeout=15,
            follow_redirects=True
        )
        response.raise_for_status()
        login_html = response.text

        # Ekstraher __RequestVerificationToken fra HTML-form
        token_match = re.search(
            r'name="__RequestVerificationToken"[^>]*value="([^"]*)"',
            login_html
        )
        if not token_match:
            raise ValueError('Kunne ikke hente CSRF-token fra login-side')

        form_token = token_match.group(1)

        # Hent cookie-token fra response cookies
        cookie_token = response.cookies.get('__RequestVerificationToken', '')

        logger.debug('[AO-LOGIN] Hentet CSRF-tokens, sender innlogging...')

        # Steg 2: POST login med credentials
        post_data = {
            '__RequestVerificationToken': form_token,
            'AuthenticationViewModel.UserName': username,
            'AuthenticationViewModel.Password': password,
            'AuthenticationViewModel.RememberMe': 'true'
        }

        auth_response = client.post(
            'https://www.artsobservasjoner.no/LogOn',
            headers={
                'Content-Type': 'application/x-www-form-urlencoded',
                'User-Agent': 'Mozilla/5.0 (compatible; Fugleobservasjoner/1.0)'
            },
            cookies={'__RequestVerificationToken': cookie_token},
            data=post_data,
            timeout=15,
            follow_redirects=False  # Ikke følg redirect automatisk, vi må sjekke det
        )

        # Sjekk for redirect til MyPages (vellykket login)
        if auth_response.status_code not in (302, 303):
            # Ingen redirect - sjekk om det er feilmelding
            if 'Feil brukernavn' in auth_response.text or 'Feil passord' in auth_response.text:
                raise ValueError('Feil brukernavn eller passord')
            raise ValueError('Innlogging feilet - ingen redirect mottatt')

        # Parse cookies fra response
        auth_cookie = None
        login_token = None
        user_id = None

        if '.ASPXAUTHNO' in auth_response.cookies:
            auth_cookie = auth_response.cookies['.ASPXAUTHNO']

        if 'logintoken' in auth_response.cookies:
            login_token = auth_response.cookies['logintoken']
            # Ekstraher userId fra logintoken (før kolon)
            if ':' in login_token:
                user_id = login_token.split(':')[0]

        if not auth_cookie:
            raise ValueError('Innlogging feilet - ingen auth cookie mottatt')

        if not login_token:
            raise ValueError('Innlogging feilet - ingen logintoken mottatt (husk å krysse av "Husk meg")')

        # Lagre credentials for auto-relogin (persisterert til disk)
        if user_id:
            _save_credentials(user_id, username, password)
            logger.debug(f'[AO-LOGIN] Lagret credentials for auto-relogin (user_id={user_id})')

        logger.info(f'[AO-LOGIN] Innlogging vellykket! user_id={user_id}, auth_cookie={mask_token(auth_cookie)}')

        return {
            'authCookie': auth_cookie,
            'loginToken': login_token,
            'userId': user_id
        }


def _refresh_with_logintoken(login_token: str, user_id: str) -> str:
    """Gjenoppretter .ASPXAUTHNO via logintoken (AO sin "husk meg"-auto-login).

    VIKTIG — bevist mekanisme (testet mot AO):
    - Må treffe FORSIDEN «/» (ikke [Authorize]-beskyttet). Beskyttede sider
      (/User/MyPages, /SubmitSighting/Report) redirecter til /LogOn FØR
      husk-meg-logikken kjører, så revival er umulig der.
    - `logintoken_ssl=1` er PÅKREVD.
    - Ingen .ASPXAUTHNO må sendes: en gammel/død cookie kortslutter auto-login.

    logintoken har ~1 års levetid, så dette gir langvarig sesjon uten passord.
    Cookies settes på CLIENT-nivå for å videresendes ved redirects.

    Returns:
        Ny .ASPXAUTHNO hvis vellykket, ellers None.
    """
    if not login_token:
        return None

    logger.debug(f'[LOGINTOKEN-REFRESH] Prøver husk-meg-revival med logintoken: {mask_token(login_token)}')

    try:
        # Kun logintoken + logintoken_ssl, INGEN .ASPXAUTHNO (den ville blokkert revival)
        with httpx.Client(cookies={
            'logintoken': login_token,
            'logintoken_ssl': '1',
            'AcceptCookies': '1'
        }) as client:
            response = client.get(
                'https://www.artsobservasjoner.no/',
                headers={'User-Agent': 'Mozilla/5.0 (compatible; Fugleobservasjoner/1.0)'},
                timeout=10,
                follow_redirects=True
            )

            # Revival mislyktes hvis vi havnet på login-siden
            if '/LogOn' in str(response.url):
                logger.debug('[LOGINTOKEN-REFRESH] Revival mislyktes (redirect til /LogOn)')
                return None

            for cookie in client.cookies.jar:
                if cookie.name == '.ASPXAUTHNO' and cookie.value:
                    logger.info(f'[LOGINTOKEN-REFRESH] Session gjenopprettet via husk-meg: {mask_token(cookie.value)}')
                    return cookie.value

        logger.debug('[LOGINTOKEN-REFRESH] Ingen .ASPXAUTHNO mottatt')
        return None
    except Exception as e:
        logger.error(f'[LOGINTOKEN-REFRESH] Feil: {e}')
        return None


def _full_relogin(user_id: str, login_token: str = None) -> str:
    """Fornyer session. Prøver logintoken først, deretter credentials fra disk.

    Returns:
        Ny .ASPXAUTHNO hvis vellykket, ellers None.
    """
    # Denne funksjonen kalles KUN når sliding expiration feilet (cookie utløpt).
    # Logger som ERROR for å gi statistikk på hvor ofte dette skjer.
    logger.error(f'[AUTH-RELOGIN-REQUIRED] Sliding expiration feilet for user_id={user_id}, må logge inn på nytt')

    # Steg 1: Prøv logintoken-refresh (ingen credentials nødvendig)
    if login_token:
        new_cookie = _refresh_with_logintoken(login_token, user_id)
        if new_cookie:
            logger.error(f'[AUTH-RELOGIN-RESULT] Logintoken-refresh vellykket for user_id={user_id}')
            return new_cookie

    # Steg 2: Full relogin med lagrede credentials (fra disk)
    creds = _load_credentials(user_id)
    if not creds:
        logger.error(f'[AUTH-RELOGIN-RESULT] Ingen lagrede credentials for user_id={user_id} — bruker må logge inn manuelt')
        return None

    username, password = creds
    try:
        result = login_to_ao(username, password)
        logger.error(f'[AUTH-RELOGIN-RESULT] Credentials-relogin vellykket for user_id={user_id}')
        return result['authCookie']
    except Exception as e:
        logger.error(f'[AUTH-RELOGIN-RESULT] Credentials-relogin feilet for user_id={user_id}: {e}')
        return None


def handle_species_search(search_term, dont_include_sub='true', ao_base_url='https://www.artsobservasjoner.no'):
    """Håndter søk etter arter via Artsobservasjoner.no."""
    if not search_term.strip():
        return []

    # Bygg URL til Artsobservasjoner
    query_params = {
        'search': search_term,
        'returnformat': 'html',
        'onlyReportable': 'true',
        'dontIncludeSubSpecies': dont_include_sub,
        'speciesGroup': '8',
        'language': '4',
    }
    ao_url = ao_base_url + '/Taxon/PickerSearch?' + urlencode(query_params)

    try:
        with httpx.Client() as client:
            resp = client.get(
                ao_url,
                headers={
                    'User-Agent': 'Mozilla/5.0 (compatible; Fugleobservasjoner-Python/0.1)',
                    'Accept': 'text/html, */*; q=0.01',
                    'X-Requested-With': 'XMLHttpRequest',
                    'Referer': 'https://www.artsobservasjoner.no/SubmitSighting/Report',
                },
                timeout=10,
            )
            resp.raise_for_status()
            html = resp.text

        # Finn alle <span class="itemjson">...</span>
        items = re.findall(r'<span class="itemjson">(.*?)</span>', html)
        results = []

        for item in items:
            try:
                data = json.loads(item)
                taxon_name_raw = data.get('taxonname')
                taxon_name = unescape(taxon_name_raw) if taxon_name_raw else None
                scientific_raw = data.get('scientificname')
                scientific_html = unescape(scientific_raw) if scientific_raw else None
                
                results.append({
                    'taxonId': data.get('taxonid'),
                    'taxonName': taxon_name,
                    'scientificNameHtml': scientific_html,
                    'speciesGroupId': data.get('speciesgroupid'),
                    'protectionLevelId': data.get('protectionlevelid'),
                    'leaf': (data.get('leaf') == 'true'),
                })
            except Exception:
                # Ignorer rader vi ikke klarer å parse
                continue

        return results
    except Exception as e:
        logger.error(f'Feil ved henting fra Artsobservasjoner: {e}')
        raise


def handle_reverse_geocoding(lat, lon, nominatim_base_url):
    """Håndter reverse geokoding via Nominatim."""
    # Valider koordinater
    try:
        float(lat)
        float(lon)
    except ValueError:
        raise ValueError('Ugyldig lat/lon')

    nominatim_url = f'{nominatim_base_url}?format=jsonv2&lat={lat}&lon={lon}&zoom=14&addressdetails=1'

    try:
        with httpx.Client() as client:
            resp = client.get(
                nominatim_url,
                headers={
                    'User-Agent': 'Fugleobservasjoner/0.1 (hobbyprosjekt)',
                    'Accept': 'application/json',
                },
                timeout=10,
            )
            resp.raise_for_status()
            body = resp.text

        if not body.strip():
            return None

        data = json.loads(body)
        address = data.get('address', {}) or {}
        
        # Finn kort stedsnavn
        name = (
            address.get('locality') or
            address.get('village') or
            address.get('town') or
            address.get('city') or
            address.get('hamlet') or
            address.get('municipality') or
            address.get('county') or
            data.get('name') or
            data.get('display_name')
        )
        
        return name
    except Exception as e:
        logger.error(f'Feil ved reverse geokoding: {e}')
        raise


def _epsg3857_to_wgs84(x, y):
    """Konverter Web Mercator (EPSG:3857) til WGS84 (lat, lon)."""
    R = 6378137.0
    lon = math.degrees(x / R)
    lat = math.degrees(2 * math.atan(math.exp(y / R)) - math.pi / 2)
    return round(lat, 6), round(lon, 6)


def handle_ao_private_sites(auth_cookie: str, ao_base_url: str = 'https://www.artsobservasjoner.no', login_token: str = None, user_id: str = None) -> tuple:
    """
    Hent alle brukerens private lokasjoner via BindUserSitesGrid.

    Returnerer tuple: (sites, refreshed_auth_cookie)
    hvor sites er liste med dicts: { id, name, lat, lon, acc }
    og refreshed_auth_cookie er ny .ASPXAUTHNO hvis sesjonen ble fornyet (ellers None).
    Koordinater er konvertert fra EPSG:3857 til WGS84.

    BindUserSitesGrid er et Kendo-grid-endepunkt som krever X-Requested-With: XMLHttpRequest.

    Med user_id + login_token sikres gyldig sesjon (sliding → logintoken-revival →
    credentials) FØR kallet, slik at en utløpt .ASPXAUTHNO ikke gir tom liste.
    """
    # Sørg for gyldig auth (sliding expiration → logintoken → credentials)
    refreshed_auth_cookie = None
    if user_id and login_token:
        auth_cookie, refreshed_auth_cookie = _ensure_auth(auth_cookie, user_id, login_token)

    url_grid = f'{ao_base_url}/Site/BindUserSitesGrid?UserSitesGrid-size=500'
    seed_cookies = {'.ASPXAUTHNO': auth_cookie, 'AcceptCookies': '1'}
    if login_token:
        seed_cookies['logintoken'] = login_token

    headers = {
        'User-Agent': 'Mozilla/5.0 (compatible; Fugleobservasjoner/1.0)',
        'Accept': 'application/json',
    }

    with httpx.Client(cookies=seed_cookies, follow_redirects=True) as client:
        response = client.post(
            url_grid,
            headers={
                **headers,
                'Content-Type': 'application/x-www-form-urlencoded',
                'X-Requested-With': 'XMLHttpRequest',
            },
            content=b'page=1&size=500',
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()

    sites = []
    for item in data.get('data', []):
        site_id = item.get('SiteId')
        name = item.get('Name')
        x = item.get('SiteXCoord')
        y = item.get('SiteYCoord')
        acc = item.get('Accuracy')
        if not (site_id and name and x and y):
            continue
        lat, lon = _epsg3857_to_wgs84(x, y)
        sites.append({'id': site_id, 'name': name, 'lat': lat, 'lon': lon, 'acc': acc})

    logger.info(f'[AO-PRIVATE-SITES] Hentet {len(sites)} private lokasjoner')
    return sites, refreshed_auth_cookie


def _wgs84_to_mercator(lat, lon):
    """Konverter WGS84 (lat, lon) til Web Mercator (EPSG:3857)."""
    x = lon * 20037508.34 / 180
    y = math.log(math.tan((90 + lat) * math.pi / 360)) / (math.pi / 180)
    y = y * 20037508.34 / 180
    return x, y


def _compute_bbox(lat, lon, size_m):
    """Beregn geografisk bounding box i WGS84.

    Boksen strekker seg size_m meter i hver kardinalretning slik at den
    omsluttes den haversine-sirkelen search_nearby() bruker (radius=size_m).
    """
    half_m = max(size_m, 1.0)
    meters_per_deg_lat = 111_320.0
    meters_per_deg_lon = meters_per_deg_lat * math.cos(math.radians(lat)) or 1.0

    d_lat = half_m / meters_per_deg_lat
    d_lon = half_m / meters_per_deg_lon

    return {
        'min_x': lon - d_lon, 'max_x': lon + d_lon,
        'min_y': lat - d_lat, 'max_y': lat + d_lat,
    }


def _ensure_auth(ao_auth, ao_user_id, login_token):
    """Sørg for at auth-cookie er gyldig.

    Strategi (én HTTP-request i normaltilfelle):
    1. Sliding expiration — forleng eksisterende session (rate-limited)
    2. Hvis cookie utløpt — full relogin (logintoken → credentials)

    Returns:
        tuple: (ao_auth, refreshed_auth_cookie_or_None)
    """
    if not ao_user_id:
        return ao_auth, None

    refreshed = None

    # Steg 1: Sliding expiration (forlenger gyldig session)
    if ao_auth:
        new_cookie = _sliding_expiration(ao_auth, ao_user_id, login_token)
        if new_cookie:
            return new_cookie, new_cookie

    # Steg 2: Hvis ingen auth eller sliding feilet, prøv full relogin
    if not ao_auth or _is_cookie_expired(ao_auth, ao_user_id, login_token):
        new_cookie = _full_relogin(ao_user_id, login_token)
        if new_cookie:
            return new_cookie, new_cookie

    return ao_auth, refreshed


def _is_cookie_expired(auth_cookie, user_id, login_token):
    """Sjekk om auth-cookie er utløpt ved å probe MyPages."""
    try:
        cookies = {'.ASPXAUTHNO': auth_cookie, 'AcceptCookies': '1'}
        if login_token:
            cookies['logintoken'] = login_token
            cookies['logintoken_ssl'] = '1'

        with httpx.Client(cookies=cookies) as client:
            response = client.get(
                'https://www.artsobservasjoner.no/User/MyPages',
                headers={'User-Agent': 'Mozilla/5.0 (compatible; Fugleobservasjoner/1.0)'},
                timeout=10,
                follow_redirects=True
            )
            # Redirect til /LogOn = utløpt
            return '/LogOn' in str(response.url)
    except Exception:
        return True  # Anta utløpt ved feil


def _fetch_private_site_ids(lat, lon, size_m, ao_login, ao_auth, ao_user_id, refreshed_auth_cookie):
    """Hent brukerens private site-IDer via GetSitesGeoJson.

    Returns:
        tuple: (my_site_ids: set, refreshed_auth_cookie, auth_failed: bool)
    """
    my_site_ids = set()
    auth_failed = False

    if not (ao_login and ao_auth and ao_user_id):
        return my_site_ids, refreshed_auth_cookie, auth_failed

    try:
        # Normaliser AO_AUTH_COOKIE verdi
        auth_val = ao_auth
        if auth_val.startswith('.ASPXAUTHNO='):
            auth_val = auth_val.split('=', 1)[1]

        # Hent CSRF token fra AO
        csrf_cookie_token = None
        try:
            _, csrf_cookie_token, refreshed = fetch_csrf_tokens(ao_login, auth_val)
            logger.debug(f'GetSitesGeoJson: Hentet CSRF token: {mask_token(csrf_cookie_token)}')
            if refreshed:
                auth_val = refreshed
                refreshed_auth_cookie = refreshed
        except Exception as csrf_err:
            logger.debug(f'GetSitesGeoJson: Kunne ikke hente CSRF token: {csrf_err}')

        # Konverter til Web Mercator bbox
        # Mercator-skalaen ved lat φ er 1/cos(φ) — uten korreksjon dekker bbox bare ~cos(φ) × ønsket radius
        center_x, center_y = _wgs84_to_mercator(lat, lon)
        mercator_scale = 1.0 / math.cos(math.radians(lat))
        half_size = max(size_m, 100) * mercator_scale
        bbox_str = f'{int(center_x - half_size)},{int(center_y - half_size)},{int(center_x + half_size)},{int(center_y + half_size)}'

        cookies_dict = {'AcceptCookies': '1', '.ASPXAUTHNO': auth_val, 'logintoken': ao_login}
        if csrf_cookie_token:
            cookies_dict['__RequestVerificationToken'] = csrf_cookie_token

        post_data = {
            'zoomLevel': 16, 'bbox': bbox_str, 'userId': int(ao_user_id),
            'coordSyst': 0, 'speciesGroupId': '0', 'taxonId': None
        }

        logger.debug(f'GetSitesGeoJson POST bbox: {bbox_str}')

        geojson_data = None
        with httpx.Client() as client:
            response = client.post(
                'https://www.artsobservasjoner.no/Map/GetSitesGeoJson',
                headers={
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:147.0) Gecko/20100101 Firefox/147.0',
                    'Accept': '*/*',
                    'Content-Type': 'application/json; charset=UTF-8',
                    'X-Requested-With': 'XMLHttpRequest',
                    'Origin': 'https://www.artsobservasjoner.no',
                    'Referer': 'https://www.artsobservasjoner.no/SubmitSighting/Report'
                },
                cookies=cookies_dict, json=post_data, timeout=15, follow_redirects=True
            )
            response.raise_for_status()

            if not refreshed_auth_cookie and '.ASPXAUTHNO' in response.cookies:
                refreshed_auth_cookie = response.cookies['.ASPXAUTHNO']

            body = response.text
            if body.strip().startswith('<!DOCTYPE') or body.strip().startswith('<html'):
                logger.warning('GetSitesGeoJson: Fikk HTML i stedet for JSON - auth ugyldig')
                auth_failed = True
            else:
                geojson_data = response.json() if body else None

        # Ekstraher private site-IDer fra GeoJSON
        if isinstance(geojson_data, dict):
            for layer_key in ('points', 'polygons'):
                layer = geojson_data.get(layer_key, {})
                if isinstance(layer, dict):
                    for feature in layer.get('features', []):
                        props = feature.get('properties', {})
                        site_id = props.get('siteId') or props.get('id') or feature.get('id')
                        if props.get('isPrivate') and site_id is not None:
                            my_site_ids.add(int(site_id))

        logger.debug(f'GetSitesGeoJson: fant {len(my_site_ids)} private site-IDs')
    except Exception as geojs_err:
        logger.warning(f'GetSitesGeoJson feilet: {geojs_err}')

    return my_site_ids, refreshed_auth_cookie, auth_failed


def _fetch_public_sites(bbox, ao_mobile_base_url):
    """Hent offentlige lokasjoner via ByBoundingBox API.

    Returns:
        list: Rå site-dicts fra API-et
    """
    query_params = {
        'maxSites': '1000',
        'minX': f'{bbox["min_x"]:.6f}', 'minY': f'{bbox["min_y"]:.6f}',
        'maxX': f'{bbox["max_x"]:.6f}', 'maxY': f'{bbox["max_y"]:.6f}',
        'includePublicSites': 'true',
    }

    ao_sites_url = ao_mobile_base_url + '/core/Sites/ByBoundingBox?' + urlencode(query_params)

    with httpx.Client() as client:
        resp = client.get(
            ao_sites_url,
            headers={
                'User-Agent': 'Mozilla/5.0 (compatible; Fugleobservasjoner-Python/0.1)',
                'Accept': 'application/json, text/plain, */*',
                'Accept-Encoding': 'identity',
                'X-CSRF': '1',
                'Referer': 'https://mobil.artsobservasjoner.no/contribute/submit-sightings',
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

    if isinstance(data, list):
        return data
    elif isinstance(data, dict):
        return data.get('sites') or data.get('Sites') or []
    return []


def _normalize_site(item, my_site_ids):
    """Normaliser et rå site-dict til internt format med superlokasjon-deteksjon."""
    name = item.get('name') or item.get('Name') or item.get('siteName') or item.get('SiteName')
    site_id = item.get('id') or item.get('Id') or item.get('siteId')
    lat_val = item.get('lat') or item.get('latitude') or item.get('Lat')
    lon_val = item.get('lon') or item.get('longitude') or item.get('Lon')

    site = {'raw': item}
    if name:
        site['name'] = name
    if site_id is not None:
        site['id'] = site_id
        try:
            if int(site_id) in my_site_ids:
                site['isMine'] = True
        except (ValueError, TypeError):
            pass
    if lat_val is not None:
        site['lat'] = lat_val
    if lon_val is not None:
        site['lon'] = lon_val

    # Kommune/fylke fra AO — brukes til å skille lokaliteter med samme navn
    municipality = item.get('municipalityName') or item.get('MunicipalityName')
    county = item.get('countyName') or item.get('CountyName')
    if municipality:
        site['municipality'] = municipality
    if county:
        site['county'] = county

    # Detekter superlokasjon-status
    try:
        for k in ('isSuper', 'isSuperSite', 'IsSuper', 'IsSuperSite', 'is_super'):
            if k in item:
                v = item.get(k)
                if v is True or v == 'true' or v == 'True' or v == '1':
                    site['isSuper'] = True
                elif v is False or v == 'false' or v == 'False' or v == '0':
                    site['isSuper'] = False
                break

        if 'isSuper' not in site:
            t = item.get('siteType') or item.get('type') or item.get('SiteType')
            if isinstance(t, str) and ('super' in t.lower() or 'superlok' in t.lower()):
                site['isSuper'] = True

        for pk in ('parentId', 'parentSiteId', 'ParentId', 'parent'):
            if pk in item and item.get(pk) is not None:
                site['parentId'] = item.get(pk)
                if 'isSuper' not in site:
                    site['isSuper'] = False
                break
    except Exception:
        pass

    return site


def _resolve_super_sites(sites):
    """Utled superlokasjoner fra parent-referanser mellom sites."""
    try:
        # Normaliser til string for å unngå int/string-mismatch fra AO-APIet
        id_map = {str(s.get('id')): s for s in sites if s.get('id') is not None}
        for s in sites:
            raw = s.get('raw') or {}
            for pk in ('parentSiteId', 'ParentSiteId', 'parentId', 'parent', 'ParentId', 'parentSite'):
                if pk in raw and raw.get(pk) is not None:
                    pid = str(raw.get(pk))
                    s['parentId'] = raw.get(pk)
                    s['isSuper'] = False
                    if pid in id_map:
                        id_map[pid]['isSuper'] = True
                    break
    except Exception:
        pass


def _mark_env_owned_sites(sites):
    """Merk bruker-eide lokasjoner fra MY_AO_SITE_IDS miljøvariabel."""
    try:
        my_ids_raw = os.getenv('MY_AO_SITE_IDS', '')
        if my_ids_raw:
            my_ids = {int(x.strip()) for x in my_ids_raw.split(',') if x.strip()}
            for s in sites:
                sid = s.get('id')
                if sid is not None and int(sid) in my_ids:
                    s['isMine'] = True
    except Exception:
        pass


def handle_ao_sites_search(lat, lon, size_m=600.0, ao_mobile_base_url='https://mobil.artsobservasjoner.no', user_id=None, login_token=None, auth_cookie=None, location_db=None):
    """Håndter søk etter AO-lokaliteter.

    Hvis location_db er satt, søkes det parallelt i lokal DB og AO.
    Resultater merges med AO som prioritet, og AO-resultater lagres i lokal DB.

    Returns:
        tuple: (sites_list, refreshed_auth_cookie_or_None, auth_failed_bool)
    """
    try:
        lat = float(lat)
        lon = float(lon)
        size_m = float(size_m) if size_m else 600.0
    except ValueError:
        raise ValueError('Ugyldig lat/lon/size')

    ao_user_id = user_id or (login_token.split(':')[0] if login_token and ':' in login_token else None)
    ao_auth = auth_cookie or os.getenv('AO_AUTH_COOKIE')

    # Sørg for gyldig auth
    ao_auth, refreshed_auth_cookie = _ensure_auth(ao_auth, ao_user_id, login_token)

    # Beregn bounding box
    bbox = _compute_bbox(lat, lon, size_m)
    logger.debug(f'AO-sites: lat={lat:.6f}, lon={lon:.6f}, size_m={size_m:.1f}')

    ao_login = login_token or os.getenv('AO_LOGIN_TOKEN')

    # Hent private site-IDer via GeoJSON
    my_site_ids, refreshed_auth_cookie, auth_failed = _fetch_private_site_ids(
        lat, lon, size_m, ao_login, ao_auth, ao_user_id, refreshed_auth_cookie
    )

    # Hent lokale lokasjoner parallelt hvis lokal DB er tilgjengelig
    local_sites = []
    if location_db:
        try:
            local_sites = location_db.search_nearby(lat, lon, radius_m=int(size_m))
            logger.debug(f'Lokal DB: {len(local_sites)} treff')
        except Exception as e:
            logger.warning(f'Lokal DB-søk feilet: {e}')

    # Hent offentlige sites via ByBoundingBox
    try:
        raw_sites = _fetch_public_sites(bbox, ao_mobile_base_url)

        # Normaliser alle sites
        sites = [_normalize_site(item, my_site_ids) for item in raw_sites if isinstance(item, dict)]

        # Utled superlokasjoner fra parent-referanser
        _resolve_super_sites(sites)

        logger.info(f'AO-sites: {len(sites)} lokaliteter')
        if sites[:3]:
            logger.info(f'AO-sites eksempel: {[s.get("name") for s in sites[:3]]}')

        # Merk bruker-eide fra miljøvariabel
        _mark_env_owned_sites(sites)

        # Merge lokale sites som ikke finnes i AO-resultater
        if local_sites:
            ao_id_map = {s.get('id'): s for s in sites if s.get('id') is not None}
            for local_site in local_sites:
                local_id = local_site.get('id')
                if local_id not in ao_id_map:
                    sites.append(local_site)
                elif local_site.get('isSuper') and not ao_id_map[local_id].get('isSuper'):
                    # AO-APIet mangler isSuper — hent fra lokal DB som har fullstendig data
                    ao_id_map[local_id]['isSuper'] = True
            # AO-APIet returnerer parentSiteId=null — bruk lokal DB sin parent_id til å utlede super-status
            for local_site in local_sites:
                pid = local_site.get('parentId')
                if pid is not None and pid in ao_id_map and not ao_id_map[pid].get('isSuper'):
                    ao_id_map[pid]['isSuper'] = True
            logger.debug(f'Merget {len(sites)} totalt (AO + lokal DB)')

        # Sorter brukerens egne først
        sites.sort(key=lambda s: (0 if s.get('isMine') else 1))

        return sites, refreshed_auth_cookie, auth_failed
    except Exception as e:
        logger.error(f'Feil ved henting av AO-lokaliteter: {repr(e)}')
        # Hvis AO feiler men vi har lokale resultater, returner dem
        if local_sites:
            logger.info(f'AO feilet, returnerer {len(local_sites)} lokale resultater')
            return local_sites, refreshed_auth_cookie, auth_failed
        raise