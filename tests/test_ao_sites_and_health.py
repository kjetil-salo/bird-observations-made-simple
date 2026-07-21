import threading
import time
import os
import sys
import json
from http.server import HTTPServer
import requests

import pytest

# Ensure repo root is importable
REPO_ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, REPO_ROOT)

from server import Handler


def start_server(port):
    server = HTTPServer(('', port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def test_health_endpoint():
    """Test at /health endpointet returnerer OK status."""
    port = 38005
    srv = start_server(port)
    time.sleep(0.05)

    r = requests.get(f'http://127.0.0.1:{port}/health')
    assert r.status_code == 200
    data = r.json()
    assert data.get('status') == 'ok'
    assert 'timestamp' in data
    assert isinstance(data['timestamp'], (int, float))

    srv.shutdown()


def test_ao_sites_valid(monkeypatch):
    """Test /api/ao-sites med gyldig input."""
    # Mock response fra AO API (ByBoundingBox-format)
    # Site 1 er en superlokasjon (referert som parent av site 2)
    # Site 2 er en underlokasjon med parentSiteId=1
    fake_sites = [
        {
            'id': 1,
            'name': 'Østensjøvannet',
            'latitude': 59.91,
            'longitude': 10.81,
        },
        {
            'id': 2,
            'name': 'Sognsvann',
            'latitude': 59.97,
            'longitude': 10.73,
            'parentSiteId': 1,
        }
    ]

    class FakeResponse:
        status_code = 200
        def __init__(self, data=None):
            self._data = data
        def raise_for_status(self):
            pass
        def json(self):
            return self._data

    class FakeClient:
        def __init__(self, **kwargs):
            pass
        def get(self, url, **kwargs):
            return FakeResponse(fake_sites)
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    monkeypatch.setattr('httpx.Client', FakeClient)

    port = 38006
    srv = start_server(port)
    time.sleep(0.05)

    r = requests.get(f'http://127.0.0.1:{port}/api/ao-sites?lat=59.9&lon=10.7&size=1000')
    assert r.status_code == 200
    data = r.json()
    assert 'sites' in data
    assert isinstance(data['sites'], list)
    assert len(data['sites']) == 2
    names = [s['name'] for s in data['sites']]
    assert 'Østensjøvannet' in names
    assert 'Sognsvann' in names
    # Østensjøvannet er superlokasjon (referert som parent av Sognsvann)
    ostensjovannet = next(s for s in data['sites'] if s['name'] == 'Østensjøvannet')
    sognsvann = next(s for s in data['sites'] if s['name'] == 'Sognsvann')
    assert ostensjovannet.get('isSuper') is True
    assert sognsvann.get('isSuper') is False

    srv.shutdown()


def test_ao_sites_missing_params():
    """Test /api/ao-sites uten påkrevde parametere."""
    port = 38007
    srv = start_server(port)
    time.sleep(0.05)

    # Mangler lat
    r = requests.get(f'http://127.0.0.1:{port}/api/ao-sites?lon=10.7')
    assert r.status_code == 400

    # Mangler lon
    r = requests.get(f'http://127.0.0.1:{port}/api/ao-sites?lat=59.9')
    assert r.status_code == 400

    srv.shutdown()


def test_ao_sites_invalid_coords():
    """Test /api/ao-sites med ugyldige koordinater."""
    port = 38008
    srv = start_server(port)
    time.sleep(0.05)

    # Ugyldig lat
    r = requests.get(f'http://127.0.0.1:{port}/api/ao-sites?lat=invalid&lon=10.7')
    assert r.status_code == 400

    # Ugyldig lon
    r = requests.get(f'http://127.0.0.1:{port}/api/ao-sites?lat=59.9&lon=notfloat')
    assert r.status_code == 400

    srv.shutdown()


def test_ao_sites_api_error(monkeypatch):
    """Test at /api/ao-sites håndterer eksterne API-feil grasiøst."""
    class FakeClient:
        def __init__(self, **kwargs):
            pass
        def get(self, url, **kwargs):
            raise Exception('External API error')
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    monkeypatch.setattr('httpx.Client', FakeClient)

    port = 38009
    srv = start_server(port)
    time.sleep(0.05)

    # Forventer graceful degradation - tom liste, status 200
    r = requests.get(f'http://127.0.0.1:{port}/api/ao-sites?lat=59.9&lon=10.7')
    assert r.status_code == 200
    data = r.json()
    assert 'sites' in data
    assert data['sites'] == []

    srv.shutdown()


def test_ao_sites_default_size(monkeypatch):
    """Test at /api/ao-sites bruker default size hvis ikke oppgitt."""
    from src.api_handlers import handle_ao_sites_search

    called_urls = []

    class FakeResponse:
        status_code = 200
        def raise_for_status(self):
            pass
        def json(self):
            return []

    class FakeClient:
        def __init__(self, **kwargs):
            pass
        def get(self, url, **kwargs):
            called_urls.append(url)
            return FakeResponse()
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    monkeypatch.setattr('httpx.Client', FakeClient)

    sites, refreshed_auth, auth_failed = handle_ao_sites_search(59.9, 10.7)
    assert len(called_urls) == 1
    # Default size er 600 meter
    assert 'minX=' in called_urls[0]
    assert 'maxX=' in called_urls[0]


def test_ao_sites_super_via_local_db_parent(monkeypatch):
    """Test at super-status utledes fra lokal DB sin parent_id når AO returnerer parentSiteId=null.

    Dette er det reelle scenariet: AO ByBoundingBox returnerer parentSiteId=None for alle sites,
    men lokal DB har parent_id satt fra importkjøring. Foreldresiten skal markeres isSuper=True.
    """
    from src.api_handlers import handle_ao_sites_search
    from unittest.mock import MagicMock

    # AO returnerer parentSiteId=None (slik APIet faktisk oppfører seg)
    fake_ao_sites = [
        {'id': 1, 'name': 'Hylkje', 'lat': 60.456, 'lon': 5.446, 'parentSiteId': None},
        {'id': 2, 'name': 'Hylkjebukta', 'lat': 60.452, 'lon': 5.444, 'parentSiteId': None},
    ]

    class FakeResponse:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return fake_ao_sites

    class FakeClient:
        def __init__(self, **kwargs): pass
        def get(self, url, **kwargs): return FakeResponse()
        def __enter__(self): return self
        def __exit__(self, *args): pass

    monkeypatch.setattr('httpx.Client', FakeClient)

    # Lokal DB vet at site 2 (Hylkjebukta) har parent_id=1 (Hylkje)
    mock_db = MagicMock()
    mock_db.search_nearby.return_value = [
        {'id': 1, 'name': 'Hylkje', 'lat': 60.456, 'lon': 5.446, 'isPrivate': False, 'isSuper': False, 'parentId': None, '_source': 'local_db', '_distance': 10},
        {'id': 2, 'name': 'Hylkjebukta', 'lat': 60.452, 'lon': 5.444, 'isPrivate': False, 'isSuper': False, 'parentId': 1, '_source': 'local_db', '_distance': 50},
    ]

    sites, _, _ = handle_ao_sites_search(60.456, 5.446, size_m=1000, location_db=mock_db)

    hylkje = next(s for s in sites if s.get('id') == 1)
    hylkjebukta = next(s for s in sites if s.get('id') == 2)
    assert hylkje.get('isSuper') is True, 'Hylkje skal være super via lokal DB parent_id'
    assert not hylkjebukta.get('isSuper'), 'Hylkjebukta er underlokasjon, ikke super'


def test_manglende_fil_gir_404_ikke_index_fallback():
    """Filaktige stier (med filendelse) som ikke finnes skal gi ekte 404.
    Index.html-fallback for slike ble cachet som HTML av Cloudflare (4 t),
    slik at et manglende bilde ble servert som appen uten CSS."""
    port = 38090
    srv = start_server(port)
    time.sleep(0.05)

    r = requests.get(f'http://127.0.0.1:{port}/img/finnes-ikke.png')
    assert r.status_code == 404
    assert r.headers.get('Cache-Control') == 'no-store'

    # Pene URL-er uten filendelse skal fortsatt gi appen (SPA-fallback)
    r2 = requests.get(f'http://127.0.0.1:{port}/en-ukjent-side')
    assert r2.status_code == 200
    assert 'text/html' in r2.headers.get('Content-Type', '')

    srv.shutdown()
