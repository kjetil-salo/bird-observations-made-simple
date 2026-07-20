"""
Opprett ny AO-lokasjon via Artsobservasjoner.no API.

Bruker EPSG:3857 (Web Mercator) koordinater og /Map/SaveSite endepunktet.
Verifisert mot AO sitt JavaScript (NewSiteAdded-funksjonen i MasterJs).
"""

import logging
import math

import httpx


logger = logging.getLogger('fugleobs')

AO_BASE_URL = 'https://www.artsobservasjoner.no'

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:147.0) Gecko/20100101 Firefox/147.0',
    'X-Requested-With': 'XMLHttpRequest',
}


def wgs84_to_web_mercator(lat, lon):
    """Konverter WGS84 (lat, lon) til EPSG:3857 (Web Mercator).

    AO sitt kart bruker EPSG:3857 internt (bekreftet via EPSG-koder i MasterJs).

    Args:
        lat: Breddegrad (desimalgrader, WGS84)
        lon: Lengdegrad (desimalgrader, WGS84)

    Returns:
        tuple: (x, y) som heltall i EPSG:3857
    """
    x = lon * 20037508.34 / 180.0
    y = math.log(math.tan((90.0 + lat) * math.pi / 360.0)) / math.pi * 20037508.34
    return round(x), round(y)


def _build_cookies(login_token, auth_cookie):
    """Bygg cookies-dict for AO-requests."""
    return {
        'logintoken': login_token,
        '.ASPXAUTHNO': auth_cookie,
        'AcceptCookies': '1',
    }


def _update_site_accuracy(site_id, name, x, y, accuracy, wkt_geometry, login_token, auth_cookie):
    """Oppdater nøyaktighet på en site via /Map/AddSiteInfo.

    SaveSite ignorerer Accuracy-parameteren, så vi bruker AddSiteInfo
    etterpå for å sette den (samme flyt som AO sitt kart ved redigering).
    """
    url = f'{AO_BASE_URL}/Map/AddSiteInfo'
    cookies = _build_cookies(login_token, auth_cookie)

    form_data = {
        'Id': str(site_id),
        'Name': name,
        'XCoord': str(x),
        'YCoord': str(y),
        'Accuracy': str(int(accuracy)),
        'Geometry': wkt_geometry,
        'ParentId': '0',
        'comment': '',
    }

    logger.debug(f'[AO-CREATE] Setter nøyaktighet: {accuracy}m for siteId={site_id}')

    try:
        with httpx.Client() as client:
            response = client.post(
                url,
                cookies=cookies,
                headers=HEADERS,
                data=form_data,
                timeout=15,
                follow_redirects=True,
            )

        logger.debug(f'[AO-CREATE] AddSiteInfo status: {response.status_code}')

        data = response.json()
        if data.get('success'):
            logger.info(f'[AO-CREATE] Nøyaktighet satt til {accuracy}m')
            return True

        logger.warning(f'[AO-CREATE] Kunne ikke sette nøyaktighet: {data.get("message")}')
        return False

    except Exception as e:
        logger.error(f'[AO-CREATE] Feil ved setting av nøyaktighet: {e}')
        return False


def create_ao_site(name, lat, lon, accuracy, login_token, auth_cookie):
    """Opprett ny lokasjon i Artsobservasjoner via /Map/SaveSite.

    Bruker samme endepunkt og parametere som AO sitt kart-JavaScript
    (NewSiteAdded-funksjonen). Koordinater konverteres til EPSG:3857.

    Args:
        name: Navn på lokasjon
        lat: Breddegrad (WGS84)
        lon: Lengdegrad (WGS84)
        accuracy: Nøyaktighet i meter (0, 25, 50, 100, 250, 500)
        login_token: AO logintoken
        auth_cookie: AO .ASPXAUTHNO cookie-verdi

    Returns:
        dict: {success, siteId, siteName, message, refreshedAuthCookie}
    """
    logger.info(f'[AO-CREATE] Oppretter lokasjon "{name}" ved {lat}, {lon} (±{accuracy}m)')

    # Konverter til Web Mercator (EPSG:3857)
    x, y = wgs84_to_web_mercator(lat, lon)
    logger.debug(f'[AO-CREATE] EPSG:3857: x={x}, y={y}')

    # WKT POINT i EPSG:3857 (slik AO sitt kart sender det)
    wkt_point = f'POINT({x} {y})'

    # Parametere fra AO JavaScript NewSiteAdded():
    # Id=-1, Name, XCoord, YCoord, Geometry (WKT), comment
    form_data = {
        'Id': '-1',
        'Name': name,
        'XCoord': str(x),
        'YCoord': str(y),
        'Accuracy': str(int(accuracy)),
        'Geometry': wkt_point,
        'comment': '',
    }

    url = f'{AO_BASE_URL}/Map/SaveSite'
    cookies = _build_cookies(login_token, auth_cookie)

    logger.debug(f'[AO-CREATE] POST {url}')

    refreshed_auth = None

    try:
        with httpx.Client() as client:
            response = client.post(
                url,
                cookies=cookies,
                headers=HEADERS,
                data=form_data,
                timeout=15,
                follow_redirects=True,
            )

        logger.debug(f'[AO-CREATE] Status: {response.status_code}')

        # Sjekk for fornyet auth cookie
        if '.ASPXAUTHNO' in response.cookies:
            refreshed_auth = response.cookies['.ASPXAUTHNO']

        body = response.text.strip()

        # Sjekk for HTML-redirect (auth feilet)
        if body.startswith('<!DOCTYPE') or body.startswith('<html'):
            return {
                'success': False,
                'message': 'Auth utløpt - AO redirectet til login',
                'refreshedAuthCookie': refreshed_auth,
            }

        # Parse JSON-response
        data = response.json()

        if not data.get('success'):
            error_msg = data.get('message', 'Ukjent feil fra AO')
            return {
                'success': False,
                'message': error_msg,
                'refreshedAuthCookie': refreshed_auth,
            }

        # Hent siteId fra response.points.features[0].properties.siteId
        site_id = None
        site_name = name
        features = data.get('points', {}).get('features', [])
        if features:
            props = features[0].get('properties', {})
            site_id = props.get('siteId')
            site_name = props.get('siteName', name)
            logger.info(f'[AO-CREATE] Opprettet: siteId={site_id}')

        if site_id and site_id > 0:
            # SaveSite ignorerer Accuracy, så vi setter den via AddSiteInfo
            if accuracy and accuracy > 0:
                _update_site_accuracy(
                    site_id, site_name, x, y, accuracy, wkt_point,
                    login_token, refreshed_auth or auth_cookie,
                )

            return {
                'success': True,
                'siteId': site_id,
                'siteName': site_name,
                'message': f'Lokasjon "{site_name}" opprettet (ID: {site_id})',
                'refreshedAuthCookie': refreshed_auth,
            }

        # success=true men siteId mangler eller er -1
        return {
            'success': True,
            'siteId': site_id,
            'siteName': site_name,
            'message': f'Lokasjon "{site_name}" opprettet',
            'refreshedAuthCookie': refreshed_auth,
        }

    except Exception as e:
        logger.error(f'[AO-CREATE] Feil: {e}')
        return {
            'success': False,
            'message': f'Feil ved opprettelse: {e}',
            'refreshedAuthCookie': refreshed_auth,
        }
