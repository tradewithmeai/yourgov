"""Unit tests for request-derived helpers (locale, country, direction,
autopilot) and the click-metadata division-id parser.

These shape i18n/layout and how the explainer reads untrusted client click
metadata, so their fallbacks matter. Each runs inside a real Flask request
context so the helpers see genuine args/headers.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as appmod


def _req(path="/", headers=None):
    return appmod.app.test_request_context(path, headers=headers or {})


# ── resolve_locale ────────────────────────────────────────────────────────

def test_locale_query_override_wins():
    with _req("/?lang=hi") as ctx:
        assert appmod.resolve_locale(ctx.request) == "hi"


def test_locale_from_accept_language_when_no_override():
    with _req("/", headers={"Accept-Language": "hi-IN,hi;q=0.9,en;q=0.8"}) as ctx:
        assert appmod.resolve_locale(ctx.request) == "hi"


def test_locale_defaults_to_en():
    with _req("/") as ctx:
        assert appmod.resolve_locale(ctx.request) == "en"
    with _req("/?lang=zz") as ctx:
        assert appmod.resolve_locale(ctx.request) == "en"


# ── resolve_country_code ──────────────────────────────────────────────────

def test_country_query_override():
    with _req("/?cc=gb") as ctx:
        assert appmod.resolve_country_code(ctx.request) == "GB"


def test_country_unknown_falls_back_to_gb():
    with _req("/?cc=zzz") as ctx:
        assert appmod.resolve_country_code(ctx.request) == "GB"


def test_country_defaults_to_gb():
    with _req("/") as ctx:
        assert appmod.resolve_country_code(ctx.request) == "GB"


# ── resolve_dir ───────────────────────────────────────────────────────────

def test_dir_rtl_for_arabic_override_even_though_untranslated():
    with _req("/?lang=ar") as ctx:
        assert appmod.resolve_dir(ctx.request) == "rtl"


def test_dir_ltr_default():
    with _req("/") as ctx:
        assert appmod.resolve_dir(ctx.request) == "ltr"
    with _req("/?lang=en") as ctx:
        assert appmod.resolve_dir(ctx.request) == "ltr"


# ── _autopilot_requested ──────────────────────────────────────────────────

def test_autopilot_flag():
    with _req("/?autopilot=1") as ctx:
        assert appmod._autopilot_requested(ctx.request) is True
    with _req("/?autopilot=0") as ctx:
        assert appmod._autopilot_requested(ctx.request) is False
    with _req("/") as ctx:
        assert appmod._autopilot_requested(ctx.request) is False


# ── _division_id_from_metadata (parses untrusted client click metadata) ────

def test_division_id_direct_field():
    assert appmod._division_id_from_metadata({"division_id": "2394"}) == 2394
    assert appmod._division_id_from_metadata({"division_id": 2394}) == 2394


def test_division_id_from_nested_state():
    meta = {"yourgov_state": {"selected_division": {"division_id": "17"}}}
    assert appmod._division_id_from_metadata(meta) == 17


def test_division_id_direct_field_takes_priority():
    meta = {
        "division_id": "1",
        "yourgov_state": {"selected_division": {"division_id": "2"}},
    }
    assert appmod._division_id_from_metadata(meta) == 1


def test_division_id_missing_or_garbage_returns_none():
    assert appmod._division_id_from_metadata({}) is None
    assert appmod._division_id_from_metadata({"division_id": "not-a-number"}) is None
    assert appmod._division_id_from_metadata({"division_id": None}) is None
    assert appmod._division_id_from_metadata({"yourgov_state": "not-a-dict"}) is None
    assert appmod._division_id_from_metadata(
        {"yourgov_state": {"selected_division": {"division_id": "x"}}}
    ) is None


# ── _norm_title (fuzzy title-match normaliser) ────────────────────────────

def test_norm_title_strips_punctuation_and_casing():
    assert appmod._norm_title("Health & Care Bill: Second Reading") == "health care bill second reading"


def test_norm_title_handles_none_and_empty():
    assert appmod._norm_title(None) == ""
    assert appmod._norm_title("   ") == ""
