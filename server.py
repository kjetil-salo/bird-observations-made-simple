#!/usr/bin/env python3
"""
HTTP server for fugleobservasjoner.

Håndterer routing og HTTP-forespørsler, delegerer API-logikk til separate moduler.
"""

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import json
import logging
import os
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

# Konfigurerbart log-nivå via miljøvariabel (DEBUG, INFO, WARNING, ERROR)
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO').upper()

# Loggen skrives alltid til konsollen (Docker/Dozzle live-visning).
_log_handlers = [logging.StreamHandler()]

# Persistent logg: hvis LOG_DIR er satt, skrives loggen i tillegg til en roterende
# fil. På Pi peker LOG_DIR til det varige /data-volumet, slik at logghistorikken
# overlever container-rebuild og restart (Docker json-file-loggen gjør ikke det).
# Uten LOG_DIR (lokal utvikling) logges kun til konsoll — ingen atferdsendring.
LOG_DIR = os.environ.get('LOG_DIR')
if LOG_DIR:
    try:
        from logging.handlers import RotatingFileHandler
        os.makedirs(LOG_DIR, exist_ok=True)
        _log_handlers.append(RotatingFileHandler(
            os.path.join(LOG_DIR, 'fugleobs.log'),
            maxBytes=10 * 1024 * 1024,  # 10 MB per fil
            backupCount=5,              # behold 5 gamle filer (~60 MB totalt)
            encoding='utf-8',
        ))
    except Exception as e:
        # Fil-logging er en bonus – aldri la det stoppe oppstart.
        logging.getLogger('fugleobs').warning(f'Kunne ikke sette opp fil-logging til {LOG_DIR}: {e}')

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=_log_handlers,
)
logger = logging.getLogger('fugleobs')

from src.api_handlers import handle_species_search, handle_reverse_geocoding, handle_ao_sites_search, login_to_ao, mask_token
from src.html_templates import generate_stats_login_page, generate_stats_page, generate_error_page, generate_feedback_admin_page
from src import stats_store
from src import feedback_store
from src import email_notify
from src.utils import parse_user_agent
from src.ao_import_httpx import post_with_curl

# Lokal lokasjons-database (feature toggle via LOCATION_DB_PATH)
_location_db = None
_location_db_path = os.environ.get('LOCATION_DB_PATH')
if _location_db_path:
    try:
        from src.location_db import LocationDB
        _location_db = LocationDB(_location_db_path)
    except Exception as e:
        logging.getLogger('fugleobs').error(f'Kunne ikke initialisere LocationDB: {e}')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PUBLIC_DIR = os.path.join(BASE_DIR, 'public')

# Enkel in-memory statistikk (beskyttet av lock)
_stats_lock = threading.Lock()
_stats = {
    'total': 0,
    'per_ip': {},
    'per_ua': {},
    'devices': set(),
}

# Enkel throttling av tilbakemeldinger per IP (anonymt endepunkt → spam-vern).
# Maks FEEDBACK_MAX_PER_WINDOW innmeldinger per FEEDBACK_WINDOW_SEC sekunder.
_feedback_lock = threading.Lock()
_feedback_hits = {}  # ip -> liste av unix-tidsstempler
FEEDBACK_MAX_PER_WINDOW = 5
FEEDBACK_WINDOW_SEC = 600


class Handler(SimpleHTTPRequestHandler):
    """HTTP request handler med API-routing."""

    def do_OPTIONS(self):
        """Håndter CORS preflight requests."""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-AO-User-Id, X-AO-Login-Token, X-AO-Auth-Cookie')
        self.end_headers()

    def do_POST(self):
        """Håndter POST-forespørsler."""
        parsed = urlparse(self.path)

        if parsed.path == '/api/logview':
            self._handle_logview_post()
            return

        if parsed.path == '/api/ao-import':
            self._handle_ao_import_post()
            return

        if parsed.path == '/api/ao-import-stream':
            self._handle_ao_import_stream_post()
            return

        if parsed.path == '/api/ao-login':
            self._handle_ao_login_post()
            return

        if parsed.path == '/api/ao-refresh':
            self._handle_ao_refresh_post()
            return

        if parsed.path == '/api/ao-create-site':
            self._handle_ao_create_site_post()
            return

        if parsed.path == '/api/log-export':
            self._handle_log_export_post()
            return

        if parsed.path == '/api/ao-search-observers':
            self._handle_ao_search_observers_post()
            return

        if parsed.path == '/api/feedback':
            self._handle_feedback_post()
            return

        if parsed.path == '/api/feedback-status':
            self._handle_feedback_status_post(parsed)
            return

        # For alt annet, returner 404
        self.send_response(404)
        self.end_headers()
    
    def _handle_log_export_post(self):
        """Håndter logging av eksport-hendelse."""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(content_length)) if content_length else {}
            export_type = body.get('type', 'unknown')
            if export_type not in ('copy_open', 'direct'):
                export_type = 'unknown'
            stats_store.log_export(export_type)
        except Exception as e:
            logger.warning(f"[log-export] Feil: {e}")
        self._send_json({'ok': True})

    def _handle_ao_search_observers_post(self):
        """Proxy for å søke etter medobservatører på AO."""
        import httpx

        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(content_length)) if content_length else {}
            search = body.get('search', '').strip()

            login_token = body.get('loginToken', '').strip()
            auth_cookie = body.get('authCookie', '').strip()

            if not login_token or not auth_cookie:
                self._send_json({'error': 'Ikke innlogget'}, status=401)
                return

            if len(search) < 3:
                self._send_json([])
                return

            # Normaliser auth cookie
            auth_val = auth_cookie
            if auth_val.startswith('.ASPXAUTHNO='):
                auth_val = auth_val.split('=', 1)[1]

            cookies = {
                'logintoken': login_token,
                'logintoken_ssl': '1',
                '.ASPXAUTHNO': auth_val,
                'AcceptCookies': '1',
            }

            ao_payload = {
                'Search': search,
                'FilterByHasCollection': False,
                'IncludeAccountsFromOldPortals': False,
                'IncludeCurrentUserInResult': False,
                'includeDeletedUsersInResult': False,
                'TopListUsers': False,
            }

            with httpx.Client(cookies=cookies) as client:
                resp = client.post(
                    'https://www.artsobservasjoner.no/User/FindUsersByName',
                    json=ao_payload,
                    headers={
                        'Content-Type': 'application/json; charset=UTF-8',
                        'X-Requested-With': 'XMLHttpRequest',
                        'User-Agent': 'Mozilla/5.0 (compatible; Fugleobservasjoner/1.0)',
                    },
                    timeout=10,
                )
                resp.raise_for_status()
                data = resp.json()

            # Returner kun nødvendige felter
            results = []
            for user in data:
                results.append({
                    'id': user.get('Id'),
                    'name': user.get('PresentationName', '').strip(),
                    'city': user.get('City', ''),
                    'isCoObserver': user.get('IsCoObserver', False),
                })

            self._send_json(results)

        except Exception as e:
            logger.error(f'[AO-SEARCH-OBSERVERS] Feil: {e}')
            self._send_json([], status=200)

    def _handle_logview_post(self):
        """Håndter logging av sidevisning."""
        import uuid
        from http.cookies import SimpleCookie

        # Hent ekte IP-adresse (støtt for proxies)
        xff = self.headers.get('X-Forwarded-For')
        real_ip = xff.split(',')[0].strip() if xff else self.client_address[0]
        user_agent = self.headers.get('User-Agent', '-')

        # Les eller generer device_id fra cookie
        device_id = ''
        cookie_header = self.headers.get('Cookie', '')
        if 'device_id=' in cookie_header:
            c = SimpleCookie(cookie_header)
            if 'device_id' in c:
                device_id = c['device_id'].value

        set_cookie = False
        if not device_id:
            device_id = str(uuid.uuid4())
            set_cookie = True

        logger.debug(f"[LOGVIEW] IP: {real_ip} | UA: {user_agent} | Device: {device_id[:8]}...")

        # Oppdater in-memory statistikk
        with _stats_lock:
            _stats['total'] += 1
            _stats['per_ip'][real_ip] = _stats['per_ip'].get(real_ip, 0) + 1
            _stats['per_ua'][user_agent] = _stats['per_ua'].get(user_agent, 0) + 1
            _stats['devices'].add(device_id)

        # Logg til alle backends (fasaden håndterer SQLite + Supabase)
        stats_store.log_view(real_ip, user_agent, device_id=device_id)

        # Sett cookie hvis ny enhet (2 år levetid)
        if set_cookie:
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Set-Cookie', f'device_id={device_id}; Path=/; Max-Age=63072000; SameSite=Lax')
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
        else:
            self._send_json({'ok': True})

    def _feedback_rate_ok(self, ip):
        """True hvis IP-en ikke har oversteget throttlegrensen for tilbakemeldinger."""
        import time
        now = time.time()
        with _feedback_lock:
            hits = [t for t in _feedback_hits.get(ip, []) if now - t < FEEDBACK_WINDOW_SEC]
            if len(hits) >= FEEDBACK_MAX_PER_WINDOW:
                _feedback_hits[ip] = hits
                return False
            hits.append(now)
            _feedback_hits[ip] = hits
            return True

    def _handle_feedback_post(self):
        """Ta imot en brukertilbakemelding (feil/ønske) fra anonym bruker."""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8') if content_length else '{}'
            data = json.loads(body)

            # Honeypot: skjult felt som bare bots fyller ut. Later som alt gikk bra,
            # men lagrer ingenting.
            if (data.get('website') or '').strip():
                self._send_json({'ok': True, 'caseNo': feedback_store._generate_case_no()})
                return

            xff = self.headers.get('X-Forwarded-For')
            real_ip = xff.split(',')[0].strip() if xff else self.client_address[0]

            if not self._feedback_rate_ok(real_ip):
                self._send_json({'error': 'For mange innsendinger — prøv igjen senere.'}, status=429)
                return

            message = data.get('message', '')
            if not (message or '').strip():
                self._send_json({'error': 'Melding er påkrevd'}, status=400)
                return

            case_no = feedback_store.create_feedback(
                message=message,
                fb_type=data.get('type', 'annet'),
                email=data.get('email', ''),
                app_version=data.get('appVersion', ''),
                user_agent=self.headers.get('User-Agent', ''),
                ip=real_ip,
            )
            if not case_no:
                self._send_json({'error': 'Kunne ikke lagre tilbakemeldingen'}, status=500)
                return

            logger.info(f'[FEEDBACK] Ny sak {case_no} (type={data.get("type", "annet")})')

            # Send eier-varsel i bakgrunnen (best effort, no-op hvis ukonfigurert)
            # slik at brukerens svar ikke forsinkes av epost-utsending.
            ua_info = parse_user_agent(self.headers.get('User-Agent', ''))
            device = ' / '.join(v for v in (
                ua_info['device_type'], ua_info['os'], ua_info['browser']) if v and v != 'unknown')
            threading.Thread(
                target=email_notify.send_feedback_notification,
                kwargs={
                    'case_no': case_no,
                    'fb_type': data.get('type', 'annet'),
                    'message': (message or '').strip(),
                    'email': (data.get('email') or '').strip(),
                    'app_version': (data.get('appVersion') or '').strip(),
                    'device': device,
                },
                daemon=True,
            ).start()

            self._send_json({'ok': True, 'caseNo': case_no})
        except (json.JSONDecodeError, ValueError) as e:
            self._send_json({'error': f'Ugyldig forespørsel: {e}'}, status=400)
        except Exception as e:
            logger.error(f'[FEEDBACK] Feil: {e}')
            self._send_json({'error': 'Server-feil'}, status=500)

    def _handle_feedback_status_post(self, parsed):
        """Oppdater status på en sak (key-beskyttet admin-handling)."""
        expected_key = os.environ.get('STATS_KEY', 'salo')
        qs = parse_qs(parsed.query)
        if qs.get('key', [''])[0] != expected_key:
            self._send_json({'error': 'Ugyldig nøkkel'}, status=403)
            return
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            data = json.loads(self.rfile.read(content_length).decode('utf-8')) if content_length else {}
            ok = feedback_store.set_status(data.get('caseNo', ''), data.get('status', ''))
            self._send_json({'ok': ok}, status=200 if ok else 400)
        except Exception as e:
            self._send_json({'error': f'Ugyldig forespørsel: {e}'}, status=400)

    def _handle_ao_import_post(self):
        """Håndter direkte posting av observasjoner til AO (kun for eier)."""
        # Les request body
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            data = json.loads(body)
            observations = data.get('observations', [])
            login_token = data.get('loginToken')
            auth_cookie = data.get('authCookie')
            area_id = data.get('areaId', '')

            if not observations:
                self._send_json({'error': 'Ingen observasjoner å importere'}, status=400)
                return

            if not login_token or not auth_cookie:
                self._send_json({'error': 'Mangler loginToken eller authCookie'}, status=400)
                return

            logger.info(f'[AO-IMPORT] Mottatt {len(observations)} observasjoner, area={area_id}')

            # Post til AO med curl (tokens fra klient)
            result = post_with_curl(observations, login_token, auth_cookie, area_id=area_id)

            logger.info(f'[AO-IMPORT] Suksess: {result}')
            self._send_json(result)

        except ValueError as e:
            # Valideringsfeil eller AO-feil
            logger.error(f'[AO-IMPORT] Feil: {e}')
            self._send_json({'error': str(e)}, status=400)
        except Exception as e:
            # Uventet feil
            logger.error(f'[AO-IMPORT] Uventet feil: {e}')
            self._send_json({'error': f'Server-feil: {str(e)}'}, status=500)

    def _handle_ao_import_stream_post(self):
        """
        Som _handle_ao_import_post, men streamer fremdrift til klienten via SSE.

        Sender events (data: {json}\\n\\n) med fasene: importing → publishing → done/error.
        Fremdriften polles fra AO (NumberOfSightingsImporting) i post_with_curl.
        """
        # Valider request FØR vi bytter til event-stream (så vi kan svare med vanlig JSON-feil)
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            data = json.loads(body)
            observations = data.get('observations', [])
            login_token = data.get('loginToken')
            auth_cookie = data.get('authCookie')
            area_id = data.get('areaId', '')

            if not observations:
                self._send_json({'error': 'Ingen observasjoner å importere'}, status=400)
                return
            if not login_token or not auth_cookie:
                self._send_json({'error': 'Mangler loginToken eller authCookie'}, status=400)
                return
        except Exception as e:
            self._send_json({'error': f'Ugyldig forespørsel: {e}'}, status=400)
            return

        # Start SSE-strøm
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('X-Accel-Buffering', 'no')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()

        def emit(event):
            try:
                self.wfile.write(f'data: {json.dumps(event)}\n\n'.encode('utf-8'))
                self.wfile.flush()
            except Exception:
                pass  # Klienten kan ha koblet fra — la importen fullføre uansett

        logger.info(f'[AO-IMPORT-STREAM] Mottatt {len(observations)} observasjoner, area={area_id}')
        try:
            result = post_with_curl(observations, login_token, auth_cookie,
                                    area_id=area_id, progress_cb=emit)
            if result.get('success'):
                emit({'phase': 'done', **result})
            else:
                emit({'phase': 'error', **result})
            logger.info(f'[AO-IMPORT-STREAM] Ferdig: {result}')
        except ValueError as e:
            logger.error(f'[AO-IMPORT-STREAM] Feil: {e}')
            emit({'phase': 'error', 'error': str(e)})
        except Exception as e:
            logger.error(f'[AO-IMPORT-STREAM] Uventet feil: {e}')
            emit({'phase': 'error', 'error': f'Server-feil: {str(e)}'})

    def _handle_ao_login_post(self):
        """Håndter innlogging til AO med brukernavn/passord."""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            data = json.loads(body)

            username = data.get('username', '').strip()
            password = data.get('password', '').strip()

            if not username or not password:
                self._send_json({'error': 'Brukernavn og passord er påkrevd'}, status=400)
                return

            logger.info(f'[AO-LOGIN] Innloggingsforsøk for bruker: {username}')

            # Logg inn via api_handlers
            result = login_to_ao(username, password)

            logger.info(f'[AO-LOGIN] Vellykket for user_id={result.get("userId")}')
            self._send_json({
                'success': True,
                'authCookie': result['authCookie'],
                'loginToken': result['loginToken'],
                'userId': result['userId']
            })

        except ValueError as e:
            logger.error(f'[AO-LOGIN] Feil: {e}')
            self._send_json({'error': str(e)}, status=401)
        except Exception as e:
            logger.error(f'[AO-LOGIN] Uventet feil: {e}')
            self._send_json({'error': f'Server-feil: {str(e)}'}, status=500)

    def _handle_ao_refresh_post(self):
        """Håndter refresh av AO session token."""
        import httpx

        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            data = json.loads(body)

            login_token = data.get('loginToken', '').strip()
            auth_cookie = data.get('authCookie', '').strip()
            user_id = data.get('userId', '').strip()

            logger.debug(f'[AO-REFRESH] Session refresh: loginToken={mask_token(login_token)}, authCookie={mask_token(auth_cookie)}, userId={user_id}')

            if not login_token:
                self._send_json({'error': 'loginToken er påkrevd'}, status=400)
                return

            # Husk-meg-revival: KUN logintoken + logintoken_ssl, INGEN .ASPXAUTHNO
            # (en gammel/død cookie kortslutter AO sin auto-login), og mot FORSIDEN «/»
            # (beskyttede sider redirecter til /LogOn før husk-meg-logikken kjører).
            cookies = {'logintoken': login_token, 'logintoken_ssl': '1', 'AcceptCookies': '1'}

            probe_url = 'https://www.artsobservasjoner.no/'
            logger.debug(f'[AO-REFRESH] Husk-meg-revival mot: {probe_url}')

            # VIKTIG: Sett cookies på CLIENT-nivå, ikke request-nivå!
            # Per-request cookies sendes kun med første request og videresendes IKKE ved redirects.
            # Client-level cookies sendes med ALLE requests i redirect-kjeden.
            with httpx.Client(cookies=cookies) as client:
                response = client.get(
                    probe_url,
                    headers={'User-Agent': 'Mozilla/5.0 (compatible; Fugleobservasjoner/1.0)'},
                    timeout=15,
                    follow_redirects=True
                )
                # Finn nye cookies fra jar (unngå dict() som krasjer ved duplikater)
                cookie_names = [c.name for c in client.cookies.jar]
                refreshed_auth = None
                refreshed_login_token = None
                for cookie in client.cookies.jar:
                    if cookie.name == '.ASPXAUTHNO' and cookie.value:
                        refreshed_auth = cookie.value
                    elif cookie.name == 'logintoken' and cookie.value != login_token:
                        refreshed_login_token = cookie.value

            logger.debug(f'[AO-REFRESH] Response: status={response.status_code}, url={response.url}, cookies={cookie_names}')
            if refreshed_auth:
                logger.debug(f'[AO-REFRESH] Ny authCookie: {mask_token(refreshed_auth)}')
            if refreshed_login_token:
                logger.debug(f'[AO-REFRESH] Ny loginToken: {mask_token(refreshed_login_token)}')

            result = {}
            if refreshed_auth:
                result['refreshedAuthCookie'] = refreshed_auth
            if refreshed_login_token:
                result['refreshedLoginToken'] = refreshed_login_token

            if not result:
                # Ingen .ASPXAUTHNO fra revival = logintoken utløpt/ugyldig (forsiden
                # redirecter ikke til /LogOn, så vi kan ikke basere oss på det).
                logger.info('[AO-REFRESH] Revival mislyktes - logintoken utløpt, krever ny innlogging')
                result['error'] = 'Token utløpt - krever ny innlogging'

            self._send_json(result)

        except Exception as e:
            logger.error(f'[AO-REFRESH] Feil: {e}')
            self._send_json({'error': str(e)}, status=500)

    def _handle_ao_create_site_post(self):
        """Håndter opprettelse av ny AO-lokasjon."""
        from src.ao_create_site import create_ao_site

        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            data = json.loads(body)

            name = data.get('name', '').strip()
            lat = data.get('lat')
            lon = data.get('lon')
            accuracy = data.get('accuracy', 50)
            login_token = data.get('loginToken', '').strip()
            auth_cookie = data.get('authCookie', '').strip()

            if not name:
                self._send_json({'error': 'Navn er påkrevd'}, status=400)
                return

            if lat is None or lon is None:
                self._send_json({'error': 'Koordinater er påkrevd'}, status=400)
                return

            if not login_token or not auth_cookie:
                self._send_json({'error': 'Mangler loginToken eller authCookie'}, status=401)
                return

            lat = float(lat)
            lon = float(lon)
            accuracy = int(accuracy)

            logger.info(f'[AO-CREATE-SITE] Oppretter "{name}" ved {lat}, {lon} (±{accuracy}m)')

            result = create_ao_site(name, lat, lon, accuracy, login_token, auth_cookie)

            logger.info(f'[AO-CREATE-SITE] Resultat: {result}')
            self._send_json(result)

        except (ValueError, TypeError) as e:
            logger.error(f'[AO-CREATE-SITE] Valideringsfeil: {e}')
            self._send_json({'error': str(e)}, status=400)
        except Exception as e:
            logger.error(f'[AO-CREATE-SITE] Uventet feil: {e}')
            self._send_json({'error': f'Server-feil: {str(e)}'}, status=500)

    def log_message(self, format, *args):
        """Overstyr BaseHTTPRequestHandler sin innebygde request-logging."""
        logger.debug(f"{self.client_address[0]} - {format % args}")

    def do_GET(self):
        """Håndter GET-forespørsler."""
        logger.debug(f"IP: {self.client_address[0]} | UA: {self.headers.get('User-Agent', '-')} | PATH: {self.path}")
        
        parsed = urlparse(self.path)
        
        # Route til riktig handler
        try:
            if parsed.path == '/health':
                import time
                self._send_json({'status': 'ok', 'timestamp': time.time()})
                return
            if parsed.path == '/stats':
                self._handle_stats_page(parsed)
                return
            if parsed.path == '/feedback':
                self._handle_feedback_page(parsed)
                return
            elif parsed.path == '/api/species':
                self._handle_species_api(parsed)
            elif parsed.path == '/api/reverse':
                self._handle_reverse_api(parsed)
            elif parsed.path == '/api/ao-sites':
                self._handle_ao_sites_api(parsed)
            elif parsed.path == '/api/ao-private-sites':
                self._handle_ao_private_sites_api()
            elif parsed.path == '/api/ao-areas':
                self._handle_ao_areas_api(parsed)
            elif parsed.path == '/api/ao-autocomplete':
                self._handle_ao_autocomplete_api(parsed)
            else:
                self._handle_static_files(parsed)
        except Exception as e:
            logger.error(f"Feil i {parsed.path}: {e}")
            self._send_error_response(str(e))
    
    def _handle_stats_page(self, parsed):
        """Håndter statistikk-siden."""
        expected_key = os.environ.get('STATS_KEY', 'salo')
        qs = parse_qs(parsed.query)
        provided_key = qs.get('key', [''])[0]
        
        # Sjekk autentisering
        if provided_key != expected_key:
            self._send_html_response(generate_stats_login_page())
            return
        
        # Hent data via fasaden (SQLite primær, Supabase fallback)
        stats, source = stats_store.get_stats()
        if stats:
            html = generate_stats_page(
                stats["recent_ips"],
                {},
                stats["total"],
                {},
                per_os=stats["per_os"],
                per_browser=stats["per_browser"],
                total_unique_ips=stats["total_unique_ips"],
                source=source,
                total_unique_devices=stats["total_unique_devices"],
                exports=stats["exports"],
                trend_30d=stats.get("trend_30d"),
                unique_devices_per_day=stats.get("unique_devices_per_day"),
                unique_users_per_week=stats.get("unique_users_per_week"),
            )
        else:
            # Fallback til in-memory statistikk
            with _stats_lock:
                total = _stats['total']
                per_ip = dict(_stats['per_ip'])
                per_ua = dict(_stats['per_ua'])
                unique_devices = len(_stats['devices'])
            recent_ips = list(per_ip.items())[:10]
            html = generate_stats_page(
                recent_ips,
                per_ua,
                total,
                {},
                {},
                {},
                len(per_ip),
                source="In-memory (denne økt)",
                total_unique_devices=unique_devices,
            )
        self._send_html_response(html)

    def _handle_feedback_page(self, parsed):
        """Key-beskyttet admin-visning av innmeldte tilbakemeldinger."""
        expected_key = os.environ.get('STATS_KEY', 'salo')
        qs = parse_qs(parsed.query)
        provided_key = qs.get('key', [''])[0]
        if provided_key != expected_key:
            self._send_html_response(generate_stats_login_page())
            return

        status_filter = qs.get('status', [''])[0]
        items = feedback_store.list_feedback(status=status_filter)
        counts = feedback_store.count_by_status()
        html = generate_feedback_admin_page(items, counts, provided_key, status_filter)
        self._send_html_response(html)

    def _handle_species_api(self, parsed):
        """Håndter arts-søk API."""
        params = parse_qs(parsed.query)
        search = params.get('search', [''])[0].strip()
        dont_include_sub = params.get('dontIncludeSubSpecies', ['true'])[0]
        ao_base = os.environ.get(
            'AO_URL', 'https://www.artsobservasjoner.no'
        )
        try:
            results = handle_species_search(search, dont_include_sub, ao_base)
            self._send_json(results)
        except Exception as e:
            self._send_json({'error': 'Feil ved henting fra Artsobservasjoner.'}, status=500)
    
    def _handle_reverse_api(self, parsed):
        """Håndter reverse geokoding API."""
        params = parse_qs(parsed.query)
        lat = params.get('lat', [''])[0].strip()
        lon = params.get('lon', [''])[0].strip()
        
        # Hent Nominatim URL fra miljøvariabler
        nominatim_base = os.environ.get(
            'NOMINATIM_URL', 'https://nominatim.openstreetmap.org/reverse'
        )
        
        try:
            name = handle_reverse_geocoding(lat, lon, nominatim_base)
            self._send_json({'name': name})
        except ValueError as e:
            self._send_json({'error': str(e)}, status=400)
        except Exception as e:
            self._send_json({'error': 'Feil ved henting av stedsnavn.'}, status=500)
    
    def _handle_ao_sites_api(self, parsed):
        """Håndter AO-lokaliteter API."""
        params = parse_qs(parsed.query)
        lat_raw = params.get('lat', [''])[0].strip()
        lon_raw = params.get('lon', [''])[0].strip()
        size_raw = params.get('size', ['600'])[0].strip()
        
        # Hent bruker-auth fra headers (sendt fra frontend)
        # Ny enkel måte: kun loginToken trengs (userId ekstraheres, authCookie hentes automatisk)
        login_token = self.headers.get('X-AO-Login-Token', '').strip() or None
        
        # Bakoverkompatibilitet: godta fortsatt separate verdier
        user_id = self.headers.get('X-AO-User-Id', '').strip() or None
        auth_cookie = self.headers.get('X-AO-Auth-Cookie', '').strip() or None
        
        # Hvis vi har loginToken men ikke user_id, ekstraher fra loginToken
        if login_token and not user_id and ':' in login_token:
            user_id = login_token.split(':')[0]
            logger.debug(f'ao-sites: Ekstraherte user_id={user_id} fra loginToken')

        logger.debug(f'ao-sites mottok auth: user_id={user_id is not None}, login_token={login_token is not None}, auth_cookie={auth_cookie is not None}')
        
        ao_mobile_base = os.environ.get(
            'AO_MOBILE_URL', 'https://mobil.artsobservasjoner.no'
        )
        try:
            sites, refreshed_auth_cookie, auth_failed = handle_ao_sites_search(lat_raw, lon_raw, size_raw, ao_mobile_base, user_id, login_token, auth_cookie, location_db=_location_db)
            response_data = {'sites': sites}
            logger.debug(f'ao-sites refresh: refreshed={refreshed_auth_cookie is not None}, auth_failed={auth_failed}')
            if refreshed_auth_cookie:
                response_data['refreshedAuthCookie'] = refreshed_auth_cookie
                logger.debug(f'Sender refreshed auth cookie til frontend: {mask_token(refreshed_auth_cookie)}')
            if auth_failed:
                response_data['authRequired'] = True
                logger.debug(f'Auth feilet - sender authRequired=true til frontend')
            self._send_json(response_data)
        except ValueError as e:
            self._send_json({'error': str(e)}, status=400)
        except Exception:
            # Ikke la dette knekke klienten – returner bare tom liste
            self._send_json({'sites': []})

    def _handle_ao_private_sites_api(self):
        """Hent alle brukerens private lokasjoner via BindUserSitesGrid."""
        from src.api_handlers import handle_ao_private_sites
        auth_cookie = self.headers.get('X-AO-Auth-Cookie', '').strip() or None
        login_token = self.headers.get('X-AO-Login-Token', '').strip() or None
        user_id = self.headers.get('X-AO-User-Id', '').strip() or None
        if not auth_cookie:
            self._send_json({'error': 'Ikke innlogget'}, status=401)
            return
        ao_base = os.environ.get('AO_URL', 'https://www.artsobservasjoner.no')
        try:
            sites, refreshed_auth_cookie = handle_ao_private_sites(
                auth_cookie, ao_base, login_token=login_token, user_id=user_id)
            response_data = {'sites': sites}
            if refreshed_auth_cookie:
                response_data['refreshedAuthCookie'] = refreshed_auth_cookie
            self._send_json(response_data)
        except Exception as e:
            logger.warning(f'[AO-PRIVATE-SITES] Feil: {e}')
            self._send_json({'error': 'Kunne ikke hente private lokasjoner'}, status=500)

    def _handle_ao_areas_api(self, parsed):
        """Proxy for AO område-søk (politiske grenser). Åpent API med access-key."""
        import httpx

        params = parse_qs(parsed.query)
        search = params.get('search', [''])[0].strip()
        if not search or len(search) < 2:
            self._send_json([])
            return

        ao_url = f'https://www.artsobservasjoner.no/Api/Areas/politicalboundary/{search}/'
        try:
            with httpx.Client() as client:
                response = client.get(
                    ao_url,
                    headers={
                        'access-key': '20a2d12937024a7391c10871d35bcc3a',
                        'X-Requested-With': 'XMLHttpRequest',
                    },
                    timeout=10
                )
                response.raise_for_status()
                data = response.json()
            self._send_json(data)
        except Exception as e:
            logger.error(f'[AO-AREAS] Feil: {e}')
            self._send_json([])

    def _handle_ao_autocomplete_api(self, parsed):
        """Proxy for AO autocomplete-søk på lokaliteter."""
        from src.api_handlers import fetch_ao_autocomplete

        params = parse_qs(parsed.query)
        term = params.get('term', [''])[0].strip()
        login_token = self.headers.get('X-AO-Login-Token', '').strip()
        auth_cookie = self.headers.get('X-AO-Auth-Cookie', '').strip()
        user_id = self.headers.get('X-AO-User-Id', '').strip()

        try:
            lat = float(params.get('lat', [None])[0]) if params.get('lat') else None
            lon = float(params.get('lon', [None])[0]) if params.get('lon') else None
        except (ValueError, TypeError):
            lat, lon = None, None

        if not term or len(term) < 2:
            self._send_json({'results': [], 'refreshed_auth_cookie': None})
            return

        logger.debug(f'[AO-AUTOCOMPLETE] Søk: term={term}, autentisert={bool(login_token and auth_cookie)}, user_id={user_id}, pos={lat},{lon}')

        try:
            # Kall autocomplete med lokal DB + AO
            data = fetch_ao_autocomplete(
                term=term,
                login_token=login_token if login_token else None,
                auth_cookie=auth_cookie if auth_cookie else None,
                user_id=user_id if user_id else None,
                location_db=_location_db,
                lat=lat,
                lon=lon,
            )
            # data er nå {'results': [...], 'refreshed_auth_cookie': ...}
            self._send_json(data)
        except Exception as e:
            logger.error(f'[AO-AUTOCOMPLETE] Feil: {e}')
            self._send_json({'results': [], 'refreshed_auth_cookie': None})

    def _handle_static_files(self, parsed):
        """Håndter statiske filer."""
        if parsed.path == '/':
            self.path = '/public/index.html'
        elif parsed.path.startswith('/public/'):
            # La SimpleHTTPRequestHandler håndtere dette direkte
            pass
        else:
            # Prøv å mappe til public-katalogen
            candidate = os.path.join(PUBLIC_DIR, parsed.path.lstrip('/'))
            real_candidate = os.path.realpath(candidate)
            if (real_candidate.startswith(os.path.realpath(PUBLIC_DIR) + os.sep)
                    and os.path.isfile(real_candidate)):
                self.path = '/public/' + parsed.path.lstrip('/')
            else:
                # Filaktige stier (med filendelse) som ikke finnes skal gi ekte 404.
                # Index.html-fallback her ble liggende i Cloudflare-cachen (4 t):
                # et manglende bilde ble servert som appen uten CSS.
                _, ext = os.path.splitext(parsed.path)
                if ext:
                    self.send_response(404)
                    self.send_header('Cache-Control', 'no-store')
                    self._cache_header_set = True
                    self.end_headers()
                    return
                # Pene URL-er uten filendelse faller tilbake til index.html
                self.path = '/public/index.html'
        
        return super().do_GET()

    def translate_path(self, path):
        """Mappe URL-path til filsystemet under PUBLIC_DIR for /public/*.

        SimpleHTTPRequestHandler sin standardoppførsel er å bruke cwd.
        Vi overstyrer for å peke eksplisitt på ./public.
        """
        path = super().translate_path(path)

        # Sørg for at alt under /public havner i PUBLIC_DIR
        rel = os.path.relpath(path, os.getcwd())
        if rel.startswith('public' + os.sep):
            return os.path.join(BASE_DIR, rel)
        return path

    def end_headers(self):
        """Legg til Cache-Control headers for å unngå aggressive mobilcache."""
        # Respekter eksplisitt satt Cache-Control (f.eks. no-store på 404)
        if getattr(self, '_cache_header_set', False):
            self._cache_header_set = False
            super().end_headers()
            return
        # HTML-filer: Alltid revalider med server (inkluderer root path /)
        if self.path.endswith('.html') or self.path == '/' or self.path == '/public/index.html':
            self.send_header('Cache-Control', 'no-cache, must-revalidate')
        # JS/CSS: Kort cache (5 minutter) for bedre ytelse
        elif self.path.endswith(('.js', '.css')):
            self.send_header('Cache-Control', 'max-age=300')
        # Andre filer: Standard 1-time cache
        else:
            self.send_header('Cache-Control', 'max-age=3600')

        super().end_headers()

    def _send_json(self, data, status=200):
        """Send JSON-respons til klient."""
        payload = json.dumps(data).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(payload)
    
    def _send_html_response(self, html, status=200):
        """Send HTML-respons til klient."""
        payload = html.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
    
    def _send_error_response(self, error_msg, status=500):
        """Send feilrespons til klient."""
        error_data = {'error': error_msg}
        self._send_json(error_data, status=status)


def run(port=3000):
    """Start HTTP-serveren."""
    os.chdir(BASE_DIR)
    server_address = ('', port)
    httpd = ThreadingHTTPServer(server_address, Handler)
    logger.info(f'Server kjører på port {port} (log_level={LOG_LEVEL})')
    httpd.serve_forever()


if __name__ == '__main__':
    # Bruk PORT fra miljøvariabel dersom den er satt
    env_port = os.environ.get('PORT')
    try:
        port = int(env_port) if env_port else 3000
    except ValueError:
        port = 3000
    run(port)
