import { describe, it, expect, beforeEach, vi } from 'vitest';

// Mock localStorage før import av storage-modulen
const store = {};
const localStorageMock = {
  getItem: vi.fn((key) => store[key] ?? null),
  setItem: vi.fn((key, value) => { store[key] = String(value); }),
  removeItem: vi.fn((key) => { delete store[key]; }),
};
vi.stubGlobal('localStorage', localStorageMock);

const { appendSentBatch, loadSentBatches, SENT_MAX_DAYS, SENT_MAX_OBS } =
  await import('../../public/js/storage.js');

const SENT_KEY = 'sent_observations_v1';

function obs(navn = 'tårnseiler') {
  return { species: { taxonName: navn }, count: 6, placeName: 'Hylkje', timestamp: '2026-07-26T15:00:00' };
}

function skrivRått(batches) {
  store[SENT_KEY] = JSON.stringify({ version: 1, batches });
}

function dagerSiden(n) {
  return new Date(Date.now() - n * 86400000).toISOString();
}

beforeEach(() => {
  Object.keys(store).forEach((k) => delete store[k]);
  vi.clearAllMocks();
});

describe('appendSentBatch', () => {
  it('returnerer tom logg når ingenting er sendt', () => {
    expect(loadSentBatches()).toEqual([]);
  });

  it('lagrer en sending som kan leses tilbake', () => {
    appendSentBatch([obs('tårnseiler'), obs('gråtrost')]);
    const batches = loadSentBatches();
    expect(batches).toHaveLength(1);
    expect(batches[0].obs).toHaveLength(2);
    expect(batches[0].obs[0].species.taxonName).toBe('tårnseiler');
  });

  it('legger nyeste sending først', () => {
    appendSentBatch([obs('tårnseiler')]);
    appendSentBatch([obs('gråtrost')]);
    const batches = loadSentBatches();
    expect(batches[0].obs[0].species.taxonName).toBe('gråtrost');
  });

  it('tar en kopi, så senere endring av arbeidslista ikke smitter', () => {
    const liste = [obs('tårnseiler')];
    appendSentBatch(liste);
    liste[0].count = 999;
    expect(loadSentBatches()[0].obs[0].count).toBe(6);
  });

  it('ignorerer tom liste', () => {
    appendSentBatch([]);
    appendSentBatch(null);
    expect(loadSentBatches()).toEqual([]);
  });

  it('velter ikke når localStorage er full', () => {
    localStorageMock.setItem.mockImplementationOnce(() => { throw new Error('QuotaExceededError'); });
    expect(() => appendSentBatch([obs()])).not.toThrow();
  });
});

describe('opprydding', () => {
  it('fjerner sendinger eldre enn grensen', () => {
    skrivRått([
      { ts: dagerSiden(1), obs: [obs('fersk')] },
      { ts: dagerSiden(SENT_MAX_DAYS + 1), obs: [obs('gammel')] },
    ]);
    const batches = loadSentBatches();
    expect(batches).toHaveLength(1);
    expect(batches[0].obs[0].species.taxonName).toBe('fersk');
  });

  it('beholder sendinger innenfor grensen', () => {
    skrivRått([{ ts: dagerSiden(SENT_MAX_DAYS - 1), obs: [obs()] }]);
    expect(loadSentBatches()).toHaveLength(1);
  });

  it('kutter når det blir for mange observasjoner totalt', () => {
    const stor = Array.from({ length: SENT_MAX_OBS }, () => obs());
    skrivRått([
      { ts: dagerSiden(0), obs: stor },
      { ts: dagerSiden(1), obs: [obs('faller-ut')] },
    ]);
    const batches = loadSentBatches();
    expect(batches).toHaveLength(1);
    expect(batches[0].obs).toHaveLength(SENT_MAX_OBS);
  });

  it('beholder alltid nyeste sending, selv om den alene er over taket', () => {
    const svær = Array.from({ length: SENT_MAX_OBS + 50 }, () => obs());
    skrivRått([{ ts: dagerSiden(0), obs: svær }]);
    expect(loadSentBatches()).toHaveLength(1);
  });

  it('tåler ødelagte poster uten å kaste', () => {
    skrivRått([{ ts: 'tull', obs: [obs()] }, { obs: null }, { ts: dagerSiden(1), obs: [obs('ok')] }]);
    const batches = loadSentBatches();
    expect(batches).toHaveLength(1);
    expect(batches[0].obs[0].species.taxonName).toBe('ok');
  });

  it('tåler ugyldig JSON i nøkkelen', () => {
    store[SENT_KEY] = '{ikke json';
    expect(loadSentBatches()).toEqual([]);
  });
});
