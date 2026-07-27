# Sending, deling og retting — arbeidsøkt 27. juli 2026

Fra v1.39.0 til v1.42.0. Startet som en plan for å kunne rette allerede innsendte
observasjoner, endte med tre feilrettinger, to nye funksjoner og en kartlegging av AOs
redigerings-API.

Detaljene ligger i egne dokumenter; dette er oversikten og beslutningene.

| Dokument | Innhold |
|----------|---------|
| `ao-rediger-api.md` | AOs redigerings-API, kartlagt fra HAR-fangst |
| `ao-rediger-capture.md` | Oppskrift for ny HAR-fangst hvis AO endrer skjemaet |
| `rediger-sendte-obs-plan.md` | Produkteier-vurdering og fase 0/A/B/C |
| `deling-av-observasjoner-plan.md` | Delingsfunksjonen, inkl. Redis-vurderingen |

---

## Hva som ble sendt ut

| Versjon | Innhold |
|---------|---------|
| **v1.39.1** | Validering av tidspunkt frem i tid (tre hull), og verifisering av at AO faktisk publiserte |
| **v1.40.0** | Deling av funn via hemmelig lenke |
| **v1.41.0** | Sendt-logg — kvittering for publiserte funn, med deling og «kopier til lista» |
| **v1.41.1–.2** | Distribusjonsfikser: SW-bump og versjonert service-worker-URL |
| **v1.42.0** | Dublett-vern: «✓ sendt»-merke og advarsel før noe sendes to ganger |

---

## Feil som ble funnet og rettet

### 1. Appen meldte suksess på funn AO ikke publiserte

Alvorligst. `publish_all` sjekket bare at `PublishAll` svarte HTTP < 400 og returnerte så
`count = len(observations)`. AO publiserer ikke rader den underkjenner — de blir liggende i
gjennomgangskøen. Brukeren fikk grønn hake på en observasjon som aldri ble publisert.

Nå polles `NumberOfSightingsSubmitted` etter publisering (`_remaining_after_publish`), og
gjenværende rader hentes med `BindReviewSightingsGrid` slik at meldingen kan si *hvilken*
observasjon og *hvorfor* — ikke bare et tall.

### 2. Validering av fremtidig tidspunkt fantes bare ett sted

`observation-commit.js` blokkerte tidspunkt frem i tid ved registrering. Men:

- **`edit.html`** hadde ingen sjekk i det hele tatt — skrev dato/tid rett til localStorage.
- **«Sett klokkeslett» på gruppe** validerte mot `groupItems[0]` sin dato, men skrev
  klokkeslettet på *hver* obs sin egen dato. Spente gruppen over flere datoer, kunne en obs
  med dagens dato få et tidspunkt frem i tid uten at advarselen slo til. Dette var den
  faktiske årsaken til tårnseiler-saken.

Begge rettet, og `handleDirectSend` kontrollerer nå hele lista før sending — uansett hvilken
vei tidspunktet kom inn.

### 3. Ingen markering av allerede sendte funn

Lista tømmes ikke automatisk etter sending. Svarte man nei på «tøm lista?» og registrerte
nye funn senere, sendte neste trykk *alt* på nytt, og de gamle ble liggende dobbelt i AO —
uten varsel og uten mulighet til å se hvilke. Løst i v1.42.0.

---

## Beslutninger

**SQLite framfor Redis for delinger.** Redis' TTL er elegant, men koster en container til på
en Pi med 4 GB, persistens som må konfigureres og en backup-rutine. Avgjørende argument:
Redis *sletter* ved utløp, og da kan vi ikke skille «utløpt» fra «finnes ikke». Utløp i
SQLite er én `DELETE WHERE expires_ts < now` ved hver skriving — ingen cron.

**Personvern som kode, ikke intensjon.** Delingen hviteliste-filtrerer felt på serveren, så
koordinater lagres aldri — de kan ikke lekke fra en database de ikke er i. Funn med
`hideUntil` er skjult på AO og deles ikke. Ukjent og utløpt lenke gir samme side, så ingen
kan teste seg fram til hvilke delinger som finnes.

**Fase A (bekreftelse før sending) droppet.** Ville bedt brukeren se etter det maskinen
allerede sjekker, og «er du sikker?» klikkes bort etter tredje gang. Publiser-knappen ligger
dessuten i seksjon ④, langt fra registreringsflyten. Erstattet av dublett-vernet, som er
stille når alt er nytt og konkret når det ikke er det.

**Fase C (redigering av publiserte funn) utsatt til etter BirdLife-lanseringen.** Fase 0 ga
teknisk grønt lys, men prisen ble bekreftet: 149 felt i `Save`, ingen GET-URL, og funnet må
publiseres på nytt. Det er det eneste i backloggen der en bug ødelegger data hos andre — AO
sender videre til GBIF. AO løser dessuten redigering allerede, og den faktiske smerten (at
appen glemte hva som ble sendt) er borte med sendt-loggen.

---

## Lærdom: riktig kode er ikke nok

Sendt-loggen var korrekt implementert og verifisert på origin, men registrerte ingenting for
brukeren. To mekanismer i lag:

1. **`CACHE_NAME` i `sw.js` ble ikke bumpet.** Uten en endring i `sw.js` trigger nettleseren
   aldri install/activate, og installerte PWA-er kjørte gammel `export-operations.js`.
2. **Cloudflare overstyrer origin sin `Cache-Control`** (`max-age=300` → `max-age=14400`).
   Da bumpen kom, lå gammel `sw.js` fortsatt i edge-cachen.

Avhjulpet med versjonert SW-URL (`/sw.js?v=<VERSION>`) og `cache: 'reload'` i precache.
SW-bumpen står nå som eksplisitt steg 2 i versjonsrutinen i `CLAUDE.md`.

Generalisert til `04-knowledge/pwa-service-worker-cloudflare.md` i Obsidian, siden det
gjelder alle hobbyappene bak Cloudflare.

---

## Åpent

- **Cloudflare Browser Cache TTL → «Respect Existing Headers».** Ett klikk i dashboardet
  fjerner hele problemklassen over. `?v=` dekker bare service workeren; øvrige `/js/*` har
  fortsatt et vindu på inntil 4 timer etter deploy. Se `ENDRINGER_OG_TODO.md`.
- **Sendt-logg for «Kopier & åpne AO-import»** — fanger i dag kun direktesending.
- **Fase 2 av deling:** «Mine delinger», valgbar levetid, visningsteller.
- **Fra UX-restlista før lansering:** LocationDB-verifisering i prod og kapasitetstest.
