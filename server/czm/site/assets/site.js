/* counter-zombie.ru: language, day/night lamp, parallax, embers, screenshot strip, live numbers and chat. */
(function () {
  'use strict';
  var doc = document, root = doc.documentElement;
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var $ = function (id) { return doc.getElementById(id); };
  var all = function (sel) { return Array.prototype.slice.call(doc.querySelectorAll(sel)); };
  var store = {
    get: function (k) { try { return window.localStorage.getItem(k); } catch (e) { return null; } },
    set: function (k, v) { try { window.localStorage.setItem(k, v); } catch (e) { /* private mode */ } }
  };

  var TEXT = {
    ru: {
      title: 'Counter Zombie Mobile — зомби-шутер для Android',
      description: 'Мобильный зомби-шутер: орды зомби, серверы до 32 игроков, свои кнопки, друзья и живой чат. Скачай бесплатно для Android.',
      langLabel: 'Язык', themeLabel: 'День или ночь', share: 'Поделиться', copied: 'Ссылка скопирована', close: 'Закрыть', prev: 'Назад', next: 'Дальше',
      tagline: 'Мобильный зомби-шутер: орды зомби, серверы до 32 игроков, свои кнопки, друзья и живой чат.',
      downloadCta: 'Скачать игру', statsLabel: 'Статистика', online: 'в игре', offline: 'не в сети', downloads: 'скачиваний', mb: 'МБ',
      shotsTitle: 'Кадры',
      shots: ['Бой на базе', 'Отряд у ворот', 'Зомби в храме', 'Вертолёт и орда', 'Главное меню', 'Серверы', 'Друзья', 'Управление', 'Профиль, аватары и спреи'],
      featTitle: 'Возможности',
      feats: [
        ['Серверы', 'Большой список серверов с зомби-режимами: фильтры, избранное, пинг и быстрая игра одной кнопкой.'],
        ['Кнопки и HUD', 'Расставь кнопки, здоровье, деньги, радар и чат как удобно. Три схемы управления и три вида радара, перекрытия видно сразу.'],
        ['Друзья и чат', 'Друзья, подписки, личные сообщения и приглашения в игру. Мировой чат Global, RU и EN.'],
        ['Профиль и облако', 'Ник, аватар или своё фото, спреи. Вход по нику или коду на почту, настройки возвращаются после переустановки.'],
        ['Обновления', 'Новые версии приходят прямо в игре и скачиваются только изменения.']
      ],
      chatTitle: 'Чат игры', chatShort: 'Чат', chatOpen: 'Открыть чат', chatLock: 'Писать можно только в игре',
      roomsLabel: 'Комнаты чата', chatEmpty: 'В этой комнате пока тихо', chatLoading: 'Загружаем чат…',
      chatError: 'Чат сейчас не отвечает, попробуем ещё раз через несколько секунд', all: 'Все',
      dlTitle: 'Заходи в игру', dlText: 'Бесплатно. Ссылка всегда ведёт на свежую версию, дальше игра обновляется сама.', dlButton: 'Скачать APK',
      newsTitle: 'Что нового', version: 'Версия', mail: 'Почта', privacy: 'Конфиденциальность',
      betaTitle: 'Бета-тест в Google Play', betaShort: 'Бета-тест',
      betaCount: 'подтвердили участие', betaCountNote: 'Данные Google Play Console, проверяются вручную',
      betaLead: 'Набираем 50 тестировщиков с запасом! Google требует минимум 12 участников на 14 дней. Присоединяйся и играй.',
      beta1: 'Вступи в группу тестировщиков', beta1Note: 'Нужен аккаунт Google — тот же, что в Google Play на телефоне.', beta1Btn: 'Вступить',
      beta2: 'Прими приглашение', beta2Note: 'Откроется Google Play. Если приглашения нет, проверь шаг 1.', beta2Btn: 'Стать тестером',
      beta3: 'Установи и играй', beta3Note: 'Заходи в игру хотя бы пару раз в неделю: Google проверяет, что тест живой.', beta3Btn: 'Открыть в Google Play'
    },
    en: {
      title: 'Counter Zombie Mobile — a zombie shooter for Android',
      description: 'A mobile zombie shooter: zombie hordes, servers for up to 32 players, your own buttons, friends and a live chat. Free for Android.',
      langLabel: 'Language', themeLabel: 'Day or night', share: 'Share', copied: 'Link copied', close: 'Close', prev: 'Previous', next: 'Next',
      tagline: 'A mobile zombie shooter: zombie hordes, servers for up to 32 players, your own buttons, friends and a live chat.',
      downloadCta: 'Get the game', statsLabel: 'Statistics', online: 'playing', offline: 'offline', downloads: 'downloads', mb: 'MB',
      shotsTitle: 'Shots',
      shots: ['Fight at the base', 'Squad at the gate', 'Zombies in the temple', 'Helicopter and the horde', 'Main menu', 'Servers', 'Friends', 'Controls', 'Profile, avatars and sprays'],
      featTitle: 'Features',
      feats: [
        ['Servers', 'A big list of zombie-mode servers: filters, favourites, ping and quick play in one tap.'],
        ['Buttons and HUD', 'Place buttons, health, money, radar and chat where you like. Three control schemes and three radar styles, overlaps show at once.'],
        ['Friends and chat', 'Friends, follows, private messages and game invites. A world chat: Global, RU and EN.'],
        ['Profile and cloud', 'Nickname, avatar or your own photo, sprays. Sign in with a nickname or an email code, settings come back after a reinstall.'],
        ['Updates', 'New versions arrive in the game, and only the changes are downloaded.']
      ],
      chatTitle: 'Game chat', chatShort: 'Chat', chatOpen: 'Open chat', chatLock: 'You can only write in the game',
      roomsLabel: 'Chat rooms', chatEmpty: 'Quiet in this room so far', chatLoading: 'Loading the chat…',
      chatError: 'The chat is not answering, trying again in a few seconds', all: 'All',
      dlTitle: 'Join the game', dlText: 'Free. The link always leads to the latest version, then the game updates itself.', dlButton: 'Download APK',
      newsTitle: 'What’s new', version: 'Version', mail: 'Email', privacy: 'Privacy',
      betaTitle: 'Google Play beta test', betaShort: 'Beta test',
      betaCount: 'confirmed testers', betaCountNote: 'Google Play Console data, checked manually',
      betaLead: 'Our goal is 50 testers as a safety margin! Google requires at least 12 opted-in testers for 14 days. Join and play.',
      beta1: 'Join the testers group', beta1Note: 'You need a Google account, the same one as in Google Play on your phone.', beta1Btn: 'Join',
      beta2: 'Accept the invitation', beta2Note: 'Google Play opens. If there is no invitation, check step 1.', beta2Btn: 'Become a tester',
      beta3: 'Install and play', beta3Note: 'Play at least a couple of times a week: Google checks that the test is alive.', beta3Btn: 'Open in Google Play'
    }
  };
  var FEAT_SHOTS = [6, 8, 7, 9, 5];
  var lang = store.get('czm-lang');
  if (lang !== 'ru' && lang !== 'en') lang = /^(ru|uk|be|kk)\b/i.test(navigator.language || 'ru') ? 'ru' : 'en';
  var T = TEXT[lang];

  /* ---------- language ---------- */
  function applyLang() {
    T = TEXT[lang];
    root.lang = lang;
    doc.title = T.title;
    var meta = doc.querySelector('meta[name="description"]');
    if (meta) meta.setAttribute('content', T.description);
    all('[data-i18n]').forEach(function (el) {
      var v = T[el.getAttribute('data-i18n')];
      if (typeof v === 'string') el.textContent = v;
    });
    all('[data-i18n-aria]').forEach(function (el) {
      var v = T[el.getAttribute('data-i18n-aria')];
      if (typeof v === 'string') el.setAttribute('aria-label', v);
    });
    all('[data-lang]').forEach(function (b) { b.setAttribute('aria-pressed', String(b.getAttribute('data-lang') === lang)); });
    buildStrip();
    buildFeatures();
    renderStats(true);
    renderChat(false);
    renderNews();
  }
  all('[data-lang]').forEach(function (b) {
    b.addEventListener('click', function () {
      var next = b.getAttribute('data-lang');
      if (next === lang) return;
      lang = next;
      store.set('czm-lang', lang);
      applyLang();
    });
  });

  /* ---------- day / night lamp ---------- */
  var lamp = $('lamp'), flash = $('flash');
  function paintLamp() {
    var svg = lamp.querySelector('svg');
    if (svg) svg.setAttribute('class', root.classList.contains('light') ? '' : 'lamp-on');
  }
  paintLamp();
  lamp.addEventListener('click', function () {
    var toLight = !root.classList.contains('light');
    var swap = function () {
      root.classList.toggle('light', toLight);
      store.set('czm-theme', toLight ? 'light' : 'dark');
      paintLamp();
    };
    if (reduce) { swap(); return; }
    flash.classList.remove('on');
    void flash.offsetWidth;
    flash.classList.add('on');
    setTimeout(swap, 260);
    setTimeout(function () { flash.classList.remove('on'); }, 650);
  });

  /* ---------- hero parallax (mouse only: on phones the picture stays still) ---------- */
  var hero = $('top');
  function setTilt(x, y) {
    hero.style.setProperty('--mx', x.toFixed(3));
    hero.style.setProperty('--my', y.toFixed(3));
  }
  if (!reduce) {
    hero.addEventListener('pointermove', function (e) {
      if (e.pointerType === 'touch') return;
      var r = hero.getBoundingClientRect();
      setTilt(((e.clientX - r.left) / r.width - 0.5) * 2, ((e.clientY - r.top) / r.height - 0.5) * 2);
    });
    hero.addEventListener('pointerleave', function () { setTilt(0, 0); });
  }

  /* ---------- embers ---------- */
  var heroVisible = true;
  if ('IntersectionObserver' in window) {
    new IntersectionObserver(function (entries) {
      heroVisible = entries[0].isIntersecting;
      if (heroVisible) startEmbers();
    }).observe(hero);
  }
  var cv = $('embers'), ctx = cv && cv.getContext ? cv.getContext('2d') : null, parts = [], raf = 0;
  function spawn(w, h, anywhere) {
    return {
      x: Math.random() * w, y: anywhere ? Math.random() * h : h + 10,
      r: 0.6 + Math.random() * 2.2, vy: 0.25 + Math.random() * 0.9, vx: (Math.random() - 0.5) * 0.3,
      life: 0, max: 260 + Math.random() * 380, hue: 8 + Math.random() * 30, wob: Math.random() * 6.28
    };
  }
  function frame() {
    raf = 0;
    if (!heroVisible || doc.hidden) return;
    var dpr = Math.min(2, window.devicePixelRatio || 1);
    var w = cv.clientWidth, h = cv.clientHeight;
    if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) {
      cv.width = Math.round(w * dpr);
      cv.height = Math.round(h * dpr);
    }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    var want = w < 640 ? 34 : 70;
    while (parts.length < want) parts.push(spawn(w, h, parts.length < want / 2));
    ctx.globalCompositeOperation = 'lighter';
    for (var i = parts.length - 1; i >= 0; i--) {
      var p = parts[i];
      p.life += 1; p.wob += 0.03;
      p.x += p.vx + Math.sin(p.wob) * 0.35; p.y -= p.vy;
      var k = p.life / p.max;
      if (k >= 1 || p.y < -10) { parts.splice(i, 1); continue; }
      var a = Math.sin(Math.PI * k) * (0.55 + 0.45 * Math.sin(p.life * 0.2));
      var g = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, p.r * 4);
      g.addColorStop(0, 'hsla(' + p.hue + ',100%,62%,' + a + ')');
      g.addColorStop(1, 'hsla(' + p.hue + ',100%,50%,0)');
      ctx.fillStyle = g;
      ctx.beginPath(); ctx.arc(p.x, p.y, p.r * 4, 0, 6.283); ctx.fill();
    }
    raf = requestAnimationFrame(frame);
  }
  function startEmbers() {
    if (reduce || !ctx || raf) return;
    raf = requestAnimationFrame(frame);
  }
  startEmbers();

  /* ---------- screenshot strip and viewer ---------- */
  var strip = $('strip'), box = $('box'), boxImg = $('boxImg'), boxCap = $('boxCap');
  var shotIndex = 0, pausedUntil = 0, boxAt = -1, stripVisible = true, lastFocus = null;
  var V = root.getAttribute('data-v') || '';
  function shotSrc(i) { return '/assets/shot-' + (i + 1) + '.webp' + (V ? '?v=' + V : ''); }
  function buildStrip() {
    strip.textContent = '';
    T.shots.forEach(function (name, i) {
      var b = doc.createElement('button');
      b.type = 'button';
      b.setAttribute('aria-label', name);
      var img = doc.createElement('img');
      img.src = shotSrc(i);
      img.alt = name;
      img.width = (i === 1 || i === 2) ? 1066 : 1287;
      img.height = 600;
      img.decoding = 'async';
      if (i > 2) img.loading = 'lazy';
      b.appendChild(img);
      b.addEventListener('click', function () { openBox(i); });
      strip.appendChild(b);
    });
  }
  var pauseStrip = function () { pausedUntil = Date.now() + 9000; };
  ['pointerdown', 'wheel', 'touchstart', 'focusin'].forEach(function (ev) { strip.addEventListener(ev, pauseStrip, { passive: true }); });
  if ('IntersectionObserver' in window) {
    new IntersectionObserver(function (e) { stripVisible = e[0].isIntersecting; }).observe(strip);
  }
  if (!reduce) {
    setInterval(function () {
      if (Date.now() < pausedUntil || boxAt >= 0 || doc.hidden || !stripVisible) return;
      var items = strip.children;
      if (!items.length) return;
      shotIndex = (shotIndex + 1) % items.length;
      if (strip.scrollLeft + strip.clientWidth >= strip.scrollWidth - 4) shotIndex = 0;
      strip.scrollTo({ left: shotIndex === 0 ? 0 : items[shotIndex].offsetLeft - 16, behavior: 'smooth' });
    }, 3500);
  }
  function showBox() {
    boxImg.src = shotSrc(boxAt);
    boxImg.alt = T.shots[boxAt];
    boxCap.textContent = T.shots[boxAt] + ' · ' + (boxAt + 1) + '/' + T.shots.length;
  }
  function openBox(i) {
    pauseStrip();
    lastFocus = doc.activeElement;
    boxAt = i;
    showBox();
    box.classList.add('on');
    box.setAttribute('aria-hidden', 'false');
    box.querySelector('.x').focus();
  }
  function closeBox() {
    if (boxAt < 0) return;
    boxAt = -1;
    box.classList.remove('on');
    box.setAttribute('aria-hidden', 'true');
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }
  function stepBox(d) {
    if (boxAt < 0) return;
    boxAt = (boxAt + d + T.shots.length) % T.shots.length;
    showBox();
  }
  $('boxPrev').addEventListener('click', function () { stepBox(-1); });
  $('boxNext').addEventListener('click', function () { stepBox(1); });
  box.addEventListener('click', function (e) { if (e.target === box) closeBox(); });
  var touchX = null;
  box.addEventListener('touchstart', function (e) { touchX = e.touches[0].clientX; }, { passive: true });
  box.addEventListener('touchend', function (e) {
    if (touchX == null) return;
    var dx = e.changedTouches[0].clientX - touchX;
    touchX = null;
    if (Math.abs(dx) > 50) stepBox(dx < 0 ? 1 : -1);
  });

  /* ---------- feature tabs ---------- */
  var tabs = $('tabs'), panels = $('panels'), feat = 0;
  function buildFeatures() {
    tabs.textContent = '';
    panels.textContent = '';
    T.feats.forEach(function (f, i) {
      var on = i === feat;
      var tab = doc.createElement('button');
      tab.type = 'button';
      tab.className = 'tab';
      tab.id = 'tab-' + i;
      tab.setAttribute('role', 'tab');
      tab.setAttribute('aria-selected', String(on));
      tab.setAttribute('aria-controls', 'panel-' + i);
      tab.tabIndex = on ? 0 : -1;
      var dot = doc.createElement('span');
      dot.className = 'dot';
      tab.appendChild(dot);
      tab.appendChild(doc.createTextNode(f[0]));
      tab.addEventListener('click', function () { pickFeature(i, false); });
      tabs.appendChild(tab);

      var panel = doc.createElement('div');
      panel.className = 'panel card' + (on ? ' on' : '');
      panel.id = 'panel-' + i;
      panel.setAttribute('role', 'tabpanel');
      panel.setAttribute('aria-labelledby', 'tab-' + i);
      if (!on) panel.setAttribute('aria-hidden', 'true');
      var pic = doc.createElement('div');
      pic.className = 'pic';
      pic.style.backgroundImage = 'url(' + shotSrc(FEAT_SHOTS[i] - 1) + ')';
      var txt = doc.createElement('div');
      txt.className = 'txt';
      var h = doc.createElement('h3');
      h.className = 'h-game';
      h.textContent = f[0];
      var p = doc.createElement('p');
      p.textContent = f[1];
      txt.appendChild(h);
      txt.appendChild(p);
      panel.appendChild(pic);
      panel.appendChild(txt);
      panels.appendChild(panel);
    });
  }
  function pickFeature(i, focus) {
    feat = i;
    all('#tabs .tab').forEach(function (t, n) {
      t.setAttribute('aria-selected', String(n === i));
      t.tabIndex = n === i ? 0 : -1;
      if (n === i && focus) t.focus();
    });
    all('#panels .panel').forEach(function (p, n) {
      p.classList.toggle('on', n === i);
      if (n === i) p.removeAttribute('aria-hidden'); else p.setAttribute('aria-hidden', 'true');
    });
  }
  tabs.addEventListener('keydown', function (e) {
    var n = T.feats.length;
    if (e.key === 'ArrowDown' || e.key === 'ArrowRight') { e.preventDefault(); pickFeature((feat + 1) % n, true); }
    else if (e.key === 'ArrowUp' || e.key === 'ArrowLeft') { e.preventDefault(); pickFeature((feat + n - 1) % n, true); }
    else if (e.key === 'Home') { e.preventDefault(); pickFeature(0, true); }
    else if (e.key === 'End') { e.preventDefault(); pickFeature(n - 1, true); }
  });

  /* ---------- chat sheet ---------- */
  var sheet = $('sheet'), veil = $('veil');
  var openPanel = null, panelFocus = null;
  function setOpen(el, on) {
    el.classList.toggle('on', on);
    el.setAttribute('aria-hidden', String(!on));
  }
  function closePanels() {
    if (!openPanel) return;
    setOpen(sheet, false);
    veil.classList.remove('on');
    all('[data-open-chat][aria-expanded]').forEach(function (b) { b.setAttribute('aria-expanded', 'false'); });
    root.style.overflow = '';
    openPanel = null;
    if (panelFocus && panelFocus.focus && doc.contains(panelFocus)) panelFocus.focus();
    panelFocus = null;
  }
  function openOne(el) {
    var keep = openPanel ? panelFocus : doc.activeElement;
    if (openPanel && openPanel !== el) { setOpen(openPanel, false); }
    setOpen(el, true);
    veil.classList.add('on');
    root.style.overflow = 'hidden';
    openPanel = el;
    panelFocus = keep;
    all('[data-open-chat][aria-expanded]').forEach(function (b) { b.setAttribute('aria-expanded', String(el === sheet)); });
    var first = el.querySelector('[data-close]');
    if (first) setTimeout(function () { first.focus({ preventScroll: true }); }, 50);
    if (el === sheet) { renderChat(false); scrollChatDown(); }
  }
  veil.addEventListener('click', closePanels);
  all('[data-open-chat]').forEach(function (b) {
    b.addEventListener('click', function (e) { e.preventDefault(); openOne(sheet); });
  });
  all('[data-close]').forEach(function (b) {
    b.addEventListener('click', function () {
      if (b.closest('#box')) closeBox(); else closePanels();
    });
  });
  doc.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') { if (boxAt >= 0) closeBox(); else closePanels(); }
    else if (boxAt >= 0 && e.key === 'ArrowRight') stepBox(1);
    else if (boxAt >= 0 && e.key === 'ArrowLeft') stepBox(-1);
  });

  /* ---------- Google Play: store buttons and the beta test ---------- */
  if (root.getAttribute('data-play-public') === '1') {
    all('[data-play-public]').forEach(function (el) { el.hidden = false; });
  }
  var beta = $('beta');
  var betaLinks = beta ? { group: beta.getAttribute('data-group') || '', optin: beta.getAttribute('data-optin') || '',
    store: beta.getAttribute('data-store') || '' } : {};
  function betaStep() {
    var n = parseInt(store.get('czm-beta') || '0', 10);
    return n >= 0 && n <= 3 ? n : 0;
  }
  function paintBeta() {
    var done = betaStep();
    all('#beta .step').forEach(function (li) {
      var n = parseInt(li.getAttribute('data-step'), 10);
      var link = li.querySelector('[data-beta]');
      li.classList.toggle('done', n <= done);
      li.classList.toggle('locked', n > done + 1);
      if (n > done + 1) link.setAttribute('aria-disabled', 'true'); else link.removeAttribute('aria-disabled');
    });
  }
  if (beta && /^https:\/\/groups\.google\.com\//.test(betaLinks.group)) {
    beta.hidden = false;
    all('[data-beta-link]').forEach(function (el) { el.hidden = false; });
    all('#beta [data-beta]').forEach(function (a) {
      a.href = betaLinks[a.getAttribute('data-beta')];
      a.addEventListener('click', function () {
        var n = parseInt(a.closest('.step').getAttribute('data-step'), 10);
        if (n > betaStep()) store.set('czm-beta', String(n));
        setTimeout(paintBeta, 400);
      });
    });
    paintBeta();
  }

  /* ---------- share ---------- */
  var toast = $('toast'), toastTimer = 0;
  function say(text) {
    toast.textContent = text;
    toast.classList.add('on');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toast.classList.remove('on'); }, 2600);
  }
  $('share').addEventListener('click', function () {
    var url = 'https://counter-zombie.ru/';
    if (navigator.share) {
      navigator.share({ title: 'Counter Zombie Mobile', text: T.tagline, url: url }).catch(function () { /* closed */ });
      return;
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(url).then(function () { say(T.copied); }, function () { say(url); });
    } else {
      say(url);
    }
  });

  /* ---------- live numbers ---------- */
  var stats = null, shown = { online: null, offline: null, downloads: null };
  function fmt(n) { return Number(n).toLocaleString(lang === 'ru' ? 'ru-RU' : 'en-US'); }
  function countTo(key, el, target, instant) {
    var from = shown[key];
    shown[key] = target;
    if (instant || reduce || from == null || from === target) { el.textContent = fmt(target); return; }
    var t0 = performance.now(), dur = 700;
    (function step(t) {
      var k = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - k, 3);
      el.textContent = fmt(Math.round(from + (target - from) * e));
      if (k < 1 && shown[key] === target) requestAnimationFrame(step);
    })(t0);
  }
  function renderStats(instant) {
    if (!stats) return;
    countTo('online', $('sOnline'), stats.online, instant);
    countTo('offline', $('sOffline'), stats.offline, instant);
    countTo('downloads', $('sDownloads'), stats.downloads, instant);
    if ($('sBetaTesters') && typeof stats.play_beta_testers === 'number') {
      $('sBetaTesters').textContent = fmt(stats.play_beta_testers);
      $('sBetaBar').style.width = Math.min(100, stats.play_beta_testers / 50 * 100) + '%';
      $('sBetaTrack').setAttribute('aria-valuenow', String(Math.min(50, stats.play_beta_testers)));
    }
    if (stats.size_mb) { $('sSize').textContent = fmt(stats.size_mb); $('dSize').textContent = fmt(stats.size_mb); }
    $('dVersion').textContent = stats.version ? T.version + ' ' + stats.version : '—';
  }
  function loadStats() {
    if (doc.hidden) return;
    fetch('/api/v1/site/stats', { cache: 'no-store' }).then(function (r) { return r.ok ? r.json() : null; }).then(function (d) {
      if (!d || typeof d.online !== 'number') return;
      var first = !stats;
      stats = d;
      if (first) { shown.online = 0; shown.offline = 0; shown.downloads = 0; }
      renderStats(false);
    }).catch(function () { /* the numbers stay as they are */ });
  }

  /* ---------- chat broadcast ---------- */
  var msgs = [], lastId = 0, room = 'all', chatState = 'loading', freshIds = {};
  var list = $('list'), preview = $('preview'), roomsEl = $('rooms');
  var AVATAR = /^\/(assets|avatars)\/[\w.\-]+(\?v=[\w\-]+)?$/;
  function when(ts) {
    var d = new Date(ts * 1000), p = function (n) { return (n < 10 ? '0' : '') + n; };
    return p(d.getDate()) + '.' + p(d.getMonth() + 1) + ' ' + p(d.getHours()) + ':' + p(d.getMinutes());
  }
  function messageNode(m, small) {
    var row = doc.createElement('div');
    row.className = 'msg' + (freshIds[m.id] && !small ? ' new' : '');
    var img = doc.createElement('img');
    img.alt = '';
    img.width = small ? 30 : 36;
    img.height = small ? 30 : 36;
    img.loading = 'lazy';
    img.src = AVATAR.test(m.avatar || '') ? m.avatar : '/assets/logo-96.png';
    img.onerror = function () { img.onerror = null; img.src = '/assets/logo-96.png'; };
    row.appendChild(img);
    var who = doc.createElement('div');
    who.className = 'who';
    var nick = doc.createElement('span');
    nick.className = 'nick';
    nick.textContent = m.nick;
    who.appendChild(nick);
    if (!small) {
      var rm = doc.createElement('span');
      rm.className = 'tag';
      rm.textContent = String(m.room).toUpperCase();
      var tm = doc.createElement('span');
      tm.className = 'time';
      tm.textContent = when(m.ts);
      who.appendChild(rm);
      who.appendChild(tm);
    }
    var text = doc.createElement('p');
    text.textContent = m.text;
    if (small) {
      row.appendChild(nick);
      text.style.flex = '1';
      row.appendChild(text);
      return row;
    }
    var body = doc.createElement('div');
    body.style.minWidth = '0';
    body.style.flex = '1';
    body.appendChild(who);
    body.appendChild(text);
    row.appendChild(body);
    return row;
  }
  function emptyNode(text) {
    var d = doc.createElement('div');
    d.className = 'empty';
    d.textContent = text;
    return d;
  }
  function buildRooms() {
    roomsEl.textContent = '';
    ['all', 'global', 'ru', 'en'].forEach(function (id) {
      var b = doc.createElement('button');
      b.type = 'button';
      b.className = 'room';
      b.setAttribute('role', 'tab');
      b.setAttribute('aria-selected', String(room === id));
      var count = id === 'all' ? msgs.length : msgs.filter(function (m) { return m.room === id; }).length;
      b.appendChild(doc.createTextNode((id === 'all' ? T.all : id.toUpperCase()) + ' '));
      var i = doc.createElement('i');
      i.textContent = String(count);
      b.appendChild(i);
      b.addEventListener('click', function () { room = id; renderChat(false); scrollChatDown(); });
      roomsEl.appendChild(b);
    });
  }
  function nearBottom() { return list.scrollHeight - list.scrollTop - list.clientHeight < 80; }
  function scrollChatDown() { list.scrollTop = list.scrollHeight; }
  function renderChat(keepScroll) {
    var stick = !keepScroll || nearBottom();
    buildRooms();
    preview.textContent = '';
    list.textContent = '';
    if (!msgs.length) {
      var t = chatState === 'loading' ? T.chatLoading : chatState === 'error' ? T.chatError : T.chatEmpty;
      preview.appendChild(emptyNode(t));
      list.appendChild(emptyNode(t));
      return;
    }
    msgs.slice(-3).forEach(function (m) { preview.appendChild(messageNode(m, true)); });
    var shownMsgs = msgs.filter(function (m) { return room === 'all' || m.room === room; });
    if (!shownMsgs.length) list.appendChild(emptyNode(T.chatEmpty));
    shownMsgs.forEach(function (m) { list.appendChild(messageNode(m, false)); });
    if (stick) scrollChatDown();
  }
  function loadChat() {
    if (doc.hidden) return;
    fetch('/api/v1/site/chat?after=' + lastId, { cache: 'no-store' }).then(function (r) {
      if (!r.ok) throw new Error(String(r.status));
      return r.json();
    }).then(function (d) {
      var added = (d.messages || []).filter(function (m) { return m && m.id > lastId; });
      var gone = {};
      (d.deleted || []).forEach(function (id) { gone[id] = true; });
      var before = msgs.length;
      freshIds = {};
      if (lastId) added.forEach(function (m) { freshIds[m.id] = true; });
      msgs = msgs.concat(added).filter(function (m) { return !gone[m.id]; }).slice(-200);
      added.forEach(function (m) { if (m.id > lastId) lastId = m.id; });
      var changed = added.length || msgs.length !== before + added.length || chatState !== 'ready';
      chatState = 'ready';
      if (changed) renderChat(true);
    }).catch(function () {
      if (chatState !== 'ready') { chatState = 'error'; renderChat(true); }
    });
  }

  /* ---------- news ---------- */
  var news = null;
  function renderNews() {
    var box2 = $('newsList');
    if (!news) return;
    box2.textContent = '';
    if (!news.length) { $('news').hidden = true; return; }
    news.forEach(function (n) {
      var item = doc.createElement('div');
      var d = doc.createElement('div');
      d.className = 'd';
      var date = new Date((n.ts || 0) * 1000);
      d.textContent = T.version + ' ' + n.version + (n.ts ? ' · ' + date.toLocaleDateString(lang === 'ru' ? 'ru-RU' : 'en-GB', { day: 'numeric', month: 'long' }) : '');
      var t = doc.createElement('div');
      t.className = 'n';
      t.textContent = n.notes;
      item.appendChild(d);
      item.appendChild(t);
      box2.appendChild(item);
    });
  }
  function loadNews() {
    fetch('/api/v1/site/news').then(function (r) { return r.ok ? r.json() : null; }).then(function (d) {
      if (!d || !Array.isArray(d.news)) return;
      news = d.news;
      renderNews();
    }).catch(function () { /* the section keeps its heading only */ });
  }

  /* ---------- start ---------- */
  applyLang();
  loadStats();
  loadChat();
  loadNews();
  setInterval(loadStats, 30000);
  setInterval(loadChat, 5000);
  doc.addEventListener('visibilitychange', function () {
    if (!doc.hidden) { loadStats(); loadChat(); startEmbers(); }
  });
})();
