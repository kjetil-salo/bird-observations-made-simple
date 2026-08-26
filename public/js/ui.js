/**
 * UI-modul for generelle UI-funksjoner
 */

/**
 * Flash en knapp med suksessmelding
 * @param {HTMLElement} button - Knappen som skal flashe
 * @param {string} successLabel - Teksten som skal vises
 */
export function flashButton(button, successLabel) {
  if (!button) return;
  
  const labelSpan = button.querySelector('span:last-child');
  if (!labelSpan) return;
  
  const originalText = labelSpan.textContent;
  button.classList.add('btn-success');
  labelSpan.textContent = successLabel;
  
  setTimeout(() => {
    labelSpan.textContent = originalText;
    button.classList.remove('btn-success');
  }, 1200);
}

/**
 * Vis toast-melding
 * @param {string} msg - Meldingen som skal vises
 * @param {Object} options - Valgfrie alternativer
 * @param {Function} options.onUndo - Callback for undo-knapp
 * @param {number} options.duration - Varighet i ms (default: 1500)
 * @param {boolean} options.raw - Vis meldingen uten automatisk "registrert"-suffix
 * @param {string} options.borderColor - Overstyr rammefargen (f.eks. advarsel)
 */
export function showToast(msg, options = {}) {
  const { onUndo, duration = 1500, raw = false, borderColor = null } = options;

  let toast = document.getElementById('registered-toast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'registered-toast';
    toast.style.cssText = `
      position: fixed;
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%) scale(0.7);
      background: ${document.body.classList.contains('theme-light') ? 'rgba(255,255,255,0.97)' : 'rgba(34,34,34,0.97)'};
      color: ${document.body.classList.contains('theme-light') ? '#1a1a1a' : '#fff'};
      font-size: 1.2em;
      padding: 12px 28px;
      border-radius: 12px;
      border: 2px solid #3b82f6;
      z-index: 9999;
      opacity: 0;
      transition: all 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);
      display: flex;
      align-items: center;
      gap: 16px;
      pointer-events: none;
    `;
    document.body.appendChild(toast);
  }

  // Clear existing content
  toast.innerHTML = '';

  // Sett tekst og border
  const textSpan = document.createElement('span');
  if (raw) {
    textSpan.textContent = msg;
    toast.style.borderColor = '#3b82f6';
  } else if (typeof msg === 'string' && msg.startsWith('Du må')) {
    textSpan.textContent = msg;
    toast.style.borderColor = '#ef4444';
  } else if (typeof msg === 'string' && msg.startsWith('Slettet')) {
    textSpan.textContent = msg;
    toast.style.borderColor = '#f59e0b';
  } else {
    textSpan.textContent = `${msg} registrert`;
    toast.style.borderColor = '#22c55e';
  }
  // Lar kalleren markere en advarsel (gul) uten å måtte gjette på tekstprefiks
  if (borderColor) toast.style.borderColor = borderColor;
  toast.appendChild(textSpan);

  // Legg til undo-knapp hvis onUndo er gitt
  let undoBtn = null;
  if (onUndo) {
    undoBtn = document.createElement('button');
    undoBtn.textContent = 'Angre';
    undoBtn.style.cssText = `
      background: rgba(255,255,255,0.2);
      border: 1px solid rgba(255,255,255,0.3);
      color: #fff;
      padding: 4px 12px;
      border-radius: 6px;
      cursor: pointer;
      font-size: 0.9em;
      font-weight: 600;
      transition: all 0.15s;
      pointer-events: auto;
    `;
    undoBtn.addEventListener('mousedown', () => {
      undoBtn.style.background = 'rgba(255,255,255,0.3)';
    });
    undoBtn.addEventListener('mouseup', () => {
      undoBtn.style.background = 'rgba(255,255,255,0.2)';
    });
    undoBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      onUndo();
      // Skjul toast umiddelbart
      toast.style.opacity = '0';
      toast.style.transform = 'translate(-50%, -50%) scale(0.95)';
    });
    toast.appendChild(undoBtn);
  }

  // Plasser toasten midt i synlig viewport (over skjermtastatur)
  if (window.visualViewport) {
    const vv = window.visualViewport;
    const topPx = vv.offsetTop + vv.height / 2;
    toast.style.top = topPx + 'px';
  } else {
    toast.style.top = '30%';
  }

  // Reset
  toast.style.transform = 'translate(-50%, -50%) scale(0.7)';
  toast.style.opacity = '0';
  toast.style.boxShadow = '0 0 0 0px rgba(34, 197, 94, 0)';

  // Trigger animasjon på neste frame
  requestAnimationFrame(() => {
    toast.style.transform = 'translate(-50%, -50%) scale(1)';
    toast.style.opacity = '1';
    toast.style.boxShadow = '0 0 0 20px rgba(34, 197, 94, 0), 0 8px 32px rgba(0,0,0,0.3)';
  });

  // Fade ut
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translate(-50%, -50%) scale(0.95)';
    setTimeout(() => {
      toast.style.borderColor = '#3b82f6';
    }, 400);
  }, duration);
}

/**
 * Sett status på søkefelt
 * @param {HTMLElement} statusDot - Status-prikk element
 * @param {HTMLElement} statusText - Status-tekst element
 * @param {string} mode - Modus: 'idle', 'loading', 'error'
 * @param {string} text - Teksten som skal vises
 */
export function setStatus(statusDot, statusText, mode, text, html) {
  if (html) {
    statusText.innerHTML = html;
  } else {
    statusText.textContent = text;
  }
  
  if (mode === 'idle') {
    statusDot.style.background = '#22c55e';
    statusDot.style.boxShadow = '0 0 0 6px rgba(34, 197, 94, 0.16)';
  } else if (mode === 'loading') {
    statusDot.style.background = '#fbbf24';
    statusDot.style.boxShadow = '0 0 0 6px rgba(251, 191, 36, 0.24)';
  } else {
    statusDot.style.background = '#ef4444';
    statusDot.style.boxShadow = '0 0 0 6px rgba(239, 68, 68, 0.27)';
  }
}

/**
 * Sett lokasjonsstatus
 * @param {HTMLElement} locDot - Lokasjon-prikk element
 * @param {HTMLElement} locText - Lokasjon-tekst element
 * @param {string} mode - Modus: 'ok', 'error', 'idle', 'pending'
 * @param {string} text - Teksten som skal vises
 */
export function setLocationStatus(locDot, locText, mode, text) {
  let displayText = text;

  if (locText) {
    // Legg til klokkeslett kun når ferdig (ok) eller feilet (error), ikke under lasting (pending)
    if (mode === 'ok' || mode === 'error') {
      const now = new Date();
      const timeStr = now.toLocaleTimeString('nb-NO', { hour: '2-digit', minute: '2-digit' });
      displayText = `${text} (kl ${timeStr})`;
    }
    locText.textContent = displayText;
    if (mode !== 'ok') {
      locText.removeAttribute('title');
    }
  }

  // Lagre status til localStorage for å bevare ved navigasjon
  try {
    localStorage.setItem('locationStatus', JSON.stringify({ mode, text: displayText }));
  } catch (e) {
    // Ignorer localStorage-feil
  }

  if (!locDot) return;

  if (mode === 'ok') {
    locDot.style.background = '#22c55e';
  } else if (mode === 'error') {
    locDot.style.background = '#ef4444';
  } else {
    locDot.style.background = '#6b7280';
  }
}

/**
 * Haversine-formel for å beregne avstand mellom to koordinater
 * @param {number} lat1 - Breddegrad 1
 * @param {number} lon1 - Lengdegrad 1
 * @param {number} lat2 - Breddegrad 2
 * @param {number} lon2 - Lengdegrad 2
 * @returns {number} - Avstand i meter
 */
// Re-eksporter haversine fra utils for bakoverkompatibilitet
export { haversine } from './utils.js';
