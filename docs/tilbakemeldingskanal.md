# Tilbakemeldingskanal (feil + ønsker)

Lavterskel kanal der brukere kan melde fra om feil og komme med ønsker – **uten
innlogging**. Innført i v1.39.0 (2026-07-23). Motivasjon: få signaler fra
(nye) brukere før og under BirdLife-lansering.

## Brukerflyt

1. Bruker åpner `public/feedback.html` (lenke i footer på forsiden og under
   Innstillinger → «Tilbakemelding»).
2. Velger type (🐛 feil / 💡 ønske / 💬 annet), skriver melding, og kan valgfritt
   oppgi e-post.
3. Skjemaet sender automatisk med **appversjon** (`version.js`) og
   **user-agent** for feilsøking.
4. Ved innsending vises et **saksnummer** (`AO-XXXXX`) som kvittering på skjerm.

Siden følger appens tema-system (`theme.js` + `body.theme-light`/`theme-clean`).
Default-temaet er lyst, så lys-varianten er viktig.

## Saksnummer

Format `AO-XXXXX` – 5 tegn fra et entydig alfabet (`ABCDEFGHJKMNPQRSTUVWXYZ23456789`,
uten 0/O/1/I/L). Kort tilfeldig kode framfor sekvensielt: ikke gjettbart, lekker
ikke saksvolum, og trygt hvis statusoppslag legges til senere.

## Backend

### `POST /api/feedback`
Tar imot `{type, message, email?, appVersion?, website?}`. Validerer,
genererer saksnummer, lagrer, og returnerer `{ok, caseNo}`.

**Spam-vern:**
- **Honeypot:** skjult `website`-felt. Fylt ut → later som alt gikk bra, lagrer
  ingenting.
- **Per-IP throttling:** maks 5 innsendinger per 10 min (in-memory).
- **Lengdegrenser:** melding maks 4000 tegn, e-post 200, versjon 40.

### `src/feedback_store.py`
SQLite-lagring i **samme `stats.db`** som statistikken (`DB_PATH`, default
`/data/stats.db`). Følger mønsteret til `src/sqlite_log.py`.

Tabell `feedback`: `id, case_no, type, message, email, app_version, user_agent,
device_type, os, browser, ip, status, ts`.

Funksjoner: `create_feedback`, `list_feedback`, `set_status`, `count_by_status`.
Status-verdier: `ny | under_arbeid | løst | avvist`.

### Admin-visning `/feedback?key=STATS_KEY`
Key-beskyttet (samme nøkkel som `/stats`). Tabell med alle saker, statusfilter,
og statusendring (POST `/api/feedback-status?key=…`). E-postadresser vises som
`mailto:`-lenke med saksnr i emnet, så eier kan svare manuelt.

## E-postvarsel (`src/email_notify.py`)

Sender et varsel til eier ved hver ny sak, i **bakgrunnstråd** (blokkerer aldri
brukerens svar), best effort med **1 retry** (SMTP-tilkoblinger timer av og til
ut forbigående).

**`Reply-To` settes til melderens e-post** → eier trykker bare «Svar» i varselet,
og svaret går rett til brukeren («starter på forms, tas videre på e-post»).

Provider auto-detekteres, og hele modulen er en **ren no-op** hvis ingenting er
konfigurert (skjemaet virker uansett). Prioritert rekkefølge:

1. **SMTP** (`SMTP_HOST` + `SMTP_USER` + `SMTP_PASS`) via `smtplib`/STARTTLS
2. `RESEND_API_KEY` → Resend HTTP-API
3. `SMTP2GO_API_KEY` → SMTP2GO HTTP-API

### Miljøvariabler
| Variabel | Beskrivelse |
|---|---|
| `FEEDBACK_NOTIFY_TO` | Mottaker (eier). Uten denne sendes ingenting |
| `FEEDBACK_NOTIFY_FROM` | Avsender (må være verifisert hos provideren) |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASS` | SMTP-utsending (`SMTP_PORT` default 2525) |
| `RESEND_API_KEY` / `SMTP2GO_API_KEY` | Alternativ HTTP-API-utsending |

### Oppsett i drift
Både **prod (Pi)** og **staging (Fly)** bruker SMTP2GO over SMTP, ved å gjenbruke
drivstoff-appens sende-credentials:
- Host `mail-eu.smtp2go.com`, port `2525`, TLS
- From `noreply@drivstoffprisene.no` (eneste verifiserte avsender i kontoen)
- `FEEDBACK_NOTIFY_TO = kjetil@vikebo.com`

Secrets ligger **utenfor repo**: på Fly som app-secrets (`flyctl secrets set … -a
enkel-ao-staging`), på Pi i `~/enkel-ao/.env` (leses via `env_file` i
`docker-compose.pi.yml`).

## Fremtidige faser (ikke gjort)

- **Kvittering-epost til melder** – bevisst droppet; saksnummer på skjerm holder.
- **Supabase-speiling** av feedback – i dag kun SQLite (prod = Pi).
- **Statusoppslag på saksnummer** – la melder følge opp saken selv.

## Filer

- `public/feedback.html` – skjemaside
- `src/feedback_store.py` – lagring
- `src/email_notify.py` – eier-varsel
- `src/html_templates.py` – `generate_feedback_admin_page(...)`
- `server.py` – ruting og handlere
- `tests/test_feedback.py` – tester
