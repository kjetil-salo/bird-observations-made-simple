import { describe, it, expect } from 'vitest';

const { sortLocationAutocompleteResults } = await import('../../public/js/autocomplete.js');

describe('sortLocationAutocompleteResults', () => {
  it('sorterer egne private før superlokasjoner og offentlige treff', () => {
    const results = sortLocationAutocompleteResults([
      { value: 'Andres private', isPrivate: true },
      { value: 'Offentlig' },
      { value: 'Min private', isPrivate: true, ColorString: '#ffff00' },
      { value: 'Super', isSuper: true },
    ]);

    expect(results.map(r => r.value)).toEqual([
      'Min private',
      'Super',
      'Offentlig',
      'Andres private',
    ]);
  });

  it('sorterer på avstand innen samme gruppe', () => {
    const results = sortLocationAutocompleteResults([
      { value: 'Langt borte', _distance: 300 },
      { value: 'Nært', _distance: 20 },
    ]);

    expect(results.map(r => r.value)).toEqual(['Nært', 'Langt borte']);
  });
});
