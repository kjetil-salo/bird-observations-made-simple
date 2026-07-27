import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock avhengigheter før import
vi.mock('../../public/js/api.js', () => ({
  fetchAoSites: vi.fn(),
  getCachedPrivateSites: vi.fn(() => []),
  ensureAoTokens: vi.fn(),
  createAoSite: vi.fn(),
}));
vi.mock('../../public/js/ui.js', () => ({
  setLocationStatus: vi.fn(),
  haversine: vi.fn((lat1, lon1, lat2, lon2) => {
    // Forenklet avstandsberegning for test (meter)
    const dlat = (lat2 - lat1) * 111320;
    const dlon = (lon2 - lon1) * 111320 * Math.cos(lat1 * Math.PI / 180);
    return Math.sqrt(dlat * dlat + dlon * dlon);
  }),
}));

const { isPrivateSite, getSiteLabel, setAoSiteSuggestions, openMap } = await import('../../public/js/location.js');

// ─── isPrivateSite ────────────────────────────────────────────

describe('isPrivateSite', () => {
  it('should return false for null/undefined', () => {
    expect(isPrivateSite(null)).toBe(false);
    expect(isPrivateSite(undefined)).toBe(false);
  });

  it('should return false for non-object', () => {
    expect(isPrivateSite('string')).toBe(false);
    expect(isPrivateSite(42)).toBe(false);
  });

  it('should return true for isPrivate=true', () => {
    expect(isPrivateSite({ isPrivate: true })).toBe(true);
  });

  it('should return true for isPrivate="true" (string)', () => {
    expect(isPrivateSite({ isPrivate: 'true' })).toBe(true);
  });

  it('should return false for isPrivate=false', () => {
    expect(isPrivateSite({ isPrivate: false })).toBe(false);
  });

  it('should return false for isPrivate="false" (string)', () => {
    expect(isPrivateSite({ isPrivate: 'false' })).toBe(false);
  });

  it('should check IsPrivate (stor I) som fallback', () => {
    expect(isPrivateSite({ IsPrivate: true })).toBe(true);
    expect(isPrivateSite({ IsPrivate: 'true' })).toBe(true);
    expect(isPrivateSite({ IsPrivate: false })).toBe(false);
  });

  it('should check raw.isPrivate nested', () => {
    expect(isPrivateSite({ raw: { isPrivate: true } })).toBe(true);
    expect(isPrivateSite({ raw: { isPrivate: false } })).toBe(false);
  });

  it('should return false when no isPrivate property', () => {
    expect(isPrivateSite({ name: 'Østensjøvannet' })).toBe(false);
  });

  it('should prioritize isPrivate over IsPrivate', () => {
    expect(isPrivateSite({ isPrivate: false, IsPrivate: true })).toBe(false);
  });
});

// ─── getSiteLabel ─────────────────────────────────────────────

describe('getSiteLabel', () => {
  it('should return empty string for null/undefined', () => {
    expect(getSiteLabel(null)).toBe('');
    expect(getSiteLabel(undefined)).toBe('');
  });

  it('should return empty string for non-object', () => {
    expect(getSiteLabel('string')).toBe('');
    expect(getSiteLabel(42)).toBe('');
  });

  it('should return name from site', () => {
    expect(getSiteLabel({ name: 'Østensjøvannet' })).toBe('Østensjøvannet');
  });

  it('should trim whitespace', () => {
    expect(getSiteLabel({ name: '  Sognsvann  ' })).toBe('Sognsvann');
  });

  it('should return empty string for blank name', () => {
    expect(getSiteLabel({ name: '   ' })).toBe('');
  });

  it('should fall back to raw.name', () => {
    expect(getSiteLabel({ raw: { name: 'Maridalsvannet' } })).toBe('Maridalsvannet');
  });

  it('should prefer site.name over raw.name', () => {
    expect(getSiteLabel({ name: 'Direkte', raw: { name: 'Fra raw' } })).toBe('Direkte');
  });

  it('should return empty string for empty object', () => {
    expect(getSiteLabel({})).toBe('');
  });
});

// ─── openMap ──────────────────────────────────────────────────

describe('openMap', () => {
  let openSpy;

  beforeEach(() => {
    openSpy = vi.fn();
    vi.stubGlobal('open', openSpy);
  });

  it('should not open window for null position', () => {
    openMap(null);
    expect(openSpy).not.toHaveBeenCalled();
  });

  it('should not open window for undefined position', () => {
    openMap(undefined);
    expect(openSpy).not.toHaveBeenCalled();
  });

  it('should open map (Google Maps for desktop) with correct coordinates', () => {
    openMap({ lat: 59.9139, lon: 10.7522 });
    expect(openSpy).toHaveBeenCalledOnce();

    const url = openSpy.mock.calls[0][0];
    expect(url).toContain('google.com/maps');
    expect(url).toContain('59.9139');
    expect(url).toContain('10.7522');
  });

  it('should open in new tab with noopener', () => {
    openMap({ lat: 60, lon: 11 });
    expect(openSpy).toHaveBeenCalledWith(expect.any(String), '_blank', 'noopener');
  });
});

// ─── setAoSiteSuggestions ─────────────────────────────────────

describe('setAoSiteSuggestions', () => {
  let dropdown, aoSitesEl, placeInput, setCurrentPlace;

  beforeEach(() => {
    dropdown = document.createElement('div');
    aoSitesEl = document.createElement('div');
    placeInput = document.createElement('input');
    setCurrentPlace = vi.fn();
  });

  it('should return empty array for null sites', () => {
    const result = setAoSiteSuggestions(null, { lat: 59.9, lon: 10.7 }, dropdown, aoSitesEl, placeInput, setCurrentPlace);
    expect(result).toEqual([]);
  });

  it('should hide dropdown and show message for empty sites', () => {
    setAoSiteSuggestions([], { lat: 59.9, lon: 10.7 }, dropdown, aoSitesEl, placeInput, setCurrentPlace);
    expect(dropdown.style.display).toBe('none');
    expect(aoSitesEl.textContent).toContain('Ingen lokasjoner');
  });

  it('should return original sites if no dropdown element', () => {
    const sites = [{ name: 'Østensjøvannet', lat: 59.9, lon: 10.8 }];
    const result = setAoSiteSuggestions(sites, null, null, aoSitesEl, placeInput, setCurrentPlace);
    expect(result).toEqual(sites);
  });

  it('should render site suggestions in dropdown', () => {
    const sites = [
      { name: 'Østensjøvannet', lat: 59.91, lon: 10.81 },
      { name: 'Sognsvann', lat: 59.97, lon: 10.73 }
    ];

    setAoSiteSuggestions(sites, { lat: 59.9, lon: 10.7 }, dropdown, aoSitesEl, placeInput, setCurrentPlace);

    // 1 tom "Velg lokasjon" + 2 sites
    expect(dropdown.children).toHaveLength(3);
    expect(dropdown.children[0].textContent).toBe('Velg lokasjon...');
  });

  it('should sort superlokasjoner first', () => {
    const sites = [
      { name: 'Vanlig sted', lat: 59.91, lon: 10.81 },
      { name: 'Superlokasjon', lat: 59.92, lon: 10.82, isSuper: true }
    ];

    setAoSiteSuggestions(sites, { lat: 59.9, lon: 10.7 }, dropdown, aoSitesEl, placeInput, setCurrentPlace);

    // children[0] er "Velg lokasjon...", children[1] er første site
    expect(dropdown.children[1].textContent).toContain('Superlokasjon');
  });

  it('should sort public before private', () => {
    const sites = [
      { name: 'Privat sted', lat: 59.91, lon: 10.81, isPrivate: true },
      { name: 'Offentlig sted', lat: 59.91, lon: 10.81, isPrivate: false }
    ];

    setAoSiteSuggestions(sites, { lat: 59.9, lon: 10.7 }, dropdown, aoSitesEl, placeInput, setCurrentPlace);

    expect(dropdown.children[1].textContent).toContain('Offentlig sted');
    expect(dropdown.children[2].textContent).toContain('Privat sted');
  });

  it('should sort egne private (isMine) before andres private', () => {
    const sites = [
      { name: 'Andres private', lat: 59.91, lon: 10.81, isPrivate: true, isMine: false },
      { name: 'Min private', lat: 59.91, lon: 10.81, isPrivate: true, isMine: true }
    ];

    setAoSiteSuggestions(sites, { lat: 59.9, lon: 10.7 }, dropdown, aoSitesEl, placeInput, setCurrentPlace);

    expect(dropdown.children[1].textContent).toContain('Min private');
    expect(dropdown.children[2].textContent).toContain('Andres private');
  });

  it('should sort: super → offentlig → egne private → andres private', () => {
    const sites = [
      { name: 'Andres private', lat: 59.91, lon: 10.81, isPrivate: true },
      { name: 'Offentlig', lat: 59.91, lon: 10.81 },
      { name: 'Min private', lat: 59.91, lon: 10.81, isPrivate: true, isMine: true },
      { name: 'Super', lat: 59.91, lon: 10.81, isSuper: true }
    ];

    setAoSiteSuggestions(sites, { lat: 59.9, lon: 10.7 }, dropdown, aoSitesEl, placeInput, setCurrentPlace);

    const names = Array.from(dropdown.children).slice(1).map(el => el.textContent);
    expect(names[0]).toContain('Super');
    expect(names[1]).toContain('Offentlig');
    expect(names[2]).toContain('Min private');
    expect(names[3]).toContain('Andres private');
  });

  it('should sort by distance (nearest first)', () => {
    const sites = [
      { name: 'Langt borte', lat: 60.5, lon: 11.0 },
      { name: 'Nært', lat: 59.91, lon: 10.71 }
    ];

    setAoSiteSuggestions(sites, { lat: 59.9, lon: 10.7 }, dropdown, aoSitesEl, placeInput, setCurrentPlace);

    expect(dropdown.children[1].textContent).toContain('Nært');
    expect(dropdown.children[2].textContent).toContain('Langt borte');
  });

  it('should show distance in meters for short distances', () => {
    const sites = [
      { name: 'Nært sted', lat: 59.9005, lon: 10.7005 }
    ];

    setAoSiteSuggestions(sites, { lat: 59.9, lon: 10.7 }, dropdown, aoSitesEl, placeInput, setCurrentPlace);

    expect(dropdown.children[1].textContent).toMatch(/\d+ m\)/);
  });

  it('should show distance in km for long distances', () => {
    const sites = [
      { name: 'Langt sted', lat: 60.5, lon: 11.5 }
    ];

    setAoSiteSuggestions(sites, { lat: 59.9, lon: 10.7 }, dropdown, aoSitesEl, placeInput, setCurrentPlace);

    expect(dropdown.children[1].textContent).toMatch(/[\d.]+ km\)/);
  });

  it('should prefix superlokasjoner with emoji', () => {
    const sites = [
      { name: 'Superlokasjon', lat: 59.91, lon: 10.81, isSuper: true }
    ];

    setAoSiteSuggestions(sites, { lat: 59.9, lon: 10.7 }, dropdown, aoSitesEl, placeInput, setCurrentPlace);

    expect(dropdown.children[1].textContent).toContain('🏷️');
  });

  it('should show kommune from AO-respons under lokalitetsnavnet', () => {
    const sites = [
      { name: 'Storevatnet', lat: 59.91, lon: 10.81, raw: { municipalityName: 'Bergen' } }
    ];

    setAoSiteSuggestions(sites, { lat: 59.9, lon: 10.7 }, dropdown, aoSitesEl, placeInput, setCurrentPlace);

    expect(dropdown.children[1].textContent).toContain('Bergen');
  });

  it('should show kommune from lokal DB', () => {
    const sites = [
      { name: 'Storevatnet', lat: 59.91, lon: 10.81, municipality: 'Askøy' }
    ];

    setAoSiteSuggestions(sites, { lat: 59.9, lon: 10.7 }, dropdown, aoSitesEl, placeInput, setCurrentPlace);

    expect(dropdown.children[1].textContent).toContain('Askøy');
  });

  it('should not break when kommune is missing', () => {
    const sites = [
      { name: 'Uten kommune', lat: 59.91, lon: 10.81 }
    ];

    setAoSiteSuggestions(sites, { lat: 59.9, lon: 10.7 }, dropdown, aoSitesEl, placeInput, setCurrentPlace);

    expect(dropdown.children[1].textContent).toContain('Uten kommune');
  });

  it('should prefix private sites with lock emoji', () => {
    const sites = [
      { name: 'Privat', lat: 59.91, lon: 10.81, isPrivate: true }
    ];

    setAoSiteSuggestions(sites, { lat: 59.9, lon: 10.7 }, dropdown, aoSitesEl, placeInput, setCurrentPlace);

    expect(dropdown.children[1].textContent).toContain('👤');
  });

  it('should limit to 20 sites', () => {
    const sites = Array.from({ length: 30 }, (_, i) => ({
      name: `Sted ${i}`, lat: 59.9 + i * 0.001, lon: 10.7
    }));

    setAoSiteSuggestions(sites, { lat: 59.9, lon: 10.7 }, dropdown, aoSitesEl, placeInput, setCurrentPlace);

    // 1 "Velg lokasjon" + 20 sites
    expect(dropdown.children).toHaveLength(21);
  });

  it('should filter out sites without name', () => {
    const sites = [
      { name: '', lat: 59.91, lon: 10.81 },
      { name: 'Gyldig', lat: 59.92, lon: 10.82 },
      { lat: 59.93, lon: 10.83 }
    ];

    setAoSiteSuggestions(sites, { lat: 59.9, lon: 10.7 }, dropdown, aoSitesEl, placeInput, setCurrentPlace);

    // 1 "Velg lokasjon" + 1 gyldig
    expect(dropdown.children).toHaveLength(2);
    expect(dropdown.children[1].textContent).toContain('Gyldig');
  });

  it('should set place name on click', () => {
    const sites = [
      { name: 'Østensjøvannet', lat: 59.91, lon: 10.81 }
    ];

    setAoSiteSuggestions(sites, { lat: 59.9, lon: 10.7 }, dropdown, aoSitesEl, placeInput, setCurrentPlace);

    // Klikk på textSpan-elementet (første child av site-elementet)
    const siteElement = dropdown.children[1];
    const textSpan = siteElement.querySelector('.ao-site-text');
    textSpan.click();

    expect(setCurrentPlace).toHaveBeenCalledWith('Østensjøvannet', null);
    expect(placeInput.value).toBe('Østensjøvannet');
    expect(placeInput.dataset.autofilled).toBe('true');
    expect(dropdown.style.display).toBe('none');
  });

  it('should handle missing position gracefully', () => {
    const sites = [
      { name: 'Sted', lat: 59.91, lon: 10.81 }
    ];

    setAoSiteSuggestions(sites, null, dropdown, aoSitesEl, placeInput, setCurrentPlace);

    // Skal fortsatt rendre, men uten avstand
    expect(dropdown.children.length).toBeGreaterThan(1);
    expect(aoSitesEl.textContent).toContain('posisjon');
  });
});
