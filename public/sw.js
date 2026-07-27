// Service Worker for offline-støtte
const CACHE_NAME = 'fugleobs-v71';
const STATIC_ASSETS = [
  '/',
  '/index.html',
  '/style.css',
  '/js/theme.js',
  '/js/main.js',
  '/js/api.js',
  '/js/ui.js',
  '/js/storage.js',
  '/js/location.js',
  '/js/observations.js',
  '/js/form-state.js',
  '/js/species-search.js',
  '/js/observation-commit.js',
  '/js/export-operations.js',
  '/js/share.js',
  '/js/visits.js',
  '/js/news-splash.js',
  '/js/first-run-hint.js',
  '/js/species_offline.js',
  '/js/version.js',
  '/data/activities.json',
  '/data/norske_arter.json',
  '/favicon.svg'
];

// Installer og cache statiske filer
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      // cache: 'reload' hopper over nettleserens HTTP-cache. Uten den kan en ny SW
      // precache akkurat de utdaterte filene den skulle erstatte — Cloudflare sender
      // max-age=14400 på JS, så nettleseren ville ellers svart fra egen cache.
      // ?v=CACHE_NAME gjør det samme mot Cloudflare-edgen: den cacher per full URL,
      // så en ny versjon gir garantert et ferskt hent fra origin. Svaret lagres
      // under den rene URL-en, så oppslag i fetch-handleren er uendret.
      return Promise.all(STATIC_ASSETS.map((url) =>
        fetch(url + (url.includes('?') ? '&' : '?') + 'v=' + CACHE_NAME, { cache: 'reload' })
          .then((res) => (res.ok ? cache.put(url, res) : null))
          .catch(() => null)
      ));
    })
  );
  self.skipWaiting();
});

// Rydd opp gamle cacher
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
      );
    })
  );
  self.clients.claim();
});

// Nettverkskall med timeout — faller tilbake til cache hvis nett er tregt/nede
function fetchWithTimeout(request, ms) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('timeout')), ms);
    fetch(request).then(
      (res) => { clearTimeout(timer); resolve(res); },
      (err) => { clearTimeout(timer); reject(err); }
    );
  });
}

// Håndter requests: network-first med timeout, fallback til cache
// API-kall går direkte til nettverket uten SW-timeout (backend har egen timeout)
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  if (url.pathname.startsWith('/api/')) {
    return;
  }

  event.respondWith(
    fetchWithTimeout(event.request, 5000)
      .then((response) => {
        if (response.ok && event.request.method === 'GET') {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
        }
        return response;
      })
      .catch(() => caches.match(event.request))
  );
});
