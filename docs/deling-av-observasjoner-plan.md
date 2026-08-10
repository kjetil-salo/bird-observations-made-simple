# Deling av observasjoner — plan

**Dato:** 2026-07-27
**Status:** Fase 1 implementert i v1.40.0 (27.07.2026). Fase 2 (Mine delinger,
oppdater eksisterende deling, bilder) implementert i v1.43.6 (10.08.2026) — se
tillegg nederst i dokumentet. «Ikke planlagt»-punktet om bilder under er
dermed foreldet og erstattet av tillegget.
**Idé:** Det er gøy å dele hva man har sett. En pen, delbar oppsummering av dagens funn —
uten å sende folk til Artsobservasjoner.

---

## 1. Avgrensning

**Er med:** en lenke du sender til fuglevenner, som viser en pen liste over hva du så, hvor
og når. Lenken slutter å virke etter en tid.

**Er ikke med:** kontoer, innlogging for leseren, kommentarer, kart, bilder, følge-funksjon,
feed. Dette er en delbar kvittering, ikke et sosialt nettverk.

**Uavhengig av sendt-loggen.** Delingen tar et øyeblikksbilde av observasjonene på
serveren, så den kan bygges før fase B i `rediger-sendte-obs-plan.md`. Senere kan man dele
rett fra sendt-loggen også.

---

## 2. Arkitektur: SQLite med `expires_ts`, ikke Redis

Spørsmålet var om Redis er mer robust siden man får TTL gratis. **Anbefaling: nei.**

| | Redis | SQLite (dagens `stats.db`) |
|---|---|---|
| Ny container på Pi | ja (Pi har 4 GB RAM) | nei |
| Persistens ved omstart | må konfigureres (RDB/AOF) | gratis |
| Backup | ny rutine | følger eksisterende fil |
| TTL | innebygd | `expires_ts`-kolonne + `DELETE WHERE` |
| Utløpt deling kan forklares | nei — nøkkelen er borte | ja — vi vet at den fantes |

Det siste punktet er det avgjørende. Redis' TTL *fjerner* dataene, og da kan vi ikke skille
«denne delingen er utløpt» fra «denne lenken har aldri eksistert». En venn som klikker på
en gammel lenke fortjener «Denne delingen er utløpt» framfor en tom 404.

TTL i SQLite er heller ikke en cron-jobb — det er én `DELETE` som kjøres ved hver skriving
(lazy expiry). Ingen ny prosess, ingen ny feilmodus, ingenting som kan henge:

```sql
DELETE FROM shares WHERE expires_ts < :now;
```

Redis ville vært riktig svar hvis vi hadde hatt høy skrivefrekvens, flere app-instanser
eller behov for delt cache mellom prosesser. Ingen av delene gjelder her: én container,
én Pi, noen delinger om dagen.

### Datamodell

Samme database som statistikk og tilbakemeldinger (`DB_PATH`, default `/data/stats.db`),
ny modul `src/share_store.py` etter mønster fra `feedback_store.py`:

```sql
CREATE TABLE IF NOT EXISTS shares (
  slug        TEXT PRIMARY KEY,
  payload     TEXT NOT NULL,   -- JSON: øyeblikksbilde av observasjonene
  display_name TEXT,           -- «Kjetil» — brukervalgt, ikke AO-brukernavn
  delete_key  TEXT NOT NULL,   -- lar deleren trekke tilbake
  created_ts  REAL,
  expires_ts  REAL,
  views       INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_shares_expires ON shares(expires_ts);
```

`slug`: 12 tegn fra `_CASE_ALPHABET` i `feedback_store.py` (uten 0/O/1/I/L). ~7·10¹⁷
kombinasjoner — ikke gjettbar. Lenken *er* tilgangskontrollen.

**Levetid:** 14 dager fast i v1 (én konstant). Folk leser lenker sent.

---

## 3. Personvern — designregler, ikke ettertanke

Dette er første gang enkel-ao publiserer brukerinnhold på en offentlig URL. Tre regler:

1. **Aldri koordinater.** Kun lokalitetsnavn. En delt posisjon på en rovfuglreir- eller
   ugleobservasjon er nøyaktig det AO har skjulingsmekanismer for å hindre.
2. **Observasjoner med `hideUntil` deles aldri.** Har du bedt AO skjule et funn, skal ikke
   appen vår publisere det på en åpen lenke samtidig.
3. **Du ser nøyaktig hva som sendes.** Forhåndsvisning før lenken lages, med mulighet til å
   hake bort enkeltobservasjoner.

Merk en begrensning vi ikke kan løse lokalt: AO skjuler noen arter automatisk
(`ProtectedBySystem`), og det vet ikke appen. Regel 1 demper konsekvensen — lokalitetsnavn
uten koordinater er vesentlig mindre sensitivt — men det bør stå i hjelpeteksten.

**Lenken er hemmelig, ikke privat.** Sier vi «bare de du sender den til kan se den», lover
vi noe vi ikke holder. Ordlyd: *«Alle med lenken kan se den. Den slutter å virke etter 14
dager.»*

---

## 4. API og sider

| Rute | Metode | Beskrivelse |
|------|--------|-------------|
| `/api/share` | POST | Lager deling. Returnerer `{slug, url, expiresTs, deleteKey}` |
| `/api/share-delete` | POST | Trekker tilbake med `slug` + `deleteKey` |
| `/d/<slug>` | GET | Selve delingssiden (server-rendret HTML) |

**Misbruksvern** (samme mønster som `/api/feedback`): per-IP throttling, maks 200
observasjoner og ~100 KB per deling, alle felt HTML-escapet ved rendring. Kun kjente
observasjonsfelt rendres — ukjente nøkler i payloaden ignoreres, så endepunktet kan ikke
brukes til å hoste vilkårlig innhold.

**Siden** (`html_templates.generate_share_page`): gruppert på lokalitet, med dato, art,
antall, aktivitet og klokkeslett. Gjenbruker `style.css` så det ser ut som appen.
Egne OG-tagger per deling, slik at limt inn i Messenger/Facebook viser
«Kjetil så 23 arter på Hylkje, 27. juli» framfor generisk app-tekst — `img/og-image.png`
som bilde i v1.

Ingen lenke til AO. Det var hele poenget.

---

## 5. Faser

### Fase 1 — Del dagens funn

Knapp «Del funnene» ved siden av eksport-knappene → forhåndsvisning → lenke + «Kopier».

Akseptansekriterier:
1. Delingen viser art, antall, aktivitet, klokkeslett og lokalitetsnavn — **aldri**
   koordinater.
2. Observasjoner med `hideUntil` er utelatt, og brukeren får beskjed om at de er det.
3. Forhåndsvisningen lar brukeren hake bort enkeltobservasjoner før lenken lages, og er
   forhåndsutfylt med observasjonene fra den nyeste datoen i lista.
4. Lenken virker uten innlogging, i inkognito, og på mobil.
5. Etter 14 dager svarer `/d/<slug>` med en vennlig «utløpt»-side, ikke 404 eller feil.
6. Ukjent slug gir samme side som utløpt — ingen måte å skille dem (ingen enumerering).
7. «Trekk tilbake» sletter delingen umiddelbart; lenken slutter å virke.
8. Delt tekst med `<script>` eller HTML i kommentarfeltet rendres som tekst.
9. Appen virker som før hvis delings-endepunktet er nede — deling er tilleggsfunksjon.

Estimat: ~1–1,5 dag (server-modul, endepunkt, side, forhåndsvisning, tester).

### Fase 2 — Etter behov
- «Mine delinger» med visningsteller
- Valgbar levetid
- Deling rett fra sendt-loggen (fase B)
- Sesong-/årsoppsummering

### Ikke planlagt
Kommentarer, likes, kart, bilder, følge-funksjon. Det er en annen app.

---

## 6. Besluttet

1. **Standardutvalg: dagens funn.** Presisering: «i dag» betyr *den nyeste
   observasjonsdatoen i lista*, ikke kalenderdagen. I feltmodus er de det samme. Sitter du
   og etterregistrerer gårsdagens tur, ville en bokstavelig kalenderdag gitt en tom deling
   — den nyeste datoen i lista gir det du faktisk nettopp la inn. Overskriften viser
   datoen («Funn 27. juli»), så det aldri er tvil om hva som deles.
   Spenner lista over flere datoer, kan eldre observasjoner hakes på manuelt i
   forhåndsvisningen — ingen egen datovelger i v1.
2. **Visningsnavn: brukeren skriver det selv** én gang, lagres lokalt. AO-brukernavnet
   lekker aldri automatisk.
3. **Levetid: 14 dager fast.** Én konstant å endre hvis det viser seg for kort.

---

## 7. Tillegg — Fase 2 (v1.43.6, 10.08.2026)

Motivasjon: lange feltøkter (f.eks. Herdla, flere timer) der man ikke rekker å publisere
til AO underveis — en venn med lenken bør likevel kunne se ferske funn ved å oppdatere
siden, uten å få tilsendt en ny lenke hver gang. Samtidig var det ingen måte å se eller
administrere egne aktive delinger på («Mine delinger» fantes ikke, bare siste deling ble
husket, kun for øyeblikkelig «trekk tilbake»).

**Bilder er nå med** — punktet om bilder under «Ikke planlagt» i §1 er dermed foreldet.
Egen, liten delings-thumbnail (maks 800px, JPEG kvalitet 0,6) genereres client-side fra
observasjonens eksisterende `photo`-felt (satt via `edit.html`), atskilt fra tekstbudsjettet:

- `MAX_PHOTO_BYTES` (~120 KB) per bilde, `MAX_TOTAL_PHOTO_BYTES` (~1,5 MB) og
  `MAX_PHOTOS_PER_SHARE` (20) totalt per deling. Overskridelse dropper bildet stille —
  feller aldri hele delingen, samme prinsipp som gjelder ellers i denne planen.
- Kun `image/jpeg` godtas (hviteliste på mime-type, ikke bare `data:image/`-prefiks) —
  stenger blant annet ute `image/svg+xml`, som kan inneholde skript.
- Canvas-nedskaleringen fjerner EXIF (kan inneholde GPS) som bieffekt — ingen egen
  strippe-logikk nødvendig, men bevisst nevnt fordi det er relevant for §3 sin regel 1.
- Brukeren ser en thumbnail + egen av/på-bryter per bilde i forhåndsvisningen (default på)
  — konsistent med §3: «du ser nøyaktig hva som sendes».

**Oppdater eksisterende deling** — ny `share_store.update_share()` og
`POST /api/share-update`, autentisert med samme `delete_key` som ble utstedt ved
opprettelse. Overskriver `payload`/`display_name`/`email` på samme rad; `expires_ts`
endres bevisst ikke (en oppdatering forlenger ikke levetiden).

**Mine delinger** — ny side `/mine-delinger.html`. `myShares_v1` i localStorage lagrer nå
`{slug, deleteKey, ts, displayName, obsCount, dato, expiresTs}` (var bare
`{slug, deleteKey, ts}`), rent lokalt — ingen nytt serverendepunkt for selve oversikten.
Samme `slug` oppdateres på plass i stedet for å dupliseres, både ved ny deling og ved
oppdatering.
