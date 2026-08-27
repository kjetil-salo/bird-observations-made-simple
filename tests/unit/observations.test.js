import { describe, it, expect, beforeEach, vi } from 'vitest';
import { renderObservations, toCsv } from '../../public/js/observations.js';

beforeEach(() => {
  document.body.innerHTML = '';
  window.matchMedia = window.matchMedia || (() => ({
    matches: false,
    addEventListener: () => {},
    removeEventListener: () => {},
  }));
});

describe('toCsv', () => {
  it('should return empty string for empty observations array', () => {
    const csv = toCsv([]);
    expect(csv).toBe('');
  });

  it('should generate correct CSV header', () => {
    const observations = [{
      species: { taxonName: 'Toppand' },
      placeName: 'Østensjøvannet',
      count: 5,
      activity: 'Rastende',
      age: 'Adult',
      gender: 'Hann',
      comment: 'Fin dag',
      timestamp: '2026-01-22T12:00:00Z',
      tilKlokkeslett: '2026-01-22T13:00:00Z',
      coObservers: []
    }];

    const csv = toCsv(observations);
    const lines = csv.split('\n');

    // Sjekk at første linje er header
    expect(lines[0]).toContain('Artsnavn');
    expect(lines[0]).toContain('Lokalitetsnavn');
    expect(lines[0]).toContain('Nord');
    expect(lines[0]).toContain('Øst');
    expect(lines[0]).toContain('Fra dato');
    expect(lines[0]).toContain('Til dato');
    expect(lines[0]).toContain('Antall');
    expect(lines[0]).toContain('Medobservatør');
  });

  it('should format a single observation correctly', () => {
    const observations = [{
      species: { taxonName: 'Toppand' },
      placeName: 'Østensjøvannet',
      count: 5,
      activity: 'Rastende',
      age: 'Adult',
      gender: 'Hann',
      comment: 'Fin dag',
      timestamp: '2026-01-22T12:30:00Z',
      tilKlokkeslett: '2026-01-22T13:45:00Z',
      coObservers: []
    }];

    const csv = toCsv(observations);
    const lines = csv.split('\n');

    // Linje 2 skal være data (linje 1 er header)
    const dataLine = lines[1];
    const columns = dataLine.split('\t');

    expect(columns[0]).toBe('Toppand');           // Artsnavn
    expect(columns[1]).toBe('Østensjøvannet');    // Lokalitetsnavn
    expect(columns[6]).toMatch(/^\d{2}\.\d{2}\.\d{4}$/); // Fra dato (DD.MM.YYYY)
    expect(columns[7]).toMatch(/^\d{2}\.\d{2}\.\d{4}$/); // Til dato
    expect(columns[8]).toMatch(/^\d{2}:\d{2}$/);  // Fra klokkeslett (HH:MM)
    expect(columns[9]).toMatch(/^\d{2}:\d{2}$/);  // Til klokkeslett
    expect(columns[10]).toBe('5');                // Antall
    expect(columns[11]).toBe('Adult');            // Alder
    expect(columns[12]).toBe('Hann');             // Kjønn
    expect(columns[13]).toBe('Rastende');         // Aktivitet
    expect(columns[14]).toBe('Fin dag');          // Kommentar
  });

  it('should handle missing species gracefully', () => {
    const observations = [{
      species: null,
      placeName: 'Test',
      count: 1,
      timestamp: '2026-01-22T12:00:00Z'
    }];

    const csv = toCsv(observations);
    const lines = csv.split('\n');
    const dataLine = lines[1];
    const columns = dataLine.split('\t');

    expect(columns[0]).toBe(''); // Tom artsnavn
  });

  it('should handle coObservers array correctly', () => {
    const observations = [{
      species: { taxonName: 'Toppand' },
      placeName: 'Østensjøvannet',
      count: 5,
      timestamp: '2026-01-22T12:00:00Z',
      coObservers: [
        { name: 'Ola Nordmann' },
        { name: 'Kari Nordmann' },
        'Per Hansen' // Også støtte for string
      ]
    }];

    const csv = toCsv(observations);
    const lines = csv.split('\n');
    const dataLine = lines[1];
    const columns = dataLine.split('\t');

    // Medobservatører starter på kolonne 17 (index 17)
    expect(columns[17]).toBe('Ola Nordmann');
    expect(columns[18]).toBe('Kari Nordmann');
    expect(columns[19]).toBe('Per Hansen');
  });

  it('should handle special characters in fields', () => {
    const observations = [{
      species: { taxonName: 'Art;med;semikolon' },
      placeName: 'Sted\tmed\ttab',
      comment: 'Kommentar; med, spesialtegn',
      count: 1,
      timestamp: '2026-01-22T12:00:00Z'
    }];

    const csv = toCsv(observations);
    const lines = csv.split('\n');
    const dataLine = lines[1];

    // Spesialtegn skal erstattes med komma
    expect(dataLine).toContain('Art,med,semikolon');
    expect(dataLine).toContain('Sted,med,tab');
    expect(dataLine).toContain('Kommentar, med, spesialtegn');
  });

  it('should use current date if timestamp is missing', () => {
    const observations = [{
      species: { taxonName: 'Toppand' },
      placeName: 'Test',
      count: 1,
      timestamp: null
    }];

    const csv = toCsv(observations);
    const lines = csv.split('\n');
    const dataLine = lines[1];
    const columns = dataLine.split('\t');

    // Skal ha en gyldig dato selv uten timestamp
    expect(columns[6]).toMatch(/^\d{2}\.\d{2}\.\d{4}$/);
    expect(columns[7]).toMatch(/^\d{2}\.\d{2}\.\d{4}$/);
  });

  it('should handle multiple observations', () => {
    const observations = [
      {
        species: { taxonName: 'Toppand' },
        placeName: 'Østensjøvannet',
        count: 5,
        timestamp: '2026-01-22T12:00:00Z'
      },
      {
        species: { taxonName: 'Stokkand' },
        placeName: 'Østensjøvannet',
        count: 3,
        timestamp: '2026-01-22T13:00:00Z'
      },
      {
        species: { taxonName: 'Grågås' },
        placeName: 'Østensjøvannet',
        count: 12,
        timestamp: '2026-01-22T14:00:00Z'
      }
    ];

    const csv = toCsv(observations);
    const lines = csv.split('\n');

    // 1 header + 3 data lines
    expect(lines).toHaveLength(4);

    // Sjekk at alle arter er med
    expect(csv).toContain('Toppand');
    expect(csv).toContain('Stokkand');
    expect(csv).toContain('Grågås');
  });

  it('should handle empty coObservers array', () => {
    const observations = [{
      species: { taxonName: 'Toppand' },
      placeName: 'Test',
      count: 1,
      timestamp: '2026-01-22T12:00:00Z',
      coObservers: []
    }];

    const csv = toCsv(observations);
    const lines = csv.split('\n');
    const dataLine = lines[1];
    const columns = dataLine.split('\t');

    // Medobservatør-kolonner (17-26) skal være tomme
    for (let i = 17; i < 27; i++) {
      expect(columns[i]).toBe('');
    }
  });

  it('should use tilKlokkeslett as end time when provided', () => {
    const observations = [{
      species: { taxonName: 'Toppand' },
      placeName: 'Test',
      count: 1,
      timestamp: '2026-01-22T10:00:00Z',
      tilKlokkeslett: '2026-01-22T12:00:00Z'
    }];

    const csv = toCsv(observations);
    const lines = csv.split('\n');
    const dataLine = lines[1];
    const columns = dataLine.split('\t');

    // Kolonne 8 = fra klokkeslett, kolonne 9 = til klokkeslett
    expect(columns[8]).toMatch(/^\d{2}:\d{2}$/);
    expect(columns[9]).toMatch(/^\d{2}:\d{2}$/);
    expect(columns[8]).not.toBe(columns[9]); // Skal være forskjellige
  });
});

describe('renderObservations besøk', () => {
  it('viser samme tilbake-ikon som hjelpesiden for tidligere besøk', () => {
    const observations = [
      {
        species: { taxonName: 'Heilo' },
        placeName: 'Herdla',
        placeId: 42,
        visitId: 'visit-morgen',
        count: 20,
        activity: 'Overflygende',
        timestamp: '2026-07-03T08:00:00',
      },
    ];
    const obsListEl = document.createElement('div');

    renderObservations(observations, obsListEl, {}, vi.fn());

    const usePlaceBtn = obsListEl.querySelector('.obs-group-place-btn');
    expect(usePlaceBtn.textContent).toBe('↩');
    expect(usePlaceBtn.getAttribute('aria-label')).toBe('Gå tilbake til besøket på Herdla');
  });

  it('låser bare valgt besøk og lar samme lokalitet ha flere besøk', () => {
    const observations = [
      {
        species: { taxonName: 'Heilo' },
        placeName: 'Herdla',
        placeId: 42,
        visitId: 'visit-kveld',
        count: 20,
        activity: 'Overflygende',
        timestamp: '2026-07-03T18:00:00',
      },
      {
        species: { taxonName: 'Heilo' },
        placeName: 'Herdla',
        placeId: 42,
        visitId: 'visit-morgen',
        count: 100,
        activity: 'Næringssøkende',
        timestamp: '2026-07-03T08:00:00',
      },
    ];
    const obsListEl = document.createElement('div');
    const saveState = vi.fn();

    renderObservations(observations, obsListEl, {}, saveState);

    const lockButtons = obsListEl.querySelectorAll('.obs-group-lock-btn');
    expect(lockButtons).toHaveLength(2);

    lockButtons[0].click();

    expect(observations[0].visitLocked).toBe(true);
    expect(observations[1].visitLocked).toBeFalsy();
    expect(saveState).toHaveBeenCalled();
    const updatedLockButtons = obsListEl.querySelectorAll('.obs-group-lock-btn');
    expect(updatedLockButtons[0].textContent).toBe('🔒');
    expect(updatedLockButtons[0].getAttribute('aria-label')).toBe('Besøk avsluttet');
  });
});
