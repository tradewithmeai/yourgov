"""WCAG 2.2 AA 'NOW tier' regression tests (accessibility plan, 2026-06-30).

Covers: site-wide skip link, landing-page <main> + heading order, labelled
search input, fixed low-contrast greys, and the removed welcome auto-dismiss.
"""
import os
import sys
import re
import pathlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as appmod

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _client():
    appmod.app.config["TESTING"] = True
    return appmod.app.test_client()


def _home_html():
    # /home renders the landing template directly (/'' redirects to the UK view).
    r = _client().get("/home")
    assert r.status_code == 200
    return r.get_data(as_text=True)


def test_skip_link_injected_and_first_focusable():
    html = _home_html()
    assert 'class="yg-skip-link"' in html
    assert 'href="#main-content"' in html
    # The skip link must be the FIRST focusable element — immediately after <body>.
    assert re.search(r'<body>\s*<a href="#main-content" class="yg-skip-link"', html)


def test_skip_link_on_app_page_too():
    html = _client().get("/source-lens?cc=GB").get_data(as_text=True)
    assert 'class="yg-skip-link"' in html
    # The injector adds the target id to the existing <main>.
    assert 'id="main-content"' in html


def test_landing_has_main_landmark_and_clean_heading_order():
    html = _home_html()
    assert '<main id="main-content"' in html
    # Heading order must not skip from h1 to h3 (the feature cards are now h2).
    headings = re.findall(r"<h([1-6])\b", html)
    assert headings[0] == "1", f"first heading should be h1, got h{headings[0]}"
    assert "3" not in headings, f"no h3 should appear (was a skip): {headings}"


def test_landing_search_input_is_labelled():
    html = _home_html()
    assert '<label for="search-input"' in html
    assert 'aria-label="Search by MP name, constituency, or postcode"' in html


def test_landing_has_no_failing_contrast_greys():
    html = _home_html()
    # The AA-failing text greys were replaced with the passing #94a3b8 token.
    assert "color: #64748b" not in html
    assert "color: #475569" not in html


def test_vote_colour_text_tokens_pass_aa():
    # The --aye/--no tokens are used as small Aye/No TEXT (division rows, search
    # results, division summary). --no was #dc2626 (~3.7:1, failed AA); it must
    # now be an AA-passing red. --aye (#16a34a) already passes.
    css = (ROOT / "static" / "panel_test.css").read_text(encoding="utf-8")
    assert "--no: #dc2626" not in css
    assert "--no: #ef4444" in css

    def _ratio(fg, bg):
        def lum(h):
            h = h.lstrip("#"); rgb = [int(h[i:i+2], 16) / 255 for i in (0, 2, 4)]
            f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
            r, g, b = (f(c) for c in rgb)
            return 0.2126 * r + 0.7152 * g + 0.0722 * b
        l1, l2 = lum(fg), lum(bg)
        return (max(l1, l2) + 0.05) / (min(l1, l2) + 0.05)

    # Both vote-text colours clear 4.5:1 against the page and panel backgrounds.
    for colour in ("#16a34a", "#ef4444"):
        for bg in ("#0b1020", "#111827"):
            assert _ratio(colour, bg) >= 4.5, f"{colour} on {bg} fails AA"


def test_welcome_overlay_has_no_auto_dismiss_timer():
    html = _home_html()
    # A timed auto-close of the welcome modal is a WCAG 2.2.1 timing barrier.
    assert "}, 1600)" not in html
    assert "welcome-fill" not in html  # the countdown progress animation is gone
