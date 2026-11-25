// Service worker: network-first for pages (falls back to the last saved copy
// when offline), cache-first for static assets.
const CACHE = 'crdc-v1';
const PRECACHE = ['/offline/', '/static/vendor/bootstrap.min.css', '/static/vendor/bootstrap.bundle.min.js',
  '/static/css/app.css', '/static/js/offline.js', '/static/img/logo.svg'];
self.addEventListener('install', e => { e.waitUntil(caches.open(CACHE).then(c => c.addAll(PRECACHE)).then(() => self.skipWaiting())); });
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET' || new URL(req.url).origin !== location.origin) return;
  const url = new URL(req.url);
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/admin/')) return;
  if (url.pathname.startsWith('/static/')) {
    e.respondWith(caches.match(req).then(hit => hit || fetch(req).then(resp => { const copy = resp.clone(); caches.open(CACHE).then(c => c.put(req, copy)); return resp; })));
    return;
  }
  e.respondWith(
    fetch(req).then(resp => {
      if (resp.ok && resp.type === 'basic') { const copy = resp.clone(); caches.open(CACHE).then(c => c.put(req, copy)); }
      return resp;
    }).catch(() => caches.match(req).then(hit => hit || caches.match('/offline/')))
  );
});
