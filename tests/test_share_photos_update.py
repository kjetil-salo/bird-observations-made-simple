"""
Tester for Fase F1: bilder på delinger og oppdatering av eksisterende deling.

Følger samme mønster som tests/test_share.py (isolert temp-DB per test via
monkeypatch av share_store.DB_PATH). HTTP-nivå-tester av /api/share-update
starter en ekte server-instans, som i tests/test_feedback.py.
"""
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

from src import share_store
from src.html_templates import generate_share_page

# server.py leser DB_PATH-relaterte moduler ved import — importeres først etter
# at eventuelle env-vars er satt (følger mønsteret i test_feedback.py).
import server as server_module  # noqa: E402
from server import Handler  # noqa: E402


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    """Egen database per test — deling skal aldri skrive i den ekte."""
    db = tmp_path / 'shares.db'
    monkeypatch.setattr(share_store, 'DB_PATH', str(db))
    share_store.init_db()
    # Rate-limit-poolen er delt mellom /api/share og /api/share-update og
    # lever på modulnivå i server.py — nullstill så tester ikke smitter.
    server_module._share_hits.clear()
    yield
    server_module._share_hits.clear()


def _obs(navn='tårnseiler', **kwargs):
    base = {
        'species': {'taxonName': navn},
        'count': 6,
        'activity': 'Næringssøkende',
        'placeName': 'Hylkjesvingen 49',
        'timestamp': '2026-07-26T15:00:00',
    }
    base.update(kwargs)
    return base


def _photo_of_size(n_bytes, mime='image/jpeg'):
    """Lag en data-URL av eksakt byte-lengde — nyttig for å teste grenser presist."""
    prefix = f'data:{mime};base64,'
    filler = 'A' * (n_bytes - len(prefix))
    return prefix + filler


def start_server(port):
    server = HTTPServer(('', port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


# ---------------------------------------------------------------------------
# Bilder: gyldig format
# ---------------------------------------------------------------------------

def test_gyldig_jpeg_bilde_deles():
    foto = _photo_of_size(500)
    share = share_store.create_share([_obs(photo=foto)])
    hentet = share_store.get_share(share['slug'])
    assert hentet['observations'][0]['photo'] == foto

    html = generate_share_page(hentet)
    assert 'class="foto"' in html
    assert foto in html


@pytest.mark.parametrize('ugyldig', [
    'data:image/png;base64,QQ==',
    'data:image/svg+xml;base64,QQ==',
    'ikke en data-url i det hele tatt',
    12345,
    None,
])
def test_ugyldig_bildeformat_droppes_stille(ugyldig):
    share = share_store.create_share([_obs(photo=ugyldig)])
    assert share is not None  # resten av observasjonen skal fortsatt deles
    hentet = share_store.get_share(share['slug'])
    obs = hentet['observations'][0]
    assert obs['photo'] == ''
    assert obs['taxonName'] == 'tårnseiler'

    html = generate_share_page(hentet)
    assert 'class="foto"' not in html


def test_observasjon_uten_photo_felt_far_tomt_bilde():
    share = share_store.create_share([_obs()])
    hentet = share_store.get_share(share['slug'])
    assert hentet['observations'][0]['photo'] == ''


# ---------------------------------------------------------------------------
# Bilder: størrelsesgrenser
# ---------------------------------------------------------------------------

def test_bilde_over_maks_storrelse_droppes():
    foto = _photo_of_size(share_store.MAX_PHOTO_BYTES + 1000)
    share = share_store.create_share([_obs(photo=foto)])
    hentet = share_store.get_share(share['slug'])
    assert hentet['observations'][0]['photo'] == ''


def test_bilde_nokyaktig_pa_grensen_godtas():
    foto = _photo_of_size(share_store.MAX_PHOTO_BYTES)
    assert len(foto.encode('utf-8')) == share_store.MAX_PHOTO_BYTES
    share = share_store.create_share([_obs(photo=foto)])
    hentet = share_store.get_share(share['slug'])
    assert hentet['observations'][0]['photo'] == foto


def test_bilde_en_byte_over_grensen_droppes():
    foto = _photo_of_size(share_store.MAX_PHOTO_BYTES + 1)
    assert len(foto.encode('utf-8')) == share_store.MAX_PHOTO_BYTES + 1
    share = share_store.create_share([_obs(photo=foto)])
    hentet = share_store.get_share(share['slug'])
    assert hentet['observations'][0]['photo'] == ''


def test_totalt_bildebudsjett_kutter_de_siste():
    """
    Flere bilder som til sammen sprenger MAX_TOTAL_PHOTO_BYTES: de første skal
    inkluderes til budsjettet er brukt opp, resten skal droppes.
    """
    # per_foto må være stor nok til at total-byte-budsjettet slår inn FØR
    # antallsgrensen (MAX_PHOTOS_PER_SHARE) gjør det.
    per_foto = share_store.MAX_TOTAL_PHOTO_BYTES // (share_store.MAX_PHOTOS_PER_SHARE - 4)
    antall_som_bor_ga_inn = share_store.MAX_TOTAL_PHOTO_BYTES // per_foto
    assert antall_som_bor_ga_inn < share_store.MAX_PHOTOS_PER_SHARE
    total_forsok = antall_som_bor_ga_inn + 3

    fotos = [_photo_of_size(per_foto) for _ in range(total_forsok)]
    obser = [_obs(f'art{i}', photo=fotos[i]) for i in range(total_forsok)]
    share = share_store.create_share(obser)
    hentet = share_store.get_share(share['slug'])

    inkludert = [o for o in hentet['observations'] if o['photo']]
    droppet = [o for o in hentet['observations'] if not o['photo']]

    assert len(inkludert) == antall_som_bor_ga_inn
    assert len(droppet) == total_forsok - antall_som_bor_ga_inn
    # De første skal være de som kom med (budsjettet brukes i rekkefølge)
    assert [o['taxonName'] for o in inkludert] == [f'art{i}' for i in range(antall_som_bor_ga_inn)]


def test_flere_enn_maks_antall_bilder_kuttes():
    antall = share_store.MAX_PHOTOS_PER_SHARE + 5
    # Små bilder slik at det er antallsgrensen, ikke total-byte-budsjettet, som slår inn
    fotos = [_photo_of_size(500) for _ in range(antall)]
    obser = [_obs(f'art{i}', photo=fotos[i]) for i in range(antall)]
    share = share_store.create_share(obser)
    hentet = share_store.get_share(share['slug'])

    inkludert = [o for o in hentet['observations'] if o['photo']]
    assert len(inkludert) == share_store.MAX_PHOTOS_PER_SHARE
    assert [o['taxonName'] for o in inkludert] == [f'art{i}' for i in range(share_store.MAX_PHOTOS_PER_SHARE)]


# ---------------------------------------------------------------------------
# Tekstbudsjett: uendret oppførsel, uavhengig av bilder
# ---------------------------------------------------------------------------

def test_stor_tekst_avvises_som_for_regresjon():
    """MAX_PAYLOAD_BYTES skal fortsatt felle en deling med for mye tekst — uendret."""
    lang_kommentar = 'x' * 500  # MAX_TEXT_LEN
    obser = [_obs(f'art med et ganske langt artsnavn nummer {i}', comment=lang_kommentar,
                   placeName='Et ganske langt stedsnavn som tar plass ' * 3)
             for i in range(200)]
    assert share_store.create_share(obser) is None


def test_mange_store_bilder_feller_ikke_tekstbudsjettet():
    """
    Bilder skal aldri kunne felle delingen pga. tekstbudsjettet — selv om de
    totalt er langt over MAX_PAYLOAD_BYTES, skal delingen gå gjennom fordi
    _text_payload_size_ok ser bort fra photo-feltet.
    """
    foto = _photo_of_size(100_000)  # godt over MAX_PAYLOAD_BYTES alene
    obser = [_obs(f'art{i}', photo=foto) for i in range(10)]
    share = share_store.create_share(obser)
    assert share is not None
    hentet = share_store.get_share(share['slug'])
    assert all(o['photo'] for o in hentet['observations'])


# ---------------------------------------------------------------------------
# update_share() — store-nivå
# ---------------------------------------------------------------------------

def test_update_share_endrer_payload_samme_slug():
    share = share_store.create_share([_obs('tårnseiler')])
    slug = share['slug']

    resultat = share_store.update_share(
        slug, share['deleteKey'], [_obs('hubro')], display_name='Ny'
    )
    assert resultat is not None
    assert resultat['slug'] == slug

    hentet = share_store.get_share(slug)
    arter = [o['taxonName'] for o in hentet['observations']]
    assert arter == ['hubro']
    assert hentet['display_name'] == 'Ny'


def test_update_share_endrer_ikke_expires_ts():
    share = share_store.create_share([_obs()])
    original = share_store.get_share(share['slug'])
    original_expires = original['expires_ts']

    time.sleep(0.01)
    resultat = share_store.update_share(share['slug'], share['deleteKey'], [_obs('hubro')])
    assert resultat is not None
    assert resultat['expiresTs'] == original_expires

    hentet = share_store.get_share(share['slug'])
    assert hentet['expires_ts'] == original_expires


def test_update_share_feil_nokkel_gir_none_og_endrer_ingenting():
    share = share_store.create_share([_obs('tårnseiler')])
    resultat = share_store.update_share(share['slug'], 'feil-nøkkel', [_obs('hubro')])
    assert resultat is None

    hentet = share_store.get_share(share['slug'])
    assert [o['taxonName'] for o in hentet['observations']] == ['tårnseiler']


def test_update_share_ukjent_slug_gir_none():
    resultat = share_store.update_share('A' * 12, 'en-eller-annen-nokkel', [_obs()])
    assert resultat is None


def test_update_share_utlopt_slug_gir_none():
    share = share_store.create_share([_obs()], ttl_days=0)
    time.sleep(0.01)
    resultat = share_store.update_share(share['slug'], share['deleteKey'], [_obs('hubro')])
    assert resultat is None


def test_update_share_ugyldig_slug_format_gir_none():
    assert share_store.update_share('', 'nokkel', [_obs()]) is None
    assert share_store.update_share('kort', 'nokkel', [_obs()]) is None
    assert share_store.update_share(None, 'nokkel', [_obs()]) is None


def test_update_share_tom_observasjonsliste_gir_none():
    share = share_store.create_share([_obs()])
    resultat = share_store.update_share(share['slug'], share['deleteKey'], [])
    assert resultat is None
    # Opprinnelig innhold skal fortsatt være der
    hentet = share_store.get_share(share['slug'])
    assert len(hentet['observations']) == 1


def test_update_share_for_stor_tekst_avvises():
    share = share_store.create_share([_obs()])
    lang_kommentar = 'x' * 500
    obser = [_obs(f'art nummer {i}', comment=lang_kommentar,
                   placeName='Et ganske langt stedsnavn som tar plass ' * 3)
             for i in range(200)]
    resultat = share_store.update_share(share['slug'], share['deleteKey'], obser)
    assert resultat is None
    # Original skal ikke være overskrevet
    hentet = share_store.get_share(share['slug'])
    assert len(hentet['observations']) == 1


# ---------------------------------------------------------------------------
# /api/share-update — HTTP-nivå
# ---------------------------------------------------------------------------

def test_http_share_update_happy_path():
    port = 38095
    srv = start_server(port)
    time.sleep(0.05)
    try:
        opprett = requests.post(
            f'http://127.0.0.1:{port}/api/share',
            json={'observations': [_obs('tårnseiler')], 'displayName': 'Kjetil'},
        )
        assert opprett.status_code == 200
        data = opprett.json()
        slug = data['slug']

        oppdater = requests.post(
            f'http://127.0.0.1:{port}/api/share-update',
            json={
                'slug': slug,
                'deleteKey': data['deleteKey'],
                'observations': [_obs('hubro')],
                'displayName': 'Kjetil',
            },
        )
        assert oppdater.status_code == 200
        oppdater_data = oppdater.json()
        assert oppdater_data['ok'] is True
        assert oppdater_data['slug'] == slug
        assert oppdater_data['expiresTs'] == data['expiresTs']

        side = requests.get(f'http://127.0.0.1:{port}/d/{slug}')
        assert side.status_code == 200
        assert 'hubro' in side.text
        assert 'tårnseiler' not in side.text
    finally:
        srv.shutdown()


def test_http_share_update_feil_delete_key_gir_404():
    port = 38096
    srv = start_server(port)
    time.sleep(0.05)
    try:
        opprett = requests.post(
            f'http://127.0.0.1:{port}/api/share',
            json={'observations': [_obs('tårnseiler')]},
        )
        slug = opprett.json()['slug']

        oppdater = requests.post(
            f'http://127.0.0.1:{port}/api/share-update',
            json={'slug': slug, 'deleteKey': 'feil-nøkkel', 'observations': [_obs('hubro')]},
        )
        assert oppdater.status_code == 404
    finally:
        srv.shutdown()


def test_http_share_update_ukjent_slug_gir_404():
    port = 38097
    srv = start_server(port)
    time.sleep(0.05)
    try:
        oppdater = requests.post(
            f'http://127.0.0.1:{port}/api/share-update',
            json={'slug': 'A' * 12, 'deleteKey': 'nokkel', 'observations': [_obs()]},
        )
        assert oppdater.status_code == 404
    finally:
        srv.shutdown()


def test_http_share_update_rate_limit():
    port = 38098
    srv = start_server(port)
    time.sleep(0.05)
    try:
        url = f'http://127.0.0.1:{port}/api/share-update'
        for _ in range(server_module.SHARE_MAX_PER_WINDOW):
            r = requests.post(url, json={'slug': 'A' * 12, 'deleteKey': 'x',
                                          'observations': [_obs()]})
            assert r.status_code != 429
        siste = requests.post(url, json={'slug': 'A' * 12, 'deleteKey': 'x',
                                          'observations': [_obs()]})
        assert siste.status_code == 429
    finally:
        srv.shutdown()


def test_http_share_update_deler_rate_limit_pool_med_share():
    """/api/share og /api/share-update deler samme kvote per IP (samme dict i server.py)."""
    port = 38099
    srv = start_server(port)
    time.sleep(0.05)
    try:
        url_share = f'http://127.0.0.1:{port}/api/share'
        url_update = f'http://127.0.0.1:{port}/api/share-update'
        # Bruk opp halve kvoten på /api/share
        for _ in range(server_module.SHARE_MAX_PER_WINDOW // 2):
            requests.post(url_share, json={'observations': [_obs()]})
        # og resten på /api/share-update
        for _ in range(server_module.SHARE_MAX_PER_WINDOW - server_module.SHARE_MAX_PER_WINDOW // 2):
            requests.post(url_update, json={'slug': 'A' * 12, 'deleteKey': 'x',
                                             'observations': [_obs()]})
        siste = requests.post(url_share, json={'observations': [_obs()]})
        assert siste.status_code == 429
    finally:
        srv.shutdown()
