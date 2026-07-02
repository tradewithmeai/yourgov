# Security review — NEW YourGov surface (site-metrics, /accessibility, after_request injectors, explain drawer)

Scope: app.py 2740–2945, 1500–1520, 60–110; static/explain-mode.js 40–135, 285–440.
Plus two load-bearing render targets confirmed for the XSS questions: templates/admin_metrics.html (telemetry render) and escHtml in explain-mode.js.

Verdict: **No exploitable vulnerabilities found in the reviewed surface.** All SQL is parameterised, all attacker-influenced output is escaped (server-side Jinja autoescape + client-side textContent/escHtml), the admin token gate uses constant-time compare and fails closed, the postMessage bridge validates origin, and the HTML injectors never embed request-derived bytes. Notes below are confirmations + minor/defence-in-depth observations.

---

## (a) Unauthenticated POST /api/telemetry

### SQL injection — NOT present (confirmed parameterised)
- `_metric_bump` (app.py:2818–2831): UPDATE and INSERT both use `?` placeholders for day/event/dim/key; the COUNT(*) query is a constant string. No string interpolation of user data into SQL.
- `_aggregate_metrics` (app.py:2886–2899): all three SELECTs are constant strings with literal WHERE clauses; no user input concatenated.
- `_resolve_metrics_db` CREATE TABLE (app.py:2793–2797): constant DDL.
- Conclusion: every metrics query is parameterised. No injection vector.

### Stored XSS via attacker-controlled event/path/referrer rendered in admin_metrics.html — NOT present
- Inputs are length-capped and lightly validated: `event` `[:60]` (app.py:2856), `path` stripped of query string and `[:120]` (app.py:2861), `referrer` reduced to host via `_referrer_host` which enforces `re.fullmatch(r"[a-z0-9.-]+", host)` and `[:120]` (app.py:2848–2850) — so the referrer dimension cannot carry markup at all. `event` and `path` are NOT character-restricted, so `<script>`/`"` bytes can be stored.
- However the render target templates/admin_metrics.html emits every attacker-influenced field through Jinja `{{ }}` expressions with default autoescaping (a `.html` template, no `{% autoescape false %}`, no `| safe`): path `{{ path }}` (line 71), referrer `{{ host }}` (82), event name `{{ name }}` (93), plus `{{ m.storage }}` (47). `&<>"'` are HTML-escaped at render. Stored-XSS path is closed at output. Confidence: certain (template inspected).
- Note: the `{{ (count/fmax*100)|round(1) }}` width is from server-computed integer counts, not attacker text — safe.

### Admin-view poisoning / table flooding — bounded, by design
- Distinct-row cap `_METRICS_MAX_ROWS` (default 50000) in `_metric_bump` (app.py:2823–2826) drops brand-new keys once the cap is hit while still incrementing existing rows. This bounds the table against spoofed-key floods. The "top N" aggregation can still be skewed by an attacker bumping arbitrary `event`/`path` strings (e.g. injecting fake pageview paths), but this is cosmetic admin-view noise, not a security boundary, and DoS/flooding is explicitly out of scope. No action required.

### Path / DB-path traversal in _resolve_metrics_db — NOT reachable by request input
- The DB path comes only from `MYGOV_METRICS_DB` env var or hard-coded server-relative candidates (app.py:2777–2786). No request data reaches the path. An operator setting the env var is trusted. No traversal from the network. Confidence: certain.

### Other
- `telemetry()` wraps all DB work in try/except and `pass` (app.py:2864–2876) so a beacon never errors — no info disclosure via exceptions. Returns generic `{"ok": ...}`. Good.

## (b) Admin token gate (/admin/metrics)

- Constant-time compare: `_metrics_authorised` uses `hmac.compare_digest(supplied, _METRICS_TOKEN)` (app.py:2920). Good — no early-exit timing leak on the token.
- Fails closed when unconfigured: `if not _METRICS_TOKEN: return False` (app.py:2917–2918), and the route `abort(404)` on unauthorised (app.py:2927–2928) — 404 not 401, so the endpoint's existence isn't advertised. No bypass: both query `?key=` and `X-Metrics-Token` header funnel through the same compare. Good.
- Response sets `X-Robots-Tag: noindex` and `Referrer-Policy: no-referrer` (app.py:2933–2934). Good.
- Minor (info, not a finding): `compare_digest` on `str` compares the UTF-8 lengths, so token *length* can leak via timing; standard and accepted for this primitive. The `?key=` form can also land in server access logs / browser history — operational, low. No code change needed.

## (c) after_request HTML injectors (feedback link + skip link)

- `_inject_feedback_link` (app.py:90–109): the injected bytes are a **static `bytes` literal** `_FEEDBACK_LINK_SNIPPET` (app.py:73–86). No request-derived value is interpolated into the injected markup — `request.path` is only read to decide *whether* to inject (skip-prefix matching at 93–98), never written into the response. The replace targets the literal `b"</body>"`. No reflected XSS. Confidence: certain.
- Guards are sound: skips non-HTML (`text/html` check + `direct_passthrough`, line 100), skips if already injected (`id="global-feedback-link"` check, 103), skips `/api`, `/static`, `/feedback`, `/map/relay` (87, 94–98). Whole thing is try/except so it can't break a render (106–108).
- The skip-link injector named in the prompt is not present in 60–110 (only the feedback-link injector and the asset-version context processor). Recorded as **unknown to confirm**: a separate skip-link `after_request` injector, if it exists elsewhere, was not in the given range — but the same static-literal pattern would need re-checking there. (Out of assigned range; not read.)

## (d) Explain drawer (explain-mode.js)

### DOM XSS via API/LLM response fields — NOT present
- `renderExplainResponse` (js:329–372): every response field reaches the DOM via **`.textContent`**, not innerHTML —
  - `data.error` → `meaning.textContent` (341)
  - `data.meaning` → `meaning.textContent` (348)
  - `data.does_not_prove` → `dnp.textContent` (351)
  - followup `q` → `chip.textContent` (364)
  These are inert against markup. The only `innerHTML` write here is `chips.innerHTML = ''` (360) — clearing, not injecting. Confidence: certain.
- `openDrawerWithLoading` (js:285–310) is the one place attacker-adjacent text hits innerHTML: the clicked text is wrapped with `escHtml(targetText.slice(0,160))` (js:292). `escHtml` (js:28–30) escapes `& < > "`. The surrounding static markup contains no attribute context where an unescaped `'` would break out (the escaped text sits in element content, not an attribute). Safe. Confidence: certain.
  - Minor (info): `escHtml` does not escape `'`. Not exploitable here because the value is placed in element text content, not a single-quoted attribute. If this helper is ever reused inside a `'...'` attribute it would be unsafe — but no such use in the reviewed range.
- The drawer scaffold innerHTML (js:77–89, 289–305) is all static string literals — no request/response data. Safe.

### postMessage origin validation — present and correct
- `setupIframeBridge` (js:120–130): `if (event.origin !== window.location.origin) return;` (js:125) before processing, plus a message-type check `event.data.type !== 'yourgov:explain-mode'` (126). Only effect of an accepted message is toggling a CSS class (`explain-mode-on`, 128) — no data is rendered from the message. Cross-origin frames cannot drive it. Confidence: certain.

### Note
- `callExplainAPI` (js:420–434) POSTs JSON to `/api/explain-selection` same-origin; response handling shown (435–440) stores `data.meaning` into `lastPriorExplanation` (a string carried back to the server as conversation history) — server-side trust of that field is in `/api/explain-selection` which is **outside the assigned range**. Recorded as **unknown to confirm**: whether the server safely handles client-supplied `prior_explanation`/`messages` (prompt-injection / unescaped reflection) was not reviewed (route not in scope).

---

## Unknowns to confirm (outside assigned ranges — not read)
1. The skip-link `after_request` injector (prompt mentioned it; not in app.py:60–110). If a separate injector exists, re-verify it embeds no request-derived bytes.
2. `/api/explain-selection` server handler — treatment of client-supplied `messages` / `prior_explanation` / `followup_question` (reflected/stored handling, LLM prompt-injection). Not in scope.
3. `.agentwork/templates/admin_metrics.html` is a second copy of the admin template (Glob found it); only `templates/admin_metrics.html` (the live render target) was inspected.
