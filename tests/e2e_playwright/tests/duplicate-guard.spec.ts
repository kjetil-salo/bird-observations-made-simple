import { test, expect, Page } from '@playwright/test';

/**
 * Dublett-vern ved publisering.
 *
 * Lista tømmes ikke automatisk etter sending. Svarer brukeren nei på «tøm lista?»
 * og registrerer nye funn senere, ville et nytt trykk sendt de gamle på nytt — og
 * de blir liggende dobbelt i AO. Advarselen skal være stille når alt er nytt.
 */

const BASE = process.env.BASE_URL || 'http://localhost:3000';

function obs(taxonName: string, sentTs?: string) {
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
    ...(sentTs ? { sentTs } : {}),
  };
}

async function seed(page: Page, observations: object[]) {
  await page.evaluate((o) => {
    localStorage.setItem('fugleobservasjoner_v1', JSON.stringify({ version: 1, observations: o }));
    // Direktesending krever lagret innlogging for at knappen skal gjøre noe
    localStorage.setItem('ao_username', 'testbruker');
    localStorage.setItem('ao_password', 'testpassord');
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

test.describe('Dublett-vern ved publisering', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(BASE);
  });

  test('viser ✓-merke på observasjoner som allerede er sendt', async ({ page }) => {
    await seed(page, [obs('Blåmeis', '2026-07-26T18:30:00'), obs('Kjøttmeis')]);
    await expect(page.locator('.obs-sent-badge')).toHaveCount(1);
  });

  test('advarer når lista inneholder allerede sendte funn', async ({ page }) => {
    await seed(page, [
      obs('Blåmeis', '2026-07-26T18:30:00'),
      obs('Gråtrost', '2026-07-26T18:30:00'),
      obs('Kjøttmeis'),
    ]);

    await page.locator('#ao-direct-btn').click();
    await expect(page.locator('#dub-nye')).toBeVisible({ timeout: 3000 });

    const tekst = await page.locator('#dub-nye').locator('..').innerText();
    expect(tekst).toContain('2 av disse 3');
    expect(tekst).toContain('dobbelt');
  });

  test('avbryt lukker dialogen uten å sende', async ({ page }) => {
    await seed(page, [obs('Blåmeis', '2026-07-26T18:30:00'), obs('Kjøttmeis')]);

    await page.locator('#ao-direct-btn').click();
    await expect(page.locator('#dub-nye')).toBeVisible({ timeout: 3000 });
    await page.locator('#dub-avbryt').click();

    await expect(page.locator('#dub-nye')).toHaveCount(0);
    // Ingen sending startet → ingen fremdriftsvisning
    await expect(page.locator('.ao-progress-track')).toHaveCount(0);
  });

  test('er stille når ingenting er sendt fra før', async ({ page }) => {
    await seed(page, [obs('Kjøttmeis'), obs('Blåmeis')]);

    await page.locator('#ao-direct-btn').click();
    await page.waitForTimeout(600);
    await expect(page.locator('#dub-nye')).toHaveCount(0);
  });
});
