/**
 * Observations-modul for håndtering av observasjoner og CSV-eksport
 */

import { defaultCoObservers, loadMedobs } from './storage.js';
import { showToast } from './ui.js';
import { toLocalISOString } from './utils.js';
import { getObservationVisitKey, setVisitLocked } from './visits.js';

/**
 * Vis modal for å sette fra/til-klokkeslett på alle obs i en gruppe
 */
function showTimeModal(groupItems, defaultFra, defaultTil, groupName, observations, obsListEl, buttons, saveState) {
  // Fjern evt. eksisterende modal
  const existing = document.getElementById('time-modal');
  if (existing) existing.remove();

  const overlay = document.createElement('div');
  overlay.id = 'time-modal';
  Object.assign(overlay.style, {
    position: 'fixed', inset: '0', zIndex: '1000',
    background: 'rgba(0,0,0,0.5)', display: 'flex',
    alignItems: 'center', justifyContent: 'center',
  });

  const box = document.createElement('div');
  Object.assign(box.style, {
    background: 'var(--card-bg, #1e293b)', borderRadius: '12px', padding: '20px',
    maxWidth: '340px', width: '90%', boxShadow: '0 8px 32px rgba(0,0,0,0.3)',
  });

  box.innerHTML = `
    <h3 style="margin:0 0 4px 0;font-size:1.05em;">🕐 Sett klokkeslett</h3>
    <p style="margin:0 0 14px 0;font-size:0.8em;color:var(--muted);line-height:1.3;">${groupName} — ${groupItems.length} observasjon${groupItems.length !== 1 ? 'er' : ''}</p>
    <div style="display:flex;gap:12px;align-items:center;margin-bottom:16px;">
      <div style="flex:1;">
        <label style="font-size:0.8em;color:var(--muted);display:block;margin-bottom:4px;">Fra</label>
        <input type="time" id="time-modal-fra" value="${defaultFra}" style="width:100%;padding:8px;border-radius:8px;border:1px solid var(--border,rgba(148,163,184,0.25));background:var(--card-bg);color:var(--text);font-size:16px;box-sizing:border-box;" />
      </div>
      <div style="flex:1;">
        <label style="font-size:0.8em;color:var(--muted);display:block;margin-bottom:4px;">Til</label>
        <input type="time" id="time-modal-til" value="${defaultTil}" style="width:100%;padding:8px;border-radius:8px;border:1px solid var(--border,rgba(148,163,184,0.25));background:var(--card-bg);color:var(--text);font-size:16px;box-sizing:border-box;" />
      </div>
    </div>
    <div style="display:flex;gap:8px;justify-content:flex-end;">
      <button type="button" id="time-modal-cancel" style="padding:8px 16px;border:1px solid var(--border,rgba(148,163,184,0.25));border-radius:6px;background:transparent;color:var(--text);cursor:pointer;font-size:0.9em;">Avbryt</button>
      <button type="button" id="time-modal-apply" style="padding:8px 16px;border:none;border-radius:6px;background:var(--accent,#3b82f6);color:white;cursor:pointer;font-size:0.9em;font-weight:500;">Sett på alle</button>
    </div>
  `;

  overlay.appendChild(box);
  document.body.appendChild(overlay);

  const fraInput = document.getElementById('time-modal-fra');
  const tilInput = document.getElementById('time-modal-til');
  const cancelBtn = document.getElementById('time-modal-cancel');
  const applyBtn = document.getElementById('time-modal-apply');

  function close() { overlay.remove(); }
  function resetBorder(el) { el.style.borderColor = ''; }

  fraInput.addEventListener('input', () => resetBorder(fraInput));
  tilInput.addEventListener('input', () => resetBorder(tilInput));

  overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });
  cancelBtn.addEventListener('click', close);

  applyBtn.addEventListener('click', () => {
    const fraVal = fraInput.value;
    const tilVal = tilInput.value;

    if (!fraVal) { fraInput.focus(); return; }

    const now = new Date();
    const [fraH, fraM] = fraVal.split(':').map(Number);
    const [tilH, tilM] = tilVal ? tilVal.split(':').map(Number) : [];

    // Regn ut resultatet for hver obs FØR noe skrives. Gruppen kan spenne over flere
    // datoer, og da sier første obs ingenting om de andre — tidligere validerte vi bare
    // mot første obs, mens klokkeslettet ble skrevet på hver obs sin egen dato. En obs
    // med dagens dato kunne dermed få et tidspunkt frem i tid som AO underkjenner.
    const beregnet = groupItems.map((obs) => {
      const baseDate = obs.timestamp ? new Date(obs.timestamp) : new Date();
      const fraDate = new Date(baseDate);
      fraDate.setHours(fraH, fraM, 0, 0);
      let tilDate = null;
      if (tilVal) {
        tilDate = new Date(baseDate);
        tilDate.setHours(tilH, tilM, 0, 0);
      }
      return { obs, fraDate, tilDate };
    });

    if (beregnet.some((b) => b.fraDate > now)) {
      fraInput.style.borderColor = '#ef4444';
      showToast(`Fra-tid ${fraVal} er frem i tid — AO underkjenner`);
      fraInput.focus();
      return;
    }

    if (beregnet.some((b) => b.tilDate && b.tilDate > now)) {
      tilInput.style.borderColor = '#ef4444';
      showToast(`Til-tid ${tilVal} er frem i tid — AO underkjenner`);
      tilInput.focus();
      return;
    }

    beregnet.forEach(({ obs, fraDate, tilDate }) => {
      obs.timestamp = toLocalISOString(fraDate);
      if (tilDate) {
        obs.tilKlokkeslett = toLocalISOString(tilDate);
      }
    });

    saveState();
    renderObservations(observations, obsListEl, buttons, saveState);
    close();
    showToast(`Klokkeslett satt på ${groupItems.length} obs`);
  });

  fraInput.focus();
}

/**
 * Render observasjoner i tabellvisning
 * @param {Array} observations - Liste med observasjoner
 * @param {HTMLElement} obsListEl - Container-element
 * @param {Object} buttons - Objekt med knapper som skal aktiveres
 * @param {Function} saveState - Callback for å lagre state
 */
export function renderObservations(observations, obsListEl, buttons, saveState) {
  obsListEl.innerHTML = '';

  if (!observations.length) {
    const item = document.createElement('div');
    item.className = 'obs-empty-msg';
    item.textContent = 'Registrerte observasjoner dukker opp her. Start med å velge lokasjon øverst, deretter art.';
    obsListEl.appendChild(item);
    return;
  }

  // Grupper observasjoner etter besøk. Eldre observasjoner uten visitId
  // faller tilbake til ett legacy-besøk per lokalitet.
  const groups = [];
  const indexByKey = new Map();
  
  observations.forEach((obs) => {
    const visitKey = getObservationVisitKey(obs);
    let idx = indexByKey.get(visitKey);
    
    if (idx === undefined) {
      idx = groups.length;
      indexByKey.set(visitKey, idx);
      groups.push({
        key: (obs.placeName && obs.placeName.trim()) || 'Uten stedsnavn',
        visitKey,
        items: [],
      });
    }
    
    groups[idx].items.push(obs);
  });
  
  // Sorter obs alfabetisk på art innenfor hver gruppe
  groups.forEach(group => {
    group.items.sort((a, b) => {
      const an = (a.species && a.species.taxonName) ? a.species.taxonName.toLowerCase() : '';
      const bn = (b.species && b.species.taxonName) ? b.species.taxonName.toLowerCase() : '';
      return an.localeCompare(bn, 'nb');
    });
  });

  const table = document.createElement('table');
  table.className = 'obs-table';

  // Auto table-layout: art-kolonnen (width:100%) tar all ledig plass, mens
  // antall- og handlings-kolonnene krymper til innhold og klumper mot høyre.
  const tbody = document.createElement('tbody');

  groups.forEach((group) => {
    // Finn antall unike arter i denne gruppen
    const uniqueSpecies = new Set(
      group.items
        .map(obs => obs.species && obs.species.taxonName ? obs.species.taxonName.trim().toLowerCase() : null)
        .filter(Boolean)
    );
    const visitLocked = group.items.every(obs => obs.visitLocked);
    // Finn tidligste og seneste klokkeslett i gruppen
    // TODO: Vis også dato ved stedsnavnet når obs spenner over flere dager
    let earliestMs = Infinity;
    let latestMs = -Infinity;
    group.items.forEach(obs => {
      if (obs.timestamp) {
        const t = new Date(obs.timestamp).getTime();
        if (!isNaN(t)) {
          if (t < earliestMs) earliestMs = t;
          if (t > latestMs) latestMs = t;
        }
      }
      // tilKlokkeslett er alltid >= timestamp for samme obs
      const til = obs.tilKlokkeslett || obs.timestamp;
      if (til) {
        const t = new Date(til).getTime();
        if (!isNaN(t) && t > latestMs) latestMs = t;
      }
    });

    const fmt = d => {
      const hh = String(d.getHours()).padStart(2, '0');
      const mm = String(d.getMinutes()).padStart(2, '0');
      return `${hh}:${mm}`;
    };

    let timeSpanText = '';
    if (earliestMs < Infinity && latestMs > -Infinity) {
      const fra = fmt(new Date(earliestMs));
      const til = fmt(new Date(latestMs));
      timeSpanText = fra === til ? fra : `${fra}–${til}`;
    }

    const groupRow = document.createElement('tr');
    groupRow.className = 'obs-group-row';
    const groupCell = document.createElement('td');
    groupCell.colSpan = 3;
    groupCell.className = 'obs-group-title';

    const groupHeader = document.createElement('div');
    groupHeader.className = 'obs-group-header';

    const nameWrap = document.createElement('div');
    nameWrap.className = 'obs-group-name-wrap';

    const nameSpan = document.createElement('span');
    nameSpan.className = 'obs-group-name';
    nameSpan.textContent = group.key;
    nameWrap.appendChild(nameSpan);

    if (timeSpanText) {
      const timeSpan = document.createElement('span');
      timeSpan.className = 'obs-group-time';
      timeSpan.textContent = timeSpanText;
      nameWrap.appendChild(timeSpan);
    }

    const metaSpan = document.createElement('span');
    metaSpan.className = 'obs-group-meta';
    metaSpan.textContent = `${uniqueSpecies.size} art${uniqueSpecies.size === 1 ? '' : 'er'}`;

    nameWrap.appendChild(metaSpan);
    groupHeader.appendChild(nameWrap);

    const groupActions = document.createElement('div');
    groupActions.className = 'obs-group-actions';

    const lockBtn = document.createElement('button');
    lockBtn.type = 'button';
    lockBtn.textContent = visitLocked ? '🔒' : '🔓';
    lockBtn.setAttribute('aria-label', visitLocked ? 'Besøk avsluttet' : 'Besøk åpent');
    lockBtn.title = visitLocked
      ? 'Åpne besøket igjen - nye observasjoner kan legges her'
      : 'Avslutt besøket - nye observasjoner på samme lokalitet starter nytt besøk';
    lockBtn.className = `obs-group-lock-btn${visitLocked ? ' is-locked' : ''}`;
    lockBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      const nextLocked = !visitLocked;
      setVisitLocked(observations, group.visitKey, nextLocked);
      saveState();
      renderObservations(observations, obsListEl, buttons, saveState);
      showToast(nextLocked ? 'Besøk avsluttet' : 'Besøk åpnet igjen', { raw: true });
    });
    groupActions.appendChild(lockBtn);

    // Klokkeikon for å sette tid på alle obs i gruppen
    const clockBtn = document.createElement('button');
    clockBtn.type = 'button';
    // Tydelig SVG-klokke (visere mot 10:10) i stedet for 🕐-emoji, som blir
    // utydelig og plattformavhengig i småformat.
    clockBtn.innerHTML = '<svg viewBox="0 0 24 24" width="19" height="19" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3.2 1.9"/></svg>';
    clockBtn.setAttribute('aria-label', 'Sett klokkeslett');
    clockBtn.title = 'Sett klokkeslett for alle observasjoner på dette stedet';
    clockBtn.className = 'obs-group-time-btn';

    const defaultFra = earliestMs < Infinity ? fmt(new Date(earliestMs)) : '';
    const defaultTil = latestMs > -Infinity ? fmt(new Date(latestMs)) : '';
    const groupItems = group.items;

    clockBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      showTimeModal(groupItems, defaultFra, defaultTil, group.key, observations, obsListEl, buttons, saveState);
    });
    groupActions.appendChild(clockBtn);
    groupHeader.appendChild(groupActions);
    groupCell.appendChild(groupHeader);

    groupRow.appendChild(groupCell);
    tbody.appendChild(groupRow);

    group.items.forEach((obs, obsIndex) => {
      const tr = document.createElement('tr');
      
      // Alternerende bakgrunn (settes på td-er for full bredde)
      const altBg = obsIndex % 2 === 1 ? 'rgba(100,116,139,0.08)' : null;

      // Primærcelle: art (fet) – aktivitet (dempet) på én bred linje.
      // Bedre bruk av bredden enn egne smale kolonner for aktivitet/detaljer.
      const primaryTd = document.createElement('td');
      primaryTd.className = 'obs-cell-primary';

      const primaryLine = document.createElement('div');
      primaryLine.className = 'obs-primary';

      const speciesSpan = document.createElement('span');
      speciesSpan.className = 'obs-species';
      speciesSpan.textContent = obs.species && obs.species.taxonName ? obs.species.taxonName : '';
      primaryLine.appendChild(speciesSpan);

      if (obs.activity) {
        // «– førsteord» bindes sammen (nowrap) så en tankestrek aldri blir
        // stående alene sist på linja; resten av lange aktiviteter kan brytes.
        primaryLine.appendChild(document.createTextNode(' '));
        const words = obs.activity.split(' ');
        const dashUnit = document.createElement('span');
        dashUnit.className = 'obs-activity-inline';
        dashUnit.style.whiteSpace = 'nowrap';
        dashUnit.textContent = `– ${words[0]}`;
        primaryLine.appendChild(dashUnit);
        if (words.length > 1) {
          const rest = document.createElement('span');
          rest.className = 'obs-activity-inline';
          rest.textContent = ' ' + words.slice(1).join(' ');
          primaryLine.appendChild(rest);
        }
      }
      // Skjul-merke (øye med strek) rett etter arten/aktiviteten på hovedlinja,
      // ikke på egen linje – merket alene under ser forlatt ut.
      // Øye-med-strek = ingen andre kan se funnet. (Hengelås er reservert for
      // den kommende tids-lås-funksjonen.)
      if (obs.hideUntil) {
        const parts = obs.hideUntil.split('-'); // YYYY-MM-DD
        const full = parts.length === 3 ? `${parts[2]}.${parts[1]}.${parts[0]}` : obs.hideUntil;
        const badge = document.createElement('span');
        badge.className = 'obs-hide-badge';
        badge.innerHTML = '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>';
        badge.title = `Skjult for offentligheten til ${full}. Ingen andre kan se funnet. Endre via blyant-ikonet.`;
        primaryLine.appendChild(badge);
      }
      primaryTd.appendChild(primaryLine);

      // Underlinje: kun alder/kjønn, og kun når noe faktisk er satt.
      const subParts = [];
      if (obs.age) subParts.push(obs.age);
      if (obs.gender) subParts.push(obs.gender);
      if (subParts.length) {
        const subline = document.createElement('div');
        subline.className = 'obs-subline';
        const meta = document.createElement('span');
        meta.className = 'obs-subline-meta';
        meta.textContent = subParts.join(', ');
        subline.appendChild(meta);
        primaryTd.appendChild(subline);
      }
      tr.appendChild(primaryTd);

      const countTd = document.createElement('td');
      countTd.className = 'obs-cell-count';

      // Render count cell med pluss/minus knapper
      function renderCountCell() {
        countTd.innerHTML = '';
        // Wrapper-div brukes i stedet for direkte flex på td —
        // display:flex på <td> overstyrer table-layout:fixed sine bredder
        const countWrap = document.createElement('div');
        countWrap.style.display = 'flex';
        countWrap.style.alignItems = 'center';

        // Detekter om vi har presis peker (mus/trackpad) vs touch
        const hasFineMouse = window.matchMedia('(pointer: fine) and (hover: hover)').matches;
        const isLargeScreen = window.innerWidth >= 768 && window.innerHeight >= 600;
        const isNarrow = !hasFineMouse && window.innerWidth <= 420;

        // Kompakte, rektangulære knapper gir bedre tabellrytme enn store sirkler.
        const btnWidth = hasFineMouse ? '28px' : isNarrow ? '34px' : '40px';
        const btnHeight = hasFineMouse ? '28px' : isNarrow ? '32px' : '36px';
        const btnFontSize = hasFineMouse ? '1em' : '1.25em';
        countWrap.style.gap = hasFineMouse ? '3px' : isNarrow ? '3px' : '5px';
        // Klyng antall-knappene mot høyre, nær handlingsknappene (mindre dødrom)
        countWrap.style.justifyContent = 'flex-end';

        const btnStyle = {
          width: btnWidth,
          height: btnHeight,
          minWidth: btnWidth,
          minHeight: btnHeight,
          maxWidth: btnWidth,
          maxHeight: btnHeight,
          flexShrink: '0',
          fontSize: btnFontSize,
          fontWeight: '700',
          borderRadius: '8px',
          border: '1px solid rgba(148,163,184,0.34)',
          background: 'rgba(100,116,139,0.10)',
          color: 'var(--text, #e5e7eb)',
          alignItems: 'center',
          justifyContent: 'center',
          cursor: 'pointer',
          userSelect: 'none',
          WebkitTapHighlightColor: 'transparent',
          touchAction: 'manipulation',
          boxSizing: 'border-box',
        };

        const btnStyleWithDisplay = { ...btnStyle, display: 'flex' };

        // Minus 10-knapp (kun på stor skjerm)
        let minus10Btn = null;
        if (isLargeScreen) {
          minus10Btn = document.createElement('button');
          minus10Btn.type = 'button';
          minus10Btn.textContent = '«';
          minus10Btn.title = '−10';
          minus10Btn.className = 'count-btn';
          Object.assign(minus10Btn.style, btnStyleWithDisplay);
          minus10Btn.addEventListener('click', (e) => {
            e.stopPropagation();
            if (obs.count > 10) {
              obs.count -= 10;
            } else {
              obs.count = 1;
            }
            obs.tilKlokkeslett = toLocalISOString(new Date());
            span.textContent = String(obs.count);
            saveState();
          });
        }

        // Minus-knapp
        const minusBtn = document.createElement('button');
        minusBtn.type = 'button';
        minusBtn.textContent = '−';
        minusBtn.title = '−1';
        minusBtn.className = 'count-btn';
        Object.assign(minusBtn.style, btnStyleWithDisplay);
        minusBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          if (obs.count > 1) {
            obs.count--;
            obs.tilKlokkeslett = toLocalISOString(new Date());
            span.textContent = String(obs.count);
            saveState();
          }
        });

        // Tallet
        const span = document.createElement('span');
        span.textContent = obs.count != null ? String(obs.count) : '';
        Object.assign(span.style, {
          cursor: 'pointer',
          minWidth: isNarrow ? '22px' : '36px',
          textAlign: 'center',
          fontSize: isNarrow ? '1.22em' : '1.28em',
          fontWeight: '700',
          lineHeight: '1',
          padding: isNarrow ? '4px 3px' : '4px 6px',
        });
        span.title = 'Klikk for å endre antall';
        span.addEventListener('click', () => {
          showInput();
        });

        // Pluss-knapp
        const plusBtn = document.createElement('button');
        plusBtn.type = 'button';
        plusBtn.textContent = '+';
        plusBtn.title = '+1';
        plusBtn.className = 'count-btn';
        Object.assign(plusBtn.style, btnStyleWithDisplay);
        plusBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          obs.count++;
          obs.tilKlokkeslett = toLocalISOString(new Date());
          span.textContent = String(obs.count);
          saveState();
        });

        // Pluss 10-knapp (kun på stor skjerm)
        let plus10Btn = null;
        if (isLargeScreen) {
          plus10Btn = document.createElement('button');
          plus10Btn.type = 'button';
          plus10Btn.textContent = '»';
          plus10Btn.title = '+10';
          plus10Btn.className = 'count-btn';
          Object.assign(plus10Btn.style, btnStyleWithDisplay);
          plus10Btn.addEventListener('click', (e) => {
            e.stopPropagation();
            obs.count += 10;
            obs.tilKlokkeslett = toLocalISOString(new Date());
            span.textContent = String(obs.count);
            saveState();
          });
        }

        if (minus10Btn) countWrap.appendChild(minus10Btn);
        countWrap.appendChild(minusBtn);
        countWrap.appendChild(span);
        countWrap.appendChild(plusBtn);
        if (plus10Btn) countWrap.appendChild(plus10Btn);
        countTd.appendChild(countWrap);
      }
      
      function showInput() {
        countTd.innerHTML = '';
        const input = document.createElement('input');
        input.type = 'number';
        input.min = '1';
        input.value = obs.count != null ? String(obs.count) : '';
        Object.assign(input.style, {
          width: '48px',
          fontSize: '0.98em',
          padding: '2px 4px',
          margin: '0',
          textAlign: 'center',
        });
        
        function save() {
          const val = input.value.trim();
          const num = parseInt(val, 10);
          if (!val || isNaN(num) || num <= 0) {
            renderCountCell();
            return;
          }
          obs.count = num;
          obs.tilKlokkeslett = toLocalISOString(new Date());
          saveState();
          renderObservations(observations, obsListEl, buttons, saveState);
        }
        
        input.addEventListener('keydown', (e) => {
          if (e.key === 'Enter') {
            save();
          } else if (e.key === 'Escape') {
            renderCountCell();
          }
        });
        input.addEventListener('blur', save);
        countTd.appendChild(input);
        input.focus();
        input.select();
      }
      
      renderCountCell();
      tr.appendChild(countTd);

      const actionTd = document.createElement('td');
      actionTd.className = 'action-td';
      actionTd.style.textAlign = 'center';

      // Edit-knapp
      const globalIndex = observations.indexOf(obs);
      const editBtn = document.createElement('button');
      editBtn.className = 'edit-obs-btn';
      editBtn.textContent = '✏️';
      editBtn.title = 'Rediger observasjon';
      editBtn.addEventListener('click', () => {
        if (globalIndex === -1) return;
        window.location.href = `/public/edit.html?id=${encodeURIComponent(globalIndex)}`;
      });
      actionTd.appendChild(editBtn);

      // Delete-knapp
      const deleteBtn = document.createElement('button');
      deleteBtn.className = 'delete-obs-btn';
      deleteBtn.textContent = '🗑️';
      deleteBtn.title = 'Slett observasjon';
      deleteBtn.style.marginLeft = '4px';
      deleteBtn.addEventListener('click', () => {
        if (globalIndex === -1) return;

        // Lagre slettet observasjon og posisjon for undo
        const deletedObs = observations[globalIndex];
        const deletedIndex = globalIndex;
        const speciesName = deletedObs.species?.taxonName || 'Observasjon';

        // Fjern fra array
        observations.splice(globalIndex, 1);
        renderObservations(observations, obsListEl, buttons, saveState);
        saveState();

        // Vis toast med undo-mulighet
        showToast(`Slettet ${speciesName}`, {
          duration: 5000,
          onUndo: () => {
            // Sett tilbake observasjonen på samme posisjon
            observations.splice(deletedIndex, 0, deletedObs);
            renderObservations(observations, obsListEl, buttons, saveState);
            saveState();
            showToast(`${speciesName} gjenopprettet`);
          }
        });
      });
      actionTd.appendChild(deleteBtn);
      tr.appendChild(actionTd);

      if (altBg) {
        tr.querySelectorAll('td').forEach(td => td.style.background = altBg);
      }
      tbody.appendChild(tr);
    });
  });

  table.appendChild(tbody);
  obsListEl.appendChild(table);

  // Aktiver knapper
  if (buttons.exportBtn) buttons.exportBtn.disabled = false;
  if (buttons.copyBtn) buttons.copyBtn.disabled = false;
  if (buttons.copyOpenBtn) buttons.copyOpenBtn.disabled = false;
  if (buttons.shareBtn) buttons.shareBtn.disabled = false;
  if (buttons.clearBtn) buttons.clearBtn.disabled = false;
  if (buttons.aoDirectBtn) buttons.aoDirectBtn.disabled = false;
}

/**
 * Konverter observasjoner til CSV-format for Artsobservasjoner
 * @param {Array} observations - Liste med observasjoner
 * @returns {string} - CSV-streng
 */
export function toCsv(observations) {
  if (!observations.length) return '';
  
  const SEP = '\t';
  const header = [
    'Artsnavn',
    'Lokalitetsnavn',
    'Superlokalitet',
    'Nord',
    'Øst',
    'Nøyaktighet',
    'Fra dato',
    'Til dato',
    'Fra klokkeslett',
    'Til klokkeslett',
    'Antall',
    'Alder',
    'Kjønn',
    'Aktivitet',
    'Kommentar (synlig for alle)',
    'Privat kommentar (kun synlig for deg selv)',
    'Skjul funn til dato',
    'Medobservatør',
    'Medobservatør',
    'Medobservatør',
    'Medobservatør',
    'Medobservatør',
    'Medobservatør',
    'Medobservatør',
    'Medobservatør',
    'Medobservatør',
    'Medobservatør',
    'Bestemmelsesmetode',
    'Natursystem',
    'Beskriv natursystem',
    'Livsmedium',
    'Beskriv livsmedium',
    'Art som livsmedium',
    'Beskriv art som livsmedium',
    'Dybde min',
    'Dybde maks',
    'Høyde min',
    'Høyde maks',
    'Andrehånds',
    'Usikker artsbestemming',
    'Ikke spontan',
    'Interessant observasjon',
    'Ikke gjenfunnet',
    'Ikke funnet',
    'Offentlig samling',
    'Privat samling',
    'Referansenummer i samling',
    'Beskrivelse artsbestemming',
    'Bestemt av',
    'Bestemt av (fritekst)',
    'Bestemmelsesår',
    'Bekreftet av',
    'Bekreftet av (fritekst)',
    'Bekreftelsesår',
  ];

  const lines = [header.join(SEP)];

  for (const obs of observations) {
    // Kråke: AO har slått sammen kråke og svartkråke – begge heter nå "kråke" i navnebasen.
    // Bruk latinsk navn for å unngå tvetydighet ved import. Fjern HTML-tags fra scientificNameHtml.
    // TODO: Fjern dette unntaket når AO har fikset navnekonflikten (~juli 2026).
    const taxonName = (obs.species && obs.species.taxonName) || '';
    const useLatin = taxonName.toLowerCase() === 'kråke' && obs.species && obs.species.scientificNameHtml;
    const resolvedName = useLatin
      ? obs.species.scientificNameHtml.replace(/<[^>]+>/g, '').trim()
      : taxonName;
    const name = resolvedName.replace(/[;\t]/g, ',');
    // Bruk lokalitets-ID hvis tilgjengelig, ellers navn (unngår tvetydighet ved import)
    const place = (obs.placeId || obs.placeName || '').toString().replace(/[;\t]/g, ',');
    const count = obs.count != null ? String(obs.count) : '';
    const activity = (obs.activity || '').replace(/[;\t]/g, ',');
    const age = (obs.age || '').replace(/[;\t]/g, ',');
    const gender = (obs.gender || '').replace(/[;\t]/g, ',');
    const comment = (obs.comment || '').replace(/[;\t]/g, ',');

    // Dato (Fra/til = samme dag) – format DD.MM.YYYY
    let dateStr = '';
    let timeStr = '';
    
    if (obs.timestamp) {
      const d = new Date(obs.timestamp);
      if (!isNaN(d.getTime())) {
        const dd = String(d.getDate()).padStart(2, '0');
        const mm = String(d.getMonth() + 1).padStart(2, '0');
        const yyyy = d.getFullYear();
        dateStr = `${dd}.${mm}.${yyyy}`;

        // Tidspunkt – format HH:MM (unntatt hvis 00:00, som betyr tid ikke er satt)
        const hh = String(d.getHours()).padStart(2, '0');
        const mi = String(d.getMinutes()).padStart(2, '0');
        if (hh !== '00' || mi !== '00') {
          timeStr = `${hh}:${mi}`;
        }
      }
    }
    // Til klokkeslett (periode)
    let tilTimeStr = '';
    if (obs.tilKlokkeslett) {
      const t = new Date(obs.tilKlokkeslett);
      if (!isNaN(t.getTime())) {
        const hh = String(t.getHours()).padStart(2, '0');
        const mi = String(t.getMinutes()).padStart(2, '0');
        tilTimeStr = `${hh}:${mi}`;
      }
    }
    
    if (!dateStr) {
      const d = new Date();
      const dd = String(d.getDate()).padStart(2, '0');
      const mm = String(d.getMonth() + 1).padStart(2, '0');
      const yyyy = d.getFullYear();
      dateStr = `${dd}.${mm}.${yyyy}`;
    }

    const cols = new Array(54).fill('');
    cols[0] = name;
    cols[1] = place;
    cols[6] = dateStr;
    cols[7] = dateStr;
    cols[8] = timeStr;
    // Kolonne 9: Bruk tilTimeStr hvis det finnes, ellers samme som fra-tid
    cols[9] = tilTimeStr ? tilTimeStr : timeStr;
    cols[10] = count;
    cols[11] = age;
    cols[12] = gender;
    cols[13] = activity;
    cols[14] = comment;

    // Skjul funn til dato (kolonne 16, index 16) — konverter YYYY-MM-DD → DD.MM.YYYY
    if (obs.hideUntil) {
      const parts = obs.hideUntil.split('-');
      if (parts.length === 3) {
        cols[16] = `${parts[2]}.${parts[1]}.${parts[0]}`;
      }
    }

    // Medobservatører (10 kolonner)
    if (Array.isArray(obs.coObservers)) {
      for (let i = 0; i < 10; i++) {
        let v = obs.coObservers[i];
        // Hvis objekt, hent .name, ellers bruk som streng
        if (v && typeof v === 'object') {
          v = v.name || '';
        }
        if (!v || v === 'undefined' || v === null) v = '';
        cols[17 + i] = String(v).replace(/[;\t]/g, ',');
      }
    } else {
      // Fyll med tomme strenger hvis ingen coObservers
      for (let i = 0; i < 10; i++) {
        cols[17 + i] = '';
      }
    }

    lines.push(cols.join(SEP));
  }
  
  return lines.join('\n');
}
