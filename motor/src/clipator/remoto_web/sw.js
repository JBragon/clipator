// Service worker mínimo: guarda só a casca da página para ela abrir rápido.
// Os dados vêm sempre do PC (nada de /m/api fica em cache). O navegador só registra
// service worker em HTTPS, então ele vale quando o acesso é pelo "tailscale serve".
const CASCA = 'clipator-remoto-v1'
const ARQUIVOS = ['./', 'app.js', 'estilo.css', 'icone.svg', 'manifest.webmanifest']

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CASCA).then((c) => c.addAll(ARQUIVOS)).then(() => self.skipWaiting()))
})

self.addEventListener('activate', (e) => {
  e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== CASCA).map((k) => caches.delete(k)))))
})

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url)
  if (e.request.method !== 'GET' || url.origin !== location.origin || url.pathname.startsWith('/m/api/')) return
  // rede primeiro (para pegar a versão nova do motor); a cópia só se o PC não responder
  e.respondWith(fetch(e.request).then((r) => {
    const copia = r.clone()
    if (r.ok) caches.open(CASCA).then((c) => c.put(e.request, copia))
    return r
  }).catch(() => caches.match(e.request)))
})
