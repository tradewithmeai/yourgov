/* YourGov autopilot demo orchestrator.

   Hard-disabled by default. Runs ONLY when:
     ?autopilot=1   on /global  → runs the globe-to-Lens half
     ?autopilot=1   on /source-lens → runs the Lens half

   Cross-page handoff via the same query param + sessionStorage flag.

   Guard-rails baked in:
     • Module is a no-op unless the autopilot=1 query flag is present.
     • A "Stop demo" pill is mounted from the first frame and can abort
       at any point.
     • Each scene is event-driven where the event exists (iframe load,
       map ready, fetch completion) and only falls back to a sleep when
       there is no signal to listen for.
     • Per-scene timeout aborts that scene cleanly and the script either
       advances to the next scene or stops; the timeline never hangs.
     • Global watchdog timeout aborts the entire run if total wall-clock
       exceeds a hard cap (default 120s).
*/
(function () {
  'use strict';

  // ── 1. Gate ─────────────────────────────────────────────────
  var params = new URLSearchParams(window.location.search);
  if (params.get('autopilot') !== '1') return;          // never autoruns

  // Stash the flag so cross-page handoff (e.g. /global → /source-lens)
  // can pick it up. The next page checks both the URL AND this key.
  try {
    sessionStorage.setItem('mygov:autopilot', '1');
    // Suppress the onboarding tour so it doesn't intercept demo clicks.
    sessionStorage.setItem('mygov:lensTourSeen', '1');
  } catch (_) {}

  // Identify which half of the script to run.
  var page;
  if (/\/global\b/.test(window.location.pathname)) page = 'global';
  else if (/\/source-lens\b/.test(window.location.pathname)) page = 'sourceLens';
  else return;     // not a demo surface; bail

  // ── 2. Overlay scaffolding ──────────────────────────────────
  var cursor = document.createElement('div');
  cursor.className = 'demo-cursor';
  cursor.style.transform = 'translate(' + (window.innerWidth / 2) + 'px, ' + (window.innerHeight / 2) + 'px)';
  document.body.appendChild(cursor);

  var caption = document.createElement('div');
  caption.className = 'demo-caption';
  caption.setAttribute('role', 'status');
  caption.setAttribute('aria-live', 'polite');
  document.body.appendChild(caption);

  var stopBtn = document.createElement('button');
  stopBtn.type = 'button';
  stopBtn.className = 'demo-stop';
  stopBtn.textContent = 'Stop demo';
  stopBtn.addEventListener('click', function () { abort('user stopped'); });
  document.body.appendChild(stopBtn);

  // ── 3. State + abort ────────────────────────────────────────
  var aborted = false;
  function abort(reason) {
    if (aborted) return;
    aborted = true;
    try { sessionStorage.removeItem('mygov:autopilot'); } catch (_) {}
    if (cursor && cursor.parentNode) cursor.parentNode.removeChild(cursor);
    if (caption && caption.parentNode) caption.parentNode.removeChild(caption);
    if (stopBtn && stopBtn.parentNode) stopBtn.parentNode.removeChild(stopBtn);
    // eslint-disable-next-line no-console
    console.info('[autopilot] stopped:', reason);
  }
  // Global watchdog — 120s hard cap.
  var watchdog = window.setTimeout(function () { abort('global timeout'); }, 120000);

  // ── 4. Primitives ───────────────────────────────────────────
  function sleep(ms) {
    return new Promise(function (resolve) { window.setTimeout(resolve, ms); });
  }
  function moveCursor(x, y) {
    cursor.style.transform = 'translate(' + x + 'px, ' + y + 'px)';
    // Resolve when the CSS transition completes; fall back at 800ms.
    return new Promise(function (resolve) {
      var done = false;
      function finish() { if (done) return; done = true; cursor.removeEventListener('transitionend', finish); resolve(); }
      cursor.addEventListener('transitionend', finish);
      window.setTimeout(finish, 820);
    });
  }
  function moveToElement(el) {
    if (!el) return Promise.resolve();
    var r = el.getBoundingClientRect();
    return moveCursor(r.left + r.width / 2, r.top + r.height / 2);
  }
  function clickAtCursor() {
    cursor.classList.add('is-clicking');
    var x = parseInt(cursor.style.transform.match(/translate\((-?\d+(?:\.\d+)?)/)?.[1] || '0', 10);
    var y = parseInt(cursor.style.transform.match(/,\s*(-?\d+(?:\.\d+)?)/)?.[1] || '0', 10);
    var rip = document.createElement('div');
    rip.className = 'demo-ripple';
    rip.style.transform = 'translate(' + x + 'px, ' + y + 'px)';
    document.body.appendChild(rip);
    window.setTimeout(function () { rip.remove(); }, 600);
    window.setTimeout(function () { cursor.classList.remove('is-clicking'); }, 140);
  }
  function clickElement(el) {
    if (!el) return;
    return moveToElement(el).then(function () {
      if (aborted) return;
      clickAtCursor();
      // Dispatch a real click event on the element so existing handlers fire.
      el.click();
    });
  }
  function setCaption(text) {
    caption.textContent = text;
    caption.classList.add('is-visible');
    // Debug log so we can audit scene timing post-hoc via window.__autopilotLog.
    try {
      if (!window.__autopilotLog) window.__autopilotLog = [];
      window.__autopilotLog.push({ t: Date.now(), caption: text });
    } catch (_) {}
  }
  function hideCaption() {
    caption.classList.remove('is-visible');
  }

  /**
   * Wait for a condition to become truthy. checkFn is polled every
   * 100ms; resolves when truthy, rejects on per-scene timeout.
   */
  function waitFor(checkFn, opts) {
    opts = opts || {};
    var interval = opts.interval || 100;
    var timeout = opts.timeout || 8000;
    var label = opts.label || 'condition';
    return new Promise(function (resolve, reject) {
      var start = Date.now();
      (function tick() {
        if (aborted) return reject(new Error('aborted'));
        var v;
        try { v = checkFn(); } catch (_) { v = false; }
        if (v) return resolve(v);
        if (Date.now() - start >= timeout) return reject(new Error('timeout: ' + label));
        window.setTimeout(tick, interval);
      })();
    });
  }

  /**
   * Wait for a specific window message event (resolves on first match).
   */
  function waitForMessage(typeStr, opts) {
    opts = opts || {};
    var timeout = opts.timeout || 8000;
    return new Promise(function (resolve, reject) {
      var t = window.setTimeout(function () {
        window.removeEventListener('message', handler);
        reject(new Error('timeout: message ' + typeStr));
      }, timeout);
      function handler(e) {
        if (!e.data || e.data.type !== typeStr) return;
        if (e.origin !== window.location.origin) return;
        window.clearTimeout(t);
        window.removeEventListener('message', handler);
        resolve(e.data);
      }
      window.addEventListener('message', handler);
    });
  }

  function safeScene(name, fn, timeoutMs) {
    if (aborted) return Promise.resolve();
    var timeout = new Promise(function (_, reject) {
      window.setTimeout(function () { reject(new Error('scene timeout: ' + name)); }, timeoutMs || 12000);
    });
    return Promise.race([Promise.resolve().then(fn), timeout]).catch(function (e) {
      // eslint-disable-next-line no-console
      console.warn('[autopilot]', name, 'failed:', e && e.message);
      // Scene failures don't abort the whole demo — log and continue.
    });
  }

  // ── 5. Globe surface scenes ─────────────────────────────────
  async function runGlobeScenes() {
    setCaption('Welcome. Public records are public — exploring civic transparency worldwide.');
    await sleep(3200);

    // Wait until the globe API is up — three.js + countries loaded.
    await safeScene('globe-ready', function () {
      return waitFor(function () {
        return !!(window.__autopilotGlobe && window.__autopilotGlobe.ready);
      }, { timeout: 12000, label: 'globe ready' });
    });

    setCaption('Every UN member, mapped for civic-data feasibility.');
    if (window.__autopilotGlobe && window.__autopilotGlobe.fastSpin) {
      window.__autopilotGlobe.fastSpin(10);   // 10× normal speed
    }
    await sleep(5000);

    // First stop: India.
    setCaption('Spinning to India — civic-data feasibility report.');
    await safeScene('stop-IN', function () {
      if (window.__autopilotGlobe && window.__autopilotGlobe.stopAt) {
        return window.__autopilotGlobe.stopAt('IN');
      }
    }, 8000);
    // Hold so the audience reads the India card.
    await sleep(5000);

    setCaption('Now spinning to the United Kingdom — the live reference adapter.');
    if (window.__autopilotGlobe && window.__autopilotGlobe.fastSpin) {
      window.__autopilotGlobe.fastSpin(10);
    }
    await sleep(2800);
    await safeScene('stop-GB', function () {
      if (window.__autopilotGlobe && window.__autopilotGlobe.stopAt) {
        return window.__autopilotGlobe.stopAt('GB');
      }
    }, 8000);
    // Hold so the audience reads the UK card.
    await sleep(3500);

    // Move the cursor toward the country card (right side of viewport)
    // where a real user would see and click "Enter site", then
    // navigate directly to /source-lens with the autopilot flag set.
    // (The "Open UK Source Lens" link only renders dynamically via the
    // entry modal — we navigate explicitly so the demo doesn't depend
    // on that element being present.)
    setCaption('Opening the UK Source Lens.');
    var cardEl = document.getElementById('country-card') ||
                 document.querySelector('.country-card') ||
                 document.querySelector('.country-panel');
    if (cardEl) {
      var rr = cardEl.getBoundingClientRect();
      await moveCursor(rr.left + Math.min(rr.width / 2, 200),
                       rr.top + Math.min(rr.height / 2, 200));
      await sleep(500);
      clickAtCursor();
    }
    await sleep(700);
    window.location.href = '/source-lens?source=lens&cc=GB&lang=' +
      encodeURIComponent((document.documentElement.lang || 'en')) +
      '&autopilot=1';
  }

  // ── 6. Source Lens surface scenes ───────────────────────────
  async function runSourceLensScenes() {
    setCaption('Inside the UK Source Lens.');
    await sleep(1500);

    // Wait for the source iframe to finish loading initial content,
    // then for the map iframe API to mount.
    await safeScene('source-iframe-load', function () {
      return waitFor(function () {
        var sf = document.getElementById('source-frame');
        return sf && sf.contentDocument && sf.contentDocument.readyState === 'complete';
      }, { timeout: 12000, label: 'source iframe ready' });
    });
    await safeScene('map-iframe-load', function () {
      return waitFor(function () {
        var mf = document.getElementById('map-frame');
        return mf && mf.contentWindow && mf.contentWindow.mygovConstituencyMap &&
               typeof mf.contentWindow.mygovConstituencyMap.setConstituencyColours === 'function';
      }, { timeout: 15000, label: 'map iframe ready' });
    });

    // Scene: open S search and type "Davey".
    setCaption('Searching for the Lib Dem leader.');
    var sBtn = document.getElementById('map-search-trigger');
    var sInput = document.getElementById('mp-search-input');
    if (sBtn && sInput) {
      await moveToElement(sBtn);
      await sleep(300);
      clickAtCursor();
      sBtn.click();
      await sleep(550);
      // Type the user query — the real product autocompletes to the
      // full MP name. Typing "Ed Davey" mirrors what a citizen would
      // actually type into the lens.
      var query = 'Ed Davey';
      for (var i = 0; i < query.length; i += 1) {
        if (aborted) return;
        sInput.value = query.slice(0, i + 1);
        sInput.dispatchEvent(new Event('input', { bubbles: true }));
        await sleep(220);
      }
      // Wait until the inline ghost completion or the fetch completes.
      await safeScene('search-suggestion', function () {
        return waitFor(function () {
          var ghost = document.querySelector('.map-search-ghost .tail');
          return ghost && ghost.textContent && ghost.textContent.length > 0;
        }, { timeout: 4000, label: 'autocomplete tail' });
      }, 5000);
      // Slight beat to let the audience SEE the ghost completion.
      await sleep(1200);
      // Press Enter to accept top match.
      setCaption('Opening Ed Davey’s profile in the right pane.');
      sInput.focus();
      sInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
      await sleep(2400);
    }

    // Scene: highlight the constituency on the map (pop-zoom effect via
    // a brief CSS transform pulse on the map iframe).
    setCaption('Kingston and Surbiton — Ed Davey’s constituency.');
    var mapWrap = document.querySelector('.map-wrap');
    if (mapWrap) {
      mapWrap.style.transition = 'transform 600ms cubic-bezier(0.16, 1, 0.3, 1)';
      mapWrap.style.transform = 'scale(1.04)';
      await sleep(700);
      mapWrap.style.transform = 'scale(1.0)';
      await sleep(900);
    }

    // Scene: click first division row in the source iframe (single click
    // = visualise on the map). Event-driven — wait for map:applied.
    setCaption('One click on a division visualises the vote.');
    var sf = document.getElementById('source-frame');
    var firstRow;
    try {
      firstRow = sf.contentDocument.querySelector('a[href*="/publicwhip/division/"], tr[data-lens-division-id] a, [data-lens-division-id]');
    } catch (_) {}
    if (firstRow) {
      var rrect = firstRow.getBoundingClientRect();
      var sfRect = sf.getBoundingClientRect();
      await moveCursor(sfRect.left + rrect.left + rrect.width / 2,
                       sfRect.top + rrect.top + rrect.height / 2);
      await sleep(300);
      clickAtCursor();
      firstRow.click();
      // Wait for the map to apply colours (parent listens for mygov:map:applied).
      await safeScene('map-applied', function () {
        return waitForMessage('mygov:map:applied', { timeout: 8000 });
      }, 9000);
      // Beat to let the audience read the map update.
      await sleep(2000);
    }

    // Scene: open Explain Mode via ring 1 click.
    setCaption('Explain Mode — any highlighted item explains itself.');
    var explainRing = document.querySelector('.service-action.ring-1');
    if (explainRing) {
      var er = explainRing.getBoundingClientRect();
      // Click on the band (top of ring), not the dead centre.
      await moveCursor(er.left + er.width / 2, er.top + 12);
      await sleep(300);
      clickAtCursor();
      // Trigger Explain via the canonical button (avoids the wedge issue).
      var explainBtn = document.getElementById('explain-mode-btn');
      if (explainBtn) explainBtn.click();
      await sleep(2200);
    }

    // Scene: click an explainable inside the source iframe to open the drawer.
    setCaption('Clicking a division opens the explainer drawer.');
    var explainable;
    try {
      explainable = sf.contentDocument.querySelector('[data-explainable], h1, h2');
    } catch (_) {}
    if (explainable) {
      var er2 = explainable.getBoundingClientRect();
      var sfRect2 = sf.getBoundingClientRect();
      await moveCursor(sfRect2.left + er2.left + er2.width / 2,
                       sfRect2.top + er2.top + er2.height / 2);
      await sleep(300);
      clickAtCursor();
      explainable.click();
      // Hold so the explainer drawer animates open and the user reads.
      await sleep(3400);
    }

    // Scene: close Explain Mode.
    setCaption('Closing Explain Mode.');
    var explainBtn2 = document.getElementById('explain-mode-btn');
    if (explainBtn2 && document.body.classList.contains('explain-mode-on')) {
      explainBtn2.click();
      await sleep(1000);
    }

    // Scene: final — point to the WriteToThem CTA in the source pane.
    setCaption('And one click later — write to your MP.');
    var writeLink;
    try {
      writeLink = sf.contentDocument.querySelector('a[href*="writetothem.com"]');
    } catch (_) {}
    if (writeLink) {
      var wr = writeLink.getBoundingClientRect();
      var sfRect3 = sf.getBoundingClientRect();
      await moveCursor(sfRect3.left + wr.left + wr.width / 2,
                       sfRect3.top + wr.top + wr.height / 2);
      // Let the audience see the cursor land on the CTA before it fires.
      await sleep(1100);
      clickAtCursor();
      // Open WriteToThem in a new tab so the demo doesn't navigate away.
      window.open(writeLink.href, '_blank', 'noopener');
      await sleep(1400);
    }

    setCaption('Public records → readable lens → personal action. Demo complete.');
    await sleep(4500);
    hideCaption();
    abort('completed');
  }

  // ── 7. Kick off ─────────────────────────────────────────────
  function start() {
    var runner = (page === 'global') ? runGlobeScenes : runSourceLensScenes;
    runner().then(function () { window.clearTimeout(watchdog); })
            .catch(function (e) { abort('script error: ' + (e && e.message)); });
  }

  if (document.readyState === 'complete') start();
  else window.addEventListener('load', start);
})();
