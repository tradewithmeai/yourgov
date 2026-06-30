/* YourGov theme picker — three switchable themes persisted in
   localStorage. Initial theme is applied inline in <head> to avoid
   flash; this module handles the popover UI and the replay-tour
   shortcut. */
(function () {
  'use strict';

  var KEY = 'yourgov:lensTheme';
  var THEMES = ['theme-glass', 'theme-quiet', 'theme-editorial'];

  var trigger = document.getElementById('theme-picker-trigger');
  var popover = document.getElementById('theme-picker-popover');
  if (!trigger || !popover) return;

  function currentTheme() {
    var html = document.documentElement;
    for (var i = 0; i < THEMES.length; i += 1) {
      if (html.classList.contains(THEMES[i])) return THEMES[i];
    }
    return 'theme-glass';
  }

  function setTheme(name) {
    if (THEMES.indexOf(name) === -1) return;
    var html = document.documentElement;
    THEMES.forEach(function (t) { html.classList.remove(t); });
    html.classList.add(name);
    try { localStorage.setItem(KEY, name); } catch (e) {}
    syncActive();
  }

  function syncActive() {
    var cur = currentTheme();
    popover.querySelectorAll('.theme-card[data-theme]').forEach(function (card) {
      card.classList.toggle('is-active', card.getAttribute('data-theme') === cur);
    });
  }

  function open() {
    popover.hidden = false;
    trigger.setAttribute('aria-expanded', 'true');
    syncActive();
    document.addEventListener('click', onDocClick, true);
    document.addEventListener('keydown', onKey);
  }

  function close() {
    popover.hidden = true;
    trigger.setAttribute('aria-expanded', 'false');
    document.removeEventListener('click', onDocClick, true);
    document.removeEventListener('keydown', onKey);
  }

  function onDocClick(e) {
    if (popover.contains(e.target) || trigger.contains(e.target)) return;
    close();
  }
  function onKey(e) { if (e.key === 'Escape') close(); }

  trigger.addEventListener('click', function (e) {
    e.stopPropagation();
    if (popover.hidden) open(); else close();
  });

  popover.addEventListener('click', function (e) {
    var card = e.target.closest('.theme-card[data-theme]');
    if (card) {
      setTheme(card.getAttribute('data-theme'));
      // Keep the popover open so the user can preview each option.
      return;
    }
    if (e.target.closest('#theme-replay-tour')) {
      close();
      // The tour is opt-in; start it directly (no reload needed).
      if (typeof window.startYourGovTour === 'function') {
        window.startYourGovTour();
      } else {
        // Fallback for an older bundle: clear the gate and reload.
        try { sessionStorage.removeItem('yourgov:lensTourSeen'); } catch (err) {}
        window.location.reload();
      }
    }
  });

  syncActive();
})();
