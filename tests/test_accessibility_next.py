"""WCAG 2.2 AA 'NEXT tier' regression tests (accessibility plan):
- Explain Mode drawer is a real modal dialog with focus management + live region.
- Division-summary dialog manages focus.
- Public /accessibility page exists and invites disabled users to say what they need.
- The drawer close button meets the 24x24 target-size minimum.
"""
import os
import sys
import pathlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as appmod

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _client():
    appmod.app.config["TESTING"] = True
    return appmod.app.test_client()


def _explain_js():
    return (ROOT / "static" / "explain-mode.js").read_text(encoding="utf-8")


def _panel_js():
    return (ROOT / "static" / "panel_test.js").read_text(encoding="utf-8")


def test_explain_drawer_is_a_real_dialog():
    js = _explain_js()
    assert "setAttribute('role', 'dialog')" in js
    assert "setAttribute('aria-modal', 'true')" in js
    assert "aria-labelledby" in js
    assert "explain-drawer-title" in js
    # The title is a heading, the follow-up input is labelled, body is a live region.
    assert "<h2 id=\"explain-drawer-title\"" in js
    assert 'for="explain-followup-input"' in js
    assert "aria-live=\"polite\"" in js


def test_explain_drawer_has_focus_management_and_escape():
    js = _explain_js()
    # Focus is moved in, trapped, returned, and Escape closes.
    assert "_drawerPrevFocus" in js
    assert "_drawerFocusables" in js
    assert "e.key === 'Escape'" in js
    assert "closeDrawer()" in js
    # Returns focus to the trigger on close.
    assert "_drawerPrevFocus.focus" in js


def test_division_summary_dialog_manages_focus():
    js = _panel_js()
    assert "_divSummaryPrevFocus" in js
    # Moves focus to the Back control on open, returns to the row on close.
    assert "divisionSummaryClose) divisionSummaryClose.focus()" in js
    assert "_divSummaryPrevFocus = row" in js


def test_accessibility_page_exists_and_invites_feedback():
    r = _client().get("/accessibility")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "WCAG 2.2 AA" in html
    assert "Tell us what you need" in html
    assert "/feedback" in html
    assert 'id="main-content"' in html        # skip-link target
    # Discoverable from the intro panel.
    assert "/accessibility" in _panel_js()


def test_drawer_close_button_meets_target_size():
    css = (ROOT / "static" / "explain-mode.css").read_text(encoding="utf-8")
    import re
    block = re.search(r"#explain-drawer-close\s*\{[^}]*\}", css).group(0)
    assert "min-width: 24px" in block
    assert "min-height: 24px" in block
