/**
 * Mock-server for E2E-tester.
 * 
 * Tilbyr mockede responser for:
 * - /api/species (artssøk)
 * - /api/reverse (geokoding)
 * - /api/ao-sites (lokaliteter)
 * 
 * Start med: npx ts-node mock-server.ts
 */

import http from 'http';
import fs from 'fs';
import path from 'path';

const PORT = parseInt(process.env.MOCK_PORT || '3333', 10);

// Mock-data for arter
const mockSpecies: Record<string, any[]> = {
  'gråspurv': [
    {
      taxonId: 4126,
      taxonName: 'Gråspurv',
      scientificNameHtml: '<em>Passer domesticus</em>',
      speciesGroupId: 8,
      protectionLevelId: 1,
      leaf: true,
    },
  ],
  'blåmeis': [
    {
      taxonId: 5968,
      taxonName: 'Blåmeis',
      scientificNameHtml: '<em>Cyanistes caeruleus</em>',
      speciesGroupId: 8,
      protectionLevelId: 1,
      leaf: true,
    },
  ],
  'meis': [
    {
      taxonId: 5968,
      taxonName: 'Blåmeis',
      scientificNameHtml: '<em>Cyanistes caeruleus</em>',
      speciesGroupId: 8,
      protectionLevelId: 1,
      leaf: true,
    },
    {
      taxonId: 5970,
      taxonName: 'Kjøttmeis',
      scientificNameHtml: '<em>Parus major</em>',
      speciesGroupId: 8,
      protectionLevelId: 1,
      leaf: true,
    },
    {
      taxonId: 5966,
      taxonName: 'Svartmeis',
      scientificNameHtml: '<em>Periparus ater</em>',
      speciesGroupId: 8,
      protectionLevelId: 1,
      leaf: true,
    },
  ],
  'trost': [
    {
      taxonId: 6227,
      taxonName: 'Gråtrost',
      scientificNameHtml: '<em>Turdus pilaris</em>',
      speciesGroupId: 8,
      protectionLevelId: 1,
      leaf: true,
    },
    {
      taxonId: 6222,
      taxonName: 'Svarttrost',
      scientificNameHtml: '<em>Turdus merula</em>',
      speciesGroupId: 8,
      protectionLevelId: 1,
      leaf: true,
    },
    {
      taxonId: 6225,
      taxonName: 'Rødvingetrost',
      scientificNameHtml: '<em>Turdus iliacus</em>',
      speciesGroupId: 8,
      protectionLevelId: 1,
      leaf: true,
    },
  ],
  'ørn': [
    {
      taxonId: 4820,
      taxonName: 'Havørn',
      scientificNameHtml: '<em>Haliaeetus albicilla</em>',
      speciesGroupId: 8,
      protectionLevelId: 2,
      leaf: true,
    },
    {
      taxonId: 4836,
      taxonName: 'Kongeørn',
      scientificNameHtml: '<em>Aquila chrysaetos</em>',
      speciesGroupId: 8,
      protectionLevelId: 2,
      leaf: true,
    },
  ],
};

// Mock-data for reverse geocoding
const mockReverseResponse = {
  place_id: 123456789,
  licence: 'Mock data',
  osm_type: 'way',
  osm_id: 12345678,
  lat: '59.9139',
  lon: '10.7522',
  display_name: 'Oslo, Norge',
  address: {
    city: 'Oslo',
    county: 'Oslo',
    country: 'Norge',
    country_code: 'no',
  },
  boundingbox: ['59.8', '60.0', '10.6', '10.9'],
};

// Mock-data for AO-sites
const mockAoSites = {
  sites: [
    {
      id: 1001,
      name: 'Maridalsvannet',
      latitude: 59.9700,
      longitude: 10.7800,
      distance: 500,
    },
    {
      id: 1002,
      name: 'Sognsvann',
      latitude: 59.9725,
      longitude: 10.7300,
      distance: 800,
    },
    // Legg til et parent (superlokasjon) og en child for E2E-testing
    {
      id: 2000,
      name: 'Mock Sentrum',
      latitude: 59.9139,
      longitude: 10.7522,
      distance: 100,
      parentSiteId: null,
      // Markér som superlokasjon i mock
      isSuper: true,
    },
    {
      id: 2001,
      name: 'Mock Sentrum - Kirken',
      latitude: 59.9140,
      longitude: 10.7525,
      distance: 120,
      parentSiteId: 2000,
      // Barn-lokalitet viser parentId i normalized output
      parentId: 2000,
      isSuper: false,
    },
  ],
};

function searchSpecies(query: string): any[] {
  const q = query.toLowerCase().trim();
  if (q.length < 2) return [];
  
  // Søk i alle mock-data
  for (const [key, species] of Object.entries(mockSpecies)) {
    if (key.includes(q) || q.includes(key)) {
      return species;
    }
  }
  
  // Søk i artsnavn
  const allSpecies = Object.values(mockSpecies).flat();
  return allSpecies.filter(s => 
    s.taxonName.toLowerCase().includes(q) ||
    s.scientificNameHtml.toLowerCase().includes(q)
  );
}

const server = http.createServer((req, res) => {
  const url = new URL(req.url || '/', `http://localhost:${PORT}`);
  const pathname = url.pathname;

  // CORS-headers for alle requests
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') {
    res.writeHead(204);
    res.end();
    return;
  }

  // /api/species - artssøk
  if (pathname === '/api/species') {
    const search = url.searchParams.get('search') || '';
    const results = searchSpecies(search);
    
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(results));
    console.log(`[mock] /api/species?search=${search} → ${results.length} treff`);
    return;
  }

  // /api/reverse - geokoding
  if (pathname === '/api/reverse') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(mockReverseResponse));
    console.log('[mock] /api/reverse → Oslo');
    return;
  }

  // /api/ao-sites - lokaliteter
  if (pathname === '/api/ao-sites') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(mockAoSites));
    console.log('[mock] /api/ao-sites → 2 sites');
    return;
  }

  // /api/logview - aksepter POST uten faktisk logging
  if (pathname === '/api/logview' && req.method === 'POST') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ ok: true }));
    console.log('[mock] /api/logview (ignored)');
    return;
  }

  // Serve statiske filer fra public/
  const publicDir = path.join(__dirname, '..', '..', 'public');
  let filePath = pathname === '/' ? '/index.html' : pathname;
  // server.py sin translate_path() strekker /public/-prefikset til å peke inn
  // i public/-katalogen (så f.eks. window.location.href = '/public/edit.html'
  // fungerer i den ekte appen) — gjenta samme mapping her, ellers 404 mock-
  // serveren på nøyaktig de URL-ene appen selv navigerer til.
  if (filePath.startsWith('/public/')) {
    filePath = filePath.slice('/public'.length);
  }
  const fullPath = path.join(publicDir, filePath);

  // Sikkerhetsjekk: ikke tillat path traversal
  if (!fullPath.startsWith(publicDir)) {
    res.writeHead(403);
    res.end('Forbidden');
    return;
  }

  fs.readFile(fullPath, (err, data) => {
    if (err) {
      res.writeHead(404);
      res.end('Not Found');
      console.log(`[mock] 404: ${pathname}`);
      return;
    }

    // Content-Type basert på filendelse
    const ext = path.extname(fullPath);
    const contentTypes: Record<string, string> = {
      '.html': 'text/html; charset=utf-8',
      '.css': 'text/css; charset=utf-8',
      '.js': 'application/javascript',
      '.json': 'application/json',
      '.svg': 'image/svg+xml',
      '.png': 'image/png',
      '.ico': 'image/x-icon',
    };

    res.writeHead(200, { 'Content-Type': contentTypes[ext] || 'text/plain' });
    res.end(data);
    console.log(`[mock] ${pathname}`);
  });
});

server.listen(PORT, () => {
  console.log(`\n🦅 Mock-server kjører på http://localhost:${PORT}\n`);
  console.log('Tilgjengelige API-er:');
  console.log('  /api/species?search=<query>  - Artssøk');
  console.log('  /api/reverse?lat=X&lon=Y     - Geokoding');
  console.log('  /api/ao-sites?lat=X&lon=Y    - Lokaliteter');
  console.log('\nMock-arter: gråspurv, blåmeis, meis, trost, ørn\n');
});

export { server, PORT };
