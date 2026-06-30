# YourGov First-Party Source Lens Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the approved production stage that makes `/source-lens` a first-party YourGov product, keeps the map visible, moves PublicWhip into a source dropdown, fixes the four map modes so every visualization is scoped to the selected division, removes public-facing YourGov copy, adds YourGov logo assets, and introduces production validation.
**Architecture:** One canonical Flask payload builder maps `division_id + mode` to map data. Existing endpoints become compatibility wrappers around that builder. The Source Lens frontend stores one selected division and asks the canonical endpoint for Vote, Party, Gender, and Rebel views. PublicWhip stays available as supporting evidence inside the left panel.
**Tech Stack:** Flask, SQLite seed database, Jinja templates, vanilla JavaScript, CSS, SVG assets, pytest, Python 3.12.

---

## Source Materials

Use these approved sources before changing code:

- `D:\Documents\11Projects\yourgov\docs\superpowers\specs\2026-06-08-yourgov-first-party-source-lens-design.md`
- `D:\Documents\11Projects\yourgov\app.py`
- `D:\Documents\11Projects\yourgov\templates\panel_test.html`
- `D:\Documents\11Projects\yourgov\templates\map_relay.html`
- `D:\Documents\11Projects\yourgov\static\panel_test.js`
- `D:\Documents\11Projects\yourgov\static\panel_test.css`
- `D:\Documents\11Projects\yourgov\tests\test_agent_api.py`

Keep all work on branch `codex/production-readiness-map-validation` in `D:\Documents\11Projects\yourgov`.

## Target File Structure

```text
D:\Documents\11Projects\yourgov
|-- app.py
|-- README.md
|-- docs
|   |-- DATA_SOURCES.md
|   |-- KRYSTAL_DEPLOY.md
|   |-- RELEASE_CHECKLIST.md
|   `-- superpowers
|       `-- plans
|           `-- 2026-06-10-yourgov-first-party-source-lens-implementation.md
|-- scripts
|   `-- validate_production_ready.py
|-- static
|   |-- img
|   |   |-- favicon.svg
|   |   |-- yourgov-logo.svg
|   |   `-- yourgov-mark.svg
|   |-- panel_test.css
|   |-- panel_test.js
|   `-- data
|       `-- global_feasibility.json
|-- templates
|   |-- ab_map.html
|   |-- global.html
|   |-- index.html
|   |-- map.html
|   |-- map_relay.html
|   |-- panel_test.html
|   |-- publicwhip.html
|   |-- pw_division.html
|   |-- pw_divisions.html
|   |-- pw_lords.html
|   |-- pw_mp.html
|   |-- pw_mps.html
|   |-- pw_msps.html
|   |-- pw_policies.html
|   |-- pw_search.html
|   `-- welcome.html
|-- tests
|   |-- test_agent_api.py
|   |-- test_division_map_payloads.py
|   |-- test_production_validation.py
|   |-- test_yourgov_branding.py
|   `-- test_yourgov_source_lens_ui.py
|-- android-yourgov
|   `-- app
|       `-- src
|           `-- main
|               `-- res
|                   `-- values
|                       `-- strings.xml
`-- ios-yourgov
    |-- README.md
    `-- project.yml
```

Do not rename `mygov.db`, `MYGOV_AGENT_API_TOKEN`, `MYGOV_APP_URL`, `yourgov:*` browser events, Android package identifiers, or iOS bundle identifiers in this stage. These names are compatibility aliases and must remain stable until a deployment migration is planned.

## Data Contract

Add one canonical map payload contract:

```json
{
  "ok": true,
  "mode": "party-split",
  "map_mode": "party-split",
  "division": {
    "division_id": 2355,
    "title": "King's Speech Motion for an Address",
    "date": "2026-05-20",
    "aye_count": 305,
    "no_count": 165,
    "source_url": "/publicwhip/division/2355"
  },
  "counts": {
    "aye": 305,
    "no": 165,
    "unknown": 177
  },
  "legend": [
    {"key": "Labour", "label": "Labour", "color": "#dc241f"}
  ],
  "map_data": {
    "Example Constituency": {
      "constituency": "Example Constituency",
      "member_id": 206,
      "name": "Example MP",
      "party": "Labour",
      "vote": "Aye",
      "color": "#dc241f",
      "label": "Labour: Example MP. Voted Aye on King's Speech Motion for an Address.",
      "source": "publicwhip",
      "mode": "party-split"
    }
  },
  "source_links": [
    {"label": "PublicWhip record", "url": "/publicwhip/division/2355"}
  ],
  "data_quality": {
    "division_scoped": true,
    "unknown_vote_count": 177,
    "member_rows": 647
  },
  "caveat": "This view describes recorded vote data for the selected division. It does not infer motive, character, or wrongdoing."
}
```

Supported request modes:

```text
vote-split
party-split
gender-split
rebel-split
rebel-rate
```

`rebel-rate` is accepted as an input alias and returns `mode: "rebel-split"` for division-scoped map payloads. The historical generic rebel-rate endpoint can remain available as a legacy route, but it must not be used by the four Source Lens wedges.

## Implementation Tasks

- [ ] 1. Add backend tests that prove every map mode is division-scoped.

Create `D:\Documents\11Projects\yourgov\tests\test_division_map_payloads.py`.

Use this test content:

```python
import pytest

from app import app


KNOWN_DIVISION_A = 2355
KNOWN_DIVISION_B = 2356


@pytest.fixture()
def client():
    app.config.update(TESTING=True)
    return app.test_client()


@pytest.mark.parametrize("mode", ["vote-split", "party-split", "gender-split", "rebel-split"])
def test_division_map_payload_contract(client, mode):
    response = client.get(f"/api/lens/division/{KNOWN_DIVISION_A}/map?mode={mode}")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["mode"] == mode
    assert payload["map_mode"] == mode
    assert payload["division"]["division_id"] == KNOWN_DIVISION_A
    assert payload["division"]["source_url"] == f"/publicwhip/division/{KNOWN_DIVISION_A}"
    assert payload["map_data"]
    assert payload["legend"]
    assert payload["source_links"]
    assert payload["data_quality"]["division_scoped"] is True

    sample = next(iter(payload["map_data"].values()))
    for key in ["constituency", "member_id", "name", "party", "vote", "color", "label", "source", "mode"]:
        assert key in sample
    assert sample["mode"] == mode
    assert sample["vote"] in sample["label"]


@pytest.mark.parametrize("mode", ["party-split", "gender-split", "rebel-split"])
def test_non_vote_modes_include_selected_division_context(client, mode):
    first = client.get(f"/api/lens/division/{KNOWN_DIVISION_A}/map?mode={mode}").get_json()
    second = client.get(f"/api/lens/division/{KNOWN_DIVISION_B}/map?mode={mode}").get_json()

    assert first["division"]["division_id"] == KNOWN_DIVISION_A
    assert second["division"]["division_id"] == KNOWN_DIVISION_B
    assert first["division"]["title"] != second["division"]["title"]

    first_sample = next(iter(first["map_data"].values()))
    second_sample = next(iter(second["map_data"].values()))
    assert first["division"]["title"] in first_sample["label"]
    assert second["division"]["title"] in second_sample["label"]
    assert first["division"]["title"] not in second_sample["label"]


def test_rebel_rate_alias_returns_division_scoped_rebel_split(client):
    response = client.get(f"/api/lens/division/{KNOWN_DIVISION_A}/map?mode=rebel-rate")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["mode"] == "rebel-split"
    assert payload["division"]["division_id"] == KNOWN_DIVISION_A
    assert payload["data_quality"]["division_scoped"] is True
```

Run:

```powershell
& 'C:\Users\richw\AppData\Local\Programs\Python\Python312\Scripts\pytest.exe' tests/test_division_map_payloads.py -q
```

Expected result before implementation:

```text
FAILED tests/test_division_map_payloads.py::test_division_map_payload_contract
404
```

- [ ] 2. Implement the canonical division map payload builder.

Modify `D:\Documents\11Projects\yourgov\app.py`.

Add these constants near the existing colour constants:

```python
MODE_ALIASES = {
    "vote": "vote-split",
    "votes": "vote-split",
    "vote-split": "vote-split",
    "party": "party-split",
    "party-split": "party-split",
    "gender": "gender-split",
    "gender-split": "gender-split",
    "rebel": "rebel-split",
    "rebel-split": "rebel-split",
    "rebel-rate": "rebel-split",
}

DIVISION_MAP_MODES = {"vote-split", "party-split", "gender-split", "rebel-split"}

VOTE_COLOURS = {
    "Aye": "#16a34a",
    "No": "#dc2626",
    "Absent/unknown": "#6b7280",
}

GENDER_COLOURS = {
    "M": "#38bdf8",
    "F": "#f472b6",
    "Unknown": "#6b7280",
}

REBEL_COLOURS = {
    "with_party_majority": "#16a34a",
    "against_party_majority": "#f59e0b",
    "no_clear_party_majority": "#64748b",
    "absent_or_unknown": "#94a3b8",
    "independent_or_no_party_grouping": "#475569",
}
```

Add mode normalization:

```python
def _normalise_division_map_mode(mode):
    key = (mode or "vote-split").strip().lower()
    normalised = MODE_ALIASES.get(key)
    if normalised not in DIVISION_MAP_MODES:
        return None
    return normalised
```

Add helpers for vote labels, gender extraction, and party majorities:

```python
def _vote_label(raw_vote):
    if raw_vote == 1:
        return "Aye"
    if raw_vote == 0:
        return "No"
    return "Absent/unknown"


def _member_gender_from_posts(raw_posts):
    try:
        posts = json.loads(raw_posts or "{}")
    except Exception:
        posts = {}
    gender = posts.get("gender") if isinstance(posts, dict) else None
    if gender in {"M", "F"}:
        return gender
    return "Unknown"


def _party_majorities_for_division(rows):
    counts = {}
    for row in rows:
        party = (row["party"] or "").strip()
        if not party or party.lower() == "independent":
            continue
        if row["voted_aye"] not in (0, 1):
            continue
        bucket = counts.setdefault(party, {0: 0, 1: 0})
        bucket[row["voted_aye"]] += 1

    majorities = {}
    for party, bucket in counts.items():
        total = bucket[0] + bucket[1]
        if total <= 0:
            continue
        if bucket[1] / total >= 0.60:
            majorities[party] = 1
        elif bucket[0] / total >= 0.60:
            majorities[party] = 0
    return majorities
```

Replace the internals of `_division_payload` with a wrapper over the new builder, preserving the current `/api/lens/division/<id>` response shape:

```python
def _division_payload(division_id, source="publicwhip"):
    return _division_map_payload(division_id, mode="vote-split", source=source)
```

Add the canonical builder:

```python
def _division_map_payload(division_id, mode="vote-split", source="publicwhip"):
    mode = _normalise_division_map_mode(mode)
    if not mode:
        return None

    conn = get_publicwhip_conn()
    meta = conn.execute(
        """
        SELECT division_id, title, division_date, aye_count, no_count
        FROM votes
        WHERE division_id=?
        LIMIT 1
        """,
        (division_id,),
    ).fetchone()
    if not meta:
        conn.close()
        return None

    rows = conn.execute(
        """
        SELECT
            m.member_id,
            m.name,
            m.party,
            m.constituency,
            m.current_posts,
            v.voted_aye
        FROM members m
        LEFT JOIN votes v
            ON v.member_id = m.member_id
           AND v.division_id = ?
        WHERE m.constituency IS NOT NULL
        ORDER BY m.constituency
        """,
        (division_id,),
    ).fetchall()
    conn.close()

    title = meta["title"] or "Untitled division"
    counts = {"aye": 0, "no": 0, "unknown": 0}
    for row in rows:
        vote = _vote_label(row["voted_aye"])
        if vote == "Aye":
            counts["aye"] += 1
        elif vote == "No":
            counts["no"] += 1
        else:
            counts["unknown"] += 1

    party_majorities = _party_majorities_for_division(rows)
    map_data = {}
    votes = []
    legend_seen = {}

    for row in rows:
        constituency = row["constituency"]
        party = row["party"] or "Unknown"
        vote = _vote_label(row["voted_aye"])
        gender = _member_gender_from_posts(row["current_posts"])
        item = {
            "constituency": constituency,
            "member_id": row["member_id"],
            "name": row["name"],
            "party": party,
            "vote": vote,
            "source": source,
            "mode": mode,
        }

        if mode == "vote-split":
            colour = VOTE_COLOURS[vote]
            legend_key = vote
            label = f"{vote}: {row['name']}. Recorded vote on {title}."
            item.update({"color": colour, "label": label})

        elif mode == "party-split":
            colour = PARTY_COLOURS.get(party, "#8a97ab")
            legend_key = party
            label = f"{party}: {row['name']}. Voted {vote} on {title}."
            item.update({"color": colour, "label": label})

        elif mode == "gender-split":
            colour = GENDER_COLOURS.get(gender, GENDER_COLOURS["Unknown"])
            legend_key = gender
            label = f"Gender {gender}: {row['name']}. Voted {vote} on {title}."
            item.update({"color": colour, "label": label, "gender": gender})

        else:
            majority = party_majorities.get(party)
            if not party or party == "Unknown" or party.lower() == "independent":
                rebel_status = "independent_or_no_party_grouping"
                label_status = "Independent or no party grouping"
            elif row["voted_aye"] not in (0, 1):
                rebel_status = "absent_or_unknown"
                label_status = "Absent or unknown"
            elif majority is None:
                rebel_status = "no_clear_party_majority"
                label_status = "No clear party majority"
            elif row["voted_aye"] == majority:
                rebel_status = "with_party_majority"
                label_status = "With party majority"
            else:
                rebel_status = "against_party_majority"
                label_status = "Against party majority"
            colour = REBEL_COLOURS[rebel_status]
            legend_key = rebel_status
            label = f"{label_status}: {row['name']}. Voted {vote} on {title}."
            item.update({
                "color": colour,
                "label": label,
                "rebel_status": rebel_status,
                "party_majority": _vote_label(majority) if majority in (0, 1) else None,
            })

        votes.append(item)
        map_data[constituency] = item.copy()
        legend_seen.setdefault(legend_key, {"key": legend_key, "label": legend_key.replace("_", " ").title(), "color": colour})

    return {
        "ok": True,
        "mode": mode,
        "map_mode": mode,
        "match": {
            "method": "exact_local_division_id",
            "confidence": "high",
            "source": source,
        },
        "division": {
            "division_id": meta["division_id"],
            "title": title,
            "date": (meta["division_date"] or "")[:10],
            "aye_count": meta["aye_count"],
            "no_count": meta["no_count"],
            "source_url": f"/publicwhip/division/{meta['division_id']}",
        },
        "counts": counts,
        "legend": list(legend_seen.values()),
        "map_data": map_data,
        "votes": votes,
        "source_links": [
            {"label": "PublicWhip record", "url": f"/publicwhip/division/{meta['division_id']}"},
        ],
        "data_quality": {
            "division_scoped": True,
            "unknown_vote_count": counts["unknown"],
            "member_rows": len(rows),
            "source": source,
        },
        "caveat": (
            "This view describes recorded vote data for the selected division. "
            "It does not infer motive, character, or wrongdoing."
        ),
    }
```

Add the canonical route:

```python
@app.route("/api/lens/division/<int:division_id>/map")
def api_lens_division_map(division_id):
    mode = _normalise_division_map_mode(request.args.get("mode"))
    if not mode:
        return jsonify({"ok": False, "error": "Unsupported map mode."}), 400
    payload = _division_map_payload(division_id, mode=mode)
    if not payload:
        return jsonify({"ok": False, "error": "Division not found in YourGov data."}), 404
    return jsonify(payload)
```

Update `/api/lens/division/<int:division_id>` to call the wrapper and keep returning the full payload:

```python
@app.route("/api/lens/division/<int:division_id>")
def api_lens_division(division_id):
    payload = _division_payload(division_id)
    if not payload:
        return jsonify({"ok": False, "error": "Division not found in YourGov data."}), 404
    return jsonify(payload)
```

Run:

```powershell
& 'C:\Users\richw\AppData\Local\Programs\Python\Python312\Scripts\pytest.exe' tests/test_division_map_payloads.py -q
```

Expected result after implementation:

```text
9 passed
```

- [ ] 3. Update the agent map payload API so `division_id` is honored for every mode.

Modify `D:\Documents\11Projects\yourgov\tests\test_agent_api.py`.

Add these tests:

```python
import pytest


@pytest.mark.parametrize("mode", ["vote-split", "party-split", "gender-split", "rebel-split"])
def test_agent_map_payload_uses_requested_division_for_every_mode(mode):
    client = app.test_client()
    response = client.get(
        f"/api/agent/map_payload?mode={mode}&division_id=2355",
        headers=_auth_header(),
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["data"]["mode"] == mode
    assert payload["data"]["division"]["division_id"] == 2355
    assert payload["data"]["map_data"]


def test_agent_map_payload_rebel_rate_alias_is_division_scoped():
    client = app.test_client()
    response = client.get(
        "/api/agent/map_payload?mode=rebel-rate&division_id=2355",
        headers=_auth_header(),
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["data"]["mode"] == "rebel-split"
    assert payload["data"]["division"]["division_id"] == 2355
```

Run:

```powershell
& 'C:\Users\richw\AppData\Local\Programs\Python\Python312\Scripts\pytest.exe' tests/test_agent_api.py -q
```

Expected result before app API changes:

```text
FAILED tests/test_agent_api.py::test_agent_map_payload_uses_requested_division_for_every_mode
KeyError: 'division'
```

Update `agent_map_payload` to normalize modes and call `_division_map_payload`:

```python
@app.route("/api/agent/map_payload")
@require_agent_token
def agent_map_payload():
    requested_mode = request.args.get("mode") or "vote-split"
    mode = _normalise_division_map_mode(requested_mode)
    division_id = request.args.get("division_id", type=int)

    if not mode:
        return _agent_response(error="Unsupported mode", status=400)

    if not division_id:
        conn = get_publicwhip_conn()
        latest = conn.execute(
            """
            SELECT DISTINCT division_id
            FROM votes
            WHERE title IS NOT NULL AND aye_count > 0
            ORDER BY division_date DESC, division_id DESC
            LIMIT 1
            """
        ).fetchone()
        conn.close()
        if not latest:
            return _agent_response(error="No divisions available", status=404)
        division_id = int(latest["division_id"])

    payload = _division_map_payload(division_id, mode=mode)
    if not payload:
        return _agent_response(error="Division payload failed", status=404)
    return _agent_response(data=payload)
```

Update the agent manifest route entry from:

```python
{"path": "/api/agent/map_payload?mode=<vote-split|party-split|gender-split|rebel-rate>[&division_id=<id>]", "description": "Get map-ready payload for a map mode"}
```

to:

```python
{"path": "/api/agent/map_payload?mode=<vote-split|party-split|gender-split|rebel-split>[&division_id=<id>]", "description": "Get selected-division map payload for a map mode"}
```

Run:

```powershell
& 'C:\Users\richw\AppData\Local\Programs\Python\Python312\Scripts\pytest.exe' tests/test_agent_api.py tests/test_division_map_payloads.py -q
```

Expected result:

```text
17 passed
```

- [ ] 4. Add UI contract tests for the YourGov first-party Source Lens shell.

Create `D:\Documents\11Projects\yourgov\tests\test_yourgov_source_lens_ui.py`.

Use this test content:

```python
from pathlib import Path

from app import app


ROOT = Path(__file__).resolve().parents[1]


def test_source_lens_html_is_yourgov_first_party_shell():
    client = app.test_client()
    response = client.get("/source-lens")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "YourGov" in html
    assert "YourGov Lens POC" not in html
    assert 'id="yourgov-panel"' in html
    assert 'id="map-frame"' in html
    assert 'id="source-view-select"' in html
    assert 'value="yourgov-summary"' in html
    assert 'value="publicwhip-record"' in html
    assert 'data-mode="rebel-split"' in html


def test_source_lens_javascript_uses_canonical_division_map_endpoint():
    js = (ROOT / "static" / "panel_test.js").read_text(encoding="utf-8")

    assert "selectedDivisionId" in js
    assert "/api/lens/division/" in js
    assert "/map?mode=" in js
    assert "/api/lens/map/party" not in js
    assert "/api/lens/map/gender" not in js
    assert "/api/lens/map/rebel-rate" not in js
    assert "ensurePublicWhipLoaded();" not in js
```

Run:

```powershell
& 'C:\Users\richw\AppData\Local\Programs\Python\Python312\Scripts\pytest.exe' tests/test_yourgov_source_lens_ui.py -q
```

Expected result before UI changes:

```text
FAILED tests/test_yourgov_source_lens_ui.py::test_source_lens_html_is_yourgov_first_party_shell
```

- [ ] 5. Redesign `panel_test.html` as the YourGov panel plus visible map.

Modify `D:\Documents\11Projects\yourgov\templates\panel_test.html`.

Make these structural changes:

```html
<title>YourGov Source Lens</title>
<link rel="icon" href="/static/img/favicon.svg" type="image/svg+xml">
```

Replace the current product header with:

```html
<section class="source-pane yourgov-panel" id="yourgov-panel" aria-label="YourGov panel">
  <header class="yg-brand">
    <a class="yg-logo-link" href="/" aria-label="YourGov home">
      <img src="/static/img/yourgov-logo.svg" alt="YourGov" class="yg-logo">
    </a>
    <p class="yg-kicker">Independent civic records, explained from sources.</p>
  </header>

  <form class="lens-search" id="source-search-form" autocomplete="off">
    <label class="sr-only" for="source-search-input">Search MPs, constituencies, issues, or divisions</label>
    <input id="source-search-input" type="search" aria-describedby="source-search-help">
    <button type="submit">Search</button>
    <p id="source-search-help">Search an MP, constituency, issue, or division.</p>
  </form>

  <section class="selected-card idle" id="selection-card" aria-live="polite">
    <p class="eyebrow">Selected division</p>
    <h2 id="selection-title">Choose a division to start</h2>
    <p id="selection-meta">Recent Commons divisions are listed below.</p>
    <p id="selection-caveat">Vote, party, gender, and rebel views will all use the same selected division.</p>
    <a id="selection-source" href="/publicwhip" target="source-frame">Open source record</a>
    <a id="selection-profile" hidden>Open MP profile</a>
  </section>

  <label class="source-select-label" for="source-view-select">Source view</label>
  <select id="source-view-select">
    <option value="yourgov-summary" selected>YourGov Summary</option>
    <option value="publicwhip-record">PublicWhip Record</option>
    <option value="parliament-record">Parliament Record</option>
  </select>

  <div id="yourgov-summary-panel" class="source-detail-panel">
    <h3>YourGov summary</h3>
    <p id="source-summary-text">Select a division to see its sourced summary and evidence links.</p>
    <ul id="source-links-list"></ul>
  </div>

  <div id="source-frame-panel" class="source-detail-panel source-frame-panel" hidden>
    <iframe id="source-frame" name="source-frame" title="Supporting source record"></iframe>
  </div>

  <section class="division-results" id="division-results" aria-label="Recent and matching divisions"></section>
</section>
```

Keep the existing map pane visible beside this left panel. Change the Rebel wedge to:

```html
<button class="topic-tab" id="topic-rebel-rate" type="button" data-mode="rebel-split">Rebel</button>
```

The button id can remain `topic-rebel-rate` so existing JS variable names do not need a wider rename in the same pass.

Run:

```powershell
& 'C:\Users\richw\AppData\Local\Programs\Python\Python312\Scripts\pytest.exe' tests/test_yourgov_source_lens_ui.py -q
```

Expected result after template-only changes:

```text
FAILED tests/test_yourgov_source_lens_ui.py::test_source_lens_javascript_uses_canonical_division_map_endpoint
```

- [ ] 6. Update Source Lens JavaScript so selected division is the single source of truth.

Modify `D:\Documents\11Projects\yourgov\static\panel_test.js`.

Add selected state near existing state variables:

```javascript
var selectedDivisionId = null;
var selectedDivisionPayload = null;
var selectedMapMode = 'vote-split';
var selectedSourceView = 'yourgov-summary';
```

Replace `TOPIC_BY_MODE` with:

```javascript
var TOPIC_BY_MODE = {
  'vote-split':   { btn: function () { return topicVoteSplit; },   kind: 'vote-split',   legend: 'vote-split' },
  'party-split':  { btn: function () { return topicPartySplit; },  kind: 'party-split',  legend: 'party' },
  'gender-split': { btn: function () { return topicGenderSplit; }, kind: 'gender-split', legend: 'gender' },
  'rebel-split':  { btn: function () { return topicRebelRate; },   kind: 'rebel-split',  legend: 'rebel-split' }
};
```

Add a default division loader:

```javascript
async function ensureSelectedDivision() {
  if (selectedDivisionId) return selectedDivisionId;
  var listResp = await fetch('/api/lens/source-divisions?limit=1');
  var list = await listResp.json();
  var divs = (list && (list.divisions || (Array.isArray(list) ? list : []))) || [];
  if (!divs.length) throw new Error('No divisions in dataset');
  selectedDivisionId = divs[0].division_id || divs[0].id;
  return selectedDivisionId;
}
```

Add canonical payload loading:

```javascript
async function loadDivisionMapPayload(mode) {
  var divisionId = await ensureSelectedDivision();
  var url = '/api/lens/division/' + encodeURIComponent(divisionId) + '/map?mode=' + encodeURIComponent(mode);
  var response = await fetch(url);
  var payload = await response.json();
  if (!response.ok || !payload.ok) {
    throw new Error(payload.error || 'Could not load division map payload');
  }
  selectedDivisionId = payload.division && payload.division.division_id;
  selectedDivisionPayload = payload;
  currentMapData = payload.map_data || {};
  currentMapDataKind = payload.mode || mode;
  lastDivisionLabel = (payload.division && payload.division.title) || ('division ' + selectedDivisionId);
  return payload;
}
```

Replace `setMapMode` with:

```javascript
async function setMapMode(mode) {
  if (mode === 'rebel-rate') mode = 'rebel-split';
  var spec = TOPIC_BY_MODE[mode];
  if (!spec) return;

  selectedMapMode = mode;
  setTopicActive(spec.btn());
  setLegend(spec.legend);
  setStatus('Loading ' + mode + ' for selected division...', 'ok');

  try {
    var payload = await loadDivisionMapPayload(mode);
    sendMapColours({ map_mode: payload.map_mode || mode, map_data: payload.map_data || {} });
    renderSelection(payload);
    renderSourceSummary(payload);
    updateSourceView();
    setStatus('Map updated: ' + mode + ' for ' + lastDivisionLabel + '.', 'ok');
  } catch (err) {
    setStatus(err.message, 'warn');
  }
}
```

Update `visualiseDivision`:

```javascript
async function visualiseDivision(divisionId, source) {
  selectedDivisionId = Number(divisionId);
  setStatus('Loading division ' + divisionId + '...', 'ok');
  var payload = await loadDivisionMapPayload(selectedMapMode || 'vote-split');
  payload.match = payload.match || {};
  payload.match.source = source || payload.match.source;

  if (!payload.map_data || !Object.keys(payload.map_data).length) {
    setStatus('Could not map this vote to constituency data.', 'warn');
    return;
  }

  document.querySelectorAll('.division-row').forEach(function (row) {
    row.classList.toggle('active', row.dataset.divisionId === String(divisionId));
  });

  sendMapColours({ map_mode: payload.map_mode || selectedMapMode, map_data: payload.map_data || {} });
  renderSelection(payload);
  renderSourceSummary(payload);
  updateSourceView();
  enrichSelectionWithMP();
}
```

Add source summary rendering:

```javascript
function renderSourceSummary(payload) {
  var division = payload.division || {};
  var summaryText = document.getElementById('source-summary-text');
  var linksList = document.getElementById('source-links-list');
  if (summaryText) {
    summaryText.textContent = (division.title || 'Selected division') + ' was recorded on ' + (division.date || 'an unknown date') + '. Aye ' + (payload.counts.aye || 0) + ', No ' + (payload.counts.no || 0) + ', Unknown ' + (payload.counts.unknown || 0) + '.';
  }
  if (linksList) {
    linksList.innerHTML = '';
    (payload.source_links || []).forEach(function (link) {
      var li = document.createElement('li');
      var a = document.createElement('a');
      a.href = link.url;
      a.textContent = link.label;
      li.appendChild(a);
      linksList.appendChild(li);
    });
  }
}
```

Add source dropdown behavior:

```javascript
function updateSourceView() {
  var select = document.getElementById('source-view-select');
  var summaryPanel = document.getElementById('yourgov-summary-panel');
  var framePanel = document.getElementById('source-frame-panel');
  if (!select || !summaryPanel || !framePanel) return;

  selectedSourceView = select.value || 'yourgov-summary';
  summaryPanel.hidden = selectedSourceView !== 'yourgov-summary';
  framePanel.hidden = selectedSourceView === 'yourgov-summary';

  if (selectedSourceView === 'publicwhip-record' && selectedDivisionId) {
    sourceFrame.src = '/publicwhip/division/' + encodeURIComponent(selectedDivisionId);
  }
}

var sourceViewSelect = document.getElementById('source-view-select');
if (sourceViewSelect) {
  sourceViewSelect.addEventListener('change', updateSourceView);
}
```

Update the legacy alias map:

```javascript
function applyTopic(topicKey) {
  var aliasToMode = {
    'vote-split': 'vote-split',
    'party': 'party-split',
    'party-split': 'party-split',
    'gender': 'gender-split',
    'gender-split': 'gender-split',
    'rebel-rate': 'rebel-split',
    'rebel-split': 'rebel-split'
  };
  var mode = aliasToMode[topicKey] || topicKey;
  return setMapMode(mode);
}
```

Remove the startup call:

```javascript
ensurePublicWhipLoaded();
```

Run:

```powershell
& 'C:\Users\richw\AppData\Local\Programs\Python\Python312\Scripts\pytest.exe' tests/test_yourgov_source_lens_ui.py tests/test_division_map_payloads.py -q
```

Expected result:

```text
11 passed
```

- [ ] 7. Update Source Lens CSS so the YourGov panel and map are the default layout.

Modify `D:\Documents\11Projects\yourgov\static\panel_test.css`.

Keep the two-column layout on desktop:

```css
.app-shell {
  display: grid;
  grid-template-columns: minmax(360px, 0.92fr) minmax(520px, 1.35fr);
  grid-template-areas: "source viz";
  min-height: 100vh;
}

.yourgov-panel {
  grid-area: source;
  background:
    radial-gradient(circle at top left, rgba(20, 94, 151, 0.18), transparent 34rem),
    linear-gradient(180deg, #f8fbff 0%, #edf4f7 100%);
  border-right: 1px solid rgba(15, 23, 42, 0.12);
  padding: 1.25rem;
  overflow-y: auto;
}

.yg-brand {
  display: grid;
  gap: 0.65rem;
  margin-bottom: 1rem;
}

.yg-logo {
  width: min(210px, 70%);
  height: auto;
}

.yg-kicker {
  color: #334155;
  font-size: 0.96rem;
}

.source-select-label {
  display: block;
  margin: 1rem 0 0.35rem;
  font-weight: 700;
  color: #0f172a;
}

#source-view-select {
  width: 100%;
  border: 1px solid rgba(15, 23, 42, 0.18);
  border-radius: 0.85rem;
  padding: 0.75rem 0.85rem;
  background: #ffffff;
  color: #0f172a;
}

.source-detail-panel {
  margin-top: 1rem;
  border: 1px solid rgba(15, 23, 42, 0.12);
  border-radius: 1rem;
  background: rgba(255, 255, 255, 0.78);
  padding: 1rem;
}

.source-frame-panel {
  min-height: 24rem;
  padding: 0;
  overflow: hidden;
}

.source-frame-panel iframe {
  width: 100%;
  height: 32rem;
  border: 0;
}

.map-pane {
  grid-area: viz;
}

@media (max-width: 900px) {
  .app-shell {
    grid-template-columns: 1fr;
    grid-template-areas:
      "source"
      "viz";
  }

  .yourgov-panel {
    border-right: 0;
    border-bottom: 1px solid rgba(15, 23, 42, 0.12);
  }
}
```

Run:

```powershell
& 'C:\Users\richw\AppData\Local\Programs\Python\Python312\Scripts\pytest.exe' tests/test_yourgov_source_lens_ui.py -q
```

Expected result:

```text
2 passed
```

- [ ] 8. Add YourGov logo, mark, and favicon SVG assets.

Create `D:\Documents\11Projects\yourgov\tests\test_yourgov_branding.py`.

Use this test content:

```python
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_yourgov_svg_assets_exist_and_avoid_official_gov_style():
    for name in ["yourgov-logo.svg", "yourgov-mark.svg", "favicon.svg"]:
        path = ROOT / "static" / "img" / name
        text = path.read_text(encoding="utf-8")
        lowered = text.lower()
        assert "<svg" in lowered
        assert "yourgov" in lowered or "yg" in lowered
        assert "crown" not in lowered
        assert "gov.uk" not in lowered


def test_key_public_templates_use_yourgov_name():
    public_files = [
        ROOT / "templates" / "panel_test.html",
        ROOT / "templates" / "map_relay.html",
        ROOT / "templates" / "welcome.html",
        ROOT / "templates" / "ab_map.html",
        ROOT / "README.md",
        ROOT / "android-yourgov" / "app" / "src" / "main" / "res" / "values" / "strings.xml",
        ROOT / "ios-yourgov" / "project.yml",
    ]
    for path in public_files:
        text = path.read_text(encoding="utf-8")
        assert "YourGov" in text
        assert "YourGov" not in text
```

Run:

```powershell
& 'C:\Users\richw\AppData\Local\Programs\Python\Python312\Scripts\pytest.exe' tests/test_yourgov_branding.py -q
```

Expected result before assets and rename:

```text
FAILED tests/test_yourgov_branding.py::test_yourgov_svg_assets_exist_and_avoid_official_gov_style
```

Create `D:\Documents\11Projects\yourgov\static\img\yourgov-mark.svg`:

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96" role="img" aria-labelledby="title desc">
  <title id="title">YourGov mark</title>
  <desc id="desc">YG monogram with a civic map-grid check motif.</desc>
  <rect width="96" height="96" rx="24" fill="#0f4c5c"/>
  <path d="M20 22h56v52H20z" fill="none" stroke="#d8f3dc" stroke-width="4" opacity=".55"/>
  <path d="M34 24v50M48 24v50M62 24v50M22 40h52M22 56h52" stroke="#d8f3dc" stroke-width="2" opacity=".35"/>
  <path d="M29 34l14 18v18h10V52l14-18H55l-7 10-7-10H29z" fill="#ffffff"/>
  <path d="M57 63l8 8 15-19" fill="none" stroke="#f7b801" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
```

Create `D:\Documents\11Projects\yourgov\static\img\yourgov-logo.svg`:

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 360 96" role="img" aria-labelledby="title desc">
  <title id="title">YourGov logo</title>
  <desc id="desc">YourGov wordmark with independent civic source motif.</desc>
  <rect width="96" height="96" rx="24" fill="#0f4c5c"/>
  <path d="M20 22h56v52H20z" fill="none" stroke="#d8f3dc" stroke-width="4" opacity=".55"/>
  <path d="M34 24v50M48 24v50M62 24v50M22 40h52M22 56h52" stroke="#d8f3dc" stroke-width="2" opacity=".35"/>
  <path d="M29 34l14 18v18h10V52l14-18H55l-7 10-7-10H29z" fill="#ffffff"/>
  <path d="M57 63l8 8 15-19" fill="none" stroke="#f7b801" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/>
  <text x="116" y="58" font-family="Georgia, 'Times New Roman', serif" font-size="38" font-weight="700" fill="#0f172a">YourGov</text>
  <text x="118" y="78" font-family="Verdana, sans-serif" font-size="12" letter-spacing="1.6" fill="#475569">SOURCE-LED CIVIC RECORDS</text>
</svg>
```

Create `D:\Documents\11Projects\yourgov\static\img\favicon.svg` with the mark SVG content.

Update visible page names in the public files listed in the test. Preserve internal compatibility names such as `uk.yourgov.mobile`, `mygov.db`, and `yourgov:*`.

Run:

```powershell
& 'C:\Users\richw\AppData\Local\Programs\Python\Python312\Scripts\pytest.exe' tests/test_yourgov_branding.py -q
```

Expected result:

```text
2 passed
```

- [ ] 9. Rename public-facing YourGov copy to YourGov across the web, docs, and mobile display strings.

Use `rg` to find public mentions:

```powershell
rg -n "YourGov|yourgov" app.py templates static README.md docs android-yourgov ios-yourgov -g "!docs/project-chat-context.md" -g "!docs/superpowers/specs/*" -g "!docs/superpowers/plans/*"
```

Apply these rules:

```text
Replace visible product text:
YourGov -> YourGov
YourGov Source Lens -> YourGov Source Lens
Back to YourGov -> Back to YourGov
YourGov-style -> YourGov-style

Keep compatibility names:
mygov.db
MYGOV_AGENT_API_TOKEN
MYGOV_APP_URL
yourgov:* browser events
uk.yourgov mobile identifiers
android-yourgov folder name
ios-yourgov folder name
yourgov-hackathon legacy deployment URL unless a current production URL is available
```

Update these files first:

```text
app.py
README.md
docs/DATA_SOURCES.md
docs/KRYSTAL_DEPLOY.md
docs/RELEASE_CHECKLIST.md
static/data/global_feasibility.json
templates/ab_map.html
templates/global.html
templates/index.html
templates/map.html
templates/map_relay.html
templates/panel_test.html
templates/publicwhip.html
templates/pw_division.html
templates/pw_divisions.html
templates/pw_lords.html
templates/pw_mp.html
templates/pw_mps.html
templates/pw_msps.html
templates/pw_policies.html
templates/pw_search.html
templates/welcome.html
android-yourgov/app/src/main/res/values/strings.xml
ios-yourgov/README.md
ios-yourgov/project.yml
```

Run:

```powershell
rg -n "YourGov" app.py templates static README.md docs android-yourgov ios-yourgov -g "!docs/project-chat-context.md" -g "!docs/superpowers/specs/*" -g "!docs/superpowers/plans/*"
```

Expected allowed output after implementation:

```text
```

Run:

```powershell
& 'C:\Users\richw\AppData\Local\Programs\Python\Python312\Scripts\pytest.exe' tests/test_yourgov_branding.py tests/test_yourgov_source_lens_ui.py -q
```

Expected result:

```text
4 passed
```

- [ ] 10. Add production validation script and tests.

Create `D:\Documents\11Projects\yourgov\tests\test_production_validation.py`.

Use this test content:

```python
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_production_ready.py"


def test_production_validation_script_passes_without_network_freshness():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--skip-network-freshness", "--division-id", "2355"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS source-lens brand" in result.stdout
    assert "PASS division map payload vote-split" in result.stdout
    assert "PASS division map payload party-split" in result.stdout
    assert "PASS division map payload gender-split" in result.stdout
    assert "PASS division map payload rebel-split" in result.stdout
    assert "VALIDATION PASS" in result.stdout
```

Create `D:\Documents\11Projects\yourgov\scripts\validate_production_ready.py`.

Use this script structure:

```python
#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import app, get_publicwhip_conn


MODES = ["vote-split", "party-split", "gender-split", "rebel-split"]


class Validation:
    def __init__(self):
        self.failures = []

    def pass_(self, name):
        print(f"PASS {name}")

    def fail(self, name, detail):
        message = f"FAIL {name}: {detail}"
        self.failures.append(message)
        print(message)

    def require(self, condition, name, detail):
        if condition:
            self.pass_(name)
        else:
            self.fail(name, detail)


def latest_local_division_id():
    conn = get_publicwhip_conn()
    row = conn.execute(
        """
        SELECT DISTINCT division_id
        FROM votes
        WHERE title IS NOT NULL AND aye_count > 0
        ORDER BY division_date DESC, division_id DESC
        LIMIT 1
        """
    ).fetchone()
    conn.close()
    return int(row["division_id"]) if row else None


def check_routes(v):
    client = app.test_client()
    for route in ["/", "/source-lens", "/global", "/publicwhip", "/publicwhip/divisions", "/publicwhip/mps"]:
        response = client.get(route)
        v.require(response.status_code in {200, 301, 302}, f"route {route}", f"status {response.status_code}")


def check_source_lens(v):
    client = app.test_client()
    response = client.get("/source-lens")
    html = response.get_data(as_text=True)
    v.require("YourGov" in html, "source-lens brand", "YourGov is missing")
    v.require("YourGov Lens POC" not in html, "source-lens old title removed", "old POC title is still visible")
    v.require('id="source-view-select"' in html and 'value="publicwhip-record"' in html, "source dropdown", "source dropdown contract missing")
    v.require('id="map-frame"' in html, "map frame visible", "map frame missing")


def check_payloads(v, division_id):
    client = app.test_client()
    for mode in MODES:
        response = client.get(f"/api/lens/division/{division_id}/map?mode={mode}")
        payload = response.get_json()
        ok = response.status_code == 200 and payload and payload.get("ok")
        v.require(ok, f"division map payload {mode}", f"status {response.status_code}")
        if not ok:
            continue
        v.require(payload["division"]["division_id"] == division_id, f"division scoped {mode}", "division_id drifted")
        v.require(bool(payload.get("map_data")), f"map data {mode}", "map_data is empty")
        v.require(bool(payload.get("source_links")), f"source links {mode}", "source links missing")
        if mode != "vote-split":
            sample = next(iter(payload["map_data"].values()))
            v.require(payload["division"]["title"] in sample.get("label", ""), f"label context {mode}", "label lacks division title")


def check_global_feasibility(v):
    path = ROOT / "static" / "data" / "global_feasibility.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    countries = data.get("countries", [])
    iso2_values = [c.get("iso2") for c in countries]
    v.require(len(countries) >= 190, "global feasibility country count", f"count {len(countries)}")
    v.require(len(iso2_values) == len(set(iso2_values)), "global feasibility unique iso2", "duplicate iso2 values found")
    uk = next((c for c in countries if c.get("iso2") == "GB"), None)
    v.require(bool(uk and uk.get("adapter_status") == "working"), "global feasibility UK adapter", "GB working adapter missing")


def check_network_freshness(v):
    local_id = latest_local_division_id()
    response = httpx.get(
        "https://commonsvotes-api.parliament.uk/data/divisions.json/search",
        params={"queryParameters.skip": 0, "queryParameters.take": 1},
        timeout=15,
        headers={"User-Agent": "YourGov production validation"},
    )
    response.raise_for_status()
    items = response.json().get("items") or response.json()
    upstream_id = int(items[0]["divisionId"])
    v.require(local_id >= upstream_id - 5, "data freshness", f"local latest {local_id}, upstream latest {upstream_id}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--division-id", type=int)
    parser.add_argument("--skip-network-freshness", action="store_true")
    args = parser.parse_args()

    v = Validation()
    division_id = args.division_id or latest_local_division_id()
    v.require(bool(division_id), "local division available", "no division found in local database")
    check_routes(v)
    check_source_lens(v)
    if division_id:
        check_payloads(v, division_id)
    check_global_feasibility(v)
    if not args.skip_network_freshness:
        check_network_freshness(v)

    if v.failures:
        print("VALIDATION FAIL")
        return 1
    print("VALIDATION PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Run:

```powershell
& 'C:\Users\richw\AppData\Local\Programs\Python\Python312\Scripts\pytest.exe' tests/test_production_validation.py -q
```

Expected result:

```text
1 passed
```

Run the validation command without network for local deterministic checks:

```powershell
& 'C:\Users\richw\AppData\Local\Programs\Python\Python312\python.exe' scripts/validate_production_ready.py --skip-network-freshness --division-id 2355
```

Expected output:

```text
PASS source-lens brand
PASS division map payload vote-split
PASS division map payload party-split
PASS division map payload gender-split
PASS division map payload rebel-split
VALIDATION PASS
```

Run the validation command with network before release:

```powershell
& 'C:\Users\richw\AppData\Local\Programs\Python\Python312\python.exe' scripts/validate_production_ready.py --division-id 2355
```

Expected output when local seed is fresh enough:

```text
PASS data freshness
VALIDATION PASS
```

Expected output when local seed is stale:

```text
FAIL data freshness: local latest 2356, upstream latest 2361
VALIDATION FAIL
```

- [ ] 11. Run the full automated verification suite.

Run:

```powershell
& 'C:\Users\richw\AppData\Local\Programs\Python\Python312\Scripts\pytest.exe' -q
```

Expected result:

```text
all tests pass
```

If the full test count changes because new tests are added, record the exact final count in the branch summary.

Run the local validation script:

```powershell
& 'C:\Users\richw\AppData\Local\Programs\Python\Python312\python.exe' scripts/validate_production_ready.py --skip-network-freshness --division-id 2355
```

Expected result:

```text
VALIDATION PASS
```

- [ ] 12. Browser-smoke the Source Lens flow in the in-app browser.

Start Flask locally:

```powershell
$env:PORT='5050'
& 'C:\Users\richw\AppData\Local\Programs\Python\Python312\python.exe' app.py
```

Open:

```text
http://127.0.0.1:5050/source-lens
```

Verify these behaviors:

```text
The left panel is branded YourGov.
The right map is visible on initial load.
PublicWhip is not loaded as the default full product frame.
The source dropdown defaults to YourGov Summary.
Selecting PublicWhip Record loads /publicwhip/division/<selected id> in the contained source frame.
Selecting a division updates the selected-division summary.
Clicking Vote keeps the selected division.
Clicking Party keeps the selected division.
Clicking Gender keeps the selected division.
Clicking Rebel keeps the selected division and uses division-scoped rebel-split output.
Browser console has no uncaught errors.
```

After browser verification, stop the local Flask process.

- [ ] 13. Final branch hygiene and review.

Run:

```powershell
git status --short
git diff -- app.py templates/panel_test.html templates/map_relay.html static/panel_test.js static/panel_test.css static/img tests scripts README.md docs android-yourgov ios-yourgov
```

Check:

```text
Only files needed for this production stage are changed.
Unrelated untracked hackathon or launch-planning files remain unstaged.
Compatibility names are preserved only where explicitly allowed.
Every test added in this plan fails against the old behavior and passes against the implemented behavior.
The generic party, gender, and rebel wedge bug is fixed by the canonical division map endpoint.
```

Commit only the implementation files:

```powershell
git add app.py README.md docs/DATA_SOURCES.md docs/KRYSTAL_DEPLOY.md docs/RELEASE_CHECKLIST.md scripts/validate_production_ready.py static/img/yourgov-logo.svg static/img/yourgov-mark.svg static/img/favicon.svg static/panel_test.css static/panel_test.js static/data/global_feasibility.json templates android-yourgov/app/src/main/res/values/strings.xml ios-yourgov/README.md ios-yourgov/project.yml tests/test_agent_api.py tests/test_division_map_payloads.py tests/test_production_validation.py tests/test_yourgov_branding.py tests/test_yourgov_source_lens_ui.py
git commit -m "feat: make Source Lens division-scoped YourGov surface"
```

Expected result:

```text
[codex/production-readiness-map-validation <hash>] feat: make Source Lens division-scoped YourGov surface
```

## Verification Matrix

```text
Backend division scoping:
  tests/test_division_map_payloads.py
  tests/test_agent_api.py

Source Lens shell:
  tests/test_yourgov_source_lens_ui.py
  in-app browser smoke at /source-lens

Brand migration:
  tests/test_yourgov_branding.py
  rg scan for public YourGov copy

Production readiness:
  tests/test_production_validation.py
  scripts/validate_production_ready.py

Regression coverage:
  full pytest suite
```

## Completion Criteria

The stage is complete only when:

```text
Full pytest suite passes.
Production validation passes locally with --skip-network-freshness.
Network freshness validation has been run or explicitly reported as stale seed data.
/source-lens opens as a YourGov-first interface in the browser.
All four map wedges use the selected division.
PublicWhip is available through the source dropdown.
No unrelated parked hackathon files are staged.
```
