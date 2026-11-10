'use strict';

const ACQ_OFFLINE_CACHE = 'acq-offline-v2';
const ACQ_OFFLINE_URL = new URL('offline.html', self.registration.scope).href;
const ACQ_WORDMARK_URL = new URL('icons/acq-media-wordmark.svg', self.registration.scope).href;

self.addEventListener('install', event => {
  event.waitUntil(caches.open(ACQ_OFFLINE_CACHE).then(cache => cache.addAll([ACQ_OFFLINE_URL, ACQ_WORDMARK_URL])).then(() => self.skipWaiting()));
});

self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key.startsWith('acq-offline-') && key !== ACQ_OFFLINE_CACHE).map(key => caches.delete(key)))).then(() => self.clients.claim()));
});

// Never cache news pages: every online navigation requests the current edition.
self.addEventListener('fetch', event => {
  if (event.request.url === ACQ_WORDMARK_URL) {
    event.respondWith(caches.open(ACQ_OFFLINE_CACHE).then(cache => cache.match(ACQ_WORDMARK_URL)).then(cached => cached || fetch(event.request)));
    return;
  }
  if (event.request.mode !== 'navigate' || new URL(event.request.url).origin !== self.location.origin) return;
  event.respondWith(fetch(event.request).catch(async () => {
    const offline = await caches.match(ACQ_OFFLINE_URL);
    return offline || Response.error();
  }));
});
