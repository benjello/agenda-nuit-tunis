// ToNight Tunis : ce qui marche sur toutes les pages.
// Langue, thème, affichage léger, favoris, « ajouter à mon agenda », partage, appli installable.
(function () {
  var d = document.documentElement;
  var I18N = window.I18N || {};
  function lire(cle, defaut) { try { return localStorage.getItem(cle) || defaut; } catch (e) { return defaut; } }
  function ecrire(cle, v) { try { localStorage.setItem(cle, v); } catch (e) {} }
  function iso(dt) { return dt.getFullYear() + '-' + ('0' + (dt.getMonth() + 1)).slice(-2) + '-' + ('0' + dt.getDate()).slice(-2); }
  function jour(decalage) { var x = new Date(); x.setDate(x.getDate() + (decalage || 0)); return iso(x); }

  // ---- Langue : français dans les pages, arabe et anglais par le dictionnaire _data/i18n.yml
  // Première visite : la langue du navigateur (arabe, anglais), sinon le français. Le choix du lecteur est gardé.
  function langueDuNavigateur() {
    var l = (navigator.languages && navigator.languages.length ? navigator.languages : [navigator.language || 'fr']);
    for (var i = 0; i < l.length; i++) {
      var c = String(l[i]).slice(0, 2).toLowerCase();
      if (c === 'ar' || c === 'en' || c === 'fr') return c;
    }
    return 'fr';
  }
  var langue = lire('langue', langueDuNavigateur());
  var LOCALE = { fr: 'fr-FR', ar: 'ar-TN', en: 'en-GB' };
  function t(cle, defaut) {
    var e = I18N[cle];
    return (e && e[langue]) || (langue === 'fr' && e && e.fr) || defaut;
  }
  window.t = t;
  // ---- Libellés (lieux, adresses, festivals, descriptifs, prix…) : libelles.json, produit par scrapers/libelles.py
  var LIBELLES = null, chargementLibelles = false;
  var MOTIF = { ar: { debut: 'ابتداءً من', dt: 'د.ت', ed: 'الدورة %n', gratuit: 'مجاني' }, en: { debut: 'From', dt: 'TND', ed: '%n edition', gratuit: 'Free' } };
  function ordinal(n) { var r = n % 100; if (r >= 11 && r <= 13) return n + 'th'; return n + (['th', 'st', 'nd', 'rd'][n % 10] || 'th'); }
  function convertir(c) {
    var m, x = MOTIF[langue];
    if (!x) return null;
    if (/^gratuit$/i.test(c)) return t('gratuit', x.gratuit);
    if ((m = c.match(/^(?:À partir de|A partir de)\s+([\d.,]+)\s*DT$/i))) return x.debut + ' ' + m[1] + ' ' + x.dt;
    if ((m = c.match(/^([\d.,]+)\s*DT$/i))) return m[1] + ' ' + x.dt;
    if ((m = c.match(/^(\d+)(?:e|er|ère|ème)\s+édition(.*)$/i))) return (langue === 'en' ? ordinal(+m[1]) + ' edition' : x.ed.replace('%n', m[1])) + (m[2] || '');
    return null;
  }
  var SPECIAUX = { 'Lieu à préciser': 'lieu_preciser', 'voir l\'annonce': 'voir_annonce', 'voir l\'article': 'voir_article' };
  function chercher(c, niveau) {
    var e = LIBELLES && LIBELLES[c], k = SPECIAUX[c], m;
    if (k) return t(k, null);
    if (e && e[langue]) return e[langue];
    var r = convertir(c);
    if (r) return r;
    if ((m = c.match(/^(.*?)\s*(\(\d+(?:e|er|ère|ème)\s+édition\))$/i)) && m[1]) {
      var a = chercher(m[1], niveau + 1), b = convertir(m[2].slice(1, -1));
      if (a || b) return (a || m[1]) + ' (' + (b || m[2].slice(1, -1)) + ')';
    }
    if (niveau > 1) return null;
    var seps = [' · ', ', '];
    for (var i = 0; i < seps.length; i++) {
      var parts = c.split(seps[i]);
      if (parts.length > 1) {
        var change = false, sortie = parts.map(function (p) { var x = chercher(p.trim(), niveau + 1); if (x) change = true; return x || p; });
        if (change) return sortie.join(seps[i]);
      }
    }
    return null;
  }
  function appliquerLibelles() {
    if (langue !== 'fr' && !LIBELLES && !chargementLibelles) {
      chargementLibelles = true;
      fetch((window.BASE || '/') + 'libelles.json').then(function (r) { return r.json(); })
        .then(function (j) { LIBELLES = j || {}; traduire(); }).catch(function () { LIBELLES = {}; });
    }
    var w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
      acceptNode: function (n) {
        var p = n.parentNode;
        return !p || /^(SCRIPT|STYLE|NOSCRIPT|TEXTAREA)$/.test(p.nodeName) || (p.closest && p.closest('[data-t],[data-tn],[data-th],[data-tr-fr],[data-tr-en],[data-tr-ar],[data-tr-bloc],[data-tr-origine],.titre-orig')) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT;
      }
    });
    var noeuds = [], n;
    while ((n = w.nextNode())) noeuds.push(n);
    noeuds.forEach(function (nd) {
      if (nd._orig === undefined) nd._orig = nd.nodeValue;
      var o = nd._orig, m = o.match(/^([\s·•|,:–—-]*)([\s\S]*?)([\s·•|,:–—-]*)$/);
      if (!m || !m[2]) return;
      var r = langue !== 'fr' ? chercher(m[2], 0) : null;
      var v = r ? m[1] + r + m[3] : o;
      if (nd.nodeValue !== v) nd.nodeValue = v;
    });
  }
  function traduire() {
    d.lang = langue; d.dir = langue === 'ar' ? 'rtl' : 'ltr';
    document.querySelectorAll('[data-t]').forEach(function (el) {
      if (el._fr === undefined) el._fr = el.textContent;
      el.textContent = langue === 'fr' ? el._fr : t(el.dataset.t, el._fr);
    });
    // Textes écrits par les scripts des pages, avec un nombre : data-tn (clé), data-n, data-tn-fr
    document.querySelectorAll('[data-tn]').forEach(function (el) {
      el.textContent = t(el.dataset.tn, el.dataset.tnFr || el.textContent).replace('%n', el.dataset.n || '');
    });
    // Paragraphes avec liens : la traduction est du HTML (« {base} » = racine du site)
    document.querySelectorAll('[data-th]').forEach(function (el) {
      if (el._fr === undefined) el._fr = el.innerHTML;
      var v = langue === 'fr' ? null : t(el.dataset.th, null);
      el.innerHTML = v ? v.replace(/\{base\}/g, window.BASE || '/') : el._fr;
    });
    document.querySelectorAll('[data-t-title]').forEach(function (el) {
      var v = t(el.dataset.tTitle, el.title); el.title = v; el.setAttribute('aria-label', v);
    });
    document.querySelectorAll('[data-t-placeholder]').forEach(function (el) {
      el.placeholder = t(el.dataset.tPlaceholder, el.placeholder);
    });
    var loc = LOCALE[langue];
    document.querySelectorAll('time[datetime]').forEach(function (el) {
      if (el._fr === undefined) el._fr = el.textContent;
      if (langue === 'fr') { el.textContent = el._fr; return; }
      var v = el.getAttribute('datetime'), heure = v.length > 10;
      var x = new Date(v.length > 10 ? v : v + 'T12:00:00');
      var o = { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' };
      if (heure) { o.hour = '2-digit'; o.minute = '2-digit'; }
      el.textContent = x.toLocaleString(loc, o);
    });
    document.querySelectorAll('[data-mc]').forEach(function (el) {
      if (el._fr === undefined) el._fr = el.textContent;
      el.textContent = langue === 'fr' ? el._fr : new Date(2026, +el.dataset.mc - 1, 15).toLocaleString(loc, { month: 'short' });
    });
    document.querySelectorAll('[data-mois]').forEach(function (el) {
      if (el._fr === undefined) el._fr = el.textContent;
      var p = el.dataset.mois.split('-');
      el.textContent = langue === 'fr' ? el._fr : new Date(+p[0], +p[1] - 1, 15).toLocaleString(loc, { month: 'long', year: 'numeric' });
    });
    // Titres et notices des événements : traduction automatique (_data/traductions.json)
    var decoder = window._decoder = function (v) { return v ? v.replace(/&quot;/g, '"').replace(/&apos;|&#39;/g, "'").replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&') : v; };
    var cle = 'tr' + langue.charAt(0).toUpperCase() + langue.slice(1);
    document.querySelectorAll('[data-tr-fr],[data-tr-en],[data-tr-ar]').forEach(function (el) {
      if (el._orig === undefined) el._orig = el.textContent;
      var v = decoder(el.dataset[cle]);
      el.textContent = v || el._orig;
      if (v) el.setAttribute('lang', langue); else el.removeAttribute('lang');
      // seul le titre garde sa langue d'origine : on l'affiche à côté de sa traduction
      if (el.matches('h1,h3 a')) {
        var o = el._origTitre;
        if (v && !o) { o = el._origTitre = document.createElement('span'); o.className = 'titre-orig'; o.setAttribute('dir', 'auto'); el.insertAdjacentElement('afterend', o); }
        if (o) { o.textContent = v ? el._orig : ''; o.hidden = !v; }
      }
    });
    var blocs = document.querySelectorAll('[data-tr-bloc]'), traduit = false, original = window._voirOriginal === true;
    blocs.forEach(function (b) { b.hidden = original || b.dataset.trBloc !== langue; traduit = traduit || b.dataset.trBloc === langue; });
    document.querySelectorAll('[data-tr-origine]').forEach(function (b) { b.hidden = traduit && !original; });
    document.querySelectorAll('.note-trad').forEach(function (b) { b.hidden = !traduit || original; });
    // « Voir le texte d'origine » / « Voir la traduction » : seulement quand une traduction existe
    document.querySelectorAll('.voir-original').forEach(function (b) {
      b.hidden = !traduit;
      b.textContent = original ? t('voir_traduction', 'Voir la traduction') : t('voir_original', 'Voir le texte d\'origine');
    });
    appliquerLibelles();
    document.querySelectorAll('a.carte[data-q]').forEach(function (a) {
      if (a.href.indexOf('geo:') === 0) return;
      if (a._href === undefined) a._href = a.getAttribute('href');
      a.setAttribute('href', langue === 'fr' || a._href.indexOf('openstreetmap.org/search') < 0 ? a._href : a._href + '&locale=' + langue);
    });
    document.querySelectorAll('[data-langue]').forEach(function (b) { b.classList.toggle('active', b.dataset.langue === langue); });
    document.dispatchEvent(new CustomEvent('langue', { detail: langue }));
  }
  document.querySelectorAll('[data-langue]').forEach(function (b) {
    b.addEventListener('click', function () { langue = b.dataset.langue; window._voirOriginal = false; ecrire('langue', langue); traduire(); });
  });
  document.querySelectorAll('.voir-original').forEach(function (b) {
    b.addEventListener('click', function () { window._voirOriginal = !window._voirOriginal; traduire(); });
  });

  // ---- Thème sombre ou clair (par défaut : celui du téléphone) et affichage léger
  var bt = document.getElementById('bouton-theme');
  if (bt) bt.addEventListener('click', function () {
    var sombre = d.dataset.theme ? d.dataset.theme === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
    d.dataset.theme = sombre ? 'light' : 'dark';
    ecrire('theme', d.dataset.theme);
  });
  var bl = document.getElementById('bouton-leger');
  function marquerLeger() { if (bl) bl.classList.toggle('active', d.classList.contains('leger')); }
  if (bl) bl.addEventListener('click', function () {
    d.classList.toggle('leger');
    ecrire('leger', d.classList.contains('leger') ? '1' : '0');
    marquerLeger();
  });
  marquerLeger();
  // Affichage léger : les images ne sont pas téléchargées du tout.
  if (d.classList.contains('leger')) document.querySelectorAll('.vignette img, img.affiche-grande').forEach(function (i) { i.removeAttribute('src'); });

  // ---- Android : liens de carte vers l'appli du téléphone
  if (/Android/i.test(navigator.userAgent)) {
    document.querySelectorAll('a.carte[data-q]').forEach(function (a) { a.href = 'geo:0,0?q=' + encodeURIComponent(a.dataset.q); });
  }

  // ---- Listes des fiches (lieu, artiste, nouveautés) : masquer ce qui est passé
  var auj = jour(), ilya7 = jour(-7);
  document.querySelectorAll('[data-masquer-passes]').forEach(function (liste) {
    var nouveaux = liste.hasAttribute('data-nouveaux'), n = 0;
    liste.querySelectorAll('.event').forEach(function (el) {
      var ok = el.dataset.date >= auj && (!nouveaux || (el.dataset.ajoute || '') >= ilya7);
      el.hidden = !ok; if (ok) n++;
    });
    var vide = liste.parentNode.querySelector('[data-vide]');
    if (vide) vide.hidden = n > 0;
  });

  // ---- Menu réduit sur téléphone : « Menu ☰ » ouvre les pages secondaires et les réglages
  var bm = document.getElementById('bouton-menu');
  if (bm) bm.addEventListener('click', function () {
    var ouvert = bm.closest('.site-header').classList.toggle('ouvert');
    bm.setAttribute('aria-expanded', ouvert ? 'true' : 'false');
  });

  // ---- Favoris, gardés dans le navigateur (sans compte)
  var favoris = [];
  try { favoris = JSON.parse(lire('favoris', '[]')); } catch (e) {}
  window.lireFavoris = function () { return favoris; };
  function marquerFavoris() {
    document.querySelectorAll('.fav').forEach(function (b) {
      var c = b.closest('[data-id]'), on = c && favoris.indexOf(c.dataset.id) >= 0;
      b.classList.toggle('on', !!on); var ic = b.querySelector('.ico'); (ic || b).textContent = on ? '★' : '☆';
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
  }
  marquerFavoris();

  // ---- « Ajouter à mon agenda » : un fichier .ics que le téléphone ouvre dans son calendrier
  function utc(dateIso, heure, decalageH) {
    var p = dateIso.split('-'), h = heure ? heure.split(':') : [0, 0];
    // Tunis : UTC+1 toute l'année
    var x = new Date(Date.UTC(+p[0], +p[1] - 1, +p[2], +h[0] - 1 + (decalageH || 0), +h[1]));
    return x.toISOString().replace(/[-:]/g, '').slice(0, 15) + 'Z';
  }
  function echapper(s) { return (s || '').replace(/\\/g, '\\\\').replace(/[,;]/g, '\\$&').replace(/\n/g, '\\n'); }
  function ics(c) {
    var debut = c.dataset.debut, fin = c.dataset.date || debut, h = c.dataset.heure, l = [];
    l.push('BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//ToNight Tunis//FR', 'BEGIN:VEVENT');
    l.push('UID:' + c.dataset.id.replace(/\W+/g, '-') + '@agenda-nuit-tunis');
    l.push('DTSTAMP:' + new Date().toISOString().replace(/[-:]/g, '').slice(0, 15) + 'Z');
    if (h && fin === debut) {
      var hf = c.dataset.heureFin, finJour = debut;
      if (hf && hf <= h) { var j = new Date(debut + 'T12:00:00'); j.setDate(j.getDate() + 1); finJour = iso(j); }
      l.push('DTSTART:' + utc(debut, h), 'DTEND:' + (hf ? utc(finJour, hf) : utc(debut, h, 2)));
    } else {
      var f = new Date(fin + 'T12:00:00'); f.setDate(f.getDate() + 1);
      l.push('DTSTART;VALUE=DATE:' + debut.replace(/-/g, ''), 'DTEND;VALUE=DATE:' + iso(f).replace(/-/g, ''));
    }
    l.push('SUMMARY:' + echapper(c.dataset.titre), 'LOCATION:' + echapper(c.dataset.lieu),
      'URL:' + c.dataset.lien, 'DESCRIPTION:' + echapper(c.dataset.lien), 'END:VEVENT', 'END:VCALENDAR');
    return l.join('\r\n');
  }
  function telecharger(blob, nom) {
    var a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = nom;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 5000);
  }

  // ---- Partage : image au format story (1080×1920) et lien
  function lignes(ctx, texte, largeur) {
    var mots = texte.split(/\s+/), res = [], l = '';
    mots.forEach(function (m) {
      var essai = l ? l + ' ' + m : m;
      if (ctx.measureText(essai).width > largeur && l) { res.push(l); l = m; } else l = essai;
    });
    if (l) res.push(l);
    return res;
  }
  function quand(c) {
    var tm = c.querySelector('time');
    return tm ? tm.textContent.trim() : c.dataset.debut;
  }
  function image(c) {
    return new Promise(function (ok, ko) {
      var W = 1080, H = 1920, cv = document.createElement('canvas'); cv.width = W; cv.height = H;
      var x = cv.getContext('2d'), coul = c.dataset.couleur || '#b5442f';
      x.fillStyle = coul; x.fillRect(0, 0, W, H);
      x.fillStyle = 'rgba(0,0,0,.45)'; x.fillRect(0, 0, W, H);
      var ar = /[\u0600-\u06FF]/.test(c.dataset.titre);
      x.font = '700 38px system-ui, sans-serif';
      var cat = (c.dataset.categorie || '').toUpperCase(), lc = x.measureText(cat).width + 48;
      x.fillStyle = '#fff'; x.fillRect(80, 360, lc, 64);
      x.fillStyle = coul; x.fillText(cat, 104, 406);
      x.direction = ar ? 'rtl' : 'ltr'; x.textAlign = ar ? 'right' : 'left';
      var gauche = ar ? W - 80 : 80;
      x.fillStyle = '#fff';
      x.font = '800 92px system-ui, sans-serif';
      var y = 560;
      lignes(x, c.dataset.titre, W - 160).slice(0, 7).forEach(function (l) { x.fillText(l, gauche, y); y += 108; });
      y += 40; x.fillStyle = '#ffe2a8'; x.font = '700 52px system-ui, sans-serif';
      lignes(x, quand(c), W - 160).forEach(function (l) { x.fillText(l, gauche, y); y += 66; });
      y += 20; x.fillStyle = '#ddd'; x.font = '500 46px system-ui, sans-serif';
      lignes(x, '📍 ' + (c.dataset.lieu || ''), W - 160).slice(0, 4).forEach(function (l) { x.fillText(l, gauche, y); y += 60; });
      x.direction = 'ltr'; x.textAlign = 'left';
      x.fillStyle = '#fff'; x.font = '700 44px system-ui, sans-serif'; x.fillText('ToNight Tunis', 80, H - 170);
      x.fillStyle = '#eee'; x.font = '400 34px system-ui, sans-serif';
      x.fillText(location.host + (window.BASE || '/'), 80, H - 110);
      cv.toBlob(function (b) { b ? ok(b) : ko(new Error('image')); }, 'image/png');
    });
  }
  function menu(c, blob) {
    var texte = c.dataset.titre + ' · ' + quand(c) + '\n' + c.dataset.lien;
    var m = document.createElement('div'); m.className = 'menu-partage'; m.setAttribute('role', 'dialog');
    function bouton(etiquette, f) { var b = document.createElement('button'); b.type = 'button'; b.textContent = etiquette; b.onclick = f; m.appendChild(b); return b; }
    var wa = document.createElement('a'); wa.href = 'https://wa.me/?text=' + encodeURIComponent(texte); wa.rel = 'noopener'; wa.target = '_blank'; wa.textContent = 'WhatsApp'; m.appendChild(wa);
    var tg = document.createElement('a'); tg.href = 'https://t.me/share/url?url=' + encodeURIComponent(c.dataset.lien) + '&text=' + encodeURIComponent(c.dataset.titre); tg.rel = 'noopener'; tg.target = '_blank'; tg.textContent = 'Telegram'; m.appendChild(tg);
    var fb = document.createElement('a'); fb.href = 'https://www.facebook.com/sharer/sharer.php?u=' + encodeURIComponent(c.dataset.lien); fb.rel = 'noopener'; fb.target = '_blank'; fb.textContent = 'Facebook'; m.appendChild(fb);
    var cp = bouton(t('copier', 'Copier le lien'), function () {
      (navigator.clipboard ? navigator.clipboard.writeText(c.dataset.lien) : Promise.reject()).then(function () { cp.textContent = t('copie', 'Lien copié'); }, function () {});
    });
    if (blob) bouton(t('image', "Télécharger l'image"), function () { telecharger(blob, 'agenda-tunis.png'); });
    bouton(t('fermer', 'Fermer'), function () { m.remove(); });
    document.querySelectorAll('.menu-partage').forEach(function (x) { x.remove(); });
    document.body.appendChild(m);
  }
  function partager(c) {
    var texte = c.dataset.titre + ' · ' + quand(c) + ' · ' + (c.dataset.lieu || '');
    image(c).then(function (blob) {
      var f = new File([blob], 'agenda-tunis.png', { type: 'image/png' });
      if (navigator.canShare && navigator.canShare({ files: [f] })) {
        return navigator.share({ files: [f], title: c.dataset.titre, text: texte + '\n' + c.dataset.lien }).catch(function (e) {
          if (e.name !== 'AbortError') menu(c, blob);
        });
      }
      if (navigator.share) {
        return navigator.share({ title: c.dataset.titre, text: texte, url: c.dataset.lien }).catch(function (e) {
          if (e.name !== 'AbortError') menu(c, blob);
        });
      }
      menu(c, blob);
    }, function () { menu(c, null); });
  }

  document.addEventListener('click', function (ev) {
    var b = ev.target.closest('.fav, .ajout-agenda, .partager');
    if (!b) return;
    var c = b.closest('[data-id]');
    if (!c) return;
    ev.preventDefault();
    if (b.classList.contains('fav')) {
      var i = favoris.indexOf(c.dataset.id);
      if (i >= 0) favoris.splice(i, 1); else favoris.push(c.dataset.id);
      ecrire('favoris', JSON.stringify(favoris));
      marquerFavoris();
      document.dispatchEvent(new CustomEvent('favoris'));
    } else if (b.classList.contains('ajout-agenda')) {
      telecharger(new Blob([ics(c)], { type: 'text/calendar;charset=utf-8' }), 'evenement.ics');
    } else {
      partager(c);
    }
  });

  if (langue !== 'fr') traduire(); else document.querySelectorAll('[data-langue="fr"]').forEach(function (b) { b.classList.add('active'); });

  // ---- Grand écran : un clic sur un événement ouvre sa fiche dans un panneau à droite,
  // sans quitter la liste. Ctrl/Cmd+clic ou clic du milieu ouvrent toujours la vraie page.
  // Sur téléphone (écran étroit), rien ne change : le lien mène à la page.
  var large = window.matchMedia ? window.matchMedia('(min-width: 1100px)') : { matches: false };
  var panneau = null, carteChoisie = null, demande = 0;
  function fermerApercu() {
    if (panneau) { panneau.remove(); panneau = null; }
    if (carteChoisie) { carteChoisie.classList.remove('choisi'); carteChoisie = null; }
  }
  function ouvrirApercu(carte, url) {
    if (!panneau) {
      panneau = document.createElement('aside');
      panneau.className = 'apercu';
      panneau.setAttribute('aria-label', t('apercu', 'Aperçu'));
      document.body.appendChild(panneau);
    }
    if (carteChoisie) carteChoisie.classList.remove('choisi');
    carteChoisie = carte; carte.classList.add('choisi');
    panneau.innerHTML = '<div class="apercu-barre"><a class="ouvrir"></a><button type="button" class="fermer">×</button></div>' +
      '<p class="chargement">…</p>';
    var lien = panneau.querySelector('.ouvrir');
    lien.href = url; lien.textContent = t('ouvrir_page', 'Ouvrir la page') + ' ↗';
    var bf = panneau.querySelector('.fermer');
    bf.title = t('fermer', 'Fermer'); bf.setAttribute('aria-label', bf.title);
    bf.onclick = fermerApercu;
    var n = ++demande;
    fetch(url).then(function (r) { if (!r.ok) throw new Error(r.status); return r.text(); }).then(function (html) {
      if (n !== demande || !panneau) return;
      var fiche = new DOMParser().parseFromString(html, 'text/html').querySelector('.event-page');
      if (!fiche) throw new Error('fiche');
      if (d.classList.contains('leger')) fiche.querySelectorAll('img.affiche-grande').forEach(function (i) { i.remove(); });
      panneau.querySelector('.chargement').replaceWith(document.importNode(fiche, true));
      panneau.scrollTop = 0;
      traduire(); marquerFavoris();
    }).catch(function () { if (n === demande) location.href = url; });
  }
  document.addEventListener('click', function (ev) {
    if (!large.matches || ev.defaultPrevented || ev.button !== 0 || ev.ctrlKey || ev.metaKey || ev.shiftKey || ev.altKey) return;
    var a = ev.target.closest('.event h3 a, .event a.vignette');
    var carte = a && a.closest('.event');
    if (!carte || carte.classList.contains('event-page') || carte.closest('.apercu')) return;
    ev.preventDefault();
    ouvrirApercu(carte, a.href);
  });
  document.addEventListener('keydown', function (ev) { if (ev.key === 'Escape' && panneau) fermerApercu(); });
  if (large.addEventListener) large.addEventListener('change', function (m) { if (!m.matches) fermerApercu(); });


  // ---- Comprendre sans cliquer : aperçu au survol (souris) ou au toucher du bouton 👁 (téléphone),
  // et « Ce soir à Tunis » en tête de l'accueil. Tout vient des attributs data-* de la carte.
  var bulle = null, delaiBulle = 0, peutSurvoler = window.matchMedia ? window.matchMedia('(any-hover: hover) and (any-pointer: fine)') : { matches: false };
  function esc(x) { return (x || '').replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  // Fiche de film (page Au cinéma) : titre, badges, durée et synopsis, lus dans la fiche elle-même.
  function contenuFilm(c) {
    var titre = c.querySelector('h3'), meta = c.querySelector('.meta'), syn = c.querySelector('.synopsis p');
    var badges = Array.prototype.map.call(c.querySelectorAll('.badges .badge'), function (b) { return b.textContent.trim(); }).join(' · ');
    var texte = syn ? syn.textContent.replace(/\s+/g, ' ').trim() : '';
    if (texte.length > 420) texte = texte.slice(0, 420).replace(/\s+\S*$/, '') + '…';
    var infos = [badges, meta ? meta.textContent.trim() : ''].filter(Boolean).join(' · ');
    return '<div class="bulle-corps"><strong>' + esc(titre ? titre.textContent.trim() : '') + '</strong>' +
      (infos ? '<p class="bulle-infos">' + esc(infos) + '</p>' : '') +
      '<p class="bulle-texte">' + esc(texte || t('pas_de_synopsis', 'Pas de synopsis disponible')) + '</p></div>';
  }
  function contenuApercu(c) {
    if (c.classList.contains('film-fiche')) return contenuFilm(c);
    var titre = c.querySelector('h3'), meta = c.querySelector('.meta'), h = c.dataset.heure;
    var prix = c.dataset.prix || '', lignes = [];
    var resume = c.dataset['resume' + langue.charAt(0).toUpperCase() + langue.slice(1)] || c.dataset.resume;
    if (resume !== c.dataset.resume && window._decoder) resume = window._decoder(resume);
    if (h) lignes.push('🕗 ' + h.replace(':', 'h').replace(/h00$/, 'h') + (c.dataset.heureFin ? ' – ' + c.dataset.heureFin.replace(':', 'h').replace(/h00$/, 'h') : ''));
    var lieu = c.dataset.lieu === 'Lieu à préciser' ? t('lieu_preciser', c.dataset.lieu) : c.dataset.lieu;
    if (lieu) lignes.push('📍 ' + esc(lieu));
    if (c.hasAttribute('data-gratuit')) lignes.push('✓ ' + esc(t('gratuit', 'Gratuit')));
    else if (prix) lignes.push('🎟 ' + esc(prix));
    return (c.dataset.image ? '<img src="' + esc(c.dataset.image) + '" alt="" loading="lazy">' : '') +
      '<div class="bulle-corps"><span class="tag" style="background:' + esc(c.dataset.couleur) + '">' + esc(c.dataset.categorie) + '</span>' +
      '<strong>' + esc((titre && titre.textContent.trim()) || c.dataset.titre) + '</strong>' +
      (lignes.length ? '<p class="bulle-infos">' + lignes.join(' · ') + '</p>' : (meta ? '<p class="bulle-infos">' + esc(meta.textContent.trim()) + '</p>' : '')) +
      (resume ? '<p class="bulle-texte">' + esc(resume) + '</p>' : '') + '</div>';
  }
  function fermerBulle() {
    clearTimeout(delaiBulle);
    if (bulle) { bulle.remove(); bulle = null; }
    document.querySelectorAll('.feuille-fond').forEach(function (x) { x.remove(); });
  }
  function montrerBulle(c, feuille) {
    fermerBulle();
    bulle = document.createElement('div');
    bulle.className = feuille ? 'bulle feuille' : 'bulle';
    bulle.setAttribute('role', feuille ? 'dialog' : 'tooltip');
    bulle.innerHTML = contenuApercu(c);
    if (feuille) {
      var fond = document.createElement('div'); fond.className = 'feuille-fond'; fond.onclick = fermerBulle;
      document.body.appendChild(fond);
      var lien = document.createElement('a'); lien.className = 'bulle-ouvrir'; lien.href = c.dataset.lien;
      lien.textContent = t('ouvrir_page', 'Ouvrir la page') + ' ↗';
      bulle.appendChild(lien);
    }
    document.body.appendChild(bulle);
    if (!feuille) {
      var r = c.getBoundingClientRect(), b = bulle.getBoundingClientRect();
      var x = Math.min(Math.max(8, r.left + 16), window.innerWidth - b.width - 8);
      var y = r.bottom + 6 + b.height > window.innerHeight - 8 ? Math.max(8, r.top - b.height - 6) : r.bottom + 6;
      bulle.style.left = x + 'px'; bulle.style.top = y + 'px';
    }
  }
  // Certains navigateurs (Firefox avec protection renforcée, écrans tactiles + souris…) annoncent mal (any-hover) :
  // on se fie aussi au type du dernier pointeur vu (souris ou stylet = survol possible, doigt = non).
  var sourisVue = false;
  document.addEventListener('pointerover', function (ev) { sourisVue = ev.pointerType === 'mouse' || ev.pointerType === 'pen'; }, true);
  function survolPossible() { return sourisVue || peutSurvoler.matches; }
  document.addEventListener('mouseover', function (ev) {
    if (!survolPossible()) return;
    var c = ev.target.closest && ev.target.closest('.event, .film-fiche');
    if (!c || c.classList.contains('event-page') || c.closest('.apercu')) { return; }
    if (c === ev.relatedTarget || c.contains(ev.relatedTarget)) return;
    clearTimeout(delaiBulle);
    delaiBulle = setTimeout(function () { montrerBulle(c, false); }, 450);
  });
  document.addEventListener('mouseout', function (ev) {
    if (!survolPossible()) return;
    var c = ev.target.closest && ev.target.closest('.event, .film-fiche');
    if (!c || c.contains(ev.relatedTarget)) return;
    fermerBulle();
  });
  document.addEventListener('click', function (ev) {
    var b = ev.target.closest && ev.target.closest('.apercu-rapide');
    if (!b) return;
    ev.preventDefault();
    montrerBulle(b.closest('.event'), true);
  });
  document.addEventListener('keydown', function (ev) { if (ev.key === 'Escape') fermerBulle(); });
  window.addEventListener('scroll', function () { if (bulle && !bulle.classList.contains('feuille')) fermerBulle(); }, { passive: true });

  // « Ce soir à Tunis » : les événements d'aujourd'hui avec une heure, classés par heure, avec le temps qui reste.
  (function () {
    var zone = document.getElementById('ce-soir'), liste = document.getElementById('ce-soir-liste');
    if (!zone || !liste) return;
    var aujourdhui = iso(new Date()), maintenant = new Date(), vus = {}, items = [];
    document.querySelectorAll('#agenda .event, #en-cours .event').forEach(function (c) {
      var h = c.dataset.heure;
      if (!h || c.dataset.debut !== aujourdhui || c.dataset.date !== aujourdhui || vus[c.dataset.id]) return;
      if (c.classList.contains('discret') || c.hasAttribute('hidden')) return;
      vus[c.dataset.id] = 1;
      var hm = h.split(':'), debut = new Date(); debut.setHours(+hm[0], +hm[1], 0, 0);
      // Commencé depuis plus de 2 h : on ne le propose plus
      if (maintenant - debut > 2 * 3600 * 1000) return;
      items.push({ c: c, h: h, debut: debut });
    });
    if (!items.length) return;
    items.sort(function (a, b) { return a.h < b.h ? -1 : a.h > b.h ? 1 : 0; });
    // Le titre suit l'heure des événements affichés : « Ce matin » (avant 12 h), « Cet après-midi » (12 h à 17 h),
    // « Ce soir » (à partir de 17 h) ; « Aujourd'hui » si la liste mêle plusieurs moments de la journée.
    var affiches = items.slice(0, 8);
    var moments = affiches.map(function (it) { return it.h < '12:00' ? 'matin' : it.h < '17:00' ? 'apres_midi' : 'soir'; });
    var cleTitre = moments.every(function (m) { return m === moments[0]; })
      ? { matin: 'ce_soir_matin', apres_midi: 'ce_soir_apres_midi', soir: 'ce_soir_titre' }[moments[0]] : 'ce_soir_jour';
    var titre = zone.querySelector('[data-t]');
    if (titre && I18N[cleTitre]) {
      titre.dataset.t = cleTitre; titre._fr = I18N[cleTitre].fr;
      titre.textContent = t(cleTitre, I18N[cleTitre].fr);
    }
    affiches.forEach(function (it) {
      var min = Math.round((it.debut - maintenant) / 60000), reste;
      if (min <= 0) reste = t('en_cours_maintenant', 'a commencé');
      else if (min < 60) reste = t('dans', 'dans') + ' ' + min + ' min';
      else reste = t('dans', 'dans') + ' ' + Math.floor(min / 60) + ' h' + (min % 60 ? (' ' + ('0' + (min % 60)).slice(-2)) : '');
      var a = document.createElement('li');
      a.innerHTML = '<span class="frise-heure">' + it.h.replace(':', 'h').replace(/h00$/, 'h') + '</span>' +
        '<a href="' + esc(it.c.dataset.lien) + '">' + esc(it.c.dataset.titre) + '</a>' +
        '<span class="frise-lieu">' + esc((it.c.dataset.lieu || '').split(',')[0]) + '</span>' +
        '<span class="frise-reste">' + esc(reste) + '</span>';
      liste.appendChild(a);
    });
    zone.hidden = false;
  })();

  // ---- Appli installable : le service worker garde les pages pour les consulter hors connexion
  if ('serviceWorker' in navigator && location.protocol === 'https:') {
    navigator.serviceWorker.register((window.BASE || '/') + 'sw.js').catch(function () {});
  }

  // ---- Bouton « Installer l'application » : un clic sur Chrome, Edge et Android (beforeinstallprompt) ;
  // ailleurs (iPhone/Safari, Firefox), pas de clic unique possible : on affiche une aide pas à pas.
  var invite = null;
  var zone = document.getElementById('installer-zone');
  var boutons = document.querySelectorAll('[data-installer]');
  var installee = (window.matchMedia && matchMedia('(display-mode: standalone)').matches) || navigator.standalone === true;
  function montrerBoutons(v) { boutons.forEach(function (b) { b.hidden = !v; }); if (zone) zone.hidden = !v && !aideVisible; }
  var aideVisible = false;
  function montrerAide() {
    var aide = document.getElementById('aide-installer'); if (!aide || installee) return;
    var ua = navigator.userAgent, ios = /iPad|iPhone|iPod/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1);
    document.getElementById('aide-ios').hidden = !ios;
    document.getElementById('aide-autre').hidden = ios;
    aide.hidden = false; aideVisible = true; if (zone) zone.hidden = false;
  }
  window.addEventListener('beforeinstallprompt', function (e) {
    e.preventDefault(); invite = e;
    var aide = document.getElementById('aide-installer'); if (aide) aide.hidden = true; aideVisible = false;
    montrerBoutons(true);
  });
  boutons.forEach(function (b) {
    b.addEventListener('click', function () {
      if (!invite) return;
      invite.prompt(); invite = null; montrerBoutons(false);
    });
  });
  window.addEventListener('appinstalled', function () { invite = null; montrerBoutons(false); if (zone) zone.hidden = true; });
  // Si le navigateur n'a pas proposé l'installation au bout d'un moment, on montre l'aide (sauf appli déjà installée).
  if (!installee) setTimeout(function () { if (!invite) montrerAide(); }, 1500);
})();
