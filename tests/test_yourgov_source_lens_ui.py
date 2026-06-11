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


def _static_text(path):
    response = _client().get(path)
    assert response.status_code == 200
    return response.get_data(as_text=True)


def _panel_js():
    return (ROOT / "static" / "panel_test.js").read_text(encoding="utf-8")


def _panel_css():
    return (ROOT / "static" / "panel_test.css").read_text(encoding="utf-8")


def _function_body(js, name):
    match = re.search(rf"function\s+{re.escape(name)}\s*\([^)]*\)\s*\{{", js)
    assert match, f"{name} function not found"
    depth = 1
    i = match.end()
    in_string = None
    escaped = False
    while i < len(js):
        ch = js[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == in_string:
                in_string = None
        elif ch in ("'", '"', "`"):
            in_string = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return js[match.end() : i]
        i += 1
    raise AssertionError(f"{name} function body not closed")


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


def test_map_payload_loads_use_request_sequence_guards():
    js = _panel_js()
    set_map_mode = _function_body(js, "setMapMode")
    visualise_division = _function_body(js, "visualiseDivision")

    assert "var mapPayloadRequestSeq" in js
    assert "function nextMapPayloadRequest" in js
    assert "function isCurrentMapPayloadRequest" in js

    assert re.search(
        r"nextMapPayloadRequest\(\)[\s\S]*await\s+loadDivisionMapPayload\([^)]*requestToken[^)]*\)"
        r"[\s\S]*isCurrentMapPayloadRequest\(requestToken\)",
        set_map_mode,
    )
    assert re.search(
        r"await\s+loadDivisionMapPayload\([^)]*requestToken[^)]*\)[\s\S]*selectedMapMode\s*!==\s*mode",
        set_map_mode,
    )

    assert re.search(
        r"nextMapPayloadRequest\(\)[\s\S]*await\s+loadDivisionMapPayload\([^)]*requestToken[^)]*\)"
        r"[\s\S]*isCurrentMapPayloadRequest\(requestToken\)",
        visualise_division,
    )
    assert re.search(
        r"await\s+loadDivisionMapPayload\([^)]*requestToken[^)]*\)[\s\S]*selectedDivisionId\s*!==\s*intendedDivisionId",
        visualise_division,
    )


def test_publicwhip_dropdown_without_division_stays_on_visible_summary_warning():
    js = _panel_js()
    update_source_view = _function_body(js, "updateSourceView")

    assert re.search(
        r"selectedSourceView\s*===\s*['\"]publicwhip-record['\"][\s\S]*?!selectedDivisionId"
        r"[\s\S]*?selectedSourceView\s*=\s*['\"]yourgov-summary['\"]"
        r"[\s\S]*?sourceViewSelect\.value\s*=\s*['\"]yourgov-summary['\"]",
        update_source_view,
    )
    assert re.search(
        r"selectedSourceView\s*===\s*['\"]publicwhip-record['\"][\s\S]*?!selectedDivisionId"
        r"[\s\S]*?(setStatus|sourceSummary\.textContent|sourceSummary\.appendChild)",
        update_source_view,
    )
    assert re.search(r"yourgovSummaryPanel\)\s+yourgovSummaryPanel\.hidden\s*=\s*false", update_source_view)
    assert re.search(r"sourceFramePanel\)\s+sourceFramePanel\.hidden\s*=\s*true", update_source_view)


def test_mobile_toolbar_scrolls_to_stacked_sections():
    js = _panel_js()
    mobile_toolbar = _function_body(js, "setupMobileToolbar")

    assert "function scrollToMobileSection" in mobile_toolbar
    assert re.search(r"scrollToMobileSection\(['\"]source['\"]\)", mobile_toolbar)
    assert re.search(r"scrollToMobileSection\(['\"]map['\"]\)", mobile_toolbar)
    assert re.search(r"scrollToMobileSection\(['\"]visualise['\"]\)", mobile_toolbar)
    assert "#yourgov-panel" in mobile_toolbar
    assert "#visualisation-panel" in mobile_toolbar or ".map-pane" in mobile_toolbar


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


def test_yourgov_static_svg_assets_are_served():
    assets = {
        "/static/img/favicon.svg": (),
        "/static/img/yourgov-logo.svg": ("yourgov",),
        "/static/img/yourgov-mark.svg": ("yourgov", "yg"),
    }

    for path, required_fragments in assets.items():
        body = _static_text(path)
        normalised = body.lower()
        assert "<svg" in normalised
        assert "crown" not in normalised
        assert "gov.uk" not in normalised
        if required_fragments:
            assert any(fragment in normalised for fragment in required_fragments)
