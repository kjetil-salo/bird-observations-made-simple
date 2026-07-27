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

function huskDeling(slug, deleteKey) {
  try {
    const liste = JSON.parse(localStorage.getItem(SHARES_KEY) || '[]');
    liste.unshift({ slug, deleteKey, ts: Date.now() });
    localStorage.setItem(SHARES_KEY, JSON.stringify(liste.slice(0, 20)));
  } catch (e) {
    console.warn('Kunne ikke lagre deling lokalt', e);
  }
}

function glemDeling(slug) {
  try {
    const liste = JSON.parse(localStorage.getItem(SHARES_KEY) || '[]');
    localStorage.setItem(SHARES_KEY, JSON.stringify(liste.filter((d) => d.slug !== slug)));
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
function visResultat(box, overlay, url, slug, deleteKey) {
  huskDeling(slug, deleteKey);

  box.innerHTML = `
    <h3 style="margin:0 0 12px 0;font-size:1.05em;">🔗 Lenken er klar</h3>
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

/** Åpne forhåndsvisning og la brukeren lage en delingslenke. */
export function openShareDialog(observations) {
  if (!observations.length) return;

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
    return `
      <label style="display:flex;gap:10px;align-items:flex-start;padding:8px 0;border-bottom:1px solid var(--border,rgba(148,163,184,0.15));cursor:pointer;">
        <input type="checkbox" data-idx="${i}" ${forvalgt.has(obs) ? 'checked' : ''} style="margin-top:3px;flex-shrink:0;" />
        <span style="flex:1;font-size:0.9em;">
          <b>${obs.count || ''} ${navn}</b>
          <span style="color:var(--muted);"> ${tid}</span>
          <br><span style="color:var(--muted);font-size:0.9em;">${sted}</span>
        </span>
      </label>`;
  }).join('');

  box.innerHTML = `
    <h3 style="margin:0 0 4px 0;font-size:1.05em;">🔗 Del funnene</h3>
    <p style="margin:0 0 14px 0;font-size:0.8em;color:var(--muted);line-height:1.35;">
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
      <button type="button" id="share-create" style="${knappPrimaer}">Lag lenke</button>
    </div>`;

  box.querySelector('#share-cancel').addEventListener('click', () => overlay.remove());

  box.querySelector('#share-create').addEventListener('click', async (e) => {
    const valgte = [...box.querySelectorAll('#share-list input:checked')]
      .map((cb) => delbare[Number(cb.dataset.idx)]);
    if (!valgte.length) {
      alert('Velg minst én observasjon.');
      return;
    }

    const navn = box.querySelector('#share-name').value.trim();
    localStorage.setItem(NAME_KEY, navn);

    e.target.disabled = true;
    e.target.textContent = 'Lager lenke…';
    try {
      const resp = await fetch('/api/share', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ observations: valgte, displayName: navn }),
      });
      const result = await resp.json();
      if (!resp.ok || !result.ok) throw new Error(result.error || 'Kunne ikke lage lenke');
      visResultat(box, overlay, window.location.origin + result.url, result.slug, result.deleteKey);
    } catch (err) {
      e.target.disabled = false;
      e.target.textContent = 'Lag lenke';
      alert(err.message);
    }
  });
}
