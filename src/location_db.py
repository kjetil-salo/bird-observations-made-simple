"""
Lokal SQLite-database for AO-lokasjoner.

Deles mellom enkel-ao og dagens-funn via et felles Docker-volum.
Aktiveres med miljøvariabel LOCATION_DB_PATH.
"""

import logging
import math
import sqlite3

logger = logging.getLogger('fugleobs')

_SCHEMA = """
CREATE TABLE IF NOT EXISTS locations (
    ao_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    lat REAL,
    lon REAL,
    is_private INTEGER DEFAULT 0,
    is_super INTEGER DEFAULT 0,
    parent_id INTEGER,
    municipality TEXT,
    county TEXT,
    source TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_locations_geo ON locations(lat, lon);
CREATE INDEX IF NOT EXISTS idx_locations_name ON locations(name COLLATE NOCASE);
"""


class LocationDB:
    """SQLite-basert lokasjons-cache med WAL-modus for deling mellom containere."""

    def __init__(self, db_path):
        self.db_path = db_path
        with self._connect() as conn:
            row = conn.execute("SELECT sql FROM sqlite_master WHERE name='locations'").fetchone()
            if row and 'lat REAL NOT NULL' in row[0]:
                logger.info('LocationDB: migrerer lat/lon til nullable...')
                conn.execute('ALTER TABLE locations RENAME TO locations_old')
                conn.executescript(_SCHEMA)
                conn.execute('INSERT INTO locations SELECT * FROM locations_old')
                conn.execute('DROP TABLE locations_old')
            else:
                conn.executescript(_SCHEMA)
                # Legg til municipality/county hvis de mangler (eksisterende DB)
                cols = {r[1] for r in conn.execute('PRAGMA table_info(locations)')}
                if 'municipality' not in cols:
                    conn.execute('ALTER TABLE locations ADD COLUMN municipality TEXT')
                if 'county' not in cols:
                    conn.execute('ALTER TABLE locations ADD COLUMN county TEXT')
        logger.info(f'LocationDB initialisert: {db_path}')

    def _connect(self):
        """Opprett ny tilkobling. Ny per operasjon for å se WAL-endringer fra andre prosesser."""
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA busy_timeout=5000')
        conn.row_factory = sqlite3.Row
        return conn

    def upsert_locations(self, sites, source='enkel-ao'):
        """Sett inn eller oppdater lokasjoner.

        Args:
            sites: Liste med site-dicts (id, name, lat, lon, isPrivate, isSuper, parentId)
            source: Kildeapp ('enkel-ao' eller 'dagens-funn')
        """
        with self._connect() as conn:
            inserted = 0
            for site in sites:
                ao_id = site.get('id')
                name = site.get('name')
                lat = site.get('lat')
                lon = site.get('lon')
                if ao_id is None or not name or lat is None or lon is None:
                    continue
                try:
                    conn.execute(
                        """INSERT INTO locations (ao_id, name, lat, lon, is_private, is_super, parent_id, municipality, county, source)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                           ON CONFLICT(ao_id) DO UPDATE SET
                               name=excluded.name,
                               lat=excluded.lat,
                               lon=excluded.lon,
                               is_private=excluded.is_private,
                               is_super=excluded.is_super,
                               parent_id=excluded.parent_id,
                               municipality=COALESCE(excluded.municipality, municipality),
                               county=COALESCE(excluded.county, county),
                               updated_at=datetime('now')""",
                        (
                            int(ao_id),
                            name,
                            float(lat),
                            float(lon),
                            1 if site.get('isPrivate') else 0,
                            1 if site.get('isSuper') else 0,
                            site.get('parentId'),
                            site.get('municipality'),
                            site.get('county'),
                            source,
                        )
                    )
                    inserted += 1
                except (ValueError, TypeError, sqlite3.Error) as e:
                    logger.debug(f'LocationDB upsert feilet for site {ao_id}: {e}')
            if inserted:
                logger.debug(f'LocationDB: upsert {inserted} lokasjoner fra {source}')
            return inserted

    def search_nearby(self, lat, lon, radius_m=600):
        """Finn lokasjoner innenfor radius.

        Bruker bounding box for grovfiltrering, deretter haversine for nøyaktighet.

        Returns:
            Liste med site-dicts.
        """
        lat_delta = radius_m / 111_320.0
        lon_delta = radius_m / (111_320.0 * math.cos(math.radians(lat)))

        with self._connect() as conn:
            rows = conn.execute(
                """SELECT ao_id, name, lat, lon, is_private, is_super, parent_id,
                          municipality, county, source
                   FROM locations
                   WHERE lat BETWEEN ? AND ?
                     AND lon BETWEEN ? AND ?""",
                (lat - lat_delta, lat + lat_delta, lon - lon_delta, lon + lon_delta)
            ).fetchall()

        results = []
        for row in rows:
            dist = _haversine(lat, lon, row['lat'], row['lon'])
            if dist <= radius_m:
                results.append({
                    'id': row['ao_id'],
                    'name': row['name'],
                    'lat': row['lat'],
                    'lon': row['lon'],
                    'isPrivate': bool(row['is_private']),
                    'isSuper': bool(row['is_super']),
                    'parentId': row['parent_id'],
                    'municipality': row['municipality'],
                    'county': row['county'],
                    '_source': 'local_db',
                    '_distance': dist,
                })
        results.sort(key=lambda s: s['_distance'])
        return results

    def search_by_name(self, query, limit=50, lat=None, lon=None):
        """Søk lokasjoner på navn (case-insensitive LIKE).

        Hvis lat/lon er oppgitt, sorteres resultatene etter avstand og
        _distance (meter) inkluderes i hvert resultat.

        Returns:
            Liste med site-dicts.
        """
        fetch_limit = limit * 5 if (lat is not None and lon is not None) else limit
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT ao_id, name, lat, lon, is_private, is_super, parent_id, municipality, county, source
                   FROM locations
                   WHERE name LIKE ?
                     AND is_private = 0
                   LIMIT ?""",
                (f'%{query}%', fetch_limit)
            ).fetchall()

        results = []
        for row in rows:
            entry = {
                'id': row['ao_id'],
                'name': row['name'],
                'lat': row['lat'],
                'lon': row['lon'],
                'isPrivate': bool(row['is_private']),
                'isSuper': bool(row['is_super']),
                'parentId': row['parent_id'],
                'municipality': row['municipality'],
                'county': row['county'],
                '_source': 'local_db',
            }
            if lat is not None and lon is not None and row['lat'] is not None and row['lon'] is not None:
                entry['_distance'] = _haversine(lat, lon, row['lat'], row['lon'])
            results.append(entry)

        if lat is not None and lon is not None:
            results.sort(key=lambda s: s.get('_distance', float('inf')))

        return results[:limit]

    def count(self):
        """Antall lokasjoner i databasen."""
        with self._connect() as conn:
            return conn.execute('SELECT COUNT(*) FROM locations').fetchone()[0]


def _haversine(lat1, lon1, lat2, lon2):
    """Beregn avstand i meter mellom to koordinater."""
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
