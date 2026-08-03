# Bildeopplasting til AO — vurdering og plan

**Dato:** 2026-08-03
**Status:** Fase 0 avklart (`docs/ao-bilder-api.md`). **POC av fase A+B bygget** samme dag —
se «Implementert (POC)» nederst for hva som faktisk er kodet og hva som gjenstår før dette
er mer enn en proof-of-concept.
**Bakgrunn:** Bruker ønsker å kunne legge ved bilde på en observasjon i enkel-ao. Hintet som
startet undersøkelsen stemte: AO lar deg ikke laste opp bilder før funnet har fått en ekte
`SightingId` — bekreftet gjennom feltet `PossibleToUploadImages` i AOs egen gjennomgangskø.

---

## 1. Hvorfor dette er vanskeligere enn det ser ut som

enkel-ao sender i dag observasjoner til AO i tre serverside-steg, uten at nettleseren noen
gang besøker `artsobservasjoner.no` (`docs/ao-import-fremdrift.md`):

```
ParseObservations (CSV)  →  poll til ferdig parset  →  PublishAll
        "importing"                                      "publishing"
```

Et funn får sin permanente `SightingId` et sted i det **første** pilen — parsingen — men det
er **ikke synlig noe sted i dagens flyt**. Bildet må kobles til akkurat den IDen, i det
smale vinduet mellom «ferdig parset» og «publisert», før raden forsvinner fra
gjennomgangskøen. Det er tre nye, sammenkoblede problemer, ikke ett:

1. **Fange riktig `SightingId` for riktig lokal observasjon** — når AO parser en hel CSV-batch
   om gangen, uten radvis kvittering.
2. **Faktisk laste opp bildebytes** til en URL vi ennå ikke har sett (se `ao-bilder-api.md`).
3. **Ikke ødelegge noe som allerede virker** — direktesendingen er kjerneflyten i appen og har
   vært skjør før (`rediger-sendte-obs-plan.md`, «Funnet underveis»-avsnittet).

## 2. Matching: hvordan vet vi hvilken `SightingId` som hører til hvilken lokal obs?

`review_queue_rows()` (`ao_import_httpx.py`, allerede i kodebasen) gir oss alle rader i
gjennomgangskøen med `SightingId`. Problemet — allerede dokumentert i `ao-rediger-api.md` og
årsaken til at fase B **droppet** ID-fangst — er at køen kan inneholde **rader fra tidligere**
(`PublishAll` publiserer alt, ikke bare vårt), og at flere observasjoner lett har samme
art+tidspunkt+lokalitet (flere individer registrert hver for seg).

**Anbefaling: markør i «Privat kommentar».** Feltet sendes i dag alltid tomt
(`ao_import.py:122`, `'',  # Privat kommentar`) og er kun synlig for deg selv på AO. Foreslått
mekanikk:

- Bare for observasjoner som faktisk har et vedlagt bilde: sett `Privat kommentar` til en kort
  unik markør, f.eks. `#pic-a1b2c3d4`.
- Etter at import er ferdig parset, hent `review_queue_rows()` og match rad ⇄ lokal obs ved å
  finne markøren i `PrivateCommentLong`. Eksakt strengmatch — ingen tvetydighet, i motsetning
  til matching på art/dato/sted.
- Markøren **fjernes ikke** etterpå. Å redigere den bort krever et 149-felts
  skjema-round-trip (`ao-rediger-api.md`) — en risiko `rediger-sendte-obs-plan.md` eksplisitt
  utsatte (fase C). Markøren er privat og ufarlig å la stå; kan nevnes i `help.html`.
- Observasjoner uten bilde påvirkes ikke i det hele tatt — ingen markør, ingen
  opplastingsforsøk, dagens oppførsel uendret.

Dette er en avveining (litt støy i et kommentarfelt, mot en trygg og billig matching) som bør
besluttes eksplisitt — se spørsmål til bruker nederst.

*Alternativ uten markør (ikke anbefalt):* match på `TaxonName` + `SearchableStartDate` +
`TimePresentation` + `SiteOrParentSiteId`, dropp bildet ved tvetydig treff. Tryggere for
kommentarfeltet, men lar ekte felt-scenarioer (to individer, samme art og minutt, samme sted)
systematisk mislykkes — akkurat den situasjonen fase B ble skrevet for å unngå å gjette på.

## 3. Hvor i flyten skjer opplastingen

Nytt steg satt inn i `post_with_curl()` (`ao_import_httpx.py`), mellom dagens `importing` og
`publishing`:

```
ParseObservations → poll til ferdig  → review_queue_rows() → match → last opp bilder → PublishAll
     "importing"                              (nytt: "uploading-images")      "publishing"
```

Vi utsetter altså publisering til bildeopplastingsforsøkene er unnagjort — nøyaktig det
vinduet AO selv bruker (`PossibleToUploadImages` er kun `true` mens raden ligger i køen).

**Feilhåndtering — bildet skal aldri kunne stoppe selve observasjonen:**

- Bildeopplasting er best-effort per observasjon: 1 retry ved nettverksfeil, så gi opp.
- Publisering skjer uansett, med eller uten vedlagte bilder.
- Resultatet fra `post_with_curl()` utvides med `imagesFailed: [...]` (hvilke lokale obs sitt
  bilde ikke kom med) slik at frontend kan vise en tydelig, ikke-blokkerende advarsel — samme
  mønster som `heldBack` i dag.

## 4. Arkitektur — server-side, som resten av integrasjonen

Bilder skal **ikke** lastes opp direkte fra nettleseren til AO. Hele direktesendingen kjører
i dag server-side med `httpx` (nettleseren ser aldri `artsobservasjoner.no`) — det er bevisst,
og gir oss server-holdt CSRF/cookie-håndtering på ett sted. Bilder bør følge samme mønster:

1. **Frontend:** bilde velges/tas, nedskaleres klientsidig (se pkt. 6), legges på
   observasjonen som base64 (`obs.photo = "data:image/jpeg;base64,..."`).
2. **Transport:** samme JSON-body som i dag går til `/api/ao-import-stream`
   (`{observations, loginToken, authCookie, areaId}`) — ingen ny endepunkt-type nødvendig,
   bare et nytt felt per observasjon.
3. **Backend:** `post_with_curl()` gjør selve multipart-POST-en til AO med `httpx`, med
   `login_token`/`auth_cookie` den allerede har.

Konsekvens å være obs på: base64 i JSON-body øker payload med ~33 %. For mobil på dårlig
dekning (appens primære brukssituasjon) bør nedskalering (pkt. 6) gjøre dette uproblematisk —
et 1600px JPEG er typisk 150–400 KB, altså 200–550 KB som base64. Flere bilder i samme batch
kan bli merkbart — vurder å begrense til **1 bilde per observasjon i v1** (se pkt. 7).

## 5. Gjenbruk av eksisterende «sendt-logg»

`sent_observations_v1` (`storage.js`, fase B i `rediger-sendte-obs-plan.md`) har allerede et
**ubrukt** `aoIds`-felt i skjemaet sitt (`{ ts, siteName, siteId, count, aoIds: [...] | null,
obs: [...] }`) — reservert nettopp for dette scenarioet, men droppet den gang fordi det ikke
fantes noen god grunn til å ha AO-IDen (ingen dyplenking mulig, jf. `ao-rediger-api.md`).

Nå finnes en konkret grunn: hvis et bilde feiler å laste opp, kan `sendt.html` tilby
**«Prøv å laste opp bilde på nytt»** for akkurat den observasjonen — som krever nettopp
`SightingId`. Dette gjenåpner `aoIds`-feltet med et reelt formål, uten å gjenåpne
dyplenkingsspørsmålet (som fortsatt ikke er mulig — `EditPublishedSightings` er en `POST`,
ikke en URL).

## 6. Frontend — skisse (detaljeres i egen implementasjonsplan)

- **Ett bilde per observasjon i v1** (se pkt. 7 for begrunnelse). Knapp/kamera-ikon per rad i
  arbeidslisten (③), med forhåndsvisning og mulighet til å fjerne før sending.
- **Nedskalering før lagring**, ikke bare før sending: mobilkamera leverer ofte 3–10 MB
  HEIC/JPEG. Skaler til maks ~1600 px langside, JPEG-kvalitet ~0.8, via `<canvas>`, før bildet
  i det hele tatt legges i lokal lagring. HEIC-støtte i `<canvas>` er usikker på tvers av
  nettlesere — bør sjekkes tidlig, kan kreve fallback/feilmelding for HEIC.
- **Lagring: IndexedDB, ikke `localStorage`.** `localStorage` har typisk 5–10 MB total kvote
  delt med alt annet appen lagrer (arbeidsliste, sendt-logg, innstillinger) — selv nedskalerte
  bilder sprenger det fort med noen få observasjoner. Observasjonen refererer til bildet med
  en nøkkel (`obs.photoRef`), ikke selve dataen.
- `observations_to_csv()` endres minimalt: privat kommentar-feltet settes til markøren
  **kun** når `obs.photoRef` finnes — ellers uendret (`ao_import.py:122`).

## 7. Omfangsbegrensning for v1 (anbefalt)

| Valg | Anbefaling | Begrunnelse |
|------|-----------|-------------|
| Bilder per observasjon | **1** | AO støtter flere, men UI + lagring + feilhåndtering dobles for lite gevinst i v1. Kan utvides senere uten brudd i matching-mekanikken. |
| Hvor i flyten | Kun ved direktesending (`/api/ao-import-stream`) | CSV-eksport («Kopier og åpne AO») går utenom serveren vår — bilder der må evt. håndteres helt separat (brukeren laster opp selv på AO), ikke i scope her. |
| Retry ved feil | Best-effort, 1 retry, aldri blokkerende | Konsistent med `heldBack`-mønsteret; et bilde er et tillegg, ikke en forutsetning for en gyldig observasjon. |
| Redigering av allerede sendte bilder | Ikke i v1 | Hører naturlig til fase C-diskusjonen i `rediger-sendte-obs-plan.md` (in-app AO-redigering), bevisst utsatt der. |

## 8. Risiko

- **Uverifisert endepunkt.** Selve opplastings-URL-en er ikke sett i praksis (kun utledet fra
  minifisert klient-JS). All koding stopper til fase 0 er fullført med en ekte fangst.
- **Skriver til AO under et tidspress-vindu.** Opplasting må skje mens raden er i
  gjennomgangskøen — hvis AO endrer dette vinduet (f.eks. strammer inn når
  `PossibleToUploadImages` er sann), stopper funksjonen å virke uten varsel. Samme
  vedlikeholdsrisiko som resten av `ao_import_httpx.py` (ett AO-`ReleaseNumber`-bump kan endre
  skjema/felt).
- **Feil bilde på feil funn** ved en matching-bug er den alvorligste feilklassen — permanent,
  offentlig, og feil handler om AOs nasjonale artsdatabase. Markør-strategien (pkt. 2) er valgt
  nettopp for å gjøre denne risikoen strengt lavere enn innholdsbasert matching, men er ikke
  null — behandle med samme forsiktighet som fase C-vurderingen i `rediger-sendte-obs-plan.md`.
- **Timing før BirdLife-lansering.** Prosjektets uttalte prioritet nå er nybegynnerfokus og
  stabilitet (`project_birdlife_launch`-notat). Bildeopplasting er en ekte, etterspurt
  funksjon, men også ny skriveflate mot AO i en allerede skjør integrasjon — vurder om dette
  bør vente til rett etter lansering, ikke rett før.

## 9. Faser

### Fase 0 — Fullfør API-fangsten (forutsetning, ingen produktkode)
Se «Oppskrift for ny fangst» i `docs/ao-bilder-api.md`. Må gi: opplastings-URL, metode,
feltnavn, CSRF-krav, filstørrelsesgrense, og bekreftelse på at CSV-importerte rader (ikke bare
AOs eget ett-funn-skjema) også får `PossibleToUploadImages: true` i køen.

### Fase A — Backend: opplasting + matching, ingen UI
`upload_image(sighting_id, image_bytes, filename, login_token, auth_cookie)` i
`ao_import_httpx.py`, markør-matching via `review_queue_rows()`, nytt SSE-steg
`uploading-images`. Testbart isolert mot en ekte (men ufarlig) testobservasjon, uten at
frontend er rørt ennå.

### Fase B — Frontend: velg og send bilde
Kamera/filvalg per obs i arbeidslisten, nedskalering, IndexedDB-lagring, `photoRef` i
observasjonsobjektet, base64 i sendingen. `handleDirectSend`/`export-operations.js` utvides
med et nytt fremdriftssteg («Laster opp bilder …») mellom «Behandler …» og «Publiserer …».

### Fase C — Robusthet
`aoIds` fylles i `sent_observations_v1` for observasjoner der bilde ble forsøkt.
`sendt.html` viser «🖼️ bilde ikke lastet opp — prøv igjen» der `imagesFailed` traff, med
retry mot lagret `SightingId`.

## 11. Implementert (POC, 2026-08-03)

Bygget som en rask proof-of-concept for å verifisere at hele kjeden faktisk fungerer, **ikke**
en ferdig, herdet v1. Kjetil valgte selv plassering (endre-modalen) og lagring
(localStorage, ikke IndexedDB) i denne runden.

**Backend (`src/ao_import_httpx.py`):**
- `upload_image()` — ekte `multipart/form-data`-POST til `/Media/UploadImageAction` med
  CSRF hentet fra `/ReviewSighting` (ny helper `_fetch_review_csrf`).
- `_upload_pending_images()` — matcher observasjoner med `obs.photo` mot rader i
  `review_queue_rows()` via markøren i `PrivateCommentLong`, laster opp, best-effort
  (feil på ett bilde stopper aldri publisering). Kalles fra `post_with_curl()` mellom
  «importing» og «publishing», med eget SSE-steg `uploading-images`.
- `_decode_data_url()` / `_obs_label()` — små hjelpefunksjoner.
- **Lisens hardkodet til `10` (CC BY)** — AOs egen default. Ikke gjort valgbart i UI ennå;
  se punkt 3 under.
- `src/ao_import.py`: `_photoMarker` skrives til «Privat kommentar»-kolonnen når satt,
  ellers uendret (tom streng som før).
- 6 nye pytest-tester i `tests/test_ao_import.py` (markør i CSV, matching, best-effort
  feilhåndtering, no-op uten bilde, `_decode_data_url`). Alle 176 tester i suiten passerer.

**Frontend:**
- `public/edit.html` — filvelger, klientsidig nedskalering til maks 1600px/JPEG q=0.85
  (`<canvas>`), forhåndsvisning, fjern-knapp. Lagrer som `obs.photo` (data-URL) i
  **`localStorage`** sammen med resten av observasjonen — bevisst forenkling for POC-en,
  se punkt 2/3 under for hva dette betyr i praksis.
- `public/js/export-operations.js` — viser `uploading-images`-steget i fremdriftslinja,
  og en advarsel i sluttmeldingen hvis `imagesFailed` er ikke-tom. Sendt-loggen
  (`appendSentBatch`) dupliserer **ikke** bilde-base64en — kun et `hadPhoto: true`-flagg.

**Ikke gjort ennå (bevisst utelatt fra POC-en):**
1. **Aldri testet mot ekte AO.** `upload_image()`/matchingen er verifisert med mocks
   (pytest), ikke med et reelt `httpx`-kall mot artsobservasjoner.no. Første ekte test bør
   gjøres av Kjetil selv, med en observasjon han uansett skulle rapportert — se
   testoppskrift under.
2. **`localStorage`, ikke IndexedDB** — pkt. 6 i planen advarte om nettopp dette
   (kvote delt med resten av appens lagring). Ufarlig med ett testbilde, men bør byttes før
   dette skal brukes med flere observasjoner/bilder samtidig.
3. **`MediaLicense` er ikke valgbar** — alle bilder sendes som CC BY. Er det riktig
   standardvalg for Kjetils bilder, eller bør brukeren få velge (jf. tabellen i
   `docs/ao-bilder-api.md`)?
4. **`aoIds`/retry i `sendt.html`** (punkt 5) — ikke bygget. `imagesFailed` vises bare i
   selve sendemeldingen, ingen senere retry-mulighet ennå.
5. **CSV-eksport / «Kopier og åpne AO»** — uendret, som planlagt (punkt 7). Bilde følger
   bare med ved direktesending.

### Manuell testoppskrift (må gjøres av Kjetil — skriver til ekte AO)

1. Bruk en ekte observasjon du uansett skulle rapportert.
2. Legg til et bilde via «Rediger» (blyantikonet) i arbeidslista.
3. «Publiser til AO» som vanlig — se etter det nye «Laster opp bilder …»-steget i
   fremdriftslinja.
4. Sjekk på artsobservasjoner.no (Mine funn) at bildet faktisk havnet på riktig funn — ikke
   bare at det ble «sendt».
5. Rydd opp testfunnet/bildet på AO etterpå, som i tidligere testrunder.

## 10. Neste steg

1. Gjennomfør fangsten i `docs/ao-bilder-api.md` (kun DevTools + en ekte, ufarlig
   testobservasjon — ingen kode).
2. Oppdater `ao-bilder-api.md` med funnene, fjern «ikke bekreftet»-punktene som blir avklart.
3. Ta stilling til avveiningen i pkt. 2 (privat-kommentar-markør) og omfangsbegrensningene i
   pkt. 7 — begge er reelle valg, ikke bare implementasjonsdetaljer.
4. Kjør fase A + B via `/agent-feature-lifecycle` når fase 0 er grønn.
