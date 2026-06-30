"""Regression tests for the rebel/party-majority convergence + gender-map fix
(quality sweep DO-CAREFULLY correctness items).

The map (app._party_majorities_for_division) and the explainer
(explainer_context.build_division_summary) previously computed "who rebelled"
differently: the map excluded Independents, the explainer did not. Both now go
through explainer_context.party_majorities, so they agree. The gender map route
previously only accepted literal 'M'/'F'; it now uses the canonical normaliser.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as appmod
import explainer_context as ec


def _rows(*triples):
    # (party, voted_aye) rows shaped like the DB query (dict access).
    return [{"party": p, "voted_aye": v, "name": n} for (n, p, v) in triples]


def test_party_majorities_excludes_non_whipped_labels():
    rows = _rows(
        ("a", "Labour", 1), ("b", "Labour", 1), ("c", "Labour", 0),   # Lab 2-1 -> Aye (>=60%)
        ("d", "Independent", 1), ("e", "Independent", 0),             # excluded
        ("f", "Unknown", 1),                                         # excluded
        ("g", "", 1),                                                # excluded
    )
    maj = ec.party_majorities(rows)
    assert maj == {"Labour": 1}
    assert "Independent" not in maj and "Unknown" not in maj and "" not in maj


def test_party_majority_threshold_no_clear_position():
    # 1-1 is below the 60% threshold -> no position, nobody is a rebel.
    rows = _rows(("a", "Green", 1), ("b", "Green", 0))
    assert ec.party_majorities(rows) == {}


def test_map_and_explainer_use_the_same_helper():
    # The map's helper now delegates to the shared one — identical results,
    # including the Independent exclusion that used to differ.
    rows = _rows(
        ("a", "Con", 1), ("b", "Con", 1), ("c", "Con", 1),
        ("d", "Independent", 0), ("e", "Independent", 0),
    )
    assert appmod._party_majorities_for_division(rows) == ec.party_majorities(rows)
    assert appmod._party_majorities_for_division(rows) == {"Con": 1}


def test_is_whipped_party():
    assert ec.is_whipped_party("Labour") is True
    for p in ("Independent", "independent", "Unknown", "", None, "  "):
        assert ec.is_whipped_party(p) is False


def test_gender_normaliser_accepts_full_words_and_casing():
    import json
    f = appmod._member_gender_from_posts
    assert f(json.dumps({"gender": "Male"})) == "M"
    assert f(json.dumps({"gender": "female"})) == "F"
    assert f(json.dumps({"gender": "M"})) == "M"
    assert f(json.dumps({"gender": "f"})) == "F"
    assert f(json.dumps({"gender": "x"})) == "Unknown"
    assert f(json.dumps({})) == "Unknown"


def test_gender_map_route_uses_canonical_normaliser():
    # The route source must call the helper, not re-implement an uppercase-only
    # check (which mislabelled 'male'/'female' as Unknown).
    import pathlib
    src = (pathlib.Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
    route = src[src.index("def api_lens_map_gender"):src.index("def ", src.index("def api_lens_map_gender") + 10)]
    assert "_member_gender_from_posts(row[" in route
    assert 'posts.get("gender")' not in route  # the inline extraction is gone
