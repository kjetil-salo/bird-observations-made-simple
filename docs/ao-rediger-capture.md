# Capture-sesjon: AO redigering av publisert observasjon

**Mål:** Kartlegge to ting vi ikke kan gjette oss til:

1. **Hvordan lister AO opp mine egne siste funn?** (Er det en ren JSON-lesing vi kan kalle,
   eller HTML som må skrapes?) → avgjør om appen skal speile lokalt eller hente fra AO.
2. **Hvordan redigeres én publisert observasjon?** URL med sighting-ID, hele skjemamodellen
   som hentes, og nøyaktig hva som POSTes ved lagring.

Samme mønster som `ao-progress-capture.md`, som fungerte godt.

## Forberedelse
- [ ] Bruk **Chrome** (best HAR-eksport) eller Firefox.
- [ ] Logg inn på artsobservasjoner.no som vanlig.
- [ ] Ha en **ekte observasjon du uansett skulle rapportert** klar til del 3 — da havner
      ingen søppeldata i den nasjonale databasen.

## DevTools-oppsett
- [ ] **F12 → Network**.
- [ ] Huk av **«Preserve log»** ✅ (sidene redirecter — ellers mistes trafikk).
- [ ] Huk av **«Disable cache»** ✅.
- [ ] Filter på **«All»** — ikke bare Fetch/XHR.
- [ ] Tøm loggen (🚫) rett før du begynner.

---

## Del 1 — Mine siste funn (lesing)
- [ ] Naviger til der du ser dine egne siste observasjoner («Mine funn» / «Mine sider» /
      månedsliste — den du selv ville brukt for å finne igjen noe du sendte i går).
- [ ] La lista laste ferdig.
- [ ] Bla til side 2 hvis det finnes paginering (viser hvordan lesingen parametriseres).

Noter:
- [ ] Nøyaktig hvilken meny/lenke du klikket: ______________________________
- [ ] Kan du filtrere på dato/periode i UI-et? ☐ ja ☐ nei

## Del 2 — Rediger en eksisterende observasjon
- [ ] Finn en av dine egne **allerede publiserte** observasjoner.
- [ ] Klikk deg inn på redigering av den.
- [ ] Endre noe helt ufarlig — f.eks. legg til en prikk i kommentarfeltet.
- [ ] **Lagre.**
- [ ] (Rydd opp etterpå: fjern prikken igjen, gjerne i en ny runde.)

Noter:
- [ ] URL-en i adresselinja mens du redigerer: ______________________________
      (Den inneholder trolig sighting-ID-en — det er nummeret vi er ute etter.)

## Del 3 (valgfritt, men avgjørende for det lokale alternativet)

Dette svarer på spørsmålet: **er ID-en fra kontrollvinduet den samme etterpå?**

> ⚠️ **Bruk «Kopier og åpne AO», ikke «Publiser til AO».** Direktesendingen kjøres
> server-side med httpx (`ao_import_httpx.py`) — nettleseren din ser aldri
> `ImportSighting`/`ReviewSighting`, så kontrollvinduet havner ikke i HAR-en. «Kopier og
> åpne AO» (`export-operations.js:88`) åpner importsiden i nettleseren, og da fanges alt.
> *Alternativ hvis du heller vil bruke direktesending: dump `ReviewSighting`-HTML-en
> server-side under en ekte sending (utvid debug-loggingen på `ao_import_httpx.py:337`).*

- [ ] Sjekk at gjennomgangskøen er **tom** før du starter — gamle funn gjør det uklart
      hvilke rader som er dine nye.
- [ ] Registrer **2–3 ekte observasjoner** i enkel-ao (én rad er ikke nok: da ser vi ikke
      om ID-ene er distinkte per rad, og det er akkurat det matchingen vår avhenger av).
- [ ] Trykk **«Kopier og åpne AO»** → lim inn på importsiden → importer.
- [ ] **Stopp i kontrollvinduet** (gjennomgang) før publisering.
- [ ] Høyreklikk en rad → **Inspiser**. Ser du et tall-ID på raden (`data-uid`, `id`,
      en checkbox med `value="..."`)? Noter ID-ene og hvilken art de hører til:

      ____________________________________________

- [ ] Publiser.
- [ ] Finn de samme observasjonene under Mine funn og gå til redigering.
- [ ] Er ID-en i URL-en **den samme** som i kontrollvinduet? ☐ ja ☐ nei ☐ vet ikke

Svaret her avgjør om appen kan koble sendte obser til AO-ID med én gang de sendes,
eller om den må slå dem opp i etterkant.

## Del 4 (valgfritt) — Sletting
Skal du likevel rydde bort en testobservasjon: gjør det med DevTools fortsatt på, så får
vi slette-endepunktet dokumentert på kjøpet. (Sletting fra appen er ikke planlagt, men det
er nyttig å vite hvordan det ser ut.)

## Eksport
- [ ] Høyreklikk i Network-lista → **«Save all as HAR with content»**.
- [ ] Gi Claude **stien** til HAR-fila.

## Sikkerhet
HAR-fila inneholder **cookies + tokens** (`.ASPXAUTHNO`, `logintoken`, CSRF) og alt
innhold på sidene du besøkte. Den blir liggende **lokalt** — deles ingensteds. For
analysen trengs URL-er, feltnavn og respons-struktur, *ikke* de faktiske cookie-verdiene.
- [ ] (Valgfritt) Søk/erstatt cookie-verdiene i HAR-en før deling — behold feltnavnene.
- [ ] (Valgfritt) Bytt AO-passord etterpå.

---

## Funn

_(fylles ut etter analyse — deretter oppsummeres API-et i `docs/ao-rediger-api.md`)_
