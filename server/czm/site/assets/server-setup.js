(function () {
  'use strict';
  var doc = document;
  var tabs = Array.prototype.slice.call(doc.querySelectorAll('[data-platform]'));
  function choose(platform) {
    tabs.forEach(function (tab) {
      var selected = tab.getAttribute('data-platform') === platform;
      tab.setAttribute('aria-selected', String(selected));
      tab.tabIndex = selected ? 0 : -1;
      doc.getElementById(tab.getAttribute('aria-controls')).hidden = !selected;
    });
  }
  function fromHash() {
    if (/^#linux/.test(location.hash)) choose('linux');
    if (/^#windows/.test(location.hash)) choose('windows');
  }
  choose(/^#linux/.test(location.hash) ? 'linux' : 'windows');
  tabs.forEach(function (tab, index) {
    tab.addEventListener('click', function () { choose(tab.getAttribute('data-platform')); });
    tab.addEventListener('keydown', function (event) {
      if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
        event.preventDefault();
        var next = tabs[(index + 1) % tabs.length];
        choose(next.getAttribute('data-platform'));
        next.focus();
      }
    });
  });
  window.addEventListener('hashchange', fromHash);
  Array.prototype.forEach.call(doc.querySelectorAll('a[href="#windows"],a[href="#linux"]'), function (link) {
    link.addEventListener('click', function () { choose(link.hash.slice(1)); });
  });
  var status = doc.getElementById('copy-status'), timer;
  function say(text) {
    status.textContent = text;
    clearTimeout(timer);
    timer = setTimeout(function () { status.textContent = ''; }, 3500);
  }
  Array.prototype.forEach.call(doc.querySelectorAll('[data-copy]'), function (button) {
    button.addEventListener('click', function () {
      var code = doc.getElementById(button.getAttribute('data-copy'));
      if (!code) return;
      if (!navigator.clipboard) { say('Выдели команду и скопируй вручную'); return; }
      navigator.clipboard.writeText(code.textContent).then(function () {
        say('Команда скопирована');
      }, function () { say('Выдели команду и скопируй вручную'); });
    });
  });
  doc.getElementById('guide-theme').addEventListener('click', function () {
    var light = doc.documentElement.classList.toggle('light');
    try { localStorage.setItem('czm-theme', light ? 'light' : 'dark'); } catch (e) { /* private mode */ }
  });
  fetch('/server-downloads/release.json', {cache: 'no-cache'}).then(function (response) {
    if (!response.ok) throw new Error('Release metadata unavailable');
    return response.json();
  }).then(function (release) {
    if (release.version !== '1.0.0' || !Array.isArray(release.kits)) return;
    release.kits.forEach(function (kit) {
      if (kit.platform !== 'windows' && kit.platform !== 'linux') return;
      var target = doc.querySelector('[data-kit-size="' + kit.platform + '"]');
      if (target && Number.isFinite(kit.bytes) && kit.bytes > 0) {
        var size = kit.bytes >= 1048576 ? (kit.bytes / 1048576).toFixed(1) + ' МБ' : Math.ceil(kit.bytes / 1024) + ' КБ';
        target.textContent = 'v1.0.0 · ' + size + ' · установочный комплект';
      }
    });
  }).catch(function () { /* Static download links remain usable. */ });
}());
