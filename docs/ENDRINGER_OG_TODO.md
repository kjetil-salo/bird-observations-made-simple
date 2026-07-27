# Endringer og TODO

## ✅ Gjennomførte forbedringer (nyeste)

### v1.39.1–v1.42.0 (27. juli 2026) — sending, deling og retting
Se **[sending-deling-2026-07.md](sending-deling-2026-07.md)** for full oversikt.
- Appen meldte suksess på funn AO faktisk ikke publiserte — nå verifiseres køen etter publisering
- Tre hull i valideringen av tidspunkt frem i tid tettet (edit.html, gruppe-klokkeslett, før sending)
- Deling av funn via hemmelig lenke (`/d/<slug>`), 14 dagers levetid, uten koordinater
- Sendt-logg: kvittering for publiserte funn i 7 dager, med deling og «kopier til lista»
- Dublett-vern: «✓ sendt»-merke og advarsel før noe sendes to ganger
- AOs redigerings-API kartlagt (`ao-rediger-api.md`); redigering i appen utsatt til etter lansering

### 🎨 UI/UX Forbedringer
- **Visuell seksjonering**: Tydelige bokser skiller obligatoriske og valgfrie felt
- **Korrekt visuelt hierarki**: Grønne bokser for obligatoriske felt, grå for valgfrie
- **Forbedret gruppering**: Lokasjon, observasjon (obligatorisk), og tilleggsinfo (valgfritt)
- **Responsiv design**: Mindre padding og bedre mobile tilpasninger
- **Valgt art flash-effekt**: Flash-animasjonen på valgt art ("chosen") er nå svært subtil og dempet, slik at fokus ikke tas bort fra antall-feltet ved registrering.

### 🔧 Tekniske forbedringer
- **Valgfri Supabase**: App fungerer uten Supabase-credentials (in-memory modus)
- **Miljøvariabel-deteksjon**: Automatisk fallback til in-memory hvis `SUPABASE_URL`/`SUPABASE_KEY` mangler
- **Forbedret portabilitet**: Kan kjøres i GitHub Codespaces og andre miljøer uten eksterne avhengigheter
- **Staging/Production setup**: Separate miljøer med `enkel-ao-staging` og `enkel-ao`
  - `./update-app.sh staging` → https://enkel-ao-staging.fly.dev
  - `./update-app.sh production` → https://enkel-ao.fly.dev
  - Staging branch for testing før produksjon


### v1.13.0 (28. januar 2026)

#### 🔧 Refaktorering
- **Splittet main.js**: Fra 919 til 306 linjer ved å ekstrahere 4 nye moduler:
  - `form-state.js` — progressiv aktivering av skjemafelter
  - `species-search.js` — artssøk, resultatvisning og artsvalg
  - `observation-commit.js` — validering, lagring og aktivitets-pills
  - `export-operations.js` — CSV-eksport, kopiering og sletting
- **Delt tilstand**: All mutable state samlet i `appState`-objekt, DOM-referanser i `dom`-objekt
- **Unit-tester**: Nye tester for storage, location, api og species_offline
- **Fikset 3 E2E-tester**: Oppdatert tittel-sjekk og erstattet `#chosen` med `#search.species-selected`

#### 🛡️ Feilhåndtering og robusthet
- **Tre separate feilscenarioer**:
  - *Server nede*: "Ingen kontakt med server — bruker lokal artsliste — ⚙️ Innstillinger"
  - *AO nede*: "AO svarer ikke — bruker lokal artsliste — ⚙️ Innstillinger"
  - *Offline*: "Du er offline — bruker lokal artsliste — ⚙️ Innstillinger"
- **Status-rad**: Rød prikk med klikkbar lenke til innstillinger ved feil
- **Underarter deaktiveres** automatisk ved offline fallback
- **Service worker v43**: API-kall (`/api/`) går utenom SW-timeout, statiske filer har 5s timeout med cache-fallback
- **Offline artsliste**: Begrenset til 15 treff med forbedret sortering (startsWith prioriteres)

#### ⚙️ Konfigurasjon
- **Konfigurerbare AO-URLer**: `AO_URL` og `AO_MOBILE_URL` miljøvariabler for lokal testing med mock
- **Mock-server**: `mock/nominatim_app_timeout.py` for testing av timeout-scenarioer

#### 🎨 UI/UX
- **Større artsnavn**: Søkefelt 1.25rem, resultatliste 1.08rem, større søkeikon
- **Kompaktere layout**: Strammere padding i søkefelt og resultatliste, 6px border-radius
- **Kun sifre i antall-felt**: Blokkerer bokstaver, `e`, `.`, `+`, `-` på desktop
- **Grønn knapp på linje**: Aktivitetsknappen holder seg på samme linje som dropdown
- **Valgt art i søkefeltet**: Artsnavn vises direkte i feltet, markeres ved klikk
- **Kompakt iPad-layout**: Mindre vertikal padding og gap
- **Aktivitets-pills offline**: Klikkbare også i offline-modus
- **Offline underarter-advarsel**: Diskret gult ikon under boksen
- **Redigerings-side**: `public/edit.html` for å endre eksisterende observasjoner
- **CSV-kommentarer**: Mappes til kolonne 15 (AO-kompatibelt felt)

### 📈 Statistikkmuligheter
- **Supabase-statistikk**: Fullstendig historikk når miljøvariabler er konfigurert
- **In-memory fallback**: Øktbasert statistikk når Supabase ikke er tilgjengelig
- **Automatisk deteksjon**: Ingen konfigurasjon nødvendig - fungerer i begge moduser

## Tidligere versjoner

### v1.3.0 (13. januar 2026)

#### ✨ Nye funksjoner implementert:
- **Avanserte felter**: Lagt til alder og kjønn som valgfrie felter med checkbox-toggle
  - Alder: Komplett dropdown med AO-kompatible verdier (Egg, Pulli, 1K, 1K+, osv.)
  - Kjønn: Dropdown med AO-verdier (Hann, Hunn, Hunnfarget, I par)
- **Ny registreringsknapp**: Stor grønn knapp under alle felter
- **Utvidet CSV-eksport**: Alder og kjønn inkluderes for AO-import
- **Forbedret observasjonsvisning**: Ny "Detaljer"-kolonne

#### 🐛 Feilrettinger:
- Fikset JavaScript-feil som hindret "Hent lokalitet"-funksjonen
- Fjernet duplikat variabel-deklarasjoner

### 🎨 UI/UX Analyse (v1.4.0 grunnlag)

#### Sterke sider:
- ✅ Mørkt tema - moderne og øyenskånsomt
- ✅ Mobile-first - godt tilpasset mobilbruk med 16px font-size  
- ✅ Tydelige ikoner - 🕊️, 📍, osv.
- ✅ Responsiv layout

#### 🚨 Kritiske UX-problemer som ble løst:

**1. Forvirrende registreringsflyt:**
- ✅ Fjernet stor registreringsknapp, bruker inline ✓-knapp
- ✅ Forenklede flyt med tilbake til original design

**2. Visuell hierarki manglende:**
- ✅ Implementerte seksjonering med grønne/grå bokser
- ✅ Tydelig skille mellom obligatoriske og valgfrie felt

**3. Avanserte felter lite synlige:**
- ✅ Alder/kjønn alltid synlige (ikke skjult bak checkbox)
- ✅ Tydelige seksjoner viser hva som er obligatorisk/valgfritt

**4. Overveldende dropdown-lister:**
- ✅ Fortsatt mange valg, men nå tydelig markert som "tilleggsinfo"
- ✅ Visuell separasjon gjør det mindre overveldende

## 📋 TODO fremover (prioritert)

### 🔴 Høy prioritet

#### Brukerkommunikasjon:
- **Tilbakemeldingskanal (feil + ønsker)** — **✅ FASE 1 IMPLEMENTERT (2026-07-23, v1.39.0):** Lavterskel skjema uten innlogging. Bruker melder feil/ønske/annet + valgfri epost, får et saksnummer (`AO-XXXXX`, kort tilfeldig kode) som kvittering på skjerm. Appversjon + enhet/nettleser lagres automatisk for feilsøking.
  - **Arkitektur:** `POST /api/feedback` → `src/feedback_store.py` (SQLite i samme `stats.db`, følger `sqlite_log`-mønsteret). Key-beskyttet admin-visning på `/feedback?key=STATS_KEY` med statusfilter (ny/under_arbeid/løst/avvist) og statusendring. Lenker fra footer (index) + Innstillinger. Spam-vern: honeypot-felt + per-IP throttling (5/10 min) + lengdegrenser. Tester i `tests/test_feedback.py`.
  - **Bevisst valg:** Ingen epostutsendelse i fase 1 — vi har ingen sendefunksjon, og det ville dratt inn epost-provider/hemmeligheter/deliverability. Saksnummer på skjerm er kvittering nok; eier leser saker i admin og svarer manuelt fra egen epost (mailto-lenke med saksnr i emnet finnes i admin-visningen).
  - **✅ FASE 2 – EIER-VARSEL IMPLEMENTERT (2026-07-23):** `src/email_notify.py` sender et varsel til eier ved ny sak (best effort, i bakgrunnstråd så brukersvaret ikke forsinkes). **`Reply-To` settes til melderens epost** → «Svar» går rett til brukeren («starter på forms, tas videre på epost»). Provider auto-detekteres fra env og er ren no-op hvis ukonfigurert (samme filosofi som valgfri Supabase).
    - **Oppsett (env-vars, settes utenfor repo på Pi/Fly):** `FEEDBACK_NOTIFY_TO` (din epost — uten denne sendes ingenting), `FEEDBACK_NOTIFY_FROM` (verifisert avsender), og **enten** `RESEND_API_KEY` **eller** `SMTP2GO_API_KEY`. Begge providere støttes; Resend prioriteres hvis begge er satt.
    - **Ikke gjort (bevisst):** kvittering-epost til melder (saksnr på skjerm holder), og Supabase-speiling av feedback (i dag kun SQLite/Pi).
  - **🔜 FASE 3 (valgfritt):** Statusoppslag på saksnummer (melder kan følge opp), evt. enkel svartråd.

#### Tekniske forbedringer:
- ✅ **Forbedret feilhåndtering**: Tre separate meldinger for server nede, AO nede og offline. Status-rad med lenke til innstillinger. Underarter deaktiveres ved fallback. Mock-server for testing (`mock/nominatim_app_timeout.py`).

#### Mobile forbedringer:
- ~~**"Chosen species" bug**~~: Løst — valgt art vises nå i søkefeltet, ikke som separat element

### 🟡 Middels prioritet

#### UX-forbedringer:
- **Forkortelser på aktivitets-pills** (tips fra Espen): La aktivitets-hurtigknappene kunne vise et kort navn (maks ~5 tegn) i stedet for fullt navn. Motivasjon: kompakte pills → flere hurtigknapper får plass på skjermen. Hører hjemme i **innstillinger** (av som default — de fleste vil ikke ha det, men de ivrigste vil).
  - **Foreslått løsning (hybrid):** Legg til valgfritt `short`-felt (maxlength 5) per pill i `activityPills_v1`-konfigen. Tomt felt → vis fullt navn. Pills på hovedsiden viser `short` når satt.
  - **Kuraterte standarder:** Ship en «Foreslå forkortelser»-knapp som fyller inn fornuftige forkortelser for de 6 standard-aktivitetene (Stasjonær→«Stasj», Rastende→«Rast», osv.). Brukeren kan redigere.
  - **Beslutning (valgt):** ✅ **Hybrid** — vi kuraterer forslag for standard-aktivitetene («Foreslå forkortelser»-knapp), men brukeren kan redigere/skrive egne kortnavn (maks 5 tegn). Tomt felt = fullt navn.
  - **Berører:** `storage.js` (utvid pill-format + migrering), `settings.html` (kortnavn-felt i pill-liste), `observation-commit.js` (render `short` på pills). Bakoverkompatibel migrering fra dagens `{label, value}`.
  - **✅ IMPLEMENTERT (2026-07-09):** Valgfritt `short`-felt (maks 5 tegn) i `activityPills_v1`, kortnavn-input per rad i innstillinger, «Foreslå forkortelser»-knapp (`ACTIVITY_SHORT_SUGGESTIONS`, fyller kun tomme felt), pills viser `short` med fullt navn som tooltip. Klikk matcher fortsatt på fullt `label`. Bakoverkompatibelt.
- **Dropdown uten layout-forskyvning**: Vurder å vise søkeresultater med `position: absolute` så de ligger over innholdet under i stedet for å forskyve det ned. Gir mer stabil layout under søk.
- **Performance optimaliseringer**: Raskere artsøk og lokalitetshenting
- **Optimaliser dropdown-design**: Grupper alder-valg logisk (Egg | Ungfugl: 1K-serie | Voksen: Adult)
- **Lyst/mørkt tema**: Implementere theme-switching for alle sider (index, hjelp, stats)
  - Toggle-knapp for å bytte mellom lyst og mørkt tema
  - Lagre brukerens preferanse i localStorage

#### Tekniske oppgaver:
- **Staging-miljø på Pi**: Lag en staging-instans på Raspberry Pi (f.eks. egen container på annen port + `staging-ao-pi.efugl.no`, eller en `update-ao-pi.sh staging`-modus). **Motivasjon:** Fly-deploy tar for lang tid når man vil se en endring raskt i felt-lignende miljø. Pi er primær prod, så en Pi-staging gir rask iterasjon uten å røre prod. Vurder delt vs. separat LocationDB-volum og at staging ikke logger til prod-Supabase.
- **OpenSSL warnings**: Fikse urllib3/OpenSSL-advarsel i Python-miljø (lav prioritet)
- **Cloudflare cache-flush i deploy (Pi)**: `update-ao-pi.sh` bør purge Cloudflare-cachen for `ao-pi.efugl.no` etter deploy. **Problem observert 2026-07-09:** Cloudflare cachet gammel `storage.js`/`version.js` (4t edge-TTL, `cf-cache-status: HIT`) selv om origin sender `max-age=300`. Ny `settings.html` importerte `ACTIVITY_SHORT_SUGGESTIONS` fra en gammel cachet `storage.js` uten eksporten → ES-modul-import kastet → hele settings-scriptet stoppet (ingen pill-rader). Fly har ikke dette problemet.
  - **Løsning:** Legg til et purge-kall på slutten av `update-ao-pi.sh`, f.eks. `curl -X POST "https://api.cloudflare.com/client/v4/zones/$CF_ZONE_ID/purge_cache" -H "Authorization: Bearer $CF_API_TOKEN" -H "Content-Type: application/json" --data '{"purge_everything":true}'`. Krever `CF_ZONE_ID` + scoped `CF_API_TOKEN` (Cache Purge-rettighet), lagret utenfor repo.
  - **Alternativ/tillegg:** Vurder Cloudflare Cache Rule som bypasser cache for `/js/*` og `/*.html` (så versjonerte assets alltid revalideres), eller cache-busting query (`?v=<VERSION>`) på modul-imports.
  - **⭐ Enklest varige fiks (anbefalt, ikke gjort):** Cloudflare-dashboardet → **Caching → Configuration → Browser Cache TTL → «Respect Existing Headers»**. Edge følger da origin sine `max-age=300` i stedet for å overstyre med 4 timer, og hele problemklassen forsvinner uten API-token. Ett klikk.
  - **Gjentok seg 2026-07-27 (v1.41.0):** sendt-loggen registrerte ingenting etter publisering. To årsaker i lag: (1) `CACHE_NAME` i `sw.js` ble ikke bumpet, så nettleseren sjekket aldri etter ny kode — installerte PWA-er kjørte gammel `export-operations.js` uten `appendSentBatch`; (2) da bumpen kom, serverte Cloudflare fortsatt gammel `sw.js` (`cf-cache-status: HIT`, `max-age=14400`), så bumpen ville uansett ikke nådd fram før TTL-en gikk ut.
    - **Avhjulpet i v1.41.1/v1.41.2:** SW-bump lagt inn som eksplisitt steg i versjonsrutinen (CLAUDE.md), `sw.js` registreres som `/sw.js?v=<VERSION>` (ny cache-nøkkel per release), og precache bruker `cache: 'reload'` så en ny SW ikke lagrer de utdaterte filene den skulle erstatte.
    - **Står igjen:** `?v=` dekker kun service workeren. Øvrige `/js/*`-filer har fortsatt et vindu på inntil 4 timer etter deploy der edge kan servere forrige versjon. Siden dette er ES-moduler som importerer hverandre, betyr fersk fil + utdatert avhengighet at importen kaster og **hele appen ikke laster** — ikke bare en manglende funksjon.

### 🟢 Lav prioritet

#### Funksjonalitet:
- **Backup/export**: Eksporter hele observasjonshistorikken
- **Ytterligere Supabase-funksjoner**: Bruke Supabase til mer enn bare statistikk
- **Server-lagring av brukerinnstillinger (multi-enhet)**: La brukeren synke innstillinger (aktivitets-pills, forkortelser, tema, medobservatører, radius m.m.) på tvers av enheter. Naturlig nøkkel: AO `userId` (allerede tilgjengelig ved innlogging), lagret i Supabase. Vurder synk-strategi (siste-skriver-vinner vs. flett), og hva som IKKE skal synkes (aldri passord). Henger sammen med innloggings-løftet — når bruker først er innlogget, kan innstillinger følge kontoen.

- **Re-import av LocationDB med AOs egne kommunedata** (etter v1.43.0): `tools/import_ao_locations.py` henter nå kommune/fylke per lokalitet fra AO (`municipalityName`/`countyName`) i stedet for ett Nominatim-oppslag per bbox-celle. Eksisterende rader i `locations.db` har fortsatt celle-basert kommune, som bommer nær kommunegrenser og mangler helt for enkelte. En re-import (~40 min, `LOCATION_DB_PATH=/mnt/ssd/docker/volumes/shared-locations/_data/locations.db`) retter dette. Gjelder kun lokaliteter som vises fra lokal DB — treff fra AO har korrekt kommune allerede.

- **Sendt-logg for «Kopier & åpne AO-import»**: Sendt-loggen (v1.41.0) fanger kun direktesending. Bruker man kopier-og-åpne, vet ikke appen om importen faktisk gikk bra, og logger derfor ingenting. Mulig løsning: logg som «antatt sendt» med tydelig merking, eller spør brukeren etterpå. Vurder om det er verdt kompleksiteten.

#### Ønsker for fremtiden (kan være komplekst):
- **Redigering av allerede innlagte observasjoner**: La brukeren endre observasjoner som allerede er publisert til AO. **Kun for innloggede brukere** (krever AO-sesjon for å gjøre endringer mot AO). Må undersøke hvilke AO-endepunkter som finnes for å hente egne observasjoner og oppdatere/slette dem. Grensesnitt: liste over egne siste observasjoner → velg → rediger felt → send oppdatering. Merk at `public/edit.html` i dag redigerer lokale (ikke-publiserte) observasjoner før import — dette er en annen flyt (endre etter publisering).
- **Bilder på observasjoner**: Mulighet for å legge ved bilde(r) til en observasjon en gang i fremtiden. KAN være komplisert (opplasting, lagring/hosting, AO-støtte for bildevedlegg, mobilkamera-flyt, størrelse/komprimering, personvern). Tas med som ønske for fremtiden — ikke prioritert nå.

---

## Miljøvariabler og portabilitet

### Supabase (valgfritt)
Appen fungerer perfekt uten Supabase-konfigurasjon og faller tilbake til in-memory statistikk:
- `SUPABASE_URL` - for full statistikk-lagring
- `SUPABASE_KEY` - for autentisering mot Supabase

### Andre miljøvariabler:
- `PORT` (default: 3000)
- `AO_URL` (default: `https://www.artsobservasjoner.no`) — base-URL for artssøk
- `AO_MOBILE_URL` (default: `https://mobil.artsobservasjoner.no`) — base-URL for AO-lokaliteter
- `NOMINATIM_URL` (default: `https://nominatim.openstreetmap.org/reverse`) — reverse geokoding
- `STATS_KEY` (for statistikk-side, default: 'salo')

Sist oppdatert: 28.01.2026
