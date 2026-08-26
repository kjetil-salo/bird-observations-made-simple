import { test, expect, Page, Route } from '@playwright/test';
import fs from 'fs';
import path from 'path';

/**
 * Del-dialogen med bilder (Fase F2).
 *
 * `openShareDialog` viser en forhåndsvisning der observasjoner med `photo`
 * får en egen thumbnail + «Del bilde»-avkrysning. Bildet nedskaleres til en
 * liten delings-thumbnail (maks 800px, JPEG q0.6) rett før sending, og
 * strippes helt (ikke bare skjules) hvis brukeren fjerner haken.
 */

const BASE = process.env.BASE_URL || 'http://localhost:3000';

// Liten, gyldig JPEG (40x30 px, generert med Pillow) til bruk som obs.photo.
const TEST_PHOTO = 'data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAUDBAQEAwUEBAQFBQUGBwwIBwcHBw8LCwkMEQ8SEhEPERETFhwXExQaFRERGCEYGh0dHx8fExciJCIeJBweHx7/2wBDAQUFBQcGBw4ICA4eFBEUHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh7/wAARCAAeACgDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDpqKKK+HPmgooooAKKKKACiiigAooooAKKKKAP/9k=';

function obs(taxonName: string, extra: Record<string, unknown> = {}) {
  return {
    species: { taxonName, taxonId: 58482, taxonGroupId: 8 },
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
  await page.evaluate((o) => {
    localStorage.setItem('fugleobservasjoner_v1', JSON.stringify({ version: 1, observations: o }));
  }, observations);
  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(400);

  // Nyhets-splashen legger seg over knappene
  const splash = page.locator('.news-splash-button');
  if (await splash.count()) {
    await splash.click();
    await page.waitForTimeout(200);
  }
}

test.describe('Del-dialog: bilder', () => {
  test.beforeEach(async ({ page }) => {
    // Slå av service worker-registrering for disse testene: appen sin SW
    // (public/sw.js) claimer siden rett etter aktivering, og i WebKit kan
    // ikke page.route intercepte fetch-kall som passerer gjennom en aktiv
    // service worker (Chromium-only CDP-oppførsel). Uten dette blir
    // page.route-testene under upålitelige (race mot SW-installasjon).
    await page.addInitScript(() => {
      if (navigator.serviceWorker) {
        navigator.serviceWorker.register = async () => {
          throw new Error('Service worker avskrudd i test');
        };
      }
    });
    await page.goto(BASE);
  });

  test('observasjon uten bilde vises uten thumbnail/avkrysning (regresjon)', async ({ page }) => {
    await seed(page, [obs('Blåmeis')]);

    await page.locator('#share-btn').click();
    const modal = page.locator('#share-modal');
    await expect(modal).toBeVisible();

    const rad = modal.locator('#share-list > div').first();
    await expect(rad.locator('img')).toHaveCount(0);
    await expect(rad.locator('input[data-photo-idx]')).toHaveCount(0);
    // Kun hovedavkrysningen for observasjonen — ingen ekstra label lagt til
    await expect(rad.locator('label')).toHaveCount(1);
    await expect(rad.locator('input[data-idx="0"]')).toBeChecked();
  });

  test('observasjon med bilde viser thumbnail og forhåndsvalgt «Del bilde»-avkrysning', async ({ page }) => {
    await seed(page, [obs('Blåmeis', { photo: TEST_PHOTO })]);

    await page.locator('#share-btn').click();
    const modal = page.locator('#share-modal');
    await expect(modal).toBeVisible();

    const rad = modal.locator('#share-list > div').first();
    await expect(rad.locator('img')).toHaveCount(1);
    await expect(rad.locator('img')).toHaveAttribute('src', /^data:image\/jpeg;base64,/);

    const photoCb = rad.locator('input[data-photo-idx="0"]');
    await expect(photoCb).toBeChecked();
  });

  test('ingen nøstede <label>-elementer i del-lista', async ({ page }) => {
    await seed(page, [obs('Blåmeis', { photo: TEST_PHOTO }), obs('Kjøttmeis')]);

    await page.locator('#share-btn').click();
    const modal = page.locator('#share-modal');
    await expect(modal).toBeVisible();
    await expect(modal.locator('#share-list input[data-photo-idx]')).toHaveCount(1);

    const nestedLabels = await modal.evaluate((el) => el.querySelectorAll('label label').length);
    expect(nestedLabels).toBe(0);
  });

  test('fjernet «Del bilde»-hake: photo-feltet sendes ikke til /api/share', async ({ page }) => {
    let sentBody: any = null;
    await page.route('**/api/share', async (route: Route) => {
      sentBody = route.request().postDataJSON();
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true, slug: 'test-uten-bilde', url: '/d/test-uten-bilde', deleteKey: 'dk' }),
      });
    });

    await seed(page, [obs('Blåmeis', { photo: TEST_PHOTO })]);

    await page.locator('#share-btn').click();
    const modal = page.locator('#share-modal');
    await expect(modal).toBeVisible();

    await modal.locator('input[data-photo-idx="0"]').uncheck();
    await modal.locator('#share-create').click();
    await expect(modal.locator('#share-url')).toBeVisible({ timeout: 5000 });

    expect(sentBody).not.toBeNull();
    expect(sentBody.observations).toHaveLength(1);
    expect(sentBody.observations[0]).not.toHaveProperty('photo');
  });

  test('avkrysset «Del bilde» (standard): nedskalert bilde sendes til /api/share', async ({ page }) => {
    let sentBody: any = null;
    await page.route('**/api/share', async (route: Route) => {
      sentBody = route.request().postDataJSON();
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true, slug: 'test-med-bilde', url: '/d/test-med-bilde', deleteKey: 'dk' }),
      });
    });

    // Stort testbilde (1000x750) slik at nedskalering til maks 800px faktisk
    // trigger resize-grenen i downscaleForShare, ikke bare kvalitetskutt.
    const storBilde = fs.readFileSync(path.join(__dirname, 'fixtures', 'test-photo.txt'), 'utf-8').trim();
    await seed(page, [obs('Blåmeis', { photo: storBilde })]);

    await page.locator('#share-btn').click();
    const modal = page.locator('#share-modal');
    await expect(modal).toBeVisible();

    // «Del bilde» er avkrysset som standard — ingen ekstra klikk nødvendig
    await modal.locator('#share-create').click();
    await expect(modal.locator('#share-url')).toBeVisible({ timeout: 5000 });

    expect(sentBody).not.toBeNull();
    expect(sentBody.observations).toHaveLength(1);
    expect(sentBody.observations[0].photo).toMatch(/^data:image\/jpeg;base64,/);
    // Nedskalert versjon skal være mindre enn originalen (samme motiv, lavere kvalitet/oppløsning)
    expect(sentBody.observations[0].photo.length).toBeLessThan(storBilde.length);
  });

  test('canvas som kaster henger ikke dialogen — delingen går uten bildet (regresjon)', async ({ page }) => {
    // toDataURL kan kaste på iOS Safari under minnepress. Kastet skjer inne i
    // img.onload, utenfor Promise-executoren, så feilen nådde aldri kallerens
    // try/catch: løftet ble aldri settlet og knappen stod på «Lager lenke…»
    // for godt. Nå skal bildet droppes og delingen fullføres uten det.
    let sentBody: any = null;
    await page.route('**/api/share', async (route: Route) => {
      sentBody = route.request().postDataJSON();
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true, slug: 'test-canvas-feil', url: '/d/test-canvas-feil', deleteKey: 'dk' }),
      });
    });

    await page.addInitScript(() => {
      HTMLCanvasElement.prototype.toDataURL = function () {
        throw new Error('Simulert iOS-minnefeil i toDataURL');
      };
    });

    await seed(page, [obs('Blåmeis', { photo: TEST_PHOTO })]);

    await page.locator('#share-btn').click();
    const modal = page.locator('#share-modal');
    await expect(modal).toBeVisible();

    await modal.locator('#share-create').click();
    // Uten fiksen henger denne til testens timeout
    await expect(modal.locator('#share-url')).toBeVisible({ timeout: 5000 });

    expect(sentBody).not.toBeNull();
    expect(sentBody.observations).toHaveLength(1);
    expect(sentBody.observations[0]).not.toHaveProperty('photo');
  });

  test('observasjon uten bilde påvirkes ikke ved sending (ingen photo-nøkkel)', async ({ page }) => {
    let sentBody: any = null;
    await page.route('**/api/share', async (route: Route) => {
      sentBody = route.request().postDataJSON();
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true, slug: 'test-ingen-bilde', url: '/d/test-ingen-bilde', deleteKey: 'dk' }),
      });
    });

    await seed(page, [obs('Blåmeis')]);

    await page.locator('#share-btn').click();
    const modal = page.locator('#share-modal');
    await expect(modal).toBeVisible();

    await modal.locator('#share-create').click();
    await expect(modal.locator('#share-url')).toBeVisible({ timeout: 5000 });

    expect(sentBody).not.toBeNull();
    expect(sentBody.observations).toHaveLength(1);
    expect(sentBody.observations[0]).not.toHaveProperty('photo');
  });
});
