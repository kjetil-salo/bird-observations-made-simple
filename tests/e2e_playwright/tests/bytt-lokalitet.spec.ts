import { test, expect, Page, Route } from '@playwright/test';

/**
 * ↩ i gruppeoverskrifta i ③: gå tilbake til akkurat dette besøket.
 *
 * Tidsregelen er poenget her. Å gå tilbake er en etterregistrering *inn i*
 * besøket: den nye arten havner i samme besøk og arver besøkets tidsspenn
 * (fra–til) — man vet at arten ble sett i løpet av besøket, ikke nøyaktig
 * når. Det gjelder også et låst
 * besøk: 🔒 hindrer *automatisk* innlegging, mens ↩ er et eksplisitt valg om
 * nettopp det. Da arver obsen også låsen, ellers ville gruppa låst seg opp.
 */

const BASE = process.env.BASE_URL || 'http://localhost:3000';

function obs(taxonName: string, placeName: string, visitId: string, extra: Record<string, unknown> = {}) {
  return {
    species: { taxonName, taxonId: 58482, taxonGroupId: 8 },
    count: 2,
    placeName,
    placeId: null,
    position: null,
    activity: 'Stasjonær',
    visitId,
    visitLocked: false,
    timestamp: '2026-08-26T09:00:00',
    age: '',
    gender: '',
    coObservers: [],
    ...extra,
  };
}

async function seed(page: Page, observations: object[]) {
  await page.evaluate((o) => {
    localStorage.setItem('fugleobservasjoner_v1', JSON.stringify({ version: 1, observations: o }));
    localStorage.removeItem('afterRegistrationMode');
  }, observations);
  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(400);

  const splash = page.locator('.news-splash-button');
  if (await splash.count()) {
    await splash.click();
    await page.waitForTimeout(200);
  }
}

/** Observasjonene slik de ligger i localStorage akkurat nå. */
async function lagrede(page: Page): Promise<any[]> {
  return page.evaluate(() => {
    const raw = localStorage.getItem('fugleobservasjoner_v1');
    return raw ? JSON.parse(raw).observations : [];
  });
}

/** Søk opp og velg en art, sett antall, og committ med første aktivitetspill. */
async function registrer(page: Page, sok: string) {
  await page.fill('#search', sok);
  const treff = page.locator('#results .result-item').first();
  await expect(treff).toBeVisible({ timeout: 5000 });
  await treff.click();
  await page.fill('#count', '3');
  const pill = page.locator('.activity-pill').first();
  await expect(pill).toBeVisible({ timeout: 2000 });
  await pill.click();
  await page.waitForTimeout(300);
}

test.describe('↩ Gå tilbake til et besøk', () => {
  test.beforeEach(async ({ page }) => {
    // Stubb artssøket: testen handler om tidsregelen, ikke om AO er oppe.
    await page.route('**/api/species*', async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          { taxonId: 4126, taxonName: 'Gråspurv', scientificNameHtml: '<em>Passer domesticus</em>', speciesGroupId: 8, protectionLevelId: 1, leaf: true },
        ]),
      });
    });
    await page.goto(BASE);
  });

  test('setter gruppens lokalitet som aktiv lokalitet', async ({ page }) => {
    await seed(page, [
      obs('Polarsnipe', 'Tovo', 'visit:tovo', { timestamp: '2026-08-26T17:09:00' }),
      obs('Steinvender', 'Kvitingen', 'visit:kvitingen', { timestamp: '2026-08-26T17:10:00' }),
    ]);

    const blyanter = page.locator('.obs-group-place-btn');
    await expect(blyanter).toHaveCount(2);

    await blyanter.nth(0).click();
    await expect(page.locator('#loc-pinned-name')).toHaveText('Tovo');
    expect(await page.locator('#place').inputValue()).toBe('Tovo');
  });

  test('åpent besøk: ny art havner i besøket og arver tidsspennet', async ({ page }) => {
    await seed(page, [
      obs('Polarsnipe', 'Tovo', 'visit:tovo', { timestamp: '2026-08-26T17:09:00', tilKlokkeslett: '2026-08-26T17:18:00' }),
      obs('Steinvender', 'Kvitingen', 'visit:kvitingen', { timestamp: '2026-08-26T17:30:00' }),
    ]);

    // Gå tilbake til Tovo — merket skal vise det nøyaktige klokkeslettet man får
    await page.locator('.obs-group-place-btn').nth(0).click();
    await expect(page.locator('#loc-pinned-visit')).toBeVisible();
    await expect(page.locator('#loc-pinned-visit')).toHaveText('↩ 17:09–17:18');

    await registrer(page, 'gråspurv');

    const alle = await lagrede(page);
    const ny = alle.find((o) => o.species.taxonName === 'Gråspurv');
    expect(ny).toBeTruthy();
    // Samme besøk, og hele besøkets tidsspenn
    expect(ny.visitId).toBe('visit:tovo');
    expect(ny.timestamp).toBe('2026-08-26T17:09:00');
    expect(ny.tilKlokkeslett).toBe('2026-08-26T17:18:00');
    expect(ny.visitLocked).toBe(false);

    // Gruppa i ③ skal fortsatt vise 17:09–17:18, ikke strekkes til nå
    const tovoHeader = page.locator('.obs-group-row', { hasText: 'TOVO' }).first();
    await expect(tovoHeader).toContainText('17:09–17:18');
  });

  test('låst besøk: obsen går inn i besøket, arver låsen, og advarselen vises', async ({ page }) => {
    await seed(page, [
      obs('Polarsnipe', 'Tovo', 'visit:tovo', { timestamp: '2026-08-26T17:09:00', visitLocked: true }),
    ]);

    await page.locator('.obs-group-place-btn').first().click();

    // Lett advarsel: avsluttet besøk, og klokka settes tilbake i tid
    const toast = page.locator('#registered-toast');
    await expect(toast).toBeVisible({ timeout: 3000 });
    await expect(toast).toContainText('avsluttet besøk');
    await expect(toast).toContainText('17:09');

    // Merket skal vise at besøket er låst. Besøket er ett tidspunkt, så
    // ingen til-tid — da vises bare det ene klokkeslettet.
    await expect(page.locator('#loc-pinned-visit')).toHaveText('🔒 ↩ 17:09');

    await registrer(page, 'gråspurv');

    const alle = await lagrede(page);
    const ny = alle.find((o) => o.species.taxonName === 'Gråspurv');
    expect(ny).toBeTruthy();
    expect(ny.visitId).toBe('visit:tovo');
    expect(ny.timestamp).toBe('2026-08-26T17:09:00');
    expect(ny.tilKlokkeslett).toBeUndefined();
    // Arver låsen — ellers ville gruppa stille låse seg opp igjen
    expect(ny.visitLocked).toBe(true);

    // Fortsatt én gruppe, og den er fortsatt låst
    await expect(page.locator('.obs-group-row')).toHaveCount(1);
    await expect(page.locator('.obs-group-lock-btn.is-locked')).toHaveCount(1);
  });

  test('etterreg-modus: fremtidig klokke i skjemaet blokkerer ikke ↩-registrering', async ({ page }) => {
    // Tidene som valideres skal være de som faktisk lagres — besøkets — ikke
    // skjemaets. Ellers ble registreringen avvist for en tid som aldri ble brukt.
    await seed(page, [
      obs('Polarsnipe', 'Tovo', 'visit:tovo', { timestamp: '2026-08-25T17:09:00', tilKlokkeslett: '2026-08-25T17:18:00' }),
    ]);
    // seed() slår av etterregistreringsmodus — slå den på og last inn på nytt
    await page.evaluate(() => localStorage.setItem('afterRegistrationMode', '1'));
    await page.reload({ waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(500);

    await page.locator('.obs-group-place-btn').first().click();
    await page.waitForTimeout(300);

    // Sett skjemaets klokke frem i tid
    const om10 = new Date(Date.now() + 10 * 60_000);
    const p = (n: number) => String(n).padStart(2, '0');
    await page.fill('#obs-date', `${om10.getFullYear()}-${p(om10.getMonth() + 1)}-${p(om10.getDate())}`);
    await page.fill('#obs-time', `${p(om10.getHours())}:${p(om10.getMinutes())}`);

    await registrer(page, 'gråspurv');

    await expect(page.locator('#registered-toast')).not.toContainText('frem i tid');
    const alle = await lagrede(page);
    const ny = alle.find((o) => o.species.taxonName === 'Gråspurv');
    expect(ny).toBeTruthy();
    expect(ny.timestamp).toBe('2026-08-25T17:09:00');
    expect(ny.tilKlokkeslett).toBe('2026-08-25T17:18:00');
  });

  test('«Bytt plass» avslutter etterregistreringen — tilbake til «nå»', async ({ page }) => {
    await seed(page, [
      obs('Polarsnipe', 'Tovo', 'visit:tovo', { timestamp: '2026-08-26T17:09:00' }),
    ]);

    await page.locator('.obs-group-place-btn').first().click();
    await expect(page.locator('#loc-pinned-visit')).toBeVisible();

    // Skriv inn en annen plass manuelt — da er vi ikke i det gamle besøket lenger
    await page.locator('#loc-change-btn').click();
    await page.fill('#place', 'Et helt annet sted');
    await expect(page.locator('#loc-pinned-visit')).toBeHidden();

    await registrer(page, 'gråspurv');

    const alle = await lagrede(page);
    const ny = alle.find((o) => o.species.taxonName === 'Gråspurv');
    expect(ny).toBeTruthy();
    expect(ny.placeName).toBe('Et helt annet sted');
    const iDag = new Date().toISOString().slice(0, 10);
    expect(ny.timestamp.slice(0, 10)).toBe(iDag);
  });
});
