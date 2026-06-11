import importlib
import os
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _client():
    appmod = importlib.import_module("app")
    appmod.app.config["TESTING"] = True
    return appmod.app.test_client()


def _source_lens_html():
    response = _client().get("/source-lens")
    assert response.status_code == 200
    return response.get_data(as_text=True)


def _panel_js():
    return (ROOT / "static" / "panel_test.js").read_text(encoding="utf-8")


def _panel_css():
    return (ROOT / "static" / "panel_test.css").read_text(encoding="utf-8")


def test_source_lens_renders_yourgov_shell():
    html = _source_lens_html()

    assert "YourGov" in html
    assert "MyGov Lens POC" not in html
    assert re.search(
        r'<section[^>]+id="yourgov-panel"[^>]+class="[^"]*\bsource-pane\b[^"]*\byourgov-panel\b[^"]*"',
        html,
    ) or re.search(
        r'<section[^>]+class="[^"]*\bsource-pane\b[^"]*\byourgov-panel\b[^"]*"[^>]+id="yourgov-panel"',
        html,
    )
    assert "/static/img/favicon.svg" in html
    assert "/static/img/yourgov-logo.svg" in html
    assert 'id="yourgov-panel"' in html
    assert 'id="map-frame"' in html
    assert 'id="source-view-select"' in html
    assert 'id="yourgov-summary-panel"' in html
    assert 'id="source-frame-panel"' in html
    assert 'id="source-summary-text"' in html
    assert 'id="source-links-list"' in html
    assert 'value="yourgov-summary"' in html
    assert 'value="publicwhip-record"' in html
    assert 'data-mode="rebel-split"' in html


def test_source_dropdown_defaults_to_yourgov_summary():
    html = _source_lens_html()

    assert re.search(
        r'<option[^>]+value="yourgov-summary"[^>]+selected[^>]*>\s*YourGov Summary\s*</option>',
        html,
    )


def test_panel_js_uses_selected_division_map_endpoint():
    js = _panel_js()

    assert "selectedDivisionId" in js
    assert "function ensureSelectedDivision" in js
    assert "function loadDivisionMapPayload" in js
    assert "function renderSourceSummary" in js
    assert "function updateSourceView" in js
    assert "/api/lens/division/" in js
    assert "/map?mode=" in js
    assert "/api/lens/map/party" not in js
    assert "/api/lens/map/gender" not in js
    assert "/api/lens/map/rebel-rate" not in js
    assert "ensurePublicWhipLoaded();" not in js


def test_publicwhip_record_loads_only_from_source_view_flow():
    js = _panel_js()

    assert "/publicwhip/division/" in js
    assert js.count("/publicwhip/division/") == 1
    update_source_view_start = js.index("function updateSourceView")
    update_source_view_end = js.index("async function ensureSelectedDivision")
    publicwhip_url_pos = js.index("/publicwhip/division/")
    assert update_source_view_start < publicwhip_url_pos < update_source_view_end
    startup = js[js.index("if (sourceViewSelect)") :]
    assert "ensurePublicWhipLoaded();" not in startup


def test_mobile_css_stacks_source_above_map_without_default_hiding():
    css = _panel_css()

    assert re.search(
        r'@media\s*\(max-width:\s*920px\)[\s\S]*?\.app-shell\s*\{[\s\S]*?grid-template-areas:\s*"source"\s*"viz"',
        css,
    )
    assert re.search(
        r'@media\s*\(max-width:\s*920px\)[\s\S]*?\.source-pane\s*\{[\s\S]*?grid-area:\s*source',
        css,
    )
    assert re.search(
        r'@media\s*\(max-width:\s*920px\)[\s\S]*?\.map-pane\s*\{[\s\S]*?grid-area:\s*viz',
        css,
    )
    assert ".source-pane:not(.active)" not in css
    assert ".map-pane:not(.active)" not in css
    assert 'body[data-mobile-view="source"] .map-pane' not in css
    assert 'body[data-mobile-view="map"]    .source-pane' not in css
