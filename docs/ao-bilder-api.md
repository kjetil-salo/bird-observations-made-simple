# AO: bildeopplasting til en observasjon

**Bekreftet 03.08.2026** via to HAR-fangster (`26-08-03 18-49-43` og `26-08-03 19-04-10`).
Den andre fangsten inneholdt hele side-HTML-en for «Kontrollér funn»
(`/ReviewSighting`), inkludert selve opplastingsskjemaet — det avklarer nesten alt.

## Kortversjon

Bilder kan først lastes opp til en observasjon når den har fått en **ekte `SightingId`** —
det skjer når AO er ferdig med å parse importen (`NumberOfSightingsImporting` → 0), altså
mens funnet ligger i **gjennomgangskøen, før publisering**. AO markerer dette eksplisitt med
feltet `PossibleToUploadImages` på hver rad i gjennomgangskøen.

Selve opplastingen POSTes til `/Media/UploadImageAction` som en ekte
`multipart/form-data`-request. AOs eget UI sender den via en skjult iframe-postback
(jQuery Form-pluginets `ajaxForm({iframe:true})`) — det er sannsynligvis derfor selve
requesten aldri viste seg i noen av de to HAR-eksportene, selv om opplastingen beviselig
lyktes begge ganger (`https://www.artsobservasjoner.no/Image/3546122`). Det er ikke noe vi
trenger å reprodusere — for vår egen server-til-server-implementasjon bygger vi en vanlig
`httpx`-multipart-POST.

## Gjennomgangskøen: `PossibleToUploadImages`

`POST /ReviewSighting/BindReviewSightingsGrid` (body `page=1&size=200`) returnerer per rad:

```json
{
  "SightingId": 41326334,
  "TemporarySightingId": 30080638,
  "PossibleToUploadImages": true,
  "TaxonName": "gråmåke",
  "SearchableStartDate": "03.08.2026",
  "TimePresentation": "18:47",
  "SiteOrParentSiteId": 362858
}
```

Sett med to rader i køen samtidig i første fangst (én fra tidligere i sesjonen) — bekrefter
at flere rader kan stå i køen om hverandre, slik `ao-rediger-api.md` allerede advarte om.
Samme mønster (inkl. `SightingId`) finnes også på `SubmitSighting/BindSubmitSightingsGrid`
(AOs eget «legg til ett funn»-skjema, ikke CSV-import).

`review_queue_rows()` (`ao_import_httpx.py`) leser allerede dette endepunktet og er bekreftet
å fungere for CSV-importerte rader (`ao-rediger-api.md`, fangst 27.07.2026) — den fangsten
sjekket bare ikke spesifikt `PossibleToUploadImages`-feltet. Siden det er nøyaktig samme
grid-endepunkt uansett hvordan raden kom dit, er det all grunn til å tro feltet oppfører seg
likt for CSV-importerte rader. Verifiseres i praksis når fase A bygges.

## Selve opplastingsskjemaet

Fra den fullstendige side-HTML-en i andre fangst:

```html
<form action="/Media/UploadImageAction" id="uploadForm" method="post">
  <input name="__RequestVerificationToken" type="hidden" value="…" />
  <div class="fileuploadwrapper">
    <input type="hidden" id="MediaFilePerSightingRestriction" value="10"/>
    <input type="hidden" class="newimage-sightingid" name="UploadImageViewModel.Sighting.Id"/>
    <input type="file" name="UploadImageViewModel.Image" class="fileupload"/>
  </div>
  <select name="UploadImageViewModel.MediaLicense">
    <option selected="selected" value="10">Creative Commons 4.0 (CC) BY</option>
    <option value="20">Creative Commons 4.0 (CC) BY-SA</option>
    <option value="30">Creative Commons 4.0 (CC) BY-NC-SA</option>
    <option value="60">Ingen (alle rettigheter forbeholdt)</option>
  </select>
  <input type="submit" value="Last opp" class="uploadbutton"/>
</form>
```

Infoboks ved siden av skjemaet: *«Maks 10 bilder per funn. Vi har ingen begrensing i
filstørrelse eller oppløsning, men bilder som er større enn den høyeste tillatte
oppløsningen 1600 X 1600 piksler, kommer til å bli nedskalert. Alle bilder komprimeres noe
med JPEG-kompresjon.»*

| Felt | Verdi |
|------|-------|
| URL | `POST /Media/UploadImageAction` |
| Bildefil | `UploadImageViewModel.Image` (`multipart`-fil-del) |
| SightingId | `UploadImageViewModel.Sighting.Id` — den **ekte** `SightingId`-en fra gjennomgangskøen |
| Lisens (påkrevd) | `UploadImageViewModel.MediaLicense` — `10`=CC BY (AOs default), `20`=CC BY-SA, `30`=CC BY-NC-SA, `60`=Ingen/alle rettigheter forbeholdt |
| CSRF | `__RequestVerificationToken` — samme mønster som resten av `ao_import_httpx.py` |
| Maks bilder/funn | **10** |
| Maks filstørrelse | Ingen. AO nedskalerer og komprimerer selv, server-side. |

**Respons ved suksess** (kjent fra klient-JS, ikke sett i en faktisk HTTP-respons — samme
iframe-blindsone som selve requesten):

```json
{"Thumbnail": "...", "Fileurl": "...", "id": 3546122, "Description": "", "SightingId": 41326426, "ImagePosition": 0}
```

## Andre Media-endepunkter (fra `Content/MasterJs`, widgeten `ui.ap2ImageUpload`)

| Endepunkt | Metode | Body | Bruk |
|-----------|--------|------|------|
| `/Media/EditableImagesForSightingId/` | POST | `{sightingId}` | Hent/refresh bildeliste for en sighting |
| `/Media/DeleteImage/` | POST | `{id}` | Slett bilde |
| `/Media/RotateImage/` | POST | `{id}` | Roter bilde |
| `/Media/DescribeImage/` | POST | `{id, description}` | Lagre bildetekst |
| `/Media/GetFullSizeImage/{imageId}` | POST | `{imageId}` | Full oppløsning (lightbox) |

## Fortsatt åpent (lav risiko — avklares under implementering, ikke blokkerende for planen)

- **Nøyaktig multipart-oppsett httpx må bruke** (boundary, content-type per del) — standard
  `httpx.post(url, files=..., data=...)`-bruk, ingen kjent AO-spesifikk vri utover CSRF- og
  cookie-mønsteret som allerede finnes i resten av `ao_import_httpx.py`.
- **Feilrespons ved for stort/ugyldig bilde** — ikke sett, siden AO ikke har noen kjent
  filstørrelsesgrense å teste mot.
- **Om `newimage-sightingid`/`image-sightingid` faktisk må ha nøyaktig det navnet, eller om
  `UploadImageViewModel.Sighting.Id` (det som faktisk står i `name=`) er det som gjelder** —
  CSS-klassene i HTML-en (`newimage-sightingid`) er bare JS-selektorer, feltnavnet i
  `name=`-attributtet er det som faktisk sendes. Bruk `UploadImageViewModel.Sighting.Id`.

## Konklusjon

Fase 0 i `docs/bilde-opplasting-plan.md` er **i praksis avklart**. Videre verifisering
(faktisk vellykket `httpx`-opplasting mot en ekte, ufarlig testobservasjon) skjer naturlig som
del av fase A — ingen ny manuell HAR-fangst nødvendig først.
