# YourGov Guided Route Streamlining Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Streamline the existing YourGov journey so users can enter from the global map, find an MP, see that MP's division voting record in the left panel, single-click a division to colour the map, double-click/open the summary, and use Explain Mode with the selected context.

**Architecture:** Keep the current two-panel product shell and internal `/source-lens` route. Add one backend endpoint for MP-scoped vote history, reuse the existing selected-division map endpoint, and update `panel_test.js` to render MP voting records in the YourGov left panel while preserving the map on the right. Enrich Explain Mode through parent-page selected-state metadata rather than introducing a new chat architecture.

**Tech Stack:** Flask, SQLite, Jinja templates, vanilla JavaScript, CSS, pytest.

---

## File Structure

- Modify `app.py`
  - Add postcode-aware `/api/mps/search` behaviour.
  - Add `/api/lens/mp/<member_id>/votes` for MP-scoped division rows.
  - Include selected MP/division metadata in `/api/explain-selection` prompt context.
- Modify `templates/panel_test.html`
  - Replace public "Source Lens" journey copy with "YourGov" route copy.
  - Update search label and placeholder.
  - Add compact map-context hint copy.
- Modify `static/panel_test.js`
  - Track `selectedMP`.
  - Render MP vote history in the left panel.
  - Add division-row single-click and double-click/open-summary behaviour.
  - Add explicit row action labels.
  - Add selected MP/division/mode context to Explain Mode payloads.
- Modify `static/panel_test.css`
  - Style MP record header, vote chips, selected row state, and action labels.
  - Re-enable visible search results for the YourGov left-panel search only.
- Modify `static/explain-mode.js`
  - Merge page-level YourGov context into click context payloads when available.
- Modify `tests/test_search_and_counts.py`
  - Cover postcode-backed `/api/mps/search`.
  - Cover `/api/lens/mp/<member_id>/votes`.
- Modify `tests/test_yourgov_source_lens_ui.py`
  - Cover public copy, search copy, MP record JS, click/double-click handlers, and explainer context.
- Modify `tests/test_yourgov_branding.py` if public route expectations need copy alignment.

## Task 1: Backend Vote History And Postcode Search

**Files:**
- Modify: `tests/test_search_and_counts.py`
- Modify: `app.py`

- [x] **Step 1: Write failing backend tests**

Add these tests to `tests/test_search_and_counts.py`:

```python
def test_api_mps_search_returns_postcode_match(monkeypatch):
    appmod = _appmod()
    appmod.app.config["TESTING"] = True
    client = appmod.app.test_client()

    def fake_lookup(query):
        assert query == "SW1A 1AA"
        return {
            "constituency": "Tottenham",
            "mp": {"id": 206, "name": "David Lammy", "party": "Labour"},
        }

    monkeypatch.setattr(appmod, "_lookup_postcode_mp", fake_lookup)

    response = client.get("/api/mps/search?q=SW1A%201AA")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["results"][0] == {
        "id": 206,
        "name": "David Lammy",
        "party": "Labour",
        "constituency": "Tottenham",
        "match_type": "postcode",
    }
```

Add this test to the same file:

```python
def test_lens_mp_votes_returns_mp_scoped_division_history():
    appmod = _appmod()
    appmod.app.config["TESTING"] = True
    client = appmod.app.test_client()

    response = client.get("/api/lens/mp/5362/votes?limit=5")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["mp"]["member_id"] == 5362
    assert payload["mp"]["name"]
    assert payload["mp"]["constituency"]
    assert 1 <= len(payload["divisions"]) <= 5
    first = payload["divisions"][0]
    assert {
        "division_id",
        "title",
        "date",
        "vote",
        "aye_count",
        "no_count",
        "source_url",
        "summary_url",
    }.issubset(first)
    assert first["source_url"].startswith("/publicwhip/division/")
    assert first["summary_url"].startswith("/publicwhip/division/")
```

- [x] **Step 2: Run backend tests and verify they fail**

Run:

```powershell
py -3.12 -m pytest tests\test_search_and_counts.py::test_api_mps_search_returns_postcode_match tests\test_search_and_counts.py::test_lens_mp_votes_returns_mp_scoped_division_history -q
```

Expected:

- postcode test fails because search results do not include `match_type`;
- MP votes test fails because `/api/lens/mp/<member_id>/votes` does not exist.

- [x] **Step 3: Implement postcode search result support**

In `app.py`, update `/api/mps/search` so postcode-looking queries call `_lookup_postcode_mp(q)` before ranked text search. If a match exists, return a single result:

```python
postcode_match = _lookup_postcode_mp(q)
if postcode_match and postcode_match.get("mp"):
    mp = postcode_match["mp"]
    return jsonify(results=[{
        "id": mp.get("id"),
        "name": mp.get("name") or "",
        "party": mp.get("party") or "",
        "constituency": postcode_match.get("constituency") or "",
        "match_type": "postcode",
    }])
```

Also add `"match_type": "text"` to existing local and Parliament search results.

- [x] **Step 4: Implement MP vote-history endpoint**

In `app.py`, add:

```python
@app.route("/api/lens/mp/<int:member_id>/votes")
def api_lens_mp_votes(member_id):
    limit = request.args.get("limit", default=100, type=int)
    limit = max(1, min(limit or 100, 200))
    conn = get_publicwhip_conn()
    mp = conn.execute(
        "SELECT member_id, name, party, constituency FROM members WHERE member_id=?",
        (member_id,),
    ).fetchone()
    if not mp:
        conn.close()
        return jsonify({"ok": False, "error": "MP not found in YourGov data."}), 404

    rows = conn.execute(
        """
        SELECT division_id, title, division_date, voted_aye, aye_count, no_count
        FROM votes
        WHERE member_id=?
        ORDER BY division_date DESC, division_id DESC
        LIMIT ?
        """,
        (member_id, limit),
    ).fetchall()
    conn.close()

    return jsonify({
        "ok": True,
        "mp": {
            "member_id": mp["member_id"],
            "name": mp["name"],
            "party": mp["party"] or "",
            "constituency": mp["constituency"] or "",
        },
        "divisions": [
            {
                "division_id": row["division_id"],
                "title": row["title"] or "Untitled division",
                "date": (row["division_date"] or "")[:10],
                "vote": _vote_label(row["voted_aye"]),
                "voted_aye": row["voted_aye"],
                "aye_count": row["aye_count"] or 0,
                "no_count": row["no_count"] or 0,
                "source_url": f"/publicwhip/division/{row['division_id']}",
                "summary_url": f"/publicwhip/division/{row['division_id']}",
            }
            for row in rows
        ],
    })
```

- [x] **Step 5: Run backend tests and verify they pass**

Run:

```powershell
py -3.12 -m pytest tests\test_search_and_counts.py -q
```

Expected: all tests in the file pass.

## Task 2: Public YourGov Copy And Static UI Contracts

**Files:**
- Modify: `tests/test_yourgov_source_lens_ui.py`
- Modify: `templates/panel_test.html`
- Modify: `static/panel_test.js`
- Modify: `static/panel_test.css`

- [x] **Step 1: Write failing UI contract tests**

Add these tests to `tests/test_yourgov_source_lens_ui.py`:

```python
def test_yourgov_guided_route_public_copy_replaces_source_lens_journey_copy():
    html = _source_lens_html()

    assert "<title>YourGov</title>" in html
    assert "Find your MP. Click a vote to colour the national map. Double click for the division summary." in html
    assert "Search by postcode, constituency, or MP name" in html
    assert "e.g. SW1A 1AA, Tottenham, or David Lammy" in html
    assert "YourGov Source Lens" not in html
    assert "First-party source lens" not in html
```

Add:

```python
def test_panel_js_renders_mp_voting_record_with_single_and_double_click_actions():
    js = _panel_js()

    assert "var selectedMP" in js
    assert "async function loadMPVotingRecord" in js
    assert "function renderMPVotingRecord" in js
    assert "/api/lens/mp/" in js
    assert "Click to map" in js
    assert "Double click for summary" in js
    assert "addEventListener('dblclick'" in js
    assert "openDivisionSummary" in js
```

Add:

```python
def test_explain_context_includes_yourgov_selected_state():
    js = _panel_js()
    explain_js = (ROOT / "static" / "explain-mode.js").read_text(encoding="utf-8")

    assert "function getYourGovExplainState" in js
    assert "selected_mp" in js
    assert "selected_division" in js
    assert "active_map_mode" in js
    assert "window.__YOURGOV_EXPLAIN_STATE__" in js
    assert "__YOURGOV_EXPLAIN_STATE__" in explain_js
```

- [x] **Step 2: Run UI tests and verify they fail**

Run:

```powershell
py -3.12 -m pytest tests\test_yourgov_source_lens_ui.py::test_yourgov_guided_route_public_copy_replaces_source_lens_journey_copy tests\test_yourgov_source_lens_ui.py::test_panel_js_renders_mp_voting_record_with_single_and_double_click_actions tests\test_yourgov_source_lens_ui.py::test_explain_context_includes_yourgov_selected_state -q
```

Expected: tests fail because copy, MP record functions, double-click handler, and explain-state export are missing.

- [x] **Step 3: Update public copy in `templates/panel_test.html`**

Change:

```html
<title>YourGov Source Lens</title>
```

to:

```html
<title>YourGov</title>
```

Change the map title:

```html
YourGov Source Lens Map
```

to:

```html
YourGov map
```

Change left-panel header copy to:

```html
<p class="eyebrow">YourGov UK</p>
<h1>YourGov</h1>
<p class="source-lens-subtitle">Find your MP. Click a vote to colour the national map. Double click for the division summary.</p>
```

Change search label and placeholder to:

```html
<label class="source-select-label" for="mp-search-input">Search by postcode, constituency, or MP name</label>
...
placeholder="e.g. SW1A 1AA, Tottenham, or David Lammy"
```

Change division list header copy:

```html
<p class="eyebrow">MP voting record</p>
```

- [x] **Step 4: Add CSS for MP record and actions**

Add rules in `static/panel_test.css`:

```css
.mp-record-header {
  display: grid;
  gap: 4px;
  padding: 12px 14px;
  border: 1px solid rgba(125, 211, 252, 0.18);
  border-radius: 12px;
  background: rgba(2, 6, 23, 0.35);
  margin-bottom: 10px;
}

.mp-record-title {
  margin: 0;
  color: var(--text);
  font-size: 15px;
  line-height: 1.25;
}

.mp-record-meta,
.division-row-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  color: var(--muted);
  font-size: 11px;
}

.division-row-vote {
  font-weight: 800;
}

.division-row-vote.aye { color: var(--aye); }
.division-row-vote.no { color: var(--no); }
.division-row-vote.unknown { color: var(--unknown); }

.division-row-action {
  border: 1px solid rgba(125, 211, 252, 0.18);
  border-radius: 999px;
  padding: 2px 7px;
  color: #bae6fd;
  background: rgba(56, 189, 248, 0.08);
}
```

Remove or narrow the global `#search-results { display: none !important; }` override so left-panel search results can display. Keep `.map-search .search-results` hidden if needed.

- [x] **Step 5: Run UI tests and verify copy tests pass**

Run:

```powershell
py -3.12 -m pytest tests\test_yourgov_source_lens_ui.py::test_yourgov_guided_route_public_copy_replaces_source_lens_journey_copy -q
```

Expected: pass.

## Task 3: MP Voting Record Rendering And Division Actions

**Files:**
- Modify: `static/panel_test.js`

- [x] **Step 1: Add selected-state globals**

Near existing state variables, add:

```javascript
var selectedMP = null;
```

- [x] **Step 2: Add explain-state helper**

Add:

```javascript
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
```

- [x] **Step 3: Add `renderMPVotingRecord`**

Add a function that clears `sourceLensList`, inserts an MP header, then creates `.division-row` elements. Each row must include `data-division-id`, `data-member-id`, `data-explainable`, `data-explain-type="vote"`, `data-source-url`, title, date, vote, counts, and action chips.

The row text must include:

```javascript
'Click to map'
'Double click for summary'
```

- [x] **Step 4: Add `loadMPVotingRecord`**

Add:

```javascript
async function loadMPVotingRecord(mp) {
  if (!mp || !mp.id) return;
  selectedMP = {
    member_id: parseInt(mp.id, 10),
    name: mp.name || '',
    party: mp.party || '',
    constituency: mp.constituency || ''
  };
  lastSourceMP = selectedMP;
  setStatus('Loading voting record for ' + selectedMP.name + '...', 'ok');
  var response = await fetch('/api/lens/mp/' + encodeURIComponent(selectedMP.member_id) + '/votes?limit=100');
  var payload = await response.json();
  if (!response.ok || !payload.ok) throw new Error(payload.error || 'Could not load this MP voting record');
  selectedMP = payload.mp;
  lastSourceMP = payload.mp;
  renderMPVotingRecord(payload);
  setStatus('Voting record loaded. Click a division to colour the map.', 'ok');
}
```

- [x] **Step 5: Route search selection through `loadMPVotingRecord`**

Update `selectSearchMP(item)` and the Enter-key path for `_topSuggestion` so they call `loadMPVotingRecord(...)` instead of loading `/mp/<id>` into the source iframe.

- [x] **Step 6: Add summary opener**

Add:

```javascript
function openDivisionSummary(row) {
  if (!row) return;
  var url = row.dataset.summaryUrl || row.dataset.sourceUrl;
  if (!url) return;
  openInSourcePane(url);
  setStatus('Opened division summary for the selected vote.', 'ok');
}
```

- [x] **Step 7: Update division row listeners**

Update `sourceLensList` listeners:

- `click` on `.division-row` maps the selected division.
- `dblclick` on `.division-row` calls `openDivisionSummary(row)`.
- `click` on `.division-row-source` calls `openDivisionSummary(row)` and prevents default.
- `Enter` maps.
- `Shift+Enter` or `o` opens summary.

- [x] **Step 8: Run UI static tests**

Run:

```powershell
py -3.12 -m pytest tests\test_yourgov_source_lens_ui.py -q
```

Expected: pass.

## Task 4: Explain Mode Context Enrichment

**Files:**
- Modify: `static/explain-mode.js`
- Modify: `app.py`
- Test: `tests/test_yourgov_source_lens_ui.py`

- [x] **Step 1: Merge page-level state in `collectContext`**

In `static/explain-mode.js`, after metadata collection, merge:

```javascript
try {
  if (window.parent === window && typeof window.__YOURGOV_EXPLAIN_STATE__ === 'function') {
    meta.yourgov_state = window.__YOURGOV_EXPLAIN_STATE__();
  }
} catch (_) {}
```

For iframe-originated context, keep existing parent `postMessage`; the parent already sends the context to the API.

- [x] **Step 2: Add explainer prompt handling for YourGov state**

In `app.py` inside `explain_selection`, when building `meta_lines`, if `metadata["yourgov_state"]` is a dict, emit a readable nested section:

```python
if k == "yourgov_state" and isinstance(v, dict):
    meta_lines.append("  yourgov_state:")
    for state_key, state_value in v.items():
        meta_lines.append(f"    {state_key}: {state_value}")
```

Update the selection system prompt to say:

```text
- If yourgov_state is supplied, use it to explain the selected MP, selected division, active map mode, and visible YourGov state.
```

- [x] **Step 3: Run explainer context tests**

Run:

```powershell
py -3.12 -m pytest tests\test_yourgov_source_lens_ui.py::test_explain_context_includes_yourgov_selected_state -q
```

Expected: pass.

## Task 5: Verification

**Files:**
- No new files.

- [x] **Step 1: Run focused tests**

Run:

```powershell
py -3.12 -m pytest tests\test_search_and_counts.py tests\test_yourgov_source_lens_ui.py -q
```

Expected: all pass.

- [x] **Step 2: Run full test suite**

Run:

```powershell
py -3.12 -m pytest -q
```

Expected: all pass.

- [x] **Step 3: Run production validation**

Run:

```powershell
py -3.12 scripts\validate_production_ready.py --skip-network-freshness --division-id 2355
```

Expected: `VALIDATION PASS`.

- [x] **Step 4: Browser smoke test**

Start Flask on a local port and verify:

- `/` resolves to the global map.
- UK entry link opens YourGov.
- `/source-lens` shows public `YourGov` copy.
- Search placeholder mentions postcode, constituency, and MP name.
- Selecting an MP renders voting-record rows.
- Single-clicking a row updates map status.
- Double-clicking or activating the summary action opens a division summary in the left-side source area.

Use the Browser plugin if available; otherwise use Flask test client and direct route checks.

## Self-Review

- Spec coverage: all approved streamlining requirements map to tasks above.
- Placeholder scan: no placeholder markers or incomplete implementation steps remain.
- Type consistency: `selectedMP`, `selectedDivisionPayload`, `selectedMapMode`, and `window.__YOURGOV_EXPLAIN_STATE__` are consistently named across tasks.
