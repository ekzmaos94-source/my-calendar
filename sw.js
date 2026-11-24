// 인터넷이 없어도 앱이 열리도록 파일을 보관해 두는 서비스 워커
// 인터넷이 되면 항상 서버에서 최신 파일을 먼저 받아요 (아이폰이 예전 파일을 붙잡고 있지 않게)
const CACHE = 'cal-v4';
const FILES = ['./', './index.html', './manifest.json', './icon-180.png', './icon-192.png', './icon-512.png'];
self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(FILES.map(f => new Request(f, {cache: 'reload'})))).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET' || new URL(e.request.url).origin !== location.origin) return;  // 날씨·시세 같은 외부 요청은 건드리지 않기
  e.respondWith(
    fetch(e.request, {cache: 'no-cache'}).then(res => {       // 저장된 사본 말고 서버에 최신인지 확인
      if (res.ok) { const copy = res.clone(); caches.open(CACHE).then(c => c.put(e.request, copy)); }
      return res;
    }).catch(() => caches.match(e.request).then(r => r || caches.match('./index.html')))
  );
});
