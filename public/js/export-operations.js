/**
 * Eksport-modul for CSV-eksport, kopiering og sletting av observasjoner
 */

import { toCsv } from './observations.js';
import { flashButton } from './ui.js';
import { appendSentBatch } from './storage.js';

function _statusColor(type) {
  const light = document.body.classList.contains('theme-light');
  const colors = {
    info:    light ? '#2563eb' : '#93c5fd',
    success: light ? '#16a34a' : '#86efac',
    error:   light ? '#dc2626' : '#fca5a5',
  };
  return colors[type];
}

// Viser stegvis progresjon med animert linje under «Publiser til AO».
// Gir brukeren trygghet om at noe faktisk skjer under sending.
function _renderProgress(dom, step, totalSteps, text, pct = null) {
  dom.aoDirectStatus.style.display = 'block';
  dom.aoDirectStatus.style.cssText = `display:block;margin-top:8px;padding:10px;border-radius:8px;font-size:0.9rem;background:rgba(59,130,246,0.1);border:1px solid rgba(59,130,246,0.3);color:${_statusColor('info')};`;
  // pct === null → indeterminert animert linje; ellers determinat bredde
  const bar = pct == null
    ? '<div class="ao-progress-bar"></div>'
    : `<div class="ao-progress-bar ao-progress-bar-det" style="width:${Math.max(4, Math.min(100, pct))}%"></div>`;
  dom.aoDirectStatus.innerHTML = `
    <div class="ao-progress-head">
      <span class="ao-progress-step">${step}/${totalSteps}</span>
      <span>${text}</span>
    </div>
    <div class="ao-progress-track">${bar}</div>`;
}

export function handleExport(observations, dom) {
  const csv = toCsv(observations);
  if (!csv) return;

  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'fugleobservasjoner.csv';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
  flashButton(dom.exportBtn, 'Lastet ned!');
}

async function copyToClipboard(csv) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    await navigator.clipboard.writeText(csv);
  } else {
    const ta = document.createElement('textarea');
    ta.value = csv;
    ta.style.position = 'fixed';
    ta.style.top = '-1000px';
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    try {
      document.execCommand('copy');
    } finally {
      document.body.removeChild(ta);
    }
  }
}

export async function handleCopy(observations, dom) {
  const csv = toCsv(observations);
  if (!csv) return;

  try {
    await copyToClipboard(csv);
    flashButton(dom.copyBtn, 'Kopiert!');
  } catch (e) {
    console.warn('Kunne ikke kopiere CSV til utklippstavlen', e);
  }
}

export async function handleCopyAndOpen(observations, dom) {
  const csv = toCsv(observations);
  if (!csv) return;

  try {
    await copyToClipboard(csv);
    window.open('https://www.artsobservasjoner.no/ImportSighting', '_blank');
    flashButton(dom.copyOpenBtn, 'Åpnet!');
    fetch('/api/log-export', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ type: 'copy_open' }) }).catch(() => {});
  } catch (e) {
    console.warn('Kunne ikke kopiere CSV til utklippstavlen', e);
  }
}

// AO underkjenner observasjoner med tidspunkt frem i tid («Angi et tidspunkt som ikke
// er passert») — de importeres, men publiseres aldri. Fang dem her, ikke i AOs
// gjennomgangskø. Observasjoner kan ha fått fremtidig tid via redigering (edit.html),
// feil dato ved etterregistrering, eller feilstilt klokke.
function _findFutureObservation(observations) {
  const now = new Date();
  return observations.find((o) => {
    const from = o.timestamp ? new Date(o.timestamp) : null;
    const to = o.tilKlokkeslett ? new Date(o.tilKlokkeslett) : null;
    return (from && !isNaN(from) && from > now) || (to && !isNaN(to) && to > now);
  });
}

export async function handleDirectSend(observations, dom, callbacks) {
  if (!observations.length) return;

  const username = localStorage.getItem('ao_username');
  const password = localStorage.getItem('ao_password');
  if (!username || !password) return;

  const future = _findFutureObservation(observations);
  if (future) {
    const navn = (future.species && future.species.taxonName) || 'En observasjon';
    dom.aoDirectStatus.style.cssText = `display:block;margin-top:8px;padding:10px;border-radius:8px;font-size:0.9rem;background:rgba(239,68,68,0.1);border:1px solid rgba(239,68,68,0.3);color:${_statusColor('error')};`;
    dom.aoDirectStatus.textContent = `❌ ${navn} har tidspunkt frem i tid — AO godtar den ikke. Rett tidspunktet før du sender.`;
    return;
  }

  const total = observations.length;

  dom.aoDirectBtn.disabled = true;
  _renderProgress(dom, 1, 3, 'Logger inn på AO…');

  try {
    const loginResp = await fetch('/api/ao-login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
    const loginResult = await loginResp.json();
    if (!loginResp.ok || !loginResult.success) {
      throw new Error(loginResult.error || 'Innlogging feilet');
    }

    const tokens = JSON.parse(localStorage.getItem('ao_tokens') || '{}');
    tokens.loginToken = loginResult.loginToken;
    tokens.authCookie = loginResult.authCookie;
    tokens.userId = tokens.mapUserId || loginResult.userId;
    localStorage.setItem('ao_tokens', JSON.stringify(tokens));

    _renderProgress(dom, 2, 3, `Sender ${total} observasjon${total !== 1 ? 'er' : ''} …`, 0);

    const importResp = await fetch('/api/ao-import-stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        observations,
        loginToken: tokens.loginToken,
        authCookie: tokens.authCookie,
        areaId: localStorage.getItem('ao_area') ? JSON.parse(localStorage.getItem('ao_area')).id : '',
      }),
    });

    // Feil før strømmen starter (f.eks. 400-validering) kommer som vanlig JSON
    if (!importResp.ok || !importResp.body) {
      let msg = 'Import feilet';
      try { const j = await importResp.json(); msg = j.error || msg; } catch (_) { /* ignorer */ }
      throw new Error(msg);
    }

    // Les SSE-strømmen og oppdater fremdrift i sanntid
    const reader = importResp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let importResult = null;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let sep;
      while ((sep = buffer.indexOf('\n\n')) >= 0) {
        const rawEvent = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);
        const dataLine = rawEvent.split('\n').find((l) => l.startsWith('data:'));
        if (!dataLine) continue;
        let evt;
        try { evt = JSON.parse(dataLine.slice(5).trim()); } catch (_) { continue; }

        if (evt.phase === 'importing') {
          const t = evt.total || total;
          const behandlet = Math.max(0, t - (evt.remaining || 0));
          const pct = t ? Math.round((behandlet / t) * 100) : null;
          _renderProgress(dom, 2, 3, `Behandler ${behandlet} av ${t} …`, pct);
        } else if (evt.phase === 'publishing') {
          const t = evt.total || total;
          _renderProgress(dom, 3, 3, `Publiserer ${t} observasjon${t !== 1 ? 'er' : ''} …`, null);
        } else if (evt.phase === 'done') {
          importResult = evt;
        } else if (evt.phase === 'error') {
          throw new Error(evt.error || 'Import feilet');
        }
      }
    }

    if (!importResult || !importResult.success) {
      throw new Error((importResult && importResult.error) || 'Import feilet');
    }

    if (importResult.refreshedAuthCookie) {
      const t = JSON.parse(localStorage.getItem('ao_tokens') || '{}');
      t.authCookie = importResult.refreshedAuthCookie;
      localStorage.setItem('ao_tokens', JSON.stringify(t));
    }
    // AO holder tilbake rader den underkjenner — da er grønn hake feil signal.
    if (importResult.heldBack) {
      dom.aoDirectStatus.style.cssText = `display:block;margin-top:8px;padding:10px;border-radius:8px;font-size:0.9rem;background:rgba(234,179,8,0.1);border:1px solid rgba(234,179,8,0.4);color:${_statusColor('error')};`;
      const detaljer = importResult.heldBackDetails
        ? `<br><span style="opacity:.85">${importResult.heldBackDetails}</span>` : '';
      dom.aoDirectStatus.innerHTML = `⚠️ ${importResult.heldBack} observasjon${importResult.heldBack !== 1 ? 'er' : ''} ble <b>ikke</b> publisert og ligger til gjennomgang på AO.${detaljer}<br>`
        + '<a href="https://www.artsobservasjoner.no/ReviewSighting" target="_blank" rel="noopener">Åpne gjennomgang</a>';
      dom.aoDirectBtn.disabled = false;
      return;
    }

    dom.aoDirectStatus.style.cssText = `display:block;margin-top:8px;padding:10px;border-radius:8px;font-size:0.9rem;background:rgba(34,197,94,0.1);border:1px solid rgba(34,197,94,0.3);color:${_statusColor('success')};`;
    dom.aoDirectStatus.textContent = `✅ ${importResult.count} observasjon${importResult.count !== 1 ? 'er' : ''} sendt til AO!`;
    fetch('/api/log-export', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ type: 'direct' }) }).catch(() => {});

    // Husk hva som ble sendt FØR lista eventuelt tømmes — ellers er kvitteringen
    // borte i samme øyeblikk brukeren svarer «ja» på spørsmålet under.
    appendSentBatch(observations);

    setTimeout(() => {
      if (confirm('Sending vellykket! Vil du tømme observasjonslisten?')) {
        observations.splice(0, observations.length);
        callbacks.doRenderObservations();
        callbacks.saveState();
        dom.aoDirectStatus.style.display = 'none';
      }
    }, 1500);
  } catch (error) {
    dom.aoDirectStatus.style.cssText = `display:block;margin-top:8px;padding:10px;border-radius:8px;font-size:0.9rem;background:rgba(239,68,68,0.1);border:1px solid rgba(239,68,68,0.3);color:${_statusColor('error')};`;
    dom.aoDirectStatus.textContent = `❌ ${error.message}`;
    dom.aoDirectBtn.disabled = false;
  }
}

export function handleClear(observations, dom, callbacks) {
  if (!observations.length) return;
  const ok = window.confirm('Slette alle observasjoner i listen?');
  if (!ok) return;
  observations.splice(0, observations.length);
  callbacks.doRenderObservations();
  callbacks.saveState();
}
