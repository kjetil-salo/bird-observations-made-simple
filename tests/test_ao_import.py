"""
Tester for AO-import funksjonalitet (CSV-generering og httpx-basert import).
"""

import json
import os
import sys
import threading
import time
from http.server import HTTPServer
from unittest.mock import MagicMock, Mock

import pytest
import requests
import httpx

# Ensure repo root is importable
REPO_ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, REPO_ROOT)

from src.ao_import import observations_to_csv
from src.ao_import_httpx import (
    fetch_csrf_tokens,
    number_of_sightings_importing,
    number_of_sightings_submitted,
    post_with_curl,
    publish_all,
)
from server import Handler


def start_server(port):
    """Start test server på gitt port."""
    server = HTTPServer(('', port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


class MockSubprocessResult:
    """Mock for subprocess.run returnverdi."""
    def __init__(self, stdout='', stderr='', returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


# ============================================================================
# Del 1: CSV-generering tester
# ============================================================================

def test_observations_to_csv_basic():
    """Test enkel observasjon → CSV med norske tegn (æøå)."""
    observations = [{
        'species': {'taxonName': 'Gråspurv'},
        'timestamp': '2024-01-15T14:30:00Z',
        'placeName': 'Østensjøvannet',
        'count': '2',
        'activity': 'Stasjonær'
    }]

    csv = observations_to_csv(observations)

    # Verifiser grunnleggende format
    assert '\t' in csv  # Tab-separert
    assert '\r\n' in csv  # Windows line endings
    assert 'Gråspurv' in csv
    assert 'Østensjøvannet' in csv
    assert '15.01.2024' in csv  # Dato-format DD.MM.YYYY
    assert '14:30' in csv  # Tid-format HH:MM
    assert 'Stasjonær' in csv

    # Verifiser header
    lines = csv.split('\r\n')
    assert lines[0].startswith('Artsnavn\tLokalitetsnavn')
    assert 'Medobservatør' in lines[0]


def test_observations_to_csv_with_coobservers():
    """Test med 1-10 medobservatører."""
    observations = [{
        'species': {'taxonName': 'Skjære'},
        'timestamp': '2024-02-20T09:15:00Z',
        'placeName': 'Sognsvann',
        'count': '1',
        'activity': 'Rastende',
        'coObservers': ['Per Hansen', 'Kari Nordmann', 'Ole Olsen']
    }]

    csv = observations_to_csv(observations)
    lines = csv.split('\r\n')
    data_row = lines[1]  # Første data-rad (etter header)
    fields = data_row.split('\t')

    # Finn medobservatør-kolonner (kolonne 17-26)
    # Header: Artsnavn, Lokalitet, ..., Kommentar, Privat, Skjul (17 kolonner)
    # Så 10 medobservatør-kolonner
    medobs_start = 17
    medobs_fields = fields[medobs_start:medobs_start + 10]

    assert medobs_fields[0] == 'Per Hansen'
    assert medobs_fields[1] == 'Kari Nordmann'
    assert medobs_fields[2] == 'Ole Olsen'
    # Resten skal være tomme
    for i in range(3, 10):
        assert medobs_fields[i] == ''


def test_observations_to_csv_with_many_coobservers():
    """Test overskridelse: > 10 medobs → kun første 10 brukes."""
    # Lag 12 medobservatører
    many_coobs = [f'Person {i}' for i in range(1, 13)]

    observations = [{
        'species': {'taxonName': 'Svale'},
        'timestamp': '2024-03-10T12:00:00Z',
        'placeName': 'Bygdøy',
        'count': '5',
        'coObservers': many_coobs
    }]

    csv = observations_to_csv(observations)
    lines = csv.split('\r\n')
    data_row = lines[1]
    fields = data_row.split('\t')

    medobs_start = 17
    medobs_fields = fields[medobs_start:medobs_start + 10]

    # Kun de 10 første skal være med
    for i in range(10):
        assert medobs_fields[i] == f'Person {i + 1}'

    # Person 11 og 12 skal IKKE være med
    assert 'Person 11' not in data_row
    assert 'Person 12' not in data_row


def test_observations_to_csv_uses_place_id_over_name():
    """Verifiser at placeId brukes i stedet for placeName når tilgjengelig."""
    observations = [{
        'species': {'taxonName': 'Gråspurv'},
        'timestamp': '2024-01-15T14:00:00Z',
        'placeName': 'Litleholmen',
        'placeId': 12345,
        'count': '1'
    }]
    csv = observations_to_csv(observations)
    lines = csv.split('\r\n')
    fields = lines[1].split('\t')
    assert fields[1] == '12345'
    assert 'Litleholmen' not in csv


def test_observations_to_csv_falls_back_to_name_when_no_id():
    """Verifiser at placeName brukes når placeId mangler."""
    observations = [{
        'species': {'taxonName': 'Gråspurv'},
        'timestamp': '2024-01-15T14:00:00Z',
        'placeName': 'Litleholmen',
        'count': '1'
    }]
    csv = observations_to_csv(observations)
    lines = csv.split('\r\n')
    fields = lines[1].split('\t')
    assert fields[1] == 'Litleholmen'


def test_observations_to_csv_hide_until():
    """Verifiser at hideUntil konverteres riktig til DD.MM.YYYY i kolonne 16."""
    observations = [{
        'species': {'taxonName': 'Hønsehauk'},
        'timestamp': '2024-06-01T10:00:00Z',
        'placeName': 'Oslomarka',
        'count': '1',
        'hideUntil': '2024-08-20',
    }]
    csv = observations_to_csv(observations)
    lines = csv.split('\r\n')
    fields = lines[1].split('\t')
    assert fields[16] == '20.08.2024'


def test_observations_to_csv_hide_until_empty_when_not_set():
    """Verifiser at kolonne 16 er tom når hideUntil ikke er satt."""
    observations = [{
        'species': {'taxonName': 'Spurvehauk'},
        'timestamp': '2024-06-01T10:00:00Z',
        'placeName': 'Oslomarka',
        'count': '1',
    }]
    csv = observations_to_csv(observations)
    lines = csv.split('\r\n')
    fields = lines[1].split('\t')
    assert fields[16] == ''


def test_observations_to_csv_time_omitted_when_midnight():
    """Verifiser at tid utelates hvis 00:00."""
    observations = [{
        'species': {'taxonName': 'Rørhøne'},
        'timestamp': '2024-05-01T00:00:00Z',
        'placeName': 'Maridalsvannet',
        'count': '1'
    }]

    csv = observations_to_csv(observations)
    lines = csv.split('\r\n')
    data_row = lines[1]

    # Dato skal være med
    assert '01.05.2024' in data_row

    # Tid skal IKKE være med (kolonne 8 og 9 skal være tomme)
    fields = data_row.split('\t')
    # Fra klokkeslett (kolonne 8), Til klokkeslett (kolonne 9)
    assert fields[8] == ''
    assert fields[9] == ''


# ============================================================================
# Del 2: CSRF Token Parsing
# ============================================================================

def test_fetch_csrf_tokens_success(monkeypatch):
    """Test vellykket CSRF token-henting."""
    # Mock httpx response
    mock_response = Mock()
    mock_response.text = '<input name="__RequestVerificationToken" value="FORM789" />'
    mock_response.status_code = 200
    mock_response.cookies = httpx.Cookies()
    mock_response.cookies.set('__RequestVerificationToken', 'COOKIE123')
    mock_response.cookies.set('.ASPXAUTHNO', 'REFRESHED456')

    def mock_raise_for_status():
        pass
    mock_response.raise_for_status = mock_raise_for_status

    # Mock httpx.Client - client.cookies akkumulerer alle cookies fra redirect-kjeden
    client_cookies = httpx.Cookies()
    client_cookies.set('__RequestVerificationToken', 'COOKIE123')
    client_cookies.set('.ASPXAUTHNO', 'REFRESHED456')

    mock_client = Mock()
    mock_client.__enter__ = Mock(return_value=mock_client)
    mock_client.__exit__ = Mock(return_value=None)
    mock_client.get = Mock(return_value=mock_response)
    mock_client.cookies = client_cookies

    monkeypatch.setattr('httpx.Client', lambda **kwargs: mock_client)

    # Test
    form_token, cookie_token, refreshed_auth = fetch_csrf_tokens('LOGIN123', 'AUTH456')

    assert form_token == 'FORM789'
    assert cookie_token == 'COOKIE123'
    assert refreshed_auth == 'REFRESHED456'


def test_fetch_csrf_tokens_httponly_cookie(monkeypatch):
    """Test parsing av HttpOnly cookies (httpx håndterer dette automatisk)."""
    # Mock httpx response med HttpOnly cookie
    mock_response = Mock()
    mock_response.text = '<input name="__RequestVerificationToken" value="FORMTOKEN" />'
    mock_response.status_code = 200
    mock_response.cookies = httpx.Cookies()
    mock_response.cookies.set('__RequestVerificationToken', 'HTTPONLY789')  # httpx håndterer HttpOnly automatisk

    def mock_raise_for_status():
        pass
    mock_response.raise_for_status = mock_raise_for_status

    # Mock httpx.Client - client.cookies akkumulerer alle cookies fra redirect-kjeden
    client_cookies = httpx.Cookies()
    client_cookies.set('__RequestVerificationToken', 'HTTPONLY789')

    mock_client = Mock()
    mock_client.__enter__ = Mock(return_value=mock_client)
    mock_client.__exit__ = Mock(return_value=None)
    mock_client.get = Mock(return_value=mock_response)
    mock_client.cookies = client_cookies

    monkeypatch.setattr('httpx.Client', lambda **kwargs: mock_client)

    form_token, cookie_token, refreshed_auth = fetch_csrf_tokens('LOGIN', 'AUTH')

    assert cookie_token == 'HTTPONLY789'
    assert form_token == 'FORMTOKEN'


# ============================================================================
# Del 3: post_with_curl Integration
# ============================================================================

def test_post_with_curl_success(monkeypatch):
    """Test vellykket post til AO med httpx."""
    # Mock fetch_csrf_tokens
    def fake_fetch_csrf(login_token, auth_cookie):
        return ('FORM123', 'COOKIE456', 'REFRESHED789')

    monkeypatch.setattr('src.ao_import_httpx.fetch_csrf_tokens', fake_fetch_csrf)

    # Mock httpx.Client for POST
    mock_response = Mock()
    mock_response.text = '<html><body>Import vellykket</body></html>'
    mock_response.status_code = 200

    mock_client = Mock()
    mock_client.__enter__ = Mock(return_value=mock_client)
    mock_client.__exit__ = Mock(return_value=None)
    mock_client.post = Mock(return_value=mock_response)

    monkeypatch.setattr('httpx.Client', lambda: mock_client)

    # Mock time.sleep
    monkeypatch.setattr('time.sleep', lambda x: None)

    # Mock publish_all
    def fake_publish(login_token, auth_cookie):
        return {'status': 200}

    monkeypatch.setattr('src.ao_import_httpx.publish_all', fake_publish)

    # Mock file writes
    write_calls = []

    original_open = open

    def fake_open(path, *args, **kwargs):
        if '/tmp/' in str(path) and 'w' in args:
            # Mock write
            class FakeFile:
                def write(self, content):
                    write_calls.append((path, content))

                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    pass

            return FakeFile()
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr('builtins.open', fake_open)

    # Test
    observations = [
        {'species': {'taxonName': 'Gråspurv'}, 'count': '1', 'timestamp': '2024-01-15T14:00:00Z', 'placeName': 'Oslo'}
    ]
    result = post_with_curl(observations, 'LOGIN123', 'AUTH456')

    assert result['success'] is True
    assert result['count'] == 1
    assert result['published'] is True
    assert result['refreshedAuthCookie'] == 'REFRESHED789'
    assert mock_client.post.called


def test_post_with_curl_reports_held_back(monkeypatch):
    """Rader AO underkjenner blir liggende i gjennomgangskøen — det skal meldes fra om."""
    monkeypatch.setattr('src.ao_import_httpx.fetch_csrf_tokens',
                        lambda lt, ac: ('FORM123', 'COOKIE456', None))

    mock_response = Mock()
    mock_response.text = '<html><body>Import vellykket</body></html>'
    mock_response.status_code = 200

    mock_client = Mock()
    mock_client.__enter__ = Mock(return_value=mock_client)
    mock_client.__exit__ = Mock(return_value=None)
    mock_client.post = Mock(return_value=mock_response)

    monkeypatch.setattr('httpx.Client', lambda: mock_client)
    monkeypatch.setattr('time.sleep', lambda x: None)
    monkeypatch.setattr('src.ao_import_httpx.publish_all', lambda lt, ac: {'status': 200})
    # AO svarer at én observasjon fortsatt ligger til gjennomgang etter publisering
    monkeypatch.setattr('src.ao_import_httpx.number_of_sightings_submitted', lambda lt, ac: 1)

    observations = [
        {'species': {'taxonName': 'Tårnseiler'}, 'count': '6', 'timestamp': '2024-01-15T14:00:00Z', 'placeName': 'Hylkje'}
    ]
    result = post_with_curl(observations, 'LOGIN123', 'AUTH456')

    assert result['success'] is True
    assert result['heldBack'] == 1
    assert 'ikke publisert' in result['message']


def test_post_with_curl_no_held_back_when_queue_empty(monkeypatch):
    """Tom gjennomgangskø etter publisering → ingen heldBack, ren suksess."""
    monkeypatch.setattr('src.ao_import_httpx.fetch_csrf_tokens',
                        lambda lt, ac: ('FORM123', 'COOKIE456', None))

    mock_response = Mock()
    mock_response.text = '<html><body>OK</body></html>'
    mock_response.status_code = 200

    mock_client = Mock()
    mock_client.__enter__ = Mock(return_value=mock_client)
    mock_client.__exit__ = Mock(return_value=None)
    mock_client.post = Mock(return_value=mock_response)

    monkeypatch.setattr('httpx.Client', lambda: mock_client)
    monkeypatch.setattr('time.sleep', lambda x: None)
    monkeypatch.setattr('src.ao_import_httpx.publish_all', lambda lt, ac: {'status': 200})
    monkeypatch.setattr('src.ao_import_httpx.number_of_sightings_submitted', lambda lt, ac: 0)

    observations = [
        {'species': {'taxonName': 'Gråspurv'}, 'count': '1', 'timestamp': '2024-01-15T14:00:00Z', 'placeName': 'Oslo'}
    ]
    result = post_with_curl(observations, 'LOGIN123', 'AUTH456')

    assert result['success'] is True
    assert 'heldBack' not in result


# ============================================================================
# Del 4: publish_all Flow
# ============================================================================

def test_publish_all_success(monkeypatch):
    """Test vellykket publisering."""
    call_count = [0]

    def mock_client_factory():
        call_count[0] += 1

        mock_client = Mock()
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=None)

        # Første kall: GET ReviewSighting
        if call_count[0] == 1:
            mock_get_response = Mock()
            mock_get_response.text = '<input name="__RequestVerificationToken" value="REVIEWFORM" />'
            mock_get_response.status_code = 200
            mock_get_response.cookies = httpx.Cookies()
            mock_get_response.cookies.set('__RequestVerificationToken', 'REVIEWCOOKIE')

            def mock_raise_for_status():
                pass
            mock_get_response.raise_for_status = mock_raise_for_status

            mock_client.get = Mock(return_value=mock_get_response)
            return mock_client

        # Andre kall: POST PublishAll
        else:
            mock_post_response = Mock()
            mock_post_response.text = '<html>Success</html>'
            mock_post_response.status_code = 200

            mock_client.post = Mock(return_value=mock_post_response)
            return mock_client

    monkeypatch.setattr('httpx.Client', mock_client_factory)

    # Mock file open
    original_open = open

    def fake_open(path, *args, **kwargs):
        if '/tmp/' in str(path) and 'w' in args:
            # Mock write
            class FakeFile:
                def write(self, content):
                    pass

                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    pass

            return FakeFile()
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr('builtins.open', fake_open)

    # Test
    result = publish_all('LOGIN123', 'AUTH456')

    assert result['status'] == 200  # int, ikke string
    assert call_count[0] == 2  # GET + POST


# ============================================================================
# Del 5: API Endpoint Integration
# ============================================================================

def test_ao_import_endpoint(monkeypatch):
    """Test /api/ao-import endpoint."""
    # Mock post_with_curl - må mocke der den brukes (i server.py)
    def fake_post(observations, login_token, auth_cookie, area_id=''):
        return {
            'success': True,
            'message': f'{len(observations)} observasjoner importert',
            'count': len(observations),
            'published': True,
            'refreshedAuthCookie': None
        }

    # Import server module først for å mocke i riktig kontekst
    import server
    monkeypatch.setattr('server.post_with_curl', fake_post)

    # Start server
    port = 38010
    srv = start_server(port)
    time.sleep(0.05)

    try:
        # Test request
        r = requests.post(
            f'http://127.0.0.1:{port}/api/ao-import',
            json={
                'observations': [
                    {'species': {'taxonName': 'Gråspurv'}, 'count': '1'},
                    {'species': {'taxonName': 'Skjære'}, 'count': '2'}
                ],
                'loginToken': 'LOGIN123',
                'authCookie': 'AUTH456'
            }
        )

        assert r.status_code == 200
        data = r.json()
        assert data['success'] is True
        assert data['count'] == 2
        assert data['published'] is True

    finally:
        srv.shutdown()


def test_ao_import_endpoint_missing_params():
    """Test /api/ao-import uten påkrevde parametere."""
    port = 38011
    srv = start_server(port)
    time.sleep(0.05)

    try:
        # Mangler loginToken
        r = requests.post(
            f'http://127.0.0.1:{port}/api/ao-import',
            json={
                'observations': [{'species': 'Gråspurv'}],
                'authCookie': 'AUTH456'
            }
        )
        assert r.status_code == 400

        # Mangler authCookie
        r = requests.post(
            f'http://127.0.0.1:{port}/api/ao-import',
            json={
                'observations': [{'species': 'Gråspurv'}],
                'loginToken': 'LOGIN123'
            }
        )
        assert r.status_code == 400

    finally:
        srv.shutdown()


# ============================================================================
# Del 6: Login Endpoint
# ============================================================================

def test_ao_login_endpoint(monkeypatch):
    """Test /api/ao-login endpoint."""
    # Mock login_to_ao - må mocke der den brukes (i server.py)
    def fake_login(username, password):
        if username == 'testuser' and password == 'testpass':
            return {
                'authCookie': 'TESTAUTHCOOKIE123',
                'loginToken': '12345:abcdef',
                'userId': '12345'
            }
        raise ValueError('Feil brukernavn eller passord')

    import server
    monkeypatch.setattr('server.login_to_ao', fake_login)

    # Start server
    port = 38012
    srv = start_server(port)
    time.sleep(0.05)

    try:
        # Test vellykket login
        r = requests.post(
            f'http://127.0.0.1:{port}/api/ao-login',
            json={
                'username': 'testuser',
                'password': 'testpass'
            }
        )

        assert r.status_code == 200
        data = r.json()
        assert data['success'] is True
        assert data['authCookie'] == 'TESTAUTHCOOKIE123'
        assert data['loginToken'] == '12345:abcdef'
        assert data['userId'] == '12345'

        # Test feil credentials
        r = requests.post(
            f'http://127.0.0.1:{port}/api/ao-login',
            json={
                'username': 'wronguser',
                'password': 'wrongpass'
            }
        )

        assert r.status_code == 401

    finally:
        srv.shutdown()


def test_ao_login_endpoint_missing_params():
    """Test /api/ao-login uten påkrevde parametere."""
    port = 38013
    srv = start_server(port)
    time.sleep(0.05)

    try:
        # Mangler password
        r = requests.post(
            f'http://127.0.0.1:{port}/api/ao-login',
            json={'username': 'testuser'}
        )
        assert r.status_code == 400

        # Mangler username
        r = requests.post(
            f'http://127.0.0.1:{port}/api/ao-login',
            json={'password': 'testpass'}
        )
        assert r.status_code == 400

    finally:
        srv.shutdown()


# ============================================================================
# Del 5: Import-fremdrift (poll-endepunkter + progress_cb)
# ============================================================================

def _mock_count_client(monkeypatch, count_value, status=200, raise_exc=False):
    """Mock httpx.Client så .post().json() gir {'Count': count_value}."""
    resp = Mock()
    resp.status_code = status
    resp.json = Mock(return_value={'Count': count_value})

    client = Mock()
    client.__enter__ = Mock(return_value=client)
    client.__exit__ = Mock(return_value=None)
    if raise_exc:
        client.post = Mock(side_effect=Exception('nettverksfeil'))
    else:
        client.post = Mock(return_value=resp)

    monkeypatch.setattr('httpx.Client', lambda: client)
    return client


def test_number_of_sightings_importing_parses_count(monkeypatch):
    _mock_count_client(monkeypatch, 7)
    assert number_of_sightings_importing('LOGIN', 'AUTH') == 7


def test_number_of_sightings_submitted_parses_count(monkeypatch):
    _mock_count_client(monkeypatch, 15)
    assert number_of_sightings_submitted('LOGIN', 'AUTH') == 15


def test_number_of_sightings_returns_none_on_error(monkeypatch):
    _mock_count_client(monkeypatch, 0, raise_exc=True)
    assert number_of_sightings_importing('LOGIN', 'AUTH') is None


def test_number_of_sightings_returns_none_on_non_200(monkeypatch):
    _mock_count_client(monkeypatch, 3, status=500)
    assert number_of_sightings_importing('LOGIN', 'AUTH') is None


def test_post_with_curl_emits_progress(monkeypatch):
    """post_with_curl skal kalle progress_cb med importing- og publishing-faser."""
    monkeypatch.setattr(
        'src.ao_import_httpx.fetch_csrf_tokens',
        lambda lt, ac: ('FORM', 'COOKIE', None),
    )

    # ParseObservations-POST mockes til 200
    resp = Mock()
    resp.status_code = 200
    resp.text = '<html>ok</html>'
    client = Mock()
    client.__enter__ = Mock(return_value=client)
    client.__exit__ = Mock(return_value=None)
    client.post = Mock(return_value=resp)
    monkeypatch.setattr('httpx.Client', lambda: client)

    monkeypatch.setattr('time.sleep', lambda x: None)
    monkeypatch.setattr('src.ao_import_httpx.publish_all', lambda lt, ac: {'status': 200})

    # Simuler nedtelling: 2 igjen → 0 ferdig
    counts = iter([2, 0])
    monkeypatch.setattr(
        'src.ao_import_httpx.number_of_sightings_importing',
        lambda lt, ac: next(counts, 0),
    )

    events = []
    observations = [
        {'species': {'taxonName': 'Gråspurv'}, 'count': '1', 'timestamp': '2024-01-15T14:00:00Z', 'placeName': 'Oslo'},
        {'species': {'taxonName': 'Kjøttmeis'}, 'count': '2', 'timestamp': '2024-01-15T14:00:00Z', 'placeName': 'Oslo'},
    ]
    result = post_with_curl(observations, 'LOGIN', 'AUTH', progress_cb=events.append)

    assert result['success'] is True
    phases = [e['phase'] for e in events]
    assert 'importing' in phases
    assert 'publishing' in phases
    # Minst én importing-event skal ha korrekt total
    importing = [e for e in events if e['phase'] == 'importing']
    assert all(e['total'] == 2 for e in importing)


def test_ao_import_stream_emits_sse(monkeypatch):
    """SSE-endepunktet skal streame progress_cb-events som data:-linjer + done."""
    import server as server_module

    def fake_post(observations, login_token, auth_cookie, area_id='', progress_cb=None):
        if progress_cb:
            progress_cb({'phase': 'importing', 'remaining': 2, 'total': 2})
            progress_cb({'phase': 'importing', 'remaining': 0, 'total': 2})
            progress_cb({'phase': 'publishing', 'total': 2})
        return {'success': True, 'count': 2, 'published': True, 'refreshedAuthCookie': None}

    monkeypatch.setattr(server_module, 'post_with_curl', fake_post)

    port = 8199
    srv = start_server(port)
    time.sleep(0.05)
    try:
        r = requests.post(
            f'http://127.0.0.1:{port}/api/ao-import-stream',
            json={'observations': [{'x': 1}, {'x': 2}], 'loginToken': 'L', 'authCookie': 'A'},
            stream=True,
            timeout=5,
        )
        assert r.status_code == 200
        assert 'text/event-stream' in r.headers.get('Content-Type', '')
        events = []
        for line in r.iter_lines():
            if line and line.startswith(b'data:'):
                events.append(json.loads(line[5:].strip()))
        phases = [e['phase'] for e in events]
        assert 'importing' in phases
        assert 'publishing' in phases
        assert phases[-1] == 'done'
        assert events[-1]['count'] == 2
    finally:
        srv.shutdown()


def test_ao_import_stream_validates_before_streaming(monkeypatch):
    """Manglende observasjoner → vanlig 400 JSON, ikke event-stream."""
    port = 8198
    srv = start_server(port)
    time.sleep(0.05)
    try:
        r = requests.post(
            f'http://127.0.0.1:{port}/api/ao-import-stream',
            json={'observations': [], 'loginToken': 'L', 'authCookie': 'A'},
            timeout=5,
        )
        assert r.status_code == 400
        assert 'error' in r.json()
    finally:
        srv.shutdown()
