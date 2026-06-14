(function () {
  'use strict';

  /* ── State ─────────────────────────────────────────────── */
  var explainModeOn = false;
  var lastExplainContext = null;
  var lastCtxKey = '';
  var lastPriorExplanation = '';
  var clientCache = {};

  // Depth levels:
  // 0 = Skim
  // 2 = Detailed
  // We intentionally avoid 1 (Practical) and 3 (Full) because they were not meaningfully distinct.
  var currentLevel = parseInt(localStorage.getItem('explain-level') || '0', 10);
  if ([0, 1, 2, 3].indexOf(currentLevel) === -1) currentLevel = 0;
  if (currentLevel === 1) currentLevel = 0; // treat Practical as Skim
  if (currentLevel === 3) currentLevel = 2; // treat Full as Detailed

  // Legacy flag kept for compatibility, but depth is always 2-step now.
  var explainMinimalMode = true;

  /* ── Helpers ────────────────────────────────────────────── */
  function escHtml(s) {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function makeCtxKey(ctx) {
    return ctx.url + '|' + JSON.stringify(ctx.metadata || {});
  }

  /* ── DOM setup ─────────────────────────────────────────── */
  function injectUI() {
    // In an iframe: do not inject floating UI (button/drawer). Instead,
    // support parent-controlled Explain Mode and forward clicks to the parent
    // so one drawer can serve both panes.
    if (window.parent !== window) {
      setupIframeBridge();
      return;
    }

    // Toggle button
    var btn = document.createElement('button');
    btn.id = 'explain-mode-btn';
    btn.setAttribute('aria-pressed', 'false');
    btn.textContent = '💡 Explain Mode';
    document.body.appendChild(btn);

    // Hint
    var hint = document.createElement('div');
    hint.id = 'explain-mode-hint';
    hint.textContent = 'Explain Mode ON — click highlighted headings or division rows.';
    document.body.appendChild(hint);

    // Backdrop
    var backdrop = document.createElement('div');
    backdrop.id = 'explain-drawer-backdrop';
    document.body.appendChild(backdrop);

    var levelBarButtons =
      '<button class="explain-level-btn" data-level="0" title="Quick overview">Skim</button>' +
      '<button class="explain-level-btn" data-level="2" title="More context and detail">Detailed</button>';

    // Drawer
    var drawer = document.createElement('div');
    drawer.id = 'explain-drawer';
    drawer.innerHTML =
      '<div id="explain-drawer-header">' +
        '<span class="drawer-title">Explain Mode</span>' +
        '<button id="explain-drawer-close" aria-label="Close">&times;</button>' +
      '</div>' +
      '<div id="explain-level-bar">' + levelBarButtons + '</div>' +
      '<div id="explain-drawer-body"></div>' +
      '<div id="explain-drawer-footer">' +
        '<input id="explain-followup-input" type="text" placeholder="Ask a follow-up…" />' +
        '<button id="explain-followup-ask">Ask</button>' +
      '</div>';
    document.body.appendChild(drawer);

    btn.addEventListener('click', toggleMode);
    backdrop.addEventListener('click', closeDrawer);
    document.getElementById('explain-drawer-close').addEventListener('click', closeDrawer);
    document.getElementById('explain-followup-ask').addEventListener('click', sendFollowup);
    document.getElementById('explain-followup-input').addEventListener('keydown', function (e) {
      if (e.key === 'Enter') sendFollowup();
    });

    document.getElementById('explain-level-bar').addEventListener('click', function (e) {
      var btn = e.target.closest('.explain-level-btn');
      if (!btn || !lastExplainContext) return;
      var newLevel = parseInt(btn.dataset.level, 10);
      if (newLevel === currentLevel) return;
      currentLevel = newLevel;
      localStorage.setItem('explain-level', newLevel);
      updateLevelBar();
      var cacheKey = lastCtxKey + ':' + newLevel;
      if (clientCache[cacheKey]) {
        renderExplainResponse(clientCache[cacheKey]);
      } else {
        setDrawerLoading();
        callExplainAPI(lastExplainContext, null);
      }
    });

    updateLevelBar();
  }

  function setupIframeBridge() {
    // Parent will toggle explain mode via postMessage. When enabled, this iframe
    // highlights [data-explainable] and forwards click context back to the parent.
    window.addEventListener('message', function (event) {
      try {
        if (event.origin !== window.location.origin) return;
        if (!event.data || event.data.type !== 'mygov:explain-mode') return;
        explainModeOn = !!event.data.on;
        document.body.classList.toggle('explain-mode-on', explainModeOn);
      } catch (e) {}
    });

    document.addEventListener('click', function (e) {
      if (!explainModeOn) return;
      var target = e.target.closest('[data-explainable]');
      if (!target) return;
      e.preventDefault();
      e.stopPropagation();
      var ctx = collectContext(target, e);
      try {
        window.parent.postMessage({ type: 'mygov:explain:ctx', ctx: ctx }, window.location.origin);
      } catch (err) {}
    }, true);
  }

  function updateLevelBar() {
    document.querySelectorAll('.explain-level-btn').forEach(function (b) {
      b.classList.toggle('active', parseInt(b.dataset.level, 10) === currentLevel);
    });
  }

  /* ── Toggle explain mode ────────────────────────────────── */
  function toggleMode() {
    explainModeOn = !explainModeOn;
    var btn = document.getElementById('explain-mode-btn');
    if (explainModeOn) {
      document.body.classList.add('explain-mode-on');
      btn.classList.add('active');
      btn.textContent = '✕ Exit Explain Mode';
      btn.setAttribute('aria-pressed', 'true');
      try {
        document.dispatchEvent(new CustomEvent('mygov:explain-mode', { detail: { on: true } }));
      } catch (e) {}
      // Propagate to same-origin source iframe if present.
      try {
        var sf = document.getElementById('source-frame');
        if (sf && sf.contentWindow) {
          sf.contentWindow.postMessage({ type: 'mygov:explain-mode', on: true }, window.location.origin);
        }
      } catch (e) {}
    } else {
      document.body.classList.remove('explain-mode-on');
      btn.classList.remove('active');
      btn.textContent = '💡 Explain Mode';
      btn.setAttribute('aria-pressed', 'false');
      closeDrawer();
      try {
        document.dispatchEvent(new CustomEvent('mygov:explain-mode', { detail: { on: false } }));
      } catch (e) {}
      try {
        var sf2 = document.getElementById('source-frame');
        if (sf2 && sf2.contentWindow) {
          sf2.contentWindow.postMessage({ type: 'mygov:explain-mode', on: false }, window.location.origin);
        }
      } catch (e) {}
    }
  }

  /* ── Click capture ──────────────────────────────────────── */
  document.addEventListener('click', function (e) {
    if (!explainModeOn) return;

    // Don't intercept clicks inside the drawer itself
    if (e.target.closest('#explain-drawer') || e.target.closest('#explain-mode-btn')) return;

    var target = e.target.closest('[data-explainable]');

    if (!target) {
      var hint = document.getElementById('explain-mode-hint');
      if (hint) {
        hint.textContent = 'Click highlighted text (headings or a division row).';
        hint.style.color = '#bae6fd';
        setTimeout(function () {
          hint.textContent = 'Explain Mode ON — click highlighted headings or division rows.';
          hint.style.color = '';
        }, 2000);
      }
      return;
    }

    e.preventDefault();
    e.stopPropagation();

    var ctx = collectContext(target, e);
    lastExplainContext = ctx;
    lastCtxKey = makeCtxKey(ctx);
    openDrawerWithLoading(ctx.target_text);

    var cacheKey = lastCtxKey + ':' + currentLevel;
    if (clientCache[cacheKey]) {
      renderExplainResponse(clientCache[cacheKey]);
    } else {
      callExplainAPI(ctx, null);
    }
  }, true);

  // Accept explain-context messages from same-origin iframes (e.g. /publicwhip)
  // so the parent drawer can explain source-pane clicks.
  window.addEventListener('message', function (event) {
    try {
      if (event.origin !== window.location.origin) return;
      if (!event.data || event.data.type !== 'mygov:explain:ctx' || !event.data.ctx) return;
      if (!explainModeOn) return;
      var ctx = event.data.ctx;
      lastExplainContext = ctx;
      lastCtxKey = makeCtxKey(ctx);
      openDrawerWithLoading(ctx.target_text || '');
      var cacheKey = lastCtxKey + ':' + currentLevel;
      if (clientCache[cacheKey]) {
        renderExplainResponse(clientCache[cacheKey]);
      } else {
        callExplainAPI(ctx, null);
      }
    } catch (e) {}
  });

  /* ── DOM context collection ─────────────────────────────── */
  function collectContext(el, e) {
    var meta = {};
    if (el.dataset.explainType)  meta.explain_type  = el.dataset.explainType;
    if (el.dataset.memberId)     meta.member_id     = parseInt(el.dataset.memberId, 10);
    if (el.dataset.divisionId)   meta.division_id   = parseInt(el.dataset.divisionId, 10);
    if (el.dataset.issue)        meta.issue         = el.dataset.issue;
    if (el.dataset.variant)      meta.variant       = el.dataset.variant;
    if (el.dataset.sourceUrl)    meta.source_url    = el.dataset.sourceUrl;

    try {
      if (window.parent === window && typeof window.__YOURGOV_EXPLAIN_STATE__ === 'function') {
        meta.yourgov_state = window.__YOURGOV_EXPLAIN_STATE__();
      }
    } catch (_) {}

    var sourceLinks = [];
    var card = el.closest('.spotlight-card, .vote-row, .issue-vote-row, .variant-card, .card') || el;
    card.querySelectorAll('a[href]').forEach(function (a) {
      var href = a.href;
      if (href && !href.startsWith('mailto') && !sourceLinks.includes(href)) {
        sourceLinks.push(href);
      }
    });

    var surroundEl = el.closest('.spotlight-card, .vote-row, .issue-vote-row, .variant-card, .card, .profile-header') || el;
    var surroundingText = (surroundEl.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 400);

    return {
      url: window.location.href,
      route: window.location.pathname,
      target_text: (el.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 300),
      surrounding_text: surroundingText,
      source_links: sourceLinks.slice(0, 5),
      metadata: meta,
    };
  }

  /* ── Drawer render ──────────────────────────────────────── */
  function openDrawerWithLoading(targetText) {
    var body = document.getElementById('explain-drawer-body');
    body.innerHTML =
      '<div class="explain-section">' +
        '<div class="explain-section-label">You clicked</div>' +
        '<div class="explain-clicked-text">' + escHtml(targetText.slice(0, 160)) + '</div>' +
      '</div>' +
      '<div class="explain-section">' +
        '<div class="explain-section-label">What this means</div>' +
        '<div class="explain-section-body loading" id="ed-meaning">Loading…</div>' +
      '</div>' +
      '<div class="explain-section">' +
        '<div class="explain-section-label">What the source supports</div>' +
        '<div class="explain-section-body loading" id="ed-source">Loading…</div>' +
      '</div>' +
      '<div class="explain-section">' +
        '<div class="explain-section-label">What this does not prove</div>' +
        '<div class="explain-section-body loading" id="ed-dnp">Loading…</div>' +
      '</div>' +
      '<div class="explain-section" id="ed-followup-section" style="display:none">' +
        '<div class="explain-section-label">Suggested follow-ups</div>' +
        '<div class="explain-followup-chips" id="ed-chips"></div>' +
      '</div>';

    document.getElementById('explain-followup-input').value = '';
    updateLevelBar();
    openDrawer();
  }

  function setDrawerLoading() {
    ['ed-meaning', 'ed-source', 'ed-dnp'].forEach(function (id) {
      var el = document.getElementById(id);
      if (el) {
        el.textContent = 'Loading…';
        el.classList.add('loading');
        el.classList.remove('muted');
      }
    });
    var fup = document.getElementById('ed-followup-section');
    if (fup) fup.style.display = 'none';
  }

  function renderExplainResponse(data) {
    var meaning = document.getElementById('ed-meaning');
    var source  = document.getElementById('ed-source');
    var dnp     = document.getElementById('ed-dnp');
    var fupSec  = document.getElementById('ed-followup-section');
    var chips   = document.getElementById('ed-chips');
    if (!meaning) return;

    if (data.error) {
      meaning.classList.remove('loading');
      meaning.textContent = 'Could not load explanation: ' + data.error;
      source.classList.remove('loading');
      source.textContent = '';
      dnp.classList.remove('loading');
      dnp.textContent = '';
      return;
    }

    meaning.classList.remove('loading');
    meaning.textContent = data.meaning || '';
    source.classList.remove('loading');
    source.textContent = data.source_support || '';
    dnp.classList.remove('loading');
    dnp.classList.add('muted');
    dnp.textContent = data.does_not_prove || '';

    // Store in client cache
    if (lastCtxKey) {
      clientCache[lastCtxKey + ':' + currentLevel] = data;
    }

    if (data.followups && data.followups.length) {
      fupSec.style.display = '';
      chips.innerHTML = '';
      data.followups.forEach(function (q) {
        var chip = document.createElement('button');
        chip.className = 'explain-followup-chip';
        chip.textContent = q;
        chip.addEventListener('click', function () {
          document.getElementById('explain-followup-input').value = q;
          sendFollowup();
        });
        chips.appendChild(chip);
      });
    }
  }

  function openDrawer() {
    document.getElementById('explain-drawer').classList.add('open');
    document.getElementById('explain-drawer-backdrop').classList.add('visible');
  }

  function closeDrawer() {
    document.getElementById('explain-drawer').classList.remove('open');
    document.getElementById('explain-drawer-backdrop').classList.remove('visible');
  }

  /* ── API calls ──────────────────────────────────────────── */
  function callExplainAPI(ctx, followupQuestion) {
    var payload = Object.assign({}, ctx, { level: currentLevel });
    if (followupQuestion) {
      payload.followup_question = followupQuestion;
      payload.prior_explanation = lastPriorExplanation;
    }

    fetch('/api/explain-selection', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.meaning) {
          lastPriorExplanation = data.meaning;
        }
        renderExplainResponse(data);
      })
      .catch(function (err) {
        renderExplainResponse({ error: 'Network error — ' + err.message });
      });
  }

  function sendFollowup() {
    var input = document.getElementById('explain-followup-input');
    var q = (input.value || '').trim();
    if (!q || !lastExplainContext) return;
    input.value = '';

    var body = document.getElementById('explain-drawer-body');
    var block = document.createElement('div');
    block.className = 'explain-section';
    block.innerHTML =
      '<div class="explain-section-label">Follow-up</div>' +
      '<div class="explain-clicked-text">' + escHtml(q) + '</div>' +
      '<div class="explain-section-body loading" id="fup-response">Loading…</div>';
    body.appendChild(block);
    body.scrollTop = body.scrollHeight;

    fetch('/api/explain-selection', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(Object.assign({}, lastExplainContext, {
        followup_question: q,
        prior_explanation: lastPriorExplanation,
        level: currentLevel,
      })),
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var el = document.getElementById('fup-response');
        if (!el) return;
        el.classList.remove('loading');
        if (data.error) {
          el.textContent = data.error;
        } else {
          el.textContent = data.meaning || '';
          if (data.meaning) lastPriorExplanation = data.meaning;
        }
        body.scrollTop = body.scrollHeight;
      })
      .catch(function (err) {
        var el = document.getElementById('fup-response');
        if (el) { el.classList.remove('loading'); el.textContent = 'Network error.'; }
      });
  }

  /* ── Init ───────────────────────────────────────────────── */
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', injectUI);
  } else {
    injectUI();
  }
})();
