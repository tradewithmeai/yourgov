/* YourGov onboarding tour — 3-step coachmark sequence shown once per
   session on /source-lens. Each step spotlights a target by drawing
   a translucent backdrop with a cut-out for that target, then floats
   a card with localised copy beside the cut-out.

   Targets resolved at runtime (so the panel-swap direction doesn't
   matter) and re-resolved on resize. Skip / Esc dismisses. */
(function () {
  'use strict';

  // Session-once gate. localStorage is too sticky; sessionStorage is
  // gentle and matches the welcome modal's pattern.
  var SESSION_KEY = 'mygov:lensTourSeen';
  try {
    if (sessionStorage.getItem(SESSION_KEY)) return;
  } catch (_) { /* private mode → allow */ }

  var overlay = document.getElementById('tour-overlay');
  if (!overlay) return;
  var spot = overlay.querySelector('.tour-spot');
  var card = overlay.querySelector('.tour-card');
  var titleEl = document.getElementById('tour-title');
  var bodyEl = document.getElementById('tour-body');
  var stepNumEl = document.getElementById('tour-step-num');
  var nextBtn = document.getElementById('tour-next');
  var skipBtn = document.getElementById('tour-skip');

  var copy = window.__TOUR_COPY__ || {
    steps: [
      { title: 'Start here',     body: 'Pick a vote, MP, or party in the source panel.' },
      { title: 'Watch the map',  body: 'The map colours your country by what you selected.' },
      { title: 'Switch the view', body: 'Use the mode ring to compare Vote / Party / Gender / Rebel splits.' }
    ],
    next: 'Next', done: 'Got it', skip: 'Skip tour'
  };

  // Each step names a CSS selector that resolves to the spotlight
  // target + an optional demo() function that actually performs the
  // suggested action so the user sees the cause-and-effect, not just
  // the text. We re-query on each transition + on resize so a late-
  // mounting iframe-driven element still gets highlighted correctly.
  // Order: introduce the OUTPUT (map) first, then the INPUT (source
  // panel where the user clicks), then the advanced mode-switcher.
  var STEPS = [
    {
      selector: '.map-pane > .map-wrap',
      pad: 0,
      // Demo: paint the map with party colours so the user can see
      // immediately what the visualisation panel does.
      demo: function () {
        var btn = document.getElementById('topic-party-split');
        if (btn) btn.click();
      }
    },
    {
      selector: '.source-pane',
      pad: 0,
      // Demo: programmatically click the first division row inside
      // the source iframe. This triggers visualiseDivision which
      // repaints the map with the real vote colouring — the user
      // sees the source → map connection in action. Same-origin
      // iframe access only; silent fallback if unavailable.
      demo: function () {
        try {
          var iframe = document.getElementById('source-frame');
          var doc = iframe && iframe.contentDocument;
          if (!doc) return;
          var row = doc.querySelector('tr[data-lens-division-id], a[href*="/publicwhip/division/"]');
          if (row) row.click();
        } catch (e) { /* cross-origin or not loaded — skip */ }
      }
    },
    {
      selector: '.service-action.ring-2',
      pad: 12,
      // Demo: switch to a different wedge to demonstrate that the
      // mode picker actually swaps what the colours mean. Pick
      // gender-split since party was shown in step 1.
      demo: function () {
        var btn = document.getElementById('topic-gender-split');
        if (btn) btn.click();
      }
    }
  ];

  var current = 0;

  function getTargetRect(step) {
    var el = document.querySelector(step.selector);
    if (!el) return null;
    var r = el.getBoundingClientRect();
    var pad = step.pad || 0;
    return { x: r.left - pad, y: r.top - pad, w: r.width + pad * 2, h: r.height + pad * 2 };
  }

  function placeSpot(rect) {
    spot.style.left = rect.x + 'px';
    spot.style.top = rect.y + 'px';
    spot.style.width = rect.w + 'px';
    spot.style.height = rect.h + 'px';
  }

  function placeCard(rect) {
    // Card sits beside the spotlight, picking the side that has more
    // room. Default below; if no room, above; if neither, beside.
    var cardRect = card.getBoundingClientRect();
    var vw = window.innerWidth;
    var vh = window.innerHeight;
    var pad = 20;
    var spaceBelow = vh - (rect.y + rect.h);
    var spaceAbove = rect.y;
    var spaceRight = vw - (rect.x + rect.w);
    var spaceLeft = rect.x;
    var x, y;
    if (spaceBelow >= cardRect.height + pad) {
      y = rect.y + rect.h + pad;
      x = Math.max(pad, Math.min(rect.x + rect.w / 2 - cardRect.width / 2, vw - cardRect.width - pad));
    } else if (spaceAbove >= cardRect.height + pad) {
      y = rect.y - cardRect.height - pad;
      x = Math.max(pad, Math.min(rect.x + rect.w / 2 - cardRect.width / 2, vw - cardRect.width - pad));
    } else if (spaceRight >= cardRect.width + pad) {
      x = rect.x + rect.w + pad;
      y = Math.max(pad, Math.min(rect.y + rect.h / 2 - cardRect.height / 2, vh - cardRect.height - pad));
    } else if (spaceLeft >= cardRect.width + pad) {
      x = rect.x - cardRect.width - pad;
      y = Math.max(pad, Math.min(rect.y + rect.h / 2 - cardRect.height / 2, vh - cardRect.height - pad));
    } else {
      // Last resort — centre.
      x = (vw - cardRect.width) / 2;
      y = (vh - cardRect.height) / 2;
    }
    card.style.left = x + 'px';
    card.style.top = y + 'px';
  }

  function render() {
    var step = STEPS[current];
    var rect = getTargetRect(step);
    if (!rect) {
      // Target not in DOM — skip this step.
      advance();
      return;
    }
    placeSpot(rect);
    var c = copy.steps[current] || {};
    titleEl.textContent = c.title || '';
    bodyEl.textContent = c.body || '';
    stepNumEl.textContent = String(current + 1);
    nextBtn.textContent = (current === STEPS.length - 1) ? copy.done : copy.next;
    // Reflow before placing the card so its measured size is accurate.
    void card.offsetHeight;
    placeCard(rect);
    // Run the step's demo action after the spotlight lands so the
    // user reads the copy first, then sees the cause-and-effect.
    if (typeof step.demo === 'function') {
      setTimeout(function () { try { step.demo(); } catch (e) {} }, 350);
    }
  }

  function show() {
    overlay.hidden = false;
    // Focus the next button so keyboard users can tab/space through.
    setTimeout(function () { try { nextBtn.focus(); } catch (e) {} }, 50);
    render();
  }

  function dismiss() {
    overlay.hidden = true;
    try { sessionStorage.setItem(SESSION_KEY, '1'); } catch (e) {}
    window.removeEventListener('resize', onResize);
    document.removeEventListener('keydown', onKey);
  }

  function advance() {
    if (current >= STEPS.length - 1) { dismiss(); return; }
    current += 1;
    render();
  }

  function onKey(e) {
    if (overlay.hidden) return;
    if (e.key === 'Escape') { e.preventDefault(); dismiss(); }
    else if (e.key === 'Enter') { e.preventDefault(); advance(); }
  }

  var resizeRaf = null;
  function onResize() {
    if (resizeRaf) cancelAnimationFrame(resizeRaf);
    resizeRaf = requestAnimationFrame(render);
  }

  nextBtn.addEventListener('click', advance);
  skipBtn.addEventListener('click', dismiss);
  window.addEventListener('resize', onResize);
  document.addEventListener('keydown', onKey);

  // Wait briefly so panes are laid out (iframes mid-load is fine —
  // we spotlight the pane element, not iframe content).
  setTimeout(show, 400);
})();
