(function () {
  'use strict';

  /* ── Source config ──────────────────────────────────────── */
  var SOURCES = {
    mygov: {
      label: 'YourGov',
      url: '/',
      can_embed: true,
      fallback_reason: null,
      source_note: 'YourGov — Parliament public records.'
    },
    twfy: {
      label: 'TheyWorkForYou',
      url: 'https://www.theyworkforyou.com',
      can_embed: true,
      fallback_reason: null,
      source_note: 'Independent parliamentary monitoring service by mySociety.'
    },
    wtt: {
      label: 'WriteToThem',
      url: 'https://www.writetothem.com/who?pc=n15+4pg',
      can_embed: true,
      fallback_reason: null,
      source_note: 'Contact your elected representatives directly.'
    },
    publicwhip: {
      label: 'PublicWhip',
      url: '/publicwhip',
      can_embed: true,
      fallback_reason: null,
      source_note: 'Historic parliamentary voting record — search MPs and divisions by name or topic.'
    }
  };

  /* ── State ─────────────────────────────────────────────── */
  var currentSource = 'mygov';
  var iframeLoadTimer = null;
  var LOAD_TIMEOUT_MS = 45000;

  /* ── Elements ───────────────────────────────────────────── */
  var sourceIframe    = document.getElementById('source-iframe');
  var sourceLoading   = document.getElementById('source-loading');
  var sourceFallback  = document.getElementById('source-fallback');
  var loadingLabel    = document.getElementById('source-loading-label');
  var fallbackTitle   = document.getElementById('fallback-title');
  var fallbackReason  = document.getElementById('fallback-reason');
  var fallbackNote    = document.getElementById('fallback-note');
  var fallbackOpen    = document.getElementById('fallback-open');
  var mpStrip         = document.getElementById('mp-selected-strip');
  var stripName       = document.getElementById('strip-name');
  var stripConst      = document.getElementById('strip-constituency');
  var stripLink       = document.getElementById('strip-link');

  /* ── Source switching ───────────────────────────────────── */
  function loadSource(key) {
    var src = SOURCES[key];
    if (!src) return;
    currentSource = key;

    // Update selector buttons
    document.querySelectorAll('.source-btn').forEach(function (btn) {
      btn.classList.toggle('active', btn.dataset.source === key);
    });

    // Update URL param without reload
    var url = new URL(window.location.href);
    url.searchParams.set('source', key);
    history.replaceState(null, '', url.toString());

    clearLoadTimer();
    hideAllPanels();

    if (!src.can_embed) {
      showFallback(src);
      return;
    }

    showLoading(src.label);
    sourceIframe.src = src.url;
    iframeLoadTimer = setTimeout(function () {
      showFallback(src, true);
    }, LOAD_TIMEOUT_MS);
  }

  function hideAllPanels() {
    sourceIframe.style.display = 'none';
    sourceLoading.classList.remove('visible');
    sourceFallback.classList.remove('visible');
  }

  function showLoading(label) {
    loadingLabel.textContent = 'Loading ' + label + '…';
    sourceLoading.classList.add('visible');
    sourceIframe.style.display = 'block';
    sourceFallback.classList.remove('visible');
  }

  function showIframe() {
    clearLoadTimer();
    sourceLoading.classList.remove('visible');
    sourceFallback.classList.remove('visible');
    sourceIframe.style.display = 'block';
  }

  function showFallback(src, timedOut) {
    clearLoadTimer();
    sourceLoading.classList.remove('visible');
    sourceIframe.style.display = 'none';
    sourceFallback.classList.add('visible');
    var src2 = SOURCES[currentSource] || src;
    fallbackTitle.textContent = timedOut
      ? src2.label + ' did not load'
      : src2.label + ' cannot be embedded';
    fallbackReason.textContent = timedOut
      ? 'The page took too long to load. It may block embedding, or be temporarily unavailable.'
      : (src2.fallback_reason || 'This site cannot be shown here.');
    fallbackNote.textContent = src2.source_note || '';
    fallbackOpen.href = src2.url;
    fallbackOpen.textContent = 'Open ' + src2.label + ' in new tab ↗';
  }

  function clearLoadTimer() {
    if (iframeLoadTimer) { clearTimeout(iframeLoadTimer); iframeLoadTimer = null; }
  }

  /* ── iframe load event ──────────────────────────────────── */
  sourceIframe.addEventListener('load', function () {
    if (currentSource && SOURCES[currentSource] && SOURCES[currentSource].can_embed) {
      showIframe();
    }
  });

  /* ── Source selector clicks ─────────────────────────────── */
  document.getElementById('source-selector').addEventListener('click', function (e) {
    var btn = e.target.closest('.source-btn');
    if (!btn) return;
    loadSource(btn.dataset.source);
  });

  /* ── Map mode controls ──────────────────────────────────── */
  document.getElementById('map-mode-bar').addEventListener('click', function (e) {
    var btn = e.target.closest('.mode-btn');
    if (!btn) return;
    document.querySelectorAll('.mode-btn').forEach(function (b) {
      b.classList.remove('active');
    });
    btn.classList.add('active');
    var mode = btn.dataset.mode;
    var mapIframe = document.getElementById('map-iframe');
    if (mapIframe && mapIframe.contentWindow) {
      mapIframe.contentWindow.postMessage({ type: 'mygov:map:setMode', mode: mode }, window.location.origin);
    }
  });

  /* ── Constituency selection from map iframe ─────────────── */
  window.addEventListener('message', function (e) {
    if (e.origin !== window.location.origin || !e.data) return;
    if (e.data.type !== 'mygov:constituency:selected' && e.data.type !== 'mygov:constituency:sel') return;
    var detail = e.data.detail || {};
    var mp = detail.mp || {};
    var selectedConstituency = detail.constituency || {};
    var name = detail.mpName || mp.name || detail.name || '';
    var constituency = detail.constituencyName || selectedConstituency.name || '';
    var memberId = detail.memberId || mp.id || detail.id || '';

    if (name || constituency) {
      stripName.textContent = name || constituency;
      stripConst.textContent = constituency && name ? constituency : '';
      if (memberId) {
        stripLink.href = '/mp/' + memberId;
      } else {
        stripLink.href = '/';
      }
      mpStrip.classList.add('visible');

      // Update explain-mode context for the strip
      mpStrip.setAttribute('data-explain-context',
        'You selected ' + (constituency || 'a constituency') +
        (name ? ', represented by ' + name : '') +
        '. The public record for this MP is available via the View MP link.'
      );
    }
  });

  /* ── Init: read source from query param ─────────────────── */
  function init() {
    var params = new URLSearchParams(window.location.search);
    var src = params.get('source') || 'mygov';
    if (!SOURCES[src]) src = 'mygov';
    loadSource(src);
  }

  init();
})();
