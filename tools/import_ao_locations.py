#!/usr/bin/env python3
"""
Batch-import av offentlige AO-lokasjoner til lokal SQLite-database.

Scanner Norge systematisk med et rutenett og henter offentlige lokasjoner
fra Artsobservasjoner sitt ByBoundingBox-API.

Bruk:
    LOCATION_DB_PATH=/path/to/locations.db python3 tools/import_ao_locations.py

Alternativt med eksplisitt AO-URL:
    LOCATION_DB_PATH=... AO_MOBILE_URL=https://mobil.artsobservasjoner.no python3 tools/import_ao_locations.py
"""

import importlib.util
import os
import sys
import time
from urllib.parse import urlencode

import httpx

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location('location_db', os.path.join(_root, 'src', 'location_db.py'))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
LocationDB = _mod.LocationDB

AO_MOBILE_BASE = os.getenv('AO_MOBILE_URL', 'https://mobil.artsobservasjoner.no')

# Norge bounding box
LAT_MIN, LAT_MAX = 57.5, 71.5
LON_MIN, LON_MAX = 4.5, 31.5

# Stegstørrelse: ~22 km lat, ~22 km lon — AO API tillater maks ~0.22°×0.22° eller ~0.20°×0.40°
LAT_STEP = 0.20
LON_STEP = 0.40

SLEEP_S = 0.2   # Pause mellom kall — etisk bruk
MAX_SITES = 1000

NOMINATIM_URL = os.getenv('NOMINATIM_URL', 'https://nominatim.openstreetmap.org/reverse')


def _frange(start, stop, step):
    """Flytallsgenerator uten akkumulert avrundingsfeil."""
    n = 0
    while True:
        v = start + n * step
        if v >= stop - 1e-9:
            break
        yield round(v, 8)
        n += 1


def fetch_sites_in_bbox(min_lat, min_lon, max_lat, max_lon):
    params = {
        'maxSites': str(MAX_SITES),
        'minX': f'{min_lon:.6f}',
        'minY': f'{min_lat:.6f}',
        'maxX': f'{max_lon:.6f}',
        'maxY': f'{max_lat:.6f}',
        'includePublicSites': 'true',
    }
    url = AO_MOBILE_BASE + '/core/Sites/ByBoundingBox?' + urlencode(params)
    with httpx.Client(timeout=15.0) as client:
        resp = client.get(url, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; Fugleobservasjoner-Import/1.0)',
            'Accept': 'application/json',
            'X-CSRF': '1',
            'Referer': 'https://mobil.artsobservasjoner.no/contribute/submit-sightings',
        })
        resp.raise_for_status()
        data = resp.json()
    if isinstance(data, list):
        return data
    elif isinstance(data, dict):
        return data.get('sites') or data.get('Sites') or []
    return []


def fetch_municipality(lat, lon):
    """Hent kommune og fylke fra Nominatim for et koordinat. Returnerer (municipality, county)."""
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(NOMINATIM_URL, params={
                'lat': f'{lat:.6f}', 'lon': f'{lon:.6f}', 'format': 'json'
            }, headers={'User-Agent': 'Mozilla/5.0 (compatible; Fugleobservasjoner-Import/1.0)'})
            resp.raise_for_status()
            addr = resp.json().get('address', {})
        municipality = addr.get('city') or addr.get('town') or addr.get('municipality') or addr.get('village')
        county = addr.get('county')
        return municipality, county
    except Exception:
        return None, None


def normalize_sites(raw_sites):
    result = []
    for item in raw_sites:
        if not isinstance(item, dict):
            continue
        name = (
            item.get('name') or item.get('Name') or
            item.get('siteName') or item.get('SiteName') or ''
        ).strip()
        site_id = item.get('id') or item.get('Id') or item.get('siteId')
        lat = item.get('lat') or item.get('latitude') or item.get('Lat')
        lon = item.get('lon') or item.get('longitude') or item.get('Lon')
        if not name or site_id is None or lat is None or lon is None:
            continue
        is_super = False
        for k in ('isSuper', 'isSuperSite', 'IsSuper', 'IsSuperSite'):
            if k in item:
                v = item[k]
                is_super = v is True or v in ('true', 'True', '1', 1)
                break
        parent_id = None
        for pk in ('parentId', 'parentSiteId', 'ParentId', 'parent'):
            if pk in item and item[pk] is not None:
                parent_id = item[pk]
                break
        result.append({
            'id': site_id,
            'name': name,
            'lat': float(lat),
            'lon': float(lon),
            'isPrivate': False,
            'isSuper': is_super,
            'parentId': parent_id,
            # AO oppgir kommune/fylke per lokalitet — mer presist enn Nominatim
            # på celle-senteret, som bommer nær kommunegrenser
            'municipality': item.get('municipalityName'),
            'county': item.get('countyName'),
        })
    return result


def main():
    db_path = os.getenv('LOCATION_DB_PATH')
    if not db_path:
        print('Feil: LOCATION_DB_PATH er ikke satt.', file=sys.stderr)
        print('Bruk: LOCATION_DB_PATH=/sti/til/locations.db python3 tools/import_ao_locations.py', file=sys.stderr)
        sys.exit(1)

    db = LocationDB(db_path)

    lat_steps = list(_frange(LAT_MIN, LAT_MAX, LAT_STEP))
    lon_steps = list(_frange(LON_MIN, LON_MAX, LON_STEP))
    total = len(lat_steps) * len(lon_steps)

    print(f'Starter import: {len(lat_steps)} lat × {len(lon_steps)} lon = {total} celler')
    print(f'Kilde: {AO_MOBILE_BASE}')
    print(f'Database: {db_path}')
    print(f'Eksisterende lokasjoner i DB: {db.count()}')
    print()

    cell = 0
    total_sites_fetched = 0
    total_upserted = 0
    errors = 0

    for lat in lat_steps:
        for lon in lon_steps:
            cell += 1
            max_lat = round(lat + LAT_STEP, 6)
            max_lon = round(lon + LON_STEP, 6)
            try:
                raw = fetch_sites_in_bbox(lat, lon, max_lat, max_lon)
                sites = normalize_sites(raw)
                municipality = county = None
                # Nominatim brukes kun som fallback for sites uten kommune fra AO
                if any(not s.get('municipality') for s in sites):
                    center_lat = (lat + max_lat) / 2
                    center_lon = (lon + max_lon) / 2
                    municipality, county = fetch_municipality(center_lat, center_lon)
                    for s in sites:
                        if not s.get('municipality'):
                            s['municipality'] = municipality
                            s['county'] = county
                upserted = db.upsert_locations(sites, source='bulk-import')
                total_sites_fetched += len(sites)
                total_upserted += upserted
                if sites:
                    first = sites[0]
                    loc_str = f'{first["municipality"]}, {first["county"]}' if first.get('municipality') else '–'
                    print(f'  [{cell:4d}/{total}] ({lat:.1f},{lon:.1f}): {len(sites):4d} lok — {loc_str}')
            except Exception as e:
                errors += 1
                print(f'  [{cell:4d}/{total}] FEIL ({lat:.1f},{lon:.1f}): {e}', file=sys.stderr)
            time.sleep(SLEEP_S)

    print()
    print(f'Ferdig. {total_sites_fetched} lokasjoner behandlet, {total_upserted} ny/oppdatert, {errors} feil.')
    print(f'Totalt i DB: {db.count()}')


if __name__ == '__main__':
    sys.stdout.reconfigure(line_buffering=True)
    main()
