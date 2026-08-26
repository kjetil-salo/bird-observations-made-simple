# Besøk og «↩ tilbake til besøket»

Hvordan observasjoner grupperes i besøk, og hva som skjer med klokkeslettet når
man går tilbake til et besøk man allerede har forlatt.

Innført i v1.44.0 (knappen), omdefinert i v1.45.0–v1.45.1 (betydning og tid).

## Begrepet besøk

Et **besøk** er én runde på én lokalitet. Hver gruppe i ③ Observasjoner er ett
besøk. Går man Tovo → Kvitingen → Tovo igjen, kan det bli tre grupper.

Besøket identifiseres av `visitId` på hver observasjon (`public/js/visits.js`):

```
visit:<stedsnøkkel>:<opprettet-ms>:<tilfeldig>
```

Stedsnøkkelen er `id:<aoSiteId>` når lokaliteten er valgt fra AO, ellers
`name:<normalisert navn>`. Observasjoner fra før besøks-funksjonen mangler
`visitId`; de faller tilbake til nøkkelen `legacy:<stedsnøkkel>`, slik at én
lokalitet blir ett besøk. `getObservationVisitKey()` skjuler den forskjellen —
resten av koden skal aldri lese `obs.visitId` direkte.

En gruppe regnes som **låst** bare når *alle* observasjonene i den har
`visitLocked: true`. Det er verdt å huske: legger man en ulåst observasjon inn i
en låst gruppe, låser gruppa seg opp igjen. Se «arv av lås» under.

## De to måtene å registrere på samme sted

| Situasjon | Hva brukeren gjør | Resultat |
|---|---|---|
| Står på lokaliteten, registrerer videre | Ingenting spesielt | Havner i det åpne besøket, tid = **nå** |
| Er faktisk tilbake på lokaliteten senere | Velger lokaliteten i ① på vanlig måte (evt. 🔒 på det gamle først) | **Nytt** besøk, tid = **nå** |
| Husker en art fra et besøk man har forlatt | Trykker **↩** ved stedsnavnet i ③ | **Samme** besøk, tid = **besøkets tidsspenn** |

Det er hele poenget med skillet: 🔒 sier «dette besøket er ferdig», ↩ sier «jeg
skal inn i akkurat dette besøket igjen». Uten skillet hadde man ingen måte å si
«jeg glemte en art fra morgenrunden» på.

## Tidsregelen

Går man tilbake til et besøk med ↩, arver den nye observasjonen **besøkets
tidsspenn**:

- `timestamp` = tidligste `timestamp` i besøket
- `tilKlokkeslett` = seneste `tilKlokkeslett`/`timestamp` i besøket

Er besøket ett enkelt tidspunkt (fra = til), settes ingen `tilKlokkeslett`.
Regnestykket ligger i `getVisitTimeSpan()` og er det samme som
gruppeoverskrifta i ③ viser.

**Hvorfor spenn og ikke ett punkt:** man vet at arten ble sett i løpet av
besøket, ikke nøyaktig når. AO leser fra–til som observasjonsvinduet, så
spennet er den ærlige påstanden. Formen er dessuten allerede i bruk — 🕐 setter
nøyaktig fra/til på en hel gruppe, og det er fortsatt verktøyet for å justere
tidene i etterkant.

**Hvorfor ikke «nå»:** hopper man tilbake til Tovo kl. 19:45, ville gruppa blitt
17:09–19:45. Det påstår at man var på Tovo i to og en halv time. Dårligere data
enn å arve 17:09–17:18.

Sammenligning skjer på parset tid, ikke på streng: lista kan inneholde både
`2026-08-26T17:09:00` (fra `toLocalISOString`) og eldre UTC-strenger med `Z`,
og de sorterer ikke likt leksikografisk.

## Låst besøk

↩ virker også på et låst besøk. Låsen hindrer at nye observasjoner havner der
*automatisk*; ↩ er et eksplisitt valg om nettopp det, og skal vinne.

To ting følger av det:

1. **Arv av lås.** Den nye observasjonen får `visitLocked: true` fra besøket.
   Uten dette ville 🔒 flippet til 🔓 i det man registrerte, siden en gruppe
   regnes som låst bare når alle observasjonene i den er det.
2. **Lett advarsel.** Brukeren har selv sagt at besøket er avsluttet, så det
   skal ikke skje stille at klokka settes tilbake i tid. Ikke-blokkerende toast
   med gul ramme: «↩ Tovo — avsluttet besøk. Nye arter får kl. 17:09, tilbake i
   tid.» Bevisst ikke en `confirm()` — dette skal ikke stå i veien i felt.

## Implementasjon

| Fil | Ansvar |
|---|---|
| `public/js/visits.js` | `getVisitTimeSpan()`, `isVisitLocked()`, `visitExists()` |
| `public/js/observations.js` | ↩-knappen i gruppeoverskrifta; sender `CustomEvent` |
| `public/js/main.js` | Eier `appState.etterregVisitKey`; merket i lokasjonslinja |
| `public/js/observation-commit.js` | Selve tidsregelen ved registrering |

`observations.js` eier ikke `appState`, så knappen sender

```js
CustomEvent('obs:bruk-lokalitet', {
  detail: { placeName, placeId, visitKey, visitLocked }
})
```

på `document`. Lytteren i `main.js` setter `currentPlaceName`/`currentPlaceId`
**og `etterregVisitKey`**, kollapser ①, scroller til toppen og fokuserer
art-feltet.

Så lenge `etterregVisitKey` er satt, hopper `observation-commit.js` over
`resolveVisitIdForNewObservation()` og bruker nøkkelen direkte.

### Når etterregistreringen avsluttes

`avsluttEtterregistrering()` kalles fra alle andre måter å sette plass på —
GPS-dropdown, autocomplete, kartvalg, manuell skriving — og fra
`expandLocation()`. **«Bytt plass» er den synlige veien tilbake til
«nå»-registrering.** I tillegg nullstilles nøkkelen automatisk hvis besøket
ikke lenger finnes (slettede observasjoner, «tøm lista»); det håndteres i
`oppdaterEtterregMerke()`, som kjører ved hver rendring av lista.

### Synlighet

Tida skal aldri settes i det skjulte. Merket `#loc-pinned-visit` i den festede
lokasjonslinja viser hvilken tid man får så lenge man er i besøket:

- `↩ 17:09–17:18` — åpent besøk med tidsspenn
- `↩ 17:09` — besøket er ett enkelt tidspunkt
- `🔒 ↩ 17:09` — låst besøk

## Fallgruver

- **Fremtids-valideringen må kjøre etter overstyringen.** Den sjekker at
  fra/til ikke er frem i tid (AO underkjenner slike). Kjørte den før, ble
  ↩-registrering i etterregistreringsmodus avvist fordi *skjemaets* klokke sto
  frem i tid — for et tidspunkt som aldri kom til å bli lagret. Rettet i
  v1.45.1. Valider alltid verdiene som faktisk havner på observasjonen.
- **Ikonet er ikke en blyant.** ✏️ betyr «rediger denne observasjonen» på hver
  rad rett under, og ➕/➖ er antallsknappene. Tilbake-pila er det eneste tegnet
  i overskrifta uten en konkurrerende betydning.
- **`obs.position`** blir stående med posisjonen fra da observasjonen ble
  registrert, ikke lokalitetens. Feltet leses ikke noe sted i eksport eller
  deling, så det er harmløst — men ikke begynn å bruke det uten å håndtere
  dette.

## Testdekning

`tests/e2e_playwright/tests/bytt-lokalitet.spec.ts` (5 tester):

1. ↩ setter gruppens lokalitet som aktiv lokalitet
2. Åpent besøk: samme `visitId`, arvet tidsspenn, gruppa strekkes ikke til «nå»
3. Låst besøk: går inn i besøket, arver låsen, advarselen vises, fortsatt én gruppe
4. Etterregistreringsmodus: fremtidig klokke i skjemaet blokkerer ikke ↩-registrering
5. «Bytt plass» avslutter etterregistreringen — tilbake til «nå»

Artssøket er stubbet med `page.route`, så testene sier noe om tidsregelen og
ikke om AO er oppe.
