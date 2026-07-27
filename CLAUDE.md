# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Norwegian bird observation web app with species autocomplete and location services. Lightweight Python HTTP server serving static frontend + API proxies to external services (Artsobservasjoner.no, OpenStreetMap Nominatim).

**Core Tech:** Python 3.12 + `http.server.ThreadingHTTPServer`, vanilla HTML/CSS/JS frontend (ES6 modules), Docker, optional Supabase logging.

## Commands

### Local Development
```bash
python3 server.py          # Start server on port 3000
# or: npm run dev
```

### Running Tests
```bash
# Python unit tests
python3 -m pytest --maxfail=3

# E2E tests (Playwright)
cd tests/e2e_playwright
npm test                   # Against live server at localhost:3000
npm run test:mock          # With mock server
npm run test:with-mock     # Start mock + run tests
```

### Docker & Deploy
```bash
make build                 # Build Docker image
make run                   # Run container on port 3000
docker-compose up --build  # Run with mock Nominatim (safe for load testing)

# Deploy to Fly.io
./update-app.sh staging    # Deploy to staging
./update-app.sh production # Deploy to production — tester kjøres automatisk!

# Deploy to Raspberry Pi (primær produksjon)
./update-ao-pi.sh          # Rsync + docker-compose up --build på Pi
```

### Lokasjons-DB import (kjøres ved behov, ~40 min)
```bash
# Fyll LocationDB med alle offentlige norske AO-lokasjoner
LOCATION_DB_PATH=/sti/til/locations.db python3 tools/import_ao_locations.py

# Berik med kommune/fylke-data etterpå (~60 min, Nominatim 1 req/sek)
LOCATION_DB_PATH=/sti/til/locations.db python3 /tmp/enrich2.py
```

### Load Testing
```bash
python3 tools/load_test.py --mode gentle --requests 100 --concurrency 10
# Modes: static, mixed, gentle, ramp, soak, spike, smoke
```

## Architecture

### Request Routing (server.py)
The `Handler` class routes requests:
- `/` → `public/index.html`
- `/api/species?search=X` → proxies to artsobservasjoner.no (HTML scraping + JSON extraction)
- `/api/reverse?lat=X&lon=Y` → proxies to Nominatim for reverse geocoding
- `/api/ao-sites?lat=X&lon=Y&size=M` → fetches nearby observation locations from Artsobservasjoner
  - **Backend returnerer både private og offentlige** (maxSites=1000)
  - **Frontend (map.js)**: Kun offentlige vises på kart (sparer CPU/minne, brukeren vet hvor egne er)
  - **Frontend (location.js)**: Både offentlige og private i dropdown, maks 20. Sortering: 🏷️ superlokasjoner → offentlige → 👤 egne private (isMine) → andres private
- `/api/ao-autocomplete?term=X[&lat=Y&lon=Z]` → tekstsøk på lokaliteter
  - Søker lokal DB først (ingen innlogging nødvendig), deretter AO hvis innlogget
  - Med lat/lon: sorterer etter avstand, returnerer `_distance` i meters
  - Returnerer `isSuper`, `isPrivate`, `subvalue` (kommune, fylke) per resultat
- `/api/ao-login` (POST) → logger inn på AO med brukernavn/passord, returnerer `loginToken` + `authCookie`
- `/api/ao-import` (POST) → direkte publisering av observasjoner til AO (CSV-import + publish). Enkelt JSON-svar.
- `/api/ao-import-stream` (POST) → som `ao-import`, men **streamer fremdrift via SSE** (`text/event-stream`)
  - Fase-events: `importing {remaining, total}` → `publishing {total}` → `done {count}` / `error`
  - Fremdriften polles fra AOs egne endepunkter (se `docs/ao-import-fremdrift.md`):
    - `POST /ImportSighting/NumberOfSightingsImporting` (body `null`) → `{"Count":N}`, teller ned til 0 = ferdig parset
    - `POST /ReviewSighting/NumberOfSightingsSubmitted` (body `null`) → `{"Count":N}` i review-kø
  - Erstatter tidligere blind `sleep(3)` i `src/ao_import_httpx.py` med reell polling
- `/api/logview` (POST) → logs page views to Supabase
- `/api/feedback` (POST) → tar imot brukertilbakemelding (feil/ønske/annet) uten innlogging
  - Lagrer i `src/feedback_store.py` (SQLite), genererer saksnummer `AO-XXXXX`
  - Spam-vern: honeypot-felt (`website`), per-IP throttling (5/10 min), lengdegrenser
  - Sender eier-varsel via `src/email_notify.py` i bakgrunnstråd (best effort, `Reply-To` = melder)
- `/api/feedback-status` (POST, key-protected) → oppdaterer status på en sak (ny/under_arbeid/løst/avvist)
- `/feedback?key=X` → key-beskyttet admin-visning av tilbakemeldinger (statusfilter + statusendring)
- `/api/share` (POST) → lager delbar lenke av valgte observasjoner, returnerer `{slug, url, deleteKey, expiresTs}`
  - Lagres i `src/share_store.py` (SQLite, samme `stats.db`). Slug: 12 tegn fra entydig alfabet
  - **Personvern:** hvitelisting av felt — koordinater lagres aldri, `hideUntil`-obser slippes ikke gjennom
  - Levetid 14 dager (`SHARE_TTL_DAYS`). Utløp uten cron: `DELETE WHERE expires_ts < now` ved hver skriving
  - Spam-vern: egen per-IP-kvote (10/10 min), maks 200 obs og ~100 KB per deling
- `/api/share-delete` (POST) → trekker tilbake en deling; krever `slug` + `deleteKey`
- `/d/<slug>` → offentlig delingsside. Ukjent og utløpt slug gir **samme** 404-side (ingen enumerering)
- `/stats?key=X` → displays analytics (key-protected)
- `/health` → health check endpoint

### Backend Modules (src/)
- `api_handlers.py` — External API calls (species search, geocoding, AO sites, autocomplete)
- `html_templates.py` — HTML generation for stats- og feedback-admin-sider
- `supabase_log.py` — Optional Supabase analytics logging
- `feedback_store.py` — SQLite-lagring av tilbakemeldinger (samme `stats.db` via `DB_PATH`)
  - Schema: `case_no, type, message, email, app_version, user_agent, device_type, os, browser, ip, status, ts`
  - Saksnummer `AO-XXXXX` fra entydig alfabet (uten 0/O/1/I/L); `create_feedback`, `list_feedback`, `set_status`, `count_by_status`
- `email_notify.py` — Eier-varsel ved ny tilbakemelding. Provider auto-detekteres, ren no-op hvis ukonfigurert
  - Prioritet: SMTP (`SMTP_HOST`+`SMTP_USER`+`SMTP_PASS` via smtplib/STARTTLS) → Resend → SMTP2GO HTTP
  - `Reply-To` settes til melderens epost → «Svar» går rett til brukeren. 1 retry ved forbigående feil
  - **Prod bruker SMTP2GO** (gjenbruker drivstoff-appens creds): `mail-eu.smtp2go.com:2525`, From `noreply@drivstoffprisene.no`
- `share_store.py` — SQLite-lagring av delte observasjonslister (samme `stats.db`)
  - Schema: `slug, payload, display_name, delete_key, created_ts, expires_ts, views`
  - `sanitize_observations()` hviteliste-filtrerer felt — nye obs-felt lekker ikke ut ved uhell
  - Bevisst **ikke** Redis: SQLite gir persistens, backup og «utløpt»-melding gratis. Se `docs/deling-av-observasjoner-plan.md`
- `location_db.py` — SQLite-cache for AO-lokasjoner (delt mellom containere via Docker-volum)
  - Aktiveres med `LOCATION_DB_PATH` env-var
  - Schema: `ao_id, name, lat, lon, is_private, is_super, parent_id, municipality, county, source`
  - `search_by_name(query, limit, lat, lon)` — tekstsøk, sorterer etter avstand hvis lat/lon gitt
  - `search_nearby(lat, lon, radius_m)` — geo-søk (haversine, radius i meter)
  - `upsert_locations(sites, source)` — idempotent insert/update
  - **Super-deteksjon**: AO ByBoundingBox returnerer `parentSiteId=null` i sanntid. Super-status utledes i merge-steget fra lokal DB sin `parent_id` — hvis en lokal site peker på en foreldreside som finnes i AO-resultatet, markeres forelderen `isSuper=True`.
  - **Viktig**: `is_private` i lokal DB kan være utdatert (site endret til privat etter import). Bbox-størrelse (`_compute_bbox`) dekker nå full `size_m`-radius slik at AO-APIet returnerer korrekt `isPrivate` for sites i ytterkanten.

### Frontend Modules (public/js/)
Pure ES6 modules with no framework:
- `api.js` — API communication with 1-hour species cache
- `location.js` — Geolocation and AO sites integration
- `observations.js` — Main observation form logic
- `observation-commit.js` — Observation validation and activity pills rendering
- `storage.js` — Browser localStorage management (includes activity pills config)
- `ui.js` — UI state and rendering
- `share.js` — Deling av funn: forhåndsvisning, lenke-generering og tilbaketrekking
  - «Dagens funn» = **nyeste observasjonsdato i lista**, ikke kalenderdagen (viktig for etterregistrering)
  - Lagrer visningsnavn i `shareDisplayName_v1` og egne delinger i `myShares_v1`
- `autocomplete.js` — Lokalitet-autocomplete med avstand og ikoner (🏷️ super, 👤 privat, ⭐ mine)
  - Aktivt i **begge** modi (Felt og Etterregistrering)
  - `initAutocomplete(placeInput, onSelect, getPosition)` — getPosition gir GPS-posisjon for sortering

### Konfigurerbare Aktivitetspills (v1.18.0+)
Brukere kan velge 0-6 aktiviteter som vises som hurtigknapper:
- **localStorage-nøkkel:** `activityPills_v1`
- **Format:** `{version: 1, pills: [{label: "Stasjonær", value: "23", short: "Stasj"}, ...]}` (`short` valgfritt, maks 5 tegn — kortnavn på pill; tomt = fullt navn)
- **Funksjoner:** `saveActivityPills()`, `loadActivityPills()` i `storage.js`
- **UI:** Settings-side med dynamisk liste og +/- knapper
- **Migrering:** Automatisk fra gammelt `activityPillCount` format
- **Default:** 4 pills (Stasjonær, Rastende, Overflygende, Næringssøkende)
- **Dokumentasjon:** Se `docs/aktivitetspills-konfigurasjon.md`

### Test Structure
- `tests/test_*.py` — Python unit tests (pytest)
- `tests/e2e_playwright/` — Playwright E2E tests with mock server support

## Key Conventions

### Language
All code comments, docs, and UI text in **Norwegian** (`nb`). Maintain this consistency.

### External API Error Handling
External API failures return graceful degraded responses (empty arrays, status 200) rather than 500 errors:
```python
except Exception as e:
    print('Feil ved henting fra Artsobservasjoner:', e)
    self._send_json({'sites': []}, status=200)  # NOT 500
```

### External API Ethics
- Never run aggressive load tests against public APIs (Nominatim, Artsobservasjoner)
- Use `docker-compose` mock or `--mode gentle` with low request counts
- External API calls require explicit `User-Agent` headers (already configured)

### Environment Variables
- `PORT` (default: 3000)
- `AO_URL` (default: `https://www.artsobservasjoner.no`) — base-URL for artssøk
- `AO_MOBILE_URL` (default: `https://mobil.artsobservasjoner.no`) — base-URL for AO-lokaliteter
- `NOMINATIM_URL` (default: `https://nominatim.openstreetmap.org/reverse`) — reverse geokoding
- `LOCATION_DB_PATH` (optional) — sti til SQLite-DB med AO-lokasjoner
  - På Pi: `/mnt/ssd/docker/volumes/shared-locations/_data/locations.db`
  - Aktiverer lokalt navnesøk og avstandssortering i autocomplete uten innlogging
  - Fylles med `tools/import_ao_locations.py` (~487k norske lokasjoner, 78 MB)
- `SUPABASE_URL`, `SUPABASE_KEY` (optional logging)
- `STATS_KEY` (stats- og feedback-admin auth, default: 'salo')
- **Tilbakemelding-epostvarsel** (alle valgfrie — uten dem er varsling en no-op, skjema virker uansett):
  - `FEEDBACK_NOTIFY_TO` — mottaker (eier). Uten denne sendes ingenting
  - `FEEDBACK_NOTIFY_FROM` — avsender (må være verifisert hos provideren)
  - `SMTP_HOST`, `SMTP_PORT` (default 2525), `SMTP_USER`, `SMTP_PASS` — SMTP-utsending (prioriteres)
  - alternativt `RESEND_API_KEY` eller `SMTP2GO_API_KEY` for HTTP-API-utsending
  - Prod (Pi) og staging (Fly) bruker SMTP2GO SMTP; ligger som secrets/`.env` utenfor repo

For å teste med mock (simulere AO-timeout):
```bash
python3 mock/nominatim_app_timeout.py &                # Start mock på port 8080
AO_URL=http://localhost:8080 AO_MOBILE_URL=http://localhost:8080 python3 server.py
```

### Mobile Considerations
- Input `font-size: 16px` minimum to prevent iOS zoom
- App is fully functional without Supabase (optional dependency)

### Geolocation Limitations
- **Mobil (anbefalt):** GPS gir nøyaktig posisjon (5-50 meter)
- **PC/Mac:** Kun IP-basert lokalisering, kan gi feil posisjon (flere km avvik)
- Appen er primært designet for bruk på mobil i felt

### Git Commits
- **Aldri bruk Co-Authored-By** - commit uten co-author linje

### Deploy
- **Production deploy**: `update-app.sh production` kjører automatisk `python3 -m pytest --maxfail=3` først. Deploy avbrytes hvis tester feiler.

### Versjonering
Ved ny versjon (git tag), gjør alltid følgende:
1. Oppdater `VERSION` i `public/js/version.js` (brukes av index.html og help.html footers)
2. Oppdater `public/changelog.html` med kort beskrivelse av hva som er nytt
3. Oppdater relevant dokumentasjon i `docs/` hvis funksjonalitet er endret
