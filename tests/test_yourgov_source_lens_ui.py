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


def _tour_js():
    return (ROOT / "static" / "tour.js").read_text(encoding="utf-8")


def _global_globe_js():
    return (ROOT / "static" / "global_globe.js").read_text(encoding="utf-8")


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


def _tag_with_id(html, tag_name, element_id):
    match = re.search(
        rf"<{tag_name}\b(?=[^>]*\bid=\"{re.escape(element_id)}\")[^>]*>",
        html,
    )
    assert match, f"{element_id} {tag_name} tag not found"
    return match.group(0)


def test_source_lens_renders_yourgov_shell():
    html = _source_lens_html()

    assert "YourGov" in html
    assert "MyGov Lens POC" not in html
    assert 'data-default-source="publicwhip"' not in html
    assert "data-default-source" not in html
    assert re.search(
        r'<section[^>]+id="yourgov-panel"[^>]+class="[^"]*\bsource-pane\b[^"]*\byourgov-panel\b[^"]*"',
        html,
    ) or re.search(
        r'<section[^>]+class="[^"]*\bsource-pane\b[^"]*\byourgov-panel\b[^"]*"[^>]+id="yourgov-panel"',
        html,
    )
    assert "/static/img/favicon.svg" in html
    assert 'id="yourgov-panel"' in html
    assert 'id="map-frame"' in html
    # Single search lives in the centre "S" widget; the native division summary
    # opens on double-click. The old source-view dropdown / PublicWhip frame /
    # always-on summary panel are gone.
    assert 'id="map-search"' in html
    assert 'id="division-summary"' in html
    assert 'id="division-summary-body"' in html
    assert 'id="source-view-select"' not in html
    assert 'id="yourgov-summary-panel"' not in html
    assert 'id="source-frame-panel"' not in html
    assert 'value="publicwhip-record"' not in html
    assert 'data-mode="rebel-split"' in html


def test_yourgov_guided_route_public_copy_replaces_source_lens_journey_copy():
    html = _source_lens_html()

    assert "<title>YourGov</title>" in html
    # Brand header and the labelled left-panel search were removed; the page
    # leads with the MP voting record and uses the centre "S" search widget.
    assert "YourGov UK" not in html
    # "Search by postcode, constituency, or MP name" now appears only as
    # onboarding-tour guidance — never as a labelled left-panel search
    # input/placeholder (the old journey copy).
    assert 'placeholder="Search by postcode' not in html
    assert 'id="map-search"' in html
    assert "YourGov Source Lens" not in html
    assert "First-party source lens" not in html


def test_global_entry_opens_yourgov_without_publicwhip_source_param():
    js = _global_globe_js()

    assert "source=lens" not in js
    assert "return `/source-lens?cc=${cc}&lang=${lang}`;" in js


def test_yourgov_left_panel_starts_as_search_journey_not_publicwhip_feed():
    html = _source_lens_html()
    js = _panel_js()

    assert "Use the search on the map to find your MP and see their voting record." in html
    assert "function renderMPSearchPrompt" in js
    startup = js[js.index("updateSourceView();") : js.index("setVisualise(true);")]
    assert "renderMPSearchPrompt();" in startup
    assert "loadSourceDivisions();" not in startup


def test_yourgov_frozen_mp_info_card_with_contact():
    html = _source_lens_html()
    js = _panel_js()
    css = _panel_css()

    # The frozen MP info card lives ABOVE the scrolling voting record.
    assert 'id="mp-info-card"' in html
    assert "function renderMPInfoCard" in js
    card = _function_body(js, "renderMPInfoCard")
    # Identity + the Contact action (the end of the find-MP-then-email flow).
    assert "mp-info-contact" in card
    assert "writetothem.com/who?pc=" in card        # postcode path -> email flow
    assert "members.parliament.uk/member/" in card  # name path -> official contact page
    assert "data-explainable" not in card or "explainable" in card  # explain hook on the card
    # The card is frozen: it does not grow/scroll with the record list.
    assert re.search(r"\.mp-info-card\s*\{[\s\S]*?flex:\s*0 0 auto", css)
    # The voting record still renders into the scrolling list.
    assert "function renderMPVotingRecord" in js


def test_yourgov_first_load_panel_shows_intro():
    js = _panel_js()
    prompt = _function_body(js, "renderMPSearchPrompt")
    # The first-load panel introduces the site (logo + what it does + the
    # agent-friendly repo + the feedback route + the Explain function), rather
    # than showing a bare one-line search prompt.
    assert "yg-intro" in prompt
    assert "yourgov-logo.svg" in prompt
    assert "github.com/tradewithmeai/mygov" in prompt
    assert "/feedback" in prompt
    assert "Explain" in prompt


def test_yourgov_search_uses_inline_autocomplete_not_result_dropdown():
    html = _source_lens_html()
    js = _panel_js()
    css = _panel_css()

    # Search now lives in the centre "S" widget (map-search-form), not a labelled
    # left-panel form.
    assert 'id="mp-search-form" class="map-search-form" autocomplete="off"' in html
    assert 'id="mp-search-input"' in html
    assert 'aria-autocomplete="inline"' in html
    assert 'id="search-results" class="search-results" hidden' in html

    render_search_results = _function_body(js, "renderSearchResults")
    assert "searchResultsEl.removeAttribute('hidden')" not in render_search_results
    assert "search-result-item" not in render_search_results
    assert "function renderInlineSearchSuggestion" in js

    # The dropdown result list stays collapsed/hidden in the widget; suggestions
    # are inline.
    assert re.search(
        r"\.map-search\.is-collapsed\s+\.search-results\s*\{[\s\S]*?display:\s*none",
        css,
    )


def test_yourgov_search_postcode_result_can_be_accepted_without_dropdown():
    js = _panel_js()

    assert "function suggestionTailForResult" in js
    assert "result.match_type === 'postcode'" in js
    assert "result.constituency" in js
    assert "function selectSearchMPData" in js
    assert "function hasCurrentTopSuggestion" in js
    assert "searchMPs(mpSearchInput.value, { acceptSingle: true })" in js
    assert "options.acceptSingle" in js


def test_yourgov_search_completes_partial_postcode_inline():
    js = _panel_js()

    # A partial postcode completes inline (as ghost text in the bar, NOT a
    # dropdown) via /api/postcode/autocomplete, and accepting it resolves the
    # postcode to its MP.
    assert "function looksLikePartialPostcode" in js
    assert "function postcodeTail" in js
    assert "/api/postcode/autocomplete?q=" in js
    assert "function acceptCurrentSuggestion" in js
    accept = _function_body(js, "acceptCurrentSuggestion")
    assert "hasCurrentTopPostcode()" in accept
    assert "/api/mps/search?q=" in accept
    assert "selectSearchMPData" in accept


def test_onboarding_tour_teaches_the_search_first_flow():
    html = _source_lens_html()
    tour = _tour_js()

    # Tour copy follows the real journey: find your MP (search) → read the
    # record + contact → switch the map view. The stale "select your country" /
    # "pick in the source panel" copy is gone.
    assert "Find your MP" in html
    assert "See how they voted" in html
    assert "Contact button to email them" in html
    assert "colours your country by what you selected" not in html
    assert "Pick a vote, MP, or party in the source panel" not in html
    # Step 1 spotlights the centre search; the dead #source-frame iframe demo
    # (the frame no longer exists) is gone.
    assert "'#map-search'" in tour
    assert "source-frame" not in tour


def test_map_relay_hides_promap_developer_placeholder_panel():
    # The promap bundle's top-right "Explore / Hover for names" panel is a
    # developer placeholder; we use our own left panel, so the relay hides the
    # whole .mygov-constituency-panel (hiding only the inner empty card left an
    # empty rounded box in the top-right corner).
    relay = _static_text("/map/relay")
    assert re.search(r"\.mygov-constituency-panel\s*\{[^}]*display:\s*none", relay)


def test_tour_cards_stay_on_the_same_half_as_their_target_panel():
    js = _tour_js()

    assert "panelSide: 'map'" in js
    assert "panelSide: 'source'" in js
    assert "function placeCard(rect, step)" in js
    assert "step.panelSide === 'map'" in js
    assert "step.panelSide === 'source'" in js


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


def test_panel_js_discloses_vote_record_completeness():
    js = _panel_js()

    # The MP record requests the full history, pages the display at 50 with an
    # expand control, and derives the count from the FULL total (total_votes),
    # never the displayed subset.
    assert "/votes?limit=2000" in js
    assert "recorded votes" in js
    assert "total_votes" in js
    assert "INITIAL_VISIBLE = 50" in js
    assert "division-expand-btn" in js
    assert "record_status" in js


def test_explain_context_includes_yourgov_selected_state():
    js = _panel_js()
    explain_js = (ROOT / "static" / "explain-mode.js").read_text(encoding="utf-8")

    assert "function getYourGovExplainState" in js
    assert "selected_mp" in js
    assert "selected_division" in js
    assert "active_map_mode" in js
    assert "window.__YOURGOV_EXPLAIN_STATE__" in js
    assert "__YOURGOV_EXPLAIN_STATE__" in explain_js


def test_panel_mutation_observers_require_real_dom_nodes():
    js = _panel_js()

    assert "bodyNode.nodeType === 1" in js
    assert "bodyObserver.observe(bodyNode" in js
    assert "explainObserverTarget.nodeType === 1" in js


def test_map_mode_buttons_render_as_synced_radios():
    html = _source_lens_html()

    expected = {
        "topic-vote-split": "true",
        "topic-party-split": "false",
        "topic-gender-split": "false",
        "topic-rebel-rate": "false",
    }

    for element_id, checked in expected.items():
        button = _tag_with_id(html, "button", element_id)
        assert 'role="radio"' in button
        assert f'aria-checked="{checked}"' in button


def test_set_topic_active_syncs_radio_aria_checked():
    js = _panel_js()
    set_topic_active = _function_body(js, "setTopicActive")

    assert re.search(r"\.setAttribute\(\s*['\"]aria-checked['\"]", set_topic_active)
    assert "b === activeBtn" in set_topic_active
    assert "'true'" in set_topic_active
    assert "'false'" in set_topic_active


def test_source_status_is_polite_status_live_region():
    html = _source_lens_html()

    source_status = _tag_with_id(html, "span", "source-status")
    assert 'aria-live="polite"' in source_status
    assert 'role="status"' in source_status


def test_load_source_divisions_does_not_interpolate_error_html():
    js = _panel_js()
    load_source_divisions = _function_body(js, "loadSourceDivisions")

    assert not re.search(r"innerHTML\s*=\s*[^\n;]*err\.message", load_source_divisions)


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


def test_map_relay_promap_bundle_observes_dom_node_for_modulepreload():
    response = _client().get("/map/relay")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    script = re.search(
        r'<script[^>]+src="([^"]*static/promap/assets/index-[^"]+\.js(?:\?v=\d+)?)"',
        html,
    )
    assert script, "map relay Promap script not found"

    bundle = _static_text(script.group(1))

    assert ".observe(document,{childList" not in bundle
    assert ".observe(document.documentElement||document.body" in bundle


def test_map_relay_promap_assets_are_cache_busted():
    response = _client().get("/map/relay")
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    script = re.search(r'src="([^"]*/static/promap/assets/(index-[^"]+\.js))\?v=(\d+)"', html)
    stylesheet = re.search(r'href="([^"]*/static/promap/assets/(index-[^"]+\.css))\?v=(\d+)"', html)
    assert script
    assert stylesheet
    assert script.group(3) == str((ROOT / "static" / "promap" / "assets" / script.group(2)).stat().st_mtime_ns)
    assert stylesheet.group(3) == str(
        (ROOT / "static" / "promap" / "assets" / stylesheet.group(2)).stat().st_mtime_ns
    )


def test_division_summary_is_native_not_publicwhip():
    """Double-clicking a division opens a first-party YourGov summary overlay,
    not the retired PublicWhip page."""
    js = _panel_js()

    assert "function renderDivisionSummary" in js
    open_div_summary = _function_body(js, "openDivisionSummary")
    assert "renderDivisionSummary(" in open_div_summary
    assert "divisionSummary.hidden = false" in open_div_summary
    # The summary no longer loads the PublicWhip page in an iframe.
    assert "openInSourcePane" not in open_div_summary
    # ...and it never calls PublicWhip auto-load on startup.
    assert "ensurePublicWhipLoaded();" not in js


def test_nav_ring_does_not_default_to_publicwhip_source():
    js = _panel_js()
    nav_ring = _function_body(js, "setupNavRing")

    assert "lens:   '/publicwhip'" not in nav_ring
    assert "SOURCE_FOR_VIEW.lens" not in nav_ring
    assert "function activateYourGovSource" in nav_ring
    assert "sourceViewSelect.value = 'yourgov-summary'" in nav_ring
    assert "frame.setAttribute('src', 'about:blank')" in nav_ring


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


def test_service_menu_body_observer_is_guarded():
    js = _panel_js()

    assert "var bodyNode = document.body;" in js
    assert re.search(r"bodyNode\s*&&\s*bodyNode\.nodeType\s*===\s*1", js)
    assert "bodyObserver.observe(bodyNode" in js


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


def test_mobile_toolbar_body_observer_is_guarded():
    js = _panel_js()
    mobile_toolbar = _function_body(js, "setupMobileToolbar")

    assert "var explainObserverTarget = document.body;" in mobile_toolbar
    assert re.search(r"explainObserverTarget\s*&&\s*explainObserverTarget\.nodeType\s*===\s*1", mobile_toolbar)
    assert "new MutationObserver(syncExplainState).observe(" in mobile_toolbar
    assert "explainObserverTarget, { attributes: true, attributeFilter: ['class'] }" in mobile_toolbar


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


def test_desktop_css_locks_split_view_to_viewport():
    css = _panel_css()

    assert re.search(
        r"@media\s*\(min-width:\s*921px\)[\s\S]*?\.lens-poc\.app-shell\s*\{"
        r"[\s\S]*?height:\s*100vh"
        r"[\s\S]*?overflow:\s*hidden",
        css,
    )
    assert re.search(
        r"@media\s*\(min-width:\s*921px\)[\s\S]*?\.lens-poc\.app-shell\s*>\s*\.map-pane"
        r"[\s\S]*?\.lens-poc\.app-shell\s*>\s*\.source-pane\s*\{"
        r"[\s\S]*?height:\s*100%",
        css,
    )
    assert re.search(
        r"@media\s*\(min-width:\s*921px\)[\s\S]*?\.lens-poc\.app-shell\s*>\s*\.map-pane\s*>\s*\.map-wrap\s*\{"
        r"[\s\S]*?height:\s*100%",
        css,
    )


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
