"""Tester for lokal lokasjons-database."""

import os
import sys
import tempfile
import importlib.util

import pytest

# Last location_db direkte uten å trigge src/__init__.py
_spec = importlib.util.spec_from_file_location(
    'location_db',
    os.path.join(os.path.dirname(__file__), '..', 'src', 'location_db.py')
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
LocationDB = _mod.LocationDB
_haversine = _mod._haversine


@pytest.fixture
def db():
    """Opprett en midlertidig database for testing."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    try:
        yield LocationDB(db_path)
    finally:
        os.unlink(db_path)
        # Fjern WAL/SHM-filer hvis de finnes
        for ext in ('-wal', '-shm'):
            p = db_path + ext
            if os.path.exists(p):
                os.unlink(p)


SITE_OPERAEN = {
    'id': 1001,
    'name': 'Operaen, Oslo',
    'lat': 59.9075,
    'lon': 10.7530,
    'isPrivate': False,
    'isSuper': False,
}

SITE_EKEBERG = {
    'id': 1002,
    'name': 'Ekebergskråningen',
    'lat': 59.9010,
    'lon': 10.7610,
    'isPrivate': False,
    'isSuper': True,
    'parentId': None,
}

SITE_PRIVAT = {
    'id': 1003,
    'name': 'Min private lokalitet',
    'lat': 59.9080,
    'lon': 10.7540,
    'isPrivate': True,
    'isSuper': False,
}


class TestUpsert:
    def test_upsert_single(self, db):
        count = db.upsert_locations([SITE_OPERAEN], source='enkel-ao')
        assert count == 1
        assert db.count() == 1

    def test_upsert_multiple(self, db):
        count = db.upsert_locations([SITE_OPERAEN, SITE_EKEBERG, SITE_PRIVAT])
        assert count == 3
        assert db.count() == 3

    def test_upsert_updates_existing(self, db):
        db.upsert_locations([SITE_OPERAEN])
        updated = {**SITE_OPERAEN, 'name': 'Operaen (oppdatert)'}
        db.upsert_locations([updated])
        assert db.count() == 1
        results = db.search_by_name('oppdatert')
        assert len(results) == 1
        assert results[0]['name'] == 'Operaen (oppdatert)'

    def test_upsert_skips_invalid(self, db):
        invalid = [{'id': None, 'name': 'Test', 'lat': 59.0, 'lon': 10.0}]
        count = db.upsert_locations(invalid)
        assert count == 0

    def test_upsert_skips_missing_name(self, db):
        count = db.upsert_locations([{'id': 99, 'lat': 59.0, 'lon': 10.0}])
        assert count == 0


class TestSearchNearby:
    def test_finds_nearby(self, db):
        db.upsert_locations([SITE_OPERAEN, SITE_EKEBERG])
        results = db.search_nearby(59.907, 10.753, radius_m=1000)
        assert len(results) == 2

    def test_respects_radius(self, db):
        db.upsert_locations([SITE_OPERAEN, SITE_EKEBERG])
        # Svært liten radius — kun nærmeste
        results = db.search_nearby(59.9075, 10.7530, radius_m=50)
        assert len(results) == 1
        assert results[0]['id'] == 1001

    def test_sorted_by_distance(self, db):
        db.upsert_locations([SITE_EKEBERG, SITE_OPERAEN])
        results = db.search_nearby(59.9075, 10.7530, radius_m=2000)
        assert results[0]['id'] == 1001  # Operaen er nærmest

    def test_empty_when_none_nearby(self, db):
        db.upsert_locations([SITE_OPERAEN])
        results = db.search_nearby(60.5, 11.0, radius_m=500)
        assert len(results) == 0

    def test_includes_source_marker(self, db):
        db.upsert_locations([SITE_OPERAEN])
        results = db.search_nearby(59.9075, 10.7530, radius_m=100)
        assert results[0]['_source'] == 'local_db'

    def test_includes_municipality(self, db):
        db.upsert_locations([{**SITE_OPERAEN, 'municipality': 'Oslo', 'county': 'Oslo'}])
        results = db.search_nearby(59.9075, 10.7530, radius_m=100)
        assert results[0]['municipality'] == 'Oslo'
        assert results[0]['county'] == 'Oslo'


class TestSearchByName:
    def test_finds_by_partial_name(self, db):
        db.upsert_locations([SITE_OPERAEN, SITE_EKEBERG])
        results = db.search_by_name('Opera')
        assert len(results) == 1
        assert results[0]['name'] == 'Operaen, Oslo'

    def test_case_insensitive(self, db):
        db.upsert_locations([SITE_OPERAEN])
        results = db.search_by_name('operaen')
        assert len(results) == 1

    def test_empty_on_no_match(self, db):
        db.upsert_locations([SITE_OPERAEN])
        results = db.search_by_name('Stavanger')
        assert len(results) == 0

    def test_preserves_fields(self, db):
        db.upsert_locations([SITE_EKEBERG])
        results = db.search_by_name('Ekeberg')
        assert results[0]['isSuper'] is True
        assert results[0]['id'] == 1002


class TestHaversine:
    def test_same_point(self):
        assert _haversine(59.9, 10.7, 59.9, 10.7) == 0.0

    def test_known_distance(self):
        # Oslo sentrum til Drammen ≈ 36 km
        dist = _haversine(59.913, 10.752, 59.744, 10.204)
        assert 33_000 < dist < 40_000
