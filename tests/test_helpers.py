"""Unit tests for pure helper functions in app.py.

These are fast, deterministic, and don't touch the DB or network. They lock in
the behaviour of the small functions that shape coverage messaging, map colours,
mode normalisation, vote labels, issue slugs, and the empty-record explanations.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as appmod


# ── _compute_coverage ─────────────────────────────────────────────────────

def test_coverage_good_at_ten_votes():
    cov = appmod._compute_coverage(10, 0, None)
    assert cov["status"] == "good"
    assert cov["show_spotlight"] is True and cov["show_pledges"] is True


def test_coverage_partial_with_some_activity():
    cov = appmod._compute_coverage(3, 0, "2026-01-01")
    assert cov["status"] == "partial"
    assert cov["show_spotlight"] is True and cov["show_pledges"] is False
    # questions alone also count as partial
    assert appmod._compute_coverage(0, 2, None)["status"] == "partial"


def test_coverage_api_mismatch_when_ingest_ran_but_empty():
    cov = appmod._compute_coverage(0, 0, "2026-01-01T00:00:00Z")
    assert cov["status"] == "possible_api_mismatch"
    assert cov["show_spotlight"] is False


def test_coverage_not_loaded_when_never_ingested():
    cov = appmod._compute_coverage(0, 0, None)
    assert cov["status"] == "not_loaded"
    assert cov["show_spotlight"] is False


# ── _hex_lerp ─────────────────────────────────────────────────────────────

def test_hex_lerp_endpoints_and_midpoint():
    assert appmod._hex_lerp("#000000", "#ffffff", 0.0) == "#000000"
    assert appmod._hex_lerp("#000000", "#ffffff", 1.0) == "#ffffff"
    assert appmod._hex_lerp("#000000", "#ffffff", 0.5) == "#7f7f7f"


def test_hex_lerp_clamps_out_of_range_t():
    assert appmod._hex_lerp("#000000", "#ffffff", -5.0) == "#000000"
    assert appmod._hex_lerp("#000000", "#ffffff", 5.0) == "#ffffff"


def test_hex_lerp_invalid_input_falls_back_to_black():
    assert appmod._hex_lerp("nothex", "#ffffff", 0.5) == "#000000"
    assert appmod._hex_lerp(None, None, 0.5) == "#000000"


# ── _normalise_division_map_mode ──────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("vote", "vote-split"),
    ("votes", "vote-split"),
    ("PARTY", "party-split"),
    ("gender_split", "gender-split"),
    ("rebel", "rebel-split"),
    ("rebel-rate", "rebel-split"),
    ("  Vote-Split  ", "vote-split"),
    (None, "vote-split"),
])
def test_normalise_mode_known_aliases(raw, expected):
    assert appmod._normalise_division_map_mode(raw) == expected


def test_normalise_mode_unknown_returns_none():
    assert appmod._normalise_division_map_mode("nonsense") is None


# ── _vote_label ───────────────────────────────────────────────────────────

def test_vote_label():
    assert appmod._vote_label(1) == "Aye"
    assert appmod._vote_label(0) == "No"
    assert appmod._vote_label(None) == "Absent/unknown"
    assert appmod._vote_label(2) == "Absent/unknown"


# ── topic <-> slug ────────────────────────────────────────────────────────

def test_topic_slug_round_trip_for_every_real_topic():
    for topic in appmod.ISSUE_TOPICS:
        slug = appmod.topic_to_slug(topic)
        assert " " not in slug and slug == slug.lower()
        assert appmod.slug_to_topic(slug) == topic


def test_slug_to_topic_unknown_is_none():
    assert appmod.slug_to_topic("not-a-real-topic") is None


# ── _mp_empty_record_status ───────────────────────────────────────────────

def test_empty_record_speaker():
    assert appmod._mp_empty_record_status("Speaker")["code"] == "speaker"


def test_empty_record_deputy_speaker_from_posts():
    posts = json.dumps({"posts": "Deputy Speaker of the House"})
    assert appmod._mp_empty_record_status("Labour", posts)["code"] == "deputy_speaker"


def test_empty_record_sinn_fein_abstentionist():
    assert appmod._mp_empty_record_status("Sinn Féin")["code"] == "abstentionist"
    assert appmod._mp_empty_record_status("Sinn Fein")["code"] == "abstentionist"


def test_empty_record_default():
    assert appmod._mp_empty_record_status("Labour")["code"] == "no_recorded_votes"
