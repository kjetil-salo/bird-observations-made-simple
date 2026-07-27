"""
AO Direct Import - Bruker httpx for HTTP-kall.
"""

import logging
import os
import re
import time
from urllib.parse import quote_plus

import httpx

from src.utils import mask_token as _mask

logger = logging.getLogger('fugleobs')


def observations_to_csv(observations):
    """Samme som i ao_import.py"""
    from src.ao_import import observations_to_csv as orig
    return orig(observations)


def _count_review_rows(html):
    """Tell antall observasjonsrader i AO ReviewSighting HTML. Returnerer 0 hvis ingen."""
    # Kendo UI grid (AO bruker Kendo) har k-master-row på datarader
    kendo = re.findall(r'class="[^"]*k-master-row[^"]*"', html)
    if kendo:
        return len(kendo)
    # Fallback: tell <tr>-elementer inne i <tbody>
    tbody = re.search(r'<tbody[^>]*>(.*?)</tbody>', html, re.DOTALL | re.IGNORECASE)
    if tbody:
        rows = re.findall(r'<tr[\s>]', tbody.group(1), re.IGNORECASE)
        return len(rows)
    # Kan ikke bestemme – returner None (betyr "ukjent", ikke 0)
    return None


def fetch_csrf_tokens(login_token, auth_cookie):
    """
    Hent BEGGE CSRF tokens:
    - cookie_token: Fra Set-Cookie header
    - form_token: Fra hidden input i HTML

    Returnerer også eventuell fornyet .ASPXAUTHNO fra Set-Cookie header.
    ASP.NET MVC krever at disse er forskjellige men matcher kryptografisk.

    Returns:
        tuple: (form_token, cookie_token, refreshed_auth_cookie or None)
    """
    cookies = {
        'logintoken': login_token,
        '.ASPXAUTHNO': auth_cookie,
        'AcceptCookies': '1'
    }

    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:147.0) Gecko/20100101 Firefox/147.0'
    }

    # VIKTIG: Cookies på CLIENT-nivå for å videresendes ved redirects
    with httpx.Client(cookies=cookies) as client:
        response = client.get(
            'https://www.artsobservasjoner.no/ImportSighting',
            headers=headers,
            timeout=15,
            follow_redirects=True
        )
        response.raise_for_status()
        # Finn cookies fra jar (unngå dict() som krasjer ved duplikater)
        refreshed_auth = None
        cookie_token = None
        for cookie in client.cookies.jar:
            if cookie.name == '.ASPXAUTHNO' and cookie.value != auth_cookie:
                refreshed_auth = cookie.value
            elif cookie.name == '__RequestVerificationToken':
                cookie_token = cookie.value

    html = response.text

    if refreshed_auth:
        logger.debug(f'[AO-HTTPX] Fornyet .ASPXAUTHNO: {_mask(refreshed_auth)}')

    # Hent form-token fra HTML
    match = re.search(r'name="__RequestVerificationToken"[^>]*value="([^"]+)"', html)
    if not match:
        raise ValueError('Kunne ikke finne form CSRF token i HTML')
    form_token = match.group(1)

    if not cookie_token:
        raise ValueError('Kunne ikke finne cookie CSRF token')

    logger.debug(f'[AO-HTTPX] Form token: {_mask(form_token)}')
    logger.debug(f'[AO-HTTPX] Cookie token: {_mask(cookie_token)}')

    return form_token, cookie_token, refreshed_auth


def _post_count(url, login_token, auth_cookie):
    """
    POST til et AO count-endepunkt (body: JSON null) og returner Count som int.

    AOs egen web-UI poller disse for å vise importfremdrift:
    - /ImportSighting/NumberOfSightingsImporting  → hvor mange som fortsatt behandles
    - /ReviewSighting/NumberOfSightingsSubmitted   → hvor mange som ligger i gjennomgang

    Returnerer None hvis endepunktet er utilgjengelig eller svaret ikke kan tolkes.
    """
    cookies = {
        'logintoken': login_token,
        '.ASPXAUTHNO': auth_cookie,
        'AcceptCookies': '1',
    }
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:147.0) Gecko/20100101 Firefox/147.0',
        'Content-Type': 'application/json; charset=UTF-8',
        'X-Requested-With': 'XMLHttpRequest',
        'Accept': '*/*',
    }
    try:
        with httpx.Client() as client:
            resp = client.post(url, content='null', cookies=cookies, headers=headers, timeout=10)
        if resp.status_code != 200:
            return None
        return int(resp.json().get('Count'))
    except Exception:
        return None


def number_of_sightings_importing(login_token, auth_cookie):
    """Antall observasjoner AO fortsatt behandler (teller ned til 0 = ferdig parset)."""
    return _post_count(
        'https://www.artsobservasjoner.no/ImportSighting/NumberOfSightingsImporting',
        login_token, auth_cookie,
    )


def number_of_sightings_submitted(login_token, auth_cookie):
    """Antall observasjoner klargjort til gjennomgang (i review-køen)."""
    return _post_count(
        'https://www.artsobservasjoner.no/ReviewSighting/NumberOfSightingsSubmitted',
        login_token, auth_cookie,
    )


def review_queue_rows(login_token, auth_cookie, size=200):
    """
    Hent gjennomgangskøen som JSON fra AOs eget Kendo-grid-endepunkt.

    `POST /ReviewSighting/BindReviewSightingsGrid` med body `page=1&size=N` gir per rad
    bl.a. `SightingId`, `TemporarySightingId`, `TaxonName`, `SearchableStartDate`,
    `TimePresentation`, `ErrorCount` og `TriggeredValidationRulesText`. Bekreftet i
    HAR-fangst 27.07.2026 — se `docs/ao-rediger-api.md`.

    Returnerer liste av dicts, eller None hvis endepunktet ikke svarer som forventet.
    """
    cookies = {
        'logintoken': login_token,
        '.ASPXAUTHNO': auth_cookie,
        'AcceptCookies': '1',
    }
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:147.0) Gecko/20100101 Firefox/147.0',
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'X-Requested-With': 'XMLHttpRequest',
        'Accept': '*/*',
    }
    try:
        with httpx.Client() as client:
            resp = client.post(
                'https://www.artsobservasjoner.no/ReviewSighting/BindReviewSightingsGrid',
                content=f'page=1&size={int(size)}',
                cookies=cookies, headers=headers, timeout=10,
            )
        if resp.status_code != 200:
            return None
        rows = resp.json().get('data')
        return rows if isinstance(rows, list) else None
    except Exception:
        return None


def _describe_held_back(login_token, auth_cookie, limit=3):
    """
    Kort, menneskelig beskrivelse av hva som ble liggende igjen i gjennomgangskøen.

    Gir brukeren «tårnseiler 26.07 15:00» i stedet for bare et tall. Returnerer tom
    streng hvis køen ikke kan leses — da faller melding tilbake til antall alene.
    """
    rows = review_queue_rows(login_token, auth_cookie)
    if not rows:
        return ''
    biter = []
    for row in rows[:limit]:
        navn = (row.get('TaxonName') or '').strip() or 'ukjent art'
        dato = (row.get('SearchableStartDate') or '').strip()
        tid = (row.get('TimePresentation') or '').strip()
        regel = (row.get('TriggeredValidationRulesText') or '').strip()
        tekst = ' '.join(x for x in (navn, dato, tid) if x)
        if regel:
            tekst += f' ({regel})'
        biter.append(tekst)
    if len(rows) > limit:
        biter.append(f'+{len(rows) - limit} til')
    return ', '.join(biter)


def _remaining_after_publish(login_token, auth_cookie, timeout=6.0, interval=1.0):
    """
    Antall observasjoner som fortsatt ligger i gjennomgangskøen etter publisering.

    AO publiserer ikke rader den underkjenner (typisk «Angi et tidspunkt som ikke er
    passert» ved tidspunkt frem i tid) — de blir liggende i køen. Uten denne sjekken
    meldte appen «sendt til AO!» selv om observasjonen aldri ble publisert.

    Returnerer antall gjenværende, eller None hvis endepunktet ikke svarer.
    """
    deadline = time.time() + timeout
    remaining = None
    while time.time() < deadline:
        remaining = number_of_sightings_submitted(login_token, auth_cookie)
        if remaining is None or remaining == 0:
            return remaining
        time.sleep(interval)
    return remaining


def _poll_importing_done(login_token, auth_cookie, total, progress_cb=None,
                         timeout=30.0, interval=0.7):
    """
    Poll NumberOfSightingsImporting til AO er ferdig med å parse (Count == 0).

    Erstatter tidligere blind time.sleep(3). Kaller progress_cb underveis med reell
    fremdrift. Faller tilbake til kort blind venting hvis endepunktet ikke svarer.
    """
    deadline = time.time() + timeout
    first = True
    while time.time() < deadline:
        remaining = number_of_sightings_importing(login_token, auth_cookie)
        if remaining is None:
            # Endepunkt utilgjengelig — blind fallback, og la publish-retry ta resten
            logger.debug('[AO-HTTPX] Progress-endepunkt svarte ikke — faller tilbake til venting')
            time.sleep(3)
            return
        if progress_cb and remaining > 0:
            progress_cb({'phase': 'importing', 'remaining': remaining, 'total': total})
        # Krev to påfølgende avlesninger for å unngå å publisere før AO har startet
        if remaining == 0 and not first:
            if progress_cb:
                progress_cb({'phase': 'importing', 'remaining': 0, 'total': total})
            return
        first = False
        time.sleep(interval)
    logger.warning('[AO-HTTPX] Poll-timeout nådd — fortsetter til publisering')


def post_with_curl(observations, login_token=None, auth_cookie=None, area_id='', progress_cb=None):
    """
    Post til AO med httpx - med korrekt CSRF token-håndtering.

    Returnerer dict med:
    - success: bool
    - message: str
    - count: int
    - published: bool
    - refreshedAuthCookie: str eller None (fornyet .ASPXAUTHNO hvis AO sendte ny)
    """
    # Bruk tokens fra parameter, eller fall tilbake til miljøvariabler
    login_token = login_token or os.getenv('AO_LOGIN_TOKEN')
    auth_cookie = auth_cookie or os.getenv('AO_AUTH_COOKIE')

    if not login_token or not auth_cookie:
        raise ValueError('Mangler loginToken eller authCookie')

    # Hent BEGGE CSRF tokens + eventuell fornyet auth cookie
    form_token, cookie_token, refreshed_auth = fetch_csrf_tokens(login_token, auth_cookie)

    csv_data = observations_to_csv(observations)
    logger.debug(f'[AO-HTTPX] CSV length: {len(csv_data)}')

    # URL-encode
    encoded_csv = quote_plus(csv_data, safe='', encoding='utf-8')
    encoded_form_token = quote_plus(form_token, safe='', encoding='utf-8')

    post_data = (
        f'__RequestVerificationToken={encoded_form_token}&'
        f'ImportSightingViewModel.Observations={encoded_csv}&'
        f'ImportSightingViewModel.Area={area_id}&'
        f'ImportSightingViewModel.OwnAndFavoriteSites=true&'
        f'OwnAndFavoriteSites=false&'
        f'ImportSightingViewModel.ProjectToAdd=&'
        f'ImportSightingViewModel.ProjectToAdd_Name=&'
        f'Shared_Import=Importer'
    )

    # Cookies dict (httpx håndterer dette bedre enn string)
    cookies = {
        'AcceptCookies': '1',
        'monthlistpagesize': '150',
        'logintoken': login_token,
        'logintoken_ssl': '1',
        '.ASPXAUTHNO': auth_cookie,
        '__RequestVerificationToken': cookie_token,
        'ReleaseNumber': '2.13.12',
        'SpeciesGroup': '8'
    }

    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:147.0) Gecko/20100101 Firefox/147.0',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'nb-NO,nb;q=0.9,no;q=0.8,en;q=0.7',
        'Origin': 'https://www.artsobservasjoner.no',
        'Content-Type': 'application/x-www-form-urlencoded',
        'Referer': 'https://www.artsobservasjoner.no/ImportSighting',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'same-origin',
        'Sec-Fetch-User': '?1',
    }

    with httpx.Client() as client:
        response = client.post(
            'https://www.artsobservasjoner.no/ImportSighting/ParseObservations',
            content=post_data,
            cookies=cookies,
            headers=headers,
            timeout=30,
            follow_redirects=True
        )

    logger.info(f'[AO-HTTPX] HTTP Status: {response.status_code}')
    logger.debug(f'[AO-HTTPX] ParseObservations URL etter redirect: {response.url}')
    logger.debug(f'[AO-HTTPX] ParseObservations respons (første 500 tegn): {response.text[:500]}')

    if response.status_code >= 400:
        logger.error(f'[AO-HTTPX] Feil: HTTP {response.status_code}')
        raise ValueError(f'HTTP {response.status_code}')

    # Steg 2: Vent på at AO er ferdig med å parse importen — poll ekte fremdrift
    total = len(observations)
    if progress_cb:
        progress_cb({'phase': 'importing', 'remaining': total, 'total': total})
    _poll_importing_done(login_token, auth_cookie, total, progress_cb)
    if progress_cb:
        progress_cb({'phase': 'publishing', 'total': total})

    # Steg 3: Publiser observasjonene (med retry)
    logger.info('[AO-HTTPX] Starter publisering...')
    last_error = None
    publish_result = None
    for attempt, delay in enumerate([0, 5, 10], start=1):
        if delay:
            logger.debug(f'[AO-HTTPX] Venter {delay} sekunder før forsøk {attempt}...')
            time.sleep(delay)
        try:
            publish_result = publish_all(login_token, auth_cookie)
            logger.info(f'[AO-HTTPX] Publisering vellykket (forsøk {attempt}): {publish_result}')
            last_error = None
            break
        except Exception as e:
            last_error = e
            logger.warning(f'[AO-HTTPX] Publisering feilet (forsøk {attempt}): {e}')

    if last_error:
        return {
            'success': False,
            'error': f'Publisering feilet: {last_error}',
            'count': 0,
            'published': False,
            'refreshedAuthCookie': refreshed_auth
        }

    pending = publish_result.get('pending_count') if publish_result else None
    if pending == 0:
        logger.warning('[AO-HTTPX] AO hadde ingen observasjoner til publisering – import kan ha feilet')
        return {
            'success': False,
            'error': 'AO aksepterte ingen observasjoner. Importen kan være nede, eller lokaliteten/arten ble ikke gjenkjent.',
            'count': 0,
            'published': False,
            'refreshedAuthCookie': refreshed_auth
        }

    # Steg 4: Verifiser at køen faktisk ble tømt. Rader AO underkjenner blir liggende,
    # og da er «publisert» en løgn overfor brukeren.
    held_back = _remaining_after_publish(login_token, auth_cookie)

    published_count = len(observations)
    result = {
        'success': True,
        'message': f'{published_count} observasjoner importert og publisert',
        'count': published_count,
        'published': True,
        'refreshedAuthCookie': refreshed_auth
    }
    if held_back:
        detaljer = _describe_held_back(login_token, auth_cookie)
        logger.warning(f'[AO-HTTPX] {held_back} observasjon(er) ble ikke publisert: {detaljer or "ukjent årsak"}')
        result['heldBack'] = held_back
        result['heldBackDetails'] = detaljer
        result['message'] = (f'{published_count} importert, men {held_back} ble ikke publisert '
                             '— de ligger til gjennomgang på AO')
    return result


def publish_all(login_token, auth_cookie):
    """Publiser alle importerte observasjoner."""
    # Hent CSRF tokens fra ReviewSighting-siden
    cookies = {
        'logintoken': login_token,
        '.ASPXAUTHNO': auth_cookie,
        'AcceptCookies': '1'
    }

    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:147.0) Gecko/20100101 Firefox/147.0'
    }

    with httpx.Client() as client:
        response = client.get(
            'https://www.artsobservasjoner.no/ReviewSighting',
            cookies=cookies,
            headers=headers,
            timeout=15,
            follow_redirects=True
        )
        response.raise_for_status()

    html = response.text
    logger.debug(f'[AO-HTTPX] ReviewSighting respons (første 500 tegn): {html[:500]}')

    # Tell antall observasjoner som venter på publisering
    pending_count = _count_review_rows(html)
    logger.info(f'[AO-HTTPX] Observasjoner til gjennomgang: {pending_count}')
    if pending_count is not None and pending_count == 0:
        raise ValueError('AO har ingen observasjoner til publisering – importen kan ha feilet')

    # Hent form-token fra HTML
    match = re.search(r'name="__RequestVerificationToken"[^>]*value="([^"]+)"', html)
    if not match:
        raise ValueError('Kunne ikke finne form CSRF token for publisering')
    form_token = match.group(1)

    # Hent cookie-token fra response
    cookie_token = response.cookies.get('__RequestVerificationToken')
    if not cookie_token:
        raise ValueError('Kunne ikke finne cookie CSRF token for publisering')

    logger.debug(f'[AO-HTTPX] Publish form token: {_mask(form_token)}')
    logger.debug(f'[AO-HTTPX] Publish cookie token: {_mask(cookie_token)}')

    # URL-encode form token
    encoded_form_token = quote_plus(form_token, safe='', encoding='utf-8')

    post_data = (
        f'__RequestVerificationToken={encoded_form_token}&'
        f'ReviewSightingViewModel.PublicationName=&'
        f'ReviewSightingViewModel.PublicationComment=&'
        f'ReviewSightingViewModel.SightingsToPublishIds='
    )

    # Cookies for publish POST
    publish_cookies = {
        'AcceptCookies': '1',
        'monthlistpagesize': '150',
        'logintoken': login_token,
        'logintoken_ssl': '1',
        '.ASPXAUTHNO': auth_cookie,
        '__RequestVerificationToken': cookie_token,
        'ReleaseNumber': '2.13.12',
        'SpeciesGroup': '8'
    }

    publish_headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:147.0) Gecko/20100101 Firefox/147.0',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'nb-NO,nb;q=0.9,no;q=0.8,en;q=0.7',
        'Origin': 'https://www.artsobservasjoner.no',
        'Content-Type': 'application/x-www-form-urlencoded',
        'Referer': 'https://www.artsobservasjoner.no/ReviewSighting',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'same-origin',
        'Sec-Fetch-User': '?1',
    }

    with httpx.Client() as client:
        response = client.post(
            'https://www.artsobservasjoner.no/PublishSighting/PublishAll',
            content=post_data,
            cookies=publish_cookies,
            headers=publish_headers,
            timeout=30,
            follow_redirects=True
        )

    logger.info(f'[AO-HTTPX] Publish HTTP Status: {response.status_code}')

    if response.status_code >= 400:
        raise ValueError(f'Publisering feilet: HTTP {response.status_code}')

    return {'status': response.status_code, 'pending_count': pending_count}
