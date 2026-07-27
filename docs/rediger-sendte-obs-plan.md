# Rette observasjoner etter sending til AO — vurdering og plan

**Dato:** 2026-07-27
**Status:** Fase 0 ferdig (se `ao-rediger-api.md`). **Fase B implementert i v1.41.0**
(27.07.2026). **Fase C besluttet utsatt til etter BirdLife-lanseringen** (27.07.2026) —
fase A er neste.
**Bakgrunn:** Brukeren sender observasjoner til Artsobservasjoner (direktesending), oppdager
etterpå at noe er feil (art, antall, aktivitet, lokalitet, tid) — og appen har ingen vei tilbake.

---

## 1. Produkteier-vurdering

### Problemet, slik det faktisk er

Det er ikke *umulig* å rette en publisert observasjon — det går fint på
artsobservasjoner.no («Mine funn»). Problemet er at:

1. **Appen glemmer alt.** Etter vellykket sending tilbys brukeren å tømme lista
   (`export-operations.js:194`), og da finnes det ingen spor av hva som ble sendt. Man må
   rekonstruere fra hukommelsen hva man skal lete etter på AO.
2. **Det finnes ingen bekreftelse før sending.** `handleDirectSend` sender umiddelbart ved
   trykk (`main.js:378`) — ingen «du sender N obs på lokalitet X»-kvittering. Dette er
   selve mekanismen bak «altfor ivrig».
3. **AO er tungt på mobil for en nybegynner.** Med BirdLife-lansering som kontekst er
   målgruppen folk som ikke kjenner AO-grensesnittet fra før.

Så det egentlige behovet er todelt: **færre feil sendes** og **kort vei fra «huff» til
retting**. Full redigering inne i appen er én mulig løsning på del to — ikke den eneste.

### Verdi

| Del | Verdi | Begrunnelse |
|-----|-------|-------------|
| Bekreftelse før sending | **Høy** | Berører kjerneflyten, forebygger problemet i stedet for å reparere |
| «Sendt til AO»-logg + lenke til retting | **Høy** | Løser «hva sendte jeg egentlig?» og gir kort vei til AO |
| Full in-app redigering mot AO | **Middels** | Gir bekvemmelighet, men AO kan allerede dette |
| Sletting av publisert obs fra appen | **Lav** | Sjelden, høy skade ved feil, AO gjør det trygt |

### Kostnad og risiko

Full in-app redigering er den dyreste og farligste delen:

- **Ingen kjent API.** All AO-integrasjon er reverse-engineerte ASP.NET MVC-skjemaer med
  antiforgery-tokens (`ao_import_httpx.py`). Redigering krever å hente hele
  skjemamodellen for én observasjon, endre ett felt, og poste *alt* tilbake. Et skjult
  felt vi ikke reproduserer blir tomt i den nasjonale artsdatabasen.
- **Vi vet ikke engang hvilken obs vi sendte.** Publiseringen skjer med tom
  `SightingsToPublishIds` (= publiser alt, `ao_import_httpx.py:366`); vi fanger ingen
  AO-ID. Uten ID kan vi ikke redigere en spesifikk observasjon i det hele tatt.
- **Skaden er permanent og offentlig.** AO-data flyter videre til GBIF/forskning. En bug
  i importflyten gir en feil obs; en bug i redigeringsflyten kan stille ødelegge en
  eksisterende, riktig obs.
- **Vedlikeholdsrisiko.** AO bumper `ReleaseNumber` jevnlig; skjemaendringer treffer oss
  uten varsel. Én utvikler.

### Alternativer

0. **Gjøre ingenting.** Brukeren retter på AO. Godt nok for erfarne brukere, dårlig for
   nybegynnere som ikke husker hva som ble sendt.
1. **Forebygg + finn igjen** (fase A + B under). Dekker mesteparten av smerten, skriver
   aldri til AO, null risiko for datakvalitet.
2. **Full in-app redigering** (fase C). Størst bekvemmelighet, klart høyest risiko og
   vedlikeholdskostnad.

### Anbefaling

**FORENK — bygg fase A og B nå, utsett fase C bak en verifiseringsport.**

Begrunnelse: mesteparten av den opplevde smerten er at appen glemmer hva som ble sendt og
sender uten å spørre — begge deler kan fikses lokalt, uten å skrive ett byte til AO. Full
redigering løser et problem AO allerede løser, mot en risiko (stille ødeleggelse av
publiserte data) som er den dyreste feilen dette prosjektet kan gjøre.

**Prioritet:** fase A + B før BirdLife-lansering. Fase C i backlog, betinget av fase 0.

**Revisjonspunkt for fase C:** bygges hvis (a) fase 0 bekrefter at vi kan fange AO-ID og
gjøre en trygg skjema-round-trip, og (b) tilbakemeldingskanalen faktisk viser at brukere
ber om det etter at fase A+B er ute.

---

## 2. Plan

### Fase 0 — Verifisering mot AO via HAR-fangst (ingen produktkode)

Oppskrift: **`docs/ao-rediger-capture.md`**. Samme mønster som `ao-progress-capture.md`,
som fungerte godt for importfremdriften.

**Sterk indikasjon på at sighting-ID finnes:** `PublishAll` poster
`ReviewSightingViewModel.SightingsToPublishIds=` (tom = publiser alt,
`ao_import_httpx.py:366`). Det feltet gir bare mening hvis kontrollvinduet rendrer en ID
per rad — ellers kunne man aldri publisere et utvalg. Så ID-ene er nesten sikkert der;
det som må bekreftes er (a) hvor de står i HTML-en, og (b) om ID-en overlever
publiseringen uendret.

Spørsmål som skal besvares:

1. Hvordan lister AO mine egne siste funn — finnes en ren JSON-lesing (Kendo-grid har ofte
   et `…/Read`-POST), eller må HTML skrapes?
2. Hvilken URL redigerer én publisert observasjon, og hvilken ID står i den?
3. Hele skjemamodellen: hva hentes ved GET, hva POSTes ved lagring?
4. Er ID-en i kontrollvinduet den samme som i redigerings-URL-en etter publisering?

**Utfall styrer fase B:**
- Ren JSON-lesing av egne funn finnes → **hent fra AO** (autoritativt, dekker også obser
  registrert utenom appen, tåler bytte av telefon).
- Bare HTML-skraping → **lokal logg** som primærkilde, AO-lenke som utgang.
- ID overlever ikke publisering → lokal logg må matche på innhold i etterkant, eller
  droppe dyplenking.

Dokumenteres i `docs/ao-rediger-api.md` (samme mønster som `ao-lokalitet-api.md`).

### Fase A — Bekreftelse før sending ❌ (droppet 27.07.2026)

**Beslutning: ikke bygget.** Begrunnelsen for fase A var å fange «altfor ivrig»-feilen, men
den feilen var ikke et bomtrykk — brukeren sendte bevisst, med feil data. Den konkrete
feilen vi observerte (tårnseiler med tidspunkt frem i tid) fanges nå av automatisk
validering i tre ledd pluss en siste kontroll før sending, og det er strengt bedre enn å be
et menneske se etter selv. «Er du sikker?»-dialoger blir dessuten klikket bort uten lesing
etter tredje gang, og publiser-knappen ligger i seksjon ④, langt fra registreringsflyten.

Det eneste den ville fanget som automatikken ikke gjør, er **feil lokalitet** — ingen regel
kan vite at brukeren egentlig var et annet sted. Men lokaliteten står allerede i lista.

**Hvis det viser seg å bli et problem:** vis opplysningen uten å blokkere — en linje ved
knappen («7 obs · Lønningen · 26. juli») som leses i forbifarten. Informasjonen, ikke
dialogen.

Opprinnelig skisse, beholdt for ettertiden:

Minimal endring i `handleDirectSend`: en oppsummering før noe sendes.

- «Send N observasjoner fra *lokalitet* til Artsobservasjoner?» med lokalitetsnavn og
  dato, slik at feil lokalitet/dato fanges før den blir permanent.
- Kan slås av i innstillinger for de som synes det er i veien (`localStorage`).

Akseptansekriterier:
1. Trykk på «Publiser til AO» sender ikke før brukeren bekrefter.
2. Dialogen viser antall, lokalitetsnavn og dato for det som sendes.
3. Avbryt lar lista stå urørt; ingen kall mot AO er gjort.
4. Med bekreftelse avslått i innstillinger er dagens oppførsel uendret.

Estimat: ~2 timer.

### Fase B — «Sendt til AO»-logg med rett-lenke ✅ (v1.41.0)

Appen husker hva som ble sendt, og gir kort vei til retting på AO. **Skriver aldri til AO.**

**Data:** ny `localStorage`-nøkkel `sent_observations_v1`:

```js
{ version: 1, batches: [ { ts, siteName, siteId, count, aoIds: [...] | null, obs: [ ... ] } ] }
```

Rullering: behold 7 dager, maks ~200 observasjoner. Quota-feil håndteres som i
`saveObservations` (advarsel, ikke krasj). *48 timer ble vurdert, men en feil oppdages
ofte når man ser gjennom uka — lagringskostnaden er den samme.*

**Flyt:** ved `phase === 'done'` skrives batchen til sendt-loggen *før* brukeren får
tilbud om å tømme lista. Fanges AO-ID-er i fase 0, tas de med.

**Forutsetning (fikset 27.07.2026):** sendt-loggen er bare sann hvis «sendt» faktisk betyr
«publisert». Fram til nå meldte appen suksess også når AO holdt rader tilbake — se
«Funnet underveis» nederst. En tilbakeholdt observasjon finnes ikke som publisert funn og
skal ikke inn i sendt-loggen som om den gjorde det.

**Fallgruve ved ID-fangst:** `PublishAll` publiserer *alt* i review-køen, også funn som lå
der fra før (`ao-progress-capture.md`). Kontrollvinduet inneholder altså ikke nødvendigvis
bare våre rader. ID-er må derfor matches mot våre observasjoner på innhold (art + antall +
dato + lokalitet) — og ved tvetydig match lagres **ingen** ID heller enn feil ID. En feil
ID betyr i fase C at vi redigerer feil observasjon.

**Implementert annerledes enn planlagt — dyplenking er ikke mulig.** HAR-fangsten viste at
redigering åpnes med `POST /ReviewSighting/EditPublishedSightings` (CSRF-token + skjemafelt
fra feltdagboka), ikke en GET-URL. En `<a href>` rett til én observasjon finnes altså ikke.
Sendt-loggen lenker derfor til `/User/MyPages`, og ID-fangst er droppet i denne fasen —
uten en URL å bruke ID-en i gir den ingen verdi ennå. Den blir aktuell igjen i fase C.

**Kilde-valg (avgjøres av fase 0):** hvis AO tilbyr en ren lesing av egne siste funn, er
den autoritativ og bør være primærkilden — den dekker også obser registrert i AO-appen
eller på web, og overlever bytte av telefon. Den lokale loggen beholdes uansett som
fallback: den virker offline, uten innlogging, og uten at AO må svare.

**UI:** ny side (`sendt.html`, samme lettvekts-mønster som `medobs.html`/`edit.html`),
gruppert på dato + lokalitet. Per observasjon: art, antall, tid, aktivitet, og
- **«Rett på AO»** → åpner AO i ny fane, på observasjonen hvis vi har ID, ellers «Mine funn».
- **«Kopier som ny»** → legger obsen tilbake i arbeidslista som *ny* registrering
  (nyttig når feilen er så grov at obsen bør slettes på AO og registreres på nytt).

Akseptansekriterier:
1. Etter vellykket sending finnes batchen i sendt-loggen med dato, lokalitet og antall —
   også etter refresh og etter at appen er lukket.
2. Sendt-loggen overlever både «tøm lista» etter sending og «Slett alle».
3. «Rett på AO» åpner AO i ny fane; med kjent ID lander man på observasjonen.
4. Ingenting på sendt-siden kan sende til AO på nytt (ingen dobbeltsending).
5. Poster eldre enn 30 dager, eller over 200 obs, ryddes automatisk ved lasting.
6. Full `localStorage` gir advarsel i konsollen, ikke ødelagt app eller tapt arbeidsliste.
7. Sendt-loggen er lokal per enhet — dokumenteres i `help.html` så forventningen er riktig.

Estimat: ~1 dag. Avgrenset: **kun direktesending logges** i v1 (CSV-eksport og
kopier-og-åpne vet vi ikke utfallet av).

### Fase C — Redigering i appen (utsatt til etter lansering, besluttet 27.07.2026)

**Beslutning:** fase 0 ga teknisk grønt lys — det *er* mulig — men prisen ble bekreftet
høyere enn antatt (149 felt i `Save`, ingen GET-URL, funnet må publiseres på nytt).
Utsatt fordi:

1. Fase C er det eneste i backloggen der en bug ødelegger data hos andre. Alt annet
   skriver til localStorage eller egen SQLite; dette skriver inn i den nasjonale
   artsdatabasen, og derfra videre til GBIF. Feil rekkefølge rett før en lansering rettet
   mot nybegynnere, der stabilitet er hovedkravet.
2. AO løser allerede redigering. Den faktiske smerten — at appen glemte hva som ble sendt
   — er borte med fase B.
3. Tilbakemeldingskanalen (v1.39.0) har ikke mottatt ett eneste ønske om redigering.

**Revisjonspunkt:** tas opp igjen når brukere ber om det, eller etter lansering.

**Første milepæl når den bygges: en no-op round-trip.** Hent skjemaet for én obs, parse
alle 149 felt, post dem tilbake *uendret*, og verifiser at observasjonen er identisk
etterpå. Klarer vi ikke det, klarer vi ikke å redigere trygt heller — og da vet vi det
uten å ha ødelagt noe.

Resten av skissen, ikke bestilling:

- **Én observasjon om gangen. Aldri batch.**
- **Full round-trip:** GET redigeringsskjemaet for obsen → parse alle felt → endre kun det
  brukeren rørte → POST alt tilbake uendret ellers.
- **Fail-safe ved ukjent skjema:** finner parseren felt vi ikke kan reprodusere, avbrytes
  redigeringen med fallback til «Rett på AO». Vi gjetter aldri på et skjemafelt.
- **Diff-bekreftelse:** «Antall: 2 → 3» vises og må bekreftes før POST.
- **Ingen sletting fra appen** i første versjon — sletting sender brukeren til AO.
- **Tester:** mot mock som simulerer AO-skjemaet (`mock/`-mønsteret). Aldri automatiserte
  tester mot ekte AO.
- Ny modul `src/ao_edit.py` + endepunkter `/api/ao-sighting` (GET) og `/api/ao-sighting-update`
  (POST), samme token-/innloggingsmønster som `ao-import`.

Estimat: 2–4 dager, pluss løpende vedlikehold hver gang AO endrer skjemaet.

---

## Funnet underveis (27.07.2026) — appen meldte suksess på funn AO ikke publiserte

En etterregistrert tårnseiler fikk tidspunkt 15:00 *i dag* i stedet for i går. AO
underkjente den («Angi et tidspunkt som ikke er passert») og lot raden bli liggende i
gjennomgangskøen — mens enkel-ao viste grønn «✅ sendt til AO!».

To hull, begge tettet:

1. **Ingen verifisering etter publisering.** `publish_all` sjekket bare at `PublishAll`
   svarte < 400, og returnerte så `count = len(observations)`. AO publiserer ikke rader den
   underkjenner; de blir liggende. Nå polles `NumberOfSightingsSubmitted` etter
   publisering (`_remaining_after_publish`), og gjenværende rader rapporteres som
   `heldBack` → frontend viser gul advarsel med lenke til gjennomgang i stedet for hake.
2. **Validering fantes bare ved registrering.** `observation-commit.js:114–123` blokkerer
   tidspunkt frem i tid, men `edit.html` skrev dato/tid rett til localStorage uten sjekk.
   Nå validerer edit.html etter samme regel, og `handleDirectSend` gjør en siste kontroll
   av hele lista før sending — uansett hvordan tidspunktet kom inn.
3. **Gruppe-klokkeslett validerte feil dato.** «Sett klokkeslett» på en gruppe validerte
   mot `groupItems[0]` sin dato, men skrev klokkeslettet på *hver* obs sin egen dato
   (`observations.js`). Spente gruppen over flere datoer, kunne en obs med dagens dato få
   et tidspunkt frem i tid uten at valideringen så det. Nå beregnes resultatet for alle
   obser først, og hele operasjonen avbrytes hvis én av dem havner frem i tid.

Merk for fase B: `PublishAll` publiserer hele køen, så en tilbakeholdt rad blir liggende og
forstyrrer både `pending_count`-sjekken og ID-matchingen ved neste sending.

## 3. Neste steg

1. Kjør fase 0 og skriv `docs/ao-rediger-api.md`.
2. Fase A + B via `/agent-feature-lifecycle`.
3. Ta stilling til fase C når fase 0 og brukertilbakemeldinger foreligger.
