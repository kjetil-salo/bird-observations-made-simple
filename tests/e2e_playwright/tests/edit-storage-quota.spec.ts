import { test, expect, Page } from '@playwright/test';

/**
 * v1.43.8: lagringsfeil (full localStorage-kvote) skal varsles i stedet for å
 * forsvinne stille på rediger-siden (public/edit.html).
 *
 * saveObservations() i storage.js returnerer nå true/false for om
 * localStorage.setItem() faktisk lyktes. edit.html sin lagre-handler bruker
 * dette til å: (1) prøve på nytt uten bilde hvis lagring feilet og obs hadde
 * bilde, (2) varsle brukeren i begge feil-tilfeller, (3) IKKE navigere bort
 * hvis lagring fortsatt feiler etter retry.
 */

const BASE = process.env.BASE_URL || 'http://localhost:3000';
const STORAGE_KEY = 'fugleobservasjoner_v1';

// Stor, men gyldig, "bilde"-verdi — vi trenger ikke et ekte JPEG, bare noe som
// gjør at payload-strengen krysser terskelen vi later som er kvoten.
const BIG_FAKE_PHOTO = 'data:image/jpeg;base64,' + 'A'.repeat(60000);

function obs(extra: Record<string, unknown> = {}) {
  return {
    species: { taxonName: 'Blåmeis', taxonId: 5968, taxonGroupId: 8 },
    count: 2,
    placeName: 'Teststed',
    placeId: null,
    position: null,
    activity: 'Stasjonær',
    timestamp: '2026-07-26T15:00:00',
    age: '',
    gender: '',
    coObservers: [],
    ...extra,
  };
}

async function seed(page: Page, observations: object[]) {
  await page.evaluate(
    ({ key, o }) => {
      localStorage.setItem(key, JSON.stringify({ version: 1, observations: o }));
    },
    { key: STORAGE_KEY, o: observations },
  );
}

/**
 * Overstyrer localStorage.setItem slik at den kaster en
 * QuotaExceededError-lignende DOMException når payload-strengen er over en
 * gitt terskel (simulerer at et stort base64-bilde sprenger kvoten), men
 * lykkes (kaller den ekte setItem) under terskelen.
 */
async function mockQuotaAboveThreshold(page: Page, thresholdBytes: number) {
  await page.addInitScript((threshold) => {
    const orig = window.localStorage.setItem.bind(window.localStorage);
    window.localStorage.setItem = function (key: string, value: string) {
      if (key === 'fugleobservasjoner_v1' && value.length > threshold) {
        const err = new DOMException('Kvote overskredet (simulert)', 'QuotaExceededError');
        throw err;
      }
      return orig(key, value);
    };
  }, thresholdBytes);
}

/** Overstyrer localStorage.setItem slik at den ALLTID kaster for observasjonsnøkkelen. */
async function mockQuotaAlwaysFails(page: Page) {
  await page.addInitScript(() => {
    window.localStorage.setItem = function (key: string) {
      if (key === 'fugleobservasjoner_v1') {
        throw new DOMException('Kvote overskredet (simulert)', 'QuotaExceededError');
      }
    };
  });
}

async function gotoEdit(page: Page, id = 0) {
  const dialogs: string[] = [];
  page.on('dialog', async (d) => {
    dialogs.push(d.message());
    await d.accept();
  });
  await page.goto(`${BASE}/public/edit.html?id=${id}`);
  return dialogs;
}

test.describe('edit.html: lagringsfeil ved full localStorage-kvote', () => {
  test.beforeEach(async ({ page }) => {
    // Samme SW-avskruing som share.spec.ts — unngår at page.route/init-script
    // racer mot en aktiv service worker.
    await page.addInitScript(() => {
      if (navigator.serviceWorker) {
        navigator.serviceWorker.register = async () => {
          throw new Error('Service worker avskrudd i test');
        };
      }
    });
  });

  test('normalt tilfelle (regresjon): lagring uten kvoteproblem fungerer som før', async ({ page }) => {
    await page.goto(BASE);
    await seed(page, [obs()]);

    const dialogs = await gotoEdit(page);
    await page.locator('#f-comment').fill('Ny kommentar uten kvoteproblem');
    await page.locator('button[type="submit"]').click();
    await page.waitForURL(/index\.html/, { timeout: 3000 });

    expect(dialogs).toHaveLength(0);
    const raw = await page.evaluate((k) => localStorage.getItem(k), STORAGE_KEY);
    const saved = JSON.parse(raw as string);
    expect(saved.observations[0].comment).toBe('Ny kommentar uten kvoteproblem');
  });

  test('kvotefeil med bilde: faller tilbake til lagring uten bilde og varsler', async ({ page }) => {
    // Seed FØR mocken registreres — addInitScript slår først inn fra NESTE
    // navigasjon, men uten denne rekkefølgen ville selve seedingen (som også
    // går via localStorage.setItem, med det store bildet i payload) kastet.
    await page.goto(BASE);
    await seed(page, [obs({ photo: BIG_FAKE_PHOTO, comment: 'Original kommentar' })]);

    // Terskel mellom «uten bilde»-payload og «med bilde»-payload.
    await mockQuotaAboveThreshold(page, 5000);

    const dialogs = await gotoEdit(page);
    await page.locator('#f-comment').fill('Endret kommentar etter kvotefeil');
    await page.locator('button[type="submit"]').click();
    await page.waitForURL(/index\.html/, { timeout: 3000 });

    expect(dialogs).toHaveLength(1);
    expect(dialogs[0]).toContain('Bildet var for stort til å lagres');

    const raw = await page.evaluate((k) => localStorage.getItem(k), STORAGE_KEY);
    const saved = JSON.parse(raw as string);
    expect(saved.observations[0].photo).toBeUndefined();
    expect(saved.observations[0].comment).toBe('Endret kommentar etter kvotefeil');
  });

  test('vedvarende kvotefeil (uten bilde eller selv uten hjelper): varsler og navigerer IKKE bort', async ({ page }) => {
    await page.goto(BASE);
    // Seed FØR mocken slås på, slik at siden i det hele tatt klarer å laste
    // observasjonen (mocken slår kun inn på setItem, ikke getItem).
    await seed(page, [obs({ comment: 'Uendret kommentar' })]);
    await mockQuotaAlwaysFails(page);

    const dialogs = await gotoEdit(page);
    await page.locator('#f-comment').fill('Denne skal aldri lagres');
    await page.locator('button[type="submit"]').click();
    await page.waitForTimeout(800);

    expect(page.url()).toContain('edit.html');
    expect(dialogs).toHaveLength(1);
    expect(dialogs[0]).toContain('Kunne ikke lagre endringene');
  });
});
