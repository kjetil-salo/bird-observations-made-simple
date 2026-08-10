/**
 * Deling av observasjoner via hemmelig lenke.
 *
 * Brukeren får en forhåndsvisning av hva som deles før lenken lages — deling
 * er en publisering, og da skal ingenting overraske. Observasjoner med
 * «skjul til dato» (hideUntil) er skjult på AO og deles aldri; de filtreres
 * både her og på serveren.
 *
 * Se docs/deling-av-observasjoner-plan.md.
 */

const NAME_KEY = 'shareDisplayName_v1';
const SHARES_KEY = 'myShares_v1';

/** Observasjonsdato («2026-07-27») eller tom streng. */
function obsDato(obs) {
  return (obs.timestamp || '').slice(0, 10);
}

/**
 * Observasjonene fra den nyeste datoen i lista.
 *
 * «Dagens funn» betyr nyeste observasjonsdato, ikke kalenderdagen: etter-
 * registrerer du gårsdagens tur, er det den turen du vil dele.
 */
export function nyesteDagsObservasjoner(observations) {
  const datoer = observations.map(obsDato).filter(Boolean);
  if (!datoer.length) return observations.slice();
  const nyeste = datoer.sort()[datoer.length - 1];
  return observations.filter((o) => obsDato(o) === nyeste);
}

function formatDato(iso) {
  const mnd = ['januar', 'februar', 'mars', 'april', 'mai', 'juni',
    'juli', 'august', 'september', 'oktober', 'november', 'desember'];
  if (!iso || iso.length < 10) return '';
  const [aar, m, dag] = iso.slice(0, 10).split('-').map(Number);
  return `${dag}. ${mnd[m - 1]} ${aar}`;
}

/**
 * Lag en liten delings-thumbnail fra et allerede eksisterende bilde (data-URL).
 *
 * Egen, mye mindre nedskalering enn AO-kvalitets-bildet fra edit.html —
 * dette skal bo i en offentlig, uinnlogget deling, ikke brukes til
 * artsbestemmelse. Canvas-omtegning fjerner samtidig EXIF (kan inneholde
 * GPS), samme bieffekt som edit.html allerede drar nytte av.
 */
function downscaleForShare(dataUrl, quality, maxSide) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      let { width, height } = img;
      if (width > maxSide || height > maxSide) {
        if (width > height) { height = Math.round(height * maxSide / width); width = maxSide; }
        else { width = Math.round(width * maxSide / height); height = maxSide; }
      }
      const canvas = document.createElement('canvas');
      canvas.width = width;
      canvas.height = height;
      canvas.getContext('2d').drawImage(img, 0, 0, width, height);
      resolve(canvas.toDataURL('image/jpeg', quality));
    };
    img.onerror = () => reject(new Error('Kunne ikke lese bildet'));
    img.src = dataUrl;
  });
}

// Mål: ~50 KB rådata per bilde er nok for en rask oppdatering til venner —
// ikke artsbestemmelse. ~68 000 tegn i data-URL-en tilsvarer omtrent det,
// etter base64-overhead (4/3) + prefiks. Serverens MAX_PHOTO_BYTES (220 KB,
// share_store.py) er bakstopperen hvis selv laveste trinn ikke når målet.
const SHARE_PHOTO_TARGET_CHARS = 68_000;
const NEDSKALERINGSTRINN = [
  { maxSide: 800, quality: 0.55 },
  { maxSide: 640, quality: 0.4 },
  { maxSide: 480, quality: 0.32 },
  { maxSide: 400, quality: 0.28 },
];

/**
 * Nedskaler til delings-thumbnail. Prøver stadig mindre/lavere kvalitet til
 * resultatet er under måltørrelsen — detaljerte naturbilder (vann, fjær,
 * bakgrunnstekstur) komprimerer dårlig, og ett trinn holdt sjelden målet.
 * Treffer ingen av trinnene målet, brukes uansett det siste (minste) forsøket
 * — serveren er bakstopperen om det fortsatt er for stort.
 */
async function nedskalerMedFallback(dataUrl) {
  let foto = null;
  for (const { maxSide, quality } of NEDSKALERINGSTRINN) {
    foto = await downscaleForShare(dataUrl, quality, maxSide);
    if (foto.length <= SHARE_PHOTO_TARGET_CHARS) break;
  }
  return foto;
}

/** Alle delinger appen kjenner til fra denne enheten, nyeste først. */
export function hentMineDelinger() {
  try {
    return JSON.parse(localStorage.getItem(SHARES_KEY) || '[]');
  } catch (e) {
    return [];
  }
}

/**
 * Husk (eller oppdater) en deling lokalt. Samme `slug` flyttes til toppen
 * og overskrives i stedet for å dupliseres — brukes både ved opprettelse og
 * ved oppdatering av en eksisterende deling.
 */
function huskDeling(record) {
  try {
    const uten = hentMineDelinger().filter((d) => d.slug !== record.slug);
    uten.unshift(record);
    localStorage.setItem(SHARES_KEY, JSON.stringify(uten.slice(0, 20)));
  } catch (e) {
    console.warn('Kunne ikke lagre deling lokalt', e);
  }
}

export function glemDeling(slug) {
  try {
    localStorage.setItem(SHARES_KEY, JSON.stringify(hentMineDelinger().filter((d) => d.slug !== slug)));
  } catch (e) {
    console.warn('Kunne ikke fjerne deling lokalt', e);
  }
}

function lagOverlay() {
  const eksisterende = document.getElementById('share-modal');
  if (eksisterende) eksisterende.remove();

  const overlay = document.createElement('div');
  overlay.id = 'share-modal';
  Object.assign(overlay.style, {
    position: 'fixed', inset: '0', zIndex: '1000',
    background: 'rgba(0,0,0,0.5)', display: 'flex',
    alignItems: 'center', justifyContent: 'center', padding: '16px',
  });

  const box = document.createElement('div');
  Object.assign(box.style, {
    background: 'var(--card-bg, #1e293b)', borderRadius: '12px', padding: '20px',
    maxWidth: '420px', width: '100%', maxHeight: '85vh', overflowY: 'auto',
    boxShadow: '0 8px 32px rgba(0,0,0,0.3)',
  });

  overlay.appendChild(box);
  document.body.appendChild(overlay);
  overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });
  return { overlay, box };
}

const knappSekundaer = 'padding:8px 16px;border:1px solid var(--border,rgba(148,163,184,0.25));border-radius:6px;background:transparent;color:var(--text);cursor:pointer;font-size:0.9em;';
const knappPrimaer = 'padding:8px 16px;border:none;border-radius:6px;background:var(--accent,#3b82f6);color:white;cursor:pointer;font-size:0.9em;font-weight:500;';

/** Vis den ferdige lenken med kopier- og tilbaketrekkings-knapp. */
function visResultat(box, overlay, url, record, erOppdatering, bilderFalt) {
  huskDeling(record);
  const { slug, deleteKey } = record;

  const bilderVarsel = bilderFalt > 0
    ? `<p style="margin:0 0 10px 0;padding:8px 10px;border-radius:8px;background:rgba(251,191,36,0.12);color:#fbbf24;font-size:0.8em;line-height:1.4;">
        ⚠️ ${bilderFalt} bilde${bilderFalt !== 1 ? 'r' : ''} kunne ikke bli med i delingen (for stort, eller nettleseren fikk ikke behandlet det). Resten er delt som normalt.
      </p>`
    : '';

  box.innerHTML = `
    <h3 style="margin:0 0 12px 0;font-size:1.05em;">${erOppdatering ? '🔄 Delingen er oppdatert' : '🔗 Lenken er klar'}</h3>
    ${bilderVarsel}
    <input id="share-url" readonly value="${url}"
      style="width:100%;padding:10px;border-radius:8px;border:1px solid var(--border,rgba(148,163,184,0.25));background:var(--card-bg);color:var(--text);font-size:16px;box-sizing:border-box;" />
    <p style="margin:10px 0 16px 0;font-size:0.8em;color:var(--muted);line-height:1.4;">
      Alle som har lenken kan se den. Den slutter å virke etter 14 dager.
    </p>
    <div style="display:flex;gap:8px;justify-content:space-between;align-items:center;">
      <button type="button" id="share-withdraw" style="${knappSekundaer}color:var(--muted);">Trekk tilbake</button>
      <div style="display:flex;gap:8px;">
        <button type="button" id="share-close" style="${knappSekundaer}">Lukk</button>
        <button type="button" id="share-copy" style="${knappPrimaer}">Kopier lenke</button>
      </div>
    </div>`;

  const urlInput = box.querySelector('#share-url');
  box.querySelector('#share-close').addEventListener('click', () => overlay.remove());

  box.querySelector('#share-copy').addEventListener('click', async (e) => {
    try {
      await navigator.clipboard.writeText(url);
    } catch (_) {
      urlInput.select();
      document.execCommand('copy');
    }
    e.target.textContent = 'Kopiert!';
  });

  box.querySelector('#share-withdraw').addEventListener('click', async (e) => {
    e.target.disabled = true;
    try {
      const r = await fetch('/api/share-delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ slug, deleteKey }),
      });
      if (!r.ok) throw new Error();
      glemDeling(slug);
      box.innerHTML = '<p style="margin:0;font-size:0.95em;">Delingen er trukket tilbake. Lenken virker ikke lenger.</p>';
      setTimeout(() => overlay.remove(), 1800);
    } catch (_) {
      e.target.disabled = false;
      e.target.textContent = 'Kunne ikke trekke tilbake';
    }
  });
}

/**
 * Åpne forhåndsvisning og la brukeren lage — eller oppdatere — en delingslenke.
 * @param {Array} observations
 * @param {{slug: string, deleteKey: string}|null} existing - satt ved oppdatering
 *   av en eksisterende deling (samme URL); null ved ny deling.
 */
export function openShareDialog(observations, existing = null) {
  if (!observations.length) return;
  const erOppdatering = !!existing;

  const skjulte = observations.filter((o) => o.hideUntil).length;
  const delbare = observations.filter((o) => !o.hideUntil);
  if (!delbare.length) {
    alert('Alle observasjonene er merket «skjul til dato» og kan ikke deles.');
    return;
  }

  const forvalgt = new Set(nyesteDagsObservasjoner(delbare));
  const { overlay, box } = lagOverlay();
  const dato = formatDato(obsDato([...forvalgt][0] || delbare[0]));
  const lagretNavn = localStorage.getItem(NAME_KEY) || '';

  const rader = delbare.map((obs, i) => {
    const navn = (obs.species && obs.species.taxonName) || '';
    const tid = (obs.timestamp || '').slice(11, 16);
    const sted = obs.placeName || '';
    const fotoHtml = obs.photo ? `
        <label style="display:flex;align-items:center;gap:6px;margin:4px 0 0 30px;font-size:0.78em;color:var(--muted);cursor:pointer;">
          <img src="${obs.photo}" style="width:32px;height:32px;object-fit:cover;border-radius:6px;flex-shrink:0;" alt="" />
          <input type="checkbox" data-photo-idx="${i}" checked style="margin:0;" /> Del bilde
        </label>` : '';
    return `
      <div style="padding:8px 0;border-bottom:1px solid var(--border,rgba(148,163,184,0.15));">
        <label style="display:flex;gap:10px;align-items:flex-start;margin:0;cursor:pointer;">
          <input type="checkbox" data-idx="${i}" ${forvalgt.has(obs) ? 'checked' : ''} style="margin-top:3px;flex-shrink:0;" />
          <span style="flex:1;font-size:0.9em;">
            <b>${obs.count || ''} ${navn}</b>
            <span style="color:var(--muted);"> ${tid}</span>
            <br><span style="color:var(--muted);font-size:0.9em;">${sted}</span>
          </span>
        </label>
        ${fotoHtml}
      </div>`;
  }).join('');

  const knappTekst = erOppdatering ? 'Oppdater' : 'Lag lenke';

  box.innerHTML = `
    <h3 style="margin:0 0 4px 0;font-size:1.05em;">${erOppdatering ? '🔄 Oppdater delingen' : '🔗 Del funnene'}</h3>
    <p style="margin:0 0 14px 0;font-size:0.8em;color:var(--muted);line-height:1.35;">
      ${erOppdatering ? 'Samme lenke fortsetter å virke — innholdet erstattes. ' : ''}
      ${dato ? `Forhåndsvalgt: ${dato}. ` : ''}Hak av det du vil dele.
      ${skjulte ? `<br>${skjulte} skjult${skjulte !== 1 ? 'e' : ''} observasjon${skjulte !== 1 ? 'er' : ''} er utelatt.` : ''}
    </p>
    <label style="font-size:0.8em;color:var(--muted);display:block;margin-bottom:4px;">Vist som</label>
    <input id="share-name" placeholder="Navnet ditt" maxlength="40" value="${lagretNavn.replace(/"/g, '&quot;')}"
      style="width:100%;padding:8px;border-radius:8px;border:1px solid var(--border,rgba(148,163,184,0.25));background:var(--card-bg);color:var(--text);font-size:16px;box-sizing:border-box;margin-bottom:12px;" />
    <div id="share-list" style="max-height:38vh;overflow-y:auto;margin-bottom:14px;">${rader}</div>
    <p style="margin:0 0 14px 0;font-size:0.75em;color:var(--muted);line-height:1.35;">
      Posisjon deles aldri — kun lokalitetsnavn. Alle med lenken kan se den, og den slutter å virke etter 14 dager.
    </p>
    <div style="display:flex;gap:8px;justify-content:flex-end;">
      <button type="button" id="share-cancel" style="${knappSekundaer}">Avbryt</button>
      <button type="button" id="share-create" style="${knappPrimaer}">${knappTekst}</button>
    </div>`;

  box.querySelector('#share-cancel').addEventListener('click', () => overlay.remove());

  box.querySelector('#share-create').addEventListener('click', async (e) => {
    const valgteIdx = [...box.querySelectorAll('#share-list input[data-idx]:checked')]
      .map((cb) => Number(cb.dataset.idx));
    if (!valgteIdx.length) {
      alert('Velg minst én observasjon.');
      return;
    }

    const navn = box.querySelector('#share-name').value.trim();
    localStorage.setItem(NAME_KEY, navn);

    // Uten navn: bruk AO-innloggingen (ofte en e-post) som visnings-fallback
    // i stedet for et anonymt «En fuglekikker». Kun hvis den ser ut som en
    // e-post — vi vil ikke publisere et rent AO-brukernavn ved et uhell.
    const lagretAoBruker = (localStorage.getItem('ao_username') || '').trim();
    const epost = !navn && lagretAoBruker.includes('@') ? lagretAoBruker : '';

    e.target.disabled = true;
    e.target.textContent = erOppdatering ? 'Oppdaterer…' : 'Lager lenke…';
    try {
      // Nedskaler bare bildene som faktisk skal deles — resten strippes helt
      // fra det som sendes (ikke bare skjules på siden etterpå). Feiler
      // nedskaleringen (f.eks. et bilde nettleseren ikke klarer å lese inn i
      // et canvas), telles det — bilde-bortfall skal aldri skje i stillhet.
      let bilderFeiletKlient = 0;
      const valgte = await Promise.all(valgteIdx.map(async (idx) => {
        const obs = delbare[idx];
        const fotoCb = box.querySelector(`#share-list input[data-photo-idx="${idx}"]`);
        if (obs.photo && fotoCb && fotoCb.checked) {
          try {
            const foto = await nedskalerMedFallback(obs.photo);
            return { ...obs, photo: foto };
          } catch (err) {
            console.warn('Kunne ikke nedskalere bilde for deling', err);
            bilderFeiletKlient++;
            const { photo, ...rest } = obs;
            return rest;
          }
        }
        const { photo, ...rest } = obs;
        return rest;
      }));

      const endepunkt = erOppdatering ? '/api/share-update' : '/api/share';
      const body = erOppdatering
        ? { slug: existing.slug, deleteKey: existing.deleteKey, observations: valgte, displayName: navn, email: epost }
        : { observations: valgte, displayName: navn, email: epost };

      const resp = await fetch(endepunkt, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const result = await resp.json();
      if (!resp.ok || !result.ok) {
        throw new Error(result.error || (erOppdatering ? 'Kunne ikke oppdatere delingen' : 'Kunne ikke lage lenke'));
      }

      const slug = result.slug;
      const deleteKey = erOppdatering ? existing.deleteKey : result.deleteKey;
      const url = erOppdatering ? `${window.location.origin}/d/${slug}` : window.location.origin + result.url;
      const nyesteValgtDato = nyesteDagsObservasjoner(valgte).map(obsDato).filter(Boolean)[0] || '';
      const record = {
        slug,
        deleteKey,
        ts: Date.now(),
        displayName: navn,
        obsCount: valgte.length,
        dato: nyesteValgtDato,
        expiresTs: result.expiresTs,
      };
      const bilderFalt = bilderFeiletKlient + (result.photosDropped || 0);
      visResultat(box, overlay, url, record, erOppdatering, bilderFalt);
    } catch (err) {
      e.target.disabled = false;
      e.target.textContent = knappTekst;
      alert(err.message);
    }
  });
}
