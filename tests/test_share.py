"""
Tester for deling av observasjoner (src/share_store.py + delingssiden).

Dekker det som gjør deling trygt: hvitelisting av felt, at skjulte funn og
koordinater aldri lekker ut, utløp, og at ukjent/utløpt lenke ikke kan skilles.
"""
import time

import pytest

from src import share_store
from src.html_templates import generate_share_page, generate_share_missing_page


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    """Egen database per test — deling skal aldri skrive i den ekte."""
    db = tmp_path / 'shares.db'
    monkeypatch.setattr(share_store, 'DB_PATH', str(db))
    share_store.init_db()
    yield


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


def test_koordinater_lagres_aldri():
    share = share_store.create_share([_obs(position={'lat': 60.4, 'lon': 5.3})])
    hentet = share_store.get_share(share['slug'])
    assert 'position' not in hentet['observations'][0]


def test_skjulte_observasjoner_deles_ikke():
    """hideUntil = skjult på AO. Da skal vi ikke publisere den samtidig."""
    obs = [_obs('tårnseiler'), _obs('hubro', hideUntil='2026-08-01')]
    share = share_store.create_share(obs)
    hentet = share_store.get_share(share['slug'])
    arter = [o['taxonName'] for o in hentet['observations']]
    assert arter == ['tårnseiler']


def test_bare_skjulte_gir_ingen_deling():
    assert share_store.create_share([_obs(hideUntil='2026-08-01')]) is None


def test_ukjente_felt_forkastes():
    share = share_store.create_share([_obs(hemmelig='lekkasje', coObservers=['Kari'])])
    lagret = share_store.get_share(share['slug'])['observations'][0]
    assert 'hemmelig' not in lagret
    assert 'coObservers' not in lagret


def test_tom_liste_gir_none():
    assert share_store.create_share([]) is None
    assert share_store.create_share('ikke en liste') is None


def test_utlopt_deling_er_utilgjengelig():
    share = share_store.create_share([_obs()], ttl_days=0)
    time.sleep(0.01)
    assert share_store.get_share(share['slug']) is None


def test_ugyldig_slug_gir_none():
    assert share_store.get_share('') is None
    assert share_store.get_share('kort') is None
    assert share_store.get_share('OOOOOOOOOOOO') is None  # tegn utenfor alfabetet


def test_sletting_krever_riktig_nokkel():
    share = share_store.create_share([_obs()])
    assert share_store.delete_share(share['slug'], 'feil-nøkkel') is False
    assert share_store.get_share(share['slug']) is not None
    assert share_store.delete_share(share['slug'], share['deleteKey']) is True
    assert share_store.get_share(share['slug']) is None


def test_for_mange_observasjoner_kuttes():
    share = share_store.create_share([_obs() for _ in range(share_store.MAX_OBSERVATIONS + 50)])
    hentet = share_store.get_share(share['slug'])
    assert len(hentet['observations']) == share_store.MAX_OBSERVATIONS


def test_side_escaper_brukerinnhold():
    share = share_store.create_share(
        [_obs(comment='<script>alert(1)</script>')],
        display_name='<b>Kjetil</b>',
    )
    html = generate_share_page(share_store.get_share(share['slug']))
    assert '<script>alert(1)</script>' not in html
    assert '&lt;script&gt;' in html
    assert '<b>Kjetil</b>' not in html


def test_side_viser_art_antall_og_sted():
    share = share_store.create_share([_obs()], display_name='Kjetil')
    html = generate_share_page(share_store.get_share(share['slug']))
    assert 'tårnseiler' in html
    assert 'Hylkjesvingen 49' in html
    assert 'Kjetil' in html
    assert '26. juli 2026' in html


def test_side_uten_navn_faller_tilbake():
    share = share_store.create_share([_obs()])
    html = generate_share_page(share_store.get_share(share['slug']))
    assert 'En fuglekikker' in html


def test_manglende_side_avslorer_ikke_om_slug_finnes():
    """Utløpt og ukjent skal gi nøyaktig samme side — ingen enumerering."""
    html = generate_share_missing_page()
    assert 'ikke tilgjengelig' in html
    assert 'noindex' in html


def test_visninger_telles():
    share = share_store.create_share([_obs()])
    share_store.get_share(share['slug'])
    hentet = share_store.get_share(share['slug'])
    assert hentet['views'] >= 1
