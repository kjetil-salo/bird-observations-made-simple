"""Tester for tilbakemeldingskanalen (/api/feedback + admin)."""
import os
import sys
import tempfile
import threading
import time
from http.server import HTTPServer

import pytest
import requests

REPO_ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, REPO_ROOT)

# Bruk en isolert temp-DB før feedback_store importeres (leser DB_PATH ved import).
_TMP_DB = os.path.join(tempfile.mkdtemp(), 'feedback_test.db')
os.environ['DB_PATH'] = _TMP_DB

from src import feedback_store  # noqa: E402
from server import Handler  # noqa: E402

# Sørg for at både modulen og en ev. tidligere lastet instans bruker temp-DB.
feedback_store.DB_PATH = _TMP_DB
feedback_store.init_db()


def start_server(port):
    server = HTTPServer(('', port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def test_create_feedback_returns_case_no():
    case_no = feedback_store.create_feedback('Testmelding', fb_type='feil', email='a@b.no')
    assert case_no and case_no.startswith('AO-')
    assert len(case_no) == 3 + feedback_store._CASE_LENGTH

    items = feedback_store.list_feedback()
    assert any(it['case_no'] == case_no for it in items)


def test_empty_message_rejected():
    assert feedback_store.create_feedback('   ') is None


def test_invalid_type_falls_back_to_annet():
    case_no = feedback_store.create_feedback('Hei', fb_type='tull')
    item = next(it for it in feedback_store.list_feedback() if it['case_no'] == case_no)
    assert item['type'] == 'annet'


def test_set_status():
    case_no = feedback_store.create_feedback('Statustest')
    assert feedback_store.set_status(case_no, 'løst') is True
    assert feedback_store.set_status(case_no, 'ugyldig') is False
    item = next(it for it in feedback_store.list_feedback() if it['case_no'] == case_no)
    assert item['status'] == 'løst'


def test_feedback_endpoint_end_to_end():
    port = 38070
    srv = start_server(port)
    time.sleep(0.05)
    try:
        r = requests.post(f'http://127.0.0.1:{port}/api/feedback',
                          json={'type': 'ønske', 'message': 'Ønsker mørk modus'})
        assert r.status_code == 200
        data = r.json()
        assert data['ok'] is True
        assert data['caseNo'].startswith('AO-')

        # Tom melding → 400
        r2 = requests.post(f'http://127.0.0.1:{port}/api/feedback', json={'message': '  '})
        assert r2.status_code == 400
    finally:
        srv.shutdown()


def test_honeypot_does_not_store():
    port = 38071
    srv = start_server(port)
    time.sleep(0.05)
    try:
        before = len(feedback_store.list_feedback(limit=1000))
        r = requests.post(f'http://127.0.0.1:{port}/api/feedback',
                          json={'message': 'spam', 'website': 'http://spam.example'})
        assert r.status_code == 200
        after = len(feedback_store.list_feedback(limit=1000))
        assert after == before  # honeypot → ingenting lagret
    finally:
        srv.shutdown()


def test_email_notify_noop_when_unconfigured(monkeypatch):
    from src import email_notify
    monkeypatch.delenv('FEEDBACK_NOTIFY_TO', raising=False)
    monkeypatch.delenv('RESEND_API_KEY', raising=False)
    monkeypatch.delenv('SMTP2GO_API_KEY', raising=False)
    assert email_notify.is_configured() is False
    # Skal returnere False uten å kaste og uten å prøve å sende
    assert email_notify.send_feedback_notification('AO-TEST1', 'feil', 'hei') is False


def test_email_notify_smtp_path(monkeypatch):
    from src import email_notify
    monkeypatch.setenv('FEEDBACK_NOTIFY_TO', 'eier@eks.no')
    monkeypatch.setenv('FEEDBACK_NOTIFY_FROM', 'noreply@eks.no')
    monkeypatch.setenv('SMTP_HOST', 'mail-eu.smtp2go.com')
    monkeypatch.setenv('SMTP_USER', 'smtpbruker')
    monkeypatch.setenv('SMTP_PASS', 'hemmelig')
    monkeypatch.delenv('RESEND_API_KEY', raising=False)

    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            sent['host'] = host; sent['port'] = port
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def starttls(self): sent['tls'] = True
        def login(self, u, p): sent['login'] = (u, p)
        def send_message(self, msg):
            sent['from'] = msg['From']; sent['to'] = msg['To']
            sent['reply_to'] = msg['Reply-To']; sent['subject'] = msg['Subject']

    import smtplib
    monkeypatch.setattr(smtplib, 'SMTP', FakeSMTP)

    ok = email_notify.send_feedback_notification(
        'AO-SMTP1', 'ønske', 'Test SMTP', email='melder@eks.no')
    assert ok is True
    assert sent['host'] == 'mail-eu.smtp2go.com' and sent['port'] == 2525
    assert sent['tls'] is True
    assert sent['reply_to'] == 'melder@eks.no'
    assert 'AO-SMTP1' in sent['subject']


def test_email_notify_resend_payload(monkeypatch):
    from src import email_notify
    monkeypatch.setenv('FEEDBACK_NOTIFY_TO', 'eier@eks.no')
    monkeypatch.setenv('FEEDBACK_NOTIFY_FROM', 'noreply@eks.no')
    monkeypatch.setenv('RESEND_API_KEY', 'test-key')
    monkeypatch.delenv('SMTP2GO_API_KEY', raising=False)

    captured = {}

    class FakeResp:
        def raise_for_status(self): pass

    def fake_post(url, headers=None, json=None, timeout=None):
        captured['url'] = url
        captured['json'] = json
        captured['headers'] = headers
        return FakeResp()

    import httpx
    monkeypatch.setattr(httpx, 'post', fake_post)

    ok = email_notify.send_feedback_notification(
        'AO-ABC12', 'feil', 'Noe er galt', email='melder@eks.no', app_version='v1.39.0')
    assert ok is True
    assert 'resend.com' in captured['url']
    assert captured['json']['to'] == ['eier@eks.no']
    assert captured['json']['reply_to'] == 'melder@eks.no'  # svar går til melder
    assert 'AO-ABC12' in captured['json']['subject']


def test_email_notify_failure_is_swallowed(monkeypatch):
    from src import email_notify
    monkeypatch.setenv('FEEDBACK_NOTIFY_TO', 'eier@eks.no')
    monkeypatch.setenv('RESEND_API_KEY', 'test-key')

    import httpx
    def boom(*a, **k):
        raise RuntimeError('nettverksfeil')
    monkeypatch.setattr(httpx, 'post', boom)

    # Skal svelge feilen og returnere False
    assert email_notify.send_feedback_notification('AO-XYZ99', 'annet', 'test') is False


def test_admin_page_requires_key(monkeypatch):
    monkeypatch.setenv('STATS_KEY', 'hemmelig')
    port = 38072
    srv = start_server(port)
    time.sleep(0.05)
    try:
        r = requests.get(f'http://127.0.0.1:{port}/feedback')
        assert 'Logg inn' in r.text  # login-side uten nøkkel

        r2 = requests.get(f'http://127.0.0.1:{port}/feedback?key=hemmelig')
        assert 'Tilbakemeldinger' in r2.text
    finally:
        srv.shutdown()
