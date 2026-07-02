# Security review — YourGov new surface

## Verdict

**No exploitable vulnerabilities found.** Every surface returned `no_exploitable_vuln`, and zero candidate findings survived adversarial verification (candidate_count = 0, confirmed_findings = 0).

---

## Confirmed vulnerabilities

**None.** No candidate finding survived adversarial verification, so there are no confirmed vulnerabilities to report. Every issue surfaced during probing was either fully mitigated by an existing defense or fell into an explicitly out-of-scope class (denial-of-service, resource/cost exhaustion, prompt-injection, and non-attacker-reachable robustness bugs) — see "Adversarial probes attempted" below.

---

## Defenses confirmed (per surface)

### Surface 1 — Unauthenticated `POST /api/telemetry` + metrics storage
`_resolve_metrics_db`, `_metrics_conn`, `_metric_bump`, `_referrer_host`, `telemetry`, `_aggregate_metrics`, `_metrics_authorised`, `admin_metrics` (app.py ~2754–2947) and `templates/admin_metrics.html`.

- **SQL injection fully prevented in all metrics queries.** `_metric_bump` UPDATE (app.py:2821–2825) and INSERT OR IGNORE (app.py:2830–2834) bind `(day,event,dim,key)` as `?` parameters; `SELECT COUNT(*)` (app.py:2827) and all three `_aggregate_metrics` SELECTs (app.py:2896–2909) are static SQL with literal predicates; `CREATE TABLE` (app.py:2796–2800) is static. No attacker value is concatenated into SQL text; no second-order SQLi (stored `event`/`path` are only returned via GROUP BY, never re-spliced); `day` is server-derived (app.py:2873).
- **Stored/reflected XSS neutralized by Jinja autoescaping.** `event` and `path` are stored unrestricted but every stored value is rendered via autoescaped `{{ }}` with no `|safe`: `{{ path }}` (admin_metrics.html:71), `{{ host }}` (:82), `{{ name }}` (:93), `{{ m.storage }}` (:47). Grep of app.py for autoescape/render_template_string/`|safe`/Markup found only `app = Flask(__name__)` (app.py:31), so Flask's default `.html` autoescaping is in force. `telemetry` reflects nothing — returns `jsonify({'ok':True})` (app.py:2887).
- **Referrer column is charset-restricted.** `_referrer_host` (app.py:2837–2853) lowercases `urlparse(raw).hostname` and requires `re.fullmatch(r'[a-z0-9.-]+', host)`, stripping any HTML metacharacters before storage and dropping same-origin/junk hosts.
- **DB path is not reachable from request input** (no path traversal / arbitrary DB path). `_resolve_metrics_db` (app.py:2774–2806) uses only the operator env var `MYGOV_METRICS_DB` and hard-coded paths relative to `__file__` / `/tmp`; it runs once at import time (app.py:2809). `_metrics_conn` always opens the fixed `_METRICS_DB` (app.py:2812–2815).
- **Admin read side is auth-gated with constant-time comparison.** `_metrics_authorised` (app.py:2928–2932) returns False when the token is unset and otherwise uses `hmac.compare_digest` on `?key=` / `X-Metrics-Token`; `admin_metrics` `abort(404)`s on failure (app.py:2939–2940).
- **No production info disclosure via errors.** Telemetry DB work is wrapped in `try/except Exception: pass` returning generic `{'ok':True}` (app.py:2874–2887); `_aggregate_metrics` swallows exceptions (app.py:2893–2913); `app.run(debug=False)` (app.py:3420) plus WSGI deploy means no traceback is returned.

### Surface 2 — Admin gate + `admin_metrics.html` render
`_metrics_authorised` / `admin_metrics` (app.py:2928–2947) and `templates/admin_metrics.html`.

- **Auth token compared in constant time (not `==`).** `return hmac.compare_digest(supplied, _METRICS_TOKEN)` (app.py:2932) — no byte-by-byte timing oracle.
- **Auth gate fails closed when unconfigured.** `if not _METRICS_TOKEN: return False` (app.py:2929–2930); `_METRICS_TOKEN` defaults to `''` (app.py:2766), so the endpoint is dark until an operator sets `MYGOV_METRICS_TOKEN`. No blank/default-token bypass.
- **Endpoint existence not advertised.** `if not _metrics_authorised(): abort(404)` (app.py:2939–2940) returns 404 (identical to a missing route), not 401/403; success sets `X-Robots-Tag` and `Referrer-Policy` (app.py:2945–2946).
- **Template autoescapes every attacker-influenced field (no stored XSS).** `render_template('admin_metrics.html', ...)` (app.py:2944) uses Flask's default Jinja autoescape for `.html`. Whole-template read: no `{% autoescape false %}`, no `|safe`/`|raw`/Markup, no `{% extends/include %}`. `event` (`{{ name }}` :93) and pageview `path` (`{{ path }}` :71) are attacker-controlled via the unauthenticated POST (app.py:2866,2871) but emitted in HTML text context and thus escaped.
- **Only attribute-context expression is numeric, not attacker string.** `style="width: {{ (count / fmax * 100) | round(1) }}%"` (admin_metrics.html:58); `count` coerced to int in `_aggregate_metrics` (`int(c or 0)`, app.py:2899/2904/2909). No attribute break-out.
- **Referrer host regex-whitelisted before storage.** `re.fullmatch(r'[a-z0-9.-]+', host)` (app.py:2851), so `{{ host }}` (:82) cannot contain `< > " '` regardless of escaping.
- **All metric SQL is parameterised** (app.py:2821–2834 and 2896–2909); no string concatenation into SQL.
- **JSON branch returns non-HTML content type.** `if request.args.get('format')=='json': return jsonify(agg)` (app.py:2942–2943) — `application/json`, no HTML/JS execution context.

### Surface 3 — `after_request` HTML injectors
`_inject_feedback_link`, `_inject_skip_link` (app.py ~78–168), plus `_FEEDBACK_LINK_SNIPPET`, `_SKIP_LINK_SNIPPET`, `_BODY_OPEN_RE`, `_MAIN_NO_ID_RE`.

- **Both injected snippets are fully static, immutable byte-literal constants** with no request-data path into them. `_FEEDBACK_LINK_SNIPPET` (app.py:88–101) and `_SKIP_LINK_SNIPPET` (app.py:132–140) are module-level `b'...'` concatenations, only read never rebuilt (app.py:88,120,132,163). Feedback insert = `body.replace(b'</body>', _FEEDBACK_LINK_SNIPPET + b'</body>', 1)` (app.py:120).
- **The skip-link regex `\1` backreference reinserts only server-generated response bytes, not request input.** `_MAIN_NO_ID_RE = rb'<main\b(?![^>]*\bid=)([^>]*)>'` (app.py:144); sub template `rb'<main id="main-content"\1>'` (app.py:162). Group 1 captures the existing `<main>` tag's attributes from the already-rendered `body` and re-emits them verbatim; `re.sub` inserts captured bytes literally without re-templating. Line 163 likewise re-emits `m.group(0)` (the matched `<body>` tag) plus the fixed constant.
- **`request.path` is a skip/no-skip decision input only and is never written into the response.** `path = request.path or ''` (app.py:108,150) is consumed solely inside `any(...)`/`startswith` guards (app.py:109–113,151–153); never concatenated into `body`, a snippet, or a header. Neither handler reads `request.args`/headers/form/cookies.
- **Injection is gated to HTML, non-passthrough responses and wrapped in fail-safe `try/except`.** `text/html` Content-Type + `not response.direct_passthrough` checks (app.py:114–116,154–156); `try/except` returns the untouched response on any error (app.py:121–123,165–167); idempotency guards (app.py:118,158,161).

### Surface 4 — Explain drawer client (`static/explain-mode.js`, IIFE, 506 lines)

- **All server/LLM response data reaches the DOM only via `textContent`, never `innerHTML`.** `data.error` (L341), `data.meaning` (L348, L484), `data.does_not_prove` (L351), and each `data.followups` entry as `chip.textContent` (L364) — response fields cannot inject markup.
- **Click/user data placed into `innerHTML` is HTML-escaped in text-content context.** `targetText` via `escHtml` (L292) inside `<div>...</div>`; follow-up input `q` via `escHtml` (L461) inside `<div>...</div>`; `escHtml` (L29) escapes `& < > "` — the required `<` and `&` plus defensive `>` and `"`.
- **Both `postMessage` receivers validate `event.origin` against same origin before acting.** `if (event.origin !== window.location.origin) return;` (L125, iframe bridge; L230, parent ctx handler).
- **All `postMessage` sends use an explicit same-origin `targetOrigin`, never a wildcard.** `window.parent.postMessage(..., window.location.origin)` (L140); `sf.contentWindow.postMessage(..., window.location.origin)` (L167, L182).
- **An accepted `postMessage` cannot inject DOM or escalate.** The iframe handler only sets boolean `explainModeOn` and toggles a CSS class (L127–128); the parent handler routes `ctx.target_text` through the escaped `openDrawerWithLoading` path (L236) and POSTs `ctx` to a static endpoint.
- **No dangerous dynamic sinks.** `fetch` target is the static same-origin path `/api/explain-selection` (L430, L466); no `eval`/`Function`/`document.write`; `source_links` are read from anchors and only sent to the API, never assigned to `href`/`src`/`location`.

### Surface 5 — `POST /api/explain-selection` server handler
app.py:1005–1176 + helpers `_client_ip`/`_explainer_fallback`/`_explainer_cache_get`/`_explainer_cache_put`/`_explainer_budget_reserve` and `explainer_context.py`.

- **Complete type coercion + caps on every client field; malformed body degrades to `{}`.** Non-dict body → `{}` (app.py:1007–1009); `_s()` (1015–1016); `target_text[:300]` (1018), `surrounding[:400]` (1019), `source_links` string-filtered+`[:5]` (1021), `metadata` dict-checked (1022–1024), `level` bool-rejected and constrained to `(0,1,2,3)` (1028–1031) so `_LEVEL_NAMES[level]` cannot KeyError.
- **Client cannot inject a system/tool/developer role into the model message array.** `normalise_history` (explainer_context.py:397) keeps only `role in (user,assistant)` with str content, capped 1200 chars, last 8; the handler prepends its own system prompt (app.py:1143–1145).
- **Cross-user cache poisoning prevented by full-context cache-key binding.** `is_cacheable_turn` (explainer_context.py:327–333) caches only fresh opening turns; the key binds `level, explain_type, division_id, division_fp, member_id, target_text, surrounding, source_links, url` (app.py:1105–1109) via injective JSON+SHA-256 (`selection_cache_key`:336–348); `member_id` `str(int())`-coerced (1101–1104); `explain_type` collapsed to a fixed set (359–365). Any injected text changes the key, so it cannot land on a victim's entry.
- **No SSRF: no client-supplied URL/host/protocol is fetched.** `url` and `source_links` are only concatenated into the prompt/cache key (app.py:1050–1056); grounding docs come from a fixed allow-list (explainer_context.py:38–41,46–69); the only outbound call is to OpenAI with a fixed model env (1146–1151).
- **No SQL injection: all statements parameterized, `division_id`/`member_id` integer-coerced.** `build_division_summary` parameterized (explainer_context.py:139–157); budget/cache get+put parameterized (app.py:940–951,954–973); `_division_id_from_metadata` `int()`-coerces (830–847); read-only connection for the division path (pw_conn/get_publicwhip_conn 363–370,392–398).
- **No server-side reflected/stored XSS on this route.** All responses are `jsonify()` `application/json`: static 400 (1034), fallback envelope (1076/1135/1139/1169), cached payload (1121), model result (1165); no client text rendered into an HTML template server-side.
- **No path traversal from request input.** `load_grounding_docs` iterates a hard-coded `_DOC_FILES` tuple relative to the module dir (explainer_context.py:46–69); `division_id` is an int DB parameter, never a filename.

### Surface 6 — `explainer_context` prompt/cache/history helpers
`assemble_system_prompt`, `is_cacheable_turn`, `selection_cache_key`, `normalise_explain_type`, `sliding_window_allow`, `normalise_history` (explainer_context.py ~250–404) + caller app.py:1005–1176.

- **`normalise_history` blocks role injection via strict allowlist.** `if role not in ("user","assistant") or not isinstance(content, str): continue` (explainer_context.py:397); the emitted dict (line 402) reuses the already-validated role, so a client cannot inject `system`/`tool`/`developer`. In app.py:1143–1145 history sits between a fixed system message and the current user turn, so it can never override the system prompt.
- **`selection_cache_key` is injective (no cross-user cache poisoning).** `json.dumps([VERSION]+[str(p) for p in parts])` then SHA-256 (explainer_context.py:347). JSON array-of-strings serialisation is unambiguous (defeats `|`-join boundary collisions), fixed positions prevent cross-slot collisions, and SHA-256 collisions are infeasible. The key (app.py:1105–1109) binds every attacker-influenced prompt input; the only other inputs are the DB-derived division summary (keyed by `division_id` + aye/no fingerprint) and static grounding docs, and `turn_index` is always 0 for a cacheable turn.
- **Cache key cannot carry SQL injection downstream.** `_explainer_cache_get/put` (app.py:954–973) use parameterised binds (`WHERE key=?`, `VALUES(?,?,?)`); the key is always a 64-char SHA-256 hex digest regardless.
- **`assemble_system_prompt` does not let untrusted text reach a code/query/path/redirect sink.** explainer_context.py:267–324 appends `click_context` and `division_summary_text` as plain `\n\n`-joined sections into one LLM-prompt string; no eval/exec, no SQL build, no filesystem/redirect use. `build_division_summary` uses parameterised queries (explainer_context.py:139–157).
- **`normalise_explain_type` bounds client input to a fixed set.** Maps to division/vote/mp else `other`; non-str → `other` (explainer_context.py:364–365) — no injection, bounded cache cardinality.

---

## Adversarial probes attempted (no reportable finding)

### In-scope probes that found no vulnerability
- **SSRF via referrer field** (S1): `_referrer_host` only parses out a hostname string for storage; nothing fetches the URL. No outbound request.
- **Analytics data poisoning** (S1): attacker can inflate counters / inject arbitrary `event`/`path` strings, but this is integrity-only on a first-party dashboard, values are escaped on render, and there is no code-exec/auth/exfil primitive.
- **XSS via telemetry `event` name / pageview `path` / referrer `host` / bar-width `style`** (S1, S2): escaped by Jinja default autoescape (`{{ name }}` :93, `{{ path }}` :71); referrer blocked upstream by `re.fullmatch(r'[a-z0-9.-]+')` (app.py:2851); the style expression is purely numeric (app.py:2899/2904/2909). No breakout.
- **Auth bypass via empty token / or-fallback** (S2): `compare_digest('', non-empty)` is False; unconfigured returns False before compare. Fails closed.
- **Backreference byte-smuggling through `\1` in `_inject_skip_link`** (S3): group 1 derives from server-rendered `<main>` attributes, not request input; `re.sub` inserts verbatim without re-templating.
- **`request.path` reflection into response body/snippet/header** (S3): decision-only (app.py:108,150); never reflected.
- **Skip-prefix bypass** (S3): only affects *whether* a fixed static snippet is injected; injected bytes are constant, so no XSS.
- **Backreference parse ambiguity (`\1>` vs `\10`) / double-injection** (S3): `\1>` parses as group 1 then literal `>`; idempotency guards prevent re-injection.
- **`<img onerror>`/`<script>` into LLM/server response fields** (`data.meaning`/`does_not_prove`/`error`/`followups[]`, S4): rendered inert — all `textContent` (L341,348,351,364,484).
- **Break out of the `escHtml`'d `innerHTML` insertions** with `target_text`/follow-up `q` (S4): text-content context (L292, L461) where only `<` and `&` matter; both escaped. Missing single-quote escaping is irrelevant outside attribute context.
- **Forge a cross-origin `postMessage`** to toggle explain mode / feed a malicious `ctx` (S4): blocked by `event.origin === window.location.origin` (L125, L230); accepted `ctx.target_text` is escaped before insertion.
- **Inject a `system`/`tool`/`developer` role via the client `messages[]` array** (S5, S6): dropped by the `normalise_history` allowlist (explainer_context.py:397); app.py rebuilds the list with the system prompt fixed first.
- **SQL injection via `metadata.division_id` / `member_id` / `yourgov_state.selected_division.division_id`** (S5): all `int()`-coerced before use; queries parameterized.
- **Cache-key collision → serve attacker's crafted answer to a later user** (S6): not achievable — the key JSON-encodes all attacker-controlled prompt inputs and is SHA-256 hashed; the prior weaker key (member + free-text omitted) is already fixed (app.py:1091–1098).
- **SQL injection via the cache key** (S6): all queries parameterised and the key is a hex digest.

### Out-of-scope probes (recorded, excluded by category)
These were exercised but fall into DoS / resource-and-cost exhaustion / prompt-injection / non-attacker-reachable robustness classes that are outside the reportable scope of this review:
- **Type-confusion 500 on `event` non-str** (S1, app.py:2866): unhandled `AttributeError` → generic 500; per-request crash (DoS). `debug=False` (app.py:3420) yields no traceback.
- **Distinct-row flood** to bloat `metric_counts` (S1): bounded by `_METRICS_MAX_ROWS` (default 50000, app.py:2771). Resource exhaustion.
- **Non-ASCII `?key=` `TypeError` → 500** instead of 404 (S2): errors *closed* (no access granted); weak route-exists/token-configured leak in the DoS/error class.
- **ReDoS / linear regex cost** over every HTML response body (S3): DoS, out of scope.
- **X-Forwarded-For spoof to evade per-IP rate limits** (S5, S6, app.py:926–933): confirmed spoofable; rate-limit bypass only, backstopped by the persisted global daily budget (app.py:1138).
- **Cache-miss flood / uncapped `url` field to inflate OpenAI cost** (S5): bounded by per-IP windows (1128–1135) + global daily budget (1138). Cost/DoS.
- **Grow `_EXPLAINER_IP_STORE` via spoofed XFF (memory exhaustion)** (S5): bounded by `_prune_ip_store` (913–923) + `_EXPLAINER_IP_STORE_CAP`. DoS.
- **Prompt injection via `target_text`/`surrounding`/`source_links` / section-boundary breakout in `assemble_system_prompt`** (S5, S6): out-of-scope class; additionally cannot poison another user's cache entry because injected text alters the cache key.

---

## Residual unknowns

- **Flask/Jinja2 runtime version not pinned-verified in this review** (S2). The no-XSS conclusion relies on Flask's long-standing default of autoescaping `.html` templates, consistent across all modern Flask versions and corroborated by the absence of any autoescape override in app.py (only `Flask(__name__)` at app.py:31).
- **Whether `MYGOV_METRICS_TOKEN` is guaranteed ASCII in production** (S2). A non-ASCII operator-set token would break `hmac.compare_digest` for all requests — operator config, outside the request-driven attack surface.
- **Whether any upstream route handler renders unescaped request input into the HTML response body** (S3). Outside this surface's scope; the two `after_request` injectors neither introduce nor amplify such reflection (the `\1` backreference only preserves bytes already present in the response).
- **Server-side page markup feeding `el.innerText` (`target_text`/`surrounding_text`) or `[data-explainable]` attributes** (S4). A server-side templating concern not decidable from `explain-mode.js`; even if attacker-influenced, this client escapes or `textContent`s it before display.
- **Server-side handling/sanitisation of the POSTed `ctx` and `source_links` at `/api/explain-selection`** (S4) — covered instead by Surfaces 5/6, which found it type-coerced, capped, and parameterized.
- **Client-side rendering of the returned JSON in the explainer drawer** (S5) — a separate template/JS surface, covered by Surface 4 (all `textContent`/escaped).
- **Non-security cache-staleness edge** (S6): the division fingerprint captures only aye/no totals, so a DB correction that changes party breakdown/rebels without changing totals could serve a stale cached summary. Requires DB write access, not attacker-reachable, not in scope.

---

## Scope + method

Reviewed at **HEAD 43cd9c2** across the new surface (telemetry/metrics storage, admin gate + template, `after_request` HTML injectors, explain-drawer client, `/api/explain-selection` handler, `explainer_context` helpers). Independent per-surface review followed by an adversarial confirmation pass; result **0 candidates / 0 confirmed findings**.
