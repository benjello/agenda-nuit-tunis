---
layout: null
permalink: /sw.js
---
// Service worker : le site s'ouvre comme une appli, et reste lisible sans connexion.
// Pages : réseau d'abord (l'agenda change chaque jour), copie gardée en secours.
// Style, script, icônes : copie gardée, mise à jour en arrière-plan.
var VERSION = 'agenda-{{ site.time | date: "%Y%m%d%H%M" }}';
var BASE = '{{ "/" | relative_url }}';
// Style et script portent ?v=date de construction (voir _layouts/default.html) : une nouvelle version = une nouvelle adresse,
// donc jamais une vieille copie servie après une mise en ligne.
var V = '?v={{ site.time | date: "%Y%m%d%H%M" }}';
var DE_BASE = [BASE, BASE + 'week-end/', BASE + 'hors-ligne/', BASE + 'assets/style.css' + V, BASE + 'assets/site.js' + V, BASE + 'assets/icones/icone-192.png'];

self.addEventListener('install', function (e) {
  e.waitUntil(caches.open(VERSION).then(function (c) { return Promise.all(DE_BASE.map(function (u) { return c.add(new Request(u, { cache: 'reload' })); })); }).then(function () { return self.skipWaiting(); }));
});
self.addEventListener('activate', function (e) {
  e.waitUntil(caches.keys().then(function (cles) {
    return Promise.all(cles.filter(function (k) { return k !== VERSION; }).map(function (k) { return caches.delete(k); }));
  }).then(function () { return self.clients.claim(); }));
});
self.addEventListener('fetch', function (e) {
  var r = e.request, u = new URL(r.url);
  if (r.method !== 'GET' || u.origin !== location.origin || u.pathname.indexOf(BASE) !== 0) return;
  if (r.mode === 'navigate') {
    e.respondWith(fetch(r).then(function (rep) {
      var copie = rep.clone();
      caches.open(VERSION).then(function (c) { c.put(r, copie); });
      return rep;
    }).catch(function () {
      return caches.match(r).then(function (m) { return m || caches.match(BASE) || caches.match(BASE + 'hors-ligne/'); });
    }));
    return;
  }
  e.respondWith(caches.match(r).then(function (m) {
    var reseau = fetch(r).then(function (rep) {
      if (rep.ok) { var copie = rep.clone(); caches.open(VERSION).then(function (c) { c.put(r, copie); }); }
      return rep;
    }).catch(function () { return m; });
    return m || reseau;
  }));
});
