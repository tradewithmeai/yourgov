(function () {
  'use strict';

  // First-party, privacy-first site metrics. Fire-and-forget beacon; never
  // blocks. Sends only the event name, the path (no query string), small
  // scalar props, and (on pageview) document.referrer — the server reduces that
  // to a host and stores no cookies/IP/per-user id. See /api/telemetry.
  function ygMetric(event, props) {
    try {
      var body = Object.assign(
        { event: event, path: location.pathname },
        props || {}
      );
      var json = JSON.stringify(body);
      if (navigator.sendBeacon) {
        navigator.sendBeacon('/api/telemetry', new Blob([json], { type: 'application/json' }));
      } else {
        fetch('/api/telemetry', { method: 'POST', headers: { 'Content-Type': 'application/json' },
                                  body: json, keepalive: true }).catch(function () {});
      }
    } catch (e) { /* metrics must never break the page */ }
  }

  var PUBLICWHIP_URL = '/publicwhip';
  var WRITETOTHEM_URL = 'https://www.writetothem.com/';
  var PUBLICWHIP_STATUS = 'Native PublicWhip source lens - full click-to-visualise enabled.';
  var visualiseActive = false;
  var currentMapData = {};
  // Track the source of currentMapData so vote-split can know whether the
  // cached data is real vote data (from a clicked division) or stale data
  // from a previous wedge click (party / gender / rebel split). Without this
  // the Vote wedge would re-paint the map with whatever data was last
  // loaded, regardless of source.
  var currentMapDataKind = null;
  var selectedDivisionId = null;
  var selectedDivisionPayload = null;
  var selectedMapMode = 'vote-split';
  var selectedSourceView = 'yourgov-summary';
  var mapPayloadRequestSeq = 0;

  // ── Stub helpers for elements that no longer exist after the
  //    minimalist-launch UI cleanup. They keep legacy code paths
  //    safe without rewriting every call site.
  function _noopBtn() {
    return {
      classList: { toggle: function () {}, add: function () {}, remove: function () {}, contains: function () { return false; } },
      setAttribute: function () {},
      removeAttribute: function () {},
      getAttribute: function () { return null; },
      addEventListener: function () {},
      textContent: '',
      innerHTML: '',
      hidden: true,
      style: {}
    };
  }

  var sourceFrame = document.getElementById('source-frame');
  var mapFrame = document.getElementById('map-frame');
  var tabs = document.getElementById('source-tabs') || _noopBtn();
  var status = document.getElementById('source-status') || _noopBtn();
  var visualiseToggle = document.getElementById('visualise-toggle') || _noopBtn();
  var sourceUrl = document.getElementById('source-url') || _noopBtn();
  var parseUrl = document.getElementById('parse-url') || _noopBtn();
  var selectionCard = document.getElementById('selection-card');
  var selectionTitle = document.getElementById('selection-title');
  var selectionMeta = document.getElementById('selection-meta');
  var selectionCaveat = document.getElementById('selection-caveat');
  var selectionSource = document.getElementById('selection-source');
  var visualiseInstruction = document.getElementById('visualise-instruction') || _noopBtn();
  var legendEl = document.getElementById('map-legend');
  var sourceLensList = document.getElementById('source-lens-list');
  var mpInfoCard = document.getElementById('mp-info-card');
  var sourceDivisions = null;
  var sourceViewSelect = document.getElementById('source-view-select');
  var sourceSummary = document.getElementById('source-summary-text');
  var sourceLinksList = document.getElementById('source-links-list');
  var yourgovSummaryPanel = document.getElementById('yourgov-summary-panel');
  var sourceFramePanel = document.getElementById('source-frame-panel');
  var divisionSummary = document.getElementById('division-summary');
  var divisionSummaryBody = document.getElementById('division-summary-body');
  var divisionSummaryClose = document.getElementById('division-summary-close');
  var pendingMapPayload = null;
  var pendingMapTimer = null;
  var mapReady = false;
  var pendingVisPayload = null;
  var visRetryTimer = null;
  var visRetryCount = 0;
  var lastDivisionLabel = '';
  var lastSourceMP = null;
  var selectedMP = null;
  var focusedResultIndex = -1;
  var searchDebounce = null;

  // Search state
  var mpSearchForm = document.getElementById('mp-search-form');
  var mpSearchInput = document.getElementById('mp-search-input');
  var searchResultsEl = document.getElementById('search-results');
  var selectionProfile = document.getElementById('selection-profile');
  // Right pane navigation controls (same-origin iframe only).
  var sourceBackBtn = document.getElementById('source-back');
  var sourceForwardBtn = document.getElementById('source-forward');
  var sourceRefreshBtn = document.getElementById('source-refresh');
  var sourceNavStack = [];
  var sourceNavIndex = -1;
  var sourceNavSuppressNextRecord = false;
  var pwNavHome = document.getElementById('pw-nav-home');
  var pwNavDivisions = document.getElementById('pw-nav-divisions');
  var pwNavMPs = document.getElementById('pw-nav-mps');
  var pwNavPolicies = document.getElementById('pw-nav-policies');
  var topicVoteSplit = document.getElementById('topic-vote-split');
  var topicPartySplit = document.getElementById('topic-party-split');
  var topicGenderSplit = document.getElementById('topic-gender-split');
  var topicRebelRate = document.getElementById('topic-rebel-rate');

  function setStatus(message, tone) {
    status.textContent = message;
    status.classList.toggle('ok', tone === 'ok');
    status.classList.toggle('warn', tone === 'warn');
  }

  function nextMapPayloadRequest() {
    mapPayloadRequestSeq += 1;
    return mapPayloadRequestSeq;
  }

  function isCurrentMapPayloadRequest(token) {
    return token === mapPayloadRequestSeq;
  }

  function normaliseDivisionId(value) {
    if (value === null || value === undefined || value === '') return null;
    return String(value);
  }

  function getYourGovExplainState() {
    return {
      product: 'YourGov',
      selected_mp: selectedMP,
      selected_division: selectedDivisionPayload && selectedDivisionPayload.division ? selectedDivisionPayload.division : null,
      active_map_mode: selectedMapMode,
      map_status: status && status.textContent ? status.textContent : '',
      map_caveat: selectionCaveat && selectionCaveat.textContent ? selectionCaveat.textContent : ''
    };
  }

  window.__YOURGOV_EXPLAIN_STATE__ = getYourGovExplainState;

  function ensurePublicWhipLoaded() {
    if (!sourceFrame) return;
    if (!sourceFrame.getAttribute('src')) sourceFrame.setAttribute('src', PUBLICWHIP_URL);
  }

  function openInSourcePane(url) {
    if (!url || !sourceFrame) return;
    if (sourceViewSelect) sourceViewSelect.value = 'publicwhip-record';
    selectedSourceView = 'publicwhip-record';
    if (yourgovSummaryPanel) yourgovSummaryPanel.hidden = true;
    if (sourceFramePanel) sourceFramePanel.hidden = false;
    sourceFrame.src = url;
  }

  // Explain Mode is parent-document only. When enabled, force the right pane into the
  // parent-rendered Source Lens list so humans have obvious clickable targets.
  document.addEventListener('yourgov:explain-mode', function (e) {
    var on = !!(e && e.detail && e.detail.on);
    if (on) {
      // Do not force switching the right pane: Explain Mode supports same-origin iframe
      // via postMessage bridge (see explain-mode.js). Keep current source selection.
      setStatus('Explain Mode ON -- click highlighted headings or source records.', 'ok');
    } else {
      setStatus(PUBLICWHIP_STATUS, 'ok');
    }
  });

  function updateInstruction() {
    if (!visualiseInstruction) return;
    visualiseInstruction.textContent = 'Click a division row to colour the map';
  }

  async function loadSourceDivisions() {
    if (sourceDivisions !== null) {
      renderDivisionRows(sourceDivisions);
      return;
    }
    if (!sourceLensList) return;
    sourceLensList.innerHTML = '<p class="source-lens-loading">Loading vote records…</p>';
    try {
      var resp = await fetch('/api/lens/source-divisions?limit=50');
      var data = await resp.json();
      if (!resp.ok || !data.ok) throw new Error(data.error || 'Could not load divisions');
      sourceDivisions = data.divisions;
      renderDivisionRows(sourceDivisions);
    } catch (err) {
      while (sourceLensList.firstChild) sourceLensList.removeChild(sourceLensList.firstChild);
      var warn = document.createElement('p');
      warn.className = 'source-lens-loading warn';
      warn.textContent = 'Could not load vote records: ' + err.message;
      sourceLensList.appendChild(warn);
    }
  }

  function voteClass(vote) {
    if (vote === 'Aye') return 'aye';
    if (vote === 'No') return 'no';
    return 'unknown';
  }

  function appendTextNode(parent, tagName, className, text) {
    var node = document.createElement(tagName);
    if (className) node.className = className;
    node.textContent = text;
    parent.appendChild(node);
    return node;
  }

  function createDivisionRow(d, mp) {
    var row = document.createElement('div');
    row.className = 'division-row';
    row.dataset.divisionId = String(d.division_id);
    // Carry the division facts on the row so the YourGov summary can render on
    // double-click without an extra fetch.
    row.dataset.title = d.title || 'Untitled division';
    row.dataset.date = d.date || '';
    if (d.vote) row.dataset.vote = d.vote;
    row.dataset.ayeCount = String(d.aye_count || 0);
    row.dataset.noCount = String(d.no_count || 0);
    if (mp && mp.member_id) row.dataset.memberId = String(mp.member_id);
    row.dataset.explainable = 'true';
    row.dataset.explainType = mp ? 'vote' : 'division-row';
    row.setAttribute('role', 'button');
    row.setAttribute('tabindex', '0');
    row.setAttribute('aria-label', (d.title || 'Division') + '. Click to map. Double click for summary.');

    appendTextNode(row, 'div', 'division-row-title', d.title || 'Untitled division');

    var meta = document.createElement('div');
    meta.className = 'division-row-meta';
    appendTextNode(meta, 'span', 'division-row-date', d.date || '');
    if (d.vote) {
      appendTextNode(meta, 'span', 'division-row-vote ' + voteClass(d.vote), 'Voted ' + d.vote);
    }
    appendTextNode(meta, 'span', 'division-row-aye', 'Aye ' + (d.aye_count || 0));
    appendTextNode(meta, 'span', 'division-row-no', 'No ' + (d.no_count || 0));
    row.appendChild(meta);

    var actions = document.createElement('div');
    actions.className = 'division-row-actions';
    appendTextNode(actions, 'span', 'division-row-action', 'Click to map');
    appendTextNode(actions, 'span', 'division-row-action', 'Double click for summary');
    var summary = document.createElement('a');
    summary.className = 'division-row-source';
    summary.href = '#';
    summary.textContent = 'Open summary';
    actions.appendChild(summary);
    row.appendChild(actions);

    return row;
  }

  function renderDivisionRows(divisions) {
    if (!sourceLensList) return;
    while (sourceLensList.firstChild) sourceLensList.removeChild(sourceLensList.firstChild);
    if (!divisions || !divisions.length) {
      var empty = document.createElement('p');
      empty.className = 'source-lens-loading';
      empty.textContent = 'No division records found.';
      sourceLensList.appendChild(empty);
      return;
    }
    var frag = document.createDocumentFragment();
    divisions.forEach(function (d) {
      frag.appendChild(createDivisionRow(d, null));
    });
    sourceLensList.appendChild(frag);
  }

  // Party → identity-dot colour (matches the map fills + the party legend).
  function partyDotColour(party) {
    var p = (party || '').toLowerCase();
    if (p.indexOf('conservative') === 0 || p === 'con') return '#1d4ed8';
    if (p.indexOf('labour') === 0) return '#dc2626';
    if (p.indexOf('liberal democrat') === 0 || p === 'lib dem') return '#f59e0b';
    if (p.indexOf('reform') === 0) return '#12b6cf';
    if (p.indexOf('green') === 0) return '#16a34a';
    if (p.indexOf('scottish national') === 0 || p === 'snp') return '#fff95d';
    if (p.indexOf('plaid') === 0) return '#00a86b';
    if (p.indexOf('democratic unionist') === 0 || p === 'dup') return '#d46a4c';
    return '#94a3b8';
  }

  function hideMPInfoCard() {
    if (!mpInfoCard) return;
    mpInfoCard.hidden = true;
    while (mpInfoCard.firstChild) mpInfoCard.removeChild(mpInfoCard.firstChild);
    delete mpInfoCard.dataset.explainable;
  }

  // Frozen MP info card at the top of the panel: identity + the Contact action
  // (the end of the find-your-MP-then-email-them flow). The card is the Explain
  // Mode hook for the MP (data-explainable). The contact link goes to WriteToThem
  // by postcode when we arrived via a postcode (a direct "email your MP" flow),
  // otherwise to the MP's official UK Parliament contact page (always available).
  function renderMPInfoCard(mp, totalVotes) {
    if (!mpInfoCard) return;
    mp = mp || {};
    while (mpInfoCard.firstChild) mpInfoCard.removeChild(mpInfoCard.firstChild);
    mpInfoCard.hidden = false;
    mpInfoCard.dataset.explainable = 'true';
    mpInfoCard.dataset.explainType = 'mp';
    if (mp.member_id) mpInfoCard.dataset.memberId = String(mp.member_id);

    appendTextNode(mpInfoCard, 'p', 'eyebrow', 'Your MP');
    appendTextNode(mpInfoCard, 'h2', 'mp-info-name', mp.name || 'this MP');

    var meta = document.createElement('p');
    meta.className = 'mp-info-meta';
    var dot = document.createElement('span');
    dot.className = 'mp-info-dot';
    dot.style.background = partyDotColour(mp.party);
    dot.setAttribute('aria-hidden', 'true');
    meta.appendChild(dot);
    meta.appendChild(document.createTextNode(
      (mp.party || 'Unknown party') + ' · ' + (mp.constituency || 'constituency unknown')
    ));
    mpInfoCard.appendChild(meta);

    if (typeof totalVotes === 'number') {
      appendTextNode(mpInfoCard, 'p', 'mp-info-votes',
        totalVotes.toLocaleString() + ' recorded vote' + (totalVotes === 1 ? '' : 's') + ' in the YourGov dataset');
    }

    var contact = document.createElement('a');
    contact.className = 'mp-info-contact';
    contact.target = '_blank';
    contact.rel = 'noopener noreferrer';
    if (mp.postcode) {
      contact.href = 'https://www.writetothem.com/who?pc=' + encodeURIComponent(mp.postcode);
      contact.textContent = 'Email ' + (mp.name || 'your MP');
      contact.setAttribute('aria-label', 'Email ' + (mp.name || 'your MP') + ' via WriteToThem');
    } else if (mp.member_id) {
      contact.href = 'https://members.parliament.uk/member/' + encodeURIComponent(mp.member_id) + '/contact';
      contact.textContent = 'Contact ' + (mp.name || 'your MP');
      contact.setAttribute('aria-label', 'Contact ' + (mp.name || 'your MP') + ' — opens their UK Parliament contact page');
    }
    // Keep Explain Mode from intercepting the contact click.
    contact.addEventListener('click', function (e) {
      e.stopPropagation();
      ygMetric('contact_click', { via: mp.postcode ? 'writetothem' : 'parliament' });
    });
    if (contact.href) mpInfoCard.appendChild(contact);
    ygMetric('mp_view', { party: mp.party || '' });
  }

  function renderMPSearchPrompt() {
    if (!sourceLensList) return;
    hideMPInfoCard();
    while (sourceLensList.firstChild) sourceLensList.removeChild(sourceLensList.firstChild);
    // First-load introduction, shown until an MP is selected. Static, trusted
    // markup (no user data) — explains what YourGov is, how to find an MP, the
    // Explain function, the agent-friendly repo, and the feedback route.
    var intro = document.createElement('div');
    intro.className = 'yg-intro';
    intro.innerHTML = [
      '<img class="yg-intro-logo" src="/static/img/yourgov-logo.svg" alt="YourGov" width="184" height="49">',
      '<p class="yg-intro-lead">See how your MP actually voted — by constituency, in plain English.</p>',
      '<p class="yg-intro-text">YourGov maps every recorded House of Commons vote onto the UK constituency map. Find your MP, read their full voting record, and open any vote for a grounded, plain-English explanation.</p>',
      '<button type="button" id="yg-intro-tour" class="yg-intro-tour">Take a quick tour</button>',
      '<ul class="yg-intro-cards">',
        '<li class="yg-intro-card">',
          '<span class="yg-intro-k">Find your MP</span>',
          '<span class="yg-intro-v">Use the search — the &ldquo;S&rdquo; at the centre of the map — by postcode, constituency, or name.</span>',
        '</li>',
        '<li class="yg-intro-card">',
          '<span class="yg-intro-k">Explain Mode</span>',
          '<span class="yg-intro-v">Turn on <strong>Explain</strong>, then click any vote, MP or division for a plain-English explanation grounded in the real record.</span>',
        '</li>',
        '<li>',
          '<a class="yg-intro-card yg-intro-link" href="https://github.com/tradewithmeai/yourgov" target="_blank" rel="noopener noreferrer">',
            '<span class="yg-intro-k">Built to be agent-friendly →</span>',
            '<span class="yg-intro-v">YourGov is an open, agent-readable codebase — AI agents can explore, test and extend it. Educational resources are on the way.</span>',
          '</a>',
        '</li>',
        '<li>',
          '<a class="yg-intro-card yg-intro-link" href="/feedback">',
            '<span class="yg-intro-k">Help shape it →</span>',
            '<span class="yg-intro-v">Send a suggestion on the feedback page. Ideas are reviewed and turned into agent tasks that build the changes.</span>',
          '</a>',
        '</li>',
        '<li>',
          '<a class="yg-intro-card yg-intro-link" href="/accessibility">',
            '<span class="yg-intro-k">Accessibility →</span>',
            '<span class="yg-intro-v">Our WCAG 2.2 AA status — and tell us what you need to use YourGov.</span>',
          '</a>',
        '</li>',
      '</ul>'
    ].join('');
    sourceLensList.appendChild(intro);
    // Opt-in tour: intro leads, the guided tour starts only when asked for.
    var tourBtn = document.getElementById('yg-intro-tour');
    if (tourBtn) {
      tourBtn.addEventListener('click', function () {
        if (typeof window.startYourGovTour === 'function') window.startYourGovTour();
      });
    }
  }

  function renderMPVotingRecord(payload) {
    if (!sourceLensList) return;
    while (sourceLensList.firstChild) sourceLensList.removeChild(sourceLensList.firstChild);

    var mp = (payload && payload.mp) || selectedMP || {};
    selectedMP = mp;
    lastSourceMP = mp;

    var divisions = (payload && payload.divisions) || [];
    // total_votes is the authoritative FULL count from the API. Every figure on
    // screen is derived from the complete record, never the displayed subset —
    // the list is merely paged for readability.
    var totalVotes = (payload && typeof payload.total_votes === 'number') ? payload.total_votes : divisions.length;
    var INITIAL_VISIBLE = 50;

    // MP identity + the Contact action go in the frozen card pinned above the
    // scrolling record. The list below holds only the voting record itself.
    renderMPInfoCard(mp, totalVotes);

    var header = document.createElement('div');
    header.className = 'mp-record-header';
    appendTextNode(header, 'p', 'caveat', 'Recorded House of Commons divisions, most recent first.');
    var countEl = appendTextNode(header, 'p', 'mp-record-count', '');
    sourceLensList.appendChild(header);

    if (!divisions.length) {
      var empty = document.createElement('p');
      empty.className = 'source-lens-loading';
      empty.textContent =
        (payload && payload.record_status && payload.record_status.message) ||
        'No House of Commons divisions are recorded for this MP in the YourGov dataset yet.';
      sourceLensList.appendChild(empty);
      return;
    }

    // Show the 50 most recent; an expand control reveals older votes in batches.
    var rowsWrap = document.createElement('div');
    rowsWrap.className = 'division-rows';
    sourceLensList.appendChild(rowsWrap);

    var expandWrap = document.createElement('div');
    expandWrap.className = 'division-expand';
    var expandBtn = document.createElement('button');
    expandBtn.type = 'button';
    expandBtn.className = 'division-expand-btn';
    expandWrap.appendChild(expandBtn);
    sourceLensList.appendChild(expandWrap);

    var rendered = 0;
    function updateCount() {
      if (rendered >= totalVotes) {
        countEl.textContent = 'Showing all ' + totalVotes + ' recorded vote' + (totalVotes === 1 ? '' : 's') + '.';
      } else {
        countEl.textContent = 'Showing ' + rendered + ' of ' + totalVotes + ' recorded votes.';
      }
    }
    function syncExpand() {
      var remaining = divisions.length - rendered;
      if (remaining <= 0) { expandWrap.hidden = true; return; }
      var next = Math.min(INITIAL_VISIBLE, remaining);
      expandBtn.textContent = 'Show ' + next + ' older vote' + (next === 1 ? '' : 's') + ' (' + remaining + ' more)';
      expandWrap.hidden = false;
    }
    function renderMore(count) {
      var frag = document.createDocumentFragment();
      var end = Math.min(rendered + count, divisions.length);
      for (var i = rendered; i < end; i += 1) {
        frag.appendChild(createDivisionRow(divisions[i], mp));
      }
      rowsWrap.appendChild(frag);
      rendered = end;
      updateCount();
      syncExpand();
    }
    expandBtn.addEventListener('click', function () { renderMore(INITIAL_VISIBLE); });

    renderMore(INITIAL_VISIBLE);
  }

  async function loadMPVotingRecord(mp) {
    if (!mp || !mp.id) return;
    // Carry the postcode (when we arrived via a postcode search) through to the
    // contact link so it can open a direct "email your MP" flow.
    var inputPostcode = mp.postcode || '';
    selectedMP = {
      member_id: parseInt(mp.id, 10),
      name: mp.name || '',
      party: mp.party || '',
      constituency: mp.constituency || ''
    };
    lastSourceMP = selectedMP;
    setStatus('Loading voting record for ' + selectedMP.name + '...', 'ok');
    var response = await fetch('/api/lens/mp/' + encodeURIComponent(selectedMP.member_id) + '/votes?limit=2000');
    var payload = await response.json();
    if (!response.ok || !payload.ok) throw new Error(payload.error || 'Could not load this MP voting record');
    selectedMP = payload.mp || {};
    if (inputPostcode) selectedMP.postcode = inputPostcode;
    payload.mp = selectedMP;
    lastSourceMP = selectedMP;
    renderMPVotingRecord(payload);
    setStatus('Voting record loaded. Click a division to colour the map.', 'ok');
  }


  function setVisualise(active) {
    visualiseActive = active;
    document.body.classList.toggle('visualise-active', active);
    visualiseToggle.classList.toggle('active', active);
    visualiseToggle.setAttribute('aria-pressed', active ? 'true' : 'false');
    visualiseToggle.textContent = active ? 'Visualise on' : 'Visualise';
    syncSourceCursor();
    updateSourceNavEnabled();
    if (active) {
      setStatus('Now click any division in the right panel to colour the map.', 'ok');
      if (selectionCard && selectionCard.classList.contains('idle')) {
        selectionTitle.textContent = 'Waiting for selection...';
        selectionMeta.textContent = 'Click a division row in the right panel.';
      }
    } else {
      setStatus(PUBLICWHIP_STATUS, 'ok');
    }
    updateInstruction();
  }

  function syncSourceCursor() {
    // Visualise is silently always-on now; never paint a crosshair into the
    // right-pane iframe. The crosshair previously signalled visualise mode
    // but reads as "Explain mode is on" to users now that Explain is the
    // only mode they can toggle. Explain Mode adds its own help cursor
    // on [data-explainable] elements when active.
    try {
      var doc = sourceFrame.contentDocument;
      if (!doc || !doc.body) return;
      doc.body.style.cursor = '';
    } catch (err) {
      // Cross-origin pages will throw here.
    }
  }

  function updateSourceNavEnabled() {
    var canAccess = false;
    try {
      canAccess = !!(sourceFrame && sourceFrame.contentWindow && sourceFrame.contentDocument);
    } catch (e) {
      canAccess = false;
    }
    var canBack = canAccess && sourceNavIndex > 0;
    var canForward = canAccess && sourceNavIndex >= 0 && sourceNavIndex < sourceNavStack.length - 1;
    if (sourceBackBtn) sourceBackBtn.disabled = !canBack;
    if (sourceForwardBtn) sourceForwardBtn.disabled = !canForward;
    if (sourceRefreshBtn) sourceRefreshBtn.disabled = !sourceFrame || !sourceFrame.contentWindow;
  }

  function sourceNavBack() {
    try {
      if (sourceNavIndex <= 0) return;
      sourceNavIndex--;
      sourceNavSuppressNextRecord = true;
      sourceFrame.src = sourceNavStack[sourceNavIndex];
      updateSourceNavEnabled();
    } catch (e) {}
  }

  function sourceNavForward() {
    try {
      if (sourceNavIndex < 0 || sourceNavIndex >= sourceNavStack.length - 1) return;
      sourceNavIndex++;
      sourceNavSuppressNextRecord = true;
      sourceFrame.src = sourceNavStack[sourceNavIndex];
      updateSourceNavEnabled();
    } catch (e) {}
  }

  function sourceNavRefresh() {
    try {
      if (!sourceFrame) return;
      if (sourceNavIndex >= 0 && sourceNavStack[sourceNavIndex]) {
        sourceNavSuppressNextRecord = true;
        sourceFrame.src = sourceNavStack[sourceNavIndex];
      } else if (sourceFrame.contentWindow) {
        sourceFrame.contentWindow.location.reload();
      }
    } catch (e) {}
  }

  // Source iframe load: re-evaluate nav button state.
  if (sourceFrame) {
    sourceFrame.addEventListener('load', function () {
      // Record the iframe URL so Back/Forward are confined to the right pane.
      try {
        if (sourceFrame.contentWindow && sourceFrame.contentWindow.location) {
          var href = sourceFrame.contentWindow.location.href;
          if (href) {
            if (sourceNavSuppressNextRecord) {
              sourceNavSuppressNextRecord = false;
            } else {
              if (sourceNavIndex >= 0 && sourceNavStack[sourceNavIndex] === href) {
                // no-op
              } else {
                sourceNavStack = sourceNavStack.slice(0, sourceNavIndex + 1);
                sourceNavStack.push(href);
                sourceNavIndex = sourceNavStack.length - 1;
              }
            }
          }
        }
      } catch (e) {}
      updateSourceNavEnabled();
    });
  }

  if (sourceBackBtn) sourceBackBtn.addEventListener('click', sourceNavBack);
  if (sourceForwardBtn) sourceForwardBtn.addEventListener('click', sourceNavForward);
  if (sourceRefreshBtn) sourceRefreshBtn.addEventListener('click', sourceNavRefresh);
  if (divisionSummaryClose) divisionSummaryClose.addEventListener('click', closeDivisionSummary);
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && divisionSummary && !divisionSummary.hidden) closeDivisionSummary();
  });

  // Parent-controlled site nav so users can always move around even if iframe header links feel unclear.
  function bindPwNav(btn, url) {
    if (!btn) return;
    btn.addEventListener('click', function () {
      openInSourcePane(url);
    });
  }
  bindPwNav(pwNavHome, '/publicwhip/divisions');
  bindPwNav(pwNavDivisions, '/publicwhip/divisions');
  bindPwNav(pwNavMPs, '/publicwhip/mps');
  bindPwNav(pwNavPolicies, '/publicwhip/policies');

  // Wedge → applyTopic delegation, driven by data-mode (decoupled from ID).
  // data-mode values match the wedge contract from the template:
  //   vote-split | party-split | gender-split | rebel-split
  // Mapped to the existing applyTopic keys to preserve the map_mode payload
  // sent to the iframe.
  var WEDGE_TO_TOPIC = {
    'vote-split': 'vote-split',
    'party-split': 'party-split',
    'gender-split': 'gender-split',
    'rebel-split': 'rebel-split'
  };
  // Colour-key data per wedge, in the order they appear around the quadrant arc.
  var WEDGE_KEYS = {
    'vote-split':   [{ c: '#16a34a', l: 'Aye'  }, { c: '#dc2626', l: 'No' }, { c: '#6b7280', l: 'Absent' }],
    'party-split':  [{ c: '#1d4ed8', l: 'Con' }, { c: '#dc2626', l: 'Lab' }, { c: '#f59e0b', l: 'LD' },
                     { c: '#12b6cf', l: 'Reform' }, { c: '#16a34a', l: 'Green' }, { c: '#6b7280', l: 'Other' }],
    'gender-split': [{ c: '#38bdf8', l: 'M' }, { c: '#f472b6', l: 'F' }, { c: '#6b7280', l: 'Unknown' }],
    'rebel-split':  [{ c: '#334155', l: 'Low' }, { c: '#f59e0b', l: 'High' }, { c: '#6b7280', l: 'No data' }]
  };
  // Quadrant angular range (deg, 0 = 12 o'clock, clockwise).
  var WEDGE_QUADRANT = {
    'vote-split':   { start:   0, end:  90 },     // NE
    'party-split':  { start:  90, end: 180 },     // SE
    'gender-split': { start: 180, end: 270 },     // SW
    'rebel-split':  { start: 270, end: 360 }      // NW
  };
  function renderWedgeKey(mode) {
    var arc = document.getElementById('wedge-key-arc');
    if (!arc) return;
    arc.innerHTML = '';
    arc.classList.remove('is-visible');
    var items = WEDGE_KEYS[mode];
    var range = WEDGE_QUADRANT[mode];
    if (!items || !range) return;
    arc.setAttribute('data-quadrant', mode);
    var span = range.end - range.start;
    var n = items.length;
    items.forEach(function (it, i) {
      var t = (i + 1) / (n + 1);
      var angle = range.start + span * t;
      var dot = document.createElement('span');
      dot.className = 'key-dot';
      dot.style.setProperty('--angle', angle + 'deg');
      dot.style.setProperty('--radius', '60px');         // start near centre, inside mask
      dot.style.transitionDelay = (i * 55) + 'ms';
      dot.innerHTML = '<i class="key-swatch" style="background:' + it.c + '"></i><span>' + it.l + '</span>';
      arc.appendChild(dot);
    });
    // Force reflow so initial state is applied, then animate outward.
    void arc.offsetHeight;
    arc.classList.add('is-visible');
    arc.querySelectorAll('.key-dot').forEach(function (d) {
      d.style.setProperty('--radius', '152px');
    });
  }
  function hideWedgeKey() {
    var arc = document.getElementById('wedge-key-arc');
    if (arc) { arc.classList.remove('is-visible'); }
  }
  document.addEventListener('click', function (e) {
    var w = e.target.closest('.ring-wedge[data-mode]');
    if (!w) return;
    e.preventDefault();
    e.stopPropagation();
    var mode = w.getAttribute('data-mode');
    // setMapMode is the single authoritative entry — it always paints,
    // even when no division is selected (vote-split falls back to the
    // most-recent division so the user always sees colours change).
    if (typeof setMapMode === 'function') setMapMode(mode);
    renderWedgeKey(mode);
  });
  // Expose so the service-menu closure can hide the arc on collapse.
  window.__hideWedgeKey = hideWedgeKey;

  function sendMapColours(payload) {
    currentMapData = payload.map_data || {};
    if (!mapFrame.contentWindow) return;
    // Don't gate on mapReady. The iframe (map_relay.html) buffers an
    // early setMode in _pendingSetMode and applies it the moment its
    // React API mounts, so dispatch unconditionally. The previous gate
    // deadlocked on a slow cold-start when the iframe posted :ready
    // before the parent's message listener attached.
    pendingVisPayload = null;
    _dispatchMapColours(payload);
  }

  function setTopicActive(activeBtn) {
    [topicVoteSplit, topicPartySplit, topicGenderSplit, topicRebelRate].forEach(function (b) {
      if (!b) return;
      b.classList.toggle('active', b === activeBtn);
      b.setAttribute('aria-checked', b === activeBtn ? 'true' : 'false');
    });
  }

  function setLegend(kind) {
    if (!legendEl) return;
    // Legend lives at the bottom of the map pane. Hidden until first
    // wedge press; thereafter persists for the session.
    legendEl.removeAttribute('hidden');

    // Data-driven so we can attach per-swatch aria-labels for screen
    // readers (colour is not the sole signal — every swatch has text
    // AND an aria-label naming the colour + the category).
    var LEGENDS = {
      'party': [
        { color: '#1d4ed8', text: 'Con',     aria: 'Blue: Conservative' },
        { color: '#dc2626', text: 'Lab',     aria: 'Red: Labour' },
        { color: '#f59e0b', text: 'Lib Dem', aria: 'Amber: Liberal Democrat' },
        { color: '#12b6cf', text: 'Reform',  aria: 'Teal: Reform UK' },
        { color: '#16a34a', text: 'Green',   aria: 'Green: Green Party' },
        { color: '#6b7280', text: 'Other',   aria: 'Grey: Other or unknown party' }
      ],
      'gender': [
        { color: '#38bdf8', text: 'M',       aria: 'Blue: Male MP' },
        { color: '#f472b6', text: 'F',       aria: 'Pink: Female MP' },
        { color: '#6b7280', text: 'Unknown', aria: 'Grey: Gender unknown / missing data' }
      ],
      'rebel-split': [
        { color: '#6b7280', text: 'Insufficient data', aria: 'Grey: Insufficient data' },
        { color: '#334155', text: 'Low',               aria: 'Dark slate: Low rebellion rate' },
        { color: '#f59e0b', text: 'Higher',            aria: 'Amber: Higher rebellion rate' }
      ],
      'vote-split': [
        { color: '#16a34a', text: 'Aye',            aria: 'Green: Voted Aye' },
        { color: '#dc2626', text: 'No',             aria: 'Red: Voted No' },
        { color: '#6b7280', text: 'Absent/unknown', aria: 'Grey: Absent or vote unknown' }
      ]
    };
    var items = LEGENDS[kind] || LEGENDS['vote-split'];

    // Build DOM safely (no innerHTML; protects against any future
    // dynamic colour/text content from being interpreted as HTML).
    while (legendEl.firstChild) legendEl.removeChild(legendEl.firstChild);
    items.forEach(function (it) {
      var span = document.createElement('span');
      span.setAttribute('aria-label', it.aria);
      var swatch = document.createElement('i');
      swatch.className = 'swatch';
      swatch.style.background = it.color;
      swatch.setAttribute('aria-hidden', 'true');
      span.appendChild(swatch);
      span.appendChild(document.createTextNode(it.text));
      legendEl.appendChild(span);
    });
  }

  // ─── Map-mode dispatcher ───────────────────────────────────
  // SINGLE authoritative entry point for every wedge. Always:
  //   1) updates active wedge UI
  //   2) loads data for selected mode (with sensible fallback if none)
  //   3) paints the map iframe via the canonical sendMapColours path
  // No early returns that bypass paint — every valid click repaints.
  //
  // Legend is rendered from the SAME resolved mode used for the paint,
  // so map + legend can never drift.
  function normaliseMapMode(mode) {
    if (mode === 'rebel-rate') return 'rebel-split';
    return mode || 'vote-split';
  }

  var TOPIC_BY_MODE = {
    'vote-split':   { btn: function () { return topicVoteSplit; },   kind: 'vote-split',   legend: 'vote-split' },
    'party-split':  { btn: function () { return topicPartySplit; },  kind: 'party-split',  legend: 'party' },
    'gender-split': { btn: function () { return topicGenderSplit; }, kind: 'gender-split', legend: 'gender' },
    'rebel-split':  { btn: function () { return topicRebelRate; },   kind: 'rebel-split',  legend: 'rebel-split' }
  };

  function renderSourceSummary(payload) {
    if (!sourceSummary) return;
    while (sourceSummary.firstChild) sourceSummary.removeChild(sourceSummary.firstChild);
    if (sourceLinksList) {
      while (sourceLinksList.firstChild) sourceLinksList.removeChild(sourceLinksList.firstChild);
    }

    if (!payload || !payload.division) {
      var loading = document.createElement('p');
      loading.className = 'source-lens-loading';
      loading.textContent = 'Select a division to see the YourGov summary.';
      sourceSummary.appendChild(loading);
      return;
    }

    var division = payload.division || {};
    var counts = payload.counts || {};
    var dataQuality = payload.data_quality || {};

    var title = document.createElement('h3');
    title.textContent = division.title || 'Selected division';
    sourceSummary.appendChild(title);

    var meta = document.createElement('p');
    meta.className = 'source-summary-meta';
    meta.textContent = [
      division.date || 'date unknown',
      'Division ' + (division.division_id || selectedDivisionId || 'unknown'),
      'Mode ' + (payload.mode || selectedMapMode)
    ].join(' | ');
    sourceSummary.appendChild(meta);

    var stats = document.createElement('div');
    stats.className = 'source-summary-stats';
    [
      ['Aye', counts.aye || 0],
      ['No', counts.no || 0],
      ['Unknown', counts.unknown || 0],
      ['Mapped MPs', dataQuality.mapped_member_rows || Object.keys(payload.map_data || {}).length]
    ].forEach(function (item) {
      var stat = document.createElement('span');
      stat.className = 'source-summary-stat';
      var strong = document.createElement('strong');
      strong.textContent = String(item[1]);
      var label = document.createElement('em');
      label.textContent = item[0];
      stat.appendChild(strong);
      stat.appendChild(label);
      stats.appendChild(stat);
    });
    sourceSummary.appendChild(stats);

    var caveat = document.createElement('p');
    caveat.className = 'caveat';
    caveat.textContent = payload.caveat || 'Map colours are scoped to the selected division.';
    sourceSummary.appendChild(caveat);

    if (!sourceLinksList) return;
    var links = payload.source_links || [];
    if (!links.length && division.source_url) {
      links = [{ label: 'PublicWhip record', url: division.source_url }];
    }
    links.forEach(function (link) {
      if (!link || !link.url) return;
      var item = document.createElement('li');
      var anchor = document.createElement('a');
      anchor.href = link.url;
      anchor.textContent = link.label || 'Source record';
      anchor.addEventListener('click', function (event) {
        event.preventDefault();
        openInSourcePane(anchor.getAttribute('href'));
      });
      item.appendChild(anchor);
      sourceLinksList.appendChild(item);
    });
  }

  function updateSourceView() {
    selectedSourceView = sourceViewSelect ? sourceViewSelect.value : selectedSourceView;
    if (selectedSourceView !== 'publicwhip-record') selectedSourceView = 'yourgov-summary';

    if (selectedSourceView === 'publicwhip-record' && !selectedDivisionId) {
      selectedSourceView = 'yourgov-summary';
      if (sourceViewSelect) sourceViewSelect.value = 'yourgov-summary';
      if (yourgovSummaryPanel) yourgovSummaryPanel.hidden = false;
      if (sourceFramePanel) sourceFramePanel.hidden = true;
      setStatus('Select a division before opening the PublicWhip record.', 'warn');
      return;
    }

    if (sourceViewSelect) sourceViewSelect.value = selectedSourceView;
    if (yourgovSummaryPanel) yourgovSummaryPanel.hidden = selectedSourceView !== 'yourgov-summary';
    if (sourceFramePanel) sourceFramePanel.hidden = selectedSourceView !== 'publicwhip-record';

    if (selectedSourceView !== 'publicwhip-record') return;
    if (!sourceFrame) return;
    var nextSrc = '/publicwhip/division/' + encodeURIComponent(selectedDivisionId);
    if (sourceFrame.getAttribute('src') !== nextSrc) sourceFrame.setAttribute('src', nextSrc);
  }

  async function ensureSelectedDivision(requestToken) {
    if (selectedDivisionId) return selectedDivisionId;

    var response = await fetch('/api/lens/source-divisions?limit=1');
    if (requestToken && !isCurrentMapPayloadRequest(requestToken)) return null;
    var payload = await response.json();
    if (requestToken && !isCurrentMapPayloadRequest(requestToken)) return null;
    if (!response.ok || (payload && payload.ok === false)) {
      throw new Error((payload && payload.error) || 'Could not load latest division');
    }
    var divisions = (payload && (payload.divisions || (Array.isArray(payload) ? payload : []))) || [];
    if (!divisions.length) throw new Error('No divisions in dataset');

    var latest = divisions[0];
    selectedDivisionId = normaliseDivisionId(latest.division_id || latest.id);
    selectedDivisionPayload = selectedDivisionPayload || { division: latest };
    return selectedDivisionId;
  }

  async function loadDivisionMapPayload(mode, requestToken) {
    mode = normaliseMapMode(mode || selectedMapMode);
    var divisionId = await ensureSelectedDivision(requestToken);
    if (requestToken && !isCurrentMapPayloadRequest(requestToken)) return null;
    if (!divisionId) return null;
    var intendedDivisionId = normaliseDivisionId(divisionId);
    var response = await fetch('/api/lens/division/' + encodeURIComponent(divisionId) + '/map?mode=' + encodeURIComponent(mode));
    if (requestToken && (!isCurrentMapPayloadRequest(requestToken) || selectedMapMode !== mode || selectedDivisionId !== intendedDivisionId)) return null;
    var payload = await response.json();
    if (requestToken && (!isCurrentMapPayloadRequest(requestToken) || selectedMapMode !== mode || selectedDivisionId !== intendedDivisionId)) return null;
    if (!response.ok || !payload.ok) {
      throw new Error(payload.error || 'Could not load map mode');
    }
    if (requestToken && (!isCurrentMapPayloadRequest(requestToken) || selectedMapMode !== mode || selectedDivisionId !== intendedDivisionId)) return null;

    selectedDivisionPayload = payload;
    if (payload.division && payload.division.division_id) selectedDivisionId = normaliseDivisionId(payload.division.division_id);
    lastDivisionLabel = (payload.division && payload.division.title) || ('division ' + selectedDivisionId);
    renderSourceSummary(payload);
    updateSourceView();
    return payload;
  }

  async function setMapMode(mode) {
    mode = normaliseMapMode(mode);
    var spec = TOPIC_BY_MODE[mode];
    if (!spec) return;
    selectedMapMode = mode;
    var intendedDivisionId = normaliseDivisionId(selectedDivisionId);
    var requestToken = nextMapPayloadRequest();

    // Step 1: active wedge + legend swap immediately — user feedback
    // happens before any network round-trip.
    setTopicActive(spec.btn());
    setLegend(spec.legend);

    setStatus('Loading YourGov ' + mode + '...', 'ok');
    try {
      var data = await loadDivisionMapPayload(mode, requestToken);
      if (!data) return;
      if (!isCurrentMapPayloadRequest(requestToken) || selectedMapMode !== mode) return;
      if (intendedDivisionId !== null && selectedDivisionId !== intendedDivisionId) return;
      currentMapDataKind = spec.kind;
      renderSelection(data);
      enrichSelectionWithMP();
      sendMapColours(data);
      setStatus('Map updated: ' + mode + '.', 'ok');
    } catch (err) {
      if (!isCurrentMapPayloadRequest(requestToken) || selectedMapMode !== mode) return;
      if (intendedDivisionId !== null && selectedDivisionId !== intendedDivisionId) return;
      setStatus(err.message, 'warn');
    }
  }

  // Backwards-compatible wrapper for any legacy caller that still uses
  // the old applyTopic('vote-split'|'party'|'gender'|'rebel-rate') keys.
  function applyTopic(topicKey) {
    var aliasToMode = {
      'vote-split': 'vote-split',
      'party':      'party-split',
      'gender':     'gender-split',
      'rebel-rate': 'rebel-split',
      'rebel-split': 'rebel-split'
    };
    var mode = aliasToMode[topicKey] || topicKey;
    return setMapMode(mode);
  }

  function _dispatchMapColours(payload) {
    if (!mapFrame.contentWindow) return;
    mapFrame.contentWindow.postMessage({
      type: 'yourgov:map:setMode',
      mode: payload.map_mode || 'votes',
      data: payload.map_data || currentMapData
    }, window.location.origin);
    _scheduleVisRetry(payload);
  }

  function _scheduleVisRetry(payload) {
    clearTimeout(visRetryTimer);
    if (visRetryCount >= 3) {
      visRetryCount = 0;
      setStatus('Map not responding — visualisation may not have applied.', 'warn');
      return;
    }
    var delay = 2000 * (visRetryCount + 1);
    visRetryTimer = window.setTimeout(function () {
      visRetryCount++;
      setStatus('Retrying… (' + visRetryCount + '/3)', 'warn');
      _dispatchMapColours(payload);
    }, delay);
  }

  function queueMapColours(payload) {
    pendingMapPayload = payload;
    if (pendingMapTimer) {
      clearTimeout(pendingMapTimer);
    }
    pendingMapTimer = window.setTimeout(function () {
      if (pendingMapPayload === payload) {
        sendMapColours(payload);
      }
    }, 400);
  }

  function renderSelection(payload) {
    if (!selectionCard) return;
    var division = payload.division || {};
    var counts = payload.counts || {};
    selectionCard.classList.remove('idle');
    selectionTitle.style.color = '';
    selectionTitle.textContent = division.title || 'Selected division';
    selectionMeta.textContent = [
      division.date || 'date unknown',
      'Aye ' + (counts.aye || 0),
      'No ' + (counts.no || 0),
      'Unknown ' + (counts.unknown || 0)
    ].join(' · ');
    selectionCaveat.textContent = payload.caveat || '';
    selectionSource.href = division.source_url || '/publicwhip';
    selectionSource.textContent = 'Open division record →';
    selectionSource.hidden = false;
    if (selectionProfile) selectionProfile.hidden = true;
  }

  function enrichSelectionWithMP() {
    if (!selectionMeta) return;
    var mp = selectedMP || lastSourceMP;
    if (!mp || !mp.constituency) return;
    var voteData = currentMapData[mp.constituency];
    if (!voteData) return;
    var v = voteData.vote || 'No record';
    selectionMeta.textContent = selectionMeta.textContent + ' | ' + mp.name + ' voted: ' + v;
    if (selectionProfile && mp.member_id) {
      selectionProfile.href = '/mp/' + mp.member_id;
      selectionProfile.hidden = false;
    }
  }

  function selectedMPVoteStatus(payload) {
    var mp = selectedMP || lastSourceMP;
    if (!mp || !mp.constituency || !payload || !payload.map_data) return '';
    var voteData = payload.map_data[mp.constituency];
    if (!voteData) return '';
    return ' ' + mp.name + ' voted ' + (voteData.vote || 'No record') + '.';
  }

  function renderDivisionSummary(d) {
    if (!divisionSummaryBody) return;
    while (divisionSummaryBody.firstChild) divisionSummaryBody.removeChild(divisionSummaryBody.firstChild);
    appendTextNode(divisionSummaryBody, 'p', 'eyebrow', 'Division summary');
    appendTextNode(divisionSummaryBody, 'h3', 'division-summary-title', d.title || 'Division');
    appendTextNode(divisionSummaryBody, 'p', 'division-summary-meta',
      [d.date || 'date unknown', 'Division ' + d.division_id].filter(Boolean).join(' · '));
    if (d.mp_name && d.vote) {
      var line = document.createElement('p');
      line.className = 'division-summary-mp';
      line.appendChild(document.createTextNode(d.mp_name + ' voted '));
      var vs = document.createElement('span');
      vs.className = 'division-summary-vote ' + voteClass(d.vote);
      vs.textContent = d.vote;
      line.appendChild(vs);
      divisionSummaryBody.appendChild(line);
    }
    var stats = document.createElement('div');
    stats.className = 'division-summary-stats';
    [['Aye', d.aye_count], ['No', d.no_count]].forEach(function (s) {
      var stat = document.createElement('div');
      stat.className = 'division-summary-stat';
      var strong = document.createElement('strong');
      strong.textContent = String(s[1] || 0);
      var em = document.createElement('em');
      em.textContent = s[0];
      stat.appendChild(strong);
      stat.appendChild(em);
      stats.appendChild(stat);
    });
    divisionSummaryBody.appendChild(stats);
    appendTextNode(divisionSummaryBody, 'p', 'caveat',
      'This is a recorded House of Commons division in the YourGov dataset. It does not infer motive, intent, or wrongdoing.');
  }

  var _divSummaryPrevFocus = null;

  function closeDivisionSummary() {
    if (divisionSummary) divisionSummary.hidden = true;
    // Return focus to the division row that opened the summary.
    try { if (_divSummaryPrevFocus && _divSummaryPrevFocus.focus) _divSummaryPrevFocus.focus(); } catch (e) {}
    _divSummaryPrevFocus = null;
  }

  // Double-clicking (or "Open summary") shows the first-party YourGov division
  // summary and colours the map for that division. PublicWhip is retired.
  function openDivisionSummary(row) {
    if (!row || !divisionSummary || !divisionSummaryBody) return;
    var divisionId = row.dataset.divisionId;
    if (!divisionId) return;
    var mp = selectedMP || lastSourceMP || {};
    renderDivisionSummary({
      division_id: divisionId,
      title: row.dataset.title || '',
      date: row.dataset.date || '',
      vote: row.dataset.vote || '',
      aye_count: row.dataset.ayeCount || '0',
      no_count: row.dataset.noCount || '0',
      mp_name: mp.name || ''
    });
    divisionSummary.hidden = false;
    // Move focus into the dialog (the Back control) and remember the row so
    // closing returns focus to it.
    _divSummaryPrevFocus = row;
    setTimeout(function () { try { if (divisionSummaryClose) divisionSummaryClose.focus(); } catch (e) {} }, 0);
    if (typeof visualiseDivision === 'function') {
      visualiseDivision(parseInt(divisionId, 10), 'division-summary').catch(function () {});
    }
    setStatus('Showing division summary. Use Back to return to the record.', 'ok');
  }

  async function visualiseDivision(divisionId, source) {
    var intendedDivisionId = normaliseDivisionId(divisionId);
    selectedDivisionId = intendedDivisionId;
    selectedMapMode = normaliseMapMode(selectedMapMode);
    var mode = selectedMapMode;
    var requestToken = nextMapPayloadRequest();
    setStatus('Loading division ' + intendedDivisionId + '...', 'ok');
    var payload;
    try {
      payload = await loadDivisionMapPayload(mode, requestToken);
    } catch (err) {
      if (!isCurrentMapPayloadRequest(requestToken) || selectedMapMode !== mode || selectedDivisionId !== intendedDivisionId) return;
      throw err;
    }
    if (!payload) return;
    if (!isCurrentMapPayloadRequest(requestToken) || selectedMapMode !== mode || selectedDivisionId !== intendedDivisionId) return;
    if (!payload.map_data || !Object.keys(payload.map_data).length) {
      setStatus('Could not map this vote to constituency data.', 'warn');
      return;
    }
    payload.match = payload.match || {};
    payload.match.source = source || payload.match.source;
    lastDivisionLabel = (payload.division && payload.division.title) || ('division ' + intendedDivisionId);
    // Mark the active row in the source lens
    document.querySelectorAll('.division-row').forEach(function (r) {
      r.classList.toggle('active', r.dataset.divisionId === intendedDivisionId);
    });
    currentMapDataKind = mode;
    sendMapColours(payload);
    var spec = TOPIC_BY_MODE[mode] || TOPIC_BY_MODE['vote-split'];
    setLegend(spec.legend);
    renderSelection(payload);
    enrichSelectionWithMP();
    setStatus('Showing how MPs voted nationally on ' + lastDivisionLabel + '.' + selectedMPVoteStatus(payload), 'ok');
    if (typeof setTopicActive === 'function') setTopicActive(spec.btn());
  }

  async function recogniseUrl(url) {
    setStatus('Parsing source URL…', 'ok');
    var response = await fetch('/api/lens/recognise-url', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: url })
    });
    var payload = await response.json();
    if (!response.ok || !payload.ok) {
      throw new Error(payload.error || 'Could not recognise URL');
    }
    lastDivisionLabel = 'recognised source URL';
    queueMapColours(payload);
    renderSelection(payload);
  }

  function bindSameOriginFrame() {
    var doc;
    try {
      doc = sourceFrame.contentDocument;
    } catch (err) {
      setStatus('Could not access source frame. Same-origin capture is unavailable.', 'warn');
      return;
    }
    if (!doc || doc.__yourgovLensBound) return;
    doc.__yourgovLensBound = true;
    syncSourceCursor();
    var lastNavCandidate = { href: '', ts: 0 };
    function _divisionIdFromClickTarget(target) {
      if (!target) return null;
      var row = target.closest('[data-lens-division-id],[data-division-id]');
      if (row) {
        var rid = row.getAttribute('data-lens-division-id') || row.getAttribute('data-division-id');
        if (rid && /^\d+$/.test(String(rid))) return parseInt(rid, 10);
      }
      var link = target.closest('a[href]');
      if (!link) return null;
      var href = link.getAttribute('href') || '';
      var match = href.match(/\/publicwhip\/division\/(\d+)/) || href.match(/\/division\/(\d+)/);
      if (match) return parseInt(match[1], 10);
      var did = link.getAttribute('data-lens-division-id') || link.getAttribute('data-division-id');
      if (did && /^\d+$/.test(String(did))) return parseInt(did, 10);
      return null;
    }
    doc.addEventListener('click', function (event) {
      if (doc.body && doc.body.classList.contains('explain-mode-on')) return;
      var divisionId = _divisionIdFromClickTarget(event.target);
      if (!divisionId) return;
      var link = event.target.closest('a[href]');
      var href = link ? (link.getAttribute('href') || '') : '';
      var now = Date.now();
      // Two-step UX: first click drives the map; second click (same link, short window)
      // navigates normally inside the iframe.
      if (href && lastNavCandidate.href === href && (now - lastNavCandidate.ts) < 2500) {
        lastNavCandidate = { href: '', ts: 0 };
        return; // allow default navigation
      }
      event.preventDefault();
      lastNavCandidate = { href: href, ts: now };
      visualiseDivision(divisionId, 'same-origin-publicwhip').catch(function (err) {
        setStatus(err.message, 'warn');
      });
      setStatus('Map updated. Click the same division again to open the source page.', 'ok');
    }, true);
  }

  // Right pane is always the PublicWhip mirror (no source switching tabs).

  // Left pane deep links should open inside the right pane (not a new tab).
  // When Explain Mode is ON, explain-mode.js will intercept these clicks instead.
  if (selectionSource) {
    selectionSource.addEventListener('click', function (event) {
      if (document.body && document.body.classList.contains('explain-mode-on')) return;
      event.preventDefault();
      openInSourcePane(selectionSource.getAttribute('href'));
    });
  }
  if (selectionProfile) {
    selectionProfile.addEventListener('click', function (event) {
      if (document.body && document.body.classList.contains('explain-mode-on')) return;
      event.preventDefault();
      openInSourcePane(selectionProfile.getAttribute('href'));
    });
  }

  visualiseToggle.addEventListener('click', function () {
    setVisualise(!visualiseActive);
  });

  parseUrl.addEventListener('click', function () {
    var url = sourceUrl.value.trim();
    if (!url) {
      setStatus('Paste a PublicWhip division URL first.', 'warn');
      return;
    }
    recogniseUrl(url).catch(function (err) {
      setStatus(err.message, 'warn');
    });
  });

  sourceUrl.addEventListener('keydown', function (event) {
    if (event.key === 'Enter') {
      event.preventDefault();
      parseUrl.click();
    }
  });

  // Division row click in source lens panel
  if (sourceLensList) {
    sourceLensList.addEventListener('click', function (event) {
      var link = event.target.closest('a.division-row-source');
      if (link) {
        event.preventDefault();
        event.stopPropagation();
        openDivisionSummary(link.closest('.division-row'));
        return;
      }
      var row = event.target.closest('.division-row');
      if (!row || !row.dataset.divisionId) return;
      event.preventDefault();
      visualiseDivision(parseInt(row.dataset.divisionId, 10), 'source-lens').catch(function (err) {
        setStatus(err.message, 'warn');
      });
    });
    sourceLensList.addEventListener('dblclick', function (event) {
      var row = event.target.closest('.division-row');
      if (!row || !row.dataset.divisionId) return;
      event.preventDefault();
      openDivisionSummary(row);
    });
    sourceLensList.addEventListener('keydown', function (event) {
      var row = event.target.closest('.division-row');
      if (!row || !row.dataset.divisionId) return;
      if (event.key === 'o' || event.key === 'O' || (event.key === 'Enter' && event.shiftKey)) {
        event.preventDefault();
        openDivisionSummary(row);
        return;
      }
      if (event.key !== 'Enter' && event.key !== ' ') return;
      event.preventDefault();
      visualiseDivision(parseInt(row.dataset.divisionId, 10), 'source-lens').catch(function (err) {
        setStatus(err.message, 'warn');
      });
    });
  }

  var readyPingTimer = null;
  function _startReadyPing() {
    if (readyPingTimer) { clearInterval(readyPingTimer); readyPingTimer = null; }
    var attempts = 0;
    readyPingTimer = window.setInterval(function () {
      attempts++;
      // Stop once handshake completes, or after ~24s (60 × 400ms).
      if (mapReady || attempts > 60) {
        clearInterval(readyPingTimer);
        readyPingTimer = null;
        return;
      }
      if (mapFrame && mapFrame.contentWindow) {
        try {
          mapFrame.contentWindow.postMessage({ type: 'yourgov:map:ping' }, window.location.origin);
        } catch (e) {}
      }
    }, 400);
  }

  mapFrame.addEventListener('load', function () {
    mapReady = false;
    clearTimeout(visRetryTimer);
    visRetryCount = 0;
    _startReadyPing();
    // Add hover tooltips to the four map demo buttons (rendered inside the map iframe bundle).
    // This keeps the map bundle untouched while making the UI self-explanatory.
    window.setTimeout(function () {
      try {
        var doc = mapFrame.contentDocument;
        if (!doc) return;
        var controls = doc.querySelectorAll('.mygov-map-controls button');
        if (!controls || !controls.length) return;
        controls.forEach(function (btn) {
          if (btn.getAttribute('title')) return;
          var label = (btn.textContent || '').trim().toLowerCase();
          if (label === 'demo score') btn.title = 'Demo colouring (synthetic score)';
          else if (label === 'activity heat') btn.title = 'Demo heat overlay (turnout/activity style)';
          else if (label === 'issue highlight') btn.title = 'Demo issue overlay (not a vote)';
          else if (label === 'neutral') btn.title = 'Clear overlays (neutral map)';
        });
      } catch (e) {}
    }, 250);
  });

  // Kick the ping immediately too — the iframe's load event may have
  // fired before our listener attached on a fast same-origin response.
  _startReadyPing();

  if (sourceFrame) {
    sourceFrame.addEventListener('load', function () {
      try {
        var path = sourceFrame.contentWindow.location.pathname;
        if (!path || path.indexOf('/publicwhip/mp/') === -1) {
          if (!selectedMP) lastSourceMP = null;
        }
      } catch (e) {}
      syncSourceCursor();
      bindSameOriginFrame();
    });
  }

  window.addEventListener('message', function (event) {
    if (event.origin !== window.location.origin || !event.data) return;
    var type = event.data.type;

    if (type === 'yourgov:map:ready') {
      mapReady = true;
      if (pendingVisPayload) {
        var p = pendingVisPayload;
        pendingVisPayload = null;
        visRetryCount = 0;
        _dispatchMapColours(p);
      }
      return;
    }

    if (type === 'yourgov:map:applied') {
      clearTimeout(visRetryTimer);
      visRetryCount = 0;
      setStatus('Map updated from ' + (lastDivisionLabel || 'selected division') + '.', 'ok');
      return;
    }

    if (type === 'yourgov:map:failed') {
      clearTimeout(visRetryTimer);
      setStatus('Map failed to load. Reload the page to try again.', 'warn');
      return;
    }

    if (type === 'yourgov:source:division-selected') {
      var divId = event.data.division_id;
      if (divId) {
        visualiseDivision(divId, 'same-origin-division-page').catch(function (err) {
          setStatus(err.message, 'warn');
        });
      }
      return;
    }

    if (type === 'yourgov:source:mp-selected') {
      var mpName = event.data.name || '';
      var mpParty = event.data.party || '';
      var mpConstituency = event.data.constituency || '';
      var mpMemberId = event.data.member_id;
      lastSourceMP = { name: mpName, party: mpParty, constituency: mpConstituency, member_id: mpMemberId };
      var voteData = currentMapData[mpConstituency];
      if (!voteData && mpConstituency) {
        var hlData = {};
        hlData[mpConstituency] = {
          color: '#38bdf8',
          label: mpName + (mpParty ? ' · ' + mpParty : ''),
          vote: null,
          member_id: mpMemberId,
          name: mpName,
          party: mpParty,
          source: 'mp-page'
        };
        if (mapFrame && mapFrame.contentWindow) {
          mapFrame.contentWindow.postMessage({
            type: 'yourgov:map:setMode',
            mode: 'highlight',
            data: hlData
          }, window.location.origin);
        }
      }
      if (selectionCard) {
        selectionCard.classList.remove('idle');
        selectionTitle.textContent = mpName;
        if (voteData) {
          var mpVote = voteData.vote || 'No record';
          selectionMeta.textContent = (mpParty || 'Unknown') + ' · ' + mpConstituency + ' · Voted: ' + mpVote;
          selectionCaveat.textContent = (mpVote === 'Absent/unknown' || mpVote === 'No record')
            ? 'No recorded vote for this MP on the selected division.' : '';
        } else {
          selectionMeta.textContent = (mpParty || 'Unknown party') + (mpConstituency ? ' · ' + mpConstituency : '');
          selectionCaveat.textContent = 'Select a division in the right panel to see how this MP voted.';
        }
        if (mpMemberId) {
          selectionSource.href = '/mp/' + mpMemberId;
          selectionSource.textContent = 'Open MP profile →';
          if (selectionProfile) {
            selectionProfile.href = '/mp/' + mpMemberId;
            selectionProfile.hidden = false;
          }
        }
      }
      return;
    }

    if (type !== 'yourgov:constituency:selected') return;
    var detail = event.data.detail || {};
    var constituency = detail.constituency || {};
    var vote = currentMapData[constituency.name] || currentMapData[constituency.code];
    if (!vote) return;
    var parts = [
      vote.name || constituency.name || 'Selected constituency',
      vote.party || '',
      constituency.name || '',
      vote.vote || 'Vote data unavailable'
    ].filter(Boolean);
    if (selectionMeta) {
      selectionMeta.textContent = parts.join(' | ');
      if (vote.member_id && selectionSource) {
        selectionSource.href = '/mp/' + vote.member_id;
        selectionSource.textContent = 'View MP profile';
      }
    }
  });

  // ── MP search ────────────────────────────────────────────────
  // Inline-autocomplete state. The dropdown list is now hidden via CSS;
  // suggestions live in a ghost layer above the input. _topSuggestion
  // holds the current best match so Enter/Tab can act on it.
  var _topSuggestion = null;     // {id, name, party, constituency}
  var _topPostcode = null;       // {full, query} while completing a postcode inline
  var _ghostEl = null;
  function _ensureGhost() {
    if (_ghostEl) return _ghostEl;
    var form = document.getElementById('mp-search-form');
    var input = document.getElementById('mp-search-input');
    var host = input && input.closest ? input.closest('.yourgov-search-input-wrap') : null;
    var target = host || form;
    if (!target) return null;
    _ghostEl = document.createElement('div');
    _ghostEl.className = 'map-search-ghost';
    _ghostEl.setAttribute('aria-hidden', 'true');
    _ghostEl.innerHTML = '<span class="typed"></span><span class="tail"></span>';
    target.insertBefore(_ghostEl, input || target.firstChild);
    return _ghostEl;
  }
  function _setGhost(typed, tail) {
    var g = _ensureGhost();
    if (!g) return;
    g.querySelector('.typed').textContent = typed;
    g.querySelector('.tail').textContent = tail;
  }
  function _clearGhost() {
    _setGhost('', '');
    _topSuggestion = null;
    _topPostcode = null;
  }

  // Postcode inline completion. A partial postcode (e.g. "SW1") completes to a
  // full one in the bar via /api/postcode/autocomplete; accepting it resolves
  // the postcode to its MP. Names/constituencies keep the existing path.
  function looksLikePartialPostcode(q) {
    var s = (q || '').replace(/\s/g, '').toUpperCase();
    // 1–2 letters then a digit, then anything — the shape of a UK outward code.
    return s.length >= 2 && s.length <= 7 && /^[A-Z]{1,2}[0-9][A-Z0-9]*$/.test(s);
  }
  function postcodeTail(typed, full) {
    // Tail of `full` (with its space) after the chars already typed, comparing
    // case- and space-insensitively. "sw1" + "SW1A 1AA" -> "A 1AA".
    var t = (typed || '').replace(/\s/g, '').toUpperCase();
    var f = (full || '').replace(/\s/g, '').toUpperCase();
    if (!t || f.indexOf(t) !== 0) return '';
    var consumed = 0, i = 0;
    for (; i < full.length && consumed < t.length; i += 1) {
      if (full[i] !== ' ') consumed += 1;
    }
    return full.substring(i);
  }
  function renderPostcodeSuggestion(postcodes) {
    var current = (mpSearchInput && mpSearchInput.value) || '';
    _topSuggestion = null;
    clearSearchResultsList();
    var full = '', tail = '';
    for (var i = 0; i < postcodes.length; i += 1) {
      var candidate = postcodeTail(current, postcodes[i]);
      if (candidate || i === 0) { full = postcodes[i]; tail = candidate; }
      if (candidate) break;
    }
    _topPostcode = { full: full, query: normaliseSearchQuery(current) };
    _setGhost(current, tail);
  }
  function hasCurrentTopPostcode() {
    if (!_topPostcode || !_topPostcode.full || !mpSearchInput) return false;
    return _topPostcode.query === normaliseSearchQuery(mpSearchInput.value);
  }
  function normaliseSearchQuery(value) {
    return (value || '').trim().replace(/\s+/g, ' ').toLowerCase();
  }
  function hasCurrentTopSuggestion() {
    if (!_topSuggestion || !_topSuggestion.id || !mpSearchInput) return false;
    return _topSuggestion.query === normaliseSearchQuery(mpSearchInput.value);
  }
  // Strip a leading honorific so "Lam" matches "Mr David Lammy" via
  // its surname-bearing portion. Order matters: more specific first.
  var _HONORIFICS = /^(?:(?:Rt\s+Hon\s+)?(?:The\s+)?(?:Dr|Sir|Dame|Lord|Lady|Mr|Mrs|Ms|Miss|Mx|Prof|Hon)\.?\s+)/i;
  function _stripHonorific(name) {
    return (name || '').replace(_HONORIFICS, '');
  }
  function _commonPrefix(typed, name) {
    // Case-insensitive prefix match. Tries the full name first, then
    // the name with leading honorific stripped, then any word-start
    // inside the name (so "Lam" can match the "Lammy" surname inside
    // "Mr David Lammy"). When a non-prefix word matches, the tail is
    // the rest of that matched word so the ghost reads sensibly.
    if (!typed || !name) return '';
    var t = typed.toLowerCase();
    var n = name.toLowerCase();
    if (n.indexOf(t) === 0) return name.substring(typed.length);
    var stripped = _stripHonorific(name);
    var ns = stripped.toLowerCase();
    if (ns !== n && ns.indexOf(t) === 0) return stripped.substring(typed.length);
    // Word-start match: find any whitespace-separated word starting
    // with the typed prefix and return the rest of that word.
    var parts = name.split(/\s+/);
    for (var i = 0; i < parts.length; i += 1) {
      if (parts[i].toLowerCase().indexOf(t) === 0 && parts[i].length > t.length) {
        return parts[i].substring(typed.length);
      }
    }
    return '';
  }

  function queryMatchesText(typed, text) {
    var t = normaliseSearchQuery(typed);
    var n = normaliseSearchQuery(_stripHonorific(text || ''));
    if (!t || !n) return false;
    if (n.indexOf(t) === 0) return true;
    var parts = n.split(/\s+/);
    for (var i = 0; i < parts.length; i += 1) {
      if (parts[i].indexOf(t) === 0) return true;
    }
    return false;
  }

  function suggestionTailForResult(typed, result) {
    if (!result || !result.name) return '';
    var nameTail = _commonPrefix(typed, result.name);
    if (nameTail) return nameTail;
    if (result.match_type === 'postcode') return ' - ' + result.name;
    if (result.constituency && queryMatchesText(typed, result.constituency)) return ' - ' + result.name;
    return '';
  }

  function clearSearchResultsList() {
    focusedResultIndex = -1;
    if (!searchResultsEl) return;
    while (searchResultsEl.firstChild) searchResultsEl.removeChild(searchResultsEl.firstChild);
    searchResultsEl.setAttribute('hidden', '');
  }

  function renderInlineSearchSuggestion(results) {
    var typed = (mpSearchInput && mpSearchInput.value) || '';
    if (!results || !results.length) {
      _clearGhost();
      clearSearchResultsList();
      return null;
    }
    var best = null;
    for (var i = 0; i < results.length; i += 1) {
      if (_commonPrefix(typed, results[i].name || '')) {
        best = results[i];
        break;
      }
    }
    if (!best) best = results[0];
    _topSuggestion = {
      id: best.id, name: best.name || '',
      party: best.party || '', constituency: best.constituency || '',
      match_type: best.match_type || '',
      query: normaliseSearchQuery(typed)
    };
    _setGhost(typed, suggestionTailForResult(typed, _topSuggestion));
    return _topSuggestion;
  }

  function renderSearchResults(results, options) {
    options = options || {};
    var suggestion = renderInlineSearchSuggestion(results);
    clearSearchResultsList();
    if (options.acceptSingle && results && results.length === 1 && suggestion && hasCurrentTopSuggestion()) {
      selectSearchMPData(suggestion);
    }
  }

  function renderSearchResultsLegacyDisabled(results) {
    // Inline autocomplete: pick top result, paint ghost tail, and keep
    // the visible YourGov result list available for explicit selection.
    var typed = (mpSearchInput && mpSearchInput.value) || '';
    if (!results || !results.length) {
      _clearGhost();
      // Keep the visible dropdown element clean too.
      if (searchResultsEl) {
        while (searchResultsEl.firstChild) searchResultsEl.removeChild(searchResultsEl.firstChild);
      }
      return;
    }
    // Pick the first result whose name starts with the typed prefix,
    // else fall back to the absolute first result.
    var best = null;
    for (var i = 0; i < results.length; i += 1) {
      if (_commonPrefix(typed, results[i].name || '')) {
        best = results[i];
        break;
      }
    }
    if (!best) best = results[0];
    _topSuggestion = {
      id: best.id, name: best.name || '',
      party: best.party || '', constituency: best.constituency || ''
    };
    var tail = _commonPrefix(typed, _topSuggestion.name);
    _setGhost(typed, tail);

    // Rebuild the visible left-panel result list.
    if (!searchResultsEl) return;
    while (searchResultsEl.firstChild) searchResultsEl.removeChild(searchResultsEl.firstChild);
    var frag = document.createDocumentFragment();
    results.forEach(function (mp) {
      var item = document.createElement('div');
      item.className = 'search-result-item';
      item.dataset.mpId = String(mp.id);
      item.dataset.mpName = mp.name || '';
      item.dataset.mpParty = mp.party || '';
      item.dataset.mpConstituency = mp.constituency || '';

      var nameEl = document.createElement('div');
      nameEl.className = 'search-result-name';
      nameEl.textContent = mp.name || '';
      item.appendChild(nameEl);

      var metaEl = document.createElement('div');
      metaEl.className = 'search-result-meta';
      metaEl.textContent = (mp.party || 'Unknown party') + ' · ' + (mp.constituency || '');
      item.appendChild(metaEl);

      // If a division is active, show the MP's vote inline
      var voteData = currentMapData[mp.constituency];
      if (voteData && voteData.vote) {
        var voteEl = document.createElement('div');
        var v = voteData.vote;
        voteEl.className = 'search-result-vote ' + (v === 'Aye' ? 'aye' : v === 'No' ? 'no' : 'unknown');
        voteEl.textContent = 'Voted ' + v + ' on current division';
        item.appendChild(voteEl);
      }

      var contactEl = document.createElement('a');
      contactEl.className = 'search-result-contact';
      contactEl.href = WRITETOTHEM_URL;
      contactEl.target = '_blank';
      contactEl.rel = 'noopener noreferrer';
      contactEl.title = 'Contact this MP via WriteToThem';
      contactEl.setAttribute('aria-label', 'Contact ' + (mp.name || 'this MP') + ' via WriteToThem');
      contactEl.innerHTML = '<span class="search-result-contact-logo" aria-hidden="true">MP</span><span>Contact</span>';
      contactEl.addEventListener('click', function (event) {
        event.stopPropagation();
      });
      item.appendChild(contactEl);

      frag.appendChild(item);
    });
    searchResultsEl.appendChild(frag);
    searchResultsEl.removeAttribute('hidden');
  }

  function hideSearchResults() {
    clearSearchResultsList();
    _clearGhost();
  }

  function updateFocusedResult(items) {
    items.forEach(function (item, i) {
      item.classList.toggle('focused', i === focusedResultIndex);
    });
  }

  async function searchMPs(q, options) {
    if (!q || q.trim().length < 2) { hideSearchResults(); return; }
    var trimmed = q.trim();
    // Partial postcode -> complete the postcode inline (then resolve to the MP
    // on accept). Falls through to name/constituency search if there are no
    // postcode completions.
    if (looksLikePartialPostcode(trimmed)) {
      try {
        var pr = await fetch('/api/postcode/autocomplete?q=' + encodeURIComponent(trimmed));
        var pdata = await pr.json();
        var postcodes = pdata.results || [];
        if (postcodes.length) { renderPostcodeSuggestion(postcodes); return; }
      } catch (e) { /* fall through to MP search */ }
    }
    _topPostcode = null;
    try {
      var resp = await fetch('/api/mps/search?q=' + encodeURIComponent(trimmed));
      var data = await resp.json();
      renderSearchResults(data.results || [], options || {});
    } catch (e) {
      renderSearchResults([]);
    }
  }

  // Accept whatever the bar is currently suggesting (a postcode being completed,
  // or an MP/constituency inline match). Returns true if an accept was started.
  function acceptCurrentSuggestion() {
    ygMetric('search', { kind: hasCurrentTopPostcode() ? 'postcode' : 'name' });
    if (hasCurrentTopPostcode()) {
      var pc = _topPostcode.full;
      if (mpSearchInput) mpSearchInput.value = pc;
      _setGhost(pc, '');
      fetch('/api/mps/search?q=' + encodeURIComponent(pc))
        .then(function (r) { return r.json(); })
        .then(function (data) {
          var mp = (data.results || [])[0];
          if (mp && mp.id) { mp.postcode = pc; selectSearchMPData(mp); }
          else setStatus('No MP found for ' + pc + '.', 'warn');
        })
        .catch(function () { setStatus('Could not resolve that postcode.', 'warn'); });
      return true;
    }
    if (hasCurrentTopSuggestion()) { selectSearchMPData(_topSuggestion); return true; }
    return false;
  }

  function selectSearchMPData(mp) {
    if (!mp || !mp.id) return;
    hideSearchResults();
    if (mpSearchInput) mpSearchInput.value = mp.name || '';
    _setGhost(mp.name || '', '');
    loadMPVotingRecord({
      id: mp.id,
      name: mp.name || '',
      party: mp.party || '',
      constituency: mp.constituency || '',
      postcode: mp.postcode || ''
    }).catch(function (err) {
      setStatus(err.message, 'warn');
    });
  }

  function selectSearchMP(item) {
    selectSearchMPData({
      id: item.dataset.mpId,
      name: item.dataset.mpName,
      party: item.dataset.mpParty,
      constituency: item.dataset.mpConstituency
    });
  }

  if (mpSearchForm) {
    mpSearchForm.addEventListener('submit', function (e) {
      e.preventDefault();
      if (!mpSearchInput) return;
      if (acceptCurrentSuggestion()) return;
      searchMPs(mpSearchInput.value, { acceptSingle: true });
    });
  }

  if (mpSearchInput) {
    mpSearchInput.addEventListener('input', function () {
      clearTimeout(searchDebounce);
      var q = mpSearchInput.value;
      // Always paint the typed prefix into the ghost (without a tail
      // yet) so the typed text + caret stay aligned during the
      // debounce.
      _setGhost(q, '');
      if (q.trim().length < 2) {
        _clearGhost();
        hideSearchResults();
        return;
      }
      searchDebounce = window.setTimeout(function () { searchMPs(q.trim()); }, 250);
    });
    mpSearchInput.addEventListener('keydown', function (e) {
      // Esc: first press clears suggestion; second press collapses
      // the pill if input is now empty.
      if (e.key === 'Escape') {
        if ((_topSuggestion || _topPostcode) && mpSearchInput.value.length > 0) {
          e.preventDefault();
          _clearGhost();
          return;
        }
        // Otherwise fall through — setupMapSearch's own Esc handler
        // clears input + collapses.
        hideSearchResults();
        return;
      }
      // Tab or ArrowRight at end-of-input → accept the inline completion
      // (an MP name/constituency match, or a postcode being completed).
      if ((e.key === 'Tab' || e.key === 'ArrowRight') && (_topSuggestion || _topPostcode)) {
        var atEnd = mpSearchInput.selectionStart === mpSearchInput.value.length;
        var tail = _topPostcode
          ? postcodeTail(mpSearchInput.value, _topPostcode.full)
          : suggestionTailForResult(mpSearchInput.value, _topSuggestion);
        if (atEnd && tail) {
          e.preventDefault();
          acceptCurrentSuggestion();
          return;
        }
      }
      // Enter accepts the current inline match (MP or postcode), or searches
      // and accepts a single result.
      if (e.key === 'Enter') {
        e.preventDefault();
        if (!acceptCurrentSuggestion()) {
          searchMPs(mpSearchInput.value, { acceptSingle: true });
        }
      }
    });
  }

  if (searchResultsEl) {
    searchResultsEl.addEventListener('click', function (e) {
      var item = e.target.closest('.search-result-item');
      if (item) selectSearchMP(item);
    });
  }

  document.addEventListener('click', function (e) {
    if (!searchResultsEl) return;
    var wrap = document.getElementById('map-search');
    if (wrap && !wrap.contains(e.target)) hideSearchResults();
  });
  // ── end MP search ─────────────────────────────────────────────

  // ── S-button expanding search pill ────────────────────────────
  // Contract: width = (typed_chars + BREATHE) * char_slot. BREATHE = 3
  // blank chars of room. Empty → 3 slots wide. Each keystroke (or
  // autocomplete pick, which also fires 'input') adds a slot; delete
  // removes one. Collapses to S-only when blurred with an empty value.
  (function setupMapSearch() {
    var searchEl = document.getElementById('map-search');
    var triggerEl = document.getElementById('map-search-trigger');
    var inputEl = document.getElementById('mp-search-input');
    if (!searchEl || !triggerEl || !inputEl) return;

    var BREATHE = 3;           // 3 blank chars of room always reserved
    var MAX_SLOTS = 48;        // hard ceiling; matches input maxlength
    var COLLAPSE_DELAY_MS = 250;
    var collapseTimer = null;

    function slotsFor(value) {
      // Width = typed length + BREATHE blank chars. Never less than BREATHE.
      var n = (value ? value.length : 0) + BREATHE;
      return Math.max(BREATHE, Math.min(MAX_SLOTS, n));
    }

    function setSlots(n) {
      searchEl.style.setProperty('--slots', String(n));
    }

    function syncWidth() {
      setSlots(slotsFor(inputEl.value));
    }

    var menuEl = document.getElementById('service-menu');

    function expand() {
      clearTimeout(collapseTimer);
      if (searchEl.classList.contains('is-expanded')) return;
      searchEl.classList.remove('is-collapsed');
      searchEl.classList.add('is-expanded');
      triggerEl.setAttribute('aria-expanded', 'true');
      if (menuEl) menuEl.classList.add('is-search-open');
      syncWidth();
    }

    /**
     * Collapse the search pill.
     * @param {boolean} force  If true, clear any typed value and
     *   collapse unconditionally — used by the explicit S-button
     *   close gesture. Without force, a non-empty input keeps the
     *   pill open (the blur-debounce path that fires while the user
     *   is mid-task).
     */
    function collapse(force) {
      if (!force && inputEl.value.length > 0) return;
      if (force && inputEl.value.length > 0) {
        inputEl.value = '';
        // Notify any input listeners (autocomplete ghost, etc.) that
        // the value has been cleared programmatically.
        inputEl.dispatchEvent(new Event('input', { bubbles: true }));
      }
      searchEl.classList.remove('is-expanded');
      searchEl.classList.add('is-collapsed');
      triggerEl.setAttribute('aria-expanded', 'false');
      if (menuEl) menuEl.classList.remove('is-search-open');
      setSlots(BREATHE);
      hideSearchResults();
      // Drop focus so the next S-button click cleanly re-enters the
      // expand path instead of the focus → expand reopen loop.
      try { inputEl.blur(); } catch (e) {}
    }

    function scheduleCollapse() {
      clearTimeout(collapseTimer);
      collapseTimer = window.setTimeout(function () { collapse(false); }, COLLAPSE_DELAY_MS);
    }

    triggerEl.addEventListener('click', function () {
      // Clicking the S button is a toggle:
      //   expanded → close (clears any typed value)
      //   collapsed → open + focus the input
      if (searchEl.classList.contains('is-expanded')) {
        collapse(true);
      } else {
        expand();
        inputEl.focus();
      }
    });

    inputEl.addEventListener('focus', expand);
    // 'input' fires for typing, paste, AND browser autocomplete pick,
    // so this is the single source of truth for width recomputation.
    inputEl.addEventListener('input', syncWidth);
    // Belt-and-braces: some browsers fire 'change' instead of 'input' on
    // autofill, especially on iOS Safari and password-manager dropdowns.
    inputEl.addEventListener('change', syncWidth);
    inputEl.addEventListener('blur', scheduleCollapse);
    inputEl.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') {
        if (inputEl.value.length === 0) {
          inputEl.blur();
          collapse();
        } else {
          inputEl.value = '';
          syncWidth();
          hideSearchResults();
        }
      }
    });

    if (searchResultsEl) {
      searchResultsEl.addEventListener('mousedown', function () {
        clearTimeout(collapseTimer);
      });
    }

    // Initial state: collapsed, 3 blank slots reserved.
    setSlots(BREATHE);
  })();
  // ── end S-button search ──────────────────────────────────────

  // ── Concentric service menu (always-on, no cycle) ────────────
  // S replaces M as the centre; Ring 1 (Explain) and Ring 2 (wedges)
  // are permanently visible. The .always-on CSS class drives reveal.
  (function setupServiceMenu() {
    var menu = document.getElementById('service-menu');
    if (!menu) return;

    // ── Action wiring (Explain ring delegates to #explain-mode-btn) ─
    function doAction(name) {
      if (name === 'explain') {
        var explainBtn = document.getElementById('explain-mode-btn');
        if (explainBtn) explainBtn.click();
      }
    }

    menu.addEventListener('click', function (e) {
      // Wedges handle themselves via document-level delegation.
      // Search trigger (#map-search-trigger) is wired by setupMapSearch.
      if (e.target.closest('.ring-wedge')) return;
      if (e.target.closest('#map-search')) return;
      var btn = e.target.closest('.service-action');
      if (!btn) return;
      var action = btn.getAttribute('data-action');
      if (action === 'modes') return;        // ring-2 container is wedge wrapper
      e.preventDefault();
      e.stopPropagation();
      doAction(action);
    });

    // ── Indicator sync (Explain on/off) ──────────────────────────
    // Label lives inside an SVG <textPath> so it follows the ring's arc.
    var explainLabelEl = menu.querySelector('#ring-1-text');
    var explainLabelOff = explainLabelEl ? (explainLabelEl.getAttribute('data-label-off') || 'Explain') : 'Explain';
    var explainLabelOn  = explainLabelEl ? (explainLabelEl.getAttribute('data-label-on')  || 'Exit Explain') : 'Exit Explain';

    function setActionOn(name, on) {
      var btn = menu.querySelector('.service-action[data-action="' + name + '"]');
      if (!btn) return;
      btn.classList.toggle('is-on', !!on);
      btn.setAttribute('aria-pressed', on ? 'true' : 'false');
    }

    function updateIndicators() {
      if (!document.body) return;
      var explainOn = document.body.classList.contains('explain-mode-on');
      setActionOn('explain', explainOn);
      if (explainLabelEl) explainLabelEl.textContent = explainOn ? explainLabelOn : explainLabelOff;
    }
    updateIndicators();

    // Watch body class flips driven by Explain Mode
    var bodyNode = document.body;
    if (bodyNode && bodyNode.nodeType === 1) {
      var bodyObserver = new MutationObserver(updateIndicators);
      bodyObserver.observe(bodyNode, { attributes: true, attributeFilter: ['class'] });
    }
  })();
  // ── end service menu ─────────────────────────────────────────

  // ── Guided tour: onboarding overlay + step rail ───────────────
  var stepRail = document.getElementById('step-rail');
  var overlay = document.getElementById('onboarding-overlay');
  var overlayStart = document.getElementById('onboarding-start');
  var overlaySkip = document.getElementById('onboarding-skip');
  var replayTourBtn = document.getElementById('replay-tour');
  var visualiseHint = document.getElementById('visualise-required-hint');
  var hintTimer = null;
  var pulseTimer = null;
  var TOUR_KEY = 'sourceLensTourSeen';

  function setStep(n) {
    if (!stepRail) return;
    stepRail.setAttribute('data-step', String(n));
    var items = stepRail.querySelectorAll('.how-step');
    items.forEach(function (el) {
      var k = parseInt(el.getAttribute('data-step-n'), 10);
      el.classList.toggle('is-active', k === n);
      el.classList.toggle('is-done', k < n);
    });
  }

  function showVisualiseHint() {
    if (!visualiseHint) return;
    visualiseHint.hidden = false;
    clearTimeout(hintTimer);
    hintTimer = window.setTimeout(function () {
      visualiseHint.hidden = true;
    }, 2400);
  }

  function pulseVisualiseButton() {
    if (!visualiseToggle) return;
    visualiseToggle.classList.add('is-pulsing');
    clearTimeout(pulseTimer);
    pulseTimer = window.setTimeout(function () {
      visualiseToggle.classList.remove('is-pulsing');
    }, 3000);
  }

  function closeOverlay(seen) {
    if (!overlay) return;
    overlay.hidden = true;
    if (seen) {
      try { localStorage.setItem(TOUR_KEY, '1'); } catch (e) {}
    }
  }

  function openOverlay() {
    if (!overlay) return;
    overlay.hidden = false;
  }

  if (overlayStart) {
    overlayStart.addEventListener('click', function () {
      closeOverlay(true);
      pulseVisualiseButton();
    });
  }
  if (overlaySkip) {
    overlaySkip.addEventListener('click', function () { closeOverlay(true); });
  }
  if (replayTourBtn) {
    replayTourBtn.addEventListener('click', function () {
      setStep(1);
      openOverlay();
    });
  }

  // Show overlay on first visit only
  try {
    if (!localStorage.getItem(TOUR_KEY)) openOverlay();
  } catch (e) { /* localStorage unavailable — leave overlay hidden */ }

  // ── Tour-aware hooks on existing functions ────────────────────
  // Auto-turn Visualise OFF after successful selection, advance rail.
  var _origRenderSelection = renderSelection;
  renderSelection = function (payload) {
    _origRenderSelection(payload);
    // Visualise is silently always-on now — no auto-turn-off after a selection.
    setStep(2);
  };

  // Block iframe division clicks when Visualise is OFF — show hint.
  var _origBindSameOriginFrame = bindSameOriginFrame;
  bindSameOriginFrame = function () {
    var doc;
    try { doc = sourceFrame.contentDocument; } catch (err) { return; }
    if (!doc || doc.__yourgovLensTourBound) {
      _origBindSameOriginFrame();
      return;
    }
    doc.__yourgovLensTourBound = true;
    function _divisionIdFromClickTarget(target) {
      if (!target) return null;
      var row = target.closest('[data-lens-division-id],[data-division-id]');
      if (row) {
        var rid = row.getAttribute('data-lens-division-id') || row.getAttribute('data-division-id');
        if (rid && /^\d+$/.test(String(rid))) return parseInt(rid, 10);
      }
      var link = target.closest('a[href]');
      if (!link) return null;
      var href = link.getAttribute('href') || '';
      var match = href.match(/\/publicwhip\/division\/(\d+)/) || href.match(/\/division\/(\d+)/);
      if (match) return parseInt(match[1], 10);
      return null;
    }
    // Pre-capture: if visualise off and click would target a division link, intercept.
    doc.addEventListener('click', function (event) {
      if (visualiseActive) return;
      if (doc.body && doc.body.classList.contains('explain-mode-on')) return;
      if (!_divisionIdFromClickTarget(event.target)) return;
      event.preventDefault();
      event.stopPropagation();
      showVisualiseHint();
    }, true);
    _origBindSameOriginFrame();
  };

  // Map applied → advance rail to step 3.
  window.addEventListener('message', function (event) {
    if (event.origin !== window.location.origin || !event.data) return;
    if (event.data.type === 'yourgov:map:applied') setStep(3);
  });

  if (sourceViewSelect) {
    selectedSourceView = sourceViewSelect.value || 'yourgov-summary';
    sourceViewSelect.addEventListener('change', updateSourceView);
  }
  updateSourceView();
  renderMPSearchPrompt();
  ygMetric('pageview', { referrer: document.referrer });
  setMapMode(selectedMapMode);
  setStatus('YourGov Summary ready. PublicWhip loads only when selected.', 'ok');
  updateInstruction();

  // ── Outer nav ring (Lens / YourGov / Global) ──────────────────
  // No-page-reload source switching: click animates the ring rotation
  // and, at the rotation midpoint, swaps #source-frame.src to the
  // target view. /source-lens stays the only top-level URL.
  (function setupNavRing() {
    var ring = document.getElementById('nav-ring');
    if (!ring) return;
    var ROTATION_MS = 420;       // matches CSS 400ms transition + small buffer

    // View -> optional inline URL.
    // PublicWhip stays behind the selected division dropdown/source link.
    var SOURCE_FOR_VIEW = {
      lens: null,
      yourgov: null,
      global: '/global',
    };
    var STORAGE_KEY = 'yourgov:lensSource';

    function isKnownView(view) {
      return Object.prototype.hasOwnProperty.call(SOURCE_FOR_VIEW, view);
    }

    function urlFor(view) {
      var base = SOURCE_FOR_VIEW[view];
      if (!base) return '';
      // Propagate cc + lang so /global can preselect the right country
      // and any view can honour the locale.
      var params = new URLSearchParams(window.location.search);
      var pass = new URLSearchParams();
      var cc = params.get('cc');
      var lang = params.get('lang');
      if (cc) pass.set('cc', cc);
      if (lang) pass.set('lang', lang);
      var qs = pass.toString();
      return qs ? base + (base.indexOf('?') >= 0 ? '&' : '?') + qs : base;
    }

    function activateYourGovSource(view) {
      var frame = document.getElementById('source-frame');
      if (sourceViewSelect) sourceViewSelect.value = 'yourgov-summary';
      selectedSourceView = 'yourgov-summary';
      updateSourceView();
      if (frame) {
        try { frame.setAttribute('src', 'about:blank'); } catch (e) {}
      }
      try { sessionStorage.setItem(STORAGE_KEY, view || 'lens'); } catch (e) {}
    }

    function setActive(view) {
      ring.setAttribute('data-active', view);
      ring.querySelectorAll('.nav-icon').forEach(function (n) {
        n.classList.toggle('is-active', n.getAttribute('data-view') === view);
      });
    }

    function rotationForIcon(iconEl) {
      var iconAngle = parseFloat(iconEl.style.getPropertyValue('--icon-angle') || '0');
      // Active icon should land at 180° (6 o'clock).
      var r = 180 - iconAngle;
      while (r > 180) r -= 360;
      while (r < -180) r += 360;
      return r;
    }

    function loadSource(view) {
      var frame = document.getElementById('source-frame');
      if (!frame) return;
      var url = urlFor(view);
      if (!url) {
        activateYourGovSource(view);
        return;
      }
      // Reset the iframe nav stack tracking — the new source starts
      // fresh history-wise.
      try { frame.setAttribute('src', url); } catch (e) {}
      try { sessionStorage.setItem(STORAGE_KEY, view); } catch (e) {}
    }

    ring.addEventListener('click', function (e) {
      var nav = e.target.closest('.nav-icon');
      if (!nav) return;
      var view = nav.getAttribute('data-view');
      if (!view) return;
      e.preventDefault();
      if (nav.classList.contains('is-active')) return;
      var rotation = rotationForIcon(nav);
      ring.style.setProperty('--nav-rotation', rotation + 'deg');
      setActive(view);
      // Swap source midway through the rotation so the visual lands
      // with the new source already loaded.
      window.setTimeout(function () { loadSource(view); }, Math.round(ROTATION_MS / 2));
    });

    // Resolve initial source: ?source= query param wins, then
    // sessionStorage, then default ('lens' → /publicwhip).
    (function initSource() {
      var params = new URLSearchParams(window.location.search);
      var requested = (params.get('source') || '').toLowerCase();
      var stored = '';
      try { stored = sessionStorage.getItem(STORAGE_KEY) || ''; } catch (e) {}
      var initial = isKnownView(requested) ? requested
                  : isKnownView(stored)    ? stored
                  : 'lens';
      // Snap rotation + active state to the initial source WITHOUT
      // animating, by killing the transition briefly.
      var target = ring.querySelector('.nav-icon[data-view="' + initial + '"]');
      if (target) {
        ring.style.transition = 'none';
        ring.style.setProperty('--nav-rotation', rotationForIcon(target) + 'deg');
        // Force reflow so the no-transition takes effect…
        void ring.offsetHeight;
        ring.style.transition = '';
        setActive(initial);
      }
      // Known first-party views reset the hidden source iframe; inline
      // views such as Global still load explicitly.
      if (SOURCE_FOR_VIEW[initial]) loadSource(initial);
      else activateYourGovSource(initial);
    })();
  })();

  // ── Silent always-on Visualise ──────────────────────────────
  // The visible Visualise toggle was removed for the minimalist launch UI,
  // but downstream logic still keys off body.visualise-active. Set it once
  // at startup and never flip — clicking a division row immediately
  // colours the map without any extra step.
  setVisualise(true);

  // ── Draggable selection-card overlay ────────────────────────
  (function setupDraggableCard() {
    var card = document.getElementById('selection-card');
    var mapWrap = card ? card.closest('.map-wrap') : null;
    if (!card || !mapWrap) return;
    // Selection card is now a hidden off-screen legacy mirror — don't
    // attach drag handlers, don't read/write storage, don't snap.
    if (card.classList.contains('legacy-mirror')) return;

    var POS_KEY = 'sourceLens:cardPos';        // {x, y} in pixels relative to map-wrap
    var COLLAPSE_KEY = 'sourceLens:cardCollapsed';
    var dragging = false;
    var startX = 0, startY = 0, baseLeft = 0, baseTop = 0;
    var pointerId = null;

    function applyPosition(pos) {
      // Clear bottom/right so left/top take effect, then clamp to bounds.
      card.style.right = 'auto';
      card.style.bottom = 'auto';
      var wrapRect = mapWrap.getBoundingClientRect();
      var cardRect = card.getBoundingClientRect();
      var maxX = Math.max(0, wrapRect.width - cardRect.width - 8);
      var maxY = Math.max(0, wrapRect.height - cardRect.height - 8);
      var x = Math.min(Math.max(8, pos.x), maxX);
      var y = Math.min(Math.max(8, pos.y), maxY);
      card.style.left = x + 'px';
      card.style.top = y + 'px';
    }

    function _readClearance(name, fallback) {
      var raw = getComputedStyle(mapWrap).getPropertyValue(name).trim();
      var n = parseInt(raw, 10);
      return isFinite(n) ? n : fallback;
    }

    function snapToNearestCorner() {
      var wrapRect = mapWrap.getBoundingClientRect();
      var cardRect = card.getBoundingClientRect();
      // Reserve space for the bottom control row and the title overlay
      // so the card never overlaps them when snapped to a corner.
      var topClear = _readClearance('--card-top-clear', 56);
      var bottomClear = _readClearance('--card-bottom-clear', 70);
      var cx = (cardRect.left - wrapRect.left) + cardRect.width / 2;
      var cy = (cardRect.top - wrapRect.top) + cardRect.height / 2;
      var midX = wrapRect.width / 2;
      var midY = wrapRect.height / 2;
      var pad = 12;
      var corner = (cy < midY ? 't' : 'b') + (cx < midX ? 'l' : 'r');
      var pos = {
        tl: { x: pad, y: topClear },
        tr: { x: wrapRect.width - cardRect.width - pad, y: topClear },
        bl: { x: pad, y: wrapRect.height - cardRect.height - bottomClear },
        br: { x: wrapRect.width - cardRect.width - pad, y: wrapRect.height - cardRect.height - bottomClear }
      }[corner];
      card.setAttribute('data-corner', corner);
      applyPosition(pos);
      try { localStorage.setItem(POS_KEY, JSON.stringify(pos)); } catch (_) {}
    }

    function restorePosition() {
      try {
        var raw = localStorage.getItem(POS_KEY);
        if (raw) {
          var pos = JSON.parse(raw);
          if (pos && typeof pos.x === 'number' && typeof pos.y === 'number') {
            applyPosition(pos);
            return;
          }
        }
      } catch (_) {}
      // Default: top-right, applied via existing CSS (right:12 top:12).
    }

    function isInteractive(target) {
      return !!(target && target.closest && target.closest('a, button, input, [data-no-drag]'));
    }

    card.addEventListener('pointerdown', function (e) {
      if (isInteractive(e.target)) return;
      if (e.button !== undefined && e.button !== 0) return;
      dragging = true;
      pointerId = e.pointerId;
      card.classList.add('is-dragging');
      var cardRect = card.getBoundingClientRect();
      var wrapRect = mapWrap.getBoundingClientRect();
      baseLeft = cardRect.left - wrapRect.left;
      baseTop  = cardRect.top - wrapRect.top;
      startX = e.clientX;
      startY = e.clientY;
      try { card.setPointerCapture(pointerId); } catch (_) {}
      e.preventDefault();
    });

    card.addEventListener('pointermove', function (e) {
      if (!dragging || e.pointerId !== pointerId) return;
      applyPosition({ x: baseLeft + (e.clientX - startX), y: baseTop + (e.clientY - startY) });
    });

    function endDrag(e) {
      if (!dragging) return;
      dragging = false;
      card.classList.remove('is-dragging');
      try { card.releasePointerCapture(pointerId); } catch (_) {}
      pointerId = null;
      snapToNearestCorner();
    }
    card.addEventListener('pointerup', endDrag);
    card.addEventListener('pointercancel', endDrag);

    // Collapse toggle
    var collapseBtn = document.getElementById('card-collapse');
    function applyCollapsed(on) {
      card.classList.toggle('is-collapsed', !!on);
      if (collapseBtn) collapseBtn.textContent = on ? '+' : '–';
      try { localStorage.setItem(COLLAPSE_KEY, on ? '1' : '0'); } catch (_) {}
      // After width change, re-snap so the card stays inside bounds + at corner.
      setTimeout(snapToNearestCorner, 30);
    }
    if (collapseBtn) {
      collapseBtn.setAttribute('data-no-drag', '');
      collapseBtn.addEventListener('click', function () {
        applyCollapsed(!card.classList.contains('is-collapsed'));
      });
    }

    // Restore persisted state
    try {
      if (localStorage.getItem(COLLAPSE_KEY) === '1') applyCollapsed(true);
    } catch (_) {}
    restorePosition();

    // Keep card inside bounds on resize / orientation change.
    window.addEventListener('resize', function () { snapToNearestCorner(); });
  })();

  // ── Global feasibility crosses overlay (2D map pane) ───────────────
  (function setupGlobalCrossOverlay() {
    var toggle = document.getElementById('global-cross-toggle');
    var overlay = document.getElementById('global-cross-overlay');
    var layer = document.getElementById('global-cross-layer');
    var card = document.getElementById('global-cross-card');
    var nameEl = document.getElementById('gcc-name');
    var statusEl = document.getElementById('gcc-status');
    var summaryEl = document.getElementById('gcc-summary');
    var nextEl = document.getElementById('gcc-next');
    if (!toggle || !overlay || !layer || !card) return;

    var countries = [];
    var on = false;

    function statusText(c) {
      if (c.working_adapter) return 'Completed and live';
      return c.status_label || c.status || 'Unknown';
    }

    function markerClass(c) {
      if (c.working_adapter) return 'live';
      if (c.status === 'green') return 'green';
      if (c.status === 'orange') return 'orange';
      return 'red';
    }

    function project(lon, lat, width, height) {
      var x = ((lon + 180) / 360) * width;
      var y = ((90 - lat) / 180) * height;
      return { x: x, y: y };
    }

    function showCard(c) {
      nameEl.textContent = c.name || 'Country';
      statusEl.textContent = statusText(c);
      summaryEl.textContent = c.summary || '';
      nextEl.textContent = c.next_action || '';
      card.hidden = false;
    }

    function renderMarkers() {
      if (!on || !countries.length) return;
      while (layer.firstChild) layer.removeChild(layer.firstChild);
      var rect = layer.getBoundingClientRect();
      var w = rect.width;
      var h = rect.height;
      countries.forEach(function (c) {
        if (typeof c.lon !== 'number' || typeof c.lat !== 'number') return;
        var p = project(c.lon, c.lat, w, h);
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'global-cross-marker ' + markerClass(c);
        btn.style.left = p.x + 'px';
        btn.style.top = p.y + 'px';
        btn.title = (c.name || 'Country') + ' · ' + statusText(c);
        btn.setAttribute('aria-label', btn.title);
        btn.addEventListener('click', function (e) {
          e.stopPropagation();
          showCard(c);
        });
        layer.appendChild(btn);
      });
    }

    function setOn(next) {
      on = !!next;
      overlay.hidden = !on;
      toggle.classList.toggle('is-on', on);
      if (!on) {
        card.hidden = true;
        return;
      }
      renderMarkers();
    }

    toggle.addEventListener('click', function () { setOn(!on); });
    overlay.addEventListener('click', function () { card.hidden = true; });
    window.addEventListener('resize', function () { if (on) renderMarkers(); });

    fetch('/api/global/feasibility')
      .then(function (r) { return r.json(); })
      .then(function (payload) {
        countries = (payload && payload.countries) || [];
      })
      .catch(function () {
        countries = [];
      });
  })();

  // ── Mobile single-panel toolbar ───────────────────────────────
  // Below 900px the layout stacks both panes. The sticky
  // bottom toolbar lets the user:
  //   • jump between Source and Map
  //   • commit a "Visualise" intent (apply the last source selection
  //     to the map AND jump to map view)
  //   • toggle Explain Mode (delegates to #explain-mode-btn — same
  //     contract the ring 1 wedge uses)
  // Both panes stay visible; this JS manages active state, scroll/focus,
  // and shows toasts.
  (function setupMobileToolbar() {
    var toolbar = document.getElementById('mobile-toolbar');
    var toast = document.getElementById('mobile-toast');
    if (!toolbar) return;

    var MOBILE_BP = 920;
    var MOBILE_MQ = window.matchMedia('(max-width: ' + MOBILE_BP + 'px)');

    function isMobile() { return MOBILE_MQ.matches; }

    function scrollToMobileSection(view) {
      if (!isMobile()) return;
      var target = null;
      if (view === 'source') {
        target = document.querySelector('#yourgov-panel') || document.querySelector('.source-pane');
      } else if (view === 'map' || view === 'visualise') {
        target = document.querySelector('#visualisation-panel') || document.querySelector('.map-pane');
      }
      if (!target) return;
      if (!target.hasAttribute('tabindex')) target.setAttribute('tabindex', '-1');
      target.scrollIntoView({ behavior: 'smooth', block: 'start' });
      if (target.focus) {
        try {
          target.focus({ preventScroll: true });
        } catch (err) {
          target.focus();
        }
      }
    }

    function setView(v, skipScroll) {
      if (v !== 'source' && v !== 'map') return;
      document.body.setAttribute('data-mobile-view', v);
      toolbar.querySelectorAll('.mob-btn[data-mobile-action]').forEach(function (btn) {
        var action = btn.getAttribute('data-mobile-action');
        var matches = (action === 'show-source' && v === 'source') ||
                      (action === 'show-map' && v === 'map');
        btn.classList.toggle('is-active', matches);
        if (action === 'show-source' || action === 'show-map') {
          btn.setAttribute('aria-pressed', matches ? 'true' : 'false');
        }
      });
      if (!skipScroll) scrollToMobileSection(v);
    }

    function applyMQ() {
      var active = isMobile();
      toolbar.hidden = !active;
      if (toast && !active) toast.hidden = true;
      // Ensure desktop never carries the data-mobile-view shadow state
      // (a defensive reset; CSS ignores it above 900px regardless).
      if (!active) document.body.setAttribute('data-mobile-view', 'source');
    }
    applyMQ();
    if (MOBILE_MQ.addEventListener) MOBILE_MQ.addEventListener('change', applyMQ);
    else if (MOBILE_MQ.addListener) MOBILE_MQ.addListener(applyMQ);   // legacy Safari

    // ── Toast ──────────────────────────────────────────────────
    var toastTimer = null;
    function showToast(message, ms) {
      if (!toast) return;
      toast.textContent = message;
      toast.hidden = false;
      clearTimeout(toastTimer);
      toastTimer = window.setTimeout(function () { toast.hidden = true; }, ms || 2200);
    }

    // ── Visualise intent ──────────────────────────────────────
    // The map paints whenever a source row is clicked (handled by
    // bindSameOriginFrame in this same closure). The Visualise pill
    // commits the *navigation* intent — switch to map view and
    // confirm to the user that the map reflects their selection.
    // currentMapData lives in the outer closure (line ~7) and is
    // populated by visualiseDivision; we read it here to know
    // whether anything has been selected yet.
    function hasMapSelection() {
      // The bottom legend strip is the most reliable visible signal
      // that the map has been painted with something. It starts hidden
      // (no [hidden] attr removed until setLegend() is called) and stays
      // visible for the rest of the session once any mode is applied.
      var legend = document.getElementById('map-legend');
      return !!(legend && !legend.hasAttribute('hidden') && legend.children.length > 0);
    }

    function commitVisualise() {
      if (isMobile()) {
        setView('map', true);
        scrollToMobileSection('visualise');
      }
      if (hasMapSelection()) {
        showToast('Showing map for selected record.');
      } else {
        showToast('Map view — pick a record in Source to colour it.');
      }
    }

    // ── Click delegation ─────────────────────────────────────
    toolbar.addEventListener('click', function (e) {
      var btn = e.target.closest('.mob-btn[data-mobile-action]');
      if (!btn) return;
      var action = btn.getAttribute('data-mobile-action');
      if (action === 'show-source') {
        setView('source', true);
        scrollToMobileSection('source');
      } else if (action === 'show-map') {
        setView('map', true);
        scrollToMobileSection('map');
      }
      else if (action === 'visualise') commitVisualise();
      else if (action === 'explain') {
        var explainBtn = document.getElementById('explain-mode-btn');
        if (explainBtn) explainBtn.click();
      }
    });

    // Mirror Explain-Mode on/off state onto the toolbar button so the
    // user always knows whether Explain is active.
    function syncExplainState() {
      if (!document.body) return;
      var on = document.body.classList.contains('explain-mode-on');
      var btn = toolbar.querySelector('.mob-btn[data-mobile-action="explain"]');
      if (btn) btn.setAttribute('aria-pressed', on ? 'true' : 'false');
    }
    syncExplainState();
    var explainObserverTarget = document.body;
    if (explainObserverTarget && explainObserverTarget.nodeType === 1) {
      new MutationObserver(syncExplainState).observe(
        explainObserverTarget, { attributes: true, attributeFilter: ['class'] }
      );
    }
  })();
})();
