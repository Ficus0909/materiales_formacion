// Service worker: app shell en caché (offline) + datos de la API "network-first" con respaldo en caché.
const VERSION = 'materiales-v2'
const SHELL = ['/', '/index.html', '/manifest.webmanifest', '/favicon.png', '/icon-192.png', '/icon-512.png',
  '/icon-maskable-512.png', '/logo-sena-blanco.png']

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()))
})

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  )
})

self.addEventListener('fetch', (e) => {
  const req = e.request
  const url = new URL(req.url)
  if (req.method !== 'GET' || url.origin !== location.origin) return
  if (url.pathname.startsWith('/api/')) {
    // Sólo consultas JSON: se guardan para poder consultarlas sin conexión
    if (/(exportar|plantilla|pdf|zip)/.test(url.pathname)) return
    e.respondWith(
      fetch(req).then((res) => {
        if (res.ok) caches.open(VERSION).then((c) => c.put(req, res.clone()))
        return res
      }).catch(() => caches.match(req).then((r) => r || new Response(
        JSON.stringify({ detail: 'Sin conexión: no hay datos guardados para esta consulta' }),
        { status: 503, headers: { 'Content-Type': 'application/json' } },
      ))),
    )
    return
  }
  if (req.mode === 'navigate') {
    e.respondWith(fetch(req).catch(() => caches.match('/index.html')))
    return
  }
  e.respondWith(
    caches.match(req).then((hit) => hit || fetch(req).then((res) => {
      if (res.ok && url.pathname.startsWith('/assets/')) caches.open(VERSION).then((c) => c.put(req, res.clone()))
      return res
    })),
  )
})
