/* YourGov onboarding tour — 3-step coachmark sequence on /source-lens.
   Each step spotlights a target by drawing a translucent backdrop with a
   cut-out for that target, then floats a card with localised copy beside it.

   OPT-IN: the tour does NOT auto-fire. On first visit the intro panel leads,
   and the tour is started on demand via window.startYourGovTour() — wired to
   the intro panel's "Take a quick tour" button and the theme-picker's "Replay
   tour" action. This keeps the first-run experience to ONE surface at a time
   (intro first, guided tour only when the user asks for it).

   Targets resolved at runtime (so the panel-swap direction doesn't matter)
   and re-resolved on resize. Skip / Esc dismisses. */
(function () {
  'use strict';

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
      { title: 'Find your MP', body: 'Search by postcode, constituency, or MP name in the search at the centre of the map.' },
      { title: 'See how they voted', body: "Your MP's full voting record opens here — with a Contact button to email them." },
      { title: 'Switch the view', body: 'Recolour the map by Vote, Party, Gender, or Rebellion using the mode ring.' }
    ],
    next: 'Next', done: 'Got it', skip: 'Skip tour'
  };

  // Each step names a CSS selector that resolves to the spotlight target + an
  // optional demo() that performs the suggested action so the user sees cause
  // and effect, not just text. Re-queried on each transition + on resize.
  // Order follows the real journey: find your MP (search) → read their record +
  // contact them (left panel) → switch the map view (mode ring).
  var STEPS = [
    {
      // The centre "S" search widget — where the journey starts.
      selector: '#map-search',
      panelSide: 'map',
      pad: 10,
      // Demo: expand the collapsed search pill so the user sees where to type.
      demo: function () {
        var search = document.getElementById('map-search');
        var trigger = document.getElementById('map-search-trigger');
        if (search && trigger && search.classList.contains('is-collapsed')) trigger.click();
      }
    },
    {
      // The left panel: the MP voting record + the frozen Contact card land here.
      selector: '.source-pane',
      panelSide: 'source',
      pad: 0
      // No demo: the copy explains what appears here once an MP is picked.
      // (Driving the multi-step search/resolve during the tour would be fragile.)
    },
    {
      selector: '.service-action.ring-2',
      panelSide: 'map',
      pad: 12,
      // Demo: colour the map by party so the mode ring's effect is visible
      // (party split works without a division selected).
      demo: function () {
        var btn = document.getElementById('topic-party-split');
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

  function clamp(value, min, max) {
    if (max < min) return min;
    return Math.max(min, Math.min(value, max));
  }

  function panelBounds(side) {
    var panel = document.querySelector(side === 'source' ? '.source-pane' : '.map-pane');
    if (!panel) return null;
    var r = panel.getBoundingClientRect();
    var left = Math.max(0, r.left);
    var top = Math.max(0, r.top);
    var right = Math.min(window.innerWidth, r.right);
    var bottom = Math.min(window.innerHeight, r.bottom);
    if (right <= left || bottom <= top) return null;
    return { x: left, y: top, w: right - left, h: bottom - top };
  }

  function placeCard(rect, step) {
    // Card sits beside the spotlight, picking the side that has more
    // room. Default below; if no room, above; if neither, beside.
    var cardRect = card.getBoundingClientRect();
    var vw = window.innerWidth;
    var vh = window.innerHeight;
    var pad = 20;
    if (vw >= 921 && step && (step.panelSide === 'map' || step.panelSide === 'source')) {
      var bounds = panelBounds(step.panelSide);
      if (bounds && bounds.w >= cardRect.width + pad * 2) {
        var panelMinX = bounds.x + pad;
        var panelMaxX = bounds.x + bounds.w - cardRect.width - pad;
        var panelMinY = Math.max(pad, bounds.y + pad);
        var panelMaxY = Math.min(vh - cardRect.height - pad, bounds.y + bounds.h - cardRect.height - pad);
        var anchoredX = clamp(rect.x + rect.w / 2 - cardRect.width / 2, panelMinX, panelMaxX);
        var anchoredY;
        if (rect.y + rect.h + pad + cardRect.height <= bounds.y + bounds.h) {
          anchoredY = rect.y + rect.h + pad;
        } else if (rect.y - cardRect.height - pad >= bounds.y) {
          anchoredY = rect.y - cardRect.height - pad;
        } else {
          anchoredY = rect.y + rect.h / 2 - cardRect.height / 2;
        }
        card.style.left = anchoredX + 'px';
        card.style.top = clamp(anchoredY, panelMinY, panelMaxY) + 'px';
        return;
      }
    }
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
    placeCard(rect, step);
    // Run the step's demo action after the spotlight lands so the
    // user reads the copy first, then sees the cause-and-effect.
    if (typeof step.demo === 'function') {
      setTimeout(function () { try { step.demo(); } catch (e) {} }, 350);
    }
  }

  var listening = false;

  function start() {
    current = 0;
    overlay.hidden = false;
    if (!listening) {
      window.addEventListener('resize', onResize);
      document.addEventListener('keydown', onKey);
      listening = true;
    }
    // Focus the next button so keyboard users can tab/space through.
    setTimeout(function () { try { nextBtn.focus(); } catch (e) {} }, 50);
    render();
  }

  function dismiss() {
    overlay.hidden = true;
    if (listening) {
      window.removeEventListener('resize', onResize);
      document.removeEventListener('keydown', onKey);
      listening = false;
    }
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

  // Opt-in entry point. Called by the intro panel's "Take a quick tour" button
  // and the theme-picker's "Replay tour" action. No auto-fire on load.
  window.startYourGovTour = start;
})();
