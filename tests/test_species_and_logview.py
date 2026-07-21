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

from server import Handler, _stats


def start_server(port):
    server = HTTPServer(('', port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def test_species_parsing(monkeypatch):
    # Provide fake HTML with two span.itemjson entries
    item1 = json.dumps({'taxonid': 1, 'taxonname': 'House Sparrow', 'scientificname': 'Passer domesticus', 'leaf': 'true'})
    item2 = json.dumps({'taxonid': 2, 'taxonname': 'Rock Dove', 'scientificname': 'Columba livia', 'leaf': 'true'})
    fake_html = f'<span class="itemjson">{item1}</span><span class="itemjson">{item2}</span>'

    class FakeResponse:
        status_code = 200
        text = fake_html
        def raise_for_status(self):
            pass

    class FakeClient:
        def __init__(self, **kwargs):
            pass
        def get(self, url, **kwargs):
            return FakeResponse()
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    monkeypatch.setattr('httpx.Client', FakeClient)

    port = 38003
    srv = start_server(port)
    time.sleep(0.05)

    r = requests.get(f'http://127.0.0.1:{port}/api/species?search=sparrow')
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert any(d.get('taxonName') == 'House Sparrow' for d in data)

    srv.shutdown()


def test_logview_monkeypatch(monkeypatch):
    # Reset stats
    _stats['total'] = 0
    _stats['per_ip'] = {}
    _stats['per_ua'] = {}

    called = {'sqlite': False}

    def fake_log_view(ip, ua, device_id=''):
        called['sqlite'] = True

    from src import sqlite_log
    import server as server_mod
    monkeypatch.setattr(sqlite_log, 'log_view', fake_log_view)

    port = 38004
    srv = start_server(port)
    time.sleep(0.05)

    headers = {'User-Agent': 'pytest-agent/1.0'}
    r = requests.post(f'http://127.0.0.1:{port}/api/logview', headers=headers)
    assert r.status_code == 200
    assert r.json().get('ok') is True
    assert _stats['total'] == 1
    assert called['sqlite'] is True

    srv.shutdown()
