# TODO

## 15. Fjern kråke-unntak i toCsv (~juli 2026)

AO slo sammen kråke og svartkråke – begge fikk norsk navn "kråke" i navnebasen, noe som gir feil ved Excel-import.
Midlertidig workaround i `observations.js` `toCsv()`: når taxonName er "kråke" brukes latinsk navn (scientificNameHtml) i stedet.

Fjern unntaket når AO har fikset navnekonflikten. Se kommentar i kode (`TODO: Fjern dette unntaket...`).
Melding fra AO-support (2026-06-01, sak #11532): *"Det vil nok bli fikset snart."*

## ~~1. Oppdater dokumentasjon for v1.18.5 og v1.18.6~~ ✅
- ~~Changelog/docs mangler for de to siste patchene~~ → Oppdatert
- ~~Legg til instruksjon i CLAUDE.md~~ → Lagt til versjoneringsrutine

## 12. Utvid Playwright-tester til å dekke Galaxy-viewports

Playwright kan **ikke** se om en knapp er utenfor skjermen via `toBeVisible()` alene —
det sjekker bare CSS-synlighet (display/opacity/visibility), ikke viewport-plassering.
Det vi må gjøre er `boundingBox()` + sammenligne med `viewportSize().width`.

Det gjør vi allerede i `mobile-layout.spec.ts`, men kun for iphone-15-prosjektet.

**Hva som mangler:**
- Legg til `samsung-galaxy-412` i `playwright.config.ts` (412px, dpr 3.5, Android UA) — dette er S21/S24 Ultra-klassen
- Kjør de eksisterende boundingBox-testene mot dette prosjektet også
- Vurder: beholder vi 360px-prosjektet, eller bytter vi til 412px som er mer representativt for flaggskip?

**Merk:** 360px (nåværende) og 412px gir ulike feil — behold begge for å fange regresjoner på tvers.

## 10. Oppdater hjelpesiden (help.html)

- Layout-endringer siden sist: alder/kjønn flyttet inn i obs-seksjonen, section-optional fjernet, knapper omstrukturert i Send inn
- Gjennomgå help.html og oppdater skjermbilder/beskrivelser som ikke lenger stemmer
- Sjekk spesielt: beskrivelse av registreringsflyt og eksport-seksjonen

## 2. Medobservatører – nullstilling og avkryssing

**Auto-nullstilling ved ny dag:**
- Medobservatører skal automatisk fjernes/nullstilles hvis forrige observasjon ble registrert en annen dag enn i dag
- Hensikt: det er lett å glemme å ta bort medobservatør – en medobservatør satt i går skal ikke følge med videre
- Implementering: ved oppstart / first interaction, sjekk dato på siste lagrede observasjon. Hvis dato ≠ i dag → nullstill medobservatørfeltet

**Avkryssing:**
- Ved registrering av observasjon med medobservatører: legg til mulighet for å avkrysse disse
- Enten ved eksport (CSV) eller ved visning neste dag
- Gjelder enkel-ao / fugleobservasjoner-appen

## ~~6. Alder og kjønn – tilbake i obs-seksjonen~~ ✅

Implementert: alder og kjønn ligger nå som to kompakte dropdowns side om side under aktivitets-raden, inne i obs-seksjonen. Den separate "Tilleggsinfo"-seksjonen er fjernet.

## ~~11. Logging på Pi – loggvisning og rotasjon~~ ✅

~~- Når appen flyttes til Pi mister vi Fly.io sin innebygde logg-visning~~
~~- **Vurder loggvisning:** [Dozzle](https://dozzle.dev/)~~ → Dozzle kjører på Pi (`logs.efugl.no`, container `enkel-ao-dozzle-1`)
~~- **Loggrotasjon er obligatorisk**~~ → `json-file` med `max-size: 10m`, `max-file: 3` er satt i `docker-compose.pi.yml`
- Gjenstår: avklar om Supabase-logging (logview) erstattes, suppleres eller droppes

## 7. Flytte enkel-ao til Raspberry Pi

Teknisk migrering er ferdig: appen kjører på Pi (`ao.efugl.no`, samme mønster som dagens-funn/efugl.no), Docker Compose + Cloudflare Tunnel er satt opp, deploy-script (`update-ao-pi.sh`) finnes, loggrotasjon er på plass (se #11).

**Avklart:** Fly.io (`enkel-ao.fly.dev`) beholdes som reserve/backup — slettes IKKE. `ao.efugl.no` er ny hovedadresse.

**Gjenstår:**
- Varselbanner på Fly-instansen som forteller brukere at `ao.efugl.no` er raskere/ny hovedadresse (implementert i `public/js/migration-banner.js`, viser kun på `*.fly.dev`)
- Avklar om Supabase-logging skal beholdes eller droppes

## 8. Settings-siden – responsivt design for desktop

- Settings-siden ser ut til å ha fast bredde og ser ikke bra ut på desktop
- Bør ha samme responsive layout som index.html (maks-bredde, sentrert, skalerer pent)
- Gjennomgå CSS og HTML-struktur for settings.html og juster

## 3. "Skjul funn til dato" (AO-felt)
- AO har et felt for å skjule observasjoner frem til en dato
- Brukes sjelden, bør IKKE ligge på index.html
- Plassering: Settings-siden
- Alternativer å vurdere:
  - **Alt A:** Enkel checkboks "Skjul funn i 1 uke" (hardkodet 7 dager fra registrering)
  - **Alt B:** Checkboks + datofelt for egendefinert dato
- Verdien lagres i localStorage og brukes automatisk i CSV-eksport (kolonne 16: "Skjul funn til dato")

## 9. Gjennomgang av testdekning (etter layout-endringer)

- Flere layout-endringer nylig: alder/kjønn flyttet inn i obs-seksjonen, section-optional fjernet, knapp-HTML omstrukturert
- Sjekk om eksisterende tester fortsatt dekker disse elementene korrekt
- Vurder om nye tester trengs for de endrede komponentene

## 4. Gjennomgang av testdekning
- Sjekk om eksisterende tester dekker alle scenarier etter nyere endringer
- Vurder om nye tester trengs for: AO-import, aktivitetspills, visuell layout, curl-baserte API-kall
- Identifiser eventuelle hull i test-coverage

## ~~6. Private lokasjoner – hente alle på én gang (ikke bare bbox)~~ ✅

Implementert i v1.23.0. `BindUserSitesGrid` henter alle private lokasjoner, cachet i `localStorage['ao_private_sites']` (24t TTL). Sammenslåing med bbox-sites skjer i `location.js`.

**Kjent begrensning:** Race condition ved kald start — hvis bruker åpner dropdown før bakgrunnshenting er ferdig, vises ikke fjerne private lokasjoner. Vurdert som uproblematisk i praksis (skjer bare aller første gang etter innlogging).

**Neste:** Sortering innen privat-bolken — egne private (⭐ `isMine`) skal sorteres før andre private (👤) innen privat-gruppen, men fortsatt på avstand innen hver undergruppe. Altså: super → public → mine private (avstand) → andre private (avstand).

---

## 13. Gjennomgang av fargebruk og visuelt theme

En bruker ga tilbakemelding om at appen har for mange forskjellige farger. Vi er ikke nødvendigvis enig, men det er verdt å vurdere:
- Kartlegg alle farger som brukes i appen (knapper, badges, statusfarger, header, bakgrunner)
- Vurder om fargepaletten er konsistent og om alle farger har en tydelig semantisk rolle
- Sjekk spesielt: er det farger som brukes i lignende kontekster men ser ulike ut?
- Bestem om noe skal harmoniseres, eller om vi aktivt forsvarer variasjonen

## 14. Verifiser auth-relogin-logging i prod

- Sjekk logger (Dozzle/Fly.io) for `AUTH-RELOGIN-REQUIRED` og `AUTH-RELOGIN-RESULT` etter noen dagers drift
- Verifiser at sliding expiration fungerer (få eller ingen relogin-events)
- Verifiser at credentials overlever restart (ingen "ingen lagrede credentials"-meldinger)
- Deployet 2026-03-22 med error-logging i `_full_relogin`

## 12. Jevnlig logg-gjennomgang

- Se gjennom Fly.io-loggene (eller Pi-logger etter migrering) jevnlig
- Se etter: feilmeldinger, warnings, timeout-mønstre, uventede statuskoder
- Bruk loggen aktivt som kilde til forbedringer (slik som med dagens-funn 2026-03-12 der logganalyse avdekket parallellitets-timeout, HTML-i-stedet-for-JSON og ugyldig push-subscription)

---

## 15. Eksport feiler for observasjoner på private lokasjoner som ikke er mine

- Observasjoner gjort på andres private lokasjoner forsvinner/mistes ved eksport
- Skjedde i felt 2026-03-22 – har skjedd flere ganger
- Undersøk: er det CSV-genereringen, AO-import, eller lagringen som mister disse?
- Sjekk om locationId/stedsnavn mangler eller blir filtrert bort for ikke-egne private steder
- Kritisk bug – tap av data i felt er uakseptabelt

---

## ~~16. ksalo.no — landingsside for mine apper~~ ✅

~~Kjøpt domenet ksalo.no. Skal være en enkel statisk landingsside med tiles/kort som lenker til appene som allerede kjører på Pi-en.~~

ksalo.no er live (HTTP 200) med tiles for Keycloak, Quarkus-app, .NET-app, Dagens fugl, Enkel AO (→ `ao.efugl.no`) og Drivstoffprisene. Simple-auth mangler som egen tile — vurder om den fortsatt er aktuell.

---

## 17. Stemmestyring i enkel-ao

- Vurder stemmestyring for rask registrering i felt, spesielt på mobil når hendene er opptatt
- Utforsk hvilke felter som egner seg best for taleinput først: art, antall, aktivitet og kommentar
- Avklar om dette skal bygge på nettleserens innebygde tale-API eller en enklere trykk-for-a-snakke-løsning
- Vurder robusthet i felt: vindstøy, dialekt, offline-begrensninger og behov for tydelig bekreftelse før lagring
- Prototypebranch `codex/stemmestyring` er vurdert: ikke merge direkte, men bruk som idebank. Se `docs/stemmestyring-vurdering.md`

---

## 5. Omfattende analyse av brukervennlighet
- Fokus på reell brukervennlighet for målgruppen: fuglekikkere i felt med mobil
- WCAG er IKKE relevant – dette er en privat app for folk med normalt syn (fuglekikking krever godt syn)
- Vurder:
  - Er flyten fra lokasjon → art → antall → registrer rask og intuitiv?
  - Fungerer det godt med kalde/våte fingre og hansker?
  - Er knapper og touch-targets store nok i felt?
  - Er informasjonshierarkiet tydelig – ser man det viktigste først?
  - Er det unødvendige steg eller klikk som kan fjernes?
  - Fungerer appen godt i sterkt sollys (kontrast)?
  - Er feilmeldinger og feedback tydelige nok i stressede situasjoner (fuglen flyr snart!)?

---

## 18. Stedsnavn-søk må virke for både innlogget og ikke-innlogget bruker

- Søk på stedsnavn (lokalitet-autocomplete) må fungere uavhengig av innlogging – spesielt i etterregistrering
- I dag: `/api/ao-autocomplete` søker lokal DB først (ingen innlogging nødvendig), deretter AO hvis innlogget
- Krav: en bruker som ikke er innlogget skal fortsatt kunne finne og velge et sted via navnesøk (lokal LocationDB)
- Verifiser at flyten faktisk gir treff uten innlogging – både i Felt- og Etterregistreringsmodus
- Sjekk at LocationDB (`LOCATION_DB_PATH`) er aktiv i prod (Pi) slik at ikke-innlogget søk har data å søke i

## 19. Vurder å slette ao-direct.html

`ao-direct.html` stammer fra da AO-innlogging ikke skulle vises for vanlige brukere.
Nå ligger innlogging synlig i innstillingene, og long-press-snarveien til siden er fjernet (v1.38.2).

- Fortsatt referert fra `autocomplete.js` som «Logg inn»-lenke for flere lokaliteter (linje ~112 og ~122)
- Vurder om den funksjonaliteten kan erstattes av / lenke til innlogging i innstillinger
- Hvis ja: fjern `ao-direct.html` og oppdater `autocomplete.js`-lenkene
- Sjekk også `api.js`/`autocomplete.js` for `CustomEvent`-dispatch som notifiserer ao-direct.html i samme tab
