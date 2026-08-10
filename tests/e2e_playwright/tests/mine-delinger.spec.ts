import { test, expect, Page, Route } from '@playwright/test';

/**
 * «Mine delinger»-siden (Fase F3).
 *
 * Lister delinger lagret lokalt (`myShares_v1`), lar brukeren oppdatere en
 * eksisterende deling (åpner samme del-dialog i «oppdater»-modus) eller
 * trekke den tilbake. Ingen ekte nettverkskall mot AO/Nominatim her —
 * `/api/share-delete` mockes, `/api/share-update` trenger vi ikke nå siden
 * vi bare sjekker at dialogen åpnes riktig.
 */

const BASE = process.env.BASE_URL || 'http://localhost:3000';

function deling(overrides: Record<string, unknown> = {}) {
  return {
    slug: 'abc123def456',
    deleteKey: 'dk-test',
    ts: Date.now(),
    displayName: 'Kjetil',
    obsCount: 3,
    dato: '2026-07-27',
    expiresTs: Math.floor(Date.now() / 1000) + 14 * 86400, // aktiv om 14 dager
    ...overrides,
  };
}

function obs(taxonName: string) {
  return {
    species: { taxonName, taxonId: 58482, taxonGroupId: 8 },
    count: 2,
    placeName: 'Teststed',
    placeId: null,
    position: null,
    activity: 'Stasjonær',
    timestamp: '2026-07-27T15:00:00',
    age: '',
    gender: '',
    coObservers: [],
  };
}

/** Naviger til mine-delinger.html med gitt myShares_v1 (og evt. arbeidsliste) forhåndsseedet. */
async function gotoMedDelinger(page: Page, shares: object[] | null, observations: object[] = []) {
  await page.goto(BASE);
  await page.evaluate(({ shares, observations }) => {
    if (shares === null) {
      localStorage.removeItem('myShares_v1');
    } else {
      localStorage.setItem('myShares_v1', JSON.stringify(shares));
    }
    if (observations.length) {
      localStorage.setItem('fugleobservasjoner_v1', JSON.stringify({ version: 1, observations }));
    }
  }, { shares, observations });
  await page.goto(`${BASE}/mine-delinger.html`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(200);
}

test.describe('Mine delinger', () => {
  test.beforeEach(async ({ page }) => {
    // Samme mønster som share.spec.ts: SW-registrering forstyrrer page.route i WebKit.
    await page.addInitScript(() => {
      if (navigator.serviceWorker) {
        navigator.serviceWorker.register = async () => {
          throw new Error('Service worker avskrudd i test');
        };
      }
    });
  });

  test('tom tilstand: viser «Ingen delinger ennå» uten myShares_v1', async ({ page }) => {
    await gotoMedDelinger(page, null);
    await expect(page.locator('.tom')).toBeVisible();
    await expect(page.locator('.tom')).toContainText('Ingen delinger ennå');
    await expect(page.locator('.deling')).toHaveCount(0);
  });

  test('tom tilstand: viser tom-melding også når myShares_v1 er tom liste', async ({ page }) => {
    await gotoMedDelinger(page, []);
    await expect(page.locator('.tom')).toBeVisible();
  });

  test('viser riktig antall rader med visningsnavn, dato og antall observasjoner', async ({ page }) => {
    await gotoMedDelinger(page, [
      deling({ slug: 'a1', displayName: 'Kjetil', obsCount: 5 }),
      deling({ slug: 'a2', displayName: '', dato: '2026-07-20', obsCount: 1 }),
    ]);

    await expect(page.locator('.deling')).toHaveCount(2);

    const forste = page.locator('.deling').nth(0);
    await expect(forste.locator('.deling-tittel')).toContainText('Kjetil');
    await expect(forste.locator('.deling-meta')).toContainText('5 observasjoner');

    // Uten displayName faller tittelen tilbake til formatert dato
    const andre = page.locator('.deling').nth(1);
    await expect(andre.locator('.deling-tittel')).toContainText('20. juli 2026');
    await expect(andre.locator('.deling-meta')).toContainText('1 observasjon');
    await expect(andre.locator('.deling-meta')).not.toContainText('1 observasjoner');
  });

  test('lenken peker til riktig /d/<slug>', async ({ page }) => {
    await gotoMedDelinger(page, [deling({ slug: 'xyz789' })]);
    const lenke = page.locator('.deling a.lenke').first();
    await expect(lenke).toHaveAttribute('href', '/d/xyz789');
  });

  test('utløpt deling: viser «Utløpt»-status og disabled oppdater-knapp', async ({ page }) => {
    await gotoMedDelinger(page, [
      deling({ slug: 'utlopt1', expiresTs: Math.floor(Date.now() / 1000) - 3600 }),
    ]);

    const rad = page.locator('.deling').first();
    await expect(rad).toHaveClass(/utlopt/);
    await expect(rad.locator('.status')).toContainText('Utløpt');
    await expect(rad.locator('[data-oppdater]')).toBeDisabled();
    // Trekk tilbake skal fortsatt være mulig for en utløpt deling
    await expect(rad.locator('[data-trekk]')).toBeEnabled();
  });

  test('aktiv deling: viser «Aktiv»-status og enablet oppdater-knapp', async ({ page }) => {
    await gotoMedDelinger(page, [
      deling({ slug: 'aktiv1', expiresTs: Math.floor(Date.now() / 1000) + 3600 }),
    ]);

    const rad = page.locator('.deling').first();
    await expect(rad).not.toHaveClass(/utlopt/);
    await expect(rad.locator('.status')).toContainText('Aktiv');
    await expect(rad.locator('[data-oppdater]')).toBeEnabled();
  });

  test('trekk tilbake: fjerner raden og oppdaterer myShares_v1 i localStorage', async ({ page }) => {
    let sentBody: any = null;
    await page.route('**/api/share-delete', async (route: Route) => {
      sentBody = route.request().postDataJSON();
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true }),
      });
    });

    await gotoMedDelinger(page, [
      deling({ slug: 'skal-bort', deleteKey: 'dk-1' }),
      deling({ slug: 'skal-bli', deleteKey: 'dk-2' }),
    ]);

    await expect(page.locator('.deling')).toHaveCount(2);

    page.once('dialog', (d) => d.accept());
    // hentMineDelinger() leser arrayet som det er lagret (ingen ekstra sortering
    // her siden begge har samme ts) — indeks 0 i DOM-en er dermed «skal-bort».
    await page.locator('[data-trekk="0"]').click();

    await expect(page.locator('.deling')).toHaveCount(1);
    expect(sentBody).toEqual({ slug: 'skal-bort', deleteKey: 'dk-1' });

    const lagret = await page.evaluate(() => JSON.parse(localStorage.getItem('myShares_v1') || '[]'));
    expect(lagret).toHaveLength(1);
    expect(lagret[0].slug).toBe('skal-bli');
  });

  test('trekk tilbake: 404 fra server behandles som suksess (deling allerede borte)', async ({ page }) => {
    await page.route('**/api/share-delete', async (route: Route) => {
      await route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ ok: false }) });
    });

    await gotoMedDelinger(page, [deling({ slug: 'borte-fra-for' })]);

    page.once('dialog', (d) => d.accept());
    await page.locator('[data-trekk="0"]').click();

    await expect(page.locator('.deling')).toHaveCount(0);
    await expect(page.locator('.tom')).toBeVisible();
    const lagret = await page.evaluate(() => JSON.parse(localStorage.getItem('myShares_v1') || '[]'));
    expect(lagret).toHaveLength(0);
  });

  test('trekk tilbake: avbrutt confirm() lar raden ligge', async ({ page }) => {
    let kalt = false;
    await page.route('**/api/share-delete', async (route: Route) => {
      kalt = true;
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true }) });
    });

    await gotoMedDelinger(page, [deling({ slug: 'behold-meg' })]);

    page.once('dialog', (d) => d.dismiss());
    await page.locator('[data-trekk="0"]').click();
    await page.waitForTimeout(300);

    await expect(page.locator('.deling')).toHaveCount(1);
    expect(kalt).toBe(false);
  });

  test('oppdater-knapp åpner del-dialogen i oppdater-modus', async ({ page }) => {
    await gotoMedDelinger(
      page,
      [deling({ slug: 'oppdater-meg', deleteKey: 'dk-opp' })],
      [obs('Blåmeis')],
    );

    await page.locator('[data-oppdater="0"]').click();

    const modal = page.locator('#share-modal');
    await expect(modal).toBeVisible();
    await expect(modal.locator('h3')).toContainText('Oppdater delingen');
    await expect(modal.locator('#share-create')).toHaveText('Oppdater');
    // Ikke ny-deling-teksten
    await expect(modal.locator('#share-create')).not.toHaveText('Lag lenke');
  });

  test('oppdater-knapp med tom arbeidsliste: varsler i stedet for å åpne dialog', async ({ page }) => {
    await gotoMedDelinger(page, [deling({ slug: 'ingen-obs' })], []);

    page.once('dialog', (d) => {
      expect(d.message()).toContain('Arbeidslista er tom');
      d.accept();
    });
    await page.locator('[data-oppdater="0"]').click();
    await page.waitForTimeout(200);

    await expect(page.locator('#share-modal')).toHaveCount(0);
  });

  test('lenken «🔗 Mine delinger» finnes på hovedsiden og leder til siden', async ({ page }) => {
    await page.goto(BASE);

    // Førstegangs-coachmarken («👋 Start her») legger seg over resten av siden
    // for helt nye brukere (tom arbeidsliste) — irrelevant for denne testen.
    const coachmark = page.locator('.coachmark-button');
    if (await coachmark.count()) {
      await coachmark.click();
    }

    const lenke = page.locator('a[href="/mine-delinger.html"]');
    await expect(lenke).toBeVisible();
    await expect(lenke).toContainText('Mine delinger');
    await lenke.click();
    await expect(page).toHaveURL(/\/mine-delinger\.html$/);
    await expect(page.locator('h1')).toContainText('Mine delinger');
  });
});
