/* 单词记忆 - Service Worker（network-first）
 * 用途：让 HTTPS 下浏览器识别为可安装 PWA（全屏独立窗口）
 * 有网时每次拉最新；断网时回退缓存页面
 */
const CACHE = 'recite-v1';
const ASSETS = ['./', './index.html', './manifest.json', './icon_192.png', './icon_512.png'];

self.addEventListener('install', function(e) {
  e.waitUntil(
    caches.open(CACHE).then(function(c) { return c.addAll(ASSETS); }).then(function() {
      return self.skipWaiting();
    })
  );
});

self.addEventListener('activate', function(e) {
  e.waitUntil(
    caches.keys().then(function(keys) {
      return Promise.all(keys.filter(function(k) { return k !== CACHE; }).map(function(k) { return caches.delete(k); }));
    }).then(function() { return self.clients.claim(); })
  );
});

self.addEventListener('fetch', function(e) {
  if (e.request.method !== 'GET') return;
  var url = new URL(e.request.url);
  if (url.origin !== self.location.origin) return;
  e.respondWith(
    fetch(e.request).then(function(res) {
      if (res && res.ok) {
        var clone = res.clone();
        caches.open(CACHE).then(function(c) { c.put(e.request, clone); });
      }
      return res;
    }).catch(function() {
      return caches.match(e.request).then(function(hit) { return hit || caches.match('./index.html'); });
    })
  );
});
