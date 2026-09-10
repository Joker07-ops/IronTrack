const CACHE = 'irontrack-v2';
const ASSETS = [
  '/static/tokens.css',
  '/static/style.css',
  '/static/auth.css',
  '/static/logo.svg',
  '/static/icons/sprite.svg'
];

/*
 * IMPORTANT: only cache static assets. HTML pages embed a session-bound
 * CSRF token, so caching documents would serve stale tokens that fail
 * CSRF validation ("The CSRF session token is missing.").
 */

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE).then(cache => cache.addAll(ASSETS).catch(() => {}))
  );
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    ).then(() => clients.claim())
  );
});

self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET') return;
  if (event.request.mode === 'navigate') return; // never serve/cache HTML
  event.respondWith(
    caches.match(event.request).then(cached => {
      const fetchPromise = fetch(event.request).then(response => {
        if (response.ok && response.type === 'basic') {
          const clone = response.clone();
          caches.open(CACHE).then(cache => cache.put(event.request, clone));
        }
        return response;
      }).catch(() => cached);
      return cached || fetchPromise;
    })
  );
});
