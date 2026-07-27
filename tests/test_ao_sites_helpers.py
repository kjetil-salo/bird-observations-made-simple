"""Tester for refaktorerte hjelpefunksjoner i api_handlers."""
import json
import math
import os
import sys
import tempfile

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, REPO_ROOT)

from src.api_handlers import (
    _wgs84_to_mercator,
    _compute_bbox,
    _normalize_site,
    _resolve_super_sites,
    _mark_env_owned_sites,
    _ensure_auth,
)


# --- _wgs84_to_mercator ---

def test_wgs84_to_mercator_oslo():
    """Test konvertering av Oslo-koordinater."""
    x, y = _wgs84_to_mercator(59.9139, 10.7522)
    # Oslo i Web Mercator: x ~ 1196900, y ~ 8388600
    assert 1_190_000 < x < 1_200_000
    assert 8_380_000 < y < 8_400_000


def test_wgs84_to_mercator_equator():
    """Test at ekvator gir y=0."""
    x, y = _wgs84_to_mercator(0.0, 0.0)
    assert abs(x) < 1
    assert abs(y) < 1


def test_wgs84_to_mercator_negative():
    """Test negative koordinater (sørlig halvkule)."""
    x, y = _wgs84_to_mercator(-33.8688, 151.2093)  # Sydney
    assert x > 0
    assert y < 0


# --- _compute_bbox ---

def test_compute_bbox_symmetry():
    """Test at bbox er symmetrisk rundt senterpunktet."""
    bbox = _compute_bbox(60.0, 10.0, 1000)
    assert bbox['min_y'] < 60.0 < bbox['max_y']
    assert bbox['min_x'] < 10.0 < bbox['max_x']
    # Sjekk symmetri
    assert abs((bbox['max_y'] - 60.0) - (60.0 - bbox['min_y'])) < 1e-10
    assert abs((bbox['max_x'] - 10.0) - (10.0 - bbox['min_x'])) < 1e-10


def test_compute_bbox_size_proportional():
    """Test at større size gir større bbox."""
    small = _compute_bbox(60.0, 10.0, 100)
    large = _compute_bbox(60.0, 10.0, 10000)
    assert (large['max_y'] - large['min_y']) > (small['max_y'] - small['min_y'])
    assert (large['max_x'] - large['min_x']) > (small['max_x'] - small['min_x'])


def test_compute_bbox_minimum_size():
    """Test at bbox har minimum størrelse selv med size=0."""
    bbox = _compute_bbox(60.0, 10.0, 0)
    # size clampes til 1.0, så bbox bør være > 0
    assert bbox['max_y'] > bbox['min_y']
    assert bbox['max_x'] > bbox['min_x']


def test_compute_bbox_covers_full_radius():
    """Bbox skal dekke full søkeradius — ikke bare halvparten.

    search_nearby() bruker haversine-radius = size_m. _compute_bbox() må strekke
    seg minst size_m meter i hver kardinalretning slik at AO-resultater og lokal
    DB-treff er konsistente (ingen sites havner i lokal DB men utenfor AO-bbox).
    """
    import math
    size_m = 1000
    bbox = _compute_bbox(60.0, 10.0, size_m)
    meters_per_deg_lat = 111_320.0
    half_lat_m = (bbox['max_y'] - bbox['min_y']) / 2 * meters_per_deg_lat
    assert half_lat_m >= size_m * 0.99, (
        f'Bbox dekker bare {half_lat_m:.0f}m nord/sør, forventet minst {size_m}m'
    )


# --- _normalize_site ---

def test_normalize_site_standard():
    """Test normalisering med standard feltnavn."""
    raw = {'id': 42, 'name': 'Østensjøvannet', 'latitude': 59.91, 'longitude': 10.81}
    site = _normalize_site(raw, set())
    assert site['id'] == 42
    assert site['name'] == 'Østensjøvannet'
    assert site['lat'] == 59.91
    assert site['lon'] == 10.81


def test_normalize_site_alternate_keys():
    """Test normalisering med alternative feltnavn."""
    raw = {'Id': 5, 'Name': 'Sognsvann', 'Lat': 59.97, 'Lon': 10.73}
    site = _normalize_site(raw, set())
    assert site['id'] == 5
    assert site['name'] == 'Sognsvann'


def test_normalize_site_mine():
    """Test at site markeres som min."""
    raw = {'id': 42, 'name': 'Min lokasjon', 'lat': 60.0, 'lon': 10.0}
    site = _normalize_site(raw, {42})
    assert site.get('isMine') is True


def test_normalize_site_not_mine():
    """Test at andre sites ikke markeres som mine."""
    raw = {'id': 42, 'name': 'Andres lokasjon', 'lat': 60.0, 'lon': 10.0}
    site = _normalize_site(raw, {99, 100})
    assert 'isMine' not in site


def test_normalize_site_issuper_true():
    """Test superlokasjon-deteksjon fra eksplisitt flagg."""
    raw = {'id': 1, 'name': 'Super', 'lat': 60.0, 'lon': 10.0, 'isSuper': True}
    site = _normalize_site(raw, set())
    assert site['isSuper'] is True


def test_normalize_site_issuper_false():
    """Test at isSuper=false bevares."""
    raw = {'id': 1, 'name': 'Normal', 'lat': 60.0, 'lon': 10.0, 'isSuper': False}
    site = _normalize_site(raw, set())
    assert site['isSuper'] is False


def test_normalize_site_parent_implies_not_super():
    """Test at site med parentSiteId ikke er superlokasjon."""
    raw = {'id': 2, 'name': 'Sub', 'lat': 60.0, 'lon': 10.0, 'parentSiteId': 1}
    site = _normalize_site(raw, set())
    assert site['isSuper'] is False
    assert site['parentId'] == 1


def test_normalize_site_municipality():
    """Test at kommune og fylke fra AO tas med."""
    raw = {'id': 3, 'name': 'Storevatnet', 'lat': 60.0, 'lon': 10.0,
           'municipalityName': 'Bergen', 'countyName': 'Vestland'}
    site = _normalize_site(raw, set())
    assert site['municipality'] == 'Bergen'
    assert site['county'] == 'Vestland'


def test_normalize_site_without_municipality():
    """Test at manglende kommune ikke gir tomme felt."""
    raw = {'id': 4, 'name': 'Uten kommune', 'lat': 60.0, 'lon': 10.0}
    site = _normalize_site(raw, set())
    assert 'municipality' not in site
    assert 'county' not in site


# --- _resolve_super_sites ---

def test_resolve_super_sites():
    """Test at parent-referanser utleder superlokasjoner."""
    sites = [
        {'id': 1, 'name': 'Parent', 'raw': {'id': 1}},
        {'id': 2, 'name': 'Child', 'raw': {'id': 2, 'parentSiteId': 1}},
    ]
    _resolve_super_sites(sites)
    assert sites[0].get('isSuper') is True
    assert sites[1].get('isSuper') is False


def test_resolve_super_sites_no_parents():
    """Test at sites uten parent-referanser ikke endres."""
    sites = [
        {'id': 1, 'name': 'A', 'raw': {'id': 1}},
        {'id': 2, 'name': 'B', 'raw': {'id': 2}},
    ]
    _resolve_super_sites(sites)
    assert 'isSuper' not in sites[0]
    assert 'isSuper' not in sites[1]


def test_resolve_super_sites_orphan_parent():
    """Test at child med parent utenfor listen håndteres."""
    sites = [
        {'id': 2, 'name': 'Child', 'raw': {'id': 2, 'parentSiteId': 99}},
    ]
    _resolve_super_sites(sites)
    assert sites[0].get('isSuper') is False
    assert sites[0].get('parentId') == 99


def test_resolve_super_sites_string_vs_int_id():
    """Test at int site-ID og string parentSiteId (eller omvendt) matches korrekt."""
    # AO returnerer noen ganger id som int men parentSiteId som string
    sites = [
        {'id': 1, 'name': 'Parent', 'raw': {'id': 1}},
        {'id': 2, 'name': 'Child', 'raw': {'id': 2, 'parentSiteId': '1'}},
    ]
    _resolve_super_sites(sites)
    assert sites[0].get('isSuper') is True
    assert sites[1].get('isSuper') is False


def test_resolve_super_sites_pascal_case_parent():
    """Test at PascalCase ParentSiteId gjenkjennes."""
    sites = [
        {'id': 10, 'name': 'Parent', 'raw': {'id': 10}},
        {'id': 20, 'name': 'Child', 'raw': {'id': 20, 'ParentSiteId': 10}},
    ]
    _resolve_super_sites(sites)
    assert sites[0].get('isSuper') is True
    assert sites[1].get('isSuper') is False


# --- _mark_env_owned_sites ---

def test_mark_env_owned_sites(monkeypatch):
    """Test at sites merkes fra MY_AO_SITE_IDS."""
    monkeypatch.setenv('MY_AO_SITE_IDS', '42, 99')
    sites = [
        {'id': 42, 'name': 'Min'},
        {'id': 1, 'name': 'Andres'},
        {'id': 99, 'name': 'Min også'},
    ]
    _mark_env_owned_sites(sites)
    assert sites[0].get('isMine') is True
    assert 'isMine' not in sites[1]
    assert sites[2].get('isMine') is True


def test_mark_env_owned_sites_empty(monkeypatch):
    """Test at tom MY_AO_SITE_IDS ikke markerer noe."""
    monkeypatch.delenv('MY_AO_SITE_IDS', raising=False)
    sites = [{'id': 42, 'name': 'Test'}]
    _mark_env_owned_sites(sites)
    assert 'isMine' not in sites[0]


# --- _ensure_auth ---

def test_ensure_auth_no_credentials():
    """Test at _ensure_auth returnerer uendret uten credentials."""
    auth, refreshed = _ensure_auth(None, None, None)
    assert auth is None
    assert refreshed is None


def test_ensure_auth_sliding_returns_new_cookie(monkeypatch):
    """Test at sliding expiration returnerer ny cookie."""
    monkeypatch.setattr(
        'src.api_handlers._sliding_expiration',
        lambda auth, user_id, login: 'new-cookie'
    )
    auth, refreshed = _ensure_auth('old-cookie', '12345', '12345:abc')
    assert auth == 'new-cookie'
    assert refreshed == 'new-cookie'


def test_ensure_auth_full_relogin_fallback(monkeypatch):
    """Test at full relogin brukes når sliding feiler og cookie er utløpt."""
    monkeypatch.setattr(
        'src.api_handlers._sliding_expiration',
        lambda auth, user_id, login: None
    )
    monkeypatch.setattr(
        'src.api_handlers._is_cookie_expired',
        lambda auth, user_id, login: True
    )
    monkeypatch.setattr(
        'src.api_handlers._full_relogin',
        lambda user_id, login: 'relogin-cookie'
    )
    auth, refreshed = _ensure_auth('old-cookie', '12345', '12345:abc')
    assert auth == 'relogin-cookie'
    assert refreshed == 'relogin-cookie'


def test_ensure_auth_no_refresh_needed(monkeypatch):
    """Test at auth beholdes når sliding ikke gir ny cookie og cookie er gyldig."""
    monkeypatch.setattr(
        'src.api_handlers._sliding_expiration',
        lambda auth, user_id, login: None
    )
    monkeypatch.setattr(
        'src.api_handlers._is_cookie_expired',
        lambda auth, user_id, login: False
    )
    auth, refreshed = _ensure_auth('valid-cookie', '12345', '12345:abc')
    assert auth == 'valid-cookie'
    assert refreshed is None


# --- _save_credentials / _load_credentials ---

def test_credentials_roundtrip(monkeypatch):
    """Test at credentials lagres og lastes fra disk."""
    from src.api_handlers import _save_credentials, _load_credentials

    with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
        tmp_path = f.name

    try:
        monkeypatch.setattr('src.api_handlers._CREDENTIALS_PATH', tmp_path)

        # Lagre
        _save_credentials('12345', 'testuser', 'testpass')

        # Last
        result = _load_credentials('12345')
        assert result == ('testuser', 'testpass')

        # Ukjent bruker
        assert _load_credentials('99999') is None
    finally:
        os.unlink(tmp_path)


def test_credentials_survives_overwrite(monkeypatch):
    """Test at credentials for flere brukere lagres uavhengig."""
    from src.api_handlers import _save_credentials, _load_credentials

    with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
        tmp_path = f.name

    try:
        monkeypatch.setattr('src.api_handlers._CREDENTIALS_PATH', tmp_path)

        _save_credentials('111', 'user1', 'pass1')
        _save_credentials('222', 'user2', 'pass2')

        assert _load_credentials('111') == ('user1', 'pass1')
        assert _load_credentials('222') == ('user2', 'pass2')
    finally:
        os.unlink(tmp_path)


def test_load_credentials_missing_file(monkeypatch):
    """Test at manglende fil returnerer None."""
    from src.api_handlers import _load_credentials

    monkeypatch.setattr('src.api_handlers._CREDENTIALS_PATH', '/tmp/nonexistent_creds_xyz.json')
    assert _load_credentials('12345') is None


# --- _full_relogin ---

def test_full_relogin_logintoken_first(monkeypatch):
    """Test at logintoken-refresh prøves før credentials."""
    from src.api_handlers import _full_relogin

    monkeypatch.setattr(
        'src.api_handlers._refresh_with_logintoken',
        lambda login_token, user_id: 'logintoken-cookie'
    )
    result = _full_relogin('12345', '12345:abc')
    assert result == 'logintoken-cookie'


def test_full_relogin_credentials_fallback(monkeypatch):
    """Test at credentials brukes når logintoken feiler."""
    from src.api_handlers import _full_relogin, _save_credentials

    with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
        tmp_path = f.name

    try:
        monkeypatch.setattr('src.api_handlers._CREDENTIALS_PATH', tmp_path)
        monkeypatch.setattr(
            'src.api_handlers._refresh_with_logintoken',
            lambda login_token, user_id: None
        )
        monkeypatch.setattr(
            'src.api_handlers.login_to_ao',
            lambda username, password: {'authCookie': 'cred-cookie', 'loginToken': 'lt', 'userId': '12345'}
        )

        _save_credentials('12345', 'testuser', 'testpass')
        result = _full_relogin('12345', '12345:abc')
        assert result == 'cred-cookie'
    finally:
        os.unlink(tmp_path)


def test_full_relogin_no_credentials(monkeypatch):
    """Test at None returneres uten credentials og logintoken."""
    from src.api_handlers import _full_relogin

    monkeypatch.setattr('src.api_handlers._CREDENTIALS_PATH', '/tmp/nonexistent_creds_xyz.json')
    result = _full_relogin('12345', None)
    assert result is None
