"""Tester for cookie-basert device tracking i logview."""
import threading
import time
import os
import sys
from http.server import HTTPServer
import requests

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, REPO_ROOT)

from server import Handler, _stats


def start_server(port):
    server = HTTPServer(('', port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def test_logview_sets_device_cookie(monkeypatch):
    """Test at /api/logview setter device_id cookie for nye enheter."""
    from src import sqlite_log
    import server as server_mod
    monkeypatch.setattr(sqlite_log, 'log_view', lambda ip, ua, device_id='': True)
    _stats['total'] = 0
    _stats['per_ip'] = {}
    _stats['per_ua'] = {}
    _stats['devices'] = set()

    port = 38050
    srv = start_server(port)
    time.sleep(0.05)

    # Første kall uten cookie → skal få Set-Cookie tilbake
    r = requests.post(f'http://127.0.0.1:{port}/api/logview')
    assert r.status_code == 200
    assert 'device_id' in r.headers.get('Set-Cookie', '')

    # Hent cookie-verdien
    cookie_val = r.cookies.get('device_id')
    assert cookie_val is not None
    assert len(cookie_val) == 36  # UUID format

    srv.shutdown()


def test_logview_reuses_existing_cookie(monkeypatch):
    """Test at /api/logview ikke setter ny cookie hvis den allerede finnes."""
    from src import sqlite_log
    import server as server_mod
    monkeypatch.setattr(sqlite_log, 'log_view', lambda ip, ua, device_id='': True)
    _stats['total'] = 0
    _stats['per_ip'] = {}
    _stats['per_ua'] = {}
    _stats['devices'] = set()

    port = 38051
    srv = start_server(port)
    time.sleep(0.05)

    # Send med eksisterende cookie
    existing_id = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
    r = requests.post(
        f'http://127.0.0.1:{port}/api/logview',
        cookies={'device_id': existing_id}
    )
    assert r.status_code == 200
    # Skal IKKE sette ny cookie
    assert 'Set-Cookie' not in r.headers or 'device_id' not in r.headers.get('Set-Cookie', '')

    # Device ID skal brukes i stats
    assert existing_id in _stats['devices']

    srv.shutdown()


def test_logview_tracks_unique_devices(monkeypatch):
    """Test at forskjellige enheter telles som unike."""
    from src import sqlite_log
    import server as server_mod
    monkeypatch.setattr(sqlite_log, 'log_view', lambda ip, ua, device_id='': True)
    _stats['total'] = 0
    _stats['per_ip'] = {}
    _stats['per_ua'] = {}
    _stats['devices'] = set()

    port = 38052
    srv = start_server(port)
    time.sleep(0.05)

    # To forskjellige enheter
    requests.post(f'http://127.0.0.1:{port}/api/logview', cookies={'device_id': 'device-1'})
    requests.post(f'http://127.0.0.1:{port}/api/logview', cookies={'device_id': 'device-2'})
    # Samme enhet igjen
    requests.post(f'http://127.0.0.1:{port}/api/logview', cookies={'device_id': 'device-1'})

    assert _stats['total'] == 3
    assert len(_stats['devices']) == 2

    srv.shutdown()
