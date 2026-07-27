# AO: redigering av publisert observasjon

**Bekreftet 27.07.2026** via HAR-fangst (én obs redigert på artsobservasjoner.no).
Erstatter antakelsene i `ao-rediger-capture.md`.

## Kortversjon

Redigering av et publisert funn skjer i tre steg, og **funnet må publiseres på nytt
etterpå** — redigering trekker det tilbake til gjennomgangskøen.

```
POST /ReviewSighting/EditPublishedSightings   → redigeringsskjema (HTML, ~75 KB)
POST /ReviewSighting/Save                     → 302 → /ReviewSighting
POST /PublishSighting/PublishAll              → publiser på nytt
```

## To ID-er per observasjon

| Felt | Eksempel | Betydning |
|------|----------|-----------|
| `SightingId` | `41252560` | Permanent ID på det publiserte funnet. Dette er ID-en å lagre. |
| `TemporarySightingId` | `30004844` | Midlertidig håndtak mens funnet ligger i gjennomgang/redigering |

`Save` refererer til `SightingViewModel.SelectedTempSightings=<TemporarySightingId>`,
mens `EditPublishedSightings` åpnes med `SightingId`.

## 1. Gjennomgangskøen som JSON ⭐

```
POST /ReviewSighting/BindReviewSightingsGrid
Content-Type: application/x-www-form-urlencoded
X-Requested-With: XMLHttpRequest
Body: page=1&size=200
```

Svarer med rent JSON — **ingen HTML-skraping nødvendig**:

```json
{"data":[{"SightingId":41252560,"TemporarySightingId":30004844,
          "TaxonName":"tårnseiler","ScientificTaxonName":"Apus apus",
          "SearchableStartDate":"26.07.2026","TimePresentation":"15:00",
          "SiteName":"<div class=''>Hylkjesvingen 49, …</div>","SiteOrParentSiteId":362858,
          "Observers":"Kjetil Salomonsen","PublicCommentLong":"…",
          "ErrorCount":0,"WarningCount":0,"InfoCount":0,
          "TriggeredValidationRulesText":""}],"total":1}
```

Merk: flere felt (`SiteName`, `Quantity`, `StartDate`, `ActivityName` …) er pakket i
`<div>`-markup for grid-rendering. Bruk de rene variantene der de finnes
(`TaxonName`, `SearchableStartDate`, `TimePresentation`).

**Dette endepunktet løser tre ting på én gang:**
1. **ID-fangst** — kall det etter import, før publisering, og koble våre rader til `SightingId`.
2. **Verifisering etter sending** — `ErrorCount` + `TriggeredValidationRulesText` sier
   *hvilken* observasjon som ble avvist og *hvorfor*. Tatt i bruk i
   `ao_import_httpx.review_queue_rows` / `_describe_held_back`.
3. **Grunnlag for fase C** — redigering trenger `SightingId` herfra.

## 2. Åpne redigeringsskjema

```
POST /ReviewSighting/EditPublishedSightings
Body: __RequestVerificationToken=…&checkedRecords=41252560
      &FieldDiaryViewModel.SelectedSightingsInList=41252560
      &…FieldDiaryViewModel.CurrentUser.Diary*…&base=on&sightingIds=41252560
```

Kalles fra feltdagboka (`POST /FieldDiary/Index/`). `checkedRecords` og `sightingIds` er
kommaseparerte lister — flere funn kan åpnes samtidig. `FieldDiaryViewModel.CurrentUser.*`
er visningsinnstillinger og ser ut som støy vi må gjenta, ikke noe med funnet å gjøre.

Svar: hele redigeringsskjemaet som HTML.

## 3. Lagre

```
POST /ReviewSighting/Save   →  302 Location: /ReviewSighting
```

**149 felt** i bodyen. Strukturen er tredelt:

- `SightingViewModel.TemporarySighting.Sighting.*` — selve dataene
- `SightingViewModel.EditableProperties.*.IsEditable` — én per felt, alltid `True` her
- Kart-/lokalitets- og observatør-felt (`selectedSite*`, `SightingViewModel.Observers[0].*`)

Feltene vi faktisk bryr oss om:

| Felt | Verdi i fangsten |
|------|------------------|
| `…Sighting.Taxon` | `3542` (tårnseiler) |
| `…Sighting.StartDate` / `StartTime` | `26.07.2026` / `15:00` |
| `…Sighting.EndDate` / `EndTime` | `26.07.2026` / `15:00` |
| `…Sighting.Quantity` | `6` |
| `…Sighting.Activity` | `25` (næringssøkende) |
| `…Sighting.Stage` / `Gender` | `0` / `0` |
| `…Sighting.PublicComment.Comment` | fritekst |
| `…Sighting.HiddenByProvider` | `28.07.2026` (skjul til) |
| `SightingViewModel.SelectedSite.Id` | `477517` |
| `SightingViewModel.Observers[0].User` | `15969` |
| `SightingViewModel.SelectedTempSightings` | `30004844` |

Dubletter er meningsbærende: ASP.NET-checkboxer sendes som `true&false`-par (siste vinner
hvis avhuket er av). Det må reproduseres nøyaktig — ikke dedupliseres.

**Konsekvens for fase C:** et trygt round-trip krever at vi parser alle 149 felt ut av
skjema-HTML-en og poster dem tilbake uendret bortsett fra det brukeren rørte. Å bygge
bodyen fra bunnen av er ikke forsvarlig.

## 4. AOs egne valideringsendepunkter ⭐

AOs UI validerer live mens du skriver. Alle er form-encoded POST som svarer `true`:

| Endepunkt | Parametre |
|-----------|-----------|
| `/SightingValidation/ValidateStartDateTime` | `StartDate`, `StartTime`, `EndDate`, `EndTime` (DD.MM.YYYY / HH:MM) |
| `/SightingValidation/ValidateQuantity` | `Quantity`, `Gender` |
| `/SightingValidation/ValidateTaxonReportable` | `Taxon` |
| `/SightingValidation/ValidateSightingActivitySiteAccuracy` | `Activity`, `SelectedSite.Id` |
| `/SightingValidation/ValidateHiddenByProviderDate` | `HiddenByProvider` |

Alle med prefikset `SightingViewModel.TemporarySighting.Sighting.`, f.eks.
`SightingViewModel.TemporarySighting.Sighting.StartDate=26.07.2026`.

`ValidateStartDateTime` er nøyaktig regelen som avviste tårnseileren. Vår egen lokale
sjekk dekker dette uten innlogging og uten nettverkskall, så den er førstevalg — men
disse endepunktene kan fange det vi *ikke* kan vite lokalt (art rapporterbar i området,
urimelig antall, aktivitet vs. lokalitetsnøyaktighet).

## 5. Konsekvenser for enkel-ao

1. **`PublishAll` publiserer hele køen.** Redigerer du et funn på AO og glemmer å
   publisere, publiseres det som bivirkning ved neste sending fra appen. Kjent siden
   `ao-progress-capture.md`, men nå med en ny kilde til etterlatte rader: redigering.
2. **Avviste rader blir liggende.** De forstyrrer `pending_count`-sjekken og vil forstyrre
   ID-matching i fase B. Bør leses med `BindReviewSightingsGrid` og vises for brukeren.
3. **Fase C er teknisk mulig**, men prisen er bekreftet: 149 felt må round-trippes.
   Vurderingen i `rediger-sendte-obs-plan.md` står — bygg fase A/B først.
