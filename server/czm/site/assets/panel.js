/* Player panel of the Survival server (/panel): CZM account sign-in, then the LVL MOD of the player.
   Every number comes from the API (/api/v1/survival/*); the page only shows it and sends choices. */
(function () {
  'use strict';
  var $ = function (id) { return document.getElementById(id); };
  var store = {
    get: function (k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set: function (k, v) { try { if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch (e) { /* private mode */ } }
  };
  var root = document.documentElement;
  var lang = store.get('czm-lang') === 'en' ? 'en' : 'ru';
  var token = store.get('czm-session') || '';
  var catalog = null, me = null, myProfile = null, liveTimer = 0, topKind = 'lvl';

  var S = {
    ru: {
      theme: 'День или ночь', logout: 'Выйти', loginTitle: 'Панель игрока',
      loginLead: 'Войди в аккаунт CZM — уровень, токены, магазин и пропуск сервера Survival откроются сразу.',
      byEmail: 'По почте', byNick: 'Ник и пароль', email: 'Почта', code: 'Код из письма', sendCode: 'Получить код',
      confirm: 'Войти', nick: 'Ник аккаунта', password: 'Пароль', signIn: 'Войти',
      loginHint: 'Аккаунта ещё нет? Создай его в игре: Профиль → Аккаунт. Почту привяжи там же — по ней приходит код входа.',
      codeSent: 'Если почта привязана к аккаунту, код уже в письме.', profileId: 'Профиль CZM', tokens: 'Токены',
      tOverview: 'Обзор', tSkins: 'Скины', tKnives: 'Ножи', tShop: 'Магазин', tPass: 'Боевой пропуск', tMarket: 'Лавка',
      tPay: 'Перевод', tTop: 'Топ', tLive: 'Сервер', history: 'Последние события', upgrades: 'Прокачка',
      skinsLead: 'Скин надевается на твоего человека в начале каждого раунда. Купленный скин можно сменить в любой момент — здесь или в игре (lvl → Магазин).',
      knivesLead: 'Нож в руках твоего человека. Купленный нож меняется в любой момент — здесь или в игре (lvl → Магазин).',
      sellTitle: 'Выставить на продажу', price: 'Цена', sell: 'Выставить', payTitle: 'Перевод токенов',
      payTarget: 'ID профиля получателя', payAmount: 'Сколько', send: 'Перевести', kills: 'Убийства', time: 'Время',
      deaths: 'Смерти', kd: 'K/D', played: 'В игре', rounds: 'Раунды', wins: 'Победы', wr: 'Побед', since: 'С нами с',
      nextLvl: 'До LVL {n}: {k} убийств или {m} мин', buy: 'Купить', wear: 'Надеть', takeOff: 'Снять', worn: 'Надето',
      owned: 'Есть', adminOnly: 'Только администраторам', boostLvl: 'LVL ×2 ещё {t}', boostTok: 'Токены ×2 ещё {t}',
      passOn: 'Пропуск: {d} дн.', passBuyTitle: 'Боевой пропуск', passBuyLead: '{d} дней: каждый день +{daily} токенов за вход и 24 задания с наградами. В финале: +200 LVL, +50 000 токенов и префикс BATTLE PASS.',
      passBuy: 'Купить за {p}', passLeft: 'Осталось {d} дн. · выполнено {c} из {all}', daily: 'Награда за вход +{n}',
      dailyTaken: 'Награда за сегодня получена', finalTitle: 'Финальные награды', finalLvl: '+200 LVL', finalTok: '+50 000 токенов',
      finalPrefix: 'Префикс BATTLE PASS', take: 'Забрать', taken: 'Получено',
      marketLead: 'Лавка игроков: вещь ждёт покупателя {d} дней, потом возвращается. До {max} предложений, продавец платит {tax}%.',
      nothingToSell: 'Нечего выставить: в лавку идут купленные вещи.', seller: 'Продавец', daysLeft: '{d} дн.',
      withdraw: 'Снять', mine: 'Твоё', marketEmpty: 'В лавке пока пусто.', payLead: 'С {lvl} LVL, до {limit} токенов в день. Сегодня отправлено: {today}.',
      topEmpty: 'Пока никого.', liveEmpty: 'Сервер сейчас не в сети или на нём никого нет.', liveNow: '{n} из {max}', leftMin: '{m} мин до смены карты',
      newsTitle: 'Новости сервера', newsEmpty: 'Новостей пока нет.', boardTitle: 'Доска нарушителей', boardEmpty: 'Нарушителей нет — играем честно.',
      ban: 'бан', mute: 'мут', forever: 'навсегда', byVote: 'голосование игроков', leftShort: 'ещё {t}',
      zombie: 'Зомби', human: 'Человек', frags: 'Фраги', lvl: 'LVL', player: 'Игрок', place: '{n} место', promoTitle: 'Промокод', promoPh: 'Например, free20lvl', promoUse: 'Активировать', promoDone: 'Промокод: +{n} {what}', tokensWord: 'токенов', crate: 'Ящик с оружием', crateLead: 'на 30 минут, выдаётся при каждом спавне человеком', charges: 'зарядов: {n}', minLeft: 'ещё {m} мин', extend: 'Продлить', hCrate: 'Ящик с оружием', hAirdrop: 'Аирдроп', done: 'Готово', bought: 'Куплено и надето', on: 'Надето', off: 'Снято',
      paid: 'Передано {n} токенов', listed: 'Выставлено в лавку', boughtMarket: 'Куплено в лавке', withdrawn: 'Вещь вернулась к тебе',
      hBuy: 'Покупка', hUpgrade: 'Прокачка', hPay: 'Перевод', hPromo: 'Промокод', hPass: 'Боевой пропуск', hMarketBuy: 'Покупка в лавке',
      hMarketSell: 'Продажа в лавке', hMapTop: 'Топ карты', noHistory: 'Событий пока нет: зайди на сервер Survival.',
      e: { tokens: 'Не хватает токенов.', not_owned: 'Этого у тебя нет.', admin_only: 'Только для администраторов.', not_for_sale: 'Это не продаётся.',
        pay_lvl: 'Перевод доступен с 10 LVL.', pay_limit: 'Дневной лимит переводов исчерпан.', bp_active: 'Пропуск уже активен.',
        bp_inactive: 'Сначала купи боевой пропуск.', bp_daily_done: 'Сегодня награда уже получена.', bp_tasks: 'Сначала выполни все задания.',
        bp_final_done: 'Эта награда уже получена.', promo: 'Нет такого промокода.', promo_used: 'Этот промокод ты уже использовал.', player: 'Игрок с таким ID ещё не играл на Survival.', self: 'Себе нельзя.',
        market_max: 'Не больше 3 предложений сразу.', listing: 'Этого предложения уже нет.', owned: 'Это у тебя уже есть.', price: 'Проверь цену.',
        amount: 'Проверь сумму.', credentials: 'Неверный ник или пароль.', code: 'Неверный код.', email: 'Проверь почту.',
        slow: 'Слишком много попыток, подожди немного.', mail_unavailable: 'Письма сейчас не отправляются, войди по нику.',
        hello: 'Войди заново.', session: 'Войди заново.', generic: 'Не получилось, попробуй ещё раз.' }
    },
    en: {
      theme: 'Day or night', logout: 'Sign out', loginTitle: 'Player panel',
      loginLead: 'Sign in with your CZM account: the level, tokens, shop and pass of the Survival server open right away.',
      byEmail: 'By email', byNick: 'Nick and password', email: 'Email', code: 'Code from the email', sendCode: 'Get a code',
      confirm: 'Sign in', nick: 'Account nick', password: 'Password', signIn: 'Sign in',
      loginHint: 'No account yet? Create it in the game: Profile → Account. Add your email there: the sign-in code comes to it.',
      codeSent: 'If the email belongs to an account, the code is in your inbox.', profileId: 'CZM profile', tokens: 'Tokens',
      tOverview: 'Overview', tSkins: 'Skins', tKnives: 'Knives', tShop: 'Shop', tPass: 'Battle pass', tMarket: 'Market',
      tPay: 'Send', tTop: 'Top', tLive: 'Server', history: 'Recent events', upgrades: 'Upgrades',
      skinsLead: 'The skin goes on your human at the start of every round. Change it any time, here or in the game (lvl → Shop).',
      knivesLead: 'The knife in your human\'s hands. Change a bought knife any time, here or in the game (lvl → Shop).',
      sellTitle: 'Put up for sale', price: 'Price', sell: 'Put up', payTitle: 'Send tokens',
      payTarget: 'Receiver profile ID', payAmount: 'How many', send: 'Send', kills: 'Kills', time: 'Time',
      deaths: 'Deaths', kd: 'K/D', played: 'Played', rounds: 'Rounds', wins: 'Wins', wr: 'Win rate', since: 'With us since',
      nextLvl: 'LVL {n}: {k} kills or {m} min to go', buy: 'Buy', wear: 'Put on', takeOff: 'Take off', worn: 'On',
      owned: 'Owned', adminOnly: 'Administrators only', boostLvl: 'LVL ×2 for {t}', boostTok: 'Tokens ×2 for {t}',
      passOn: 'Pass: {d} d', passBuyTitle: 'Battle pass', passBuyLead: '{d} days: +{daily} tokens every day you come in and 24 tasks with rewards. At the end: +200 LVL, +50,000 tokens and the BATTLE PASS prefix.',
      passBuy: 'Buy for {p}', passLeft: '{d} days left · {c} of {all} done', daily: 'Daily reward +{n}',
      dailyTaken: "Today's reward is taken", finalTitle: 'Final rewards', finalLvl: '+200 LVL', finalTok: '+50,000 tokens',
      finalPrefix: 'BATTLE PASS prefix', take: 'Take', taken: 'Taken',
      marketLead: 'Player market: an item waits for a buyer {d} days, then comes back. Up to {max} offers, the seller pays {tax}%.',
      nothingToSell: 'Nothing to sell: bought items go to the market.', seller: 'Seller', daysLeft: '{d} d',
      withdraw: 'Take back', mine: 'Yours', marketEmpty: 'The market is empty for now.', payLead: 'From LVL {lvl}, up to {limit} tokens a day. Sent today: {today}.',
      topEmpty: 'Nobody yet.', liveEmpty: 'The server is offline or empty right now.', liveNow: '{n} of {max}', leftMin: '{m} min to the next map',
      newsTitle: 'Server news', newsEmpty: 'No news yet.', boardTitle: 'Violators board', boardEmpty: 'Nobody is banned or muted: fair play.',
      ban: 'ban', mute: 'mute', forever: 'forever', byVote: 'players\' vote', leftShort: '{t} left',
      zombie: 'Zombie', human: 'Human', frags: 'Frags', lvl: 'LVL', player: 'Player', place: 'place {n}', promoTitle: 'Promo code', promoPh: 'For example, free20lvl', promoUse: 'Activate', promoDone: 'Promo code: +{n} {what}', tokensWord: 'tokens', crate: 'Weapon crate', crateLead: 'for 30 minutes, given at every spawn as a human', charges: '{n} charges', minLeft: '{m} min left', extend: 'Extend', hCrate: 'Weapon crate', hAirdrop: 'Airdrop', done: 'Done', bought: 'Bought and put on', on: 'Put on', off: 'Taken off',
      paid: '{n} tokens sent', listed: 'Put up for sale', boughtMarket: 'Bought on the market', withdrawn: 'The item is back with you',
      hBuy: 'Purchase', hUpgrade: 'Upgrade', hPay: 'Transfer', hPromo: 'Promo code', hPass: 'Battle pass', hMarketBuy: 'Market purchase',
      hMarketSell: 'Market sale', hMapTop: 'Map top', noHistory: 'Nothing yet: join the Survival server.',
      e: { tokens: 'Not enough tokens.', not_owned: 'You do not own it.', admin_only: 'Administrators only.', not_for_sale: 'Not for sale.',
        pay_lvl: 'Transfers open at LVL 10.', pay_limit: "Today's transfer limit is used up.", bp_active: 'The pass is already active.',
        bp_inactive: 'Buy the battle pass first.', bp_daily_done: "Today's reward is already taken.", bp_tasks: 'Finish every task first.',
        bp_final_done: 'This reward is already taken.', promo: 'No such promo code.', promo_used: 'You have used this promo code.', player: 'Nobody with this ID has played Survival yet.', self: 'Not to yourself.',
        market_max: 'No more than 3 offers at once.', listing: 'This offer is gone.', owned: 'You already own it.', price: 'Check the price.',
        amount: 'Check the amount.', credentials: 'Wrong nick or password.', code: 'Wrong code.', email: 'Check the email.',
        slow: 'Too many tries, wait a little.', mail_unavailable: 'Emails are not sent right now, sign in with your nick.',
        hello: 'Sign in again.', session: 'Sign in again.', generic: 'That did not work, try again.' }
    }
  };
  var t = function (k, vars) {
    var s = S[lang][k] || S.ru[k] || k;
    return vars ? s.replace(/\{(\w+)\}/g, function (_, v) { return vars[v] !== undefined ? vars[v] : ''; }) : s;
  };
  var errorText = function (code) { return S[lang].e[code] || S[lang].e.generic; };
  var fmt = function (n) { return Number(n || 0).toLocaleString(lang === 'en' ? 'en-US' : 'ru-RU'); };
  var name = function (o) { return o ? (lang === 'en' ? o.en : o.ru) : ''; };
  var esc = function (s) { return String(s === undefined || s === null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); };
  var hm = function (sec) { var h = Math.floor(sec / 3600), m = Math.floor(sec / 60) % 60; return lang === 'en' ? h + ' h ' + m + ' min' : h + ' ч ' + m + ' мин'; };
  var op = function () { var a = new Uint8Array(12); (window.crypto || window.msCrypto).getRandomValues(a); return Array.prototype.map.call(a, function (b) { return ('0' + b.toString(16)).slice(-2); }).join(''); };

  function api(path, opts) {
    opts = opts || {};
    var headers = { 'Content-Type': 'application/json' };
    if (token) headers['X-CZM-Key'] = token;
    return fetch('/api/v1' + path, { method: opts.method || 'GET', headers: headers, body: opts.body ? JSON.stringify(opts.body) : undefined, cache: 'no-store' })
      .then(function (r) {
        return r.json().catch(function () { return {}; }).then(function (data) {
          if (!r.ok) { var e = new Error(data.error || 'generic'); e.code = data.error || 'generic'; e.status = r.status; throw e; }
          return data;
        });
      });
  }

  var toastTimer = 0;
  function toast(text, bad) {
    var el = $('toast');
    el.textContent = text; el.className = 'toast' + (bad ? ' bad' : ''); el.hidden = false;
    clearTimeout(toastTimer); toastTimer = setTimeout(function () { el.hidden = true; }, 3200);
  }

  /* ---------- language and theme, shared with the main page ---------- */
  function applyLang() {
    root.lang = lang;
    document.querySelectorAll('[data-i18n]').forEach(function (el) { el.textContent = t(el.getAttribute('data-i18n')); });
    document.querySelectorAll('[data-i18n-aria]').forEach(function (el) { el.setAttribute('aria-label', t(el.getAttribute('data-i18n-aria'))); });
    document.querySelectorAll('[data-i18n-ph]').forEach(function (el) { el.setAttribute('placeholder', t(el.getAttribute('data-i18n-ph'))); });
    document.querySelectorAll('[data-lang]').forEach(function (b) { b.setAttribute('aria-pressed', String(b.getAttribute('data-lang') === lang)); });
    if (me) render();
  }
  document.querySelectorAll('[data-lang]').forEach(function (b) {
    b.addEventListener('click', function () { lang = b.getAttribute('data-lang'); store.set('czm-lang', lang); applyLang(); });
  });
  $('lamp').addEventListener('click', function () {
    var light = !root.classList.contains('light');
    root.classList.toggle('light', light); store.set('czm-theme', light ? 'light' : 'dark');
  });

  /* ---------- sign in ---------- */
  var emailStep = 'ask';
  function showLogin() {
    $('panel').hidden = true; $('logout').hidden = true; $('login').hidden = false;
  }
  document.querySelectorAll('[data-login]').forEach(function (b) {
    b.addEventListener('click', function () {
      document.querySelectorAll('[data-login]').forEach(function (x) { x.setAttribute('aria-selected', String(x === b)); });
      var byEmail = b.getAttribute('data-login') === 'email';
      $('emailForm').hidden = !byEmail; $('nickForm').hidden = byEmail; note('');
    });
  });
  function note(text, kind) { var n = $('loginNote'); n.textContent = text; n.className = 'note' + (kind ? ' ' + kind : ''); }
  function signedIn(result) {
    token = result.token; store.set('czm-session', token);
    note(''); start();
  }
  $('emailForm').addEventListener('submit', function (ev) {
    ev.preventDefault();
    var email = $('email').value.trim();
    var btn = $('emailBtn'); btn.disabled = true;
    var done = function () { btn.disabled = false; };
    if (emailStep === 'ask') {
      api('/auth/email-login', { method: 'POST', body: { email: email } }).then(function () {
        emailStep = 'code'; $('codeRow').hidden = false; btn.textContent = t('confirm'); note(t('codeSent'), 'good'); $('code').focus();
      }).catch(function (e) { note(errorText(e.code), 'bad'); }).then(done);
    } else {
      api('/auth/email-login-confirm', { method: 'POST', body: { email: email, code: $('code').value.trim() } })
        .then(signedIn).catch(function (e) { note(errorText(e.code), 'bad'); }).then(done);
    }
  });
  $('email').addEventListener('input', function () {
    if (emailStep === 'code') { emailStep = 'ask'; $('codeRow').hidden = true; $('emailBtn').textContent = t('sendCode'); }
  });
  $('nickForm').addEventListener('submit', function (ev) {
    ev.preventDefault();
    api('/auth/login', { method: 'POST', body: { nick: $('nick').value.trim(), password: $('password').value } })
      .then(signedIn).catch(function (e) { note(errorText(e.code), 'bad'); });
  });
  $('logout').addEventListener('click', function () {
    api('/auth/logout', { method: 'POST', body: {} }).catch(function () {}).then(function () {
      token = ''; store.set('czm-session', null); me = null; clearInterval(liveTimer); showLogin();
    });
  });

  /* ---------- the panel ---------- */
  function start() {
    if (!token) { showLogin(); return; }
    Promise.all([api('/auth/me', { method: 'POST', body: {} }), api('/survival/catalog'), api('/survival/me')]).then(function (r) {
      myProfile = r[0].profile || r[0]; catalog = r[1]; me = r[2];
      $('login').hidden = true; $('panel').hidden = false; $('logout').hidden = false;
      render(); openTab(store.get('czm-panel-tab') || 'overview');
    }).catch(function (e) {
      if (e.status === 401) { token = ''; store.set('czm-session', null); }
      showLogin(); if (e.status && e.status !== 401) note(errorText(e.code), 'bad');
    });
  }

  function refresh() {
    return api('/survival/me').then(function (r) { me = r; render(); });
  }

  function act(action, args, okText) {
    return api('/survival/action', { method: 'POST', body: { op: op(), action: action, args: args || {} } }).then(function (r) {
      me.state = r.state; render(); toast(okText || t('done'));
      api('/survival/me').then(function (x) { me = x; render(); });
      return r;
    }).catch(function (e) { toast(errorText(e.code), true); throw e; });
  }

  function cat(key) { return (catalog.categories || []).filter(function (c) { return c.key === key; })[0]; }

  function render() {
    var s = me.state;
    $('pNick').textContent = s.nick || (myProfile && myProfile.nick) || '—';
    $('pId').textContent = s.id;
    $('pLvl').textContent = s.lvl;
    $('pTokens').textContent = fmt(s.tokens);
    var av = myProfile && myProfile.avatar ? String(myProfile.avatar) : '1';
    $('avatar').src = av.indexOf('photo:') === 0 ? '/avatars/' + s.id + '.png?v=' + av.slice(6) : '/assets/avatar-' + (parseInt(av, 10) || 1) + '.png';
    var kShare = 1 - s.next_lvl_kills / 10, tShare = 1 - s.next_lvl_time / 600;
    $('pNextBar').style.width = Math.round(Math.max(kShare, tShare) * 100) + '%';
    $('pNext').textContent = t('nextLvl', { n: s.lvl + 1, k: s.next_lvl_kills, m: Math.ceil(s.next_lvl_time / 60) });
    var chips = [];
    if (s.boosts.lvl > 0) chips.push('<span class="chip gold">' + esc(t('boostLvl', { t: hm(s.boosts.lvl) })) + '</span>');
    if (s.boosts.tokens > 0) chips.push('<span class="chip gold">' + esc(t('boostTok', { t: hm(s.boosts.tokens) })) + '</span>');
    if (s.battlepass.active) chips.push('<span class="chip green">' + esc(t('passOn', { d: Math.ceil(s.battlepass.left / 86400) })) + '</span>');
    var prefix = s.equipped.prefix && item('prefix', s.equipped.prefix);
    if (prefix) chips.push('<span class="chip" style="color:' + esc(s.equipped.prefcolor || 'inherit') + '">[' + esc(name(prefix)) + ']</span>');
    $('pChips').innerHTML = chips.join('');
    renderOverview(); renderWear('skin', 'skins', 'skins'); renderWear('knife', 'knives', 'knives'); renderShop(); renderPass(); renderPay();
    if (currentTab === 'market') loadMarket();
  }

  function item(catKey, id) {
    var c = cat(catKey); if (!c) return null;
    return c.items.filter(function (i) { return i.id.toLowerCase() === String(id).toLowerCase(); })[0] || null;
  }

  function renderOverview() {
    var s = me.state;
    var stats = [[t('kills'), fmt(s.kills)], [t('deaths'), fmt(s.deaths)], [t('kd'), s.kd], [t('played'), hm(s.time)],
      [t('rounds'), fmt(s.matches)], [t('wins'), fmt(s.wins)], [t('wr'), s.wr + '%'],
      [t('since'), s.first_seen ? new Date(s.first_seen * 1000).toLocaleDateString(lang === 'en' ? 'en-GB' : 'ru-RU') : '—']];
    $('stats').innerHTML = stats.map(function (x) { return '<div class="stat card"><small>' + esc(x[0]) + '</small><b>' + esc(x[1]) + '</b></div>'; }).join('');
    var kinds = { buy: 'hBuy', upgrade: 'hUpgrade', pay: 'hPay', promo: 'hPromo', battlepass: 'hPass', market_buy: 'hMarketBuy', market_sell: 'hMarketSell', map_top: 'hMapTop', crate: 'hCrate', airdrop: 'hAirdrop' };
    var rows = (me.history || []).map(function (h) {
      var when = new Date(h.time * 1000).toLocaleString(lang === 'en' ? 'en-GB' : 'ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
      var amount = h.amount ? '<span class="amount ' + (h.amount > 0 ? 'plus' : 'minus') + '">' + (h.amount > 0 ? '+' : '') + fmt(h.amount) + '</span>' : '';
      return '<li><div>' + esc(t(kinds[h.kind] || h.kind)) + ' <span class="muted small-text">' + esc(describe(h)) + ' · ' + esc(when) + '</span></div>' + amount + '</li>';
    });
    $('history').innerHTML = rows.join('') || '<li class="empty">' + esc(t('noHistory')) + '</li>';
  }

  function describe(h) {
    var place = /^place (\d+)$/.exec(h.detail || '');
    if (place) return t('place', { n: place[1] });
    var m = /^(\w+):(.+)$/.exec(h.detail || '');
    if (m) { var it = item(m[1], m[2]); if (it) return name(it); }
    var up = (catalog.upgrades || []).concat((catalog.crate || {}).items || []).filter(function (u) { return u.id === h.detail; })[0];
    return up ? name(up) : (h.detail || '');
  }

  function wearButton(catKey, it, owned, on) {
    if (on) return '<button class="btn ghost small" data-act="takeoff" data-cat="' + catKey + '">' + esc(t('takeOff')) + '</button>';
    if (owned) return '<button class="btn small" data-act="wear" data-cat="' + catKey + '" data-item="' + esc(it.id) + '">' + esc(t('wear')) + '</button>';
    if (it.admin) return '<span class="muted small-text">' + esc(t('adminOnly')) + '</span>';
    return '<button class="btn gold small" data-act="buy" data-cat="' + catKey + '" data-item="' + esc(it.id) + '">' + esc(t('buy')) + ' · ' + fmt(it.price) + '</button>';
  }

  function renderWear(catKey, folder, box) {
    var c = cat(catKey); if (!c) return;
    var s = me.state, owned = s.owned[catKey] || [];
    $(box).innerHTML = c.items.filter(function (it) { return it.shop || owned.indexOf(it.id) >= 0 || it.admin; }).map(function (it) {
      var have = owned.indexOf(it.id) >= 0, on = s.equipped[catKey] === it.id;
      return '<article class="item card' + (on ? ' on' : '') + '">' +
        (on ? '<span class="badge on">' + esc(t('worn')) + '</span>' : have ? '<span class="badge">' + esc(t('owned')) + '</span>' : '') +
        '<div class="pic"><img loading="lazy" src="/assets/lvl/' + folder + '/' + esc(it.id) + '.webp" alt=""></div>' +
        '<div class="meta"><div class="name">' + esc(name(it)) + '</div>' + wearButton(catKey, it, have, on) + '</div></article>';
    }).join('');
  }

  var SHOP_CATS = ['prefix', 'prefcolor', 'skincolor', 'crit', 'wsound', 'minimap'];
  function renderShop() {
    var s = me.state;
    $('upgrades').innerHTML = (catalog.upgrades || []).map(function (u) {
      return '<div class="offer card"><div class="top-row"><div class="name">' + esc(name(u)) + '</div></div>' +
        '<button class="btn gold small" data-act="upgrade" data-item="' + esc(u.id) + '">' + esc(t('buy')) + ' · ' + fmt(u.price) + '</button></div>';
    }).join('');
    var crate = catalog.crate || { items: [] }, have = s.crate || {};
    var crateHtml = '<h2 class="cat-title">' + esc(t('crate')) + ' <small>' + esc(t('crateLead')) + '</small></h2><div class="grid offers">' + crate.items.map(function (it) {
      var left = have[it.id] || 0;
      var extra = it.id === 'invis' && left ? ' · ' + t('charges', { n: have.charges || 0 }) : '';
      return '<div class="offer card' + (left ? ' item on' : '') + '"><div class="top-row"><div class="name">' + esc(name(it)) + '</div>' +
        (left ? '<span class="chip green">' + esc(t('minLeft', { m: Math.ceil(left / 60) }) + extra) + '</span>' : '') + '</div>' +
        '<button class="btn gold small" data-act="crate" data-item="' + esc(it.id) + '">' + esc(left ? t('extend') : t('buy')) + ' · ' + fmt(it.price) + '</button></div>';
    }).join('') + '</div>';
    $('shopCats').innerHTML = crateHtml + SHOP_CATS.map(function (key) {
      var c = cat(key); if (!c) return '';
      var owned = s.owned[key] || [];
      var cards = c.items.filter(function (it) { return it.shop || owned.indexOf(it.id) >= 0; }).map(function (it) {
        var have = owned.indexOf(it.id) >= 0, on = s.equipped[key] === it.id;
        var swatch = /^#[0-9a-f]{6}$/i.test(it.id) ? '<span class="swatch" style="background:' + esc(it.id) + '"></span>' : '';
        return '<div class="offer card' + (on ? ' item on' : '') + '"><div class="top-row">' + swatch + '<div class="name">' + esc(name(it)) + '</div>' +
          (on ? '<span class="chip green">' + esc(t('worn')) + '</span>' : have ? '<span class="chip">' + esc(t('owned')) + '</span>' : '') + '</div>' +
          wearButton(key, it, have, on) + '</div>';
      }).join('');
      return '<h2 class="cat-title">' + esc(name(c)) + ' <small>' + owned.length + '/' + c.items.filter(function (i) { return i.shop; }).length + '</small></h2><div class="grid offers">' + cards + '</div>';
    }).join('');
  }

  function renderPass() {
    var s = me.state, bp = catalog.battlepass, p = s.battlepass;
    if (!p.active) {
      $('pass').innerHTML = '<div class="pass-head card"><div><h2 class="h-game">' + esc(t('passBuyTitle')) + '</h2><p class="muted">' +
        esc(t('passBuyLead', { d: bp.days, daily: fmt(bp.daily) })) + '</p></div><button class="btn gold" data-act="bp_buy">' +
        esc(t('passBuy', { p: fmt(bp.price) })) + '</button></div>' + tasksHtml(bp, p, false);
      return;
    }
    var all = bp.tasks.length, claimed = p.claimed.length, allDone = claimed >= all;
    var finals = [['lvl', 'finalLvl'], ['tokens', 'finalTok'], ['prefix', 'finalPrefix']].map(function (f) {
      var got = p.final.indexOf(f[0]) >= 0;
      return '<div class="offer card"><div class="name">' + esc(t(f[1])) + '</div>' + (got ? '<span class="chip green">' + esc(t('taken')) + '</span>' :
        '<button class="btn small' + (allDone ? ' gold' : ' ghost') + '" data-act="bp_final" data-item="' + f[0] + '"' + (allDone ? '' : ' disabled') + '>' + esc(t('take')) + '</button>') + '</div>';
    }).join('');
    $('pass').innerHTML = '<div class="pass-head card"><div><h2 class="h-game">' + esc(t('passBuyTitle')) + '</h2><p class="muted">' +
      esc(t('passLeft', { d: Math.ceil(p.left / 86400), c: claimed, all: all })) + '</p></div>' +
      (p.daily ? '<button class="btn gold" data-act="bp_daily">' + esc(t('daily', { n: fmt(bp.daily) })) + '</button>' : '<span class="chip green">' + esc(t('dailyTaken')) + '</span>') +
      '</div>' + tasksHtml(bp, p, true) + '<h2>' + esc(t('finalTitle')) + '</h2><div class="grid offers">' + finals + '</div>';
  }

  function tasksHtml(bp, p, active) {
    return '<ul class="tasks">' + bp.tasks.map(function (task) {
      var have = active ? (p.progress[task.kind] || 0) : 0, done = p.claimed.indexOf(task.id) >= 0;
      var share = Math.min(1, have / task.goal);
      var shown = task.kind === 'time' ? Math.floor(have / 3600) + '/' + Math.floor(task.goal / 3600) + (lang === 'en' ? ' h' : ' ч') : fmt(Math.min(have, task.goal)) + '/' + fmt(task.goal);
      return '<li class="task card' + (done ? ' done' : '') + '"><div>' + esc(name(task)) + ' <span class="muted small-text">' + esc(shown) + '</span></div>' +
        '<span class="reward">+' + fmt(task.reward) + '</span><div class="bar-track"><i style="width:' + Math.round(share * 100) + '%"></i></div></li>';
    }).join('') + '</ul>';
  }

  function renderPay() {
    var s = me.state, pay = catalog.pay;
    $('payLead').textContent = t('payLead', { lvl: pay.min_lvl, limit: pay.daily, today: s.pay.today });
  }

  /* ---------- market ---------- */
  function loadMarket() {
    var m = catalog.market;
    $('marketLead').textContent = t('marketLead', { d: m.days, max: m.max, tax: m.tax });
    var s = me.state, options = [];
    (catalog.categories || []).forEach(function (c) {
      (s.owned[c.key] || []).forEach(function (id) { var it = item(c.key, id); if (it && !it.admin) options.push('<option value="' + esc(c.key + '|' + id) + '">' + esc(name(c) + ': ' + name(it)) + '</option>'); });
    });
    $('sellItem').innerHTML = options.join('') || '<option value="">' + esc(t('nothingToSell')) + '</option>';
    api('/survival/market').then(function (r) {
      $('market').innerHTML = (r.listings || []).map(function (l) {
        return '<div class="offer card"><div class="top-row"><div class="name">' + esc(lang === 'en' ? l.en : l.ru) + '</div>' + (l.mine ? '<span class="chip gold">' + esc(t('mine')) + '</span>' : '') + '</div>' +
          '<div class="sub">' + esc(t('seller')) + ': ' + esc(l.nick || ('#' + l.seller)) + ' · ' + esc(t('daysLeft', { d: Math.ceil(l.left / 86400) })) + '</div>' +
          (l.mine ? '<button class="btn ghost small" data-act="market_withdraw" data-item="' + l.id + '">' + esc(t('withdraw')) + '</button>'
                  : '<button class="btn gold small" data-act="market_buy" data-item="' + l.id + '">' + esc(t('buy')) + ' · ' + fmt(l.price) + '</button>') + '</div>';
      }).join('') || '<div class="empty card">' + esc(t('marketEmpty')) + '</div>';
    });
  }
  $('sellForm').addEventListener('submit', function (ev) {
    ev.preventDefault();
    var v = $('sellItem').value.split('|'); if (v.length !== 2) return;
    act('market_sell', { cat: v[0], item: v[1], price: parseInt($('sellPrice').value, 10) }, t('listed')).then(loadMarket, function () {});
  });

  $('promoForm').addEventListener('submit', function (ev) {
    ev.preventDefault();
    var code = $('promoCode').value.trim(); if (!code) return;
    api('/survival/action', { method: 'POST', body: { op: op(), action: 'promo', args: { code: code } } }).then(function (r) {
      me.state = r.state; render(); $('promoCode').value = '';
      toast(t('promoDone', { n: fmt(r.amount), what: r.kind === 'lvl' ? 'LVL' : t('tokensWord') }));
    }).catch(function (e) { toast(errorText(e.code), true); });
  });

  $('payForm').addEventListener('submit', function (ev) {
    ev.preventDefault();
    var n = parseInt($('payAmount').value, 10);
    act('pay', { target: parseInt($('payTarget').value, 10), amount: n }, t('paid', { n: n })).catch(function () {});
  });

  /* ---------- top and live ---------- */
  function loadTop() {
    api('/survival/top?kind=' + topKind + '&limit=50').then(function (r) {
      $('top').innerHTML = (r.top || []).map(function (p) {
        var value = topKind === 'lvl' ? 'LVL ' + p.lvl : topKind === 'kills' ? fmt(p.kills) : topKind === 'tokens' ? fmt(p.tokens) : hm(p.time);
        return '<li class="' + (me && p.id === me.state.id ? 'me' : '') + '"><span class="place">' + p.place + '</span><span>' + esc(p.nick || '#' + p.id) + '</span><b class="amount">' + esc(value) + '</b></li>';
      }).join('') || '<li class="empty">' + esc(t('topEmpty')) + '</li>';
    });
  }
  document.querySelectorAll('#topKinds .tab').forEach(function (b) {
    b.addEventListener('click', function () {
      topKind = b.getAttribute('data-kind');
      document.querySelectorAll('#topKinds .tab').forEach(function (x) { x.setAttribute('aria-selected', String(x === b)); });
      loadTop();
    });
  });

  function loadLive() {
    api('/survival/live').then(function (r) {
      var servers = r.servers || [];
      $('live').innerHTML = servers.map(function (sv) {
        var players = (sv.players || []).filter(function (p) { return !p.bot; });
        var all = (sv.players || []).slice().sort(function (a, b) { return b.frags - a.frags; });
        var rows = all.map(function (p) {
          return '<li class="' + (p.alive ? '' : 'dead') + '"><span class="side' + (p.zombie ? ' z' : '') + '" title="' + esc(p.zombie ? t('zombie') : t('human')) + '"></span><span>' + esc(p.nick) + '</span><span>' + (p.lvl ? 'LVL ' + p.lvl : '') + '</span><b class="amount">' + p.frags + '</b></li>';
        }).join('');
        return '<article class="live card"><div class="live-map" style="background-image:url(/assets/lvl/maps/' + encodeURIComponent(sv.map) + '.webp)"><div><b>' + esc(sv.map) + '</b><span>' +
          esc(t('liveNow', { n: players.length, max: sv.max })) + '</span>' + (sv.timeleft > 0 ? '<span>' + esc(t('leftMin', { m: Math.ceil(sv.timeleft / 60) })) + '</span>' : '') + '</div></div>' +
          '<ul class="players"><li class="head"><span></span><span>' + esc(t('player')) + '</span><span>' + esc(t('lvl')) + '</span><span>' + esc(t('frags')) + '</span></li>' + rows + '</ul></article>';
      }).join('') || '<div class="empty card">' + esc(t('liveEmpty')) + '</div>';
    }).catch(function () { $('live').innerHTML = '<div class="empty card">' + esc(t('liveEmpty')) + '</div>'; });
  }

  /* news of the server and the violators board, under the live server */
  function span(sec) {
    if (sec < 0) return t('forever');
    var d = Math.floor(sec / 86400), h = Math.floor(sec / 3600) % 24, m = Math.floor(sec / 60) % 60;
    if (d) return lang === 'en' ? d + ' d ' + h + ' h' : d + ' д ' + h + ' ч';
    if (h) return lang === 'en' ? h + ' h ' + m + ' min' : h + ' ч ' + m + ' мин';
    return lang === 'en' ? Math.max(1, Math.ceil(sec / 60)) + ' min' : Math.max(1, Math.ceil(sec / 60)) + ' мин';
  }
  function loadNotes() {
    var none = function () { return {}; };
    Promise.all([api('/survival/news?limit=6').catch(none), api('/survival/board?limit=30').catch(none)]).then(function (r) {
      var news = (r[0].news || []).map(function (n) {
        var day = new Date(n.created * 1000).toLocaleDateString(lang === 'en' ? 'en-GB' : 'ru-RU', { day: 'numeric', month: 'short' });
        return '<li><time>' + esc(day) + '</time><span>' + esc(lang === 'en' ? n.en : n.ru) + '</span></li>';
      }).join('');
      var board = (r[1].board || []).map(function (b) {
        var why = [b.reason, b.vote ? t('byVote') : b.by].filter(Boolean).join(' · ');
        return '<li><span class="kind ' + (b.kind === 'ban' ? 'ban' : 'mute') + '">' + esc(t(b.kind === 'ban' ? 'ban' : 'mute')) + '</span><span><b>' + esc(b.name) + '</b>' +
          (why ? '<small>' + esc(why) + '</small>' : '') + '</span><span class="amount">' + esc(b.left < 0 ? t('forever') : t('leftShort', { t: span(b.left) })) + '</span></li>';
      }).join('');
      $('notes').innerHTML = '<h2>' + esc(t('newsTitle')) + '</h2>' + (news ? '<ul class="news card">' + news + '</ul>' : '<div class="empty card">' + esc(t('newsEmpty')) + '</div>') +
        '<h2>' + esc(t('boardTitle')) + '</h2>' + (board ? '<ul class="board card">' + board + '</ul>' : '<div class="empty card">' + esc(t('boardEmpty')) + '</div>');
    });
  }

  /* ---------- tabs and buttons ---------- */
  var currentTab = 'overview';
  function openTab(name_) {
    if (!document.querySelector('[data-view="' + name_ + '"]')) name_ = 'overview';
    currentTab = name_; store.set('czm-panel-tab', name_);
    document.querySelectorAll('#tabs .tab').forEach(function (b) { b.setAttribute('aria-selected', String(b.getAttribute('data-tab') === name_)); });
    document.querySelectorAll('.view').forEach(function (v) { v.hidden = v.getAttribute('data-view') !== name_; });
    clearInterval(liveTimer);
    if (name_ === 'market') loadMarket();
    if (name_ === 'top') loadTop();
    if (name_ === 'live') { loadLive(); loadNotes(); liveTimer = setInterval(function () { if (!document.hidden) loadLive(); }, 10000); }
    if (name_ === 'overview') refresh();
  }
  document.querySelectorAll('#tabs .tab').forEach(function (b) { b.addEventListener('click', function () { openTab(b.getAttribute('data-tab')); }); });

  document.addEventListener('click', function (ev) {
    var b = ev.target.closest('[data-act]'); if (!b || b.disabled) return;
    var a = b.getAttribute('data-act'), catKey = b.getAttribute('data-cat'), it = b.getAttribute('data-item');
    b.disabled = true;
    var p;
    if (a === 'buy') p = act('buy', { cat: catKey, item: it }, t('bought'));
    else if (a === 'wear') p = act('equip', { cat: catKey, item: it }, t('on'));
    else if (a === 'takeoff') p = act('equip', { cat: catKey, item: '' }, t('off'));
    else if (a === 'upgrade') p = act('upgrade', { item: it });
    else if (a === 'crate') p = act('crate', { item: it });
    else if (a === 'bp_buy' || a === 'bp_daily') p = act(a, {});
    else if (a === 'bp_final') p = act('bp_final', { item: it });
    else if (a === 'market_buy') p = act('market_buy', { listing: parseInt(it, 10) }, t('boughtMarket')).then(loadMarket);
    else if (a === 'market_withdraw') p = act('market_withdraw', { listing: parseInt(it, 10) }, t('withdrawn')).then(loadMarket);
    if (p) p.catch(function () {}).then(function () { b.disabled = false; });
  });

  applyLang();
  start();
})();
