/* counter-zombie.ru: language, parallax, gameplay carousel, feature imagery, live stats and chat. */
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
      downloadCta: 'Принять участие в бета-тесте', statsLabel: 'Статистика', online: 'в игре', offline: 'не в сети', downloads: 'скачиваний', mb: 'МБ',
      launchStatus: 'Бета-тест уже идёт', launchFinished: '14-дневный этап завершён',
      launchTitle: 'На пути к', launchAccent: 'глобальному релизу',
      launchLead: 'Присоединяйся к бета-тесту и помоги сделать игру лучше перед большим запуском.',
      countdownLabel: 'До завершения 14-дневного этапа', countdownFinished: 'Готовимся к следующему этапу',
      clockDays: 'дней', clockHours: 'часов', clockMinutes: 'минут', clockSeconds: 'секунд',
      launchNote: 'Ориентир завершения:', launchEndedNote: 'Этап завершился:',
      launchReview: 'После теста — заявка на глобальный релиз и проверка Google Play.', launchJoin: 'Участвовать в бете',
      overviewTitle: 'Видеообзор игры', overviewPlay: 'Смотреть видеообзор игры',
      overviewNote: 'Живой геймплей Counter Zombie Mobile: зомби, командная игра и управление на телефоне.',
      overviewError: 'Не удалось загрузить видео. Попробуй запустить его ещё раз.', overviewFallback: 'Браузер не поддерживает видео.',
      shotsTitle: 'Кадры', gallery: ['Игровая сцена: бой', 'Игровая сцена: начало раунда', 'Зомби-режим: локация', 'Зомби-режим: сражение'],
      featTitle: 'Возможности', featLead: 'Загляни в игру. Выбирай раздел и знакомься с интерфейсом.',
      featBadge: '10 экранов игры', featHint: 'Настоящие скриншоты игры · Нажми на экран, чтобы рассмотреть детали',
      featZoom: 'На весь экран', featOpen: 'Открыть экран: ', featPrev: 'Предыдущий раздел', featNext: 'Следующий раздел',
      feats: [
        ['Главное меню', 'Всё для старта на одном экране: быстрая игра, любимые серверы, чат и друзья. Уведомления помогут не пропустить новости и обновления.'],
        ['Серверы', 'Найди свой сервер: поиск по названию, карте или IP, фильтры и сортировка. Смотри пинг, свободные места и игроков, сохраняй любимые серверы.'],
        ['Общий чат', 'Общайся с игроками до начала матча. Переключайся между Global, RU и EN, выбирай аватар и оставайся на связи с сообществом.'],
        ['Управление', 'Три схемы кнопок, редактор управления и HUD, обмен раскладками. Настрой чувствительность камеры, прицеливания и гироскоп под себя.'],
        ['Графика', 'Выбери подходящий режим отрисовки, яркость и лимит FPS. Настрой размер текста и HUD, количество эффектов и отображение пинга.'],
        ['Звук', 'Отрегулируй игру, музыку и голосовой чат отдельно. Выбери трек меню, настрой громкость голосов и проверь микрофон перед матчем.'],
        ['Игра', 'Свой прицел: размер, цвет, прозрачность и динамика. Выбирай руку с оружием, вид магазина и другие игровые параметры.'],
        ['HUD', 'Три вида радара и варианты оформления чата. Подбери удобный вид интерфейса, а положение и размер элементов измени в редакторе управления.'],
        ['Профиль', 'Твой ник, аватар или своё фото и спрей в игре. Привяжи почту к игровому аккаунту и сохраняй настройки в облаке.'],
        ['Друзья', 'Находи игроков по ID, добавляй друзей и общайся в личных сообщениях. Управляй подписками, подписчиками и списком блокировок.']
      ],
      chatTitle: 'Чат игры', chatShort: 'Чат', chatOpen: 'Открыть чат', chatLock: 'Писать можно только в игре',
      roomsLabel: 'Комнаты чата', chatEmpty: 'В этой комнате пока тихо', chatLoading: 'Загружаем чат…',
      chatError: 'Чат сейчас не отвечает, попробуем ещё раз через несколько секунд', all: 'Все',
      newsTitle: 'Что нового', version: 'Версия', mail: 'Почта', privacy: 'Конфиденциальность',
      betaTitle: 'Бета-тест в Google Play', betaShort: 'Бета-тест',
      betaCount: 'подтвердили участие в Google Play', betaCountNote: 'По данным Google Play Console, обновляется вручную',
      betaUseful: 'Полезно знать', betaAccounts: 'В группе Google, на странице участия в бета-тесте и в Play Маркете должен быть выбран один и тот же Google-аккаунт.', betaVpn: 'Если страницы Google не открываются, может потребоваться VPN. Доступ к тесту иногда появляется с задержкой.', betaSave: 'Перед удалением старой игры сохраните аккаунт и настройки. В версии Google Play войдите в тот же игровой аккаунт.',
      betaVideo: 'Видео инструкция', betaProgress: 'Подтверждённые тестировщики', betaPending: 'Google Play проверяет игру. Пока можно вступить в группу; шаги 2 и 3 откроются после одобрения.',
      betaReady: 'Закрытая бета в Google Play доступна! Вступи в группу, подтверди участие и установи игру.',
      betaLead: 'Цель — 50 тестировщиков с запасом! Для допуска к рабочей версии Google требует минимум 12 участников на 14 дней.',
      beta1: 'Вступи в группу тестировщиков', beta1Note: 'Нужен аккаунт Google — тот же, что в Google Play на телефоне.', beta1Btn: 'Вступить',
      beta2: 'Прими приглашение', beta2Note: 'Откроется Google Play. Если приглашения нет, проверь шаг 1.', beta2Btn: 'Стать тестером',
      beta3: 'Установи и играй', beta3Note: 'Заходи в игру хотя бы пару раз в неделю: Google проверяет, что тест живой.', beta3Btn: 'Открыть в Google Play'
    },
    en: {
      title: 'Counter Zombie Mobile — a zombie shooter for Android',
      description: 'A mobile zombie shooter: zombie hordes, servers for up to 32 players, your own buttons, friends and a live chat. Free for Android.',
      langLabel: 'Language', themeLabel: 'Day or night', share: 'Share', copied: 'Link copied', close: 'Close', prev: 'Previous', next: 'Next',
      tagline: 'A mobile zombie shooter: zombie hordes, servers for up to 32 players, your own buttons, friends and a live chat.',
      downloadCta: 'Join the beta test', statsLabel: 'Statistics', online: 'playing', offline: 'offline', downloads: 'downloads', mb: 'MB',
      launchStatus: 'The beta is live', launchFinished: 'The 14-day stage has ended',
      launchTitle: 'On the road to', launchAccent: 'global release',
      launchLead: 'Join the beta and help us make the game better before the big launch.',
      countdownLabel: 'Until the end of the 14-day stage', countdownFinished: 'Getting ready for the next stage',
      clockDays: 'days', clockHours: 'hours', clockMinutes: 'minutes', clockSeconds: 'seconds',
      launchNote: 'Target completion:', launchEndedNote: 'Stage ended:',
      launchReview: 'After testing: an application for global release and a Google Play review.', launchJoin: 'Join the beta',
      overviewTitle: 'Game video overview', overviewPlay: 'Play the game overview',
      overviewNote: 'Real Counter Zombie Mobile gameplay: zombies, teamwork and touch controls.',
      overviewError: 'The video could not load. Please try playing it again.', overviewFallback: 'Your browser does not support video.',
      shotsTitle: 'Screenshots', gallery: ['Gameplay: battle', 'Gameplay: round start', 'Zombie mode: location', 'Zombie mode: combat'],
      featTitle: 'Features', featLead: 'Take a look inside. Choose a section and explore the game interface.',
      featBadge: '10 game screens', featHint: 'Real game screenshots · Tap a screen to take a closer look',
      featZoom: 'Full screen', featOpen: 'Open screen: ', featPrev: 'Previous section', featNext: 'Next section',
      feats: [
        ['Main menu', 'Everything you need to get started: quick play, favourite servers, chat and friends. Notifications keep you up to date with game news and updates.'],
        ['Servers', 'Find a server by name, map or IP, with filters and sorting. Check ping, available slots and players, and save your favourites.'],
        ['Global chat', 'Meet the community before a match. Switch between Global, RU and EN, choose an avatar and stay in touch with other players.'],
        ['Controls', 'Three button layouts, a controls and HUD editor, and layout sharing. Adjust camera, aiming and gyroscope sensitivity to suit you.'],
        ['Graphics', 'Choose a rendering mode, brightness and FPS limit. Adjust text and HUD size, effects and the on-screen ping display.'],
        ['Audio', 'Adjust game audio, music and voice chat separately. Choose a menu track, set voice volume and check your microphone before a match.'],
        ['Game', 'Make the crosshair yours: size, colour, transparency and movement. Choose your weapon hand, shop style and other game options.'],
        ['HUD', 'Three radar styles and different chat designs. Choose the look you like, then use the controls editor to change element positions and sizes.'],
        ['Profile', 'Your nickname, avatar or personal photo, and in-game spray. Link an email to your game account and save your settings in the cloud.'],
        ['Friends', 'Find players by ID, add friends and chat in private messages. Manage your follows, followers and blocked players.']
      ],
      chatTitle: 'Game chat', chatShort: 'Chat', chatOpen: 'Open chat', chatLock: 'You can only write in the game',
      roomsLabel: 'Chat rooms', chatEmpty: 'Quiet in this room so far', chatLoading: 'Loading the chat…',
      chatError: 'The chat is not answering, trying again in a few seconds', all: 'All',
      newsTitle: 'What’s new', version: 'Version', mail: 'Email', privacy: 'Privacy',
      betaTitle: 'Google Play beta test', betaShort: 'Beta test',
      betaCount: 'confirmed Google Play testers', betaCountNote: 'From Google Play Console, manually updated',
      betaUseful: 'Useful information', betaAccounts: 'Use the same Google account in the Google group, on the beta opt-in page and in the Play Store.', betaVpn: 'If Google pages do not open, a VPN may be needed. Access to the test can take some time to appear.', betaSave: 'Save your account and settings before removing the old game. Sign in to the same game account in the Google Play version.',
      betaVideo: 'Video instructions', betaProgress: 'Confirmed testers', betaPending: 'Google Play is reviewing the game. You can join the group now; steps 2 and 3 will unlock after approval.',
      betaReady: 'The Google Play closed beta is available! Join the group, opt in and install the game.',
      betaLead: 'Our goal is 50 testers as a safety margin! Google requires at least 12 opted-in testers for 14 days.',
      beta1: 'Join the testers group', beta1Note: 'You need a Google account, the same one as in Google Play on your phone.', beta1Btn: 'Join',
      beta2: 'Accept the invitation', beta2Note: 'Google Play opens. If there is no invitation, check step 1.', beta2Btn: 'Become a tester',
      beta3: 'Install and play', beta3Note: 'Play at least a couple of times a week: Google checks that the test is alive.', beta3Btn: 'Open in Google Play'
    }
  };
  var FEAT_SHOTS = ['menu', 'servers', 'chat', 'controls', 'graphics', 'audio', 'game', 'hud', 'profile', 'friends'];
  var FEAT_ICONS = [
    '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
    '<rect x="3" y="3" width="18" height="7" rx="2"/><rect x="3" y="14" width="18" height="7" rx="2"/><path d="M7 6.5h.01M7 17.5h.01M11 6.5h6M11 17.5h6"/>',
    '<path d="M21 11.5a8.4 8.4 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7a8.4 8.4 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.4 8.4 0 0 1 3.8-.9h.5a8.5 8.5 0 0 1 8 8v.5Z"/>',
    '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="9" r="4"/><path d="M12 13v8"/>',
    '<rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8M12 17v4"/>',
    '<path d="m11 5-6 4H2v6h3l6 4V5ZM15.5 8.5a5 5 0 0 1 0 7M19 5a10 10 0 0 1 0 14"/>',
    '<circle cx="12" cy="12" r="7"/><circle cx="12" cy="12" r="2"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3"/>',
    '<path d="M8 3H3v5M16 3h5v5M8 21H3v-5M16 21h5v-5"/><circle cx="12" cy="12" r="3"/>',
    '<circle cx="12" cy="7" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/>',
    '<circle cx="9" cy="8" r="3"/><path d="M2 21v-2a7 7 0 0 1 14 0v2M16 4a4 4 0 0 1 0 8M19 15a6 6 0 0 1 3 5v1"/>'
  ];
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
    if (boxAt >= 0) showBox();
    paintCountdown();
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

  /* Feature screenshots remain available through the tabbed Features section. */
  var V = root.getAttribute('data-v') || '';
  function shotSrc(i) { return '/assets/feature-' + FEAT_SHOTS[i] + '.webp' + (V ? '?v=' + V : ''); }

  /* ---------- gameplay screenshot carousel and lightbox ---------- */
  var strip = $('strip'), box = $('box'), boxImg = $('boxImg'), boxCap = $('boxCap');
  var galleryIndex = 0, pausedUntil = 0, boxAt = -1, boxKind = 'gallery', boxScroll = '';
  var stripVisible = true, lastFocus = null;
  function gallerySrc(i) { return '/assets/gameplay-' + (i + 1) + '.webp' + (V ? '?v=' + V : ''); }
  function buildStrip() {
    strip.textContent = '';
    T.gallery.forEach(function (name, i) {
      var b = doc.createElement('button');
      b.type = 'button';
      b.setAttribute('aria-label', name);
      var img = doc.createElement('img');
      img.src = gallerySrc(i);
      img.alt = name;
      img.width = 772;
      img.height = 360;
      img.decoding = 'async';
      if (i > 0) img.loading = 'lazy';
      b.appendChild(img);
      b.addEventListener('click', function () { openBox(i); });
      strip.appendChild(b);
    });
  }
  var pauseStrip = function () { pausedUntil = Date.now() + 9000; };
  ['pointerdown','wheel','touchstart','focusin'].forEach(function (ev) { strip.addEventListener(ev, pauseStrip, { passive:true }); });
  if ('IntersectionObserver' in window) {
    new IntersectionObserver(function (entries) { stripVisible = entries[0].isIntersecting; }).observe(strip);
  }
  if (!reduce) {
    setInterval(function () {
      if (Date.now() < pausedUntil || boxAt >= 0 || doc.hidden || !stripVisible) return;
      var items = strip.children;
      if (!items.length) return;
      galleryIndex = (galleryIndex + 1) % items.length;
      if (strip.scrollLeft + strip.clientWidth >= strip.scrollWidth - 4) galleryIndex = 0;
      strip.scrollTo({ left: galleryIndex === 0 ? 0 : items[galleryIndex].offsetLeft - 16, behavior:'smooth' });
    }, 3500);
  }
  function showBox() {
    var features = boxKind === 'features';
    var title = features ? T.feats[boxAt][0] : T.gallery[boxAt];
    var count = features ? T.feats.length : T.gallery.length;
    boxImg.src = features ? shotSrc(boxAt) : gallerySrc(boxAt);
    boxImg.alt = title;
    boxCap.textContent = title + ' · ' + (boxAt + 1) + '/' + count;
    box.setAttribute('aria-label', features ? T.featTitle : T.shotsTitle);
  }
  function openBox(i, kind) {
    pauseStrip();
    lastFocus = doc.activeElement;
    boxScroll = root.style.overflow;
    root.style.overflow = 'hidden';
    boxKind = kind || 'gallery';
    boxAt = i;
    showBox();
    box.classList.add('on');
    box.setAttribute('aria-hidden','false');
    box.querySelector('.x').focus();
  }
  function closeBox() {
    if (boxAt < 0) return;
    boxAt = -1;
    box.classList.remove('on');
    box.setAttribute('aria-hidden','true');
    root.style.overflow = boxScroll;
    if (boxKind === 'features') {
      var screen = $('panel-' + feat).querySelector('.feature-screen');
      screen.focus({ preventScroll:true });
    } else if (lastFocus && lastFocus.focus) lastFocus.focus({ preventScroll:true });
  }
  function stepBox(delta) {
    if (boxAt < 0) return;
    var count = boxKind === 'features' ? T.feats.length : T.gallery.length;
    boxAt = (boxAt + delta + count) % count;
    if (boxKind === 'features') pickFeature(boxAt, false);
    showBox();
  }
  $('boxPrev').addEventListener('click', function () { stepBox(-1); });
  $('boxNext').addEventListener('click', function () { stepBox(1); });
  box.addEventListener('click', function (e) { if (e.target === box) closeBox(); });
  var touchX = null;
  box.addEventListener('touchstart', function (e) { touchX = e.touches[0].clientX; }, { passive:true });
  box.addEventListener('touchend', function (e) {
    if (touchX == null) return;
    var dx = e.changedTouches[0].clientX - touchX;
    touchX = null;
    if (Math.abs(dx) > 50) stepBox(dx < 0 ? 1 : -1);
  });

  /* ---------- feature tabs ---------- */
  var tabs = $('tabs'), panels = $('panels'), feat = 0;
  function featureIcon(paths) {
    var svg = doc.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('fill', 'none');
    svg.setAttribute('stroke', 'currentColor');
    svg.setAttribute('stroke-width', '1.8');
    svg.setAttribute('stroke-linecap', 'round');
    svg.setAttribute('stroke-linejoin', 'round');
    svg.setAttribute('aria-hidden', 'true');
    svg.innerHTML = paths; // Only the static, local icon paths above are used here.
    return svg;
  }
  function featureNav(delta) {
    var b = doc.createElement('button');
    b.type = 'button';
    b.className = 'icon-btn';
    b.setAttribute('aria-label', delta < 0 ? T.featPrev : T.featNext);
    b.appendChild(featureIcon(delta < 0 ? '<path d="m15 5-7 7 7 7"/>' : '<path d="m9 5 7 7-7 7"/>'));
    b.addEventListener('click', function () {
      pickFeature((feat + delta + T.feats.length) % T.feats.length, false);
      // The old panel becomes hidden; retain focus on the matching visible control.
      $('panel-' + feat).querySelectorAll('.feature-nav button')[delta < 0 ? 0 : 1].focus({ preventScroll:true });
    });
    return b;
  }
  function loadFeature(i) {
    var img = $('panel-' + i).querySelector('img');
    if (!img.hasAttribute('src')) img.src = shotSrc(i);
  }
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
      tab.appendChild(featureIcon(FEAT_ICONS[i]));
      tab.appendChild(doc.createTextNode(f[0]));
      tab.addEventListener('click', function () { pickFeature(i, false); });
      tabs.appendChild(tab);

      var panel = doc.createElement('div');
      panel.className = 'panel' + (on ? ' on' : '');
      panel.id = 'panel-' + i;
      panel.setAttribute('role', 'tabpanel');
      panel.setAttribute('aria-labelledby', 'tab-' + i);
      panel.hidden = !on;
      var pic = doc.createElement('button');
      pic.type = 'button';
      pic.className = 'feature-screen';
      pic.setAttribute('aria-label', T.featOpen + f[0]);
      pic.setAttribute('aria-haspopup', 'dialog');
      var img = doc.createElement('img');
      img.alt = f[0];
      img.width = 1536;
      img.height = 716;
      img.decoding = 'async';
      img.loading = 'lazy';
      pic.appendChild(img);
      var zoom = doc.createElement('span');
      zoom.className = 'feature-zoom';
      zoom.setAttribute('aria-hidden', 'true');
      zoom.appendChild(featureIcon('<path d="M8 3H3v5M16 3h5v5M8 21H3v-5M16 21h5v-5"/>'));
      var zoomText = doc.createElement('span');
      zoomText.textContent = T.featZoom;
      zoom.appendChild(zoomText);
      pic.appendChild(zoom);
      pic.addEventListener('click', function () { openBox(i, 'features'); });
      var txt = doc.createElement('div');
      txt.className = 'txt';
      var number = doc.createElement('span');
      number.className = 'feature-number';
      number.setAttribute('aria-hidden', 'true');
      number.textContent = String(i + 1).padStart(2, '0');
      var copy = doc.createElement('div');
      copy.className = 'feature-copy';
      var h = doc.createElement('h3');
      h.className = 'h-game';
      h.textContent = f[0];
      var p = doc.createElement('p');
      p.textContent = f[1];
      copy.appendChild(h);
      copy.appendChild(p);
      var nav = doc.createElement('div');
      nav.className = 'feature-nav';
      nav.appendChild(featureNav(-1));
      nav.appendChild(featureNav(1));
      txt.appendChild(number);
      txt.appendChild(copy);
      txt.appendChild(nav);
      panel.appendChild(pic);
      panel.appendChild(txt);
      panels.appendChild(panel);
    });
    loadFeature(feat);
  }
  function pickFeature(i, focus) {
    feat = i;
    all('#tabs .tab').forEach(function (t, n) {
      t.setAttribute('aria-selected', String(n === i));
      t.tabIndex = n === i ? 0 : -1;
      if (n === i) {
        if (focus) t.focus({ preventScroll:true });
        if (tabs.scrollWidth > tabs.clientWidth) tabs.scrollTo({ left:t.offsetLeft - tabs.offsetLeft - (tabs.clientWidth - t.offsetWidth) / 2, behavior:reduce ? 'auto' : 'smooth' });
      }
    });
    all('#panels .panel').forEach(function (p, n) {
      p.classList.toggle('on', n === i);
      p.hidden = n !== i;
    });
    loadFeature(i);
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
    else if (boxAt >= 0 && e.key === 'Tab') {
      var buttons = Array.prototype.slice.call(box.querySelectorAll('button'));
      var first = buttons[0], last = buttons[buttons.length - 1];
      if (e.shiftKey && doc.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && doc.activeElement === last) { e.preventDefault(); first.focus(); }
    }
  });

  /* ---------- Google Play: store buttons and the beta test ---------- */
var beta = $('beta');
  var betaLinks = beta ? { group: beta.getAttribute('data-group') || '', optin: beta.getAttribute('data-optin') || '',
    store: beta.getAttribute('data-store') || '' } : {};
  function paintBeta() {
    if (!beta || beta.hidden) return;
    var open = Boolean(stats && stats.play_beta_open === true);
    $('betaStatus').textContent = open ? T.betaReady : T.betaPending;
    all('#beta .step').forEach(function (li) {
      var n = parseInt(li.getAttribute('data-step'), 10);
      var link = li.querySelector('[data-beta]');
      var kind = link.getAttribute('data-beta');
      var allowed = kind === 'group' || open;
      li.classList.toggle('locked', !allowed);
      li.classList.remove('done'); // clicks cannot verify Google Group membership or opt-in
      if (allowed) {
        link.href = betaLinks[kind];
        link.removeAttribute('aria-disabled');
        link.removeAttribute('tabindex');
      } else {
        link.removeAttribute('href');
        link.setAttribute('aria-disabled', 'true');
        link.setAttribute('tabindex', '-1');
      }
    });
  }
  if (beta && /^https:\/\/groups\.google\.com\//.test(betaLinks.group)) {
    beta.hidden = false;
    all('[data-beta-link]').forEach(function (el) { el.hidden = false; });
    paintBeta();
  }

  /* ---------- one shared beta milestone, independent of visits and time zones ---------- */
  var countdown = $('beta-countdown'), serverOffset = 0;
  var betaStart = countdown ? Date.parse(countdown.getAttribute('data-start')) : NaN;
  var betaEnd = countdown ? Date.parse(countdown.getAttribute('data-end')) : NaN;
  function countdownParts(now, start, end) {
    var seconds = Math.ceil(Math.max(0, end - Math.max(start, now)) / 1000);
    return {
      days: Math.floor(seconds / 86400), hours: Math.floor(seconds / 3600) % 24,
      minutes: Math.floor(seconds / 60) % 60, seconds: seconds % 60,
      progress: Math.max(0, Math.min(1, (now - start) / (end - start))), finished: now >= end
    };
  }
  function paintCountdown() {
    if (!countdown) return;
    if (!isFinite(betaStart) || !isFinite(betaEnd) || betaEnd <= betaStart) { countdown.hidden = true; return; }
    var p = countdownParts(Date.now() + serverOffset, betaStart, betaEnd);
    [['betaDays',p.days],['betaHours',p.hours],['betaMinutes',p.minutes],['betaSeconds',p.seconds]].forEach(function (unit) {
      var value = String(unit[1]).padStart(2, '0');
      if ($(unit[0]).textContent !== value) $(unit[0]).textContent = value;
    });
    $('betaTimeBar').style.width = (p.progress * 100).toFixed(3) + '%';
    $('launchCard').classList.toggle('finished', p.finished);
    $('launchStatus').textContent = p.finished ? T.launchFinished : T.launchStatus;
    $('countdownLabel').textContent = p.finished ? T.countdownFinished : T.countdownLabel;
    $('launchNote').textContent = p.finished ? T.launchEndedNote : T.launchNote;
    $('betaEndDate').textContent = new Intl.DateTimeFormat(lang === 'ru' ? 'ru-RU' : 'en-GB', {
      timeZone:'Europe/Moscow', day:'numeric', month:'long', hour:'2-digit', minute:'2-digit'
    }).format(new Date(betaEnd)) + (lang === 'ru' ? ' МСК' : ' MSK');
  }
  setInterval(function () { if (!doc.hidden) paintCountdown(); }, 1000);

  /* ---------- gameplay overview: no autoplay or video preload ---------- */
  var overview = $('gameOverview'), overviewPlay = $('overviewPlay'), overviewStatus = $('overviewStatus');
  if (overview && overviewPlay) {
    overviewPlay.addEventListener('click', function () {
      overviewStatus.hidden = true;
      if (overview.error) overview.load();
      var play = overview.play();
      if (play && play.catch) play.catch(function () {
        overviewStatus.hidden = false;
        overviewPlay.hidden = false;
      });
    });
    overview.addEventListener('play', function () { overviewPlay.hidden = true; overviewStatus.hidden = true; });
    overview.addEventListener('error', function () { overviewStatus.hidden = false; overviewPlay.hidden = false; });
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
  var stats = null, shown = { online: null, offline: null };
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
    if ($('sBetaTesters')) {
      var testers = stats.play_beta_testers;
      $('sBetaTesters').textContent = typeof testers === 'number' ? fmt(testers) : '—';
      $('sBetaBar').style.width = typeof testers === 'number' ? Math.min(100, testers / 50 * 100) + '%' : '0%';
      $('sBetaTrack').setAttribute('aria-valuenow', String(typeof testers === 'number' ? Math.min(50, testers) : 0));
      var checked = stats.play_beta_checked_at;
      $('betaCountUpdated').textContent = T.betaCountNote + (checked ? ' · ' + new Date(checked * 1000).toLocaleString(lang === 'ru' ? 'ru-RU' : 'en-GB') : '');
    }
    paintBeta();
  }
  function loadStats() {
    if (doc.hidden) return;
    var requestedAt = Date.now();
    fetch('/api/v1/site/stats', { cache: 'no-store' }).then(function (r) {
      var serverDate = Date.parse(r.headers.get('Date'));
      if (r.ok && isFinite(serverDate)) {
        serverOffset = serverDate + (Date.now() - requestedAt) / 2 - Date.now();
        paintCountdown();
      }
      return r.ok ? r.json() : null;
    }).then(function (d) {
      if (!d || typeof d.online !== 'number') return;
      var first = !stats;
      stats = d;
      if (first) { shown.online = 0; shown.offline = 0; }
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
    if (!doc.hidden) { paintCountdown(); loadStats(); loadChat(); startEmbers(); }
  });
})();
