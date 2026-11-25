/* Offline support for the council website.
 *  - Registers the service worker (caches pages & static files for offline viewing).
 *  - Forms marked data-offline="true" are queued in IndexedDB when offline and
 *    replayed automatically when the connection returns. Each queued form
 *    carries a unique idempotency_key so the server never saves it twice.
 */
(function () {
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js').catch(function () {});
  }
  var DB = 'crdc-offline', STORE = 'outbox';
  function db() {
    return new Promise(function (resolve, reject) {
      var req = indexedDB.open(DB, 1);
      req.onupgradeneeded = function () { req.result.createObjectStore(STORE, { keyPath: 'key' }); };
      req.onsuccess = function () { resolve(req.result); };
      req.onerror = function () { reject(req.error); };
    });
  }
  function tx(mode, fn) {
    return db().then(function (d) {
      return new Promise(function (resolve, reject) {
        var t = d.transaction(STORE, mode), s = t.objectStore(STORE), r = fn(s);
        t.oncomplete = function () { resolve(r && r.result); };
        t.onerror = function () { reject(t.error); };
      });
    });
  }
  function uuid() {
    return (crypto.randomUUID && crypto.randomUUID()) || ('k' + Date.now() + Math.random().toString(16).slice(2));
  }
  function updateBanner() {
    var banner = document.getElementById('offline-banner');
    if (!banner) return;
    banner.classList.toggle('d-none', navigator.onLine);
    tx('readonly', function (s) { return s.count(); }).then(function (n) {
      var el = document.getElementById('queue-count');
      if (el) el.textContent = n ? '(' + n + ' form(s) waiting to be sent)' : '';
    }).catch(function () {});
  }
  function replay() {
    if (!navigator.onLine) return;
    tx('readonly', function (s) { return s.getAll(); }).then(function (items) {
      (items || []).forEach(function (item) {
        fetch(item.url, { method: 'POST', body: new URLSearchParams(item.body), credentials: 'same-origin',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' } })
          .then(function (resp) {
            if (resp.ok || resp.redirected) {
              tx('readwrite', function (s) { return s.delete(item.key); }).then(updateBanner);
            }
          }).catch(function () {});
      });
    }).catch(function () {});
  }
  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('input.idem-key').forEach(function (i) { if (!i.value) i.value = uuid(); });
    document.querySelectorAll('form[data-offline="true"]').forEach(function (form) {
      form.addEventListener('submit', function (e) {
        if (navigator.onLine) return;
        e.preventDefault();
        var fd = new FormData(form), body = {};
        fd.forEach(function (v, k) { body[k] = v; });
        var key = body.idempotency_key || uuid();
        tx('readwrite', function (s) { return s.put({ key: key, url: form.action || location.href, body: body, saved: Date.now() }); })
          .then(function () {
            alert('You are offline. This form has been saved on this device and will be submitted automatically when you are back online.');
            form.reset();
            form.querySelectorAll('input.idem-key').forEach(function (i) { i.value = uuid(); });
            updateBanner();
          });
      });
    });
    updateBanner();
    replay();
  });
  window.addEventListener('online', function () { updateBanner(); replay(); });
  window.addEventListener('offline', updateBanner);
})();
